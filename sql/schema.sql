-- IMGW local mirror. All timestamps are UTC. Idempotent: safe to run on every start.

CREATE TABLE IF NOT EXISTS stations (
    imgw_id     VARCHAR PRIMARY KEY,   -- 9-digit IMGW code, e.g. 352200375
    name        VARCHAR,
    id3         VARCHAR,               -- short code from wykaz_stacji.csv (synop: WMO 12xxx suffix)
    wmo_id      VARCHAR,               -- '12' || id3 for synop stations (35xxxxxxx)
    lat         DOUBLE,
    lon         DOUBLE,
    elevation   DOUBLE
);

CREATE TABLE IF NOT EXISTS daily_obs (
    imgw_id VARCHAR NOT NULL, date DATE NOT NULL,
    source  VARCHAR NOT NULL,          -- synop | klimat | opad
    tx DOUBLE, tn DOUBLE, tm DOUBLE, tng DOUBLE,
    prcp DOUBLE, prcp_kind VARCHAR, prcp_cumulative BOOLEAN,
    snow_depth DOUBLE, snow_depth_code VARCHAR, snow_water DOUBLE,
    fresh_snow DOUBLE, snow_type DOUBLE, snow_cover_type DOUBLE,
    sunshine DOUBLE,
    ra_time DOUBLE, sn_time DOUBLE, rasn_time DOUBLE, hail_time DOUBLE,
    fo_time DOUBLE, mist_time DOUBLE, rime_time DOUBLE, glaze_time DOUBLE,
    drift_low_time DOUBLE, drift_high_time DOUBLE, haze_time DOUBLE,
    ff10_time DOUBLE, ff15_time DOUBLE, ts_time DOUBLE, dew_time DOUBLE, frost_time DOUBLE,
    snow_cover_day BOOLEAN, lightning_day BOOLEAN, ground_state VARCHAR,
    isotherm_low_cm DOUBLE, isotherm_high_cm DOUBLE, radiation DOUBLE
);

-- Daily means from synoptic terms. origin='imgw' = s_d_t/k_d_t files (until mid-2024),
-- origin='derived' = computed by imgw.derive from hourly_obs.
CREATE TABLE IF NOT EXISTS daily_agg (
    imgw_id VARCHAR NOT NULL, date DATE NOT NULL,
    source VARCHAR NOT NULL, origin VARCHAR NOT NULL,
    cloud_cover DOUBLE,                -- oktas
    wind_speed DOUBLE, tm_terms DOUBLE, vapp DOUBLE, rh DOUBLE,
    ppp DOUBLE, mslp DOUBLE, prcp_day DOUBLE, prcp_night DOUBLE,
    n_terms SMALLINT
);

CREATE TABLE IF NOT EXISTS hourly_obs (
    imgw_id VARCHAR NOT NULL, ts TIMESTAMP NOT NULL,
    source VARCHAR NOT NULL,           -- synop (hourly) | klimat (06/12/18 UTC)
    tm DOUBLE, td DOUBLE, wb DOUBLE, rh DOUBLE, vapp DOUBLE, vpd DOUBLE,
    wind_dir DOUBLE, wind_dir_variable BOOLEAN, wind_dir_code DOUBLE, calm BOOLEAN,
    wind_speed DOUBLE, wind_gust DOUBLE, wind_gust_ww DOUBLE,
    mslp DOUBLE, ppp DOUBLE, p_tendency_code VARCHAR, p_tendency DOUBLE,
    prcp_6h DOUBLE, prcp_kind_6h DOUBLE,
    cloud_cover DOUBLE, low_cloud_cover DOUBLE, cl DOUBLE, cm DOUBLE, ch DOUBLE,
    cloud_base_code DOUBLE, cloud_base_low_m DOUBLE, cloud_base_high_m DOUBLE,
    visib_code DOUBLE, visib_obs_m DOUBLE, visib_auto_m DOUBLE,
    ww DOUBLE, w1 DOUBLE, sunshine DOUBLE, dew BOOLEAN, ground_state DOUBLE,
    tx_12h DOUBLE, tn_12h DOUBLE, tng_12h DOUBLE,
    snow_depth DOUBLE, snow_depth_code VARCHAR, snow_water DOUBLE, fresh_snow DOUBLE,
    tg05 DOUBLE, tg10 DOUBLE, tg20 DOUBLE, tg50 DOUBLE, tg100 DOUBLE
);

