#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for architectural insights functionality in DSM analysis."""

import pytest
from typing import Dict, Set
from collections import defaultdict

from lib.dsm_types import (
    CouplingStatistics,
    CycleComplexityStats,
    StabilityChange,
    RippleImpactAnalysis,
    ArchitecturalInsights,
    DSMAnalysisResults,
    MatrixStatistics,
)
from lib.dsm_analysis import compute_coupling_trends, compute_cycle_insights, compute_ripple_impact, compute_architectural_insights, determine_severity
from lib.graph_utils import DSMMetrics
import networkx as nx


class TestCouplingTrends:
    """Test compute_coupling_trends function."""

    def test_coupling_trends_with_common_headers(self) -> None:
        """Test coupling trend computation with common headers."""
        baseline_metrics = {
            "a.h": DSMMetrics(fan_out=5, fan_in=10, coupling=15, stability=0.33),
            "b.h": DSMMetrics(fan_out=8, fan_in=12, coupling=20, stability=0.40),
            "c.h": DSMMetrics(fan_out=3, fan_in=7, coupling=10, stability=0.30),
        }

        current_metrics = {
            "a.h": DSMMetrics(fan_out=6, fan_in=12, coupling=18, stability=0.33),
            "b.h": DSMMetrics(fan_out=10, fan_in=15, coupling=25, stability=0.40),
            "c.h": DSMMetrics(fan_out=3, fan_in=8, coupling=11, stability=0.27),
        }

        common_headers = {"a.h", "b.h", "c.h"}

        stats = compute_coupling_trends(baseline_metrics, current_metrics, common_headers)

        assert stats.mean_baseline == 15.0
        assert stats.mean_current == 18.0
        assert stats.mean_delta_pct == pytest.approx(20.0, abs=0.1)
        assert stats.stddev_baseline > 0
        assert stats.stddev_current > 0

    def test_coupling_trends_no_common_headers(self) -> None:
        """Test coupling trends with no common headers returns zero stats."""
        baseline_metrics = {"a.h": DSMMetrics(fan_out=5, fan_in=10, coupling=15, stability=0.33)}
        current_metrics = {"b.h": DSMMetrics(fan_out=8, fan_in=12, coupling=20, stability=0.40)}
        common_headers: Set[str] = set()

        stats = compute_coupling_trends(baseline_metrics, current_metrics, common_headers)

        assert stats.mean_baseline == 0
        assert stats.mean_current == 0
        assert stats.mean_delta_pct == 0


class TestCycleInsights:
    """Test compute_cycle_insights function."""

    def test_cycle_insights_with_cycles(self) -> None:
        """Test cycle complexity computation with cycles present."""
        baseline_cycles = [{"a.h", "b.h"}, {"c.h", "d.h", "e.h"}]
        current_cycles = [{"a.h", "b.h", "c.h"}, {"d.h", "e.h"}]

        # Create a simple graph
        G: "nx.DiGraph[str]" = nx.DiGraph()
        G.add_edges_from([("a.h", "b.h"), ("b.h", "c.h"), ("c.h", "a.h"), ("d.h", "e.h"), ("e.h", "d.h")])

        insights = compute_cycle_insights(baseline_cycles, current_cycles, G)

        assert insights is not None
        assert insights.avg_cycle_size_baseline == pytest.approx(2.5, abs=0.1)
        assert insights.avg_cycle_size_current == pytest.approx(2.5, abs=0.1)
        assert insights.max_cycle_size_baseline == 3
        assert insights.max_cycle_size_current == 3

    def test_cycle_insights_no_cycles(self) -> None:
        """Test cycle insights returns None when no cycles exist."""
        baseline_cycles = [{"a.h", "b.h"}]
        current_cycles: list[Set[str]] = []
        G: "nx.DiGraph[str]" = nx.DiGraph()

        insights = compute_cycle_insights(baseline_cycles, current_cycles, G)

        assert insights is None


class TestRippleImpact:
    """Test compute_ripple_impact function."""

    def test_ripple_impact_heuristic(self) -> None:
        """Test heuristic ripple impact computation."""
        baseline_graph: "nx.DiGraph[str]" = nx.DiGraph()
        current_graph: "nx.DiGraph[str]" = nx.DiGraph()
        current_graph.add_edges_from([("a.h", "b.h"), ("b.h", "c.h")])

        baseline_metrics = {
            "a.h": DSMMetrics(fan_out=5, fan_in=10, coupling=15, stability=0.33),
            "b.h": DSMMetrics(fan_out=8, fan_in=5, coupling=13, stability=0.62),
        }

        current_metrics = {
            "a.h": DSMMetrics(fan_out=6, fan_in=12, coupling=18, stability=0.33),
            "b.h": DSMMetrics(fan_out=8, fan_in=5, coupling=13, stability=0.62),
        }

        changed_headers = {"a.h"}

        # Build reverse dependencies from current graph
        reverse_deps = {"b.h": {"a.h"}, "c.h": {"b.h"}}

        impact = compute_ripple_impact(baseline_graph, current_graph, baseline_metrics, current_metrics, changed_headers, reverse_deps, compute_precise=False)

        assert impact.heuristic_score > 0
        assert impact.heuristic_confidence == 5.0
        assert impact.precise_score is None
        assert len(impact.high_impact_headers) > 0
        assert impact.total_downstream_impact >= 0
        assert impact.unique_downstream_count >= 0

    def test_ripple_impact_with_precise(self) -> None:
        """Test ripple impact with precise transitive closure."""
        # Create graphs with clear transitive relationships
        baseline_graph: "nx.DiGraph[str]" = nx.DiGraph()
        baseline_graph.add_edges_from([("a.h", "b.h"), ("b.h", "c.h")])

        current_graph: "nx.DiGraph[str]" = nx.DiGraph()
        current_graph.add_edges_from([("a.h", "b.h"), ("b.h", "c.h"), ("a.h", "d.h")])

        baseline_metrics = {"a.h": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0)}
        current_metrics = {"a.h": DSMMetrics(fan_out=2, fan_in=0, coupling=2, stability=1.0)}

        changed_headers = {"a.h"}

        # Build reverse dependencies from current graph
        reverse_deps = {"b.h": {"a.h"}, "c.h": {"b.h"}, "d.h": {"a.h"}}

        impact = compute_ripple_impact(baseline_graph, current_graph, baseline_metrics, current_metrics, changed_headers, reverse_deps, compute_precise=True)

        assert impact.precise_score is not None
        assert impact.precise_confidence == 95.0
        assert impact.total_downstream_impact >= 0
        assert impact.unique_downstream_count >= 0


