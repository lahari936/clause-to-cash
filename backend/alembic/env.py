from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.db.models import Base

target_metadata = Base.metadata

engine = create_engine(get_settings().database_url)
with engine.connect() as conn:
    context.configure(connection=conn, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
