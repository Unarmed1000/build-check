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
"""Dependency Structure Matrix (DSM) analysis for C++ header dependencies.

Version: 1.0.0

PURPOSE:
    Visualizes header dependencies as a Dependency Structure Matrix, providing a
    comprehensive architectural view of the codebase. Identifies circular dependencies,
    analyzes layered architecture, and highlights high-coupling headers that may need
    refactoring.

WHAT IT DOES:
    - Builds a Dependency Structure Matrix showing header-to-header dependencies
    - Detects circular dependencies (strongly connected components)
    - Computes architectural layers using topological ordering
    - Calculates per-header metrics: fan-in, fan-out, stability, coupling
    - Identifies headers that violate layered architecture
    - Provides compact matrix visualization with color coding
    - Exports full matrix to CSV for detailed offline analysis
    - Compares DSM between two builds (differential analysis)

USE CASES:
    - "Show me the overall dependency structure of my codebase"
    - "Which headers are in circular dependencies?"
    - "Is my architecture properly layered?"
    - "What's the safest order to refactor headers?"
    - "Which headers have the highest coupling?"
    - "Are my module boundaries clean?"
    - "How did my architecture change between two commits/branches?"
    - "Did my refactoring introduce new circular dependencies?"
    - "Did I increase or decrease coupling with my changes?"
    - "What will rebuild if I commit my current changes?" (--git-impact)
    - "What architectural risks do my uncommitted changes pose?" (--git-impact)
    - "Which of my changed headers are in circular dependencies?" (--git-impact)
    - "What should I refactor to improve my codebase?" (--suggest-improvements)
    - "Which refactorings give the best return on investment?" (--suggest-improvements)
    - "Show me quick wins for architectural improvement" (--suggest-improvements)
    - "What are the god objects and coupling hotspots?" (--suggest-improvements)

METHOD:
    Parses header files directly using buildCheckDependencyHell's build_include_graph()
    to build an accurate directed dependency graph, then constructs a Dependency Structure
    Matrix showing which headers include which. Applies graph algorithms (SCC detection,
    topological sorting) to analyze architectural properties.

OUTPUT:
    1. Summary Statistics:
       - Matrix size, sparsity, total dependencies
       - Cycle count, layer count

    2. Dependency Structure Matrix (Visual):
       - Compact matrix view (top N×N most coupled headers)
       - Color-coded by coupling strength (green/yellow/red)

    3. Circular Dependencies:
       - List of cycles with participants
       - Suggested edges to break cycles

    4. Layered Architecture:
       - Headers grouped by dependency layer
       - Layer violations (back-edges)

    5. High-Coupling Headers:
       - Headers with highest fan-in/fan-out
       - Stability analysis

    6. Differential Analysis (with --compare-with):
       - Headers added/removed between builds
       - Circular dependencies introduced/resolved
       - Coupling changes per header
       - Layer shifts (architectural depth changes)
       - Overall assessment (regressions/improvements)

METRICS EXPLAINED:
    - Fan-out: Number of headers this header includes
    - Fan-in: Number of headers that include this header
    - Coupling: Total dependencies (fan-in + fan-out)
    - Stability: Fan-out / (Fan-in + Fan-out) - measures resistance to change
    - Sparsity: Percentage of empty cells in matrix
    - Layer: Topological level in dependency hierarchy (0 = foundation)

PERFORMANCE:
    Similar to buildCheckIncludeGraph.py (3-10 seconds). Uses NetworkX for efficient
    graph analysis. Results can be cached.

"""
__version__ = "1.2.0"

import os
import sys
import argparse
import logging
from typing import Dict, Set, List, Tuple, DefaultDict, Any

# Import library modules
from lib.color_utils import Colors, print_error, print_warning, print_success
from lib.constants import DEFAULT_TOP_N, EXIT_INVALID_ARGS, EXIT_RUNTIME_ERROR, EXIT_KEYBOARD_INTERRUPT, EXIT_SUCCESS, BuildCheckError
from lib.file_utils import filter_headers_by_pattern, cluster_headers_by_directory, exclude_headers_by_patterns, filter_by_file_type, FilterStatistics
from lib.library_parser import map_headers_to_libraries
from lib.export_utils import export_dsm_to_csv, export_dependency_graph
from lib.ninja_utils import validate_build_directory_with_feedback
from lib.dsm_analysis import (
    run_dsm_analysis,
    display_analysis_results,
    run_differential_analysis,
    run_differential_analysis_with_baseline,
    run_git_working_tree_analysis,
    run_proactive_improvement_analysis,
)
from lib.dsm_types import DSMAnalysisResults
from lib.dsm_serialization import save_dsm_results, load_dsm_results

