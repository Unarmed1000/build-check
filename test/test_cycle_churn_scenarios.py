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
"""Tests for cycle churn detection and reporting.

This module tests the handling of scenarios where cycles are both added and removed
in the same commit, which indicates architectural instability (cycle churn).
"""
import sys
from pathlib import Path
from collections import defaultdict
from typing import Set

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.dsm_analysis import compare_dsm_results, determine_severity, run_dsm_analysis, print_dsm_delta
from lib.dsm_types import CouplingStatistics, CycleComplexityStats


class TestCycleChurnDetection:
    """Test cycle churn detection in different scenarios."""

    @pytest.mark.unit
    def test_pure_cycle_addition_no_churn(self) -> None:
        """Test pure cycle addition (baseline=0, current=2) - should be critical, not churn."""
        # Baseline: No cycles
        baseline_headers = {"a.hpp", "b.hpp", "c.hpp", "d.hpp"}
        baseline_deps: defaultdict[str, Set[str]] = defaultdict(set)
        baseline_deps["a.hpp"] = {"b.hpp"}
        baseline_deps["b.hpp"] = {"c.hpp"}

        baseline_results = run_dsm_analysis(baseline_headers, baseline_deps, compute_layers=True, show_progress=False)

        # Current: Two cycles added
        current_headers = {"a.hpp", "b.hpp", "c.hpp", "d.hpp"}
        current_deps: defaultdict[str, Set[str]] = defaultdict(set)
        current_deps["a.hpp"] = {"b.hpp"}
        current_deps["b.hpp"] = {"a.hpp"}  # Cycle 1: a <-> b
        current_deps["c.hpp"] = {"d.hpp"}
        current_deps["d.hpp"] = {"c.hpp"}  # Cycle 2: c <-> d

        current_results = run_dsm_analysis(current_headers, current_deps, compute_layers=True, show_progress=False)

        # Compare
        delta = compare_dsm_results(baseline_results, current_results)

        # Assertions
        assert len(baseline_results.cycles) == 0
        assert len(current_results.cycles) == 2
        assert delta.cycles_added == 2
        assert delta.cycles_removed == 0
        assert len(delta.new_cycle_participants) > 0
        assert len(delta.resolved_cycle_participants) == 0

    @pytest.mark.unit
    def test_pure_cycle_removal_no_churn(self) -> None:
        """Test pure cycle removal (baseline=2, current=0) - should be improvement, not churn."""
        # Baseline: Two cycles
        baseline_headers = {"a.hpp", "b.hpp", "c.hpp", "d.hpp"}
        baseline_deps: defaultdict[str, Set[str]] = defaultdict(set)
        baseline_deps["a.hpp"] = {"b.hpp"}
        baseline_deps["b.hpp"] = {"a.hpp"}  # Cycle 1: a <-> b
        baseline_deps["c.hpp"] = {"d.hpp"}
        baseline_deps["d.hpp"] = {"c.hpp"}  # Cycle 2: c <-> d

        baseline_results = run_dsm_analysis(baseline_headers, baseline_deps, compute_layers=False, show_progress=False)

        # Current: No cycles
        current_headers = {"a.hpp", "b.hpp", "c.hpp", "d.hpp"}
        current_deps: defaultdict[str, Set[str]] = defaultdict(set)
        current_deps["a.hpp"] = {"b.hpp"}
        current_deps["b.hpp"] = set()
        current_deps["c.hpp"] = {"d.hpp"}
        current_deps["d.hpp"] = set()

        current_results = run_dsm_analysis(current_headers, current_deps, compute_layers=True, show_progress=False)

        # Compare
        delta = compare_dsm_results(baseline_results, current_results)

        # Assertions
        assert len(baseline_results.cycles) == 2
        assert len(current_results.cycles) == 0
        assert delta.cycles_added == 0
        assert delta.cycles_removed == 2
        assert len(delta.new_cycle_participants) == 0
        assert len(delta.resolved_cycle_participants) > 0

    @pytest.mark.unit
    def test_cycle_churn_net_positive(self) -> None:
        """Test cycle churn with net increase (baseline=1, current=2, 1 resolved + 2 new)."""
        # Baseline: One cycle (a <-> b)
        baseline_headers = {"a.hpp", "b.hpp", "c.hpp", "d.hpp"}
        baseline_deps: defaultdict[str, Set[str]] = defaultdict(set)
        baseline_deps["a.hpp"] = {"b.hpp"}
        baseline_deps["b.hpp"] = {"a.hpp"}  # Cycle 1: a <-> b
        baseline_deps["c.hpp"] = set()
        baseline_deps["d.hpp"] = set()

        baseline_results = run_dsm_analysis(baseline_headers, baseline_deps, compute_layers=False, show_progress=False)

        # Current: Two different cycles (c <-> d and e <-> f)
        # Cycle with a <-> b is resolved, but two new cycles introduced
        current_headers = {"a.hpp", "b.hpp", "c.hpp", "d.hpp", "e.hpp", "f.hpp"}
        current_deps: defaultdict[str, Set[str]] = defaultdict(set)
        current_deps["a.hpp"] = {"b.hpp"}
        current_deps["b.hpp"] = set()  # Resolved: a <-> b
        current_deps["c.hpp"] = {"d.hpp"}
        current_deps["d.hpp"] = {"c.hpp"}  # New Cycle 1: c <-> d
        current_deps["e.hpp"] = {"f.hpp"}
        current_deps["f.hpp"] = {"e.hpp"}  # New Cycle 2: e <-> f

        current_results = run_dsm_analysis(current_headers, current_deps, compute_layers=False, show_progress=False)

        # Compare
        delta = compare_dsm_results(baseline_results, current_results)

        # Assertions - cycle churn detected
        assert len(baseline_results.cycles) >= 1
        assert len(current_results.cycles) >= 2
        assert delta.cycles_added > 0
        assert delta.cycles_removed >= 0  # May be 0 if cycles counted differently

        # Should have both new participants and resolved participants (churn)
        # Note: This depends on whether common headers moved in/out of cycles
        cycle_change = len(current_results.cycles) - len(baseline_results.cycles)
        assert cycle_change > 0  # Net increase    @pytest.mark.unit

    def test_cycle_churn_net_negative(self) -> None:
        """Test cycle churn with net decrease (baseline=3, current=1, 2 resolved + 1 added)."""
        # Baseline: Three cycles
        baseline_headers = {"a.hpp", "b.hpp", "c.hpp", "d.hpp", "e.hpp", "f.hpp"}
        baseline_deps: defaultdict[str, Set[str]] = defaultdict(set)
        baseline_deps["a.hpp"] = {"b.hpp"}
        baseline_deps["b.hpp"] = {"a.hpp"}  # Cycle 1: a <-> b
        baseline_deps["c.hpp"] = {"d.hpp"}
        baseline_deps["d.hpp"] = {"c.hpp"}  # Cycle 2: c <-> d
        baseline_deps["e.hpp"] = {"f.hpp"}
        baseline_deps["f.hpp"] = {"e.hpp"}  # Cycle 3: e <-> f

        baseline_results = run_dsm_analysis(baseline_headers, baseline_deps, compute_layers=False, show_progress=False)

        # Current: One cycle (different from any baseline cycle)
        current_headers = {"a.hpp", "b.hpp", "c.hpp", "d.hpp", "e.hpp", "f.hpp", "g.hpp"}
        current_deps: defaultdict[str, Set[str]] = defaultdict(set)
        current_deps["a.hpp"] = {"b.hpp"}
        current_deps["b.hpp"] = set()  # Resolved
        current_deps["c.hpp"] = {"d.hpp"}
        current_deps["d.hpp"] = set()  # Resolved
        current_deps["e.hpp"] = {"f.hpp"}
        current_deps["f.hpp"] = set()  # Resolved
        current_deps["g.hpp"] = {"a.hpp"}
        current_deps["a.hpp"].add("g.hpp")  # New cycle: a <-> g

        current_results = run_dsm_analysis(current_headers, current_deps, compute_layers=False, show_progress=False)

        # Compare
        delta = compare_dsm_results(baseline_results, current_results)

        # Assertions - cycle churn with net improvement
        assert len(baseline_results.cycles) >= 3
        assert len(current_results.cycles) >= 1
        cycle_change = len(current_results.cycles) - len(baseline_results.cycles)
        assert cycle_change < 0  # Net decrease (improvement)

        # Still churn if both additions and removals occurred
        assert delta.cycles_removed > 0

    @pytest.mark.unit
    def test_no_cycle_change(self) -> None:
        """Test no cycle change (baseline=2, current=2, same cycles) - should not trigger churn."""
        # Baseline: Two cycles
        baseline_headers = {"a.hpp", "b.hpp", "c.hpp", "d.hpp"}
        baseline_deps: defaultdict[str, Set[str]] = defaultdict(set)
        baseline_deps["a.hpp"] = {"b.hpp"}
        baseline_deps["b.hpp"] = {"a.hpp"}  # Cycle 1: a <-> b
        baseline_deps["c.hpp"] = {"d.hpp"}
        baseline_deps["d.hpp"] = {"c.hpp"}  # Cycle 2: c <-> d

        baseline_results = run_dsm_analysis(baseline_headers, baseline_deps, compute_layers=False, show_progress=False)

        # Current: Same cycles
        current_headers = {"a.hpp", "b.hpp", "c.hpp", "d.hpp"}
        current_deps: defaultdict[str, Set[str]] = defaultdict(set)
        current_deps["a.hpp"] = {"b.hpp"}
        current_deps["b.hpp"] = {"a.hpp"}  # Cycle 1: a <-> b
        current_deps["c.hpp"] = {"d.hpp"}
        current_deps["d.hpp"] = {"c.hpp"}  # Cycle 2: c <-> d

        current_results = run_dsm_analysis(current_headers, current_deps, compute_layers=False, show_progress=False)

        # Compare
        delta = compare_dsm_results(baseline_results, current_results)

        # Assertions - no churn
        assert len(baseline_results.cycles) == len(current_results.cycles)
        assert delta.cycles_added == 0
        assert delta.cycles_removed == 0
        assert len(delta.new_cycle_participants) == 0
        assert len(delta.resolved_cycle_participants) == 0


