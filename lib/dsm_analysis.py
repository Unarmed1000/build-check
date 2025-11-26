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
"""DSM-specific analysis functions for buildCheckDSM.

This module provides helper functions for DSM analysis that can be tested independently
and reused across the codebase. Extracted from buildCheckDSM.py for better modularity.
"""

import os
import logging
from typing import Dict, Set, List, Tuple, Any, DefaultDict, Optional

import networkx as nx
import numpy as np

from .color_utils import Colors, print_error, print_warning, print_success
from .constants import (
    HIGH_COUPLING_THRESHOLD,
    MODERATE_COUPLING_THRESHOLD,
    SPARSITY_HEALTHY,
    SPARSITY_MODERATE,
    MAX_CYCLES_DISPLAY,
    MAX_LAYERS_DISPLAY,
    CYCLE_HIGHLIGHT,
    DEPENDENCY_MARKER,
    EMPTY_CELL,
    EXIT_SUCCESS,
    EXIT_INVALID_ARGS,
    EXIT_RUNTIME_ERROR,
)
from .file_utils import cluster_headers_by_directory
from .dsm_types import (
    MatrixStatistics,
    DSMAnalysisResults,
    DSMDelta,
    CouplingStatistics,
    CycleComplexityStats,
    StabilityChange,
    RippleImpactAnalysis,
    ArchitecturalInsights,
    FutureRebuildPrediction,
    LayerMovementStats,
    ImprovementCandidate,
)
from .graph_utils import DSMMetrics, build_reverse_dependencies, calculate_dsm_metrics, analyze_cycles, compute_layers as compute_layer_structure, visualize_dsm
from .library_parser import analyze_cross_library_dependencies
from .ninja_utils import validate_build_directory_with_feedback
from .clang_utils import build_include_graph, is_system_header
from .git_utils import find_git_repo, get_working_tree_changes_from_commit, categorize_changed_files
from .dependency_utils import build_reverse_dependency_map, compute_affected_sources

logger = logging.getLogger(__name__)

# Export types for mypy
__all__ = [
    "MatrixStatistics",
    "DSMAnalysisResults",
    "DSMDelta",
    "calculate_matrix_statistics",
    "print_summary_statistics",
    "print_circular_dependencies",
    "print_layered_architecture",
    "print_high_coupling_headers",
    "print_recommendations",
    "display_directory_clusters",
    "compare_dsm_results",
    "print_dsm_delta",
    "run_dsm_analysis",
    "display_analysis_results",
    "run_differential_analysis",
    "run_differential_analysis_with_baseline",
    "run_git_working_tree_analysis",
    "run_proactive_improvement_analysis",
    "identify_improvement_candidates",
    "estimate_improvement_roi",
    "rank_improvements_by_impact",
]


def calculate_matrix_statistics(
    all_headers: Set[str],
    header_to_headers: Dict[str, Set[str]],
    metrics: Optional[Dict[str, DSMMetrics]] = None,
    headers_in_cycles: Optional[Set[str]] = None,
    num_cycles: Optional[int] = None,
) -> MatrixStatistics:
    """Calculate DSM matrix statistics including advanced metrics.

    Args:
        all_headers: Set of all headers
        header_to_headers: Mapping of headers to their dependencies
        metrics: Optional pre-computed per-header metrics
        headers_in_cycles: Optional set of headers in cycles
        num_cycles: Optional number of cycle groups

    Returns:
        MatrixStatistics with comprehensive architectural metrics
    """
    from lib.graph_utils import calculate_architecture_quality_score, calculate_adp_score, calculate_interface_implementation_ratio

    total_headers = len(all_headers)
    total_possible_deps = total_headers * (total_headers - 1)  # Exclude diagonal
    total_actual_deps = sum(len(deps) for deps in header_to_headers.values())

    sparsity = 100.0 * (1 - total_actual_deps / total_possible_deps) if total_possible_deps > 0 else 100.0
    avg_deps = total_actual_deps / total_headers if total_headers > 0 else 0

    # Architecture health indicator
    if sparsity > SPARSITY_HEALTHY:
        health = "Healthy - low coupling"
        health_color = Colors.GREEN
    elif sparsity > SPARSITY_MODERATE:
        health = "Moderate coupling"
        health_color = Colors.YELLOW
    else:
        health = "Highly coupled"
        health_color = Colors.RED

    # Calculate advanced metrics if data available
    quality_score = 0.0
    adp_score = 0.0
    interface_ratio = 0.0

    if metrics is not None:
        # Calculate coupling percentiles for quality score
        couplings = [m.coupling for m in metrics.values()]
        if couplings:
            coupling_p95 = float(np.percentile(couplings, 95))
            coupling_p99 = float(np.percentile(couplings, 99))

            # Count stable interfaces (stability < 0.3)
            num_stable_interfaces = sum(1 for m in metrics.values() if m.stability < 0.3)

            # Calculate interface ratio
            interface_ratio, num_stable_interfaces_calc, _ = calculate_interface_implementation_ratio(metrics, stability_threshold=0.3)
            num_stable_interfaces = int(num_stable_interfaces_calc)
        else:
            coupling_p95 = 0
            coupling_p99 = 0
            num_stable_interfaces = 0

        # Calculate architecture quality score
        cycles_count = num_cycles if num_cycles is not None else 0
        quality_score = calculate_architecture_quality_score(
            sparsity=sparsity,
            num_cycles=cycles_count,
            total_headers=total_headers,
            coupling_p95=coupling_p95,
            coupling_p99=coupling_p99,
            num_stable_interfaces=num_stable_interfaces,
        )

        # Calculate ADP score
        if headers_in_cycles is not None:
            adp_score = calculate_adp_score(total_headers, len(headers_in_cycles))

    return MatrixStatistics(
        total_headers=total_headers,
        total_actual_deps=total_actual_deps,
        total_possible_deps=total_possible_deps,
        sparsity=sparsity,
        avg_deps=avg_deps,
        health=health,
        health_color=health_color,
        quality_score=quality_score,
        adp_score=adp_score,
        interface_ratio=interface_ratio,
    )


def print_summary_statistics(stats: MatrixStatistics, cycles_count: int, headers_in_cycles_count: int, layers: List[List[str]], has_cycles: bool) -> None:
    """Print summary statistics section.

    Args:
        stats: MatrixStatistics from calculate_matrix_statistics
        cycles_count: Number of circular dependency groups
        headers_in_cycles_count: Number of headers in cycles
        layers: List of dependency layers
        has_cycles: Whether the graph has cycles
    """
    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}SUMMARY STATISTICS{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")

    print(f"\n{Colors.BRIGHT}Matrix Properties:{Colors.RESET}")
    print(f"  Total headers: {stats.total_headers}")
    print(f"  Total dependencies: {stats.total_actual_deps}")
    print(f"  Matrix size: {stats.total_headers} × {stats.total_headers}")
    print(f"  Sparsity: {stats.sparsity:.1f}% (lower is more coupled)")
    print(f"  Average dependencies per header: {stats.avg_deps:.1f}")
    print(f"  Architecture health: {stats.health_color}{stats.health}{Colors.RESET}")

    # Display advanced metrics if available
    if stats.quality_score > 0:
        print(f"\n{Colors.BRIGHT}Architecture Quality:{Colors.RESET}")

        # Quality score with color coding
        if stats.quality_score >= 80:
            quality_color = Colors.GREEN
            quality_label = "Excellent"
        elif stats.quality_score >= 60:
            quality_color = Colors.CYAN
            quality_label = "Good"
        elif stats.quality_score >= 40:
            quality_color = Colors.YELLOW
            quality_label = "Fair"
        else:
            quality_color = Colors.RED
            quality_label = "Needs Improvement"

        print(f"  Quality Score: {quality_color}{stats.quality_score:.1f}/100{Colors.RESET} ({quality_label})")

        if stats.adp_score > 0:
            adp_color = Colors.GREEN if stats.adp_score >= 90 else Colors.YELLOW if stats.adp_score >= 70 else Colors.RED
            print(f"  ADP Compliance: {adp_color}{stats.adp_score:.1f}%{Colors.RESET} (headers without cycles)")

        if stats.interface_ratio > 0:
            interface_color = Colors.GREEN if stats.interface_ratio >= 30 else Colors.YELLOW if stats.interface_ratio >= 15 else Colors.DIM
            print(f"  Interface Headers: {interface_color}{stats.interface_ratio:.1f}%{Colors.RESET} (stable, low coupling)")

    print(f"\n{Colors.BRIGHT}Structural Properties:{Colors.RESET}")
    print(f"  Circular dependency groups: {cycles_count}")
    print(f"  Headers in cycles: {headers_in_cycles_count}")

    if not has_cycles and layers:
        print(f"  Dependency layers: {len(layers)}")
        print(f"  Maximum dependency depth: {len(layers) - 1}")
    elif has_cycles:
        print_warning("Cannot compute layers: graph contains cycles", prefix=False)


def print_circular_dependencies(
    cycles: List[Set[str]], feedback_edges: List[Tuple[str, str]], project_root: str, cycles_only: bool = False, self_loops: Optional[List[str]] = None
) -> None:
    """Print circular dependencies analysis.

    Args:
        cycles: List of circular dependency groups (multi-header cycles only)
        feedback_edges: Edges to break to eliminate cycles
        project_root: Root directory for relative paths
        cycles_only: Whether we're in cycles-only mode
        self_loops: Optional list of headers that include themselves
    """
    if not cycles and not self_loops and cycles_only:
        return

    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}CIRCULAR DEPENDENCIES{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")

    if cycles:
        print_error(f"Found {len(cycles)} circular dependency groups:", prefix=False)
        print()

        display_cycles = cycles[:MAX_CYCLES_DISPLAY]
        for i, cycle in enumerate(sorted(display_cycles, key=len, reverse=True), 1):
            print_error(f"Cycle {i} ({len(cycle)} headers):", prefix=False)
            for header in sorted(cycle):
                rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                print(f"  • {rel_path}")
            print()

        if len(cycles) > MAX_CYCLES_DISPLAY:
            print(f"{Colors.DIM}... and {len(cycles) - MAX_CYCLES_DISPLAY} more cycles{Colors.RESET}\n")

        if feedback_edges:
            print(f"{Colors.BRIGHT}Suggested edges to remove to break cycles:{Colors.RESET}")
            print(f"{Colors.DIM}(Breaking these {len(feedback_edges)} dependencies would eliminate all cycles){Colors.RESET}\n")

            for src, dst in feedback_edges[:10]:  # Show first 10
                src_rel = os.path.relpath(src, project_root) if src.startswith(project_root) else src
                dst_rel = os.path.relpath(dst, project_root) if dst.startswith(project_root) else dst
                print_warning(f"{src_rel}", prefix=False)
                print(f" → {dst_rel}")

            if len(feedback_edges) > 10:
                print(f"  {Colors.DIM}... and {len(feedback_edges) - 10} more{Colors.RESET}")
    else:
        print_success("✓ No circular dependencies found!", prefix=False)
        print("  The codebase has a clean, acyclic dependency structure.")

    # Display self-loops as warnings (not true cycles)
    if self_loops:
        print(f"\n{Colors.YELLOW}{'─'*80}{Colors.RESET}")
        print_warning(f"Found {len(self_loops)} header(s) with self-references:", prefix=False)
        print(f"{Colors.DIM}(These headers include themselves - unusual but not true circular dependencies){Colors.RESET}\n")

        for header in sorted(self_loops)[:10]:  # Show first 10
            rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
            print(f"  ⚠  {rel_path}")

        if len(self_loops) > 10:
            print(f"  {Colors.DIM}... and {len(self_loops) - 10} more{Colors.RESET}")


def print_layered_architecture(layers: List[List[str]], project_root: str, show_layers: bool, auto_display: bool = False) -> None:
    """Print layered architecture analysis.

    Args:
        layers: List of dependency layers
        project_root: Root directory for relative paths
        show_layers: Whether to show layers (from --show-layers flag)
        auto_display: Whether layers were auto-displayed
    """
    if not layers:
        return

    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}LAYERED ARCHITECTURE{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")

    print(f"\n{Colors.BRIGHT}Dependency layers (from top to foundation):{Colors.RESET}")
    print(f"{Colors.DIM}Layer 0 = top-level sources (no incoming deps), higher layers = foundation (depended upon){Colors.RESET}\n")

    max_layers_to_show = len(layers) if show_layers else min(MAX_LAYERS_DISPLAY, len(layers))

    for layer_num, layer_headers in enumerate(layers[:max_layers_to_show]):
        print(f"{Colors.CYAN}Layer {layer_num} ({len(layer_headers)} headers):{Colors.RESET}")

        # Show sample headers from this layer
        sample_size = min(5, len(layer_headers))
        for header in sorted(layer_headers)[:sample_size]:
            rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
            print(f"  • {rel_path}")

        if len(layer_headers) > sample_size:
            print(f"  {Colors.DIM}... and {len(layer_headers) - sample_size} more{Colors.RESET}")
        print()

    if len(layers) > max_layers_to_show and not show_layers:
        print(f"{Colors.DIM}... and {len(layers) - max_layers_to_show} more layers (use --show-layers to see all){Colors.RESET}\n")

    if auto_display:
        print(f"{Colors.DIM}💡 Tip: Layers were automatically shown because of clean architecture.{Colors.RESET}\n")


def print_high_coupling_headers(
    sorted_headers: List[str],
    metrics: Dict[str, "DSMMetrics"],
    headers_in_cycles: Set[str],
    project_root: str,
    max_display: int = 20,
    directed_graph: Optional[Any] = None,
) -> None:
    """Print high-coupling headers analysis with PageRank prioritization.

    Args:
        sorted_headers: Headers sorted by coupling (descending)
        metrics: Metrics dataclass for each header
        headers_in_cycles: Set of headers in cycles
        project_root: Root directory for relative paths
        max_display: Maximum headers to display
        directed_graph: Optional NetworkX graph for PageRank calculation
    """
    from lib.graph_utils import identify_critical_headers

    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}HIGH-COUPLING HEADERS{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")

    # Compute PageRank if graph available
    pagerank_scores: Dict[str, float] = {}
    if directed_graph is not None:
        try:
            critical_headers = identify_critical_headers(directed_graph, top_n=len(sorted_headers))
            pagerank_scores = dict(critical_headers)
        except Exception as e:
            logger.warning("Could not compute PageRank: %s", e)

    print(f"\n{Colors.BRIGHT}Top {min(max_display, len(sorted_headers))} headers by coupling:{Colors.RESET}")
    print(f"{Colors.DIM}(Coupling = Fan-in + Fan-out, PageRank = architectural importance){Colors.RESET}\n")

    for header in sorted_headers[:max_display]:
        rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
        m = metrics[header]

        # Color by coupling level
        coupling = m.coupling
        if coupling >= HIGH_COUPLING_THRESHOLD:
            color = Colors.RED
        elif coupling >= MODERATE_COUPLING_THRESHOLD:
            color = Colors.YELLOW
        else:
            color = Colors.GREEN

        in_cycle = header in headers_in_cycles
        cycle_marker = f" {Colors.RED}[IN CYCLE]{Colors.RESET}" if in_cycle else ""

        # Add PageRank indicator if available
        pagerank_info = ""
        if header in pagerank_scores:
            pr_score = pagerank_scores[header]
            if pr_score > 0.01:  # Significant PageRank
                pagerank_info = f" | {Colors.CYAN}PageRank: {pr_score:.4f}{Colors.RESET}"

        print(f"{color}{rel_path}{Colors.RESET}{cycle_marker}")
        print(f"  Fan-out: {m.fan_out} | Fan-in: {m.fan_in} | Coupling: {coupling} | Stability: {m.stability:.3f}{pagerank_info}")


def print_architectural_hotspots(directed_graph: Any, metrics: Dict[str, "DSMMetrics"], project_root: str, top_n: int = 15) -> None:
    """Print architectural hotspots: betweenness centrality and hub nodes.

    Args:
        directed_graph: NetworkX directed graph
        metrics: Per-header metrics
        project_root: Project root for relative paths
        top_n: Number of items to show
    """
    from lib.graph_utils import compute_betweenness_centrality, find_hub_nodes, detect_god_objects

    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}ARCHITECTURAL HOTSPOTS{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")

    # Betweenness Centrality - identifies bottlenecks
    print(f"\n{Colors.BRIGHT}Bottleneck Headers (Betweenness Centrality):{Colors.RESET}")
    print(f"{Colors.DIM}Headers that appear frequently on dependency paths - architectural bottlenecks{Colors.RESET}\n")

    try:
        # Sample for large graphs to keep it fast
        k = min(1000, len(directed_graph.nodes())) if len(directed_graph.nodes()) > 2000 else None
        betweenness = compute_betweenness_centrality(directed_graph, k=k)

        if betweenness:
            sorted_betweenness = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)[:top_n]

            for i, (header, score) in enumerate(sorted_betweenness, 1):
                if score > 0:  # Only show non-zero scores
                    rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                    m = metrics.get(header)

                    # Color by significance
                    if score > 0.1:
                        color = Colors.RED
                    elif score > 0.05:
                        color = Colors.YELLOW
                    else:
                        color = Colors.GREEN

                    coupling_info = f" (coupling: {m.coupling})" if m else ""
                    print(f"  {i:2d}. {color}{rel_path}{Colors.RESET}")
                    print(f"      Betweenness: {score:.4f}{coupling_info}")

            if not any(score > 0 for _, score in sorted_betweenness):
                print(f"  {Colors.DIM}No significant bottlenecks detected{Colors.RESET}")
        else:
            print(f"  {Colors.DIM}Unable to compute betweenness centrality{Colors.RESET}")
    except Exception as e:
        print(f"  {Colors.DIM}Error computing betweenness: {e}{Colors.RESET}")

    # Hub Nodes - high connectivity
    print(f"\n{Colors.BRIGHT}Hub Headers (High Connectivity):{Colors.RESET}")
    print(f"{Colors.DIM}Headers with high total degree (fan-in + fan-out) - architectural focal points{Colors.RESET}\n")

    try:
        hubs = find_hub_nodes(directed_graph, threshold=15)

        if hubs:
            for i, (header, fan_in, fan_out) in enumerate(hubs[:top_n], 1):
                rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                total_degree = fan_in + fan_out

                # Color by connectivity level
                if total_degree >= 30:
                    color = Colors.RED
                elif total_degree >= 20:
                    color = Colors.YELLOW
                else:
                    color = Colors.CYAN

                print(f"  {i:2d}. {color}{rel_path}{Colors.RESET}")
                print(f"      Fan-in: {fan_in}, Fan-out: {fan_out}, Total: {total_degree}")
        else:
            print(f"  {Colors.DIM}No hub nodes with high connectivity detected{Colors.RESET}")
    except Exception as e:
        print(f"  {Colors.DIM}Error finding hub nodes: {e}{Colors.RESET}")

    # God Objects - extreme fan-out (anti-pattern)
    print(f"\n{Colors.BRIGHT}God Object Detection (Anti-pattern):{Colors.RESET}")
    print(f"{Colors.DIM}Headers with extreme fan-out that may violate Single Responsibility Principle{Colors.RESET}\n")

    god_objects = detect_god_objects(metrics, threshold=50)

    if god_objects:
        print(f"  {Colors.RED}⚠ Found {len(god_objects)} potential God Object(s):{Colors.RESET}\n")
        for i, (header, fan_out) in enumerate(god_objects[:10], 1):
            rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
            print(f"  {i:2d}. {Colors.RED}{rel_path}{Colors.RESET}")
            print(f"      Fan-out: {fan_out} (depends on {fan_out} other headers)")
        print(f"\n  {Colors.YELLOW}💡 Tip: Consider splitting these into smaller, focused components{Colors.RESET}")
    else:
        print(f"  {Colors.GREEN}✓ No God Objects detected (all fan-outs < 50){Colors.RESET}")


def print_recommendations(
    cycles: List[Set[str]],
    metrics: Dict[str, "DSMMetrics"],
    all_headers: Set[str],
    stats: "MatrixStatistics",
    feedback_edges: List[Tuple[str, str]],
    layers: List[List[str]],
    show_layers: bool,
) -> None:
    """Print recommendations based on analysis.

    Args:
        cycles: List of circular dependency groups
        metrics: Metrics dataclass for each header
        all_headers: All headers analyzed
        stats: Matrix statistics dataclass
        feedback_edges: Edges to break cycles
        layers: Dependency layers
        show_layers: Whether layers were displayed
    """
    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}RECOMMENDATIONS{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}\n")

    has_recommendations = False

    if cycles:
        print_warning("Priority: Break circular dependencies", prefix=False)
        print(f"  • {len(cycles)} circular dependency groups found")
        print(f"  • Consider removing {len(feedback_edges)} dependencies to eliminate cycles")
        print()
        has_recommendations = True

    high_coupling_count = sum(1 for h in all_headers if metrics[h].coupling >= HIGH_COUPLING_THRESHOLD)
    if high_coupling_count > 0:
        print_warning("Refactoring opportunity: Reduce high coupling", prefix=False)
        print(f"  • {high_coupling_count} headers have coupling ≥ {HIGH_COUPLING_THRESHOLD}")
        print("  • Consider splitting, using forward declarations, or reducing dependencies")
        print()
        has_recommendations = True

    if stats.sparsity < SPARSITY_MODERATE:
        print_warning("Architecture note: Low sparsity indicates high coupling", prefix=False)
        print(f"  • Matrix sparsity: {stats.sparsity:.1f}%")
        print("  • Consider modularizing to reduce global coupling")
        print()
        has_recommendations = True

    if not cycles and layers:
        print_success("✓ Clean layered architecture detected", prefix=False)
        print("  • No circular dependencies")
        print(f"  • {len(layers)} clear dependency layers")
        print(f"  • Maximum depth: {len(layers) - 1}")
        if not show_layers:
            print(f"\n{Colors.DIM}Tip: Layers were automatically shown above. Use --show-layers to force display.{Colors.RESET}")
        has_recommendations = True
    elif not cycles:
        print_success("✓ No circular dependencies", prefix=False)
        print("  • Clean acyclic dependency structure")
        print("  • Good foundation for refactoring")
        has_recommendations = True

    if not has_recommendations:
        print_success("✓ No major issues detected", prefix=False)
        print("  • Architecture appears healthy")


