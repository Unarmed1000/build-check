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
    
    # Analyze only changed headers with details
    ./buildCheckDependencyHell.py ../build/release/ --changed --detailed
"""
import subprocess
import re
import os
import sys
import argparse
import time
import json
import logging
import multiprocessing as mp
from collections import defaultdict
from typing import Dict, Set, List, Tuple, Optional, DefaultDict, Any
from pathlib import Path

from lib.constants import (
    EXIT_SUCCESS,
    EXIT_RUNTIME_ERROR,
    EXIT_KEYBOARD_INTERRUPT,
    BuildCheckError,
)

# Check networkx availability early with helpful error message
from lib.package_verification import require_package
require_package('networkx', 'dependency analysis')

import networkx as nx

# Import library modules
from lib.ninja_utils import extract_rebuild_info
from lib.color_utils import Colors, print_error, print_warning, print_success
from lib.clang_utils import (
    IncludeGraphScanResult,
    find_clang_scan_deps, create_filtered_compile_commands,
    is_valid_source_file, is_valid_header_file, is_system_header as is_system_header_lib,
    extract_include_paths, compute_transitive_deps, build_include_graph,
    VALID_SOURCE_EXTENSIONS, VALID_HEADER_EXTENSIONS
)
from lib.graph_utils import build_dependency_graph, verify_requirements as verify_graph
from lib.dependency_utils import find_dependency_fanout, DependencyAnalysisResult, SourceDependencyMap

__all__ = ['build_include_graph', 'analyze_dependency_hell']

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
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


# create_filtered_compile_commands and build_include_graph are now imported from lib.clang_utils
# build_dependency_graph is now imported from lib.graph_utils


def analyze_dependency_hell(build_dir: str, rebuild_targets: List[str], threshold: int = DEFAULT_THRESHOLD) -> 'DependencyAnalysisResult':
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
        scan_time = scan_result.scan_time
    except Exception as e:
        raise RuntimeError(f"Failed to build include graph: {e}") from e
    
    logger.info("Building dependency graph with NetworkX...")
    try:
        G = build_dependency_graph(include_graph, all_headers)
    except Exception as e:
        raise RuntimeError(f"Failed to build dependency graph: {e}") from e
    
    if G is None:
        raise RuntimeError("Failed to build dependency graph: NetworkX not available")
    
    logger.info(f"Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    
    print(f"{Colors.BLUE}Computing transitive dependencies for all headers...{Colors.RESET}")
    
    # Count how many source files include each header (directly or transitively)
    header_usage_count: Dict[str, int] = defaultdict(int)
    print(f"{Colors.DIM}  Analyzing {len(source_to_deps)} source files...{Colors.RESET}")
    for idx, (source, deps) in enumerate(source_to_deps.items(), 1):
        if idx % 100 == 0:
            print(f"\r{Colors.DIM}  Progress: {idx}/{len(source_to_deps)} sources analyzed{Colors.RESET}", end='', flush=True)
        for dep in deps:
            if dep.endswith(('.h', '.hpp', '.hxx')) and not dep.startswith('/usr/') and not dep.startswith('/lib/'):
                header_usage_count[dep] += 1
    if len(source_to_deps) >= 100:
        print()  # New line after progress
    
    # Compute reverse dependencies (how many headers depend on each header)
    print(f"{Colors.BLUE}Computing reverse dependencies (rebuild blast radius)...{Colors.RESET}")
    reverse_deps = defaultdict(set)  # headers that depend on this header (transitively)
    if G is not None:
        nodes = list(G.nodes())
        print(f"{Colors.DIM}  Analyzing {len(nodes)} headers...{Colors.RESET}")
        for idx, node in enumerate(nodes, 1):
            if idx % 50 == 0:
                print(f"\r{Colors.DIM}  Progress: {idx}/{len(nodes)} headers analyzed{Colors.RESET}", end='', flush=True)
            # Get all ancestors (headers that include this one transitively)
            ancestors = nx.ancestors(G, node)
            reverse_deps[node] = ancestors
        if len(nodes) >= 50:
            print()  # New line after progress
    
    # Identify base types: headers with zero out-degree (don't include any project headers)
    base_types = set()
    header_transitive_deps: Dict[str, int] = {}
    header_reverse_impact: Dict[str, int] = {}
    header_max_chain_length: Dict[str, int] = {}
    
    # Only process project headers
    project_headers = [h for h in all_headers 
                      if not h.startswith('/usr/') and not h.startswith('/lib/')]
    
    print(f"{Colors.BLUE}Computing rebuild impact metrics...{Colors.RESET}")
    for header in project_headers:
        # Base type = no outgoing edges (doesn't include other project headers)
        out_degree = G.out_degree(header) if G is not None and header in G else 0
        if out_degree == 0:
            base_types.add(header)
        
        # Compute transitive dependencies using NetworkX descendants
        if G is not None and header in G:
            descendants = nx.descendants(G, header)
            header_transitive_deps[header] = len(descendants)
            
            # Reverse impact: how many headers depend on this one
            header_reverse_impact[header] = len(reverse_deps[header])
            
            # Longest chain through this header
            # Find longest path from this node to any leaf (base type)
            try:
                # Get all paths from this header to base types
                max_chain = 0
                for base in base_types:
                    if base in descendants:
                        try:
                            path_len = nx.shortest_path_length(G, header, base)
                            max_chain = max(max_chain, int(path_len))
                        except nx.NetworkXNoPath:
                            pass
                header_max_chain_length[header] = max_chain
            except nx.NetworkXError:
                header_max_chain_length[header] = 0
        else:
            header_transitive_deps[header] = 0
            header_reverse_impact[header] = 0
            header_max_chain_length[header] = 0
    
    elapsed = time.time() - start_time
    print(f"{Colors.BLUE}Finished dependency analysis in {elapsed:.2f}s{Colors.RESET}")
    print(f"{Colors.BLUE}Total unique project headers: {len(project_headers)}{Colors.RESET}")
    print(f"{Colors.BLUE}Identified {len(base_types)} base type headers (no direct project includes){Colors.RESET}")
    
    if base_types and len(base_types) < 50:
        print(f"{Colors.CYAN}Base type headers:{Colors.RESET}")
        for bt in sorted(base_types):
            print_success(f"  {bt}", prefix=False)
    
    problematic = []
    print(f"{Colors.BLUE}Checking for headers exceeding threshold ({threshold})...{Colors.RESET}")
    for header, trans_count in header_transitive_deps.items():
        if trans_count > threshold:
            usage_count = header_usage_count.get(header, 0)
            reverse_impact = header_reverse_impact.get(header, 0)
            chain_length = header_max_chain_length.get(header, 0)
            problematic.append((header, trans_count, usage_count, reverse_impact, chain_length))
    
    if problematic:
        print_warning(f"  Found {len(problematic)} headers exceeding threshold", prefix=False)
    print(f"{Colors.BLUE}Dependency analysis complete.{Colors.RESET}")
    
    return DependencyAnalysisResult(
        problematic=sorted(problematic, key=lambda x: x[1], reverse=True),
        source_to_deps=source_to_deps,
        base_types=base_types,
        header_usage_count=header_usage_count,
        header_reverse_impact=header_reverse_impact,
        header_max_chain_length=header_max_chain_length
    )


def main() -> int:
    """Main entry point for the dependency hell analyzer.
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Verify dependencies early
    verify_graph()
    
    parser = argparse.ArgumentParser(
        description='Comprehensive dependency analysis: find headers causing dependency hell.',
        epilog='''
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
        default=50,
        help='Minimum transitive dependency count to flag as problematic (default: 50). '
             'Lower = more strict (e.g., 30), higher = less strict (e.g., 100)'
    )
    
    parser.add_argument(
        '--top',
        type=int,
        default=10,
        help='Number of items to show in each ranked list (default: 10). '
             'Use 20-30 for comprehensive view'
    )
    
    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Show detailed per-header analysis with metrics, severity, and '
             'frequently cooccurring headers. Use this for deep-dive analysis'
    )
    
    parser.add_argument(
        '--changed',
        action='store_true',
        help='Only analyze changed headers (from rebuild root causes). '
             'Faster and more focused on recent modifications'
    )
    
    args = parser.parse_args()
    build_dir = args.build_directory

    # Validate arguments
    if args.threshold <= 0:
        logger.error(f"Invalid threshold: {args.threshold}. Must be positive.")
        return 1
    
    if args.top <= 0:
        logger.error(f"Invalid top value: {args.top}. Must be positive.")
        return 1

    print(f"{Colors.CYAN}Starting dependency hell analysis...{Colors.RESET}")
    if not os.path.isdir(build_dir):
        logger.error(f"Build directory not found: {build_dir}")
        return 1
    
    build_dir = os.path.abspath(build_dir)

    try:
        project_root = str(Path(build_dir).parent.parent.parent)
    except Exception as e:
        logger.error(f"Failed to determine project root: {e}")
        return 1

    # Get changed files if --changed is specified
    changed_headers: Set[str] = set()
    if args.changed:
        print(f"{Colors.BLUE}Extracting changed headers from rebuild root causes...{Colors.RESET}")
        try:
            rebuild_entries, reasons, root_causes = extract_rebuild_info(build_dir)
            changed_headers = set(root_causes.keys())
        except Exception as e:
            logger.error(f"Failed to extract rebuild info: {e}")
            return 1

        if not changed_headers:
            print_warning("\nNo changed header files found in rebuild root causes", prefix=False)
            return 0

        print(f"\n{Colors.CYAN}Found {len(changed_headers)} changed headers to analyze:{Colors.RESET}")
        for header in sorted(changed_headers):
            display_header = header
            if header.startswith(project_root):
                display_header = os.path.relpath(header, project_root)
            print(f"  {Colors.MAGENTA}{display_header}{Colors.RESET}")

    print(f"{Colors.BLUE}Running ninja dry-run to collect rebuild targets...{Colors.RESET}")
    # Run ninja -n -d explain to get what would rebuild
    try:
        result = subprocess.run(
            ["ninja", "-n", "-d", "explain"],
            capture_output=True,
            text=True,
            check=True,
            cwd=build_dir,
            timeout=60
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Ninja command failed: {e.stderr}")
        return 1
    except subprocess.TimeoutExpired:
        logger.error("Ninja command timed out after 60 seconds")
        return 1
    except FileNotFoundError:
        logger.error("Ninja not found. Please ensure ninja is installed and in PATH.")
        return 1

    lines = result.stderr.splitlines()

    rebuild_targets = []

    for line in lines:
        m = RE_OUTPUT.search(line)
        if not m:
            continue

        explain_msg = m.group(1)

        # Skip "is dirty" lines - these are just CMake files
        if "is dirty" in explain_msg:
            continue

        output_file = "unknown"
        if explain_msg.startswith("output "):
            parts = explain_msg.split(" ", 2)
            if len(parts) > 1:
                output_file = parts[1]
        elif "command line changed for " in explain_msg:
            output_file = explain_msg.split("command line changed for ", 1)[1]
        
        # Only include actual object files
        if any(f'{ext}.o' in output_file for ext in VALID_SOURCE_EXTENSIONS):
            rebuild_targets.append(output_file)

    # If no rebuilds detected, get all object files instead
    if not rebuild_targets:
        print_warning("No rebuilds detected, analyzing all object files...", prefix=False)
        try:
            result = subprocess.run(
                ["ninja", "-t", "targets", "all"],
                capture_output=True,
                text=True,
                check=True,
                cwd=build_dir,
                timeout=30
            )
            for line in result.stdout.splitlines():
                target = line.split(':')[0].strip()
                if any(f'{ext}.o' in target for ext in VALID_SOURCE_EXTENSIONS):
                    rebuild_targets.append(target)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.warning(f"Failed to get ninja targets: {e}")

    if not rebuild_targets:
        logger.error("No compilation targets found.")
        return 1

    mode_desc = f"changed headers only" if args.changed else "all headers"
    print(f"\n{Colors.CYAN}Analyzing dependency hell ({len(rebuild_targets)} targets, {mode_desc})...{Colors.RESET}")
    
    try:
        analysis_result = analyze_dependency_hell(build_dir, rebuild_targets, args.threshold)
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        logger.debug("Exception details:", exc_info=True)
        return 1
    
    problematic = analysis_result.problematic
    source_to_deps = analysis_result.source_to_deps
    base_types = analysis_result.base_types
    header_usage_count = analysis_result.header_usage_count
    header_reverse_impact = analysis_result.header_reverse_impact
    header_max_chain_length = analysis_result.header_max_chain_length
    
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
    # This is needed for severity calculation even when not in detailed mode
    all_problematic_headers = [h for h, _, _, _, _ in problematic]
    
    source_dep_map = SourceDependencyMap(source_to_deps)
    
    cooccurrence = find_dependency_fanout(
        all_problematic_headers, source_dep_map,
        is_header_filter=lambda d: d.endswith(VALID_HEADER_EXTENSIONS),
        is_system_filter=is_system_header_lib
    )
    
    # Show detailed analysis if requested
    if args.detailed:
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
                    print(f"    Frequently pulls in:")
                    for coheader, count in top_cooccur:
                        display_co = coheader
                        if coheader.startswith(project_root):
                            display_co = os.path.relpath(coheader, project_root)
                        print(f"      {Colors.DIM}{display_co}{Colors.RESET} ({count} times)")
    
    # Calculate summary statistics
    total_problematic = len(problematic)
    critical_count = len([h for h, dc, _, _, _ in problematic if dc + (len([x for x, c in cooccurrence[h].items() if c > FANOUT_THRESHOLD]) * 10) > SEVERITY_CRITICAL])
    high_count = len([h for h, dc, _, _, _ in problematic if SEVERITY_HIGH < (dc + (len([x for x, c in cooccurrence[h].items() if c > FANOUT_THRESHOLD]) * 10)) <= SEVERITY_CRITICAL])
    moderate_count = total_problematic - critical_count - high_count
    
    # Print summary last
    print(f"\n{Colors.BRIGHT}═══ Dependency Hell Summary ═══{Colors.RESET}")
    print(f"  Analyzed: {len(rebuild_targets)} rebuild targets")
    print(f"  Method: clang-scan-deps (parallel, optimized)")
    print(f"  Found: {total_problematic} headers with >{args.threshold} transitive dependencies")
    print(f"  Severity breakdown: {Colors.RED}{critical_count} CRITICAL{Colors.RESET}, "
          f"{Colors.YELLOW}{high_count} HIGH{Colors.RESET}, "
          f"{Colors.CYAN}{moderate_count} MODERATE{Colors.RESET}")
    print(f"\n{Colors.BRIGHT}Metric Explanations:{Colors.RESET}")
    print(f"  {Colors.BRIGHT}Build Impact{Colors.RESET} = deps × direct usage - measures compilation cost of header's dependencies")
    print(f"  {Colors.BRIGHT}Rebuild Cost{Colors.RESET} = usage × (1 + dependents) - measures rebuild impact if header changes")
    print(f"  {Colors.BRIGHT}Hub Headers{Colors.RESET} = reverse dependency count - shows architectural bottlenecks")
    
    # Show top 10 worst offenders
    if problematic:
        print(f"\n  {Colors.BRIGHT}Top {args.top} Worst Offenders (by dependency count):{Colors.RESET}")
        for i, (header, dep_count, usage_count, reverse_impact, chain_length) in enumerate(problematic[:args.top], 1):
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
        print(f"\n  {Colors.BRIGHT}Top {args.top} by Build Impact (deps × usage count):{Colors.RESET}")
        by_impact = sorted(problematic, key=lambda x: x[1] * x[2], reverse=True)
        for i, (header, dep_count, usage_count, reverse_impact, chain_length) in enumerate(by_impact[:args.top], 1):
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
        
        # NEW: Show top N by rebuild cost (what causes most expensive rebuilds if changed)
        print(f"\n  {Colors.BRIGHT}Top {args.top} by Rebuild Cost (if changed, what causes worst rebuild):{Colors.RESET}")
        by_rebuild_cost = sorted(problematic, key=lambda x: x[2] * (1 + x[3]), reverse=True)
        for i, (header, dep_count, usage_count, reverse_impact, chain_length) in enumerate(by_rebuild_cost[:args.top], 1):
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
            
            print(f"    {Colors.DIM}{i:2}.{Colors.RESET} {cost_color}{display_path}{Colors.RESET} "
                  f"({usage_count} uses × {reverse_impact} dependents = {rebuild_cost:,} source rebuilds)")
        
        # NEW: Show top N hub headers (most headers depend on these)
        print(f"\n  {Colors.BRIGHT}Top {args.top} Hub Headers (most other headers depend on these):{Colors.RESET}")
        by_hub = sorted(problematic, key=lambda x: x[3], reverse=True)
        for i, (header, dep_count, usage_count, reverse_impact, chain_length) in enumerate(by_hub[:args.top], 1):
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
            
            print(f"    {Colors.DIM}{i:2}.{Colors.RESET} {hub_color}{display_path}{Colors.RESET} "
                  f"({reverse_impact} headers depend on this, max chain: {chain_length})")
    
    if not args.detailed and total_problematic > 0:
        print(f"\n  {Colors.DIM}Use --detailed to see per-header analysis{Colors.RESET}")
    
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
        logger.error(f"Missing dependency: {e}")
        sys.exit(EXIT_RUNTIME_ERROR)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.debug("Exception details:", exc_info=True)
        sys.exit(EXIT_RUNTIME_ERROR)
