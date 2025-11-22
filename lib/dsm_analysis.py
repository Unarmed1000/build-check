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
"""DSM-specific analysis functions for buildCheckDSM.

This module provides helper functions for DSM analysis that can be tested independently
and reused across the codebase. Extracted from buildCheckDSM.py for better modularity.
"""

import os
import logging
from typing import Dict, Set, List, Tuple, Any, DefaultDict
from collections import defaultdict

import networkx as nx

from .color_utils import Colors, print_error, print_warning, print_success
from .constants import (
    HIGH_COUPLING_THRESHOLD,
    MODERATE_COUPLING_THRESHOLD,
    SPARSITY_HEALTHY,
    SPARSITY_MODERATE,
    MAX_HEADERS_DISPLAY,
    MAX_CYCLES_DISPLAY,
    EXIT_SUCCESS,
    EXIT_INVALID_ARGS,
    EXIT_RUNTIME_ERROR,
)
from .file_utils import cluster_headers_by_directory
from .dsm_types import MatrixStatistics, DSMAnalysisResults, DSMDelta
from .graph_utils import DSMMetrics

logger = logging.getLogger(__name__)

# Export types for mypy
__all__ = [
    'MatrixStatistics',
    'DSMAnalysisResults', 
    'DSMDelta',
    'calculate_matrix_statistics',
    'print_summary_statistics',
    'print_circular_dependencies',
    'print_layered_architecture',
    'print_high_coupling_headers',
    'print_recommendations',
    'display_directory_clusters',
    'compare_dsm_results',
    'print_dsm_delta',
    'run_dsm_analysis',
    'display_analysis_results',
    'run_differential_analysis',
    'run_differential_analysis_with_baseline',
]


def calculate_matrix_statistics(all_headers: Set[str], 
                                header_to_headers: Dict[str, Set[str]]) -> MatrixStatistics:
    """Calculate DSM matrix statistics.
    
    Args:
        all_headers: Set of all headers
        header_to_headers: Mapping of headers to their dependencies
        
    Returns:
        MatrixStatistics with total_headers, total_deps, sparsity, avg_deps, and health
    """
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
    
    return MatrixStatistics(
        total_headers=total_headers,
        total_actual_deps=total_actual_deps,
        total_possible_deps=total_possible_deps,
        sparsity=sparsity,
        avg_deps=avg_deps,
        health=health,
        health_color=health_color
    )


def print_summary_statistics(stats: MatrixStatistics, 
                            cycles_count: int, 
                            headers_in_cycles_count: int,
                            layers: List[List[str]],
                            has_cycles: bool) -> None:
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
    
    print(f"\n{Colors.BRIGHT}Structural Properties:{Colors.RESET}")
    print(f"  Circular dependency groups: {cycles_count}")
    print(f"  Headers in cycles: {headers_in_cycles_count}")
    
    if not has_cycles and layers:
        print(f"  Dependency layers: {len(layers)}")
        print(f"  Maximum dependency depth: {len(layers) - 1}")
    elif has_cycles:
        print_warning("Cannot compute layers: graph contains cycles", prefix=False)


def print_circular_dependencies(cycles: List[Set[str]], 
                               feedback_edges: List[Tuple[str, str]],
                               project_root: str,
                               cycles_only: bool = False) -> None:
    """Print circular dependencies analysis.
    
    Args:
        cycles: List of circular dependency groups
        feedback_edges: Edges to break to eliminate cycles
        project_root: Root directory for relative paths
        cycles_only: Whether we're in cycles-only mode
    """
    if not cycles and cycles_only:
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
        print(f"  The codebase has a clean, acyclic dependency structure.")


def print_layered_architecture(layers: List[List[str]], 
                               project_root: str,
                               show_layers: bool,
                               auto_display: bool = False) -> None:
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
    
    from .constants import MAX_LAYERS_DISPLAY
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


