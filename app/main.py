from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx
import os
from typing import Optional, Dict, Any
import secrets
from itsdangerous import URLSafeTimedSerializer, BadSignature
import asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="LLMeet - Coding Interview Platform")

# Configuration
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI", "http://localhost:8000/auth/callback")
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
        "language": "Python"
    },
    {
        "id": "merge-sorted",
        "title": "Merge Sorted Arrays",
        "difficulty": "Medium",
        "description": "Given two sorted integer arrays nums1 and nums2, merge nums2 into nums1 as one sorted array.",
        "topics": ["Array", "Two Pointers"],
        "language": "Python"
    }
]

class CodespaceRequest(BaseModel):
    problem_id: str
    language: str = "python"

def get_session_data(request: Request) -> Dict[str, Any]:
    """Get session data from encrypted cookie"""
    session_token = request.cookies.get("session")
    if not session_token:
        return {}
    try:
        return serializer.loads(session_token, max_age=3600)  # 1 hour expiry
    except BadSignature:
        return {}

async def create_codespace(access_token: str, problem_id: str) -> str:
    """Create a GitHub Codespace for the given problem"""
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    async with httpx.AsyncClient() as client:
        # First, get the repository ID from the repository name
        repo_response = await client.get(
            f"https://api.github.com/repos/{TEMPLATE_REPO}",
            headers=headers
        )
        
        if repo_response.status_code != 200:
            error_detail = repo_response.json().get("message", "Unknown error")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get repository info: {error_detail}"
            )
        
        repo_data = repo_response.json()
        repository_id = repo_data["id"]
        default_branch = repo_data.get("default_branch")
        
        if not default_branch:
            raise HTTPException(
                status_code=500,
                detail="Repository has no branches. Please initialize the repository with at least a README file and a commit."
            )
        
        # Get available machine types for this repository
        machines_response = await client.get(
            f"https://api.github.com/repos/{TEMPLATE_REPO}/codespaces/machines",
            headers=headers
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
            "machine": machine_type, # Use the fetched machine type
            "devcontainer_path": ".devcontainer/devcontainer.json",
            "display_name": f"llmeet-{problem_id}-{secrets.token_hex(4)}",
            "idle_timeout_minutes": 30
        }
        
        # Create the codespace
        response = await client.post(
            "https://api.github.com/user/codespaces",
            json=codespace_data,
            headers=headers
        )
        
        if response.status_code != 201:
            error_data = response.json()
            print(f"GitHub API Error Response: {error_data}")  # Debug print
            error_detail = error_data.get("message", "Unknown error")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create codespace: {error_detail}"
            )
        
        codespace = response.json()
        codespace_name = codespace["name"]
        
        # Poll for codespace to be ready
        print(f"Waiting for codespace {codespace_name} to be ready...")  # Debug print
        for i in range(60):  # Wait up to 60 seconds (increased from 30)
            await asyncio.sleep(1)
            
            status_response = await client.get(
                f"https://api.github.com/user/codespaces/{codespace_name}",
                headers=headers
            )
            
            if status_response.status_code == 200:
                codespace_status = status_response.json()
                state = codespace_status.get("state")
                print(f"Codespace status (attempt {i+1}/60): {state}")  # Debug print
                if state == "Available":
                    return codespace_status["web_url"]
        
        raise HTTPException(
            status_code=500,
            detail="Codespace creation timed out after 60 seconds"
        )

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Main page listing coding problems"""
    session = get_session_data(request)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "problems": SAMPLE_PROBLEMS,
            "user": session.get("user"),
            "logged_in": bool(session)
        }
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
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
async def auth_callback(code: str):
    """Handle GitHub OAuth callback"""
    
    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code
            },
            headers={"Accept": "application/json"}
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
                "Accept": "application/vnd.github.v3+json"
            }
        )
        
        if user_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info")
        
        user_data = user_response.json()
    
    # Create session
    session_data = {
        "access_token": access_token,
        "user": {
            "login": user_data["login"],
            "name": user_data.get("name"),
            "avatar_url": user_data.get("avatar_url")
        }
    }
    
    session_token = serializer.dumps(session_data)
    
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        "session",
        session_token,
        max_age=3600,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax"
    )
    
    return response

@app.post("/codespaces/create")
async def create_codespace_endpoint(
    request: CodespaceRequest,
    http_request: Request
):
    """Create a new codespace for a problem"""
    session = get_session_data(http_request)
    
    if not session or "access_token" not in session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        codespace_url = await create_codespace(
            session["access_token"],
            request.problem_id
        )
        return {"url": codespace_url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auth/logout")
async def logout():
    """Clear session and logout"""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("session")
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
