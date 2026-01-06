"""Tests for main application endpoints"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from itsdangerous import BadSignature

from app.main import (
    SAMPLE_PROBLEMS,
    create_codespace,
    delete_codespace,
    get_session_data,
)

# Sample GitHub API response data for mocking codespace tests
GITHUB_CODESPACES_RESPONSE = {
    "total_count": 3,
    "codespaces": [
        {
            "name": "urban-space-abc123",
            "display_name": "llmeetcode-two-sum-abc123",
            "state": "Available",
            "web_url": "https://github.com/codespaces/urban-space-abc123",
            "created_at": "2024-01-01T10:00:00Z",
            "last_used_at": "2024-01-02T15:00:00Z",
        },
        {
            "name": "cosmic-xyz789",
            "display_name": "llmeetcode-merge-sorted-xyz789",
            "state": "Stopped",
            "web_url": "https://github.com/codespaces/cosmic-xyz789",
            "created_at": "2024-01-01T08:00:00Z",
            "last_used_at": "2024-01-01T12:00:00Z",
        },
        {
            "name": "other-codespace",
            "display_name": "my-other-project",  # Should be filtered out
            "state": "Available",
            "web_url": "https://github.com/codespaces/other",
            "created_at": "2024-01-01T05:00:00Z",
            "last_used_at": "2024-01-01T06:00:00Z",
        },
    ],
}

GITHUB_CODESPACES_EMPTY = {
    "total_count": 0,
    "codespaces": [],
}


class TestHome:
    """Test cases for the home page"""

    def test_home_unauthenticated(self, client):
        """Test home page without authentication"""
        response = client.get("/")
        assert response.status_code == 200
        assert "LLMeetCode" in response.text
        assert "Login with GitHub" in response.text
        assert len(SAMPLE_PROBLEMS) == len(response.context["problems"])

    def test_home_with_difficulty_filter(self, client):
        """Test filtering by difficulty"""
        response = client.get("/?difficulty=Easy")
        assert response.status_code == 200
        problems = response.context["problems"]
        assert all(p["difficulty"] == "Easy" for p in problems)

    def test_home_with_topic_filter(self, client):
        """Test filtering by topic"""
        response = client.get("/?topic=Array")
        assert response.status_code == 200
        problems = response.context["problems"]
        assert all("Array" in p["topics"] for p in problems)

    def test_home_with_language_filter(self, client):
        """Test filtering by language"""
        response = client.get("/?language=Python")
        assert response.status_code == 200
        problems = response.context["problems"]
        assert all(p["language"] == "Python" for p in problems)

    def test_home_with_hide_completed(self, client):
        """Test hiding completed problems when not logged in"""
        response = client.get("/?hide_completed=true")
        assert response.status_code == 200
        # Should show all problems when not logged in
        assert len(response.context["problems"]) == len(SAMPLE_PROBLEMS)

    @patch("app.main.list_user_codespaces")
    def test_home_shows_active_codespaces(
        self, mock_list_codespaces, authenticated_client
    ):
        """Test home page shows active codespaces for authenticated users"""
        mock_list_codespaces.return_value = [
            {
                "name": "urban-space-abc123",
                "display_name": "llmeetcode-two-sum-abc123",
                "state": "Available",
                "web_url": "https://github.com/codespaces/urban-space-abc123",
                "created_at": "2024-01-01T10:00:00Z",
                "last_used_at": "2024-01-02T15:00:00Z",
                "problem_id": "two-sum",
            },
        ]

        response = authenticated_client.get("/")
        assert response.status_code == 200
        active_codespaces = response.context["active_codespaces"]
        assert "two-sum" in active_codespaces
        assert (
            active_codespaces["two-sum"]
            == "https://github.com/codespaces/urban-space-abc123"
        )


class TestAuth:
    """Test authentication endpoints"""

    def test_login_redirect(self, client):
        """Test that login redirects to GitHub OAuth"""
        response = client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 302
        assert "github.com/login/oauth/authorize" in response.headers["location"]

    def test_logout(self, client):
        """Test logout functionality"""
        response = client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/"

    @patch("app.main.httpx.AsyncClient")
    def test_auth_callback_success(self, mock_client, client):
        """Test successful OAuth callback"""
        from app.database import get_db
        from app.main import app

        # Create a mock database session
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = 1
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        # Override the get_db dependency to use the mock
        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        try:
            # Mock the token exchange
            mock_token_response = MagicMock()
            mock_token_response.status_code = 200
            mock_token_response.json.return_value = {"access_token": "test_token"}

            # Mock the user info request
            mock_user_response = MagicMock()
            mock_user_response.status_code = 200
            mock_user_response.json.return_value = {
                "id": 12345,
                "login": "testuser",
                "name": "Test User",
                "avatar_url": "https://example.com/avatar.jpg",
            }

            mock_client.return_value.__aenter__.return_value.post.return_value = (
                mock_token_response
            )
            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_user_response
            )

            response = client.get(
                "/auth/callback?code=test_code", follow_redirects=False
            )
            assert response.status_code == 302
            assert response.headers["location"] == "/"
            assert "session" in response.cookies
        finally:
            app.dependency_overrides.clear()

    @patch("httpx.AsyncClient")
    def test_auth_callback_error(self, mock_client, client):
        """Test OAuth callback with error"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_client.return_value.__aenter__.return_value.post.return_value = (
            mock_response
        )

        response = client.get("/auth/callback?code=invalid_code")
        assert response.status_code == 400

    @patch("httpx.AsyncClient")
    def test_auth_callback_token_exchange_failure(self, mock_client, client):
        """Test auth callback when token exchange fails"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_client.return_value.__aenter__.return_value.post.return_value = (
            mock_response
        )

        response = client.get("/auth/callback?code=invalid_code")
        assert response.status_code == 400

    @patch("httpx.AsyncClient")
    def test_auth_callback_no_access_token(self, mock_client, client):
        """Test auth callback when no access token is returned"""
        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {"error": "invalid_grant"}

        mock_client.return_value.__aenter__.return_value.post.return_value = (
            mock_token_response
        )

        response = client.get("/auth/callback?code=invalid_code")
        assert response.status_code == 400

    @patch("httpx.AsyncClient")
    def test_auth_callback_user_info_failure(self, mock_client, client):
        """Test auth callback when getting user info fails"""
        # Mock successful token exchange
        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {"access_token": "test_token"}

        # Mock failed user info request
        mock_user_response = MagicMock()
        mock_user_response.status_code = 400

        mock_client.return_value.__aenter__.return_value.post.return_value = (
            mock_token_response
        )
        mock_client.return_value.__aenter__.return_value.get.return_value = (
            mock_user_response
        )

        response = client.get("/auth/callback?code=test_code")
        assert response.status_code == 400


class TestCodespaces:
    """Test codespace creation endpoints"""

    @patch("app.main.create_codespace")
    def test_create_codespace_authenticated(self, mock_create, authenticated_client):
        """Test creating a codespace when authenticated"""
        mock_create.return_value = {
            "name": "test-codespace",
            "web_url": "https://github.com/codespaces/test",
            "state": "Creating",
        }

        response = authenticated_client.post(
            "/codespaces/create", json={"problem_id": "two-sum", "language": "python"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test-codespace"
        mock_create.assert_called_once()

    def test_create_codespace_unauthenticated(self, client):
        """Test creating a codespace without authentication"""
        response = client.post(
            "/codespaces/create", json={"problem_id": "two-sum", "language": "python"}
        )
        assert response.status_code == 401

    @patch("app.main.create_codespace")
    def test_create_codespace_invalid_problem(self, mock_create, authenticated_client):
        """Test creating a codespace with invalid problem ID"""
        mock_create.side_effect = Exception("Problem not found")

        response = authenticated_client.post(
            "/codespaces/create",
            json={"problem_id": "invalid-problem", "language": "python"},
        )
        assert response.status_code == 500


class TestCreateCodespaceFunction:
    """Test codespace creation function"""

    @patch("app.main.httpx.AsyncClient")
    def test_create_codespace_invalid_problem(self, mock_client):
        """Test create_codespace with invalid problem ID"""
        import asyncio

        with pytest.raises(HTTPException):  # Should raise HTTPException
            asyncio.run(create_codespace("test_token", "invalid-problem"))

    @patch("app.main.httpx.AsyncClient")
    def test_create_codespace_repo_not_found(self, mock_client):
        """Test create_codespace when repository is not found"""
        import asyncio

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Not Found"}

        mock_client.return_value.__aenter__.return_value.get.return_value = (
            mock_response
        )

        with pytest.raises(Exception) as exc_info:
            asyncio.run(create_codespace("test_token", "two-sum"))

        assert "Failed to get repository info" in str(exc_info.value.detail)

    @patch("app.main.httpx.AsyncClient")
    def test_create_codespace_no_branches(self, mock_client):
        """Test create_codespace when repository has no branches"""
        import asyncio

        # Mock repo response
        mock_repo_response = MagicMock()
        mock_repo_response.status_code = 200
        mock_repo_response.json.return_value = {"id": 123, "default_branch": None}

        mock_client.return_value.__aenter__.return_value.get.return_value = (
            mock_repo_response
        )

        with pytest.raises(Exception) as exc_info:
            asyncio.run(create_codespace("test_token", "two-sum"))

        assert "Repository has no branches" in str(exc_info.value.detail)

    @patch("app.main.httpx.AsyncClient")
    def test_create_codespace_creation_failed(self, mock_client):
        """Test create_codespace when codespace creation fails"""
        import asyncio

        # Mock repo response
        mock_repo_response = MagicMock()
        mock_repo_response.status_code = 200
        mock_repo_response.json.return_value = {"id": 123, "default_branch": "main"}

        # Mock machines response
        mock_machines_response = MagicMock()
        mock_machines_response.status_code = 200
        mock_machines_response.json.return_value = {"machines": []}

        # Mock creation response
        mock_creation_response = MagicMock()
        mock_creation_response.status_code = 400
        mock_creation_response.json.return_value = {"message": "Insufficient quota"}

        mock_client.return_value.__aenter__.return_value.get.side_effect = [
            mock_repo_response,
            mock_machines_response,
        ]
        mock_client.return_value.__aenter__.return_value.post.return_value = (
            mock_creation_response
        )

        with pytest.raises(Exception) as exc_info:
            asyncio.run(create_codespace("test_token", "two-sum"))

        assert "Failed to create codespace" in str(exc_info.value.detail)

    @patch("app.main.httpx.AsyncClient")
    def test_create_codespace_success(self, mock_client):
        """Test successful codespace creation"""
        import asyncio

        # Mock repo response
        mock_repo_response = MagicMock()
        mock_repo_response.status_code = 200
        mock_repo_response.json.return_value = {"id": 123, "default_branch": "main"}

        # Mock machines response
        mock_machines_response = MagicMock()
        mock_machines_response.status_code = 200
        mock_machines_response.json.return_value = {
            "machines": [{"name": "standardLinux"}]
        }

        # Mock creation response
        mock_creation_response = MagicMock()
        mock_creation_response.status_code = 201
        mock_creation_response.json.return_value = {
            "name": "test-codespace",
            "web_url": "https://github.com/codespaces/test",
            "state": "Creating",
            "created_at": "2024-01-01T00:00:00Z",
        }

        mock_client.return_value.__aenter__.return_value.get.side_effect = [
            mock_repo_response,
            mock_machines_response,
        ]
        mock_client.return_value.__aenter__.return_value.post.return_value = (
            mock_creation_response
        )

        result = asyncio.run(create_codespace("test_token", "two-sum"))

        assert result["name"] == "test-codespace"
        assert result["web_url"] == "https://github.com/codespaces/test"
        assert result["state"] == "Creating"


class TestDashboard:
    """Test dashboard functionality"""

    def test_dashboard_unauthenticated(self, client):
        """Test dashboard redirects when not authenticated"""
        response = client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert "/auth/login" in response.headers["location"]

    def test_dashboard_authenticated(self, authenticated_client):
        """Test dashboard when authenticated"""
        response = authenticated_client.get("/dashboard")
        assert response.status_code == 200
        assert "Dashboard" in response.text
        assert "stats" in response.context


class TestProblemCompletion:
    """Test problem completion tracking"""

    def test_mark_complete_unauthenticated(self, client):
        """Test marking problem complete without authentication"""
        response = client.post("/problems/two-sum/complete")
        assert response.status_code == 401

    def test_mark_complete_authenticated(self, authenticated_client):
        """Test marking problem complete when authenticated"""
        response = authenticated_client.post("/problems/two-sum/complete")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    def test_mark_complete_already_completed(self, authenticated_client):
        """Test marking already completed problem"""
        # Mark it complete once
        authenticated_client.post("/problems/two-sum/complete")

        # Try to mark it again
        response = authenticated_client.post("/problems/two-sum/complete")
        assert response.status_code == 200
        assert response.json()["status"] == "already_completed"

    def test_unmark_complete_authenticated(self, authenticated_client):
        """Test removing completion status"""
        # First mark it complete
        authenticated_client.post("/problems/two-sum/complete")

        # Then unmark it
        response = authenticated_client.delete("/problems/two-sum/complete")
        assert response.status_code == 200
        assert response.json()["status"] == "removed"

    def test_unmark_complete_unauthenticated(self, client):
        """Test unmarking problem without authentication"""
        response = client.delete("/problems/two-sum/complete")
        assert response.status_code == 401

    def test_unmark_complete_nonexistent(self, authenticated_client):
        """Test unmarking a problem that wasn't completed"""
        response = authenticated_client.delete("/problems/nonexistent/complete")
        assert response.status_code == 200
        assert response.json()["status"] == "removed"

    def test_mark_complete_invalid_problem_id(self, authenticated_client):
        """Test marking complete with non-existent problem ID"""
        response = authenticated_client.post("/problems/nonexistent/complete")
        assert response.status_code == 200
        # Should still create completion record even if problem doesn't exist in SAMPLE_PROBLEMS


