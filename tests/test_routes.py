import pytest


class TestHomepage:
    def test_index_returns_200(self, client):
        response = client.get('/')
        assert response.status_code == 200

    def test_index_contains_problems(self, client):
        response = client.get('/')
        assert b'TICKET-1042' in response.data
        assert b'SUPPORT-887' in response.data
        assert b'BUG-2341' in response.data


class TestChallengePage:
    def test_challenge_valid_id_returns_200(self, client):
        response = client.get('/challenge/refactor-user-validator')
        assert response.status_code == 200

    def test_challenge_contains_problem_title(self, client):
        response = client.get('/challenge/refactor-user-validator')
        assert b'Refactor User Validator' in response.data

    def test_challenge_invalid_id_returns_404(self, client):
        response = client.get('/challenge/nonexistent-problem')
        assert response.status_code == 404


class TestSubmitEndpoint:
    def test_submit_valid_problem_returns_json(self, client):
        response = client.post(
            '/submit/refactor-user-validator',
            json={'code': '''
def validate_user(email, password, username):
    if '@' not in email or '.' not in email.split('@')[1]:
        return False
    if len(password) < 8 or not any(c.isupper() for c in password) or not any(c.isdigit() for c in password):
        return False
    if len(username) < 3 or len(username) > 20 or not username.isalnum():
        return False
    return True
'''}
        )
        assert response.status_code == 200
        data = response.get_json()
        assert 'all_passed' in data
        assert 'test_results' in data

    def test_submit_correct_code_passes(self, client):
        response = client.post(
            '/submit/refactor-user-validator',
            json={'code': '''
def validate_user(email, password, username):
    if '@' not in email or '.' not in email.split('@')[1]:
        return False
    if len(password) < 8 or not any(c.isupper() for c in password) or not any(c.isdigit() for c in password):
        return False
    if len(username) < 3 or len(username) > 20 or not username.isalnum():
        return False
    return True
'''}
        )
        data = response.get_json()
        assert data['all_passed'] is True

    def test_submit_invalid_problem_returns_404(self, client):
        response = client.post(
            '/submit/nonexistent-problem',
            json={'code': 'print("hello")'}
        )
        assert response.status_code == 404

    def test_submit_incorrect_code_fails(self, client):
        response = client.post(
            '/submit/refactor-user-validator',
            json={'code': '''
def validate_user(email, password, username):
    return False
'''}
        )
        data = response.get_json()
        assert data['all_passed'] is False


class TestHistoryEndpoint:
    def test_history_returns_json(self, client):
        response = client.get('/history/refactor-user-validator')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    def test_history_empty_initially(self, client):
        response = client.get('/history/refactor-user-validator')
        data = response.get_json()
        assert data == []
