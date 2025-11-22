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
"""Analyze the ripple effect of working directory changes on C/C++ compilation.

PURPOSE:
    Determines which C/C++ source files will be recompiled based on uncommitted
    changes in your working directory compared to HEAD. Uses dependency analysis
    from buildCheckDependencyHell.py to compute transitive impact.

WHAT IT DOES:
    - Detects changed files in working directory (staged and unstaged)
    - Uses clang-scan-deps to build complete dependency graph
    - For changed headers: finds all source files that transitively depend on them
    - For changed source files: directly marks them for recompilation
    - Calculates total rebuild impact and shows detailed breakdown

USE CASES:
    - "What will rebuild if I commit these changes?"
    - Estimate CI/CD build time impact before committing
    - Review code changes with rebuild cost in mind
    - Identify high-impact changes that need extra testing

METHOD:
    1. Run git diff to get changed files (HEAD vs working directory)
    2. Filter to C/C++ source and header files
    3. Build complete include graph using clang-scan-deps
    4. For each changed header, compute reverse dependencies
    5. Aggregate all affected source files

OUTPUT:
    - List of changed files (headers and sources)
    - For each changed header: list of affected source files
    - Summary: total files changed, total sources affected, rebuild percentage
    - Color-coded severity based on rebuild impact

PERFORMANCE:
    Moderate (5-10 seconds). Uses build_include_graph from buildCheckDependencyHell.py
    which parallelizes clang-scan-deps across all CPU cores.

REQUIREMENTS:
    - Python 3.7+
    - git repository
    - ninja build directory (compile_commands.json auto-generated)
    - clang-scan-deps (clang-19, clang-18, or clang-XX)
    - networkx: pip install networkx

EXAMPLES:
    # Analyze working directory changes (default: vs HEAD)
    ./buildCheckRippleEffect.py ../build/release/
    
    # Compare working directory against a specific branch
    ./buildCheckRippleEffect.py ../build/release/ --from origin/main
    
    # Compare against a release tag
    ./buildCheckRippleEffect.py ../build/release/ --from v2.0.0
    
    # Compare against N commits ago
    ./buildCheckRippleEffect.py ../build/release/ --from HEAD~10
    
    # Specify git repository location
    ./buildCheckRippleEffect.py ../build/release/ --repo ~/projects/myproject
    
    # Output as JSON
    ./buildCheckRippleEffect.py ../build/release/ --json results.json
"""
import subprocess
import sys
import os
import argparse
import logging
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional, List, Tuple, Dict, Set
from dataclasses import dataclass, asdict

# Import library modules
from lib.git_utils import find_git_repo, get_uncommitted_changes, get_working_tree_changes_from_commit, validate_ancestor_relationship, categorize_changed_files
from lib.ninja_utils import validate_and_prepare_build_dir, validate_build_directory_with_feedback
from lib.dependency_utils import build_reverse_dependency_map, compute_affected_sources, SourceDependencyMap
from lib.color_utils import Colors, print_error, print_warning, print_success

@dataclass
class RippleEffectResult:
    """Result of ripple effect analysis.
    
    Attributes:
        affected_sources: Mapping of changed headers to affected source files
        total_affected: Set of all affected source files (from headers)
        direct_sources: Set of directly changed source files
        source_to_deps: Mapping of source files to their dependencies
        header_to_sources: Mapping of headers to sources that depend on them
    """
    affected_sources: Dict[str, List[str]]
    total_affected: Set[str]
    direct_sources: Set[str]
    source_to_deps: Dict[str, List[str]]
    header_to_sources: Dict[str, Set[str]]


@dataclass
class RippleEffectData:
    """Data about ripple effect for working directory changes.
    
    Attributes:
        changed_headers: List of changed header file paths
        changed_sources: List of changed source file paths
        affected_sources_by_header: Mapping of headers to affected source paths
        all_affected_sources: List of all unique affected source file paths
        total_sources: Total number of source files in build
        rebuild_percentage: Percentage of sources affected (0-100)
    """
    changed_headers: List[str]
    changed_sources: List[str]
    affected_sources_by_header: Dict[str, List[str]]
    all_affected_sources: List[str]
    total_sources: int
    rebuild_percentage: float


