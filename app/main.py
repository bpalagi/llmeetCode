import os
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import (
    CodespaceToken,
    CompletedProblem,
    Problem,
    User,
    UserRepo,
    get_db,
    init_db,
)

# Load environment variables from .env file
load_dotenv()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup
    init_db()
    yield
    # Shutdown


app = FastAPI(title="LLMeetCode - Coding Interview Platform", lifespan=lifespan)

# Configuration
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv(
    "GITHUB_REDIRECT_URI", "http://localhost:8000/auth/callback"
)
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Session management
serializer = URLSafeTimedSerializer(SECRET_KEY)

# Templates
templates = Jinja2Templates(directory="app/templates")

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")


class CodespaceRequest(BaseModel):
    problem_id: str
    language: str = "python"


def get_session_data(request: Request) -> dict[str, Any]:
    """Get session data from encrypted cookie"""
    session_token = request.cookies.get("session")
    if not session_token:
        return {}
    try:
        return serializer.loads(session_token, max_age=3600)  # 1 hour expiry
    except BadSignature:
        return {}


async def create_codespace(
    access_token: str, problem_id: str, username: str, user_id: int, db: Session
) -> dict:
    """Create a GitHub Codespace for the given problem.

    This function:
    1. Creates a new repo in the user's account from the problem's template
    2. Creates a codespace from that new repo
    3. Tracks the repo in the database for later cleanup

    Args:
        access_token: GitHub OAuth access token
        problem_id: The problem identifier
        username: GitHub username of the authenticated user
        user_id: Database user ID
        db: Database session

    Returns:
        Dict with codespace info: name, web_url, state, created_at, repo_name
    """

    # Validate problem ID exists and get problem from database
    problem = (
        db.query(Problem)
        .filter(Problem.id == problem_id, Problem.is_active.is_(True))
        .first()
    )
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")

    # Get the template repo from the problem
    template_repo = problem.template_repo

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step 1: Create a new repo from the template in the user's account
        unique_suffix = secrets.token_hex(4)
        new_repo_name = f"llmeetcode-{problem_id}-{unique_suffix}"

        # Create repo from template
        create_repo_response = await client.post(
            f"https://api.github.com/repos/{template_repo}/generate",
            json={
                "owner": username,
                "name": new_repo_name,
                "private": True,
                "description": f"LLMeetCode interview problem: {problem.title}",
            },
            headers=headers,
        )

        if create_repo_response.status_code == 404:
            raise HTTPException(
                status_code=500,
                detail=f"Template repository '{template_repo}' not found or not marked as a template. "
                "Please ensure the template repo exists and is marked as a template in GitHub settings.",
            )
        elif create_repo_response.status_code != 201:
            error_data = create_repo_response.json()
            error_detail = error_data.get("message", "Unknown error")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create repository from template: {error_detail}",
            )

        new_repo_data = create_repo_response.json()
        new_repo_full_name = new_repo_data["full_name"]
        repository_id = new_repo_data["id"]
        default_branch = new_repo_data.get("default_branch", "main")

        # Wait for the repo to be fully initialized by polling for the branch
        import asyncio

        max_retries = 10
        for attempt in range(max_retries):
            await asyncio.sleep(2)
            # Check if the branch exists
            branch_response = await client.get(
                f"https://api.github.com/repos/{new_repo_full_name}/branches/{default_branch}",
                headers=headers,
            )
            if branch_response.status_code == 200:
                break
            if attempt == max_retries - 1:
                # Clean up the repo if we can't verify it's ready
                await client.delete(
                    f"https://api.github.com/repos/{new_repo_full_name}",
                    headers=headers,
                )
                raise HTTPException(
                    status_code=500,
                    detail="Repository created but branch not available. Please try again.",
                )

        # Step 2: Create config file with completion token BEFORE creating codespace
        # This ensures the token is available when the codespace container starts
        completion_token = secrets.token_urlsafe(32)
        token_expires_at = datetime.now(UTC) + timedelta(days=7)  # 7 day expiry

        # Create the config file content
        config_content = f"""# LLMeetCode Configuration
# This file was auto-generated when the codespace was created.
# DO NOT EDIT or share this file - it contains your authentication token.

LLMEETCODE_TOKEN={completion_token}
LLMEETCODE_PROBLEM_ID={problem_id}
LLMEETCODE_API_URL={API_BASE_URL}
"""
        # Base64 encode the content for GitHub Contents API
        import base64

        config_content_b64 = base64.b64encode(config_content.encode()).decode()

        # Create the .llmeetcode-config file in the repo
        config_response = await client.put(
            f"https://api.github.com/repos/{new_repo_full_name}/contents/.llmeetcode-config",
            json={
                "message": "Add LLMeetCode configuration",
                "content": config_content_b64,
                "branch": default_branch,
            },
            headers=headers,
        )

        if config_response.status_code not in (200, 201):
            # Log warning but continue - the codespace can still be created
            print(
                f"Warning: Failed to create .llmeetcode-config: "
                f"{config_response.status_code} {config_response.text}"
            )

        # Step 3: Get available machine types for the new repository
        machines_response = await client.get(
            f"https://api.github.com/repos/{new_repo_full_name}/codespaces/machines",
            headers=headers,
        )

        machine_type = "basicLinux32gb"  # Default to a known valid machine type

        if machines_response.status_code == 200:
            machines = machines_response.json()
            if machines and "machines" in machines and len(machines["machines"]) > 0:
                machine_type = machines["machines"][0]["name"]

        # Step 4: Create the codespace from the new repo
        display_name = f"llmeetcode-{problem_id}-{unique_suffix}"
        codespace_data = {
            "repository_id": repository_id,
            "ref": default_branch,
            "location": "WestUs2",
            "machine": machine_type,
            "devcontainer_path": ".devcontainer/devcontainer.json",
            "display_name": display_name,
            "idle_timeout_minutes": 30,
        }

        response = await client.post(
            "https://api.github.com/user/codespaces",
            json=codespace_data,
            headers=headers,
        )

        if response.status_code != 201:
            # If codespace creation fails, try to clean up the repo we created
            await client.delete(
                f"https://api.github.com/repos/{new_repo_full_name}",
                headers=headers,
            )
            error_data = response.json()
            print(f"GitHub API Error Response: {error_data}")
            error_detail = error_data.get("message", "Unknown error")
            raise HTTPException(
                status_code=500, detail=f"Failed to create codespace: {error_detail}"
            )

        codespace = response.json()

        # Step 5: Store token in database (token was already generated before codespace creation)
        codespace_token = CodespaceToken(
            token=completion_token,
            user_id=user_id,
            problem_id=problem_id,
            codespace_name=codespace["name"],
            expires_at=token_expires_at,
        )
        db.add(codespace_token)

        # Step 6: Track the repo in the database for cleanup later
        user_repo = UserRepo(
            user_id=user_id,
            github_username=username,
            repo_name=new_repo_name,
            codespace_name=codespace["name"],
            problem_id=problem_id,
            template_repo=template_repo,
        )
        db.add(user_repo)
        db.commit()

        # Return the codespace info
        return {
            "name": codespace["name"],
            "web_url": codespace.get(
                "web_url", f"https://github.com/codespaces/{codespace['name']}"
            ),
            "state": codespace.get("state", "Unknown"),
            "created_at": codespace.get("created_at"),
            "repo_name": new_repo_full_name,
        }


