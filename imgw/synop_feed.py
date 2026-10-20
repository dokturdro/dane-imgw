"""Provisional hourly data from WMO SYNOP messages (via OGIMET).

IMGW's hourly archive is built from the same synoptic observations, but is
published monthly. OGIMET archives the messages exchanged on the WMO GTS, so for
the ~60 Polish synop stations we can fill the gap between the end of the IMGW
archive and the current hour. Rows live in ``synop_msg_obs`` and are dropped once
the archive covers them (:func:`prune`).

Values were checked against the archive (Opole, Sep 2026): identical except wind
direction, which messages round to 10°.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import httpx
import pandas as pd
import warnings

from pymetdecoder import synop as pmd

from . import db
from .config import Config

# consistency notes about cloud groups, not errors
warnings.filterwarnings("ignore", module="pymetdecoder")

log = logging.getLogger(__name__)

OGIMET_URL = "https://www.ogimet.com/cgi-bin/getsynop"
BLOCK = "12"                       # WMO block for Poland
CHUNK = timedelta(days=7)          # per request
PAUSE = 12.0                       # seconds between OGIMET requests (courtesy)
REFETCH = timedelta(hours=6)       # re-read the last hours: late and corrected messages

_SEC3 = re.compile(r"\s333\s+(.*?)(?:\s555\s|=|$)")
_GUST = re.compile(r"(?:^|\s)911(\d\d)(?=\s|$)")
_SUN24 = re.compile(r"(?:^|\s)55(\d{3})(?=\s|$)")


# ----------------------------------------------------------------- fetching ---

def fetch(client: httpx.Client, begin: datetime, end: datetime, pause: float = PAUSE) -> list[str]:
    """CSV lines ``wmo,Y,M,D,H,m,message`` for block 12 between begin and end (UTC)."""
    lines: list[str] = []
    t = begin
    first = True
    while t < end:
        t2 = min(t + CHUNK, end)
        if not first:
            time.sleep(pause)
        first = False
        params = {"block": BLOCK, "begin": t.strftime("%Y%m%d%H%M"), "end": t2.strftime("%Y%m%d%H%M")}
        for attempt in range(4):
            r = client.get(OGIMET_URL, params=params, timeout=120)
            text = r.text
            if r.status_code == 200 and "too many" not in text.lower()[:300]:
                break
            wait = 30 * (attempt + 1)
            log.warning("OGIMET busy (%s), retry in %ss", r.status_code, wait)
            time.sleep(wait)
        else:
            raise RuntimeError(f"OGIMET refused {params}")
        chunk = [ln for ln in text.splitlines() if ln[:2].isdigit() and "AAXX" in ln]
        log.info("OGIMET %s..%s: %d messages", params["begin"], params["end"], len(chunk))
        lines += chunk
        t = t2
    return lines


# ----------------------------------------------------------------- decoding ---

def _v(d: dict | None, *path):
    for p in path:
        if d is None:
            return None
        d = d.get(p) if isinstance(d, dict) else None
    return d


def _vapour_pressure(td: float | None) -> float | None:
    """hPa over water (Magnus, WMO-No. 8 coefficients)."""
    if td is None:
        return None
    return 6.112 * math.exp(17.62 * td / (243.12 + td))


def decode(line: str) -> dict | None:
    """One OGIMET CSV line -> row for synop_msg_obs, or None if unusable."""
    parts = line.split(",", 6)
    if len(parts) < 7:
        return None
    wmo, y, mo, d, h, mi, msg = parts
    try:
        ts = datetime(int(y), int(mo), int(d), int(h), int(mi))
    except ValueError:
        return None
    msg = msg.strip().rstrip("=").rstrip() + "="
    try:
        s = pmd.SYNOP().decode(msg)
    except Exception as e:  # malformed message
        log.debug("undecodable %s %s: %s", wmo, ts, e)
        return None

    tm = _v(s, "air_temperature", "value")
    td = _v(s, "dewpoint_temperature", "value")
    e = _vapour_pressure(td)
    es = _vapour_pressure(tm)
    rh = min(100.0, 100 * e / es) if e is not None and es else None

    wind = s.get("surface_wind") or {}
    wdir = None if _v(wind, "direction", "calm") else _v(wind, "direction", "value")
    if _v(wind, "direction", "calm"):
        wdir = 0
    unit = _v(s, "wind_indicator", "unit")
    wspd = _v(wind, "speed", "value")
    kt = 0.514444 if unit == "KT" else 1.0
    wspd = None if wspd is None else round(wspd * kt, 1)

    # precipitation: section 1 group 6RRRt; indicator 3 = omitted because none fell
    p = s.get("precipitation_s1")
    p_amt = _v(p, "amount", "value")
    p_per = _v(p, "time_before_obs", "value")
    if p is None and _v(s, "precipitation_indicator", "value") == 3:
        p_amt, p_per = 0.0, (12 if ts.hour in (6, 18) else 6)
    if p is not None and _v(p, "amount", "trace"):
        p_amt = 0.0
    p24 = _v(s, "precipitation_24h", "amount", "value")
    if _v(s, "precipitation_24h", "amount", "trace"):
        p24 = 0.0

    sec3 = (_SEC3.search(msg) or [None, ""])[1]
    gust = _GUST.search(sec3)
    sun = None
    for item in s.get("sunshine") or []:
        if _v(item, "duration", "value") == 24:
            sun = _v(item, "amount", "value")
    if sun is None and (m := _SUN24.search(sec3)) and ts.hour == 6:
        sun = int(m[1]) / 10

    ct = s.get("cloud_types") or {}
    vis = _v(s, "visibility", "value")
    # snow depth (4E'sss, 06 UTC): codes as in the archive; group omitted = no snow
    snow = _v(s, "ground_state_snow", "depth", "depth")
    if _v(s, "ground_state_snow", "depth", "impossible") or snow in (998, 999):
        snow = None
    elif snow == 997:
        snow = 0.25
    elif snow is None and "ground_state_snow" not in s and ts.hour == 6:
        snow = 0.0

    return dict(
        wmo_id=wmo, ts=ts, raw=msg,
        tm=tm, td=td, rh=None if rh is None else round(rh, 1), vapp=None if e is None else round(e, 1),
        ppp=_v(s, "station_pressure", "value"), mslp=_v(s, "sea_level_pressure", "value"),
        p_tendency=_v(s, "pressure_tendency", "change", "value"),
        wind_dir=wdir, wind_speed=wspd,
        wind_gust=None if not gust else round(int(gust[1]) * kt, 1),
        cloud_cover=_v(s, "cloud_cover", "value"), low_cloud_cover=_v(ct, "low_cloud_amount", "value"),
        cl=_v(ct, "low_cloud_type", "value"), cm=_v(ct, "middle_cloud_type", "value"),
        ch=_v(ct, "high_cloud_type", "value"),
        visib_obs_m=vis, ww=_v(s, "present_weather", "value"),
        w1=_v((s.get("past_weather") or [None])[0], "value"),
        prcp=p_amt, prcp_period_h=p_per, prcp_24h=p24,
        tx_12h=_v(s, "maximum_temperature", "value"), tn_12h=_v(s, "minimum_temperature", "value"),
        # 3EsTgTg carries the ground minimum in whole degrees only, too coarse next to the archive
        tng_12h=None,
        snow_depth=snow if ts.hour == 6 else None, sunshine_24h=sun,
    )


def decode_all(lines: list[str]) -> pd.DataFrame:
    rows = [r for ln in lines if (r := decode(ln))]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # corrected re-sends (CCA) come later in the feed: keep the last one per station/time
    return df.drop_duplicates(["wmo_id", "ts"], keep="last").reset_index(drop=True)


# ------------------------------------------------------------------ storage ---

# A station's provisional coverage starts after its *daily* archive ends (synop
# stations: end of the synop month; ex-synop stations now archived as klimat:
# end of the klimat month). Stations silent in the archive for longer than this
# are treated as closed and do not hold the window back.
ACTIVE_DAYS = 120

_ARCHIVE_END = f"""
    SELECT d.imgw_id, max(d.date) AS last_date
    FROM daily_obs d JOIN stations s USING (imgw_id)
    WHERE s.wmo_id IS NOT NULL
    GROUP BY d.imgw_id
    HAVING max(d.date) >= (SELECT max(date) FROM daily_obs) - {ACTIVE_DAYS}
