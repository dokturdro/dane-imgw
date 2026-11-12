"""Altair charts. One y-axis per chart (except the forecast's precipitation + wind panel), 2px lines, recessive grid, tooltips on
every mark. Series colours are the dataviz reference palette's slots 1-2
(validated light & dark with validate_palette.js); text stays in theme ink."""

from __future__ import annotations

import altair as alt
import pandas as pd

from imgw.dash import style
from imgw.dash.labels import MONTH_ABBR

LOCAL_TZ = "Europe/Warsaw"


def to_local(df: pd.DataFrame | None, cols=("date",)) -> pd.DataFrame | None:
    """Copy with naive-UTC ``cols`` turned into naive Polish local time (CET/CEST), for the charts."""
    if df is None or df.empty:
        return df
    out = df.copy()
    for c in cols:
        out[c] = (pd.to_datetime(out[c]).dt.tz_localize("UTC").dt.tz_convert(LOCAL_TZ).dt.tz_localize(None))
    return out


def utc_offset_label(dates: pd.Series) -> str:
    """"UTC+1", "UTC+2", or "UTC+1/+2" when the span crosses a clock change, for naive-UTC ``dates``."""
    hours = sorted({int(o.total_seconds() // 3600) for o in
                    pd.to_datetime(dates).dt.tz_localize("UTC").dt.tz_convert(LOCAL_TZ).map(lambda t: t.utcoffset())})
    return "UTC" + "/".join(f"+{h}" for h in hours) if hours else "UTC"


RAIN_STOPS_MM = [0, 2.5, 10, 22.5, 40]  # daily totals pinned to each THEMES "rain" colour

THEMES = {
    "light": dict(s1="#2a78d6", s2="#eb6834", s3="#86b6ef", night="rgba(82, 81, 78, 0.13)", fc_label="#b8b7b0", now_rule="#adaca5", ink="#0b0b0b", ink2="#52514e", muted="#898781",
                  grid="#e1e0d9", axis="#c3c2b7", band="#e1e0d9", context="#c3c2b7",
                  div=["#184f95", "#f0efec", "#e34948"],
                  frost="rgba(158, 197, 244, 0.35)",
                  rain=["#9ec5f4", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"]),
    "dark": dict(s1="#3987e5", s2="#d95926", s3="#9ec5f4", night="rgba(195, 194, 183, 0.10)", fc_label="#62615d", now_rule="#6b6a65", ink="#f0efec", ink2="#c3c2b7", muted="#898781",
                 grid="#2c2c2a", axis="#383835", band="#383835", context="#52514e",
                 div=["#3987e5", "#383835", "#e66767"],
                 frost="rgba(57, 135, 229, 0.18)",
                 rain=["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf"]),
}


def _style(chart, palette: dict):
    # configure() replaces the whole config, so it has to come before the specific configure_* calls
    return (chart.configure(background="transparent")
            .configure_view(stroke=None)
            .configure_axis(gridColor=palette["grid"], domainColor=palette["axis"], tickColor=palette["axis"],
                            labelColor=palette["ink2"], titleColor=palette["ink2"], labelFontSize=11,
                            titleFontSize=11, titleFontWeight="normal")
            .configure_legend(labelColor=palette["ink2"], titleColor=palette["ink2"], orient="top"))


def _cfg(chart: alt.Chart, palette: dict, height: int) -> alt.Chart:
    return _style(chart.properties(height=height, width="container"), palette)


def daily_temperature(df: pd.DataFrame, normal: pd.DataFrame | None, normal_label: str, theme: str) -> alt.Chart:
    """tn-tx band, tm line, normal tm as a dashed step line."""
    palette = THEMES[theme]
    d = df[["date", "tm", "tx", "tn"]].copy()
    d["date"] = pd.to_datetime(d["date"])
    base = alt.Chart(d).encode(x=alt.X("date:T", title=None, axis=alt.Axis(format="%d.%m")))
    tip = [alt.Tooltip("date:T", title="data", format="%Y-%m-%d"),
           alt.Tooltip("tm:Q", title="Tśr", format=".1f"),
           alt.Tooltip("tx:Q", title="Tmax", format=".1f"),
           alt.Tooltip("tn:Q", title="Tmin", format=".1f")]
    band = base.mark_area(opacity=0.25, color=palette["s1"]).encode(
        y=alt.Y("tn:Q", title="°C", scale=alt.Scale(zero=False)), y2="tx:Q")
    line = base.mark_line(strokeWidth=2, color=palette["s1"]).encode(y="tm:Q")
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", empty=False)
    pts = base.mark_point(size=60, filled=True, color=palette["s1"]).encode(
        y="tm:Q", opacity=alt.condition(hover, alt.value(1), alt.value(0)), tooltip=tip
    ).add_params(hover)
    rule = base.mark_rule(color=palette["muted"]).encode(
        opacity=alt.condition(hover, alt.value(0.6), alt.value(0))).transform_filter(hover)
    layers = [band, line, rule, pts]
    if normal is not None and not normal.empty:
        n = normal.copy()
        n["date"] = pd.to_datetime(n["date"])
        layers.insert(0, alt.Chart(n).mark_line(strokeDash=[4, 3], strokeWidth=1.5, color=palette["muted"],
                                                interpolate="step-after").encode(
            x="date:T", y="normal:Q",
            tooltip=[alt.Tooltip("normal:Q", title=f"norma Tśr {normal_label}", format=".1f")]))
    return _cfg(alt.layer(*layers), palette, 220)


def daily_precip(df: pd.DataFrame, theme: str) -> alt.Chart:
    palette = THEMES[theme]
    d = df[["date", "prcp"]].copy()
    d["date"] = pd.to_datetime(d["date"])
    d["cum"] = d["prcp"].fillna(0).cumsum()
    # each bar spans its whole day, centred on the date, less a 1px gap between neighbours
    half_day = pd.Timedelta(hours=12)
    d["start"], d["end"] = d["date"] - half_day, d["date"] + half_day
    bars = alt.Chart(d).mark_bar(xOffset=0.5, x2Offset=-0.5, cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
        x=alt.X("start:T", title=None, axis=alt.Axis(format="%d.%m")), x2="end:T",
        y=alt.Y("prcp:Q", title="opad [mm]"), y2=alt.datum(0),
        # fixed mm stops, so a shade means the same rainfall whatever the date range
        color=alt.Color("prcp:Q", legend=None, scale=alt.Scale(
            domain=RAIN_STOPS_MM, range=palette["rain"], clamp=True)),
        tooltip=[alt.Tooltip("date:T", title="data", format="%Y-%m-%d"),
                 alt.Tooltip("prcp:Q", title="opad", format=".1f")])
    cum = alt.Chart(d).mark_line(strokeWidth=2, color=palette["s1"]).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%d.%m")),
        y=alt.Y("cum:Q", title="suma [mm]"),
        tooltip=[alt.Tooltip("date:T", title="data", format="%Y-%m-%d"),
                 alt.Tooltip("cum:Q", title="suma od początku zakresu", format=".1f")])
    # two charts, two axes — never a dual axis
    return _style(alt.vconcat(bars.properties(height=130, width="container"),
                        cum.properties(height=100, width="container"))
            .resolve_scale(x="shared"), palette)


def _frost(palette: dict, scale: str = "y", height: str = "height") -> alt.Chart:
    """Sub-zero shading, positioned from the y scale so it can't stretch the axis to reach 0:
    clamped to the plot, it collapses to nothing when 0 lies below the visible range."""
    return alt.Chart(alt.Data(values=[{}])).mark_rect(
        color=palette["frost"], x=0, x2=alt.expr("range('x')[1]"),
        y=alt.expr(f"clamp(scale('{scale}', 0), 0, {height})"), y2=alt.expr(height))


SERIES = {"tm": "temperatura", "td": "punkt rosy"}


def _melt(df: pd.DataFrame) -> pd.DataFrame:
    d = df[["date", "tm", "td"]].melt("date", var_name="series", value_name="value")
    d["series"] = d["series"].map(SERIES)
    d["date"] = pd.to_datetime(d["date"])
    return d.dropna(subset=["value"])


FC_T = "prognoza T"


def _midnights(*frames: pd.DataFrame, include_start: bool = False) -> pd.DataFrame:
    """Every 00:00 inside the frames' time span (the span's first instant only with ``include_start``)."""
    dates = pd.concat([pd.to_datetime(f["date"]) for f in frames if f is not None and not f.empty])
    days = pd.date_range(dates.min().ceil("D"), dates.max(), freq="D")
    if not include_start:
        return pd.DataFrame({"date": days[days > dates.min()]})
    # label the first day at the left edge even when the data starts after its midnight
    return pd.DataFrame({"date": days if dates.min() in days else days.insert(0, dates.min())})


def _ticks(freq: str, *frames: pd.DataFrame) -> list[alt.DateTime]:
    """Tick values every ``freq`` ("3h", "D") across the frames' span; DateTime keeps them in the
    data's (naive) time."""
    dates = pd.concat([pd.to_datetime(f["date"]) for f in frames if f is not None and not f.empty])
    if dates.empty:
        return []
    ticks = pd.date_range(dates.min().ceil(freq), dates.max(), freq=freq)
    if freq == "D" and dates.min() not in ticks:     # name the first (partial) day at the left edge
        ticks = ticks.insert(0, dates.min())
    return [alt.DateTime(year=ts.year, month=ts.month, date=ts.day, hours=ts.hour)
            for ts in ticks]


def hourly_temperature(df: pd.DataFrame, theme: str, forecast: pd.DataFrame | None = None,
                       past: pd.DataFrame | None = None, sun: pd.DataFrame | None = None) -> alt.Chart:
    """Observed temperature and dew point, plus the temperature forecast as its own line.

    ``past``: the forecast issued 24 h earlier for the observed hours (prediction vs result);
    ``forecast``: the latest forecast after the last observation (temperature and dew point);
    ``sun``: sunrise / sunset times, nights greyed out.
    """
    palette = THEMES[theme]
    d = _melt(df)
    series = alt.Scale(domain=[*SERIES.values(), FC_T], range=[palette["s1"], palette["s2"], palette["s3"]])
    color = alt.Color("series:N", title=None, scale=series)
    # hours below (every 3 h); the date sits on top, once per day, over its midnight separator
    axis = alt.Axis(format="%H", labelAngle=0, labelOverlap=False, values=_ticks("3h", d, forecast))
    x = alt.X("date:T", title=None, axis=axis)
    base = alt.Chart(d).encode(x=x, y=alt.Y("value:Q", title="°C", scale=alt.Scale(zero=False)))
    line = base.mark_line(strokeWidth=2).encode(color=color)
    # dots filled with the table's temperature colours, ringed in the series colour
    dots = base.mark_point(size=55, filled=True, strokeWidth=1.5, opacity=1).encode(
        fill=alt.Fill("value:Q", legend=None,
                      scale=alt.Scale(type="threshold", domain=style.T2M_DOMAIN, range=style.T2M_RANGE)),
        stroke=alt.Stroke("series:N", title=None, scale=series),
        tooltip=[alt.Tooltip("date:T", title="czas", format="%Y-%m-%d %H:%M"),
                 alt.Tooltip("series:N", title="seria"), alt.Tooltip("value:Q", format=".1f", title="°C")])
    # temperature labels above its dots, dew point below, so the two series don't collide
    text = [base.mark_text(dy=dy, fontSize=9, color=palette["ink2"]).encode(text=alt.Text("value:Q", format=".1f"))
            .transform_filter(alt.datum.series == s) for s, dy in (("temperatura", -10), ("punkt rosy", 11))]
    layers = [*_night_layer(palette, sun, axis, d, forecast), _frost(palette)]
    if not d.empty:
        layers.append(alt.Chart(_midnights(d, forecast)).mark_rule(color=palette["muted"], strokeWidth=1.5, strokeDash=[6, 4])
                      .encode(x=x))
        layers.append(alt.Chart(_midnights(d, forecast, include_start=True)).mark_text(
            baseline="bottom", dy=-4, fontSize=11, fontWeight="bold", color=palette["ink2"]).encode(
            x=x, y=alt.value(0), text=alt.Text("date:T", format="%d.%m")))
    layers += [line, dots, *text]
    if d.empty:
        return _cfg(alt.layer(*layers), palette, 260)

    last_obs = d["date"].max()
    fc_parts = []
    if past is not None and not past.empty:
        p = past[pd.to_datetime(past["date"]).between(d["date"].min(), last_obs)]
        fc_parts.append(p[["date", "tm"]].assign(run="sprzed 24 h"))
    have_ahead = forecast is not None and not forecast.empty
    if have_ahead:
        fc_parts.append(forecast[["date", "tm"]].assign(run="najnowsza"))
        # dew point forecast continues the observed dew point line
        dew = pd.concat([d[d["series"] == "punkt rosy"].tail(1),
                         _melt(forecast).query("series == 'punkt rosy'")], ignore_index=True)
        layers.append(alt.Chart(dew).mark_line(strokeWidth=1.5, strokeDash=[5, 3], opacity=0.9)
                      .encode(x=x, y="value:Q", color=color))
        layers.append(alt.Chart(dew.iloc[1:]).mark_point(size=40, filled=True, opacity=0.7).encode(
            x=x, y="value:Q", color=color,
            tooltip=[alt.Tooltip("date:T", title="prognoza, czas", format="%Y-%m-%d %H:%M"),
                     alt.Tooltip("value:Q", format=".1f", title="punkt rosy °C")]))
    if fc_parts:
        f = pd.concat(fc_parts, ignore_index=True).rename(columns={"tm": "value"}).assign(series=FC_T)
        f["date"] = pd.to_datetime(f["date"])
        fenc = dict(x=x, y="value:Q", color=color)
        layers.append(alt.Chart(f).mark_line(strokeWidth=2, strokeDash=[5, 3]).encode(**fenc))
        layers.append(alt.Chart(f).mark_point(size=40, filled=True, opacity=0.8).encode(
            **fenc, tooltip=[alt.Tooltip("date:T", title="czas", format="%Y-%m-%d %H:%M"),
                             alt.Tooltip("run:N", title="prognoza"),
                             alt.Tooltip("value:Q", format=".1f", title="T °C")]))
        layers.append(alt.Chart(f).mark_text(dy=-10, fontSize=9, color=palette["fc_label"]).encode(
            x=x, y="value:Q", text=alt.Text("value:Q", format=".1f")))
    if have_ahead:   # where the readings end and the latest forecast takes over
        layers.append(alt.Chart(pd.DataFrame({"date": [last_obs]})).mark_rule(
            color=palette["now_rule"], strokeWidth=1.5, strokeDash=[2, 2]).encode(x=x))
    layers += _hover_columns(palette, axis, d, f if fc_parts else None)
    return _cfg(alt.layer(*layers), palette, 260)


HOVER_FIELDS = [("temperatura", "temperatura"), ("prognoza T", "prognoza"), ("punkt rosy", "punkt rosy")]


def hover_table(obs: pd.DataFrame, fc_t: pd.DataFrame | None) -> pd.DataFrame:
    """One row per hour with every value shown on the plot, pre-formatted ("—" when absent)."""
    wide = obs.pivot_table(index="date", columns="series", values="value")
    if fc_t is not None and not fc_t.empty:
        wide = wide.join(fc_t.set_index("date")["value"].rename("prognoza T"), how="outer")
    out = pd.DataFrame({"date": wide.index})
    for col, _ in HOVER_FIELDS:
        v = wide[col] if col in wide else pd.Series(float("nan"), index=wide.index)
        out[col] = [("—" if pd.isna(x) else f"{x:.1f} °C") for x in v]
    return out


def _hover_columns(palette: dict, axis: alt.Axis, obs, fc_t) -> list[alt.Chart]:
    """Invisible one-hour columns: hovering anywhere over an hour shows all its values and a guide line."""
    h = hover_table(obs, fc_t)
    half = pd.Timedelta(minutes=30)     # clipped to the data, so the columns don't widen the x axis
    h["start"] = (h["date"] - half).clip(lower=h["date"].min())
    h["end"] = (h["date"] + half).clip(upper=h["date"].max())
    hover = alt.selection_point(fields=["date"], on="pointerover", clear="pointerout", empty=False)
    tip = [alt.Tooltip("date:T", title="czas", format="%d.%m %H:%M"),
           *[alt.Tooltip(f"{col}:N", title=title) for col, title in HOVER_FIELDS]]
    guide = alt.Chart(h).mark_rule(color=palette["muted"], strokeWidth=1).encode(
        x=alt.X("date:T", axis=axis, title=None),
        opacity=alt.condition(hover, alt.value(0.7), alt.value(0)))
    # a rect with only x/x2 fills the plot's height; Vega doesn't hover marks at opacity 0, so 0.001
    cols = alt.Chart(h).mark_rect(opacity=0.001).encode(
        x=alt.X("start:T", axis=axis, title=None), x2="end:T", tooltip=tip).add_params(hover)
    return [guide, cols]


def daily_extremes(tm: pd.DataFrame) -> pd.DataFrame:
    """Highest temperature of each day (06–18) and lowest of each night (18–06), in the data's time.

    Day and night windows, not calendar days, so a cold spell crossing midnight gives one
    minimum instead of two neighbouring ones. Column ``kind``: "Tmax dzień" / "Tmin noc".
    """
    h = tm["date"].dt.hour
    day, night = tm[h.between(6, 18)], tm[(h >= 18) | (h <= 6)]
    hi = day.loc[day.groupby(day["date"].dt.date)["value"].idxmax()].assign(kind="Tmax dzień")
    # a night belongs to the morning it ends in
    lo = night.loc[night.groupby((night["date"] + pd.Timedelta(hours=6)).dt.date)["value"].idxmin()]
    return pd.concat([hi, lo.assign(kind="Tmin noc")], ignore_index=True)


def nights(sun: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Sunset-to-sunrise spans clipped to ``start..end``: columns ``start``, ``end``."""
    sun = sun.sort_values("sunrise")
    # night before the first sunrise, every sunset to the next sunrise, and after the last sunset
    starts = [start, *sun["sunset"]]
    ends = [*sun["sunrise"], end]
    n = pd.DataFrame({"start": starts, "end": ends})
    n["start"], n["end"] = n["start"].clip(lower=start, upper=end), n["end"].clip(lower=start, upper=end)
    return n[n["end"] > n["start"]].reset_index(drop=True)


def _night_layer(palette: dict, sun: pd.DataFrame | None, axis: alt.Axis, *frames: pd.DataFrame) -> list[alt.Chart]:
    """Grey night rects over the frames' time span (empty list without sun times)."""
    frames = [f for f in frames if f is not None and not f.empty]
    if sun is None or sun.empty or not frames:
        return []
    dates = pd.concat([pd.to_datetime(f["date"]) for f in frames])
    n = nights(sun, dates.min(), dates.max())
    # a rect with only x/x2 fills the panel's whole height
    return [alt.Chart(n).mark_rect(color=palette["night"]).encode(x=alt.X("start:T", title=None, axis=axis), x2="end:T")]


def forecast_chart(df: pd.DataFrame, theme: str, sun: pd.DataFrame | None = None) -> alt.Chart:
    """Whole hourly forecast: temperature and dew point above one panel of hourly precipitation
    (left axis) and wind speed and gusts (right axis) over the cloud cover; ``sun`` greys out the nights."""
    palette = THEMES[theme]
    d = _melt(df)
    series = alt.Scale(domain=list(SERIES.values()), range=[palette["s1"], palette["s2"]])
    # one tick, label and grid line per day, at its midnight
    axis = alt.Axis(format="%d.%m", labelAngle=0, labelOverlap=False, values=_ticks("D", d))
    x = alt.X("date:T", title=None, axis=axis)
    base = alt.Chart(d).encode(x=x, y=alt.Y("value:Q", title="°C", scale=alt.Scale(zero=False)))
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", empty=False)
    lines = base.mark_line(strokeWidth=2).encode(color=alt.Color("series:N", title=None, scale=series))
    pts = base.mark_point(size=60, filled=True).encode(
        color=alt.Color("series:N", title=None, scale=series),
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("date:T", title="czas", format="%Y-%m-%d %H:%M"),
                 alt.Tooltip("series:N", title="seria"), alt.Tooltip("value:Q", format=".1f", title="°C")]
    ).add_params(hover)
    rule = base.mark_rule(color=palette["muted"]).encode(
        opacity=alt.condition(hover, alt.value(0.6), alt.value(0))).transform_filter(hover)
    ext = daily_extremes(d[d["series"] == "temperatura"])
    etip = [alt.Tooltip("date:T", title="czas", format="%Y-%m-%d %H:%M"),
            alt.Tooltip("kind:N", title=""), alt.Tooltip("value:Q", format=".1f", title="°C")]
    edots = alt.Chart(ext).mark_point(size=45, filled=True, opacity=1, color=palette["s1"]).encode(
        x=x, y="value:Q", tooltip=etip)
    elabels = [alt.Chart(ext[ext["kind"] == k]).mark_text(dy=dy, fontSize=10, color=palette["ink2"]).encode(
        x=x, y="value:Q", text=alt.Text("value:Q", format=".1f")) for k, dy in (("Tmax dzień", -10), ("Tmin noc", 12))]
    shade = _night_layer(palette, sun, axis, d)
    top = alt.layer(*shade, _frost(palette, "fc_temp_y", "fc_temp_height"), lines, edots, *elabels, rule, pts).properties(name="fc_temp", height=220, width="container")

    h = df[["date", "prcp", "cloud_cover", "wind_speed", "wind_gust"]].copy()
    h["date"] = pd.to_datetime(h["date"])
    h["start"] = h["date"] - pd.Timedelta(hours=1)    # Open-Meteo sums the preceding hour
    # the precipitation bars and the hourly wind points each carry the whole hour
    tip = [alt.Tooltip("date:T", title="czas", format="%Y-%m-%d %H:%M"),
           alt.Tooltip("prcp:Q", title="opad w godzinie do [mm]", format=".1f"),
           alt.Tooltip("cloud_cover:Q", title="zachmurzenie [%]", format=".0f"),
           alt.Tooltip("wind_speed:Q", title="prędkość wiatru [m/s]", format=".1f"),
           alt.Tooltip("wind_gust:Q", title="porywy [m/s]", format=".1f")]
    # cloud cover is instantaneous, so each hour's step is centred on the hour itself
    clouds = alt.Chart(h).mark_area(color=palette["muted"], opacity=0.3, interpolate="step").encode(
        x=x, y=alt.Y("cloud_cover:Q", axis=None, scale=alt.Scale(domain=[0, 100])))
    bars = alt.Chart(h[h["prcp"] > 0]).mark_bar(color=palette["s1"]).encode(
        x=alt.X("start:T", title=None, axis=axis), x2="date:T",
        y=alt.Y("prcp:Q", title="opad [mm/h]"), y2=alt.datum(0), tooltip=tip)
    # invisible points give every hour of both lines its own tooltip
    wind_base = alt.Chart(h).encode(x=x, tooltip=tip)
    hour_points = alt.OverlayMarkDef(size=40, opacity=0)
    wind = alt.layer(
        wind_base.mark_line(strokeWidth=1.5, strokeDash=[4, 3], color=palette["ink2"], point=hour_points).encode(
            y=alt.Y("wind_gust:Q", title="wiatr [m/s]", axis=alt.Axis(orient="right", grid=False))),
        wind_base.mark_line(strokeWidth=2, color=palette["ink2"], point=hour_points).encode(y="wind_speed:Q"))
    # cloud cover fills the panel behind; precipitation and wind each get their own side's axis
    weather = (alt.layer(*shade, clouds, bars, wind).resolve_scale(y="independent")
               .properties(height=150, width="container"))
    return _style(alt.vconcat(top, weather).resolve_scale(x="shared"), palette)


def climograph(year_vals: pd.DataFrame, normals: pd.DataFrame, theme: str, unit: str,
               label: str, bars: bool = False) -> alt.Chart:
    """One variable for one year vs the normal (mean ± sd band)."""
    palette = THEMES[theme]
    n = normals.assign(lo=normals["mean"] - normals["sd"], hi=normals["mean"] + normals["sd"],
                       m=normals["month"].map(lambda m: MONTH_ABBR[m - 1]))
    y = year_vals.assign(m=year_vals["month"].map(lambda m: MONTH_ABBR[m - 1]))
    x = alt.X("m:N", sort=MONTH_ABBR, title=None, axis=alt.Axis(labelAngle=0))
    ntip = [alt.Tooltip("m:N", title="miesiąc"), alt.Tooltip("mean:Q", title="norma", format=".1f"),
            alt.Tooltip("sd:Q", title="odch. std.", format=".1f")]
    band = alt.Chart(n).mark_area(color=palette["band"], opacity=0.8).encode(
        x=x, y=alt.Y("lo:Q", title=unit, scale=alt.Scale(zero=bars)), y2="hi:Q", tooltip=ntip)
    ytip = [alt.Tooltip("m:N", title="miesiąc"), alt.Tooltip("value:Q", title=label, format=".1f"),
            alt.Tooltip("is_partial:N", title="niepełny")]
    if bars:
        layers = [alt.Chart(y).mark_bar(color=palette["s1"], opacity=0.85, size=18,
                                        cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
                      x=x, y=alt.Y("value:Q", title=unit), tooltip=ytip),
                  alt.Chart(n).mark_tick(color=palette["ink"], thickness=2, size=24).encode(
                      x=x, y="mean:Q", tooltip=ntip)]
    else:
        layers = [band,
                  alt.Chart(n).mark_line(color=palette["muted"], strokeWidth=1.5, strokeDash=[4, 3]).encode(
                      x=x, y="mean:Q", tooltip=ntip),
                  alt.Chart(y).mark_line(color=palette["s1"], strokeWidth=2,
                                         point=alt.OverlayMarkDef(size=70, filled=True)).encode(
                      x=x, y="value:Q", tooltip=ytip)]
    return _cfg(alt.layer(*layers), palette, 240)


def stripes(df: pd.DataFrame, theme: str) -> alt.Chart:
    """Warming stripes: annual anomaly vs the normal, diverging around 0."""
    palette = THEMES[theme]
    lim = max(abs(df["anomaly"].min()), abs(df["anomaly"].max()), 0.5)
    tip = [alt.Tooltip("year:O", title="rok"), alt.Tooltip("value:Q", title="Tśr", format=".1f"),
           alt.Tooltip("anomaly:Q", title="anomalia", format="+.1f")]
    color = alt.Color("anomaly:Q", title="anomalia [°C]",
                      scale=alt.Scale(domain=[-lim, 0, lim], range=palette["div"], interpolate="lab"))
    strip = alt.Chart(df).mark_rect().encode(
        x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0, values=[y for y in df["year"] if y % 5 == 0])),
        color=color, tooltip=tip).properties(height=90, width="container")
    bars = alt.Chart(df).mark_bar(cornerRadius=2).encode(
        x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0, values=[y for y in df["year"] if y % 5 == 0])),
        y=alt.Y("anomaly:Q", title="anomalia [°C]"), color=alt.Color("anomaly:Q", scale=alt.Scale(
            domain=[-lim, 0, lim], range=palette["div"], interpolate="lab"), legend=None), tooltip=tip
    ).properties(height=160, width="container")
    ext = df.loc[[df["anomaly"].idxmax(), df["anomaly"].idxmin()]]
    extreme_labels = alt.Chart(ext).mark_text(dy=-8, color=palette["ink2"], fontSize=11).encode(
        x="year:O", y="anomaly:Q", text=alt.Text("anomaly:Q", format="+.1f"))
    return _style(alt.vconcat(strip, alt.layer(bars, extreme_labels)), palette)


