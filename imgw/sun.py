"""Sunrise and sunset in UTC from the NOAA solar equations (about a minute's accuracy)."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import pandas as pd

ZENITH = 90.833   # sun's centre 50' below the horizon: refraction plus the solar radius


def _events(lat: float, lon: float, day: date) -> tuple[datetime | None, datetime | None]:
    n = day.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)                                     # fractional year at 00 UTC
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    phi = math.radians(lat)
    cos_ha = (math.cos(math.radians(ZENITH)) / (math.cos(phi) * math.cos(decl))
              - math.tan(phi) * math.tan(decl))
    if not -1 <= cos_ha <= 1:            # polar day or night
        return None, None
    ha = math.degrees(math.acos(cos_ha))
    midnight = datetime.combine(day, datetime.min.time())
    rise = 720 - 4 * (lon + ha) - eqtime
    sets = 720 - 4 * (lon - ha) - eqtime
    return midnight + timedelta(minutes=rise), midnight + timedelta(minutes=sets)


def times(lat: float, lon: float, start: date, end: date) -> pd.DataFrame:
    """Sunrise and sunset (naive UTC) for every day of ``start..end``: columns ``sunrise``, ``sunset``."""
    rows = [_events(lat, lon, start + timedelta(days=i)) for i in range((end - start).days + 1)]
    df = pd.DataFrame([r for r in rows if r[0] is not None], columns=["sunrise", "sunset"])
    return df.apply(lambda c: c.dt.round("min"))