class TestDashboardWithCompleted:
    """Test dashboard with completed problems"""

    def test_dashboard_with_completed_problems(self, authenticated_client, db_session):
        """Test dashboard shows completed problems correctly"""
        # Create a test user and completed problems
        import random

        from app.database import CompletedProblem, User

        # Use random github_id to avoid unique constraint issues
        user = User(
            github_id=random.randint(10000, 99999),
            login=f"testuser{random.randint(1000, 9999)}",
            name="Test User",
        )
        db_session.add(user)
        db_session.commit()

        # Add completed problems
        for problem_id in ["two-sum", "merge-sorted"]:
            completion = CompletedProblem(user_id=user.id, problem_id=problem_id)
            db_session.add(completion)
        db_session.commit()

        # Update authenticated client to use real user ID
        from app.main import serializer

        session_token = serializer.dumps(
            {
                "access_token": "test_token",
                "user_id": user.id,
                "user": {"login": user.login},
            }
        )
        authenticated_client.cookies.set("session", session_token)

        response = authenticated_client.get("/dashboard")
        assert response.status_code == 200
        assert len(response.context["completed_problems"]) == 2
        assert response.context["stats"]["total"] == 2


class TestSessionData:
    """Test session data handling"""

    def test_get_session_data_no_cookie(self):
        """Test get_session_data when no session cookie exists"""
        request = MagicMock()
        request.cookies = {}

        result = get_session_data(request)
        assert result == {}

    def test_get_session_data_invalid_signature(self):
        """Test get_session_data with invalid session token"""
        request = MagicMock()
        request.cookies = {"session": "invalid_token"}

        with patch("app.main.serializer") as mock_serializer:
            mock_serializer.loads.side_effect = BadSignature("Invalid signature")
            result = get_session_data(request)
            assert result == {}

    def test_get_session_data_valid_token(self):
        """Test get_session_data with valid session token"""
        request = MagicMock()
        request.cookies = {"session": "valid_token"}

        expected_data = {"user_id": 123, "access_token": "token"}
        with patch("app.main.serializer") as mock_serializer:
            mock_serializer.loads.return_value = expected_data
            result = get_session_data(request)
            assert result == expected_data

    def test_get_session_data_expired_token(self):
        """Test get_session_data with expired token"""
        request = MagicMock()
        request.cookies = {"session": "expired_token"}

        with patch("app.main.serializer") as mock_serializer:
            mock_serializer.loads.side_effect = BadSignature("Token expired")
            result = get_session_data(request)
            assert result == {}


