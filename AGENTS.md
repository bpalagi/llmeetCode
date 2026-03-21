# AGENTS.md

## Overview
- `LLMeetCode` is a FastAPI app for coding interview practice with GitHub OAuth, GitHub Codespaces provisioning, and PostgreSQL-backed persistence.
- The main user flows are browsing problems, authenticating with GitHub, creating or resuming Codespaces, and tracking completed problems.

## Stack
- Python 3.11+
- FastAPI + Jinja2 templates
- SQLAlchemy ORM
- PostgreSQL
- `httpx` for GitHub API calls
- Pytest + Testcontainers for integration-style tests

## Project Layout
- `app/main.py` - FastAPI app, route handlers, GitHub OAuth, Codespaces lifecycle, session handling
- `app/database.py` - SQLAlchemy models, engine/session helpers, lightweight migrations, initial seed data
- `app/templates/base.html` - shared layout, nav, theme toggle, shared frontend JavaScript
- `app/templates/index.html` - problem catalog UI
- `app/templates/dashboard.html` - user dashboard for completed problems and active Codespaces
- `tests/` - endpoint and helper coverage using a real PostgreSQL container
- `requirements.txt` / `requirements-test.txt` - runtime and test dependencies
- `render.yaml` / `Procfile` - deployment config

## Local Development
- Create a virtualenv: `python3 -m venv .venv`
- Activate it: `source .venv/bin/activate`
- Install deps: `pip install -r requirements.txt -r requirements-test.txt`
- Run the app: `python -m app.main`
- App default URL: `http://localhost:8000`

## Testing
- Preferred test command: `./run_tests.sh`
- Tests rely on Testcontainers and Docker to boot PostgreSQL from `tests/conftest.py`.
- The pre-commit hook runs tests before allowing commits.

## Conventions
- Database access uses `Depends(get_db)` in route handlers.
- App startup initializes schema via the FastAPI lifespan hook.
- Session state is stored in a signed cookie named `session`.
- Codespace-related GitHub API logic lives in async helpers in `app/main.py`.
- UI is server-rendered Jinja with Tailwind classes and small inline scripts for interactivity.

## Environment Variables
- `DATABASE_URL`
- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`
- `GITHUB_REDIRECT_URI`
- `SECRET_KEY`
- `API_BASE_URL`

## Notes For Agents
- Do not commit `.env`.
- Preserve the existing dark-mode capable template structure unless intentionally redesigning it.
- Be careful with repo cleanup logic in codespace deletion flows; it deletes user-owned generated repositories.
- If tests fail unexpectedly, check Docker/Testcontainers availability first.
