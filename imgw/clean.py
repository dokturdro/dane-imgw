"""Turn parsed IMGW frames into the tidy column sets stored in DuckDB.

Naming follows dane.meteomodel.pl where it has a name for a field
(tm, tx, tn, tng, prcp, snow_depth, ff10_time, ...).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# --- column maps: IMGW code -> table column -------------------------------

DAILY_SYNOP = {
    "TMAX": "tx", "TMIN": "tn", "STD": "tm", "TMNG": "tng",
    "SMDB": "prcp", "ROOP": "prcp_kind", "PKSN": "snow_depth", "RWSN": "snow_water",
    "USL": "sunshine", "DESZ": "ra_time", "SNEG": "sn_time", "DISN": "rasn_time",
    "GRAD": "hail_time", "MGLA": "fo_time", "ZMGL": "mist_time", "SADZ": "rime_time",
    "GOLO": "glaze_time", "ZMNI": "drift_low_time", "ZMWS": "drift_high_time",
    "ZMET": "haze_time", "FF10": "ff10_time", "FF15": "ff15_time", "BRZA": "ts_time",
    "ROSA": "dew_time", "SZRO": "frost_time", "DZPS": "snow_cover_day",
    "DZBL": "lightning_day", "SGR": "ground_state", "IZD": "isotherm_low_cm",
    "IZG": "isotherm_high_cm", "AKTN": "radiation",
}
DAILY_KLIMAT = {
    "TMAX": "tx", "TMIN": "tn", "STD": "tm", "TMNG": "tng",
    "SMDB": "prcp", "ROOP": "prcp_kind", "PKSN": "snow_depth",
}
DAILY_OPAD = {
    "SMDB": "prcp", "ROOP": "prcp_kind", "PKSN": "snow_depth",
    "HSS": "fresh_snow", "GATS": "snow_type", "RPSN": "snow_cover_type",
}
DAILY_AGG_SYNOP = {
    "NOS": "cloud_cover", "FWS": "wind_speed", "TEMP": "tm_terms", "CPW": "vapp",
    "WLGS": "rh", "PPPS": "ppp", "PPPM": "mslp", "WODZ": "prcp_day", "WONO": "prcp_night",
}
DAILY_AGG_KLIMAT = {"TEMP": "tm_terms", "WLGS": "rh", "FWS": "wind_speed", "NOS": "cloud_cover"}
HOURLY_SYNOP = {
    "HPOD": "cloud_base_code", "HPON": "cloud_base_low_m", "HPOW": "cloud_base_high_m",
    "WID": "visib_code", "WIDO": "visib_obs_m", "WIDA": "visib_auto_m",
    "NOG": "cloud_cover", "KRWR": "wind_dir", "FWR": "wind_speed", "PORW": "wind_gust",
    "TEMP": "tm", "TTZW": "wb", "CPW": "vapp", "WLGW": "rh", "TPTR": "td",
    "PPPS": "ppp", "PPPM": "mslp", "TECH": "p_tendency_code", "APP": "p_tendency",
    "WO6G": "prcp_6h", "ROPT": "prcp_kind_6h", "POGB": "ww", "POGU": "w1",
    "CLCM": "low_cloud_cover", "CHCL": "cl", "CHCM": "cm", "CHCH": "ch",
    "SGRN": "ground_state", "DEFI": "vpd", "USLN": "sunshine", "ROSW": "dew",
    "PORK": "wind_gust_ww", "TG05": "tg05", "TG10": "tg10", "TG20": "tg20",
    "TG50": "tg50", "TG100": "tg100", "TMIN": "tn_12h", "TMAX": "tx_12h",
    "TGMI": "tng_12h", "RWSN": "snow_water", "PKSN": "snow_depth", "HSS": "fresh_snow",
}
HOURLY_KLIMAT = {
    "TEMP": "tm", "TTZW": "wb", "WLGW": "rh", "DKDK": "wind_dir_code",
    "FWR": "wind_speed", "ZOGK": "cloud_cover", "WID": "visib_code",
}

DAILY_MAPS = {"s_d": ("synop", DAILY_SYNOP), "k_d": ("klimat", DAILY_KLIMAT),
              "o_d": ("opad", DAILY_OPAD)}
AGG_MAPS = {"s_d_t": ("synop", DAILY_AGG_SYNOP), "k_d_t": ("klimat", DAILY_AGG_KLIMAT)}
HOURLY_MAPS = {"s_t": ("synop", HOURLY_SYNOP), "k_t": ("klimat", HOURLY_KLIMAT)}

# Physical plausibility limits; values outside are kept but flagged.
RANGES = {
    "tm": (-50, 45), "tx": (-50, 45), "tn": (-50, 45), "tng": (-55, 45),
    "td": (-60, 35), "wb": (-50, 40), "rh": (0, 100), "mslp": (900, 1080),
    "ppp": (600, 1080), "prcp": (0, 400), "wind_speed": (0, 75),
    "wind_gust": (0, 90), "sunshine": (0, 17), "snow_depth": (0, 600),
}

SNOW_CODES = {997: "trace", 998: "patchy", 999: "unmeasurable"}

# Anything outside this cannot be sea-level pressure (Polish record low ~ 950 hPa).
MSLP_PLAUSIBLE = (900.0, 1100.0)


def _rename(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    keep = ["imgw_id", "date" if "date" in df else "ts"]
    cols = {k: v for k, v in mapping.items() if k in df}
    out = df[keep + list(cols)].rename(columns=cols)
    if "SMDB_Z" in df:
        out["prcp_cumulative"] = df["SMDB_Z"].fillna(False).astype(bool)
    return out


def _snow_codes(df: pd.DataFrame, col: str = "snow_depth") -> pd.DataFrame:
    if col not in df:
        return df
    v = df[col]
    code = pd.Series(pd.NA, index=df.index, dtype="string")
    for num, label in SNOW_CODES.items():
        code = code.mask(v == num, label)
    df[f"{col}_code"] = code
    df[col] = v.mask(v == 997, 0.25).mask(v.isin([998, 999]), np.nan)
    return df


def rebuild_qc(con) -> int:
    """Recompute qc_issues: out-of-range values and tx < tn. Values stay in the
    data tables; this table lists them so a dashboard can grey them out."""
    parts = []
    for tbl, tcol in (("daily_obs", "date"), ("hourly_obs", "ts")):
        cols = {r[0] for r in con.execute(f"DESCRIBE {tbl}").fetchall()}
        for var, (lo, hi) in RANGES.items():
            if var in cols:
                parts.append(
                    f"SELECT imgw_id, CAST({tcol} AS TIMESTAMP), '{tbl}', '{var}', {var}, "
                    f"'out_of_range[{lo},{hi}]' FROM {tbl} WHERE {var} < {lo} OR {var} > {hi}"
                )
    parts.append(
        "SELECT imgw_id, CAST(date AS TIMESTAMP), 'daily_obs', 'tx', tx, 'tx<tn' "
        "FROM daily_obs WHERE tx < tn"
    )
    con.execute("BEGIN")
    con.execute("DELETE FROM qc_issues")
    con.execute("INSERT INTO qc_issues " + "\nUNION ALL\n".join(parts))
    con.execute("COMMIT")
    return con.execute("SELECT count(*) FROM qc_issues").fetchone()[0]


def daily_obs(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    source, mapping = DAILY_MAPS[kind]
    out = _snow_codes(_rename(df, mapping))
    for flag in ("snow_cover_day", "lightning_day"):
        if flag in out:
            out[flag] = out[flag].map({1.0: True, 0.0: False}).astype("boolean")
    out.insert(2, "source", source)
    return out.drop_duplicates(["imgw_id", "date"], keep="last")


def daily_agg(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    source, mapping = AGG_MAPS[kind]
    out = _rename(df, mapping)
    out.insert(2, "source", source)
    out["origin"] = "imgw"
    return out.drop_duplicates(["imgw_id", "date"], keep="last")


def hourly_obs(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    source, mapping = HOURLY_MAPS[kind]
    out = _snow_codes(_rename(df, mapping))
    if "wind_dir" in out:
        out["wind_dir_variable"] = out["wind_dir"] == 999
        out["wind_dir"] = out["wind_dir"].mask(out["wind_dir"] == 999, np.nan)
        out["calm"] = (out["wind_speed"] == 0) & (out["wind_dir"].fillna(0) == 0)
    if "dew" in out:
        out["dew"] = out["dew"].map({1.0: True, 0.0: False}).astype("boolean")
    if "mslp" in out:
        # Mountain stations (Zakopane, Kasprowy Wierch, Śnieżka) reported the
        # geopotential height of an isobaric surface [gpm] in PPPM until 2015.
        out["mslp"] = out["mslp"].mask(~out["mslp"].between(*MSLP_PLAUSIBLE))
    out.insert(2, "source", source)
    return out.drop_duplicates(["imgw_id", "ts"], keep="last")


def frames_for(kind: str, df: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    """Dispatch a parsed frame to (table_name, cleaned frame)."""
    if kind in DAILY_MAPS:
        return "daily_obs", daily_obs(df, kind)
    if kind in AGG_MAPS:
        return "daily_agg", daily_agg(df, kind)
    if kind in HOURLY_MAPS:
        return "hourly_obs", hourly_obs(df, kind)
    raise ValueError(kind)