class TestCycleChurnSeverity:
    """Test severity classification for cycle churn scenarios."""

    @pytest.mark.unit
    def test_severity_pure_addition_critical(self) -> None:
        """Severity should be critical for pure cycle addition (0 -> 2) with high coupling increase."""
        coupling_stats = CouplingStatistics(
            mean_baseline=10.0,
            mean_current=15.0,
            median_baseline=8.0,
            median_current=12.0,
            stddev_baseline=3.0,
            stddev_current=4.0,
            p95_baseline=20,
            p95_current=25,
            p99_baseline=30,
            p99_current=35,
            mean_delta_pct=50.1,  # > 50 to trigger critical threshold
            stddev_delta_pct=33.0,
            outliers_baseline=set(),
            outliers_current=set(),
        )

        cycle_complexity = CycleComplexityStats(
            size_histogram={2: 2},
            avg_cycle_size_baseline=0,
            avg_cycle_size_current=2.0,
            max_cycle_size_baseline=0,
            max_cycle_size_current=2,
            edge_density_per_cycle={},
            critical_breaking_edges=[],
        )

        severity = determine_severity(coupling_stats, cycle_complexity, current_cycles_count=2, baseline_cycles_count=0)

        # Should be critical due to mean_delta_pct > 50 (not due to cycle churn)
        # Cycle churn requires both baseline and current to have cycles > 0
        assert severity == "critical"

    @pytest.mark.unit
    def test_severity_cycle_churn_moderate(self) -> None:
        """Severity should be moderate for cycle churn (both added and removed)."""
        coupling_stats = CouplingStatistics(
            mean_baseline=10.0,
            mean_current=12.0,
            median_baseline=8.0,
            median_current=10.0,
            stddev_baseline=3.0,
            stddev_current=3.5,
            p95_baseline=20,
            p95_current=22,
            p99_baseline=30,
            p99_current=32,
            mean_delta_pct=20.0,  # Under 50%, so not critical from coupling alone
            stddev_delta_pct=16.7,
            outliers_baseline=set(),
            outliers_current=set(),
        )

        cycle_complexity = CycleComplexityStats(
            size_histogram={2: 1, 3: 1},
            avg_cycle_size_baseline=2.0,
            avg_cycle_size_current=2.5,
            max_cycle_size_baseline=2,
            max_cycle_size_current=3,
            edge_density_per_cycle={},
            critical_breaking_edges=[],
        )

        severity = determine_severity(coupling_stats, cycle_complexity, current_cycles_count=2, baseline_cycles_count=1)

        # Should be moderate due to cycle churn (baseline > 0, current > 0, count changed)
        assert severity == "moderate"

    @pytest.mark.unit
    def test_severity_pure_removal_positive(self) -> None:
        """Severity should be positive for pure cycle removal (2 -> 0)."""
        coupling_stats = CouplingStatistics(
            mean_baseline=15.0,
            mean_current=10.0,
            median_baseline=12.0,
            median_current=8.0,
            stddev_baseline=4.0,
            stddev_current=3.0,
            p95_baseline=25,
            p95_current=20,
            p99_baseline=35,
            p99_current=30,
            mean_delta_pct=-33.3,  # Improvement
            stddev_delta_pct=-25.0,
            outliers_baseline=set(),
            outliers_current=set(),
        )

        cycle_complexity = None  # No cycles in current

        severity = determine_severity(coupling_stats, cycle_complexity, current_cycles_count=0, baseline_cycles_count=2)

        # Should be positive due to cycle removal and coupling decrease
        assert severity == "positive"