# Import build_include_graph and build_dependency_graph from library
from lib.clang_utils import build_include_graph
from lib.graph_utils import build_dependency_graph

# Explicitly export functions for testing (library functions are imported, not exported)
__all__ = ['get_ripple_effect_data', 'analyze_ripple_effect', 'print_ripple_report', 'RippleEffectResult', 'RippleEffectData', 'find_git_repo', 'categorize_changed_files']


def analyze_ripple_effect(build_dir: str, changed_headers: List[str], changed_sources: List[str], verbose: bool = False) -> RippleEffectResult:
    """Analyze which C/C++ files will recompile due to changes.
    
    Args:
        build_dir: Path to ninja build directory
        changed_headers: List of changed header files (absolute paths)
        changed_sources: List of changed source files (absolute paths)
        verbose: Whether to print progress messages
    
    Returns:
        Dictionary with analysis results:
        - affected_sources: dict mapping changed header -> list of affected sources
        - total_affected: set of all affected source files
        - direct_sources: set of changed source files
        - source_to_deps: dict mapping source files to their dependencies
        - header_to_sources: dict mapping headers to sources that depend on them
    
    Raises:
        ValueError: If build_dir is invalid or missing compile_commands.json
        RuntimeError: If dependency graph building fails
    """
    # Validate inputs
    build_dir, compile_commands = validate_and_prepare_build_dir(build_dir, verbose)
    
    if not isinstance(changed_headers, list) or not isinstance(changed_sources, list):
        raise TypeError("changed_headers and changed_sources must be lists")
    
    logging.info(f"Analyzing {len(changed_headers)} headers and {len(changed_sources)} sources")
    
    if verbose:
        print(f"{Colors.BLUE}Building dependency graph...{Colors.RESET}")
    
    # Build complete include graph
    try:
        scan_result = build_include_graph(build_dir)
        source_to_deps = scan_result.source_to_deps
        include_graph = scan_result.include_graph
        all_headers = scan_result.all_headers
        scan_time = scan_result.scan_time
    except Exception as e:
        logging.error(f"Failed to build include graph: {e}")
        raise RuntimeError(f"Failed to build dependency graph: {e}") from e
    
    if not source_to_deps:
        logging.warning("No dependencies found in build directory")
        raise RuntimeError("No compilation units found - check compile_commands.json")
    
    if verbose:
        print_success(f"Dependency graph built in {scan_time:.2f}s")
    
    # Build reverse dependency map: header -> list of sources that depend on it
    if verbose:
        print(f"{Colors.BLUE}Computing reverse dependencies...{Colors.RESET}")
    
    dependency_map = SourceDependencyMap(source_to_deps)
    header_to_sources = build_reverse_dependency_map(dependency_map)
    
    if verbose:
        print_success("Reverse dependency map built")
    
    # Analyze impact of changed headers
    affected_sources = compute_affected_sources(changed_headers, header_to_sources)
    total_affected = set()
    for sources in affected_sources.values():
        total_affected.update(sources)
    
    # Changed source files are directly affected
    direct_sources = set(changed_sources)
    
    if verbose:
        print()
    
    return RippleEffectResult(
        affected_sources=affected_sources,
        total_affected=total_affected,
        direct_sources=direct_sources,
        source_to_deps=source_to_deps,
        header_to_sources=header_to_sources
    )


