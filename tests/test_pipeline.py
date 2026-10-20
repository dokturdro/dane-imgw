"""Cleaning, derived daily means and climate summaries on a throwaway DuckDB."""

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from imgw import clean, climate, db, derive
from imgw.config import Config


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "t.duckdb")
    yield c
    c.close()


def test_snow_and_wind_codes():
    df = pd.DataFrame({
        "imgw_id": ["1"] * 4, "ts": pd.date_range("2026-01-01", periods=4, freq="h"),
        "PKSN": [997.0, 998.0, 999.0, 12.0], "KRWR": [999.0, 0.0, 180.0, 90.0],
        "FWR": [2.0, 0.0, 3.0, 1.0],
    })
    out = clean.hourly_obs(df, "s_t")
    assert out.snow_depth.tolist()[0] == 0.25
    assert out.snow_depth.isna().tolist() == [False, True, True, False]
    assert out.snow_depth_code.tolist()[:3] == ["trace", "patchy", "unmeasurable"]
    assert out.wind_dir_variable.tolist() == [True, False, False, False]
    assert np.isnan(out.wind_dir.iloc[0])
    assert out.calm.tolist() == [False, True, False, False]


def test_replace_rows_is_idempotent(con):
    df = pd.DataFrame({"imgw_id": ["1", "1"], "date": [date(2026, 1, 1), date(2026, 1, 2)],
                       "source": "synop", "tm": [1.0, 2.0]})
    con.execute("BEGIN"); db.replace_rows(con, "daily_obs", df); con.execute("COMMIT")
    df.loc[0, "tm"] = 5.0
    con.execute("BEGIN"); db.replace_rows(con, "daily_obs", df); con.execute("COMMIT")
    assert con.execute("SELECT count(*), sum(tm) FROM daily_obs").fetchone() == (2, 7.0)


def test_derived_means_use_8_terms_and_round_half_up(con):
    ts = [datetime(2026, 8, 25) + timedelta(hours=h) for h in range(24)]
    # 3-hourly terms average to exactly 1.25; off-term hours are noise that must be ignored
    cc = [1.0 if h % 3 == 0 and h < 12 else 1.5 if h % 3 == 0 else 8.0 for h in range(24)]
    df = pd.DataFrame({"imgw_id": "1", "ts": ts, "source": "synop", "vapp": cc,
                       "cloud_cover": cc, "wind_speed": cc})
    con.execute("BEGIN"); db.replace_rows(con, "hourly_obs", df); con.execute("COMMIT")
    db.replace_rows(con, "daily_obs", pd.DataFrame(
        {"imgw_id": ["1"], "date": [date(2026, 8, 25)], "source": ["synop"], "tm": [10.0]}))
    derive.rebuild_daily_agg(con)
    row = con.execute("SELECT cloud_cover, vapp, wind_speed FROM v_daily").fetchone()
    assert row == (1.3, 1.3, 1.3)


def test_live_daily_requires_coverage(con):
    base = datetime(2026, 10, 16, 18, 10)
    rows = [dict(imgw_id="352200375", station_key="352200375", network="telemetry",
                 ts=base + timedelta(minutes=10 * i), variable="temperatura_powietrza",
                 value=float(i % 20), fetched_at=base) for i in range(144)]
    db.insert_df(con, "live_obs", pd.DataFrame(rows))
    r = con.execute("SELECT tx, tn FROM v_live_daily WHERE date = '2026-10-17'").fetchone()
    assert r == (19.0, 0.0)
    # same window with only 50 samples -> no provisional extremes
    con.execute("DELETE FROM live_obs WHERE ts > ?", [base + timedelta(minutes=500)])
    assert con.execute("SELECT tx FROM v_live_daily WHERE date = '2026-10-17'").fetchone()[0] is None


def _daily_frame(start: date, days: int, tm, tx=None, tn=None, prcp=0.0):
    d = [start + timedelta(days=i) for i in range(days)]
    return pd.DataFrame({"imgw_id": "1", "date": d, "source": "synop", "tm": tm,
                         "tx": tx if tx is not None else np.asarray(tm) + 5,
                         "tn": tn if tn is not None else np.asarray(tm) - 5, "prcp": prcp})


def test_monthly_summary_values(con):
    tm = [10.0] * 10 + [20.0] * 10 + [float("nan")] * 11  # 31-day month, 11 missing
    db.replace_rows(con, "daily_obs", _daily_frame(date(2026, 7, 1), 31, tm, prcp=1.0))
    climate.rebuild_all(con, Config())
    got = dict(con.execute("""SELECT variable, value FROM monthly_summary
                              WHERE year = 2026 AND month = 7""").fetchall())
    assert got["tm"] == 15.0
    assert got["prcp"] == 31.0
    assert got["txgt25"] == 10            # tx = 25 on the 20 °C days
    assert got["cdd"] == pytest.approx(20.0)   # 10 days × (20 - 18)
    assert got["hdd"] == pytest.approx(80.0)   # 10 days × (18 - 10)
    assert got["gdd"] == pytest.approx(100.0)  # 10 days × (20 - 10)
    m = con.execute("""SELECT days_missing, is_partial FROM v_monthly
                       WHERE variable = 'tm' AND year = 2026 AND month = 7""").fetchone()
    assert m == (11, True)


def test_percentile_classes_like_meteomodel(con):
    # 20 Julys with tm = 1..20: linear P5=1.95 ... P40=8.6, P60=12.4 ... P95=19.05
    for i, y in enumerate(range(2001, 2021), start=1):
        db.replace_rows(con, "daily_obs", _daily_frame(date(y, 7, 1), 31, [float(i)] * 31))
    climate.rebuild_all(con, Config())
    cls = dict(con.execute("""SELECT CAST(value AS INTEGER), class FROM v_monthly
                              WHERE variable = 'tm' AND month = 7""").fetchall())
    assert cls[20] == 1      # above P95
    assert cls[1] == 11      # at/below P5
    assert cls[10] == 6      # between P40 and P60: normal
    assert cls[13] == 5      # just above P60
    hi, lo = con.execute("""SELECT is_record_high, is_record_low FROM v_monthly
                            WHERE variable = 'tm' AND month = 7 AND value = 20""").fetchone()
    assert hi and not lo


def test_lt_counts_are_inclusive(con):
    tn = [0.0] * 5 + [-0.1] * 5 + [0.1] * 21
    db.replace_rows(con, "daily_obs", _daily_frame(date(2026, 1, 1), 31, [1.0] * 31, tn=tn))
    climate.rebuild_all(con, Config())
    got = con.execute("""SELECT value FROM monthly_summary
                         WHERE variable = 'tnlt0' AND year = 2026 AND month = 1""").fetchone()[0]
    assert got == 10


def test_seasonal_djf_belongs_to_next_year(con):
    db.replace_rows(con, "daily_obs", _daily_frame(date(2025, 12, 1), 31 + 31 + 28, [0.0] * 90))
    climate.rebuild_all(con, Config())
    row = con.execute("""SELECT days_present, days_missing FROM period_summary
                         WHERE period = 'DJF' AND year = 2026 AND variable = 'tm'""").fetchone()
    assert row == (90, 0)
