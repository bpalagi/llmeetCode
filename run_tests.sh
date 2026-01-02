#!/bin/bash

# Create and activate virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# Install test dependencies
pip install -r requirements-test.txt

# Run tests with coverage
pytest --cov=app --cov-report=html --cov-report=term-missing

open htmlcov/index.html
