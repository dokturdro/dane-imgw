"""Dashboard: colour scales, queries on a temp DB, and a headless app run."""

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from imgw import climate, db, derive
from imgw.config import Config
from imgw.dash import queries as q, style


# --- colour scales: boundaries copied from meteomodel's utils-daily.js ----------

@pytest.mark.parametrize("v,bg", [(20.0, "#ffffcc"), (19.9, "#f7fcb9"), (0.0, "#238443"),
                                  (-0.1, "#f7fbff"), (-2.0, "#f7fbff"), (-2.1, "#deebf7"),
                                  (50.0, "#000000"), (-60.0, "#000000")])
def test_temperature_scale(v, bg):
    assert style.temperature(v).startswith(f"background-color: {bg}")


@pytest.mark.parametrize("v,bg", [(0.0, "#ffffff"), (0.1, "#99ccff"), (1.0, "#99ccff"),
                                  (1.1, "#3399ff"), (10.0, "#3366ff"), (24.9, "#3366ff"),
                                  (25.0, "#0000cc"), (199.0, "#ffccff"), (250.0, "#000000")])
def test_precip_scale(v, bg):
    assert style.precipitation(v).startswith(f"background-color: {bg}")


def test_scales_skip_missing_and_set_text_colour():
    assert style.temperature(float("nan")) == "" and style.precipitation(None) == ""
    assert "color: #ffffff" in style.temperature(-12) and "color: #000000" in style.temperature(21)
    assert style.sunshine_daily(15.9).startswith("background-color: #bd0026")
    assert style.cloud_cover(8).startswith("background-color: #000000")
    assert style.humidity(90).startswith("background-color: #33334d")


def test_no_negative_zero():
    assert style.fmt_num(-0.04) == "0.0" and style.fmt_num(-0.04, 0) == "0"
    assert style.fmt_num(-1.24) == "-1.2" and style.fmt_num(None) == ""


def test_style_frame_blanks_and_whole_numbers():
    df = pd.DataFrame({"tm": [1.25, np.nan], "ww": [3.0, 61.0], "x": [None, None]})
    html = style.style_frame(df, {"tm": style.temperature}, whole={"ww"}).to_html()
    assert "None" not in html and "nan" not in html
    assert ">61<" in html and (">1.2<" in html or ">1.3<" in html)


# --- queries ----------------------------------------------------------------------

def _daily(sid, start, days, tm, prcp=1.0):
    d = [start + timedelta(days=i) for i in range(days)]
    return pd.DataFrame({"imgw_id": sid, "date": d, "source": "synop", "tm": tm,
                         "tx": np.asarray(tm) + 5, "tn": np.asarray(tm) - 5, "prcp": prcp})


@pytest.fixture
def dbfile(tmp_path):
    path = tmp_path / "t.duckdb"
    con = db.connect(path)
    con.execute("INSERT INTO stations (imgw_id, name, wmo_id) VALUES ('352200375', 'WARSZAWA', '12375')")
    for y in range(1991, 2027):
        n = 31 if y < 2026 else 20               # last July incomplete
        db.replace_rows(con, "daily_obs", _daily("352200375", date(y, 7, 1), n, [15.0 + (y % 7)] * n))
    ts = [datetime(2026, 7, 20) + timedelta(hours=h) for h in range(24)]
    db.replace_rows(con, "hourly_obs", pd.DataFrame({"imgw_id": "352200375", "ts": ts, "source": "synop",
                                                     "tm": 20.0, "td": 10.0, "cloud_cover": 4.0}))
    derive.rebuild_daily_agg(con)
    climate.rebuild_all(con, Config())
    con.close()
    return path


def test_queries_on_temp_db(dbfile):
    with q.open_ro(dbfile) as con:
        st = q.stations(con)
        assert st.loc[0, "label"].startswith("WARSZAWA (352200375) · s · 1991")
        assert q.freshness(con, "352200375")["archive"] == date(2026, 7, 20)
        d = q.daily(con, "352200375", date(2026, 7, 1), date(2026, 7, 31))
        assert len(d) == 20 and not d["provisional"].any()
        g = q.monthly_grid(con, "352200375", "tm")
        assert list(g["value"].columns) == q.MONTH_COLS + q.PERIOD_COLS
        assert g["partial"].at[2026, "7"]                     # 11 days missing
        assert pd.isna(g["class"].at[2026, "7"])              # no class for partial months
        assert g["class"].at[2025, "7"] in range(1, 12)
        assert "1991–2020" in g["means"].index and "1961–1990" not in g["means"].index
        assert len(q.hourly(con, "352200375", date(2026, 7, 19), date(2026, 7, 20))) == 24
        assert len(q.annual_anomalies(con, "352200375")) == 0   # only Julys -> no complete years


def test_read_only_connection_does_not_block_writer(dbfile):
    with q.open_ro(dbfile) as con:
        q.stations(con)
    w = db.connect(dbfile)          # would raise DatabaseLocked if the reader leaked
    w.close()


def test_app_runs_headless(dbfile, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'db_path = "{dbfile.as_posix()}"\n', encoding="utf-8")
    monkeypatch.setenv("IMGW_CONFIG", str(cfg))
    at = AppTest.from_file("../imgw/dash/app.py", default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title[0].value == "WARSZAWA"
    [s for s in at.selectbox if s.label == "Zmienna"][0].set_value("prcp").run()
    assert not at.exception, [e.value for e in at.exception]
