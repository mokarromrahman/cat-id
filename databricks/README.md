# Databricks (Free Edition)

Postgres on the home server → `export_databricks.py` (hourly, outbound HTTPS only) → Parquet
files in the volume `cat_id.bronze.landing` → one Lakeflow declarative pipeline (daily) →
bronze, silver and gold tables.

| Layer | Tables | What's in them |
| --- | --- | --- |
| raw | `/Volumes/cat_id/bronze/landing/<table>/*.parquet` | The exporter's files, never changed. Extra columns `_deleted`, `_deleted_at`, `_change_on`, `_exported_at`. |
| bronze | `cat_id.bronze.<table>` (one per Postgres table) | Every exported row version, append-only, plus `_source_file`, `_ingested_at`. |
| silver | `cat_id.silver.<table>` (one per Postgres table) | Latest version of each row (SCD type 1) plus `is_deleted`/`deleted_at`: removed from Postgres by a hard delete (undo, chore doers). Soft deletes stay in `deleted_on`. |
| gold | `cat_events_daily`, `litterbox_cleanings_daily`, `vet_visits`, `chores_done` | One table per question (`pipeline/gold.sql`). Edmonton days. |

`deleted_row` and `export_state` are not sent as tables of their own: deleted rows travel in
their own table's files (flagged `_deleted`), and `export_state` is the exporter's bookkeeping.

## One-time setup

1. **Catalog, schemas, volume.** Catalog `cat_id`, type Standard. Then run
   [`setup.sql`](setup.sql) in the SQL Editor. Its last query checks the Edmonton time zone:
   it must say `06:00:00`.
2. **Token.** Avatar → Settings → Developer → Access tokens → Generate new token (lifetime
   e.g. 365 days; note when it expires). On the server, in `.env`:
   ```
   DATABRICKS_HOST=https://<your-workspace>.cloud.databricks.com
   DATABRICKS_TOKEN=dapi...
   ```
   (`DATABRICKS_VOLUME_PATH` defaults to `/Volumes/cat_id/bronze/landing`;
   `EXPORT_INTERVAL_SECONDS` to 3600.)
3. **Start the exporter** (needs the image with migration `0006`):
   ```
   docker compose up -d cat-id exporter      # cat-id runs the migration
   docker compose exec exporter python export_databricks.py --dry-run /app/inbox/_export_test
   docker compose logs -f exporter           # "export 2026...Z: app_user 4, cat 2, ..."
   ```
   The dry run writes the files to `inbox/_export_test/` and doesn't move anything. The loop's
   first run sends every table in full; check Catalog → `cat_id` → `bronze` → `landing`.
4. **Code into the workspace.** Either Workspace → Create → Git folder (this repo; a private
   repo needs a GitHub token under Settings → Linked accounts), or import
   `pipeline/bronze_silver.py` and `pipeline/gold.sql` into a workspace folder by hand.
5. **Pipeline.** Jobs & Pipelines → Create → ETL pipeline:
   - Name `cat_id`, serverless, **Triggered** (not Continuous: continuous runs all day and
     uses up the Free Edition quota).
   - Default catalog `cat_id`, default schema `bronze` (tables use full names anyway).
   - Source code: the two files from step 4.
   - Configuration (optional): `cat_id.catalog` = `cat_id`.
   - Start it once by hand. The first update sees every folder in the volume, so run the
     exporter (step 3) before it.
6. **Schedule.** On the pipeline: Schedule → daily, e.g. 04:00 America/Edmonton.

## Checks

```sql
-- Bronze has at least as many rows as Postgres (more: updates are new rows).
SELECT count(*) FROM cat_id.bronze.event;
-- Silver matches Postgres: SELECT count(*) FROM event; on the server.
SELECT count(*) FROM cat_id.silver.event WHERE NOT is_deleted;
-- Undone labels show up as deleted.
SELECT * FROM cat_id.silver.event WHERE is_deleted ORDER BY deleted_at DESC;
```

On the server: `SELECT * FROM export_state ORDER BY table_name;` shows how far each table was
sent, the last file and its row count. A bad token or no internet: the log says which tables
failed, their watermarks don't move, and the exporter retries in 5 minutes.

## When something changes

- **New column in Postgres:** nothing to do. Auto Loader adds it to bronze (the update fails
  once with a schema change and the pipeline restarts it), and it flows to silver. Add it to
  gold by hand if a gold table should use it.
- **New table:** its migration needs the delete trigger (see CLAUDE.md). The exporter sends it
  in full on its next run; the next pipeline update creates its bronze and silver.
- **Renamed or dropped column, changed type:** bronze keeps old files with the old shape.
  Easiest: full refresh of that table's bronze and silver in the pipeline (Databricks rereads
  every file), or delete the table's `export_state` row to resend it.
- **Resend a table:** `DELETE FROM export_state WHERE table_name = 'event';` on the server.
  The next run sends every row again; silver keeps one copy of each.

## Limits

- Silver has the latest version only. Bronze has every *exported* version, so two changes
  to a row within the same hour keep only the second.
- A row created and deleted between two exports arrives only as its deleted copy.
- Free Edition: serverless only, a daily compute quota (going over stops compute until the
  next day), one active pipeline per type. Accounts unused for a long time can be deleted.
