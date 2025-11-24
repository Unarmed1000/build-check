#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for delta-aware recommendation generation in DSM analysis."""

import pytest
from typing import Dict, Set, List, Tuple, Optional
from collections import defaultdict
import networkx as nx

from lib.dsm_types import CouplingStatistics, CycleComplexityStats, StabilityChange, RippleImpactAnalysis, DSMAnalysisResults, DSMDelta, MatrixStatistics
from lib.dsm_analysis import generate_recommendations
from lib.graph_utils import DSMMetrics


class TestDeltaAwareRecommendations:
    """Test generate_recommendations with delta awareness for change attribution."""

    def create_mock_current(self, cycles: Optional[List[Set[str]]] = None) -> DSMAnalysisResults:
        """Create a mock current DSMAnalysisResults."""
        if cycles is None:
            cycles = []

        return DSMAnalysisResults(
            metrics={
                "a.h": DSMMetrics(fan_out=5, fan_in=10, coupling=15, stability=0.33),
                "b.h": DSMMetrics(fan_out=8, fan_in=12, coupling=20, stability=0.40),
            },
            cycles=cycles,
            headers_in_cycles=set().union(*cycles) if cycles else set(),
            feedback_edges=[],
            directed_graph=nx.DiGraph(),
            layers=[],
            header_to_layer={},
            has_cycles=len(cycles) > 0,
            stats=MatrixStatistics(
                total_headers=2, total_actual_deps=0, total_possible_deps=2, sparsity=100.0, avg_deps=0.0, health="Healthy", health_color="GREEN"
            ),
            sorted_headers=["a.h", "b.h"],
            reverse_deps=defaultdict(set),
            header_to_headers=defaultdict(set),
        )

    def test_new_cycles_priority_1(self) -> None:
        """Test that NEW cycles get highest priority (Priority 1)."""
        coupling_stats = CouplingStatistics(
            mean_baseline=15.0,
            mean_current=18.0,
            median_baseline=15.0,
            median_current=18.0,
            stddev_baseline=2.0,
            stddev_current=3.0,
            p95_baseline=17.0,
            p95_current=20.0,
            p99_baseline=18.0,
            p99_current=21.0,
            mean_delta_pct=20.0,
            stddev_delta_pct=50.0,
            outliers_baseline=set(),
            outliers_current=set(),
            min_baseline=13.0,
            min_current=15.0,
            max_baseline=17.0,
            max_current=21.0,
            outliers_1sigma=[],
            outliers_2sigma=[],
        )

        cycle_complexity = CycleComplexityStats(
            size_histogram={8: 1},
            max_cycle_size_baseline=0,
            max_cycle_size_current=8,
            avg_cycle_size_baseline=0.0,
            avg_cycle_size_current=8.0,
            edge_density_per_cycle={0: 1.0},
            critical_breaking_edges=[],
        )

        stability_changes = StabilityChange(became_unstable=set(), became_stable=set(), high_instability=set(), stability_details={}, extreme_instability=[])

        ripple_impact = RippleImpactAnalysis(
            precise_score=100,
            precise_confidence=95.0,
            high_impact_headers=[],
            ripple_reduction=[],
            total_downstream_impact=15,
            unique_downstream_count=10,
            this_commit_rebuild_count=0,
            this_commit_rebuild_percentage=0.0,
            future_ongoing_rebuild_count=0,
            future_ongoing_rebuild_percentage=0.0,
            baseline_ongoing_rebuild_count=0,
            baseline_ongoing_rebuild_percentage=0.0,
            ongoing_rebuild_delta_percentage=0.0,
            total_source_files=0,
            roi_payback_commits=0.0,
            roi_payback_min=0.0,
            roi_payback_max=0.0,
            future_savings=None,
        )

        current_cycles = [{"a.h", "b.h", "c.h", "d.h", "e.h", "f.h", "g.h", "h.h"}]
        current = self.create_mock_current(current_cycles)

        # Delta with NO pre-existing cycles (all cycles are new)
        delta = DSMDelta(
            headers_added={"c.h"},
            headers_removed=set(),
            cycles_added=1,
            cycles_removed=0,
            coupling_increased={"a.h": 5},
            coupling_decreased={},
            layer_changes={},
            new_cycle_participants={"a.h", "b.h"},
            resolved_cycle_participants=set(),
            architectural_insights=None,
            pre_existing_cycle_headers=set(),  # No pre-existing cycles
            escalated_cycle_headers=set(),
            pre_existing_unstable_headers=set(),
            pre_existing_coupling_outliers=[],
        )

        recommendations = generate_recommendations(coupling_stats, cycle_complexity, stability_changes, ripple_impact, current_cycles, current, delta)

        # Should have NEW cycle recommendations at top (Priority 1)
        assert len(recommendations) > 0
        assert any("NEW" in rec and ("CRITICAL" in rec or "cycle" in rec.lower()) for rec in recommendations)
        # First critical recommendation should mention NEW
        critical_recs = [r for r in recommendations if "🔴" in r]
        if critical_recs:
            assert "NEW" in critical_recs[0]

    def test_escalated_cycles_priority_2(self) -> None:
        """Test that ESCALATED pre-existing cycles get Priority 2."""
        coupling_stats = CouplingStatistics(
            mean_baseline=15.0,
            mean_current=18.0,
            median_baseline=15.0,
            median_current=18.0,
            stddev_baseline=2.0,
            stddev_current=3.0,
            p95_baseline=17.0,
            p95_current=20.0,
            p99_baseline=18.0,
            p99_current=21.0,
            mean_delta_pct=20.0,
            stddev_delta_pct=50.0,
            outliers_baseline=set(),
            outliers_current=set(),
            min_baseline=13.0,
            min_current=15.0,
            max_baseline=17.0,
            max_current=21.0,
            outliers_1sigma=[],
            outliers_2sigma=[],
        )

        cycle_complexity = CycleComplexityStats(
            size_histogram={3: 1},
            max_cycle_size_baseline=3,
            max_cycle_size_current=3,
            avg_cycle_size_baseline=3.0,
            avg_cycle_size_current=3.0,
            edge_density_per_cycle={0: 1.0},
            critical_breaking_edges=[],
        )

        stability_changes = StabilityChange(became_unstable=set(), became_stable=set(), high_instability=set(), stability_details={}, extreme_instability=[])

        ripple_impact = RippleImpactAnalysis(
            precise_score=None,
            precise_confidence=None,
            high_impact_headers=[],
            ripple_reduction=[],
            total_downstream_impact=15,
            unique_downstream_count=0,
            this_commit_rebuild_count=0,
            this_commit_rebuild_percentage=0.0,
            future_ongoing_rebuild_count=0,
            future_ongoing_rebuild_percentage=0.0,
            baseline_ongoing_rebuild_count=0,
            baseline_ongoing_rebuild_percentage=0.0,
            ongoing_rebuild_delta_percentage=0.0,
            total_source_files=0,
            roi_payback_commits=0.0,
            roi_payback_min=0.0,
            roi_payback_max=0.0,
            future_savings=None,
        )

        current_cycles = [{"a.h", "b.h", "c.h"}]
        current = self.create_mock_current(current_cycles)

        # Delta with escalated pre-existing cycles
        delta = DSMDelta(
            headers_added=set(),
            headers_removed=set(),
            cycles_added=0,
            cycles_removed=0,
            coupling_increased={"a.h": 5},
            coupling_decreased={},
            layer_changes={},
            new_cycle_participants=set(),
            resolved_cycle_participants=set(),
            architectural_insights=None,
            pre_existing_cycle_headers={"a.h", "b.h", "c.h"},  # Cycles existed before
            escalated_cycle_headers={"a.h"},  # Modified header in pre-existing cycle
            pre_existing_unstable_headers=set(),
            pre_existing_coupling_outliers=[],
        )

        recommendations = generate_recommendations(coupling_stats, cycle_complexity, stability_changes, ripple_impact, current_cycles, current, delta)

        # Should have escalated cycle recommendation
        assert len(recommendations) > 0
        escalated_recs = [r for r in recommendations if "PRE-EXISTING" in r and "modified" in r.lower()]
        assert len(escalated_recs) > 0
        # Should mention "a.h" and "pre-existing"
        assert any("a.h" in rec for rec in escalated_recs)

    def test_pre_existing_issues_priority_5(self) -> None:
        """Test that PRE-EXISTING issues get lowest priority (Priority 5) with INFO marker."""
        coupling_stats = CouplingStatistics(
            mean_baseline=15.0,
            mean_current=18.0,
            median_baseline=15.0,
            median_current=18.0,
            stddev_baseline=2.0,
            stddev_current=3.0,
            p95_baseline=17.0,
            p95_current=20.0,
            p99_baseline=18.0,
            p99_current=21.0,
            mean_delta_pct=5.0,  # Small change
            stddev_delta_pct=10.0,  # Small change
            outliers_baseline=set(),
            outliers_current=set(),
            min_baseline=13.0,
            min_current=15.0,
            max_baseline=17.0,
            max_current=21.0,
            outliers_1sigma=[],
            outliers_2sigma=[("a.h", 25.0)],  # Current outlier
        )

        cycle_complexity = None
        stability_changes = StabilityChange(
            became_unstable={"b.h"}, became_stable=set(), high_instability=set(), stability_details={}, extreme_instability=[]  # New unstable
        )

        ripple_impact = RippleImpactAnalysis(
            precise_score=None,
            precise_confidence=None,
            high_impact_headers=[],
            ripple_reduction=[],
            total_downstream_impact=15,
            unique_downstream_count=0,
            this_commit_rebuild_count=0,
            this_commit_rebuild_percentage=0.0,
            future_ongoing_rebuild_count=0,
            future_ongoing_rebuild_percentage=0.0,
            baseline_ongoing_rebuild_count=0,
            baseline_ongoing_rebuild_percentage=0.0,
            ongoing_rebuild_delta_percentage=0.0,
            total_source_files=0,
            roi_payback_commits=0.0,
            roi_payback_min=0.0,
            roi_payback_max=0.0,
            future_savings=None,
        )

        current = self.create_mock_current()

        # Delta with pre-existing issues
        delta = DSMDelta(
            headers_added=set(),
            headers_removed=set(),
            cycles_added=0,
            cycles_removed=0,
            coupling_increased={},
            coupling_decreased={},
            layer_changes={},
            new_cycle_participants=set(),
            resolved_cycle_participants=set(),
            architectural_insights=None,
            pre_existing_cycle_headers=set(),
            escalated_cycle_headers=set(),
            pre_existing_unstable_headers={"c.h", "d.h"},  # Pre-existing unstable headers
            pre_existing_coupling_outliers=[("a.h", 25.0)],  # Pre-existing outlier
        )

        recommendations = generate_recommendations(coupling_stats, cycle_complexity, stability_changes, ripple_impact, [], current, delta)

        # Should have pre-existing recommendations with INFO marker (⚪)
        info_recs = [r for r in recommendations if "⚪ INFO" in r]
        assert len(info_recs) > 0
        # Should mention pre-existing
        assert any("pre-existing" in rec.lower() or "existed in baseline" in rec.lower() for rec in info_recs)

    def test_new_vs_pre_existing_unstable_headers(self) -> None:
        """Test that new unstable headers are distinguished from pre-existing ones."""
        coupling_stats = CouplingStatistics(
            mean_baseline=15.0,
            mean_current=18.0,
            median_baseline=15.0,
            median_current=18.0,
            stddev_baseline=2.0,
            stddev_current=3.0,
            p95_baseline=17.0,
            p95_current=20.0,
            p99_baseline=18.0,
            p99_current=21.0,
            mean_delta_pct=20.0,
            stddev_delta_pct=50.0,
            outliers_baseline=set(),
            outliers_current=set(),
            min_baseline=13.0,
            min_current=15.0,
            max_baseline=17.0,
            max_current=21.0,
            outliers_1sigma=[],
            outliers_2sigma=[],
        )

        cycle_complexity = None
        stability_changes = StabilityChange(
            became_unstable={"new1.h", "new2.h", "pre_exist.h"},  # 3 became unstable
            became_stable=set(),
            high_instability=set(),
            stability_details={},
            extreme_instability=[],
        )

        ripple_impact = RippleImpactAnalysis(
            precise_score=None,
            precise_confidence=None,
            high_impact_headers=[],
            ripple_reduction=[],
            total_downstream_impact=15,
            unique_downstream_count=0,
            this_commit_rebuild_count=0,
            this_commit_rebuild_percentage=0.0,
            future_ongoing_rebuild_count=0,
            future_ongoing_rebuild_percentage=0.0,
            baseline_ongoing_rebuild_count=0,
            baseline_ongoing_rebuild_percentage=0.0,
            ongoing_rebuild_delta_percentage=0.0,
            total_source_files=0,
            roi_payback_commits=0.0,
            roi_payback_min=0.0,
            roi_payback_max=0.0,
            future_savings=None,
        )

        current = self.create_mock_current()

        delta = DSMDelta(
            headers_added=set(),
            headers_removed=set(),
            cycles_added=0,
            cycles_removed=0,
            coupling_increased={},
            coupling_decreased={},
            layer_changes={},
            new_cycle_participants=set(),
            resolved_cycle_participants=set(),
            architectural_insights=None,
            pre_existing_cycle_headers=set(),
            escalated_cycle_headers=set(),
            pre_existing_unstable_headers={"pre_exist.h"},  # One was pre-existing
            pre_existing_coupling_outliers=[],
        )

        recommendations = generate_recommendations(coupling_stats, cycle_complexity, stability_changes, ripple_impact, [], current, delta)

        # Should only report 2 new unstable headers (new1.h, new2.h), not pre_exist.h
        new_unstable_recs = [r for r in recommendations if "became unstable" in r and "due to this change" in r]
        assert len(new_unstable_recs) > 0
        assert "2 headers" in new_unstable_recs[0]

    def test_interface_extraction_positive(self) -> None:
        """Test that interface extraction gets positive recommendation (Priority 3)."""
        from lib.dsm_types import FutureRebuildPrediction

        coupling_stats = CouplingStatistics(
            mean_baseline=15.0,
            mean_current=18.0,
            median_baseline=15.0,
            median_current=18.0,
            stddev_baseline=2.0,
            stddev_current=3.0,
            p95_baseline=17.0,
            p95_current=20.0,
            p99_baseline=18.0,
            p99_current=21.0,
            mean_delta_pct=20.0,
            stddev_delta_pct=50.0,
            outliers_baseline=set(),
            outliers_current=set(),
            min_baseline=13.0,
            min_current=15.0,
            max_baseline=17.0,
            max_current=21.0,
            outliers_1sigma=[],
            outliers_2sigma=[],
        )

        future_savings = FutureRebuildPrediction(
            interface_headers=2,
            isolated_impl_headers=5,
            baseline_volatile_fanin=50,
            current_volatile_fanin=10,
            reduction_percentage=80,
            description="Interface extraction pattern detected",
        )

        ripple_impact = RippleImpactAnalysis(
            precise_score=None,
            precise_confidence=None,
            high_impact_headers=[],
            ripple_reduction=[],
            total_downstream_impact=15,
            unique_downstream_count=0,
            this_commit_rebuild_count=0,
            this_commit_rebuild_percentage=0.0,
            future_ongoing_rebuild_count=0,
            future_ongoing_rebuild_percentage=0.0,
            baseline_ongoing_rebuild_count=0,
            baseline_ongoing_rebuild_percentage=0.0,
            ongoing_rebuild_delta_percentage=0.0,
            total_source_files=0,
            roi_payback_commits=0.0,
            roi_payback_min=0.0,
            roi_payback_max=0.0,
            future_savings=future_savings,
        )

        cycle_complexity = None
        stability_changes = StabilityChange(became_unstable=set(), became_stable=set(), high_instability=set(), stability_details={}, extreme_instability=[])

        current = self.create_mock_current()

        delta = DSMDelta(
            headers_added=set(),
            headers_removed=set(),
            cycles_added=0,
            cycles_removed=0,
            coupling_increased={},
            coupling_decreased={},
            layer_changes={},
            new_cycle_participants=set(),
            resolved_cycle_participants=set(),
            architectural_insights=None,
            pre_existing_cycle_headers=set(),
            escalated_cycle_headers=set(),
            pre_existing_unstable_headers=set(),
            pre_existing_coupling_outliers=[],
        )

        recommendations = generate_recommendations(coupling_stats, cycle_complexity, stability_changes, ripple_impact, [], current, delta)

        # Should have positive interface extraction recommendation
        positive_recs = [r for r in recommendations if "🟢 POSITIVE" in r and "Interface extraction" in r]
        assert len(positive_recs) > 0
        assert "80%" in positive_recs[0]

    def test_empty_recommendations_for_clean_architecture(self) -> None:
        """Test that minimal recommendations are generated for clean architecture with no issues."""
        coupling_stats = CouplingStatistics(
            mean_baseline=15.0,
            mean_current=15.0,  # No change
            median_baseline=15.0,
            median_current=15.0,
            stddev_baseline=2.0,
            stddev_current=2.0,
            p95_baseline=17.0,
            p95_current=17.0,
            p99_baseline=18.0,
            p99_current=18.0,
            mean_delta_pct=0.0,  # No change
            stddev_delta_pct=0.0,  # No change
            outliers_baseline=set(),
            outliers_current=set(),
            min_baseline=13.0,
            min_current=13.0,
            max_baseline=17.0,
            max_current=17.0,
            outliers_1sigma=[],
            outliers_2sigma=[],
        )

        cycle_complexity = None
        stability_changes = StabilityChange(became_unstable=set(), became_stable=set(), high_instability=set(), stability_details={}, extreme_instability=[])

        ripple_impact = RippleImpactAnalysis(
            precise_score=None,
            precise_confidence=None,
            high_impact_headers=[],
            ripple_reduction=[],
            total_downstream_impact=15,
            unique_downstream_count=0,
            this_commit_rebuild_count=0,
            this_commit_rebuild_percentage=0.0,
            future_ongoing_rebuild_count=0,
            future_ongoing_rebuild_percentage=0.0,
            baseline_ongoing_rebuild_count=0,
            baseline_ongoing_rebuild_percentage=0.0,
            ongoing_rebuild_delta_percentage=0.0,
            total_source_files=0,
            roi_payback_commits=0.0,
            roi_payback_min=0.0,
            roi_payback_max=0.0,
            future_savings=None,
        )

        current = self.create_mock_current()

        delta = DSMDelta(
            headers_added=set(),
            headers_removed=set(),
            cycles_added=0,
            cycles_removed=0,
            coupling_increased={},
            coupling_decreased={},
            layer_changes={},
            new_cycle_participants=set(),
            resolved_cycle_participants=set(),
            architectural_insights=None,
            pre_existing_cycle_headers=set(),
            escalated_cycle_headers=set(),
            pre_existing_unstable_headers=set(),
            pre_existing_coupling_outliers=[],
        )

        recommendations = generate_recommendations(coupling_stats, cycle_complexity, stability_changes, ripple_impact, [], current, delta)

        # Should have few or no recommendations for clean architecture
        critical_recs = [r for r in recommendations if "🔴 CRITICAL" in r]
        assert len(critical_recs) == 0

    def test_recommendation_ordering(self) -> None:
        """Test that recommendations are ordered by priority."""
        coupling_stats = CouplingStatistics(
            mean_baseline=15.0,
            mean_current=18.0,
            median_baseline=15.0,
            median_current=18.0,
            stddev_baseline=2.0,
            stddev_current=3.0,
            p95_baseline=17.0,
            p95_current=20.0,
            p99_baseline=18.0,
            p99_current=21.0,
            mean_delta_pct=20.0,
            stddev_delta_pct=50.0,
            outliers_baseline=set(),
            outliers_current=set(),
            min_baseline=13.0,
            min_current=15.0,
            max_baseline=17.0,
            max_current=21.0,
            outliers_1sigma=[],
            outliers_2sigma=[("outlier.h", 30.0)],
        )

        cycle_complexity = CycleComplexityStats(
            size_histogram={6: 1},
            max_cycle_size_baseline=0,
            max_cycle_size_current=6,
            avg_cycle_size_baseline=0.0,
            avg_cycle_size_current=6.0,
            edge_density_per_cycle={0: 1.0},
            critical_breaking_edges=[],
        )

        stability_changes = StabilityChange(
            became_unstable={"new_unstable.h"}, became_stable=set(), high_instability=set(), stability_details={}, extreme_instability=[]
        )

        ripple_impact = RippleImpactAnalysis(
            precise_score=None,
            precise_confidence=None,
            high_impact_headers=[],
            ripple_reduction=[("reduced.h", 5)],
            total_downstream_impact=15,
            unique_downstream_count=0,
            this_commit_rebuild_count=0,
            this_commit_rebuild_percentage=0.0,
            future_ongoing_rebuild_count=0,
            future_ongoing_rebuild_percentage=0.0,
            baseline_ongoing_rebuild_count=0,
            baseline_ongoing_rebuild_percentage=0.0,
            ongoing_rebuild_delta_percentage=0.0,
            total_source_files=0,
            roi_payback_commits=0.0,
            roi_payback_min=0.0,
            roi_payback_max=0.0,
            future_savings=None,
        )

        current_cycles = [{"a.h", "b.h", "c.h", "d.h", "e.h", "f.h"}]
        current = self.create_mock_current(current_cycles)

        delta = DSMDelta(
            headers_added={"new.h"},
            headers_removed=set(),
            cycles_added=1,
            cycles_removed=0,
            coupling_increased={"a.h": 5},
            coupling_decreased={},
            layer_changes={},
            new_cycle_participants={"a.h"},
            resolved_cycle_participants=set(),
            architectural_insights=None,
            pre_existing_cycle_headers=set(),  # No pre-existing
            escalated_cycle_headers=set(),
            pre_existing_unstable_headers=set(),
            pre_existing_coupling_outliers=[("outlier.h", 30.0)],  # Pre-existing outlier
        )

        recommendations = generate_recommendations(coupling_stats, cycle_complexity, stability_changes, ripple_impact, current_cycles, current, delta)

        # Verify ordering: Priority 1 (NEW cycles) should come before Priority 5 (INFO)
        new_cycle_idx = -1
        info_idx = -1
        for i, rec in enumerate(recommendations):
            if "NEW" in rec and "cycle" in rec.lower():
                new_cycle_idx = i
            if "⚪ INFO" in rec:
                info_idx = i

        # If both exist, NEW cycles should come before INFO
        if new_cycle_idx >= 0 and info_idx >= 0:
            assert new_cycle_idx < info_idx, "NEW cycles should appear before INFO pre-existing issues"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
