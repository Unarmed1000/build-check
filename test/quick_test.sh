#!/bin/bash
# Quick test runner - runs a subset of fast tests for development

cd "$(dirname "$0")/.."

echo "Running quick tests (unit + security)..."
pytest test/ -v -m "not slow" --tb=short 2>&1 | head -100

echo ""
echo "For full test suite, run: ./test/run_tests.sh"
echo "For coverage report, run: ./test/run_tests.sh --coverage"