def compare_dsm_results(baseline: DSMAnalysisResults, current: DSMAnalysisResults) -> DSMDelta:
    """Compare two DSM analysis results and compute differences.

    Args:
        baseline: DSM analysis results from baseline build
        current: DSM analysis results from current build

    Returns:
        DSMDelta containing all differences and architectural insights
    """
    # Compute header set differences
    baseline_headers = set(baseline.sorted_headers)
    current_headers = set(current.sorted_headers)

    headers_added = current_headers - baseline_headers
    headers_removed = baseline_headers - current_headers
    common_headers = baseline_headers & current_headers

    # Compute cycle differences
    cycles_delta = len(current.cycles) - len(baseline.cycles)
    cycles_added = max(0, cycles_delta)
    cycles_removed = max(0, -cycles_delta)

    # Compute coupling changes for common headers
    coupling_increased: Dict[str, int] = {}
    coupling_decreased: Dict[str, int] = {}

    for header in common_headers:
        baseline_coupling = baseline.metrics[header].coupling
        current_coupling = current.metrics[header].coupling
        delta = current_coupling - baseline_coupling

        if delta > 0:
            coupling_increased[header] = delta
        elif delta < 0:
            coupling_decreased[header] = abs(delta)

    # Compute layer changes for common headers
    layer_changes: Dict[str, Tuple[int, int]] = {}

    if baseline.header_to_layer and current.header_to_layer:
        for header in common_headers:
            baseline_layer = baseline.header_to_layer.get(header, -1)
            current_layer = current.header_to_layer.get(header, -1)

            if baseline_layer != -1 and current_layer != -1 and baseline_layer != current_layer:
                layer_changes[header] = (baseline_layer, current_layer)

    # Compute cycle participation changes
    baseline_in_cycles = baseline.headers_in_cycles
    current_in_cycles = current.headers_in_cycles

    new_cycle_participants = (current_in_cycles & common_headers) - baseline_in_cycles
    resolved_cycle_participants = (baseline_in_cycles & common_headers) - current_in_cycles

    # Track pre-existing cycle headers (were in cycles in baseline, still in cycles in current)
    pre_existing_cycle_headers = baseline_in_cycles & current_in_cycles & common_headers

    # Track escalated cycle headers (pre-existing cycles + modified headers)
    modified_headers = set(coupling_increased.keys()) | set(coupling_decreased.keys()) | headers_added
    escalated_cycle_headers = pre_existing_cycle_headers & modified_headers

    # Track pre-existing unstable headers (stability >0.5 in both baseline and current)
    pre_existing_unstable_headers: Set[str] = set()
    for header in common_headers:
        if baseline.metrics[header].stability > 0.5 and current.metrics[header].stability > 0.5:
            pre_existing_unstable_headers.add(header)

    # Track pre-existing coupling outliers (will be computed in architectural insights)
    pre_existing_coupling_outliers: List[Tuple[str, float]] = []

    # Compute architectural insights
    architectural_insights: Optional[ArchitecturalInsights] = None
    if common_headers:  # Only compute if there are common headers
        # Detect interface extraction first
        future_savings = compute_future_rebuild_prediction(baseline.metrics, current.metrics, headers_removed, headers_added)

        architectural_insights = compute_architectural_insights(baseline.metrics, current.metrics, baseline, current, future_savings=future_savings)

        # Compute pre-existing coupling outliers from architectural insights
        if architectural_insights and architectural_insights.coupling_stats:
            cs = architectural_insights.coupling_stats
            # Find outliers (>2σ) that existed in both baseline and current
            baseline_outliers_2sigma = {h for h, c in cs.outliers_2sigma if h in baseline.metrics}
            for header, coupling in cs.outliers_2sigma:
                if header in common_headers:
                    # Check if this was also an outlier in baseline
                    baseline_coupling = baseline.metrics[header].coupling
                    baseline_mean = cs.mean_baseline
                    baseline_stddev = cs.stddev_baseline
                    if baseline_stddev > 0 and abs(baseline_coupling - baseline_mean) > 2 * baseline_stddev:
                        pre_existing_coupling_outliers.append((header, coupling))

    return DSMDelta(
        headers_added=headers_added,
        headers_removed=headers_removed,
        cycles_added=cycles_added,
        cycles_removed=cycles_removed,
        coupling_increased=coupling_increased,
        coupling_decreased=coupling_decreased,
        layer_changes=layer_changes,
        new_cycle_participants=new_cycle_participants,
        resolved_cycle_participants=resolved_cycle_participants,
        architectural_insights=architectural_insights,
        pre_existing_cycle_headers=pre_existing_cycle_headers,
        escalated_cycle_headers=escalated_cycle_headers,
        pre_existing_unstable_headers=pre_existing_unstable_headers,
        pre_existing_coupling_outliers=pre_existing_coupling_outliers,
    )


def compute_coupling_trends(baseline_metrics: Dict[str, DSMMetrics], current_metrics: Dict[str, DSMMetrics], common_headers: Set[str]) -> CouplingStatistics:
    """Analyze coupling distribution shifts and outliers.

    Args:
        baseline_metrics: Baseline per-header metrics
        current_metrics: Current per-header metrics
        common_headers: Headers present in both builds

    Returns:
        CouplingStatistics with distribution analysis
    """
    if not common_headers:
        # Return zero stats if no common headers
        return CouplingStatistics(
            mean_baseline=0,
            mean_current=0,
            median_baseline=0,
            median_current=0,
            stddev_baseline=0,
            stddev_current=0,
            p95_baseline=0,
            p95_current=0,
            p99_baseline=0,
            p99_current=0,
            mean_delta_pct=0,
            stddev_delta_pct=0,
            outliers_baseline=set(),
            outliers_current=set(),
            min_baseline=0,
            min_current=0,
            max_baseline=0,
            max_current=0,
            outliers_1sigma=[],
            outliers_2sigma=[],
        )

    # Extract coupling values for common headers
    baseline_couplings = [baseline_metrics[h].coupling for h in common_headers]
    current_couplings = [current_metrics[h].coupling for h in common_headers]

    # Compute statistics using numpy for accuracy
    mean_baseline = float(np.mean(baseline_couplings))
    mean_current = float(np.mean(current_couplings))
    median_baseline = float(np.median(baseline_couplings))
    median_current = float(np.median(current_couplings))
    min_baseline = float(np.min(baseline_couplings)) if baseline_couplings else 0
    min_current = float(np.min(current_couplings)) if current_couplings else 0
    max_baseline = float(np.max(baseline_couplings)) if baseline_couplings else 0
    max_current = float(np.max(current_couplings)) if current_couplings else 0

    # Standard deviation (need at least 2 values)
    stddev_baseline = float(np.std(baseline_couplings, ddof=1)) if len(baseline_couplings) > 1 else 0
    stddev_current = float(np.std(current_couplings, ddof=1)) if len(current_couplings) > 1 else 0

    # Percentiles using numpy for accurate calculation
    p95_baseline = float(np.percentile(baseline_couplings, 95))
    p95_current = float(np.percentile(current_couplings, 95))
    p99_baseline = float(np.percentile(baseline_couplings, 99))
    p99_current = float(np.percentile(current_couplings, 99))

    # Percentage changes
    mean_delta_pct = ((mean_current - mean_baseline) / mean_baseline * 100) if mean_baseline > 0 else 0
    stddev_delta_pct = ((stddev_current - stddev_baseline) / stddev_baseline * 100) if stddev_baseline > 0 else 0

    # Identify outliers (>1σ from mean)
    outliers_baseline = {h for h in common_headers if abs(baseline_metrics[h].coupling - mean_baseline) > stddev_baseline} if stddev_baseline > 0 else set()

    outliers_current = {h for h in common_headers if abs(current_metrics[h].coupling - mean_current) > stddev_current} if stddev_current > 0 else set()

    # Identify 1σ and 2σ outliers in current with their coupling values
    outliers_1sigma: List[Tuple[str, float]] = []
    outliers_2sigma: List[Tuple[str, float]] = []

    if stddev_current > 0:
        for h in common_headers:
            coupling = current_metrics[h].coupling
            deviation = abs(coupling - mean_current)
            if deviation > 2 * stddev_current:
                outliers_2sigma.append((h, coupling))
            elif deviation > stddev_current:
                outliers_1sigma.append((h, coupling))

        # Sort by coupling value (descending)
        outliers_1sigma.sort(key=lambda x: x[1], reverse=True)
        outliers_2sigma.sort(key=lambda x: x[1], reverse=True)

    return CouplingStatistics(
        mean_baseline=mean_baseline,
        mean_current=mean_current,
        median_baseline=median_baseline,
        median_current=median_current,
        stddev_baseline=stddev_baseline,
        stddev_current=stddev_current,
        p95_baseline=p95_baseline,
        p95_current=p95_current,
        p99_baseline=p99_baseline,
        p99_current=p99_current,
        mean_delta_pct=mean_delta_pct,
        stddev_delta_pct=stddev_delta_pct,
        outliers_baseline=outliers_baseline,
        outliers_current=outliers_current,
        min_baseline=min_baseline,
        min_current=min_current,
        max_baseline=max_baseline,
        max_current=max_current,
        outliers_1sigma=outliers_1sigma,
        outliers_2sigma=outliers_2sigma,
    )


def compute_cycle_insights(baseline_cycles: List[Set[str]], current_cycles: List[Set[str]], current_graph: Any) -> Optional[CycleComplexityStats]:
    """Compute cycle complexity statistics and identify critical breaking edges.

    Args:
        baseline_cycles: Cycles in baseline build
        current_cycles: Cycles in current build
        current_graph: NetworkX graph for current build

    Returns:
        CycleComplexityStats or None if no cycles in current
    """
    if not current_cycles:
        return None

    # Cycle size histogram
    size_histogram: Dict[int, int] = {}
    for cycle in current_cycles:
        size = len(cycle)
        size_histogram[size] = size_histogram.get(size, 0) + 1

    # Average and max cycle sizes
    baseline_sizes = [len(c) for c in baseline_cycles] if baseline_cycles else [0]
    current_sizes = [len(c) for c in current_cycles]

    avg_cycle_size_baseline = float(np.mean(baseline_sizes)) if baseline_sizes else 0
    avg_cycle_size_current = float(np.mean(current_sizes))
    max_cycle_size_baseline = max(baseline_sizes) if baseline_sizes else 0
    max_cycle_size_current = max(current_sizes)

    # Edge density per cycle (edges / nodes)
    edge_density_per_cycle: Dict[int, float] = {}
    for idx, cycle in enumerate(current_cycles):
        subgraph = current_graph.subgraph(cycle)
        num_edges = subgraph.number_of_edges()
        num_nodes = len(cycle)
        edge_density_per_cycle[idx] = num_edges / num_nodes if num_nodes > 0 else 0

    # Compute betweenness centrality for edges in cycles to find critical breaking edges
    critical_breaking_edges: List[Tuple[Tuple[str, str], float]] = []

    try:
        # Get all edges in cycles
        cycle_edges: Set[Tuple[str, str]] = set()
        for cycle in current_cycles:
            subgraph = current_graph.subgraph(cycle)
            cycle_edges.update(subgraph.edges())

        if cycle_edges:
            # Compute edge betweenness centrality (limited to cycle subgraph for performance)
            edge_betweenness = nx.edge_betweenness_centrality(current_graph, k=min(100, len(current_graph)))

            # Get top edges by betweenness within cycles
            cycle_edge_betweenness = [(edge, edge_betweenness.get(edge, 0)) for edge in cycle_edges]
            critical_breaking_edges = sorted(cycle_edge_betweenness, key=lambda x: x[1], reverse=True)[:5]
    except Exception as e:
        logger.debug("Could not compute edge betweenness: %s", e)

    return CycleComplexityStats(
        size_histogram=size_histogram,
        avg_cycle_size_baseline=avg_cycle_size_baseline,
        avg_cycle_size_current=avg_cycle_size_current,
        max_cycle_size_baseline=max_cycle_size_baseline,
        max_cycle_size_current=max_cycle_size_current,
        edge_density_per_cycle=edge_density_per_cycle,
        critical_breaking_edges=critical_breaking_edges,
    )


def compute_ripple_impact(
    baseline_graph: Any,
    current_graph: Any,
    baseline_metrics: Dict[str, DSMMetrics],
    current_metrics: Dict[str, DSMMetrics],
    changed_headers: Set[str],
    reverse_deps: Dict[str, Set[str]],
    compute_precise: bool = True,
    source_to_deps: Optional[Dict[str, List[str]]] = None,
) -> RippleImpactAnalysis:
    """Compute ripple impact with precise transitive closure analysis.

    Performs accurate transitive closure analysis for precise rebuild predictions (95% confidence).

    Args:
        baseline_graph: NetworkX graph for baseline
        current_graph: NetworkX graph for current
        baseline_metrics: Baseline metrics
        current_metrics: Current metrics
        changed_headers: Headers with coupling changes
        reverse_deps: Reverse dependency map (header -> dependents)
        compute_precise: Whether to compute precise transitive closure (default: True, for accurate results)
        source_to_deps: Optional mapping of source files to header dependencies

    Returns:
        RippleImpactAnalysis with precise impact scores
    """
    # Track high-impact headers
    high_impact_headers: List[Tuple[str, int, int]] = []

    for header in changed_headers:
        if header in current_metrics:
            fan_in = current_metrics[header].fan_in
            baseline_coupling = baseline_metrics.get(header, DSMMetrics(0, 0, 0, 0.5)).coupling
            current_coupling = current_metrics[header].coupling
            coupling_delta = current_coupling - baseline_coupling

            if coupling_delta > 0:
                high_impact_headers.append((header, fan_in, coupling_delta))

    # Sort by impact
    high_impact_headers.sort(key=lambda x: x[1] * x[2], reverse=True)
    high_impact_headers = high_impact_headers[:15]  # Top 15

    # Identify headers with reduced coupling (ripple reduction)
    ripple_reduction: List[Tuple[str, int]] = []
    for header in changed_headers:
        if header in baseline_metrics and header in current_metrics:
            baseline_coupling = baseline_metrics[header].coupling
            current_coupling = current_metrics[header].coupling
            if current_coupling < baseline_coupling:
                reduction = baseline_coupling - current_coupling
                ripple_reduction.append((header, reduction))

    ripple_reduction.sort(key=lambda x: x[1], reverse=True)
    ripple_reduction = ripple_reduction[:10]  # Top 10

    # Option 2A: Total downstream impact (sum of fan-ins)
    # This shows the average blast radius - can exceed 100% due to overlapping dependents
    total_downstream_impact = sum(current_metrics[h].fan_in for h in changed_headers if h in current_metrics)

    # Option 2B: Unique downstream count (primary metric)
    # This shows the precise percentage of build affected - bounded 0-100%
    unique_downstream_headers: Set[str] = set()

    for header in changed_headers:
        if header in reverse_deps:
            unique_downstream_headers.update(reverse_deps[header])

    unique_downstream_count = len(unique_downstream_headers)

    # Precise analysis
    precise_score: Optional[int] = None
    precise_confidence: Optional[float] = None

    if compute_precise:
        try:
            # Compute full transitive closure for precise downstream impact
            precise_affected = set()

            for header in changed_headers:
                if header in current_graph:
                    # Get all transitive dependents
                    descendants = nx.descendants(current_graph, header)
                    precise_affected.update(descendants)

            # Compare with baseline
            baseline_affected = set()
            for header in changed_headers:
                if header in baseline_graph:
                    descendants = nx.descendants(baseline_graph, header)
                    baseline_affected.update(descendants)

            precise_score = len(precise_affected)
            baseline_score = len(baseline_affected)

            # Confidence: 95% for precise transitive closure
            precise_confidence = 95.0

            logger.info("Precise impact: %d downstream headers (baseline: %d)", precise_score, baseline_score)
        except Exception as e:
            logger.warning("Precise impact computation failed: %s", e)

    # Calculate source file rebuild impact - DUAL METRICS:
    # 1. THIS COMMIT: Transitive closure of ALL changed headers (one-time restructuring cost)
    # 2. FUTURE ONGOING: Volatility-weighted direct dependents (ongoing cost per future change)

    this_commit_rebuild_count = 0
    future_ongoing_rebuild_count = 0
    baseline_ongoing_rebuild_count = 0
    total_source_files = 0
    this_commit_rebuild_percentage = 0.0
    future_ongoing_rebuild_percentage = 0.0
    baseline_ongoing_rebuild_percentage = 0.0
    ongoing_rebuild_delta_percentage = 0.0
    roi_payback_commits = 0.0
    roi_payback_min = 0.0
    roi_payback_max = 0.0

    if source_to_deps:
        total_source_files = len(source_to_deps)

        # ========== THIS COMMIT (One-Time Cost) ==========
        # Compute full set of affected headers (changed + all downstream transitively)
        all_affected_headers_this_commit: Set[str] = set(changed_headers)

        # Add all unique downstream headers
        all_affected_headers_this_commit.update(unique_downstream_headers)

        # For precise mode, also compute transitive closure for maximum accuracy
        if compute_precise and current_graph:
            try:
                for header in changed_headers:
                    if header in current_graph:
                        # Get all transitive dependents of this changed header
                        descendants = nx.descendants(current_graph, header)
                        all_affected_headers_this_commit.update(descendants)
            except Exception as e:
                logger.warning("Transitive closure for this commit rebuild failed: %s", e)

        # Count source files that depend on any affected header (direct or transitive)
        for source_file, deps in source_to_deps.items():
            deps_set = set(deps)
            # If source file includes any affected header, it needs rebuild
            if deps_set & all_affected_headers_this_commit:
                this_commit_rebuild_count += 1

        # Calculate percentage
        this_commit_rebuild_percentage = (this_commit_rebuild_count / total_source_files * 100) if total_source_files > 0 else 0.0

        # ========== FUTURE ONGOING (Ongoing Cost) ==========
        # Only count DIRECT dependents, weighted by volatility
        # Interface/abstract headers get 0.1 weight, implementation headers get 1.0 weight
        # CRITICAL FIX: Only count headers with INCREASED coupling (not all changed headers)

        interface_volatility_weight = 0.1
        impl_volatility_weight = 1.0

        def is_interface_header(header: str) -> bool:
            """Detect if header is an interface (low volatility)."""
            basename = os.path.basename(header).lower()
            return any(pattern in basename for pattern in ["interface", "iabstract", "/i", "_i.", ".i."])

        # Filter to only headers with INCREASED coupling (architectural regressions)
        headers_with_increased_coupling = {
            h for h in changed_headers if h in baseline_metrics and h in current_metrics and current_metrics[h].coupling > baseline_metrics[h].coupling
        }

        # Count weighted future impact (CURRENT architecture)
        future_affected_sources: Set[str] = set()

        for header in headers_with_increased_coupling:
            if header in reverse_deps:
                weight = interface_volatility_weight if is_interface_header(header) else impl_volatility_weight

                # If weight is low (interface), this header's changes rarely propagate
                if weight < 0.5:
                    continue  # Interface changes are rare, skip from future ongoing cost

                # Add source files that directly depend on this header
                for source_file, deps in source_to_deps.items():
                    deps_set = set(deps)
                    if header in deps_set:
                        future_affected_sources.add(source_file)

        future_ongoing_rebuild_count = len(future_affected_sources)
        future_ongoing_rebuild_percentage = (future_ongoing_rebuild_count / total_source_files * 100) if total_source_files > 0 else 0.0

        # ========== BASELINE COMPARISON (What Would Baseline Cost Be?) ==========
        # Compute what the ongoing rebuild cost would be if we were still on baseline
        # This allows us to show: "baseline: 80% → current: 70%" (improvement)

        baseline_affected_sources: Set[str] = set()
        baseline_reverse_deps: Dict[str, Set[str]] = {}

        # Build baseline reverse dependency map
        if baseline_graph:
            for node in baseline_graph.nodes():
                baseline_reverse_deps[node] = set(baseline_graph.predecessors(node))

        # Count what baseline's future ongoing cost would be
        # Use same logic: only headers with high coupling, volatility-weighted
        for header in changed_headers:
            if header in baseline_metrics:
                # Check if this header had significant coupling in baseline
                baseline_coupling = baseline_metrics[header].coupling
                if baseline_coupling > 1:  # Only count headers that had coupling in baseline
                    weight = interface_volatility_weight if is_interface_header(header) else impl_volatility_weight

                    if weight < 0.5:
                        continue

                    # Add source files that directly depend on this header
                    for source_file, deps in source_to_deps.items():
                        deps_set = set(deps)
                        if header in deps_set:
                            baseline_affected_sources.add(source_file)

        baseline_ongoing_rebuild_count = len(baseline_affected_sources)
        baseline_ongoing_rebuild_percentage = (baseline_ongoing_rebuild_count / total_source_files * 100) if total_source_files > 0 else 0.0

        # Calculate delta (negative = improvement, positive = regression)
        ongoing_rebuild_delta_percentage = future_ongoing_rebuild_percentage - baseline_ongoing_rebuild_percentage

        # ========== ROI CALCULATION ==========
        # Break-even point: commits until refactoring pays for itself
        # Formula: payback = this_commit_cost / (this_commit_cost - future_ongoing_cost)

        cost_delta = this_commit_rebuild_percentage - future_ongoing_rebuild_percentage

        if this_commit_rebuild_percentage == 0:
            # Zero-cost edge case: Immediate ROI
            roi_payback_commits = 0.0
            roi_payback_min = 0.0
            roi_payback_max = 0.0
        elif cost_delta <= 0:
            # Negative ROI: Future cost >= this commit cost (architectural regression)
            roi_payback_commits = -1.0
            roi_payback_min = -1.0
            roi_payback_max = -1.0
        else:
            # Positive ROI: Calculate break-even
            # Normalize to percentage per commit
            this_commit_cost_normalized = this_commit_rebuild_percentage / 100.0
            future_cost_normalized = future_ongoing_rebuild_percentage / 100.0

            savings_per_commit = this_commit_cost_normalized - future_cost_normalized

            if savings_per_commit > 0:
                roi_payback_commits = this_commit_cost_normalized / savings_per_commit

                # Confidence intervals: ±30% volatility variance, ±25% commit frequency variance
                volatility_variance = 0.30

                # Worst case: higher volatility (more changes) + lower commit frequency
                worst_case_savings = savings_per_commit * (1 + volatility_variance)
                roi_payback_min = this_commit_cost_normalized / worst_case_savings if worst_case_savings > 0 else roi_payback_commits

                # Best case: lower volatility (fewer changes) + higher commit frequency
                best_case_savings = savings_per_commit * (1 - volatility_variance)
                roi_payback_max = this_commit_cost_normalized / best_case_savings if best_case_savings > 0 else roi_payback_commits

                # Ensure min <= nominal <= max
                roi_payback_min = min(roi_payback_min, roi_payback_commits)
                roi_payback_max = max(roi_payback_max, roi_payback_commits)
            else:
                roi_payback_commits = -1.0
                roi_payback_min = -1.0
                roi_payback_max = -1.0

        logger.info(
            "Source rebuild impact - This commit: %d/%d files (%.1f%%), Baseline ongoing: %d/%d files (%.1f%%), Current ongoing: %d/%d files (%.1f%%), Delta: %.1f%%, ROI: %.1f commits (%.1f-%.1f)",
            this_commit_rebuild_count,
            total_source_files,
            this_commit_rebuild_percentage,
            baseline_ongoing_rebuild_count,
            total_source_files,
            baseline_ongoing_rebuild_percentage,
            future_ongoing_rebuild_count,
            total_source_files,
            future_ongoing_rebuild_percentage,
            ongoing_rebuild_delta_percentage,
            roi_payback_commits,
            roi_payback_min,
            roi_payback_max,
        )

    return RippleImpactAnalysis(
        precise_score=precise_score,
        precise_confidence=precise_confidence,
        high_impact_headers=high_impact_headers,
        ripple_reduction=ripple_reduction,
        total_downstream_impact=total_downstream_impact,
        unique_downstream_count=unique_downstream_count,
        this_commit_rebuild_count=this_commit_rebuild_count,
        this_commit_rebuild_percentage=this_commit_rebuild_percentage,
        future_ongoing_rebuild_count=future_ongoing_rebuild_count,
        future_ongoing_rebuild_percentage=future_ongoing_rebuild_percentage,
        baseline_ongoing_rebuild_count=baseline_ongoing_rebuild_count,
        baseline_ongoing_rebuild_percentage=baseline_ongoing_rebuild_percentage,
        ongoing_rebuild_delta_percentage=ongoing_rebuild_delta_percentage,
        total_source_files=total_source_files,
        roi_payback_commits=roi_payback_commits,
        roi_payback_min=roi_payback_min,
        roi_payback_max=roi_payback_max,
        future_savings=None,  # Will be computed separately if applicable
    )


