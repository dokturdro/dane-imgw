"""Read-only queries for the dashboard.

Every public function takes a DuckDB connection; ``open_ro`` gives a short-lived
read-only one, so the dashboard never holds the file between queries and
`imgw live` / `imgw sync` can write in the gaps.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from .. import db

MONTH_COLS = [str(m) for m in range(1, 13)]
PERIOD_COLS = ["DJF", "MAM", "JJA", "SON", "year"]
REFERENCE_PERIODS = [(1961, 1990), (1971, 2000), (1981, 2010), (1991, 2020)]


@contextmanager
def open_ro(path: Path, wait: float = 3.0):
    con = db.connect(path, read_only=True, wait=wait)
    try:
        yield con
    finally:
        con.close()


def stations(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    df = con.execute("""
        SELECT imgw_id, coalesce(name, imgw_id) AS name, type, networks,
               year(first_date) AS first_year, year(last_date) AS last_year, lat, lon, elevation
        FROM v_stations
        ORDER BY name, imgw_id
    """).df()
    df["label"] = (df["name"] + " (" + df["imgw_id"] + ") · " + df["type"] + " · "
                   + df["first_year"].astype(str) + "–" + df["last_year"].astype(str))
    return df


def freshness(con, sid: str) -> dict:
    a = con.execute("SELECT max(date) FROM daily_obs WHERE imgw_id = ?", [sid]).fetchone()[0]
    h = con.execute("SELECT max(ts) FROM hourly_obs WHERE imgw_id = ?", [sid]).fetchone()[0]
    l = con.execute("SELECT max(ts) FROM live_obs WHERE imgw_id = ?", [sid]).fetchone()[0]
    s = con.execute("SELECT max(ts) FROM synop_msg_obs WHERE imgw_id = ?", [sid]).fetchone()[0]
    return {"archive": a, "hourly": h, "live": l, "synop": s}


def daily(con, sid: str, start: date, end: date) -> pd.DataFrame:
    """Archive days plus provisional days after the archive ends (column ``provisional``)."""
    arch = con.execute("""
        SELECT *, FALSE AS provisional FROM v_daily
        WHERE imgw_id = ? AND date BETWEEN ? AND ? ORDER BY date
    """, [sid, start, end]).df()
    prov = con.execute("""
        SELECT * EXCLUDE (prov_source), prov_source, TRUE AS provisional FROM v_provisional_daily
        WHERE imgw_id = ? AND date BETWEEN ? AND ? ORDER BY date
    """, [sid, start, end]).df()
    prov = prov.dropna(subset=["tm", "tx", "tn", "prcp"], how="all")   # day not far enough along yet
    parts = [p for p in (arch, prov) if not p.empty]
    if not parts:
        return arch
    return pd.concat(parts, ignore_index=True).sort_values("date").reset_index(drop=True)


def latest_synop(con, sid: str) -> dict | None:
    """Most recent SYNOP-message observation for the station (provisional)."""
    df = con.execute("""
        SELECT * FROM v_hourly WHERE imgw_id = ? AND provisional ORDER BY date DESC LIMIT 1
    """, [sid]).df()
    return None if df.empty else df.iloc[0].to_dict()


def live_days(con, sid: str, days: int = 3) -> pd.DataFrame:
    return con.execute("""
        SELECT * FROM v_live_daily WHERE imgw_id = ? AND date >= current_date - ?::INTEGER
        ORDER BY date DESC
    """, [sid, days]).df()


def monthly_normals(con, sid: str, variable: str) -> pd.DataFrame:
    return con.execute("""
        SELECT month, mean, sd, p10, p90, n_years FROM normals
        WHERE imgw_id = ? AND variable = ? ORDER BY month
    """, [sid, variable]).df()


def month_to_date(con, sid: str, today: date) -> dict:
    """This month's provisional+archive tm mean and prcp sum vs the normal."""
    first = today.replace(day=1)
    d = daily(con, sid, first, today)
    n_days = (today - first).days + 1
    days_in_month = ((first + timedelta(days=32)).replace(day=1) - first).days
    out = {"days": n_days, "tm": None, "tm_anom": None, "prcp": None, "prcp_pct": None,
           "n_tm": 0, "n_prcp": 0}
    if d.empty:
        return out
    norm = dict(con.execute("""
        SELECT variable, mean FROM normals WHERE imgw_id = ? AND month = ? AND variable IN ('tm', 'prcp')
    """, [sid, today.month]).fetchall())
    tm, pr = d["tm"].dropna(), d["prcp"].dropna()
    out.update(n_tm=len(tm), n_prcp=len(pr))
    if len(tm):
        out["tm"] = tm.mean()
        if norm.get("tm") is not None:
            out["tm_anom"] = out["tm"] - norm["tm"]
    if len(pr):
        out["prcp"] = pr.sum()
        if norm.get("prcp"):
            # normal monthly sum pro-rated to the days we have
            out["prcp_pct"] = 100 * out["prcp"] / (norm["prcp"] * len(pr) / days_in_month)
    return out


