#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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

REQUIREMENTS:
    - Python 3.7+
    - networkx: pip install networkx
    - colorama: pip install colorama (optional, for colored output)
    - clang-scan-deps (clang-19, clang-18, or clang-XX)
    - compile_commands.json (auto-generated from Ninja build)

COMPLEMENTARY TOOLS:
    - buildCheckSummary.py: What changed and will rebuild
    - buildCheckImpact.py: Quick impact check
    - buildCheckIncludeGraph.py: Gateway header analysis
    - buildCheckDependencyHell.py: Multi-metric dependency analysis
    - buildCheckIncludeChains.py: Cooccurrence patterns

EXAMPLES:
    # Basic DSM of all project headers
    ./buildCheckDSM.py ../build/release/

    # Show only top 50 most coupled headers
    ./buildCheckDSM.py ../build/release/ --top 50

    # Focus on cycle analysis only
    ./buildCheckDSM.py ../build/release/ --cycles-only

    # Show hierarchical layers
    ./buildCheckDSM.py ../build/release/ --show-layers

    # Export full matrix to CSV
    ./buildCheckDSM.py ../build/release/ --export matrix.csv

    # Export dependency graph for visualization (with library metadata)
    ./buildCheckDSM.py ../build/release/ --export-graph graph.graphml
    ./buildCheckDSM.py ../build/release/ --export-graph graph.json
    ./buildCheckDSM.py ../build/release/ --export-graph graph.gexf

    # Export with enhanced library grouping information
    ./buildCheckDSM.py ../build/release/ --show-library-boundaries --export-graph graph.graphml

    # Filter to specific directory/module
    ./buildCheckDSM.py ../build/release/ --filter "FslBase/*"

    # Exclude third-party libraries and generated files
    ./buildCheckDSM.py ../build/release/ --exclude "*/ThirdParty/*" --exclude "*/build/*"
    ./buildCheckDSM.py ../build/release/ --exclude "*_generated.h" --exclude "*/test/*"

    # Combine filter and exclude (include FslBase, but exclude tests)
    ./buildCheckDSM.py ../build/release/ --filter "FslBase/*" --exclude "*/test/*"

    # Cluster by directory structure
    ./buildCheckDSM.py ../build/release/ --cluster-by-directory

    # SAVE/LOAD BASELINE: Save analysis for later comparison
    # Step 1: Analyze and save baseline (compressed ~200-500KB for 1000 headers)
    git checkout main
    ./buildCheckDSM.py ../build/release/ --save-results baseline.dsm.json.gz
    
    # Step 2: Analyze current build and compare with saved baseline
    git checkout feature-branch
    ./buildCheckDSM.py ../build/release/ --load-baseline baseline.dsm.json.gz
    
    # Note: Baseline must be from the same build directory and system
    # Shows: headers added/removed, cycles introduced/resolved,
    #        coupling changes, layer shifts, overall assessment

    # DIFFERENTIAL ANALYSIS: Compare architecture between two builds
    # Step 1: Create baseline build
    git checkout main
    mkdir build_baseline && cd build_baseline
    cmake .. && ninja
    
    # Step 2: Create current build
    git checkout feature-branch
    mkdir build_current && cd build_current
    cmake .. && ninja
    
    # Step 3: Compare
    ./buildCheckDSM.py build_current/ --compare-with build_baseline/
    
    # Shows: headers added/removed, cycles introduced/resolved,
    #        coupling changes, layer shifts, overall assessment

Note: This tool provides the architectural "big picture" view that complements the
      detailed analysis provided by other buildCheck tools.
      
      Differential analysis enables architectural impact assessment by comparing
      two complete builds. User manages builds manually - no git integration needed.

      Graph exports can be visualized with:
      - GraphML (.graphml): Gephi, yEd, Cytoscape
      - JSON (.json): D3.js, custom visualization tools
      - GEXF (.gexf): Gephi
      - DOT (.dot): Graphviz (requires pydot: pip install pydot)
