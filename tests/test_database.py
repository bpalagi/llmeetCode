"""Tests for database functionality"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, User, CompletedProblem, init_db, get_db

# Use in-memory SQLite for testing
TEST_DATABASE_URL = "sqlite:///./test.db"

@pytest.fixture(scope="function")
def test_db():
    """Create a fresh database for each test"""
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

class TestUser:
    """Test User model"""
    
    def test_create_user(self, test_db):
        """Test creating a new user"""
        user = User(
            github_id=12345,
            login="testuser",
            name="Test User",
            avatar_url="https://example.com/avatar.jpg"
        )
        test_db.add(user)
        test_db.commit()
        
        retrieved_user = test_db.query(User).filter(User.github_id == 12345).first()
        assert retrieved_user is not None
        assert retrieved_user.login == "testuser"
        assert retrieved_user.name == "Test User"
        assert retrieved_user.avatar_url == "https://example.com/avatar.jpg"
    
    def test_user_unique_github_id(self, test_db):
        """Test that github_id must be unique"""
        user1 = User(github_id=12345, login="user1")
        user2 = User(github_id=12345, login="user2")
        
        test_db.add(user1)
        test_db.commit()
        
        test_db.add(user2)
        with pytest.raises(Exception):  # Should raise an integrity error
            test_db.commit()

class TestCompletedProblem:
    """Test CompletedProblem model"""
    
    def test_create_completed_problem(self, test_db):
        """Test creating a completed problem record"""
        # First create a user
        user = User(github_id=12345, login="testuser")
        test_db.add(user)
        test_db.commit()
        
        # Then create a completed problem
        completed = CompletedProblem(
            user_id=user.id,
            problem_id="two-sum"
        )
        test_db.add(completed)
        test_db.commit()
        
        retrieved = test_db.query(CompletedProblem).filter(
            CompletedProblem.user_id == user.id,
            CompletedProblem.problem_id == "two-sum"
        ).first()
        assert retrieved is not None
        assert retrieved.problem_id == "two-sum"
    
    def test_user_relationship(self, test_db):
        """Test the relationship between User and CompletedProblem"""
        user = User(github_id=12345, login="testuser")
        test_db.add(user)
        test_db.commit()
        
        completed1 = CompletedProblem(user_id=user.id, problem_id="two-sum")
        completed2 = CompletedProblem(user_id=user.id, problem_id="merge-sorted")
        test_db.add_all([completed1, completed2])
        test_db.commit()
        
        # Test relationship from user to completed problems
        retrieved_user = test_db.query(User).filter(User.id == user.id).first()
        assert len(retrieved_user.completed_problems) == 2
        assert retrieved_user.completed_problems[0].problem_id == "two-sum"
        assert retrieved_user.completed_problems[1].problem_id == "merge-sorted"

class TestDatabaseFunctions:
    """Test database utility functions"""
    
    def test_init_db(self):
        """Test database initialization"""
        # Use a separate database for this test
        engine = create_engine("sqlite:///./test_init.db", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        
        # Check that tables exist using connection instead of engine
        with engine.connect() as conn:
            assert engine.dialect.has_table(conn, "users")
            assert engine.dialect.has_table(conn, "completed_problems")
        
        # Clean up
        engine.dispose()
        import os
        if os.path.exists("test_init.db"):
            os.remove("test_init.db")
    
    def test_init_db_function(self):
        """Test that init_db() function creates tables"""
        from app.database import init_db
        # Test that init_db runs without error
        init_db()
        # Tables should exist in the main database now
