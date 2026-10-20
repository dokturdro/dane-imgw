/# daneimgw — local IMGW data mirror

A local, self-refreshing replacement for the data pipeline behind
[dane.meteomodel.pl](https://dane.meteomodel.pl) ("Dane IMGW": Miesięczne / Dobowe / Terminowe).
It mirrors IMGW's public archive into a DuckDB file, cleans it, and exposes views
named like meteomodel's API so a dashboard can sit straight on top.

## How meteomodel works (reverse-engineered)

Flask backend + vanilla-JS frontend. The JS calls:

| endpoint | returns |
|---|---|
| `/api/stations` | `[{imgw_id, name, type, first_year, last_year, ...}]` |
| `/api/daterange?station_id=` | `[{from, to}]` |
| `/api/daily?imgw_id&start_date&end_date&variables=` | `{data:[{date, tm, tx, ...}]}` (≤366 days) |
| `/api/hourly?...` | `{data:[{date: "YYYY-MM-DDTHH:00:00", ...}]}` (≤10 days) |
| `/api/monthly_summary?station_id&variable` | year×month table with classes, records, missing days |

The data comes from the IMGW monthly ZIP archive
(`danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne/`).
Meteomodel re-imports it only occasionally. On 2026-10-17 it ended at 2026-08-31,
while IMGW had already published September.

## Freshness

| layer | source | lag |
|---|---|---|
| archive (`daily_obs`, `hourly_obs`) | monthly ZIPs; `imgw sync` picks each file up the day it appears | IMGW publishes 2–8 weeks after month end |
| provisional, synop stations (`synop_msg_obs` → `v_synop_daily`, `v_hourly`) | WMO SYNOP messages via [OGIMET](https://www.ogimet.com) (`imgw synop`, hourly) | current hour, with history back to the archive end |
| provisional, other stations (`live_obs` → `v_live_daily`) | `/api/data/meteo` (≈790 telemetry stations, 10-min) + `/api/data/synop` (62 stations, latest only) | minutes, only while `imgw live` runs |

Live rows are pruned at each sync once the archive covers those days, and in any case after `live_keep_days` (default 400). That limit matters for telemetry-only stations, which never get archive rows.

## Usage

```powershell
uv sync
uv run imgw init                  # DB + station list
uv run imgw sync                  # 1991+ by default (config.toml); --from 1951 for full depth
uv run imgw live                  # one poll of the live APIs
uv run imgw synop                 # SYNOP messages from the archive end to now (hourly)
uv run imgw status
uv run imgw rebuild               # recompute derived tables only
uv run imgw dash                  # local dashboard at http://localhost:8501
powershell -File scripts\register_tasks.ps1   # schedule live (10 min) + sync (daily 09:00)
powershell -File scripts\open_dash.ps1 -Register  # once; then bookmark imgw://dash: starts the dashboard
                                                  # hidden, opens the browser, refreshes synop -> live -> sync
powershell -File scripts\open_dash.ps1 -Stop      # stop that background dashboard
```

DuckDB allows one process at a time. A `live` poll that finds the database busy (for example during a long `sync`) saves its raw API responses to `data/live_spool/`. The next poll or sync loads them, so no 10-minute samples are lost. `sync`, `init` and `rebuild` wait up to 10 minutes for a running poll to finish.

## Other IMGW data sources (checked 2026-10-18)

- **No official free IMGW API offers history fresher than the monthly archive.** The `api/data/*` endpoints return only the latest value.
- **Datastore telemetry:** `danepubliczne.imgw.pl/datastore` holds 10-min telemetry since 2008, as monthly files with the same lag as the archive.
- **Paid options:** the Bank Danych IMGW-PIB shop sells historical products. Anything else is "na wniosek" or by commercial agreement (biznes@imgw.pl); it is free for private use, with fees by contract for business use.
- **SYNOP via OGIMET:** IMGW's hourly archive is built from the same SYNOP observations the stations exchange internationally. OGIMET archives them for free.
  - Back-test against September 2026 for 58 stations: tx 100 %, tn 99.9 %, prcp 99.7 %, tm 99.0 %, sunshine 98.4 %, snow depth 100 %, pressure/RH/wind ≥ 98.9 %.
  - Not in SYNOP: phenomenon durations, wet-bulb and soil temperatures. The ground minimum is in whole degrees only, so it is not used.
  - SYNOP covers synop stations only.

## Tables and views (`sql/schema.sql`)

- `stations`: wykaz_stacji.csv plus coordinates from telemetry; `wmo_id` links the live synop feed.
- `daily_obs`: one row per station/day/source (synop, klimat, opad), friendly names (tm, tx, tn, tng, prcp, snow_depth, sunshine, *_time …).
- `daily_agg`: daily means of cloud cover, wind, RH, vapour pressure and pressure. `origin='imgw'` rows come from s_d_t/k_d_t (IMGW stopped publishing these in mid-2024). `origin='derived'` rows are the mean of the 8 synoptic terms from hourly data, which is how meteomodel fills the gap.
- `hourly_obs`: synop hourly (all 50+ fields) and klimat terms.
- `live_obs`: provisional telemetry, long format.
- `synop_msg_obs`: decoded SYNOP messages after the archive end. Only stations with an active IMGW archive are stored, and rows are pruned as the archive catches up.
- `monthly_summary`, `period_summary` (DJF/MAM/JJA/SON/year), `normals`, `station_thresholds`.
- `qc_issues`: out-of-range values and tx<tn. These values are flagged, not removed.
- **Views:** `v_daily`, `v_hourly` (meteomodel names/units), `v_monthly` / `v_period` (completeness, 11 classes, records, anomaly vs 1991–2020), `v_stations`, `v_synop_daily` / `v_live_daily` → `v_provisional_daily` (SYNOP first, telemetry as fallback), `v_latest` (archive ∪ provisional). `v_hourly` appends provisional SYNOP hours with `provisional = TRUE`.

## Cleaning rules

- The CSVs are cp1250, headerless, and quoted inconsistently. Column layouts are transcribed from IMGW's `*_format.txt` (`imgw/schema.py`) and verified against 1991, 2023 and 2026 files.
- Status `"8"` (not measured) → NULL even if the value field says 0. Status `"9"` (no phenomenon) → 0, except gusts → NULL. Status `"Z"` (opad cumulative over preceding unmeasured days) → value kept, `prcp_cumulative = TRUE`. Both pre-2024 (`0,"8"`) and post-2024 (`,"8"`) encodings are handled.
- Snow depth codes: 997 → 0.25 cm (`trace`), 998 → NULL (`patchy`), 999 → NULL (`unmeasurable`). Wind direction 999 → NULL with `wind_dir_variable`. Dir 0 + speed 0 → `calm`.
- Cloud genus `/` (not observable) → NULL. Meteomodel shows these as 0.
- Sea-level pressure outside 900–1100 hPa → NULL. Until 2015 the mountain stations (Zakopane, Kasprowy Wierch, Śnieżka) put the geopotential height of an isobaric surface in that field.
- Daily means are rounded half-up for display. Derived means are rounded to 4 dp first, so float noise (1.2499999…) doesn't flip the result.
- `v_daily` takes each variable from the best source: synop > klimat > opad.

## Climate products

- Monthly variables match meteomodel's selector: tm, tm2, tx, tn, txx, tnn, txn, tnx, tmx, tmn, tgn, prcp, prcpx, mslp, ppp, wind_speed, sunshine, rh, vapp, snow_depth, sndpx, sndpcnt, hdd/cdd/gdd, hot (Tmax ≥ station P95 of JJA 1981–2020), and threshold-day counts. The "gt" counts use ≥ and the "lt" counts use ≤, as meteomodel does.
- Classes use meteomodel's method, reverse-engineered and matching 100%. There are 11 classes, from linear percentiles (5, 10, 20, 30, 40, 60, 70, 80, 90, 95) of all complete periods in the station's own record. 1 = above P95, 6 = between P40 and P60, 11 = at or below P5. Ties go to the lower class. A period is complete when it is missing at most 3 days (month), 5 (season) or 10 (year).
- Because the ranking uses the station's whole record, classes match meteomodel only when the history matches too. Meteomodel starts in 1951, the default here is 1991 (`imgw sync --from 1951` to match). `hot` likewise needs data from 1981 for its P95.

## Verified against meteomodel

Covers 2026-01-01…08-31 for Warszawa, Kraków-Balice and Gdańsk, plus hourly 21–31 Aug for Warszawa. All daily and hourly variables are identical except:

- **Daily means on days missing 1–2 synoptic terms:** meteomodel returns NULL because it requires 8/8 terms. We return a value because we require ≥6/8 (`MIN_TERMS` in `imgw/derive.py`).
- **Exact x.x5 ties:** a single ±0.1 difference.
- **`snow_water` / hourly `sunshine` / `prcp` on "no phenomenon" days:** meteomodel shows NULL; we show 0.
- **Cloud genus `/`:** meteomodel shows 0; we show NULL.

The monthly summaries were checked for Warszawa and Kraków-Balice, 1991–2025, across 13 variables. All values are identical except `hot`, whose threshold needs the 1981–1990 data.

## Dashboard (`imgw dash`)

A Streamlit app in `imgw/dash/`, localhost only. It follows the system light/dark setting.

- **Teraz i dobowe:**
  - provisional tiles (today's live values, month-to-date vs normal);
  - a daily table with meteomodel's colour scales, column groups, and short headers with full names in the tooltips;
  - temperature and precipitation charts;
  - an hourly drill-down with weather codes named.
- **Miesięczne:** meteomodel's year × month grid for any variable. Cells are coloured by class, ▲▼ marks records, partial months are grey italics, and hovering shows details. Seasonal/annual columns and reference-period means sit underneath.
- **Klimat:**
  - climographs (temperature and precipitation vs the 1991–2020 normal);
  - warming stripes plus an anomaly bar chart;
  - cumulative precipitation against the normal and the driest/wettest years.

Every query opens a short-lived read-only connection, and results are cached for 10 minutes ("Odśwież dane" clears the cache). A running dashboard therefore never blocks `imgw live` or `imgw sync`. While a sync holds the database, it shows the last cached data under a notice. After changing code under `imgw/`, restart `imgw dash`: Streamlit reloads `app.py` but keeps imported modules cached.
