import os
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
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
    hide_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    completed_problems = relationship("CompletedProblem", back_populates="user")
    user_repos = relationship("UserRepo", back_populates="user")


class CompletedProblem(Base):
    __tablename__ = "completed_problems"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    problem_id = Column(String, index=True)
    completed_at = Column(DateTime, default=lambda: datetime.now(UTC))

    user = relationship("User", back_populates="completed_problems")


class UserRepo(Base):
    """Tracks repos created from templates for each user's codespace sessions."""

    __tablename__ = "user_repos"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    github_username = Column(String, index=True)  # Owner of the created repo
    repo_name = Column(String, index=True)  # Name of the created repo
    codespace_name = Column(String, unique=True, index=True)  # Associated codespace
    problem_id = Column(String, ForeignKey("problems.id"), index=True)
    template_repo = Column(
        String
    )  # Source template repo (e.g., "bpalagi/slow-api-template")
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    user = relationship("User", back_populates="user_repos")
    problem = relationship("Problem")


class Problem(Base):
    """Coding problems available for interview practice."""

    __tablename__ = "problems"

    id = Column(String, primary_key=True, index=True)  # e.g., "slow-api"
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    difficulty = Column(String, nullable=False)  # Easy, Medium, Hard
    language = Column(String, nullable=False)  # Java, Python, etc.
    template_repo = Column(String, nullable=False)  # e.g., "bpalagi/slow-api-template"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class CodespaceToken(Base):
    """Tokens for codespaces to call back to mark problems complete."""

    __tablename__ = "codespace_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    problem_id = Column(String, ForeignKey("problems.id"), index=True, nullable=False)
    codespace_name = Column(String, index=True, nullable=False)
    used = Column(Boolean, default=False)  # Track if token has been used
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime, nullable=False)  # Token expiration time

    user = relationship("User")
    problem = relationship("Problem")


def _run_migrations():
    """Run any pending schema migrations.

    This handles adding new columns to existing tables that SQLAlchemy's
    create_all() won't add (it only creates missing tables, not columns).
    """
    engine = get_engine()

    # List of migrations to apply
    # Each migration is (check_sql, migrate_sql, description)
    migrations = [
        (
            # Check if column exists
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'hide_completed'
            """,
            # Add column if missing
            """
            ALTER TABLE users ADD COLUMN hide_completed BOOLEAN DEFAULT FALSE
            """,
            "Add hide_completed column to users table",
        ),
    ]

    with engine.connect() as conn:
        for check_sql, migrate_sql, description in migrations:
            result = conn.execute(text(check_sql))
            if result.fetchone() is None:
                print(f"[Migration] {description}")
                conn.execute(text(migrate_sql))
                conn.commit()


def init_db():
    """Create all tables, run migrations, and seed initial data"""
    Base.metadata.create_all(bind=get_engine())
    _run_migrations()
    _seed_initial_data()


def _seed_initial_data():
    """Seed the database with initial problem data if empty."""
    session_factory = get_session_local()
    db = session_factory()
    try:
        # Check if we already have problems
        existing = db.query(Problem).first()
        if existing:
            return

        # Seed the slow-api problem
        slow_api_problem = Problem(
            id="slow-api",
            title="Slow API Performance",
            description="A Spring Boot REST API for managing orders is experiencing performance issues. "
            "Investigate and optimize the API to improve response times.",
            difficulty="Medium",
            language="Java",
            template_repo="bpalagi/slow-api-template",
            is_active=True,
        )
        db.add(slow_api_problem)
        db.commit()
        print("[Seed] Added initial problem: slow-api")
    except Exception as e:
        print(f"[Seed] Error seeding data: {e}")
        db.rollback()
    finally:
        db.close()


def get_db():
    """Dependency to get database session"""
    session_factory = get_session_local()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
