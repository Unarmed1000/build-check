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
    
    # Exclude third-party and test headers
    ./buildCheckIncludeChains.py ../build/release/ --exclude "*/ThirdParty/*" --exclude "*/test/*"
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

# Import library modules
from lib.color_utils import Colors, print_error, print_warning, is_color_supported
from lib.file_utils import exclude_headers_by_patterns
from lib.ninja_utils import (
    check_ninja_available, 
    validate_build_directory, 
    get_dependencies,
    run_ninja_explain,
    parse_ninja_explain_output,
    extract_rebuild_info
)
from lib.dependency_utils import compute_header_cooccurrence_from_deps_lists, SourceDependencyMap

COLORAMA_AVAILABLE = is_color_supported()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
HEADER_EXTENSIONS = ('.h', '.hpp', '.hxx', '.hh')
SYSTEM_PATH_PREFIXES = ('/usr/', '/lib/', '/opt/')
DEFAULT_THRESHOLD = 5
DEFAULT_MAX_RESULTS = 10

# check_ninja_available, validate_build_directory, and get_dependencies moved to lib modules

# Helper functions for local use
def is_system_header(path: str) -> bool:
    """Check if a path appears to be a system header."""
    return any(path.startswith(prefix) for prefix in SYSTEM_PATH_PREFIXES)

def is_header_file(path: str) -> bool:
    """Check if a path is a header file."""
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
    # Collect dependencies for all targets
    dependencies_by_target = {}
    for target in rebuild_targets:
        dependencies_by_target[target] = get_dependencies(str(build_dir), target)
    
    # Create SourceDependencyMap and use library function to compute cooccurrence
    dependency_map = SourceDependencyMap(dependencies_by_target)
    return compute_header_cooccurrence_from_deps_lists(
        dependency_map,
        is_header_filter=is_header_file,
        is_system_filter=is_system_header,
        show_progress=True
    )


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


# run_ninja_explain and parse_ninja_output are now imported from lib.ninja_utils
# The library versions are: run_ninja_explain() and parse_ninja_explain_output()


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
    print(f"\n{Colors.BRIGHT}Include Chain Analysis "
          f"(headers frequently included with changed headers):{Colors.RESET}")
    
    for changed_file in sorted(changed_files):
        display_changed = get_relative_path(changed_file, project_root)
        
        causes = find_inclusion_causes(
            changed_file, include_graph, project_root, threshold
        )
        
        if causes:
            print(f"\n  {Colors.RED}{display_changed}{Colors.RESET} "
                  f"often appears with:")
            for header, count in causes[:max_results]:
                print(f"    {Colors.CYAN}{header}{Colors.RESET} ({count} times)")
            
            if len(causes) > max_results:
                remaining = len(causes) - max_results
                print(f"    {Colors.DIM}... and {remaining} more{Colors.RESET}")
        else:
            print(f"\n  {Colors.YELLOW}{display_changed}{Colors.RESET}: "
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
    
    parser.add_argument(
        '--exclude',
        type=str,
        action='append',
        metavar='PATTERN',
        help='Exclude headers matching glob pattern (can be used multiple times). '
             'Useful for excluding third-party libraries, generated files, or test code. '
             'Supports glob patterns: * (any chars), ** (recursive), ? (single char). '
             'Examples: "*/ThirdParty/*", "*/build/*", "*_generated.h", "*/test/*"'
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
    rebuild_targets, changed_files = parse_ninja_explain_output(result.stderr.splitlines())
    
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
    
    # Apply exclude patterns if specified
    if hasattr(args, 'exclude') and args.exclude:
        try:
            project_root_for_filter = build_dir.parent.parent.parent
        except Exception:
            project_root_for_filter = build_dir.parent
        
        original_count = len(changed_files)
        filtered_headers, excluded_count, no_match_patterns = exclude_headers_by_patterns(
            changed_files, args.exclude, str(project_root_for_filter)
        )
        
        if excluded_count > 0:
            changed_files = filtered_headers
            print(f"{Colors.GREEN}Excluded {excluded_count} headers matching {len(args.exclude)} pattern(s){Colors.RESET}")
        
        # Warn about patterns that matched nothing
        for pattern in no_match_patterns:
            print(f"{Colors.YELLOW}Warning: Exclude pattern '{pattern}' matched no headers{Colors.RESET}")
        
        if not changed_files:
            logger.info("All changed headers were excluded")
            print(f"{Colors.YELLOW}All changed headers were excluded by filters{Colors.RESET}")
            return 0
    
    # Determine project root (heuristic: 3 levels up from build dir)
    try:
        project_root = build_dir.parent.parent.parent
    except Exception:
        project_root = build_dir.parent
    
    # Build include graph
    print(f"\n{Colors.CYAN}Building include cooccurrence graph from "
          f"{len(rebuild_targets)} rebuild targets...{Colors.RESET}")
    
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
    from lib.constants import (
        EXIT_SUCCESS, EXIT_KEYBOARD_INTERRUPT, EXIT_RUNTIME_ERROR,
        BuildCheckError
    )
    
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user")
        sys.exit(EXIT_KEYBOARD_INTERRUPT)
    except BuildCheckError as e:
        logger.error(str(e))
        sys.exit(e.exit_code)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if logger.level == logging.DEBUG:
            import traceback
            traceback.print_exc()
        sys.exit(EXIT_RUNTIME_ERROR)
