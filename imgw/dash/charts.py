"""Altair charts. One y-axis per chart, 2px lines, recessive grid, tooltips on
every mark. Series colours are the dataviz reference palette's slots 1-2
(validated light & dark with validate_palette.js); text stays in theme ink."""

from __future__ import annotations

import altair as alt
import pandas as pd

from imgw.dash import style

MONTH_ABBR = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"]

THEMES = {
    "light": dict(s1="#2a78d6", s2="#eb6834", ink="#0b0b0b", ink2="#52514e", muted="#898781",
                  grid="#e1e0d9", axis="#c3c2b7", band="#e1e0d9", context="#c3c2b7",
                  div=["#184f95", "#f0efec", "#e34948"]),
    "dark": dict(s1="#3987e5", s2="#d95926", ink="#f0efec", ink2="#c3c2b7", muted="#898781",
                 grid="#2c2c2a", axis="#383835", band="#383835", context="#52514e",
                 div=["#3987e5", "#383835", "#e66767"]),
}


def _cfg(chart: alt.Chart, t: dict, height: int) -> alt.Chart:
    return (chart.properties(height=height, width="container")
            .configure_view(stroke=None)
            .configure_axis(gridColor=t["grid"], domainColor=t["axis"], tickColor=t["axis"],
                            labelColor=t["ink2"], titleColor=t["ink2"], labelFontSize=11,
                            titleFontSize=11, titleFontWeight="normal")
            .configure_legend(labelColor=t["ink2"], titleColor=t["ink2"], orient="top")
            .configure(background="transparent"))


def daily_temperature(df: pd.DataFrame, normal: pd.DataFrame | None, theme: str) -> alt.Chart:
    """tn-tx band, tm line, normal tm as a dashed step line."""
    t = THEMES[theme]
    d = df[["date", "tm", "tx", "tn"]].copy()
    d["date"] = pd.to_datetime(d["date"])
    base = alt.Chart(d).encode(x=alt.X("date:T", title=None, axis=alt.Axis(format="%d.%m")))
    tip = [alt.Tooltip("date:T", title="data", format="%Y-%m-%d"),
           alt.Tooltip("tm:Q", title="Tśr", format=".1f"),
           alt.Tooltip("tx:Q", title="Tmax", format=".1f"),
           alt.Tooltip("tn:Q", title="Tmin", format=".1f")]
    band = base.mark_area(opacity=0.25, color=t["s1"]).encode(
        y=alt.Y("tn:Q", title="°C", scale=alt.Scale(zero=False)), y2="tx:Q")
    line = base.mark_line(strokeWidth=2, color=t["s1"]).encode(y="tm:Q")
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", empty=False)
    pts = base.mark_point(size=60, filled=True, color=t["s1"]).encode(
        y="tm:Q", opacity=alt.condition(hover, alt.value(1), alt.value(0)), tooltip=tip
    ).add_params(hover)
    rule = base.mark_rule(color=t["muted"]).encode(
        opacity=alt.condition(hover, alt.value(0.6), alt.value(0))).transform_filter(hover)
    layers = [band, line, rule, pts]
    if normal is not None and not normal.empty:
        n = normal.copy()
        n["date"] = pd.to_datetime(n["date"])
        layers.insert(0, alt.Chart(n).mark_line(strokeDash=[4, 3], strokeWidth=1.5, color=t["muted"],
                                                interpolate="step-after").encode(
            x="date:T", y="normal:Q",
            tooltip=[alt.Tooltip("normal:Q", title="norma Tśr 1991–2020", format=".1f")]))
    return _cfg(alt.layer(*layers), t, 220)


def daily_precip(df: pd.DataFrame, theme: str) -> alt.Chart:
    t = THEMES[theme]
    d = df[["date", "prcp"]].copy()
    d["date"] = pd.to_datetime(d["date"])
    d["cum"] = d["prcp"].fillna(0).cumsum()
    bars = alt.Chart(d).mark_bar(color=t["s1"], cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%d.%m")),
        y=alt.Y("prcp:Q", title="opad [mm]"),
        tooltip=[alt.Tooltip("date:T", title="data", format="%Y-%m-%d"),
                 alt.Tooltip("prcp:Q", title="opad", format=".1f")])
    cum = alt.Chart(d).mark_line(strokeWidth=2, color=t["s1"]).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%d.%m")),
        y=alt.Y("cum:Q", title="suma [mm]"),
        tooltip=[alt.Tooltip("date:T", title="data", format="%Y-%m-%d"),
                 alt.Tooltip("cum:Q", title="suma od początku zakresu", format=".1f")])
    # two charts, two axes — never a dual axis
    return (alt.vconcat(bars.properties(height=130, width="container"),
                        cum.properties(height=100, width="container"))
            .configure_view(stroke=None)
            .configure_axis(gridColor=t["grid"], domainColor=t["axis"], tickColor=t["axis"],
                            labelColor=t["ink2"], titleColor=t["ink2"], titleFontWeight="normal")
            .configure(background="transparent"))


