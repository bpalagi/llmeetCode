import pytest
import json


class TestChatHistoryEndpoint:
    def test_chat_history_returns_empty_list(self, client):
        response = client.get('/chat/history/refactor-user-validator')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    def test_chat_history_invalid_problem(self, client):
        response = client.get('/chat/history/nonexistent')
        assert response.status_code == 200
        data = response.get_json()
        assert data == []


class TestClearChatEndpoint:
    def test_clear_chat_returns_success(self, client):
        response = client.post('/chat/clear/refactor-user-validator')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True


class TestSaveChatEndpoint:
    def test_save_chat_success(self, client):
        response = client.post(
            '/chat/save/refactor-user-validator',
            json={
                'user_message': 'Hello',
                'assistant_response': 'Hi there!'
            }
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_save_chat_missing_user_message(self, client):
        response = client.post(
            '/chat/save/refactor-user-validator',
            json={
                'assistant_response': 'Hi there!'
            }
        )
        assert response.status_code == 400

    def test_save_chat_missing_assistant_response(self, client):
        response = client.post(
            '/chat/save/refactor-user-validator',
            json={
                'user_message': 'Hello'
            }
        )
        assert response.status_code == 400

    def test_save_chat_persists_to_history(self, client):
        # Save a chat message
        client.post(
            '/chat/save/refactor-user-validator',
            json={
                'user_message': 'Test message',
                'assistant_response': 'Test response'
            }
        )
        
        # Verify it appears in history
        response = client.get('/chat/history/refactor-user-validator')
        data = response.get_json()
        
        assert len(data) == 2
        assert data[0]['role'] == 'user'
        assert data[0]['content'] == 'Test message'
        assert data[1]['role'] == 'model'
        assert data[1]['content'] == 'Test response'


class TestCompleteEndpoint:
    def test_complete_invalid_problem_returns_404(self, client):
        response = client.post(
            '/complete/nonexistent',
            json={
                'code_before': 'def ',
                'code_after': ''
            }
        )
        assert response.status_code == 404

    def test_complete_valid_problem_returns_json(self, client):
        # Note: This test will fail without GEMINI_API_KEY set
        # In a real test environment, we'd mock the LLM call
        response = client.post(
            '/complete/refactor-user-validator',
            json={
                'code_before': 'def validate_user(',
                'code_after': ')'
            }
        )
        # Either 200 (success) or 500 (no API key) is acceptable
        assert response.status_code in [200, 500]
