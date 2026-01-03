import os
import secrets
from contextlib import asynccontextmanager
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

from .database import CompletedProblem, User, get_db, init_db

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
TEMPLATE_REPO = os.getenv("TEMPLATE_REPO", "llmeet/problem-template")

# Session management
serializer = URLSafeTimedSerializer(SECRET_KEY)

# Templates
templates = Jinja2Templates(directory="app/templates")

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Sample problems data
SAMPLE_PROBLEMS = [
    {
        "id": "two-sum",
        "title": "Two Sum",
        "difficulty": "Easy",
        "description": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
        "topics": ["Array", "Hash Table"],
        "language": "Python",
    },
    {
        "id": "merge-sorted",
        "title": "Merge Sorted Arrays",
        "difficulty": "Medium",
        "description": "Given two sorted integer arrays nums1 and nums2, merge nums2 into nums1 as one sorted array.",
        "topics": ["Array", "Two Pointers"],
        "language": "Python",
    },
    {
        "id": "binary-tree-inorder",
        "title": "Binary Tree Inorder Traversal",
        "difficulty": "Easy",
        "description": "Given the root of a binary tree, return the inorder traversal of its nodes' values.",
        "topics": ["Tree", "Depth-First Search"],
        "language": "Python",
    },
    {
        "id": "validate-binary-tree",
        "title": "Validate Binary Search Tree",
        "difficulty": "Medium",
        "description": "Given the root of a binary tree, determine if it is a valid binary search tree.",
        "topics": ["Tree", "Binary Search Tree"],
        "language": "Java",
    },
    {
        "id": "longest-palindromic-substring",
        "title": "Longest Palindromic Substring",
        "difficulty": "Hard",
        "description": "Given a string s, return the longest palindromic substring in s.",
        "topics": ["String", "Dynamic Programming"],
        "language": "Python",
    },
    {
        "id": "coin-change",
        "title": "Coin Change",
        "difficulty": "Medium",
        "description": "You are given an integer array coins representing coins of different denominations and an integer amount. Return the fewest number of coins that you need to make up that amount.",
        "topics": ["Array", "Dynamic Programming", "Breadth-First Search"],
        "language": "JavaScript",
    },
    {
        "id": "merge-k-sorted-lists",
        "title": "Merge K Sorted Lists",
        "difficulty": "Hard",
        "description": "You are given an array of k linked-lists lists, each linked-list is sorted in ascending order. Merge all the linked-lists into one sorted linked-list.",
        "topics": ["Linked List", "Divide and Conquer", "Heap"],
        "language": "Python",
    },
    {
        "id": "reverse-linked-list",
        "title": "Reverse Linked List",
        "difficulty": "Easy",
        "description": "Given the head of a singly linked list, reverse the list, and return the reversed list.",
        "topics": ["Linked List"],
        "language": "Java",
    },
]


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