def compute_future_rebuild_prediction(
    baseline_metrics: Dict[str, DSMMetrics], current_metrics: Dict[str, DSMMetrics], delta_headers_removed: Set[str], delta_headers_added: Set[str]
) -> Optional["FutureRebuildPrediction"]:
    """Predict future rebuild reduction from interface extraction patterns.

    This detects when headers have been refactored into interface+implementation pairs
    and estimates the future rebuild savings from isolating volatile code.

    Args:
        baseline_metrics: Baseline per-header metrics
        current_metrics: Current per-header metrics
        delta_headers_removed: Headers removed in the delta
        delta_headers_added: Headers added in the delta

    Returns:
        FutureRebuildPrediction if interface extraction pattern detected, None otherwise
    """
    from .dsm_types import FutureRebuildPrediction

    # Detect interface extraction pattern:
    # - Headers removed with high fan-in (>10)
    # - New headers added with names suggesting interface/impl split
    # - Current implementation headers with low/zero fan-in

    volatile_headers_removed: List[Tuple[str, int]] = []
    for header in delta_headers_removed:
        if header in baseline_metrics:
            fan_in = baseline_metrics[header].fan_in
            if fan_in >= 10:  # High fan-in = volatile
                volatile_headers_removed.append((header, fan_in))

    if not volatile_headers_removed:
        return None  # No high fan-in headers removed

    # Look for interface/impl patterns in added headers
    interface_headers = []
    impl_headers = []

    for header in delta_headers_added:
        header_lower = header.lower()
        # Interface patterns: IXxx, XxxInterface, XxxApi
        if ("/i" in header_lower or "interface" in header_lower or "api" in header_lower) and header in current_metrics:
            interface_headers.append(header)
        # Implementation patterns: XxxImpl, XxxImplementation
        elif ("impl" in header_lower or "implementation" in header_lower) and header in current_metrics:
            impl_headers.append(header)

    # Check if we have the pattern
    if not (interface_headers or impl_headers):
        return None  # No interface/impl pattern detected

    # Calculate baseline volatile fan-in
    baseline_volatile_fanin = sum(fan_in for _, fan_in in volatile_headers_removed)

    # Calculate current volatile fan-in (implementations should be isolated)
    # Use volatility weighting: interfaces change rarely (0.1x weight), implementations often (1.0x weight)
    interface_volatility_weight = 0.1
    impl_volatility_weight = 1.0

    current_volatile_fanin = 0
    isolated_impl_count = 0

    for header in impl_headers:
        if header in current_metrics:
            fan_in = current_metrics[header].fan_in
            # Weight implementation fan-ins at full volatility (they change frequently)
            current_volatile_fanin += int(fan_in * impl_volatility_weight)
            if fan_in == 0:
                isolated_impl_count += 1

    # Also count interface fan-ins (but they're stable, so weigh less)
    interface_fanin = 0
    for header in interface_headers:
        if header in current_metrics:
            # Weight interface fan-ins at reduced volatility (they change rarely)
            interface_fanin += int(current_metrics[header].fan_in * interface_volatility_weight)

    # Add weighted interface fan-in to current volatile total
    current_volatile_fanin += interface_fanin

    # Calculate reduction (implementations should have zero or minimal fan-in)
    if baseline_volatile_fanin > 0:
        # Future changes will primarily affect implementations (isolated) not interfaces
        reduction_pct = int((baseline_volatile_fanin - current_volatile_fanin) / baseline_volatile_fanin * 100)

        # Only report if significant reduction detected
        if reduction_pct >= 25 or isolated_impl_count > 0:
            description = (
                f"Extracted {len(interface_headers)} interface header(s) and isolated "
                f"{isolated_impl_count} implementation header(s). "
                f"Future changes to implementations will cascade to ~{current_volatile_fanin} "
                f"headers instead of {baseline_volatile_fanin}."
            )

            return FutureRebuildPrediction(
                baseline_volatile_fanin=baseline_volatile_fanin,
                current_volatile_fanin=current_volatile_fanin,
                reduction_percentage=reduction_pct,
                interface_headers=len(interface_headers),
                isolated_impl_headers=isolated_impl_count,
                description=description,
            )

    return None


def determine_severity(
    coupling_stats: CouplingStatistics,
    cycle_complexity: Optional[CycleComplexityStats],
    current_cycles_count: int,
    baseline_cycles_count: int,
    ripple_impact: Optional[RippleImpactAnalysis] = None,
) -> str:
    """Determine overall severity of architectural changes.

    Returns:
        "critical", "moderate", or "positive"
    """
    # Critical regressions
    if current_cycles_count > baseline_cycles_count and current_cycles_count > 0:
        if cycle_complexity and cycle_complexity.max_cycle_size_current > 5:
            return "critical"

    if coupling_stats.mean_delta_pct > 50:
        return "critical"

    if coupling_stats.p99_baseline > 0 and coupling_stats.p99_current > coupling_stats.p99_baseline * 1.5:
        return "critical"

    # Cycle churn (both baseline AND current have cycles, but count changed) = architectural instability
    # This is AFTER critical checks so high coupling takes precedence
    if baseline_cycles_count > 0 and current_cycles_count > 0 and current_cycles_count != baseline_cycles_count:
        return "moderate"  # Cycle churn indicates refactoring instability

    # Moderate concerns
    if coupling_stats.mean_delta_pct > 20:
        return "moderate"

    if coupling_stats.stddev_delta_pct > 30:
        return "moderate"

    # Positive improvements
    # Interface extraction pattern is architecturally positive
    if ripple_impact and ripple_impact.future_savings:
        return "positive"

    if current_cycles_count < baseline_cycles_count:
        return "positive"

    if coupling_stats.mean_delta_pct < -20:
        return "positive"

    return "moderate"


def generate_recommendations(
    coupling_stats: CouplingStatistics,
    cycle_complexity: Optional[CycleComplexityStats],
    stability_changes: StabilityChange,
    ripple_impact: RippleImpactAnalysis,
    current_cycles: List[Set[str]],
    current: DSMAnalysisResults,
    delta: DSMDelta,
) -> List[str]:
    """Generate actionable recommendations based on insights, prioritizing by change attribution.

    Prioritization order:
    1. NEW cycles (introduced by this change)
    2. ESCALATED pre-existing cycles (modified headers in existing cycles)
    3. Other NEW issues (coupling, instability, etc.)
    4. PRE-EXISTING issues (informational, dimmed)

    Returns:
        List of recommendation strings with severity indicators
    """
    recommendations: List[str] = []

    # PRIORITY 1: NEW CYCLES (introduced by this change)
    if cycle_complexity and current_cycles:
        # Check if any new cycles introduced
        new_cycles = [cycle for cycle in current_cycles if not any(h in delta.pre_existing_cycle_headers for h in cycle)]
        if new_cycles:
            if cycle_complexity.max_cycle_size_current > 5:
                recommendations.append(
                    f"🔴 CRITICAL: NEW large cycle ({cycle_complexity.max_cycle_size_current} nodes) introduced by this change - "
                    f"MUST eliminate before further development"
                )

            if cycle_complexity.critical_breaking_edges:
                edge, betweenness = cycle_complexity.critical_breaking_edges[0]
                recommendations.append(
                    f"🔴 CRITICAL: Break NEW edge {os.path.basename(edge[0])} → {os.path.basename(edge[1])} "
                    f"(betweenness: {betweenness:.2f}) introduced by this change"
                )

    # PRIORITY 2: ESCALATED PRE-EXISTING CYCLES (your modified headers in existing cycles)
    if delta.escalated_cycle_headers:
        escalated_names = ", ".join([os.path.basename(h) for h in sorted(delta.escalated_cycle_headers)[:3]])
        if len(delta.escalated_cycle_headers) > 3:
            escalated_names += "..."
        recommendations.append(
            f"🔴 CRITICAL: Your modified headers ({escalated_names}) are in PRE-EXISTING cycles - "
            f"resolve cycle before continuing changes to avoid compounding technical debt"
        )

    # PRIORITY 3: INTERFACE EXTRACTION (positive pattern)
    if ripple_impact.future_savings:
        future_pred = ripple_impact.future_savings
        recommendations.append(
            f"🟢 POSITIVE: Interface extraction detected - {future_pred.interface_headers} interface(s) "
            f"isolate {future_pred.isolated_impl_headers} implementation(s). "
            f"Future changes cascade to ~{future_pred.current_volatile_fanin} headers "
            f"instead of {future_pred.baseline_volatile_fanin} ({future_pred.reduction_percentage}% reduction)"
        )

    # PRIORITY 4: OTHER NEW ISSUES (coupling hotspots, instability)
    # Coupling hotspot recommendations (only if NOT pre-existing)
    if ripple_impact.high_impact_headers:
        top_header, fan_in, coupling_delta = ripple_impact.high_impact_headers[0]
        if top_header in current.metrics:
            pct_change = (coupling_delta / current.metrics[top_header].coupling) * 100
            recommendations.append(
                f"🔴 CRITICAL: NEW refactor hotspot header (coupling +{pct_change:.0f}%, "
                f"triggers rebuilds of {fan_in} files). Split into 2-3 focused headers to reduce blast radius by ~60%"
            )

    # Variance spike concerns
    if coupling_stats.stddev_delta_pct > 50:
        recommendations.append(
            f"🟡 MODERATE: Coupling variance increased {coupling_stats.stddev_delta_pct:.0f}% - "
            f"indicates emerging architectural hotspots. Review outlier headers for refactoring opportunities"
        )

    # New stability degradations (not pre-existing)
    new_unstable = [h for h in stability_changes.became_unstable if h not in delta.pre_existing_unstable_headers]
    if len(new_unstable) > 0:
        recommendations.append(
            f"🟡 MODERATE: {len(new_unstable)} headers became unstable (stability > 0.5) due to this change. "
            f"Consider inverting dependencies to improve stability"
        )

    # Positive improvements
    if ripple_impact.ripple_reduction:
        total_reduction = sum(r[1] for r in ripple_impact.ripple_reduction)
        recommendations.append(
            f"🟢 POSITIVE: {len(ripple_impact.ripple_reduction)} headers reduced coupling by {total_reduction} total. "
            f"Continue this trend to improve architectural health"
        )

    # PRIORITY 5: PRE-EXISTING ISSUES (informational, dimmed)
    # Pre-existing cycle churn (cycles both added and removed, but NOT new cycles)
    if cycle_complexity and current_cycles and delta.pre_existing_cycle_headers:
        if cycle_complexity.avg_cycle_size_baseline > 0 and cycle_complexity.avg_cycle_size_current > 0:
            baseline_cycles_count = int(cycle_complexity.avg_cycle_size_baseline)
            current_cycles_count = len(current_cycles)
            if baseline_cycles_count != current_cycles_count and min(baseline_cycles_count, current_cycles_count) > 0:
                recommendations.append(
                    f"⚪ INFO: Pre-existing cycle churn ({baseline_cycles_count}→{current_cycles_count} cycles existed before this change). "
                    f"Consider separate refactoring to stabilize architecture"
                )

    # Pre-existing coupling outliers
    if delta.pre_existing_coupling_outliers:
        recommendations.append(
            f"⚪ INFO: {len(delta.pre_existing_coupling_outliers)} coupling outliers (>2σ) existed in baseline - "
            f"consider separate technical debt reduction effort"
        )

    # Pre-existing unstable headers
    if delta.pre_existing_unstable_headers:
        recommendations.append(
            f"⚪ INFO: {len(delta.pre_existing_unstable_headers)} unstable headers (>0.5) existed in baseline - " f"not caused by this change"
        )

    if not recommendations:
        recommendations.append("✓ No significant architectural issues detected")

    return recommendations


def compute_architectural_insights(
    baseline_metrics: Dict[str, DSMMetrics],
    current_metrics: Dict[str, DSMMetrics],
    baseline: DSMAnalysisResults,
    current: DSMAnalysisResults,
    future_savings: Optional["FutureRebuildPrediction"] = None,
) -> ArchitecturalInsights:
    """Compute comprehensive architectural insights from differential analysis.

    Args:
        baseline_metrics: Baseline per-header metrics
        current_metrics: Current per-header metrics
        baseline: Baseline analysis results
        current: Current analysis results
        future_savings: Optional interface extraction prediction

    Returns:
        ArchitecturalInsights with all statistical and impact analysis
    """
    common_headers = set(baseline_metrics.keys()) & set(current_metrics.keys())

    # Coupling trends
    coupling_stats = compute_coupling_trends(baseline_metrics, current_metrics, common_headers)

    # Cycle complexity
    cycle_complexity = compute_cycle_insights(baseline.cycles, current.cycles, current.directed_graph)

    # Stability changes
    became_unstable: Set[str] = set()
    became_stable: Set[str] = set()
    high_instability: Set[str] = set()
    stability_details: Dict[str, Tuple[float, float]] = {}
    extreme_instability: List[Tuple[str, float]] = []

    for header in common_headers:
        baseline_stability = baseline_metrics[header].stability
        current_stability = current_metrics[header].stability

        if baseline_stability <= 0.5 and current_stability > 0.5:
            became_unstable.add(header)
            stability_details[header] = (baseline_stability, current_stability)
        elif baseline_stability > 0.5 and current_stability <= 0.5:
            became_stable.add(header)
            stability_details[header] = (baseline_stability, current_stability)

        if current_stability > 0.8:
            high_instability.add(header)
            extreme_instability.append((header, current_stability))

    # Sort extreme instability by value (descending)
    extreme_instability.sort(key=lambda x: x[1], reverse=True)

    stability_changes = StabilityChange(
        became_unstable=became_unstable,
        became_stable=became_stable,
        high_instability=high_instability,
        stability_details=stability_details,
        extreme_instability=extreme_instability,
    )

    # Changed headers (coupling increased or layer changes)
    changed_headers = {h for h in common_headers if baseline_metrics[h].coupling != current_metrics[h].coupling}

    # Ripple impact
    ripple_impact = compute_ripple_impact(
        baseline.directed_graph,
        current.directed_graph,
        baseline_metrics,
        current_metrics,
        changed_headers,
        current.reverse_deps,
        compute_precise=True,
        source_to_deps=current.source_to_deps,
    )

    # Add interface extraction prediction if detected
    if future_savings:
        ripple_impact.future_savings = future_savings

    # Layer depth delta
    max_layer_baseline = max(baseline.header_to_layer.values()) if baseline.header_to_layer else 0
    max_layer_current = max(current.header_to_layer.values()) if current.header_to_layer else 0
    layer_depth_delta = max_layer_current - max_layer_baseline

    # Layer movement statistics
    layer_movement: Optional[LayerMovementStats] = None
    if baseline.header_to_layer and current.header_to_layer:
        headers_moved_deeper: List[Tuple[str, int, int]] = []
        headers_moved_shallower: List[Tuple[str, int, int]] = []
        headers_skipped_layers: List[Tuple[str, int, int, int]] = []
        headers_stayed_same = 0

        for header in common_headers:
            if header in baseline.header_to_layer and header in current.header_to_layer:
                old_layer = baseline.header_to_layer[header]
                new_layer = current.header_to_layer[header]

                if new_layer > old_layer:
                    headers_moved_deeper.append((header, old_layer, new_layer))
                    if new_layer - old_layer > 2:
                        headers_skipped_layers.append((header, old_layer, new_layer, new_layer - old_layer))
                elif new_layer < old_layer:
                    headers_moved_shallower.append((header, old_layer, new_layer))
                    if old_layer - new_layer > 2:
                        headers_skipped_layers.append((header, old_layer, new_layer, old_layer - new_layer))
                else:
                    headers_stayed_same += 1

        # Sort by magnitude of change
        headers_moved_deeper.sort(key=lambda x: x[2] - x[1], reverse=True)
        headers_moved_shallower.sort(key=lambda x: x[1] - x[2], reverse=True)
        headers_skipped_layers.sort(key=lambda x: x[3], reverse=True)

        # Compute layer cohesion (headers per layer)
        layer_cohesion_baseline: Dict[int, int] = {}
        layer_cohesion_current: Dict[int, int] = {}

        for header, layer in baseline.header_to_layer.items():
            layer_cohesion_baseline[layer] = layer_cohesion_baseline.get(layer, 0) + 1

        for header, layer in current.header_to_layer.items():
            layer_cohesion_current[layer] = layer_cohesion_current.get(layer, 0) + 1

        layer_movement = LayerMovementStats(
            headers_moved_deeper=headers_moved_deeper,
            headers_moved_shallower=headers_moved_shallower,
            headers_skipped_layers=headers_skipped_layers,
            layer_cohesion_baseline=layer_cohesion_baseline,
            layer_cohesion_current=layer_cohesion_current,
            headers_stayed_same=headers_stayed_same,
        )

    # Generate recommendations (basic version without delta awareness)
    # These will be replaced with delta-aware versions in print_dsm_delta when delta is available
    recommendations: List[str] = []

    # Interface extraction pattern detected
    if ripple_impact.future_savings:
        future_pred = ripple_impact.future_savings
        recommendations.append(
            f"🟢 POSITIVE: Interface extraction detected - {future_pred.interface_headers} interface(s) "
            f"isolate {future_pred.isolated_impl_headers} implementation(s). "
            f"Future changes cascade to ~{future_pred.current_volatile_fanin} headers "
            f"instead of {future_pred.baseline_volatile_fanin} ({future_pred.reduction_percentage}% reduction)"
        )

    # Critical cycle recommendations
    if cycle_complexity and current.cycles:
        if cycle_complexity.max_cycle_size_current > 5:
            recommendations.append(f"🔴 CRITICAL: Break large cycle ({cycle_complexity.max_cycle_size_current} nodes) " f"to eliminate cascading dependencies")

        if cycle_complexity.critical_breaking_edges:
            edge, betweenness = cycle_complexity.critical_breaking_edges[0]
            recommendations.append(
                f"🔴 CRITICAL: Break edge {os.path.basename(edge[0])} → {os.path.basename(edge[1])} "
                f"(betweenness: {betweenness:.2f}) to significantly reduce cycle complexity"
            )

    # Coupling hotspot recommendations
    if ripple_impact.high_impact_headers:
        top_header, fan_in, coupling_delta = ripple_impact.high_impact_headers[0]
        if top_header in current.metrics:
            pct_change = (coupling_delta / current.metrics[top_header].coupling) * 100
            recommendations.append(
                f"🔴 CRITICAL: Refactor hotspot header (coupling +{pct_change:.0f}%, "
                f"triggers rebuilds of {fan_in} files). Split into 2-3 focused headers to reduce blast radius by ~60%"
            )

    # Variance spike concerns
    if coupling_stats.stddev_delta_pct > 50:
        recommendations.append(
            f"🟡 MODERATE: Coupling variance increased {coupling_stats.stddev_delta_pct:.0f}% - "
            f"indicates emerging architectural hotspots. Review outlier headers for refactoring opportunities"
        )

    # Stability degradations
    if len(stability_changes.became_unstable) > 0:
        recommendations.append(
            f"🟡 MODERATE: {len(stability_changes.became_unstable)} headers became unstable (stability > 0.5). "
            f"Consider inverting dependencies to improve stability"
        )

    # Positive improvements
    if ripple_impact.ripple_reduction:
        total_reduction = sum(r[1] for r in ripple_impact.ripple_reduction)
        recommendations.append(
            f"🟢 POSITIVE: {len(ripple_impact.ripple_reduction)} headers reduced coupling by {total_reduction} total. "
            f"Continue this trend to improve architectural health"
        )

    # Determine overall severity
    severity = determine_severity(coupling_stats, cycle_complexity, len(current.cycles), len(baseline.cycles), ripple_impact)

    # Confidence level (high if we have enough common headers)
    confidence_level = "high" if len(common_headers) > 10 else "medium" if len(common_headers) > 3 else "low"

    return ArchitecturalInsights(
        coupling_stats=coupling_stats,
        cycle_complexity=cycle_complexity,
        stability_changes=stability_changes,
        ripple_impact=ripple_impact,
        layer_depth_delta=layer_depth_delta,
        layer_movement=layer_movement,
        confidence_level=confidence_level,
        severity=severity,
        recommendations=recommendations,
    )


