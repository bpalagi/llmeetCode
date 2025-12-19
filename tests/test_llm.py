import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm import build_system_prompt, format_test_cases, format_submissions


class TestBuildSystemPrompt:
    def test_basic_prompt_structure(self):
        problem = {
            'title': 'Test Problem',
            'type': 'Bug Report',
            'priority': 'High',
            'description': 'Fix the bug',
            'tests': [{'input': 'func(1)', 'expected': '2', 'hidden': False}]
        }
        code = 'def func(x): return x'
        
        prompt = build_system_prompt(problem, code)
        
        assert 'Test Problem' in prompt
        assert 'Bug Report' in prompt
        assert 'High' in prompt
        assert 'Fix the bug' in prompt
        assert 'def func(x): return x' in prompt

    def test_prompt_includes_submission_history(self):
        problem = {
            'title': 'Test',
            'type': 'Bug Report',
            'priority': 'High',
            'description': 'Test',
            'tests': []
        }
        submissions = [
            {'passed': False, 'results': [{'passed': False, 'message': 'Failed'}]}
        ]
        
        prompt = build_system_prompt(problem, 'code', submissions)
        
        assert 'Submission #1' in prompt
        assert '✗' in prompt

    def test_prompt_without_submissions(self):
        problem = {
            'title': 'Test',
            'type': 'Bug Report',
            'priority': 'High',
            'description': 'Test',
            'tests': []
        }
        
        prompt = build_system_prompt(problem, 'code', None)
        
        assert 'No submissions yet' in prompt


class TestFormatTestCases:
    def test_visible_tests_formatted(self):
        tests = [
            {'input': 'add(1, 2)', 'expected': '3', 'hidden': False},
            {'input': 'add(0, 0)', 'expected': '0', 'hidden': False}
        ]
        
        result = format_test_cases(tests)
        
        assert 'Test 1: add(1, 2)' in result
        assert 'Test 2: add(0, 0)' in result

    def test_hidden_tests_counted(self):
        tests = [
            {'input': 'add(1, 2)', 'expected': '3', 'hidden': False},
            {'input': 'add(5, 5)', 'expected': '10', 'hidden': True}
        ]
        
        result = format_test_cases(tests)
        
        assert 'Test 1: add(1, 2)' in result
        assert 'add(5, 5)' not in result
        assert '1 hidden' in result

    def test_empty_tests(self):
        result = format_test_cases([])
        assert result == ''


class TestFormatSubmissions:
    def test_no_submissions(self):
        result = format_submissions(None)
        assert result == 'No submissions yet.'
        
        result = format_submissions([])
        assert result == 'No submissions yet.'

    def test_passing_submission(self):
        submissions = [
            {'passed': True, 'results': [{'passed': True}]}
        ]
        
        result = format_submissions(submissions)
        
        assert 'Submission #1' in result
        assert '✓ All passed' in result

    def test_failing_submission_with_details(self):
        submissions = [
            {
                'passed': False,
                'results': [
                    {'passed': True},
                    {'passed': False, 'message': 'Expected 5, got 3'}
                ]
            }
        ]
        
        result = format_submissions(submissions)
        
        assert 'Submission #1' in result
        assert '1/2 passed' in result
        assert 'Expected 5, got 3' in result

    def test_multiple_submissions(self):
        submissions = [
            {'passed': False, 'results': [{'passed': False, 'message': 'Error'}]},
            {'passed': True, 'results': [{'passed': True}]}
        ]
        
        result = format_submissions(submissions)
        
        assert 'Submission #1' in result
        assert 'Submission #2' in result