async def create_codespace(access_token: str, problem_id: str) -> dict:
    """Create a GitHub Codespace for the given problem"""

    # Validate problem ID exists
    problem = next((p for p in SAMPLE_PROBLEMS if p["id"] == problem_id), None)
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient() as client:
        # First, get the repository ID from the repository name
        repo_response = await client.get(
            f"https://api.github.com/repos/{TEMPLATE_REPO}", headers=headers
        )

        if repo_response.status_code != 200:
            error_detail = repo_response.json().get("message", "Unknown error")
            raise HTTPException(
                status_code=500, detail=f"Failed to get repository info: {error_detail}"
            )

        repo_data = repo_response.json()
        repository_id = repo_data["id"]
        default_branch = repo_data.get("default_branch")

        if not default_branch:
            raise HTTPException(
                status_code=500,
                detail="Repository has no branches. Please initialize the repository with at least a README file and a commit.",
            )

        # Get available machine types for this repository
        machines_response = await client.get(
            f"https://api.github.com/repos/{TEMPLATE_REPO}/codespaces/machines",
            headers=headers,
        )

        machine_type = "basicLinux32gb"  # Default to a known valid machine type

        if machines_response.status_code == 200:
            machines = machines_response.json()
            if machines and "machines" in machines and len(machines["machines"]) > 0:
                machine_type = machines["machines"][0]["name"]

        # Codespace configuration
        codespace_data = {
            "repository_id": repository_id,
            "ref": default_branch,
            "location": "WestUs2",
            "machine": machine_type,  # Use the fetched machine type
            "devcontainer_path": ".devcontainer/devcontainer.json",
            "display_name": f"llmeetcode-{problem_id}-{secrets.token_hex(4)}",
            "idle_timeout_minutes": 30,
        }

        # Create the codespace
        response = await client.post(
            "https://api.github.com/user/codespaces",
            json=codespace_data,
            headers=headers,
        )

        if response.status_code != 201:
            error_data = response.json()
            print(f"GitHub API Error Response: {error_data}")  # Debug print
            error_detail = error_data.get("message", "Unknown error")
            raise HTTPException(
                status_code=500, detail=f"Failed to create codespace: {error_detail}"
            )

        codespace = response.json()

        # Return the codespace info immediately, even if still provisioning
        return {
            "name": codespace["name"],
            "web_url": codespace.get(
                "web_url", f"https://github.com/codespaces/{codespace['name']}"
            ),
            "state": codespace.get("state", "Unknown"),
            "created_at": codespace.get("created_at"),
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


@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    db: Session = Depends(get_db),
    difficulty: str | None = None,
    topic: str | None = None,
    language: str | None = None,
    hide_completed: str | None = None,
):
    """Main page listing coding problems"""
    session = get_session_data(request)

    # Parse hide_completed as boolean
    hide_completed_bool = hide_completed == "true"

    # Get completed problem IDs for logged in user
    completed_ids = set()
    active_codespaces = {}  # Maps problem_id -> codespace web_url
    if session and "user_id" in session:
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

    # Filter problems based on query parameters
    filtered_problems = SAMPLE_PROBLEMS.copy()

    if difficulty and difficulty != "All Difficulties":
        filtered_problems = [
            p for p in filtered_problems if p["difficulty"] == difficulty
        ]

    if topic and topic != "All Topics":
        filtered_problems = [p for p in filtered_problems if topic in p["topics"]]

    if language and language != "All Languages":
        filtered_problems = [p for p in filtered_problems if p["language"] == language]

    # Hide completed problems if requested
    if hide_completed_bool and completed_ids:
        filtered_problems = [
            p for p in filtered_problems if p["id"] not in completed_ids
        ]

    # Get unique values for filter options
    all_difficulties = sorted({p["difficulty"] for p in SAMPLE_PROBLEMS})
    all_topics = sorted({topic for p in SAMPLE_PROBLEMS for topic in p["topics"]})
    all_languages = sorted({p["language"] for p in SAMPLE_PROBLEMS})

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
            "selected_topic": topic or "All Topics",
            "selected_language": language or "All Languages",
            "all_difficulties": all_difficulties,
            "all_topics": all_topics,
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
        f"scope=codespace user:email"
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
async def create_codespace_endpoint(request: CodespaceRequest, http_request: Request):
    """Create a new codespace for a problem"""
    session = get_session_data(http_request)

    if not session or "access_token" not in session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        codespace_info = await create_codespace(
            session["access_token"], request.problem_id
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
):
    """Delete a codespace by name"""
    session = get_session_data(http_request)

    if not session or "access_token" not in session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    await delete_codespace(session["access_token"], codespace_name)
    return JSONResponse({"status": "deleted"})


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

    # Match with problem details
    completed_problems = []
    for cp in completed:
        problem = next((p for p in SAMPLE_PROBLEMS if p["id"] == cp.problem_id), None)
        if problem:
            completed_problems.append({**problem, "completed_at": cp.completed_at})

    # Stats
    stats = {
        "total": len(completed),
        "easy": len([p for p in completed_problems if p["difficulty"] == "Easy"]),
        "medium": len([p for p in completed_problems if p["difficulty"] == "Medium"]),
        "hard": len([p for p in completed_problems if p["difficulty"] == "Hard"]),
    }

    # Get active codespaces
    codespaces = []
    if session.get("access_token"):
        try:
            codespaces = await list_user_codespaces(session["access_token"])
            # Enrich with problem titles
            for cs in codespaces:
                problem = next(
                    (p for p in SAMPLE_PROBLEMS if p["id"] == cs["problem_id"]), None
                )
                cs["problem_title"] = problem["title"] if problem else cs["problem_id"]
        except Exception:
            # If fetching codespaces fails, continue without them
            pass

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": session.get("user"),
            "logged_in": True,
            "completed_problems": completed_problems,
            "stats": stats,
            "total_problems": len(SAMPLE_PROBLEMS),
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
