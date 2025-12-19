# LLM Integration Plan

> Enable LLMs to solve coding problems via chat interface and code completion

---

### 0. Example LLM Call

```
from google import genai

client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))

# Test gemini-3-flash-preview
response = client.models.generate_content(
    model="gemini-3-flash-preview", contents="Explain how AI works in a few words"
)
print(response.text)
```

## Two Integration Options

### 1. Chat Interface (Sidebar/Panel)

A conversational assistant that can discuss the problem, provide hints, and generate code suggestions.

**Implementation:**
- Add a collapsible chat panel to `challenge.html`
- New endpoint: `POST /chat/<problem_id>` that sends problem context + user message to Gemini
- System prompt includes the problem description, test cases, and current code from the editor
- Responses can include code blocks that users can "insert into editor"

### 2. Inline Code Completion (Monaco Integration)

Monaco Editor has built-in support for inline suggestions (like Copilot).

**Implementation:**
- Register a `CompletionItemProvider` with Monaco
- New endpoint: `POST /complete/<problem_id>` for completion requests
- Trigger on typing or via keyboard shortcut (e.g., `Ctrl+Space`)
- Returns code completions based on cursor position + context

---

## Gemini API Setup

```python
# In app.py or llm.py
import google.generativeai as genai

genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-3-flash')  # Free tier friendly
```

**Requirements addition:**
```
google-generativeai>=0.3.0
```

---

## Recommended Starting Point

Start with the **chat interface** because:
1. Simpler to implement and test
2. More aligned with "interview discussion" philosophy from design doc
3. Code completion can be added later as enhancement

---

## Proposed Architecture

```
New Routes:
├── POST /chat/<problem_id>     # Chat with LLM about the problem
├── POST /complete/<problem_id> # (Phase 2) Code completion
└── GET  /chat/history/<id>     # Retrieve chat history

New Files:
├── llm.py                      # Gemini client wrapper
└── templates/partials/
    └── chat_panel.html         # Chat UI component
```

---

## Security Considerations

- **API key**: Store in environment variable (`GEMINI_API_KEY`)
- **Rate limiting**: Consider per-session limits to avoid abuse
- **Prompt injection**: Sanitize user input before sending to LLM

---

## Implementation Phases

### Phase 1: Chat Interface
- [ ] Add `google-generativeai` to requirements.txt
- [ ] Create `llm.py` with Gemini client wrapper
- [ ] Add `/chat/<problem_id>` endpoint to app.py
- [ ] Build chat panel UI in challenge.html
- [ ] Wire up frontend JS to send/receive messages
- [ ] Store chat history in session

### Phase 2: Code Completion
- [ ] Add `/complete/<problem_id>` endpoint
- [ ] Register Monaco `CompletionItemProvider`
- [ ] Configure trigger characters and debouncing
- [ ] Test with various problem types

### Phase 3: Polish
- [ ] Add rate limiting
- [ ] Improve system prompts for better responses
- [ ] Add "insert code" button for chat suggestions
- [ ] Persist chat history across page reloads
