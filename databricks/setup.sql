-- One-time setup in the Databricks SQL Editor (after creating the Standard catalog cat_id).
-- Safe to run again.
CREATE CATALOG IF NOT EXISTS cat_id;
CREATE SCHEMA IF NOT EXISTS cat_id.bronze COMMENT 'Every exported row version, append-only (Auto Loader)';
CREATE SCHEMA IF NOT EXISTS cat_id.silver COMMENT 'Latest version of each Postgres row, with is_deleted';
CREATE SCHEMA IF NOT EXISTS cat_id.gold   COMMENT 'Reporting tables, one per question';
-- export_databricks.py uploads Parquet files here, one folder per Postgres table.
CREATE VOLUME IF NOT EXISTS cat_id.bronze.landing COMMENT 'Raw files from the home server';

-- Edmonton has been UTC-6 all year since Nov 2026 (tzdata 2026c). If Databricks' time zone
-- data is older, local dates in gold are an hour off in winter. This must say 06:00:00:
SELECT from_utc_timestamp(TIMESTAMP '2026-12-01 12:00:00', 'America/Edmonton') AS should_be_0600;
