#!/bin/bash
# Run mypy type checking on all Python scripts

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Change to project root so imports work correctly
cd "$PROJECT_ROOT" || exit 1
export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"

echo "Running mypy type checking with strict mode..."
echo "================================"

# Run mypy with strict checks and additional warnings
# --strict: Enable all optional error checking flags
# --warn-redundant-casts: Warn about redundant casts
# --warn-unused-ignores: Warn about unused '# type: ignore' comments
# --warn-unreachable: Warn about unreachable code
# --show-error-codes: Show error codes in messages
python3 -m mypy \
    --strict \
    --warn-redundant-casts \
    --warn-unused-ignores \
    --warn-unreachable \
    --show-error-codes \
    "$PROJECT_ROOT"/*.py \
    "$PROJECT_ROOT"/lib/*.py \
    "$PROJECT_ROOT"/test/*.py \
    "$PROJECT_ROOT"/test/internal/*.py

echo "================================"
echo "Mypy type checking completed successfully!"