# Import build_include_graph from library
from lib.clang_utils import build_include_graph, FileType

# Explicitly export functions for testing
__all__ = [
    "filter_headers_by_pattern",
    "cluster_headers_by_directory",
    "exclude_headers_by_patterns",
    "apply_all_filters",
    "apply_exclude_filters",
    "DSMAnalysisResults",
]


def validate_and_prepare_args(args: argparse.Namespace) -> Tuple[str, str]:
    """Validate command-line arguments and prepare paths.

    Args:
        args: Parsed command-line arguments

    Returns:
        Tuple of (build_dir, project_root) as absolute paths

    Raises:
        ValueError: If arguments are invalid
    """
    # Validate arguments
    if not args.build_directory:
        raise ValueError("Build directory not specified")

    if args.top < 0:
        raise ValueError(f"--top must be non-negative, got {args.top}")

    # Validate and prepare build directory
    build_dir, _ = validate_build_directory_with_feedback(args.build_directory, verbose=False)
    logging.info("Build directory: %s", build_dir)

    project_root: str = os.path.dirname(os.path.abspath(__file__))

    return build_dir, project_root


def setup_library_mapping(args: argparse.Namespace, all_headers: Set[str]) -> Dict[str, str]:
    """Set up library mapping if requested by command-line options.

    Args:
        args: Parsed command-line arguments
        all_headers: Set of all headers in the project

    Returns:
        Dictionary mapping headers to library names (empty if not requested)

    Raises:
        RuntimeError: If library mapping is required but fails
    """
    if not (args.show_library_boundaries or args.library_filter or args.cross_library_only):
        return {}

    logging.info("Mapping headers to libraries using source file dependencies")
    header_to_lib: Dict[str, str] = map_headers_to_libraries(all_headers)

    if not header_to_lib:
        raise RuntimeError("Library mapping failed")

    num_libs: int = len(set(header_to_lib.values()))
    print(f"{Colors.CYAN}Mapped {len(header_to_lib)} headers to {num_libs} libraries{Colors.RESET}")

    return header_to_lib


