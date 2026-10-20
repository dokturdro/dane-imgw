"""SYNOP message layer: decoding, upserts, IMGW day conventions, pruning."""

from datetime import date, datetime

import pandas as pd
import pytest

from imgw import db, synop_feed

# real OGIMET lines (Opole 12530, Rozewie 12100), 2026-10-18
OPOLE_06 = ("12530,2026,10,18,06,00,AAXX 18061 12530 11950 30101 10063 20057 30035 40238 "
            "53016 60002 710// 80002 333 10114 20063 30004 55085==")
ROZEWIE_06 = ("12100,2026,10,18,06,00,AAXX 18061 12100 12470 80509 10125 20109 30266 40273 "
              "53016 60022 885// 333 10132 20120 31012 55001 70022 88616 90760 91117==")


def test_decode_section1_and_333():
    r = synop_feed.decode(OPOLE_06)
    assert r["wmo_id"] == "12530" and r["ts"] == datetime(2026, 10, 18, 6)
    assert (r["tm"], r["td"], r["ppp"], r["mslp"]) == (6.3, 5.7, 1003.5, 1023.8)
    assert (r["wind_dir"], r["wind_speed"], r["cloud_cover"], r["ww"]) == (10, 1, 3, 10)
    assert (r["tx_12h"], r["tn_12h"]) == (11.4, 6.3)
    assert r["sunshine_24h"] == 8.5                 # 55085, via the regex fallback
    assert r["prcp"] == 0 and r["prcp_period_h"] == 12
    assert r["snow_depth"] == 0.0                   # no 4E'sss group at 06 UTC = no snow
    assert r["tng_12h"] is None                     # whole-degree group deliberately not used
    assert r["rh"] == pytest.approx(95.9, abs=0.1)


def test_decode_gust_24h_precip_and_sunshine_group():
    r = synop_feed.decode(ROZEWIE_06)
    assert r["prcp_24h"] == 2.2 and r["prcp"] == 2 and r["prcp_period_h"] == 12
    assert r["wind_gust"] == 17                     # 911ff
    assert r["sunshine_24h"] == 0.1


def test_snow_codes():
    base = "12530,2026,01,10,06,00,AAXX 10061 12530 11950 30101 10063 20057 30035 40238 53016 710// 333 {}=="
    assert synop_feed.decode(base.format("4/005"))["snow_depth"] == 5
    assert synop_feed.decode(base.format("4/997"))["snow_depth"] == 0.25
    assert synop_feed.decode(base.format("4/998"))["snow_depth"] is None


def test_garbage_is_skipped():
    assert synop_feed.decode("12530,2026,10,18,06,00,NIL") is None
    assert synop_feed.decode("not,a,line") is None


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "t.duckdb")
    c.execute("INSERT INTO stations (imgw_id, name, wmo_id) VALUES ('350170530', 'OPOLE', '12530')")
    db.replace_rows(c, "daily_obs", pd.DataFrame({                       # active: archive to 30 Sep
        "imgw_id": ["350170530"], "date": [date(2026, 9, 30)], "source": ["synop"], "tm": [12.0]}))
    yield c
    c.close()


def _msg(day, hour, temp10, extra=""):
    ir = 1 if extra.startswith("6") else 4      # precipitation indicator: group present / omitted
    t = f"1{'0' if temp10 >= 0 else '1'}{abs(temp10):03d}"
    return (f"12530,2026,10,{day:02d},{hour:02d},00,AAXX {day:02d}{hour:02d}1 12530 {ir}1950 30101 "
            f"{t} 20057 30035 40238 53016 {extra}==")


def test_daily_conventions(con):
    lines = [_msg(17, h, 100) for h in range(0, 24, 3)]                        # tm = 10.0 on the 17th
    lines += [_msg(17, 6, 100, "60052 333 10150 20020"),                       # 18-06: Tx 15.0 Tn 2.0, 5 mm
              _msg(17, 18, 100, "60032 333 10180 20070"),                      # 06-18: Tx 18.0 Tn 7.0, 3 mm
              _msg(18, 6, 50, "60012 333 10120 20010 55085")]                  # next 06: 1 mm, sun 8.5 h
    synop_feed.ingest(con, synop_feed.decode_all(lines))
    d = con.execute("SELECT * FROM v_synop_daily WHERE date = '2026-10-17'").df().iloc[0]
    assert d["tm"] == 10.0
    assert (d["tx"], d["tn"]) == (18.0, 2.0)            # 18-18 UTC window
    assert d["prcp"] == 4.0                              # 18 UTC (3) + next 06 UTC (1)
    assert d["sunshine"] == 8.5                          # reported next morning
    prov = con.execute("SELECT prov_source, tm FROM v_provisional_daily WHERE date = '2026-10-17'").fetchone()
    assert prov == ("synop_msg", 10.0)


def test_correction_replaces_and_archive_prunes(con):
    synop_feed.ingest(con, synop_feed.decode_all([_msg(17, 12, 100)]))
    synop_feed.ingest(con, synop_feed.decode_all([_msg(17, 12, 120)]))           # CCA re-send
    assert con.execute("SELECT count(*), max(tm) FROM synop_msg_obs").fetchone() == (1, 12.0)
    assert con.execute("SELECT provisional FROM v_hourly WHERE imgw_id='350170530'").fetchone()[0]
    synop_feed.ingest(con, synop_feed.decode_all([_msg(18, 3, 80)]))
    # IMGW publishes the 17th: daily + hourly archive up to 17th 23 UTC
    db.replace_rows(con, "daily_obs", pd.DataFrame({
        "imgw_id": ["350170530"], "date": [date(2026, 10, 17)], "source": ["synop"], "tm": [9.0]}))
    db.replace_rows(con, "hourly_obs", pd.DataFrame({
        "imgw_id": ["350170530"], "ts": [datetime(2026, 10, 17, 23)], "source": ["synop"], "tm": [9.0]}))
    assert synop_feed.prune(con) == 1                       # 17th 12 UTC goes, 18th 03 UTC stays
    assert con.execute("SELECT count(*) FROM synop_msg_obs").fetchone()[0] == 1
    db.replace_rows(con, "daily_obs", pd.DataFrame({
        "imgw_id": ["350170530"], "date": [date(2026, 10, 18)], "source": ["synop"], "tm": [9.0]}))
    db.replace_rows(con, "hourly_obs", pd.DataFrame({
        "imgw_id": ["350170530"], "ts": [datetime(2026, 10, 18, 23)], "source": ["synop"], "tm": [9.0]}))
    assert synop_feed.prune(con) == 1
    assert con.execute("SELECT count(*) FROM synop_msg_obs").fetchone()[0] == 0


def test_pending_window(con):
    con.execute("INSERT INTO stations (imgw_id, name, wmo_id) VALUES ('353160215', 'SZCZECINEK', '12215')")
    daily = pd.DataFrame({"imgw_id": ["350170530", "353160215", "353160215"],
                          "date": [date(2026, 9, 30), date(2015, 1, 1), date(2015, 1, 2)],
                          "source": ["synop", "klimat", "klimat"], "tm": [9.0, 1.0, 1.0]})
    db.replace_rows(con, "daily_obs", daily)                # a long-closed station must not drag the window back
    now = datetime(2026, 10, 18, 9, 5)
    assert synop_feed.pending_window(con, now) == (datetime(2026, 10, 1, 0), now)
    synop_feed.ingest(con, synop_feed.decode_all([_msg(18, 8, 100)]))
    assert synop_feed.pending_window(con, now)[0] == datetime(2026, 10, 18, 2)   # last message - 6 h
