import pytest
import os
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient

# Set environment variables BEFORE importing app
os.environ["GITHUB_CLIENT_ID"] = "test_client_id"
os.environ["GITHUB_CLIENT_SECRET"] = "test_client_secret"
os.environ["GITHUB_REDIRECT_URI"] = "http://localhost:8000/auth/callback"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["TEMPLATE_REPO"] = "test/repo"

# Now import app after setting environment variables
from app.main import app

@pytest.fixture
def client():
    """Create a test client"""
    return TestClient(app)

@pytest.fixture
def mock_httpx():
    """Create a mock for httpx.AsyncClient"""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock()
    mock_client.get = AsyncMock()
    return mock_client

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
def valid_session_token():
    """Create a valid session token for testing"""
    from app.main import serializer
    return serializer.dumps({"access_token": "test_token", "user": {"id": 12345}})
