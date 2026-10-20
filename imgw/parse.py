"""Read IMGW archive ZIP/CSV files into DataFrames with status flags resolved.

Output keeps IMGW column codes (TMAX, SMDB, ...). Renaming to friendly names
and unit/code handling happens in :mod:`imgw.clean`.
"""

from __future__ import annotations

import io
import logging
import zipfile
from collections.abc import Iterator

import numpy as np
import pandas as pd

from .schema import ABSENT_IS_NULL, SPECS, TEXT_COLUMNS, kind_from_filename

log = logging.getLogger(__name__)

ENCODING = "cp1250"
KEY_COLUMNS = ("NSP", "POST", "ROK", "MC", "DZ", "GG")


def iter_zip(data: bytes) -> Iterator[tuple[str, str, bytes]]:
    """Yield (member_name, kind, raw_bytes) for every recognised CSV in a ZIP."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            kind = kind_from_filename(name)
            if kind is None or not name.lower().endswith(".csv"):
                log.debug("skipping unknown member %s", name)
                continue
            yield name, kind, zf.read(name)


def read_csv(raw: bytes, kind: str) -> pd.DataFrame:
    """Parse one CSV member and resolve value/status pairs.

    * status "8" (not measured)   -> NULL, whatever the value field says
    * status "9" (no phenomenon)  -> 0 (NULL for gusts, see ABSENT_IS_NULL)
    * status "Z" (opad cumulative) -> value kept, ``<COL>_Z`` = True
    * empty value without status  -> NULL

    Handles both the pre-2024 (``0,"8"`` / ``,""``) and post-2024 (``,"8"`` / ``,,``)
    encodings, since only the status field is trusted.
    """
    spec = SPECS[kind]
    df = pd.read_csv(
        io.BytesIO(raw),
        header=None,
        names=list(spec.columns),
        dtype=str,
        encoding=ENCODING,
        keep_default_na=False,
        na_filter=False,
        on_bad_lines="warn",
        skipinitialspace=True,
    )
    n_lines = raw.count(b"\n") + (0 if raw.endswith(b"\n") else 1)
    if n_lines - len(df) > 0 and raw.strip():
        log.warning("%s: %d malformed lines skipped", kind, n_lines - len(df))

    out = pd.DataFrame(
        {
            "imgw_id": df["NSP"].str.strip(),
            "name": df["POST"].str.strip(),
        }
    )
    y = pd.to_numeric(df["ROK"], errors="coerce")
    m = pd.to_numeric(df["MC"], errors="coerce")
    d = pd.to_numeric(df["DZ"], errors="coerce")
    date = pd.to_datetime(dict(year=y, month=m, day=d), errors="coerce")
    if "GG" in spec.columns:
        h = pd.to_numeric(df["GG"], errors="coerce")
        out["ts"] = date + pd.to_timedelta(h, unit="h")
    else:
        out["date"] = date.dt.date

    status_cols = spec.status_columns
    for col in spec.columns:
        if col in KEY_COLUMNS or col in status_cols:
            continue
        values = df[col].str.strip()
        if col in TEXT_COLUMNS:
            out[col] = values.replace("", None)
            continue
        num = pd.to_numeric(values, errors="coerce").astype("float64")
        st_name = spec.status_of(col)
        if st_name:
            st = df[st_name].str.strip()
            num = num.mask(st == "8", np.nan)
            num = num.mask(st == "9", np.nan if col in ABSENT_IS_NULL else 0.0)
            is_z = st == "Z"
            if is_z.any():
                out[f"{col}_Z"] = is_z
        out[col] = num

    bad = out["imgw_id"].eq("") | (out["ts"] if "ts" in out else out["date"]).isna()
    if bad.any():
        log.warning("%s: dropping %d rows without station/date", kind, int(bad.sum()))
        out = out[~bad]
    return out.reset_index(drop=True)


def read_zip(data: bytes) -> dict[str, pd.DataFrame]:
    """Parse every CSV in a ZIP, concatenated per kind."""
    parts: dict[str, list[pd.DataFrame]] = {}
    for _name, kind, raw in iter_zip(data):
        parts.setdefault(kind, []).append(read_csv(raw, kind))
    return {k: pd.concat(v, ignore_index=True) for k, v in parts.items()}


def read_station_list(raw: bytes) -> pd.DataFrame:
    """wykaz_stacji.csv: "id","name","id3"."""
    df = pd.read_csv(
        io.BytesIO(raw), header=None, names=["imgw_id", "name", "id3"],
        dtype=str, encoding=ENCODING, keep_default_na=False,
    )
    return df.apply(lambda s: s.str.strip())
