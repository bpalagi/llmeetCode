# LLMeetCode

> "Interviews for the modern enterprise" — LLMs allowed, and it's not just memorizing algorithms.
> Interview aspect is the discussion around the code and problem-solving approach, not just the final submission.
> **One chance to deploy** — like real production, you only get one shot.

## Overview

A coding challenge platform where problems look like **Jira tickets**, **Support Requests**, and **Bug Reports** — real-world scenarios instead of abstract puzzles.

### Inspiration
- getcracked.io + LeetCode hybrid
- @SumitM_X twitter examples

---

## Architecture

```
llmeetCode/
├── app.py                 # Flask application & routes
├── requirements.txt       # Python dependencies
├── render.yaml            # Render deployment config
├── pytest.ini             # Test configuration
├── data/
│   └── problems.json      # Challenge definitions
├── templates/
│   ├── base.html          # Layout with TailwindCSS
│   ├── index.html         # Homepage (ticket list)
│   └── challenge.html     # Code editor & test runner
└── tests/
    ├── conftest.py        # Shared fixtures
    ├── test_routes.py     # Route/endpoint tests
    ├── test_code_execution.py  # Code runner tests
    └── test_problems.py   # Problem loading tests
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Flask 3.0 |
| Frontend | Jinja2 templates |
| Code Editor | Monaco Editor (CDN) |
| Styling | TailwindCSS (CDN) |
| Code Execution | Python subprocess (5s timeout) |
| Session | Flask sessions (in-memory) |
| Deployment | Render (gunicorn) |

---

## Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Homepage listing all challenges |
| `/challenge/<id>` | GET | Challenge detail with code editor |
| `/submit/<id>` | POST | Deploy code to prod (one chance only) |
| `/chat/<id>` | POST | Chat with AI assistant |
| `/chat/stream/<id>` | POST | Streaming chat with AI assistant |
| `/chat/history/<id>` | GET | Get chat history for a problem |
| `/chat/clear/<id>` | POST | Clear chat history |
| `/chat/save/<id>` | POST | Save chat exchange to history |
| `/complete/<id>` | POST | Get code completion suggestions |

---

## Problem Schema

Problems are defined in `data/problems.json`:

```json
{
  "id": "refactor-user-validator",
  "title": "TICKET-1042: Refactor User Validator",
  "type": "Jira Ticket",
  "priority": "Medium",
  "reporter": "Sarah Chen",
  "description": "Markdown description...",
  "starter_code": "def validate_user(...):",
  "setup_code": "# Optional test fixtures",
  "tests": [
    {"input": "validate_user(...)", "expected": "True", "hidden": false}
  ]
}
```

### Problem Types
- **Jira Ticket** — Refactoring tasks
- **Support Request** — Performance/debugging
- **Bug Report** — Fix broken code

---

## Code Execution

1. User submits code via POST to `/submit/<id>`
2. Server writes code + test to temp file
3. Runs via `subprocess` with 5-second timeout
4. Parses output for PASS/FAIL/ERROR
5. Returns JSON with test results

**Security:** Basic sandboxing via subprocess isolation and timeout. Not production-hardened.

---

## Current Sample Problems

1. **TICKET-1042** — Refactor a user validator into helper functions
2. **SUPPORT-887** — Fix N+1 query performance issue
3. **BUG-2341** — Debug shopping cart discount calculation

---

## Testing

### Test Framework

| Component | Technology |
|-----------|------------|
| Framework | pytest |
| HTTP Client | Flask test client |
| Coverage | pytest-cov |

### Test Structure

```
tests/
├── conftest.py          # Shared fixtures
├── test_routes.py       # Route/endpoint tests
├── test_code_execution.py  # Code runner tests
└── test_problems.py     # Problem loading tests
```

### Test Categories

**Route Tests (`test_routes.py`)**
- `GET /` — Returns homepage with problem list
- `GET /challenge/<id>` — Returns challenge page for valid ID
- `GET /challenge/<id>` — Returns 404 for invalid ID
- `POST /submit/<id>` — Deploys code and returns test results

**Code Execution Tests (`test_code_execution.py`)**
- `run_single_test` — Passes for correct code
- `run_single_test` — Fails for incorrect code
- `run_single_test` — Handles syntax errors gracefully
- `run_single_test` — Enforces timeout for infinite loops
- `run_tests` — Aggregates multiple test results

**Problem Loading Tests (`test_problems.py`)**
- `load_problems` — Loads all problems from JSON
- `load_problems` — Returns valid problem schema

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_routes.py -v
```
