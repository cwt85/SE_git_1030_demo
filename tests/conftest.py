from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from DB import Database, database_url


@pytest.fixture
def database():
    # Schema, migrations and rows live in one rollback-only test transaction.
    engine = create_engine(database_url(), connect_args={"connect_timeout": 5})
    with engine.connect() as connection:
        outer = connection.begin()
        schema = "test_db_" + uuid4().hex
        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            yield Database(connection), connection
        finally:
            outer.rollback()
    engine.dispose()