-- Provisional observations from the live JSON APIs (long format).
CREATE TABLE IF NOT EXISTS live_obs (
    imgw_id VARCHAR,                   -- resolved 9-digit id when known
    station_key VARCHAR NOT NULL,      -- id as given by the API
    network VARCHAR NOT NULL,          -- synop_live | telemetry
    ts TIMESTAMP NOT NULL,
    variable VARCHAR NOT NULL,
    value DOUBLE,
    fetched_at TIMESTAMP NOT NULL
);

-- Provisional hourly observations decoded from WMO SYNOP messages (imgw.synop_feed),
-- covering the gap between the end of the IMGW archive and now. Pruned once the
-- archive covers the hour.
CREATE TABLE IF NOT EXISTS synop_msg_obs (
    wmo_id VARCHAR NOT NULL, imgw_id VARCHAR, ts TIMESTAMP NOT NULL,
    received_at TIMESTAMP, raw VARCHAR,
    tm DOUBLE, td DOUBLE, rh DOUBLE, vapp DOUBLE, ppp DOUBLE, mslp DOUBLE, p_tendency DOUBLE,
    wind_dir DOUBLE, wind_speed DOUBLE, wind_gust DOUBLE,
    cloud_cover DOUBLE, low_cloud_cover DOUBLE, cl DOUBLE, cm DOUBLE, ch DOUBLE,
    visib_obs_m DOUBLE, ww DOUBLE, w1 DOUBLE,
    prcp DOUBLE, prcp_period_h DOUBLE, prcp_24h DOUBLE,
    tx_12h DOUBLE, tn_12h DOUBLE, tng_12h DOUBLE, snow_depth DOUBLE, sunshine_24h DOUBLE
);

CREATE TABLE IF NOT EXISTS qc_issues (
    imgw_id VARCHAR, obs_time TIMESTAMP, tbl VARCHAR, variable VARCHAR,
    value DOUBLE, issue VARCHAR
);

CREATE TABLE IF NOT EXISTS sync_log (
    url VARCHAR PRIMARY KEY,
    fingerprint VARCHAR,               -- "<mtime>|<size>" as shown in the directory listing
    sha256 VARCHAR, rows BIGINT, loaded_at TIMESTAMP, status VARCHAR
);

CREATE TABLE IF NOT EXISTS monthly_summary (
    imgw_id VARCHAR, year INTEGER, month INTEGER, variable VARCHAR,
    value DOUBLE, days_present INTEGER, days_missing INTEGER
);

-- period: 'DJF' | 'MAM' | 'JJA' | 'SON' | 'year'; DJF belongs to the year of its Jan/Feb.
CREATE TABLE IF NOT EXISTS period_summary (
    imgw_id VARCHAR, year INTEGER, period VARCHAR, variable VARCHAR,
    value DOUBLE, days_present INTEGER, days_missing INTEGER
);

CREATE TABLE IF NOT EXISTS normals (            -- rebuilt by imgw.climate.rebuild_normals
    imgw_id VARCHAR, month INTEGER, variable VARCHAR, period VARCHAR,
    n_years BIGINT, mean DOUBLE, sd DOUBLE, p10 DOUBLE, p90 DOUBLE, min DOUBLE, max DOUBLE
);

CREATE TABLE IF NOT EXISTS station_thresholds (
    imgw_id VARCHAR PRIMARY KEY, hot_p95 DOUBLE
);

-- ---------------------------------------------------------------- views ---