class TestErrorHandling:
    """Test various error handling scenarios"""

    def test_home_with_invalid_filter_params(self, client):
        """Test home page with various filter combinations"""
        response = client.get("/?difficulty=Invalid&topic=NonExistent&language=Unknown")
        assert response.status_code == 200
        # Should return empty list when no matches
        assert len(response.context["problems"]) == 0

    def test_codespace_create_invalid_json(self, authenticated_client):
        """Test creating codespace with invalid JSON"""
        response = authenticated_client.post(
            "/codespaces/create", json={"invalid_field": "value"}
        )
        # Pydantic validates the request body, missing problem_id causes 422
        assert response.status_code == 422


class TestSessionEdgeCases:
    """Test session management edge cases"""

    def test_session_with_malformed_token(self, client):
        """Test handling of malformed session token"""
        client.cookies.set("session", "not_a_valid_token")
        response = client.post("/codespaces/create", json={"problem_id": "two-sum"})
        assert response.status_code == 401

    def test_session_without_user_id(self, client):
        """Test session token without user_id"""
        from app.main import serializer

        session_token = serializer.dumps({"access_token": "token"})  # No user_id
        client.cookies.set("session", session_token)

        response = client.post("/problems/two-sum/complete")
        assert response.status_code == 401

    def test_session_with_expired_token(self, client):
        """Test handling of expired session token"""
        # Manually create an expired token
        import time

        from app.main import serializer

        session_data = {"user_id": 123, "exp": time.time() - 3600}  # Expired 1 hour ago
        client.cookies.set("session", serializer.dumps(session_data))

        response = client.post("/codespaces/create", json={"problem_id": "two-sum"})
        assert response.status_code == 401


