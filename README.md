# LLMeetCode - Coding Interview Platform

A modern coding interview platform that provides browser-based development environments using GitHub Codespaces.

## Features

- **Problem Catalog**: Browse coding challenges with filters for difficulty and language
- **GitHub Codespaces Integration**: One-click launch of disposable development environments
- **Real-time IDE**: Full VS Code experience in the browser with pre-configured problems
- **Secure Authentication**: GitHub OAuth with encrypted session management
- **Dynamic Repo Creation**: Creates a private repo from template in user's account for each problem

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL

**Install PostgreSQL (macOS):**
```bash
brew install postgresql@15
brew services start postgresql@15
```

**Create the database:**
```bash
createdb llmeetcode
```

**Stop PostgreSQL (when not needed):**
```bash
brew services stop postgresql@15
```

### Setup

1. Create a virtual environment:
```bash
python -m venv .venv
```

2. Activate the virtual environment:
```bash
source .venv/bin/activate
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
python -m app.main
```

The app will be available at `http://localhost:8000`

### Running Tests

```bash
./run_tests.sh
```

### GitHub OAuth Setup

1. Go to GitHub Settings > Developer settings > OAuth Apps
2. Create a new OAuth App with:
   - **Application name**: LLMeetCode (or your preferred name)
   - **Homepage URL**: `http://localhost:8000`
   - **Authorization callback URL**: `http://localhost:8000/auth/callback`
3. Note the Client ID and generate a Client Secret
4. Add these to your `.env` file

### Problem Template Repositories

Problems are stored in the database with a reference to their GitHub template repository. Each template repo should:

1. **Be marked as a template** in GitHub (Settings > Template repository)
2. Contain the problem starter code and tests
3. Include a `.devcontainer/devcontainer.json` for the Codespaces environment

When a user starts a problem:
1. A new private repo is created from the template in the user's GitHub account
2. A Codespace is launched from that repo
3. When the user deletes the Codespace, the repo is also deleted

## Git Hooks

### Pre-commit Hook

The repository includes a pre-commit hook that automatically runs tests before allowing commits. This ensures code quality and prevents broken code from being committed.

The hook will:
- Create/activate a virtual environment if needed
- Install test dependencies
- Run all tests with coverage
- Block the commit if any tests fail

### Pre-push Hook

A pre-push hook provides a reminder about Render deployment when pushing changes.

## Deployment to Render

### Automatic Deployment

The project is configured for automatic deployment to Render when pushing to the main branch.

1. **Prerequisites**:
   - Connect your GitHub repository to Render
   - Render will automatically detect the `render.yaml` configuration

2. **Configuration Files**:
   - `render.yaml` - Defines the web service and build settings
   - `Procfile` - Specifies the command to run the web server
   - `requirements.txt` - Lists all Python dependencies

3. **Environment Variables**:
   Set these in your Render dashboard:
   - `GITHUB_CLIENT_ID` - Your GitHub OAuth app client ID
   - `GITHUB_CLIENT_SECRET` - Your GitHub OAuth app client secret
   - `GITHUB_REDIRECT_URI` - Your Render app URL + `/auth/callback`
   - `SECRET_KEY` - A secure random string for session encryption
   - `DATABASE_URL` - PostgreSQL connection string

4. **Deployment Process**:
   - Push to your main branch
   - Render automatically builds and deploys
   - Tests run during the build process
   - Your app is live at your Render URL

### Manual Deployment

If auto-deploy is disabled, you can trigger deployments manually from the Render dashboard.
