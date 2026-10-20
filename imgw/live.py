"""Poll IMGW's live JSON APIs into live_obs (provisional data).

* /api/data/synop  - 62 synop stations, latest hourly report, WMO-style id (12375)
* /api/data/meteo  - ~790 telemetry stations, latest 10-min value per field,
                     each with its own timestamp, 9-digit IMGW code

Both APIs return only the latest value, so history accumulates only while the
poller runs. Duplicate (station, variable, ts) rows are ignored, so polling
more often than the data changes is harmless.

A poll that finds the database held by a sync writes its raw responses to the
spool directory instead; the next poll or sync ingests them, so nothing is lost.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import httpx
import pandas as pd

from . import db
from .config import LIVE_METEO_URL, LIVE_SYNOP_URL, Config

log = logging.getLogger(__name__)

SYNOP_FIELDS = ["temperatura", "predkosc_wiatru", "kierunek_wiatru",
                "wilgotnosc_wzgledna", "suma_opadu", "cisnienie"]
METEO_FIELDS = ["temperatura_gruntu", "temperatura_powietrza", "wiatr_kierunek",
                "wiatr_srednia_predkosc", "wiatr_predkosc_maksymalna",
                "wilgotnosc_wzgledna", "wiatr_poryw_10min", "opad_10min"]


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def synop_rows(payload: list[dict], wmo_map: dict[str, str], now: datetime) -> list[dict]:
    rows = []
    for rec in payload:
        if not rec.get("data_pomiaru") or rec.get("godzina_pomiaru") in (None, ""):
            continue
        ts = datetime.fromisoformat(rec["data_pomiaru"]).replace(hour=int(rec["godzina_pomiaru"]))
        key = str(rec["id_stacji"])
        for f in SYNOP_FIELDS:
            val = _num(rec.get(f))
            if val is not None:
                rows.append(dict(imgw_id=wmo_map.get(key), station_key=key,
                                 network="synop_live", ts=ts, variable=f,
                                 value=val, fetched_at=now))
    return rows


def meteo_rows(payload: list[dict], now: datetime) -> list[dict]:
    rows = []
    for rec in payload:
        key = str(rec["kod_stacji"])
        for f in METEO_FIELDS:
            val, stamp = _num(rec.get(f)), rec.get(f"{f}_data")
            if val is None or not stamp:
                continue
            rows.append(dict(imgw_id=key, station_key=key, network="telemetry",
                             ts=datetime.fromisoformat(stamp), variable=f,
                             value=val, fetched_at=now))
    return rows


def station_meta(payload: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([
        dict(imgw_id=str(r["kod_stacji"]), name=r.get("nazwa_stacji"),
             lat=_num(r.get("lat")), lon=_num(r.get("lon")),
             elevation=_num(r.get("wysokosc_npm")))
        for r in payload
    ])


def fetch(client: httpx.Client) -> dict:
    """One snapshot of both APIs; needs no database."""
    return {
        "fetched_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "synop": client.get(LIVE_SYNOP_URL).raise_for_status().json(),
        "meteo": client.get(LIVE_METEO_URL).raise_for_status().json(),
    }


def spool(snap: dict, spool_dir: Path) -> Path:
    """Save a snapshot for later ingestion (written atomically)."""
    spool_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromisoformat(snap["fetched_at"]).strftime("%Y%m%dT%H%M%S%f")
    path = spool_dir / f"{stamp}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap), encoding="utf-8")
    os.replace(tmp, path)
    return path


def drain_spool(con: duckdb.DuckDBPyConnection, spool_dir: Path) -> int:
    """Ingest spooled snapshots oldest first; returns the number of new rows."""
    added = 0
    for path in sorted(spool_dir.glob("*.json")):
        try:
            snap = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning("unreadable spool file %s (%s), set aside", path.name, e)
            os.replace(path, path.with_suffix(".bad"))
            continue
        added += ingest(con, snap)["new_rows"]
        path.unlink()
    return added


def ingest(con: duckdb.DuckDBPyConnection, snap: dict) -> dict[str, int]:
    now = datetime.fromisoformat(snap["fetched_at"])
    synop, meteo = snap["synop"], snap["meteo"]
    wmo_map = dict(con.execute(
        "SELECT wmo_id, imgw_id FROM stations WHERE wmo_id IS NOT NULL").fetchall())
    df = pd.DataFrame(synop_rows(synop, wmo_map, now) + meteo_rows(meteo, now))
    meta = station_meta(meteo)

    con.begin()
    try:
        added = 0
        if not df.empty:
            con.register("_live", df)
            # only the snapshot's time range can hold duplicates, so skip scanning the rest
            added = con.execute("""
                INSERT INTO live_obs BY NAME
                SELECT n.* FROM _live n
                ANTI JOIN (SELECT station_key, network, ts, variable FROM live_obs
                           WHERE ts >= (SELECT min(ts) FROM _live)) o
                  ON o.station_key = n.station_key AND o.network = n.network
                 AND o.ts = n.ts AND o.variable = n.variable
            """).fetchone()[0]
            con.unregister("_live")

        # telemetry carries coordinates; keep the station table's location fresh
        if not meta.empty:
            con.register("_meta", meta)
            con.execute("""
                UPDATE stations s SET lat = m.lat, lon = m.lon, elevation = m.elevation
                FROM _meta m WHERE s.imgw_id = m.imgw_id
            """)
            con.execute("""
                INSERT INTO stations (imgw_id, name, lat, lon, elevation)
                SELECT m.imgw_id, m.name, m.lat, m.lon, m.elevation FROM _meta m
                ANTI JOIN stations s USING (imgw_id)
            """)
            con.unregister("_meta")
        con.commit()
    except BaseException:
        con.rollback()
        raise
    return {"synop_records": len(synop), "telemetry_records": len(meteo), "new_rows": added}


def update(cfg: Config, client: httpx.Client) -> dict:
    """Poll both APIs and store the snapshot; spool it when another process holds the DB."""
    snap = fetch(client)
    try:
        con = db.connect(cfg.db_path)
    except db.DatabaseLocked:
        return {"spooled_to": str(spool(snap, cfg.live_spool_dir))}
    with con:
        spooled = drain_spool(con, cfg.live_spool_dir)
        return {**ingest(con, snap), "spooled_rows": spooled}


def poll(con: duckdb.DuckDBPyConnection, client: httpx.Client) -> dict[str, int]:
    return ingest(con, fetch(client))


def prune(con: duckdb.DuckDBPyConnection, keep_days: int) -> int:
    """Drop live rows for days the archive now covers, and any older than ``keep_days``."""
    # synop rows polled before the station list knew their WMO id
    con.execute("""
        UPDATE live_obs l SET imgw_id = s.imgw_id FROM stations s
        WHERE l.imgw_id IS NULL AND l.network = 'synop_live' AND s.wmo_id = l.station_key
    """)
    covered = con.execute("""
        DELETE FROM live_obs l USING (
            SELECT imgw_id, max(date) AS last_date FROM daily_obs GROUP BY imgw_id
        ) a
        WHERE l.imgw_id = a.imgw_id AND CAST(l.ts AS DATE) < a.last_date - INTERVAL 1 DAY
    """).fetchone()[0]
    aged = con.execute(
        "DELETE FROM live_obs WHERE ts < current_date - to_days(CAST(? AS INTEGER))",
        [keep_days],
    ).fetchone()[0]
    return covered + aged

