#!/bin/bash
# Run pylint linting on all Python scripts

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Change to project root so imports work correctly
cd "$PROJECT_ROOT" || exit 1
export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"

echo "Running pylint code quality checks..."
echo "================================"

# Check if pylint is available
if ! python3 -c "import pylint" 2>/dev/null; then
    echo "Error: pylint is not installed"
    echo "Install with: pip install pylint"
    exit 1
fi

# Run pylint with project configuration
python3 -m pylint \
    --rcfile="$PROJECT_ROOT/.pylintrc" \
    "$PROJECT_ROOT"/buildCheck*.py \
    "$PROJECT_ROOT"/lib/*.py

echo "================================"
echo "Pylint checking completed successfully!"
