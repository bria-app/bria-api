from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings

# Create synchronous engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # Check connection validity before using from pool
    echo=settings.app_debug
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Generator[Session, None, None]:
    """Per-request transactional session.

    Commits once if the request handler succeeds; rolls back on any exception
    (including domain errors). Repositories should ``flush()`` (not commit), so a
    use case that performs several writes stays atomic within one transaction.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
