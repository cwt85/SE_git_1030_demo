from alembic import context
from sqlalchemy import create_engine, pool
from DB import Base, database_url

config = context.config


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=database_url(), target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    run(config.attributes["connection"])
else:
    engine = create_engine(database_url(), poolclass=pool.NullPool, connect_args={"connect_timeout": 5})
    with engine.connect() as connection:
        run(connection)
    engine.dispose()
