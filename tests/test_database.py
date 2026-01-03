"""Tests for database functionality"""

from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import (
    Base,
    CompletedProblem,
    User,
    create_db_engine,
    get_database_url,
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
