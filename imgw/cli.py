"""Command line: `uv run imgw --help`."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import config, db, download, live, sync, synop_feed

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="Local mirror of IMGW public meteorological data.")

ConfigOpt = Annotated[Optional[Path], typer.Option("--config", help="config.toml path")]

# Long enough for a live poll to finish; a busy sync makes `live` spool instead of waiting.
LOCK_WAIT = 600.0


def _setup(cfg_path: Path | None, verbose: bool = False) -> config.Config:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return config.load(cfg_path)


def _csv(v: str | None) -> list[str] | None:
    return [x.strip() for x in v.split(",") if x.strip()] if v else None


@app.command()
def init(cfg_path: ConfigOpt = None):
    """Create the database and load the station list."""
    cfg = _setup(cfg_path)
    with db.connect(cfg.db_path, wait=LOCK_WAIT) as con, download.client() as c:
        n = sync.load_stations(con, c)
    typer.echo(f"{cfg.db_path}: {n} stations")


@app.command("sync")
def sync_cmd(
    from_year: Annotated[Optional[int], typer.Option("--from", help="first year of daily data")] = None,
    hourly_from: Annotated[Optional[int], typer.Option(help="first year of hourly data")] = None,
    networks: Annotated[Optional[str], typer.Option(help="daily networks, e.g. synop,klimat,opad")] = None,
    hourly_networks: Annotated[Optional[str], typer.Option(help="hourly networks, e.g. synop,klimat")] = None,
    force: Annotated[bool, typer.Option(help="reload every file, ignoring sync_log")] = False,
    limit: Annotated[Optional[int], typer.Option(help="load at most N files (testing)")] = None,
    verbose: Annotated[bool, typer.Option("-v")] = False,
    cfg_path: ConfigOpt = None,
):
    """Download new/changed archive files and rebuild derived tables."""
    cfg = _setup(cfg_path, verbose)
    with db.connect(cfg.db_path, wait=LOCK_WAIT) as con, download.client() as c:
        r = sync.sync(con, c, cfg, start_year=from_year, hourly_start_year=hourly_from,
                      networks=_csv(networks), hourly_networks=_csv(hourly_networks),
                      force=force, limit=limit)
        spooled = live.drain_spool(con, cfg.live_spool_dir)
        pruned = live.prune(con, cfg.live_keep_days)
        synop_feed.drain_spool(con, cfg.live_spool_dir / "synop")
        pruned_msgs = synop_feed.prune(con)
    typer.echo(f"files listed {r.files_seen}, loaded {r.files_loaded}, failed {len(r.files_failed)}; rows {r.rows}; "
               f"live rows from spool {spooled}, pruned {pruned}; SYNOP rows superseded by archive {pruned_msgs}")
    if r.files_failed:
        raise typer.Exit(1)


@app.command("live")
def live_cmd(cfg_path: ConfigOpt = None):
    """Poll the live synop + telemetry APIs once (schedule every 10 minutes)."""
    cfg = _setup(cfg_path)
    with download.client() as c:
        r = live.update(cfg, c)
    typer.echo(f"database busy, saved poll to {r['spooled_to']}" if "spooled_to" in r else r)


@app.command("synop")
def synop_cmd(
    days: Annotated[Optional[int], typer.Option(help="fetch the last N days instead of the gap since the archive")] = None,
    cfg_path: ConfigOpt = None,
):
    """Fetch WMO SYNOP messages (OGIMET) from the archive end to now (schedule hourly at :25)."""
    cfg = _setup(cfg_path)
    with download.client() as c:
        r = synop_feed.update(cfg, c, days)
    head = f"window {r['begin']:%Y-%m-%d %H:%M} .. {r['end']:%Y-%m-%d %H:%M} UTC: {r['messages']} messages"
    if "spooled_to" in r:
        typer.echo(f"{head}; database busy, saved to {r['spooled_to']}")
    else:
        typer.echo(f"{head}, {r['stored']} rows stored, {r['from_spool']} from spool, "
                   f"{r['pruned']} superseded by archive; latest {r['latest']:%Y-%m-%d %H:%M} UTC")


@app.command()
def rebuild(cfg_path: ConfigOpt = None):
    """Recompute derived daily means, climate summaries, normals and QC."""
    cfg = _setup(cfg_path)
    with db.connect(cfg.db_path, wait=LOCK_WAIT) as con:
        typer.echo(sync.rebuild_derived(con, cfg))


@app.command()
def status(cfg_path: ConfigOpt = None):
    """Show coverage of every table."""
    cfg = _setup(cfg_path)
    with db.connect(cfg.db_path, read_only=True, wait=LOCK_WAIT) as con:
        typer.echo(sync.status(con).to_string(index=False))


@app.command()
def dash(
    port: Annotated[int, typer.Option(help="localhost port")] = 8501,
    open_browser: Annotated[bool, typer.Option("--open/--no-open", help="open a browser tab")] = True,
):
    """Start the local Streamlit dashboard (Ctrl+C to stop)."""
    app_path = Path(__file__).parent / "dash" / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path),
           "--server.port", str(port), "--server.address", "localhost",
           "--server.headless", "false" if open_browser else "true"]
    # cwd = project root so .streamlit/config.toml applies
    raise typer.Exit(subprocess.call(cmd, cwd=config.ROOT))


if __name__ == "__main__":
    app()