def cumulative(cum: pd.DataFrame, year: int, normal_period: tuple[int, int], theme: str) -> alt.Chart:
    """Selected year's running precipitation vs the normal period's mean curve; driest/wettest as grey context."""
    palette = THEMES[theme]
    totals = cum.groupby("year")["cum"].max()
    full = totals[totals.index < pd.Timestamp.today().year]
    y0, y1 = normal_period
    mean_label = f"średnia {y0}–{y1}"
    normal = (cum[cum["year"].between(y0, y1)].groupby("doy")["cum"].mean().reset_index()
              .assign(series=mean_label))
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
        color=alt.Color("series:N", legend=None, scale=alt.Scale(range=[palette["muted"], palette["context"], palette["context"]])),
        strokeDash=alt.condition(alt.datum.series == mean_label, alt.value([4, 3]), alt.value([1, 0])),
        tooltip=tip)
    end = ctx.groupby("series").tail(1)
    glabels = alt.Chart(end).mark_text(align="left", dx=4, color=palette["muted"], fontSize=11).encode(
        x=x, y="cum:Q", text="series:N")
    main = alt.Chart(sel).mark_line(strokeWidth=2.5, color=palette["s1"]).encode(x=x, y="cum:Q", tooltip=tip)
    mlabel = alt.Chart(sel.tail(1)).mark_text(align="left", dx=4, color=palette["ink"], fontWeight="bold").encode(
        x=x, y="cum:Q", text="series:N")
    return _cfg(alt.layer(grey, glabels, main, mlabel), palette, 300)