"""
__version__ = "1.1.0"

import os
import sys
import argparse
import logging
from typing import Dict, Set, List, Tuple, DefaultDict, Any, Optional
# Dependencies assumed to be installed

# Check networkx availability early with helpful error message
from lib.package_verification import require_package
require_package('networkx', 'DSM analysis')

import networkx as nx

# Import library modules
from lib.color_utils import Colors, print_error, print_warning, print_success
from lib.constants import (
    DEFAULT_TOP_N,
    CYCLE_HIGHLIGHT,
    DEPENDENCY_MARKER,
    EMPTY_CELL,
    EXIT_SUCCESS,
    EXIT_INVALID_ARGS,
    EXIT_RUNTIME_ERROR,
    EXIT_KEYBOARD_INTERRUPT,
    BuildCheckError,
)
from lib.file_utils import filter_headers_by_pattern, cluster_headers_by_directory, exclude_headers_by_patterns
from lib.library_parser import map_headers_to_libraries
from lib.export_utils import export_dsm_to_csv, export_dependency_graph
from lib.ninja_utils import validate_build_directory_with_feedback
from lib.dsm_analysis import (
    print_summary_statistics,
    print_circular_dependencies,
    print_layered_architecture,
    print_high_coupling_headers,
    print_recommendations,
    display_directory_clusters,
    compare_dsm_results,
    print_dsm_delta,
    run_dsm_analysis,
    display_analysis_results,
    run_differential_analysis,
    run_differential_analysis_with_baseline,
)
from lib.dsm_types import DSMAnalysisResults, DSMDelta
from lib.dsm_serialization import save_dsm_results, load_dsm_results

# Import build_include_graph from library
from lib.clang_utils import build_include_graph

# Explicitly export functions for testing
__all__ = ['filter_headers_by_pattern', 'cluster_headers_by_directory', 'exclude_headers_by_patterns',
           'apply_all_filters', 'apply_exclude_filters', 'DSMAnalysisResults']


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


def setup_library_mapping(
    args: argparse.Namespace,
    all_headers: Set[str]
) -> Dict[str, str]:
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
    args: argparse.Namespace,
    all_headers: Set[str],
    header_to_lib: Dict[str, str],
    project_root: str
) -> Set[str]:
    """Apply all filtering options and return filtered header set.

    Args:
        args: Parsed command-line arguments
        all_headers: Initial set of all headers
        header_to_lib: Mapping of headers to libraries
        project_root: Project root directory for relative paths

    Returns:
        Filtered set of headers

    Raises:
        ValueError: If filtering results in empty set or invalid filter
    """
    filtered_headers: Set[str] = all_headers

    # Apply library filter if specified
    if args.library_filter:
        if not header_to_lib:
            raise ValueError("Library filter requested but library mapping not available")

        filtered_headers = {
            header for header in filtered_headers
            if header_to_lib.get(header) == args.library_filter
        }

        if not filtered_headers:
            available_libs = sorted(set(header_to_lib.values()))[:10]
            raise ValueError(
                f"No headers found for library '{args.library_filter}'. "
                f"Available libraries: {', '.join(available_libs)}..."
            )

        print_success(f"Filtered to {len(filtered_headers)} headers from {args.library_filter}", prefix=False)

    # Show helpful suggestions for large projects
    if len(filtered_headers) > 500 and not args.filter and not args.library_filter:
        print_warning(f"Large project detected ({len(filtered_headers)} headers). "
              f"Consider using --filter to focus analysis.", prefix=False)
        print(f"{Colors.DIM}Examples: --filter '*FslBase/*' or --filter '*Graphics/*'{Colors.RESET}")
        if header_to_lib:
            example_lib = next(iter(set(header_to_lib.values())))
            print(f"{Colors.DIM}Or filter by library: --library-filter '{example_lib}'{Colors.RESET}")

    # Apply pattern filter if specified
    if args.filter:
        logging.info("Applying filter: %s", args.filter)
        filtered_headers = filter_headers_by_pattern(filtered_headers, args.filter, project_root)
        print_success(f"Filtered to {len(filtered_headers)} headers matching '{args.filter}'", prefix=False)

    if not filtered_headers:
        raise ValueError("No headers found after filtering")

    # Apply exclude patterns if specified
    if hasattr(args, 'exclude') and args.exclude:
        filtered_headers, excluded_count, no_match_patterns = apply_exclude_filters(
            filtered_headers, args.exclude, project_root
        )
        
        if excluded_count > 0:
            print_success(f"Excluded {excluded_count} headers matching {len(args.exclude)} pattern(s)", prefix=False)
        
        # Warn about patterns that matched nothing
        for pattern in no_match_patterns:
            print_warning(f"Exclude pattern '{pattern}' matched no headers", prefix=False)
    
    if not filtered_headers:
        raise ValueError("No headers found after filtering and exclusions")

    return filtered_headers


def apply_exclude_filters(
    headers: Set[str],
    exclude_patterns: List[str],
    project_root: str
) -> tuple[Set[str], int, List[str]]:
    """Apply exclude patterns to filter out unwanted headers.
    
    Args:
        headers: Set of header paths
        exclude_patterns: List of glob patterns to exclude
        project_root: Project root directory for relative paths
        
    Returns:
        Tuple of (filtered_headers, excluded_count, patterns_with_no_matches)
    """
    if not exclude_patterns:
        return headers, 0, []
    
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
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description='Dependency Structure Matrix (DSM) analysis for C++ headers.',
        epilog='''
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
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}',
        help='Show version and exit'
    )

    parser.add_argument(
        'build_directory',
        metavar='BUILD_DIR',
        help='Path to the ninja build directory (e.g., build/release)'
    )

    parser.add_argument(
        '--top',
        type=int,
        default=DEFAULT_TOP_N,
        help=f'Number of headers to show in matrix (default: {DEFAULT_TOP_N}, use 0 to disable matrix display)'
    )

    parser.add_argument(
        '--cycles-only',
        action='store_true',
        help='Show only circular dependency analysis'
    )

    parser.add_argument(
        '--show-layers',
        action='store_true',
        help='Show hierarchical layer structure (automatically shown if architecture is clean)'
    )

    parser.add_argument(
        '--export',
        type=str,
        metavar='FILE.csv',
        help='Export full matrix to CSV file'
    )

    parser.add_argument(
        '--export-graph',
        type=str,
        metavar='FILE',
        help='Export dependency graph with library/module grouping (formats: .graphml, .dot, .gexf, .json). '
             'Includes library attributes for visualization tools (Gephi, yEd, Cytoscape). '
             'Use with --show-library-boundaries for enhanced library metadata.'
    )

    parser.add_argument(
        '--filter',
        type=str,
        metavar='PATTERN',
        help='Filter headers by glob pattern (e.g., "FslBase/*")'
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

    parser.add_argument(
        '--cluster-by-directory',
        action='store_true',
        help='Group headers by directory in output'
    )

    parser.add_argument(
        '--show-library-boundaries',
        action='store_true',
        help='Show which library each header belongs to and analyze cross-library dependencies'
    )

    parser.add_argument(
        '--library-filter',
        type=str,
        metavar='LIBRARY',
        help='Show only headers from specified library (e.g., "libFslBase.a")'
    )

    parser.add_argument(
        '--cross-library-only',
        action='store_true',
        help='Show only dependencies that cross library boundaries (identifies boundary violations)'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose debug logging'
    )

    parser.add_argument(
        '--compare-with',
        type=str,
        metavar='BASELINE_BUILD_DIR',
        help='Compare DSM against baseline build directory (enables differential analysis)'
    )

    parser.add_argument(
        '--save-results',
        type=str,
        metavar='FILE.dsm.json.gz',
        help='Save DSM analysis results to compressed file for later comparison (gzip compressed JSON)'
    )

    parser.add_argument(
        '--load-baseline',
        type=str,
        metavar='FILE.dsm.json.gz',
        help='Load baseline DSM results from file and compare with current build '
             '(baseline must be from same build directory and system)'
    )

    args: argparse.Namespace = parser.parse_args()

    # Set logging level based on verbose flag
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Verbose logging enabled")

    try:
        # Phase 1: Validate and prepare
        build_dir, project_root = validate_and_prepare_args(args)

        # Validate mutually exclusive options
        if args.compare_with and args.load_baseline:
            raise ValueError("Cannot use both --compare-with and --load-baseline simultaneously")

        # Check if differential analysis is requested
        if args.compare_with:
            return run_differential_analysis(build_dir, args.compare_with, project_root)

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
            elapsed = scan_result.scan_time
        except Exception as e:
            logging.error("Failed to build include graph: %s", e)
            raise RuntimeError(f"Failed to build include graph: {e}") from e

        print_success(f"Built directed include graph with {len(all_headers)} headers in {elapsed:.1f}s", prefix=False)

        # Keep unfiltered data for saving baselines
        unfiltered_headers: Set[str] = all_headers.copy()
        unfiltered_include_graph: DefaultDict[str, Set[str]] = header_to_headers

        # Phase 3: Setup library mapping (if requested)
        header_to_lib: Dict[str, str] = setup_library_mapping(args, all_headers)

        # Phase 4: Apply all filters
        all_headers = apply_all_filters(args, all_headers, header_to_lib, project_root)

        # Phase 5: Run DSM analysis
        compute_layers_flag = args.show_layers or not args.cycles_only
        results: DSMAnalysisResults = run_dsm_analysis(
            all_headers, 
            header_to_headers, 
            compute_layers=compute_layers_flag,
            show_progress=True
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
            cluster_by_directory=args.cluster_by_directory
        )

        # Phase 7: Export data (if requested)
        if args.export:
            export_dsm_to_csv(
                args.export,
                results.sorted_headers,
                results.header_to_headers,
                results.metrics,
                project_root
            )

        if args.export_graph:
            export_dependency_graph(
                args.export_graph,
                results.directed_graph,
                results.metrics,
                results.cycles,
                project_root,
                header_to_lib,
                results.header_to_headers
            )

        # Save results (if requested)
        if args.save_results:
            save_dsm_results(
                results,
                unfiltered_headers,
                unfiltered_include_graph,
                args.save_results,
                build_dir,
                args.filter,
                args.exclude
            )

        # Load and compare with baseline (if requested)
        if args.load_baseline:
            baseline_results = load_dsm_results(
                args.load_baseline, 
                build_dir,
                args.filter,
                args.exclude,
                project_root
            )
            return run_differential_analysis_with_baseline(results, baseline_results, project_root)

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
        logging.error(f"Missing dependency: {e}")
        sys.exit(EXIT_RUNTIME_ERROR)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        sys.exit(EXIT_RUNTIME_ERROR)
