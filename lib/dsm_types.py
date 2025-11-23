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
"""Type definitions for DSM analysis.

This module contains dataclasses and type definitions used across DSM analysis modules.
"""

from typing import Dict, Set, List, Tuple, Any, DefaultDict, Optional
from dataclasses import dataclass, field

import networkx as nx
from .graph_utils import DSMMetrics


@dataclass
class MatrixStatistics:
    """DSM matrix statistics.

    Attributes:
        total_headers: Total number of headers in the matrix
        total_actual_deps: Total number of actual dependencies
        total_possible_deps: Maximum possible dependencies
        sparsity: Percentage of missing dependencies (0-100)
        avg_deps: Average dependencies per header
        health: Health description string
        health_color: Color code for health display
        quality_score: Architecture quality score (0-100)
        adp_score: Acyclic Dependencies Principle compliance (0-100)
        interface_ratio: Percentage of stable interface headers (0-100)
    """

    total_headers: int
    total_actual_deps: int
    total_possible_deps: int
    sparsity: float
    avg_deps: float
    health: str
    health_color: str
    quality_score: float = 0.0
    adp_score: float = 0.0
    interface_ratio: float = 0.0


@dataclass
class DSMAnalysisResults:
    """Container for DSM analysis results.

    Attributes:
        metrics: Per-header metrics (fan-in, fan-out, coupling, stability)
        cycles: List of circular dependency groups (multi-header cycles only)
        headers_in_cycles: Set of headers that are part of multi-header cycles
        feedback_edges: Edges that should be removed to break cycles
        directed_graph: NetworkX directed graph of dependencies
        layers: Dependency layers (topological ordering)
        header_to_layer: Mapping of headers to their layer number
        has_cycles: Whether the graph contains multi-header cycles
        stats: Matrix statistics (sparsity, coupling, etc.)
        sorted_headers: Headers sorted by coupling (descending)
        reverse_deps: Reverse dependency mapping
        header_to_headers: Forward dependency mapping
        source_to_deps: Optional mapping of source files to header dependencies
        self_loops: List of headers that include themselves (not true cycles)
    """

    metrics: Dict[str, "DSMMetrics"]
    cycles: List[Set[str]]
    headers_in_cycles: Set[str]
    feedback_edges: List[Tuple[str, str]]
    directed_graph: "nx.DiGraph[Any]"  # NetworkX DiGraph (required dependency)
    layers: List[List[str]]
    header_to_layer: Dict[str, int]
    has_cycles: bool
    stats: "MatrixStatistics"
    sorted_headers: List[str]
    reverse_deps: Dict[str, Set[str]]
    header_to_headers: DefaultDict[str, Set[str]]
    source_to_deps: Optional[Dict[str, List[str]]] = None
    self_loops: List[str] = field(default_factory=list)


@dataclass
class DSMDelta:
    """Differences between two DSM analysis results.

    Attributes:
        headers_added: Headers present in current but not baseline
        headers_removed: Headers present in baseline but not current
        cycles_added: Number of new cycles introduced
        cycles_removed: Number of cycles eliminated
        coupling_increased: Headers with increased coupling (header -> delta)
        coupling_decreased: Headers with decreased coupling (header -> delta)
        layer_changes: Headers that moved layers (header -> (old_layer, new_layer))
        new_cycle_participants: Headers newly involved in cycles
        resolved_cycle_participants: Headers no longer in cycles
    """

    headers_added: Set[str]
    headers_removed: Set[str]
    cycles_added: int
    cycles_removed: int
    coupling_increased: Dict[str, int]
    coupling_decreased: Dict[str, int]
    layer_changes: Dict[str, Tuple[int, int]]
    new_cycle_participants: Set[str]
    resolved_cycle_participants: Set[str]
    architectural_insights: Optional["ArchitecturalInsights"] = None