async def list_user_codespaces(
    access_token: str, problem_id: str | None = None
) -> list[dict]:
    """List user's GitHub Codespaces created by llmeetcode.

    Args:
        access_token: GitHub OAuth access token
        problem_id: Optional problem ID to filter by

    Returns:
        List of codespace dicts with: name, web_url, state, display_name,
        created_at, last_used_at, problem_id (extracted from display_name)
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.github.com/user/codespaces",
            headers=headers,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to list codespaces: {response.json().get('message', 'Unknown error')}",
            )

        data = response.json()
        codespaces = data.get("codespaces", [])

        # Filter to only llmeetcode codespaces
        llmeetcode_codespaces = []
        for cs in codespaces:
            display_name = cs.get("display_name", "")
            if not display_name.startswith("llmeetcode-"):
                continue

            # Extract problem_id from display_name: "llmeetcode-{problem_id}-{8_char_hex}"
            parts = display_name.split("-")
            # parts[0] = "llmeetcode", parts[1:-1] = problem_id parts, parts[-1] = hex
            extracted_problem_id = "-".join(parts[1:-1]) if len(parts) > 2 else ""

            # Filter by problem_id if provided
            if problem_id and extracted_problem_id != problem_id:
                continue

            llmeetcode_codespaces.append(
                {
                    "name": cs["name"],
                    "web_url": cs.get(
                        "web_url", f"https://github.com/codespaces/{cs['name']}"
                    ),
                    "state": cs.get("state", "Unknown"),
                    "display_name": display_name,
                    "created_at": cs.get("created_at"),
                    "last_used_at": cs.get("last_used_at"),
                    "problem_id": extracted_problem_id,
                }
            )

        # Sort by last_used_at descending, fall back to created_at
        llmeetcode_codespaces.sort(
            key=lambda x: x.get("last_used_at") or x.get("created_at") or "",
            reverse=True,
        )

        return llmeetcode_codespaces


async def delete_codespace(access_token: str, codespace_name: str) -> bool:
    """Delete a GitHub Codespace.

    Args:
        access_token: GitHub OAuth access token
        codespace_name: The name of the codespace to delete

    Returns:
        True if deletion was successful

    Raises:
        HTTPException: If deletion fails
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"https://api.github.com/user/codespaces/{codespace_name}",
            headers=headers,
        )

        if response.status_code == 202:
            # 202 Accepted means deletion is in progress
            return True
        elif response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="Codespace not found",
            )
        else:
            error_msg = response.json().get("message", "Unknown error")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to delete codespace: {error_msg}",
            )


