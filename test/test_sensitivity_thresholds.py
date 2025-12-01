#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for sensitivity threshold configuration.

Tests the DetectionThresholds dataclass and SensitivityLevel enum used for
configurable anti-pattern detection in --suggest-improvements mode.
"""

import pytest
from lib.sensitivity_thresholds import SensitivityLevel, DetectionThresholds


class TestSensitivityLevel:
    """Tests for SensitivityLevel enum."""

    def test_sensitivity_level_enum_has_three_levels(self) -> None:
        """Verify SensitivityLevel enum has LOW, MEDIUM, HIGH values."""
        assert hasattr(SensitivityLevel, "LOW")
        assert hasattr(SensitivityLevel, "MEDIUM")
        assert hasattr(SensitivityLevel, "HIGH")
        assert SensitivityLevel.LOW.value == "low"
        assert SensitivityLevel.MEDIUM.value == "medium"
        assert SensitivityLevel.HIGH.value == "high"

    def test_sensitivity_level_from_string(self) -> None:
        """Verify SensitivityLevel can be created from string values."""
        assert SensitivityLevel("low") == SensitivityLevel.LOW
        assert SensitivityLevel("medium") == SensitivityLevel.MEDIUM
        assert SensitivityLevel("high") == SensitivityLevel.HIGH


class TestDetectionThresholds:
    """Tests for DetectionThresholds dataclass."""

    def test_detection_thresholds_immutable(self) -> None:
        """Verify DetectionThresholds is frozen (immutable)."""
        thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.MEDIUM)
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            thresholds.god_object_fanout = 999  # type: ignore[misc]

    def test_low_sensitivity_thresholds(self) -> None:
        """Verify LOW sensitivity has most permissive thresholds."""
        thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.LOW)

        # God object detection
        assert thresholds.god_object_fanout == 70
        assert thresholds.split_target_includes == 20

        # Coupling outlier detection
        assert thresholds.outlier_sigma == 3.0

        # Unstable interface detection
        assert thresholds.unstable_stability_threshold == 0.7
        assert thresholds.unstable_fanin_threshold == 15

        # Foundation header exemption
        assert thresholds.foundation_stability_threshold == 0.15
        assert thresholds.foundation_project_fanout_max == 5
        assert thresholds.foundation_fanin_min == 30

        # Hub node detection
        assert thresholds.hub_betweenness_min == 0.01
        assert thresholds.hub_detection_top_n == 10

        # Interface extraction
        assert thresholds.interface_extraction_target == 5

        # Debt score thresholds
        assert thresholds.debt_score_low_threshold == 30
        assert thresholds.debt_score_moderate_threshold == 60

    def test_medium_sensitivity_thresholds(self) -> None:
        """Verify MEDIUM sensitivity has balanced thresholds (default)."""
        thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.MEDIUM)

        # God object detection
        assert thresholds.god_object_fanout == 50
        assert thresholds.split_target_includes == 20

        # Coupling outlier detection
        assert thresholds.outlier_sigma == 2.5

        # Unstable interface detection
        assert thresholds.unstable_stability_threshold == 0.5
        assert thresholds.unstable_fanin_threshold == 10

        # Foundation header exemption
        assert thresholds.foundation_stability_threshold == 0.05
        assert thresholds.foundation_project_fanout_max == 3
        assert thresholds.foundation_fanin_min == 30

        # Hub node detection
        assert thresholds.hub_betweenness_min == 0.01
        assert thresholds.hub_detection_top_n == 10

        # Interface extraction
        assert thresholds.interface_extraction_target == 5

        # Debt score thresholds
        assert thresholds.debt_score_low_threshold == 30
        assert thresholds.debt_score_moderate_threshold == 60

    def test_high_sensitivity_thresholds(self) -> None:
        """Verify HIGH sensitivity has strictest thresholds."""
        thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.HIGH)

        # God object detection
        assert thresholds.god_object_fanout == 30
        assert thresholds.split_target_includes == 20

        # Coupling outlier detection
        assert thresholds.outlier_sigma == 1.5

        # Unstable interface detection
        assert thresholds.unstable_stability_threshold == 0.4
        assert thresholds.unstable_fanin_threshold == 8

        # Foundation header exemption
        assert thresholds.foundation_stability_threshold == 0.03
        assert thresholds.foundation_project_fanout_max == 2
        assert thresholds.foundation_fanin_min == 30

        # Hub node detection
        assert thresholds.hub_betweenness_min == 0.01
        assert thresholds.hub_detection_top_n == 10

        # Interface extraction
        assert thresholds.interface_extraction_target == 5

        # Debt score thresholds
        assert thresholds.debt_score_low_threshold == 30
        assert thresholds.debt_score_moderate_threshold == 60

    def test_thresholds_positive_values(self) -> None:
        """Verify all numeric thresholds are positive."""
        for level in [SensitivityLevel.LOW, SensitivityLevel.MEDIUM, SensitivityLevel.HIGH]:
            thresholds = DetectionThresholds.for_sensitivity(level)

            assert thresholds.god_object_fanout > 0
            assert thresholds.outlier_sigma > 0
            assert thresholds.unstable_stability_threshold > 0
            assert thresholds.unstable_fanin_threshold > 0
            assert thresholds.foundation_stability_threshold > 0
            assert thresholds.foundation_project_fanout_max > 0
            assert thresholds.foundation_fanin_min > 0
            assert thresholds.hub_betweenness_min > 0
            assert thresholds.hub_detection_top_n > 0
            assert thresholds.interface_extraction_target > 0
            assert thresholds.split_target_includes > 0
            assert thresholds.debt_score_low_threshold > 0
            assert thresholds.debt_score_moderate_threshold > 0

    def test_thresholds_logical_ordering(self) -> None:
        """Verify LOW is most permissive, HIGH is most strict."""
        low = DetectionThresholds.for_sensitivity(SensitivityLevel.LOW)
        medium = DetectionThresholds.for_sensitivity(SensitivityLevel.MEDIUM)
        high = DetectionThresholds.for_sensitivity(SensitivityLevel.HIGH)

        # God object: higher threshold = more permissive
        assert low.god_object_fanout > medium.god_object_fanout > high.god_object_fanout

        # Outlier sigma: higher = more permissive (requires more std deviations)
        assert low.outlier_sigma > medium.outlier_sigma > high.outlier_sigma

        # Unstable stability: higher = more permissive (requires higher instability)
        assert low.unstable_stability_threshold > medium.unstable_stability_threshold > high.unstable_stability_threshold

        # Unstable fan-in: higher = more permissive (requires more dependents)
        assert low.unstable_fanin_threshold > medium.unstable_fanin_threshold > high.unstable_fanin_threshold

        # Foundation stability: higher = more permissive (allows higher outgoing deps)
        assert low.foundation_stability_threshold > medium.foundation_stability_threshold > high.foundation_stability_threshold

        # Foundation project fanout: higher = more permissive (allows more project includes)
        assert low.foundation_project_fanout_max > medium.foundation_project_fanout_max > high.foundation_project_fanout_max

    def test_debt_score_thresholds_consistent(self) -> None:
        """Verify debt score thresholds are consistent across sensitivity levels."""
        # Debt score thresholds should be the same regardless of detection sensitivity
        # (they define output categorization, not detection behavior)
        low = DetectionThresholds.for_sensitivity(SensitivityLevel.LOW)
        medium = DetectionThresholds.for_sensitivity(SensitivityLevel.MEDIUM)
        high = DetectionThresholds.for_sensitivity(SensitivityLevel.HIGH)

        assert low.debt_score_low_threshold == medium.debt_score_low_threshold == high.debt_score_low_threshold == 30
        assert low.debt_score_moderate_threshold == medium.debt_score_moderate_threshold == high.debt_score_moderate_threshold == 60
