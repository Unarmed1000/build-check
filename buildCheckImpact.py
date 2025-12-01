#!/usr/bin/env python3
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
"""Analyze changed headers and their impact on rebuild targets.

PURPOSE:
    Quick and simple impact analysis tool that identifies which headers are causing
    rebuilds and shows how many compilation targets each header affects.

WHAT IT DOES:
    - Runs 'ninja -n -d explain' to detect what would rebuild
    - Uses 'ninja -t deps' to get dependencies for each target
    - Creates an impact map showing how many targets depend on each header
    - Highlights changed headers and shows their rebuild impact
    - Can optionally show all high-impact headers (not just changed ones)

USE CASES:
    - Quick check after making changes: "What will rebuild and why?"
    - Identify which changed headers have the widest impact
    - Find high-impact headers that should be refactored
    - Fast baseline analysis (no external dependencies required)

METHOD:
    Uses Ninja's built-in dependency tracking (ninja -t deps) which is fast but only
    shows what Ninja already knows from previous builds. Does not parse source files.

OUTPUT:
    - List of changed headers with their target impact count
    - Optional: All high-impact headers sorted by number of affected targets

PERFORMANCE:
    Very fast (typically <1 second) since it only queries Ninja's build graph.

REQUIREMENTS:
    - Python 3.7+
    - ninja build system
    - colorama (optional, for colored output): pip install colorama

COMPLEMENTARY TOOLS:
    - buildCheckIncludeChains.py: Shows header cooccurrence patterns
    - buildCheckIncludeGraph.py: Analyzes gateway headers and .cpp rebuild impact
    - buildCheckDependencyHell.py: Comprehensive multi-metric dependency analysis

EXAMPLES:
    # Show changed headers and their impact
    ./buildCheckImpact.py ../build/release/

    # Show all high-impact headers (not just changed)
    ./buildCheckImpact.py ../build/release/ --all-headers
"""
import subprocess
import re
import os
import sys
import argparse
import logging
from collections import defaultdict
from pathlib import Path
from typing import Set, Dict, List, Tuple

# Import library modules
from lib.color_utils import Colors, print_error, print_warning
from lib.ninja_utils import get_dependencies, validate_build_directory_with_feedback

# RE_OUTPUT constant (kept for local use)
RE_OUTPUT = re.compile(r"ninja explain: (.*)")

# get_dependencies moved to lib.ninja_utils


def build_dependency_impact_map(build_dir: str, rebuild_targets: List[str]) -> Tuple[Dict[str, Set[str]], str, int]:
    """Build a map of which files impact how many rebuild targets.

    Args:
        build_dir: Path to the build directory
        rebuild_targets: List of targets that need rebuilding

    Returns:
        Tuple of (impact_map, project_root, target_count)
    """
    impact_map: Dict[str, Set[str]] = defaultdict(set)

    try:
        project_root = str(Path(build_dir).resolve().parent.parent.parent)
    except Exception as e:
        logging.warning("Could not determine project root: %s", e)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(build_dir)))

    logging.info("Analyzing dependencies for %s rebuild targets...", len(rebuild_targets))

    for idx, target in enumerate(rebuild_targets, 1):
        if idx % 100 == 0:
            logging.debug("Processing target %s/%s", idx, len(rebuild_targets))

        deps = get_dependencies(build_dir, target)

        for dep in deps:
            if dep.endswith((".h", ".hpp", ".hxx")):
                if not dep.startswith("/usr/") and not dep.startswith("/lib/"):
                    impact_map[dep].add(target)

    return impact_map, project_root, len(rebuild_targets)


def main() -> int:
    """Main entry point for the build impact analysis tool.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    parser = argparse.ArgumentParser(
        description="Quick impact analysis: shows how many targets each changed header affects.",
        epilog="""
This tool provides fast, basic impact analysis using Ninja's built-in dependency tracking.
For more detailed analysis, use buildCheckIncludeGraph.py or buildCheckDependencyHell.py.