async def delete_user_repo(
    access_token: str, github_username: str, repo_name: str
) -> bool:
    """Delete a user's repository that was created for a codespace session.

    Args:
        access_token: GitHub OAuth access token
        github_username: The GitHub username who owns the repo
        repo_name: The name of the repo to delete (not full_name, just repo name)

    Returns:
        True if deletion was successful or repo not found (already deleted)

    Raises:
        HTTPException: If deletion fails for reasons other than 404
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    repo_full_name = f"{github_username}/{repo_name}"

    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"https://api.github.com/repos/{repo_full_name}",
            headers=headers,
        )

        if response.status_code in (204, 404):
            # 204 = deleted successfully, 404 = already gone
            return True
        else:
            error_msg = response.json().get("message", "Unknown error")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to delete repository: {error_msg}",
            )


@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    db: Session = Depends(get_db),
    difficulty: str | None = None,
    language: str | None = None,
):
    """Main page listing coding problems"""
    session = get_session_data(request)

    # Get user's hide_completed preference from database
    hide_completed_bool = False
    completed_ids = set()
    active_codespaces = {}  # Maps problem_id -> codespace web_url
    if session and "user_id" in session:
        user = db.query(User).filter(User.id == session["user_id"]).first()
        if user:
            hide_completed_bool = user.hide_completed

        completed = (
            db.query(CompletedProblem)
            .filter(CompletedProblem.user_id == session["user_id"])
            .all()
        )
        completed_ids = {cp.problem_id for cp in completed}

        # Get active codespaces for this user
        if session.get("access_token"):
            try:
                codespaces = await list_user_codespaces(session["access_token"])
                active_codespaces = {
                    cs["problem_id"]: cs["web_url"] for cs in codespaces
                }
            except Exception:
                # If fetching codespaces fails, continue without them
                pass

    # Get all active problems from database
    problems_query = db.query(Problem).filter(Problem.is_active.is_(True))

    # Apply filters
    if difficulty and difficulty != "All Difficulties":
        problems_query = problems_query.filter(Problem.difficulty == difficulty)

    if language and language != "All Languages":
        problems_query = problems_query.filter(Problem.language == language)

    all_problems = problems_query.all()

    # Convert to dict format for template compatibility
    filtered_problems = [
        {
            "id": p.id,
            "title": p.title,
            "description": p.description,
            "difficulty": p.difficulty,
            "language": p.language,
            "template_repo": p.template_repo,
        }
        for p in all_problems
    ]

    # Hide completed problems if requested
    if hide_completed_bool and completed_ids:
        filtered_problems = [
            p for p in filtered_problems if p["id"] not in completed_ids
        ]

    # Get unique values for filter options from all active problems
    all_active_problems = db.query(Problem).filter(Problem.is_active.is_(True)).all()
    all_difficulties = sorted({p.difficulty for p in all_active_problems})
    all_languages = sorted({p.language for p in all_active_problems})

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "problems": filtered_problems,
            "user": session.get("user"),
            "logged_in": bool(session),
            "completed_ids": completed_ids,
            "active_codespaces": active_codespaces,
            "hide_completed": "true" if hide_completed_bool else "false",
            "selected_difficulty": difficulty or "All Difficulties",
            "selected_language": language or "All Languages",
            "all_difficulties": all_difficulties,
            "all_languages": all_languages,
        },
    )


@app.get("/auth/login")
async def login():
    """Redirect to GitHub OAuth"""
    auth_url = (
        f"https://github.com/login/oauth/authorize?"
        f"client_id={GITHUB_CLIENT_ID}&"
        f"redirect_uri={GITHUB_REDIRECT_URI}&"
        f"scope=codespace user:email repo delete_repo"
    )
    return RedirectResponse(auth_url, status_code=302)


@app.get("/auth/callback")
async def auth_callback(code: str, db: Session = Depends(get_db)):
    """Handle GitHub OAuth callback"""

    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )

        if token_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get access token")

        token_data = token_response.json()
        access_token = token_data.get("access_token")

        if not access_token:
            raise HTTPException(status_code=400, detail="No access token received")

        # Get user info
        user_response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )

        if user_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info")

        user_data = user_response.json()

    # Create or update user in database
    github_id = user_data["id"]
    db_user = db.query(User).filter(User.github_id == github_id).first()

    if db_user:
        # Update existing user
        db_user.login = user_data["login"]
        db_user.name = user_data.get("name")
        db_user.avatar_url = user_data.get("avatar_url")
    else:
        # Create new user
        db_user = User(
            github_id=github_id,
            login=user_data["login"],
            name=user_data.get("name"),
            avatar_url=user_data.get("avatar_url"),
        )
        db.add(db_user)

    db.commit()
    db.refresh(db_user)

    # Create session
    session_data = {
        "access_token": access_token,
        "user_id": db_user.id,
        "user": {
            "login": user_data["login"],
            "name": user_data.get("name"),
            "avatar_url": user_data.get("avatar_url"),
        },
    }

    session_token = serializer.dumps(session_data)

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        "session",
        session_token,
        max_age=3600,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
    )

    return response


@app.post("/codespaces/create")
async def create_codespace_endpoint(
    request: CodespaceRequest, http_request: Request, db: Session = Depends(get_db)
):
    """Create a new codespace for a problem.

    This creates a new repository from the problem's template in the user's
    GitHub account, then creates a codespace from that repo.
    """
    session = get_session_data(http_request)

    if not session or "access_token" not in session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if "user_id" not in session or "user" not in session:
        raise HTTPException(status_code=401, detail="Session missing user info")

    username = session["user"].get("login")
    if not username:
        raise HTTPException(status_code=401, detail="Session missing GitHub username")

    try:
        codespace_info = await create_codespace(
            access_token=session["access_token"],
            problem_id=request.problem_id,
            username=username,
            user_id=session["user_id"],
            db=db,
        )
        return codespace_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/codespaces/list")
async def list_codespaces_endpoint(
    http_request: Request,
    problem_id: str | None = None,
):
    """List user's llmeetcode codespaces"""
    session = get_session_data(http_request)

    if not session or "access_token" not in session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return await list_user_codespaces(session["access_token"], problem_id)


