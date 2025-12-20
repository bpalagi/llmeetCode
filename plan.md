# Modern Coding Interview Platform — Product & Technical Design

A browser-based coding interview playground that evolves LeetCode-style challenges to Jira-ticket style tasks, with GitHub Codespaces powered AI allowed editor. 

---

# Idea

## Python Web App

- **Challenge Catalog**
  Browse/search problems, filters (difficulty, topic, language).
- **Codespaces-Powered IDE**  
  One-click launch of disposable GitHub Codespace pre-loaded with starter repo; VS Code UI in browser.
- **Progress Dashboard**  
  Solved count, streaks, historical submissions, skill radar chart.

## VS Code Extension

- **Codespaces-Powered IDE**  
  GitHub Codespace pre-loaded with starter repo based on problem from web-app.
- **Autograder Service**  
  Sandbox executes code against public & hidden tests; returns pass/fail + logs.

---


### 1 Web App (FastAPI or Flask)
- Single route `/` shows *Example Question* with "Open in Codespaces" button.
- GitHub OAuth login; obtain `codespace` scope token.
- On click, backend `POST`s to `https://api.github.com/user/codespaces` with template repo & `devcontainer_path`.
- Redirect user to the returned codespace URL.

### 2 Template Repository
- Contains `problem.py`, `README.md`, `tests/test_problem.py`.
- `devcontainer.json` installs custom VS Code extension via Marketplace or bundled `.vsix`.

### 3 VS Code Extension
- Executes tests inside the workspace, captures test results and POSTs to web-app endpoint

### 4 Result Dashboard
- Web app renders the latest result on the dashboard.

