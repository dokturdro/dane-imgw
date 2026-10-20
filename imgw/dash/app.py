"""Personal IMGW dashboard. Run with `uv run imgw dash`."""

from __future__ import annotations

import html
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from imgw import config, db, download, live, synop_feed
from imgw.dash import charts, labels, queries as q, style

st.set_page_config(page_title="Dane IMGW", page_icon="🌦️", layout="wide")
CFG = config.load(Path(os.environ["IMGW_CONFIG"]) if os.environ.get("IMGW_CONFIG") else None)
DEFAULT_STATION = "350170530"   # Opole (synop)
TODAY = date.today()


# ------------------------------------------------------------- data access ---

@st.cache_data(ttl=600, show_spinner=False)
def _cached(name: str, *args, db_mtime: float = 0.0):
    # db_mtime only keys the cache: a write by sync/live/synop (e.g. the launcher's refresh) invalidates it
    with q.open_ro(CFG.db_path) as con:
        return getattr(q, name)(con, *args)


def _db_mtime() -> float:
    try:
        return CFG.db_path.stat().st_mtime
    except OSError:
        return 0.0


@st.cache_resource
def _last_good() -> dict:
    return {}


def load(name: str, *args):
    """Cached query; while a sync holds the database, fall back to the last result."""
    key = (name, args)
    try:
        val = _cached(name, *args, db_mtime=_db_mtime())
        _last_good()[key] = (val, datetime.now())
        return val
    except db.DatabaseLocked:
        if key in _last_good():
            val, when = _last_good()[key]
            st.session_state["busy_since"] = when
            return val
        st.warning("Baza jest zajęta (trwa synchronizacja). Spróbuj za chwilę.")
        st.stop()


def refresh_sources() -> str:
    """Fetch new SYNOP messages and one telemetry poll; return a one-line summary."""
    parts = []
    with download.client() as c:
        try:
            r = synop_feed.update(CFG, c)
            parts.append("SYNOP: baza zajęta, zapisano do kolejki" if "spooled_to" in r else
                         f"SYNOP do {r['latest']:%H:%M} UTC" if r.get("latest") else "SYNOP: brak nowych")
        except Exception as e:   # network trouble must not break the page
            parts.append(f"SYNOP: błąd ({type(e).__name__})")
        try:
            r = live.update(CFG, c)
            parts.append("telemetria: w kolejce" if "spooled_to" in r else f"telemetria: +{r['new_rows']} odczytów")
        except Exception as e:
            parts.append(f"telemetria: błąd ({type(e).__name__})")
    return " · ".join(parts)


def theme() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:
        return "light"


def fmt(v, digits=1, unit=""):
    return "—" if v is None or pd.isna(v) else f"{v:.{digits}f}{unit}"


# ----------------------------------------------------------------- top bar ---

# use the full window width (Streamlit's wide layout still keeps generous side padding)
st.html("<style>.block-container{padding:1.2rem 1.5rem 2rem;max-width:100%}</style>")

stations = load("stations")
with st.container(border=True):
    c_brand, c_station, c_opad, c_btn = st.columns([1.2, 4, 1.6, 1], vertical_alignment="bottom")
    c_brand.markdown("### Dane IMGW")
    show_opad = c_opad.toggle("Posterunki opadowe", value=False,
                              help="Posterunki 'o' mierzą tylko opad i śnieg.")
    pool = stations if show_opad else stations[stations["type"] != "o"]
    ids = pool["imgw_id"].tolist()
    wanted = st.query_params.get("station", DEFAULT_STATION)
    if wanted not in ids:
        ids = [wanted] + ids if wanted in stations["imgw_id"].values else ids
    label_of = dict(zip(stations["imgw_id"], stations["label"]))
    sid = c_station.selectbox("Stacja", ids, index=ids.index(wanted) if wanted in ids else 0,
                              format_func=lambda i: label_of.get(i, i), label_visibility="collapsed")
    st.query_params["station"] = sid
    if c_btn.button("Odśwież dane", width="stretch",
                    help="Pobiera najnowsze raporty SYNOP i odczyt telemetrii, potem odświeża widok."):
        with st.spinner("Pobieram najnowsze raporty…"):
            st.session_state["refresh_msg"] = refresh_sources()
        st.cache_data.clear()
        st.rerun()
    meta = stations.set_index("imgw_id").loc[sid]
    fresh = load("freshness", sid)
    info = [f"archiwum → **{fresh['archive'] or '—'}**",
            f"godzinowe → {fresh['hourly'].strftime('%Y-%m-%d %H:%M') + ' UTC' if fresh['hourly'] else '—'}",
            f"SYNOP → {fresh['synop'].strftime('%d.%m %H:%M') + ' UTC' if fresh['synop'] else '—'}",
            f"telemetria → {fresh['live'].strftime('%d.%m %H:%M') + ' UTC' if fresh['live'] else '—'}"]
    if pd.notna(meta["lat"]):
        info.append(f"{meta['lat']:.3f}° N, {meta['lon']:.3f}° E · {meta['elevation']:.0f} m n.p.m.")
    st.caption(" &nbsp;·&nbsp; ".join(info))