@app.get("/codespaces/{problem_id}/active")
async def get_active_codespace(
    problem_id: str,
    http_request: Request,
):
    """Get the active codespace for a specific problem, if any exists"""
    session = get_session_data(http_request)

    if not session or "access_token" not in session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    codespaces = await list_user_codespaces(session["access_token"], problem_id)

    if codespaces:
        return codespaces[0]

    return {"codespace": None}


@app.delete("/codespaces/{codespace_name}")
async def delete_codespace_endpoint(
    codespace_name: str,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """Delete a codespace by name and its associated repository.

    This endpoint:
    1. Deletes the codespace from GitHub
    2. Deletes the associated repo that was created for this codespace
    3. Removes the tracking record from the database
    """
    session = get_session_data(http_request)

    if not session or "access_token" not in session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    access_token = session["access_token"]

    # First, delete the codespace
    await delete_codespace(access_token, codespace_name)

    # Then, find and delete the associated repo
    user_repo = (
        db.query(UserRepo).filter(UserRepo.codespace_name == codespace_name).first()
    )

    if user_repo:
        try:
            await delete_user_repo(
                access_token=access_token,
                github_username=str(user_repo.github_username),
                repo_name=str(user_repo.repo_name),
            )
        except HTTPException as e:
            # Log but don't fail if repo deletion fails
            print(f"Warning: Failed to delete repo {user_repo.repo_name}: {e.detail}")

        # Remove from database regardless
        db.delete(user_repo)
        db.commit()

    return JSONResponse({"status": "deleted", "repo_deleted": user_repo is not None})


@app.get("/auth/logout")
async def logout():
    """Clear session and logout"""
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """User dashboard showing completed problems and active codespaces"""
    session = get_session_data(request)

    if not session or "user_id" not in session:
        return RedirectResponse(url="/auth/login", status_code=302)

    user_id = session["user_id"]

    # Get completed problems for this user
    completed = (
        db.query(CompletedProblem)
        .filter(CompletedProblem.user_id == user_id)
        .order_by(CompletedProblem.completed_at.desc())
        .all()
    )

    # Match with problem details from database
    completed_problems = []
    for cp in completed:
        problem = db.query(Problem).filter(Problem.id == cp.problem_id).first()
        if problem:
            completed_problems.append(
                {
                    "id": problem.id,
                    "title": problem.title,
                    "difficulty": problem.difficulty,
                    "completed_at": cp.completed_at,
                }
            )

    # Stats - use completed_problems (which only includes valid problems from database)
    stats = {
        "total": len(completed_problems),
        "easy": len([p for p in completed_problems if p["difficulty"] == "Easy"]),
        "medium": len([p for p in completed_problems if p["difficulty"] == "Medium"]),
        "hard": len([p for p in completed_problems if p["difficulty"] == "Hard"]),
    }

    # Get active codespaces
    codespaces = []
    if session.get("access_token"):
        try:
            codespaces = await list_user_codespaces(session["access_token"])
            # Enrich with problem titles from database
            for cs in codespaces:
                problem = (
                    db.query(Problem).filter(Problem.id == cs["problem_id"]).first()
                )
                cs["problem_title"] = problem.title if problem else cs["problem_id"]
        except Exception:
            # If fetching codespaces fails, continue without them
            pass

    # Get total problem count from database
    total_problems = db.query(Problem).filter(Problem.is_active.is_(True)).count()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": session.get("user"),
            "logged_in": True,
            "completed_problems": completed_problems,
            "stats": stats,
            "total_problems": total_problems,
            "codespaces": codespaces,
        },
    )