"""


def pending_window(con: duckdb.DuckDBPyConnection, now: datetime | None = None) -> tuple[datetime, datetime]:
    """From the earliest active station's daily-archive end (or the last stored
    message minus REFETCH) to now."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    arch = con.execute(f"SELECT min(last_date) FROM ({_ARCHIVE_END})").fetchone()[0]
    try:
        last_msg = con.execute("SELECT max(ts) FROM synop_msg_obs").fetchone()[0]
    except duckdb.CatalogException:     # read-only view of a database the schema hasn't reached yet
        last_msg = None
    begin = datetime.combine(arch + timedelta(days=1), datetime.min.time()) if arch else now - timedelta(days=31)
    if last_msg and last_msg - REFETCH > begin:
        begin = last_msg - REFETCH
    begin = max(begin, now - timedelta(days=62))       # never ask OGIMET for more than 2 months
    return begin.replace(minute=0, second=0, microsecond=0), now


def ingest(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Store messages of stations with an active IMGW archive; others (auxiliary
    stations, or WMO ids whose IMGW series ended long ago) are dropped."""
    if df.empty:
        return 0
    wmo_map = dict(con.execute(f"""
        SELECT s.wmo_id, s.imgw_id FROM stations s JOIN ({_ARCHIVE_END}) a USING (imgw_id)
    """).fetchall())
    df = df.assign(imgw_id=df["wmo_id"].map(wmo_map))
    df = df[df["imgw_id"].notna()].copy()
    if df.empty:
        return 0
    df["received_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    cols = [c for c in (r[0] for r in con.execute("DESCRIBE synop_msg_obs").fetchall()) if c in df.columns]
    con.register("_syn", df[cols])
    try:
        con.begin()
        con.execute("""DELETE FROM synop_msg_obs t USING _syn n
                       WHERE t.wmo_id = n.wmo_id AND t.ts = n.ts""")
        con.execute(f"INSERT INTO synop_msg_obs BY NAME SELECT {', '.join(cols)} FROM _syn")
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.unregister("_syn")
    return len(df)


def prune(con: duckdb.DuckDBPyConnection) -> int:
    """Drop messages the IMGW archive has superseded.

    A message is no longer needed once the station's daily archive covers its day
    (day D uses messages up to 06 UTC of D+1) and its hourly archive, if the
    station has a current one, covers its hour. Unmapped rows are dropped too.
    """
    return con.execute(f"""
        DELETE FROM synop_msg_obs m USING (
            SELECT d.imgw_id, max(d.date) AS last_date, any_value(h.last_ts) AS last_ts
            FROM daily_obs d
            LEFT JOIN (SELECT imgw_id, max(ts) AS last_ts FROM hourly_obs
                       WHERE source = 'synop' GROUP BY imgw_id) h USING (imgw_id)
            GROUP BY d.imgw_id
        ) a
        WHERE m.imgw_id IS NULL
           OR m.imgw_id NOT IN (SELECT imgw_id FROM ({_ARCHIVE_END}))
           OR (m.imgw_id = a.imgw_id
               AND m.ts <= a.last_date + INTERVAL 1 DAY + INTERVAL 6 HOUR
               AND (a.last_ts IS NULL OR a.last_ts < a.last_date OR m.ts <= a.last_ts))
    """).fetchone()[0]


# --------------------------------------------- spooling while the DB is busy ---

def spool(lines: list[str], spool_dir: Path) -> Path:
    spool_dir.mkdir(parents=True, exist_ok=True)
    path = spool_dir / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(lines), encoding="utf-8")
    os.replace(tmp, path)
    return path


def drain_spool(con: duckdb.DuckDBPyConnection, spool_dir: Path) -> int:
    n = 0
    for path in sorted(spool_dir.glob("*.json")):
        try:
            lines = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning("unreadable spool file %s (%s), set aside", path.name, e)
            os.replace(path, path.with_suffix(".bad"))
            continue
        n += ingest(con, decode_all(lines))
        path.unlink()
    return n


# ------------------------------------------------------------------- update ---

def update(cfg: Config, client: httpx.Client, days: int | None = None) -> dict:
    """Fetch messages for the pending window (or the last ``days``) and store them.

    The window is read without blocking writers; while a sync holds the database
    the last 12 hours are fetched and spooled for the next run.
    """
    spool_dir = cfg.live_spool_dir / "synop"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        with db.connect(cfg.db_path, read_only=True, wait=30) as con:
            begin, end = pending_window(con, now)
    except db.DatabaseLocked:
        begin, end = now - timedelta(hours=12), now
    if days:
        begin = now - timedelta(days=days)
    lines = fetch(client, begin, end)
    out = {"begin": begin, "end": end, "messages": len(lines)}
    try:
        con = db.connect(cfg.db_path)
    except db.DatabaseLocked:
        return {**out, "spooled_to": str(spool(lines, spool_dir))}
    with con:
        spooled = drain_spool(con, spool_dir)
        stored = ingest(con, decode_all(lines))
        pruned = prune(con)
        latest = con.execute("SELECT max(ts) FROM synop_msg_obs").fetchone()[0]
    return {**out, "stored": stored, "from_spool": spooled, "pruned": pruned, "latest": latest}