def print_dsm_delta(delta: DSMDelta, baseline: DSMAnalysisResults, current: DSMAnalysisResults, project_root: str, verbose: bool = False) -> None:
    """Display DSM differential analysis results.

    Args:
        delta: Computed differences between baseline and current
        baseline: Baseline DSM analysis results
        current: Current DSM analysis results
        project_root: Project root directory for relative paths
    """
    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}DSM DIFFERENTIAL ANALYSIS{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}\n")

    # Overall summary
    baseline_headers = set(baseline.sorted_headers)
    current_headers = set(current.sorted_headers)

    header_change = len(current_headers) - len(baseline_headers)
    header_change_str = f"+{header_change}" if header_change > 0 else str(header_change)
    header_color = Colors.GREEN if header_change >= 0 else Colors.RED

    dep_baseline = sum(len(deps) for deps in baseline.header_to_headers.values())
    dep_current = sum(len(deps) for deps in current.header_to_headers.values())
    dep_change = dep_current - dep_baseline
    dep_change_str = f"+{dep_change}" if dep_change > 0 else str(dep_change)
    dep_color = Colors.YELLOW if dep_change > 0 else Colors.GREEN if dep_change < 0 else Colors.WHITE

    cycle_change = len(current.cycles) - len(baseline.cycles)
    cycle_change_str = f"+{cycle_change}" if cycle_change > 0 else str(cycle_change)
    cycle_color = Colors.RED if cycle_change > 0 else Colors.GREEN if cycle_change < 0 else Colors.WHITE

    print(f"{Colors.BRIGHT}Summary:{Colors.RESET}")
    print(f"  Headers: {len(baseline_headers)} → {len(current_headers)} ({header_color}{header_change_str}{Colors.RESET})")
    print(f"  Dependencies: {dep_baseline} → {dep_current} ({dep_color}{dep_change_str}{Colors.RESET})")
    print(f"  Cycles: {len(baseline.cycles)} → {len(current.cycles)} ({cycle_color}{cycle_change_str}{Colors.RESET})")

    # FUTURE BUILD IMPACT - Always show (most important insight!)
    if delta.architectural_insights:
        ri = delta.architectural_insights.ripple_impact

        # Calculate rebuild impact percentages
        current_headers_count = len(current.sorted_headers) if current.sorted_headers else 1

        # Option 2B: Unique downstream count (primary - bounded 0-100%)
        rebuild_impact = (ri.unique_downstream_count / current_headers_count * 100) if current_headers_count > 0 else 0

        # Option 2A: Total downstream impact (supplementary - can exceed 100%)
        total_impact_pct = (ri.total_downstream_impact / current_headers_count * 100) if current_headers_count > 0 else 0

        # Add teaser to summary with ROI preview and baseline comparison
        # PRIORITY: Pure cycle addition (critical) > Cycle churn > Ongoing cost delta (long-term) > This-commit cost (one-time)

        # CRITICAL: Any cycle addition blocks ALL positive messaging
        # True cycle churn: both new AND resolved cycle participants (headers moved between cycles)
        if cycle_change > 0 and len(delta.resolved_cycle_participants) > 0:
            # Cycle churn (both added and removed = instability)
            print(
                f"  {Colors.YELLOW}⚠ Cycle churn detected: +{delta.cycles_added} added, "
                f"+{delta.cycles_removed} removed (net +{cycle_change}, instability concern){Colors.RESET}"
            )
        elif cycle_change < 0 and len(delta.new_cycle_participants) > 0:
            # Net cycle reduction but with new participants = churn
            print(
                f"  {Colors.YELLOW}⚠ Cycle churn detected: +{delta.cycles_added} added, "
                f"+{delta.cycles_removed} removed (net {cycle_change}, instability concern){Colors.RESET}"
            )
        elif cycle_change > 0:
            # Pure cycle addition - ALWAYS CRITICAL
            print(f"  {Colors.RED}⚠ CRITICAL: +{delta.cycles_added} circular dependencies introduced (details below){Colors.RESET}")
        elif cycle_change < 0 and delta.cycles_added > 0:
            # Net cycle reduction but still churn (fallback)
            print(
                f"  {Colors.YELLOW}⚠ Cycle churn detected: +{delta.cycles_added} added, "
                f"+{delta.cycles_removed} removed (net {cycle_change}, instability concern){Colors.RESET}"
            )
        elif ri.future_savings:
            fs = ri.future_savings
            if ri.total_source_files > 0:
                print(
                    f"  {Colors.GREEN}🚀 Future rebuild reduction: {fs.reduction_percentage}% headers, "
                    f"{ri.future_ongoing_rebuild_percentage:.1f}% ongoing source files (details below){Colors.RESET}"
                )
            else:
                print(f"  {Colors.GREEN}🚀 Future rebuild reduction: {fs.reduction_percentage}% (details below){Colors.RESET}")
        elif ri.ongoing_rebuild_delta_percentage < -5.0:
            # Significant improvement in ongoing cost - categorize by magnitude
            if ri.total_source_files > 0 and ri.baseline_ongoing_rebuild_percentage > 0:
                files_saved = ri.baseline_ongoing_rebuild_count - ri.future_ongoing_rebuild_count
                delta_pct = abs(ri.ongoing_rebuild_delta_percentage)

                # Determine magnitude and visual style
                if delta_pct >= 15.0:
                    # Significantly improved (>= 15%)
                    symbol = "✓✓✓"
                    color = Colors.BRIGHT + Colors.GREEN
                    magnitude = "SIGNIFICANTLY IMPROVED"
                elif delta_pct >= 10.0:
                    # Improved (10-15%)
                    symbol = "✓✓"
                    color = Colors.GREEN
                    magnitude = "improved"
                else:
                    # Slightly improved (5-10%)
                    symbol = "✓"
                    color = Colors.GREEN
                    magnitude = "slightly improved"

                print(
                    f"  {color}{symbol} Future rebuild impact: {magnitude} "
                    f"(saves {files_saved} of {ri.total_source_files} files per commit, {delta_pct:.1f}% reduction, details below){Colors.RESET}"
                )
            else:
                print(f"  {Colors.GREEN}✓ Future rebuild improvement: {abs(rebuild_impact):.0f}% fewer headers affected (details below){Colors.RESET}")
        elif ri.ongoing_rebuild_delta_percentage > 5.0:
            # Significant regression in ongoing cost - categorize by magnitude (PRIORITIZE ONGOING OVER ONE-TIME)
            if ri.total_source_files > 0:
                files_added = ri.future_ongoing_rebuild_count - ri.baseline_ongoing_rebuild_count
                delta_pct = abs(ri.ongoing_rebuild_delta_percentage)

                # Determine magnitude and visual style
                if delta_pct >= 15.0:
                    # Significantly degraded (>= 15%)
                    symbol = "⚠⚠⚠"
                    color = Colors.BRIGHT + Colors.RED
                    magnitude = "SIGNIFICANTLY DEGRADED"
                elif delta_pct >= 10.0:
                    # Degraded (10-15%)
                    symbol = "⚠⚠"
                    color = Colors.RED
                    magnitude = "DEGRADED"
                else:
                    # Slightly degraded (5-10%)
                    symbol = "⚠"
                    color = Colors.YELLOW
                    magnitude = "slightly degraded"

                print(
                    f"  {color}{symbol} Future rebuild impact: {magnitude} "
                    f"(adds {files_added} of {ri.total_source_files} files per commit, {delta_pct:.1f}% increase, details below){Colors.RESET}"
                )
            else:
                print(f"  {Colors.RED}⚠ Future rebuild cost: {rebuild_impact:.0f}% of build in blast radius (details below){Colors.RESET}")
        elif abs(ri.ongoing_rebuild_delta_percentage) < 5.0 and ri.total_source_files > 0:
            # Minimal change in ongoing cost - categorize with file counts and colors
            if ri.baseline_ongoing_rebuild_percentage > 0:
                delta_pct = ri.ongoing_rebuild_delta_percentage

                # Determine status, color, and file delta
                if abs(delta_pct) < 1.0:
                    # Unchanged (< 1%)
                    status_text = "unchanged"
                    color = Colors.DIM + Colors.YELLOW
                    symbol = "○"
                    file_detail = f"{ri.future_ongoing_rebuild_count} of {ri.total_source_files} files per commit"
                elif delta_pct < -1.0:
                    # Slightly improved (1-5%)
                    status_text = "slightly improved"
                    color = Colors.GREEN
                    symbol = "✓"
                    files_saved = ri.baseline_ongoing_rebuild_count - ri.future_ongoing_rebuild_count
                    file_detail = f"saves {files_saved} of {ri.total_source_files} files per commit, {abs(delta_pct):.1f}% reduction"
                elif delta_pct > 1.0:
                    # Slightly degraded (1-5%)
                    status_text = "slightly degraded"
                    color = Colors.YELLOW
                    symbol = "⚠"
                    files_added = ri.future_ongoing_rebuild_count - ri.baseline_ongoing_rebuild_count
                    file_detail = f"adds {files_added} of {ri.total_source_files} files per commit, {abs(delta_pct):.1f}% increase"
                else:
                    # Stable (very close to unchanged)
                    status_text = "stable"
                    color = Colors.DIM + Colors.YELLOW
                    symbol = "○"
                    file_detail = f"{ri.future_ongoing_rebuild_count} of {ri.total_source_files} files per commit"

                print(f"  {color}{symbol} Future rebuild impact: {status_text} " f"({file_detail}, details below){Colors.RESET}")
            else:
                # No baseline available - show current file count
                if ri.future_ongoing_rebuild_count > 0:
                    print(
                        f"  {Colors.YELLOW}○ Future rebuild impact: no significant change "
                        f"({ri.future_ongoing_rebuild_count} of {ri.total_source_files} files per commit, details below){Colors.RESET}"
                    )
                else:
                    print(f"  {Colors.YELLOW}○ Future rebuild impact: no significant change (details below){Colors.RESET}")

    # FUTURE BUILD IMPACT section (always shown when architectural_insights available)
    if delta.architectural_insights:
        ri = delta.architectural_insights.ripple_impact

        # Calculate impact metrics using Option 2B (primary) and Option 2A (supplementary)
        current_headers_count = len(current.sorted_headers) if current.sorted_headers else 1

        # Option 2B: Unique downstream count (primary - bounded 0-100%)
        rebuild_impact = (ri.unique_downstream_count / current_headers_count * 100) if current_headers_count > 0 else 0

        # Option 2A: Total downstream impact (supplementary - can exceed 100%)
        total_impact_pct = (ri.total_downstream_impact / current_headers_count * 100) if current_headers_count > 0 else 0

        print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")

        # CRITICAL PRIORITY: Check for cycle additions FIRST - blocks ALL positive messaging
        if cycle_change > 0:
            print(f"{Colors.BRIGHT}{Colors.RED}⚠ FUTURE BUILD IMPACT{Colors.RESET}")
            print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")
            print(f"{Colors.RED}CRITICAL: Circular dependencies introduced - architectural regression{Colors.RESET}\n")

            print(f"{Colors.BRIGHT}Cycle Impact:{Colors.RESET}")
            print(f"  • {Colors.RED}+{delta.cycles_added} circular dependency group(s) added{Colors.RESET}")
            if delta.cycles_removed > 0:
                print(f"  • +{delta.cycles_removed} group(s) resolved (cycle churn)")
            print(f"  • {len(delta.new_cycle_participants)} header(s) now in cycles")
            print(f"  • {Colors.RED}⚠ Cycles must be resolved before evaluating other metrics{Colors.RESET}")

            print(f"\n{Colors.BRIGHT}Why Cycles Are Critical:{Colors.RESET}")
            print(f"  • Circular dependencies create build instability")
            print(f"  • Changes propagate indefinitely through the cycle")
            print(f"  • Cannot establish clear architectural layers")
            print(f"  • Maintenance becomes exponentially harder")

            if ri.total_source_files > 0:
                print(f"\n{Colors.BRIGHT}Current Build Impact:{Colors.RESET}")
                print(
                    f"  • {Colors.BRIGHT}{ri.this_commit_rebuild_count} of {ri.total_source_files} .c/.cpp files{Colors.RESET} must rebuild ({ri.this_commit_rebuild_percentage:.1f}%)"
                )
                print(f"    {Colors.DIM}Immediate cost for introducing this cycle{Colors.RESET}")
                print(f"  • {Colors.YELLOW}Note: Other metrics (coupling, rebuild impact) are masked by cycle regression{Colors.RESET}")

            print(f"\n{Colors.BRIGHT}{Colors.RED}🔴 PRIORITY ACTION REQUIRED:{Colors.RESET}")
            print(f"  1. Review new circular dependencies in 'CIRCULAR DEPENDENCY CHANGES' section below")
            print(f"  2. Break cycles by extracting interfaces or inverting dependencies")
            print(f"  3. Re-evaluate architectural improvements after cycles are resolved")

        # Case 1: POSITIVE - Interface extraction detected
        elif ri.future_savings:
            fs = ri.future_savings
            print(f"{Colors.BRIGHT}{Colors.GREEN}🚀 FUTURE BUILD IMPACT{Colors.RESET}")
            print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")
            print(f"{Colors.DIM}This refactoring creates ongoing value for every future commit{Colors.RESET}\n")

            print(f"{Colors.BRIGHT}{Colors.GREEN}Interface Extraction Detected:{Colors.RESET}")
            print(f"  • {fs.description}")

            # Show ongoing cost first (long-term impact), then one-time cost
            print(f"\n{Colors.BRIGHT}Future Commits (Ongoing Cost):{Colors.RESET}")
            if ri.total_source_files > 0:
                print(
                    f"  • {Colors.GREEN}{Colors.BRIGHT}{ri.future_ongoing_rebuild_count} of {ri.total_source_files} .c/.cpp files{Colors.RESET} per change ({ri.future_ongoing_rebuild_percentage:.1f}%)"
                )
                if ri.baseline_ongoing_rebuild_count > 0 and ri.baseline_ongoing_rebuild_count != ri.future_ongoing_rebuild_count:
                    files_saved = ri.baseline_ongoing_rebuild_count - ri.future_ongoing_rebuild_count
                    if files_saved > 0:
                        file_word = "file" if files_saved == 1 else "files"
                        print(
                            f"    {Colors.GREEN}({files_saved} {file_word} saved vs. baseline: {ri.baseline_ongoing_rebuild_count} → {ri.future_ongoing_rebuild_count}){Colors.RESET}"
                        )
            print(f"  • {Colors.GREEN}{Colors.BRIGHT}{fs.reduction_percentage}% fewer headers affected{Colors.RESET} (which cascade to .c/.cpp files)")

            print(f"\n{Colors.BRIGHT}This Commit (One-Time Cost):{Colors.RESET}")
            if ri.total_source_files > 0:
                print(
                    f"  • {Colors.BRIGHT}{ri.this_commit_rebuild_count} of {ri.total_source_files} .c/.cpp files{Colors.RESET} must rebuild ({ri.this_commit_rebuild_percentage:.1f}%)"
                )
                print(f"    {Colors.DIM}One-time rebuild for this architectural change{Colors.RESET}")
            print(f"  • {rebuild_impact:.1f}% of headers in blast radius ({ri.unique_downstream_count} unique downstream headers)")

            if fs.isolated_impl_headers > 0:
                print(f"\n{Colors.BRIGHT}Implementation Isolation:{Colors.RESET}")
                print(f"  • {Colors.GREEN}✓ {fs.isolated_impl_headers} implementation header(s) fully isolated{Colors.RESET}")
                print(f"  • Future changes to these implementations will NOT cascade to dependent code")
                print(f"  • Developers can modify implementation details without triggering widespread header and .c/.cpp file rebuilds")

            # ROI with edge cases
            print(f"\n{Colors.BRIGHT}{Colors.CYAN}💡 ROI Analysis:{Colors.RESET}")
            if ri.roi_payback_commits == 0:
                print(f"  • {Colors.GREEN}{Colors.BRIGHT}ROI: Immediate (zero-cost refactoring){Colors.RESET}")
            elif ri.roi_payback_commits < 0:
                print(f"  • {Colors.RED}{Colors.BRIGHT}ROI: Negative (ongoing increased cost){Colors.RESET}")
            else:
                # Color-coded based on payback period
                if ri.roi_payback_commits < 5:
                    roi_color = Colors.GREEN
                elif ri.roi_payback_commits <= 10:
                    roi_color = Colors.YELLOW
                else:
                    roi_color = Colors.RED

                savings_pct = ri.this_commit_rebuild_percentage - ri.future_ongoing_rebuild_percentage
                savings_files = ri.this_commit_rebuild_count - ri.future_ongoing_rebuild_count
                print(
                    f"  • One-time cost: {Colors.BRIGHT}{ri.this_commit_rebuild_count} files{Colors.RESET} rebuild now ({ri.this_commit_rebuild_percentage:.1f}%)"
                )
                print(f"  • Ongoing savings: {Colors.GREEN}{Colors.BRIGHT}{savings_files} fewer files{Colors.RESET} per future commit ({savings_pct:.1f}%)")
                print(f"  • {roi_color}Break-even: {int(ri.roi_payback_min)}-{int(ri.roi_payback_max)} commits{Colors.RESET}")
                print(f"  • {Colors.GREEN}Long-term: Massive cumulative savings over project lifetime{Colors.RESET}")

        # Case 2: NEGATIVE - Increased coupling (bad architectural decision)
        # PRIORITY: Check ongoing cost delta (long-term), not one-time header rebuild impact
        elif ri.ongoing_rebuild_delta_percentage > 5.0:
            print(f"{Colors.BRIGHT}{Colors.RED}⚠ FUTURE BUILD IMPACT{Colors.RESET}")
            print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")
            print(f"{Colors.DIM}This change creates ongoing cost for every future commit{Colors.RESET}\n")

            print(f"{Colors.BRIGHT}{Colors.RED}Increased Coupling Detected:{Colors.RESET}")
            print(f"  • {len(delta.coupling_increased)} header(s) with increased coupling")
            print(f"  • Changes to these headers will cascade more widely")

            # Show ongoing cost first (long-term impact), then one-time cost
            print(f"\n{Colors.BRIGHT}Future Commits (Ongoing Cost):{Colors.RESET}")
            if ri.total_source_files > 0:
                # Lead with improvement/regression in bold color with clear visual indicators
                if ri.ongoing_rebuild_delta_percentage < -5.0:
                    # Improvement - green with success indicators throughout
                    files_saved = ri.baseline_ongoing_rebuild_count - ri.future_ongoing_rebuild_count
                    print(
                        f"  {Colors.GREEN}{Colors.BRIGHT}✓ {abs(ri.ongoing_rebuild_delta_percentage):.1f}% FEWER FILES REBUILD{Colors.RESET} {Colors.GREEN}— {files_saved} files saved per future commit{Colors.RESET}"
                    )
                    print(
                        f"    {Colors.BRIGHT}Was:{Colors.RESET} {ri.baseline_ongoing_rebuild_count} files ({ri.baseline_ongoing_rebuild_percentage:.1f}%)  {Colors.GREEN}→{Colors.RESET}  {Colors.BRIGHT}Now:{Colors.RESET} {ri.future_ongoing_rebuild_count} files ({ri.future_ongoing_rebuild_percentage:.1f}%)"
                    )
                    print(
                        f"    {Colors.DIM}Each future change to these headers will trigger {files_saved} fewer files to rebuild (of {ri.total_source_files} total){Colors.RESET}"
                    )
                elif ri.ongoing_rebuild_delta_percentage > 5.0:
                    # Regression - red with warning indicators throughout
                    files_added = ri.future_ongoing_rebuild_count - ri.baseline_ongoing_rebuild_count
                    print(
                        f"  {Colors.RED}{Colors.BRIGHT}⚠ {abs(ri.ongoing_rebuild_delta_percentage):.1f}% MORE FILES REBUILD{Colors.RESET} {Colors.RED}— {files_added} extra files per future commit{Colors.RESET}"
                    )
                    print(
                        f"    {Colors.BRIGHT}Was:{Colors.RESET} {ri.baseline_ongoing_rebuild_count} files ({ri.baseline_ongoing_rebuild_percentage:.1f}%)  {Colors.RED}→{Colors.RESET}  {Colors.BRIGHT}Now:{Colors.RESET} {Colors.RED}{ri.future_ongoing_rebuild_count} files ({ri.future_ongoing_rebuild_percentage:.1f}%){Colors.RESET}"
                    )
                    print(
                        f"    {Colors.DIM}Each future change to these headers will trigger {files_added} additional files to rebuild (of {ri.total_source_files} total){Colors.RESET}"
                    )
                else:
                    # Minimal change
                    files_delta = ri.baseline_ongoing_rebuild_count - ri.future_ongoing_rebuild_count
                    print(f"  • {Colors.BRIGHT}{ri.future_ongoing_rebuild_percentage:.1f}% of .c/.cpp files{Colors.RESET} will rebuild per change")

                    if files_delta > 0:
                        file_word = "file" if files_delta == 1 else "files"
                        print(
                            f"    {Colors.GREEN}{files_delta} {file_word} saved{Colors.RESET} vs. baseline: {ri.baseline_ongoing_rebuild_count} → {ri.future_ongoing_rebuild_count} files"
                        )
                    elif files_delta < 0:
                        file_word = "file" if abs(files_delta) == 1 else "files"
                        print(
                            f"    {Colors.YELLOW}{abs(files_delta)} more {file_word}{Colors.RESET} vs. baseline: {ri.baseline_ongoing_rebuild_count} → {ri.future_ongoing_rebuild_count} files"
                        )
                    else:
                        print(f"    No change from baseline: {ri.baseline_ongoing_rebuild_count} → {ri.future_ongoing_rebuild_count} files")
            print(f"  • {ri.unique_downstream_count} unique downstream headers affected")
            print(f"  • Average blast radius: {total_impact_pct:.0f}% (sum of fan-ins)")

            print(f"\n{Colors.BRIGHT}This Commit (One-Time Cost):{Colors.RESET}")
            if ri.total_source_files > 0:
                print(
                    f"  • {Colors.BRIGHT}{ri.this_commit_rebuild_count} of {ri.total_source_files} .c/.cpp files{Colors.RESET} must rebuild ({ri.this_commit_rebuild_percentage:.1f}%)"
                )
                print(f"    {Colors.DIM}Immediate rebuild cost for this change{Colors.RESET}")
            print(f"  • {rebuild_impact:.1f}% of headers in blast radius")

            if ri.high_impact_headers:
                print(f"\n{Colors.BRIGHT}High-Impact Headers (Future Hotspots):{Colors.RESET}")
                for header, fan_in, coupling_delta in ri.high_impact_headers[:3]:
                    rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                    print(f"  • {rel_path}")
                    print(f"    Fan-in: {fan_in} headers depend on this, Coupling increase: +{coupling_delta}")
                    print(f"    {Colors.RED}→ Every change triggers rebuilds in {fan_in}+ headers and their .c/.cpp files{Colors.RESET}")

            # Check if there are actually future savings despite high rebuild_impact
            has_future_savings = (
                ri.total_source_files > 0
                and ri.future_ongoing_rebuild_percentage < ri.this_commit_rebuild_percentage
                and (ri.this_commit_rebuild_percentage - ri.future_ongoing_rebuild_percentage) > 5.0
            )

            if has_future_savings and verbose and delta.coupling_decreased:
                # Show BEFORE/AFTER even for high rebuild impact if there are future savings
                print(f"\n{Colors.BRIGHT}{'─'*80}{Colors.RESET}")
                print(f"{Colors.CYAN}BUT WAIT: FUTURE REBUILD REDUCTION DETECTED{Colors.RESET}\n")
                print(f"  {Colors.YELLOW}Despite the high one-time rebuild cost, this change reduces ongoing cost:{Colors.RESET}")
                print(f"  • Future commits: {ri.future_ongoing_rebuild_percentage:.1f}% rebuild (ongoing)")
                print(f"  • This commit: {ri.this_commit_rebuild_percentage:.1f}% rebuild (one-time)")
                print(
                    f"  • {Colors.GREEN}Net savings: {ri.this_commit_rebuild_percentage - ri.future_ongoing_rebuild_percentage:.1f}% per future commit{Colors.RESET}"
                )
                print()

                # Show coupling reduction details
                print(f"  {Colors.BRIGHT}Headers with Reduced Coupling:{Colors.RESET}")
                for header, decrease in sorted(delta.coupling_decreased.items(), key=lambda x: x[1], reverse=True)[:5]:
                    if header in baseline.metrics and header in current.metrics:
                        rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else os.path.basename(header)
                        old_fanin = baseline.metrics[header].fan_in
                        new_fanin = current.metrics[header].fan_in
                        reduction_pct = int((old_fanin - new_fanin) / old_fanin * 100) if old_fanin > 0 else 0
                        print(f"    • {rel_path}: {old_fanin} → {new_fanin} downstream headers rebuild ({reduction_pct}% reduction, cascades to .c/.cpp files)")
                print()

            print(f"\n{Colors.BRIGHT}{Colors.CYAN}💰 Cost Analysis:{Colors.RESET}")
            print(f"  • This commit: {ri.this_commit_rebuild_percentage:.1f}% rebuild (one-time cost)")
            print(f"  • {Colors.RED}Ongoing regression: {abs(ri.ongoing_rebuild_delta_percentage):.1f}% MORE files rebuild per future commit{Colors.RESET}")
            print(f"  • Baseline was: {ri.baseline_ongoing_rebuild_percentage:.1f}%, now: {ri.future_ongoing_rebuild_percentage:.1f}%")
            if has_future_savings:
                print(
                    f"  • {Colors.GREEN}BUT: Future savings of {ri.this_commit_rebuild_percentage - ri.future_ongoing_rebuild_percentage:.1f}% per commit makes this worthwhile{Colors.RESET}"
                )
            else:
                print(f"  • {Colors.YELLOW}Recommendation: Consider refactoring to reduce coupling before it compounds{Colors.RESET}")

        # Case 3: NEUTRAL/MINOR - Small changes (with enhanced reporting for coupling reduction)
        else:
            print(f"{Colors.BRIGHT}📊 FUTURE BUILD IMPACT{Colors.RESET}")
            print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")

            # Check for future savings (regardless of header-level rebuild_impact)
            has_future_savings = (
                ri.total_source_files > 0
                and ri.future_ongoing_rebuild_percentage < ri.this_commit_rebuild_percentage
                and (ri.this_commit_rebuild_percentage - ri.future_ongoing_rebuild_percentage) > 5.0
            )

            if abs(ri.ongoing_rebuild_delta_percentage) < 5.0 and not has_future_savings:
                print(f"{Colors.DIM}This change has minimal future build impact{Colors.RESET}\n")
                print(f"{Colors.BRIGHT}Impact Assessment:{Colors.RESET}")

                # Show dual metrics for clarity with baseline comparison
                if ri.total_source_files > 0:
                    print(
                        f"  • This commit: {ri.this_commit_rebuild_count} of {ri.total_source_files} .c/.cpp files must rebuild ({ri.this_commit_rebuild_percentage:.1f}%)"
                    )
                    if ri.baseline_ongoing_rebuild_percentage > 0:
                        files_delta = ri.baseline_ongoing_rebuild_count - ri.future_ongoing_rebuild_count
                        if files_delta != 0:
                            print(
                                f"  • Future ongoing: {ri.baseline_ongoing_rebuild_count} → {ri.future_ongoing_rebuild_count} .c/.cpp files ({ri.baseline_ongoing_rebuild_percentage:.1f}% → {ri.future_ongoing_rebuild_percentage:.1f}%)"
                            )
                        else:
                            print(
                                f"  • Future ongoing: {ri.future_ongoing_rebuild_count} .c/.cpp files per commit ({ri.future_ongoing_rebuild_percentage:.1f}%)"
                            )
                    else:
                        print(f"  • Future ongoing: {ri.future_ongoing_rebuild_count} .c/.cpp files per commit ({ri.future_ongoing_rebuild_percentage:.1f}%)")

                # SUPPLEMENTARY: Header metrics
                print(f"  • Header rebuild impact: {rebuild_impact:+.1f}% (ongoing delta: {ri.ongoing_rebuild_delta_percentage:+.1f}%, negligible)")
                print(f"  • Future changes will have similar build times")
            elif ri.ongoing_rebuild_delta_percentage < -5.0 or has_future_savings:
                print(f"{Colors.DIM}This change improves future build efficiency{Colors.RESET}\n")

                # BEFORE/AFTER comparison for coupling reduction (verbose mode)
                if verbose and (delta.coupling_decreased or delta.headers_removed):
                    print(f"{Colors.BRIGHT}{'─'*80}{Colors.RESET}")
                    print(f"{Colors.CYAN}FUTURE REBUILD REDUCTION (What Happens Next):{Colors.RESET}\n")

                    # Enhanced scenario description for interface extraction
                    if delta.headers_removed and delta.headers_added:
                        print(f"  {Colors.GREEN}Scenario:{Colors.RESET} Developer modifies implementation code (bug fix, optimization, logging)")
                        print(
                            f"  {Colors.DIM}Context: {len(delta.headers_removed)} headers refactored → {len(delta.headers_added)} new headers (interface extraction){Colors.RESET}"
                        )
                    else:
                        print(f"  {Colors.GREEN}Scenario:{Colors.RESET} Developer modifies implementation code (bug fix, optimization, logging)")
                    print()

                    # Collect headers to show: both reduced coupling and removed high-impact headers
                    headers_to_show = []

                    # Add headers with reduced coupling
                    for header, decrease in delta.coupling_decreased.items():
                        if header in baseline.metrics:
                            headers_to_show.append((header, baseline.metrics[header].fan_in, "reduced"))

                    # Add removed headers with high fan-in (likely refactored away)
                    for header in delta.headers_removed:
                        if header in baseline.metrics and baseline.metrics[header].fan_in > 2:
                            headers_to_show.append((header, baseline.metrics[header].fan_in, "removed"))

                    # Sort by fan-in and take top 5
                    headers_to_show.sort(key=lambda x: x[1], reverse=True)
                    headers_to_show = headers_to_show[:5]

                    if headers_to_show:
                        print(f"  {Colors.BRIGHT}BEFORE Refactoring:{Colors.RESET}")
                        baseline_total_fanin = 0
                        for header, fan_in, status in headers_to_show:
                            baseline_total_fanin += fan_in
                            rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else os.path.basename(header)
                            status_label = " (removed)" if status == "removed" else ""
                            print(f"    • Change {rel_path:40s} → {Colors.RED}{fan_in} dependent headers{Colors.RESET}{status_label}")
                        if baseline_total_fanin > 0:
                            print(f"    {Colors.DIM}Total blast radius: {baseline_total_fanin} dependent headers{Colors.RESET}")
                        print()

                        print(f"  {Colors.BRIGHT}AFTER Refactoring:{Colors.RESET}")
                        current_total_fanin = 0
                        isolated_implementations = []

                        for header, baseline_fan_in, status in headers_to_show:
                            if status == "removed":
                                # Find potential replacement headers (heuristic: similar base name)
                                base_name = os.path.basename(header).replace(".hpp", "").replace(".h", "")
                                replacements = []
                                for new_header in delta.headers_added:
                                    new_base = os.path.basename(new_header).replace(".hpp", "").replace(".h", "")
                                    if base_name.lower() in new_base.lower() or new_base.lower() in base_name.lower():
                                        if new_header in current.metrics:
                                            replacements.append((new_header, current.metrics[new_header].fan_in))

                                if replacements:
                                    # Sort by fan-in to show interface first, then implementation
                                    replacements.sort(key=lambda x: x[1], reverse=True)
                                    for repl_header, repl_fan_in in replacements:
                                        current_total_fanin += repl_fan_in
                                        rel_path = (
                                            os.path.relpath(repl_header, project_root)
                                            if repl_header.startswith(project_root)
                                            else os.path.basename(repl_header)
                                        )

                                        # Check if this is an isolated implementation (low fan-in)
                                        if repl_fan_in <= 1:
                                            isolated_implementations.append(rel_path)
                                            print(f"    • Change {rel_path:40s} → {Colors.GREEN}{repl_fan_in} dependent headers{Colors.RESET} (isolated! 🎯)")
                                        else:
                                            reduction_pct = int((baseline_fan_in - repl_fan_in) / baseline_fan_in * 100) if baseline_fan_in > 0 else 0
                                            print(
                                                f"    • Change {rel_path:40s} → {Colors.GREEN}{repl_fan_in} dependent headers{Colors.RESET} ({reduction_pct}% reduction)"
                                            )
                                else:
                                    # No clear replacement found
                                    print(f"    • {Colors.DIM}(header removed - dependencies eliminated){Colors.RESET}")
                            else:
                                # Header still exists with reduced coupling
                                if header in current.metrics:
                                    fan_in = current.metrics[header].fan_in
                                    current_total_fanin += fan_in
                                    rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else os.path.basename(header)
                                    reduction_pct = int((baseline_fan_in - fan_in) / baseline_fan_in * 100) if baseline_fan_in > 0 else 0
                                    print(f"    • Change {rel_path:40s} → {Colors.GREEN}{fan_in} dependent headers{Colors.RESET} ({reduction_pct}% reduction)")

                        if current_total_fanin >= 0:
                            print(f"    {Colors.DIM}Total blast radius: ~{current_total_fanin} dependent headers{Colors.RESET}")
                        print()

                        if baseline_total_fanin > 0 and current_total_fanin < baseline_total_fanin:
                            reduction_pct = int((baseline_total_fanin - current_total_fanin) / baseline_total_fanin * 100)
                            print(
                                f"  {Colors.BRIGHT}{Colors.GREEN}→ Future rebuild reduction: {reduction_pct}% fewer cascading header dependencies (and their .c/.cpp files){Colors.RESET}"
                            )

                        # Highlight isolated implementations
                        if isolated_implementations:
                            print(f"  {Colors.BRIGHT}{Colors.CYAN}→ Implementation isolation wins:{Colors.RESET}")
                            for impl in isolated_implementations:
                                print(f"    • {impl}: Changes have {Colors.GREEN}ZERO cascade effect{Colors.RESET} (volatile code isolated)")
                        print()

                print(f"{Colors.BRIGHT}{Colors.GREEN}Coupling Reduction Detected:{Colors.RESET}")
                print(f"  • {len(delta.coupling_decreased)} header(s) with reduced coupling")
                print(f"\n{Colors.BRIGHT}Ongoing Benefit (Every Future Change):{Colors.RESET}")

                # Show dual metrics
                if ri.total_source_files > 0:
                    print(
                        f"  • {Colors.GREEN}Future ongoing: {ri.future_ongoing_rebuild_count} of {ri.total_source_files} .c/.cpp files{Colors.RESET} per change ({ri.future_ongoing_rebuild_percentage:.1f}%)"
                    )
                    if ri.baseline_ongoing_rebuild_count > 0 and ri.baseline_ongoing_rebuild_count != ri.future_ongoing_rebuild_count:
                        files_saved = ri.baseline_ongoing_rebuild_count - ri.future_ongoing_rebuild_count
                        if files_saved > 0:
                            file_word = "file" if files_saved == 1 else "files"
                            print(
                                f"    {Colors.GREEN}({files_saved} {file_word} saved vs. baseline: {ri.baseline_ongoing_rebuild_count} → {ri.future_ongoing_rebuild_count}){Colors.RESET}"
                            )

                if ri.ripple_reduction:
                    total_reduction = sum(r[1] for r in ri.ripple_reduction)
                    print(f"  • {len(ri.ripple_reduction)} foundation headers improved (total coupling reduction: {total_reduction})")

                # ROI Analysis for coupling reduction
                # Three rebuild metrics:
                # - baseline_ongoing: Files that rebuild per commit in OLD architecture
                # - this_commit: Files that rebuild for THIS refactoring commit (one-time cost)
                # - future_ongoing: Files that rebuild per commit in NEW architecture
                # Ongoing savings = baseline_ongoing - future_ongoing (NOT this_commit - future_ongoing)
                if ri.total_source_files > 0:
                    print(f"\n{Colors.BRIGHT}{'─'*80}{Colors.RESET}")
                    print(f"{Colors.CYAN}ROI CALCULATION:{Colors.RESET}\n")

                    print(f"  {Colors.BRIGHT}One-Time Cost (Today):{Colors.RESET}")
                    print(
                        f"    • Refactoring commit: {ri.this_commit_rebuild_count} of {ri.total_source_files} .c/.cpp files must rebuild ({ri.this_commit_rebuild_percentage:.1f}%)"
                    )
                    estimated_time_min = int(ri.this_commit_rebuild_percentage / 100 * 10)  # ~10 min for full rebuild
                    print(f"    • Estimated time: ~{estimated_time_min} minutes for {ri.total_source_files}-file project")
                    print()

                    print(f"  {Colors.BRIGHT}Ongoing Savings (Every Future Commit):{Colors.RESET}")
                    files_saved = ri.baseline_ongoing_rebuild_count - ri.future_ongoing_rebuild_count
                    savings_pct = ri.baseline_ongoing_rebuild_percentage - ri.future_ongoing_rebuild_percentage
                    if files_saved > 0:
                        file_word = "file" if files_saved == 1 else "files"
                        print(f"    • Implementation changes: {files_saved} {file_word} saved ({savings_pct:.1f}% fewer files rebuild)")
                    print(
                        f"    • Future cost: {ri.future_ongoing_rebuild_count} of {ri.total_source_files} .c/.cpp files per change ({ri.future_ongoing_rebuild_percentage:.1f}%)"
                    )

                    # Estimate time savings
                    avg_saving_min = max(0, int(savings_pct / 100 * 2))  # ~2 min saved per incremental build
                    if avg_saving_min > 0:
                        team_size = 10
                        yearly_hours = int(avg_saving_min * team_size * 250 / 60)  # 250 working days
                        print(f"    • Average saving: ~{avg_saving_min} minutes per developer per day")
                        print(
                            f"    • Team of {team_size}: ~{avg_saving_min * team_size} minutes/day = {Colors.GREEN}~{yearly_hours} hours/year saved{Colors.RESET}"
                        )
                    print()

                    print(f"  {Colors.BRIGHT}Payback Period:{Colors.RESET}")
                    if ri.roi_payback_commits == 0:
                        print(f"    • Break-even: {Colors.GREEN}Immediate (zero-cost refactoring){Colors.RESET}")
                    elif ri.roi_payback_commits < 0:
                        print(f"    • Break-even: {Colors.RED}Negative ROI (increased ongoing cost){Colors.RESET}")
                    else:
                        # Color-coded based on payback period
                        if ri.roi_payback_commits < 5:
                            roi_color = Colors.GREEN
                        elif ri.roi_payback_commits <= 10:
                            roi_color = Colors.YELLOW
                        else:
                            roi_color = Colors.RED

                        print(
                            f"    • Break-even after: {roi_color}{int(ri.roi_payback_min)}-{int(ri.roi_payback_max)} commits to volatile headers{Colors.RESET}"
                        )
                    print()

                    print(f"{Colors.BRIGHT}{'─'*80}{Colors.RESET}")
                    print(f"{Colors.CYAN}KEY INSIGHT:{Colors.RESET}\n")
                    print(
                        f"  The DSM tool helps you understand {Colors.GREEN}future ongoing costs{Colors.RESET} (every commit: {ri.future_ongoing_rebuild_percentage:.1f}%)."
                    )
                    print(
                        f"  Today's one-time cost ({Colors.YELLOW}{ri.this_commit_rebuild_percentage:.1f}%{Colors.RESET}) is the investment to achieve future savings."
                    )
                    print()
                    if savings_pct > 0:
                        print(f"  {Colors.BRIGHT}Think of it like this:{Colors.RESET}")
                        print(f"    • Today: Pay {ri.this_commit_rebuild_percentage:.1f}% refactoring tax (one-time investment)")
                        print(f"    • Future: Save {savings_pct:.1f}% on every implementation change (ongoing benefit)")
                        print(f"    • Net effect: {Colors.GREEN}Massively positive ROI{Colors.RESET} after just {int(ri.roi_payback_commits)} commits")
                        print()
            else:
                print(f"{Colors.DIM}This change has moderate future build impact{Colors.RESET}\n")
                print(f"{Colors.BRIGHT}Impact Assessment:{Colors.RESET}")
                print(f"  • Rebuild impact: ~{rebuild_impact:.0f}% increase")
                print(f"  • Manageable overhead for future changes")
                if ri.high_impact_headers:
                    print(f"  • {len(ri.high_impact_headers)} header(s) with increased fan-in")

    # Headers added/removed
    if delta.headers_added or delta.headers_removed:
        print(f"\n{Colors.BRIGHT}Header Changes:{Colors.RESET}")

        if delta.headers_added:
            print_success(f"Added ({len(delta.headers_added)} headers):", prefix=False)
            print()
            for header in sorted(list(delta.headers_added)[:10]):
                rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                print(f"    + {rel_path}")
            if len(delta.headers_added) > 10:
                print(f"    ... and {len(delta.headers_added) - 10} more")

        if delta.headers_removed:
            print_error(f"Removed ({len(delta.headers_removed)} headers):", prefix=False)
            print()
            for header in sorted(list(delta.headers_removed)[:10]):
                rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                print(f"    - {rel_path}")
            if len(delta.headers_removed) > 10:
                print(f"    ... and {len(delta.headers_removed) - 10} more")

    # Cycle changes
    if delta.new_cycle_participants or delta.resolved_cycle_participants:
        print(f"\n{Colors.BRIGHT}Circular Dependency Changes:{Colors.RESET}")

        if delta.new_cycle_participants:
            print_error(f"⚠ New Cycle Participants ({len(delta.new_cycle_participants)} headers):", prefix=False)
            print()
            for header in sorted(list(delta.new_cycle_participants)[:10]):
                rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                print(f"    {rel_path}")
            if len(delta.new_cycle_participants) > 10:
                print(f"    ... and {len(delta.new_cycle_participants) - 10} more")

        if delta.resolved_cycle_participants:
            print_success(f"✓ Resolved Cycle Participants ({len(delta.resolved_cycle_participants)} headers):", prefix=False)
            print()
            for header in sorted(list(delta.resolved_cycle_participants)[:10]):
                rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                print(f"    {rel_path}")
            if len(delta.resolved_cycle_participants) > 10:
                print(f"    ... and {len(delta.resolved_cycle_participants) - 10} more")

    # Coupling changes
    if delta.coupling_increased or delta.coupling_decreased:
        print(f"\n{Colors.BRIGHT}Coupling Changes:{Colors.RESET}")

        if delta.coupling_increased:
            # Sort by magnitude of increase
            top_increases = sorted(delta.coupling_increased.items(), key=lambda x: x[1], reverse=True)[:10]
            print_warning(f"⚠ Increased Coupling ({len(delta.coupling_increased)} headers):", prefix=False)
            print()
            for header, increase in top_increases:
                rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                baseline_coupling = baseline.metrics[header].coupling
                current_coupling = current.metrics[header].coupling
                print(f"    {rel_path}")
                print(f"      {baseline_coupling} → {current_coupling} (+{increase})")

        if delta.coupling_decreased:
            # Sort by magnitude of decrease
            top_decreases = sorted(delta.coupling_decreased.items(), key=lambda x: x[1], reverse=True)[:10]
            print_success(f"✓ Decreased Coupling ({len(delta.coupling_decreased)} headers):", prefix=False)
            print()
            for header, decrease in top_decreases:
                rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                baseline_coupling = baseline.metrics[header].coupling
                current_coupling = current.metrics[header].coupling
                print(f"    {rel_path}")
                print(f"      {baseline_coupling} → {current_coupling} (-{decrease})")

    # NEW SECTION: Architectural Impact Analysis
    if delta.architectural_insights:
        insights = delta.architectural_insights

        # Regenerate recommendations with delta-awareness for change attribution
        insights.recommendations = generate_recommendations(
            insights.coupling_stats, insights.cycle_complexity, insights.stability_changes, insights.ripple_impact, current.cycles, current, delta
        )

        print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
        print(f"{Colors.BRIGHT}{Colors.CYAN}🔍 ARCHITECTURAL IMPACT ANALYSIS{Colors.RESET}")
        print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}\n")

        # Check for cycle changes - block positive interpretations if cycles added
        cycle_change = len(current.cycles) - len(baseline.cycles)
        has_cycle_regression = cycle_change > 0

        # STEP 1: CRITICAL BLOCKERS FIRST (Cycles with stop-sign visibility)
        if has_cycle_regression:
            print(f"{Colors.RED}{'='*80}{Colors.RESET}")
            print(f"{Colors.RED}🛑 CRITICAL BLOCKER: CIRCULAR DEPENDENCIES INTRODUCED{Colors.RESET}")
            print(f"{Colors.RED}{'='*80}{Colors.RESET}\n")
            print(f"  {Colors.BRIGHT}New cycles added:{Colors.RESET} {cycle_change}")
            print(f"  {Colors.BRIGHT}Total cycles now:{Colors.RESET} {len(current.cycles)}")
            print(f"\n{Colors.YELLOW}⚠  All metrics below are masked by this architectural regression.{Colors.RESET}")
            print(f"{Colors.YELLOW}⚠  Statistical improvements (coupling, layering) are irrelevant when cycles exist.{Colors.RESET}")
            print(f"{Colors.YELLOW}⚠  Cycles prevent proper architectural analysis and must be resolved FIRST.{Colors.RESET}\n")

        # STEP 2: SUMMARY SCORECARD (Red/Yellow/Green indicators upfront)
        print(f"{Colors.BRIGHT}{Colors.CYAN}📊 Architectural Health Scorecard{Colors.RESET}")
        print(f"{Colors.CYAN}{'─'*80}{Colors.RESET}")

        # Cycles indicator
        if has_cycle_regression:
            cycle_indicator = f"{Colors.RED}🔴 CRITICAL{Colors.RESET}"
            cycle_detail_color = Colors.RED
        elif len(current.cycles) > 0:
            cycle_indicator = f"{Colors.YELLOW}🟡 NEEDS ATTENTION{Colors.RESET}"
            cycle_detail_color = Colors.YELLOW
        else:
            cycle_indicator = f"{Colors.GREEN}🟢 HEALTHY{Colors.RESET}"
            cycle_detail_color = Colors.GREEN
        cycle_count_colored = f"{cycle_detail_color}{len(current.cycles)}{Colors.RESET}"
        cycle_change_colored = f"{cycle_detail_color}{cycle_change:+d}{Colors.RESET}" if cycle_change != 0 else f"{Colors.DIM}{cycle_change:+d}{Colors.RESET}"
        print(f"  {Colors.BRIGHT}Cycles:{Colors.RESET}              {cycle_indicator}  ({cycle_count_colored} cycles, {cycle_change_colored} from baseline)")

        # Coupling indicator
        cs = insights.coupling_stats
        if cs.mean_delta_pct > 10:
            coupling_indicator = f"{Colors.RED}🔴 DEGRADING{Colors.RESET}"
            coupling_detail_color = Colors.RED
        elif cs.mean_delta_pct > 0:
            coupling_indicator = f"{Colors.YELLOW}🟡 INCREASING{Colors.RESET}"
            coupling_detail_color = Colors.YELLOW
        elif cs.mean_delta_pct < -10:
            coupling_indicator = f"{Colors.GREEN}🟢 IMPROVING{Colors.RESET}"
            coupling_detail_color = Colors.GREEN
        else:
            coupling_indicator = f"{Colors.GREEN}🟢 STABLE{Colors.RESET}"
            coupling_detail_color = Colors.GREEN
        mean_pct_colored = f"{coupling_detail_color}{cs.mean_delta_pct:+.0f}%{Colors.RESET}"
        range_colored = f"{Colors.CYAN}{cs.min_current:.0f}-{cs.max_current:.0f}{Colors.RESET}"
        print(f"  {Colors.BRIGHT}Coupling:{Colors.RESET}            {coupling_indicator}  (μ {mean_pct_colored}, range: {range_colored})")

        # Stability indicator
        sc = insights.stability_changes
        if len(sc.became_unstable) > len(sc.became_stable):
            stability_indicator = f"{Colors.RED}🔴 DESTABILIZING{Colors.RESET}"
        elif len(sc.became_unstable) > 0:
            stability_indicator = f"{Colors.YELLOW}🟡 MIXED{Colors.RESET}"
        elif len(sc.became_stable) > 0:
            stability_indicator = f"{Colors.GREEN}🟢 STABILIZING{Colors.RESET}"
        else:
            stability_indicator = f"{Colors.GREEN}🟢 STABLE{Colors.RESET}"
        worse_colored = (
            f"{Colors.RED}{len(sc.became_unstable)}{Colors.RESET}" if len(sc.became_unstable) > 0 else f"{Colors.DIM}{len(sc.became_unstable)}{Colors.RESET}"
        )
        better_colored = (
            f"{Colors.GREEN}{len(sc.became_stable)}{Colors.RESET}" if len(sc.became_stable) > 0 else f"{Colors.DIM}{len(sc.became_stable)}{Colors.RESET}"
        )
        extreme_colored = (
            f"{Colors.YELLOW}{len(sc.extreme_instability)}{Colors.RESET}"
            if len(sc.extreme_instability) > 0
            else f"{Colors.DIM}{len(sc.extreme_instability)}{Colors.RESET}"
        )
        stability_summary = f"({worse_colored} worse, {better_colored} better, {extreme_colored} extreme)"
        print(f"  {Colors.BRIGHT}Stability:{Colors.RESET}           {stability_indicator}  {stability_summary}")

        # Layer depth indicator
        if insights.layer_depth_delta > 2:
            layer_indicator = f"{Colors.RED}🔴 DEEPENING{Colors.RESET}"
            layer_detail_color = Colors.RED
        elif insights.layer_depth_delta > 0:
            layer_indicator = f"{Colors.YELLOW}🟡 DEEPER{Colors.RESET}"
            layer_detail_color = Colors.YELLOW
        elif insights.layer_depth_delta < -2:
            layer_indicator = f"{Colors.GREEN}🟢 FLATTENING{Colors.RESET}"
            layer_detail_color = Colors.GREEN
        elif insights.layer_depth_delta < 0:
            layer_indicator = f"{Colors.GREEN}🟢 SHALLOWER{Colors.RESET}"
            layer_detail_color = Colors.GREEN
        else:
            layer_indicator = f"{Colors.GREEN}🟢 UNCHANGED{Colors.RESET}"
            layer_detail_color = Colors.DIM
        layer_delta_colored = f"{layer_detail_color}{insights.layer_depth_delta:+d}{Colors.RESET}"
        print(f"  {Colors.BRIGHT}Layer Depth:{Colors.RESET}         {layer_indicator}  ({layer_delta_colored} levels)")

        print(f"{Colors.CYAN}{'─'*80}{Colors.RESET}\n")

        # STEP 3: ACTIONABILITY ORDER - Cycles → Stability → Coupling → Layers

        # 3a. Cycle Complexity Analysis (if cycles exist)
        if insights.cycle_complexity:
            cc = insights.cycle_complexity
            print(f"{Colors.BRIGHT}1. Cycle Complexity Analysis{Colors.RESET}")
            print(f"   {Colors.DIM}(Top priority: break these cycles to enable proper architectural analysis){Colors.RESET}\n")

            print(f"  Avg cycle size: {cc.avg_cycle_size_baseline:.1f} → {cc.avg_cycle_size_current:.1f}")
            print(f"  Max cycle size: {cc.max_cycle_size_baseline} → {cc.max_cycle_size_current}")

            if cc.size_histogram:
                print(f"  Size distribution: {dict(sorted(cc.size_histogram.items())[:5])}")

            if cc.critical_breaking_edges:
                print(f"\n  {Colors.CYAN}🔧 Recommended Breaking Edges (by betweenness centrality):{Colors.RESET}")
                for (u, v), betweenness in cc.critical_breaking_edges[:3]:
                    u_short = os.path.basename(u)
                    v_short = os.path.basename(v)
                    print(f"    • {u_short} → {v_short} (impact: {betweenness:.3f})")
                print(f"      {Colors.DIM}→ Breaking these edges will resolve the most cycles{Colors.RESET}")
            print()

        # 3b. Stability Crossings (architectural hotspots)
        if sc.became_unstable or sc.became_stable or sc.extreme_instability:
            section_num = "2" if insights.cycle_complexity else "1"
            print(f"{Colors.BRIGHT}{section_num}. Stability Analysis{Colors.RESET}")
            print(f"   {Colors.DIM}(Headers crossing stability thresholds indicate architectural shifts){Colors.RESET}\n")

            if sc.became_unstable:
                print(f"  {Colors.RED}Became Unstable (crossed 0.5 threshold): {len(sc.became_unstable)} headers{Colors.RESET}")
                if verbose and sc.stability_details:
                    for header in list(sc.became_unstable)[:5]:
                        if header in sc.stability_details:
                            old_stab, new_stab = sc.stability_details[header]
                            rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else os.path.basename(header)
                            print(f"    • {rel_path}")
                            print(f"      {old_stab:.2f} → {new_stab:.2f} (Δ {new_stab - old_stab:+.2f})")

            if sc.became_stable:
                print(f"  {Colors.GREEN}Became Stable (crossed below 0.5): {len(sc.became_stable)} headers{Colors.RESET}")
                if verbose and sc.stability_details:
                    for header in list(sc.became_stable)[:5]:
                        if header in sc.stability_details:
                            old_stab, new_stab = sc.stability_details[header]
                            rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else os.path.basename(header)
                            print(f"    • {rel_path}")
                            print(f"      {old_stab:.2f} → {new_stab:.2f} (Δ {new_stab - old_stab:+.2f})")

            if sc.extreme_instability:
                print(f"  {Colors.YELLOW}Extreme Instability (>0.8): {len(sc.extreme_instability)} headers{Colors.RESET}")
                if verbose:
                    for header, stability in sc.extreme_instability[:5]:
                        rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else os.path.basename(header)
                        print(f"    • {rel_path} (stability: {stability:.2f})")
                print(f"      {Colors.DIM}→ These are architectural hotspots - volatile and widely depended upon{Colors.RESET}")
            print()

        # 3c. Coupling Distribution Analysis
        section_num = "3" if insights.cycle_complexity else ("2" if (sc.became_unstable or sc.became_stable or sc.extreme_instability) else "1")
        print(f"{Colors.BRIGHT}{section_num}. Coupling Distribution{Colors.RESET}")
        print(f"   {Colors.DIM}(Statistical analysis of dependency spread){Colors.RESET}\n")

        print(f"  μ (mean):     {cs.mean_baseline:.1f} → {cs.mean_current:.1f} ({cs.mean_delta_pct:+.0f}%)")
        print(f"  σ (stddev):   {cs.stddev_baseline:.1f} → {cs.stddev_current:.1f} ({cs.stddev_delta_pct:+.0f}%)")
        print(f"  Range:        [{cs.min_baseline:.0f}, {cs.max_baseline:.0f}] → [{cs.min_current:.0f}, {cs.max_current:.0f}]")
        print(
            f"  P95:          {cs.p95_baseline:.0f} → {cs.p95_current:.0f} ({((cs.p95_current - cs.p95_baseline) / cs.p95_baseline * 100) if cs.p95_baseline > 0 else 0:+.0f}%)"
        )
        print(
            f"  P99:          {cs.p99_baseline:.0f} → {cs.p99_current:.0f} ({((cs.p99_current - cs.p99_baseline) / cs.p99_baseline * 100) if cs.p99_baseline > 0 else 0:+.0f}%)"
        )

        # Outlier identification
        if cs.outliers_2sigma:
            print(f"\n  {Colors.RED}Extreme Outliers (>2σ): {len(cs.outliers_2sigma)} headers{Colors.RESET}")
            if verbose:
                for header, coupling in cs.outliers_2sigma[:5]:
                    rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else os.path.basename(header)
                    print(f"    • {rel_path} (coupling: {coupling:.0f})")

        if cs.outliers_1sigma and verbose:
            print(f"\n  {Colors.YELLOW}Outliers (>1σ): {len(cs.outliers_1sigma)} headers{Colors.RESET}")
            for header, coupling in cs.outliers_1sigma[:5]:
                rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else os.path.basename(header)
                print(f"    • {rel_path} (coupling: {coupling:.0f})")

        # Link to ripple analysis
        ri = insights.ripple_impact
        if cs.outliers_2sigma and ri.high_impact_headers:
            outlier_headers = {h for h, _ in cs.outliers_2sigma}
            high_impact_set = {h for h, _, _ in ri.high_impact_headers}
            overlap = outlier_headers & high_impact_set
            if overlap:
                print(f"\n  {Colors.CYAN}🔗 Cross-reference: {len(overlap)} extreme outliers are also high-impact in ripple analysis{Colors.RESET}")
        print()

        # 3d. Layer Movement Analysis
        if insights.layer_movement:
            section_num = str(int(section_num) + 1)
            lm = insights.layer_movement
            print(f"{Colors.BRIGHT}{section_num}. Layer Movement Analysis{Colors.RESET}")
            print(f"   {Colors.DIM}(Tracking architectural depth changes){Colors.RESET}\n")

            if insights.layer_depth_delta != 0:
                direction = "increased" if insights.layer_depth_delta > 0 else "decreased"
                color = Colors.YELLOW if insights.layer_depth_delta > 0 else Colors.GREEN
                print(f"  Max depth {direction} by {color}{abs(insights.layer_depth_delta)}{Colors.RESET} levels")

            print(f"  Headers moved deeper:    {len(lm.headers_moved_deeper)}")
            print(f"  Headers moved shallower: {len(lm.headers_moved_shallower)}")
            print(f"  Headers stayed same:     {lm.headers_stayed_same}")

            # Show headers that skipped multiple layers (architectural jumps)
            if lm.headers_skipped_layers:
                print(f"\n  {Colors.YELLOW}Architectural Jumps (>2 layers): {len(lm.headers_skipped_layers)} headers{Colors.RESET}")
                if verbose:
                    for header, old_layer, new_layer, skip_count in lm.headers_skipped_layers[:5]:
                        rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else os.path.basename(header)
                        direction = "deeper" if new_layer > old_layer else "shallower"
                        print(f"    • {rel_path}")
                        print(f"      Layer {old_layer} → {new_layer} ({skip_count} levels {direction})")
                print(f"      {Colors.DIM}→ Large layer jumps suggest significant dependency restructuring{Colors.RESET}")

            # Layer cohesion (headers per layer)
            if lm.layer_cohesion_current:
                avg_cohesion = sum(lm.layer_cohesion_current.values()) / len(lm.layer_cohesion_current)
                print(f"\n  Layer cohesion: {avg_cohesion:.1f} headers/layer (avg)")
                if verbose:
                    bloated_layers = [(layer, count) for layer, count in lm.layer_cohesion_current.items() if count > avg_cohesion * 1.5]
                    if bloated_layers:
                        print(f"  {Colors.YELLOW}Bloated layers:{Colors.RESET}")
                        for layer, count in sorted(bloated_layers, key=lambda x: x[1], reverse=True)[:3]:
                            print(f"    • Layer {layer}: {count} headers ({count / avg_cohesion:.1f}x average)")
            print()

        # Build Impact Assessment - ALWAYS SHOW (represents future ongoing architectural cost)
        section_num = str(int(section_num) + 1)
        print(f"{Colors.BRIGHT}{section_num}. Build Impact Assessment{Colors.RESET}")
        print(f"   {Colors.DIM}(Future ongoing impact - every subsequent commit to these headers){Colors.RESET}\n")

        # Precise impact analysis
        current_headers_count = len(current.sorted_headers) if current.sorted_headers else 1

        if ri.precise_score is not None:
            precise_pct = ri.precise_score / current_headers_count * 100

            # Show file count comparison if we have baseline and source file data
            if ri.total_source_files > 0 and ri.baseline_ongoing_rebuild_count > 0:
                # We have baseline - lead with improvement/regression prominently
                if ri.ongoing_rebuild_delta_percentage < -5.0:
                    # Improvement - lead with green success indicator
                    files_saved = ri.baseline_ongoing_rebuild_count - ri.future_ongoing_rebuild_count
                    print(
                        f"\n  {Colors.GREEN}{Colors.BRIGHT}✓ {abs(ri.ongoing_rebuild_delta_percentage):.1f}% FEWER FILES REBUILD{Colors.RESET} {Colors.GREEN}— {files_saved} files saved per future commit{Colors.RESET}"
                    )
                    print(
                        f"  {Colors.BRIGHT}Before:{Colors.RESET} {ri.baseline_ongoing_rebuild_count} files ({ri.baseline_ongoing_rebuild_percentage:.1f}%)  {Colors.GREEN}→{Colors.RESET}  {Colors.BRIGHT}After:{Colors.RESET} {ri.future_ongoing_rebuild_count} files ({ri.future_ongoing_rebuild_percentage:.1f}%)"
                    )
                    print(
                        f"  {Colors.DIM}Each future commit will trigger {files_saved} fewer files to rebuild (of {ri.total_source_files} total .c/.cpp files){Colors.RESET}"
                    )
                elif ri.ongoing_rebuild_delta_percentage > 5.0:
                    # Regression - lead with red warning indicator
                    files_added = ri.future_ongoing_rebuild_count - ri.baseline_ongoing_rebuild_count
                    print(
                        f"\n  {Colors.RED}{Colors.BRIGHT}⚠ {abs(ri.ongoing_rebuild_delta_percentage):.1f}% MORE FILES REBUILD{Colors.RESET} {Colors.RED}— {files_added} extra files per future commit{Colors.RESET}"
                    )
                    print(
                        f"  {Colors.BRIGHT}Before:{Colors.RESET} {ri.baseline_ongoing_rebuild_count} files ({ri.baseline_ongoing_rebuild_percentage:.1f}%)  {Colors.RED}→{Colors.RESET}  {Colors.BRIGHT}After:{Colors.RESET} {Colors.RED}{ri.future_ongoing_rebuild_count} files ({ri.future_ongoing_rebuild_percentage:.1f}%){Colors.RESET}"
                    )
                    print(
                        f"  {Colors.DIM}Each future commit will trigger {files_added} additional files to rebuild (of {ri.total_source_files} total .c/.cpp files){Colors.RESET}"
                    )
                else:
                    # Minimal change - show file counts prominently with clear improvement/regression
                    files_delta = ri.baseline_ongoing_rebuild_count - ri.future_ongoing_rebuild_count

                    print(
                        f"\n  {Colors.BRIGHT}Build Impact:{Colors.RESET} {Colors.BRIGHT}{ri.future_ongoing_rebuild_count} of {ri.total_source_files} .c/.cpp files{Colors.RESET} must rebuild ({ri.future_ongoing_rebuild_percentage:.1f}%)"
                    )

                    if files_delta > 0:
                        # Improvement - files saved
                        file_word = "file" if files_delta == 1 else "files"
                        print(
                            f"  {Colors.GREEN}Improvement:{Colors.RESET} {files_delta} {file_word} saved from rebuild vs. baseline ({ri.baseline_ongoing_rebuild_count} → {ri.future_ongoing_rebuild_count} files)"
                        )
                    elif files_delta < 0:
                        # Regression - more files rebuild
                        file_word = "file" if abs(files_delta) == 1 else "files"
                        print(
                            f"  {Colors.YELLOW}Regression:{Colors.RESET} {abs(files_delta)} more {file_word} must rebuild vs. baseline ({ri.baseline_ongoing_rebuild_count} → {ri.future_ongoing_rebuild_count} files)"
                        )
                    else:
                        # No change
                        print(f"  No change from baseline ({ri.baseline_ongoing_rebuild_count} → {ri.future_ongoing_rebuild_count} files, impact stable)")

                    print(f"  {Colors.DIM}- These {ri.future_ongoing_rebuild_count} files include (directly or transitively) modified headers{Colors.RESET}")
            elif ri.total_source_files > 0:
                # No baseline - just show current state with file counts prominently
                print(
                    f"\n  {Colors.BRIGHT}Precise:{Colors.RESET} {Colors.BRIGHT}{ri.future_ongoing_rebuild_count} of {ri.total_source_files} files{Colors.RESET} rebuild per future change ({ri.future_ongoing_rebuild_percentage:.1f}%)"
                )
                print(f"  Each commit to these headers triggers rebuilds for these files")
            else:
                # Fallback to header-based metric
                print(f"\n  {Colors.BRIGHT}Precise:{Colors.RESET} {precise_pct:.0f}% of downstream headers affected per future change")
                print(f"  Exact downstream headers affected: {ri.precise_score}")

            print(f"  Confidence: {ri.precise_confidence:.0f}% (exact transitive impact)")

        # Contextual clarification
        print(f"\n  {Colors.CYAN}💡 Context:{Colors.RESET}")
        print(f"  These metrics show the {Colors.BRIGHT}ongoing architectural cost{Colors.RESET} of coupling changes.")
        print(f"  Every future commit touching these headers will trigger the indicated rebuild percentage.")
        if ri.future_savings:
            print(f"  See 'Future Build Impact' section above for detailed source file rebuild metrics.")
        else:
            print(f"  This represents the incremental cost of maintaining high-coupling headers.")

        # High-impact headers (verbose mode with future-focused language)
        if verbose and ri.high_impact_headers:
            print(f"\n  {Colors.BRIGHT}Future Hotspots (High-Impact Headers):{Colors.RESET}")
            print(f"  {Colors.DIM}These headers will trigger widespread rebuilds of dependent headers and .c/.cpp files in future commits:{Colors.RESET}")
            for header, fan_in, coupling_delta in ri.high_impact_headers[:5]:
                rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                print(f"    • {rel_path}")
                print(f"      Fan-in: {fan_in}, Coupling Δ: +{coupling_delta}")
                print(f"      {Colors.YELLOW}→ Every change will cascade to {fan_in}+ downstream headers{Colors.RESET}")
        print()

        # STEP 4: UNIFIED KEY FINDINGS (consolidated interpretation with new vs pre-existing split)
        print(f"{Colors.BRIGHT}{'─'*80}{Colors.RESET}")
        print(f"{Colors.BRIGHT}🔑 Key Findings{Colors.RESET}")
        print(f"{Colors.BRIGHT}{'─'*80}{Colors.RESET}\n")

        # Severity banner
        if insights.severity == "critical":
            print(f"{Colors.RED}⚠ CRITICAL ARCHITECTURAL ISSUES DETECTED{Colors.RESET}\n")
        elif insights.severity == "moderate":
            print(f"{Colors.YELLOW}⚠ MODERATE ARCHITECTURAL CONCERNS{Colors.RESET}\n")
        else:
            print(f"{Colors.GREEN}✓ POSITIVE ARCHITECTURAL IMPROVEMENTS{Colors.RESET}\n")

        # Generate key findings split into categories
        introduced_findings: List[Tuple[str, str]] = []  # (severity_icon, finding)
        escalated_findings: List[Tuple[str, str]] = []  # (severity_icon, finding)
        pre_existing_findings: List[Tuple[str, str]] = []  # (severity_icon, finding)

        # INTRODUCED BY THIS CHANGE
        if has_cycle_regression:
            introduced_findings.append(("🔴", f"CRITICAL: {cycle_change} new circular dependencies block architectural progress"))

        if cs.mean_delta_pct > 10:
            introduced_findings.append(("🔴", f"Coupling mean increased {cs.mean_delta_pct:.0f}% - systemic architectural degradation"))
        elif cs.mean_delta_pct > 0:
            introduced_findings.append(("🟡", f"Coupling mean increased {cs.mean_delta_pct:.0f}% - monitor for continued growth"))
        elif cs.mean_delta_pct < -10:
            introduced_findings.append(("🟢", f"Coupling mean decreased {abs(cs.mean_delta_pct):.0f}% - significant architectural improvement"))

        # New coupling outliers (not pre-existing)
        new_outliers = [h for h, c in cs.outliers_2sigma if (h, c) not in delta.pre_existing_coupling_outliers]
        if new_outliers:
            introduced_findings.append(("🟡", f"{len(new_outliers)} new extreme coupling outliers (>2σ) introduced by this change"))

        # New unstable headers (not pre-existing)
        new_unstable = {h for h in sc.became_unstable if h not in delta.pre_existing_unstable_headers}
        if len(new_unstable) > 0:
            introduced_findings.append(("🟡", f"{len(new_unstable)} headers crossed into unstable territory (stability >0.5)"))

        if len(sc.extreme_instability) > 0:
            new_extreme = [h for h, s in sc.extreme_instability if h not in delta.pre_existing_unstable_headers]
            if len(new_extreme) > 0:
                introduced_findings.append(
                    (
                        "🔴" if len(new_extreme) > 5 else "🟡",
                        f"{len(new_extreme)} headers have new extreme instability (>0.8) - volatile architectural hotspots",
                    )
                )

        if insights.layer_depth_delta > 2:
            introduced_findings.append(("🟡", f"Layer depth increased by {insights.layer_depth_delta} levels - deeper dependency chains may slow builds"))
        elif insights.layer_depth_delta < -2:
            introduced_findings.append(("🟢", f"Layer depth decreased by {abs(insights.layer_depth_delta)} levels - flatter architecture improves parallelism"))

        if insights.layer_movement and len(insights.layer_movement.headers_skipped_layers) > 0:
            introduced_findings.append(
                ("🟡", f"{len(insights.layer_movement.headers_skipped_layers)} headers skipped multiple layers - significant restructuring")
            )

        if ri.high_impact_headers:
            top_count = min(3, len(ri.high_impact_headers))
            introduced_findings.append(("🟡", f"{top_count} high fan-in headers modified - future changes will cascade more widely"))

        # ESCALATED PRE-EXISTING CYCLES (your modified headers in existing cycles)
        if delta.escalated_cycle_headers:
            escalated_findings.append(
                (
                    "🔴",
                    f"Your modified headers ({', '.join(sorted([os.path.basename(h) for h in list(delta.escalated_cycle_headers)[:3]]))}{'...' if len(delta.escalated_cycle_headers) > 3 else ''}) "
                    f"are in existing cycles - resolve cycle before further changes",
                )
            )

        # PRE-EXISTING TECHNICAL DEBT (informational only)
        if delta.pre_existing_coupling_outliers:
            pre_existing_findings.append(
                ("⚪", f"{len(delta.pre_existing_coupling_outliers)} coupling outliers (>2σ) existed in baseline (not caused by this change)")
            )

        if delta.pre_existing_unstable_headers:
            pre_existing_findings.append(
                ("⚪", f"{len(delta.pre_existing_unstable_headers)} unstable headers (>0.5) existed in baseline (not caused by this change)")
            )

        if delta.pre_existing_cycle_headers and not delta.escalated_cycle_headers:
            pre_existing_findings.append(("⚪", f"{len(delta.pre_existing_cycle_headers)} headers in pre-existing cycles (not modified by this change)"))

        # Print findings by category
        if introduced_findings:
            print(f"{Colors.BRIGHT}Introduced by This Change:{Colors.RESET}")
            for icon, finding in introduced_findings:
                print(f"  {icon} {finding}")
            print()

        if escalated_findings:
            print(f"{Colors.BRIGHT}Your Modified Headers in Pre-existing Cycles:{Colors.RESET}")
            for icon, finding in escalated_findings:
                print(f"  {icon} {finding}")
            print()

        if pre_existing_findings:
            print(f"{Colors.DIM}Pre-existing Technical Debt (Informational):{Colors.RESET}")
            for icon, finding in pre_existing_findings:
                print(f"  {Colors.DIM}{icon} {finding}{Colors.RESET}")
            print()

        # If no findings in any category
        if not introduced_findings and not escalated_findings and not pre_existing_findings:
            print(f"  {Colors.GREEN}✓ No significant architectural issues detected{Colors.RESET}\n")

        # Cross-references between metrics
        if cs.outliers_2sigma and ri.high_impact_headers:
            outlier_headers = {h for h, _ in cs.outliers_2sigma}
            high_impact_set = {h for h, _, _ in ri.high_impact_headers}
            overlap = outlier_headers & high_impact_set
            if overlap:
                print(f"  {Colors.CYAN}🔗 {len(overlap)} headers are both coupling outliers AND high-impact - top priority for refactoring{Colors.RESET}\n")

        print(f"{Colors.BRIGHT}Recommendations:{Colors.RESET}")
        for recommendation in insights.recommendations:
            print(f"  {recommendation}")

        # Confidence footer
        print(f"\n{Colors.DIM}Analysis confidence: {insights.confidence_level.upper()}{Colors.RESET}")

    # Layer changes
    if delta.layer_changes:
        print(f"\n{Colors.BRIGHT}Layer Changes ({len(delta.layer_changes)} headers):{Colors.RESET}")

        # Sort by magnitude of layer change
        sorted_changes = sorted(delta.layer_changes.items(), key=lambda x: abs(x[1][1] - x[1][0]), reverse=True)[:15]

        for header, (old_layer, new_layer) in sorted_changes:
            rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
            delta_layer = new_layer - old_layer
            color = Colors.YELLOW if abs(delta_layer) > 2 else Colors.WHITE
            direction = "deeper" if delta_layer > 0 else "shallower"
            print(f"  {color}{rel_path}{Colors.RESET}")
            print(f"    Layer {old_layer} → {new_layer} ({abs(delta_layer)} levels {direction})")

    # Overall assessment
    print(f"\n{Colors.BRIGHT}Assessment:{Colors.RESET}")

    # Check for cycle churn first (both added and removed = instability)
    if delta.new_cycle_participants and delta.resolved_cycle_participants:
        print_warning(
            f"⚠ CYCLE CHURN: Circular dependencies both added ({len(delta.new_cycle_participants)}) "
            f"and removed ({len(delta.resolved_cycle_participants)}) - architectural instability",
            prefix=False,
        )
    elif delta.new_cycle_participants:
        print_error("⚠ REGRESSION: New circular dependencies introduced", prefix=False)
    elif delta.resolved_cycle_participants:
        print_success("✓ IMPROVEMENT: Circular dependencies resolved", prefix=False)

    if len(delta.coupling_increased) > len(delta.coupling_decreased):
        print_warning("⚠ Overall coupling increased", prefix=False)
    elif len(delta.coupling_decreased) > len(delta.coupling_increased):
        print_success("✓ Overall coupling decreased", prefix=False)

    if not delta.new_cycle_participants and not delta.coupling_increased:
        print_success("✓ No architectural regressions detected", prefix=False)


