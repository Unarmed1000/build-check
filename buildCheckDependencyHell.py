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
"""Find headers that lead to dependency hell (excessive transitive dependencies).

PURPOSE:
    Comprehensive, multi-dimensional analysis of header dependency problems using
    graph theory and transitive dependency tracking. Identifies headers that cause
    excessive compilation costs through deep dependency chains.

WHAT IT DOES:
    - Builds complete transitive dependency graph using clang-scan-deps + NetworkX
    - Calculates multiple impact metrics for each header:
      * Transitive dependency count (how many headers this pulls in)
      * Build impact (deps × usage = total compilation cost)
      * Rebuild cost (if changed, how many sources rebuild)
      * Reverse impact (how many headers depend on this one)
      * Hub headers (architectural bottlenecks)
      * Maximum chain length (deepest include path)
    - Classifies headers by severity (CRITICAL/HIGH/MODERATE)
    - Identifies base type headers (no project includes)
    - Provides multiple ranked lists for different refactoring priorities

USE CASES:
    - "Which headers should I refactor first to improve build times?"
    - Find architectural bottlenecks (hub headers with many dependents)
    - Identify headers causing the most compilation work (build impact)
    - Find headers that would cause expensive rebuilds if changed
    - Prioritize technical debt reduction
    - Track dependency complexity over time
    - Validate architectural decisions

METHOD:
    1. Uses clang-scan-deps (parallel) to parse all #include directives
    2. Builds directed graph with NetworkX
    3. Computes transitive closures (descendants/ancestors)
    4. Calculates multiple impact metrics
    5. Ranks headers by different criteria

OUTPUT:
    Multiple ranked lists:
    1. Worst Offenders: By transitive dependency count
    2. Build Impact: By (deps × usage) - total compilation cost
    3. Rebuild Cost: By (usage × dependents) - rebuild expense if changed
    4. Hub Headers: By reverse dependency count - architectural bottlenecks

    Severity classification:
    - CRITICAL: Combined score > 500 (urgent refactoring needed)
    - HIGH: Combined score 300-500 (should refactor soon)
    - MODERATE: Combined score < 300 (monitor)

METRICS EXPLAINED:
    - Transitive Deps: Total headers pulled in (direct + indirect)
    - Build Impact: deps × usage = total header compilations across project
    - Rebuild Cost: usage × (1 + dependents) = sources rebuilt if header changes
    - Reverse Impact: Number of other headers that depend on this one
    - Hub Header: Header with high reverse impact (architectural bottleneck)
    - Max Chain: Longest include path through this header
    - Fanout: Number of headers frequently pulled in together
    - Base Type: Header with no outgoing project includes

PERFORMANCE:
    Moderate (5-10 seconds for large projects). Uses all CPU cores.
    Most expensive but most comprehensive analysis.

REQUIREMENTS:
    - Python 3.7+
    - clang-scan-deps (clang-19, clang-18, or clang-XX)
    - networkx: pip install networkx
    - compile_commands.json (auto-generated)

COMPLEMENTARY TOOLS:
    This is the most comprehensive tool. Use the others for quick checks:
    - buildCheckImpact.py: Quick impact check (1 second)
    - buildCheckIncludeChains.py: Simple cooccurrence patterns
    - buildCheckIncludeGraph.py: Gateway headers and .cpp rebuild lists

REFACTORING GUIDE:
    1. Start with CRITICAL severity headers
    2. Look at "Rebuild Cost" list first - these cause most pain when changed
    3. Use "Hub Headers" to find architectural bottlenecks
    4. Use "Build Impact" to find headers slowing compilation
    5. Use --detailed to see per-header analysis with recommendations

EXAMPLES:
    # Analyze all headers with default threshold (50 deps)
    ./buildCheckDependencyHell.py ../build/release/

    # Only analyze changed headers (faster, focused)
    ./buildCheckDependencyHell.py ../build/release/ --changed

    # Show detailed per-header analysis
    ./buildCheckDependencyHell.py ../build/release/ --detailed

    # More strict threshold (30 deps) and show top 20
    ./buildCheckDependencyHell.py ../build/release/ --threshold 30 --top 20

    # Exclude third-party and test headers
    ./buildCheckDependencyHell.py ../build/release/ --exclude "*/ThirdParty/*" --exclude "*/test/*"

    # Analyze only changed headers with details
    ./buildCheckDependencyHell.py ../build/release/ --changed --detailed
"""
import subprocess
import re
import os
import sys
import argparse
import time
import logging
from typing import Dict, Set, List, Tuple
from pathlib import Path