@dataclass
class CouplingStatistics:
    """Statistical analysis of coupling distribution.

    Attributes:
        mean_baseline: Mean coupling in baseline
        mean_current: Mean coupling in current
        median_baseline: Median coupling in baseline
        median_current: Median coupling in current
        stddev_baseline: Standard deviation in baseline
        stddev_current: Standard deviation in current
        p95_baseline: 95th percentile in baseline
        p95_current: 95th percentile in current
        p99_baseline: 99th percentile in baseline
        p99_current: 99th percentile in current
        mean_delta_pct: Percentage change in mean
        stddev_delta_pct: Percentage change in std deviation
        outliers_baseline: Headers >1σ from mean in baseline
        outliers_current: Headers >1σ from mean in current
        min_baseline: Minimum coupling in baseline
        min_current: Minimum coupling in current
        max_baseline: Maximum coupling in baseline
        max_current: Maximum coupling in current
        outliers_1sigma: List[Tuple[str, float]]  # (header, coupling) for >1σ outliers
        outliers_2sigma: List[Tuple[str, float]]  # (header, coupling) for >2σ outliers
    """

    mean_baseline: float
    mean_current: float
    median_baseline: float
    median_current: float
    stddev_baseline: float
    stddev_current: float
    p95_baseline: float
    p95_current: float
    p99_baseline: float
    p99_current: float
    mean_delta_pct: float
    stddev_delta_pct: float
    outliers_baseline: Set[str]
    outliers_current: Set[str]
    min_baseline: float = 0.0
    min_current: float = 0.0
    max_baseline: float = 0.0
    max_current: float = 0.0
    outliers_1sigma: List[Tuple[str, float]] = field(default_factory=list)
    outliers_2sigma: List[Tuple[str, float]] = field(default_factory=list)


@dataclass
class CycleComplexityStats:
    """Cycle complexity analysis.

    Attributes:
        size_histogram: Distribution of cycle sizes (size → count)
        avg_cycle_size_baseline: Average cycle size in baseline
        avg_cycle_size_current: Average cycle size in current
        max_cycle_size_baseline: Largest cycle in baseline
        max_cycle_size_current: Largest cycle in current
        edge_density_per_cycle: Edges per cycle (cycle_id → density)
        critical_breaking_edges: Top edges by betweenness centrality
    """

    size_histogram: Dict[int, int]
    avg_cycle_size_baseline: float
    avg_cycle_size_current: float
    max_cycle_size_baseline: int
    max_cycle_size_current: int
    edge_density_per_cycle: Dict[int, float]
    critical_breaking_edges: List[Tuple[Tuple[str, str], float]]  # (edge, betweenness)


@dataclass
class StabilityChange:
    """Stability threshold crossing tracking.

    Attributes:
        became_unstable: Headers that crossed into unstable territory (stability > 0.5)
        became_stable: Headers that became more stable (stability <= 0.5)
        high_instability: Headers with stability > 0.8
        stability_details: Dict mapping header → (baseline_stability, current_stability)
        extreme_instability: List of headers with instability > 0.8 and their values
    """

    became_unstable: Set[str]
    became_stable: Set[str]
    high_instability: Set[str]
    stability_details: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    extreme_instability: List[Tuple[str, float]] = field(default_factory=list)


@dataclass
class RippleImpactAnalysis:
    """Build impact assessment with heuristic and optional precise analysis.

    Attributes:
        heuristic_score: Fast approximation (sum of fan_in × coupling_delta)
        heuristic_confidence: Confidence level for heuristic (±percentage)
        precise_score: Optional precise transitive closure count
        precise_confidence: Confidence level for precise (percentage)
        high_impact_headers: Headers with largest ripple effect
        ripple_reduction: Headers whose changes reduce future ripples
        affected_file_estimate: Estimated number of files affected by changes
        total_downstream_impact: Option 2A - Sum of all fan-ins (can exceed 100%)
        unique_downstream_count: Option 2B - Count of unique downstream headers (0-100%)
        this_commit_rebuild_count: Number of .c/.cpp files requiring rebuild (this commit only, transitive)
        this_commit_rebuild_percentage: Percentage of source files affected (this commit, one-time cost)
        future_ongoing_rebuild_count: Number of .c/.cpp files affected by ongoing changes (volatility-weighted)
        future_ongoing_rebuild_percentage: Percentage of source files affected (future commits, ongoing cost)
        total_source_files: Total number of .c/.cpp files in project
        roi_payback_commits: Number of commits until break-even (-1=negative ROI, 0=zero-cost)
        roi_payback_min: Minimum commits in confidence interval
        roi_payback_max: Maximum commits in confidence interval
        future_savings: Optional prediction of future rebuild reduction
    """

    heuristic_score: float
    heuristic_confidence: float
    precise_score: Optional[int]
    precise_confidence: Optional[float]
    high_impact_headers: List[Tuple[str, int, int]]  # (header, fan_in, coupling_delta)
    ripple_reduction: List[Tuple[str, int]]  # (header, reduction_estimate)
    affected_file_estimate: int
    total_downstream_impact: int  # Option 2A: Sum of fan-ins (average blast radius)
    unique_downstream_count: int  # Option 2B: Unique downstream headers (precise %)
    this_commit_rebuild_count: int = 0  # Number of .c/.cpp files needing rebuild (this commit only)
    this_commit_rebuild_percentage: float = 0.0  # Percentage of source files affected (this commit)
    future_ongoing_rebuild_count: int = 0  # Number of .c/.cpp files affected by future changes
    future_ongoing_rebuild_percentage: float = 0.0  # Percentage of source files affected (future)
    baseline_ongoing_rebuild_count: int = 0  # Number of .c/.cpp files that WOULD rebuild in baseline (for comparison)
    baseline_ongoing_rebuild_percentage: float = 0.0  # Percentage of source files in baseline (for comparison)
    ongoing_rebuild_delta_percentage: float = 0.0  # Delta between baseline and current ongoing cost (negative=improvement)
    total_source_files: int = 0  # Total .c/.cpp files in project
    roi_payback_commits: float = 0.0  # Commits until break-even (-1=negative, 0=zero-cost)
    roi_payback_min: float = 0.0  # Minimum commits in confidence interval
    roi_payback_max: float = 0.0  # Maximum commits in confidence interval
    future_savings: Optional["FutureRebuildPrediction"] = None


