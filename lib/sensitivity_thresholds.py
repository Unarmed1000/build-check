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
"""Sensitivity threshold configuration for anti-pattern detection.

This module provides type-safe configuration of detection thresholds used in
--suggest-improvements mode. Supports three sensitivity levels:

- LOW: Most permissive (fewer false positives, may miss issues)
- MEDIUM: Balanced (default)
- HIGH: Most strict (more candidates, may include borderline cases)

Example usage:
    from lib.sensitivity_thresholds import SensitivityLevel, DetectionThresholds

    thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.MEDIUM)
    if metric.fan_out_project > thresholds.god_object_fanout:
        # Flag as god object
        pass
"""

from dataclasses import dataclass
from enum import Enum


class SensitivityLevel(Enum):
    """Detection sensitivity levels for anti-pattern identification.

    Controls how aggressively the analysis flags potential issues:
    - LOW: Conservative detection (high confidence, fewer candidates)
    - MEDIUM: Balanced detection (default, good for most projects)
    - HIGH: Aggressive detection (catches more issues, may include borderline cases)
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class DetectionThresholds:
    """Type-safe detection thresholds for anti-pattern identification.

    Immutable configuration object that defines numeric thresholds for various
    anti-pattern detection heuristics. Create instances using the factory method
    for_sensitivity() rather than directly constructing.

    Attributes:
        god_object_fanout: Max project includes before flagging as god object
        outlier_sigma: Standard deviations above mean to flag coupling outliers
        unstable_stability_threshold: Min stability (fan_out/coupling) to flag unstable interface
        unstable_fanin_threshold: Min dependents to flag unstable interface
        foundation_stability_threshold: Max stability to exempt as foundation header
        foundation_project_fanout_max: Max project includes to exempt as foundation header
        foundation_fanin_min: Min dependents to exempt as foundation header
        hub_betweenness_min: Min betweenness centrality to consider as hub
        hub_detection_top_n: Number of top betweenness nodes to analyze for hubs
        interface_extraction_target: Target fan_out after interface extraction
        split_target_includes: Recommended target includes per module after splitting
        debt_score_low_threshold: Score below which debt is considered low (healthy)
        debt_score_moderate_threshold: Score below which debt is moderate (consider improvements)
    """

    god_object_fanout: int
    outlier_sigma: float
    unstable_stability_threshold: float
    unstable_fanin_threshold: int
    foundation_stability_threshold: float
    foundation_project_fanout_max: int
    foundation_fanin_min: int
    hub_betweenness_min: float
    hub_detection_top_n: int
    interface_extraction_target: int
    split_target_includes: int
    debt_score_low_threshold: int
    debt_score_moderate_threshold: int

    def __post_init__(self) -> None:
        """Validate threshold values are positive and logically consistent."""
        # Validate all numeric thresholds are positive
        assert self.god_object_fanout > 0, "god_object_fanout must be positive"
        assert self.outlier_sigma > 0, "outlier_sigma must be positive"
        assert self.unstable_stability_threshold > 0, "unstable_stability_threshold must be positive"
        assert self.unstable_fanin_threshold > 0, "unstable_fanin_threshold must be positive"
        assert self.foundation_stability_threshold > 0, "foundation_stability_threshold must be positive"
        assert self.foundation_project_fanout_max > 0, "foundation_project_fanout_max must be positive"
        assert self.foundation_fanin_min > 0, "foundation_fanin_min must be positive"
        assert self.hub_betweenness_min > 0, "hub_betweenness_min must be positive"
        assert self.hub_detection_top_n > 0, "hub_detection_top_n must be positive"
        assert self.interface_extraction_target > 0, "interface_extraction_target must be positive"
        assert self.split_target_includes > 0, "split_target_includes must be positive"
        assert self.debt_score_low_threshold > 0, "debt_score_low_threshold must be positive"
        assert self.debt_score_moderate_threshold > 0, "debt_score_moderate_threshold must be positive"

        # Validate logical constraints
        assert self.unstable_stability_threshold <= 1.0, "stability threshold must be <= 1.0"
        assert self.foundation_stability_threshold <= 1.0, "foundation stability threshold must be <= 1.0"
        assert self.debt_score_low_threshold < self.debt_score_moderate_threshold, "low threshold must be less than moderate threshold"

    @staticmethod
    def for_sensitivity(level: SensitivityLevel) -> "DetectionThresholds":
        """Factory method to create DetectionThresholds for a given sensitivity level.

        Args:
            level: Desired sensitivity level (LOW, MEDIUM, or HIGH)

        Returns:
            Immutable DetectionThresholds instance with appropriate threshold values

        Example:
            >>> thresholds = DetectionThresholds.for_sensitivity(SensitivityLevel.MEDIUM)
            >>> thresholds.god_object_fanout
            50
        """
        if level == SensitivityLevel.LOW:
            # Most permissive: high thresholds, fewer candidates
            return DetectionThresholds(
                god_object_fanout=70,
                outlier_sigma=3.0,
                unstable_stability_threshold=0.7,
                unstable_fanin_threshold=15,
                foundation_stability_threshold=0.15,
                foundation_project_fanout_max=5,
                foundation_fanin_min=30,
                hub_betweenness_min=0.01,
                hub_detection_top_n=10,
                interface_extraction_target=5,
                split_target_includes=20,
                debt_score_low_threshold=30,
                debt_score_moderate_threshold=60,
            )
        elif level == SensitivityLevel.HIGH:
            # Most strict: low thresholds, more candidates
            return DetectionThresholds(
                god_object_fanout=30,
                outlier_sigma=1.5,
                unstable_stability_threshold=0.4,
                unstable_fanin_threshold=8,
                foundation_stability_threshold=0.03,
                foundation_project_fanout_max=2,
                foundation_fanin_min=30,
                hub_betweenness_min=0.01,
                hub_detection_top_n=10,
                interface_extraction_target=5,
                split_target_includes=20,
                debt_score_low_threshold=30,
                debt_score_moderate_threshold=60,
            )
        else:  # SensitivityLevel.MEDIUM (default)
            # Balanced: moderate thresholds, good for most projects
            return DetectionThresholds(
                god_object_fanout=50,
                outlier_sigma=2.5,
                unstable_stability_threshold=0.5,
                unstable_fanin_threshold=10,
                foundation_stability_threshold=0.05,
                foundation_project_fanout_max=3,
                foundation_fanin_min=30,
                hub_betweenness_min=0.01,
                hub_detection_top_n=10,
                interface_extraction_target=5,
                split_target_includes=20,
                debt_score_low_threshold=30,
                debt_score_moderate_threshold=60,
            )