from lib.constants import EXIT_RUNTIME_ERROR, EXIT_KEYBOARD_INTERRUPT, BuildCheckError

# Import library modules
from lib.ninja_utils import extract_rebuild_info, parse_ninja_explain_line
from lib.color_utils import Colors, print_warning, print_success
from lib.file_utils import exclude_headers_by_patterns, filter_by_file_type, FileClassificationStats
from lib.clang_utils import is_system_header as is_system_header_lib, build_include_graph, FileType, VALID_SOURCE_EXTENSIONS, VALID_HEADER_EXTENSIONS
from lib.graph_utils import build_dependency_graph, compute_reverse_dependencies, compute_transitive_metrics, compute_chain_lengths
from lib.dependency_utils import find_dependency_fanout, DependencyAnalysisResult, SourceDependencyMap, compute_header_usage, identify_problematic_headers

__all__ = ["build_include_graph", "analyze_dependency_hell"]

# Constants
RE_OUTPUT = re.compile(r"ninja explain: (.*)")
# VALID_HEADER_EXTENSIONS, VALID_SOURCE_EXTENSIONS, SYSTEM_PREFIXES moved to lib.clang_utils
# CLANG_SCAN_DEPS_COMMANDS moved to lib.clang_utils
DEFAULT_THRESHOLD = 50
DEFAULT_TOP_N = 10
SEVERITY_CRITICAL = 500
SEVERITY_HIGH = 300
FANOUT_THRESHOLD = 5
MAX_AMBIGUOUS_DISPLAY = 10

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# create_filtered_compile_commands and build_include_graph are now imported from lib.clang_utils
# build_dependency_graph is now imported from lib.graph_utils


