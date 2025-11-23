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
"""Shared utilities for scenario testing.

This module provides common classes and utilities used across scenario tests
to validate DSM analysis results against expected architectural outcomes.
"""

from lib.dsm_types import DSMAnalysisResults, DSMDelta
from lib.scenario_definitions import CouplingTrend, ScenarioDefinition


class ArchitecturalMetrics:
    """Container for key architectural metrics extracted from DSMDelta."""

    def __init__(self, delta: DSMDelta, baseline: DSMAnalysisResults, current: DSMAnalysisResults):
        """Extract key metrics from DSM delta.

        Args:
            delta: DSMDelta from comparison
            baseline: Baseline DSM analysis results
            current: Current DSM analysis results
        """
        self.cycles_delta = delta.cycles_added - delta.cycles_removed
        self.cycles_added = delta.cycles_added
        self.cycles_removed = delta.cycles_removed
        self.headers_added = len(delta.headers_added)
        self.headers_removed = len(delta.headers_removed)

        # Coupling trend analysis
        total_coupling_increase = sum(delta.coupling_increased.values())
        total_coupling_decrease = sum(abs(v) for v in delta.coupling_decreased.values())
        self.coupling_net_change = total_coupling_increase - total_coupling_decrease
        self.coupling_trend = self._determine_coupling_trend(delta)

        # Stability crossings
        if delta.architectural_insights:
            self.stability_crossings = len(delta.architectural_insights.stability_changes.became_unstable) + len(
                delta.architectural_insights.stability_changes.became_stable
            )
            self.severity_level = delta.architectural_insights.severity
            self.has_layer_violations = any("layer" in rec.lower() or "inversion" in rec.lower() for rec in delta.architectural_insights.recommendations)
            self.has_interface_extraction = any(
                "interface" in rec.lower() or "extraction" in rec.lower() for rec in delta.architectural_insights.recommendations
            )

            # Rebuild impact trend
            if delta.architectural_insights.ripple_impact:
                ripple = delta.architectural_insights.ripple_impact
                if ripple.this_commit_rebuild_count > 0:
                    self.rebuild_impact_trend = "increase"
                elif ripple.ongoing_rebuild_delta_percentage < -5:
                    self.rebuild_impact_trend = "decrease"
                else:
                    self.rebuild_impact_trend = "stable"
            else:
                self.rebuild_impact_trend = "stable"
        else:
            self.stability_crossings = 0
            self.severity_level = "neutral"
            self.has_layer_violations = False
            self.has_interface_extraction = False
            self.rebuild_impact_trend = "stable"

        # Cycle complexity
        self.max_cycle_size_baseline = max((len(c) for c in baseline.cycles), default=0)
        self.max_cycle_size_current = max((len(c) for c in current.cycles), default=0)
        self.cycle_complexity_change = self._determine_cycle_complexity_change()

    def _determine_coupling_trend(self, delta: DSMDelta) -> CouplingTrend:
        """Determine overall coupling trend from delta."""
        increases = len(delta.coupling_increased)
        decreases = len(delta.coupling_decreased)

        if increases == 0 and decreases == 0:
            return CouplingTrend.STABLE
        elif increases > decreases * 2:
            return CouplingTrend.INCREASE
        elif decreases > increases * 2:
            return CouplingTrend.DECREASE
        else:
            return CouplingTrend.MIXED

    def _determine_cycle_complexity_change(self) -> str:
        """Determine if cycle complexity increased, decreased, or stayed stable."""
        if self.max_cycle_size_current > self.max_cycle_size_baseline:
            return "larger"
        elif self.max_cycle_size_current < self.max_cycle_size_baseline:
            return "smaller"
        else:
            return "stable"

    def matches_expected(self, expected: ScenarioDefinition, tolerance_pct: float = 5.0) -> tuple[bool, list[str]]:
        """Check if metrics match expected outcomes.

        Args:
            expected: Expected scenario definition
            tolerance_pct: Tolerance percentage for numeric comparisons

        Returns:
            Tuple of (matches: bool, mismatches: list of error messages)
        """
        mismatches = []
        exp = expected.expected_outcome

        # Check cycles delta
        if self.cycles_delta != exp.cycles_delta:
            mismatches.append(f"Cycles delta mismatch: expected {exp.cycles_delta}, got {self.cycles_delta}")

        # Check coupling trend
        if self.coupling_trend != exp.coupling_trend:
            mismatches.append(f"Coupling trend mismatch: expected {exp.coupling_trend.value}, got {self.coupling_trend.value}")

        # Check new headers
        has_new = self.headers_added > 0
        if has_new != exp.has_new_headers:
            mismatches.append(f"New headers mismatch: expected {exp.has_new_headers}, got {has_new}")

        # Check removed headers
        has_removed = self.headers_removed > 0
        if has_removed != exp.has_removed_headers:
            mismatches.append(f"Removed headers mismatch: expected {exp.has_removed_headers}, got {has_removed}")

        # Check stability crossings (with tolerance)
        if abs(self.stability_crossings - exp.stability_crossings) > 1:  # Allow ±1 difference
            mismatches.append(f"Stability crossings mismatch: expected ~{exp.stability_crossings}, got {self.stability_crossings}")

        # Check severity level
        expected_severity = exp.severity_level.value
        if self.severity_level != expected_severity:
            mismatches.append(f"Severity mismatch: expected {expected_severity}, got {self.severity_level}")

        # Check layer violations (if expected)
        if exp.has_layer_violations and not self.has_layer_violations:
            mismatches.append("Expected layer violations but none detected")

        # Check interface extraction (if expected)
        if exp.has_interface_extraction and not self.has_interface_extraction:
            mismatches.append("Expected interface extraction pattern but not detected")

        return len(mismatches) == 0, mismatches
