"""Open-Meteo forecast parsing, the two-day window and the forecast charts."""

from datetime import date, datetime

import httpx
import pandas as pd

from imgw import forecast, sun
from imgw.dash import charts


def _payload(n=6, nulls=2):
    times = [f"2026-11-07T{h:02d}:00" for h in range(n)]
    tm = [1.0 * h - 2 for h in range(n - nulls)] + [None] * nulls
    return {"hourly": {"time": times, "temperature_2m": tm, "dew_point_2m": [x and x - 1 for x in tm],
                       "precipitation": [0.0, 0.3] + [0.0] * (n - 2),
                       "cloud_cover": [100] * n, "wind_speed_10m": [3.2] * n, "wind_gusts_10m": [7.5] * n}}


def _client(seen):
    def handler(request):
        seen.append(request.url.params)
        return httpx.Response(200, json=_payload())
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_drops_trailing_nulls_and_keeps_naive_utc():
    seen = []
    with _client(seen) as c:
        df = forecast.fetch(c, 50.6, 17.9, 176.0)
    assert list(df.columns) == ["date", "tm", "td", "prcp", "cloud_cover", "wind_speed", "wind_gust"]
    assert len(df) == 4 and df["date"].dt.tz is None
    assert df["date"].iloc[0] == pd.Timestamp("2026-11-07 00:00")
    assert seen[0]["timezone"] == "GMT" and seen[0]["elevation"] == "176.0"
    assert seen[0]["wind_speed_unit"] == "ms"


def test_fetch_skips_unknown_elevation():
    seen = []
    with _client(seen) as c:
        forecast.fetch(c, 50.6, 17.9, float("nan"))
    assert "elevation" not in seen[0]


def test_next_days_window():
    df = pd.DataFrame({"date": pd.date_range("2026-11-07", periods=120, freq="h"), "tm": 1.0})
    out = forecast.next_days(df, after=datetime(2026, 11, 7, 5), now=datetime(2026, 11, 7, 6, 30))
    assert out["date"].min() == pd.Timestamp("2026-11-07 06:00")
    assert out["date"].max() == pd.Timestamp("2026-11-09 23:00")       # today + two full days


def test_charts_build():
    fc = pd.DataFrame({"date": pd.date_range("2026-11-07", periods=30, freq="h"),
                       "tm": 1.0, "td": -1.0, "prcp": 0.2, "cloud_cover": 75.0, "wind_speed": 4.0, "wind_gust": 9.0})
    obs = fc.iloc[:6]
    for th in ("light", "dark"):
        assert charts.hourly_temperature(obs, th).to_dict()
        assert charts.hourly_temperature(obs, th, fc.iloc[6:]).to_dict()
        assert charts.hourly_temperature(obs, th, fc.iloc[6:], fc.iloc[:6]).to_dict()
        assert charts.hourly_temperature(obs, th, None, fc.iloc[:6]).to_dict()
        st = sun.times(50.6, 17.9, date(2026, 11, 6), date(2026, 11, 9))
        assert charts.hourly_temperature(obs, th, fc.iloc[6:], fc.iloc[:6], st).to_dict()
        assert charts.forecast_chart(fc, th).to_dict()
        assert charts.forecast_chart(fc.assign(prcp=0.0), th).to_dict()
        assert charts.forecast_chart(fc, th, st).to_dict()


