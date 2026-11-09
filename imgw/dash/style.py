"""Cell colours and table styling.

Daily/hourly scales are ports of dane.meteomodel.pl's utils-daily.js / utils-hourly.js
(getT2MColor2JS, getRRRRColorJS, getSunshineColorJS, getCloudCoverColorJS,
getRHColorJS), so tables look the way the user is used to. Every rule sets both
background and text colour, so cells stay readable in light and dark themes.
The monthly class scale is a diverging red-grey-blue ramp (dataviz rules).
"""

from __future__ import annotations

import html
import math

import pandas as pd

from imgw.dash import labels

WHITE, BLACK = "#ffffff", "#000000"

# (min, background, text) — first row with value >= min wins
_T2M = [
    (50, "#000000", WHITE), (48, "#252525", WHITE), (46, "#525252", WHITE), (44, "#737373", WHITE),
    (42, "#969696", BLACK), (40, "#bdbdbd", BLACK), (38, "#662506", WHITE), (36, "#800026", WHITE),
    (34, "#bd0026", WHITE), (32, "#e31a1c", WHITE), (30, "#fc4e2a", WHITE), (28, "#fd8d3c", BLACK),
    (26, "#feb24c", BLACK), (24, "#fed976", BLACK), (22, "#ffeda0", BLACK), (20, "#ffffcc", BLACK),
    (18, "#f7fcb9", BLACK), (16, "#f7fcf5", BLACK), (14, "#e5f5e0", BLACK), (12, "#c7e9c0", BLACK),
    (10, "#a1d99b", BLACK), (8, "#74c476", BLACK), (6, "#41ab5d", WHITE), (4, "#238b45", WHITE),
    (2, "#006d2c", WHITE), (0, "#238443", WHITE), (-2, "#f7fbff", BLACK), (-4, "#deebf7", BLACK),
    (-6, "#c6dbef", BLACK), (-8, "#9ecae1", BLACK), (-10, "#6baed6", WHITE), (-12, "#4292c6", WHITE),
    (-14, "#2171b5", WHITE), (-16, "#08519c", WHITE), (-18, "#8c6bb1", WHITE), (-20, "#88419d", WHITE),
    (-22, "#810f7c", WHITE), (-24, "#dd3497", WHITE), (-26, "#f768a1", WHITE), (-28, "#fa9fb5", BLACK),
    (-30, "#fcc5c0", BLACK), (-32, "#fde0dd", BLACK), (-34, "#f0f0f0", BLACK), (-36, "#d9d9d9", BLACK),
    (-38, "#bdbdbd", BLACK), (-40, "#969696", BLACK), (-42, "#737373", WHITE), (-44, "#525252", WHITE),
    (-46, "#252525", WHITE), (-100, "#000000", WHITE),
]
# the same scale as a Vega-Lite threshold scale for charts: domain = lower bounds above the floor
T2M_DOMAIN = [lo for lo, _, _ in reversed(_T2M[:-1])]
T2M_RANGE = [bg for _, bg, _ in reversed(_T2M)]


def _missing(v: object) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA


def _css(bg: str, fg: str) -> str:
    return f"background-color: {bg}; color: {fg}"


def temperature(v: float | None) -> str:
    if _missing(v):
        return ""
    for lo, bg, fg in _T2M:
        if v >= lo:
            return _css(bg, fg)
    return ""


def precipitation(v: float | None) -> str:
    if _missing(v):
        return ""
    if v < 0:
        return _css("#cccccc", BLACK)
    if v == 0:
        return _css(WHITE, BLACK)
    for hi, bg, fg in ((1, "#99ccff", BLACK), (10, "#3399ff", WHITE), (25, "#3366ff", WHITE),
                       (50, "#0000cc", WHITE), (100, "#000066", WHITE), (150, "#660066", WHITE),
                       (200, "#ffccff", BLACK)):
        # meteomodel: (0,1] then [1,10) [10,25) ... — only 1 itself is inclusive at the top
        if v < hi or (hi == 1 and v == 1):
            return _css(bg, fg)
    return _css("#000000", WHITE)