if "refresh_msg" in st.session_state:
    st.toast(st.session_state.pop("refresh_msg"))
if "busy_since" in st.session_state:
    st.info(f"Baza zajęta (synchronizacja) — pokazuję dane z {st.session_state.pop('busy_since'):%H:%M}.")

st.title(meta["name"])
tab_now, tab_month, tab_clim = st.tabs(["Teraz i dobowe", "Miesięczne", "Klimat"])
TH = theme()


# ------------------------------------------------------------- tab: daily ---

DAILY_GROUPS = {
    "Temperatura": ["tm", "tx", "tn", "tng", "tm2"],
    "Opad i śnieg": ["prcp", "prcp_kind", "snow_depth", "fresh_snow", "snow_water"],
    "Wiatr i ciśnienie": ["wind_speed", "ff10_time", "ff15_time", "mslp", "ppp", "rh", "vapp", "cloud_cover"],
    "Słońce i zjawiska": ["sunshine", "ra_time", "sn_time", "rasn_time", "fo_time", "dew_time",
                          "frost_time", "ts_time", "glaze_time", "rime_time"],
}
HOURLY_COLS = ["tm", "td", "rh", "wind_speed", "wind_dir", "wind_gust", "mslp", "ppp", "cloud_cover",
               "low_cloud_cover", "cl", "cm", "ch", "prcp", "visib", "sunshine", "ww", "w1"]


SHORT = {"tm": "Tśr", "tx": "Tmax", "tn": "Tmin", "tng": "Tmin grunt", "tm2": "(Tx+Tn)/2", "td": "Td",
         "wb": "Tw", "prcp": "opad", "prcp_kind": "rodzaj", "snow_depth": "śnieg cm",
         "fresh_snow": "świeży cm", "snow_water": "równoważnik", "wind_speed": "wiatr m/s",
         "wind_dir": "kier.", "wind_gust": "poryw", "ff10_time": "≥10 m/s h", "ff15_time": "≥15 m/s h",
         "mslp": "p morze", "ppp": "p stacja", "rh": "RH %", "vapp": "e hPa", "cloud_cover": "zachm.",
         "low_cloud_cover": "zachm. niskie", "cl": "CL", "cm": "CM", "ch": "CH", "visib": "widz. km",
         "sunshine": "słońce h", "ra_time": "deszcz h", "sn_time": "śnieg h", "rasn_time": "deszcz+śn. h",
         "fo_time": "mgła h", "dew_time": "rosa h", "frost_time": "szron h", "ts_time": "burza h",
         "glaze_time": "gołoledź h", "rime_time": "sadź h", "ww": "ww", "w1": "W1"}


def column_config(cols, names):
    """Short headers; the full Polish name and the code go in the header tooltip."""
    return {c: st.column_config.Column(SHORT.get(c, c), help=f"{names.get(c, c)} ({c})") for c in cols}


COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def compass(deg) -> str:
    return "" if deg is None or pd.isna(deg) else ("cisza" if deg == 0 else COMPASS[int((deg + 22.5) // 45) % 8])


with tab_now:
    now = load("latest_synop", sid)
    recent = load("daily", sid, TODAY - timedelta(days=4), TODAY)
    done = recent[recent["tx"].notna()] if not recent.empty else recent
    last_day = None if done.empty else done.iloc[-1]
    mtd = load("month_to_date", sid, TODAY)
    have_mtd = mtd["tm"] is not None or mtd["prcp"] is not None
    live = load("live_days", sid, 2) if now is None else pd.DataFrame()
    have_live = not live.empty and live.iloc[0][["tm", "tx", "tn", "prcp"]].notna().any()

    if now is None and not (have_live or have_mtd):
        st.caption("Brak danych wstępnych — archiwum IMGW kończy się "
                   f"{fresh['archive'] or '—'}. Stacje synoptyczne: uruchom `imgw synop`; "
                   "pozostałe: `imgw live` co 10 min.")
    tiles = iter(st.columns(8))
    if now is not None:
        when = f"{pd.Timestamp(now['date']):%d.%m %H:%M} UTC"
        next(tiles).metric(f"Teraz · {when}", fmt(now["tm"], unit=" °C"),
                           help=f"SYNOP (wstępne). Punkt rosy {fmt(now['td'], unit=' °C')}, "
                                f"wilgotność {fmt(now['rh'], 0, ' %')}")
        gust = "" if pd.isna(now.get("wind_gust")) else f", poryw {now['wind_gust']:.0f}"
        next(tiles).metric("Wiatr", fmt(now["wind_speed"], 0, " m/s"),
                           delta=f"{compass(now['wind_dir'])}{gust}" if not pd.isna(now["wind_speed"]) else None,
                           delta_color="off", delta_arrow="off")
        next(tiles).metric("Ciśnienie (morze)", fmt(now["mslp"], 1, " hPa"),
                           delta=None if pd.isna(now.get("p_tendency")) else f"zmiana {now['p_tendency']:.1f} hPa / 3 h",
                           delta_color="off", delta_arrow="off")
        ww = labels.WW_NAMES.get(int(now["ww"]), "") if pd.notna(now["ww"]) else ""
        next(tiles).metric("Zachmurzenie", fmt(now["cloud_cover"], 0, "/8"), help=ww or None,
                           delta=(ww[:28] + "…" if len(ww) > 28 else ww) or None, delta_color="off",
                           delta_arrow="off")
    elif have_live:
        row = live.iloc[0]
        next(tiles).metric(f"Tśr {row['date']:%d.%m} (telemetria)", fmt(row["tm"], unit=" °C"),
                           help=f"średnia z terminów synoptycznych, {row['n_terms']}/8 terminów")
        next(tiles).metric("Tmax 18–18 UTC", fmt(row["tx"], unit=" °C"), help=f"{row['n_t']} odczytów 10-min (min. 120)")
        next(tiles).metric("Tmin 18–18 UTC", fmt(row["tn"], unit=" °C"), help=f"{row['n_t']} odczytów 10-min (min. 120)")
        next(tiles).metric("Opad 06–06 UTC", fmt(row["prcp"], unit=" mm"), help=f"{row['n_p']} odczytów 10-min (min. 138)")
    if last_day is not None:
        tag = " Dane wstępne (SYNOP)." if last_day["provisional"] else ""
        next(tiles).metric(f"Tmax / Tmin {last_day['date']:%d.%m} °C",
                           f"{fmt(last_day['tx'])} / {fmt(last_day['tn'])}",
                           help="Doba klimatologiczna 18–18 UTC." + tag)
        next(tiles).metric(f"Opad {last_day['date']:%d.%m}", fmt(last_day["prcp"], unit=" mm"),
                           help="06 UTC tego dnia – 06 UTC następnego." + tag)
    if have_mtd:
        next(tiles).metric(f"Tśr {TODAY:%m.%Y} do dziś", fmt(mtd["tm"], unit=" °C"),
                           delta=None if mtd["tm_anom"] is None else f"{mtd['tm_anom']:+.1f} °C vs norma",
                           delta_color="off", help=f"{mtd['n_tm']} dni z danymi; norma 1991–2020")
        next(tiles).metric("Opad w miesiącu", fmt(mtd["prcp"], unit=" mm"),
                           delta=None if mtd["prcp_pct"] is None else f"{mtd['prcp_pct']:.0f}% normy",
                           delta_color="off", delta_arrow="off",
                           help=f"{mtd['n_prcp']} dni z danymi; norma pro rata")

    # --- hourly (latest day first) ---
    hcol, _ = st.columns([1, 3])
    stamps = [t for t in (fresh["synop"], fresh["hourly"]) if t]
    hour_end = max(stamps).date() if stamps else TODAY
    day = hcol.date_input("Dane godzinowe — dzień", hour_end, max_value=hour_end, format="YYYY-MM-DD")
    h = load("hourly", sid, day - timedelta(days=1), day)
    if h.empty:
        st.caption("Brak danych godzinowych (tylko stacje synoptyczne).")
    else:
        hv = h[["date", *[c for c in HOURLY_COLS if c in h]]].copy()
        if h["provisional"].any():
            hv.insert(1, "◦", h["provisional"].map({True: "wstępne", False: ""}))
        hv["pogoda"] = hv["ww"].map(lambda v: labels.WW_NAMES.get(int(v), "") if pd.notna(v) else "")
        hv = hv.sort_values("date", ascending=False)
        st.dataframe(style.style_frame(hv, style.HOURLY_SCALES, whole=style.HOURLY_WHOLE), hide_index=True,
                     width="stretch", placeholder="", height=420,
                     column_config={"date": st.column_config.DatetimeColumn("czas UTC", format="DD.MM HH:mm"),
                                    "◦": st.column_config.Column(" ", width="small"),
                                    "pogoda": st.column_config.Column("pogoda bieżąca", width="large"),
                                    **column_config(HOURLY_COLS, labels.HOURLY_VARS)})
        st.altair_chart(charts.hourly_temperature(h, TH), width="stretch", theme=None)

    # --- daily ---
    st.divider()
    c1, c2 = st.columns([2, 3])
    rng = c1.date_input("Zakres", (TODAY - timedelta(days=60), TODAY), max_value=TODAY, format="YYYY-MM-DD")
    groups = c2.pills("Kolumny", list(DAILY_GROUPS), selection_mode="multi",
                      default=list(DAILY_GROUPS))
    if isinstance(rng, tuple) and len(rng) == 2:
        start, end = rng
        if (end - start).days > 366:
            start = end - timedelta(days=366)
            st.caption("Zakres przycięty do 366 dni.")
        d = load("daily", sid, start, end)
        if d.empty:
            st.info("Brak danych w tym zakresie.")
        else:
            cols = [c for g in (groups or ["Temperatura"]) for c in DAILY_GROUPS[g] if c in d and d[c].notna().any()]
            if "Słońce i zjawiska" not in (groups or []) and "sunshine" in d and d["sunshine"].notna().any():
                cols.append("sunshine")
            view = d[["date", *cols]].copy()
            if d["provisional"].any():
                view.insert(1, "◦", d["provisional"].map({True: "wstępne", False: ""}))
            view = view.sort_values("date", ascending=False)
            st.dataframe(style.style_frame(view, style.DAILY_SCALES), hide_index=True, width="stretch", placeholder="",
                         height=min(36 * (len(view) + 1) + 3, 520),
                         column_config={"date": st.column_config.DateColumn("data", format="YYYY-MM-DD"),
                                        "◦": st.column_config.Column(" ", width="small"),
                                        **column_config(cols, labels.DAILY_VARS)})

            norm = load("monthly_normals", sid, "tm")
            nd = None
            if not norm.empty:
                days = pd.date_range(start, end, freq="D")
                nd = pd.DataFrame({"date": days, "normal": days.month.map(norm.set_index("month")["mean"])})
            g1, g2 = st.columns(2)
            with g1:
                st.caption("Temperatura: zakres Tmin–Tmax, Tśr, norma 1991–2020 (przerywana)")
                st.altair_chart(charts.daily_temperature(d, nd, TH), width="stretch", theme=None)
            with g2:
                st.caption("Opad dobowy i suma narastająca")
                st.altair_chart(charts.daily_precip(d, TH), width="stretch", theme=None)


# ----------------------------------------------------------- tab: monthly ---

COL_NAMES = {**{str(i + 1): m for i, m in enumerate(charts.MONTH_ABBR)}, "DJF": "DJF", "MAM": "MAM",
             "JJA": "JJA", "SON": "SON", "year": "Rok"}


def grid_html(g: dict, variable: str) -> str:
    val, cls, part = g["value"], g["class"], g["partial"]
    hi, lo, dp, dm, an = (g["is_record_high"], g["is_record_low"], g["days_present"],
                          g["days_missing"], g["anomaly"])
    digits = 0 if variable in style.INT_VARS else 1

    def cell(y, c):
        v = val.at[y, c]
        if pd.isna(v):
            return ""
        mark = " ▲" if hi.at[y, c] is True else " ▼" if lo.at[y, c] is True else ""
        return f"{style.fmt_num(v, digits)}{mark}"

    shown = pd.DataFrame({c: [cell(y, c) for y in val.index] for c in val.columns}, index=val.index)

    def css(y, c):
        if pd.isna(val.at[y, c]):
            return ""
        if part.at[y, c] is True:
            return style.PARTIAL
        s = style.class_css(cls.at[y, c])
        return s + ("; font-weight: 700" if (hi.at[y, c] is True or lo.at[y, c] is True) else "")

    def tip(y, c):
        if pd.isna(val.at[y, c]):
            return ""
        k = cls.at[y, c]
        parts = [f"{COL_NAMES[c]} {y}: {val.at[y, c]:.{digits}f}",
                 "niepełny (za dużo braków)" if part.at[y, c] is True else
                 f"klasa {int(k)}: {labels.CLASS_NAMES[int(k)]}" if pd.notna(k) else "",
                 "rekord: najwyższa" if hi.at[y, c] is True else "rekord: najniższa" if lo.at[y, c] is True else "",
                 f"anomalia vs 1991–2020: {an.at[y, c]:+.1f}" if pd.notna(an.at[y, c]) else "",
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
    digits = 0 if variable in style.INT_VARS else 1
    m = means.copy()
    m.columns = [COL_NAMES[c] for c in m.columns]
    sty = m.style.format(lambda v: style.fmt_num(v, digits)).set_table_styles([
        {"selector": "", "props": "border-spacing: 2px; font-size: 13px; font-variant-numeric: tabular-nums;"},
        {"selector": "td", "props": "padding: 3px 6px; text-align: right; min-width: 44px;"},
        {"selector": "th", "props": "padding: 3px 6px; text-align: right; font-weight: 600;"}])
    return f'<div style="overflow-x:auto">{sty.to_html()}</div>'


def legend_html() -> str:
    sw = "".join(
        f'<span title="{html.escape(labels.CLASS_NAMES[k])}" style="display:inline-block;padding:2px 7px;'
        f'margin:1px;border-radius:3px;font-size:12px;background:{bg};color:{fg}">{k}</span>'
        for k, (bg, fg) in style.CLASS_COLORS.items())
    return (f'<div style="font-size:12px">{sw} &nbsp; 1 = ekstremalnie wysoka … 6 = normalna … '
            f'11 = ekstremalnie niska (percentyle całego okresu stacji) · ▲▼ rekord · '
            f'<i style="color:#898781">kursywa</i> = niepełny</div>')


with tab_month:
    c1, c2, _ = st.columns([3, 1, 2])
    var_keys = list(labels.MONTHLY_VARS)
    variable = c1.selectbox("Zmienna", var_keys, index=0,
                            format_func=lambda k: f"{labels.MONTHLY_VARS[k]} ({k})")
    max_missing = c2.number_input("Maks. braków (dni)", 0, 31, 3)
    if variable in labels.DESCRIPTIONS:
        st.caption(labels.DESCRIPTIONS[variable])
    g = load("monthly_grid", sid, variable, int(max_missing))
    if "value" not in g:
        st.info("Brak danych miesięcznych dla tej stacji.")
    else:
        st.html(legend_html())
        st.html(grid_html(g, variable))
        if not g["means"].empty:
            st.caption("Średnie wieloletnie (tylko pełne miesiące)")
            st.html(means_html(g["means"], variable))


# ----------------------------------------------------------- tab: climate ---

with tab_clim:
    anomalies = load("annual_anomalies", sid, "tm")
    years = sorted(set(anomalies["year"]) | {TODAY.year}, reverse=True)
    year = st.selectbox("Rok", years, index=0)

    c1, c2 = st.columns(2)
    yv = load("monthly_year", sid, int(year), ("tm", "prcp"))
    with c1:
        st.markdown(f"**Temperatura średnia {year} vs norma 1991–2020** (pas = ±1 odch. std.)")
        n_tm = load("monthly_normals", sid, "tm")
        if n_tm.empty:
            st.caption("Brak normy temperatury dla tej stacji.")
        else:
            st.altair_chart(charts.climograph(yv[yv["variable"] == "tm"], n_tm, TH, "°C", "Tśr"),
                            width="stretch", theme=None)
    with c2:
        st.markdown(f"**Opad miesięczny {year} vs norma 1991–2020** (kreska = średnia)")
        n_pr = load("monthly_normals", sid, "prcp")
        if n_pr.empty:
            st.caption("Brak normy opadu dla tej stacji.")
        else:
            st.altair_chart(charts.climograph(yv[yv["variable"] == "prcp"], n_pr, TH, "mm", "opad", bars=True),
                            width="stretch", theme=None)

    st.markdown("**Paski ocieplenia** — roczna anomalia Tśr względem 1991–2020")
    if len(anomalies) >= 5 and anomalies["anomaly"].notna().any():
        st.altair_chart(charts.stripes(anomalies.dropna(subset=["anomaly"]), TH), width="stretch", theme=None)
    else:
        st.caption("Za mało pełnych lat.")

    st.markdown(f"**Narastająca suma opadu {year}** na tle średniej oraz najsuchszego i najwilgotniejszego roku")
    cum = load("cumulative_prcp", sid)
    if cum.empty or int(year) not in set(cum["year"]):
        st.caption("Brak kompletnego roku opadowego.")
    else:
        st.altair_chart(charts.cumulative(cum, int(year), TH), width="stretch", theme=None)
