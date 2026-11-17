"""Who cleaned a litterbox: litterbox_clean_event.cleaned_by (a person, separate from the
reporter who sent it). Existing rows get their reporter when that's a person.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("litterbox_clean_event", sa.Column(
        "cleaned_by", sa.Integer(), sa.ForeignKey("app_user.id", ondelete="RESTRICT")))
    # Until now the sender was the one who cleaned it. (The audit trigger stamps
    # modified_on on these rows, which is right: they changed.)
    op.execute("""
        UPDATE litterbox_clean_event e SET cleaned_by = e.reporter_id
        FROM app_user u WHERE u.id = e.reporter_id AND u.human
    """)


def downgrade():
    op.drop_column("litterbox_clean_event", "cleaned_by")
