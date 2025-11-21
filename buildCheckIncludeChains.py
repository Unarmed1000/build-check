#!/usr/bin/env python3
#****************************************************************************************************************************************************
#* BSD 3-Clause License
#*
#* Copyright (c) 2025, Mana Battery
#* All rights reserved.
#*
#* Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#*
#* 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#* 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the
#*    documentation and/or other materials provided with the distribution.
#* 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this
#*    software without specific prior written permission.
#*
#* THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
#* THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
#* CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
#* PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
#* LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
#* EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#****************************************************************************************************************************************************
"""Analyze include chains to find transitive dependencies through cooccurrence patterns.

PURPOSE:
    Identifies which headers frequently appear together in compilation units to understand
    indirect coupling and include chain patterns. This helps find "gateway" headers that
    transitively pull in other headers.

WHAT IT DOES:
    - Builds a cooccurrence matrix showing which headers appear together
    - For each changed header, shows which other headers are frequently included with it
    - Helps identify why a header gets included indirectly
    - Reveals coupling patterns between headers

USE CASES:
    - "Why is this header being pulled in everywhere?"
    - Find which parent headers are causing transitive includes
    - Identify coupling between seemingly unrelated headers
    - Understand include chain patterns (A includes B, B includes C...)
    - Discover refactoring opportunities to break coupling

METHOD:
    Analyzes cooccurrence: if headers A and B appear together in many compilation units,
    they likely have a dependency relationship (either direct or transitive).
    Uses 'ninja -t deps' to get the full dependency list for each target.

OUTPUT:
    For each changed header:
    - List of other headers that frequently appear with it (cooccurrence count)
    - Helps identify which "parent" headers are causing the inclusion

PERFORMANCE:
    Fast (typically 1-2 seconds). Only queries Ninja's dependency graph.

REQUIREMENTS:
    - Python 3.7+
    - ninja build system
    - colorama (optional, for colored output): pip install colorama

INTERPRETATION:
    If header X frequently appears with Y (high cooccurrence):
    - X might directly include Y
    - Y might directly include X  
    - Both might be included by a common parent header
    - Use buildCheckIncludeGraph.py to see the actual include relationships

COMPLEMENTARY TOOLS:
    - buildCheckImpact.py: Shows direct rebuild impact (simpler)
    - buildCheckIncludeGraph.py: Shows actual include graph with gateway analysis
    - buildCheckDependencyHell.py: Comprehensive transitive dependency metrics

EXAMPLES:
    # Show cooccurrence patterns for changed headers
    ./buildCheckIncludeChains.py ../build/release/
    
    # Only show headers that appear together 10+ times
    ./buildCheckIncludeChains.py ../build/release/ --threshold 10
"""
import subprocess
import re
import os
import sys
import argparse
import logging
from collections import defaultdict
from typing import List, Dict, Set, Tuple, Optional
from pathlib import Path

try:
    from colorama import Fore, Style, init
    init(autoreset=False)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    class Fore:
        RED = YELLOW = GREEN = BLUE = MAGENTA = CYAN = WHITE = LIGHTBLACK_EX = RESET = ''
    class Style:
        RESET_ALL = BRIGHT = DIM = ''

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

RE_OUTPUT = re.compile(r"ninja explain: (.*)")
RE_RECENT_INPUT = re.compile(r'most recent input\s+([^\s\(]+)')

# Constants
HEADER_EXTENSIONS = ('.h', '.hpp', '.hxx', '.hh')
SYSTEM_PATH_PREFIXES = ('/usr/', '/lib/', '/opt/')
DEFAULT_THRESHOLD = 5
DEFAULT_MAX_RESULTS = 10