def display_directory_clusters(all_headers: List[str], header_to_headers: DefaultDict[str, Set[str]], project_root: str) -> None:
    """Display directory-based clustering analysis.

    Args:
        all_headers: List of all headers
        header_to_headers: Mapping of headers to their dependencies
        project_root: Project root directory for relative paths
    """
    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}MODULE ANALYSIS (by directory){Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")

    clusters = cluster_headers_by_directory(all_headers, project_root)

    # Calculate inter-module vs intra-module dependencies
    for module_name in sorted(clusters.keys()):
        module_headers = set(clusters[module_name])

        intra_deps = 0
        inter_deps = 0

        for header in module_headers:
            for dep in header_to_headers.get(header, set()):
                if dep in module_headers:
                    intra_deps += 1
                else:
                    inter_deps += 1

        total = intra_deps + inter_deps
        if total > 0:
            cohesion = 100.0 * intra_deps / total
            print(f"\n{Colors.CYAN}{module_name}:{Colors.RESET}")
            print(f"  Headers: {len(module_headers)}")
            print(f"  Internal dependencies: {intra_deps}")
            print(f"  External dependencies: {inter_deps}")
            print(f"  Cohesion: {cohesion:.1f}% (higher is better)")


def run_dsm_analysis(
    all_headers: Set[str],
    header_to_headers: DefaultDict[str, Set[str]],
    compute_layers: bool = True,
    show_progress: bool = True,
    source_to_deps: Optional[Dict[str, List[str]]] = None,
) -> DSMAnalysisResults:
    """Run all DSM analysis phases and return structured results.

    Args:
        all_headers: Set of headers to analyze
        header_to_headers: Mapping of headers to their dependencies
        compute_layers: Whether to compute dependency layers (can be skipped for cycles-only mode)
        show_progress: Whether to print progress messages
        source_to_deps: Optional mapping of source files (.c/.cpp) to header dependencies

    Returns:
        DSMAnalysisResults containing all analysis results
    """
    # Build reverse dependencies
    reverse_deps: Dict[str, Set[str]] = build_reverse_dependencies(header_to_headers, all_headers)

    # Calculate metrics for all headers
    if show_progress:
        print(f"{Colors.CYAN}Calculating dependency metrics...{Colors.RESET}")

    metrics: Dict[str, DSMMetrics] = {}
    for header in all_headers:
        metrics[header] = calculate_dsm_metrics(header, header_to_headers, reverse_deps)

    # Analyze cycles
    if show_progress:
        print(f"{Colors.CYAN}Analyzing circular dependencies...{Colors.RESET}")

    cycles: List[Set[str]]
    headers_in_cycles: Set[str]
    feedback_edges: List[Tuple[str, str]]
    directed_graph: Any
    self_loops: List[str]
    cycles, headers_in_cycles, feedback_edges, directed_graph, self_loops = analyze_cycles(header_to_headers, all_headers)

    # Compute layers if needed
    layers: List[List[str]] = []
    header_to_layer: Dict[str, int] = {}
    has_cycles: bool = len(cycles) > 0  # Detect multi-header cycles only

    if compute_layers:
        if show_progress:
            print(f"{Colors.CYAN}Computing dependency layers...{Colors.RESET}")
        layers, header_to_layer, has_cycles = compute_layer_structure(header_to_headers, all_headers)

    # Calculate matrix statistics with advanced metrics
    stats: MatrixStatistics = calculate_matrix_statistics(
        all_headers, header_to_headers, metrics=metrics, headers_in_cycles=headers_in_cycles, num_cycles=len(cycles)
    )

    # Sort headers by coupling for display
    sorted_headers: List[str] = sorted(all_headers, key=lambda h: metrics[h].coupling, reverse=True)

    return DSMAnalysisResults(
        metrics=metrics,
        cycles=cycles,
        headers_in_cycles=headers_in_cycles,
        feedback_edges=feedback_edges,
        directed_graph=directed_graph,
        layers=layers,
        header_to_layer=header_to_layer,
        has_cycles=has_cycles,
        stats=stats,
        sorted_headers=sorted_headers,
        reverse_deps=reverse_deps,
        header_to_headers=header_to_headers,
        source_to_deps=source_to_deps,
        self_loops=self_loops,
    )


def display_analysis_results(
    results: DSMAnalysisResults,
    project_root: str,
    header_to_lib: Dict[str, str],
    top_n: int,
    cycles_only: bool = False,
    show_layers: bool = False,
    show_library_boundaries: bool = False,
    cluster_by_directory: bool = False,
) -> None:
    """Display all analysis results based on configuration options.

    Args:
        results: DSM analysis results
        project_root: Project root directory for relative paths
        header_to_lib: Mapping of headers to libraries
        top_n: Number of headers to show in matrix (0 to disable)
        cycles_only: Show only circular dependency analysis
        show_layers: Show hierarchical layer structure
        show_library_boundaries: Show library boundary analysis
        cluster_by_directory: Group headers by directory in output
    """
    # Print summary statistics
    print_summary_statistics(results.stats, len(results.cycles), len(results.headers_in_cycles), results.layers, results.has_cycles)

    # Show matrix visualization (unless cycles-only mode or top_n is 0)
    if not cycles_only and top_n > 0:
        visualize_dsm(
            results.sorted_headers, results.header_to_headers, results.headers_in_cycles, project_root, top_n, CYCLE_HIGHLIGHT, DEPENDENCY_MARKER, EMPTY_CELL
        )

    # Circular Dependencies Analysis
    print_circular_dependencies(results.cycles, results.feedback_edges, project_root, cycles_only, results.self_loops)

    # Layered Architecture Analysis (auto-show if clean, or if explicitly requested)
    show_layers_flag: bool = bool(show_layers or (not results.cycles and results.layers and not cycles_only and len(results.layers) <= 20))
    auto_display: bool = not show_layers and show_layers_flag

    if show_layers_flag and results.layers:
        print_layered_architecture(results.layers, project_root, show_layers, auto_display)

    # High-Coupling Headers
    if not cycles_only:
        print_high_coupling_headers(results.sorted_headers, results.metrics, results.headers_in_cycles, project_root, 20, results.directed_graph)

    # Architectural Hotspots (Betweenness Centrality, Hub Nodes, God Objects)
    if not cycles_only:
        print_architectural_hotspots(results.directed_graph, results.metrics, project_root, top_n=15)

    # Library Boundary Analysis
    if show_library_boundaries and header_to_lib and not cycles_only:
        _display_library_boundary_analysis(results.header_to_headers, header_to_lib, project_root)

    # Directory clustering
    if cluster_by_directory and not cycles_only:
        display_directory_clusters(list(results.header_to_headers.keys()), results.header_to_headers, project_root)

    # Print recommendations
    print_recommendations(results.cycles, results.metrics, set(results.sorted_headers), results.stats, results.feedback_edges, results.layers, show_layers_flag)


def _display_library_boundary_analysis(header_to_headers: DefaultDict[str, Set[str]], header_to_lib: Dict[str, str], project_root: str) -> None:
    """Display library boundary analysis section.

    Args:
        header_to_headers: Mapping of headers to their dependencies
        header_to_lib: Mapping of headers to libraries
        project_root: Project root directory for relative paths
    """
    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}LIBRARY BOUNDARY ANALYSIS{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")

    cross_lib_stats = analyze_cross_library_dependencies(header_to_headers, header_to_lib)

    total: int = cross_lib_stats.total_deps
    intra: int = cross_lib_stats.intra_library_deps
    cross: int = cross_lib_stats.cross_library_deps

    if total > 0:
        intra_pct = (intra / total) * 100
        cross_pct = (cross / total) * 100

        print(f"\n{Colors.BRIGHT}Dependency Distribution:{Colors.RESET}")
        print(f"  Total dependencies: {total}")
        print(f"  Intra-library (within same library): {intra} ({intra_pct:.1f}%)")
        print(f"  Cross-library (between libraries): {cross} ({cross_pct:.1f}%)")

        if cross_pct > 50:
            print_warning("⚠ High cross-library coupling - consider refactoring", prefix=False)
        elif cross_pct > 30:
            print_warning("⚠ Moderate cross-library coupling", prefix=False)
        else:
            print_success("✓ Good library cohesion", prefix=False)

        # Show top library-to-library couplings
        lib_violations = cross_lib_stats.library_violations
        if lib_violations:
            print(f"\n{Colors.BRIGHT}Top Cross-Library Dependencies:{Colors.RESET}")
            print(f"{Colors.DIM}(Library A → Library B: count){Colors.RESET}\n")

            # Flatten and sort
            all_violations = []
            for from_lib, to_libs in lib_violations.items():
                for to_lib, count in to_libs.items():
                    all_violations.append((from_lib, to_lib, count))

            all_violations.sort(key=lambda x: x[2], reverse=True)

            for from_lib, to_lib, count in all_violations[:15]:
                color = Colors.RED if count > 50 else Colors.YELLOW if count > 20 else Colors.WHITE
                print(f"  {color}{from_lib} → {to_lib}: {count} dependencies{Colors.RESET}")

        # Show headers with most cross-library dependencies
        if cross_lib_stats.worst_offenders:
            print(f"\n{Colors.BRIGHT}Headers with Most Cross-Library Dependencies:{Colors.RESET}")
            print(f"{Colors.DIM}(These headers heavily couple different libraries){Colors.RESET}\n")

            for header, count in cross_lib_stats.worst_offenders[:10]:
                rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                lib_name = header_to_lib.get(header, "unknown")
                print(f"  {rel_path}")
                print(f"    Library: {lib_name} | Cross-library deps: {count}")


def run_differential_analysis(
    current_build_dir: str, baseline_build_dir: str, project_root: str, verbose: bool = False, include_system_headers: bool = False
) -> int:
    """Run differential DSM analysis comparing two builds.

    Args:
        current_build_dir: Path to current build directory
        baseline_build_dir: Path to baseline build directory
        project_root: Project root directory for relative path display
        verbose: Show detailed statistical breakdowns
        include_system_headers: Include system headers in analysis

    Returns:
        Exit code (0 for success, non-zero for errors)

    Raises:
        ValueError: If build directories are invalid
        RuntimeError: If analysis fails
    """
    # Validate baseline build directory
    try:
        validated_baseline_dir, _ = validate_build_directory_with_feedback(baseline_build_dir, verbose=False)
    except Exception as e:
        logger.error("Invalid baseline build directory: %s", e)
        print_error(f"Invalid baseline build directory: {baseline_build_dir}")
        print_warning("Please ensure the baseline build directory contains build.ninja", prefix=False)
        return EXIT_INVALID_ARGS

    # Validate current build directory
    try:
        validated_current_dir, _ = validate_build_directory_with_feedback(current_build_dir, verbose=False)
    except Exception as e:
        logger.error("Invalid current build directory: %s", e)
        print_error(f"Invalid current build directory: {current_build_dir}")
        print_warning("Please ensure the current build directory contains build.ninja", prefix=False)
        return EXIT_INVALID_ARGS

    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}DSM DIFFERENTIAL ANALYSIS{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}\n")
    print(f"{Colors.CYAN}Baseline: {validated_baseline_dir}{Colors.RESET}")
    print(f"{Colors.CYAN}Current:  {validated_current_dir}{Colors.RESET}\n")

    # Analyze baseline build
    print(f"{Colors.BRIGHT}Analyzing baseline build...{Colors.RESET}")
    try:
        baseline_scan = build_include_graph(validated_baseline_dir)
        baseline_headers = baseline_scan.all_headers
        print_success(f"Baseline: {len(baseline_headers)} headers in {baseline_scan.scan_time:.1f}s", prefix=False)
    except Exception as e:
        logger.error("Failed to analyze baseline build: %s", e)
        print_error(f"Failed to analyze baseline build: {e}")
        return EXIT_RUNTIME_ERROR

    # Analyze current build
    print(f"\n{Colors.BRIGHT}Analyzing current build...{Colors.RESET}")
    try:
        current_scan = build_include_graph(validated_current_dir)
        current_headers = current_scan.all_headers
        print_success(f"Current: {len(current_headers)} headers in {current_scan.scan_time:.1f}s", prefix=False)
    except Exception as e:
        logger.error("Failed to analyze current build: %s", e)
        print_error(f"Failed to analyze current build: {e}")
        return EXIT_RUNTIME_ERROR

    # Filter system headers if requested (for both baseline and current)
    if not include_system_headers:
        from .file_utils import filter_system_headers

        baseline_headers, _ = filter_system_headers(baseline_headers, show_progress=False)
        current_headers, _ = filter_system_headers(current_headers, show_progress=False)
        print(f"\n{Colors.DIM}System headers excluded from analysis{Colors.RESET}")

    # Run DSM analysis on both
    print(f"\n{Colors.BRIGHT}Computing DSM metrics...{Colors.RESET}")

    baseline_results = run_dsm_analysis(baseline_headers, baseline_scan.include_graph, compute_layers=True, show_progress=True)

    current_results = run_dsm_analysis(current_headers, current_scan.include_graph, compute_layers=True, show_progress=True)

    # Compute and display differences with architectural insights
    delta = compare_dsm_results(baseline_results, current_results)
    print_dsm_delta(delta, baseline_results, current_results, project_root, verbose=verbose)

    return EXIT_SUCCESS