def analyze_dependency_hell(
    build_dir: str, rebuild_targets: List[str], threshold: int = DEFAULT_THRESHOLD
) -> Tuple["DependencyAnalysisResult", Dict[str, FileType]]:
    """Find headers with excessive dependencies using include graph.

    Args:
        build_dir: Path to the build directory
        rebuild_targets: List of rebuild target files
        threshold: Minimum transitive dependency count to flag as problematic

    Returns:
        DependencyAnalysisResult containing analysis results

    Raises:
        ValueError: If inputs are invalid
        RuntimeError: If analysis fails
    """
    build_dir = os.path.realpath(os.path.abspath(build_dir))
    if not os.path.isdir(build_dir):
        raise ValueError(f"Invalid build directory: {build_dir}")

    if not rebuild_targets:
        logger.warning("No rebuild targets provided")

    if threshold <= 0:
        raise ValueError(f"Threshold must be positive, got {threshold}")

    start_time = time.time()

    # Build complete include graph
    try:
        scan_result = build_include_graph(build_dir)
        source_to_deps = scan_result.source_to_deps
        include_graph = scan_result.include_graph
        all_headers = scan_result.all_headers
        file_types = scan_result.file_types
    except Exception as e:
        raise RuntimeError(f"Failed to build include graph: {e}") from e

    logger.info("Building dependency graph with NetworkX...")
    try:
        G = build_dependency_graph(include_graph, all_headers)
    except Exception as e:
        raise RuntimeError(f"Failed to build dependency graph: {e}") from e

    if G is None:
        raise RuntimeError("Failed to build dependency graph: NetworkX not available")

    logger.info("Graph built: %s nodes, %s edges", G.number_of_nodes(), G.number_of_edges())

    print(f"{Colors.BLUE}Computing transitive dependencies for all headers...{Colors.RESET}")

    # Count header usage across all source files
    # Convert List[str] to Set[str] for compute_header_usage
    source_to_deps_sets = {src: set(deps) for src, deps in source_to_deps.items()}
    header_usage_count = compute_header_usage(source_to_deps_sets, file_types)

    # Compute reverse dependencies using transitive closure
    reverse_deps, tc = compute_reverse_dependencies(G)

    # Only process project headers (using file classification)
    project_headers = [h for h in all_headers if file_types.get(h, FileType.PROJECT) == FileType.PROJECT]

    print(f"{Colors.BLUE}Computing rebuild impact metrics...{Colors.RESET}")

    # Compute transitive dependencies and identify base types
    base_types, header_transitive_deps, header_reverse_impact = compute_transitive_metrics(G, tc, project_headers, reverse_deps)

    # Compute maximum chain lengths
    header_max_chain_length = compute_chain_lengths(G, project_headers, base_types)

    elapsed = time.time() - start_time
    print(f"{Colors.BLUE}Finished dependency analysis in {elapsed:.2f}s{Colors.RESET}")
    print(f"{Colors.BLUE}Total unique project headers: {len(project_headers)}{Colors.RESET}")
    print(f"{Colors.BLUE}Identified {len(base_types)} base type headers (no direct project includes){Colors.RESET}")

    if base_types and len(base_types) < 50:
        print(f"{Colors.CYAN}Base type headers:{Colors.RESET}")
        for bt in sorted(base_types):
            print_success(f"  {bt}", prefix=False)

    # Identify problematic headers
    problematic = identify_problematic_headers(header_transitive_deps, header_usage_count, header_reverse_impact, header_max_chain_length, threshold)

    print(f"{Colors.BLUE}Dependency analysis complete.{Colors.RESET}")

    return (
        DependencyAnalysisResult(
            problematic=sorted(problematic, key=lambda x: x[1], reverse=True),
            source_to_deps=source_to_deps,
            base_types=base_types,
            header_usage_count=header_usage_count,
            header_reverse_impact=header_reverse_impact,
            header_max_chain_length=header_max_chain_length,
        ),
        file_types,
    )


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Comprehensive dependency analysis: find headers causing dependency hell.",
        epilog="""
This is the most comprehensive build analysis tool. It provides multiple ranked
lists to help prioritize refactoring:

  1. Worst Offenders: Most transitive dependencies
  2. Build Impact: Highest total compilation cost (deps × usage)
  3. Rebuild Cost: Most expensive if changed (usage × dependents)
  4. Hub Headers: Architectural bottlenecks (most dependents)

Severity levels:
  CRITICAL (>500): Urgent refactoring needed
  HIGH (300-500): Should refactor soon
  MODERATE (<300): Monitor and consider refactoring

Workflow:
  1. Run without flags to see all problematic headers
  2. Use --changed to focus on recently modified headers
  3. Use --detailed to see per-header recommendations
  4. Start refactoring from "Rebuild Cost" list (causes most pain)

Requires: clang-scan-deps, networkx (pip install networkx)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("build_directory", metavar="BUILD_DIR", help="Path to the ninja build directory (e.g., build/release)")

    parser.add_argument(
        "--threshold",
        type=int,
        default=50,
        help="Minimum transitive dependency count to flag as problematic (default: 50). " "Lower = more strict (e.g., 30), higher = less strict (e.g., 100)",
    )

    parser.add_argument("--top", type=int, default=10, help="Number of items to show in each ranked list (default: 10). " "Use 20-30 for comprehensive view")

    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed per-header analysis with metrics, severity, and " "frequently cooccurring headers. Use this for deep-dive analysis",
    )

    parser.add_argument(
        "--changed", action="store_true", help="Only analyze changed headers (from rebuild root causes). " "Faster and more focused on recent modifications"
    )

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

    parser.add_argument("--include-system-headers", action="store_true", help="Include system headers in analysis (default: exclude /usr/*, /lib/*, /opt/*)")

    return parser.parse_args()


def get_changed_headers(build_dir: str) -> Set[str]:
    """Get changed header files from rebuild root causes.

    Args:
        build_dir: Path to the build directory

    Returns:
        Set of changed header file paths

    Raises:
        RuntimeError: If extraction fails
    """
    print(f"{Colors.BLUE}Extracting changed headers from rebuild root causes...{Colors.RESET}")
    try:
        _, _, root_causes = extract_rebuild_info(build_dir)
        changed_headers = set(root_causes.keys())
    except Exception as e:
        raise RuntimeError(f"Failed to extract rebuild info: {e}") from e

    if not changed_headers:
        print_warning("\nNo changed header files found in rebuild root causes", prefix=False)
        return set()

    print(f"\n{Colors.CYAN}Found {len(changed_headers)} changed headers to analyze:{Colors.RESET}")
    for header in sorted(changed_headers):
        display_header = header
        print(f"  {Colors.MAGENTA}{display_header}{Colors.RESET}")

    return changed_headers


def collect_rebuild_targets(build_dir: str) -> List[str]:
    """Collect rebuild targets from ninja.

    Args:
        build_dir: Path to the build directory

    Returns:
        List of rebuild target file paths

    Raises:
        RuntimeError: If ninja command fails
    """
    print(f"{Colors.BLUE}Running ninja dry-run to collect rebuild targets...{Colors.RESET}")
    # Run ninja -n -d explain to get what would rebuild
    try:
        result = subprocess.run(["ninja", "-n", "-d", "explain"], capture_output=True, text=True, check=True, cwd=build_dir, timeout=60)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Ninja command failed: {e.stderr}") from e
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Ninja command timed out after 60 seconds") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("Ninja not found. Please ensure ninja is installed and in PATH.") from exc

    lines = result.stderr.splitlines()

    rebuild_targets = []

    for line in lines:
        parsed = parse_ninja_explain_line(line, RE_OUTPUT)
        if not parsed:
            continue

        output_file, _explain_msg = parsed

        # Only include actual object files
        if any(f"{ext}.o" in output_file for ext in VALID_SOURCE_EXTENSIONS):
            rebuild_targets.append(output_file)

    # If no rebuilds detected, get all object files instead
    if not rebuild_targets:
        print_warning("No rebuilds detected, analyzing all object files...", prefix=False)
        try:
            result = subprocess.run(["ninja", "-t", "targets", "all"], capture_output=True, text=True, check=True, cwd=build_dir, timeout=30)
            for line in result.stdout.splitlines():
                target = line.split(":")[0].strip()
                if any(f"{ext}.o" in target for ext in VALID_SOURCE_EXTENSIONS):
                    rebuild_targets.append(target)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.warning("Failed to get ninja targets: %s", e)

    if not rebuild_targets:
        raise RuntimeError("No compilation targets found.")

    return rebuild_targets


def display_detailed_analysis(problematic: List[Tuple[str, int, int, int, int]], cooccurrence: Dict[str, Dict[str, int]], project_root: str) -> None:
    """Display detailed per-header analysis.

    Args:
        problematic: List of problematic headers with metrics
        cooccurrence: Cooccurrence matrix
        project_root: Path to the project root
    """
    print(f"\n{Colors.BRIGHT}Detailed Analysis (showing all {len(problematic)} headers):{Colors.RESET}")

    for header, dep_count, usage_count, reverse_impact, chain_length in problematic:
        display_path = header
        if header.startswith(project_root):
            display_path = os.path.relpath(header, project_root)

        # Calculate fanout (how many other headers it pulls in frequently)
        fanout = len([h for h, count in cooccurrence[header].items() if count > FANOUT_THRESHOLD]) if header in cooccurrence else 0

        # Rebuild cost: if this header changes, how expensive is the rebuild?
        rebuild_cost = usage_count * (1 + reverse_impact)

        # Combined score for severity
        combined_score = dep_count + (fanout * 10)

        if combined_score > SEVERITY_CRITICAL:
            severity = f"{Colors.RED}CRITICAL{Colors.RESET}"
        elif combined_score > SEVERITY_HIGH:
            severity = f"{Colors.YELLOW}HIGH{Colors.RESET}"
        else:
            severity = f"{Colors.CYAN}MODERATE{Colors.RESET}"

        print(f"\n  {Colors.MAGENTA}{display_path}{Colors.RESET}")
        print(f"    Transitive deps: {Colors.BRIGHT}{dep_count}{Colors.RESET}, Fanout: {fanout}, Usage: {usage_count} sources")
        print(f"    Reverse impact: {reverse_impact} headers depend on this, Max chain: {chain_length}, Rebuild cost: {rebuild_cost:,}")
        print(f"    Severity: {severity}")

        # Show top cooccurring headers
        if header in cooccurrence:
            top_cooccur = sorted(cooccurrence[header].items(), key=lambda x: x[1], reverse=True)[:5]
            if top_cooccur:
                print("    Frequently pulls in:")
                for coheader, count in top_cooccur:
                    display_co = coheader
                    if coheader.startswith(project_root):
                        display_co = os.path.relpath(coheader, project_root)
                    print(f"      {Colors.DIM}{display_co}{Colors.RESET} ({count} times)")


def calculate_summary_statistics(problematic: List[Tuple[str, int, int, int, int]], cooccurrence: Dict[str, Dict[str, int]]) -> Tuple[int, int, int]:
    """Calculate severity breakdown statistics.

    Args:
        problematic: List of problematic headers with metrics
        cooccurrence: Cooccurrence matrix

    Returns:
        Tuple of (critical_count, high_count, moderate_count)
    """
    total_problematic = len(problematic)
    critical_count = len(
        [h for h, dc, _, _, _ in problematic if dc + (len([x for x, c in cooccurrence[h].items() if c > FANOUT_THRESHOLD]) * 10) > SEVERITY_CRITICAL]
    )
    high_count = len(
        [
            h
            for h, dc, _, _, _ in problematic
            if SEVERITY_HIGH < (dc + (len([x for x, c in cooccurrence[h].items() if c > FANOUT_THRESHOLD]) * 10)) <= SEVERITY_CRITICAL
        ]
    )
    moderate_count = total_problematic - critical_count - high_count
    return critical_count, high_count, moderate_count


def display_summary_output(
    problematic: List[Tuple[str, int, int, int, int]],
    cooccurrence: Dict[str, Dict[str, int]],
    rebuild_targets_count: int,
    threshold: int,
    top_n: int,
    project_root: str,
    show_detailed_hint: bool,
) -> None:
    """Display summary output with ranked lists.

    Args:
        problematic: List of problematic headers with metrics
        cooccurrence: Cooccurrence matrix
        rebuild_targets_count: Number of rebuild targets analyzed
        threshold: Threshold used for analysis
        top_n: Number of items to show in each list
        project_root: Path to the project root
        show_detailed_hint: Whether to show hint about --detailed flag
    """
    critical_count, high_count, moderate_count = calculate_summary_statistics(problematic, cooccurrence)
    total_problematic = len(problematic)

    # Print summary last
    print(f"\n{Colors.BRIGHT}═══ Dependency Hell Summary ═══{Colors.RESET}")
    print(f"  Analyzed: {rebuild_targets_count} rebuild targets")
    print("  Method: clang-scan-deps (parallel, optimized)")
    print(f"  Found: {total_problematic} headers with >{threshold} transitive dependencies")
    print(
        f"  Severity breakdown: {Colors.RED}{critical_count} CRITICAL{Colors.RESET}, "
        f"{Colors.YELLOW}{high_count} HIGH{Colors.RESET}, "
        f"{Colors.CYAN}{moderate_count} MODERATE{Colors.RESET}"
    )
    print(f"\n{Colors.BRIGHT}Metric Explanations:{Colors.RESET}")
    print(f"  {Colors.BRIGHT}Build Impact{Colors.RESET} = deps × direct usage - measures compilation cost of header's dependencies")
    print(f"  {Colors.BRIGHT}Rebuild Cost{Colors.RESET} = usage × (1 + dependents) - measures rebuild impact if header changes")
    print(f"  {Colors.BRIGHT}Hub Headers{Colors.RESET} = reverse dependency count - shows architectural bottlenecks")

    # Show top N worst offenders
    if problematic:
        print(f"\n  {Colors.BRIGHT}Top {top_n} Worst Offenders (by dependency count):{Colors.RESET}")
        for i, (header, dep_count, usage_count, reverse_impact, chain_length) in enumerate(problematic[:top_n], 1):
            display_path = header
            if header.startswith(project_root):
                display_path = os.path.relpath(header, project_root)

            # Get severity color
            fanout = len([h for h, count in cooccurrence.get(header, {}).items() if count > FANOUT_THRESHOLD])
            combined_score = dep_count + (fanout * 10)

            if combined_score > SEVERITY_CRITICAL:
                severity_color = Colors.RED
            elif combined_score > SEVERITY_HIGH:
                severity_color = Colors.YELLOW
            else:
                severity_color = Colors.CYAN

            print(f"    {Colors.DIM}{i:2}.{Colors.RESET} {severity_color}{display_path}{Colors.RESET} ({dep_count} deps, {usage_count} uses)")

        # Show top N by impact (deps * usage)
        print(f"\n  {Colors.BRIGHT}Top {top_n} by Build Impact (deps × usage count):{Colors.RESET}")
        by_impact = sorted(problematic, key=lambda x: x[1] * x[2], reverse=True)
        for i, (header, dep_count, usage_count, reverse_impact, chain_length) in enumerate(by_impact[:top_n], 1):
            display_path = header
            if header.startswith(project_root):
                display_path = os.path.relpath(header, project_root)

            impact = dep_count * usage_count

            # Color by impact
            if impact > 100000:
                impact_color = Colors.RED
            elif impact > 50000:
                impact_color = Colors.YELLOW
            else:
                impact_color = Colors.CYAN

            print(f"    {Colors.DIM}{i:2}.{Colors.RESET} {impact_color}{display_path}{Colors.RESET} ({dep_count} deps × {usage_count} uses = {impact:,} total)")

        # Show top N by rebuild cost (what causes most expensive rebuilds if changed)
        print(f"\n  {Colors.BRIGHT}Top {top_n} by Rebuild Cost (if changed, what causes worst rebuild):{Colors.RESET}")
        by_rebuild_cost = sorted(problematic, key=lambda x: x[2] * (1 + x[3]), reverse=True)
        for i, (header, dep_count, usage_count, reverse_impact, chain_length) in enumerate(by_rebuild_cost[:top_n], 1):
            display_path = header
            if header.startswith(project_root):
                display_path = os.path.relpath(header, project_root)

            rebuild_cost = usage_count * (1 + reverse_impact)

            # Color by rebuild cost
            if rebuild_cost > 50000:
                cost_color = Colors.RED
            elif rebuild_cost > 20000:
                cost_color = Colors.YELLOW
            else:
                cost_color = Colors.CYAN

            print(
                f"    {Colors.DIM}{i:2}.{Colors.RESET} {cost_color}{display_path}{Colors.RESET} "
                f"({usage_count} uses × {reverse_impact} dependents = {rebuild_cost:,} source rebuilds)"
            )

        # Show top N hub headers (most headers depend on these)
        print(f"\n  {Colors.BRIGHT}Top {top_n} Hub Headers (most other headers depend on these):{Colors.RESET}")
        by_hub = sorted(problematic, key=lambda x: x[3], reverse=True)
        for i, (header, dep_count, usage_count, reverse_impact, chain_length) in enumerate(by_hub[:top_n], 1):
            display_path = header
            if header.startswith(project_root):
                display_path = os.path.relpath(header, project_root)

            # Color by reverse impact
            if reverse_impact > 500:
                hub_color = Colors.RED
            elif reverse_impact > 200:
                hub_color = Colors.YELLOW
            else:
                hub_color = Colors.CYAN

            print(
                f"    {Colors.DIM}{i:2}.{Colors.RESET} {hub_color}{display_path}{Colors.RESET} "
                f"({reverse_impact} headers depend on this, max chain: {chain_length})"
            )

    if show_detailed_hint:
        print(f"\n  {Colors.DIM}Use --detailed to see per-header analysis{Colors.RESET}")


def main() -> int:
    """Main entry point for the dependency hell analyzer.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    args = parse_arguments()
    build_dir = args.build_directory

    # Validate arguments
    if args.threshold <= 0:
        logger.error("Invalid threshold: %s. Must be positive.", args.threshold)
        return 1

    if args.top <= 0:
        logger.error("Invalid top value: %s. Must be positive.", args.top)
        return 1

    print(f"{Colors.CYAN}Starting dependency hell analysis...{Colors.RESET}")
    if not os.path.isdir(build_dir):
        logger.error("Build directory not found: %s", build_dir)
        return 1

    build_dir = os.path.abspath(build_dir)

    try:
        project_root = str(Path(build_dir).parent.parent.parent)
    except Exception as e:
        logger.error("Failed to determine project root: %s", e)
        return 1

    # Get changed files if --changed is specified
    changed_headers: Set[str] = set()
    if args.changed:
        try:
            changed_headers = get_changed_headers(build_dir)
            if not changed_headers:
                return 0
        except RuntimeError as e:
            logger.error(str(e))
            return 1

    try:
        rebuild_targets = collect_rebuild_targets(build_dir)
    except RuntimeError as e:
        logger.error(str(e))
        return 1

    mode_desc = "changed headers only" if args.changed else "all headers"
    print(f"\n{Colors.CYAN}Analyzing dependency hell ({len(rebuild_targets)} targets, {mode_desc})...{Colors.RESET}")

    try:
        analysis_result, file_types = analyze_dependency_hell(build_dir, rebuild_targets, args.threshold)
    except Exception as e:
        logger.error("Analysis failed: %s", e)
        logger.debug("Exception details:", exc_info=True)
        return 1

    problematic = analysis_result.problematic
    source_to_deps = analysis_result.source_to_deps

    # Apply exclude patterns if specified
    if hasattr(args, "exclude") and args.exclude:
        original_count = len(problematic)
        problematic_headers_set = set(h for h, _, _, _, _ in problematic)

        filtered_headers, excluded_count, no_match_patterns, _ = exclude_headers_by_patterns(problematic_headers_set, args.exclude, project_root)

        if excluded_count > 0:
            # Filter the problematic list to only include non-excluded headers
            problematic = [(h, c, u, r, ch) for h, c, u, r, ch in problematic if h in filtered_headers]
            print_success(f"Excluded {excluded_count} headers matching {len(args.exclude)} pattern(s)", prefix=False)

        # Warn about patterns that matched nothing
    # Filter system headers unless explicitly included
    if not getattr(args, "include_system_headers", False):
        original_count = len(problematic)
        problematic_headers_set = set(h for h, _, _, _, _ in problematic)
        filtered_headers, stats = filter_by_file_type(problematic_headers_set, file_types, exclude_types={FileType.SYSTEM}, show_progress=False)

        if stats.system > 0:
            problematic = [(h, c, u, r, ch) for h, c, u, r, ch in problematic if h in filtered_headers]
            print_success(f"Excluded {stats.system} system headers", prefix=False)

    # Filter to only changed headers if requested
    if args.changed and changed_headers:
        original_count = len(problematic)
        problematic = [(h, c, u, r, ch) for h, c, u, r, ch in problematic if h in changed_headers]
        if len(problematic) < original_count:
            filtered_out = original_count - len(problematic)
            print(f"{Colors.BLUE}Filtered to {len(problematic)} changed headers (excluded {filtered_out} unchanged headers){Colors.RESET}")

    if not problematic:
        if args.changed:
            print_warning(f"\nNo changed headers exceed threshold (threshold={args.threshold})", prefix=False)
            print(f"{Colors.CYAN}The changed headers are base types or have fewer than {args.threshold} transitive dependencies{Colors.RESET}")
        else:
            print_success(f"\nNo headers with excessive dependencies found (threshold={args.threshold})", prefix=False)
        return 0

    # Always compute cooccurrence for all problematic headers to get accurate severity breakdown
    all_problematic_headers = [h for h, _, _, _, _ in problematic]
    source_dep_map = SourceDependencyMap(source_to_deps)
    cooccurrence = find_dependency_fanout(
        all_problematic_headers, source_dep_map, is_header_filter=lambda d: d.endswith(VALID_HEADER_EXTENSIONS), is_system_filter=is_system_header_lib
    )

    # Show detailed analysis if requested
    if args.detailed:
        display_detailed_analysis(problematic, cooccurrence, project_root)

    # Display summary output
    display_summary_output(
        problematic, cooccurrence, len(rebuild_targets), args.threshold, args.top, project_root, show_detailed_hint=not args.detailed and len(problematic) > 0
    )

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(EXIT_KEYBOARD_INTERRUPT)
    except BuildCheckError as e:
        logger.error(str(e))
        sys.exit(e.exit_code)
    except ImportError as e:
        logger.error("Missing dependency: %s", e)
        sys.exit(EXIT_RUNTIME_ERROR)
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        logger.debug("Exception details:", exc_info=True)
        sys.exit(EXIT_RUNTIME_ERROR)
