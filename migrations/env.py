"""Alembic environment: connects with DATABASE_URL and compares against the models in db.py."""
import os
from logging.config import fileConfig

from alembic import context

import db

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = db.Base.metadata
URL = os.environ["DATABASE_URL"]


def run_migrations_offline():
    """`alembic upgrade head --sql`: print the SQL instead of running it."""
    context.configure(url=URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with db.make_engine(URL).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