def print_high_coupling_headers(sorted_headers: List[str],
                               metrics: Dict[str, 'DSMMetrics'],
                               headers_in_cycles: Set[str],
                               project_root: str,
                               max_display: int = 20) -> None:
    """Print high-coupling headers analysis.
    
    Args:
        sorted_headers: Headers sorted by coupling (descending)
        metrics: Metrics dataclass for each header
        headers_in_cycles: Set of headers in cycles
        project_root: Root directory for relative paths
        max_display: Maximum headers to display
    """
    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}HIGH-COUPLING HEADERS{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    
    print(f"\n{Colors.BRIGHT}Top {min(max_display, len(sorted_headers))} headers by coupling:{Colors.RESET}")
    print(f"{Colors.DIM}(Coupling = Fan-in + Fan-out){Colors.RESET}\n")
    
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
        
        print(f"{color}{rel_path}{Colors.RESET}{cycle_marker}")
        print(f"  Fan-out: {m.fan_out} | Fan-in: {m.fan_in} | " +
              f"Coupling: {coupling} | Stability: {m.stability:.3f}")


def print_recommendations(cycles: List[Set[str]],
                         metrics: Dict[str, 'DSMMetrics'],
                         all_headers: Set[str],
                         stats: 'MatrixStatistics',
                         feedback_edges: List[Tuple[str, str]],
                         layers: List[List[str]],
                         show_layers: bool) -> None:
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
        print(f"  • Consider splitting, using forward declarations, or reducing dependencies")
        print()
        has_recommendations = True
    
    if stats.sparsity < SPARSITY_MODERATE:
        print_warning("Architecture note: Low sparsity indicates high coupling", prefix=False)
        print(f"  • Matrix sparsity: {stats.sparsity:.1f}%")
        print(f"  • Consider modularizing to reduce global coupling")
        print()
        has_recommendations = True
    
    if not cycles and layers:
        print_success("✓ Clean layered architecture detected", prefix=False)
        print(f"  • No circular dependencies")
        print(f"  • {len(layers)} clear dependency layers")
        print(f"  • Maximum depth: {len(layers) - 1}")
        if not show_layers:
            print(f"\n{Colors.DIM}Tip: Layers were automatically shown above. Use --show-layers to force display.{Colors.RESET}")
        has_recommendations = True
    elif not cycles:
        print_success("✓ No circular dependencies", prefix=False)
        print(f"  • Clean acyclic dependency structure")
        print(f"  • Good foundation for refactoring")
        has_recommendations = True
    
    if not has_recommendations:
        print_success("✓ No major issues detected", prefix=False)
        print(f"  • Architecture appears healthy")


def compare_dsm_results(
    baseline: DSMAnalysisResults,
    current: DSMAnalysisResults
) -> DSMDelta:
    """Compare two DSM analysis results and compute differences.
    
    Args:
        baseline: DSM analysis results from baseline build
        current: DSM analysis results from current build
        
    Returns:
        DSMDelta containing all differences between baseline and current
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
    )


def print_dsm_delta(
    delta: DSMDelta,
    baseline: DSMAnalysisResults,
    current: DSMAnalysisResults,
    project_root: str
) -> None:
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
    
    if delta.new_cycle_participants:
        print_error("⚠ REGRESSION: New circular dependencies introduced", prefix=False)
    elif delta.resolved_cycle_participants:
        print_success("✓ IMPROVEMENT: Circular dependencies resolved", prefix=False)
    
    if len(delta.coupling_increased) > len(delta.coupling_decreased):
        print_warning("⚠ Overall coupling increased", prefix=False)
    elif len(delta.coupling_decreased) > len(delta.coupling_increased):
        print_success("✓ Overall coupling decreased", prefix=False)
    
    if not delta.new_cycle_participants and not delta.coupling_increased:
        print_success("✓ No architectural regressions detected", prefix=False)


def display_directory_clusters(
    all_headers: List[str],
    header_to_headers: DefaultDict[str, Set[str]],
    project_root: str
) -> None:
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
    show_progress: bool = True
) -> DSMAnalysisResults:
    """Run all DSM analysis phases and return structured results.

    Args:
        all_headers: Set of headers to analyze
        header_to_headers: Mapping of headers to their dependencies
        compute_layers: Whether to compute dependency layers (can be skipped for cycles-only mode)
        show_progress: Whether to print progress messages

    Returns:
        DSMAnalysisResults containing all analysis results
    """
    from .graph_utils import (
        build_reverse_dependencies,
        calculate_dsm_metrics,
        analyze_cycles,
        compute_layers as compute_layer_structure,
        DSMMetrics,
    )
    
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
    cycles, headers_in_cycles, feedback_edges, directed_graph = analyze_cycles(header_to_headers, all_headers)

    # Compute layers if needed
    layers: List[List[str]] = []
    header_to_layer: Dict[str, int] = {}
    has_cycles: bool = len(cycles) > 0  # Detect cycles from cycle analysis

    if compute_layers:
        if show_progress:
            print(f"{Colors.CYAN}Computing dependency layers...{Colors.RESET}")
        layers, header_to_layer, has_cycles = compute_layer_structure(header_to_headers, all_headers)

    # Calculate matrix statistics
    stats: MatrixStatistics = calculate_matrix_statistics(all_headers, header_to_headers)

    # Sort headers by coupling for display
    sorted_headers: List[str] = sorted(
        all_headers,
        key=lambda h: metrics[h].coupling,
        reverse=True
    )

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
    )


def display_analysis_results(
    results: DSMAnalysisResults,
    project_root: str,
    header_to_lib: Dict[str, str],
    top_n: int,
    cycles_only: bool = False,
    show_layers: bool = False,
    show_library_boundaries: bool = False,
    cluster_by_directory: bool = False
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
    from .graph_utils import visualize_dsm
    from .library_parser import analyze_cross_library_dependencies
    from .constants import (
        CYCLE_HIGHLIGHT,
        DEPENDENCY_MARKER,
        EMPTY_CELL,
    )
    
    # Print summary statistics
    print_summary_statistics(
        results.stats,
        len(results.cycles),
        len(results.headers_in_cycles),
        results.layers,
        results.has_cycles
    )

    # Show matrix visualization (unless cycles-only mode or top_n is 0)
    if not cycles_only and top_n > 0:
        visualize_dsm(
            results.sorted_headers,
            results.header_to_headers,
            results.headers_in_cycles,
            project_root,
            top_n,
            CYCLE_HIGHLIGHT,
            DEPENDENCY_MARKER,
            EMPTY_CELL
        )

    # Circular Dependencies Analysis
    print_circular_dependencies(
        results.cycles,
        results.feedback_edges,
        project_root,
        cycles_only
    )

    # Layered Architecture Analysis (auto-show if clean, or if explicitly requested)
    show_layers_flag: bool = bool(
        show_layers or
        (not results.cycles and results.layers and not cycles_only and len(results.layers) <= 20)
    )
    auto_display: bool = not show_layers and show_layers_flag

    if show_layers_flag and results.layers:
        print_layered_architecture(
            results.layers,
            project_root,
            show_layers,
            auto_display
        )

    # High-Coupling Headers
    if not cycles_only:
        print_high_coupling_headers(
            results.sorted_headers,
            results.metrics,
            results.headers_in_cycles,
            project_root,
            20
        )

    # Library Boundary Analysis
    if show_library_boundaries and header_to_lib and not cycles_only:
        _display_library_boundary_analysis(
            results.header_to_headers,
            header_to_lib,
            project_root
        )

    # Directory clustering
    if cluster_by_directory and not cycles_only:
        display_directory_clusters(
            list(results.header_to_headers.keys()),
            results.header_to_headers,
            project_root
        )

    # Print recommendations
    print_recommendations(
        results.cycles,
        results.metrics,
        set(results.sorted_headers),
        results.stats,
        results.feedback_edges,
        results.layers,
        show_layers_flag
    )


def _display_library_boundary_analysis(
    header_to_headers: DefaultDict[str, Set[str]],
    header_to_lib: Dict[str, str],
    project_root: str
) -> None:
    """Display library boundary analysis section.

    Args:
        header_to_headers: Mapping of headers to their dependencies
        header_to_lib: Mapping of headers to libraries
        project_root: Project root directory for relative paths
    """
    from .library_parser import analyze_cross_library_dependencies
    
    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}LIBRARY BOUNDARY ANALYSIS{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")

    cross_lib_stats = analyze_cross_library_dependencies(
        header_to_headers,
        header_to_lib
    )

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
                lib_name = header_to_lib.get(header, 'unknown')
                print(f"  {rel_path}")
                print(f"    Library: {lib_name} | Cross-library deps: {count}")


def run_differential_analysis(
    current_build_dir: str,
    baseline_build_dir: str,
    project_root: str,
) -> int:
    """Run differential DSM analysis comparing two builds.
    
    Args:
        current_build_dir: Path to current build directory
        baseline_build_dir: Path to baseline build directory
        project_root: Project root directory for relative path display
        
    Returns:
        Exit code (0 for success, non-zero for errors)
        
    Raises:
        ValueError: If build directories are invalid
        RuntimeError: If analysis fails
    """
    from .ninja_utils import validate_build_directory_with_feedback
    from .clang_utils import build_include_graph
    
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
    
    # Run DSM analysis on both
    print(f"\n{Colors.BRIGHT}Computing DSM metrics...{Colors.RESET}")
    
    baseline_results = run_dsm_analysis(
        baseline_headers,
        baseline_scan.include_graph,
        compute_layers=True,
        show_progress=True
    )
    
    current_results = run_dsm_analysis(
        current_headers,
        current_scan.include_graph,
        compute_layers=True,
        show_progress=True
    )
    
    # Compute and display differences
    delta = compare_dsm_results(baseline_results, current_results)
    print_dsm_delta(delta, baseline_results, current_results, project_root)
    
    return EXIT_SUCCESS


def run_differential_analysis_with_baseline(
    current_results: DSMAnalysisResults,
    baseline_results: DSMAnalysisResults,
    project_root: str
) -> int:
    """Run differential DSM analysis comparing current results with loaded baseline.
    
    This function accepts pre-loaded DSMAnalysisResults objects (e.g., from saved files)
    and performs comparison without re-scanning build directories.
    
    Args:
        current_results: Current DSM analysis results
        baseline_results: Baseline DSM analysis results (loaded from file)
        project_root: Project root directory for relative path display
        
    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}DSM DIFFERENTIAL ANALYSIS (WITH BASELINE){Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}\n")
    
    print(f"{Colors.CYAN}Baseline: {len(baseline_results.sorted_headers)} headers{Colors.RESET}")
    print(f"{Colors.CYAN}Current:  {len(current_results.sorted_headers)} headers{Colors.RESET}\n")
    
    # Compute and display differences
    delta = compare_dsm_results(baseline_results, current_results)
    print_dsm_delta(delta, baseline_results, current_results, project_root)
    
    return EXIT_SUCCESS