def apply_all_filters(
    args: argparse.Namespace, all_headers: Set[str], header_to_lib: Dict[str, str], project_root: str, file_types: Dict[str, Any]
) -> Tuple[Set[str], FilterStatistics]:
    """Apply all filtering options and return filtered header set with statistics.

    Args:
        args: Parsed command-line arguments
        all_headers: Initial set of all headers
        header_to_lib: Mapping of headers to libraries
        project_root: Project root directory for relative paths
        file_types: Pre-computed file type classifications

    Returns:
        Tuple of (filtered_headers, filter_statistics)

    Raises:
        ValueError: If filtering results in empty set or invalid filter
    """
    # Initialize statistics
    stats = FilterStatistics(initial_count=len(all_headers), final_count=0)
    filtered_headers: Set[str] = all_headers

    # Step 1: Apply file scope filtering based on --file-scope argument
    file_scope = getattr(args, "file_scope", "project")
    exclude_types: Set[FileType] = set()

    if file_scope == "project":
        # Exclude both third-party and system files
        exclude_types = {FileType.SYSTEM, FileType.THIRD_PARTY}
    elif file_scope == "thirdparty":
        # Exclude only system files, include third-party
        exclude_types = {FileType.SYSTEM}
    # else file_scope == "system": include everything, no exclusions

    if exclude_types:
        filtered_headers, system_stats = filter_by_file_type(
            filtered_headers, file_types, exclude_types=exclude_types, show_progress=(len(filtered_headers) > 5000)
        )
        stats.system_headers = system_stats
        logging.info("After file scope filtering (%s): %d headers", file_scope, len(filtered_headers))

    # Step 2: Apply library filter if specified
    if args.library_filter:
        if not header_to_lib:
            raise ValueError("Library filter requested but library mapping not available")

        before_count = len(filtered_headers)
        filtered_headers = {header for header in filtered_headers if header_to_lib.get(header) == args.library_filter}

        if not filtered_headers:
            available_libs = sorted(set(header_to_lib.values()))[:10]
            raise ValueError(f"No headers found for library '{args.library_filter}'. " f"Available libraries: {', '.join(available_libs)}...")

        stats.library_filter = {"library": args.library_filter, "matched": len(filtered_headers), "reduced_by": before_count - len(filtered_headers)}
        print_success(f"Filtered to {len(filtered_headers)} headers from {args.library_filter}", prefix=False)

    # Show helpful suggestions for large projects
    if len(filtered_headers) > 500 and not args.filter and not args.library_filter:
        print_warning(f"Large project detected ({len(filtered_headers)} headers). " f"Consider using --filter to focus analysis.", prefix=False)
        print(f"{Colors.DIM}Examples: --filter '*FslBase/*' or --filter '*Graphics/*'{Colors.RESET}")
        if header_to_lib:
            example_lib = next(iter(set(header_to_lib.values())))
            print(f"{Colors.DIM}Or filter by library: --library-filter '{example_lib}'{Colors.RESET}")

    # Step 3: Apply pattern filter if specified
    if args.filter:
        logging.info("Applying filter: %s", args.filter)
        before_count = len(filtered_headers)
        filtered_headers = filter_headers_by_pattern(filtered_headers, args.filter, project_root)

        stats.filter_pattern = {"pattern": args.filter, "matched": len(filtered_headers), "reduced_by": before_count - len(filtered_headers)}
        print_success(f"Filtered to {len(filtered_headers)} headers matching '{args.filter}'", prefix=False)

    if not filtered_headers:
        raise ValueError("No headers found after filtering")

    # Step 4: Apply exclude patterns if specified
    if hasattr(args, "exclude") and args.exclude:
        filtered_headers, excluded_count, no_match_patterns, exclude_stats = apply_exclude_filters(filtered_headers, args.exclude, project_root)
        stats.exclude_patterns = exclude_stats

        if excluded_count > 0:
            print_success(f"Excluded {excluded_count} headers matching {len(args.exclude)} pattern(s)", prefix=False)

        # Warn about patterns that matched nothing
        for pattern in no_match_patterns:
            print_warning(f"Exclude pattern '{pattern}' matched no headers", prefix=False)

    if not filtered_headers:
        raise ValueError("No headers found after filtering and exclusions")

    stats.final_count = len(filtered_headers)
    return filtered_headers, stats


def apply_exclude_filters(headers: Set[str], exclude_patterns: List[str], project_root: str) -> tuple[Set[str], int, List[str], Dict[str, Any]]:
    """Apply exclude patterns to filter out unwanted headers.

    Args:
        headers: Set of header paths
        exclude_patterns: List of glob patterns to exclude
        project_root: Project root directory for relative paths

    Returns:
        Tuple of (filtered_headers, excluded_count, patterns_with_no_matches, statistics_dict)
    """
    if not exclude_patterns:
        return headers, 0, [], {}

    logging.info("Applying %d exclude pattern(s)", len(exclude_patterns))
    for pattern in exclude_patterns:
        logging.debug("  Exclude pattern: %s", pattern)

    return exclude_headers_by_patterns(headers, exclude_patterns, project_root)


def main() -> int:
    """Main entry point for the DSM analysis tool.

    Orchestrates the complete DSM analysis workflow:
    1. Parse and validate command-line arguments
    2. Build dependency graph from compilation database
    3. Apply filters (library, pattern, directory)
    4. Run DSM analysis (metrics, cycles, layers)
    5. Display results and recommendations
    6. Export data if requested

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Dependency Structure Matrix (DSM) analysis for C++ headers.",
        epilog="""
This tool visualizes header dependencies as a matrix, identifies circular
dependencies, analyzes layered architecture, and highlights high-coupling headers.

The DSM provides an architectural "big picture" view showing:
  • Which headers depend on which (matrix visualization)
  • Circular dependency groups (strongly connected components)
  • Architectural layers (topological ordering)
  • Per-header coupling metrics (fan-in, fan-out, stability)

Use this tool for architectural reviews, refactoring planning, and validating
that module boundaries are clean.