-- One row per station-day; each variable taken from the best source available
-- (synop > klimat > opad), daily means from IMGW files first, derived second.
CREATE OR REPLACE VIEW v_daily AS
WITH o AS (
    SELECT *, CASE source WHEN 'synop' THEN 1 WHEN 'klimat' THEN 2 ELSE 3 END AS prio
    FROM daily_obs
), obs AS (
    SELECT imgw_id, date,
        first(tm ORDER BY prio) FILTER (WHERE tm IS NOT NULL) AS tm,
        first(tx ORDER BY prio) FILTER (WHERE tx IS NOT NULL) AS tx,
        first(tn ORDER BY prio) FILTER (WHERE tn IS NOT NULL) AS tn,
        first(tng ORDER BY prio) FILTER (WHERE tng IS NOT NULL) AS tng,
        first(prcp ORDER BY prio) FILTER (WHERE prcp IS NOT NULL) AS prcp,
        first(prcp_kind ORDER BY prio) FILTER (WHERE prcp IS NOT NULL) AS prcp_kind,
        bool_or(prcp_cumulative) AS prcp_cumulative,
        first(snow_depth ORDER BY prio) FILTER (WHERE snow_depth IS NOT NULL) AS snow_depth,
        max(snow_water) AS snow_water, max(fresh_snow) AS fresh_snow,
        max(sunshine) AS sunshine,
        max(ff10_time) AS ff10_time, max(ff15_time) AS ff15_time,
        max(ra_time) AS ra_time, max(sn_time) AS sn_time, max(rasn_time) AS rasn_time,
        max(hail_time) AS hail_time, max(fo_time) AS fo_time, max(mist_time) AS mist_time,
        max(dew_time) AS dew_time, max(frost_time) AS frost_time, max(ts_time) AS ts_time,
        max(glaze_time) AS glaze_time, max(rime_time) AS rime_time,
        string_agg(DISTINCT source, ',') AS sources
    FROM o GROUP BY imgw_id, date
), agg AS (
    SELECT imgw_id, date,
        first(cloud_cover ORDER BY p) FILTER (WHERE cloud_cover IS NOT NULL) AS cloud_cover,
        first(wind_speed ORDER BY p) FILTER (WHERE wind_speed IS NOT NULL) AS wind_speed,
        first(rh ORDER BY p) FILTER (WHERE rh IS NOT NULL) AS rh,
        first(vapp ORDER BY p) FILTER (WHERE vapp IS NOT NULL) AS vapp,
        first(mslp ORDER BY p) FILTER (WHERE mslp IS NOT NULL) AS mslp,
        first(ppp ORDER BY p) FILTER (WHERE ppp IS NOT NULL) AS ppp,
        first(prcp_day ORDER BY p) FILTER (WHERE prcp_day IS NOT NULL) AS prcp_day,
        first(prcp_night ORDER BY p) FILTER (WHERE prcp_night IS NOT NULL) AS prcp_night
    FROM (SELECT *, (CASE source WHEN 'synop' THEN 0 ELSE 2 END)
                    + (CASE origin WHEN 'imgw' THEN 0 ELSE 1 END) AS p FROM daily_agg)
    GROUP BY imgw_id, date
)
SELECT obs.imgw_id, obs.date,
       obs.tm, obs.tx, obs.tn, obs.tng,
       round((obs.tx + obs.tn) / 2, 1) AS tm2,
       round(agg.rh, 1) AS rh, round(agg.vapp, 1) AS vapp,
       round(agg.cloud_cover, 1) AS cloud_cover,            -- oktas (as on meteomodel)
       round(agg.cloud_cover * 12.5, 0) AS cloud_cover_pct,
       round(agg.wind_speed, 1) AS wind_speed,
       obs.ff10_time, obs.ff15_time,
       round(agg.mslp, 1) AS mslp, round(agg.ppp, 1) AS ppp,
       obs.prcp, obs.prcp_kind, obs.prcp_cumulative, agg.prcp_day, agg.prcp_night,
       obs.snow_depth, obs.snow_water, obs.fresh_snow, obs.sunshine,
       obs.ra_time, obs.sn_time, obs.rasn_time, obs.hail_time, obs.fo_time, obs.mist_time,
       obs.dew_time, obs.frost_time, obs.ts_time, obs.glaze_time, obs.rime_time,
       obs.sources
FROM obs LEFT JOIN agg USING (imgw_id, date);