def check_ninja_available() -> bool:
    """Check if ninja is available in PATH.
    
    Returns:
        True if ninja is available, False otherwise
    """
    try:
        subprocess.run(
            ["ninja", "--version"],
            capture_output=True,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def validate_build_directory(build_dir: str) -> Path:
    """Validate that the build directory exists and contains a ninja build file.
    
    Args:
        build_dir: Path to the build directory
        
    Returns:
        Validated Path object
        
    Raises:
        ValueError: If directory is invalid or doesn't contain build.ninja
    """
    path = Path(build_dir).resolve()
    
    if not path.exists():
        raise ValueError(f"Directory does not exist: {path}")
    
    if not path.is_dir():
        raise ValueError(f"Path is not a directory: {path}")
    
    build_ninja = path / "build.ninja"
    if not build_ninja.exists():
        raise ValueError(
            f"No build.ninja found in {path}. "
            "This doesn't appear to be a ninja build directory."
        )
    
    return path


def get_dependencies(build_dir: Path, target: str) -> List[str]:
    """Get dependencies for a target using ninja -t deps.
    
    Args:
        build_dir: Path to the build directory
        target: Target name to query dependencies for
        
    Returns:
        List of dependency file paths
    """
    try:
        result = subprocess.run(
            ["ninja", "-t", "deps", target],
            capture_output=True,
            text=True,
            check=True,
            cwd=build_dir,
            timeout=30
        )
        deps = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and not line.endswith(":") and not line.startswith("#"):
                deps.append(line)
        return deps
    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout querying dependencies for target: {target}")
        return []
    except subprocess.CalledProcessError as e:
        logger.debug(f"Failed to get dependencies for {target}: {e}")
        return []
    except Exception as e:
        logger.debug(f"Unexpected error getting dependencies for {target}: {e}")
        return []


def is_system_header(path: str) -> bool:
    """Check if a path appears to be a system header.
    
    Args:
        path: File path to check
        
    Returns:
        True if path looks like a system header
    """
    return any(path.startswith(prefix) for prefix in SYSTEM_PATH_PREFIXES)


def is_header_file(path: str) -> bool:
    """Check if a path is a header file.
    
    Args:
        path: File path to check
        
    Returns:
        True if path ends with a header extension
    """
    return path.endswith(HEADER_EXTENSIONS)


def build_include_graph(
    build_dir: Path, 
    rebuild_targets: List[str]
) -> Dict[str, Dict[str, int]]:
    """Build a cooccurrence graph of which headers appear together.
    
    Args:
        build_dir: Path to the build directory
        rebuild_targets: List of targets that need rebuilding
        
    Returns:
        Dictionary mapping header -> (header -> cooccurrence_count)
    """
    cooccurrence: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total = len(rebuild_targets)
    
    logger.info(f"Analyzing {total} rebuild targets...")
    
    for idx, target in enumerate(rebuild_targets, 1):
        if idx % 100 == 0 or idx == total:
            logger.info(f"Progress: {idx}/{total} targets processed")
        
        deps = get_dependencies(build_dir, target)
        headers = [
            d for d in deps 
            if is_header_file(d) and not is_system_header(d)
        ]
        
        # Build cooccurrence matrix
        for h1 in headers:
            for h2 in headers:
                if h1 != h2:
                    cooccurrence[h1][h2] += 1
    
    logger.info(f"Built cooccurrence graph with {len(cooccurrence)} headers")
    return dict(cooccurrence)  # Convert to regular dict for clarity


def get_relative_path(file_path: str, project_root: Path) -> str:
    """Get relative path for display, handling errors gracefully.
    
    Args:
        file_path: Absolute or relative file path
        project_root: Project root directory
        
    Returns:
        Relative path if possible, otherwise original path
    """
    try:
        path = Path(file_path)
        if path.is_absolute() and path.is_relative_to(project_root):
            return str(path.relative_to(project_root))
        return file_path
    except (ValueError, Exception):
        return file_path


def find_inclusion_causes(
    changed_file: str,
    include_graph: Dict[str, Dict[str, int]],
    project_root: Path,
    threshold: int = DEFAULT_THRESHOLD
) -> List[Tuple[str, int]]:
    """Find headers that likely cause the changed file to be included.
    
    Args:
        changed_file: Path to the changed header file
        include_graph: Cooccurrence graph
        project_root: Project root directory for path display
        threshold: Minimum cooccurrence count to report
        
    Returns:
        List of (header_path, cooccurrence_count) tuples, sorted by count descending
    """
    if changed_file not in include_graph:
        return []
    
    cooccurrences = include_graph[changed_file]
    
    causes = []
    for header, count in cooccurrences.items():
        if count >= threshold:
            display_path = get_relative_path(header, project_root)
            causes.append((display_path, count))
    
    return sorted(causes, key=lambda x: x[1], reverse=True)


def run_ninja_explain(build_dir: Path) -> subprocess.CompletedProcess:
    """Run ninja -n -d explain to get rebuild information.
    
    Args:
        build_dir: Path to the build directory
        
    Returns:
        CompletedProcess result
        
    Raises:
        subprocess.CalledProcessError: If ninja command fails
    """
    return subprocess.run(
        ["ninja", "-n", "-d", "explain"],
        capture_output=True,
        text=True,
        check=True,
        cwd=build_dir,
        timeout=60
    )


def parse_ninja_output(
    stderr_lines: List[str]
) -> Tuple[List[str], Set[str]]:
    """Parse ninja explain output to extract rebuild targets and changed files.
    
    Args:
        stderr_lines: Lines from ninja stderr output
        
    Returns:
        Tuple of (rebuild_targets, changed_header_files)
    """
    rebuild_targets = []
    changed_files = set()

    for line in stderr_lines:
        m = RE_OUTPUT.search(line)
        if not m:
            continue

        explain_msg = m.group(1)
        
        # Skip dirty messages
        if "is dirty" in explain_msg:
            continue
        
        # Extract output file
        output_file = "unknown"
        if explain_msg.startswith("output "):
            parts = explain_msg.split(" ", 2)
            if len(parts) > 1:
                output_file = parts[1]
        elif "command line changed for " in explain_msg:
            output_file = explain_msg.split("command line changed for ", 1)[1]
        
        rebuild_targets.append(output_file)
        
        # Extract changed header files
        match = RE_RECENT_INPUT.search(line)
        if match:
            file_path = match.group(1)
            if is_header_file(file_path):
                changed_files.add(file_path)
    
    return rebuild_targets, changed_files


def print_results(
    changed_files: Set[str],
    include_graph: Dict[str, Dict[str, int]],
    project_root: Path,
    threshold: int,
    max_results: int = DEFAULT_MAX_RESULTS
) -> None:
    """Print the analysis results.
    
    Args:
        changed_files: Set of changed header files
        include_graph: Cooccurrence graph
        project_root: Project root for path display
        threshold: Minimum cooccurrence threshold
        max_results: Maximum number of results to show per header
    """
    print(f"\n{Style.BRIGHT}Include Chain Analysis "
          f"(headers frequently included with changed headers):{Style.RESET_ALL}")
    
    for changed_file in sorted(changed_files):
        display_changed = get_relative_path(changed_file, project_root)
        
        causes = find_inclusion_causes(
            changed_file, include_graph, project_root, threshold
        )
        
        if causes:
            print(f"\n  {Fore.RED}{display_changed}{Style.RESET_ALL} "
                  f"often appears with:")
            for header, count in causes[:max_results]:
                print(f"    {Fore.CYAN}{header}{Style.RESET_ALL} ({count} times)")
            
            if len(causes) > max_results:
                remaining = len(causes) - max_results
                print(f"    {Fore.LIGHTBLACK_EX}... and {remaining} more{Style.RESET_ALL}")
        else:
            print(f"\n  {Fore.YELLOW}{display_changed}{Style.RESET_ALL}: "
                  f"No frequent cooccurrences (threshold={threshold})")


def main() -> int:
    """Main entry point.
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    parser = argparse.ArgumentParser(
        description='Analyze header cooccurrence patterns to understand include chains.',
        epilog='''
This tool helps answer: "Why is header X getting included everywhere?"
It shows which other headers frequently appear with your changed headers,
revealing indirect coupling through include chains.

Interpretation:
  High cooccurrence = headers often compiled together
  This suggests one includes the other (directly or transitively)
  
Use buildCheckIncludeGraph.py to see the actual include relationships.
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'build_directory',
        metavar='BUILD_DIR',
        help='Path to the ninja build directory (e.g., build/release)'
    )
    
    parser.add_argument(
        '--threshold',
        type=int,
        default=DEFAULT_THRESHOLD,
        help=f'Minimum cooccurrence count to report (default: {DEFAULT_THRESHOLD})'
    )
    
    parser.add_argument(
        '--max-results',
        type=int,
        default=DEFAULT_MAX_RESULTS,
        help=f'Maximum results to show per header (default: {DEFAULT_MAX_RESULTS})'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Validate inputs
    if args.threshold < 1:
        logger.error("Threshold must be at least 1")
        return 1
    
    if args.max_results < 1:
        logger.error("Max results must be at least 1")
        return 1
    
    # Check ninja availability
    if not check_ninja_available():
        logger.error(
            "ninja not found in PATH. "
            "Please install ninja or ensure it's in your PATH."
        )
        return 1
    
    # Validate build directory
    try:
        build_dir = validate_build_directory(args.build_directory)
    except ValueError as e:
        logger.error(str(e))
        return 1

    # Run ninja explain
    logger.info("Running ninja -n -d explain...")
    try:
        result = run_ninja_explain(build_dir)
    except subprocess.TimeoutExpired:
        logger.error(
            "Timeout running ninja -n -d explain. "
            "The build graph may be too large."
        )
        return 1
    except subprocess.CalledProcessError as e:
        logger.error("Error running ninja -n -d explain:")
        if e.stderr:
            logger.error(e.stderr)
        return 1
    except Exception as e:
        logger.error(f"Unexpected error running ninja: {e}")
        return 1
    
    # Parse output
    logger.info("Parsing ninja output...")
    rebuild_targets, changed_files = parse_ninja_output(result.stderr.splitlines())
    
    if not rebuild_targets:
        logger.info("No rebuild targets found. Build is up to date.")
        return 0
    
    if not changed_files:
        logger.info(
            f"No changed header files detected among {len(rebuild_targets)} "
            "rebuild targets."
        )
        return 0
    
    logger.info(
        f"Found {len(changed_files)} changed header(s) affecting "
        f"{len(rebuild_targets)} target(s)"
    )
    
    # Determine project root (heuristic: 3 levels up from build dir)
    try:
        project_root = build_dir.parent.parent.parent
    except Exception:
        project_root = build_dir.parent
    
    # Build include graph
    print(f"\n{Fore.CYAN}Building include cooccurrence graph from "
          f"{len(rebuild_targets)} rebuild targets...{Style.RESET_ALL}")
    
    try:
        include_graph = build_include_graph(build_dir, rebuild_targets)
    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user")
        return 130  # Standard exit code for SIGINT
    except Exception as e:
        logger.error(f"Error building include graph: {e}")
        return 1
    
    # Print results
    try:
        print_results(
            changed_files,
            include_graph,
            project_root,
            args.threshold,
            args.max_results
        )
    except Exception as e:
        logger.error(f"Error printing results: {e}")
        return 1
    
    logger.info("\nAnalysis complete.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if logger.level == logging.DEBUG:
            import traceback
            traceback.print_exc()
        sys.exit(1)
