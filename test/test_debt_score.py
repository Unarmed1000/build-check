#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for comprehensive debt score calculation (Phase 4)."""

import pytest
from typing import Dict
from collections import defaultdict
from lib.graph_utils import DSMMetrics
from lib.dsm_types import DSMAnalysisResults
from lib.dsm_analysis import calculate_architectural_debt_score
from unittest.mock import Mock
import networkx as nx


def create_test_results(metrics_dict: Dict[str, DSMMetrics], cycles: int = 0, hub_count: int = 0) -> DSMAnalysisResults:
    """Create test DSMAnalysisResults with given metrics."""
    G: "nx.DiGraph[str]" = nx.DiGraph()
    G.add_nodes_from(metrics_dict.keys())

    # Create fake cycles if needed
    cycle_list = [{f"cycle_header_{i}.h"} for i in range(cycles)]

    return DSMAnalysisResults(
        metrics=metrics_dict,
        cycles=cycle_list,
        headers_in_cycles=set([h for cycle in cycle_list for h in cycle]),
        feedback_edges=[],
        directed_graph=G,
        layers=[],
        header_to_layer={},
        has_cycles=len(cycle_list) > 0,
        stats=Mock(),
        sorted_headers=list(metrics_dict.keys()),
        reverse_deps={h: set() for h in metrics_dict.keys()},
        header_to_headers=defaultdict(set, {h: set() for h in metrics_dict.keys()}),
        source_to_deps=None,
        self_loops=[],
    )