-- Hourly data under meteomodel's API names: the IMGW archive, then provisional
-- SYNOP-message hours after each station's archive end (provisional = TRUE).
CREATE OR REPLACE VIEW v_hourly AS
SELECT imgw_id, ts AS date, source,
       tm, tx_12h AS tx, tn_12h AS tn, tng_12h AS tng, td, rh, wb,
       cloud_cover, low_cloud_cover, cl, cm, ch,
       wind_speed, wind_dir, wind_dir_variable, calm, wind_gust, wind_gust_ww,
       mslp, ppp, p_tendency, prcp_6h AS prcp,
       round(visib_obs_m / 1000, 1) AS visib, round(visib_auto_m / 1000, 1) AS visib_auto,
       sunshine, ww, w1, snow_depth, snow_depth_code, FALSE AS provisional
FROM hourly_obs
UNION ALL BY NAME
SELECT m.imgw_id, m.ts AS date, 'synop_msg' AS source,
       m.tm, m.tx_12h AS tx, m.tn_12h AS tn, m.tng_12h AS tng, m.td, m.rh,
       m.cloud_cover, m.low_cloud_cover, m.cl, m.cm, m.ch,
       m.wind_speed, m.wind_dir, m.wind_dir = 0 AND m.wind_speed = 0 AS calm, m.wind_gust,
       m.mslp, m.ppp, m.p_tendency,
       CASE WHEN m.prcp_period_h <= 6 THEN m.prcp END AS prcp,    -- 12 h totals at 06/18 go to the daily view
       round(m.visib_obs_m / 1000, 1) AS visib, m.ww, m.w1, m.snow_depth, TRUE AS provisional
FROM synop_msg_obs m
LEFT JOIN (SELECT imgw_id, max(ts) AS last_ts FROM hourly_obs WHERE source = 'synop' GROUP BY imgw_id) a
       USING (imgw_id)
WHERE m.imgw_id IS NOT NULL AND (a.last_ts IS NULL OR m.ts > a.last_ts);

-- Provisional daily values from SYNOP messages, with IMGW's day conventions:
--   tm and daily means: the 8 synoptic terms 00..21 UTC of the day (>= 6 present)
--   tx / tn / tng: 12 h extremes reported at 06 and 18 UTC of the day (18-18 UTC window)
--   prcp: 06-06 UTC, assigned to the day it starts: the 24 h group at 06 UTC next day,
--         else the 12 h totals at 18 UTC + 06 UTC next day
--   sunshine: 55SSS reported at 06 UTC next day;  snow_depth: at 06 UTC of the day
CREATE OR REPLACE VIEW v_synop_daily AS
WITH m AS (
    SELECT *, CAST(ts AS DATE) AS d, hour(ts) AS hh FROM synop_msg_obs
    WHERE imgw_id IS NOT NULL AND minute(ts) = 0
), terms AS (
    SELECT imgw_id, d AS date, count(tm) AS n_terms,
        CASE WHEN count(tm) >= 6 THEN round(avg(tm), 4) END AS tm,
        CASE WHEN count(rh) >= 6 THEN round(avg(rh), 4) END AS rh,
        CASE WHEN count(vapp) >= 6 THEN round(avg(vapp), 4) END AS vapp,
        CASE WHEN count(cloud_cover) >= 6 THEN round(avg(cloud_cover), 4) END AS cloud_cover,
        CASE WHEN count(wind_speed) >= 6 THEN round(avg(wind_speed), 4) END AS wind_speed,
        CASE WHEN count(mslp) >= 6 THEN round(avg(mslp), 4) END AS mslp,
        CASE WHEN count(ppp) >= 6 THEN round(avg(ppp), 4) END AS ppp
    FROM m WHERE hh % 3 = 0 GROUP BY ALL
), ext AS (
    SELECT imgw_id, d AS date,
        CASE WHEN count(tx_12h) = 2 THEN max(tx_12h) END AS tx,
        CASE WHEN count(tn_12h) = 2 THEN min(tn_12h) END AS tn,
        min(tng_12h) FILTER (WHERE hh = 6) AS tng,
        max(snow_depth) FILTER (WHERE hh = 6) AS snow_depth
    FROM m WHERE hh IN (6, 18) GROUP BY ALL
), pr AS (                                     -- report at 06 UTC belongs to the previous day
    SELECT imgw_id, CASE WHEN hh = 6 THEN d - 1 ELSE d END AS date,
        max(prcp_24h) FILTER (WHERE hh = 6) AS p24,
        max(prcp) FILTER (WHERE hh = 18 AND prcp_period_h = 12) AS p18,
        max(prcp) FILTER (WHERE hh = 6 AND prcp_period_h = 12) AS p06,
        max(sunshine_24h) FILTER (WHERE hh = 6) AS sunshine
    FROM m WHERE hh IN (6, 18) GROUP BY ALL
)
SELECT imgw_id, CAST(date AS DATE) AS date,
       round(tm, 1) AS tm, tx, tn, tng, round((tx + tn) / 2, 1) AS tm2,
       round(rh, 1) AS rh, round(vapp, 1) AS vapp, round(cloud_cover, 1) AS cloud_cover,
       round(wind_speed, 1) AS wind_speed, round(mslp, 1) AS mslp, round(ppp, 1) AS ppp,
       coalesce(p24, p18 + p06) AS prcp, snow_depth, sunshine, n_terms
