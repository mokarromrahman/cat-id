"""Databricks export: deleted_row (a copy of every hard-deleted row), export_state (how far
export_databricks.py has sent each table), and a delete trigger on every other table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)

# Every table that existed before this migration. A table added later needs its own
# `CREATE TRIGGER <table>_deleted ...` in its migration (see CLAUDE.md, "Changing the schema").
TABLES = [
    "app_user", "cat", "event_type", "label", "picture", "event", "vet_visit", "location",
    "litterbox_clean_event", "chore", "chore_event", "chore_event_doer", "chore_request",
    "chore_start", "chore_start_doer",
]


def audit_columns():
    return [
        sa.Column("created_on", TZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("modified_by", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("modified_on", TZ, server_default=sa.text("now()"), nullable=False),
    ]


def upgrade():
    op.create_table(
        "deleted_row",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("row_id", sa.Integer(), nullable=False),
        sa.Column("row_data", postgresql.JSONB(), nullable=False),
        sa.Column("deleted_on", TZ, server_default=sa.text("now()"), nullable=False),
        *audit_columns(),
    )
    op.create_index("ix_deleted_row_table_name_modified_on", "deleted_row",
                    ["table_name", "modified_on"])
    op.create_table(
        "export_state",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("table_name", sa.Text(), nullable=False, unique=True),
        sa.Column("exported_through", TZ, nullable=False),
        sa.Column("last_run_on", TZ, nullable=False),
        sa.Column("last_file", sa.Text()),
        sa.Column("last_row_count", sa.Integer(), nullable=False),
        *audit_columns(),
    )
    for table in ("deleted_row", "export_state"):
        op.execute(f"CREATE TRIGGER {table}_audit BEFORE INSERT OR UPDATE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION set_audit_columns()")

    # Copies the whole row (to_jsonb(OLD)) into deleted_row. Fires for cascaded deletes too
    # (chore_event_doer rows go when their chore_event is deleted). The export turns these
    # into rows flagged _deleted in the table's own files.
    op.execute("""
        CREATE FUNCTION record_deleted_row() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            INSERT INTO deleted_row (table_name, row_id, row_data)
            VALUES (TG_TABLE_NAME, OLD.id, to_jsonb(OLD));
            RETURN OLD;
        END
        $$
    """)
    for table in TABLES:
        op.execute(f"CREATE TRIGGER {table}_deleted AFTER DELETE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION record_deleted_row()")


def downgrade():
    for table in TABLES:
        op.execute(f"DROP TRIGGER {table}_deleted ON {table}")
    op.execute("DROP FUNCTION record_deleted_row()")
    op.drop_table("export_state")
    op.drop_table("deleted_row")