def hourly(con, sid: str, start: date, end: date) -> pd.DataFrame:
    return con.execute("""
        SELECT * FROM v_hourly WHERE imgw_id = ? AND date >= ? AND date < ? ORDER BY date
    """, [sid, start, end + timedelta(days=1)]).df()


def monthly_grid(con, sid: str, variable: str, max_missing: int = 3) -> dict[str, pd.DataFrame]:
    """Year × (12 months + DJF/MAM/JJA/SON/year) frames: value, class, flags, tooltip data."""
    m = con.execute("""
        SELECT year, CAST(month AS VARCHAR) AS col, value, class, days_present, days_missing,
               is_record_high, is_record_low, anomaly
        FROM v_monthly WHERE imgw_id = ? AND variable = ?
    """, [sid, variable]).df()
    p = con.execute("""
        SELECT year, period AS col, value, class, days_present, days_missing,
               is_record_high, is_record_low, anomaly
        FROM v_period WHERE imgw_id = ? AND variable = ?
    """, [sid, variable]).df()
    long = pd.concat([x for x in (m, p) if not x.empty], ignore_index=True) if len(m) or len(p) else m
    cols = MONTH_COLS + PERIOD_COLS
    if long.empty:
        return {"long": long}
    limit = long["col"].map(lambda c: 10 if c == "year" else 5 if c in PERIOD_COLS else max_missing)
    long["partial"] = long["days_missing"] > limit
    long.loc[long["partial"], "class"] = pd.NA
    out = {"long": long}
    for field in ("value", "class", "partial", "is_record_high", "is_record_low",
                  "days_present", "days_missing", "anomaly"):
        out[field] = (long.pivot(index="year", columns="col", values=field)
                      .reindex(columns=cols).sort_index(ascending=False))
    out["means"] = reference_means(long)
    return out


def reference_means(long: pd.DataFrame) -> pd.DataFrame:
    """Means of complete values per column for meteomodel's reference periods."""
    rows = {}
    ok = long[~long["partial"] & long["value"].notna()]
    for y0, y1 in REFERENCE_PERIODS:
        sub = ok[ok["year"].between(y0, y1)]
        if sub["year"].nunique() >= 25:      # of 30; partial coverage would mislead
            rows[f"{y0}–{y1}"] = sub.groupby("col")["value"].mean()
    return pd.DataFrame(rows).T.reindex(columns=MONTH_COLS + PERIOD_COLS)


def monthly_year(con, sid: str, year: int, variables=("tm", "prcp")) -> pd.DataFrame:
    return con.execute(f"""
        SELECT month, variable, value, is_partial, class FROM v_monthly
        WHERE imgw_id = ? AND year = ? AND variable IN ({', '.join('?' * len(variables))})
    """, [sid, year, *variables]).df()


def annual_anomalies(con, sid: str, variable: str = "tm") -> pd.DataFrame:
    return con.execute("""
        SELECT year, value, anomaly, class FROM v_period
        WHERE imgw_id = ? AND variable = ? AND period = 'year' AND NOT is_partial
        ORDER BY year
    """, [sid, variable]).df()


def cumulative_prcp(con, sid: str) -> pd.DataFrame:
    """Day-of-year cumulative precipitation for every year with near-complete data."""
    return con.execute("""
        WITH d AS (
            SELECT year(date) AS year, dayofyear(date) AS doy, prcp FROM v_daily
            WHERE imgw_id = ?
        ), ok AS (
            SELECT year FROM d GROUP BY year HAVING count(prcp) >= 0.9 * max(doy)
        )
        SELECT year, doy, sum(coalesce(prcp, 0)) OVER (PARTITION BY year ORDER BY doy) AS cum
        FROM d WHERE year IN (SELECT year FROM ok)
        ORDER BY year, doy
    """, [sid]).df()