FROM terms FULL JOIN ext USING (imgw_id, date) FULL JOIN pr USING (imgw_id, date);

-- Provisional daily values from 10-min telemetry (needs `imgw live` every 10 min).
-- Windows follow IMGW conventions: tx/tn over 18-18 UTC, prcp over 06-06 UTC
-- (assigned to the day the window starts), tm = mean of the 8 synoptic terms.
-- A value is only given when coverage is near-complete (n_* = samples seen).
CREATE OR REPLACE VIEW v_live_daily AS
WITH tel AS (
    SELECT imgw_id, ts, variable, value FROM live_obs
    WHERE network = 'telemetry' AND imgw_id IS NOT NULL
), temp AS (
    SELECT imgw_id, CAST(ts + INTERVAL 6 HOUR - INTERVAL 1 SECOND AS DATE) AS date,
           max(value) AS tx, min(value) AS tn, count(*) AS n_t
    FROM tel WHERE variable = 'temperatura_powietrza' GROUP BY ALL
), tmean AS (
    SELECT imgw_id, CAST(ts AS DATE) AS date, avg(value) AS tm, count(*) AS n_terms
    FROM tel WHERE variable = 'temperatura_powietrza' AND minute(ts) = 0 AND hour(ts) % 3 = 0
    GROUP BY ALL
), pr AS (
    SELECT imgw_id, CAST(ts - INTERVAL 6 HOUR - INTERVAL 1 SECOND AS DATE) AS date,
           sum(value) AS prcp, count(*) AS n_p
    FROM tel WHERE variable = 'opad_10min' GROUP BY ALL
)
SELECT imgw_id, date,
       CASE WHEN n_terms >= 6 THEN round(tm, 1) END AS tm,
       CASE WHEN n_t >= 120 THEN tx END AS tx,
       CASE WHEN n_t >= 120 THEN tn END AS tn,
       CASE WHEN n_p >= 138 THEN round(prcp, 1) END AS prcp,
       coalesce(n_terms, 0) AS n_terms, coalesce(n_t, 0) AS n_t, coalesce(n_p, 0) AS n_p
FROM tmean FULL JOIN temp USING (imgw_id, date) FULL JOIN pr USING (imgw_id, date);

-- Provisional days after each station's daily archive ends: SYNOP-message days
-- where available (synop stations), else 10-min telemetry days.
CREATE OR REPLACE VIEW v_provisional_daily AS
WITH last_archive AS (SELECT imgw_id, max(date) AS last_date FROM daily_obs GROUP BY imgw_id),
syn AS (
    SELECT s.*, 'synop_msg' AS prov_source FROM v_synop_daily s LEFT JOIN last_archive a USING (imgw_id)
    WHERE (a.last_date IS NULL OR s.date > a.last_date)
      AND (s.tm IS NOT NULL OR s.tx IS NOT NULL OR s.prcp IS NOT NULL)
)
SELECT * EXCLUDE (n_terms) FROM syn
UNION ALL BY NAME
SELECT l.imgw_id, l.date, l.tm, l.tx, l.tn, l.prcp, 'telemetry' AS prov_source
FROM v_live_daily l LEFT JOIN last_archive a USING (imgw_id)
WHERE (a.last_date IS NULL OR l.date > a.last_date)
  AND NOT EXISTS (SELECT 1 FROM syn WHERE syn.imgw_id = l.imgw_id AND syn.date = l.date);

