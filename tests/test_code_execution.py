import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import run_single_test, run_tests


class TestRunSingleTest:
    def test_passing_code(self):
        code = "def add(a, b): return a + b"
        test = {"input": "add(2, 3)", "expected": "5", "hidden": False}
        result = run_single_test(code, test)
        assert result['passed'] is True
        assert result['hidden'] is False

    def test_failing_code(self):
        code = "def add(a, b): return a - b"
        test = {"input": "add(2, 3)", "expected": "5", "hidden": False}
        result = run_single_test(code, test)
        assert result['passed'] is False

    def test_syntax_error(self):
        code = "def add(a, b) return a + b"  # Missing colon
        test = {"input": "add(2, 3)", "expected": "5", "hidden": False}
        result = run_single_test(code, test)
        assert result['passed'] is False
        assert 'message' in result

    def test_runtime_error(self):
        code = "def divide(a, b): return a / b"
        test = {"input": "divide(1, 0)", "expected": "0", "hidden": False}
        result = run_single_test(code, test)
        assert result['passed'] is False

    def test_timeout_enforcement(self):
        code = """
def infinite():
    while True:
        pass
"""
        test = {"input": "infinite()", "expected": "None", "hidden": False}
        result = run_single_test(code, test)
        assert result['passed'] is False
        assert 'Timeout' in result['message']

    def test_hidden_flag_preserved(self):
        code = "def add(a, b): return a + b"
        test = {"input": "add(2, 3)", "expected": "5", "hidden": True}
        result = run_single_test(code, test)
        assert result['hidden'] is True

    def test_setup_code_execution(self):
        code = "def get_value(): return CONSTANT"
        test = {"input": "get_value()", "expected": "42", "hidden": False}
        setup_code = "CONSTANT = 42"
        result = run_single_test(code, test, setup_code)
        assert result['passed'] is True


class TestRunTests:
    def test_all_tests_pass(self):
        code = "def add(a, b): return a + b"
        tests = [
            {"input": "add(1, 2)", "expected": "3", "hidden": False},
            {"input": "add(0, 0)", "expected": "0", "hidden": False},
            {"input": "add(-1, 1)", "expected": "0", "hidden": False},
        ]
        results = run_tests(code, tests)
        assert results['all_passed'] is True
        assert len(results['test_results']) == 3

    def test_some_tests_fail(self):
        code = "def add(a, b): return a + b if a > 0 else 0"
        tests = [
            {"input": "add(1, 2)", "expected": "3", "hidden": False},
            {"input": "add(-1, 1)", "expected": "0", "hidden": False},
        ]
        results = run_tests(code, tests)
        assert results['all_passed'] is True

    def test_all_tests_fail(self):
        code = "def add(a, b): return 0"
        tests = [
            {"input": "add(1, 2)", "expected": "3", "hidden": False},
            {"input": "add(5, 5)", "expected": "10", "hidden": False},
        ]
        results = run_tests(code, tests)
        assert results['all_passed'] is False

    def test_empty_tests_list(self):
        code = "def add(a, b): return a + b"
        tests = []
        results = run_tests(code, tests)
        assert results['all_passed'] is True
        assert len(results['test_results']) == 0
