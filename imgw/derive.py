"""Daily means computed from hourly synop data.

IMGW stopped publishing s_d_t (daily cloud/wind/RH/pressure means) in mid-2024.
dane.meteomodel.pl fills the gap with the mean of the 8 synoptic terms
(00, 03, ..., 21 UTC); this reproduces its values exactly (verified on
Warszawa 352200375, Aug 2026). Values are kept unrounded; views round half-up.
"""

from __future__ import annotations

import duckdb

MIN_TERMS = 6  # of 8

_VARS = {
    "cloud_cover": "cloud_cover",
    "wind_speed": "wind_speed",
    "tm_terms": "tm",
    "vapp": "vapp",
    "rh": "rh",
    "ppp": "ppp",
    "mslp": "mslp",
}


def rebuild_daily_agg(con: duckdb.DuckDBPyConnection) -> int:
    sel = ",\n".join(
        # round to 4 dp so float noise (1.2499999...) does not defeat half-up rounding later
        f"CASE WHEN count({src}) >= {MIN_TERMS} THEN round(avg({src}), 4) END AS {dst}"
        for dst, src in _VARS.items()
    )
    con.execute("BEGIN")
    con.execute("DELETE FROM daily_agg WHERE origin = 'derived'")
    con.execute(f"""
        INSERT INTO daily_agg BY NAME
        SELECT imgw_id, CAST(ts AS DATE) AS date, 'synop' AS source, 'derived' AS origin,
               {sel},
               count(*) AS n_terms
        FROM hourly_obs
        WHERE source = 'synop' AND hour(ts) % 3 = 0 AND minute(ts) = 0
        GROUP BY imgw_id, CAST(ts AS DATE)
    """)
    n = con.execute("SELECT count(*) FROM daily_agg WHERE origin = 'derived'").fetchone()[0]
    con.execute("COMMIT")
    return n
