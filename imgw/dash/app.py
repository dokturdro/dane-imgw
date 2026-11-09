"""Personal IMGW dashboard. Run with `uv run imgw dash`."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
import streamlit as st

from imgw import config, db, download, forecast, live, sun, synop_feed
from imgw.dash import charts, labels, queries, style

st.set_page_config(page_title="Dane IMGW", page_icon="🌦️", layout="wide")
CFG = config.load(Path(os.environ["IMGW_CONFIG"]) if os.environ.get("IMGW_CONFIG") else None)
DEFAULT_STATION = "350170530"   # Opole (synop)
TODAY = date.today()
NORMAL_LABEL = "{}–{}".format(*CFG.normal_period)


# ------------------------------------------------------------- data access ---

@st.cache_data(ttl=600, show_spinner=False)
def _cached(name: str, *args: object, db_mtime: float = 0.0):
    # db_mtime only keys the cache: a write by sync/live/synop (e.g. the launcher's refresh) invalidates it
    with queries.open_ro(CFG.db_path) as con:
        return getattr(queries, name)(con, *args)


def _db_mtime() -> float:
    try:
        return CFG.db_path.stat().st_mtime
    except OSError:
        return 0.0


@st.cache_resource
def _last_good() -> dict:
    return {}


def load(name: str, *args: object):
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


@st.cache_data(ttl=3600, show_spinner=False)
def _forecast(lat: float, lon: float, elevation: float | None) -> pd.DataFrame:
    with download.client() as c:
        return forecast.fetch(c, lat, lon, elevation)


@st.cache_data(ttl=3600, show_spinner=False)
def _day_ahead(lat: float, lon: float, elevation: float | None, start: date, end: date) -> pd.DataFrame:
    with download.client() as c:
        return forecast.day_ahead(c, lat, lon, elevation, start, end)


def load_forecast(meta, fn=_forecast, *args) -> pd.DataFrame | None:
    """Open-Meteo data for the station: None without coordinates, empty when the request fails."""
    if pd.isna(meta["lat"]) or pd.isna(meta["lon"]):
        return None
    try:   # raised outside the cached call, so a failure is retried on the next run
        return fn(float(meta["lat"]), float(meta["lon"]),
                  None if pd.isna(meta["elevation"]) else float(meta["elevation"]), *args)
    except httpx.HTTPError:
        return pd.DataFrame()


def refresh_sources() -> str:
    """Fetch new SYNOP messages and one telemetry poll; return a one-line summary."""
    parts = []
    with download.client() as c:
        try:
            r = synop_feed.update(CFG, c)
            parts.append("SYNOP: baza zajęta, zapisano do kolejki" if "spooled_to" in r else
                         f"SYNOP do {r['latest']:%H:%M} UTC" if r.get("latest") else "SYNOP: brak nowych")
        except (httpx.HTTPError, RuntimeError) as e:   # network trouble must not break the page
            parts.append(f"SYNOP: błąd ({type(e).__name__})")
        try:
            r = live.update(CFG, c)
            parts.append("telemetria: w kolejce" if "spooled_to" in r else f"telemetria: +{r['new_rows']} odczytów")
        except httpx.HTTPError as e:
            parts.append(f"telemetria: błąd ({type(e).__name__})")
    return " · ".join(parts)


def theme() -> str:
    return "dark" if st.context.theme.type == "dark" else "light"


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
    station_id = c_station.selectbox("Stacja", ids, index=ids.index(wanted) if wanted in ids else 0,
                                     format_func=lambda i: label_of.get(i, i), label_visibility="collapsed")
    st.query_params["station"] = station_id
    if c_btn.button("Odśwież dane", width="stretch",
                    help="Pobiera najnowsze raporty SYNOP i odczyt telemetrii, potem odświeża widok."):
        with st.spinner("Pobieram najnowsze raporty…"):
            st.session_state["refresh_msg"] = refresh_sources()
        st.cache_data.clear()
        st.rerun()
    meta = stations.set_index("imgw_id").loc[station_id]
    fresh = load("freshness", station_id)
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
THEME = theme()


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


# additive daily values: the month summary also shows their sum
SUMMABLE = {"prcp", "fresh_snow", "sunshine", *[c for g in DAILY_GROUPS.values() for c in g if c.endswith("_time")]}


def month_summary(d: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Min / max / mean (and sum for additive columns), laid out with the daily table's columns.

    The row label goes in ``date``; columns that have no such statistic stay blank.
    """
    data = [c for c in columns if c not in ("date", "◦")]
    num = [c for c in data if c in d and pd.api.types.is_numeric_dtype(d[c])]
    rows = {"min": d[num].min(), "max": d[num].max(), "średnia": d[num].mean(),
            "suma": d[[c for c in num if c in SUMMABLE]].sum(min_count=1)}
    out = pd.DataFrame(rows).T.reindex(columns=data).astype("float64")
    if out.loc["suma"].isna().all():
        out = out.drop(index="suma")
    out = out.rename_axis("date").reset_index()
    if "◦" in columns:
        out["◦"] = ""
    return out[columns]


