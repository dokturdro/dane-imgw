"""Hourly point forecast from Open-Meteo (CC BY 4.0), fetched on demand, not stored."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import httpx
import pandas as pd

from .config import OPEN_METEO_PREVIOUS_URL, OPEN_METEO_URL

HOURLY = {"temperature_2m": "tm", "dew_point_2m": "td", "precipitation": "prcp",
          "cloud_cover": "cloud_cover", "wind_speed_10m": "wind_speed", "wind_gusts_10m": "wind_gust"}


def fetch(client: httpx.Client, lat: float, lon: float, elevation: float | None = None) -> pd.DataFrame:
    """Hourly forecast for the point, columns ``date`` (naive UTC), ``tm``, ``td``, ``prcp``,
    ``cloud_cover`` [%], ``wind_speed`` and ``wind_gust`` [m/s, as in the IMGW tables]."""
    params = {**_point(lat, lon, elevation), "hourly": ",".join(HOURLY), "forecast_days": 16,
              "wind_speed_unit": "ms"}
    h = client.get(OPEN_METEO_URL, params=params).raise_for_status().json()["hourly"]
    df = pd.DataFrame({"date": pd.to_datetime(h["time"]),
                       **{col: pd.to_numeric(pd.Series(h[k]), errors="coerce") for k, col in HOURLY.items()}})
    return df.dropna(subset=["tm"]).reset_index(drop=True)   # the last hours come back null


def _point(lat: float, lon: float, elevation: float | None) -> dict:
    p = {"latitude": lat, "longitude": lon, "timezone": "GMT"}
    if elevation is not None and not pd.isna(elevation):
        p["elevation"] = elevation     # temperature adjusted to the station's height
    return p


def day_ahead(client: httpx.Client, lat: float, lon: float, elevation: float | None,
              start: date, end: date) -> pd.DataFrame:
    """What the forecast issued 24 h earlier predicted for each hour of ``start..end``: ``date``, ``tm``."""
    params = {**_point(lat, lon, elevation), "hourly": "temperature_2m_previous_day1",
              "start_date": start.isoformat(), "end_date": end.isoformat()}
    h = client.get(OPEN_METEO_PREVIOUS_URL, params=params).raise_for_status().json()["hourly"]
    df = pd.DataFrame({"date": pd.to_datetime(h["time"]),
                       "tm": pd.to_numeric(pd.Series(h["temperature_2m_previous_day1"]), errors="coerce")})
    return df.dropna(subset=["tm"]).reset_index(drop=True)


def next_days(df: pd.DataFrame, after: datetime, now: datetime, days: int = 2) -> pd.DataFrame:
    """Forecast rows later than the last observation ``after``: the rest of today plus ``days`` full days."""
    end = datetime.combine(now.date() + timedelta(days=days + 1), datetime.min.time())
    return df[(df["date"] > after) & (df["date"] < end)].reset_index(drop=True)
