#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test git-based DSM scenario equivalence.

This test suite validates that git-based DSM analysis (using physical git repos)
produces equivalent results to DSM-direct analysis (programmatic graphs).
"""

import sys
from pathlib import Path

import pytest

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.dsm_analysis import compare_dsm_results, run_dsm_analysis
from lib.scenario_creators import BASELINE_CREATORS, SCENARIO_CREATORS, create_git_repo_from_scenario
from lib.git_utils import reconstruct_head_graph
from lib.clang_utils import build_include_graph


@pytest.mark.parametrize("scenario_id", list(SCENARIO_CREATORS.keys()))
def test_git_scenario_equivalence(scenario_id: int, tmp_path: Path) -> None:
    """Test that git-based DSM analysis produces equivalent results to DSM-direct.

    Creates actual git repositories with baseline committed to HEAD and current
    state in working tree, runs FULL git-based DSM analysis using the same
    build_include_graph pipeline as buildCheckDSM.py, and compares metrics.
    """
    # Get DSM-direct results for comparison baseline
    baseline_creator = BASELINE_CREATORS.get(scenario_id)
    scenario_creator = SCENARIO_CREATORS.get(scenario_id)

    if not baseline_creator or not scenario_creator:
        pytest.skip(f"Creators for scenario {scenario_id} not found")

    dsm_direct_baseline, _, _, _ = baseline_creator()
    dsm_direct_current, _, _, _ = scenario_creator()
    dsm_direct_delta = compare_dsm_results(dsm_direct_baseline, dsm_direct_current)

    # Create physical git repo with baseline committed and current in working tree
    repo_path = tmp_path / f"scenario_{scenario_id}_repo"
    create_git_repo_from_scenario(scenario_id=scenario_id, repo_path=str(repo_path), baseline_as_head=True, current_as_working=True)

    # Verify git repo structure
    git_dir = repo_path / ".git"
    assert git_dir.exists(), f"Git directory not created"

    compile_commands_path = repo_path / "compile_commands.json"
    assert compile_commands_path.exists(), f"compile_commands.json not found"

    # Use the SAME pipeline as buildCheckDSM.py - build_include_graph on the repo
    # This parses compile_commands.json and uses clang-scan-deps (or falls back to direct parsing)
    scan_result = build_include_graph(str(repo_path), verbose=False)

    current_all_headers = scan_result.all_headers
    current_header_to_headers = scan_result.include_graph
    current_source_to_deps = scan_result.source_to_deps

    # Run DSM analysis on current working tree
    git_current_dsm = run_dsm_analysis(
        all_headers=current_all_headers,
        header_to_headers=current_header_to_headers,
        compute_layers=True,
        show_progress=False,
        source_to_deps=current_source_to_deps,
    )

    # Reconstruct baseline (HEAD) dependency graph using git utils
    baseline_all_headers, baseline_header_to_headers = reconstruct_head_graph(
        working_tree_headers=current_all_headers, working_tree_graph=current_header_to_headers, base_ref="HEAD", repo_path=str(repo_path)
    )

    # Build source_to_deps for baseline
    baseline_source_to_deps = {}
    for header in baseline_all_headers:
        source_file = header.replace("/include/", "/src/").replace(".hpp", ".cpp")
        deps = [header]
        if header in baseline_header_to_headers:
            deps.extend(list(baseline_header_to_headers[header]))
        baseline_source_to_deps[source_file] = deps

    # Run DSM analysis on baseline (HEAD)
    git_baseline_dsm = run_dsm_analysis(
        all_headers=baseline_all_headers,
        header_to_headers=baseline_header_to_headers,
        compute_layers=True,
        show_progress=False,
        source_to_deps=baseline_source_to_deps,
    )

    # Compare baseline and current using git-based analysis
    git_based_delta = compare_dsm_results(git_baseline_dsm, git_current_dsm)

    # NOW COMPARE: DSM-direct vs Git-based analysis results
    # Both should produce equivalent architectural metrics

    # Compare coupling changes (calculate from delta)
    dsm_coupling_increase = sum(dsm_direct_delta.coupling_increased.values())
    dsm_coupling_decrease = sum(abs(v) for v in dsm_direct_delta.coupling_decreased.values())
    dsm_coupling_net = dsm_coupling_increase - dsm_coupling_decrease

    git_coupling_increase = sum(git_based_delta.coupling_increased.values())
    git_coupling_decrease = sum(abs(v) for v in git_based_delta.coupling_decreased.values())
    git_coupling_net = git_coupling_increase - git_coupling_decrease

    assert dsm_coupling_net == git_coupling_net, f"Coupling net change mismatch: DSM-direct={dsm_coupling_net}, Git-based={git_coupling_net}"

    # Compare cycle counts
    dsm_cycles = len(dsm_direct_current.cycles)
    git_cycles = len(git_current_dsm.cycles)
    assert dsm_cycles == git_cycles, f"Cycle count mismatch: DSM-direct={dsm_cycles}, Git-based={git_cycles}"

    # Compare header counts
    dsm_header_count = len(dsm_direct_current.metrics)
    git_header_count = len(git_current_dsm.metrics)
    assert dsm_header_count == git_header_count, f"Header count mismatch: DSM-direct={dsm_header_count}, Git-based={git_header_count}"


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
