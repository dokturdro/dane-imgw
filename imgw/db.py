"""DuckDB connection, schema bootstrap and replace-on-reload upserts."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from .config import ROOT

SCHEMA_SQL = ROOT / "sql" / "schema.sql"

log = logging.getLogger(__name__)

# "another process has the file" as DuckDB words it on Linux/macOS and on Windows
_LOCK_MARKERS = ("could not set lock", "used by another process", "already open")

# Natural key columns besides imgw_id; rows sharing a key are replaced on reload.
KEYS = {
    "daily_obs": ("date", "source"),
    "daily_agg": ("date", "source", "origin"),
    "hourly_obs": ("ts", "source"),
}


class DatabaseLocked(Exception):
    """Another process (a sync or a live poll) has the database open."""


def connect(path: Path, read_only: bool = False, wait: float = 0.0) -> duckdb.DuckDBPyConnection:
    """Open ``path``; while another process holds it, retry for up to ``wait`` seconds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait
    while True:
        try:
            con = duckdb.connect(str(path), read_only=read_only)
            break
        except duckdb.IOException as e:
            if not any(m in str(e).lower() for m in _LOCK_MARKERS):
                raise
            if time.monotonic() >= deadline:
                raise DatabaseLocked(f"{path} is open in another process") from e
            log.info("%s is busy, waiting", path.name)
            time.sleep(5)
    if not read_only:
        con.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    return con


def table_columns(con: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    return [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]


def replace_rows(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> int:
    """Delete rows with the same (imgw_id, key...) as ``df`` and insert ``df``.

    The caller owns the transaction.
    """
    if df.empty:
        return 0
    cols = [c for c in table_columns(con, table) if c in df.columns]
    time_col, *rest = KEYS[table]
    key_cols = ["imgw_id", time_col, *rest]
    con.register("_new", df[cols])
    try:
        lo, hi = con.execute(f"SELECT min({time_col}), max({time_col}) FROM _new").fetchone()
        join = " AND ".join(f"t.{k} = n.{k}" for k in key_cols)
        con.execute(
            f"""DELETE FROM {table} t USING (SELECT DISTINCT {', '.join(key_cols)} FROM _new) n
                WHERE t.{time_col} BETWEEN ? AND ? AND {join}""",
            [lo, hi],
        )
        con.execute(f"INSERT INTO {table} BY NAME SELECT {', '.join(cols)} FROM _new")
    finally:
        con.unregister("_new")
    return len(df)


def insert_df(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    cols = [c for c in table_columns(con, table) if c in df.columns]
    con.register("_ins", df[cols])
    try:
        con.execute(f"INSERT INTO {table} BY NAME SELECT {', '.join(cols)} FROM _ins")
    finally:
        con.unregister("_ins")


def synced_fingerprints(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    return dict(con.execute(
        "SELECT url, fingerprint FROM sync_log WHERE status = 'ok'"
    ).fetchall())


def log_sync(con, url: str, fingerprint: str, sha: str, rows: int, status: str) -> None:
    con.execute(
        "INSERT OR REPLACE INTO sync_log VALUES (?, ?, ?, ?, ?, ?)",
        [url, fingerprint, sha, rows, datetime.now(), status],
    )
