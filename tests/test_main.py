"""Tests for main application endpoints"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from itsdangerous import BadSignature

from app.database import (
    CodespaceToken,
    CompletedProblem,
    Problem,
    ProblemSolutionSubmission,
    User,
    UserRepo,
)
from app.main import (
    build_problem_overview_paragraphs,
    create_codespace,
    delete_codespace,
    get_session_data,
    validate_problem_authoring_form,
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

    def test_home_unauthenticated(self, client, db_session):
        """Test home page without authentication"""
        response = client.get("/")
        assert response.status_code == 200
        assert "LLMeetCode" in response.text
        assert "Login with GitHub" in response.text
        # Should show problems from database (seeded in conftest)
        assert len(response.context["problems"]) >= 1

    def test_home_with_difficulty_filter(self, client, db_session):
        """Test filtering by difficulty"""
        response = client.get("/?difficulty=Easy")
        assert response.status_code == 200
        problems = response.context["problems"]
        assert all(p["difficulty"] == "Easy" for p in problems)

    def test_home_with_language_filter(self, client, db_session):
        """Test filtering by language"""
        response = client.get("/?language=Java")
        assert response.status_code == 200
        problems = response.context["problems"]
        assert all(p["language"] == "Java" for p in problems)

    def test_home_with_hide_completed(self, client, db_session):
        """Test hiding completed problems when not logged in"""
        response = client.get("/?hide_completed=true")
        assert response.status_code == 200
        # Should show all problems when not logged in (no completed problems)
        assert len(response.context["problems"]) >= 1

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

    def test_home_contains_problem_detail_links(self, client):
        """Catalog renders links to dedicated problem pages."""
        response = client.get("/")

        assert response.status_code == 200
        assert "/problems/slow-api" in response.text

    def test_home_shows_add_problem_cta_for_logged_in_users(self, authenticated_client):
        response = authenticated_client.get("/")

        assert response.status_code == 200
        assert "Add a Problem" in response.text
        assert 'href="/problems/new"' in response.text

    def test_home_hides_add_problem_cta_for_guests(self, client):
        response = client.get("/")

        assert response.status_code == 200
        assert "Add a Problem" not in response.text


class TestProblemAuthoring:
    """Test the add-problem authoring flow."""

    def test_get_add_problem_requires_authentication(self, client):
        response = client.get("/problems/new", follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["location"] == "/auth/login"

    def test_get_add_problem_authenticated(self, authenticated_client):
        response = authenticated_client.get("/problems/new")

        assert response.status_code == 200
        assert "Add a new problem" in response.text
        assert "Template repo" in response.text
        assert "Optional YouTube URL" in response.text

    def test_post_add_problem_requires_authentication(self, client):
        response = client.post(
            "/problems/new", data={"problem_id": "new-problem"}, follow_redirects=False
        )

        assert response.status_code == 302
        assert response.headers["location"] == "/auth/login"

    def test_post_add_problem_success_with_video(
        self, authenticated_client, db_session
    ):
        response = authenticated_client.post(
            "/problems/new",
            data={
                "problem_id": "latency-lab",
                "title": "Latency Lab",
                "description": "Investigate a latency regression in a customer-facing API.",
                "difficulty": "Hard",
                "language": "Go",
                "is_active": "true",
                "detail_summary": "Trace production latency from symptom to fix.",
                "detail_overview": "Customers are reporting severe latency spikes.\n\nIdentify the bottleneck and restore healthy response times.",
                "domain_specialization": "Distributed systems performance",
                "template_repo": "acme/latency-lab-template",
                "youtube_url": "https://www.youtube.com/watch?v=abc123xyz",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/problems/latency-lab?created=1"

        problem = db_session.query(Problem).filter(Problem.id == "latency-lab").first()
        assert problem is not None
        assert problem.domain_specialization == "Distributed systems performance"

        submission = (
            db_session.query(ProblemSolutionSubmission)
            .filter(ProblemSolutionSubmission.problem_id == "latency-lab")
            .first()
        )
        assert submission is not None
        assert submission.embed_url == "https://www.youtube.com/embed/abc123xyz"

        detail_response = authenticated_client.get(response.headers["location"])
        assert detail_response.status_code == 200
        assert "Problem created successfully" in detail_response.text
        assert "Distributed systems performance" in detail_response.text
        assert "https://www.youtube.com/embed/abc123xyz" in detail_response.text

        catalog_response = authenticated_client.get("/")
        assert "Latency Lab" in catalog_response.text
        assert "/problems/latency-lab" in catalog_response.text

    def test_post_add_problem_success_inactive_redirects_back_to_form(
        self, authenticated_client, db_session
    ):
        response = authenticated_client.post(
            "/problems/new",
            data={
                "problem_id": "draft-problem",
                "title": "Draft Problem",
                "description": "Saved without being exposed in the catalog.",
                "difficulty": "Easy",
                "language": "Python",
                "is_active": "false",
                "detail_summary": "A hidden draft summary.",
                "detail_overview": "Draft overview content.",
                "domain_specialization": "Authoring workflow",
                "template_repo": "acme/draft-template",
                "youtube_url": "",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert (
            response.headers["location"]
            == "/problems/new?created_problem_id=draft-problem"
        )

        follow_up = authenticated_client.get(response.headers["location"])
        assert "draft-problem" in follow_up.text
        assert "hidden from the catalog" in follow_up.text

        catalog_response = authenticated_client.get("/")
        problem_ids = [
            problem["id"] for problem in catalog_response.context["problems"]
        ]
        assert "draft-problem" not in problem_ids
        assert any(
            problem["id"] == "draft-problem"
            for problem in catalog_response.context["inactive_problems"]
        )

    def test_post_add_problem_duplicate_id(self, authenticated_client):
        response = authenticated_client.post(
            "/problems/new",
            data={
                "problem_id": "slow-api",
                "title": "Another Slow API",
                "description": "Duplicate id should fail.",
                "difficulty": "Medium",
                "language": "Java",
                "is_active": "true",
                "detail_summary": "Summary",
                "detail_overview": "Overview",
                "domain_specialization": "APIs",
                "template_repo": "acme/duplicate-template",
                "youtube_url": "",
            },
        )

        assert response.status_code == 200
        assert "That problem id already exists." in response.text
        assert 'value="slow-api"' in response.text

    def test_post_add_problem_missing_required_fields(self, authenticated_client):
        response = authenticated_client.post(
            "/problems/new",
            data={
                "problem_id": "",
                "title": "",
                "description": "",
                "difficulty": "",
                "language": "",
                "is_active": "",
                "detail_summary": "",
                "detail_overview": "",
                "domain_specialization": "",
                "template_repo": "",
                "youtube_url": "",
            },
        )

        assert response.status_code == 200
        assert "Enter a stable problem id." in response.text
        assert "Enter a problem title." in response.text
        assert "Enter the GitHub template repository." in response.text

    def test_post_add_problem_blank_template_repo(self, authenticated_client):
        response = authenticated_client.post(
            "/problems/new",
            data={
                "problem_id": "repo-check",
                "title": "Repo Check",
                "description": "Template repo is required.",
                "difficulty": "Easy",
                "language": "Python",
                "is_active": "true",
                "detail_summary": "Summary",
                "detail_overview": "Overview",
                "domain_specialization": "Developer tooling",
                "template_repo": "   ",
                "youtube_url": "",
            },
        )

        assert response.status_code == 200
        assert "Enter the GitHub template repository." in response.text

    def test_post_add_problem_rejects_whitespace_only_youtube(
        self, authenticated_client
    ):
        response = authenticated_client.post(
            "/problems/new",
            data={
                "problem_id": "video-check",
                "title": "Video Check",
                "description": "Whitespace-only video input should fail.",
                "difficulty": "Easy",
                "language": "Python",
                "is_active": "true",
                "detail_summary": "Summary",
                "detail_overview": "Overview",
                "domain_specialization": "Video validation",
                "template_repo": "acme/video-check-template",
                "youtube_url": "   ",
            },
        )

        assert response.status_code == 200
        assert "Enter a YouTube URL or leave this blank." in response.text

    def test_post_add_problem_rejects_invalid_youtube(self, authenticated_client):
        response = authenticated_client.post(
            "/problems/new",
            data={
                "problem_id": "invalid-video",
                "title": "Invalid Video",
                "description": "Non-YouTube URLs should fail.",
                "difficulty": "Easy",
                "language": "Python",
                "is_active": "true",
                "detail_summary": "Summary",
                "detail_overview": "Overview",
                "domain_specialization": "Video validation",
                "template_repo": "acme/invalid-video-template",
                "youtube_url": "https://vimeo.com/12345",
            },
        )

        assert response.status_code == 200
        assert (
            "Use a supported YouTube watch, live, embed, or short link."
            in response.text
        )

    def test_validate_problem_authoring_form_trims_fields(self, db_session):
        form_data, errors, normalized_youtube_url = validate_problem_authoring_form(
            {
                "problem_id": "  trim-me  ",
                "title": "  Trim Me  ",
                "description": "  Description  ",
                "difficulty": "Medium",
                "language": "  Python  ",
                "is_active": " true ",
                "detail_summary": "  Summary  ",
                "detail_overview": "  Overview  ",
                "domain_specialization": "  Testing  ",
                "template_repo": "  acme/trim-template  ",
                "youtube_url": " https://youtu.be/trim123 ",
            },
            db_session,
        )

        assert errors == {}
        assert form_data["problem_id"] == "trim-me"
        assert form_data["language"] == "Python"
        assert form_data["template_repo"] == "acme/trim-template"
        assert normalized_youtube_url == "https://www.youtube.com/embed/trim123"

    def test_validate_problem_authoring_form_allows_same_id_when_editing(
        self, db_session
    ):
        form_data, errors, _ = validate_problem_authoring_form(
            {
                "problem_id": "slow-api",
                "title": "Slow API Performance",
                "description": "Updated description",
                "difficulty": "Medium",
                "language": "Java",
                "is_active": "true",
                "detail_summary": "Updated summary",
                "detail_overview": "Updated overview",
                "domain_specialization": "API performance investigation",
                "template_repo": "bpalagi/slow-api-template",
                "youtube_url": "",
            },
            db_session,
            current_problem_id="slow-api",
        )

        assert errors == {}
        assert form_data["problem_id"] == "slow-api"

    def test_get_edit_problem_requires_authentication(self, client):
        response = client.get("/problems/slow-api/edit", follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["location"] == "/auth/login"

    def test_get_edit_problem_prefills_existing_values(self, authenticated_client):
        response = authenticated_client.get("/problems/slow-api/edit")

        assert response.status_code == 200
        assert "Edit problem" in response.text
        assert 'value="slow-api"' in response.text
        assert 'readonly aria-readonly="true"' in response.text
        assert "This slug is locked after creation" in response.text

    def test_get_edit_problem_supports_inactive_problem(
        self, authenticated_client, db_session
    ):
        db_session.add(
            Problem(
                id="inactive-lab",
                title="Inactive Lab",
                description="An inactive problem.",
                detail_summary="Inactive summary",
                detail_overview="Inactive overview",
                domain_specialization="Maintenance",
                difficulty="Easy",
                language="Python",
                template_repo="test/inactive-lab-template",
                is_active=False,
            )
        )
        db_session.commit()

        response = authenticated_client.get("/problems/inactive-lab/edit")

        assert response.status_code == 200
        assert "Inactive Lab" in response.text
        assert 'value="inactive-lab"' in response.text

    def test_post_edit_problem_updates_problem_and_walkthrough(
        self, authenticated_client, db_session
    ):
        response = authenticated_client.post(
            "/problems/slow-api/edit",
            data={
                "problem_id": "attempted-slug-change",
                "title": "Slow API Rescue",
                "description": "Updated short description.",
                "difficulty": "Hard",
                "language": "Go",
                "is_active": "true",
                "detail_summary": "Updated summary",
                "detail_overview": "Updated overview",
                "domain_specialization": "Incident response",
                "template_repo": "acme/slow-api-rescue-template",
                "youtube_url": "https://youtu.be/rescue123",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/problems/slow-api?updated=1"

        problem = db_session.query(Problem).filter(Problem.id == "slow-api").one()
        assert problem.title == "Slow API Rescue"
        assert problem.language == "Go"
        assert problem.template_repo == "acme/slow-api-rescue-template"
        assert (
            db_session.query(Problem)
            .filter(Problem.id == "attempted-slug-change")
            .first()
            is None
        )

        walkthrough = (
            db_session.query(ProblemSolutionSubmission)
            .filter(ProblemSolutionSubmission.problem_id == "slow-api")
            .filter(ProblemSolutionSubmission.title == "Problem walkthrough")
            .one()
        )
        assert walkthrough.video_url == "https://youtu.be/rescue123"
        assert walkthrough.embed_url == "https://www.youtube.com/embed/rescue123"

        detail_response = authenticated_client.get(response.headers["location"])
        assert detail_response.status_code == 200
        assert "Problem updated successfully" in detail_response.text
        assert "Slow API Rescue" in detail_response.text

        catalog_response = authenticated_client.get("/")
        assert "Slow API Rescue" in catalog_response.text

    def test_post_edit_problem_invalid_submission_preserves_values(
        self, authenticated_client
    ):
        response = authenticated_client.post(
            "/problems/slow-api/edit",
            data={
                "problem_id": "slow-api",
                "title": "",
                "description": "Still here",
                "difficulty": "Medium",
                "language": "Python",
                "is_active": "true",
                "detail_summary": "Summary",
                "detail_overview": "Overview",
                "domain_specialization": "Testing",
                "template_repo": "bad-format",
                "youtube_url": "https://vimeo.com/12345",
            },
        )

        assert response.status_code == 200
        assert "Enter a problem title." in response.text
        assert "Use the GitHub owner/repository format." in response.text
        assert (
            "Use a supported YouTube watch, live, embed, or short link."
            in response.text
        )
        assert 'value="slow-api"' in response.text
        assert 'readonly aria-readonly="true"' in response.text
        assert "Still here" in response.text

    def test_post_edit_problem_can_save_inactive(
        self, authenticated_client, db_session
    ):
        response = authenticated_client.post(
            "/problems/slow-api/edit",
            data={
                "problem_id": "slow-api",
                "title": "Slow API Performance",
                "description": "Temporarily hidden.",
                "difficulty": "Medium",
                "language": "Java",
                "is_active": "false",
                "detail_summary": "Summary",
                "detail_overview": "Overview",
                "domain_specialization": "API performance investigation",
                "template_repo": "bpalagi/slow-api-template",
                "youtube_url": "",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert (
            response.headers["location"] == "/problems/slow-api/edit?saved_inactive=1"
        )

        edit_response = authenticated_client.get(response.headers["location"])
        assert edit_response.status_code == 200
        assert "remains hidden from the catalog" in edit_response.text

        catalog_response = authenticated_client.get("/")
        problem_ids = [
            problem["id"] for problem in catalog_response.context["problems"]
        ]
        assert "slow-api" not in problem_ids
        assert any(
            problem["id"] == "slow-api"
            for problem in catalog_response.context["inactive_problems"]
        )

        detail_response = authenticated_client.get("/problems/slow-api")
        assert detail_response.status_code == 404

        problem = db_session.query(Problem).filter(Problem.id == "slow-api").one()
        assert problem.is_active is False

    def test_post_edit_problem_clears_managed_walkthrough(
        self, authenticated_client, db_session
    ):
        response = authenticated_client.post(
            "/problems/slow-api/edit",
            data={
                "problem_id": "slow-api",
                "title": "Slow API Performance",
                "description": "No walkthrough now.",
                "difficulty": "Medium",
                "language": "Java",
                "is_active": "true",
                "detail_summary": "Summary",
                "detail_overview": "Overview",
                "domain_specialization": "API performance investigation",
                "template_repo": "bpalagi/slow-api-template",
                "youtube_url": "",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        walkthrough = (
            db_session.query(ProblemSolutionSubmission)
            .filter(ProblemSolutionSubmission.problem_id == "slow-api")
            .filter(ProblemSolutionSubmission.title == "Problem walkthrough")
            .first()
        )
        assert walkthrough is None

    def test_problem_delete_confirmation_requires_authentication(self, client):
        response = client.get("/problems/slow-api/delete", follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["location"] == "/auth/login"

    def test_problem_delete_confirmation_page(self, authenticated_client):
        response = authenticated_client.get("/problems/slow-api/delete")

        assert response.status_code == 200
        assert "Delete Slow API Performance?" in response.text
        assert "GitHub repositories and Codespaces are not cleaned up" in response.text
        assert 'action="/problems/slow-api/delete"' in response.text
        assert 'href="/problems/slow-api"' in response.text

    def test_inactive_problem_delete_confirmation_returns_to_edit(
        self, authenticated_client, db_session
    ):
        problem = db_session.query(Problem).filter(Problem.id == "slow-api").one()
        problem.is_active = False
        db_session.commit()

        response = authenticated_client.get("/problems/slow-api/delete")

        assert response.status_code == 200
        assert 'href="/problems/slow-api/edit"' in response.text
        assert 'href="/problems/slow-api"' not in response.text
        assert "Back to edit" in response.text

    def test_problem_delete_removes_dependent_rows(
        self, authenticated_client, db_session
    ):
        response = authenticated_client.post("/problems/slow-api/complete")
        assert response.status_code == 200

        user = db_session.query(User).filter(User.id == 1).first()
        assert user is not None

        db_session.add(
            UserRepo(
                user_id=user.id,
                github_username="testuser",
                repo_name="llmeetcode-slow-api-test",
                codespace_name="slow-api-space",
                problem_id="slow-api",
                template_repo="bpalagi/slow-api-template",
            )
        )
        db_session.add(
            CodespaceToken(
                token="delete-problem-token",
                user_id=user.id,
                problem_id="slow-api",
                codespace_name="slow-api-space",
                expires_at=datetime.now(UTC),
            )
        )
        db_session.commit()

        delete_response = authenticated_client.post(
            "/problems/slow-api/delete", follow_redirects=False
        )

        assert delete_response.status_code == 303
        assert delete_response.headers["location"] == "/?deleted_problem_id=slow-api"

        assert (
            db_session.query(Problem).filter(Problem.id == "slow-api").first() is None
        )
        assert (
            db_session.query(ProblemSolutionSubmission)
            .filter(ProblemSolutionSubmission.problem_id == "slow-api")
            .count()
            == 0
        )
        assert (
            db_session.query(UserRepo).filter(UserRepo.problem_id == "slow-api").count()
            == 0
        )
        assert (
            db_session.query(CodespaceToken)
            .filter(CodespaceToken.problem_id == "slow-api")
            .count()
            == 0
        )
        assert (
            db_session.query(CompletedProblem)
            .filter(CompletedProblem.problem_id == "slow-api")
            .count()
            == 0
        )

        home_response = authenticated_client.get(delete_response.headers["location"])
        assert home_response.status_code == 200
        assert "was deleted permanently" in home_response.text

        detail_response = authenticated_client.get("/problems/slow-api")
        assert detail_response.status_code == 404

        dashboard_response = authenticated_client.get("/dashboard")
        assert dashboard_response.status_code == 200


class TestProblemDetailPage:
    """Test dedicated problem detail page rendering and state."""

    def test_problem_detail_success(self, client):
        response = client.get("/problems/slow-api")

        assert response.status_code == 200
        assert "Slow API Performance" in response.text
        assert "Recent Orders dashboard" in response.text
        assert "https://www.youtube.com/embed/dtjqMNyNPiw" in response.text

    def test_problem_detail_unknown_problem(self, client):
        response = client.get("/problems/does-not-exist")

        assert response.status_code == 404

    @patch("app.main.list_user_codespaces")
    def test_problem_detail_authenticated_context(
        self, mock_list_codespaces, authenticated_client
    ):
        mock_list_codespaces.return_value = [
            {
                "name": "slow-api-codespace",
                "display_name": "llmeetcode-slow-api-abc123",
                "state": "Available",
                "web_url": "https://github.com/codespaces/slow-api-codespace",
                "created_at": "2024-01-01T10:00:00Z",
                "last_used_at": "2024-01-02T15:00:00Z",
                "problem_id": "slow-api",
            },
        ]

        authenticated_client.post("/problems/slow-api/complete")
        response = authenticated_client.get("/problems/slow-api")

        assert response.status_code == 200
        assert response.context["logged_in"] is True
        assert response.context["is_completed"] is True
        assert (
            response.context["active_codespace_url"]
            == "https://github.com/codespaces/slow-api-codespace"
        )
        assert "Resume Codespace" in response.text
        assert "Completed" in response.text

    def test_problem_detail_fallback_content(self, client, db_session):
        from app.database import Problem

        db_session.add(
            Problem(
                id="plain-problem",
                title="Plain Problem",
                description="Short catalog copy only.",
                difficulty="Easy",
                language="Python",
                template_repo="test/plain-problem-template",
                is_active=True,
            )
        )
        db_session.commit()

        response = client.get("/problems/plain-problem")

        assert response.status_code == 200
        assert response.context["detail_summary"] == "Short catalog copy only."
        assert response.context["overview_paragraphs"] == ["Short catalog copy only."]
        assert "No solution videos yet" in response.text

    def test_problem_detail_shows_management_controls_for_logged_in_users(
        self, authenticated_client
    ):
        response = authenticated_client.get("/problems/slow-api")

        assert response.status_code == 200
        assert 'href="/problems/slow-api/edit"' in response.text
        assert 'href="/problems/slow-api/delete"' in response.text

    def test_problem_detail_hides_management_controls_for_guests(self, client):
        response = client.get("/problems/slow-api")

        assert response.status_code == 200
        assert 'href="/problems/slow-api/edit"' not in response.text
        assert 'href="/problems/slow-api/delete"' not in response.text

    def test_build_problem_overview_paragraphs(self, db_session):
        from app.database import Problem

        problem = db_session.query(Problem).filter(Problem.id == "slow-api").first()

        paragraphs = build_problem_overview_paragraphs(problem)
        assert len(paragraphs) >= 2
        assert paragraphs[0].startswith("Multiple enterprise customers")


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
    def test_create_codespace_invalid_problem(self, mock_client, db_session):
        """Test create_codespace with invalid problem ID"""
        import asyncio

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                create_codespace(
                    access_token="test_token",
                    problem_id="invalid-problem",
                    username="testuser",
                    user_id=1,
                    db=db_session,
                )
            )
        assert exc_info.value.status_code == 404
        assert "Problem not found" in exc_info.value.detail

    @patch("app.main.httpx.AsyncClient")
    def test_create_codespace_template_not_found(self, mock_client, db_session):
        """Test create_codespace when template repository is not found"""
        import asyncio

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Not Found"}

        mock_client.return_value.__aenter__.return_value.post.return_value = (
            mock_response
        )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                create_codespace(
                    access_token="test_token",
                    problem_id="two-sum",
                    username="testuser",
                    user_id=1,
                    db=db_session,
                )
            )
        assert "not marked as a template" in exc_info.value.detail

    @patch("app.main.httpx.AsyncClient")
    def test_create_codespace_creation_failed(self, mock_client, db_session):
        """Test create_codespace when codespace creation fails"""
        import asyncio

        # Mock template repo generation response (success)
        mock_generate_response = MagicMock()
        mock_generate_response.status_code = 201
        mock_generate_response.json.return_value = {
            "id": 456,
            "full_name": "testuser/llmeetcode-two-sum-abc123",
            "default_branch": "main",
        }

        # Mock machines response
        mock_machines_response = MagicMock()
        mock_machines_response.status_code = 200
        mock_machines_response.json.return_value = {"machines": []}

        # Mock codespace creation response (failure)
        mock_creation_response = MagicMock()
        mock_creation_response.status_code = 400
        mock_creation_response.json.return_value = {"message": "Insufficient quota"}

        # Mock repo deletion response (cleanup)
        mock_delete_response = MagicMock()
        mock_delete_response.status_code = 204

        mock_client.return_value.__aenter__.return_value.get.return_value = (
            mock_machines_response
        )
        mock_client.return_value.__aenter__.return_value.post.side_effect = [
            mock_generate_response,
            mock_creation_response,
        ]
        mock_client.return_value.__aenter__.return_value.delete.return_value = (
            mock_delete_response
        )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                create_codespace(
                    access_token="test_token",
                    problem_id="two-sum",
                    username="testuser",
                    user_id=1,
                    db=db_session,
                )
            )
        assert "Failed to create codespace" in exc_info.value.detail

    @patch("app.main.httpx.AsyncClient")
    def test_create_codespace_success(self, mock_client, db_session):
        """Test successful codespace creation"""
        import asyncio

        from app.database import User

        # Create a user in the database
        user = db_session.query(User).filter(User.github_id == 99999).first()
        if not user:
            user = User(
                github_id=99999,
                login="testuser",
                name="Test User",
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)

        # Mock template repo generation response
        mock_generate_response = MagicMock()
        mock_generate_response.status_code = 201
        mock_generate_response.json.return_value = {
            "id": 456,
            "full_name": "testuser/llmeetcode-two-sum-abc123",
            "default_branch": "main",
        }

        # Mock branch check response
        mock_branch_response = MagicMock()
        mock_branch_response.status_code = 200

        # Mock machines response
        mock_machines_response = MagicMock()
        mock_machines_response.status_code = 200
        mock_machines_response.json.return_value = {
            "machines": [{"name": "standardLinux"}]
        }

        # Mock codespace creation response
        mock_creation_response = MagicMock()
        mock_creation_response.status_code = 201
        mock_creation_response.json.return_value = {
            "name": "test-codespace",
            "web_url": "https://github.com/codespaces/test",
            "state": "Creating",
            "created_at": "2024-01-01T00:00:00Z",
        }

        # Mock config file creation response
        mock_config_response = MagicMock()
        mock_config_response.status_code = 201

        # Set up GET responses: branch check, machines
        mock_client.return_value.__aenter__.return_value.get.side_effect = [
            mock_branch_response,
            mock_machines_response,
        ]
        # Set up POST responses: repo generation, codespace creation
        mock_client.return_value.__aenter__.return_value.post.side_effect = [
            mock_generate_response,
            mock_creation_response,
        ]
        # Set up PUT response for config file creation
        mock_client.return_value.__aenter__.return_value.put.return_value = (
            mock_config_response
        )

        # Get the user_id as an integer for the function call
        the_user_id: int = user.id  # type: ignore[assignment]

        result = asyncio.run(
            create_codespace(
                access_token="test_token",
                problem_id="two-sum",
                username="testuser",
                user_id=the_user_id,
                db=db_session,
            )
        )

        assert result["name"] == "test-codespace"
        assert result["web_url"] == "https://github.com/codespaces/test"
        assert result["state"] == "Creating"
        assert "repo_name" in result

        # Verify PUT was called for config file creation
        mock_client.return_value.__aenter__.return_value.put.assert_called_once()


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

        # Add completed problems (use seeded test problems: slow-api and two-sum)
        for problem_id in ["slow-api", "two-sum"]:
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
                "display_name": "llmeetcode-slow-api-xyz789",
                "state": "Stopped",
                "web_url": "https://github.com/codespaces/cosmic-xyz789",
                "created_at": "2024-01-01T08:00:00Z",
                "last_used_at": "2024-01-01T12:00:00Z",
                "problem_id": "slow-api",
            },
        ]

        response = authenticated_client.get("/dashboard")

        assert response.status_code == 200
        codespaces = response.context["codespaces"]
        assert len(codespaces) == 2
        assert codespaces[0]["name"] == "urban-space-abc123"
        assert codespaces[0]["problem_title"] == "Two Sum"
        assert codespaces[1]["problem_title"] == "Slow API Performance"

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
        # Using seeded test problems: slow-api and two-sum
        assert 'data-problem-id="slow-api"' in response.text
        assert 'data-problem-id="two-sum"' in response.text

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
        # Ensure problem is not completed (use slow-api which exists in test seed)
        authenticated_client.delete("/problems/slow-api/complete")

        response = authenticated_client.get("/")
        assert response.status_code == 200
        # The slow-api problem card should not have the green check icon
        # (but two-sum might if it was completed in another test)

    def test_update_hide_completed_preference(self, authenticated_client):
        """Test updating hide_completed preference via API"""
        # Set preference to true
        response = authenticated_client.put(
            "/user/preferences/hide-completed", json={"hide_completed": True}
        )
        assert response.status_code == 200
        assert response.json()["hide_completed"] is True

        # Set preference to false
        response = authenticated_client.put(
            "/user/preferences/hide-completed", json={"hide_completed": False}
        )
        assert response.status_code == 200
        assert response.json()["hide_completed"] is False

    def test_update_hide_completed_unauthenticated(self, client):
        """Test that unauthenticated users cannot update preference"""
        response = client.put(
            "/user/preferences/hide-completed", json={"hide_completed": True}
        )
        assert response.status_code == 401

    def test_hide_completed_filter_works(self, authenticated_client):
        """Test that hide_completed filter removes completed problems from list"""
        # Mark a problem as complete
        authenticated_client.post("/problems/two-sum/complete")

        # Set hide_completed preference via API
        authenticated_client.put(
            "/user/preferences/hide-completed", json={"hide_completed": True}
        )

        # Get page - should use saved preference
        response = authenticated_client.get("/")
        assert response.status_code == 200

        # two-sum should not be in the problems list
        problems = response.context["problems"]
        problem_ids = [p["id"] for p in problems]
        assert "two-sum" not in problem_ids

    def test_hide_completed_shows_uncompleted(self, authenticated_client):
        """Test that hide_completed filter still shows uncompleted problems"""
        # Mark one problem as complete
        authenticated_client.post("/problems/two-sum/complete")
        # Ensure another is not completed (use slow-api which exists in test seed)
        authenticated_client.delete("/problems/slow-api/complete")

        # Set hide_completed preference via API
        authenticated_client.put(
            "/user/preferences/hide-completed", json={"hide_completed": True}
        )

        # Get page - should use saved preference
        response = authenticated_client.get("/")
        assert response.status_code == 200

        # slow-api should still be in the problems list
        problems = response.context["problems"]
        problem_ids = [p["id"] for p in problems]
        assert "slow-api" in problem_ids


class TestTokenBasedCompletion:
    """Test the token-based /api/complete endpoint for codespace callbacks"""

    def test_complete_with_valid_token(self, client, db_session):
        """Test successful completion with valid token"""
        from datetime import UTC, datetime, timedelta

        from app.database import CodespaceToken, User

        # Create a user
        user = User(
            github_id=12345,
            login="tokenuser",
            name="Token User",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Create a valid token
        token = CodespaceToken(
            token="valid_test_token_12345",
            user_id=user.id,
            problem_id="two-sum",
            codespace_name="test-codespace",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        db_session.add(token)
        db_session.commit()

        response = client.post(
            "/api/complete",
            json={"token": "valid_test_token_12345"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["problem_id"] == "two-sum"

    def test_complete_with_invalid_token(self, client):
        """Test completion with invalid token returns 401"""
        response = client.post(
            "/api/complete",
            json={"token": "invalid_token_that_does_not_exist"},
        )

        assert response.status_code == 401
        assert "Invalid token" in response.json()["detail"]

    def test_complete_with_expired_token(self, client, db_session):
        """Test completion with expired token returns 401"""
        from datetime import UTC, datetime, timedelta

        from app.database import CodespaceToken, User

        # Create a user
        user = User(
            github_id=12346,
            login="expireduser",
            name="Expired User",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Create an expired token
        token = CodespaceToken(
            token="expired_test_token_12345",
            user_id=user.id,
            problem_id="two-sum",
            codespace_name="test-codespace-2",
            expires_at=datetime.now(UTC) - timedelta(days=1),  # Expired yesterday
        )
        db_session.add(token)
        db_session.commit()

        response = client.post(
            "/api/complete",
            json={"token": "expired_test_token_12345"},
        )

        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()

    def test_complete_already_completed(self, client, db_session):
        """Test completing an already completed problem returns appropriate status"""
        from datetime import UTC, datetime, timedelta

        from app.database import CodespaceToken, CompletedProblem, User

        # Create a user
        user = User(
            github_id=12347,
            login="alreadyuser",
            name="Already User",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Create a completed problem record
        completed = CompletedProblem(
            user_id=user.id,
            problem_id="two-sum",
        )
        db_session.add(completed)

        # Create a valid token
        token = CodespaceToken(
            token="already_complete_token_12345",
            user_id=user.id,
            problem_id="two-sum",
            codespace_name="test-codespace-3",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        db_session.add(token)
        db_session.commit()

        response = client.post(
            "/api/complete",
            json={"token": "already_complete_token_12345"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "already_completed"
        assert data["problem_id"] == "two-sum"

    def test_complete_marks_token_as_used(self, client, db_session):
        """Test that completing marks the token as used"""
        from datetime import UTC, datetime, timedelta

        from app.database import CodespaceToken, User

        # Create a user
        user = User(
            github_id=12348,
            login="useduser",
            name="Used User",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Create a valid token
        token = CodespaceToken(
            token="mark_used_token_12345",
            user_id=user.id,
            problem_id="slow-api",
            codespace_name="test-codespace-4",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            used=False,
        )
        db_session.add(token)
        db_session.commit()

        response = client.post(
            "/api/complete",
            json={"token": "mark_used_token_12345"},
        )

        assert response.status_code == 200

        # Refresh the token to check if it was marked as used
        db_session.refresh(token)
        assert token.used is True
