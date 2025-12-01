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
from typing import Any


def normalize_dsm_results_paths(dsm_results: Any, repo_path: str) -> Any:
    """Normalize DSM results to use relative paths (relative to include directory).

    This allows comparison between:
    - Git-based analysis (absolute paths like /tmp/.../include/Module0/Header0.hpp)
    - Programmatic scenarios (relative paths like Module0/Header0.hpp)

    Args:
        dsm_results: DSM analysis results with potentially absolute paths
        repo_path: Repository root path

    Returns:
        DSM results with normalized relative paths
    """
    import os
    from collections import defaultdict

    include_dir = os.path.join(repo_path, "include")

    def normalize_path(path: str) -> str:
        """Convert absolute path to relative (from include dir) if applicable."""
        if path.startswith(include_dir + os.sep):
            return os.path.relpath(path, include_dir)
        return path

    # Create normalized copies
    normalized_headers = [normalize_path(h) for h in dsm_results.sorted_headers]
    normalized_metrics = {normalize_path(k): v for k, v in dsm_results.metrics.items()}
    normalized_header_to_headers = defaultdict(set)
    for header, deps in dsm_results.header_to_headers.items():
        normalized_header_to_headers[normalize_path(header)] = {normalize_path(d) for d in deps}

    # Update the DSM results object with normalized paths
    dsm_results.sorted_headers = normalized_headers
    dsm_results.metrics = normalized_metrics
    dsm_results.header_to_headers = dict(normalized_header_to_headers)

    # Normalize header_to_layer if present
    if hasattr(dsm_results, "header_to_layer") and dsm_results.header_to_layer:
        dsm_results.header_to_layer = {normalize_path(k): v for k, v in dsm_results.header_to_layer.items()}

    # Normalize headers_in_cycles if present
    if hasattr(dsm_results, "headers_in_cycles") and dsm_results.headers_in_cycles:
        dsm_results.headers_in_cycles = {normalize_path(h) for h in dsm_results.headers_in_cycles}

    return dsm_results


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

    # Normalize git-based results to use relative paths for comparison
    git_current_dsm = normalize_dsm_results_paths(git_current_dsm, str(repo_path))
    git_baseline_dsm = normalize_dsm_results_paths(git_baseline_dsm, str(repo_path))

    # Compare baseline and current using git-based analysis
    git_based_delta = compare_dsm_results(git_baseline_dsm, git_current_dsm)  # NOW COMPARE: DSM-direct vs Git-based analysis results
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