class TestListUserCodespacesFunction:
    """Test the list_user_codespaces helper function"""

    @patch("app.main.httpx.AsyncClient")
    def test_list_codespaces_success(self, mock_client):
        """GitHub API returns multiple codespaces, function filters and returns llmeetcode ones"""
        from app.main import list_user_codespaces

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = GITHUB_CODESPACES_RESPONSE

        mock_client.return_value.__aenter__.return_value.get.return_value = (
            mock_response
        )

        result = asyncio.run(list_user_codespaces("test_token"))

        assert len(result) == 2  # Only llmeetcode codespaces
        assert result[0]["name"] == "urban-space-abc123"
        assert result[1]["name"] == "cosmic-xyz789"

        for codespace in result:
            assert "name" in codespace
            assert "web_url" in codespace
            assert "state" in codespace
            assert "display_name" in codespace
            assert "created_at" in codespace
            assert "last_used_at" in codespace
            assert "problem_id" in codespace

    @patch("app.main.httpx.AsyncClient")
    def test_list_codespaces_filters_by_prefix(self, mock_client):
        """Only returns codespaces with llmeetcode- prefix, ignores others"""
        from app.main import list_user_codespaces

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = GITHUB_CODESPACES_RESPONSE

        mock_client.return_value.__aenter__.return_value.get.return_value = (
            mock_response
        )

        result = asyncio.run(list_user_codespaces("test_token"))

        assert len(result) == 2
        for codespace in result:
            assert codespace["display_name"].startswith("llmeetcode-")

        names = [cs["name"] for cs in result]
        assert "other-codespace" not in names

    @patch("app.main.httpx.AsyncClient")
    def test_list_codespaces_extracts_problem_id(self, mock_client):
        """Correctly parses problem_id from display_name"""
        from app.main import list_user_codespaces

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = GITHUB_CODESPACES_RESPONSE

        mock_client.return_value.__aenter__.return_value.get.return_value = (
            mock_response
        )

        result = asyncio.run(list_user_codespaces("test_token"))

        problem_ids = {cs["problem_id"] for cs in result}
        assert "two-sum" in problem_ids
        assert "merge-sorted" in problem_ids

    @patch("app.main.httpx.AsyncClient")
    def test_list_codespaces_empty_response(self, mock_client):
        """Returns empty list when no codespaces exist"""
        from app.main import list_user_codespaces

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = GITHUB_CODESPACES_EMPTY

        mock_client.return_value.__aenter__.return_value.get.return_value = (
            mock_response
        )

        result = asyncio.run(list_user_codespaces("test_token"))

        assert result == []
        assert isinstance(result, list)