def run_differential_analysis_with_baseline(
    current_results: DSMAnalysisResults, baseline_results: DSMAnalysisResults, project_root: str, compute_precise_impact: bool = False, verbose: bool = False
) -> int:
    """Run differential DSM analysis comparing current results with loaded baseline.

    This function accepts pre-loaded DSMAnalysisResults objects (e.g., from saved files)
    and performs comparison without re-scanning build directories.

    Args:
        current_results: Current DSM analysis results
        baseline_results: Baseline DSM analysis results (loaded from file)
        project_root: Project root directory for relative path display
        verbose: Show detailed statistical breakdowns

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}DSM DIFFERENTIAL ANALYSIS (WITH BASELINE){Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}\n")

    print(f"{Colors.CYAN}Baseline: {len(baseline_results.sorted_headers)} headers{Colors.RESET}")
    print(f"{Colors.CYAN}Current:  {len(current_results.sorted_headers)} headers{Colors.RESET}\n")

    # Compute and display differences with architectural insights
    delta = compare_dsm_results(baseline_results, current_results)
    print_dsm_delta(delta, baseline_results, current_results, project_root, verbose=verbose)

    return EXIT_SUCCESS


def run_git_working_tree_analysis(
    build_dir: str,
    project_root: str,
    git_from_ref: str = "HEAD",
    git_repo_path: Optional[str] = None,
    verbose: bool = False,
    filter_pattern: Optional[str] = None,
    exclude_patterns: Optional[List[str]] = None,
    show_layers: bool = False,
    include_system_headers: bool = False,
) -> int:
    """Run git working tree impact analysis using unified baseline comparison workflow.

    Analyzes architectural and rebuild impact of uncommitted changes in the working tree
    by reconstructing the baseline (HEAD) dependency graph and comparing it with the
    current working tree state. This uses the same sophisticated reporting as baseline
    analysis (interface extraction detection, ROI calculation, before/after scenarios).

    Args:
        build_dir: Path to ninja build directory (represents working tree state)
        project_root: Project root directory for relative path display
        git_from_ref: Git reference to compare against (default: HEAD)
        git_repo_path: Explicit git repository path (auto-detected if None)
        compute_precise_impact: Use precise transitive closure analysis (slower but accurate)
        verbose: Show detailed metrics for changed headers
        filter_pattern: Optional glob pattern to filter headers
        exclude_patterns: Optional list of glob patterns to exclude headers
        show_layers: Show layer information in output
        include_system_headers: Include system headers in analysis

    Returns:
        Exit code (0 for success, non-zero for errors)

    Raises:
        ValueError: If git repository not found or invalid reference
        RuntimeError: If analysis fails
    """
    from .file_utils import filter_headers_by_pattern, exclude_headers_by_patterns, filter_system_headers
    from .git_utils import reconstruct_head_graph, get_working_tree_changes_from_commit_batched

    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}GIT WORKING TREE IMPACT ANALYSIS{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}\n")

    # Step 1: Find git repository
    repo_dir: str
    if git_repo_path:
        repo_dir = git_repo_path
        if not os.path.isdir(repo_dir):
            print_error(f"Specified git repository not found: {repo_dir}")
            return EXIT_INVALID_ARGS
    else:
        # Auto-detect from build directory
        found_repo = find_git_repo(build_dir)
        if not found_repo:
            print_error("Git repository not found")
            print_warning("Please ensure you are in a git repository or use --git-repo to specify path", prefix=False)
            return EXIT_INVALID_ARGS
        repo_dir = found_repo

    print(f"{Colors.CYAN}Git repository: {repo_dir}{Colors.RESET}")
    print(f"{Colors.CYAN}Comparing against: {git_from_ref}{Colors.RESET}\n")

    # Step 2: Get changed files from git (with batching for large diffs)
    try:

        def progress_callback(current: int, total: int, message: str) -> None:
            print(f"  {message} ({current}/{total})")

        changed_files, description = get_working_tree_changes_from_commit_batched(
            base_ref=git_from_ref, repo_path=repo_dir, batch_size=100, progress_callback=progress_callback if verbose else None
        )
        print_success(f"Detected {len(changed_files)} changed files ({description})", prefix=False)
    except ValueError as e:
        print_error(f"Invalid git reference: {e}")
        return EXIT_INVALID_ARGS
    except RuntimeError as e:
        print_error(f"Git operation failed: {e}")
        return EXIT_RUNTIME_ERROR

    if not changed_files:
        print_success(f"\nNo changes detected - working tree is clean (matches {git_from_ref})", prefix=False)
        print(f"{Colors.DIM}Tip: To analyze the last commit's impact instead, use: --git-from HEAD~1{Colors.RESET}")
        return EXIT_SUCCESS

    # Step 3: Categorize changed files (headers vs sources)
    try:
        changed_headers, changed_sources = categorize_changed_files(changed_files)

        # Filter system headers from git changes if requested
        if not include_system_headers:
            changed_headers = [h for h in changed_headers if not is_system_header(h)]
            changed_sources = [s for s in changed_sources if not is_system_header(s)]

        print(f"  • {len(changed_headers)} headers changed")
        print(f"  • {len(changed_sources)} sources changed\n")
    except Exception as e:
        logger.error("Failed to categorize changed files: %s", e)
        print_error(f"Failed to categorize changed files: {e}")
        return EXIT_RUNTIME_ERROR

    if not changed_headers and not changed_sources:
        print_warning("No C/C++ headers or sources changed - nothing to analyze", prefix=False)
        return EXIT_SUCCESS

    # Step 4: Build dependency graph from working tree (CURRENT state)
    print(f"{Colors.BRIGHT}Building current state dependency graph (working tree)...{Colors.RESET}")
    try:
        scan_result = build_include_graph(build_dir)
        current_headers = scan_result.all_headers
        current_graph = scan_result.include_graph
        source_to_deps = scan_result.source_to_deps
        elapsed = scan_result.scan_time
        print_success(f"Built current graph with {len(current_headers)} headers in {elapsed:.1f}s", prefix=False)
    except Exception as e:
        logger.error("Failed to build include graph: %s", e)
        print_error(f"Failed to build dependency graph: {e}")
        return EXIT_RUNTIME_ERROR

    # Step 5: Reconstruct baseline graph from git history (BASELINE state)
    print(f"\n{Colors.BRIGHT}Reconstructing baseline state from {git_from_ref}...{Colors.RESET}")
    try:

        def baseline_progress(current: int, total: int, message: str) -> None:
            if total > 50:  # Only show progress for substantial operations
                print(f"  {message} ({current}/{total})")

        baseline_headers, baseline_graph = reconstruct_head_graph(
            working_tree_headers=current_headers,
            working_tree_graph=current_graph,
            base_ref=git_from_ref,
            repo_path=repo_dir,
            compile_commands_db=None,  # TODO: Pass actual compilation database
            project_root=project_root,
            progress_callback=baseline_progress if verbose else None,
        )
        print_success(f"Reconstructed baseline with {len(baseline_headers)} headers", prefix=False)
    except ValueError as e:
        print_error(f"Failed to reconstruct baseline: {e}")
        return EXIT_INVALID_ARGS
    except Exception as e:
        logger.error("Failed to reconstruct baseline graph: %s", e)
        print_error(f"Baseline reconstruction failed: {e}")
        return EXIT_RUNTIME_ERROR

    # Step 6: Apply filters to both baseline and current
    filtered_baseline_headers = baseline_headers.copy()
    filtered_current_headers = current_headers.copy()

    if not include_system_headers:
        filtered_baseline_headers, _ = filter_system_headers(filtered_baseline_headers, show_progress=False)
        filtered_current_headers, _ = filter_system_headers(filtered_current_headers, show_progress=False)

    if filter_pattern:
        filtered_baseline_headers = filter_headers_by_pattern(filtered_baseline_headers, filter_pattern, project_root)
        filtered_current_headers = filter_headers_by_pattern(filtered_current_headers, filter_pattern, project_root)
        print(f"Filtered to {len(filtered_current_headers)} current headers matching '{filter_pattern}'")

    if exclude_patterns:
        filtered_baseline_headers, _, _, _ = exclude_headers_by_patterns(filtered_baseline_headers, exclude_patterns, project_root)
        filtered_current_headers, excluded_count, _, _ = exclude_headers_by_patterns(filtered_current_headers, exclude_patterns, project_root)
        if excluded_count > 0:
            print(f"Excluded {excluded_count} headers from current")

    # Step 7: Run DSM analysis on both baseline and current
    print(f"\n{Colors.BRIGHT}Computing architectural metrics...{Colors.RESET}")

    print(f"  Analyzing baseline ({len(filtered_baseline_headers)} headers)...")
    baseline_results = run_dsm_analysis(
        filtered_baseline_headers,
        baseline_graph,
        compute_layers=show_layers or True,
        show_progress=False,
        source_to_deps=source_to_deps,  # Use same source mapping (from working tree)
    )

    print(f"  Analyzing current ({len(filtered_current_headers)} headers)...")
    current_results = run_dsm_analysis(
        filtered_current_headers, current_graph, compute_layers=show_layers or True, show_progress=False, source_to_deps=source_to_deps
    )
    print_success("Computed metrics for both baseline and current states", prefix=False)

    # Step 8: Compare baseline vs current (unified workflow)
    print(f"\n{Colors.BRIGHT}Computing impact delta (baseline → current)...{Colors.RESET}")
    delta = compare_dsm_results(baseline_results, current_results)
    print_success("Computed architectural impact delta", prefix=False)

    # Step 9: Display unified impact report (reuses sophisticated baseline reporting)
    print_dsm_delta(delta=delta, baseline=baseline_results, current=current_results, project_root=project_root, verbose=verbose)

    return EXIT_SUCCESS


def identify_improvement_candidates(results: DSMAnalysisResults, project_root: str) -> List["ImprovementCandidate"]:
    """Identify headers that are candidates for architectural improvement.

    Detects anti-patterns using existing sophisticated metrics:
    - God objects (fan-out >50)
    - Cycle participants (in circular dependencies)
    - Coupling outliers (z-score >2.5σ)
    - Unstable interfaces (stability >0.5, high fan-in)
    - Hub nodes (high betweenness centrality)

    Args:
        results: DSM analysis results
        project_root: Project root for relative paths

    Returns:
        List of ImprovementCandidate objects
    """
    candidates: List[ImprovementCandidate] = []
    metrics = results.metrics

    # Calculate statistical thresholds
    couplings = [m.coupling for m in metrics.values()]
    if not couplings:
        return candidates

    mean_coupling = float(np.mean(couplings))
    stddev_coupling = float(np.std(couplings, ddof=1)) if len(couplings) > 1 else 0
    outlier_threshold = mean_coupling + 2.5 * stddev_coupling if stddev_coupling > 0 else mean_coupling * 2

    # Calculate betweenness centrality for hub detection
    betweenness = nx.betweenness_centrality(results.directed_graph)
    sorted_betweenness = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)
    high_betweenness_threshold = sorted_betweenness[min(10, len(sorted_betweenness) - 1)][1] if sorted_betweenness else 0.0

    for header, metric in metrics.items():
        issues: List[str] = []
        steps: List[str] = []
        anti_patterns: List[str] = []
        affected: Set[str] = set()

        # Pattern 1: God Object Detection (fan-out >50)
        if metric.fan_out > 50:
            anti_patterns.append("god_object")
            issues.append(f"Includes {metric.fan_out} headers (god object pattern)")
            steps.append(f"Split into focused modules (target: <20 includes each)")
            steps.append(f"Extract common utilities to separate headers")
            affected = results.reverse_deps.get(header, set())

        # Pattern 2: Cycle Participant
        if header in results.headers_in_cycles:
            anti_patterns.append("cycle_participant")
            # Find which cycle(s) this header belongs to
            cycle_ids = [i for i, cycle in enumerate(results.cycles) if header in cycle]
            for cycle_id in cycle_ids:
                cycle_size = len(results.cycles[cycle_id])
                issues.append(f"Part of circular dependency group #{cycle_id + 1} ({cycle_size} headers)")
            steps.append("Break circular dependency by introducing interface layer")
            steps.append("Use forward declarations to reduce includes")
            affected.update(results.reverse_deps.get(header, set()))

        # Pattern 3: Coupling Outlier (>2.5σ)
        # Exclude stable foundation headers (stability ≈ 0.0, high fan-in, low fan-out)
        # These are architecturally correct - they're meant to be widely used base types
        is_foundation_header = metric.stability < 0.1 and metric.fan_in >= 30 and metric.fan_out <= 5
        if metric.coupling > outlier_threshold and not is_foundation_header:
            z_score = (metric.coupling - mean_coupling) / stddev_coupling if stddev_coupling > 0 else 0
            anti_patterns.append("coupling_outlier")
            issues.append(f"Coupling {metric.coupling} is {z_score:.1f}σ above mean ({mean_coupling:.1f})")
            steps.append(f"Reduce coupling by {int(metric.coupling - mean_coupling)} to reach mean")
            affected.update(results.reverse_deps.get(header, set()))

        # Pattern 4: Unstable Interface (stability >0.5, high fan-in)
        if metric.stability > 0.5 and metric.fan_in >= 10:
            anti_patterns.append("unstable_interface")
            issues.append(f"High instability ({metric.stability:.2f}) with {metric.fan_in} dependents")
            issues.append(f"Changes ripple to {metric.fan_in} headers")
            steps.append("Extract stable interface (reduce fan-out to <5)")
            steps.append("Move implementation details to separate .cpp or impl header")
            affected = results.reverse_deps.get(header, set())

        # Pattern 5: Hub Node (high betweenness centrality)
        header_betweenness = betweenness.get(header, 0.0)
        if header_betweenness >= high_betweenness_threshold and header_betweenness > 0.01:
            anti_patterns.append("hub_node")
            issues.append(f"Critical hub node (betweenness: {header_betweenness:.3f})")
            issues.append(f"Bottleneck in dependency graph")
            steps.append("Reduce centrality by extracting interfaces")
            steps.append("Consider breaking into multiple focused headers")
            affected.update(results.reverse_deps.get(header, set()))

        # Only create candidate if at least one anti-pattern detected
        if anti_patterns:
            # Create candidate (will be populated with estimates in next phase)
            candidate = ImprovementCandidate(
                header=header,
                anti_pattern=", ".join(sorted(set(anti_patterns))),
                current_metrics=metric,
                estimated_coupling_reduction=0,  # Will be computed by estimate_improvement_roi
                estimated_rebuild_reduction=0.0,
                effort_estimate="unknown",
                roi_score=0.0,
                break_even_commits=0.0,
                severity="unknown",
                specific_issues=issues,
                actionable_steps=steps,
                affected_headers=affected,
            )
            candidates.append(candidate)

    return candidates


def estimate_improvement_roi(
    candidate: "ImprovementCandidate", results: DSMAnalysisResults, source_to_deps: Optional[Dict[str, List[str]]] = None
) -> "ImprovementCandidate":
    """Estimate ROI for a refactoring candidate using precise transitive closure.

    Simulates refactoring scenarios:
    - Splitting god objects: Reduce fan-out by 60-80%
    - Breaking cycles: Remove feedback edges
    - Extracting interfaces: Reduce fan-out to <5
    - Isolating implementations: Reduce fan-in to 0-1

    Args:
        candidate: Improvement candidate to analyze
        results: DSM analysis results for context
        source_to_deps: Optional source-to-deps mapping for precise rebuild calculation

    Returns:
        Updated candidate with ROI estimates
    """
    header = candidate.header
    metric = candidate.current_metrics

    # Simulation parameters based on anti-pattern type
    fan_out_reduction = 0
    fan_in_reduction = 0

    if "god_object" in candidate.anti_pattern:
        # Split god object: reduce fan-out by 70%
        fan_out_reduction = int(metric.fan_out * 0.7)
        effort = "high"  # Significant refactoring
    elif "cycle_participant" in candidate.anti_pattern:
        # Break cycle: remove 2-3 key includes
        fan_out_reduction = min(3, max(1, metric.fan_out // 4))
        effort = "medium"
    elif "unstable_interface" in candidate.anti_pattern:
        # Extract interface: reduce fan-out to <5
        fan_out_reduction = max(0, metric.fan_out - 5)
        effort = "medium"
    elif "coupling_outlier" in candidate.anti_pattern:
        # Reduce coupling: bring to mean
        couplings = [m.coupling for m in results.metrics.values()]
        mean_coupling = float(np.mean(couplings)) if couplings else 0
        fan_out_reduction = max(0, int((metric.coupling - mean_coupling) * 0.6))
        effort = "medium"
    elif "hub_node" in candidate.anti_pattern:
        # Reduce centrality: split into 2-3 focused headers
        fan_out_reduction = int(metric.fan_out * 0.5)
        effort = "high"
    else:
        fan_out_reduction = int(metric.fan_out * 0.3)
        effort = "medium"

    # Estimate coupling reduction
    coupling_reduction = fan_out_reduction + fan_in_reduction
    candidate.estimated_coupling_reduction = coupling_reduction

    # Estimate rebuild impact reduction using precise transitive closure
    rebuild_reduction = 0.0
    if source_to_deps and metric.fan_in > 0:
        # Calculate current rebuild cascade
        affected_headers = compute_transitive_dependents(header, results.reverse_deps)
        current_rebuild = estimate_affected_sources(affected_headers, source_to_deps)

        # Simulate reduced cascade after refactoring
        # Assume interface extraction isolates implementation volatility
        if "unstable_interface" in candidate.anti_pattern or "god_object" in candidate.anti_pattern:
            # Interface pattern: reduces ongoing rebuild by ~60-80%
            simulated_rebuild = int(current_rebuild * 0.3)
        elif "cycle_participant" in candidate.anti_pattern:
            # Breaking cycles: reduces rebuild by ~30-50%
            simulated_rebuild = int(current_rebuild * 0.6)
        else:
            # General coupling reduction: ~20-40% improvement
            simulated_rebuild = int(current_rebuild * 0.7)

        total_sources = len(source_to_deps)
        if total_sources > 0:
            current_pct = (current_rebuild / total_sources) * 100
            simulated_pct = (simulated_rebuild / total_sources) * 100
            rebuild_reduction = current_pct - simulated_pct
    else:
        # Heuristic estimate based on fan-in and coupling reduction
        rebuild_reduction = (metric.fan_in * coupling_reduction) / max(1, len(results.metrics)) * 100
        rebuild_reduction = min(rebuild_reduction, 20.0)  # Cap heuristic at 20%

    candidate.estimated_rebuild_reduction = rebuild_reduction
    candidate.effort_estimate = effort

    # Calculate ROI score (0-100, higher is better)
    # Weighted: 40% cycle elimination, 30% rebuild reduction, 20% coupling decrease, 10% ease
    cycle_score = 40 if "cycle_participant" in candidate.anti_pattern else 0
    rebuild_score = min(30, rebuild_reduction * 1.5)  # 20% reduction = 30 points
    coupling_score = min(20, (coupling_reduction / max(1, metric.coupling)) * 20)  # Full reduction = 20 points
    ease_score = 10 if effort == "low" else (5 if effort == "medium" else 2)

    candidate.roi_score = cycle_score + rebuild_score + coupling_score + ease_score

    # Estimate break-even commits
    # High effort = 40 developer-hours, Medium = 20, Low = 5
    refactoring_cost = 40 if effort == "high" else (20 if effort == "medium" else 5)
    # Assume 2 hours saved per 1% rebuild reduction per 10 commits
    if rebuild_reduction > 0.1:
        hours_saved_per_10_commits = rebuild_reduction * 2
        commits_to_break_even = (refactoring_cost / hours_saved_per_10_commits) * 10
        candidate.break_even_commits = commits_to_break_even
    else:
        candidate.break_even_commits = 999  # No significant ongoing benefit

    # Assign severity based on ROI score and break-even
    if candidate.roi_score >= 60 and candidate.break_even_commits <= 5:
        candidate.severity = "quick_win"
    elif candidate.roi_score >= 40 or "cycle_participant" in candidate.anti_pattern:
        candidate.severity = "critical"
    else:
        candidate.severity = "moderate"

    return candidate


def compute_transitive_dependents(header: str, reverse_deps: Dict[str, Set[str]]) -> Set[str]:
    """Compute transitive closure of all headers that transitively depend on the given header.

    Args:
        header: Header to analyze
        reverse_deps: Reverse dependency mapping

    Returns:
        Set of all headers that transitively depend on the input header
    """
    visited: Set[str] = set()
    stack: List[str] = [header]

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)

        # Add all direct dependents
        dependents = reverse_deps.get(current, set())
        for dep in dependents:
            if dep not in visited:
                stack.append(dep)

    return visited


def estimate_affected_sources(affected_headers: Set[str], source_to_deps: Dict[str, List[str]]) -> int:
    """Estimate number of source files that would rebuild due to header changes.

    Args:
        affected_headers: Set of headers that are affected
        source_to_deps: Mapping of source files to their header dependencies

    Returns:
        Number of source files that would need recompilation
    """
    affected_sources = 0
    for source, deps in source_to_deps.items():
        if any(header in affected_headers for header in deps):
            affected_sources += 1
    return affected_sources


def rank_improvements_by_impact(candidates: List["ImprovementCandidate"]) -> List["ImprovementCandidate"]:
    """Rank improvement candidates by composite impact score.

    Sorting priority:
    1. Severity (quick_win > critical > moderate)
    2. ROI score (higher is better)
    3. Break-even commits (lower is better)

    Args:
        candidates: List of improvement candidates

    Returns:
        Sorted list (highest impact first)
    """
    severity_order = {"quick_win": 0, "critical": 1, "moderate": 2}

    return sorted(
        candidates,
        key=lambda c: (
            severity_order.get(c.severity, 3),  # Primary: severity
            -c.roi_score,  # Secondary: ROI (higher is better, so negate)
            c.break_even_commits,  # Tertiary: break-even (lower is better)
        ),
    )


def display_improvement_suggestions(
    candidates: List["ImprovementCandidate"], results: DSMAnalysisResults, project_root: str, top_n: int = 10, verbose: bool = False
) -> None:
    """Display ranked improvement suggestions with actionable recommendations.

    Args:
        candidates: Ranked improvement candidates
        results: DSM analysis results for context
        project_root: Project root for relative paths
        top_n: Number of top candidates to display
        verbose: Show detailed breakdown
    """
    if not candidates:
        print(f"\n{Colors.GREEN}✓ No significant architectural debt detected{Colors.RESET}")
        print(f"{Colors.DIM}Your codebase shows healthy coupling patterns and clean architecture{Colors.RESET}")
        return

    # Check for circular dependencies - these are blocking issues
    has_cycles = len(results.cycles) > 0
    cycle_participants = [c for c in candidates if "cycle_participant" in c.anti_pattern]

    # Summary statistics
    total_debt = sum(c.roi_score for c in candidates)
    quick_wins = [c for c in candidates if c.severity == "quick_win"]
    critical = [c for c in candidates if c.severity == "critical"]
    moderate = [c for c in candidates if c.severity == "moderate"]

    total_estimated_reduction = sum(c.estimated_rebuild_reduction for c in candidates)
    avg_break_even = float(np.mean([c.break_even_commits for c in candidates if c.break_even_commits < 900]))

    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}PROACTIVE ARCHITECTURAL IMPROVEMENT ANALYSIS{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}\n")

    # If cycles exist, show critical blocker message
    if has_cycles:
        print(f"{Colors.RED}{'='*80}{Colors.RESET}")
        print(f"{Colors.RED}⚠ CRITICAL BLOCKER: CIRCULAR DEPENDENCIES DETECTED{Colors.RESET}")
        print(f"{Colors.RED}{'='*80}{Colors.RESET}\n")
        print(f"{Colors.BRIGHT}Circular Dependencies:{Colors.RESET} {len(results.cycles)} cycle group(s)")
        print(f"{Colors.BRIGHT}Headers in Cycles:{Colors.RESET} {len(cycle_participants)} headers\n")
        print(f"{Colors.YELLOW}Why this blocks other improvements:{Colors.RESET}")
        print(f"  • Circular dependencies create architectural instability")
        print(f"  • Changes propagate indefinitely through cycles")
        print(f"  • Cannot establish proper dependency layers")
        print(f"  • Makes accurate impact analysis impossible")
        print(f"  • Other refactorings may worsen or hide the problem\n")
        print(f"{Colors.RED}PRIORITY:{Colors.RESET} Break all circular dependencies before other refactorings.\n")
        print(f"{Colors.BRIGHT}Cycle Participants to Fix:{Colors.RESET}\n")

        # Show only cycle participants
        for i, candidate in enumerate(cycle_participants, 1):
            rel_path = os.path.relpath(candidate.header, project_root) if project_root else candidate.header
            print(f"🔴 {Colors.BRIGHT}#{i}. {rel_path}{Colors.RESET}")
            print(f"   In cycle: Yes (part of {len([c for c in results.cycles if candidate.header in c])} cycle group(s))")
            print(f"   Current Metrics: fan-in={candidate.current_metrics.fan_in}, fan-out={candidate.current_metrics.fan_out}")

            if verbose:
                print(f"\n   {Colors.CYAN}Cycle Breaking Steps:{Colors.RESET}")
                for step in candidate.actionable_steps:
                    print(f"     → {step}")
            print()

        # Show recommended breaking edges if available
        if results.feedback_edges:
            print(f"\n{Colors.BRIGHT}Suggested Edges to Break (minimum set):{Colors.RESET}")
            for src, dst in results.feedback_edges[:5]:
                src_rel = os.path.relpath(src, project_root) if project_root else src
                dst_rel = os.path.relpath(dst, project_root) if project_root else dst
                print(f"  • {src_rel}")
                print(f"    → {dst_rel}")

        print(f"\n{Colors.YELLOW}After breaking cycles, re-run this analysis for other improvement opportunities.{Colors.RESET}")
        return

    # No cycles - proceed with normal recommendations
    print(f"{Colors.BRIGHT}Summary:{Colors.RESET}")
    print(f"  Total Improvement Candidates: {len(candidates)}")
    print(f"  🟢 Quick Wins (ROI ≥60, break-even ≤5 commits): {len(quick_wins)}")
    print(f"  🔴 Critical (cycles or ROI ≥40): {len(critical)}")
    print(f"  🟡 Moderate (ROI <40): {len(moderate)}")
    print(f"  Estimated Total .c/.cpp Rebuild Reduction: {total_estimated_reduction:.1f}%")
    print(f"  Average Break-Even Point: {avg_break_even:.0f} commits (when rebuild savings exceed refactoring cost)")

    # Architectural debt score (inverse of quality)
    couplings = [m.coupling for m in results.metrics.values()]
    mean_coupling = float(np.mean(couplings)) if couplings else 0
    cycle_penalty = len(results.cycles) * 10
    debt_score = min(100, mean_coupling + cycle_penalty)

    print(f"  Architectural Debt Score: {debt_score:.0f}/100 ", end="")
    if debt_score < 30:
        print(f"{Colors.GREEN}(Low){Colors.RESET}")
    elif debt_score < 60:
        print(f"{Colors.YELLOW}(Moderate){Colors.RESET}")
    else:
        print(f"{Colors.RED}(High){Colors.RESET}")

    # Display top N candidates
    display_count = min(top_n, len(candidates))
    print(f"\n{Colors.BRIGHT}Top {display_count} Improvement Opportunities:{Colors.RESET}\n")

    for i, candidate in enumerate(candidates[:display_count], 1):
        severity_icon = "🟢" if candidate.severity == "quick_win" else ("🔴" if candidate.severity == "critical" else "🟡")
        rel_path = os.path.relpath(candidate.header, project_root) if project_root else candidate.header

        print(f"{severity_icon} {Colors.BRIGHT}#{i}. {rel_path}{Colors.RESET}")
        print(f"   Anti-Pattern: {candidate.anti_pattern}")
        print(
            f"   Current Metrics: fan-in={candidate.current_metrics.fan_in}, "
            f"fan-out={candidate.current_metrics.fan_out}, coupling={candidate.current_metrics.coupling}, "
            f"stability={candidate.current_metrics.stability:.2f}"
        )
        print(f"   ROI Score: {candidate.roi_score:.1f}/100")
        print(
            f"   Estimated Impact: {candidate.estimated_coupling_reduction} coupling reduction, "
            f"{candidate.estimated_rebuild_reduction:.1f}% fewer .c/.cpp files rebuild"
        )
        print(f"   Effort: {candidate.effort_estimate.capitalize()}")
        print(f"   Break-Even: {candidate.break_even_commits:.0f} commits (until .c/.cpp rebuild savings cover refactoring cost)")

        if verbose:
            print(f"\n   {Colors.CYAN}Issues Detected:{Colors.RESET}")
            for issue in candidate.specific_issues:
                print(f"     • {issue}")

            print(f"\n   {Colors.CYAN}Actionable Steps:{Colors.RESET}")
            for step in candidate.actionable_steps:
                print(f"     → {step}")

            if candidate.affected_headers:
                print(f"\n   {Colors.DIM}Affects {len(candidate.affected_headers)} downstream headers{Colors.RESET}")

        print()

    # Overall recommendations
    print(f"{Colors.BRIGHT}Recommended Action Plan:{Colors.RESET}\n")

    step_num = 1

    if quick_wins:
        print(f"  {step_num}. {Colors.GREEN}START WITH QUICK WINS{Colors.RESET} ({len(quick_wins)} candidates)")
        print(f"     Low effort, high reward. Break-even in ≤5 commits.")
        for qw in quick_wins[:3]:
            rel_path = os.path.relpath(qw.header, project_root) if project_root else qw.header
            print(f"     • {rel_path}")
        step_num += 1

    if critical:
        print(f"\n  {step_num}. {Colors.RED}ADDRESS CRITICAL ISSUES{Colors.RESET} ({len(critical)} candidates)")
        print(f"     Focus on cycle elimination and high-impact refactorings.")
        cycles_in_critical = [c for c in critical if "cycle_participant" in c.anti_pattern]
        if cycles_in_critical:
            # Note: Only show this message if there are actual cycles in the analysis scope
            if results.cycles:
                print(f"     Priority: {len(cycles_in_critical)} headers in circular dependencies")
        step_num += 1

    if moderate:
        print(f"\n  {step_num}. {Colors.YELLOW}PLAN MODERATE REFACTORINGS{Colors.RESET} ({len(moderate)} candidates)")
        print(f"     Schedule for future iterations based on team capacity.")
        step_num += 1

    # Team impact estimation
    if avg_break_even < 100:
        commits_per_week = 20  # Assume ~4 commits/day * 5 days
        weeks_to_payback = avg_break_even / commits_per_week
        hours_saved_per_year = total_estimated_reduction * 2 * 52  # 2 hours per % per week

        print(f"\n  {Colors.BRIGHT}Team Impact Estimation:{Colors.RESET}")
        print(f"     Average payback time: {weeks_to_payback:.1f} weeks")
        print(f"     Estimated developer-hours saved/year: {hours_saved_per_year:.0f} hours")
        print(f"     Equivalent to: {hours_saved_per_year / 160:.1f} developer-months/year")


def run_proactive_improvement_analysis(
    build_dir: str,
    project_root: str,
    filter_pattern: Optional[str] = None,
    exclude_patterns: Optional[List[str]] = None,
    top_n: int = 10,
    verbose: bool = False,
    include_system_headers: bool = False,
) -> int:
    """Run proactive improvement analysis without requiring a baseline.

    Identifies high-impact refactoring opportunities using current codebase state:
    - God objects, cycles, coupling outliers
    - Unstable interfaces, hub nodes
    - ROI-ranked recommendations

    Args:
        build_dir: Build directory with compile_commands.json
        project_root: Project root for relative paths
        filter_pattern: Optional glob pattern to filter headers
        exclude_patterns: Optional list of glob patterns to exclude
        top_n: Number of top candidates to display
        verbose: Show detailed breakdown
        include_system_headers: Include system headers in analysis

    Returns:
        Exit code (0 for success)
    """
    from .file_utils import filter_headers_by_pattern, exclude_headers_by_patterns, filter_system_headers

    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}PROACTIVE ARCHITECTURAL IMPROVEMENT ANALYSIS{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}\n")

    # Important disclaimer about single-state analysis
    print(f"{Colors.YELLOW}{'━'*80}{Colors.RESET}")
    print(f"{Colors.YELLOW}⚠  IMPORTANT: SINGLE-STATE ANALYSIS (NO CHANGE ATTRIBUTION){Colors.RESET}")
    print(f"{Colors.YELLOW}{'━'*80}{Colors.RESET}")
    print(f"{Colors.YELLOW}This analysis examines the current codebase state without baseline comparison.{Colors.RESET}")
    print(f"{Colors.YELLOW}All findings reflect existing technical debt - NOT specifically caused by recent changes.{Colors.RESET}")
    print(f"{Colors.YELLOW}For change attribution (new vs pre-existing issues), use:{Colors.RESET}")
    print(f"  {Colors.CYAN}• --load-baseline <file>{Colors.RESET} to compare against a saved baseline")
    print(f"  {Colors.CYAN}• --git-impact{Colors.RESET} to analyze changes in your working tree")
    print(f"{Colors.YELLOW}{'━'*80}{Colors.RESET}\n")

    # Build dependency graph
    try:
        scan_result = build_include_graph(build_dir)
        header_to_headers = scan_result.include_graph
        all_headers = scan_result.all_headers
        source_to_deps = scan_result.source_to_deps
    except Exception as e:
        logger.error("Failed to build include graph: %s", e)
        print_error(f"Failed to build include graph: {e}")
        return EXIT_RUNTIME_ERROR

    print_success(f"Built directed include graph with {len(all_headers)} headers in {scan_result.scan_time:.1f}s", prefix=False)

    # Apply filters
    filtered_headers = all_headers

    if not include_system_headers:
        filtered_headers, _ = filter_system_headers(filtered_headers)

    if filter_pattern:
        filtered_headers = filter_headers_by_pattern(filtered_headers, filter_pattern, project_root)
        print(f"Filtered to {len(filtered_headers)} headers matching '{filter_pattern}'")

    if exclude_patterns:
        filtered_headers, excluded_count, _, _ = exclude_headers_by_patterns(filtered_headers, exclude_patterns, project_root)
        print(f"Excluded {excluded_count} headers")

    # Run DSM analysis
    print(f"\n{Colors.CYAN}Analyzing architectural patterns...{Colors.RESET}")
    results = run_dsm_analysis(filtered_headers, header_to_headers, compute_layers=True, show_progress=False, source_to_deps=source_to_deps)
    print_success(f"Analyzed {len(filtered_headers)} headers", prefix=False)

    # Identify improvement candidates
    print(f"\n{Colors.CYAN}Identifying improvement candidates...{Colors.RESET}")
    candidates = identify_improvement_candidates(results, project_root)
    print_success(f"Found {len(candidates)} candidates", prefix=False)

    if not candidates:
        print(f"\n{Colors.GREEN}✓ No significant architectural debt detected{Colors.RESET}")
        return EXIT_SUCCESS

    # Estimate ROI for each candidate (using precise analysis)
    print(f"\n{Colors.CYAN}Computing ROI estimates (precise transitive closure)...{Colors.RESET}")
    for i, candidate in enumerate(candidates, 1):
        if i % 10 == 0 or i == len(candidates):
            print(f"  Progress: {i}/{len(candidates)} candidates analyzed", end="\r")
        candidates[i - 1] = estimate_improvement_roi(candidate, results, source_to_deps)
    print()
    print_success(f"Completed ROI analysis for {len(candidates)} candidates", prefix=False)

    # Rank by impact
    ranked_candidates = rank_improvements_by_impact(candidates)

    # Display results
    display_improvement_suggestions(ranked_candidates, results, project_root, top_n=top_n, verbose=verbose)

    return EXIT_SUCCESS
