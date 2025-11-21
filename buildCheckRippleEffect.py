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
"""Analyze the ripple effect of git changes on C/C++ compilation.

PURPOSE:
    Determines which C/C++ source files will be recompiled based on changes
    in the last git commit (or specified commit). Uses dependency analysis
    from buildCheckDependencyHell.py to compute transitive impact.

WHAT IT DOES:
    - Detects changed files from git commit (headers and source files)
    - Uses clang-scan-deps to build complete dependency graph
    - For changed headers: finds all source files that transitively depend on them
    - For changed source files: directly marks them for recompilation
    - Calculates total rebuild impact and shows detailed breakdown

USE CASES:
    - "If I commit this header change, what will rebuild?"
    - Estimate CI/CD build time impact before pushing
    - Review code changes with rebuild cost in mind
    - Identify high-impact changes that need extra testing

METHOD:
    1. Run git diff to get changed files from commit
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
    - ninja build directory with compile_commands.json
    - clang-scan-deps (clang-19, clang-18, or clang-XX)
    - networkx: pip install networkx

EXAMPLES:
    # Analyze last commit's impact
    ./buildCheckRippleEffect.py ../build/release/
    
    # Analyze specific commit
    ./buildCheckRippleEffect.py ../build/release/ --commit abc123
    
    # Specify git repository location
    ./buildCheckRippleEffect.py ../build/release/ --repo ~/projects/myproject
    
    # Analyze commit range (shows cumulative impact)
    ./buildCheckRippleEffect.py ../build/release/ --commit HEAD~5..HEAD
"""
import subprocess
import sys
import os
import argparse
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional, List, Tuple

# Import existing functions from buildCheckDependencyHell
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from buildCheckDependencyHell import build_include_graph, build_dependency_graph
except ImportError as e:
    print(f"Error: Failed to import buildCheckDependencyHell: {e}", file=sys.stderr)
    print("Ensure buildCheckDependencyHell.py is in the same directory.", file=sys.stderr)
    sys.exit(1)

try:
    from colorama import Fore, Style, init
    init(autoreset=False)
except ImportError:
    class Fore:
        RED = YELLOW = GREEN = BLUE = MAGENTA = CYAN = WHITE = LIGHTBLACK_EX = RESET = ''
    class Style:
        RESET_ALL = BRIGHT = DIM = ''


def find_git_repo(start_path: str) -> Optional[str]:
    """Find the git repository root by searching upward from start_path."""
    current = os.path.realpath(os.path.abspath(start_path))
    while current != os.path.dirname(current):  # Stop at filesystem root
        git_dir = os.path.realpath(os.path.join(current, '.git'))
        # Validate git_dir is within current (prevent path traversal via symlinks)
        if git_dir.startswith(current + os.sep) or git_dir == os.path.join(current, '.git'):
            if os.path.isdir(git_dir):
                return current
        current = os.path.dirname(current)
    return None


