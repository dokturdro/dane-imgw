# daneimgw — local IMGW data mirror

Mirrors IMGW's public meteorological archive into DuckDB, cleans it, and exposes views named like
[dane.meteomodel.pl](https://dane.meteomodel.pl)'s API. The weeks before IMGW publishes a month are
filled with provisional SYNOP reports (via [OGIMET](https://www.ogimet.com)) and live telemetry.
A local Streamlit dashboard sits on top.

## Quick start

Needs [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run imgw init     # create data/imgw.duckdb and load the station list
uv run imgw sync     # download the archive; the first run fetches 1991 onwards and takes hours
uv run imgw synop    # provisional SYNOP from the archive end to now
uv run imgw dash     # dashboard on http://localhost:8501
```

Settings live in [`config.toml`](config.toml); every command is listed in `uv run imgw --help`.

On Windows, `scripts/register_tasks.ps1` schedules `live`, `synop` and `sync`, and
`scripts/open_dash.ps1 -Register` adds an `imgw://dash` bookmark that starts the dashboard.

## Data sources

- **Archive:** IMGW monthly ZIPs, published 2–8 weeks after month end. No free official source is fresher.
- **SYNOP via OGIMET:** the observations IMGW's hourly archive is built from. Back-tested on
  September 2026 (58 stations): ≥ 98.4 % match on every variable. Synop stations only.
- **Live telemetry:** IMGW `api/data/*`, latest values only (≈790 stations, 10-min).
- Paid history: the Bank Danych IMGW-PIB shop, or a contract (biznes@imgw.pl).
