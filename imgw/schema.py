"""Column layouts of IMGW archive CSVs, transcribed from the *_format.txt files.

Files have no header row. A column named ``W<X>`` directly after column ``<X>``
is the measurement status of ``<X>`` ("8" = not measured, "9" = phenomenon
absent, "Z" = cumulative precipitation in opad files).
"""

from __future__ import annotations

from dataclasses import dataclass

# Columns that hold free text / letter codes rather than numbers.
TEXT_COLUMNS = {
    "NSP", "POST", "ROOP", "SGR", "HTXT", "POM1", "POM2", "WENT", "TWLW",
    "TECH", "CHLT", "CHMT", "CHHT",
}

# Status "9" (no phenomenon) normally means 0; for gusts "no gust" has no
# meaningful magnitude, so it becomes NULL.
ABSENT_IS_NULL = {"PORW", "PORK"}

_SPECS = {
    # dobowe/synop  s_d_*.csv
    "s_d": """NSP POST ROK MC DZ TMAX WTMAX TMIN WTMIN STD WSTD TMNG WTMNG SMDB WSMDB ROOP
        PKSN WPKSN RWSN WRWSN USL WUSL DESZ WDESZ SNEG WSNEG DISN WDISN GRAD WGRAD
        MGLA WMGLA ZMGL WZMGL SADZ WSADZ GOLO WGOLO ZMNI WZMNI ZMWS WZMWS ZMET WZMET
        FF10 WFF10 FF15 WFF15 BRZA WBRZA ROSA WROSA SZRO WSZRO DZPS WDZPS DZBL WDZBL
        SGR IZD WIZD IZG WIZG AKTN WAKTN""",
    # dobowe/synop  s_d_t_*.csv
    "s_d_t": """NSP POST ROK MC DZ NOS WNOS FWS WFWS TEMP WTEMP CPW WCPW WLGS WWLGS
        PPPS WPPPS PPPM WPPPM WODZ WWODZ WONO WWONO""",
    # terminowe/synop  s_t_*.csv
    "s_t": """NSP POST ROK MC DZ GG HPOD WHPOD HPON WHPON HPOW WHPOW HTXT POM1 POM2
        WID WWID WIDO WWIDO WIDA WWIDA NOG WNOG KRWR WKRWR FWR WFWR PORW WPORW
        TEMP WTEMP TTZW WTTZW WENT TWLW CPW WCPW WLGW WWLGW TPTR WTPTR PPPS WPPPS
        PPPM WPPPM TECH APP WAPP WO6G WWO6G ROPT WROPT POGB POGU CLCM WCLCM
        CHCL WCHCL CHLT CHCM WCHCM CHMT CHCH WCHCH CHHT SGRN WSGRN DEFI WDEFI
        USLN WUSLN ROSW WROSW PORK WPORK GODP MINP TG05 WTG05 TG10 WTG10
        TG20 WTG20 TG50 WTG50 TG100 WTG100 TMIN WTMIN TMAX WTMAX TGMI WTGMI
        RWSN WRWSN PKSN WPKSN HSS WHSS GRSN WGRSN GATS UKPO HPRO WHPRO CIPR WCIPR""",
    # dobowe/klimat  k_d_*.csv
    "k_d": """NSP POST ROK MC DZ TMAX WTMAX TMIN WTMIN STD WSTD TMNG WTMNG SMDB WSMDB ROOP
        PKSN WPKSN""",
    # dobowe/klimat  k_d_t_*.csv
    "k_d_t": """NSP POST ROK MC DZ TEMP WTEMP WLGS WWLGS FWS WFWS NOS WNOS""",
    # terminowe/klimat  k_t_*.csv
    "k_t": """NSP POST ROK MC DZ GG TEMP WTEMP TTZW WTTZW TWLW WENT WLGW WWLGW
        DKDK WDKDK FWR WFWR ZOGK WZOGK WID WWID""",
    # dobowe/opad  o_d_*.csv
    "o_d": """NSP POST ROK MC DZ SMDB WSMDB ROOP PKSN WPKSN HSS WHSS GATS WGATS
        RPSN WRPSN""",
}


@dataclass(frozen=True)
class FileSpec:
    kind: str
    columns: tuple[str, ...]

    def status_of(self, col: str) -> str | None:
        """Name of the status column belonging to ``col``, if it has one."""
        s = "W" + col
        i = self.columns.index(col)
        if i + 1 < len(self.columns) and self.columns[i + 1] == s:
            return s
        return None

    @property
    def status_columns(self) -> set[str]:
        return {s for c in self.columns if (s := self.status_of(c))}

    @property
    def value_columns(self) -> list[str]:
        st = self.status_columns
        return [c for c in self.columns if c not in st]


SPECS: dict[str, FileSpec] = {
    k: FileSpec(k, tuple(v.split())) for k, v in _SPECS.items()
}


def kind_from_filename(name: str) -> str | None:
    """'s_d_t_09_2026.csv' -> 's_d_t'; '1991_1995_100_s.zip' members likewise."""
    base = name.rsplit("/", 1)[-1].lower()
    # longest prefix first so s_d_t wins over s_d
    for kind in sorted(SPECS, key=len, reverse=True):
        if base.startswith(kind + "_"):
            return kind
    return None
