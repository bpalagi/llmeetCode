import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

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
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker


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

SLOW_API_DETAIL_SUMMARY = (
    "Enterprise customers report that the Recent Orders dashboard has regressed "
    "from near-instant responses to 3-4 second loads and occasional timeouts. "
    "Investigate the orders API, isolate the bottleneck, and restore healthy "
    "latency without breaking the existing test suite."
)

SLOW_API_DETAIL_OVERVIEW = (
    "Multiple enterprise customers have escalated slow response times when "
    "loading the Recent Orders dashboard. Customer Success flagged the issue "
    "because it is now affecting the largest accounts and interrupting daily "
    "operations.\n\n"
    'Support reports include: "The recent orders page takes forever to load. '
    'It used to be instant." from Foo Corp, "Dashboard performance has degraded '
    'significantly. Sometimes it takes 3-4 seconds to show our orders." from '
    "GlobalTrade Ltd, and \"We're seeing timeouts on the orders API when "
    'fetching recent orders." from MegaRetail Inc.\n\n'
    "Your goal is to identify the impacted endpoint or endpoints, determine the "
    "root cause of the slowdown, and implement a fix that brings response times "
    "back under 100ms. Use the repository README for setup instructions, keep "
    "existing tests green, and document your investigation as you work."
)

SLOW_API_DOMAIN_SPECIALIZATION = "API performance investigation"
MAINTAINER_LOGIN = "bpalagi"

MANAGED_PROBLEM_WALKTHROUGH_TITLE = "Problem walkthrough"
LEGACY_MANAGED_PROBLEM_WALKTHROUGH_TITLES = ("Slow API walkthrough",)
SLOW_API_SOLUTION_VIDEO_TITLE = MANAGED_PROBLEM_WALKTHROUGH_TITLE
SLOW_API_SOLUTION_VIDEO_URL = "https://youtube.com/live/dtjqMNyNPiw?feature=share"


def normalize_youtube_embed_url(video_url: str) -> str:
    """Normalize supported YouTube URLs into a stable embed URL."""
    parsed = urlparse(video_url)
    host = (parsed.netloc or "").lower()
    path = parsed.path.strip("/")

    video_id = ""

    if host in {"youtu.be", "www.youtu.be"}:
        video_id = path.split("/")[0]
    elif host.endswith("youtube.com"):
        if path == "watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif path.startswith("live/") or path.startswith("embed/"):
            video_id = path.split("/", 1)[1]

    if not video_id:
        return video_url

    video_id = video_id.split("?", 1)[0].split("&", 1)[0]
    return f"https://www.youtube.com/embed/{video_id}"


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
    created_problems = relationship(
        "Problem",
        back_populates="creator",
        foreign_keys="Problem.creator_user_id",
    )


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
    detail_summary = Column(Text, nullable=True)
    detail_overview = Column(Text, nullable=True)
    domain_specialization = Column(Text, nullable=True)
    creator_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    difficulty = Column(String, nullable=False)  # Easy, Medium, Hard
    language = Column(String, nullable=False)  # Java, Python, etc.
    template_repo = Column(String, nullable=False)  # e.g., "bpalagi/slow-api-template"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    solution_submissions = relationship(
        "ProblemSolutionSubmission",
        back_populates="problem",
        order_by=lambda: (
            ProblemSolutionSubmission.sort_order.asc(),
            ProblemSolutionSubmission.id.asc(),
        ),
    )
    creator = relationship(
        "User",
        back_populates="created_problems",
        foreign_keys=[creator_user_id],
    )


