#!/bin/bash
# BuildCheck Environment Validation Script
# Validates that all non-test required dependencies are available

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

echo ""

# Run Python verification for all other packages
if [ "$CRITICAL_MISSING" = false ]; then
    cd "$SCRIPT_DIR"
    python3 -m lib.package_verification --check-all
    PYTHON_EXIT=$?
    
    if [ $PYTHON_EXIT -ne 0 ]; then
        CRITICAL_MISSING=true
    fi
fi

# Check ninja (optional but useful)
echo -n "✓ Checking ninja... "
NINJA_FOUND=false
# Try different ways to find ninja
if command -v ninja >/dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
    NINJA_FOUND=true
elif command -v ninja-build >/dev/null 2>&1; then
    echo -e "${GREEN}OK (ninja-build)${NC}"
    NINJA_FOUND=true
elif [ -x /usr/bin/ninja ]; then
    echo -e "${GREEN}OK (/usr/bin/ninja)${NC}"
    NINJA_FOUND=true
elif [ -x /usr/local/bin/ninja ]; then
    echo -e "${GREEN}OK (/usr/local/bin/ninja)${NC}"
    NINJA_FOUND=true
fi

if [ "$NINJA_FOUND" = false ]; then
    echo -e "${YELLOW}MISSING (optional, needed for ninja build analysis)${NC}"
    OPTIONAL_MISSING+=("ninja")
fi

# Check clang-scan-deps (optional)
echo -n "✓ Checking clang-scan-deps... "
if command -v clang-scan-deps >/dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    # Try to find any version
    FOUND=false
    for version in 19 18 17 16 15 14 13 12; do
        if command -v clang-scan-deps-$version >/dev/null 2>&1; then
            echo -e "${GREEN}OK (clang-scan-deps-$version)${NC}"
            FOUND=true
            break
        fi
    done
    if [ "$FOUND" = false ]; then
        echo -e "${YELLOW}MISSING (optional, for C++ dependency scanning)${NC}"
        OPTIONAL_MISSING+=("clang-scan-deps")
    fi
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
