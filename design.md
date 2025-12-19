# LLMeetCode

> "Interviews for the modern enterprise" — LLMs allowed, and it's not just memorizing algorithms.
> Interview aspect is the discussion around the code and problem-solving approach, not just the final submission

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
├── data/
│   └── problems.json      # Challenge definitions
└── templates/
    ├── base.html          # Layout with TailwindCSS
    ├── index.html         # Homepage (ticket list)
    └── challenge.html     # Code editor & test runner
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
| `/submit/<id>` | POST | Submit code, run tests, return results |

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
