#!/bin/bash

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    NEED_INSTALL=1
fi

# Install dependencies only if venv was just created or explicitly requested
if [ "$NEED_INSTALL" = "1" ] || [ "$1" = "--install" ] || ! .venv/bin/python -c "import fastapi, pytest" 2>/dev/null; then
    .venv/bin/pip install -q -r requirements.txt -r requirements-test.txt
fi

# Run tests with coverage
.venv/bin/pytest --cov=app --cov-report=html --cov-report=term-missing "$@"

open htmlcov/index.html