def test_day_ahead_reads_previous_run():
    seen = []

    def handler(request):
        seen.append(request.url)
        return httpx.Response(200, json={"hourly": {"time": ["2026-11-06T00:00", "2026-11-06T01:00"],
                                                    "temperature_2m_previous_day1": [1.5, None]}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        df = forecast.day_ahead(c, 50.6, 17.9, None, date(2026, 11, 6), date(2026, 11, 7))
    assert "previous-runs" in seen[0].host and seen[0].params["start_date"] == "2026-11-06"
    assert df["tm"].tolist() == [1.5]


def test_midnight_rules_inside_span():
    obs = pd.DataFrame({"date": pd.date_range("2026-11-06 00:00", "2026-11-07 17:00", freq="h")})
    fc = pd.DataFrame({"date": pd.date_range("2026-11-07 18:00", "2026-11-09 17:00", freq="h")})
    assert charts._midnights(obs, fc)["date"].dt.day.tolist() == [7, 8, 9]


def test_daily_extremes_use_day_and_night_windows():
    idx = pd.date_range("2026-11-07 00:00", "2026-11-08 23:00", freq="h")
    tm = pd.DataFrame({"date": idx, "value": [float(-abs(12 - h.hour)) if h.day == 7 else 5.0 for h in idx]})
    tm.loc[tm["date"] == pd.Timestamp("2026-11-07 23:00"), "value"] = -20.0   # cold late evening
    tm.loc[tm["date"] == pd.Timestamp("2026-11-08 01:00"), "value"] = -15.0   # same night, after midnight
    ext = charts.daily_extremes(tm)
    lows = ext[ext["kind"] == "Tmin noc"]
    assert lows["value"].tolist().count(-20.0) == 1 and -15.0 not in lows["value"].tolist()
    assert ext[ext["kind"] == "Tmax dzień"].set_index("date")["value"].get(pd.Timestamp("2026-11-07 12:00")) == 0.0


def test_nights_span_sunset_to_sunrise_clipped():
    sun = pd.DataFrame({"sunrise": pd.to_datetime(["2026-11-07 05:49", "2026-11-08 05:51"]),
                        "sunset": pd.to_datetime(["2026-11-07 15:13", "2026-11-08 15:12"])})
    n = charts.nights(sun, pd.Timestamp("2026-11-07 00:00"), pd.Timestamp("2026-11-08 12:00"))
    assert n.values.tolist() == [[pd.Timestamp("2026-11-07 00:00"), pd.Timestamp("2026-11-07 05:49")],
                                 [pd.Timestamp("2026-11-07 15:13"), pd.Timestamp("2026-11-08 05:51")]]


def test_sun_times_match_open_meteo_for_opole():
    st = sun.times(50.627, 17.969, date(2026, 11, 7), date(2026, 11, 7)).iloc[0]
    # Open-Meteo gave 05:49 / 15:13 UTC for this day
    assert abs(st["sunrise"] - pd.Timestamp("2026-11-07 05:49")) <= pd.Timedelta(minutes=3)
    assert abs(st["sunset"] - pd.Timestamp("2026-11-07 15:13")) <= pd.Timedelta(minutes=3)
    assert sun.times(78.2, 15.6, date(2026, 12, 21), date(2026, 12, 21)).empty   # polar night


def test_hover_table_has_every_series_per_hour():
    obs = charts._melt(pd.DataFrame({"date": pd.to_datetime(["2026-11-09 04:00", "2026-11-09 05:00"]),
                                     "tm": [-3.0, -3.1], "td": [-3.5, None]}))
    fc_t = pd.DataFrame({"date": pd.to_datetime(["2026-11-09 05:00", "2026-11-09 06:00"]),
                         "value": [-2.0, 2.7], "run": ["sprzed 24 h", "najnowsza"]})
    h = charts.hover_table(obs, fc_t).set_index("date")
    assert h.loc["2026-11-09 05:00", "temperatura"] == "-3.1 °C" and h.loc["2026-11-09 05:00", "punkt rosy"] == "—"
    assert h.loc["2026-11-09 05:00", "prognoza T"] == "-2.0 °C" and "prognoza" not in h
    assert h.loc["2026-11-09 06:00", "temperatura"] == "—" and "prognoza Td" not in h
    assert list(h.columns)[:3] == ["temperatura", "prognoza T", "punkt rosy"]


def test_to_local_follows_cet_and_cest():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-11-09 05:00", "2026-07-01 05:00"])})
    assert charts.to_local(df)["date"].tolist() == [pd.Timestamp("2026-11-09 06:00"), pd.Timestamp("2026-07-01 07:00")]
    assert df["date"].iloc[0] == pd.Timestamp("2026-11-09 05:00")      # input left as is
    assert charts.to_local(None) is None


def test_utc_offset_label():
    assert charts.utc_offset_label(pd.Series(pd.to_datetime(["2026-11-09 05:00"]))) == "UTC+1"
    assert charts.utc_offset_label(pd.Series(pd.to_datetime(["2026-07-01 05:00"]))) == "UTC+2"
    assert charts.utc_offset_label(pd.Series(pd.to_datetime(["2026-10-24 12:00", "2026-10-25 12:00"]))) == "UTC+1/+2"