def column_config(cols, names, width=None):
    """Short headers; the full Polish name and the code go in the header tooltip."""
    return {c: st.column_config.Column(SHORT.get(c, c), help=f"{names.get(c, c)} ({c})", width=width) for c in cols}


# fixed pixel widths so the month summary lines up with the daily table below it
DATE_W, PROV_W, VALUE_W = 100, 70, 84


COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def compass(deg) -> str:
    return "" if deg is None or pd.isna(deg) else ("cisza" if deg == 0 else COMPASS[int((deg + 22.5) // 45) % 8])


with tab_now:
    now = load("latest_synop", station_id)
    recent = load("daily", station_id, TODAY - timedelta(days=4), TODAY)
    done = recent[recent["tx"].notna()] if not recent.empty else recent
    last_day = None if done.empty else done.iloc[-1]
    month_so_far = load("month_to_date", station_id, TODAY)
    have_month_so_far = month_so_far["tm"] is not None or month_so_far["prcp"] is not None
    live_days = load("live_days", station_id, 2) if now is None else pd.DataFrame()
    have_live = not live_days.empty and live_days.iloc[0][["tm", "tx", "tn", "prcp"]].notna().any()

    if now is None and not (have_live or have_month_so_far):
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
        row = live_days.iloc[0]
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
    if have_month_so_far:
        next(tiles).metric(f"Tśr {TODAY:%m.%Y} do dziś", fmt(month_so_far["tm"], unit=" °C"),
                           delta=None if month_so_far["tm_anom"] is None else f"{month_so_far['tm_anom']:+.1f} °C vs norma",
                           delta_color="off", help=f"{month_so_far['n_tm']} dni z danymi; norma {NORMAL_LABEL}")
        next(tiles).metric("Opad w miesiącu", fmt(month_so_far["prcp"], unit=" mm"),
                           delta=None if month_so_far["prcp_pct"] is None else f"{month_so_far['prcp_pct']:.0f}% normy",
                           delta_color="off", delta_arrow="off",
                           help=f"{month_so_far['n_prcp']} dni z danymi; norma pro rata")

    # --- hourly (latest day first) ---
    hcol, _ = st.columns([1, 3])
    stamps = [t for t in (fresh["synop"], fresh["hourly"]) if t]
    hour_end = max(stamps).date() if stamps else TODAY
    day = hcol.date_input("Dane godzinowe — dzień", hour_end, max_value=hour_end, format="YYYY-MM-DD")
    hourly_utc = load("hourly", station_id, day - timedelta(days=1), day)
    forecast_utc = load_forecast(meta)
    # sunrise / sunset for the night shading: yesterday through the end of the 16-day forecast
    sun_utc = (None if pd.isna(meta["lat"]) or pd.isna(meta["lon"]) else
               sun.times(float(meta["lat"]), float(meta["lon"]), min(day, TODAY) - timedelta(days=2),
                         TODAY + timedelta(days=17)))
    forecast_local = charts.to_local(forecast_utc)
    sun_local = charts.to_local(sun_utc, ("sunrise", "sunset"))
    if hourly_utc.empty:
        st.caption("Brak danych godzinowych (tylko stacje synoptyczne).")
    else:
        hourly_table = charts.to_local(hourly_utc)[["date", *[c for c in HOURLY_COLS if c in hourly_utc]]].copy()
        tz_label = charts.utc_offset_label(hourly_utc["date"])
        if hourly_utc["provisional"].any():
            hourly_table.insert(1, "◦", hourly_utc["provisional"].map({True: "wstępne", False: ""}))
        hourly_table["pogoda"] = hourly_table["ww"].map(lambda v: labels.WW_NAMES.get(int(v), "") if pd.notna(v) else "")
        hourly_table = hourly_table.sort_values("date", ascending=False)
        st.dataframe(style.style_frame(hourly_table, style.HOURLY_SCALES, whole=style.HOURLY_WHOLE), hide_index=True,
                     width="stretch", placeholder="", height=420,
                     column_config={"date": st.column_config.DatetimeColumn(f"czas ({tz_label})", format="DD.MM HH:mm",
                                                                           help="czas polski"),
                                    "◦": st.column_config.Column(" ", width="small"),
                                    "pogoda": st.column_config.Column("pogoda bieżąca", width="large"),
                                    **column_config(HOURLY_COLS, labels.HOURLY_VARS)})
        # the plots run in Polish local time; the table above stays in UTC like the archive
        hourly_local = charts.to_local(hourly_utc)
        ahead = None
        past = charts.to_local(load_forecast(meta, _day_ahead, day - timedelta(days=1), day))
        if forecast_local is not None and not forecast_local.empty and day == hour_end:
            obs = hourly_local.dropna(subset=["tm"])["date"]
            if not obs.empty:
                ahead = forecast.next_days(forecast_local, pd.Timestamp(obs.max()).to_pydatetime(),
                                           datetime.now(ZoneInfo(charts.LOCAL_TZ)).replace(tzinfo=None))
        if (ahead is not None and not ahead.empty) or (past is not None and not past.empty):
            st.caption("Prognoza T (Open-Meteo): nad pomiarami — prognoza wydana 24 h wcześniej, "
                       "dalej — najnowsza do końca jutra i pojutrza · przerywane pionowe linie: północ · czas polski · "
                       "szare tło: noc")
        st.altair_chart(charts.hourly_temperature(hourly_local, THEME, ahead, past, sun_local), width="stretch", theme=None)
    if forecast_utc is not None:
        if forecast_utc.empty:
            st.caption("Prognoza niedostępna.")
        else:
            st.caption(f"Prognoza godzinowa do {forecast_local['date'].max():%d.%m %H:%M} (czas polski) · temperatura, punkt rosy "
                       "i opad godzinowy · szare tło: noc (zachód–wschód słońca) · dane Open-Meteo.com (CC BY 4.0), punkt siatki modelu przy stacji")
            st.altair_chart(charts.forecast_chart(forecast_local, THEME, sun_local), width="stretch", theme=None)

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
        d = load("daily", station_id, start, end)
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
            daily_columns = {"◦": st.column_config.Column(" ", width=PROV_W), **column_config(cols, labels.DAILY_VARS, VALUE_W)}
            m = load("daily", station_id, TODAY.replace(day=1), TODAY)
            if not m.empty:
                st.caption(f"{labels.MONTH_ABBR[TODAY.month - 1]} {TODAY.year} do dziś · {len(m)} dni")
                summ = month_summary(m, list(view.columns))
                st.dataframe(style.style_frame(summ, style.DAILY_SCALES), hide_index=True, width="stretch",
                             placeholder="", height=36 * (len(summ) + 1) + 3,
                             column_config={"date": st.column_config.Column(" ", width=DATE_W), **daily_columns})
            st.dataframe(style.style_frame(view, style.DAILY_SCALES), hide_index=True, width="stretch", placeholder="",
                         height=min(36 * (len(view) + 1) + 3, 520),
                         column_config={"date": st.column_config.DateColumn("data", format="YYYY-MM-DD", width=DATE_W),
                                        **daily_columns})

            norm = load("monthly_normals", station_id, "tm")
            daily_normal = None
            if not norm.empty:
                days = pd.date_range(start, end, freq="D")
                daily_normal = pd.DataFrame({"date": days, "normal": days.month.map(norm.set_index("month")["mean"])})
            g1, g2 = st.columns(2)
            with g1:
                st.caption(f"Temperatura: zakres Tmin–Tmax, Tśr, norma {NORMAL_LABEL} (przerywana)")
                st.altair_chart(charts.daily_temperature(d, daily_normal, NORMAL_LABEL, THEME), width="stretch", theme=None)
            with g2:
                st.caption("Opad dobowy i suma narastająca")
                st.altair_chart(charts.daily_precip(d, THEME), width="stretch", theme=None)


# ----------------------------------------------------------- tab: monthly ---

with tab_month:
    c1, c2, _ = st.columns([3, 1, 2])
    var_keys = list(labels.MONTHLY_VARS)
    variable = c1.selectbox("Zmienna", var_keys, index=0,
                            format_func=lambda k: f"{labels.MONTHLY_VARS[k]} ({k})")
    max_missing = c2.number_input("Maks. braków (dni)", 0, 31, 3)
    if variable in labels.DESCRIPTIONS:
        st.caption(labels.DESCRIPTIONS[variable])
    grid = load("monthly_grid", station_id, variable, int(max_missing))
    if "value" not in grid:
        st.info("Brak danych miesięcznych dla tej stacji.")
    else:
        st.html(style.legend_html())
        st.html(style.grid_html(grid, variable, NORMAL_LABEL))
        if not grid["means"].empty:
            st.caption("Średnie wieloletnie (tylko pełne miesiące)")
            st.html(style.means_html(grid["means"], variable))


# ----------------------------------------------------------- tab: climate ---

with tab_clim:
    anomalies = load("annual_anomalies", station_id, "tm")
    years = sorted(set(anomalies["year"]) | {TODAY.year}, reverse=True)
    year = st.selectbox("Rok", years, index=0)

    c1, c2 = st.columns(2)
    year_values = load("monthly_year", station_id, int(year), ("tm", "prcp"))
    with c1:
        st.markdown(f"**Temperatura średnia {year} vs norma {NORMAL_LABEL}** (pas = ±1 odch. std.)")
        n_tm = load("monthly_normals", station_id, "tm")
        if n_tm.empty:
            st.caption("Brak normy temperatury dla tej stacji.")
        else:
            st.altair_chart(charts.climograph(year_values[year_values["variable"] == "tm"], n_tm, THEME, "°C", "Tśr"),
                            width="stretch", theme=None)
    with c2:
        st.markdown(f"**Opad miesięczny {year} vs norma {NORMAL_LABEL}** (kreska = średnia)")
        n_pr = load("monthly_normals", station_id, "prcp")
        if n_pr.empty:
            st.caption("Brak normy opadu dla tej stacji.")
        else:
            st.altair_chart(charts.climograph(year_values[year_values["variable"] == "prcp"], n_pr, THEME, "mm", "opad", bars=True),
                            width="stretch", theme=None)

    st.markdown(f"**Paski ocieplenia** — roczna anomalia Tśr względem {NORMAL_LABEL}")
    if len(anomalies) >= 5 and anomalies["anomaly"].notna().any():
        st.altair_chart(charts.stripes(anomalies.dropna(subset=["anomaly"]), THEME), width="stretch", theme=None)
    else:
        st.caption("Za mało pełnych lat.")

    st.markdown(f"**Narastająca suma opadu {year}** na tle średniej oraz najsuchszego i najwilgotniejszego roku")
    cum = load("cumulative_prcp", station_id)
    if cum.empty or int(year) not in set(cum["year"]):
        st.caption("Brak kompletnego roku opadowego.")
    else:
        st.altair_chart(charts.cumulative(cum, int(year), CFG.normal_period, THEME), width="stretch", theme=None)
