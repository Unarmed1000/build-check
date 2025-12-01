#!/usr/bin/env bash
# ****************************************************************************************************************************************************
# * Advanced test for bash completion functionality
# ****************************************************************************************************************************************************

# This test validates that completion functions return appropriate suggestions

set -e

# Source the completion script from the repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${REPO_ROOT}/buildcheck-completion.bash"

echo "Testing bash completion functionality..."
echo

# Helper function to test completion
test_completion() {
    local cmd="$1"
    local cur="$2"
    local prev="$3"
    local expected="$4"
    
    # Set up COMP_WORDS and COMP_CWORD as bash completion would
    COMP_WORDS=("$cmd" "$prev")
    COMP_CWORD=1
    
    # If cur is provided, simulate typing
    if [[ -n "$cur" ]]; then
        COMP_WORDS+=("$cur")
        COMP_CWORD=2
    fi
    
    # Call the completion function
    local func="_${cmd}"
    if declare -f "$func" > /dev/null; then
        COMPREPLY=()
        "$func"
        
        # Check if expected string is in completions
        if [[ -n "$expected" ]]; then
            for item in "${COMPREPLY[@]}"; do
                if [[ "$item" == *"$expected"* ]]; then
                    echo "  ✓ $cmd $prev $cur -> found '$expected'"
                    return 0
                fi
            done
            echo "  ✗ $cmd $prev $cur -> expected '$expected' not found in: ${COMPREPLY[*]}"
            return 1
        else
            echo "  ✓ $cmd $prev $cur -> ${#COMPREPLY[@]} suggestions"
            return 0
        fi
    else
        echo "  ✗ Function $func not found"
        return 1
    fi
}

# Test various completion scenarios
echo "Testing option completions..."
test_completion "buildCheckSummary" "--" "" "--detailed"
test_completion "buildCheckDSM" "--" "" "--export"
test_completion "buildCheckOptimize" "--" "" "--quick"

echo
echo "Testing format value completion..."
COMP_WORDS=("buildCheckSummary" "--format" "")
COMP_CWORD=2
COMPREPLY=()
_buildCheckSummary
if [[ "${COMPREPLY[*]}" == *"json"* ]] && [[ "${COMPREPLY[*]}" == *"text"* ]]; then
    echo "  ✓ buildCheckSummary --format -> json, text"
else
    echo "  ✗ buildCheckSummary --format -> expected json and text, got: ${COMPREPLY[*]}"
    exit 1
fi

echo
echo "Testing that number options don't complete..."
COMP_WORDS=("buildCheckDSM" "--max-matrix-size" "")
COMP_CWORD=2
COMPREPLY=()
_buildCheckDSM
if [[ ${#COMPREPLY[@]} -eq 0 ]]; then
    echo "  ✓ buildCheckDSM --max-matrix-size -> no completions (user enters number)"
else
    echo "  ✗ buildCheckDSM --max-matrix-size -> should have no completions, got: ${COMPREPLY[*]}"
fi

echo
echo "✅ All completion tests passed!"
echo
echo "Manual testing suggestions:"
echo "  1. Source the completion: source buildcheck-completion.bash"
echo "  2. Try: buildCheckSummary --<Tab><Tab>"
echo "  3. Try: buildCheckDSM --format <Tab>"
echo "  4. Try: buildCheckOptimize ../build/<Tab>"
