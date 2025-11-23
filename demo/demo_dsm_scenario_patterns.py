#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ****************************************************************************************************************************************************
# * BSD 3-Clause License
# *
# * Copyright (c) 2025, Mana Battery
# * All rights reserved.
# *
# * Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
# *
# * 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
# * 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the
# *    documentation and/or other materials provided with the distribution.
# * 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this
# *    software without specific prior written permission.
# *
# * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# * THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# * PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# * LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
# * EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# ****************************************************************************************************************************************************
"""Demo: DSM Scenario Patterns with Baseline Comparison

This demo demonstrates DSM baseline comparison by creating git repositories for each
architectural scenario and running buildCheckDSM.py --load-baseline on them. This shows
how the tool performs differential analysis between a saved baseline and current state.

Key Features:
- Creates temporary git repositories with baseline at HEAD
- Saves baseline DSM results to compressed file
- Makes scenario changes in working tree and commits them
- Runs buildCheckDSM.py --load-baseline to show differential analysis
- Shows authentic architectural insights output
- Cleans up temporary repositories automatically

Usage:
    python demo/demo_dsm_scenario_patterns.py [--verbose]

Options:
    --verbose    Enable verbose output from buildCheckDSM.py

Output:
    For each scenario, displays:
    - Scenario header with ID and name
    - Expected architectural patterns (description)
    - Actual buildCheckDSM.py --load-baseline output
    - Architectural insights with statistics and recommendations
    - Success/failure status

Exit Status:
    0: All scenarios executed successfully
    1: One or more scenarios failed (details reported)
"""

import sys
import subprocess
import tempfile
import argparse
from pathlib import Path

# Add parent directory to path to import lib modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.scenario_creators import create_git_repo_from_scenario
from lib.scenario_definitions import ALL_SCENARIOS, print_scenario_header, print_scenario_summary
from lib.color_utils import Colors


def run_dsm_scenario(scenario_id: int, buildcheck_dsm_path: str, verbose: bool = False) -> bool:
    """
    Execute DSM baseline comparison for a single scenario.

    Creates a physical git repository with the scenario, saves baseline,
    commits changes, then runs buildCheckDSM.py --load-baseline to show
    differential analysis.

    Args:
        scenario_id: The scenario identifier from ALL_SCENARIOS (1-10)
        buildcheck_dsm_path: Path to buildCheckDSM.py script
        verbose: If True, enable verbose output from buildCheckDSM.py

    Returns:
        True if scenario executed successfully, False on error

    Raises:
        No exceptions - all errors are caught and reported
    """
    try:
        scenario = ALL_SCENARIOS[scenario_id]

        # Print scenario header and expected patterns
        print_scenario_header(scenario_id, scenario.name)
        print_scenario_summary(scenario_id)
        print()

        # Create temporary directory for git repository
        with tempfile.TemporaryDirectory(prefix=f"demo_dsm_{scenario_id}_") as tmpdir:
            repo_path = Path(tmpdir)
            baseline_file = repo_path / "baseline.dsm.json.gz"

            if verbose:
                print(f"{Colors.CYAN}Creating git repository with baseline at {repo_path}{Colors.RESET}")

            # Create git repository with baseline committed
            create_git_repo_from_scenario(
                scenario_id=scenario_id, repo_path=str(repo_path), baseline_as_head=True, current_as_working=False  # Don't leave changes uncommitted yet
            )

            if verbose:
                print(f"{Colors.CYAN}Saving baseline with --save-results{Colors.RESET}")

            # Save baseline DSM results
            save_cmd = [sys.executable, buildcheck_dsm_path, str(repo_path), "--save-results", str(baseline_file)]

            result = subprocess.run(save_cmd, capture_output=True, text=True, cwd=str(repo_path))

            if result.returncode != 0:
                print(f"{Colors.RED}Failed to save baseline{Colors.RESET}")
                if verbose and result.stderr:
                    print(result.stderr)
                return False

            if verbose:
                print(f"{Colors.CYAN}Applying scenario changes and committing{Colors.RESET}")

            # Now apply the scenario changes
            create_git_repo_from_scenario(
                scenario_id=scenario_id,
                repo_path=str(repo_path),
                baseline_as_head=False,  # Baseline already at HEAD
                current_as_working=True,  # Apply changes to working tree
            )

            # Commit the changes
            subprocess.run(["git", "add", "-A"], cwd=str(repo_path), capture_output=True)
            subprocess.run(["git", "commit", "-m", f"Apply scenario {scenario_id} changes"], cwd=str(repo_path), capture_output=True)

            if verbose:
                print(f"{Colors.CYAN}Running buildCheckDSM.py --load-baseline{Colors.RESET}")

            # Run buildCheckDSM.py --load-baseline
            analyze_cmd = [sys.executable, buildcheck_dsm_path, str(repo_path), "--load-baseline", str(baseline_file)]

            if verbose:
                analyze_cmd.append("--verbose")

            result = subprocess.run(analyze_cmd, capture_output=True, text=True, cwd=str(repo_path))

            # Display the actual tool output
            print(result.stdout)

            if result.stderr and verbose:
                print(f"{Colors.YELLOW}Stderr:{Colors.RESET}")
                print(result.stderr)

            print()

            if result.returncode == 0:
                print(f"{Colors.GREEN}✓ Scenario {scenario_id}: Completed successfully{Colors.RESET}")
            else:
                print(f"{Colors.RED}✗ Scenario {scenario_id}: buildCheckDSM.py exited with code {result.returncode}{Colors.RESET}")
                return False

            print()
            print(f"{Colors.CYAN}{'=' * 80}{Colors.RESET}")
            print()

            return result.returncode == 0

    except Exception as e:
        print()
        print(f"{Colors.RED}✗ Scenario {scenario_id} FAILED: {str(e)}{Colors.RESET}")
        if verbose:
            import traceback

            traceback.print_exc()
        print()
        print(f"{Colors.CYAN}{'=' * 80}{Colors.RESET}")
        print()
        return False


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Demo: DSM Scenario Patterns with Baseline Comparison",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run all scenarios with standard output
    python demo/demo_dsm_scenario_patterns.py
    
    # Run with verbose output for debugging
    python demo/demo_dsm_scenario_patterns.py --verbose

