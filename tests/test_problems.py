import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import load_problems


class TestLoadProblems:
    def test_load_problems_returns_list(self):
        problems = load_problems()
        assert isinstance(problems, list)

    def test_load_problems_not_empty(self):
        problems = load_problems()
        assert len(problems) > 0

    def test_problems_have_required_fields(self):
        problems = load_problems()
        required_fields = ['id', 'title', 'type', 'priority', 'reporter', 'description', 'starter_code', 'tests']
        for problem in problems:
            for field in required_fields:
                assert field in problem, f"Problem missing required field: {field}"

    def test_problem_ids_are_unique(self):
        problems = load_problems()
        ids = [p['id'] for p in problems]
        assert len(ids) == len(set(ids)), "Problem IDs are not unique"

    def test_tests_have_required_fields(self):
        problems = load_problems()
        for problem in problems:
            for test in problem['tests']:
                assert 'input' in test, f"Test missing 'input' field in problem {problem['id']}"
                assert 'expected' in test, f"Test missing 'expected' field in problem {problem['id']}"

    def test_problem_types_are_valid(self):
        problems = load_problems()
        valid_types = ['Jira Ticket', 'Support Request', 'Bug Report']
        for problem in problems:
            assert problem['type'] in valid_types, f"Invalid problem type: {problem['type']}"

    def test_specific_problems_exist(self):
        problems = load_problems()
        problem_ids = [p['id'] for p in problems]
        assert 'refactor-user-validator' in problem_ids
        assert 'fix-api-timeout' in problem_ids
        assert 'debug-cart-total' in problem_ids
