import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from config.settings import settings

# Create engine
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base model
Base = declarative_base()


def get_session():
    """Create a new database session."""
    return SessionLocal()


def close_session(db):
    """Close the given database session."""
    if db:
        db.close()


def init_db():
    """Initialize database tables."""
    # Import all models to ensure they are registered with Base.metadata
    import api.auth.repo
    import api.files.repo

    Base.metadata.create_all(bind=engine)