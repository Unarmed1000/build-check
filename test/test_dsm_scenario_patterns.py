#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test DSM scenario architectural patterns.

This test suite validates that DSM-direct analysis correctly identifies
architectural patterns (cycles, coupling, stability) for each scenario.
"""

import sys
from pathlib import Path

import pytest

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.dsm_analysis import compare_dsm_results
from lib.scenario_definitions import ALL_SCENARIOS
from lib.scenario_creators import BASELINE_CREATORS, SCENARIO_CREATORS
from lib.scenario_test_utils import ArchitecturalMetrics


@pytest.mark.parametrize("scenario_id", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
def test_dsm_scenario_architectural_patterns(scenario_id: int) -> None:
    """Test that DSM-direct analysis produces expected architectural patterns.

    This test validates that programmatic DSM analysis correctly identifies
    architectural changes for each scenario.

    Args:
        scenario_id: Scenario number (1-10)
    """
    # Get scenario definition
    scenario_def = ALL_SCENARIOS[scenario_id]
    assert scenario_def is not None, f"Scenario {scenario_id} not defined"

    # Get scenario creator
    creator = SCENARIO_CREATORS.get(scenario_id)
    if creator is None:
        pytest.skip(f"Scenario {scenario_id} not yet implemented")

    # Create baseline and current scenarios using the BASELINE_CREATORS registry
    baseline_creator = BASELINE_CREATORS.get(scenario_id)
    if baseline_creator is None:
        pytest.skip(f"Baseline creator for scenario {scenario_id} not found")

    baseline, _, _, _ = baseline_creator()
    current, _, _, _ = creator()

    # Compare and extract metrics
    delta = compare_dsm_results(baseline, current, compute_precise_impact=True)
    metrics = ArchitecturalMetrics(delta, baseline, current)

    # Check metrics match expected outcomes
    matches, mismatches = metrics.matches_expected(scenario_def, tolerance_pct=scenario_def.tolerance_pct)

    # Report results
    if not matches:
        error_msg = f"Scenario {scenario_id} ({scenario_def.name}) failed:\n"
        error_msg += "\n".join(f"  - {m}" for m in mismatches)
        pytest.fail(error_msg)


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
