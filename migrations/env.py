from alembic import context

from api.database import Database
from api.models import Base
from api.settings import Settings

config = context.config
target_metadata = Base.metadata


def migrate():
    supplied = config.attributes.get("connection")
    if supplied is not None:
        context.configure(connection=supplied, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    database = Database(Settings.from_env().database_url.get_secret_value())
    try:
        with database.engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        database.close()


migrate()
