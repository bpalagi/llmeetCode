import os
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker


def get_database_url(url: str | None = None) -> str:
    """Get and normalize the database URL.

    Handles Render's postgres:// URLs by converting them to postgresql://
    which is required by SQLAlchemy.

    Args:
        url: Optional database URL. If not provided, uses DATABASE_URL env var.

    Returns:
        Normalized database URL.

    Raises:
        ValueError: If DATABASE_URL environment variable is not set.
    """
    if url is None:
        url = os.environ.get("DATABASE_URL")
        if url is None:
            raise ValueError(
                "DATABASE_URL environment variable is required. "
                "Set it to a PostgreSQL connection string, e.g., "
                "postgresql://user:password@localhost:5432/dbname"
            )

    # Handle Render's postgres:// URLs (SQLAlchemy requires postgresql://)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url


def create_db_engine(database_url: str):
    """Create a SQLAlchemy engine for PostgreSQL.

    Args:
        database_url: The PostgreSQL database URL to connect to.

    Returns:
        SQLAlchemy engine instance.
    """
    return create_engine(database_url)


# Module-level engine singleton management
_engine = None
_session_local = None


def get_engine():
    """Get or create the database engine (lazy initialization).

    This allows tests to set DATABASE_URL before the engine is created.
    """
    global _engine
    if _engine is None:
        database_url = get_database_url()
        _engine = create_db_engine(database_url)
    return _engine


def get_session_local():
    """Get or create the session factory (lazy initialization)."""
    global _session_local
    if _session_local is None:
        _session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=get_engine()
        )
    return _session_local


def reset_database():
    """Reset the database engine and session. Used for testing."""
    global _engine, _session_local
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_local = None


Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    github_id = Column(Integer, unique=True, index=True)
    login = Column(String, unique=True, index=True)
    name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    completed_problems = relationship("CompletedProblem", back_populates="user")


class CompletedProblem(Base):
    __tablename__ = "completed_problems"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    problem_id = Column(String, index=True)
    completed_at = Column(DateTime, default=lambda: datetime.now(UTC))

    user = relationship("User", back_populates="completed_problems")


def init_db():
    """Create all tables"""
    Base.metadata.create_all(bind=get_engine())


def get_db():
    """Dependency to get database session"""
    session_factory = get_session_local()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