-- Archive where available, provisional values after the archive ends.
CREATE OR REPLACE VIEW v_latest AS
SELECT imgw_id, date, tm, tx, tn, prcp, FALSE AS is_provisional FROM v_daily
UNION ALL
SELECT imgw_id, date, tm, tx, tn, prcp, TRUE FROM v_provisional_daily;

-- Station catalogue in meteomodel's /api/stations shape.
CREATE OR REPLACE VIEW v_stations AS
WITH cov AS (
    SELECT imgw_id, min(date) AS first_date, max(date) AS last_date,
           list(DISTINCT source ORDER BY source) AS networks
    FROM daily_obs GROUP BY imgw_id
)
SELECT s.imgw_id, s.name, s.wmo_id, s.lat, s.lon, s.elevation,
       cov.first_date, cov.last_date, cov.networks,
       concat(CASE WHEN list_contains(networks, 'synop') THEN 's' ELSE '' END,
              CASE WHEN list_contains(networks, 'klimat') THEN 'k' ELSE '' END,
              CASE WHEN list_contains(networks, 'opad') THEN 'o' ELSE '' END) AS type
FROM cov LEFT JOIN stations s USING (imgw_id);

-- Monthly / seasonal / annual values with meteomodel's classification:
-- 11 classes from linear percentiles (5,10,20,30,40,60,70,80,90,95) of all complete
-- periods in the station's record (1 = above P95 ... 11 = at or below P5).
-- Complete = days_missing <= 3 (month), 5 (season), 10 (year), meteomodel's defaults.
-- Records are the highest/lowest complete value. Reproduces meteomodel's classes exactly.
CREATE OR REPLACE VIEW v_monthly AS
WITH m AS (
    SELECT *, days_missing <= 3 AS complete FROM monthly_summary
), w AS (
    SELECT *,
        quantile_cont(value, [0.05, 0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9, 0.95])
            FILTER (WHERE complete) OVER p AS th,
        max(value) FILTER (WHERE complete) OVER p AS rec_hi,
        min(value) FILTER (WHERE complete) OVER p AS rec_lo
    FROM m WINDOW p AS (PARTITION BY imgw_id, month, variable)
)
SELECT w.imgw_id, w.year, w.month, w.variable, w.value, w.days_present, w.days_missing,
       NOT w.complete AS is_partial,
       CASE WHEN w.complete AND w.value IS NOT NULL
            THEN 11 - len(list_filter(w.th, x -> x < w.value)) END AS class,
       w.complete AND w.value = w.rec_hi AS is_record_high,
       w.complete AND w.value = w.rec_lo AS is_record_low,
       w.value - n.mean AS anomaly
FROM w LEFT JOIN normals n
       ON n.imgw_id = w.imgw_id AND n.month = w.month AND n.variable = w.variable;

CREATE OR REPLACE VIEW v_period AS
WITH m AS (
    SELECT *, days_missing <= CASE period WHEN 'year' THEN 10 ELSE 5 END AS complete
    FROM period_summary
), w AS (
    SELECT *,
        quantile_cont(value, [0.05, 0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9, 0.95])
            FILTER (WHERE complete) OVER p AS th,
        max(value) FILTER (WHERE complete) OVER p AS rec_hi,
        min(value) FILTER (WHERE complete) OVER p AS rec_lo,
        avg(value) FILTER (WHERE complete AND year BETWEEN 1991 AND 2020) OVER p AS normal
    FROM m WINDOW p AS (PARTITION BY imgw_id, period, variable)
)
SELECT imgw_id, year, period, variable, value, days_present, days_missing,
       NOT complete AS is_partial,
       CASE WHEN complete AND value IS NOT NULL
            THEN 11 - len(list_filter(th, x -> x < value)) END AS class,
       complete AND value = rec_hi AS is_record_high,
       complete AND value = rec_lo AS is_record_low,
       value - normal AS anomaly
FROM w;