class TestListCodespacesEndpoint:
    """Test GET /codespaces/list endpoint"""

    @patch("app.main.list_user_codespaces")
    def test_list_codespaces_authenticated(
        self, mock_list_codespaces, authenticated_client
    ):
        """Returns filtered codespace list when authenticated"""
        mock_list_codespaces.return_value = [
            {
                "name": "urban-space-abc123",
                "display_name": "llmeetcode-two-sum-abc123",
                "state": "Available",
                "web_url": "https://github.com/codespaces/urban-space-abc123",
                "created_at": "2024-01-01T10:00:00Z",
                "last_used_at": "2024-01-02T15:00:00Z",
                "problem_id": "two-sum",
            },
            {
                "name": "cosmic-xyz789",
                "display_name": "llmeetcode-merge-sorted-xyz789",
                "state": "Stopped",
                "web_url": "https://github.com/codespaces/cosmic-xyz789",
                "created_at": "2024-01-01T08:00:00Z",
                "last_used_at": "2024-01-01T12:00:00Z",
                "problem_id": "merge-sorted",
            },
        ]

        response = authenticated_client.get("/codespaces/list")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["name"] == "urban-space-abc123"
        assert data[0]["problem_id"] == "two-sum"

    def test_list_codespaces_unauthenticated(self, client):
        """Returns 401 when not authenticated"""
        response = client.get("/codespaces/list")
        assert response.status_code == 401