def get_changed_files_from_git(repo_dir: str, commit: str = 'HEAD') -> List[str]:
    """Get list of changed files from git commit.
    
    Args:
        repo_dir: Path to git repository
        commit: Git commit reference (e.g., 'HEAD', 'abc123', 'HEAD~5..HEAD')
    
    Returns:
        List of changed file paths (absolute paths)
    """
    try:
        # Validate repo_dir exists
        if not os.path.isdir(repo_dir):
            raise ValueError(f"Repository directory does not exist: {repo_dir}")
        
        # Handle commit ranges (e.g., HEAD~5..HEAD)
        if '..' in commit:
            cmd = ['git', 'diff', '--name-only', commit]
        else:
            # Single commit - compare with parent
            cmd = ['git', 'diff', '--name-only', f'{commit}~1', commit]
        
        logging.debug(f"Running git command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=repo_dir,
            check=True,
            timeout=30  # Prevent hanging
        )
        
        # Convert relative paths to absolute and validate
        repo_dir_real = os.path.realpath(repo_dir)
        changed_files = []
        for line in result.stdout.strip().split('\n'):
            if line:
                abs_path = os.path.realpath(os.path.join(repo_dir, line))
                # Validate path is within repo_dir (prevent path traversal)
                if not abs_path.startswith(repo_dir_real + os.sep):
                    logging.warning(f"Path traversal detected, skipping: {line}")
                    continue
                if os.path.exists(abs_path):
                    changed_files.append(abs_path)
                else:
                    logging.warning(f"File from git diff does not exist: {abs_path}")
        
        logging.info(f"Found {len(changed_files)} changed files")
        return changed_files
    
    except subprocess.TimeoutExpired:
        logging.error(f"Git command timed out after 30 seconds")
        print(f"{Fore.RED}Error: Git command timed out{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        logging.error(f"Git command failed: {e}")
        print(f"{Fore.RED}Error running git diff: {e}{Style.RESET_ALL}", file=sys.stderr)
        if e.stderr:
            print(f"{Fore.YELLOW}{e.stderr.strip()}{Style.RESET_ALL}", file=sys.stderr)
        print(f"{Fore.YELLOW}Hint: Ensure '{commit}' is a valid commit reference{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        logging.error(str(e))
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logging.exception(f"Unexpected error in get_changed_files_from_git: {e}")
        print(f"{Fore.RED}Unexpected error: {e}{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(1)


def categorize_changed_files(changed_files: List[str]) -> Tuple[List[str], List[str]]:
    """Categorize changed files into headers and sources.
    
    Args:
        changed_files: List of file paths to categorize
    
    Returns:
        Tuple of (header_files, source_files)
    """
    if not isinstance(changed_files, list):
        raise TypeError(f"changed_files must be a list, got {type(changed_files)}")
    
    headers = []
    sources = []
    other_files = []
    
    for file in changed_files:
        if not isinstance(file, str):
            logging.warning(f"Skipping non-string file entry: {file}")
            continue
            
        ext = os.path.splitext(file)[1].lower()
        if ext in ['.h', '.hpp', '.hxx', '.hh']:
            headers.append(file)
        elif ext in ['.cpp', '.c', '.cc', '.cxx', '.C']:
            sources.append(file)
        else:
            other_files.append(file)
    
    if other_files:
        logging.debug(f"Ignored {len(other_files)} non-C/C++ files")
    
    logging.info(f"Categorized: {len(headers)} headers, {len(sources)} sources")
    return headers, sources


def analyze_ripple_effect(build_dir: str, changed_headers: list[str], changed_sources: list[str], verbose: bool = False) -> dict:
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
    build_dir = os.path.realpath(os.path.abspath(build_dir))
    if not os.path.isdir(build_dir):
        raise ValueError(f"Build directory does not exist: {build_dir}")
    
    compile_commands = os.path.realpath(os.path.join(build_dir, 'compile_commands.json'))
    # Validate compile_commands is within build_dir
    if not compile_commands.startswith(build_dir + os.sep):
        raise ValueError(f"Path traversal detected: compile_commands.json")
    if not os.path.isfile(compile_commands):
        raise ValueError(f"compile_commands.json not found in {build_dir}")
    
    if not isinstance(changed_headers, list) or not isinstance(changed_sources, list):
        raise TypeError("changed_headers and changed_sources must be lists")
    
    logging.info(f"Analyzing {len(changed_headers)} headers and {len(changed_sources)} sources")
    
    if verbose:
        print(f"{Fore.BLUE}Building dependency graph...{Style.RESET_ALL}")
    
    # Build complete include graph
    try:
        source_to_deps, include_graph, all_headers, scan_time = build_include_graph(build_dir)
    except Exception as e:
        logging.error(f"Failed to build include graph: {e}")
        raise RuntimeError(f"Failed to build dependency graph: {e}") from e
    
    if not source_to_deps:
        logging.warning("No dependencies found in build directory")
        raise RuntimeError("No compilation units found - check compile_commands.json")
    
    if verbose:
        print(f"{Fore.GREEN}Dependency graph built in {scan_time:.2f}s{Style.RESET_ALL}")
    
    # Build reverse dependency map: header -> list of sources that depend on it
    if verbose:
        print(f"{Fore.BLUE}Computing reverse dependencies...{Style.RESET_ALL}")
    header_to_sources = defaultdict(set)
    
    for source, deps in source_to_deps.items():
        # Extract the source file path from the target
        # Targets are like "path/to/file.cpp.o", we want "path/to/file.cpp"
        source_file = source
        if source.endswith('.o'):
            # Strip .o and check if it's a valid source
            source_file = source[:-2]
        
        # Add this source to all headers it depends on (transitively)
        for dep in deps:
            if dep.endswith(('.h', '.hpp', '.hxx')):
                header_to_sources[dep].add(source_file)
    
    if verbose:
        print(f"{Fore.GREEN}Reverse dependency map built{Style.RESET_ALL}")
    
    # Analyze impact of changed headers
    affected_sources = {}
    total_affected = set()
    
    for header in changed_headers:
        sources = header_to_sources.get(header, set())
        if sources:
            affected_sources[header] = sorted(sources)
            total_affected.update(sources)
    
    # Changed source files are directly affected
    direct_sources = set(changed_sources)
    
    if verbose:
        print()
    
    return {
        'affected_sources': affected_sources,
        'total_affected': total_affected,
        'direct_sources': direct_sources,
        'source_to_deps': source_to_deps,
        'header_to_sources': header_to_sources
    }


def print_ripple_report(changed_headers: list[str], changed_sources: list[str], analysis_result: dict, repo_dir: str) -> None:
    """Print formatted ripple effect report.
    
    Args:
        changed_headers: List of changed header files
        changed_sources: List of changed source files
        analysis_result: Dictionary containing analysis results
        repo_dir: Path to git repository for relative path display
    """
    # Validate required keys in analysis_result
    required_keys = ['affected_sources', 'total_affected', 'direct_sources', 'source_to_deps']
    missing_keys = [k for k in required_keys if k not in analysis_result]
    if missing_keys:
        raise ValueError(f"analysis_result missing required keys: {missing_keys}")
    
    affected_sources = analysis_result['affected_sources']
    total_affected = analysis_result['total_affected']
    direct_sources = analysis_result['direct_sources']
    source_to_deps = analysis_result['source_to_deps']
    
    # Calculate total unique sources that will rebuild
    all_affected = total_affected.union(direct_sources)
    total_sources = len(source_to_deps)
    
    print(f"\n{Style.BRIGHT}═══ Git Change Ripple Effect Analysis ═══{Style.RESET_ALL}\n")
    
    # Summary statistics
    total_changed = len(changed_headers) + len(changed_sources)
    rebuild_pct = (len(all_affected) / total_sources * 100) if total_sources > 0 else 0
    
    # Color code based on impact
    if len(all_affected) > 100:
        impact_color = Fore.RED
        severity = "HIGH IMPACT"
    elif len(all_affected) > 50:
        impact_color = Fore.YELLOW
        severity = "MODERATE IMPACT"
    else:
        impact_color = Fore.CYAN
        severity = "LOW IMPACT"
    
    print(f"{Style.BRIGHT}Summary:{Style.RESET_ALL}")
    print(f"  Changed files: {Fore.CYAN}{total_changed}{Style.RESET_ALL} ({len(changed_headers)} headers, {len(changed_sources)} sources)")
    print(f"  Affected sources: {impact_color}{len(all_affected)}{Style.RESET_ALL} / {total_sources} ({rebuild_pct:.1f}%)")
    print(f"  Severity: {impact_color}{severity}{Style.RESET_ALL}\n")
    
    # Show changed files
    if changed_headers:
        print(f"{Style.BRIGHT}Changed Headers ({len(changed_headers)}):{Style.RESET_ALL}")
        for header in sorted(changed_headers):
            display_path = os.path.relpath(header, repo_dir) if header.startswith(repo_dir) else header
            num_affected = len(affected_sources.get(header, []))
            
            if num_affected > 20:
                color = Fore.RED
            elif num_affected > 10:
                color = Fore.YELLOW
            else:
                color = Fore.CYAN
            
            print(f"  {color}{display_path}{Style.RESET_ALL} → affects {num_affected} sources")
    
    if changed_sources:
        print(f"\n{Style.BRIGHT}Changed Sources ({len(changed_sources)}):{Style.RESET_ALL}")
        for source in sorted(changed_sources):
            display_path = os.path.relpath(source, repo_dir) if source.startswith(repo_dir) else source
            print(f"  {Fore.MAGENTA}{display_path}{Style.RESET_ALL} → directly recompiles")
    
    # Detailed breakdown by header
    if changed_headers and affected_sources:
        print(f"\n{Style.BRIGHT}Detailed Ripple Effect:{Style.RESET_ALL}")
        
        # Sort headers by impact (most affected sources first)
        sorted_headers = sorted(affected_sources.items(), key=lambda x: len(x[1]), reverse=True)
        
        for header, sources in sorted_headers:
            display_path = os.path.relpath(header, repo_dir) if header.startswith(repo_dir) else header
            num_affected = len(sources)
            
            if num_affected > 20:
                color = Fore.RED
            elif num_affected > 10:
                color = Fore.YELLOW
            else:
                color = Fore.CYAN
            
            print(f"\n  {color}{display_path}{Style.RESET_ALL} → {num_affected} affected sources:")
            
            # Show up to 10 affected sources
            for source in sources[:10]:
                display_source = os.path.relpath(source, repo_dir) if source.startswith(repo_dir) else source
                # Remove .o extension if present
                if display_source.endswith('.o'):
                    display_source = display_source[:-2]
                print(f"    {Style.DIM}{display_source}{Style.RESET_ALL}")
            
            if num_affected > 10:
                print(f"    {Style.DIM}... and {num_affected - 10} more{Style.RESET_ALL}")


def get_ripple_effect_data(build_dir: str, repo_dir: str, commit: str = 'HEAD') -> dict:
    """
    Get structured ripple effect analysis data without printing.
    
    Args:
        build_dir: Path to ninja build directory
        repo_dir: Path to git repository
        commit: Git commit reference to analyze
    
    Returns:
        dict with keys:
            - changed_headers: list of changed header file paths
            - changed_sources: list of changed source file paths
            - affected_sources_by_header: dict mapping header -> list of affected source paths
            - all_affected_sources: list of all unique affected source file paths
            - total_sources: total number of source files in build
            - rebuild_percentage: percentage of sources affected
    
    Raises:
        ValueError: If build_dir or repo_dir are invalid
        RuntimeError: If analysis fails
    """
    # Validate inputs
    if not build_dir or not isinstance(build_dir, str):
        raise ValueError(f"Invalid build_dir: {build_dir}")
    if not repo_dir or not isinstance(repo_dir, str):
        raise ValueError(f"Invalid repo_dir: {repo_dir}")
    if not commit or not isinstance(commit, str):
        raise ValueError(f"Invalid commit: {commit}")
    
    logging.info(f"Getting ripple effect data for commit: {commit}")
    
    # Get changed files from git
    try:
        changed_files = get_changed_files_from_git(repo_dir, commit)
    except Exception as e:
        logging.error(f"Failed to get changed files: {e}")
        raise
    
    if not changed_files:
        return {
            'changed_headers': [],
            'changed_sources': [],
            'affected_sources_by_header': {},
            'all_affected_sources': [],
            'total_sources': 0,
            'rebuild_percentage': 0.0
        }
    
    # Categorize changed files
    changed_headers, changed_sources = categorize_changed_files(changed_files)
    
    if not changed_headers and not changed_sources:
        return {
            'changed_headers': [],
            'changed_sources': [],
            'affected_sources_by_header': {},
            'all_affected_sources': [],
            'total_sources': 0,
            'rebuild_percentage': 0.0
        }
    
    # Analyze ripple effect (verbose=False to suppress progress messages)
    analysis_result = analyze_ripple_effect(build_dir, changed_headers, changed_sources, verbose=False)
    
    affected_sources = analysis_result.get('affected_sources', {})
    source_to_deps = analysis_result.get('source_to_deps', {})
    total_sources = len(source_to_deps)
    
    # Collect all affected sources
    all_affected = set(changed_sources)
    for sources in affected_sources.values():
        all_affected.update(sources)
    
    rebuild_pct = (len(all_affected) * 100.0 / total_sources) if total_sources > 0 else 0.0
    
    return {
        'changed_headers': sorted(changed_headers),
        'changed_sources': sorted(changed_sources),
        'affected_sources_by_header': {k: sorted(v) for k, v in sorted(affected_sources.items())},
        'all_affected_sources': sorted(all_affected),
        'total_sources': total_sources,
        'rebuild_percentage': rebuild_pct
    }


def main() -> None:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Analyze ripple effect of git changes on C/C++ compilation.',
        prog='buildCheckRippleEffect.py',
        epilog='''
This tool helps you understand the rebuild impact of git commits before pushing.

Examples:
  # Analyze last commit
  %(prog)s ../build/release/
  
  # Analyze specific commit
  %(prog)s ../build/release/ --commit abc123
  
  # Analyze commit range
  %(prog)s ../build/release/ --commit HEAD~5..HEAD
  
  # Specify git repository
  %(prog)s ../build/release/ --repo ~/projects/myproject

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
        '--commit',
        default='HEAD',
        help='Git commit to analyze (default: HEAD). Supports commit hashes, '
             'references (HEAD~1), or ranges (HEAD~5..HEAD)'
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
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = getattr(logging, args.log_level)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    logging.info("Starting buildCheckRippleEffect analysis")
    
    # Validate build directory
    try:
        build_dir = os.path.realpath(os.path.abspath(args.build_directory))
        if not os.path.isdir(build_dir):
            logging.error(f"Build directory does not exist: {build_dir}")
            print(f"{Fore.RED}Error: '{build_dir}' is not a directory{Style.RESET_ALL}", file=sys.stderr)
            sys.exit(1)
        
        # Check for compile_commands.json
        compile_commands = os.path.realpath(os.path.join(build_dir, 'compile_commands.json'))
        # Validate compile_commands is within build_dir
        if not compile_commands.startswith(build_dir + os.sep):
            logging.error("Path traversal detected in compile_commands.json path")
            print(f"{Fore.RED}Error: Path traversal detected{Style.RESET_ALL}", file=sys.stderr)
            sys.exit(1)
        if not os.path.isfile(compile_commands):
            logging.error(f"compile_commands.json not found in {build_dir}")
            print(f"{Fore.RED}Error: compile_commands.json not found in '{build_dir}'{Style.RESET_ALL}", file=sys.stderr)
            print(f"{Fore.YELLOW}Hint: This script requires a Ninja build with compile_commands.json{Style.RESET_ALL}", file=sys.stderr)
            sys.exit(1)
        
        logging.info(f"Using build directory: {build_dir}")
    except Exception as e:
        logging.exception(f"Error validating build directory: {e}")
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(1)
    
    # Find or validate git repository
    try:
        if args.repo:
            repo_dir = os.path.realpath(os.path.abspath(args.repo))
            if not os.path.isdir(repo_dir):
                logging.error(f"Repository directory does not exist: {repo_dir}")
                print(f"{Fore.RED}Error: '{repo_dir}' is not a directory{Style.RESET_ALL}", file=sys.stderr)
                sys.exit(1)
            git_dir = os.path.realpath(os.path.join(repo_dir, '.git'))
            # Validate git_dir is within repo_dir (prevent path traversal)
            if not git_dir.startswith(repo_dir + os.sep):
                logging.error("Path traversal detected in .git path")
                print(f"{Fore.RED}Error: Path traversal detected{Style.RESET_ALL}", file=sys.stderr)
                sys.exit(1)
            if not os.path.isdir(git_dir):
                logging.error(f"Not a git repository: {repo_dir}")
                print(f"{Fore.RED}Error: '{repo_dir}' is not a git repository{Style.RESET_ALL}", file=sys.stderr)
                sys.exit(1)
            logging.info(f"Using git repository: {repo_dir}")
        else:
            # Auto-detect git repo from build directory
            repo_dir = find_git_repo(build_dir)
            if not repo_dir:
                logging.error("Could not find git repository")
                print(f"{Fore.RED}Error: Could not find git repository{Style.RESET_ALL}", file=sys.stderr)
                print(f"{Fore.YELLOW}Hint: Use --repo to specify the repository path{Style.RESET_ALL}", file=sys.stderr)
                sys.exit(1)
            logging.info(f"Auto-detected git repository: {repo_dir}")
            print(f"{Fore.BLUE}Found git repository: {repo_dir}{Style.RESET_ALL}")
    except Exception as e:
        logging.exception(f"Error validating git repository: {e}")
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(1)
    
    # JSON output mode
    if args.json:
        import json
        try:
            logging.info(f"Generating JSON output to: {args.json}")
            result = get_ripple_effect_data(build_dir, repo_dir, args.commit)
            json_output = json.dumps(result, indent=2)
            
            # Ensure output directory exists
            output_path = Path(args.json)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(args.json, 'w', encoding='utf-8') as f:
                f.write(json_output)
            
            logging.info(f"Successfully wrote JSON output to {args.json}")
            print(f"{Fore.GREEN}JSON output written to: {args.json}{Style.RESET_ALL}", file=sys.stderr)
            return
        except Exception as e:
            logging.exception(f"Failed to write JSON output: {e}")
            print(f"{Fore.RED}Error writing JSON output: {e}{Style.RESET_ALL}", file=sys.stderr)
            sys.exit(1)
    
    # Get changed files from git
    try:
        print(f"{Fore.CYAN}Analyzing git changes for commit: {args.commit}{Style.RESET_ALL}")
        logging.info(f"Analyzing commit: {args.commit}")
        changed_files = get_changed_files_from_git(repo_dir, args.commit)
        
        if not changed_files:
            logging.info("No files changed in commit")
            print(f"{Fore.YELLOW}No files changed in commit {args.commit}{Style.RESET_ALL}")
            return
        
        print(f"{Fore.GREEN}Found {len(changed_files)} changed files{Style.RESET_ALL}")
        
        # Categorize changed files
        changed_headers, changed_sources = categorize_changed_files(changed_files)
        
        if not changed_headers and not changed_sources:
            logging.info("No C/C++ files changed")
            print(f"{Fore.YELLOW}No C/C++ source or header files changed in this commit{Style.RESET_ALL}")
            return
        
        print(f"{Fore.BLUE}C/C++ changes: {len(changed_headers)} headers, {len(changed_sources)} sources{Style.RESET_ALL}")
        
        # Analyze ripple effect
        logging.info("Starting ripple effect analysis")
        analysis_result = analyze_ripple_effect(build_dir, changed_headers, changed_sources, verbose=args.verbose)
        logging.info("Ripple effect analysis completed")
        
        # Print report
        print_ripple_report(changed_headers, changed_sources, analysis_result, repo_dir)
        logging.info("Analysis complete")
        
    except KeyboardInterrupt:
        logging.warning("Analysis interrupted by user")
        print(f"\n{Fore.YELLOW}Analysis interrupted by user{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        logging.exception(f"Analysis failed: {e}")
        print(f"{Fore.RED}Error during analysis: {e}{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
