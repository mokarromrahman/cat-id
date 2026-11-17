"""Chore requests: chore_request ("this chore needs doing"), at most one open per chore.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)
OPEN = "done_on IS NULL AND cancelled_on IS NULL"


def upgrade():
    op.create_table(
        "chore_request",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("chore_id", sa.Integer(), sa.ForeignKey("chore.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("requested_on", TZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("app_user.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("quantity", sa.Numeric(10, 2)),
        sa.Column("unit", sa.Text()),
        sa.Column("needed_by", sa.Date()),
        sa.Column("done_on", TZ),
        sa.Column("chore_event_id", sa.Integer(),
                  sa.ForeignKey("chore_event.id", ondelete="SET NULL")),
        sa.Column("cancelled_on", TZ),
        sa.Column("closed_by", sa.Integer(), sa.ForeignKey("app_user.id", ondelete="RESTRICT")),
        sa.Column("discord_message_id", sa.Text()),
        sa.Column("created_on", TZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("modified_by", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("modified_on", TZ, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name="chore_request_quantity_positive"),
        sa.CheckConstraint("done_on IS NULL OR cancelled_on IS NULL",
                           name="chore_request_done_or_cancelled"),
    )
    op.create_index("ix_chore_request_chore_id_requested_on", "chore_request",
                    ["chore_id", "requested_on"])
    op.create_index("uq_chore_request_open", "chore_request", ["chore_id"], unique=True,
                    postgresql_where=sa.text(OPEN))
    # Same audit trigger function as the other tables (created in 0001).
    op.execute("CREATE TRIGGER chore_request_audit BEFORE INSERT OR UPDATE ON chore_request "
               "FOR EACH ROW EXECUTE FUNCTION set_audit_columns()")


def downgrade():
    op.drop_table("chore_request")
