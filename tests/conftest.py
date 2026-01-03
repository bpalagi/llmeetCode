import pytest
import os
from fastapi.testclient import TestClient

# Set environment variables BEFORE importing app
os.environ["GITHUB_CLIENT_ID"] = "test_client_id"
os.environ["GITHUB_CLIENT_SECRET"] = "test_client_secret"
os.environ["GITHUB_REDIRECT_URI"] = "http://localhost:8000/auth/callback"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["TEMPLATE_REPO"] = "test/repo"
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

# Now import app after setting environment variables
from app.main import app

@pytest.fixture
def client():
    """Create a test client"""
    return TestClient(app)

@pytest.fixture
def authenticated_client():
    """Create a test client with authentication cookie set"""
    test_client = TestClient(app)
    # Set cookie on client to avoid per-request cookie deprecation
    from app.main import serializer
    session_token = serializer.dumps({"access_token": "test_token", "user_id": 12345, "user": {"id": 12345}})
    test_client.cookies.set("session", session_token)
    return test_client

@pytest.fixture
def db_session():
    """Create a test database session"""
    from app.database import SessionLocal, Base, engine
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        # Clean up database after test
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