def hourly_temperature(df: pd.DataFrame, theme: str) -> alt.Chart:
    t = THEMES[theme]
    d = df[["date", "tm", "td"]].melt("date", var_name="series", value_name="value")
    d["series"] = d["series"].map({"tm": "temperatura", "td": "punkt rosy"})
    d = d.dropna(subset=["value"])
    series = alt.Scale(domain=["temperatura", "punkt rosy"], range=[t["s1"], t["s2"]])
    base = alt.Chart(d).encode(x=alt.X("date:T", title=None, axis=alt.Axis(format="%d.%m %H:%M")),
                               y=alt.Y("value:Q", title="°C", scale=alt.Scale(zero=False)))
    line = base.mark_line(strokeWidth=2).encode(color=alt.Color("series:N", title=None, scale=series))
    # dots filled with the table's temperature colours, ringed in the series colour
    dots = base.mark_point(size=55, filled=True, strokeWidth=1.5, opacity=1).encode(
        fill=alt.Fill("value:Q", legend=None,
                      scale=alt.Scale(type="threshold", domain=style.T2M_DOMAIN, range=style.T2M_RANGE)),
        stroke=alt.Stroke("series:N", title=None, scale=series),
        tooltip=[alt.Tooltip("date:T", title="czas UTC", format="%Y-%m-%d %H:%M"),
                 alt.Tooltip("series:N", title="seria"), alt.Tooltip("value:Q", format=".1f", title="°C")])
    # temperature labels above its dots, dew point below, so the two series don't collide
    text = [base.mark_text(dy=dy, fontSize=9, color=t["ink2"]).encode(text=alt.Text("value:Q", format=".1f"))
            .transform_filter(alt.datum.series == s) for s, dy in (("temperatura", -10), ("punkt rosy", 11))]
    return _cfg(alt.layer(line, dots, *text), t, 260)


def climograph(year_vals: pd.DataFrame, normals: pd.DataFrame, theme: str, unit: str,
               label: str, bars: bool = False) -> alt.Chart:
    """One variable for one year vs the 1991-2020 normal (mean ± sd band)."""
    t = THEMES[theme]
    n = normals.assign(lo=normals["mean"] - normals["sd"], hi=normals["mean"] + normals["sd"],
                       m=normals["month"].map(lambda m: MONTH_ABBR[m - 1]))
    y = year_vals.assign(m=year_vals["month"].map(lambda m: MONTH_ABBR[m - 1]))
    x = alt.X("m:N", sort=MONTH_ABBR, title=None, axis=alt.Axis(labelAngle=0))
    ntip = [alt.Tooltip("m:N", title="miesiąc"), alt.Tooltip("mean:Q", title="norma", format=".1f"),
            alt.Tooltip("sd:Q", title="odch. std.", format=".1f")]
    band = alt.Chart(n).mark_area(color=t["band"], opacity=0.8).encode(
        x=x, y=alt.Y("lo:Q", title=unit, scale=alt.Scale(zero=bars)), y2="hi:Q", tooltip=ntip)
    ytip = [alt.Tooltip("m:N", title="miesiąc"), alt.Tooltip("value:Q", title=label, format=".1f"),
            alt.Tooltip("is_partial:N", title="niepełny")]
    if bars:
        layers = [alt.Chart(y).mark_bar(color=t["s1"], opacity=0.85, size=18,
                                        cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
                      x=x, y=alt.Y("value:Q", title=unit), tooltip=ytip),
                  alt.Chart(n).mark_tick(color=t["ink"], thickness=2, size=24).encode(
                      x=x, y="mean:Q", tooltip=ntip)]
    else:
        layers = [band,
                  alt.Chart(n).mark_line(color=t["muted"], strokeWidth=1.5, strokeDash=[4, 3]).encode(
                      x=x, y="mean:Q", tooltip=ntip),
                  alt.Chart(y).mark_line(color=t["s1"], strokeWidth=2,
                                         point=alt.OverlayMarkDef(size=70, filled=True)).encode(
                      x=x, y="value:Q", tooltip=ytip)]
    return _cfg(alt.layer(*layers), t, 240)


