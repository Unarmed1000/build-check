#!/usr/bin/env bash
# ****************************************************************************************************************************************************
# * Test script for buildcheck bash completion
# ****************************************************************************************************************************************************

echo "Testing buildCheck bash completion..."
echo

# Source the completion script from the repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${REPO_ROOT}/buildcheck-completion.bash"

echo "✓ Completion script sourced successfully"
echo

# Check if completion functions are registered
echo "Checking registered completions..."
for cmd in buildCheckSummary buildCheckDSM buildCheckIncludeChains \
           buildCheckDependencyHell buildCheckRippleEffect buildCheckLibraryGraph \
           buildCheckImpact buildCheckIncludeGraph buildCheckOptimize; do
    if complete -p "$cmd" &>/dev/null; then
        echo "  ✓ $cmd"
    else
        echo "  ✗ $cmd - NOT REGISTERED"
        exit 1
    fi
done

echo
echo "✓ All completion functions registered successfully!"
echo
echo "To enable completion in your current shell, run:"
echo "  source buildcheck-completion.bash"
echo
echo "For permanent installation, see BASH_COMPLETION.md"