Requires: clang-scan-deps (install: sudo apt install clang-19)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}", help="Show version and exit")

    parser.add_argument("build_directory", metavar="BUILD_DIR", help="Path to the ninja build directory (e.g., build/release)")

    parser.add_argument(
        "--top", type=int, default=DEFAULT_TOP_N, help=f"Number of headers to show in matrix (default: {DEFAULT_TOP_N}, use 0 to disable matrix display)"
    )

    parser.add_argument("--cycles-only", action="store_true", help="Show only circular dependency analysis")

    parser.add_argument("--show-layers", action="store_true", help="Show hierarchical layer structure (automatically shown if architecture is clean)")

    parser.add_argument("--export", type=str, metavar="FILE.csv", help="Export full matrix to CSV file")

    parser.add_argument(
        "--export-graph",
        type=str,
        metavar="FILE",
        help="Export dependency graph with library/module grouping (formats: .graphml, .dot, .gexf, .json). "
        "Includes library attributes for visualization tools (Gephi, yEd, Cytoscape). "
        "Use with --show-library-boundaries for enhanced library metadata.",
    )

    parser.add_argument("--filter", type=str, metavar="PATTERN", help='Filter headers by glob pattern (e.g., "FslBase/*")')

    parser.add_argument(
        "--exclude",
        type=str,
        action="append",
        metavar="PATTERN",
        help="Exclude headers matching glob pattern (can be used multiple times). "
        "Useful for excluding third-party libraries, generated files, or test code. "
        "Supports glob patterns: * (any chars), ** (recursive), ? (single char). "
        'Examples: "*/ThirdParty/*", "*/build/*", "*_generated.h", "*/test/*"',
    )

    parser.add_argument("--cluster-by-directory", action="store_true", help="Group headers by directory in output")

    parser.add_argument(
        "--show-library-boundaries", action="store_true", help="Show which library each header belongs to and analyze cross-library dependencies"
    )

    parser.add_argument("--library-filter", type=str, metavar="LIBRARY", help='Show only headers from specified library (e.g., "libFslBase.a")')

    parser.add_argument(
        "--cross-library-only", action="store_true", help="Show only dependencies that cross library boundaries (identifies boundary violations)"
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")

    parser.add_argument(
        "--file-scope",
        type=str,
        choices=["project", "thirdparty", "system"],
        default="project",
        help="File scope for analysis (default: project). "
        "project: only user project files (excludes third-party and system headers). "
        "thirdparty: project + third-party libraries (excludes system headers). "
        "system: all files including system headers (/usr/*, /lib/*, /opt/*).",
    )

    parser.add_argument(
        "--sort-by",
        type=str,
        choices=["coupling", "topological"],
        default="topological",
        help="Sort DSM matrix by coupling (highest first) or topological layers (foundation first). "
        "Default: topological. Topological sorting shows dependencies in build order; "
        "falls back to coupling if cycles exist.",
    )

    parser.add_argument(
        "--compare-with", type=str, metavar="BASELINE_BUILD_DIR", help="Compare DSM against baseline build directory (enables differential analysis)"
    )

    parser.add_argument(
        "--save-results", type=str, metavar="FILE.dsm.json.gz", help="Save DSM analysis results to compressed file for later comparison (gzip compressed JSON)"
    )

    parser.add_argument(
        "--load-baseline",
        type=str,
        metavar="FILE.dsm.json.gz",
        help="Load baseline DSM results from file and compare with current build " "(baseline must be from same build directory and system)",
    )

    parser.add_argument(
        "--git-impact",
        action="store_true",
        help="Analyze architectural and rebuild impact of uncommitted changes in working tree "
        "(compares working tree against HEAD). Shows which headers changed, rebuild percentage, "
        "architectural risks, and cycle involvement. Repository auto-detected from build directory.",
    )

    parser.add_argument(
        "--git-from",
        type=str,
        metavar="REF",
        default="HEAD",
        help="Git reference to compare working tree against (default: HEAD). "
        "Supports: commits (abc123), branches (main, origin/develop), tags (v1.0), "
        "relative refs (HEAD~5, HEAD~10). Requires --git-impact.",
    )

    parser.add_argument(
        "--git-repo",
        type=str,
        metavar="PATH",
        help="Explicit path to git repository (default: auto-detect from build directory). " "Useful when build directory is outside the repository.",
    )

    parser.add_argument(
        "--suggest-improvements",
        action="store_true",
        help="Analyze current codebase and suggest high-impact architectural improvements "
        "(proactive mode, no baseline required). Identifies god objects, cycles, coupling outliers, "
        "unstable interfaces, and hub nodes. Provides ROI-ranked recommendations with break-even analysis.",
    )

    parser.add_argument(
        "--sensitivity",
        type=str,
        choices=["low", "medium", "high"],
        default="medium",
        help="Detection sensitivity for anti-patterns (default: medium). "
        "Low: fewer candidates, high thresholds (large projects). "
        "Medium: balanced detection (most projects). "
        "High: more candidates, strict thresholds (small projects or aggressive refactoring).",
    )

    parser.add_argument(
        "--debug-sanitization", action="store_true", help="Enable detailed logging of compile command sanitization (shows what gets removed and why)"
    )

    args: argparse.Namespace = parser.parse_args()

    # Set logging level based on verbose flag
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Verbose logging enabled")

    # Set debug sanitization if requested
    if args.debug_sanitization:
        from lib.clang_utils import set_debug_sanitization

        set_debug_sanitization(True)
        logging.info("Debug sanitization enabled")

    try:
        # Phase 1: Validate and prepare
        build_dir, project_root = validate_and_prepare_args(args)

        # Validate mutually exclusive options
        if args.compare_with and args.load_baseline:
            raise ValueError("Cannot use both --compare-with and --load-baseline simultaneously")

        if args.git_impact and (args.compare_with or args.load_baseline):
            raise ValueError("Cannot use --git-impact with --compare-with or --load-baseline")

        if args.suggest_improvements and (args.compare_with or args.load_baseline or args.git_impact):
            raise ValueError("Cannot use --suggest-improvements with comparison modes (--compare-with, --load-baseline, --git-impact)")

        if args.git_from != "HEAD" and not args.git_impact:
            raise ValueError("--git-from requires --git-impact")

        # Check if proactive improvement analysis is requested
        if args.suggest_improvements:
            return run_proactive_improvement_analysis(
                build_dir=build_dir,
                project_root=project_root,
                filter_pattern=args.filter,
                exclude_patterns=args.exclude if hasattr(args, "exclude") else None,
                top_n=args.top if args.top > 0 else 10,
                verbose=args.verbose,
                file_scope=getattr(args, "file_scope", "project"),
                sensitivity=args.sensitivity,
            )

        # Check if git working tree analysis is requested
        if args.git_impact:
            return run_git_working_tree_analysis(
                build_dir=build_dir,
                project_root=project_root,
                git_from_ref=args.git_from,
                git_repo_path=args.git_repo,
                verbose=args.verbose,
                filter_pattern=args.filter,
                exclude_patterns=args.exclude if hasattr(args, "exclude") else None,
                show_layers=args.show_layers,
                file_scope=getattr(args, "file_scope", "project"),
            )

        # Check if differential analysis is requested
        if args.compare_with:
            return run_differential_analysis(
                build_dir, args.compare_with, project_root, verbose=args.verbose, file_scope=getattr(args, "file_scope", "project")
            )

        # Phase 2: Build dependency graph
        print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
        print(f"{Colors.BRIGHT}DEPENDENCY STRUCTURE MATRIX ANALYSIS{Colors.RESET}")
        print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}\n")

        header_to_headers: DefaultDict[str, Set[str]]
        all_headers: Set[str]
        elapsed: float

        try:
            scan_result = build_include_graph(build_dir)
            header_to_headers = scan_result.include_graph
            all_headers = scan_result.all_headers
            file_types = scan_result.file_types
            elapsed = scan_result.scan_time
        except Exception as e:
            logging.error("Failed to build include graph: %s", e)
            raise RuntimeError(f"Failed to build include graph: {e}") from e

        print_success(f"Built directed include graph with {len(all_headers)} headers in {elapsed:.1f}s", prefix=False)

        # Keep unfiltered data for saving baselines
        unfiltered_headers: Set[str] = all_headers.copy()
        unfiltered_include_graph: DefaultDict[str, Set[str]] = header_to_headers
        # Compute all_files (headers + sources) for baseline
        all_files: Set[str] = set(all_headers)
        all_files.update(scan_result.source_to_deps.keys())

        # Phase 3: Setup library mapping (if requested)
        header_to_lib: Dict[str, str] = setup_library_mapping(args, all_headers)

        # Phase 4: Apply all filters
        all_headers, filter_stats = apply_all_filters(args, all_headers, header_to_lib, project_root, file_types)

        # Display filtering scope
        print(f"\n{Colors.BRIGHT}Filter Scope:{Colors.RESET} {filter_stats.format_concise()}\n")
        if args.verbose:
            verbose_output = filter_stats.format_verbose(project_root)
            if verbose_output:
                print(verbose_output)

        # Phase 5: Run DSM analysis
        compute_layers_flag = args.show_layers or not args.cycles_only
        results: DSMAnalysisResults = run_dsm_analysis(
            all_headers,
            header_to_headers,
            compute_layers=compute_layers_flag,
            show_progress=True,
            source_to_deps=scan_result.source_to_deps,
            file_types=file_types,
        )

        # Phase 6: Display results
        display_analysis_results(
            results,
            project_root,
            header_to_lib,
            top_n=args.top,
            cycles_only=args.cycles_only,
            show_layers=args.show_layers,
            show_library_boundaries=args.show_library_boundaries,
            cluster_by_directory=args.cluster_by_directory,
            sort_by=args.sort_by,
            verbose=args.verbose,
        )

        # Phase 7: Export data (if requested)
        if args.export:
            export_dsm_to_csv(args.export, results.sorted_headers, results.header_to_headers, results.metrics, project_root)

        if args.export_graph:
            export_dependency_graph(
                args.export_graph, results.directed_graph, results.metrics, results.cycles, project_root, header_to_lib, results.header_to_headers
            )

        # Save results (if requested)
        if args.save_results:
            save_dsm_results(results, all_files, unfiltered_include_graph, file_types, args.save_results, build_dir, args.filter, args.exclude)

        # Load and compare with baseline (if requested)
        if args.load_baseline:
            # Load unfiltered baseline data
            baseline_headers, baseline_include_graph, baseline_file_types = load_dsm_results(args.load_baseline, build_dir, project_root)

            # Apply identical filtering to baseline as current analysis
            baseline_headers, baseline_filter_stats = apply_all_filters(args, baseline_headers, header_to_lib, project_root, baseline_file_types)

            # Run DSM analysis on filtered baseline
            baseline_results = run_dsm_analysis(
                baseline_headers, baseline_include_graph, compute_layers=compute_layers_flag, show_progress=False, file_types=baseline_file_types
            )

            # Display side-by-side filter scope comparison
            print(f"\n{Colors.BRIGHT}Filter Scope Comparison:{Colors.RESET}")
            print(f"  Current:  {filter_stats.format_concise()}")
            print(f"  Baseline: {baseline_filter_stats.format_concise()}\n")

            if args.verbose:
                print(f"{Colors.BRIGHT}Current Filtering Details:{Colors.RESET}")
                verbose_current = filter_stats.format_verbose(project_root)
                if verbose_current:
                    print(verbose_current)

                print(f"\n{Colors.BRIGHT}Baseline Filtering Details:{Colors.RESET}")
                verbose_baseline = baseline_filter_stats.format_verbose(project_root)
                if verbose_baseline:
                    print(verbose_baseline)

            # Run differential analysis with architectural insights
            return run_differential_analysis_with_baseline(results, baseline_results, project_root, verbose=args.verbose)

        return EXIT_SUCCESS

    except ValueError as e:
        # Validation errors - user fixable
        logging.error("Validation error: %s", e)
        print_error(str(e))
        if "build.ninja" in str(e):
            print("Please provide the path to the ninja build directory containing build.ninja")
        return EXIT_INVALID_ARGS

    except RuntimeError as e:
        # Runtime errors - possibly transient
        logging.error("Runtime error: %s", e)
        print_error(f"Runtime error: {e}")
        print_warning("Run with --verbose for more details", prefix=False)
        return EXIT_RUNTIME_ERROR

    except Exception as e:  # pylint: disable=broad-exception-caught
        # Unexpected errors - catch all to provide user-friendly error message
        logging.critical("Unexpected error: %s", e, exc_info=True)
        print_error(f"Fatal error: {e}")
        print_warning("Run with --verbose for more details", prefix=False)
        return EXIT_RUNTIME_ERROR


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        print_warning("\\nInterrupted by user", prefix=False)
        sys.exit(EXIT_KEYBOARD_INTERRUPT)
    except BuildCheckError as e:
        logging.error(str(e))
        sys.exit(e.exit_code)
    except ImportError as e:
        logging.error("Missing dependency: %s", e)
        sys.exit(EXIT_RUNTIME_ERROR)
    except Exception as e:
        logging.error("Unexpected error: %s", e)
        sys.exit(EXIT_RUNTIME_ERROR)
