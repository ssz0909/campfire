from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# Register connector tables with SQLAlchemy metadata without creating a package
# import cycle through app.models.__init__.
import app.connectors.hotel.models  # noqa: F401,E402
import app.models.publishing  # noqa: F401,E402

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=settings.ENVIRONMENT == "development",
)

# Enable UUID extension on first connect (PostgreSQL)
@event.listens_for(engine, "connect")
def on_connect(dbapi_connection, connection_record):  # type: ignore[misc]
    pass  # uuid-ossp must be enabled via migration: CREATE EXTENSION IF NOT EXISTS "uuid-ossp"


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
