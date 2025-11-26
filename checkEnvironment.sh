#!/bin/bash
# BuildCheck Environment Validation Script
# Validates that all non-test required dependencies are available

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Change to project root and add to PYTHONPATH so lib module can be imported
cd "$SCRIPT_DIR" || exit 1
export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

echo "🔍 BuildCheck Environment Check"
echo "================================"
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track if any critical dependency is missing
CRITICAL_MISSING=false
OPTIONAL_MISSING=()

# Check Python version (need 3.8+)
echo -n "✓ Checking Python version... "
if python3 --version 2>/dev/null | grep -q "Python 3\.[89]\|Python 3\.[1-9][0-9]"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "  Error: Python 3.8 or higher is required"
    CRITICAL_MISSING=true
fi

# Check colorama separately (truly optional with graceful fallback)
echo -n "✓ Checking colorama... "
if python3 -c "import colorama" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}MISSING (optional, for colored output)${NC}"
    OPTIONAL_MISSING+=("colorama")
fi

# Check numpy (required for statistical analysis)
echo -n "✓ Checking numpy... "
if python3 -c "import numpy" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}MISSING (required for statistical analysis)${NC}"
    CRITICAL_MISSING=true
fi

echo ""

# Run Python verification for all other packages
if [ "$CRITICAL_MISSING" = false ]; then
    python3 -m lib.package_verification --check-all
    PYTHON_EXIT=$?
    
    if [ $PYTHON_EXIT -ne 0 ]; then
        CRITICAL_MISSING=true
    fi
fi

# Check ninja (optional but useful)
echo -n "✓ Checking ninja... "
NINJA_CMD=$(python3 -m lib.tool_detection --find-ninja 2>/dev/null)
if [ -n "$NINJA_CMD" ]; then
    echo -e "${GREEN}OK ($NINJA_CMD)${NC}"
else
    echo -e "${YELLOW}MISSING (optional, needed for ninja build analysis)${NC}"
    OPTIONAL_MISSING+=("ninja")
fi

# Check clang-scan-deps (optional)
echo -n "✓ Checking clang-scan-deps... "
CLANG_SCAN_DEPS_CMD=$(python3 -m lib.tool_detection --find-clang-scan-deps 2>/dev/null)
if [ -n "$CLANG_SCAN_DEPS_CMD" ]; then
    echo -e "${GREEN}OK ($CLANG_SCAN_DEPS_CMD)${NC}"
else
    echo -e "${YELLOW}MISSING (optional, for C++ dependency scanning)${NC}"
    OPTIONAL_MISSING+=("clang-scan-deps")
fi

echo ""
echo "================================"
echo ""

# Summary
if [ "$CRITICAL_MISSING" = true ]; then
    echo -e "${RED}✗ Environment check FAILED${NC}"
    echo "  Critical dependencies are missing. Please install them before using BuildCheck."
    exit 1
else
    echo -e "${GREEN}✓ Environment check PASSED${NC}"
    echo "  All critical dependencies are available."
    
    if [ ${#OPTIONAL_MISSING[@]} -gt 0 ]; then
        echo ""
        echo -e "${YELLOW}⚠ Optional dependencies missing:${NC}"
        for dep in "${OPTIONAL_MISSING[@]}"; do
            echo "  - $dep"
        done
        echo ""
        echo "Install optional dependencies:"
        echo "  pip install -r requirements.txt"
        echo ""
        echo "Install system tools (Ubuntu/Debian):"
        echo "  sudo apt-get install ninja-build clang-tools"
    else
        echo "  All optional dependencies are also available. You're all set!"
    fi
    echo ""
    exit 0
fi