def sunshine_daily(v: float | None) -> str:
    if _missing(v) or v < 0:
        return ""
    steps = [("#ffffcc", BLACK), ("#ffeda0", BLACK), ("#fed976", BLACK), ("#feb24c", BLACK),
             ("#fd8d3c", WHITE), ("#fc4e2a", WHITE), ("#e31a1c", WHITE), ("#bd0026", WHITE),
             ("#800026", WHITE)]
    return _css(*steps[min(int(v // 2), 8)])


def sunshine_hourly(v: float | None) -> str:
    if _missing(v) or v < 0:
        return ""
    # meteomodel's hourly scale in 0.1 h steps (its 0.7-0.8 gap renders white; kept as-is)
    steps = [("#ffffcc", BLACK), ("#ffeda0", BLACK), ("#fed976", BLACK), ("#feb24c", BLACK),
             ("#fd8d3c", WHITE), ("#fc4e2a", WHITE), ("#e31a1c", WHITE)]
    if v >= 1:
        return _css("#800026", WHITE)
    if v >= 0.8:
        return _css("#bd0026", WHITE)
    i = int(round(v * 10, 6))
    return _css(*steps[i]) if i < len(steps) else _css(WHITE, BLACK)


def cloud_cover(v: float | None) -> str:
    """Oktas."""
    if _missing(v):
        return ""
    for hi, bg, fg in ((1, "#ccffff", BLACK), (2, "#cccccc", BLACK), (4, "#999999", BLACK),
                       (6, "#666666", WHITE)):
        if v <= hi:
            return _css(bg, fg)
    return _css("#333333", WHITE) if v < 8 else _css("#000000", WHITE)


def humidity(v: float | None) -> str:
    if _missing(v):
        return ""
    for hi, bg, fg in ((10, "#f0f0f5", BLACK), (25, "#e0e0eb", BLACK), (50, "#b3b3cc", BLACK),
                       (75, "#52527a", WHITE), (90, "#33334d", WHITE)):
        if v <= hi:
            return _css(bg, fg)
    return _css("#1f1f2e", WHITE)


DAILY_SCALES = {
    "tm": temperature, "tx": temperature, "tn": temperature, "tng": temperature, "tm2": temperature,
    "prcp": precipitation, "sunshine": sunshine_daily, "cloud_cover": cloud_cover, "rh": humidity,
}
HOURLY_SCALES = {
    "tm": temperature, "tx": temperature, "tn": temperature, "tng": temperature, "td": temperature,
    "wb": temperature, "prcp": precipitation, "sunshine": sunshine_hourly,
    "cloud_cover": cloud_cover, "low_cloud_cover": cloud_cover, "rh": humidity,
}

# Monthly classes 1 (extremely high) .. 11 (extremely low): red arm, grey middle, blue arm.
# Blue steps are the dataviz reference sequential ramp; red mirrors it in lightness.
CLASS_COLORS = {
    1: ("#7a1717", WHITE), 2: ("#b52a2a", WHITE), 3: ("#e34948", WHITE),
    4: ("#f2a09e", BLACK), 5: ("#fbd5d4", BLACK), 6: ("#f0efec", BLACK),
    7: ("#cde2fb", BLACK), 8: ("#86b6ef", BLACK), 9: ("#3987e5", WHITE),
    10: ("#1c5cab", WHITE), 11: ("#0d366b", WHITE),
}
PARTIAL = "color: #898781; font-style: italic"


def class_css(cls: float | None) -> str:
    if _missing(cls):
        return ""
    bg, fg = CLASS_COLORS[int(cls)]
    return _css(bg, fg)


# meteomodel's intVariable(): shown without decimals
INT_VARS = {"txgt35", "txgt30", "txgt25", "txgt20", "txgt15", "txgt10", "txlt10", "txlt0",
            "txltm10", "tnlt10", "tnlt0", "tnltm10", "tnltm20", "tnltm30", "tngt10", "tngt15",
            "tngt20", "hot", "snow_depth", "sndpx", "sndpcnt"}


# hourly codes, directions, oktas and RH are whole numbers in the source
HOURLY_WHOLE = {"wind_dir", "cloud_cover", "low_cloud_cover", "cl", "cm", "ch", "ww", "w1", "rh",
                "wind_speed", "wind_gust"}


def fmt_num(v: float | None, digits: int = 1) -> str:
    """Fixed decimals without the "-0.0" that rounding tiny negatives produces."""
    if _missing(v):
        return ""
    out = f"{v:.{digits}f}"
    return out[1:] if out.startswith("-") and float(out) == 0 else out


def style_frame(df: pd.DataFrame, scales: dict, decimals: int = 1, whole: set[str] = frozenset()):
    """pandas Styler with per-column colour scales and 1-decimal formatting.

    ``whole`` lists extra columns shown without decimals (codes, oktas).
    """
    df = df.copy()
    for c in df.columns:   # all-empty columns arrive as object dtype; make them blank floats
        if df[c].dtype == object and df[c].isna().all():
            df[c] = df[c].astype("float64")
    sty = df.style.format(na_rep="")
    for col, fn in scales.items():
        if col in df.columns:
            sty = sty.map(fn, subset=[col])
    num = [c for c in df.columns if pd.api.types.is_float_dtype(df[c])]
    ints = [c for c in num if c in INT_VARS or c in whole or c.endswith("_code")]
    return (sty.format(lambda v: fmt_num(v, decimals), subset=[c for c in num if c not in ints])
               .format(lambda v: fmt_num(v, 0), subset=ints))


# --------------------------------------------------- monthly grid (HTML) ---

COL_NAMES = {**{str(i + 1): m for i, m in enumerate(labels.MONTH_ABBR)}, "DJF": "DJF", "MAM": "MAM",
             "JJA": "JJA", "SON": "SON", "year": "Rok"}


def grid_html(grid: dict[str, pd.DataFrame], variable: str, normal_label: str) -> str:
    """Year × month/season grid as HTML: class colours, record marks, tooltips."""
    val, cls, part = grid["value"], grid["class"], grid["partial"]
    hi, lo, dp, dm, an = (grid["is_record_high"], grid["is_record_low"], grid["days_present"],
                          grid["days_missing"], grid["anomaly"])
    digits = 0 if variable in INT_VARS else 1

    def cell(y, c):
        v = val.at[y, c]
        if pd.isna(v):
            return ""
        mark = " ▲" if hi.at[y, c] is True else " ▼" if lo.at[y, c] is True else ""
        return f"{fmt_num(v, digits)}{mark}"

    shown = pd.DataFrame({c: [cell(y, c) for y in val.index] for c in val.columns}, index=val.index)

    def css(y, c):
        if pd.isna(val.at[y, c]):
            return ""
        if part.at[y, c] is True:
            return PARTIAL
        s = class_css(cls.at[y, c])
        return s + ("; font-weight: 700" if (hi.at[y, c] is True or lo.at[y, c] is True) else "")

    def tip(y, c):
        if pd.isna(val.at[y, c]):
            return ""
        k = cls.at[y, c]
        parts = [f"{COL_NAMES[c]} {y}: {val.at[y, c]:.{digits}f}",
                 "niepełny (za dużo braków)" if part.at[y, c] is True else
                 f"klasa {int(k)}: {labels.CLASS_NAMES[int(k)]}" if pd.notna(k) else "",
                 "rekord: najwyższa" if hi.at[y, c] is True else "rekord: najniższa" if lo.at[y, c] is True else "",
                 f"anomalia vs {normal_label}: {an.at[y, c]:+.1f}" if pd.notna(an.at[y, c]) else "",
                 f"dni z danymi {int(dp.at[y, c])}, braki {int(dm.at[y, c])}"]
        return html.escape(" · ".join(p for p in parts if p))

    styles = pd.DataFrame({c: [css(y, c) for y in val.index] for c in val.columns}, index=val.index)
    tips = pd.DataFrame({c: [tip(y, c) for y in val.index] for c in val.columns}, index=val.index)
    shown.columns = [COL_NAMES[c] for c in shown.columns]
    styles.columns = tips.columns = shown.columns
    shown.index.name = None
    sty = (shown.style.apply(lambda _: styles, axis=None).set_tooltips(tips, props=(
        "visibility: hidden; position: absolute; z-index: 10; background: #1a1a19; color: #f0efec;"
        "padding: 4px 8px; border-radius: 4px; font-size: 12px; white-space: nowrap; transform: translate(-40%, 22px);"))
           .set_table_styles([
               {"selector": "", "props": "border-collapse: separate; border-spacing: 2px; font-size: 13px;"
                                         "font-variant-numeric: tabular-nums;"},
               {"selector": "td", "props": "padding: 3px 6px; text-align: right; border-radius: 3px; min-width: 44px;"},
               {"selector": "th", "props": "padding: 3px 6px; font-weight: 600; text-align: right;"},
               {"selector": "td:nth-child(14)", "props": "border-left: 6px solid transparent;"},
           ]))
    return f'<div style="overflow-x:auto">{sty.to_html()}</div>'


def means_html(means: pd.DataFrame, variable: str) -> str:
    digits = 0 if variable in INT_VARS else 1
    m = means.copy()
    m.columns = [COL_NAMES[c] for c in m.columns]
    sty = m.style.format(lambda v: fmt_num(v, digits)).set_table_styles([
        {"selector": "", "props": "border-spacing: 2px; font-size: 13px; font-variant-numeric: tabular-nums;"},
        {"selector": "td", "props": "padding: 3px 6px; text-align: right; min-width: 44px;"},
        {"selector": "th", "props": "padding: 3px 6px; text-align: right; font-weight: 600;"}])
    return f'<div style="overflow-x:auto">{sty.to_html()}</div>'


def legend_html() -> str:
    sw = "".join(
        f'<span title="{html.escape(labels.CLASS_NAMES[k])}" style="display:inline-block;padding:2px 7px;'
        f'margin:1px;border-radius:3px;font-size:12px;background:{bg};color:{fg}">{k}</span>'
        for k, (bg, fg) in CLASS_COLORS.items())
    return (f'<div style="font-size:12px">{sw} &nbsp; 1 = ekstremalnie wysoka … 6 = normalna … '
            f'11 = ekstremalnie niska (percentyle całego okresu stacji) · ▲▼ rekord · '
            f'<i style="color:#898781">kursywa</i> = niepełny</div>')