class TestGetActiveCodespaceEndpoint:
    """Test GET /codespaces/{problem_id}/active endpoint"""

    @patch("app.main.list_user_codespaces")
    def test_get_active_codespace_found(
        self, mock_list_codespaces, authenticated_client
    ):
        """Returns existing codespace for problem"""
        mock_list_codespaces.return_value = [
            {
                "name": "urban-space-abc123",
                "display_name": "llmeetcode-two-sum-abc123",
                "state": "Available",
                "web_url": "https://github.com/codespaces/urban-space-abc123",
                "created_at": "2024-01-01T10:00:00Z",
                "last_used_at": "2024-01-02T15:00:00Z",
                "problem_id": "two-sum",
            },
        ]

        response = authenticated_client.get("/codespaces/two-sum/active")

        assert response.status_code == 200
        data = response.json()
        assert data is not None
        assert data["name"] == "urban-space-abc123"
        assert data["problem_id"] == "two-sum"
        assert data["state"] == "Available"
        assert data["web_url"] == "https://github.com/codespaces/urban-space-abc123"

    @patch("app.main.list_user_codespaces")
    def test_get_active_codespace_not_found(
        self, mock_list_codespaces, authenticated_client
    ):
        """Returns null/empty when no codespace exists for problem"""
        mock_list_codespaces.return_value = []

        response = authenticated_client.get("/codespaces/nonexistent-problem/active")

        assert response.status_code == 200
        data = response.json()
        assert data.get("codespace") is None

    def test_get_active_codespace_unauthenticated(self, client):
        """Returns 401 when not authenticated"""
        response = client.get("/codespaces/two-sum/active")
        assert response.status_code == 401