@app.post("/problems/{problem_id}/complete")
async def mark_complete(
    problem_id: str, request: Request, db: Session = Depends(get_db)
):
    """Mark a problem as completed"""
    session = get_session_data(request)

    if not session or "user_id" not in session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = session["user_id"]

    # Check if already completed
    existing = (
        db.query(CompletedProblem)
        .filter(
            CompletedProblem.user_id == user_id,
            CompletedProblem.problem_id == problem_id,
        )
        .first()
    )

    if existing:
        return JSONResponse({"status": "already_completed"})

    # Add completion
    completion = CompletedProblem(user_id=user_id, problem_id=problem_id)
    db.add(completion)
    db.commit()

    return JSONResponse({"status": "completed"})


@app.delete("/problems/{problem_id}/complete")
async def unmark_complete(
    problem_id: str, request: Request, db: Session = Depends(get_db)
):
    """Remove completion status from a problem"""
    session = get_session_data(request)

    if not session or "user_id" not in session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = session["user_id"]

    # Delete completion
    db.query(CompletedProblem).filter(
        CompletedProblem.user_id == user_id, CompletedProblem.problem_id == problem_id
    ).delete()
    db.commit()

    return JSONResponse({"status": "removed"})


@app.put("/user/preferences/hide-completed")
async def update_hide_completed(request: Request, db: Session = Depends(get_db)):
    """Update user's hide_completed preference"""
    session = get_session_data(request)

    if not session or "user_id" not in session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = session["user_id"]

    # Parse request body
    body = await request.json()
    hide_completed = body.get("hide_completed", False)

    # Update user preference
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.hide_completed = hide_completed
        db.commit()

    return JSONResponse({"status": "updated", "hide_completed": hide_completed})


