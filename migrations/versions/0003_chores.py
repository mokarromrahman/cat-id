"""Chores: chore, chore_event and chore_event_doer tables, app_user.human, seed rows.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TABLES = ["chore", "chore_event", "chore_event_doer"]
TZ = sa.DateTime(timezone=True)

# (name, label_name, warning_threshold_days), in the order the app lists them.
CHORES = [
    ("vacuum", "Vacuum", 7),
    ("laundry", "Laundry", 7),
    ("sweeping", "Sweeping", 7),
    ("mopping", "Mopping", 14),
    ("bathrooms", "Bathrooms", 7),
    ("bed_sheets", "Bed Sheets", 14),
    ("cat_food_pickup", "Cat Food Pickup", None),
    ("cat_medication_pickup", "Cat Medication Pickup", None),
    ("cat_treat_pickup", "Cat Treat Pickup", None),
]


def audit_columns():
    return [
        sa.Column("created_on", TZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("modified_by", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("modified_on", TZ, server_default=sa.text("now()"), nullable=False),
    ]


def id_column():
    return sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True)


def upgrade():
    # People (who can be picked as having done a chore) vs systems and devices.
    op.add_column("app_user", sa.Column("human", sa.Boolean(), server_default=sa.text("false"),
                                        nullable=False))
    op.execute("UPDATE app_user SET human = true, modified_by = NULL WHERE name IN ('Ashley', 'Mac')")

    op.create_table(
        "chore", id_column(),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("label_name", sa.Text(), nullable=False),
        sa.Column("warning_threshold_days", sa.Integer()),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *audit_columns(),
        sa.CheckConstraint("name ~ '^[a-z0-9_]+$'", name="chore_name_code"),
        sa.CheckConstraint("warning_threshold_days > 0", name="chore_warning_threshold_positive"),
    )
    op.create_table(
        "chore_event", id_column(),
        sa.Column("chore_id", sa.Integer(), sa.ForeignKey("chore.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("event_timestamp", TZ, nullable=False),
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("app_user.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("deleted_on", TZ),
        *audit_columns(),
    )
    op.create_index("ix_chore_event_event_timestamp", "chore_event", ["event_timestamp"])
    op.create_index("ix_chore_event_chore_id_event_timestamp", "chore_event",
                    ["chore_id", "event_timestamp"])
    op.create_table(
        "chore_event_doer", id_column(),
        sa.Column("chore_event_id", sa.Integer(),
                  sa.ForeignKey("chore_event.id", ondelete="CASCADE"), nullable=False),
        sa.Column("app_user_id", sa.Integer(), sa.ForeignKey("app_user.id", ondelete="RESTRICT"),
                  nullable=False),
        *audit_columns(),
        sa.UniqueConstraint("chore_event_id", "app_user_id", name="uq_chore_event_doer"),
    )
    # Same audit trigger function as the other tables (created in 0001).
    for table in TABLES:
        op.execute(f"CREATE TRIGGER {table}_audit BEFORE INSERT OR UPDATE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION set_audit_columns()")

    chore = sa.table("chore", sa.column("name"), sa.column("label_name"),
                     sa.column("warning_threshold_days"))
    op.bulk_insert(chore, [{"name": n, "label_name": l, "warning_threshold_days": d}
                           for n, l, d in CHORES])


def downgrade():
    for table in reversed(TABLES):
        op.drop_table(table)
    op.drop_column("app_user", "human")
