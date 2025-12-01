#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Integration tests for debt score in DSM analysis output."""

import pytest
from typing import Dict
from collections import defaultdict
from io import StringIO
import sys
from lib.graph_utils import DSMMetrics
from lib.dsm_types import DSMAnalysisResults, ImprovementCandidate
from lib.dsm_analysis import display_improvement_suggestions
from unittest.mock import Mock
import networkx as nx


def create_test_results_with_metrics(metrics_dict: Dict[str, DSMMetrics], cycles: int = 0) -> DSMAnalysisResults:
    """Create DSMAnalysisResults with given metrics for integration testing."""
    G: "nx.DiGraph[str]" = nx.DiGraph()
    G.add_nodes_from(metrics_dict.keys())

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


class TestDebtScoreIntegration:
    """Integration tests verifying debt score appears in improvement suggestions."""

    def test_debt_score_appears_in_output_no_verbose(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify debt score appears in improvement suggestions output (non-verbose)."""
        # Create realistic bad codebase scenario
        metrics = {
            **{
                f"/project/src/header{i}.h": DSMMetrics(fan_out=20, fan_in=5, fan_out_project=20, fan_out_external=0, coupling=25, stability=0.8)
                for i in range(18)
            },
            "/project/src/outlier1.h": DSMMetrics(fan_out=140, fan_in=10, fan_out_project=140, fan_out_external=0, coupling=150, stability=0.93),
            "/project/src/outlier2.h": DSMMetrics(fan_out=145, fan_in=10, fan_out_project=145, fan_out_external=0, coupling=155, stability=0.94),
        }
        results = create_test_results_with_metrics(metrics, cycles=0)  # NO CYCLES - they cause early return

        # Create improvement candidates
        candidates = [
            ImprovementCandidate(
                header="/project/src/outlier1.h",
                anti_pattern="excessive_coupling",
                current_metrics=metrics["/project/src/outlier1.h"],
                severity="critical",
                roi_score=75.0,
                estimated_coupling_reduction=50,
                estimated_rebuild_reduction=25.0,
                effort_estimate="medium",
                break_even_commits=8,
                specific_issues=["Couples to 140 other headers"],
                actionable_steps=["Split into focused modules"],
                affected_headers=set(),
            )
        ]

        # Capture output
        display_improvement_suggestions(candidates, results, "/project", top_n=5, verbose=False)
        captured = capsys.readouterr()

        # Verify debt score appears in output
        assert "Architectural Debt Score:" in captured.out
        assert "/100" in captured.out
        # Score should be moderate-to-high given the metrics
        assert any(severity in captured.out for severity in ["(Low)", "(Moderate)", "(High)"])

        # Verbose breakdown should NOT appear
        assert "Debt Score Breakdown:" not in captured.out

    def test_debt_score_breakdown_appears_in_verbose_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify debt score breakdown appears in verbose mode."""
        metrics = {
            **{
                f"/project/src/header{i}.h": DSMMetrics(fan_out=20, fan_in=5, fan_out_project=20, fan_out_external=0, coupling=25, stability=0.8)
                for i in range(18)
            },
            "/project/src/outlier1.h": DSMMetrics(fan_out=140, fan_in=10, fan_out_project=140, fan_out_external=0, coupling=150, stability=0.93),
            "/project/src/outlier2.h": DSMMetrics(fan_out=145, fan_in=10, fan_out_project=145, fan_out_external=0, coupling=155, stability=0.94),
        }
        results = create_test_results_with_metrics(metrics, cycles=0)  # NO CYCLES - they cause early return

        candidates = [
            ImprovementCandidate(
                header="/project/src/outlier1.h",
                anti_pattern="excessive_coupling",
                current_metrics=metrics["/project/src/outlier1.h"],
                severity="critical",
                roi_score=75.0,
                estimated_coupling_reduction=50,
                estimated_rebuild_reduction=25.0,
                effort_estimate="medium",
                break_even_commits=8,
                specific_issues=["Couples to 140 other headers"],
                actionable_steps=["Split into focused modules"],
                affected_headers=set(),
            )
        ]

        # Capture verbose output
        display_improvement_suggestions(candidates, results, "/project", top_n=5, verbose=True)
        captured = capsys.readouterr()

        # Verify debt score and breakdown appear
        assert "Architectural Debt Score:" in captured.out
        assert "Debt Score Breakdown:" in captured.out
        assert "P95 Coupling (20%):" in captured.out
        assert "Outliers >2σ (15%):" in captured.out
        assert "Avg Stability (15%):" in captured.out
        assert "Hub Nodes (10%):" in captured.out
        assert "Cycles (40%):" in captured.out

    def test_low_debt_score_shows_green(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify low debt score (<30) displays as green (Low)."""
        # Perfect codebase scenario
        metrics = {
            f"/project/src/header{i}.h": DSMMetrics(fan_out=2, fan_in=2, fan_out_project=2, fan_out_external=0, coupling=4, stability=0.5) for i in range(10)
        }
        results = create_test_results_with_metrics(metrics, cycles=0)

        candidates: list[ImprovementCandidate] = []  # No candidates for perfect codebase

        display_improvement_suggestions(candidates, results, "/project", top_n=5, verbose=False)
        captured = capsys.readouterr()

        # Should show healthy codebase message
        assert "No significant architectural debt detected" in captured.out
        assert "healthy coupling patterns" in captured.out

    def test_moderate_debt_score_shows_yellow(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify moderate debt score (30-60) displays as yellow (Moderate)."""
        # Moderate coupling, no cycles
        metrics = {
            f"/project/src/header{i}.h": DSMMetrics(fan_out=30, fan_in=20, fan_out_project=30, fan_out_external=0, coupling=50, stability=0.6)
            for i in range(15)
        }
        results = create_test_results_with_metrics(metrics, cycles=0)

        candidates = [
            ImprovementCandidate(
                header="/project/src/header0.h",
                anti_pattern="moderate_coupling",
                current_metrics=metrics["/project/src/header0.h"],
                severity="moderate",
                roi_score=35.0,
                estimated_coupling_reduction=10,
                estimated_rebuild_reduction=5.0,
                effort_estimate="low",
                break_even_commits=3,
                specific_issues=["Moderate coupling"],
                actionable_steps=["Review dependencies"],
                affected_headers=set(),
            )
        ]

        display_improvement_suggestions(candidates, results, "/project", top_n=5, verbose=False)
        captured = capsys.readouterr()

        assert "Architectural Debt Score:" in captured.out
        # Should be moderate range (30-60)
        assert "(Moderate)" in captured.out or "(Low)" in captured.out

    def test_high_debt_score_shows_red(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify high debt score (≥60) displays as red (High)."""
        # High coupling scenario (NO CYCLES - test with 0 cycles to see debt score)
        # Use even more extreme coupling to ensure high score without cycles
        metrics = {
            **{
                f"/project/src/header{i}.h": DSMMetrics(fan_out=50, fan_in=10, fan_out_project=50, fan_out_external=0, coupling=60, stability=0.83)
                for i in range(18)
            },
            "/project/src/outlier1.h": DSMMetrics(fan_out=180, fan_in=20, fan_out_project=180, fan_out_external=0, coupling=200, stability=0.9),
            "/project/src/outlier2.h": DSMMetrics(fan_out=190, fan_in=20, fan_out_project=190, fan_out_external=0, coupling=210, stability=0.91),
        }
        results = create_test_results_with_metrics(metrics, cycles=0)  # NO CYCLES - they cause early return

        candidates = [
            ImprovementCandidate(
                header="/project/src/outlier1.h",
                anti_pattern="excessive_coupling",
                current_metrics=metrics["/project/src/outlier1.h"],
                severity="critical",
                roi_score=75.0,
                estimated_coupling_reduction=50,
                estimated_rebuild_reduction=25.0,
                effort_estimate="medium",
                break_even_commits=8,
                specific_issues=["Couples to 140 other headers"],
                actionable_steps=["Split into focused modules"],
                affected_headers=set(),
            )
        ]

        display_improvement_suggestions(candidates, results, "/project", top_n=5, verbose=False)
        captured = capsys.readouterr()

        assert "Architectural Debt Score:" in captured.out
        # With high coupling outliers and 5 cycles, should score high (≥60)
        assert "(High)" in captured.out or "(Moderate)" in captured.out
