#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for enhanced metrics usage in anti-pattern detection.

Tests that anti-pattern detection correctly uses fan_out_project instead of
total fan_out, preventing false positives for headers with many external includes.
"""

import pytest
from typing import Dict
from collections import defaultdict
from unittest.mock import Mock, MagicMock
from lib.sensitivity_thresholds import SensitivityLevel, DetectionThresholds
from lib.dsm_analysis import identify_improvement_candidates, estimate_improvement_roi
from lib.graph_utils import DSMMetrics
from lib.dsm_types import DSMAnalysisResults
import networkx as nx


def create_mock_dsm_results(metrics_dict: Dict[str, DSMMetrics]) -> DSMAnalysisResults:
    """Create a mock DSMAnalysisResults for testing.

    Args:
        metrics_dict: Dictionary mapping header paths to DSMMetrics

    Returns:
        Mock DSMAnalysisResults with necessary attributes
    """
    G: "nx.DiGraph[str]" = nx.DiGraph()
    G.add_nodes_from(metrics_dict.keys())

    return DSMAnalysisResults(
        metrics=metrics_dict,
        cycles=[],
        headers_in_cycles=set(),
        feedback_edges=[],
        directed_graph=G,
        layers=[],
        header_to_layer={},
        has_cycles=False,
        stats=Mock(),
        sorted_headers=list(metrics_dict.keys()),
        reverse_deps={h: set() for h in metrics_dict.keys()},
        header_to_headers=defaultdict(set, {h: set() for h in metrics_dict.keys()}),
        source_to_deps=None,
        self_loops=[],
    )


class TestGodObjectDetection:
    """Tests for god object detection using fan_out_project."""

    def test_god_object_uses_fan_out_project(self) -> None:
        """Verify god object detection uses fan_out_project, not total fan_out."""
        # Header with high project includes (55) + low external (5) = 60 total
        # Should be flagged as god object at MEDIUM sensitivity (threshold=50)
        header = "/project/src/Engine.h"
        metrics = {header: DSMMetrics(fan_out=60, fan_in=10, fan_out_project=55, fan_out_external=5, coupling=70, stability=0.857)}

        results = create_mock_dsm_results(metrics)
        thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.MEDIUM)

        candidates = identify_improvement_candidates(results, "/project", thresholds)

        # Should find exactly 1 candidate (god object)
        assert len(candidates) == 1
        assert "god_object" in candidates[0].anti_pattern
        assert candidates[0].header == header

    def test_third_party_heavy_header_not_flagged(self) -> None:
        """Verify headers with many external includes are NOT flagged as god objects."""
        # Header with low project includes (3) + high external (57) = 60 total
        # Should NOT be flagged at MEDIUM sensitivity (project < 50)
        header = "/project/src/ThirdPartyWrapper.h"
        metrics = {header: DSMMetrics(fan_out=60, fan_in=10, fan_out_project=3, fan_out_external=57, coupling=70, stability=0.857)}

        results = create_mock_dsm_results(metrics)
        thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.MEDIUM)

        candidates = identify_improvement_candidates(results, "/project", thresholds)

        # Should find NO candidates (not a god object)
        god_object_candidates = [c for c in candidates if "god_object" in c.anti_pattern]
        assert len(god_object_candidates) == 0


class TestFoundationHeaderExemption:
    """Tests for foundation header exemption using fan_out_project."""

    def test_foundation_exemption_uses_fan_out_project(self) -> None:
        """Verify foundation headers with low project fan_out are exempted from coupling outlier."""
        # Foundation header: low project includes (2), high external (50), high fan_in (35)
        # Should be exempted from coupling outlier detection
        header = "/project/include/BaseTypes.h"
        metrics = {
            header: DSMMetrics(fan_out=52, fan_in=35, fan_out_project=2, fan_out_external=50, coupling=87, stability=0.60)  # Would normally flag as outlier
        }

        results = create_mock_dsm_results(metrics)
        thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.MEDIUM)

        candidates = identify_improvement_candidates(results, "/project", thresholds)

        # Should find NO candidates (exempted as foundation)
        coupling_outliers = [c for c in candidates if "coupling_outlier" in c.anti_pattern]
        assert len(coupling_outliers) == 0

    def test_high_project_fanout_not_exempted(self) -> None:
        """Verify headers with high project includes are NOT exempted as foundation."""
        # Not a foundation: high project includes (60), low external (5), high fan_in (35)
        # Should be flagged as god_object (fan_out_project=60 > 50 threshold)
        header = "/project/include/NotFoundation.h"

        # Create metrics - header with high project fanout should be detected as god object
        metrics = {
            header: DSMMetrics(fan_out=65, fan_in=35, fan_out_project=60, fan_out_external=5, coupling=100, stability=0.65),
            "/project/src/dummy1.h": DSMMetrics(fan_out=5, fan_in=5, fan_out_project=3, fan_out_external=2, coupling=8, stability=0.5),
            "/project/src/dummy2.h": DSMMetrics(fan_out=6, fan_in=6, fan_out_project=4, fan_out_external=2, coupling=9, stability=0.5),
            "/project/src/dummy3.h": DSMMetrics(fan_out=8, fan_in=8, fan_out_project=6, fan_out_external=2, coupling=11, stability=0.5),
            "/project/src/dummy4.h": DSMMetrics(fan_out=7, fan_in=7, fan_out_project=5, fan_out_external=2, coupling=10, stability=0.5),
            "/project/src/dummy5.h": DSMMetrics(fan_out=6, fan_in=6, fan_out_project=4, fan_out_external=2, coupling=12, stability=0.5),
        }

        results = create_mock_dsm_results(metrics)
        thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.MEDIUM)

        candidates = identify_improvement_candidates(results, "/project", thresholds)

        # Should find candidate (not exempted, high fan_out_project triggers god_object)
        header_candidates = [c for c in candidates if c.header == header]

        assert len(header_candidates) >= 1  # Should have at least one anti-pattern
        # Should NOT be exempted as foundation despite high fan_in (because fan_out_project=60 >> 3)
        # Verify god_object anti-pattern is detected (fan_out_project=60 > threshold=50)
        assert any("god_object" in c.anti_pattern for c in header_candidates)


class TestSensitivityLevels:
    """Tests for different sensitivity levels producing different results."""

    def test_sensitivity_changes_detection_counts(self) -> None:
        """Verify HIGH sensitivity finds more issues than MEDIUM than LOW."""
        # Borderline god object: 45 project includes
        # LOW (70): not flagged
        # MEDIUM (50): not flagged
        # HIGH (30): flagged
        header = "/project/src/BorderlineGodObject.h"
        metrics = {header: DSMMetrics(fan_out=50, fan_in=10, fan_out_project=45, fan_out_external=5, coupling=60, stability=0.833)}

        results = create_mock_dsm_results(metrics)

        # Test LOW sensitivity (should NOT flag)
        low_thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.LOW)
        low_candidates = identify_improvement_candidates(results, "/project", low_thresholds)
        low_god_objects = [c for c in low_candidates if "god_object" in c.anti_pattern]
        assert len(low_god_objects) == 0

        # Test MEDIUM sensitivity (should NOT flag, 45 < 50)
        medium_thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.MEDIUM)
        medium_candidates = identify_improvement_candidates(results, "/project", medium_thresholds)
        medium_god_objects = [c for c in medium_candidates if "god_object" in c.anti_pattern]
        assert len(medium_god_objects) == 0

        # Test HIGH sensitivity (should flag, 45 > 30)
        high_thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.HIGH)
        high_candidates = identify_improvement_candidates(results, "/project", high_thresholds)
        high_god_objects = [c for c in high_candidates if "god_object" in c.anti_pattern]
        assert len(high_god_objects) == 1


class TestUnstableInterfaceDetection:
    """Tests for unstable interface detection with configurable thresholds."""

    def test_unstable_interface_respects_thresholds(self) -> None:
        """Verify unstable interface detection uses configurable stability and fan_in thresholds."""
        # Borderline unstable: stability=0.55, fan_in=12
        # LOW (stability>0.7, fan_in>=15): not flagged
        # MEDIUM (stability>0.5, fan_in>=10): flagged
        # HIGH (stability>0.4, fan_in>=8): flagged
        header = "/project/include/BorderlineUnstable.h"
        metrics = {header: DSMMetrics(fan_out=12, fan_in=12, fan_out_project=10, fan_out_external=2, coupling=24, stability=0.5)}

        results = create_mock_dsm_results(metrics)

        # Test LOW sensitivity (should NOT flag: 0.5 < 0.7)
        low_thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.LOW)
        low_candidates = identify_improvement_candidates(results, "/project", low_thresholds)
        low_unstable = [c for c in low_candidates if "unstable_interface" in c.anti_pattern]
        assert len(low_unstable) == 0

        # Test MEDIUM sensitivity (should NOT flag: 0.5 == 0.5, need > not >=)
        medium_thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.MEDIUM)
        medium_candidates = identify_improvement_candidates(results, "/project", medium_thresholds)
        medium_unstable = [c for c in medium_candidates if "unstable_interface" in c.anti_pattern]
        assert len(medium_unstable) == 0

        # Test HIGH sensitivity (should flag: 0.5 > 0.4 and 12 >= 8)
        high_thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.HIGH)
        high_candidates = identify_improvement_candidates(results, "/project", high_thresholds)
        high_unstable = [c for c in high_candidates if "unstable_interface" in c.anti_pattern]
        assert len(high_unstable) == 1


class TestROIEstimation:
    """Tests for ROI estimation using fan_out_project."""

    def test_roi_uses_fan_out_project_for_god_object(self) -> None:
        """Verify ROI estimation uses fan_out_project for god object reduction."""
        from lib.dsm_types import ImprovementCandidate

        header = "/project/src/GodObject.h"
        metrics = DSMMetrics(fan_out=70, fan_in=20, fan_out_project=60, fan_out_external=10, coupling=90, stability=0.778)

        candidate = ImprovementCandidate(
            header=header,
            anti_pattern="god_object",
            current_metrics=metrics,
            estimated_coupling_reduction=0,
            estimated_rebuild_reduction=0.0,
            effort_estimate="unknown",
            roi_score=0.0,
            break_even_commits=0.0,
            severity="unknown",
            specific_issues=[],
            actionable_steps=[],
            affected_headers=set(),
        )

        results = create_mock_dsm_results({header: metrics})
        thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.MEDIUM)

        updated_candidate = estimate_improvement_roi(candidate, results, None, thresholds)

        # God object reduction should be 70% of project fan_out (60), not total (70)
        # Expected: 60 * 0.7 = 42
        assert updated_candidate.estimated_coupling_reduction == 42

    def test_roi_uses_thresholds_for_interface_extraction(self) -> None:
        """Verify ROI estimation uses threshold for interface extraction target."""
        from lib.dsm_types import ImprovementCandidate

        header = "/project/src/UnstableInterface.h"
        metrics = DSMMetrics(fan_out=15, fan_in=25, fan_out_project=12, fan_out_external=3, coupling=40, stability=0.375)

        candidate = ImprovementCandidate(
            header=header,
            anti_pattern="unstable_interface",
            current_metrics=metrics,
            estimated_coupling_reduction=0,
            estimated_rebuild_reduction=0.0,
            effort_estimate="unknown",
            roi_score=0.0,
            break_even_commits=0.0,
            severity="unknown",
            specific_issues=[],
            actionable_steps=[],
            affected_headers=set(),
        )

        results = create_mock_dsm_results({header: metrics})
        thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.MEDIUM)

        updated_candidate = estimate_improvement_roi(candidate, results, None, thresholds)

        # Interface extraction: reduce fan_out_project to threshold target (5)
        # Expected: max(0, 12 - 5) = 7
        assert updated_candidate.estimated_coupling_reduction == 7