def print_ripple_report(changed_headers: List[str], changed_sources: List[str], analysis_result: RippleEffectResult, repo_dir: str) -> None:
    """Print formatted ripple effect report.
    
    Args:
        changed_headers: List of changed header files
        changed_sources: List of changed source files
        analysis_result: RippleEffectResult containing analysis results
        repo_dir: Path to git repository for relative path display
    """
    affected_sources = analysis_result.affected_sources
    total_affected = analysis_result.total_affected
    direct_sources = analysis_result.direct_sources
    source_to_deps = analysis_result.source_to_deps
    
    # Calculate total unique sources that will rebuild
    all_affected = total_affected.union(direct_sources)
    total_sources = len(source_to_deps)
    
    print(f"\n{Colors.BRIGHT}═══ Git Change Ripple Effect Analysis ═══{Colors.RESET}\n")
    
    # Summary statistics
    total_changed = len(changed_headers) + len(changed_sources)
    rebuild_pct = (len(all_affected) / total_sources * 100) if total_sources > 0 else 0
    
    # Color code based on impact
    if len(all_affected) > 100:
        impact_color = Colors.RED
        severity = "HIGH IMPACT"
    elif len(all_affected) > 50:
        impact_color = Colors.YELLOW
        severity = "MODERATE IMPACT"
    else:
        impact_color = Colors.CYAN
        severity = "LOW IMPACT"
    
    print(f"{Colors.BRIGHT}Summary:{Colors.RESET}")
    print(f"  Changed files: {Colors.CYAN}{total_changed}{Colors.RESET} ({len(changed_headers)} headers, {len(changed_sources)} sources)")
    print(f"  Affected sources: {impact_color}{len(all_affected)}{Colors.RESET} / {total_sources} ({rebuild_pct:.1f}%)")
    print(f"  Severity: {impact_color}{severity}{Colors.RESET}\n")
    
    # Show changed files
    if changed_headers:
        print(f"{Colors.BRIGHT}Changed Headers ({len(changed_headers)}):{Colors.RESET}")
        for header in sorted(changed_headers):
            display_path = os.path.relpath(header, repo_dir) if header.startswith(repo_dir) else header
            num_affected = len(affected_sources.get(header, []))
            
            if num_affected > 20:
                color = Colors.RED
            elif num_affected > 10:
                color = Colors.YELLOW
            else:
                color = Colors.CYAN
            
            print(f"  {color}{display_path}{Colors.RESET} → affects {num_affected} sources")
    
    if changed_sources:
        print(f"\n{Colors.BRIGHT}Changed Sources ({len(changed_sources)}):{Colors.RESET}")
        for source in sorted(changed_sources):
            display_path = os.path.relpath(source, repo_dir) if source.startswith(repo_dir) else source
            print(f"  {Colors.MAGENTA}{display_path}{Colors.RESET} → directly recompiles")
    
    # Detailed breakdown by header
    if changed_headers and affected_sources:
        print(f"\n{Colors.BRIGHT}Detailed Ripple Effect:{Colors.RESET}")
        
        # Sort headers by impact (most affected sources first)
        sorted_headers = sorted(affected_sources.items(), key=lambda x: len(x[1]), reverse=True)
        
        for header, sources in sorted_headers:
            display_path = os.path.relpath(header, repo_dir) if header.startswith(repo_dir) else header
            num_affected = len(sources)
            
            if num_affected > 20:
                color = Colors.RED
            elif num_affected > 10:
                color = Colors.YELLOW
            else:
                color = Colors.CYAN
            
            print(f"\n  {color}{display_path}{Colors.RESET} → {num_affected} affected sources:")
            
            # Show up to 10 affected sources
            for source in sources[:10]:
                display_source = os.path.relpath(source, repo_dir) if source.startswith(repo_dir) else source
                # Remove .o extension if present
                if display_source.endswith('.o'):
                    display_source = display_source[:-2]
                print(f"    {Colors.DIM}{display_source}{Colors.RESET}")
            
            if num_affected > 10:
                print(f"    {Colors.DIM}... and {num_affected - 10} more{Colors.RESET}")


