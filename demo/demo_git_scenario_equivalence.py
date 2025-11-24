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
"""Demo: Git Impact Analysis with Architectural Scenarios

This demo demonstrates the git impact analysis capabilities of buildCheckDSM.py
by running all predefined architectural scenarios through physical git repositories.
Each scenario is created as a git repo with baseline at HEAD and changes as uncommitted
working tree modifications, then analyzed by calling buildCheckDSM.py --git-impact.

Key Features:
- Creates physical git repositories for each scenario using scenario_creators
- Calls buildCheckDSM.py --git-impact to show authentic tool output
- Demonstrates real-world usage of git working tree analysis
- Continues on errors to report all failures
- Cleans up temporary repositories automatically

Usage:
    python demo/demo_git_impact.py [--verbose]

Options:
    --verbose    Enable verbose output from buildCheckDSM.py

Output:
    For each scenario, displays:
    - Scenario header with ID and name
    - Expected architectural patterns (description)
    - Actual buildCheckDSM.py --git-impact output
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


def run_git_scenario(scenario_id: int, buildcheck_dsm_path: str, verbose: bool = False) -> bool:
    """
    Execute git-based DSM analysis for a single scenario.

    Creates a physical git repository with the scenario baseline at HEAD and
    changes as uncommitted modifications in the working tree, then calls
    buildCheckDSM.py --git-impact to analyze it.

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
        with tempfile.TemporaryDirectory(prefix=f"demo_git_{scenario_id}_") as tmpdir:
            repo_path = Path(tmpdir)

            if verbose:
                print(f"{Colors.CYAN}Creating git repository at {repo_path}{Colors.RESET}")

            # Create git repository with scenario
            create_git_repo_from_scenario(scenario_id=scenario_id, repo_path=str(repo_path), baseline_as_head=True, current_as_working=True)

            if verbose:
                print(f"{Colors.CYAN}Calling buildCheckDSM.py --git-impact{Colors.RESET}")

            # Call buildCheckDSM.py --git-impact on the repository
            cmd = [sys.executable, buildcheck_dsm_path, str(repo_path), "--git-impact"]

            if verbose:
                cmd.append("--verbose")

            # Run buildCheckDSM.py and capture output
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_path))

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
        description="Demo: Git Impact Analysis with Architectural Scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run all scenarios with standard output
    python demo/demo_git_impact.py
    
    # Run specific scenarios only
    python demo/demo_git_impact.py -s 1 -s 3 -s 5
    python demo/demo_git_impact.py --scenario 10
    
    # Run with verbose output for debugging
    python demo/demo_git_impact.py --verbose

This demo creates physical git repositories for each predefined architectural
scenario and analyzes them using buildCheckDSM.py --git-impact. Each scenario
demonstrates different architectural patterns (regressions, improvements,
trade-offs, etc.) that can be detected through dependency analysis.
""",
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose output from buildCheckDSM.py")
    parser.add_argument(
        "-s",
        "--scenario",
        type=int,
        action="append",
        dest="scenarios",
        metavar="ID",
        help="Run specific scenario(s) by ID. Can be specified multiple times. If not provided, runs all scenarios.",
    )

    return parser.parse_args()


def main():
    """
    Main entry point for git impact demo.

    Runs all predefined architectural scenarios through git-based DSM analysis,
    continuing on errors to report all failures. Provides summary of results
    at the end.

    Returns:
        Exit code: 0 for success, 1 if any scenarios failed
    """
    args = parse_args()

    # Determine which scenarios to run
    if args.scenarios:
        # Validate scenario IDs
        invalid_scenarios = [sid for sid in args.scenarios if sid not in ALL_SCENARIOS]
        if invalid_scenarios:
            print(f"{Colors.RED}Error: Invalid scenario ID(s): {', '.join(map(str, invalid_scenarios))}{Colors.RESET}")
            print(f"Valid scenario IDs: {', '.join(map(str, sorted(ALL_SCENARIOS.keys())))}")
            return 1
        scenarios_to_run = sorted(args.scenarios)
    else:
        scenarios_to_run = sorted(ALL_SCENARIOS.keys())

    # Find buildCheckDSM.py (should be in parent directory)
    script_dir = Path(__file__).parent.parent
    buildcheck_dsm = script_dir / "buildCheckDSM.py"

    if not buildcheck_dsm.exists():
        print(f"{Colors.RED}Error: buildCheckDSM.py not found at {buildcheck_dsm}{Colors.RESET}")
        return 1

    print()
    print(f"{Colors.CYAN}{Colors.BRIGHT}Git Impact Analysis Demo{Colors.RESET}")
    print(f"{Colors.CYAN}{'=' * 80}{Colors.RESET}")
    print()
    print("This demo demonstrates git-based DSM impact analysis using predefined")
    print("architectural scenarios. Each scenario creates a physical git repository")
    print("with baseline at HEAD and changes in the working tree, then runs")
    print("buildCheckDSM.py --git-impact to analyze the architectural impact.")
    print()
    if args.scenarios:
        print(f"Running {len(scenarios_to_run)} selected scenario(s): {', '.join(map(str, scenarios_to_run))}")
    else:
        print(f"Running all {len(scenarios_to_run)} scenarios...")
    print()
    print(f"{Colors.CYAN}{'=' * 80}{Colors.RESET}")
    print()

    # Track results
    passed = []
    failed = []

    # Run selected scenarios, continuing on errors
    for scenario_id in scenarios_to_run:
        success = run_git_scenario(scenario_id, str(buildcheck_dsm), verbose=args.verbose)
        if success:
            passed.append(scenario_id)
        else:
            failed.append(scenario_id)

    # Print summary
    print()
    print(f"{Colors.CYAN}{Colors.BRIGHT}Summary{Colors.RESET}")
    print(f"{Colors.CYAN}{'=' * 80}{Colors.RESET}")
    print()
    print(f"Total scenarios run: {len(scenarios_to_run)}")
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
