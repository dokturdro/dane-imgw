"""Monthly / seasonal / annual summaries, normals and classes (meteomodel's
"Miesięczne" view), computed in DuckDB from v_daily.
"""

from __future__ import annotations

import duckdb

from .config import Config

# name -> (aggregate expression over v_daily d, base column for completeness)
VARIABLES: dict[str, tuple[str, str]] = {
    "tm": ("avg(tm)", "tm"),
    "tm2": ("avg((tx + tn) / 2)", "tm2"),
    "tx": ("avg(tx)", "tx"),
    "tn": ("avg(tn)", "tn"),
    "txx": ("max(tx)", "tx"),
    "tnn": ("min(tn)", "tn"),
    "txn": ("min(tx)", "tx"),
    "tnx": ("max(tn)", "tn"),
    "tmx": ("max(tm)", "tm"),
    "tmn": ("min(tm)", "tm"),
    "tgn": ("avg(tng)", "tng"),
    "prcp": ("sum(prcp)", "prcp"),
    "prcpx": ("max(prcp)", "prcp"),
    "mslp": ("avg(mslp)", "mslp"),
    "ppp": ("avg(ppp)", "ppp"),
    "wind_speed": ("avg(wind_speed)", "wind_speed"),
    "sunshine": ("sum(sunshine)", "sunshine"),
    "rh": ("avg(rh)", "rh"),
    "vapp": ("avg(vapp)", "vapp"),
    "snow_depth": ("sum(snow_depth)", "snow_depth"),
    "sndpx": ("max(snow_depth)", "snow_depth"),
    "sndpcnt": ("count(*) FILTER (WHERE snow_depth >= 1)", "snow_depth"),
    "hdd": ("sum(CASE WHEN tm <= 15 THEN 18 - tm ELSE 0 END)", "tm"),
    "cdd": ("sum(CASE WHEN tm > 18 THEN tm - 18 ELSE 0 END)", "tm"),
    "gdd": ("sum(CASE WHEN tm > 10 THEN tm - 10 ELSE 0 END)", "tm"),
    "hot": ("count(*) FILTER (WHERE tx >= th.hot_p95)", "tx"),
}
for _t in (35, 30, 25, 20, 15, 10):
    VARIABLES[f"txgt{_t}"] = (f"count(*) FILTER (WHERE tx >= {_t})", "tx")
# meteomodel's "lt" counts are inclusive (verified: tx/tn <= t reproduces them exactly)
for _t, _n in ((10, "10"), (0, "0"), (-10, "m10")):
    VARIABLES[f"txlt{_n}"] = (f"count(*) FILTER (WHERE tx <= {_t})", "tx")
for _t in (10, 15, 20):
    VARIABLES[f"tngt{_t}"] = (f"count(*) FILTER (WHERE tn >= {_t})", "tn")
for _t, _n in ((10, "10"), (0, "0"), (-10, "m10"), (-20, "m20"), (-30, "m30")):
    VARIABLES[f"tnlt{_n}"] = (f"count(*) FILTER (WHERE tn <= {_t})", "tn")


def _season(day: str) -> str:
    return (f"CASE WHEN month({day}) IN (12,1,2) THEN 'DJF' WHEN month({day}) IN (3,4,5) THEN 'MAM' "
            f"WHEN month({day}) IN (6,7,8) THEN 'JJA' ELSE 'SON' END")


def _season_year(day: str) -> str:
    """DJF is dated to the year of its Jan/Feb."""
    return f"CASE WHEN month({day}) = 12 THEN year({day}) + 1 ELSE year({day}) END"


def rebuild_thresholds(con: duckdb.DuckDBPyConnection, cfg: Config) -> None:
    y0, y1 = cfg.hot_period
    con.execute("DELETE FROM station_thresholds")
    con.execute(f"""
        INSERT INTO station_thresholds
        SELECT imgw_id, quantile_cont(tx, 0.95)
        FROM v_daily
        WHERE month(date) IN (6, 7, 8) AND year(date) BETWEEN {y0} AND {y1} AND tx IS NOT NULL
        GROUP BY imgw_id
        HAVING count(tx) >= 900          -- ~10 complete summers
    """)


def _summary_select(keys: str) -> str:
    """One wide row per (station, period) with value + present-days per variable."""
    cols = []
    for name, (expr, base) in VARIABLES.items():
        cols.append(f"{expr} AS v_{name}")
        cols.append(f"count({base}) AS n_{name}")
    return f"""
        SELECT d.imgw_id, {keys}, {', '.join(cols)}
        FROM v_daily d LEFT JOIN station_thresholds th USING (imgw_id)
        GROUP BY ALL
    """


