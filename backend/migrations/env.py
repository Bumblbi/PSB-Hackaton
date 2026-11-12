from alembic import context
from sqlalchemy import create_engine

from adapters.storage.database import Base
from apps.api.app.settings import Settings


def configure(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


def run():
    connection = context.config.attributes.get("connection")
    if connection is not None:
        configure(connection)
        return
    # Match API configuration, including .env and environment variable precedence.
    url = Settings().database_url
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(url)
        try:
            with engine.connect() as connection:
                configure(connection)
        finally:
            engine.dispose()


run()