Typical workflow:
  1. Make changes to header files
  2. Run this tool to see immediate rebuild impact
  3. Use other tools for deeper analysis if needed
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("build_directory", metavar="BUILD_DIR", help="Path to the ninja build directory (e.g., build/release)")

    parser.add_argument("--all-headers", action="store_true", help="Show all high-impact headers, not just changed ones")

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging output")

    parser.add_argument("--limit", type=int, default=20, help="Maximum number of headers to display (default: 20)")

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    # Validate build directory using library helper
    # Skip generated file checks since we only use ninja deps and explain commands
    try:
        build_dir, _ = validate_build_directory_with_feedback(args.build_directory, verbose=args.verbose, skip_generated_files_check=True)
    except (ValueError, RuntimeError):
        # Error message already printed by helper
        return 1

    # Check if ninja is available
    try:
        subprocess.run(["ninja", "--version"], capture_output=True, check=True, timeout=5)
    except FileNotFoundError:
        logging.error("Ninja build system not found. Please install ninja.")
        return 1
    except subprocess.CalledProcessError:
        logging.error("Failed to execute ninja. Please check your installation.")
        return 1
    except subprocess.TimeoutExpired:
        logging.error("Ninja command timed out.")
        return 1

    # Store original directory to restore later
    original_dir = os.getcwd()

    try:
        os.chdir(build_dir)
    except PermissionError:
        logging.error("Permission denied accessing directory: '%s'", build_dir)
        return 1
    except Exception as e:
        logging.error("Failed to change to build directory: %s", e)
        return 1

    # Run ninja -n -d explain
    try:
        logging.info("Running ninja -n -d explain...")
        result = subprocess.run(["ninja", "-n", "-d", "explain"], capture_output=True, text=True, check=True, timeout=120)
    except subprocess.TimeoutExpired:
        logging.error("Ninja command timed out after 120 seconds")
        os.chdir(original_dir)
        return 1
    except subprocess.CalledProcessError as e:
        logging.error("Error running ninja -n -d explain:")
        if e.stderr:
            logging.error(e.stderr)
        os.chdir(original_dir)
        return 1
    except Exception as e:
        logging.error("Unexpected error running ninja: %s", e)
        os.chdir(original_dir)
        return 1

    lines = result.stderr.splitlines()

    rebuild_targets: List[str] = []
    changed_files: Set[str] = set()

    logging.debug("Parsing %s lines of ninja output...", len(lines))

    for line in lines:
        m = RE_OUTPUT.search(line)
        if not m:
            continue

        explain_msg = m.group(1)

        if "is dirty" in explain_msg:
            continue

        output_file = "unknown"
        if explain_msg.startswith("output "):
            parts = explain_msg.split(" ", 2)
            if len(parts) > 1:
                output_file = parts[1]
        elif "command line changed for " in explain_msg:
            output_file = explain_msg.split("command line changed for ", 1)[1]

        rebuild_targets.append(output_file)

        # Extract changed files
        match = re.search(r"most recent input\s+([^\s\(]+)", line)
        if match:
            file_path = match.group(1)
            if file_path.endswith((".h", ".hpp", ".hxx", ".cpp", ".c", ".cc")):
                changed_files.add(file_path)

    if not rebuild_targets:
        print("No rebuilds detected.")
        os.chdir(original_dir)
        return 0

    print(f"\n{Colors.CYAN}Analyzing dependencies (found {len(changed_files)} changed files)...{Colors.RESET}")

    try:
        impact_map, project_root, _ = build_dependency_impact_map(build_dir, rebuild_targets)
    except Exception as e:
        logging.error("Failed to build dependency impact map: %s", e)
        os.chdir(original_dir)
        return 1

    # Filter changed headers with impact
    changed_with_impact = {f: targets for f, targets in impact_map.items() if len(targets) > 1 and f in changed_files}

    # All high-impact headers
    all_high_impact = {f: targets for f, targets in impact_map.items() if len(targets) > 1}

    changed_with_impact = dict(sorted(changed_with_impact.items(), key=lambda x: len(x[1]), reverse=True))
    all_high_impact = dict(sorted(all_high_impact.items(), key=lambda x: len(x[1]), reverse=True))

    # Print changed headers
    if changed_with_impact:
        print(f"\n{Colors.BRIGHT}Changed Headers (impacting multiple targets):{Colors.RESET}")

        displayed = 0
        for file_path, impacted_targets in changed_with_impact.items():
            if displayed >= args.limit:
                remaining = len(changed_with_impact) - displayed
                if remaining > 0:
                    print(f"\n  ... and {remaining} more (use --limit to show more)")
                break

            try:
                display_path = file_path
                if file_path.startswith(project_root):
                    display_path = os.path.relpath(file_path, project_root)
            except ValueError:
                display_path = file_path

            count = len(impacted_targets)
            print_error(f"  {display_path} → impacts {Colors.BRIGHT}{count}{Colors.RESET} targets", prefix=False)
            displayed += 1
    else:
        print_warning("\nNo changed headers with dependencies found", prefix=False)

    # Show all high-impact headers if requested
    if args.all_headers and all_high_impact:
        print(f"\n{Colors.BRIGHT}All High-Impact Headers:{Colors.RESET}")

        displayed = 0
        for file_path, impacted_targets in all_high_impact.items():
            if displayed >= args.limit:
                remaining = len(all_high_impact) - displayed
                if remaining > 0:
                    print(f"\n  ... and {remaining} more (use --limit to show more)")
                break

            try:
                display_path = file_path
                if file_path.startswith(project_root):
                    display_path = os.path.relpath(file_path, project_root)
            except ValueError:
                display_path = file_path

            count = len(impacted_targets)
            marker = f" {Colors.RED}[CHANGED]{Colors.RESET}" if file_path in changed_files else ""
            print(f"  {Colors.MAGENTA}{display_path}{Colors.RESET} → impacts {Colors.BRIGHT}{count}{Colors.RESET} targets{marker}")
            displayed += 1

    # Restore original directory
    os.chdir(original_dir)
    return 0


if __name__ == "__main__":
    from lib.constants import EXIT_KEYBOARD_INTERRUPT, EXIT_RUNTIME_ERROR, BuildCheckError

    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user", prefix=False)
        sys.exit(EXIT_KEYBOARD_INTERRUPT)
    except BuildCheckError as e:
        logging.error(str(e))
        sys.exit(e.exit_code)
    except Exception as e:
        logging.error("Unexpected error: %s", e)
        if logging.getLogger().level == logging.DEBUG:
            import traceback

            traceback.print_exc()
        sys.exit(EXIT_RUNTIME_ERROR)