This demo creates physical git repositories for each predefined architectural
scenario, saves a baseline, applies changes, then runs buildCheckDSM.py 
--load-baseline to demonstrate differential analysis with architectural insights.
Each scenario shows statistical analysis, ripple impact, and severity-based
recommendations.
""",
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose output from buildCheckDSM.py")

    return parser.parse_args()


def main():
    """
    Main entry point for DSM scenario patterns demo.

    Runs all predefined architectural scenarios through DSM baseline comparison,
    continuing on errors to report all failures. Provides summary of results
    at the end.

    Returns:
        Exit code: 0 for success, 1 if any scenarios failed
    """
    args = parse_args()

    # Find buildCheckDSM.py (should be in parent directory)
    script_dir = Path(__file__).parent.parent
    buildcheck_dsm = script_dir / "buildCheckDSM.py"

    if not buildcheck_dsm.exists():
        print(f"{Colors.RED}Error: buildCheckDSM.py not found at {buildcheck_dsm}{Colors.RESET}")
        return 1

    print()
    print(f"{Colors.CYAN}{Colors.BRIGHT}DSM Scenario Patterns Demo{Colors.RESET}")
    print(f"{Colors.CYAN}{'=' * 80}{Colors.RESET}")
    print()
    print("This demo demonstrates DSM baseline comparison using predefined architectural")
    print("scenarios. Each scenario creates a git repository, saves a baseline, applies")
    print("changes, then runs buildCheckDSM.py --load-baseline to show differential")
    print("analysis with architectural insights (statistics, ripple impact, recommendations).")
    print()
    print(f"Running {len(ALL_SCENARIOS)} scenarios...")
    print()
    print(f"{Colors.CYAN}{'=' * 80}{Colors.RESET}")
    print()

    # Track results
    passed = []
    failed = []

    # Run all scenarios, continuing on errors
    for scenario_id in ALL_SCENARIOS.keys():
        success = run_dsm_scenario(scenario_id, str(buildcheck_dsm), verbose=args.verbose)
        if success:
            passed.append(scenario_id)
        else:
            failed.append(scenario_id)

    # Print summary
    print()
    print(f"{Colors.CYAN}{Colors.BRIGHT}Summary{Colors.RESET}")
    print(f"{Colors.CYAN}{'=' * 80}{Colors.RESET}")
    print()
    print(f"Total scenarios: {len(ALL_SCENARIOS)}")
    print(f"{Colors.GREEN}Passed: {len(passed)}{Colors.RESET}")
    if failed:
        print(f"{Colors.RED}Failed: {len(failed)}{Colors.RESET}")
        print()
        print("Failed scenarios:")
        for scenario_id in failed:
            print(f"  - {scenario_id}: {ALL_SCENARIOS[scenario_id].name}")
    print()

    # Exit with appropriate status
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
