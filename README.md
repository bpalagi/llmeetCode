# LLMeetCode

> "Interviews for the modern enterprise" — LLMs allowed, and it's not just memorizing algorithms.

A coding challenge platform where problems look like **Jira tickets**, **Support Requests**, and **Bug Reports** — real-world scenarios instead of abstract puzzles.

## Features

- **Ticket-style problems** — Challenges framed as realistic work tasks
- **Monaco code editor** — VS Code's editor in the browser
- **Instant feedback** — Run code against visible + hidden test cases
- **One chance to deploy** — Like real production, you only get one shot
- **AI assistant** — Chat with Gemini for hints and code review

## Local Development

### Prerequisites

- Python 3.11+

### Setup

```bash
# Clone the repo
git clone https://github.com/bpalagi/llmeetCode.git
cd llmeetCode

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

The app will be available at **http://127.0.0.1:5000**

### Project Structure

```
llmeetCode/
├── app.py                 # Flask application
├── requirements.txt       # Python dependencies
├── data/
│   └── problems.json      # Challenge definitions
└── templates/
    ├── base.html          # Layout
    ├── index.html         # Homepage
    └── challenge.html     # Code editor page
```

## Adding Problems

Edit `data/problems.json` to add new challenges:

```json
{
  "id": "unique-slug",
  "title": "TICKET-123: Problem Title",
  "type": "Jira Ticket",
  "priority": "Medium",
  "reporter": "Name",
  "description": "Markdown description...",
  "starter_code": "def solution():\n    pass",
  "tests": [
    {"input": "solution()", "expected": "True", "hidden": false}
  ]
}
```