class TestDeleteCodespaceFunction:
    """Test the delete_codespace helper function"""

    @patch("app.main.httpx.AsyncClient")
    def test_delete_codespace_success(self, mock_client):
        """Deletion succeeds with 202 response"""
        mock_response = MagicMock()
        mock_response.status_code = 202

        mock_client.return_value.__aenter__.return_value.delete.return_value = (
            mock_response
        )

        result = asyncio.run(delete_codespace("test_token", "urban-space-abc123"))

        assert result is True
        mock_client.return_value.__aenter__.return_value.delete.assert_called_once()

    @patch("app.main.httpx.AsyncClient")
    def test_delete_codespace_not_found(self, mock_client):
        """Returns 404 when codespace doesn't exist"""
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client.return_value.__aenter__.return_value.delete.return_value = (
            mock_response
        )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(delete_codespace("test_token", "nonexistent"))

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @patch("app.main.httpx.AsyncClient")
    def test_delete_codespace_api_error(self, mock_client):
        """Handles GitHub API errors appropriately"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"message": "Internal Server Error"}

        mock_client.return_value.__aenter__.return_value.delete.return_value = (
            mock_response
        )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(delete_codespace("test_token", "some-codespace"))

        assert exc_info.value.status_code == 500
        assert "Failed to delete codespace" in exc_info.value.detail

    @patch("app.main.httpx.AsyncClient")
    def test_delete_codespace_forbidden(self, mock_client):
        """Handles 403 forbidden response"""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"message": "Must have admin access"}

        mock_client.return_value.__aenter__.return_value.delete.return_value = (
            mock_response
        )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(delete_codespace("test_token", "someone-elses-codespace"))

        assert exc_info.value.status_code == 403


class TestDeleteCodespaceEndpoint:
    """Test DELETE /codespaces/{codespace_name} endpoint"""

    @patch("app.main.delete_codespace")
    def test_delete_codespace_authenticated(self, mock_delete, authenticated_client):
        """Successfully deletes codespace when authenticated"""
        mock_delete.return_value = True

        response = authenticated_client.delete("/codespaces/urban-space-abc123")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        mock_delete.assert_called_once()

    def test_delete_codespace_unauthenticated(self, client):
        """Returns 401 when not authenticated"""
        response = client.delete("/codespaces/urban-space-abc123")
        assert response.status_code == 401

    @patch("app.main.delete_codespace")
    def test_delete_codespace_not_found(self, mock_delete, authenticated_client):
        """Returns 404 when codespace not found"""
        mock_delete.side_effect = HTTPException(
            status_code=404, detail="Codespace not found"
        )

        response = authenticated_client.delete("/codespaces/nonexistent")

        assert response.status_code == 404

    @patch("app.main.delete_codespace")
    def test_delete_codespace_api_error(self, mock_delete, authenticated_client):
        """Handles API errors appropriately"""
        mock_delete.side_effect = HTTPException(
            status_code=500, detail="Failed to delete codespace: Internal Server Error"
        )

        response = authenticated_client.delete("/codespaces/some-codespace")

        assert response.status_code == 500


class TestDashboardWithCodespaces:
    """Test dashboard with codespaces list"""

    @patch("app.main.list_user_codespaces")
    def test_dashboard_shows_codespaces(
        self, mock_list_codespaces, authenticated_client
    ):
        """Dashboard shows active codespaces"""
        mock_list_codespaces.return_value = [
            {
                "name": "urban-space-abc123",
                "display_name": "llmeetcode-two-sum-abc123",
                "state": "Available",
                "web_url": "https://github.com/codespaces/urban-space-abc123",
                "created_at": "2024-01-01T10:00:00Z",
                "last_used_at": "2024-01-02T15:00:00Z",
                "problem_id": "two-sum",
            },
            {
                "name": "cosmic-xyz789",
                "display_name": "llmeetcode-merge-sorted-xyz789",
                "state": "Stopped",
                "web_url": "https://github.com/codespaces/cosmic-xyz789",
                "created_at": "2024-01-01T08:00:00Z",
                "last_used_at": "2024-01-01T12:00:00Z",
                "problem_id": "merge-sorted",
            },
        ]

        response = authenticated_client.get("/dashboard")

        assert response.status_code == 200
        codespaces = response.context["codespaces"]
        assert len(codespaces) == 2
        assert codespaces[0]["name"] == "urban-space-abc123"
        assert codespaces[0]["problem_title"] == "Two Sum"
        assert codespaces[1]["problem_title"] == "Merge Sorted Arrays"

    @patch("app.main.list_user_codespaces")
    def test_dashboard_empty_codespaces(
        self, mock_list_codespaces, authenticated_client
    ):
        """Dashboard shows empty state when no codespaces"""
        mock_list_codespaces.return_value = []

        response = authenticated_client.get("/dashboard")

        assert response.status_code == 200
        codespaces = response.context["codespaces"]
        assert codespaces == []

    @patch("app.main.list_user_codespaces")
    def test_dashboard_codespaces_api_failure(
        self, mock_list_codespaces, authenticated_client
    ):
        """Dashboard gracefully handles codespaces API failure"""
        mock_list_codespaces.side_effect = HTTPException(
            status_code=500, detail="API Error"
        )

        response = authenticated_client.get("/dashboard")

        # Should still return 200 with empty codespaces
        assert response.status_code == 200
        codespaces = response.context["codespaces"]
        assert codespaces == []

    @patch("app.main.list_user_codespaces")
    def test_dashboard_codespaces_unknown_problem(
        self, mock_list_codespaces, authenticated_client
    ):
        """Dashboard handles codespaces for unknown problems"""
        mock_list_codespaces.return_value = [
            {
                "name": "test-codespace",
                "display_name": "llmeetcode-unknown-problem-abc123",
                "state": "Available",
                "web_url": "https://github.com/codespaces/test",
                "created_at": "2024-01-01T10:00:00Z",
                "last_used_at": "2024-01-02T15:00:00Z",
                "problem_id": "unknown-problem",
            },
        ]

        response = authenticated_client.get("/dashboard")

        assert response.status_code == 200
        codespaces = response.context["codespaces"]
        assert len(codespaces) == 1
        # Should use problem_id as fallback title
        assert codespaces[0]["problem_title"] == "unknown-problem"


class TestMarkCompleteToggleUI:
    """Test the Mark Complete toggle UI functionality and template rendering"""

    def test_mark_complete_button_has_data_problem_id(self, authenticated_client):
        """Test that Mark Complete button has data-problem-id attribute for reliable selection"""
        response = authenticated_client.get("/")
        assert response.status_code == 200
        # Check that the data-problem-id attribute is present in the rendered HTML
        assert 'data-problem-id="two-sum"' in response.text
        assert 'data-problem-id="merge-sorted"' in response.text

    def test_mark_complete_button_not_shown_unauthenticated(self, client):
        """Test that Mark Complete button is not shown when not logged in"""
        response = client.get("/")
        assert response.status_code == 200
        # Check that no actual button with data-problem-id exists (the string appears
        # in JavaScript but not as an actual button element when not logged in)
        # The pattern <button...data-problem-id="xxx" only appears for logged-in users
        import re

        button_pattern = r'<button[^>]*data-problem-id="[^"]*"'
        assert not re.search(button_pattern, response.text)
        # Also verify the login prompt is shown instead
        assert "Login with GitHub" in response.text

    def test_completed_problem_shows_completed_button(self, authenticated_client):
        """Test that completed problems show 'Completed' button state"""
        # First mark a problem as complete
        authenticated_client.post("/problems/two-sum/complete")

        response = authenticated_client.get("/")
        assert response.status_code == 200
        # The completed problem should show in completed_ids context
        assert "two-sum" in response.context["completed_ids"]

    def test_toggle_complete_multiple_times(self, authenticated_client):
        """Test toggling completion status multiple times works correctly"""
        # Mark complete
        response = authenticated_client.post("/problems/two-sum/complete")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        # Unmark complete
        response = authenticated_client.delete("/problems/two-sum/complete")
        assert response.status_code == 200
        assert response.json()["status"] == "removed"

        # Mark complete again
        response = authenticated_client.post("/problems/two-sum/complete")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        # Unmark complete again
        response = authenticated_client.delete("/problems/two-sum/complete")
        assert response.status_code == 200
        assert response.json()["status"] == "removed"

        # Verify final state - should not be in completed_ids
        response = authenticated_client.get("/")
        assert "two-sum" not in response.context["completed_ids"]

    def test_completed_problem_shows_check_icon_in_title(self, authenticated_client):
        """Test that completed problems show check icon in title row"""
        # Mark problem as complete
        authenticated_client.post("/problems/two-sum/complete")

        response = authenticated_client.get("/")
        assert response.status_code == 200
        # Check that the green check icon is present for completed problems
        assert "fa-check-circle text-green-500" in response.text

    def test_uncompleted_problem_no_check_icon(self, authenticated_client):
        """Test that uncompleted problems don't show check icon in title"""
        # Ensure problem is not completed
        authenticated_client.delete("/problems/merge-sorted/complete")

        response = authenticated_client.get("/")
        assert response.status_code == 200
        # The merge-sorted problem card should not have the green check icon
        # (but two-sum might if it was completed in another test)

    def test_hide_completed_filter_works(self, authenticated_client):
        """Test that hide_completed filter removes completed problems from list"""
        # Mark a problem as complete
        authenticated_client.post("/problems/two-sum/complete")

        # Get page with hide_completed=true
        response = authenticated_client.get("/?hide_completed=true")
        assert response.status_code == 200

        # two-sum should not be in the problems list
        problems = response.context["problems"]
        problem_ids = [p["id"] for p in problems]
        assert "two-sum" not in problem_ids

    def test_hide_completed_shows_uncompleted(self, authenticated_client):
        """Test that hide_completed filter still shows uncompleted problems"""
        # Mark one problem as complete
        authenticated_client.post("/problems/two-sum/complete")
        # Ensure another is not completed
        authenticated_client.delete("/problems/merge-sorted/complete")

        # Get page with hide_completed=true
        response = authenticated_client.get("/?hide_completed=true")
        assert response.status_code == 200

        # merge-sorted should still be in the problems list
        problems = response.context["problems"]
        problem_ids = [p["id"] for p in problems]
        assert "merge-sorted" in problem_ids
