"""
Pytest configuration with PostgreSQL testcontainers support.

This module provides fixtures for testing with a real PostgreSQL database
using testcontainers. The container is started at module load time (before
test collection) to ensure DATABASE_URL is set before any app imports.
"""

import os
import time

import pytest
from fastapi.testclient import TestClient

# Set environment variables BEFORE importing app
os.environ["GITHUB_CLIENT_ID"] = "test_client_id"
os.environ["GITHUB_CLIENT_SECRET"] = "test_client_secret"
os.environ["GITHUB_REDIRECT_URI"] = "http://localhost:8000/auth/callback"
os.environ["SECRET_KEY"] = "test-secret-key"

# Module-level container reference
_postgres_container = None


def _wait_for_postgres(
    connection_url: str, max_retries: int = 30, delay: float = 0.5
) -> bool:
    """
    Wait for PostgreSQL to be ready to accept connections.

    Args:
        connection_url: SQLAlchemy connection URL
        max_retries: Maximum number of connection attempts
        delay: Delay between retries in seconds

    Returns:
        True if connection succeeded, raises RuntimeError otherwise
    """
    from urllib.parse import urlparse

    import psycopg2

    parsed = urlparse(connection_url)
    dbname = parsed.path.lstrip("/")

    for attempt in range(1, max_retries + 1):
        try:
            conn = psycopg2.connect(
                host=parsed.hostname,
                port=parsed.port,
                user=parsed.username,
                password=parsed.password,
                dbname=dbname,
            )
            conn.close()
            print(f"PostgreSQL ready after {attempt} attempt(s)")
            return True
        except psycopg2.OperationalError:
            if attempt < max_retries:
                time.sleep(delay)
            else:
                raise RuntimeError(
                    f"PostgreSQL not ready after {max_retries} attempts "
                    f"({max_retries * delay:.1f}s)"
                ) from None
    return False


def _setup_postgres():
    """Start PostgreSQL container and wait for it to be ready."""
    global _postgres_container
    from testcontainers.postgres import PostgresContainer

    print("\n[Setup] Starting PostgreSQL container...")
    _postgres_container = PostgresContainer(
        image="postgres:16-alpine",
        username="test",
        password="test",
        dbname="test_db",
    )
    _postgres_container.start()

    connection_url = _postgres_container.get_connection_url()
    print("[Setup] Container started, waiting for PostgreSQL to be ready...")

    _wait_for_postgres(connection_url)

    os.environ["DATABASE_URL"] = connection_url
    print(f"[Setup] DATABASE_URL set to: {connection_url}")


# Start PostgreSQL container at module load time
# This ensures DATABASE_URL is set before any test file imports app modules
_setup_postgres()

# Now import app - this happens AFTER DATABASE_URL is set
from app.main import app  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    """Clean up PostgreSQL container after test session."""
    global _postgres_container
    if _postgres_container is not None:
        try:
            print("\n[Teardown] Stopping PostgreSQL container...")
            _postgres_container.stop()
            print("[Teardown] Container stopped")
        except Exception as e:
            print(f"[Teardown] Error stopping container: {e}")


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def db_session():
    """
    Create a test database session.

    Creates tables before yielding and cleans up after each test.
    """
    from app.database import Base, Problem, get_engine, get_session_local

    engine = get_engine()
    SessionLocal = get_session_local()

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()

    # Seed test problems if they don't exist
    if not session.query(Problem).first():
        test_problems = [
            Problem(
                id="slow-api",
                title="Slow API Performance",
                description="A Spring Boot REST API is experiencing performance issues.",
                difficulty="Medium",
                language="Java",
                template_repo="bpalagi/slow-api-template",
                is_active=True,
            ),
            Problem(
                id="two-sum",
                title="Two Sum",
                description="Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
                difficulty="Easy",
                language="Python",
                template_repo="test/two-sum-template",
                is_active=True,
            ),
        ]
        for p in test_problems:
            session.add(p)
        session.commit()

    try:
        yield session
    finally:
        session.close()
        # Clean up database after test
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)


@pytest.fixture
def authenticated_client(db_session):
    """
    Create a test client with authentication cookie set and a real user in the database.

    Depends on db_session to ensure tables are created.
    """
    from app.database import User
    from app.main import serializer

    # Check if user already exists
    user = db_session.query(User).filter(User.github_id == 12345).first()
    if not user:
        user = User(
            github_id=12345,
            login="testuser",
            name="Test User",
            avatar_url="https://example.com/avatar.jpg",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

    user_id = user.id

    test_client = TestClient(app)
    session_token = serializer.dumps(
        {
            "access_token": "test_token",
            "user_id": user_id,
            "user": {"id": user_id, "login": "testuser", "name": "Test User"},
        }
    )
    test_client.cookies.set("session", str(session_token))
    return test_client
