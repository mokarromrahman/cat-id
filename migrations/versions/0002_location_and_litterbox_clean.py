"""Litterbox locations and cleans: location and litterbox_clean_event tables, location_id on
picture and event, seed rows, and a backfill of the Pi's photos (it watches the basement box).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TABLES = ["location", "litterbox_clean_event"]
TZ = sa.DateTime(timezone=True)


def audit_columns():
    return [
        sa.Column("created_on", TZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("modified_by", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("modified_on", TZ, server_default=sa.text("now()"), nullable=False),
    ]


def id_column():
    return sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True)


def upgrade():
    op.create_table(
        "location", id_column(),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("label_name", sa.Text(), nullable=False),
        *audit_columns(),
    )
    op.create_table(
        "litterbox_clean_event", id_column(),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("location.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("event_timestamp", TZ, nullable=False),
        sa.Column("server_timestamp", TZ, nullable=False),
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("app_user.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("bag_changed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("notes", sa.Text()),
        *audit_columns(),
    )
    op.create_index("ix_litterbox_clean_event_event_timestamp", "litterbox_clean_event",
                    ["event_timestamp"])
    # Same audit trigger function as the other tables (created in 0001).
    for table in TABLES:
        op.execute(f"CREATE TRIGGER {table}_audit BEFORE INSERT OR UPDATE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION set_audit_columns()")

    op.add_column("picture", sa.Column("location_id", sa.Integer(), sa.ForeignKey("location.id")))
    op.add_column("event", sa.Column("location_id", sa.Integer(), sa.ForeignKey("location.id")))

    op.execute("INSERT INTO location (name, label_name) VALUES "
               "('basement', 'Basement'), ('master_bathroom', 'Master Bathroom')")

    # Backfill: every /litterbox photo so far came from the Pi, which watches the basement
    # box, and so did the litterbox events made by labeling them (crops included). Hand
    # reported visits stay without a location (not known). The trigger records `system`
    # as modified_by for these updates.
    op.execute("UPDATE picture SET location_id = (SELECT id FROM location WHERE name = 'basement'), "
               "modified_by = NULL WHERE source = 'litterbox' AND reporter_id = "
               "(SELECT id FROM app_user WHERE name = 'pi')")
    op.execute("UPDATE event e SET location_id = p.location_id, modified_by = NULL "
               "FROM picture p, event_type t "
               "WHERE e.picture_id = p.id AND p.location_id IS NOT NULL "
               "AND e.event_type_id = t.id AND t.type = 'litterbox'")


def downgrade():
    op.drop_column("event", "location_id")
    op.drop_column("picture", "location_id")
    for table in reversed(TABLES):
        op.drop_table(table)
