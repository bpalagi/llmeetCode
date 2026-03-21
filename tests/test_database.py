"""Tests for database functionality"""

from typing import cast
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import (
    MANAGED_PROBLEM_WALKTHROUGH_TITLE,
    SLOW_API_DETAIL_OVERVIEW,
    SLOW_API_DETAIL_SUMMARY,
    SLOW_API_DOMAIN_SPECIALIZATION,
    SLOW_API_SOLUTION_VIDEO_URL,
    Base,
    CodespaceToken,
    CompletedProblem,
    Problem,
    ProblemSolutionSubmission,
    User,
    UserRepo,
    _seed_initial_data,
    create_db_engine,
    delete_problem_and_dependencies,
    get_database_url,
    get_managed_problem_walkthrough_submission,
    normalize_youtube_embed_url,
    sync_managed_problem_walkthrough_submission,
)


class TestUser:
    """Test User model"""

    def test_create_user(self, db_session):
        """Test creating a new user"""
        user = User(
            github_id=99999,
            login="testuser_create",
            name="Test User",
            avatar_url="https://example.com/avatar.jpg",
        )
        db_session.add(user)
        db_session.commit()

        retrieved_user = db_session.query(User).filter(User.github_id == 99999).first()
        assert retrieved_user is not None
        assert retrieved_user.login == "testuser_create"
        assert retrieved_user.name == "Test User"
        assert retrieved_user.avatar_url == "https://example.com/avatar.jpg"

    def test_user_unique_github_id(self, db_session):
        """Test that github_id must be unique"""
        user1 = User(github_id=88888, login="user1_unique")
        user2 = User(github_id=88888, login="user2_unique")

        db_session.add(user1)
        db_session.commit()

        db_session.add(user2)
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestCompletedProblem:
    """Test CompletedProblem model"""

    def test_create_completed_problem(self, db_session):
        """Test creating a completed problem record"""
        user = User(github_id=77777, login="testuser_completed")
        db_session.add(user)
        db_session.commit()

        completed = CompletedProblem(user_id=user.id, problem_id="two-sum")
        db_session.add(completed)
        db_session.commit()

        retrieved = (
            db_session.query(CompletedProblem)
            .filter(
                CompletedProblem.user_id == user.id,
                CompletedProblem.problem_id == "two-sum",
            )
            .first()
        )
        assert retrieved is not None
        assert retrieved.problem_id == "two-sum"

    def test_user_relationship(self, db_session):
        """Test the relationship between User and CompletedProblem"""
        user = User(github_id=66666, login="testuser_rel")
        db_session.add(user)
        db_session.commit()

        completed1 = CompletedProblem(user_id=user.id, problem_id="two-sum")
        completed2 = CompletedProblem(user_id=user.id, problem_id="merge-sorted")
        db_session.add_all([completed1, completed2])
        db_session.commit()

        retrieved_user = db_session.query(User).filter(User.id == user.id).first()
        assert len(retrieved_user.completed_problems) == 2
        problem_ids = [cp.problem_id for cp in retrieved_user.completed_problems]
        assert "two-sum" in problem_ids
        assert "merge-sorted" in problem_ids


class TestDatabaseFunctions:
    """Test database utility functions"""

    def test_init_db_function(self, db_session):
        """Test that tables exist in the database"""
        result = db_session.execute(Base.metadata.tables["users"].select())
        assert result is not None

        result = db_session.execute(Base.metadata.tables["completed_problems"].select())
        assert result is not None