class TokenCompleteRequest(BaseModel):
    token: str


@app.post("/api/complete")
async def complete_with_token(
    request: TokenCompleteRequest, db: Session = Depends(get_db)
):
    """Mark a problem as completed using a codespace token.

    This endpoint is called from within a codespace (e.g., by mark-complete.sh).
    It validates the token and marks the associated problem as complete for the user.

    The token was injected as a secret when the codespace was created.
    """
    # Find the token
    token_record = (
        db.query(CodespaceToken).filter(CodespaceToken.token == request.token).first()
    )

    if not token_record:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Check if token has expired
    # Handle both timezone-aware and naive datetimes from database
    now = datetime.now(UTC)
    expires_at = token_record.expires_at
    if expires_at.tzinfo is None:
        # If database returns naive datetime, assume it's UTC
        expires_at = expires_at.replace(tzinfo=UTC)
    if now > expires_at:
        raise HTTPException(status_code=401, detail="Token has expired")

    # Check if already used (optional: allow multiple uses)
    # if token_record.used:
    #     raise HTTPException(status_code=400, detail="Token already used")

    # Check if already completed
    existing = (
        db.query(CompletedProblem)
        .filter(
            CompletedProblem.user_id == token_record.user_id,
            CompletedProblem.problem_id == token_record.problem_id,
        )
        .first()
    )

    if existing:
        return JSONResponse(
            {
                "status": "already_completed",
                "problem_id": token_record.problem_id,
            }
        )

    # Mark as completed
    completion = CompletedProblem(
        user_id=token_record.user_id,
        problem_id=token_record.problem_id,
    )
    db.add(completion)

    # Mark token as used
    token_record.used = True
    db.commit()

    return JSONResponse(
        {
            "status": "completed",
            "problem_id": token_record.problem_id,
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