def _unpivot(wide: str, keys: list[str]) -> str:
    k = ", ".join(keys)
    parts = [
        f"SELECT imgw_id, {k}, '{name}' AS variable, v_{name} AS value, n_{name} AS days_present FROM {wide}"
        for name in VARIABLES
    ]
    return "\nUNION ALL\n".join(parts)


def rebuild_monthly(con: duckdb.DuckDBPyConnection) -> int:
    con.execute("CREATE OR REPLACE TEMP TABLE _wide AS "
                + _summary_select("year(d.date) AS year, month(d.date) AS month"))
    con.execute("BEGIN")
    con.execute("DELETE FROM monthly_summary")
    con.execute(f"""
        INSERT INTO monthly_summary
        SELECT imgw_id, year, month, variable,
               CASE WHEN days_present > 0 THEN value END,
               days_present,
               day(last_day(make_date(year, month, 1))) - days_present
        FROM ({_unpivot('_wide', ['year', 'month'])})
    """)
    con.execute("COMMIT")
    con.execute("DROP TABLE _wide")
    return con.execute("SELECT count(*) FROM monthly_summary").fetchone()[0]


def rebuild_periods(con: duckdb.DuckDBPyConnection) -> int:
    """Seasonal and annual summaries."""
    con.execute(f"""CREATE OR REPLACE TEMP TABLE _wide AS
        {_summary_select(f"{_season_year('d.date')} AS year, {_season('d.date')} AS period")}
        UNION ALL BY NAME
        {_summary_select("year(d.date) AS year, 'year' AS period")}
    """)
    con.execute("BEGIN")
    con.execute("DELETE FROM period_summary")
    con.execute(f"""
        WITH cal AS (
            SELECT {_season_year('d')} AS year, {_season('d')} AS period, count(*) AS n
            FROM range(DATE '1900-12-01', DATE '2101-01-01', INTERVAL 1 DAY) t(d) GROUP BY ALL
            UNION ALL
            SELECT year(d), 'year', count(*)
            FROM range(DATE '1901-01-01', DATE '2101-01-01', INTERVAL 1 DAY) t(d) GROUP BY ALL
        )
        INSERT INTO period_summary
        SELECT u.imgw_id, u.year, u.period, u.variable,
               CASE WHEN u.days_present > 0 THEN u.value END, u.days_present,
               cal.n - u.days_present
        FROM ({_unpivot('_wide', ['year', 'period'])}) u JOIN cal USING (year, period)
    """)
    con.execute("COMMIT")
    con.execute("DROP TABLE _wide")
    return con.execute("SELECT count(*) FROM period_summary").fetchone()[0]


def rebuild_normals(con: duckdb.DuckDBPyConnection, cfg: Config, max_missing: int = 3) -> int:
    """Mean/spread of complete months over the normal period (anomalies, chart bands).

    Classes do not use this table: v_monthly ranks each value against the
    station's whole record, as meteomodel does.
    """
    y0, y1 = cfg.normal_period
    con.execute(f"""
        CREATE OR REPLACE TABLE normals AS
        SELECT imgw_id, month, variable, '{y0}-{y1}' AS period,
               count(value) AS n_years, avg(value) AS mean, stddev_samp(value) AS sd,
               quantile_cont(value, 0.1) AS p10, quantile_cont(value, 0.9) AS p90,
               min(value) AS min, max(value) AS max
        FROM monthly_summary
        WHERE year BETWEEN {y0} AND {y1} AND days_missing <= {max_missing} AND value IS NOT NULL
        GROUP BY imgw_id, month, variable
    """)
    return con.execute("SELECT count(*) FROM normals").fetchone()[0]


def rebuild_period_normals(con: duckdb.DuckDBPyConnection, cfg: Config) -> int:
    """Mean of complete seasons / years over the normal period (v_period anomalies).

    Complete = at most 5 (season) or 10 (year) days missing, as in v_period.
    """
    y0, y1 = cfg.normal_period
    con.execute(f"""
        CREATE OR REPLACE TABLE period_normals AS
        SELECT imgw_id, period, variable, avg(value) AS mean
        FROM period_summary
        WHERE year BETWEEN {y0} AND {y1} AND value IS NOT NULL
          AND days_missing <= CASE period WHEN 'year' THEN 10 ELSE 5 END
        GROUP BY imgw_id, period, variable
    """)
    return con.execute("SELECT count(*) FROM period_normals").fetchone()[0]


def rebuild_all(con: duckdb.DuckDBPyConnection, cfg: Config) -> dict[str, int]:
    rebuild_thresholds(con, cfg)
    out = {"monthly": rebuild_monthly(con), "periods": rebuild_periods(con)}
    out["normals"] = rebuild_normals(con, cfg)
    out["period_normals"] = rebuild_period_normals(con, cfg)
    return out