class TestArchitecturalInsights:
    """Test compute_architectural_insights integration."""

    def test_architectural_insights_computation(self) -> None:
        """Test full architectural insights computation."""
        # Create minimal DSMAnalysisResults
        baseline_metrics = {
            "a.h": DSMMetrics(fan_out=5, fan_in=10, coupling=15, stability=0.33),
            "b.h": DSMMetrics(fan_out=8, fan_in=12, coupling=20, stability=0.40),
        }

        current_metrics = {
            "a.h": DSMMetrics(fan_out=6, fan_in=12, coupling=18, stability=0.33),
            "b.h": DSMMetrics(fan_out=10, fan_in=15, coupling=25, stability=0.40),
        }

        baseline_graph: "nx.DiGraph[str]" = nx.DiGraph()
        baseline_graph.add_node("a.h")
        baseline_graph.add_node("b.h")

        current_graph: "nx.DiGraph[str]" = nx.DiGraph()
        current_graph.add_node("a.h")
        current_graph.add_node("b.h")

        baseline = DSMAnalysisResults(
            metrics=baseline_metrics,
            cycles=[],
            headers_in_cycles=set(),
            feedback_edges=[],
            directed_graph=baseline_graph,
            layers=[["a.h"], ["b.h"]],
            header_to_layer={"a.h": 0, "b.h": 1},
            has_cycles=False,
            stats=MatrixStatistics(
                total_headers=2, total_actual_deps=0, total_possible_deps=2, sparsity=100.0, avg_deps=0.0, health="Healthy", health_color="GREEN"
            ),
            sorted_headers=["a.h", "b.h"],
            reverse_deps=defaultdict(set),
            header_to_headers=defaultdict(set),
        )

        current = DSMAnalysisResults(
            metrics=current_metrics,
            cycles=[],
            headers_in_cycles=set(),
            feedback_edges=[],
            directed_graph=current_graph,
            layers=[["a.h"], ["b.h"]],
            header_to_layer={"a.h": 0, "b.h": 1},
            has_cycles=False,
            stats=MatrixStatistics(
                total_headers=2, total_actual_deps=0, total_possible_deps=2, sparsity=100.0, avg_deps=0.0, health="Healthy", health_color="GREEN"
            ),
            sorted_headers=["a.h", "b.h"],
            reverse_deps=defaultdict(set),
            header_to_headers=defaultdict(set),
        )

        insights = compute_architectural_insights(baseline_metrics, current_metrics, baseline, current, compute_precise_impact=False)

        assert insights is not None
        assert isinstance(insights.coupling_stats, CouplingStatistics)
        assert isinstance(insights.stability_changes, StabilityChange)
        assert isinstance(insights.ripple_impact, RippleImpactAnalysis)
        assert insights.confidence_level in ["high", "medium", "low"]
        assert insights.severity in ["critical", "moderate", "positive"]
        assert len(insights.recommendations) > 0


class TestSeverityDetermination:
    """Test determine_severity function."""

    def test_severity_critical_large_cycle(self) -> None:
        """Test critical severity for large cycles."""
        coupling_stats = CouplingStatistics(
            mean_baseline=10,
            mean_current=15,
            median_baseline=10,
            median_current=15,
            stddev_baseline=2,
            stddev_current=3,
            p95_baseline=20,
            p95_current=25,
            p99_baseline=30,
            p99_current=35,
            mean_delta_pct=50.0,
            stddev_delta_pct=50.0,
            outliers_baseline=set(),
            outliers_current=set(),
        )

        cycle_complexity = CycleComplexityStats(
            size_histogram={6: 1},
            avg_cycle_size_baseline=3,
            avg_cycle_size_current=6,
            max_cycle_size_baseline=3,
            max_cycle_size_current=6,
            edge_density_per_cycle={0: 1.5},
            critical_breaking_edges=[],
        )

        severity = determine_severity(coupling_stats, cycle_complexity, current_cycles_count=1, baseline_cycles_count=0)

        assert severity == "critical"

    def test_severity_positive_improvements(self) -> None:
        """Test positive severity for improvements."""
        coupling_stats = CouplingStatistics(
            mean_baseline=20,
            mean_current=15,
            median_baseline=20,
            median_current=15,
            stddev_baseline=3,
            stddev_current=2,
            p95_baseline=30,
            p95_current=25,
            p99_baseline=40,
            p99_current=35,
            mean_delta_pct=-25.0,
            stddev_delta_pct=-33.0,
            outliers_baseline=set(),
            outliers_current=set(),
        )

        severity = determine_severity(coupling_stats, None, current_cycles_count=0, baseline_cycles_count=1)

        assert severity == "positive"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