def get_ripple_effect_data(build_dir: str, repo_dir: str, from_ref: Optional[str] = None) -> RippleEffectData:
    """
    Get structured ripple effect analysis data without printing.
    
    Args:
        build_dir: Path to ninja build directory
        repo_dir: Path to git repository
        from_ref: Git reference to compare against (default: None = HEAD, uncommitted only)
    
    Returns:
        dict with keys:
            - changed_headers: list of changed header file paths
            - changed_sources: list of changed source file paths
            - affected_sources_by_header: dict mapping header -> list of affected source paths
            - all_affected_sources: list of all unique affected source file paths
            - total_sources: total number of source files in build
            - rebuild_percentage: percentage of sources affected
    
    Raises:
        ValueError: If build_dir or repo_dir are invalid, or if from_ref is not an ancestor
        RuntimeError: If analysis fails
    """
    # Validate inputs
    if not build_dir or not isinstance(build_dir, str):
        raise ValueError(f"Invalid build_dir: {build_dir}")
    if not repo_dir or not isinstance(repo_dir, str):
        raise ValueError(f"Invalid repo_dir: {repo_dir}")
    
    logging.info(f"Getting ripple effect data for working directory changes{' from ' + from_ref if from_ref else ''}")
    
    # Get changed files from git
    try:
        if from_ref:
            # Validate that from_ref is a linear ancestor of HEAD
            validate_ancestor_relationship(repo_dir, from_ref)
            changed_files, _ = get_working_tree_changes_from_commit(repo_dir, from_ref)
        else:
            changed_files = get_uncommitted_changes(repo_dir)
    except Exception as e:
        logging.error(f"Failed to get changed files: {e}")
        raise
    
    if not changed_files:
        return RippleEffectData(
            changed_headers=[],
            changed_sources=[],
            affected_sources_by_header={},
            all_affected_sources=[],
            total_sources=0,
            rebuild_percentage=0.0
        )
    
    # Categorize changed files
    changed_headers, changed_sources = categorize_changed_files(changed_files)
    
    if not changed_headers and not changed_sources:
        return RippleEffectData(
            changed_headers=[],
            changed_sources=[],
            affected_sources_by_header={},
            all_affected_sources=[],
            total_sources=0,
            rebuild_percentage=0.0
        )
    
    # Analyze ripple effect (verbose=False to suppress progress messages)
    analysis_result = analyze_ripple_effect(build_dir, changed_headers, changed_sources, verbose=False)
    
    affected_sources = analysis_result.affected_sources
    source_to_deps = analysis_result.source_to_deps
    total_sources = len(source_to_deps)
    
    # Collect all affected sources
    all_affected = set(changed_sources)
    for sources in affected_sources.values():
        all_affected.update(sources)
    
    rebuild_pct = (len(all_affected) * 100.0 / total_sources) if total_sources > 0 else 0.0
    
    return RippleEffectData(
        changed_headers=sorted(changed_headers),
        changed_sources=sorted(changed_sources),
        affected_sources_by_header={k: sorted(v) for k, v in sorted(affected_sources.items())},
        all_affected_sources=sorted(all_affected),
        total_sources=total_sources,
        rebuild_percentage=rebuild_pct
    )


