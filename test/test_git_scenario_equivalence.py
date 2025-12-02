#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test git-based DSM scenario equivalence.

This test suite validates that git-based DSM analysis (using physical git repos)
produces equivalent results to DSM-direct analysis (programmatic graphs).
"""

import sys
from pathlib import Path
from typing import Dict, List

import pytest

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.dsm_analysis import compare_dsm_results, run_dsm_analysis
from lib.scenario_creators import BASELINE_CREATORS, SCENARIO_CREATORS, create_git_repo_from_scenario
from lib.git_utils import reconstruct_head_graph
from lib.clang_utils import build_include_graph
from typing import Any, Generator


@pytest.fixture(autouse=True)
def clear_module_caches() -> Generator[None, None, None]:
    """Clear any module-level caches between tests."""
    import importlib
    import sys

    # Reload modules that might have caches
    if "lib.clang_utils" in sys.modules:
        importlib.reload(sys.modules["lib.clang_utils"])
    if "lib.ninja_utils" in sys.modules:
        importlib.reload(sys.modules["lib.ninja_utils"])

    yield

    # Cleanup after test
    pass


def log_test_details(scenario_id: int, repo_path: Path, scan_result: Any, current_dsm: Any, baseline_dsm: Any, delta: Any, log_suffix: str) -> None:
    """Log detailed test information for debugging."""
    import json

    log_file = f"/tmp/test_scenario_{scenario_id}_{log_suffix}.log"

    with open(log_file, "w") as f:
        f.write(f"=== Test Scenario {scenario_id} - {log_suffix} ===\n\n")
        f.write(f"Repo path: {repo_path}\n")
        f.write(f"Repo exists: {repo_path.exists()}\n\n")

        f.write(f"Scan result:\n")
        f.write(f"  All headers: {len(scan_result.all_headers)}\n")
        f.write(f"  Total edges: {sum(len(deps) for deps in scan_result.include_graph.values())}\n")
        f.write(f"  Source files: {len(scan_result.source_to_deps)}\n")

        # File type counts
        from lib.clang_utils import FileType

        type_counts = {ft: 0 for ft in FileType}
        for ft in scan_result.file_types.values():
            type_counts[ft] += 1
        f.write(f"  File types: {dict(type_counts)}\n\n")

        # Sample headers
        f.write(f"Sample headers (first 10):\n")
        for i, h in enumerate(sorted(scan_result.all_headers)[:10]):
            ft = scan_result.file_types.get(h, "UNKNOWN")
            f.write(f"  {i+1}. {h} [{ft}]\n")
        f.write("\n")

        f.write(f"Current DSM:\n")
        f.write(f"  Headers: {len(current_dsm.metrics)}\n")
        f.write(f"  Cycles: {len(current_dsm.cycles)}\n")
        f.write(f"  Sample metrics (first 5):\n")
        for header, metrics in list(current_dsm.metrics.items())[:5]:
            f.write(f"    {header}: coupling={metrics.coupling}, fan_in={metrics.fan_in}, fan_out={metrics.fan_out}\n")
        f.write("\n")

        f.write(f"Baseline DSM:\n")
        f.write(f"  Headers: {len(baseline_dsm.metrics)}\n")
        f.write(f"  Cycles: {len(baseline_dsm.cycles)}\n\n")

        f.write(f"Delta:\n")
        f.write(f"  Headers added: {len(delta.headers_added)}\n")
        f.write(f"  Headers removed: {len(delta.headers_removed)}\n")
        f.write(f"  Coupling increased: {dict(delta.coupling_increased)}\n")
        f.write(f"  Coupling decreased: {dict(delta.coupling_decreased)}\n")

        coupling_increase = sum(delta.coupling_increased.values())
        coupling_decrease = sum(abs(v) for v in delta.coupling_decreased.values())
        net = coupling_increase - coupling_decrease
        f.write(f"  Net coupling change: {net}\n\n")

        # Build.ninja check
        build_ninja = repo_path / "build.ninja"
        if build_ninja.exists():
            f.write(f"build.ninja exists, first 50 lines:\n")
            with open(build_ninja) as bn:
                for i, line in enumerate(bn):
                    if i < 50:
                        f.write(f"  {line.rstrip()}\n")
                    else:
                        break

    print(f"Logged details to {log_file}")


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
    import shutil

    # Get DSM-direct results for comparison baseline
    baseline_creator = BASELINE_CREATORS.get(scenario_id)
    scenario_creator = SCENARIO_CREATORS.get(scenario_id)

    if not baseline_creator or not scenario_creator:
        pytest.skip(f"Creators for scenario {scenario_id} not found")

    dsm_direct_baseline, _, _, _ = baseline_creator()
    dsm_direct_current, _, _, _ = scenario_creator()
    dsm_direct_delta = compare_dsm_results(dsm_direct_baseline, dsm_direct_current)

    # Create physical git repo with baseline committed and current in working tree
    # Use unique directory for complete test isolation
    import uuid

    unique_id = uuid.uuid4().hex[:8]
    repo_path = tmp_path / f"scenario_{scenario_id}_repo_{unique_id}"
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
    baseline_all_headers, baseline_header_to_headers, baseline_sources, baseline_project_root = reconstruct_head_graph(
        working_tree_headers=current_all_headers, working_tree_graph=current_header_to_headers, base_ref="HEAD", repo_path=str(repo_path)
    )

    # DEBUG: Log what was reconstructed from HEAD
    if scenario_id in [8, 9]:
        import os

        log_suffix = f"after_test_8" if scenario_id == 9 and os.path.exists("/tmp/test_scenario_8_isolated.log") else "isolated"
        debug_log = f"/tmp/test_scenario_{scenario_id}_{log_suffix}_baseline_reconstruction.log"
        with open(debug_log, "w") as f:
            f.write(f"=== Baseline Reconstruction Debug - Scenario {scenario_id} ===\n\n")
            f.write(f"Working tree (current):\n")
            f.write(f"  Headers: {len(current_all_headers)}\n")
            f.write(f"  Sample headers (first 10):\n")
            for h in sorted(current_all_headers)[:10]:
                f.write(f"    {h}\n")
            f.write(f"\nBaseline from HEAD:\n")
            f.write(f"  Headers: {len(baseline_all_headers)}\n")
            f.write(f"  Sources: {len(baseline_sources)}\n")
            f.write(f"  Project root: {baseline_project_root}\n")
            f.write(f"  Sample headers (first 10):\n")
            for h in sorted(baseline_all_headers)[:10]:
                f.write(f"    {h}\n")
            f.write(f"\n  Sample sources (first 10):\n")
            for s in sorted(baseline_sources)[:10]:
                f.write(f"    {s}\n")
            f.write(f"\n  Graph edges: {sum(len(v) for v in baseline_header_to_headers.values())}\n")
            f.write(f"  Sample edges (first 10 headers):\n")
            for h in sorted(baseline_header_to_headers.keys())[:10]:
                deps = baseline_header_to_headers[h]
                f.write(f"    {h} -> {deps}\n")
        print(f"Baseline reconstruction logged to {debug_log}")

    # Derive baseline headers from sources
    baseline_headers_derived = [src.replace("/src/", "/include/").replace(".cpp", ".hpp") for src in baseline_sources]

    # Build source_to_deps for baseline
    baseline_source_to_deps: Dict[str, List[str]] = {}
    for header in baseline_all_headers:
        source_file = header.replace("/include/", "/src/").replace(".hpp", ".cpp")
        header_deps: List[str] = [header]
        if header in baseline_header_to_headers:
            header_deps.extend(list(baseline_header_to_headers[header]))
        baseline_source_to_deps[source_file] = header_deps

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

    # Log detailed information for debugging (especially for scenarios 8 and 9)
    if scenario_id in [8, 9]:
        import os

        log_suffix = f"after_test_8" if scenario_id == 9 and os.path.exists("/tmp/test_scenario_8_isolated.log") else "isolated"
        log_test_details(scenario_id, repo_path, scan_result, git_current_dsm, git_baseline_dsm, git_based_delta, log_suffix)

    assert dsm_coupling_net == git_coupling_net, f"Coupling net change mismatch: DSM-direct={dsm_coupling_net}, Git-based={git_coupling_net}"

    # Compare cycle counts
    dsm_cycles = len(dsm_direct_current.cycles)
    git_cycles = len(git_current_dsm.cycles)
    assert dsm_cycles == git_cycles, f"Cycle count mismatch: DSM-direct={dsm_cycles}, Git-based={git_cycles}"

    # Compare header counts
    dsm_header_count = len(dsm_direct_current.metrics)
    git_header_count = len(git_current_dsm.metrics)
    assert dsm_header_count == git_header_count, f"Header count mismatch: DSM-direct={dsm_header_count}, Git-based={git_header_count}"

    # Explicit cleanup - remove the test repo directory
    if repo_path.exists():
        shutil.rmtree(repo_path, ignore_errors=True)


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
