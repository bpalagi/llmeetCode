# LLMeetCode - Python Web App Prototype

> "Interviews for the modern enterprise" — LLMs allowed, but not just algorithm solving.

## Concept
A coding challenge platform (mix of getcracked.io + LeetCode) where problems look like **Jira tickets** or **Support Requests** with real-world vibes:
- "Refactor this" — without breaking test cases
- "Resolve this k8s issue" — request failing, find a misconfigured port
- @SumitM_X twitter examples

---

## Step-by-Step Build Guide

### Phase 1: Project Setup
1. Create project structure with Flask/FastAPI
2. Set up `requirements.txt` with dependencies
3. Create basic app entry point (`app.py`)

### Phase 2: Core Models & Data
4. Define problem/challenge data model (title, description, starter code, tests)
5. Create sample "ticket-style" problems as JSON/YAML fixtures
6. Set up SQLite or in-memory storage for MVP

### Phase 3: Web Interface
7. Build homepage listing available challenges
8. Create challenge detail page with:
   - Ticket-style problem description
   - Code editor (Monaco or CodeMirror)
   - Submit button
9. Add basic styling (Tailwind or simple CSS)

### Phase 4: Code Execution & Validation
10. Implement sandboxed code runner (subprocess or Docker)
11. Run submitted code against hidden test cases
12. Return pass/fail results to the user

### Phase 5: Polish & Extras
13. Add user session tracking (optional auth)
14. Display submission history
15. Add timer/scoring mechanics

---

## Tech Stack
- **Backend:** Python (Flask or FastAPI)
- **Frontend:** Jinja2 templates + HTMX or vanilla JS
- **Code Editor:** Monaco Editor (VS Code's editor)
- **Database:** SQLite (MVP)
- **Styling:** TailwindCSS