@dataclass
class FutureRebuildPrediction:
    """Prediction of future rebuild impact after refactoring.

    Attributes:
        baseline_volatile_fanin: Total fan-in of volatile headers before refactoring
        current_volatile_fanin: Total fan-in of volatile headers after refactoring
        reduction_percentage: Percentage reduction in future rebuild cascades
        interface_headers: Number of stable interface headers created
        isolated_impl_headers: Number of implementation headers isolated (zero dependents)
        description: Human-readable description of the savings
    """

    baseline_volatile_fanin: int
    current_volatile_fanin: int
    reduction_percentage: int
    interface_headers: int
    isolated_impl_headers: int
    description: str


@dataclass
class LayerMovementStats:
    """Statistics about layer movement between baseline and current.

    Attributes:
        headers_moved_deeper: List of (header, old_layer, new_layer) moved to deeper layers
        headers_moved_shallower: List of (header, old_layer, new_layer) moved to shallower layers
        headers_skipped_layers: List of (header, old_layer, new_layer, skip_count) that skipped multiple layers
        layer_cohesion_baseline: Dict mapping layer → count of headers in baseline
        layer_cohesion_current: Dict mapping layer → count of headers in current
        headers_stayed_same: Number of headers that remained in the same layer
    """

    headers_moved_deeper: List[Tuple[str, int, int]]
    headers_moved_shallower: List[Tuple[str, int, int]]
    headers_skipped_layers: List[Tuple[str, int, int, int]]
    layer_cohesion_baseline: Dict[int, int]
    layer_cohesion_current: Dict[int, int]
    headers_stayed_same: int = 0


@dataclass
class ArchitecturalInsights:
    """Comprehensive architectural change analysis.

    Attributes:
        coupling_stats: Coupling distribution statistics
        cycle_complexity: Cycle complexity analysis
        stability_changes: Stability threshold crossings
        ripple_impact: Build impact assessment
        layer_depth_delta: Change in maximum layer depth
        layer_movement: Statistics about layer movement between baseline and current
        confidence_level: Overall confidence in analysis (high/medium/low)
        severity: Overall severity (critical/moderate/positive)
        recommendations: Actionable recommendations list
    """

    coupling_stats: CouplingStatistics
    cycle_complexity: Optional[CycleComplexityStats]
    stability_changes: StabilityChange
    ripple_impact: RippleImpactAnalysis
    layer_depth_delta: int
    layer_movement: Optional[LayerMovementStats]
    confidence_level: str
    severity: str
    recommendations: List[str]


@dataclass
class ImprovementCandidate:
    """Candidate for architectural improvement.

    Attributes:
        header: Path to the header file
        anti_pattern: Type of anti-pattern detected (god_object, cycle_participant, outlier, unstable_interface, hub_node)
        current_metrics: Current DSMMetrics for the header
        estimated_coupling_reduction: Estimated reduction in coupling after refactoring
        estimated_rebuild_reduction: Estimated percentage reduction in future rebuilds
        effort_estimate: Relative effort (low/medium/high)
        roi_score: Return on investment score (0-100, higher is better)
        break_even_commits: Estimated commits until benefits exceed costs
        severity: Priority level (critical/moderate/quick_win)
        specific_issues: List of specific problems detected
        actionable_steps: List of recommended refactoring steps
        affected_headers: Headers that would benefit from this refactoring
    """

    header: str
    anti_pattern: str
    current_metrics: "DSMMetrics"
    estimated_coupling_reduction: int
    estimated_rebuild_reduction: float
    effort_estimate: str
    roi_score: float
    break_even_commits: float
    severity: str
    specific_issues: List[str]
    actionable_steps: List[str]
    affected_headers: Set[str] = field(default_factory=set)
