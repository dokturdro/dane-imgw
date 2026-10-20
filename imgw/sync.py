"""Incremental archive sync: crawl -> download changed files -> parse -> clean -> load."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import duckdb
import httpx
import pandas as pd

from . import clean, climate, crawl, db, derive
from .config import BASE_URL, Config
from .download import fetch, fetch_cached
from .parse import read_station_list, read_zip

log = logging.getLogger(__name__)


@dataclass
class SyncResult:
    files_seen: int = 0
    files_loaded: int = 0
    files_failed: list[str] = field(default_factory=list)
    rows: dict[str, int] = field(default_factory=dict)


def load_stations(con: duckdb.DuckDBPyConnection, client: httpx.Client) -> int:
    df = read_station_list(fetch(client, f"{BASE_URL}/wykaz_stacji.csv"))
    df = df.drop_duplicates("imgw_id", keep="last")
    df["wmo_id"] = None
    synop = df["imgw_id"].str.startswith("3") & df["id3"].str.fullmatch(r"\d{1,3}")
    df.loc[synop, "wmo_id"] = "12" + df.loc[synop, "id3"].str.zfill(3)
    con.register("_st", df)
    con.execute("""
        INSERT INTO stations (imgw_id, name, id3, wmo_id)
        SELECT imgw_id, name, id3, wmo_id FROM _st
        ON CONFLICT (imgw_id) DO UPDATE SET
            name = excluded.name, id3 = excluded.id3, wmo_id = excluded.wmo_id
    """)
    con.unregister("_st")
    return len(df)


def _load_file(con, rf: crawl.RemoteFile, data: bytes) -> dict[str, int]:
    frames = read_zip(data)
    counts: dict[str, int] = {}
    con.execute("BEGIN")
    try:
        for kind, raw in frames.items():
            table, df = clean.frames_for(kind, raw)
            counts[table] = counts.get(table, 0) + db.replace_rows(con, table, df)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return counts


def sync(
    con: duckdb.DuckDBPyConnection,
    client: httpx.Client,
    cfg: Config,
    *,
    start_year: int | None = None,
    hourly_start_year: int | None = None,
    networks: list[str] | None = None,
    hourly_networks: list[str] | None = None,
    force: bool = False,
    limit: int | None = None,
) -> SyncResult:
    res = SyncResult()
    load_stations(con, client)
    known = {} if force else db.synced_fingerprints(con)
    # anything logged before (changed upstream, or failed) must bypass the ZIP cache
    seen_before = {r[0] for r in con.execute("SELECT url FROM sync_log").fetchall()}

    plan: list[crawl.RemoteFile] = []
    for res_kind, nets, y0 in (
        ("daily", networks or cfg.networks, start_year or cfg.start_year),
        ("hourly", hourly_networks or cfg.hourly_networks, hourly_start_year or cfg.hourly_start_year),
    ):
        for net in nets:
            if (res_kind, net) not in crawl.SECTIONS:
                log.warning("no %s archive for network %s", res_kind, net)
                continue
            for rf in crawl.walk(client, res_kind, net, y0):
                res.files_seen += 1
                if known.get(rf.url) != rf.fingerprint:
                    plan.append(rf)
    if limit:
        plan = plan[:limit]
    log.info("%d files listed, %d new or changed", res.files_seen, len(plan))

    t0 = time.monotonic()
    for i, rf in enumerate(plan, 1):
        try:
            data, sha = fetch_cached(client, rf.url, cfg.raw_dir, cfg.keep_raw,
                                     refresh=force or rf.url in seen_before,
                                     delay=cfg.request_delay)
            counts = _load_file(con, rf, data)
            db.log_sync(con, rf.url, rf.fingerprint, sha, sum(counts.values()), "ok")
            for k, v in counts.items():
                res.rows[k] = res.rows.get(k, 0) + v
            res.files_loaded += 1
            log.info("[%d/%d] %s %s", i, len(plan), rf.url.removeprefix(BASE_URL), counts)
        except Exception as e:  # keep going; failed files are retried next run
            log.error("[%d/%d] %s failed: %s", i, len(plan), rf.url, e)
            res.files_failed.append(rf.url)
            db.log_sync(con, rf.url, rf.fingerprint, "", 0, f"error: {e}"[:500])
    log.info("loaded %d files in %.0fs", res.files_loaded, time.monotonic() - t0)

    if res.files_loaded:
        rebuild_derived(con, cfg)
    return res


def rebuild_derived(con: duckdb.DuckDBPyConnection, cfg: Config) -> dict[str, int]:
    out = {"daily_agg_derived": derive.rebuild_daily_agg(con)}
    out.update(climate.rebuild_all(con, cfg))
    out["qc_issues"] = clean.rebuild_qc(con)
    log.info("derived products: %s", out)
    return out


def status(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT 'daily ' || source AS dataset, count(*) AS rows,
               count(DISTINCT imgw_id) AS stations, min(date)::VARCHAR AS first, max(date)::VARCHAR AS last
        FROM daily_obs GROUP BY source
        UNION ALL
        SELECT 'hourly ' || source, count(*), count(DISTINCT imgw_id), min(ts)::VARCHAR, max(ts)::VARCHAR
        FROM hourly_obs GROUP BY source
        UNION ALL
        SELECT 'live ' || network, count(*), count(DISTINCT station_key), min(ts)::VARCHAR, max(ts)::VARCHAR
        FROM live_obs GROUP BY network
        UNION ALL
        SELECT 'synop messages', count(*), count(DISTINCT imgw_id), min(ts)::VARCHAR, max(ts)::VARCHAR
        FROM synop_msg_obs
        UNION ALL
        SELECT 'monthly_summary', count(*), count(DISTINCT imgw_id), min(year)::VARCHAR, max(year)::VARCHAR
        FROM monthly_summary
        UNION ALL
        SELECT 'qc_issues', count(*), count(DISTINCT imgw_id), NULL, NULL FROM qc_issues
        UNION ALL
        SELECT 'files failed', count(*), NULL, NULL, NULL FROM sync_log WHERE status <> 'ok'
        ORDER BY 1
    """).df()
