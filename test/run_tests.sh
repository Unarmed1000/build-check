#!/bin/bash
# Run BuildCheck test suite with various options

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR" || exit 1
export PYTHONPATH="$PROJECT_DIR:${PYTHONPATH:-}"

echo "═══════════════════════════════════════════════════"
echo "  BuildCheck Test Suite"
echo "═══════════════════════════════════════════════════"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "Error: pytest not found. Install with: pip install pytest"
    exit 1
fi

# Parse arguments
COVERAGE=false
VERBOSE=false
PATTERN=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --coverage|-c)
            COVERAGE=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --pattern|-p)
            PATTERN="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -c, --coverage    Generate coverage report"
            echo "  -v, --verbose     Verbose output"
            echo "  -p, --pattern     Run tests matching pattern"
            echo "  -h, --help        Show this help"
            echo ""
            echo "Examples:"
            echo "  $0                          # Run all tests"
            echo "  $0 --coverage               # Run with coverage"
            echo "  $0 --pattern security       # Run security tests only"
            echo "  $0 -c -v                    # Verbose with coverage"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Build pytest command
PYTEST_CMD="pytest test/"

if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -vv"
fi

if [ -n "$PATTERN" ]; then
    PYTEST_CMD="$PYTEST_CMD -k $PATTERN"
fi

if [ "$COVERAGE" = true ]; then
    if ! command -v pytest-cov &> /dev/null; then
        echo "Warning: pytest-cov not found. Install with: pip install pytest-cov"
        echo "Running tests without coverage..."
    else
        PYTEST_CMD="$PYTEST_CMD --cov=. --cov-report=term-missing --cov-report=html"
    fi
fi

echo "Running: $PYTEST_CMD"
echo ""

# Run tests
$PYTEST_CMD

# Show coverage report location if generated
if [ "$COVERAGE" = true ] && [ -d "htmlcov" ]; then
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "Coverage report generated: htmlcov/index.html"
    echo "═══════════════════════════════════════════════════"
fi

echo ""
echo "✓ Tests completed successfully"
