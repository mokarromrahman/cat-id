"""Bronze and silver for every table export_databricks.py sends (Lakeflow declarative pipeline).

One folder per Postgres table in the landing volume gives, with no per-table code:
  cat_id.bronze.<table>  every exported row version, append-only (Auto Loader), plus
                         _source_file and _ingested_at. Kept forever: the history and the
                         thing to rebuild silver from.
  cat_id.silver.<table>  the latest version of each row (SCD type 1, AUTO CDC keyed on id,
                         ordered by _change_on), with is_deleted / deleted_at for rows removed
                         from Postgres (hard deletes: undo, chore doers). Soft deletes
                         (vet_visit.deleted_on, chore_event.deleted_on) stay ordinary columns.

A new Postgres table shows up by itself once the exporter has sent it (the next update after
that creates its bronze and silver). A new column is added to bronze by Auto Loader (the update
restarts once) and flows to silver.

Pipeline configuration (optional): cat_id.catalog (default cat_id), cat_id.landing
(default /Volumes/<catalog>/bronze/landing).
"""
import os

from pyspark import pipelines as dp
from pyspark.sql import functions as F

CATALOG = spark.conf.get("cat_id.catalog", "cat_id")  # noqa: F821 (spark is provided)
LANDING = spark.conf.get("cat_id.landing", f"/Volumes/{CATALOG}/bronze/landing")  # noqa: F821

# Columns that only matter in bronze.
BRONZE_ONLY = ("_exported_at", "_source_file", "_ingested_at", "_rescued_data")


def landed_tables() -> list[str]:
    """The table folders the exporter has created in the landing volume."""
    return sorted(e.name for e in os.scandir(LANDING)
                  if e.is_dir() and not e.name.startswith(("_", ".")))


def define(table: str):
    bronze = f"{CATALOG}.bronze.{table}"
    silver = f"{CATALOG}.silver.{table}"
    changes = f"{table}_changes"

    @dp.table(name=bronze, comment=f"Every exported version of Postgres {table} rows (append-only).")
    def _bronze():
        return (spark.readStream.format("cloudFiles")  # noqa: F821
                .option("cloudFiles.format", "parquet")
                .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
                .load(f"{LANDING}/{table}/")
                .withColumn("_source_file", F.col("_metadata.file_path"))
                .withColumn("_ingested_at", F.current_timestamp()))

    @dp.temporary_view(name=changes)
    def _changes():
        return (spark.readStream.table(bronze)  # noqa: F821
                .withColumnRenamed("_deleted", "is_deleted")
                .withColumnRenamed("_deleted_at", "deleted_at")
                .drop(*BRONZE_ONLY)
                # The exporter's overlap sends some row versions twice.
                .dropDuplicates(["id", "_change_on", "is_deleted"]))

    dp.create_streaming_table(
        name=silver,
        comment=f"Latest version of each Postgres {table} row; is_deleted = removed from Postgres.")
    dp.create_auto_cdc_flow(
        target=silver,
        source=changes,
        keys=["id"],
        # A delete and an update in the same transaction share _change_on: the delete wins.
        sequence_by=F.struct("_change_on", "is_deleted"),
        except_column_list=["_change_on"],
        stored_as_scd_type=1,
    )


for _table in landed_tables():
    define(_table)
