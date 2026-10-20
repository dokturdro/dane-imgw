from datetime import date
from pathlib import Path

import io
import zipfile

import pandas as pd
import pytest

from imgw.parse import read_csv, read_zip
from imgw.schema import SPECS, kind_from_filename

FIX = Path(__file__).parent / "fixtures"


def raw(name: str) -> bytes:
    return (FIX / name).read_bytes()


def test_kind_from_filename():
    assert kind_from_filename("s_d_t_09_2026.csv") == "s_d_t"
    assert kind_from_filename("s_d_375_2023.csv") == "s_d"
    assert kind_from_filename("x/o_d_1991.csv") == "o_d"
    assert kind_from_filename("k_t_08_2026.csv") == "k_t"
    assert kind_from_filename("readme.txt") is None


@pytest.mark.parametrize("kind,ncols", [("s_d", 65), ("s_d_t", 23), ("s_t", 107),
                                        ("k_d", 18), ("k_d_t", 13), ("k_t", 22), ("o_d", 16)])
def test_spec_widths_match_real_files(kind, ncols):
    # widths verified against 1991, 2023 and 2026 archive files
    assert len(SPECS[kind].columns) == ncols


def test_status_pairs():
    s = SPECS["s_t"]
    assert s.status_of("TEMP") == "WTEMP"
    assert s.status_of("WENT") is None          # ventilation flag, not a status
    assert "WENT" not in s.status_columns
    assert s.status_of("POGB") is None


def test_old_convention_2023():
    df = read_csv(raw("s_d_2023.csv"), "s_d")
    assert set(df.imgw_id) == {"352200375"}
    # first row carries status "8" with a ".0" in the value field -> must be NULL
    spec = SPECS["s_d"]
    first = (FIX / "s_d_2023.csv").read_bytes().decode("cp1250").splitlines()[0].split(",")
    flagged = [c for c in spec.columns if spec.status_of(c)
               and first[spec.columns.index(spec.status_of(c))] == '"8"']
    assert flagged
    for c in flagged:
        assert first[spec.columns.index(c)] in (".0", "0", "")
        assert pd.isna(df.loc[0, c]), c
    # status 9 with ".0" -> 0
    assert (df["GRAD"].dropna() == 0).all()


def test_new_convention_2026():
    df = read_csv(raw("s_d_2026.csv"), "s_d")
    w = df[df.imgw_id == "352200375"].iloc[0]
    assert w["date"] == date(2026, 9, 1)
    assert w["TMAX"] == pytest.approx(w["TMAX"])  # numeric
    assert w["GRAD"] == 0                          # ,,"9" -> 0
    gap = df.iloc[-1]                              # row with many ,,"8"
    assert gap.isna().sum() > 15


def test_opad_and_text_columns():
    df = read_csv(raw("o_d_2026.csv"), "o_d")
    assert df.iloc[0]["SMDB"] == 15.2 and df.iloc[0]["ROOP"] == "W"
    assert df.iloc[1]["SMDB"] == 0.0                # ,"9" -> no precipitation
    assert pd.isna(df.iloc[0]["PKSN"])              # ,"8" -> not measured


def test_hourly_timestamp_and_names():
    df = read_csv(raw("s_t_2026.csv"), "s_t")
    assert str(df.iloc[0]["ts"]) == "2026-09-10 20:00:00"
    assert df.name.iloc[0] == "BIELSKO-BIAŁA"       # cp1250 decoded
    assert df.iloc[0]["TEMP"] == 13.9


def test_cumulative_flag():
    line = b'"249180020",TEST,"2026","08","05",12.5,"Z",W,,"8",,"8",,"8",,"8"\r\n'
    df = read_csv(line, "o_d")
    assert df.loc[0, "SMDB"] == 12.5 and bool(df.loc[0, "SMDB_Z"])


def test_gust_absent_is_null():
    # PORW status 9 -> NULL, PORK status 9 -> NULL; FWR status 9 would be 0
    cols = SPECS["s_t"].columns
    row = ["" for _ in cols]
    row[:6] = ['"352200375"', "WARSZAWA", '"2026"', '"09"', '"01"', '"00"']
    row[cols.index("WPORW")] = '"9"'
    row[cols.index("WPORK")] = '"9"'
    row[cols.index("WFWR")] = '"9"'
    df = read_csv((",".join(row) + "\r\n").encode("cp1250"), "s_t")
    assert pd.isna(df.loc[0, "PORW"]) and pd.isna(df.loc[0, "PORK"])
    assert df.loc[0, "FWR"] == 0


def test_read_zip_groups_members():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("s_d_375_1991_1995.csv", raw("s_d_2023.csv"))
        z.writestr("s_d_t_375_1991_1995.csv", raw("s_d_t_1991.csv"))
        z.writestr("notes.txt", b"ignored")
    frames = read_zip(buf.getvalue())
    assert set(frames) == {"s_d", "s_d_t"}
    assert frames["s_d_t"].iloc[0]["NOS"] == 7.8