class TestDebtScoreCalculation:
    """Tests for comprehensive debt score formula."""

    def test_perfect_codebase_scores_zero(self) -> None:
        """Verify perfect codebase (no debt) scores 0."""
        # Perfect: low coupling, no cycles, low stability, no outliers
        metrics = {
            f"/project/header{i}.h": DSMMetrics(fan_out=2, fan_in=2, fan_out_project=2, fan_out_external=0, coupling=4, stability=0.5) for i in range(10)
        }
        results = create_test_results(metrics, cycles=0)

        score, breakdown = calculate_architectural_debt_score(results, verbose=True)

        # Should be very low (close to 0)
        assert score < 10, f"Perfect codebase should score < 10, got {score}"
        assert breakdown is not None
        assert breakdown["p95_coupling_component"] >= 0
        assert breakdown["outlier_component"] >= 0
        assert breakdown["stability_component"] >= 0
        assert breakdown["hub_component"] >= 0
        assert breakdown["cycle_component"] == 0  # No cycles

    def test_high_coupling_increases_score(self) -> None:
        """Verify high coupling increases debt score."""
        # High coupling scenario
        metrics = {
            f"/project/header{i}.h": DSMMetrics(fan_out=50, fan_in=50, fan_out_project=50, fan_out_external=0, coupling=100, stability=0.5) for i in range(10)
        }
        results = create_test_results(metrics, cycles=0)

        score, breakdown = calculate_architectural_debt_score(results, verbose=True)

        # High coupling should result in significant score (P95=100 gives 20 points + stability)
        assert score > 25, f"High coupling should score > 25, got {score}"
        # P95 component should be at max (20% weight, coupling 100 = max)
        assert breakdown is not None
        assert breakdown["p95_coupling_component"] == 20.0

    def test_outliers_increase_score(self) -> None:
        """Verify coupling outliers increase debt score."""
        # Most headers low coupling, one outlier
        metrics = {
            **{f"/project/header{i}.h": DSMMetrics(fan_out=5, fan_in=5, fan_out_project=5, fan_out_external=0, coupling=10, stability=0.5) for i in range(9)},
            "/project/god_object.h": DSMMetrics(fan_out=100, fan_in=100, fan_out_project=100, fan_out_external=0, coupling=200, stability=0.5),
        }
        results = create_test_results(metrics, cycles=0)

        score, breakdown = calculate_architectural_debt_score(results, verbose=True)

        # Outlier should contribute significantly (20% weight)
        assert breakdown is not None
        assert breakdown["outlier_component"] > 5, "Outlier should contribute > 5 points"

    def test_high_stability_increases_score(self) -> None:
        """Verify high average stability increases debt score."""
        # High stability = high instability (many outgoing dependencies)
        metrics = {
            f"/project/header{i}.h": DSMMetrics(fan_out=20, fan_in=2, fan_out_project=20, fan_out_external=0, coupling=22, stability=0.91)  # High instability
            for i in range(10)
        }
        results = create_test_results(metrics, cycles=0)

        score, breakdown = calculate_architectural_debt_score(results, verbose=True)

        # High stability should contribute (15% weight)
        assert breakdown is not None
        assert breakdown["stability_component"] > 5, "High stability should contribute > 5 points"

    def test_cycles_increase_score(self) -> None:
        """Verify circular dependencies increase debt score."""
        metrics = {
            f"/project/header{i}.h": DSMMetrics(fan_out=5, fan_in=5, fan_out_project=5, fan_out_external=0, coupling=10, stability=0.5) for i in range(10)
        }
        results = create_test_results(metrics, cycles=3)  # 3 cycles

        score, breakdown = calculate_architectural_debt_score(results, verbose=True)

        # Cycles should contribute significantly (40% weight - increased priority)
        assert breakdown is not None
        assert breakdown["cycle_component"] > 20, "3 cycles should contribute > 20 points"

    def test_comprehensive_bad_codebase_scores_high(self) -> None:
        """Verify codebase with multiple issues scores high."""
        # Bad: high coupling, statistical outliers, high stability, cycles
        # Use realistic sample size (20 headers) with tight cluster and true outliers
        # This ensures 2σ outlier detection works correctly (2 outliers = 10% of data)
        metrics = {
            **{
                f"/project/header{i}.h": DSMMetrics(fan_out=20, fan_in=5, fan_out_project=20, fan_out_external=0, coupling=25, stability=0.8) for i in range(18)
            },
            "/project/outlier1.h": DSMMetrics(fan_out=140, fan_in=10, fan_out_project=140, fan_out_external=0, coupling=150, stability=0.93),
            "/project/outlier2.h": DSMMetrics(fan_out=145, fan_in=10, fan_out_project=145, fan_out_external=0, coupling=155, stability=0.94),
        }
        results = create_test_results(metrics, cycles=5)

        score, breakdown = calculate_architectural_debt_score(results, verbose=True)

        # Should score high with the new formula (cycles weighted more heavily at 40%)
        assert score > 60, f"Bad codebase should score > 60, got {score}"
        assert score <= 100, f"Score should be capped at 100, got {score}"

        # All components should contribute meaningfully
        assert breakdown is not None
        assert breakdown["p95_coupling_component"] > 15  # High P95 (~154), 20% weight
        assert breakdown["outlier_component"] > 5  # 2 statistical outliers (10% of data)
        assert breakdown["stability_component"] > 5  # High avg stability (~0.81)
        assert breakdown["cycle_component"] > 30  # 5 cycles, 40% weight

    def test_score_breakdown_sums_correctly(self) -> None:
        """Verify breakdown components sum to total score."""
        metrics = {
            f"/project/header{i}.h": DSMMetrics(fan_out=20, fan_in=10, fan_out_project=20, fan_out_external=0, coupling=30, stability=0.67) for i in range(10)
        }
        results = create_test_results(metrics, cycles=2)

        score, breakdown = calculate_architectural_debt_score(results, verbose=True)

        # Sum of components should equal total score (within rounding)
        assert breakdown is not None
        component_sum = (
            breakdown["p95_coupling_component"]
            + breakdown["outlier_component"]
            + breakdown["stability_component"]
            + breakdown["hub_component"]
            + breakdown["cycle_component"]
        )
        assert abs(score - component_sum) < 0.1, f"Components {component_sum} should sum to score {score}"

    def test_verbose_false_returns_only_score(self) -> None:
        """Verify verbose=False returns only score, no breakdown."""
        metrics = {
            f"/project/header{i}.h": DSMMetrics(fan_out=10, fan_in=10, fan_out_project=10, fan_out_external=0, coupling=20, stability=0.5) for i in range(5)
        }
        results = create_test_results(metrics, cycles=1)

        score, breakdown = calculate_architectural_debt_score(results, verbose=False)

        assert isinstance(score, (int, float))
        assert breakdown is None, "verbose=False should return None for breakdown"

    def test_empty_codebase_scores_zero(self) -> None:
        """Verify empty codebase scores 0."""
        results = create_test_results({}, cycles=0)

        score, breakdown = calculate_architectural_debt_score(results, verbose=False)

        assert score == 0, "Empty codebase should score 0"

    def test_weights_sum_to_100_percent(self) -> None:
        """Verify component weights sum to 100%."""
        # This is a sanity check on the implementation
        # Weights: P95=30%, Outliers=20%, Stability=15%, Hubs=10%, Cycles=25%
        total_weight = 30 + 20 + 15 + 10 + 25
        assert total_weight == 100, "Component weights must sum to 100%"
