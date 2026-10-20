# daneimgw — local IMGW data mirror

A local, self-refreshing replacement for the data behind
[dane.meteomodel.pl](https://dane.meteomodel.pl). It mirrors IMGW's public archive into DuckDB,
cleans it, and exposes views named like meteomodel's API. Meteomodel re-imports the archive only
occasionally (weeks behind IMGW); this picks up each monthly file the day it appears and fills the
gap with provisional SYNOP (via [OGIMET](https://www.ogimet.com)) and live telemetry.

## Data sources

- **Archive:** IMGW monthly ZIPs, published 2–8 weeks after month end. No free official source is fresher.
- **SYNOP via OGIMET:** the same observations IMGW's hourly archive is built from. Back-tested on
  September 2026 (58 stations): ≥ 98.4 % match on every variable. Synop stations only.
- **Live telemetry:** IMGW `api/data/*`, latest values only (≈790 stations, 10-min).
- Paid history: the Bank Danych IMGW-PIB shop, or a contract (biznes@imgw.pl).

## Dashboard (`imgw dash`)

A local Streamlit app that follows the system light/dark setting:

- **Teraz i dobowe:** provisional tiles, a colour-scaled daily table, charts, hourly drill-down.
- **Miesięczne:** meteomodel's year × month grid, coloured by class, with records marked.
- **Klimat:** climographs, warming stripes, cumulative precipitation vs normal.

It reads through short-lived read-only connections, so it never blocks `sync` or `live`.