class TestProblemDetailContent:
    """Test rich problem content persistence and relationships."""

    def test_problem_detail_fields_persist(self, db_session):
        problem = db_session.query(Problem).filter(Problem.id == "slow-api").first()

        assert problem is not None
        assert problem.detail_summary == SLOW_API_DETAIL_SUMMARY
        assert problem.detail_overview == SLOW_API_DETAIL_OVERVIEW
        assert problem.domain_specialization == SLOW_API_DOMAIN_SPECIALIZATION

    def test_problem_solution_submission_relationship(self, db_session):
        problem = db_session.query(Problem).filter(Problem.id == "slow-api").first()

        assert problem is not None
        assert len(problem.solution_submissions) == 1
        submission = problem.solution_submissions[0]
        assert submission.problem_id == "slow-api"
        assert submission.video_url == SLOW_API_SOLUTION_VIDEO_URL
        assert submission.embed_url == normalize_youtube_embed_url(
            SLOW_API_SOLUTION_VIDEO_URL
        )

    def test_seed_initial_data_is_idempotent_for_solution_submission(self, db_session):
        _seed_initial_data()
        _seed_initial_data()

        submissions = (
            db_session.query(ProblemSolutionSubmission)
            .filter(ProblemSolutionSubmission.problem_id == "slow-api")
            .all()
        )
        assert len(submissions) == 1

    def test_problem_with_video_submission_persists_normalized_embed_url(
        self, db_session
    ):
        problem = Problem(
            id="cache-debug",
            title="Cache Debugging",
            description="Investigate a stale cache issue.",
            detail_summary="Trace the cache invalidation path.",
            detail_overview="Reproduce the bug and fix the invalidation logic.",
            domain_specialization="Caching systems",
            difficulty="Medium",
            language="Python",
            template_repo="test/cache-debug-template",
            is_active=True,
        )
        db_session.add(problem)
        db_session.flush()

        video_url = "https://www.youtube.com/watch?v=cache123xyz"
        submission = ProblemSolutionSubmission(
            problem_id=problem.id,
            title="Problem walkthrough",
            video_url=video_url,
            embed_url=normalize_youtube_embed_url(video_url),
            sort_order=1,
            is_active=True,
        )
        db_session.add(submission)
        db_session.commit()

        saved_submission = (
            db_session.query(ProblemSolutionSubmission)
            .filter(ProblemSolutionSubmission.problem_id == "cache-debug")
            .one()
        )
        assert saved_submission.embed_url == "https://www.youtube.com/embed/cache123xyz"

    def test_sync_managed_walkthrough_updates_existing_submission(self, db_session):
        sync_managed_problem_walkthrough_submission(
            db_session,
            "slow-api",
            "https://youtu.be/updated123",
            "https://www.youtube.com/embed/updated123",
        )
        db_session.commit()

        submission = get_managed_problem_walkthrough_submission(db_session, "slow-api")
        assert submission is not None
        assert cast(str, submission.title) == MANAGED_PROBLEM_WALKTHROUGH_TITLE
        assert cast(str, submission.video_url) == "https://youtu.be/updated123"
        assert (
            cast(str, submission.embed_url)
            == "https://www.youtube.com/embed/updated123"
        )

    def test_sync_managed_walkthrough_removes_submission_when_cleared(self, db_session):
        sync_managed_problem_walkthrough_submission(db_session, "slow-api", "", None)
        db_session.commit()

        submission = get_managed_problem_walkthrough_submission(db_session, "slow-api")
        assert submission is None

    def test_delete_problem_and_dependencies_cleans_all_known_rows(self, db_session):
        user = User(github_id=515151, login="cleanup-user")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        db_session.add(CompletedProblem(user_id=user.id, problem_id="slow-api"))
        db_session.add(
            UserRepo(
                user_id=user.id,
                github_username="cleanup-user",
                repo_name="cleanup-repo",
                codespace_name="cleanup-codespace",
                problem_id="slow-api",
                template_repo="bpalagi/slow-api-template",
            )
        )
        from datetime import UTC, datetime, timedelta

        db_session.add(
            CodespaceToken(
                token="cleanup-token",
                user_id=user.id,
                problem_id="slow-api",
                codespace_name="cleanup-codespace",
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        db_session.commit()

        delete_problem_and_dependencies(db_session, "slow-api")
        db_session.commit()

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


class TestYoutubeNormalization:
    """Test YouTube embed normalization helper."""

    def test_normalize_live_url(self):
        assert normalize_youtube_embed_url(SLOW_API_SOLUTION_VIDEO_URL) == (
            "https://www.youtube.com/embed/dtjqMNyNPiw"
        )

    def test_normalize_watch_url(self):
        assert (
            normalize_youtube_embed_url("https://www.youtube.com/watch?v=abc123xyz")
            == "https://www.youtube.com/embed/abc123xyz"
        )


class TestGetDatabaseUrl:
    """Test get_database_url function"""

    def test_postgres_url_converted_to_postgresql(self):
        """Test that postgres:// URLs are converted to postgresql://"""
        url = "postgres://user:pass@host:5432/dbname"
        result = get_database_url(url)
        assert result == "postgresql://user:pass@host:5432/dbname"

    def test_postgresql_url_unchanged(self):
        """Test that postgresql:// URLs are not modified"""
        url = "postgresql://user:pass@host:5432/dbname"
        result = get_database_url(url)
        assert result == "postgresql://user:pass@host:5432/dbname"

    def test_postgres_replacement_only_at_start(self):
        """Test that postgres:// is only replaced at the start of the URL"""
        url = "postgres://user:postgres@host:5432/dbname"
        result = get_database_url(url)
        assert result == "postgresql://user:postgres@host:5432/dbname"

    def test_default_url_from_env(self):
        """Test that DATABASE_URL env var is used when no URL provided"""
        with patch.dict("os.environ", {"DATABASE_URL": "postgres://envhost/db"}):
            result = get_database_url()
            assert result == "postgresql://envhost/db"

    def test_missing_database_url_raises_error(self):
        """Test that missing DATABASE_URL raises ValueError"""
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(
                ValueError, match="DATABASE_URL environment variable is required"
            ),
        ):
            get_database_url()


class TestCreateDbEngine:
    """Test create_db_engine function"""

    def test_postgresql_engine_created(self):
        """Test that PostgreSQL engine is created correctly"""
        with patch("app.database.create_engine") as mock_create_engine:
            mock_create_engine.return_value = None
            create_db_engine("postgresql://user:pass@localhost:5432/testdb")
            mock_create_engine.assert_called_once_with(
                "postgresql://user:pass@localhost:5432/testdb"
            )

    def test_postgres_url_engine_created(self):
        """Test that postgres:// URLs work after normalization"""
        with patch("app.database.create_engine") as mock_create_engine:
            mock_create_engine.return_value = None
            # First normalize the URL, then create engine
            normalized_url = get_database_url(
                "postgres://user:pass@localhost:5432/testdb"
            )
            create_db_engine(normalized_url)
            mock_create_engine.assert_called_once_with(
                "postgresql://user:pass@localhost:5432/testdb"
            )