class ProblemSolutionSubmission(Base):
    """Embeddable solution videos associated with a problem."""

    __tablename__ = "problem_solution_submissions"

    id = Column(Integer, primary_key=True, index=True)
    problem_id = Column(String, ForeignKey("problems.id"), index=True, nullable=False)
    title = Column(String, nullable=False)
    video_url = Column(Text, nullable=False)
    embed_url = Column(Text, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    problem = relationship("Problem", back_populates="solution_submissions")


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


def get_managed_problem_walkthrough_submission(
    db: Session, problem_id: str
) -> ProblemSolutionSubmission | None:
    return (
        db.query(ProblemSolutionSubmission)
        .filter(
            ProblemSolutionSubmission.problem_id == problem_id,
            ProblemSolutionSubmission.title.in_(
                (
                    MANAGED_PROBLEM_WALKTHROUGH_TITLE,
                    *LEGACY_MANAGED_PROBLEM_WALKTHROUGH_TITLES,
                )
            ),
        )
        .order_by(
            ProblemSolutionSubmission.sort_order.asc(),
            ProblemSolutionSubmission.id.asc(),
        )
        .first()
    )


def sync_managed_problem_walkthrough_submission(
    db: Session,
    problem_id: str,
    video_url: str,
    embed_url: str | None,
) -> ProblemSolutionSubmission | None:
    submission = get_managed_problem_walkthrough_submission(db, problem_id)

    if not video_url or not embed_url:
        if submission is not None:
            db.delete(submission)
        return None

    if submission is None:
        submission = ProblemSolutionSubmission(
            problem_id=problem_id,
            title=MANAGED_PROBLEM_WALKTHROUGH_TITLE,
            video_url=video_url,
            embed_url=embed_url,
            sort_order=1,
            is_active=True,
        )
        db.add(submission)
        return submission

    submission_row: Any = submission
    submission_row.video_url = video_url
    submission_row.embed_url = embed_url
    submission_row.title = MANAGED_PROBLEM_WALKTHROUGH_TITLE
    submission_row.sort_order = 1
    submission_row.is_active = True
    return submission


def delete_problem_and_dependencies(db: Session, problem_id: str) -> None:
    db.query(ProblemSolutionSubmission).filter(
        ProblemSolutionSubmission.problem_id == problem_id
    ).delete(synchronize_session=False)
    db.query(UserRepo).filter(UserRepo.problem_id == problem_id).delete(
        synchronize_session=False
    )
    db.query(CodespaceToken).filter(CodespaceToken.problem_id == problem_id).delete(
        synchronize_session=False
    )
    db.query(CompletedProblem).filter(CompletedProblem.problem_id == problem_id).delete(
        synchronize_session=False
    )
    db.query(Problem).filter(Problem.id == problem_id).delete(synchronize_session=False)


def _backfill_problem_ownership(db: Session) -> None:
    maintainer = db.query(User).filter(User.login == MAINTAINER_LOGIN).first()
    if maintainer is None:
        return

    db.query(Problem).filter(Problem.creator_user_id.is_(None)).update(
        {Problem.creator_user_id: maintainer.id},
        synchronize_session=False,
    )


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
        (
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'problems' AND column_name = 'detail_summary'
            """,
            """
            ALTER TABLE problems ADD COLUMN detail_summary TEXT
            """,
            "Add detail_summary column to problems table",
        ),
        (
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'problems' AND column_name = 'detail_overview'
            """,
            """
            ALTER TABLE problems ADD COLUMN detail_overview TEXT
            """,
            "Add detail_overview column to problems table",
        ),
        (
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'problems' AND column_name = 'domain_specialization'
            """,
            """
            ALTER TABLE problems ADD COLUMN domain_specialization TEXT
            """,
            "Add domain_specialization column to problems table",
        ),
        (
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'problems' AND column_name = 'creator_user_id'
            """,
            """
            ALTER TABLE problems
            ADD COLUMN creator_user_id INTEGER REFERENCES users(id)
            """,
            "Add creator_user_id column to problems table",
        ),
        (
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'problem_solution_submissions'
            """,
            """
            CREATE TABLE problem_solution_submissions (
                id SERIAL PRIMARY KEY,
                problem_id VARCHAR NOT NULL REFERENCES problems(id),
                title VARCHAR NOT NULL,
                video_url TEXT NOT NULL,
                embed_url TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
            """,
            "Create problem_solution_submissions table",
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
    """Seed the database with initial problem data and backfill detail content."""
    session_factory = get_session_local()
    db = session_factory()
    try:
        slow_api_problem = db.query(Problem).filter(Problem.id == "slow-api").first()
        if not slow_api_problem:
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
            slow_api_problem_row: Any = slow_api_problem
            slow_api_problem_row.detail_summary = SLOW_API_DETAIL_SUMMARY
            slow_api_problem_row.detail_overview = SLOW_API_DETAIL_OVERVIEW
            slow_api_problem_row.domain_specialization = SLOW_API_DOMAIN_SPECIALIZATION
            db.add(slow_api_problem)
            db.flush()
            print("[Seed] Added initial problem: slow-api")
        else:
            slow_api_problem_row: Any = slow_api_problem
            if not getattr(slow_api_problem, "detail_summary", None):
                slow_api_problem_row.detail_summary = SLOW_API_DETAIL_SUMMARY
            if not getattr(slow_api_problem, "detail_overview", None):
                slow_api_problem_row.detail_overview = SLOW_API_DETAIL_OVERVIEW
            if not getattr(slow_api_problem, "domain_specialization", None):
                slow_api_problem_row.domain_specialization = (
                    SLOW_API_DOMAIN_SPECIALIZATION
                )

        existing_submission = (
            db.query(ProblemSolutionSubmission)
            .filter(
                ProblemSolutionSubmission.problem_id == "slow-api",
                ProblemSolutionSubmission.video_url == SLOW_API_SOLUTION_VIDEO_URL,
            )
            .first()
        )
        if not existing_submission:
            submission = ProblemSolutionSubmission(
                problem_id="slow-api",
                title=SLOW_API_SOLUTION_VIDEO_TITLE,
                video_url=SLOW_API_SOLUTION_VIDEO_URL,
                sort_order=1,
                is_active=True,
            )
            submission_row: Any = submission
            submission_row.embed_url = normalize_youtube_embed_url(
                SLOW_API_SOLUTION_VIDEO_URL
            )
            db.add(submission)
            print("[Seed] Added slow-api solution submission")
        elif not getattr(existing_submission, "embed_url", None):
            existing_submission_row: Any = existing_submission
            existing_submission_row.embed_url = normalize_youtube_embed_url(
                str(existing_submission.video_url)
            )

        _backfill_problem_ownership(db)
        db.commit()
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