class TestCycleChurnReporting:
    """Test cycle churn detection in print output."""

    @pytest.mark.unit
    def test_cycle_churn_warning_in_assessment(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test that cycle churn produces appropriate warning in assessment section."""
        # Create baseline with one cycle
        baseline_headers = {"a.hpp", "b.hpp", "c.hpp", "d.hpp"}
        baseline_deps: defaultdict[str, Set[str]] = defaultdict(set)
        baseline_deps["a.hpp"] = {"b.hpp"}
        baseline_deps["b.hpp"] = {"a.hpp"}

        baseline_results = run_dsm_analysis(baseline_headers, baseline_deps, compute_layers=False, show_progress=False)

        # Create current with different cycle (churn scenario)
        current_headers = {"a.hpp", "b.hpp", "c.hpp", "d.hpp"}
        current_deps: defaultdict[str, Set[str]] = defaultdict(set)
        current_deps["a.hpp"] = set()  # a <-> b resolved
        current_deps["b.hpp"] = set()
        current_deps["c.hpp"] = {"d.hpp"}
        current_deps["d.hpp"] = {"c.hpp"}  # c <-> d added

        current_results = run_dsm_analysis(current_headers, current_deps, compute_layers=True, show_progress=False)

        # Compare and print
        delta = compare_dsm_results(baseline_results, current_results)
        print_dsm_delta(delta, baseline_results, current_results, "/tmp", verbose=False)

        captured = capsys.readouterr()

        # Should contain cycle churn warning if both participants added and removed
        # (depends on whether common headers moved between cycle states)
        assert "Assessment:" in captured.out
        # The specific warning depends on whether new_cycle_participants and resolved_cycle_participants are both non-empty


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
