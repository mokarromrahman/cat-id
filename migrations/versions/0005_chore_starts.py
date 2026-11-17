"""Chore starts: chore_start ("doing it now") and chore_start_doer, chore_event.started_on.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def audit_columns():
    return [
        sa.Column("created_on", TZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("modified_by", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("modified_on", TZ, server_default=sa.text("now()"), nullable=False),
    ]


def upgrade():
    op.create_table(
        "chore_start",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("chore_id", sa.Integer(), sa.ForeignKey("chore.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("started_on", TZ, nullable=False),
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("app_user.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("ended_on", TZ),
        sa.Column("end_reason", sa.Text()),
        sa.Column("chore_event_id", sa.Integer(),
                  sa.ForeignKey("chore_event.id", ondelete="SET NULL")),
        sa.Column("ended_by", sa.Integer(), sa.ForeignKey("app_user.id", ondelete="RESTRICT")),
        sa.Column("discord_message_id", sa.Text()),
        *audit_columns(),
        sa.CheckConstraint("end_reason IN ('done', 'stopped')", name="chore_start_end_reason"),
        sa.CheckConstraint("(ended_on IS NULL) = (end_reason IS NULL)", name="chore_start_ended"),
    )
    op.create_index("ix_chore_start_chore_id_started_on", "chore_start", ["chore_id", "started_on"])
    op.create_index("uq_chore_start_open", "chore_start", ["chore_id"], unique=True,
                    postgresql_where=sa.text("ended_on IS NULL"))
    op.create_table(
        "chore_start_doer",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("chore_start_id", sa.Integer(),
                  sa.ForeignKey("chore_start.id", ondelete="CASCADE"), nullable=False),
        sa.Column("app_user_id", sa.Integer(), sa.ForeignKey("app_user.id", ondelete="RESTRICT"),
                  nullable=False),
        *audit_columns(),
        sa.UniqueConstraint("chore_start_id", "app_user_id", name="uq_chore_start_doer"),
    )
    for table in ("chore_start", "chore_start_doer"):
        op.execute(f"CREATE TRIGGER {table}_audit BEFORE INSERT OR UPDATE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION set_audit_columns()")

    # When the chore was started (from its chore_start, or typed in on the Done sheet); null =
    # not known. The time it took = event_timestamp - started_on.
    op.add_column("chore_event", sa.Column("started_on", TZ))
    op.create_check_constraint("chore_event_started_before_done", "chore_event",
                               "started_on <= event_timestamp")


def downgrade():
    op.drop_constraint("chore_event_started_before_done", "chore_event")
    op.drop_column("chore_event", "started_on")
    op.drop_table("chore_start_doer")
    op.drop_table("chore_start")
