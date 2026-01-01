# LLMeetCode - Coding Interview Platform

A modern coding interview platform that provides browser-based development environments using GitHub Codespaces.

## Features

- **Problem Catalog**: Browse coding challenges with filters for difficulty, topic, and language
- **GitHub Codespaces Integration**: One-click launch of disposable development environments
- **Real-time IDE**: Full VS Code experience in the browser with pre-configured problems
- **Secure Authentication**: GitHub OAuth with encrypted session management

## Quick Start


2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your GitHub OAuth credentials
```

5. Run the application:
```bash
python app/main.py
```

The app will be available at `http://localhost:8000`

### GitHub OAuth Setup

1. Go to GitHub Settings > Developer settings > OAuth Apps
2. Create a new OAuth App with:
   - **Application name**: LLMeet (or your preferred name)
   - **Homepage URL**: `http://localhost:8000`
   - **Authorization callback URL**: `http://localhost:8000/auth/callback`
3. Note the Client ID and generate a Client Secret
4. Add these to your `.env` file

### Codespaces Template Repository

Create a GitHub repository that contains:
- `problem.py` - Starter code for the problem
- `tests/test_problem.py` - Test cases
- `.devcontainer/devcontainer.json` - Development container configuration
- `README.md` - Problem description

Example devcontainer.json:
```json
{
    "name": "Python Coding Environment",
    "image": "mcr.microsoft.com/devcontainers/python:3.10",
    "customizations": {
        "vscode": {
            "extensions": [
                "ms-python.python",
                "ms-python.vscode-pylance"
            ]
        }
    }
}
```

## API Endpoints

- `GET /` - Home page with problem list
- `GET /auth/login` - Redirect to GitHub OAuth
- `GET /auth/callback` - OAuth callback handler
- `POST /codespaces/create` - Create a new codespace
- `GET /auth/logout` - Clear session and logout

## Security Notes

- Session tokens are encrypted and expire after 1 hour
- GitHub access tokens are stored only in the session, not in a database
- In production, use HTTPS and set `secure=True` for cookies
- The `codespace` OAuth scope is required for creating codespaces

## Development

### Running in Development Mode

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Adding New Problems

1. Update the `SAMPLE_PROBLEMS` list in `app/main.py`
2. Create corresponding problem files in your template repository
3. Ensure the problem ID matches between the web app and template

