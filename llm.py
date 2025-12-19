"""Gemini LLM client wrapper for chat functionality."""
import os
from google import genai

# Initialize client
client = None

def get_client():
    """Get or create the Gemini client."""
    global client
    if client is None:
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        client = genai.Client(api_key=api_key)
    return client

def build_system_prompt(problem, current_code):
    """Build the system prompt with problem context."""
    return f"""You are a helpful coding assistant helping a developer solve a programming problem.
This is an "LLM allowed" interview - the candidate gets ONE chance to deploy their solution to production.

## Problem: {problem['title']}
Type: {problem['type']}
Priority: {problem['priority']}

## Description:
{problem['description']}

## Test Cases:
{format_test_cases(problem['tests'])}

## Current Code:
```python
{current_code}
```

## Guidelines:
- Help the user understand the problem and guide them toward a solution
- Provide hints and explanations rather than complete solutions unless asked
- If sharing code, use markdown code blocks
- Be concise and focused on the coding task
- If the user's code has bugs, help them identify and fix the issues
- Remember: they only get ONE deployment attempt, so help them be confident before deploying
"""

def format_test_cases(tests):
    """Format test cases for the prompt."""
    visible_tests = [t for t in tests if not t.get('hidden', False)]
    lines = []
    for i, test in enumerate(visible_tests, 1):
        lines.append(f"Test {i}: {test['input']} → {test['expected']}")
    hidden_count = len(tests) - len(visible_tests)
    if hidden_count > 0:
        lines.append(f"(+ {hidden_count} hidden tests)")
    return '\n'.join(lines)

def chat(problem, current_code, user_message, chat_history=None):
    """Send a chat message and get a response from Gemini.
    
    Args:
        problem: The problem dict with title, description, tests, etc.
        current_code: The user's current code in the editor
        user_message: The user's chat message
        chat_history: List of previous messages [{"role": "user"|"model", "content": "..."}]
    
    Returns:
        dict with 'response' (str) and 'error' (str or None)
    """
    try:
        gemini_client = get_client()
        
        # Build the conversation contents
        system_prompt = build_system_prompt(problem, current_code)
        
        # Build contents array for the API
        contents = []
        
        # Add system context as first user message
        contents.append({
            "role": "user",
            "parts": [{"text": system_prompt + "\n\nPlease acknowledge you understand the problem context."}]
        })
        contents.append({
            "role": "model", 
            "parts": [{"text": "I understand the problem. I'm ready to help you work through it. What would you like to discuss?"}]
        })
        
        # Add chat history
        if chat_history:
            for msg in chat_history:
                contents.append({
                    "role": msg["role"],
                    "parts": [{"text": msg["content"]}]
                })
        
        # Add current user message
        contents.append({
            "role": "user",
            "parts": [{"text": user_message}]
        })
        
        # Call Gemini API
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents
        )
        
        return {
            "response": response.text,
            "error": None
        }
        
    except Exception as e:
        return {
            "response": None,
            "error": str(e)
        }

def chat_stream(problem, current_code, user_message, chat_history=None):
    """Stream a chat response from Gemini.
    
    Yields chunks of the response text as they arrive.
    """
    try:
        gemini_client = get_client()
        
        # Build the conversation contents
        system_prompt = build_system_prompt(problem, current_code)
        
        # Build contents array for the API
        contents = []
        
        # Add system context as first user message
        contents.append({
            "role": "user",
            "parts": [{"text": system_prompt + "\n\nPlease acknowledge you understand the problem context."}]
        })
        contents.append({
            "role": "model", 
            "parts": [{"text": "I understand the problem. I'm ready to help you work through it. What would you like to discuss?"}]
        })
        
        # Add chat history
        if chat_history:
            for msg in chat_history:
                contents.append({
                    "role": msg["role"],
                    "parts": [{"text": msg["content"]}]
                })
        
        # Add current user message
        contents.append({
            "role": "user",
            "parts": [{"text": user_message}]
        })
        
        # Call Gemini API with streaming
        response = gemini_client.models.generate_content_stream(
            model="gemini-2.5-flash",
            contents=contents
        )
        
        for chunk in response:
            if chunk.text:
                yield chunk.text
                
    except Exception as e:
        yield f"[ERROR] {str(e)}"

def complete(problem, code_before_cursor, code_after_cursor):
    """Generate code completion suggestions.
    
    Args:
        problem: The problem dict with title, description, tests, etc.
        code_before_cursor: Code text before the cursor position
        code_after_cursor: Code text after the cursor position
    
    Returns:
        dict with 'completion' (str) and 'error' (str or None)
    """
    try:
        gemini_client = get_client()
        
        prompt = f"""You are a code completion assistant. Complete the Python code at the cursor position.

## Problem Context: {problem['title']}
{problem['description']}

## Code before cursor:
```python
{code_before_cursor}
```

## Code after cursor:
```python
{code_after_cursor}
```

## Instructions:
- Provide ONLY the code that should be inserted at the cursor position
- Do not include any explanation, markdown formatting, or code fences
- The completion should logically continue from the code before the cursor
- Keep completions concise (1-3 lines typically)
- If the cursor is at the end of a line, complete that line or add the next logical line
"""
        
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        
        # Clean up the response - remove any markdown formatting
        completion = response.text.strip()
        if completion.startswith("```"):
            lines = completion.split('\n')
            completion = '\n'.join(lines[1:-1] if lines[-1] == '```' else lines[1:])
        
        return {
            "completion": completion,
            "error": None
        }
        
    except Exception as e:
        return {
            "completion": None,
            "error": str(e)
        }
