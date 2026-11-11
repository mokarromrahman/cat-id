"""Initial schema: tables, allowed-value checks, audit trigger, active_vet_visit view, seed rows.

Revision ID: 0001
Revises:
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TABLES = ["app_user", "cat", "event_type", "label", "picture", "event", "vet_visit"]
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
        "app_user", id_column(),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        *audit_columns(),
    )
    op.create_table(
        "cat", id_column(),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("birthday", sa.Date()),
        sa.Column("gotcha_day", sa.Date()),
        *audit_columns(),
        sa.CheckConstraint("name IN ('Litten', 'Shinx')", name="cat_name_allowed"),
    )
    op.create_table(
        "event_type", id_column(),
        sa.Column("type", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        *audit_columns(),
    )
    op.create_table(
        "label", id_column(),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("cat_id", sa.Integer(), sa.ForeignKey("cat.id")),
        *audit_columns(),
        sa.CheckConstraint("name IN ('Litten', 'Shinx', 'neither', 'both')",
                           name="label_name_allowed"),
    )
    op.create_table(
        "picture", id_column(),
        sa.Column("event_timestamp", TZ, nullable=False),
        sa.Column("best_guess", sa.Text()),
        sa.Column("confidence", sa.REAL()),
        sa.Column("predicted_label", sa.Text()),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("final_label_id", sa.Integer(), sa.ForeignKey("label.id")),
        sa.Column("labeled_on", TZ),
        sa.Column("labeled_by", sa.Integer(), sa.ForeignKey("app_user.id")),
        sa.Column("model_version", sa.Text()),
        sa.Column("parent_picture_id", sa.Integer(), sa.ForeignKey("picture.id")),
        *audit_columns(),
        sa.CheckConstraint("source IN ('litterbox', 'identify')", name="picture_source_allowed"),
        sa.CheckConstraint("status IN ('pending', 'labeled', 'archived', 'deleted')",
                           name="picture_status_allowed"),
    )
    op.create_index("ix_picture_event_timestamp", "picture", ["event_timestamp"])
    op.create_index("ix_picture_status", "picture", ["status"])
    # Original photos have unique names (the saved_as name). Crops don't: the label page can
    # write <photo>_crop1.jpg into both data/Litten/ and data/Shinx/.
    op.create_index("uq_picture_original_filename", "picture", ["filename"], unique=True,
                    postgresql_where=sa.text("parent_picture_id IS NULL"))
    op.create_table(
        "event", id_column(),
        sa.Column("event_type_id", sa.Integer(), sa.ForeignKey("event_type.id"), nullable=False),
        sa.Column("cat_id", sa.Integer(), sa.ForeignKey("cat.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("app_user.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("picture_id", sa.Integer(), sa.ForeignKey("picture.id"), unique=True),
        sa.Column("notes", sa.Text()),
        sa.Column("event_timestamp", TZ, nullable=False),
        *audit_columns(),
    )
    op.create_index("ix_event_event_timestamp", "event", ["event_timestamp"])
    op.create_table(
        "vet_visit", id_column(),
        sa.Column("cat_id", sa.Integer(), sa.ForeignKey("cat.id")),
        sa.Column("visit_date", sa.Date(), nullable=False),
        sa.Column("appointment_time", sa.Time()),
        sa.Column("doctor", sa.Text()),
        sa.Column("clinic", sa.Text(), server_default="unknown", nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("reason", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("weight_kg", sa.Numeric(5, 2)),
        sa.Column("cost", sa.Numeric(10, 2)),
        sa.Column("follow_up_date", sa.Date()),
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("deleted_on", TZ),
        *audit_columns(),
        sa.CheckConstraint(
            "cardinality(reason) > 0 AND reason <@ ARRAY['checkup', 'shots', 'emergency', "
            "'food pickup', 'medication pickup', 'other']::text[]",
            name="vet_visit_reason_allowed"),
    )
    op.create_index("ix_vet_visit_visit_date", "vet_visit", ["visit_date"])

    # Audit trigger: keeps modified_on current on every insert and update (including edits in
    # DBeaver or psql), and fills an empty modified_by with the system user. The very first
    # row, the system user itself, points modified_by at its own id.
    op.execute("""
        CREATE FUNCTION set_audit_columns() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.modified_on := now();
            IF NEW.modified_by IS NULL THEN
                NEW.modified_by := (SELECT id FROM app_user WHERE name = 'system');
                IF NEW.modified_by IS NULL AND TG_TABLE_NAME = 'app_user' THEN
                    NEW.modified_by := NEW.id;
                END IF;
            END IF;
            RETURN NEW;
        END
        $$
    """)
    for table in TABLES:
        op.execute(f"CREATE TRIGGER {table}_audit BEFORE INSERT OR UPDATE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION set_audit_columns()")

    # SELECT * is expanded when the view is created: a migration that adds a vet_visit column
    # must recreate this view to include it.
    op.execute("CREATE VIEW active_vet_visit AS "
               "SELECT * FROM vet_visit WHERE deleted_on IS NULL")

    # Seed rows. modified_by is left out, so the trigger records the system user.
    op.execute("INSERT INTO app_user (name) VALUES ('system')")
    op.execute("INSERT INTO app_user (name) VALUES ('pi'), ('Ashley'), ('Mac')")
    op.execute("INSERT INTO cat (name, birthday, gotcha_day) VALUES "
               "('Litten', '2023-06-15', '2023-11-21'), ('Shinx', '2023-06-15', '2023-11-21')")
    op.execute("INSERT INTO event_type (type, name) VALUES "
               "('litterbox', 'Litterbox'), ('cough', 'Cough')")
    op.execute("INSERT INTO label (name, cat_id) VALUES "
               "('Litten', (SELECT id FROM cat WHERE name = 'Litten')), "
               "('Shinx', (SELECT id FROM cat WHERE name = 'Shinx')), "
               "('neither', NULL), ('both', NULL)")


def downgrade():
    op.execute("DROP VIEW active_vet_visit")
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION set_audit_columns()")