def parse_arguments() -> argparse.Namespace:
    """Parse and return command line arguments.
    
    Returns:
        Parsed command line arguments
    """
    parser = argparse.ArgumentParser(
        description='Analyze ripple effect of working directory changes on C/C++ compilation.',
        prog='buildCheckRippleEffect.py',
        epilog='''
This tool helps you understand the rebuild impact of your current changes before committing.

Examples:
  # Analyze uncommitted changes (default)
  %(prog)s ../build/release/
  
  # Compare working directory against a branch
  %(prog)s ../build/release/ --from origin/main
  
  # Compare against a release tag
  %(prog)s ../build/release/ --from v2.0.0
  
  # Compare against 10 commits ago
  %(prog)s ../build/release/ --from HEAD~10
  
  # Specify git repository
  %(prog)s ../build/release/ --repo ~/projects/myproject
  
  # Output as JSON
  %(prog)s ../build/release/ --json results.json

Requires: git, clang-scan-deps, networkx (pip install networkx)
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'build_directory',
        metavar='BUILD_DIR',
        help='Path to the ninja build directory (e.g., build/release)'
    )
    
    parser.add_argument(
        '--repo',
        metavar='REPO_DIR',
        help='Path to git repository (default: auto-detect from build directory)'
    )
    
    parser.add_argument(
        '--from',
        dest='from_ref',
        metavar='REF',
        default=None,
        help='Git reference to compare working directory against (must be a linear ancestor of HEAD). '
             'Default: HEAD (shows only uncommitted changes). '
             'Examples: origin/main, v2.0.0, HEAD~10'
    )
    
    parser.add_argument(
        '--json',
        metavar='FILE',
        help='Output results as JSON to the specified file'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output (show progress messages)'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='WARNING',
        help='Set logging level (default: WARNING)'
    )
    
    return parser.parse_args()


def setup_logging(log_level_str: str) -> None:
    """Configure logging settings.
    
    Args:
        log_level_str: Logging level as string (DEBUG, INFO, etc.)
    """
    log_level = getattr(logging, log_level_str)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def validate_git_repository_path(repo_path: Optional[str], build_dir: str) -> str:
    """Find or validate the git repository path.
    
    Args:
        repo_path: User-specified repository path (or None to auto-detect)
        build_dir: Build directory path (used for auto-detection)
    
    Returns:
        Validated repository directory path
    
    Raises:
        SystemExit: If validation fails
    """
    try:
        if repo_path:
            repo_dir = os.path.realpath(os.path.abspath(repo_path))
            if not os.path.isdir(repo_dir):
                logging.error(f"Repository directory does not exist: {repo_dir}")
                print_error(f"'{repo_dir}' is not a directory")
                raise ValueError(f"'{repo_dir}' is not a directory")
            git_dir = os.path.realpath(os.path.join(repo_dir, '.git'))
            # Validate git_dir is within repo_dir (protect against symlink attacks)
            try:
                rel_path = os.path.relpath(git_dir, repo_dir)
                if rel_path.startswith('..'):
                    raise ValueError("Path outside repository directory")
            except (ValueError, OSError) as e:
                logging.error(f"Path traversal detected in .git path: {e}")
                print_error("Path traversal detected")
                raise ValueError("Path traversal detected") from e
            if not os.path.isdir(git_dir):
                logging.error(f"Not a git repository: {repo_dir}")
                print_error(f"'{repo_dir}' is not a git repository")
                raise ValueError(f"'{repo_dir}' is not a git repository")
            logging.info(f"Using git repository: {repo_dir}")
        else:
            # Auto-detect git repo from build directory
            detected_repo = find_git_repo(build_dir)
            if not detected_repo:
                logging.error("Could not find git repository")
                print_error("Could not find git repository")
                print_warning("Hint: Use --repo to specify the repository path", prefix=False)
                raise ValueError("Could not find git repository")
            repo_dir = detected_repo
            logging.info(f"Auto-detected git repository: {repo_dir}")
            print(f"{Colors.BLUE}Found git repository: {repo_dir}{Colors.RESET}")
        return repo_dir
    except Exception as e:
        logging.exception(f"Error validating git repository: {e}")
        print_error(str(e))
        raise RuntimeError(f"Error validating git repository: {e}") from e


def write_json_output_file(json_path: str, build_dir: str, repo_dir: str, from_ref: Optional[str] = None) -> None:
    """Generate and write JSON output to file.
    
    Args:
        json_path: Path to output JSON file
        build_dir: Build directory path
        repo_dir: Repository directory path
        from_ref: Git reference to compare against (default: None = HEAD)
    
    Raises:
        SystemExit: If JSON generation fails
    """
    try:
        logging.info(f"Generating JSON output to: {json_path}")
        ripple_result = get_ripple_effect_data(build_dir, repo_dir, from_ref)
        json_output = json.dumps(asdict(ripple_result), indent=2)
        
        # Ensure output directory exists
        output_path = Path(json_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(json_path, 'w', encoding='utf-8') as f:
            f.write(json_output)
        
        logging.info(f"Successfully wrote JSON output to {json_path}")
        print_success(f"JSON output written to: {json_path}")
    except Exception as e:
        logging.exception(f"Failed to write JSON output: {e}")
        print_error(f"writing JSON output: {e}", prefix=False)
        raise RuntimeError(f"Failed to write JSON output: {e}") from e


def run_analysis_workflow(build_dir: str, repo_dir: str, verbose: bool, from_ref: Optional[str] = None) -> None:
    """Execute the main ripple effect analysis workflow.
    
    Args:
        build_dir: Build directory path
        repo_dir: Repository directory path
        verbose: Whether to show verbose output
        from_ref: Git reference to compare against (default: None = HEAD)
    
    Raises:
        SystemExit: If analysis fails
    """
    try:
        comparison_ref = from_ref if from_ref else "HEAD"
        print(f"{Colors.CYAN}Analyzing working directory changes vs {comparison_ref}{Colors.RESET}")
        logging.info(f"Analyzing working directory changes vs {comparison_ref}")
        
        if from_ref:
            # Validate that from_ref is a linear ancestor of HEAD
            validate_ancestor_relationship(repo_dir, from_ref)
            changed_files, _ = get_working_tree_changes_from_commit(repo_dir, from_ref)
        else:
            changed_files = get_uncommitted_changes(repo_dir)
        
        if not changed_files:
            logging.info("No uncommitted changes")
            print_warning("No uncommitted changes in working directory", prefix=False)
            return
        
        print_success(f"Found {len(changed_files)} changed files")
        
        # Categorize changed files
        changed_headers, changed_sources = categorize_changed_files(changed_files)
        
        if not changed_headers and not changed_sources:
            logging.info("No C/C++ files changed")
            print_warning("No C/C++ source or header files changed", prefix=False)
            return
        
        print(f"{Colors.BLUE}C/C++ changes: {len(changed_headers)} headers, {len(changed_sources)} sources{Colors.RESET}")
        
        # Analyze ripple effect
        logging.info("Starting ripple effect analysis")
        analysis_result = analyze_ripple_effect(build_dir, changed_headers, changed_sources, verbose=verbose)
        logging.info("Ripple effect analysis completed")
        
        # Print report
        print_ripple_report(changed_headers, changed_sources, analysis_result, repo_dir)
        logging.info("Analysis complete")
        
    except KeyboardInterrupt:
        logging.warning("Analysis interrupted by user")
        print_warning("\nAnalysis interrupted by user", prefix=False)
        sys.exit(130)
    except Exception as e:
        logging.exception(f"Analysis failed: {e}")
        print_error(f"during analysis: {e}", prefix=False)
        sys.exit(1)


def main() -> int:
    """Main entry point for the script.
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Verify dependencies early
    pass  # Dependencies assumed to be installed
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Setup logging
    setup_logging(args.log_level)
    logging.info("Starting buildCheckRippleEffect analysis")
    
    # Validate build directory using library helper
    try:
        build_dir, _ = validate_build_directory_with_feedback(args.build_directory, verbose=True)
    except (ValueError, RuntimeError) as e:
        # Error message already printed by helper
        return 1
    
    # Find or validate git repository
    try:
        repo_dir = validate_git_repository_path(args.repo, build_dir)
    except (ValueError, RuntimeError) as e:
        # Error message already printed
        return 1
    
    # JSON output mode
    if args.json:
        try:
            write_json_output_file(args.json, build_dir, repo_dir, args.from_ref)
            return 0
        except RuntimeError:
            # Error message already printed
            return 1
    
    # Run main analysis workflow
    run_analysis_workflow(build_dir, repo_dir, args.verbose, args.from_ref)
    return 0


if __name__ == "__main__":
    from lib.constants import (
        EXIT_SUCCESS, EXIT_KEYBOARD_INTERRUPT, EXIT_INVALID_ARGS, EXIT_RUNTIME_ERROR,
        BuildCheckError
    )
    
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        print_warning("\nInterrupted by user", prefix=False)
        sys.exit(EXIT_KEYBOARD_INTERRUPT)
    except BuildCheckError as e:
        logging.error(str(e))
        sys.exit(e.exit_code)
    except ValueError as e:
        logging.error(f"Validation error: {e}")
        sys.exit(EXIT_INVALID_ARGS)
    except Exception as e:
        logging.exception(f"Unexpected error: {e}")
        print_error(f"Fatal error: {e}")
        sys.exit(EXIT_RUNTIME_ERROR)
