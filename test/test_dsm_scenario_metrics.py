#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test DSM scenario metrics equivalence.

This test suite validates that key architectural metrics (cycles, headers)
match expected outcomes for each scenario.
"""

import sys
from pathlib import Path

import pytest

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.dsm_analysis import compare_dsm_results
from lib.scenario_definitions import ALL_SCENARIOS
from lib.scenario_creators import BASELINE_CREATORS, SCENARIO_CREATORS, create_baseline_scenario


@pytest.mark.parametrize("scenario_id", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
def test_scenario_metrics_equivalence(scenario_id: int) -> None:
    """Test key architectural metrics for each scenario.

    This is a more focused test that checks specific metrics that should
    be stable across both demo approaches.

    Args:
        scenario_id: Scenario number (1-10)
    """
    scenario_def = ALL_SCENARIOS[scenario_id]
    creator = SCENARIO_CREATORS.get(scenario_id)

    if creator is None:
        pytest.skip(f"Scenario {scenario_id} not yet implemented")

    # Use correct baseline for each scenario using BASELINE_CREATORS registry
    baseline_creator = BASELINE_CREATORS.get(scenario_id)
    if baseline_creator is None:
        pytest.skip(f"Baseline creator for scenario {scenario_id} not found")

    baseline, _, _, _ = baseline_creator()
    current, _, _, _ = creator()
    delta = compare_dsm_results(baseline, current, compute_precise_impact=True)

    # Verify basic cycle counting
    expected_cycles_delta = scenario_def.expected_outcome.cycles_delta
    actual_cycles_delta = delta.cycles_added - delta.cycles_removed

    assert actual_cycles_delta == expected_cycles_delta, (
        f"Scenario {scenario_id}: Expected cycle delta of {expected_cycles_delta}, "
        f"got {actual_cycles_delta} (added={delta.cycles_added}, removed={delta.cycles_removed})"
    )

    # Verify header changes
    if scenario_def.expected_outcome.has_new_headers:
        assert len(delta.headers_added) > 0, f"Scenario {scenario_id}: Expected new headers but found none"

    if scenario_def.expected_outcome.has_removed_headers:
        assert len(delta.headers_removed) > 0, f"Scenario {scenario_id}: Expected removed headers but found none"


def test_baseline_scenario_stability() -> None:
    """Test that baseline scenario is stable and cycle-free."""
    baseline, _, _, _ = create_baseline_scenario()

    # Baseline should have no cycles
    assert len(baseline.cycles) == 0, f"Baseline has {len(baseline.cycles)} cycles, expected 0"

    # Baseline should have expected number of headers
    assert len(baseline.metrics) == 10, f"Baseline has {len(baseline.metrics)} headers, expected 10"

    # Baseline should have multiple layers
    assert len(baseline.layers) >= 3, f"Baseline has {len(baseline.layers)} layers, expected at least 3"


def test_all_scenarios_defined() -> None:
    """Test that all 10 scenarios are defined in scenario_definitions.py."""
    from lib.scenario_definitions import get_all_scenario_ids

    scenario_ids = get_all_scenario_ids()
    assert len(scenario_ids) == 10, f"Expected 10 scenarios, found {len(scenario_ids)}"
    assert scenario_ids == list(range(1, 11)), "Scenario IDs should be 1-10"


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