def stripes(df: pd.DataFrame, theme: str) -> alt.Chart:
    """Warming stripes: annual anomaly vs 1991-2020, diverging around 0."""
    t = THEMES[theme]
    lim = max(abs(df["anomaly"].min()), abs(df["anomaly"].max()), 0.5)
    tip = [alt.Tooltip("year:O", title="rok"), alt.Tooltip("value:Q", title="Tśr", format=".1f"),
           alt.Tooltip("anomaly:Q", title="anomalia", format="+.1f")]
    color = alt.Color("anomaly:Q", title="anomalia [°C]",
                      scale=alt.Scale(domain=[-lim, 0, lim], range=t["div"], interpolate="lab"))
    strip = alt.Chart(df).mark_rect().encode(
        x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0, values=[y for y in df["year"] if y % 5 == 0])),
        color=color, tooltip=tip).properties(height=90, width="container")
    bars = alt.Chart(df).mark_bar(cornerRadius=2).encode(
        x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0, values=[y for y in df["year"] if y % 5 == 0])),
        y=alt.Y("anomaly:Q", title="anomalia [°C]"), color=alt.Color("anomaly:Q", scale=alt.Scale(
            domain=[-lim, 0, lim], range=t["div"], interpolate="lab"), legend=None), tooltip=tip
    ).properties(height=160, width="container")
    ext = df.loc[[df["anomaly"].idxmax(), df["anomaly"].idxmin()]]
    labels = alt.Chart(ext).mark_text(dy=-8, color=t["ink2"], fontSize=11).encode(
        x="year:O", y="anomaly:Q", text=alt.Text("anomaly:Q", format="+.1f"))
    return (alt.vconcat(strip, alt.layer(bars, labels)).configure_view(stroke=None)
            .configure_axis(gridColor=t["grid"], domainColor=t["axis"], tickColor=t["axis"],
                            labelColor=t["ink2"], titleColor=t["ink2"], titleFontWeight="normal")
            .configure_legend(labelColor=t["ink2"], titleColor=t["ink2"], orient="top")
            .configure(background="transparent"))


def cumulative(cum: pd.DataFrame, year: int, theme: str) -> alt.Chart:
    """Selected year's running precipitation vs mean 1991-2020 curve; driest/wettest as grey context."""
    t = THEMES[theme]
    totals = cum.groupby("year")["cum"].max()
    full = totals[totals.index < pd.Timestamp.today().year]
    normal = (cum[cum["year"].between(1991, 2020)].groupby("doy")["cum"].mean().reset_index()
              .assign(series="średnia 1991–2020"))
    parts = [normal]
    if len(full):
        for label, y in ((f"najsuchszy ({full.idxmin()})", full.idxmin()),
                         (f"najwilgotniejszy ({full.idxmax()})", full.idxmax())):
            parts.append(cum[cum["year"] == y][["doy", "cum"]].assign(series=label))
    sel = cum[cum["year"] == year][["doy", "cum"]].assign(series=str(year))
    ctx = pd.concat(parts, ignore_index=True)
    x = alt.X("doy:Q", title="dzień roku", scale=alt.Scale(domain=[1, 366]))
    tip = [alt.Tooltip("series:N", title="seria"), alt.Tooltip("doy:Q", title="dzień roku"),
           alt.Tooltip("cum:Q", title="suma [mm]", format=".0f")]
    grey = alt.Chart(ctx).mark_line(strokeWidth=1.5).encode(
        x=x, y=alt.Y("cum:Q", title="suma opadu [mm]"),
        color=alt.Color("series:N", legend=None, scale=alt.Scale(range=[t["muted"], t["context"], t["context"]])),
        strokeDash=alt.condition(alt.datum.series == "średnia 1991–2020", alt.value([4, 3]), alt.value([1, 0])),
        tooltip=tip)
    end = ctx.groupby("series").tail(1)
    glabels = alt.Chart(end).mark_text(align="left", dx=4, color=t["muted"], fontSize=11).encode(
        x=x, y="cum:Q", text="series:N")
    main = alt.Chart(sel).mark_line(strokeWidth=2.5, color=t["s1"]).encode(x=x, y="cum:Q", tooltip=tip)
    mlabel = alt.Chart(sel.tail(1)).mark_text(align="left", dx=4, color=t["ink"], fontWeight="bold").encode(
        x=x, y="cum:Q", text="series:N")
    return _cfg(alt.layer(grey, glabels, main, mlabel), t, 300)
