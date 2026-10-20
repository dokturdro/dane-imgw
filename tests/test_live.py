"""Live spool, pruning, lock handling and listing retries."""

import subprocess
import sys
import textwrap
from datetime import datetime, timedelta

import httpx
import pandas as pd
import pytest

from imgw import crawl, db, download, live


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "t.duckdb")
    yield c
    c.close()


def _snap(fetched_at: datetime, temp: float) -> dict:
    stamp = fetched_at.replace(second=0, microsecond=0).isoformat(sep=" ")
    return {
        "fetched_at": fetched_at.isoformat(),
        "synop": [{"id_stacji": "12375", "data_pomiaru": fetched_at.date().isoformat(),
                   "godzina_pomiaru": str(fetched_at.hour), "temperatura": str(temp)}],
        "meteo": [{"kod_stacji": "999000001", "nazwa_stacji": "X", "lat": "52.1", "lon": "21.0",
                   "temperatura_powietrza": temp, "temperatura_powietrza_data": stamp}],
    }


def test_spooled_polls_are_ingested_once(con, tmp_path):
    spool = tmp_path / "spool"
    t0 = datetime(2026, 10, 17, 12, 0, 5)
    for i in range(3):
        live.spool(_snap(t0 + timedelta(minutes=10 * i), 10.0 + i), spool)
    live.spool(_snap(t0, 10.0), spool)          # same readings again, later file name
    assert live.drain_spool(con, spool) == 4    # 3 telemetry + 1 synop hour
    assert list(spool.iterdir()) == []
    assert live.ingest(con, _snap(t0, 10.0))["new_rows"] == 0
    assert con.execute("SELECT name FROM stations WHERE imgw_id = '999000001'").fetchone() == ("X",)


def test_bad_spool_file_is_set_aside(con, tmp_path):
    spool = tmp_path / "spool"
    spool.mkdir()
    (spool / "20261017T000000000000.json").write_text("{trunc", encoding="utf-8")
    assert live.drain_spool(con, spool) == 0
    assert [p.suffix for p in spool.iterdir()] == [".bad"]


def test_prune_drops_old_unarchived_rows_and_resolves_synop_ids(con):
    now = datetime.now().replace(microsecond=0)
    rows = [dict(imgw_id=None, station_key="12375", network="synop_live", ts=now,
                 variable="temperatura", value=1.0, fetched_at=now)]
    rows += [dict(imgw_id="999000001", station_key="999000001", network="telemetry",
                  ts=now - timedelta(days=d), variable="temperatura_powietrza",
                  value=1.0, fetched_at=now) for d in (1, 30, 500)]
    db.insert_df(con, "live_obs", pd.DataFrame(rows))
    con.execute("INSERT INTO stations (imgw_id, name, wmo_id) VALUES ('352200375', 'W', '12375')")

    assert live.prune(con, keep_days=400) == 1
    assert con.execute("SELECT imgw_id FROM live_obs WHERE network = 'synop_live'").fetchone() == ("352200375",)
    assert con.execute("SELECT count(*) FROM live_obs WHERE network = 'telemetry'").fetchone() == (2,)


def test_connect_reports_lock_held_by_other_process(tmp_path):
    path = tmp_path / "held.duckdb"
    holder = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(f"""
            import duckdb, sys, time
            con = duckdb.connect({str(path)!r})
            print("ready", flush=True)
            sys.stdin.read()
        """)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "ready"
        with pytest.raises(db.DatabaseLocked):
            db.connect(path)
    finally:
        holder.stdin.close()
        holder.wait(10)
    db.connect(path).close()


def test_list_dir_retries_transient_errors(monkeypatch):
    monkeypatch.setattr(download.time, "sleep", lambda s: None)
    calls = []
    page = ('<tr><td><a href="1991/">1991/</a></td>'
            '<td align="right">2024-01-01 10:00  </td><td align="right">  - </td></tr>')

    def handler(request):
        calls.append(request.url)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, text=page)

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        assert crawl.list_dir(c, "https://example.test/") == [("1991/", "2024-01-01 10:00", "-")]
    assert len(calls) == 2
