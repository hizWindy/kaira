#!/bin/bash
# Automated publishing workflow for Khaira
# Credentials loaded from environment variables, NEVER from the script

set -e

echo "Building package..."
python -m build

echo "Running tests..."
pytest tests/framework/ -v

echo "Linting..."
ruff check . && ruff format .

echo "Type checking..."
mypy kaira

echo "Publishing to TestPyPI..."
twine upload --repository testpypi dist/*

echo "Installing from TestPyPI..."
pip install --index-url https://test.pypi.org/simple/ khaira[framework]

echo "Publishing to PyPI..."
twine upload dist/*

echo "Verifying..."
pip install khaira[framework]
kaira --version

echo "✅ Published successfully!"
