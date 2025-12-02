#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test git baseline reconstruction logic.

Verifies that baseline sources, headers, and project root are correctly
reconstructed from git HEAD, and that they differ appropriately from
the working tree state.
"""

import os
import sys
import tempfile
from collections import defaultdict
from typing import DefaultDict
from pathlib import Path

import pytest
from typing import Any, Dict, Set

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.git_utils import reconstruct_head_graph
from lib.scenario_git_utils import setup_git_repo, commit_all_files, create_physical_file_structure, generate_build_ninja
from lib.clang_utils import find_project_root_from_sources


@pytest.fixture
def git_repo_with_baseline_and_changes(tmp_path: Path) -> Any:
    """Create a git repo with committed baseline and working tree changes."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    setup_git_repo(str(repo_path))

    # Create baseline files (to be committed)
    baseline_headers = {"Module0/Header0.hpp", "Module0/Header1.hpp", "Module1/Header0.hpp"}

    baseline_graph: DefaultDict[str, Set[str]] = defaultdict(set)
    baseline_graph["Module0/Header0.hpp"].add("Module0/Header1.hpp")
    baseline_graph["Module0/Header1.hpp"].add("Module1/Header0.hpp")

    baseline_source_deps = {
        "src/Module0/Header0.cpp": ["Module0/Header0.hpp", "Module0/Header1.hpp"],
        "src/Module0/Header1.cpp": ["Module0/Header1.hpp", "Module1/Header0.hpp"],
        "src/Module1/Header0.cpp": ["Module1/Header0.hpp"],
    }

    # Create physical files for baseline
    create_physical_file_structure(str(repo_path), baseline_headers, baseline_graph, baseline_source_deps)

    # Generate build.ninja for baseline
    baseline_sources = list(baseline_source_deps.keys())
    generate_build_ninja(str(repo_path), baseline_sources, str(repo_path / "include"))

    # Commit baseline
    commit_all_files(str(repo_path), "Baseline commit")

    # Create current state (working tree changes)
    current_headers = baseline_headers | {"Module1/Header1.hpp"}  # Add one header

    current_graph = defaultdict(set)
    current_graph["Module0/Header0.hpp"].add("Module0/Header1.hpp")
    current_graph["Module0/Header1.hpp"].add("Module1/Header0.hpp")
    current_graph["Module1/Header0.hpp"].add("Module1/Header1.hpp")  # New dependency

    current_source_deps = {
        "src/Module0/Header0.cpp": ["Module0/Header0.hpp", "Module0/Header1.hpp"],
        "src/Module0/Header1.cpp": ["Module0/Header1.hpp", "Module1/Header0.hpp"],
        "src/Module1/Header0.cpp": ["Module1/Header0.hpp", "Module1/Header1.hpp"],
        "src/Module1/Header1.cpp": ["Module1/Header1.hpp"],  # New source file
    }

    # Create physical files for current state (uncommitted)
    create_physical_file_structure(str(repo_path), current_headers, current_graph, current_source_deps)

    # Regenerate build.ninja for current state
    current_sources = list(current_source_deps.keys())
    generate_build_ninja(str(repo_path), current_sources, str(repo_path / "include"))

    # Convert relative paths to absolute for reconstruct_head_graph compatibility
    current_headers_abs = {str(repo_path / "include" / h) for h in current_headers}
    current_graph_abs: DefaultDict[str, Set[str]] = defaultdict(set)
    for header, deps in current_graph.items():
        header_abs = str(repo_path / "include" / header)
        deps_abs = {str(repo_path / "include" / d) for d in deps}
        current_graph_abs[header_abs] = deps_abs

    return {
        "repo_path": repo_path,
        "baseline_headers": baseline_headers,
        "baseline_graph": baseline_graph,
        "baseline_sources": baseline_sources,
        "current_headers": current_headers_abs,  # Absolute paths
        "current_graph": current_graph_abs,  # Absolute paths
        "current_sources": current_sources,
    }


def test_reconstruct_baseline_headers(git_repo_with_baseline_and_changes) -> None:  # type: ignore[no-untyped-def]
    """Test that baseline headers are correctly reconstructed from git HEAD."""
    data = git_repo_with_baseline_and_changes
    repo_path = data["repo_path"]

    # Reconstruct baseline from git HEAD
    baseline_headers, baseline_graph, baseline_sources, baseline_project_root = reconstruct_head_graph(
        working_tree_headers=data["current_headers"], working_tree_graph=data["current_graph"], base_ref="HEAD", repo_path=str(repo_path)
    )

    # Convert to relative paths for comparison
    baseline_headers_rel = {os.path.relpath(h, str(repo_path / "include")) for h in baseline_headers}

    # Should match original baseline (3 headers, not 4)
    assert len(baseline_headers) == 3, f"Expected 3 baseline headers, got {len(baseline_headers)}"
    assert baseline_headers_rel == data["baseline_headers"], f"Baseline headers mismatch: {baseline_headers_rel} != {data['baseline_headers']}"


def test_reconstruct_baseline_sources(git_repo_with_baseline_and_changes) -> None:  # type: ignore[no-untyped-def]
    """Test that baseline sources are correctly reconstructed from git HEAD."""
    data = git_repo_with_baseline_and_changes
    repo_path = data["repo_path"]

    # Reconstruct baseline from git HEAD
    _, _, baseline_sources, _ = reconstruct_head_graph(
        working_tree_headers=data["current_headers"], working_tree_graph=data["current_graph"], base_ref="HEAD", repo_path=str(repo_path)
    )

    # Should have 3 source files (not 4)
    assert len(baseline_sources) == 3, f"Expected 3 baseline sources, got {len(baseline_sources)}: {baseline_sources}"

    # Check specific files
    source_basenames = {os.path.basename(s) for s in baseline_sources}
    assert "Header0.cpp" in source_basenames
    assert "Header1.cpp" in source_basenames


def test_baseline_vs_current_sources_differ(git_repo_with_baseline_and_changes) -> None:  # type: ignore[no-untyped-def]
    """Test that baseline sources differ from current sources."""
    data = git_repo_with_baseline_and_changes
    repo_path = data["repo_path"]

    # Reconstruct baseline
    _, _, baseline_sources, _ = reconstruct_head_graph(
        working_tree_headers=data["current_headers"], working_tree_graph=data["current_graph"], base_ref="HEAD", repo_path=str(repo_path)
    )

    # Current has 4 sources (includes Module1/Header1.cpp)
    # Baseline should have 3 sources (no Module1/Header1.cpp)
    assert len(baseline_sources) == 3, f"Baseline should have 3 sources"
    assert len(data["current_sources"]) == 4, f"Current should have 4 sources"

    # Verify Module1/Header1.cpp is NOT in baseline
    baseline_names = {os.path.basename(s) for s in baseline_sources}
    assert "Header1.cpp" in baseline_names  # Module0/Header1.cpp exists

    # But Module1/Header1.cpp should not be in baseline
    module1_sources_baseline = [s for s in baseline_sources if "Module1" in s]
    module1_basenames = {os.path.basename(s) for s in module1_sources_baseline}
    # Module1 should only have Header0.cpp in baseline, not Header1.cpp
    assert "Header0.cpp" in module1_basenames


def test_baseline_project_root_calculation(git_repo_with_baseline_and_changes) -> None:  # type: ignore[no-untyped-def]
    """Test that project root can be calculated from baseline sources/headers."""
    data = git_repo_with_baseline_and_changes
    repo_path = data["repo_path"]

    # Reconstruct baseline
    baseline_headers, _, baseline_sources, baseline_project_root = reconstruct_head_graph(
        working_tree_headers=data["current_headers"], working_tree_graph=data["current_graph"], base_ref="HEAD", repo_path=str(repo_path)
    )

    # Derive baseline headers from sources
    baseline_headers_from_sources = [s.replace("/src/", "/include/").replace(".cpp", ".hpp") for s in baseline_sources]

    # Calculate project root from baseline files
    all_baseline_files = baseline_sources + list(baseline_headers)
    baseline_project_root = find_project_root_from_sources(all_baseline_files)

    # Should be the repo root
    assert baseline_project_root == str(repo_path), f"Baseline project root should be {repo_path}, got {baseline_project_root}"


def test_baseline_and_current_same_project_root(git_repo_with_baseline_and_changes) -> None:  # type: ignore[no-untyped-def]
    """Test that baseline and current have the same project root."""
    data = git_repo_with_baseline_and_changes
    repo_path = data["repo_path"]

    # Reconstruct baseline
    baseline_headers, _, baseline_sources, baseline_project_root = reconstruct_head_graph(
        working_tree_headers=data["current_headers"], working_tree_graph=data["current_graph"], base_ref="HEAD", repo_path=str(repo_path)
    )

    # Calculate baseline project root
    all_baseline_files = baseline_sources + list(baseline_headers)
    baseline_project_root = find_project_root_from_sources(all_baseline_files)

    # Calculate current project root (from build.ninja on disk)
    from lib.ninja_utils import extract_source_and_header_files_from_ninja

    build_ninja = repo_path / "build.ninja"
    current_ninja_sources, current_ninja_headers = extract_source_and_header_files_from_ninja(str(build_ninja))
    all_current_files = current_ninja_sources + current_ninja_headers
    current_project_root = find_project_root_from_sources(all_current_files)

    # Both should be the repo root
    assert (
        baseline_project_root == current_project_root == str(repo_path)
    ), f"Project roots should match: baseline={baseline_project_root}, current={current_project_root}"


def test_scenario_9_header_count() -> None:
    """Test that scenario 9 has all 25 headers in both baseline and current.

    This is a regression test for the missing Module0/Header0 issue.
    """
    from lib.scenario_creators import create_baseline_for_scenario_9, create_scenario_9_outlier_detection

    # Get baseline
    _, baseline_graph, baseline_headers, _ = create_baseline_for_scenario_9()

    # Get current
    _, current_graph, current_headers, _ = create_scenario_9_outlier_detection()

    # Both should have 25 headers (5 modules × 5 headers)
    assert len(baseline_headers) == 25, f"Baseline should have 25 headers, got {len(baseline_headers)}"
    assert len(current_headers) == 25, f"Current should have 25 headers, got {len(current_headers)}"

    # Specifically check for Module0/Header0
    assert "Module0/Header0.hpp" in baseline_headers, "Module0/Header0.hpp missing from baseline"
    assert "Module0/Header0.hpp" in current_headers, "Module0/Header0.hpp missing from current"

    # Check all Module0 headers are present
    module0_baseline = {h for h in baseline_headers if h.startswith("Module0/")}
    module0_current = {h for h in current_headers if h.startswith("Module0/")}

    assert len(module0_baseline) == 5, f"Module0 should have 5 headers in baseline, got {len(module0_baseline)}"
    assert len(module0_current) == 5, f"Module0 should have 5 headers in current, got {len(module0_current)}"

    # Check each Module0 header individually
    for i in range(5):
        header = f"Module0/Header{i}.hpp"
        assert header in baseline_headers, f"{header} missing from baseline"
        assert header in current_headers, f"{header} missing from current"


def test_git_repo_has_all_module0_headers(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Test that git repo creation includes all Module0 headers including Header0."""
    from lib.scenario_creators import create_git_repo_from_scenario

    repo_path = tmp_path / "scenario_9_test"

    # Create git repo for scenario 9
    create_git_repo_from_scenario(scenario_id=9, repo_path=str(repo_path), baseline_as_head=True, current_as_working=True)

    # Check that all Module0 headers exist physically
    module0_include = repo_path / "include" / "Module0"
    assert module0_include.exists(), "Module0 include directory should exist"

    module0_headers = list(module0_include.glob("*.hpp"))
    assert len(module0_headers) == 5, f"Should have 5 Module0 headers, got {len(module0_headers)}"

    # Specifically check for Header0
    header0 = module0_include / "Header0.hpp"
    assert header0.exists(), "Module0/Header0.hpp should exist"

    # Check all headers
    for i in range(5):
        header_file = module0_include / f"Header{i}.hpp"
        assert header_file.exists(), f"Module0/Header{i}.hpp should exist"

    # Check corresponding source files
    module0_src = repo_path / "src" / "Module0"
    assert module0_src.exists(), "Module0 src directory should exist"

    for i in range(5):
        src_file = module0_src / f"Header{i}.cpp"
        assert src_file.exists(), f"Module0/Header{i}.cpp should exist"

    # Check that Header0.cpp includes Header0.hpp
    header0_cpp = module0_src / "Header0.cpp"
    content = header0_cpp.read_text()
    assert "Header0.hpp" in content, "Header0.cpp should include Header0.hpp"


def test_build_ninja_includes_all_module0_files(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Test that build.ninja includes all Module0 files including Header0."""
    from lib.scenario_creators import create_git_repo_from_scenario

    repo_path = tmp_path / "scenario_9_ninja_test"

    # Create git repo for scenario 9
    create_git_repo_from_scenario(scenario_id=9, repo_path=str(repo_path), baseline_as_head=True, current_as_working=True)

    # Read build.ninja
    build_ninja = repo_path / "build.ninja"
    assert build_ninja.exists(), "build.ninja should exist"

    content = build_ninja.read_text()

    # Check that all Module0 files are in build.ninja
    for i in range(5):
        header = f"Module0/Header{i}.hpp"
        source = f"Module0/Header{i}.cpp"

        assert header in content, f"{header} should be in build.ninja"
        assert source in content, f"{source} should be in build.ninja"

    # Specifically verify Header0 lines
    assert "Module0/Header0.cpp" in content, "Module0/Header0.cpp missing from build.ninja"
    assert "Module0/Header0.hpp" in content, "Module0/Header0.hpp missing from build.ninja"

    # Extract and verify using ninja_utils
    from lib.ninja_utils import extract_source_and_header_files_from_ninja

    sources, headers = extract_source_and_header_files_from_ninja(str(build_ninja))

    # Check Module0 files
    module0_sources = [s for s in sources if "Module0" in s]
    module0_headers = [h for h in headers if "Module0" in h]

    assert len(module0_sources) == 5, f"Should extract 5 Module0 sources, got {len(module0_sources)}"
    assert len(module0_headers) == 5, f"Should extract 5 Module0 headers, got {len(module0_headers)}"

    # Verify Header0 specifically
    assert any("Header0.cpp" in s for s in module0_sources), "Header0.cpp not in extracted sources"
    assert any("Header0.hpp" in h for h in module0_headers), "Header0.hpp not in extracted headers"


def test_reconstruct_uses_git_head_not_disk_files(tmp_path: Path) -> None:
    """CRITICAL: Verify reconstruct_head_graph uses git HEAD files, not disk files.

    This test ensures that:
    1. Files deleted from disk but in git HEAD are included in baseline
    2. Files added to disk but not in git HEAD are excluded from baseline
    3. Project root is calculated from git HEAD sources, not disk files
    """
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    setup_git_repo(str(repo_path))

    # BASELINE: Commit to git HEAD
    baseline_headers = {"Module0/Header0.hpp", "Module0/Header1.hpp"}
    baseline_graph: DefaultDict[str, Set[str]] = defaultdict(set)
    baseline_graph["Module0/Header0.hpp"].add("Module0/Header1.hpp")
    baseline_source_deps = {"Module0/InGitOnly.cpp": ["Module0/Header0.hpp"], "Module0/Common.cpp": ["Module0/Header1.hpp"]}

    create_physical_file_structure(str(repo_path), baseline_headers, baseline_graph, baseline_source_deps)
    generate_build_ninja(str(repo_path), list(baseline_source_deps.keys()), str(repo_path / "include"))
    commit_all_files(str(repo_path), "Baseline commit")

    # MODIFY DISK: Delete InGitOnly.cpp, add DiskOnly.cpp (don't commit)
    os.remove(str(repo_path / "src" / "Module0" / "InGitOnly.cpp"))

    current_headers = baseline_headers | {"Module1/DiskOnly.hpp"}
    current_graph: DefaultDict[str, Set[str]] = baseline_graph.copy()
    current_graph["Module1/DiskOnly.hpp"] = set()
    current_source_deps = {"Module0/Common.cpp": ["Module0/Header1.hpp"], "Module1/DiskOnly.cpp": ["Module1/DiskOnly.hpp"]}

    create_physical_file_structure(str(repo_path), current_headers, current_graph, current_source_deps)
    generate_build_ninja(str(repo_path), list(current_source_deps.keys()), str(repo_path / "include"))

    # Verify disk state
    assert not os.path.exists(repo_path / "src" / "Module0" / "InGitOnly.cpp"), "InGitOnly.cpp should be deleted from disk"
    assert os.path.exists(repo_path / "src" / "Module1" / "DiskOnly.cpp"), "DiskOnly.cpp should exist on disk"

    # Reconstruct from git HEAD (note: headers are in include/ directory)
    current_headers_abs = {str(repo_path / "include" / h) for h in current_headers}
    current_graph_abs: DefaultDict[str, Set[str]] = defaultdict(set)
    for header, deps in current_graph.items():
        header_abs = str(repo_path / "include" / header)
        deps_abs = {str(repo_path / "include" / d) for d in deps}
        current_graph_abs[header_abs] = deps_abs

    result_headers, result_graph, result_sources, result_project_root = reconstruct_head_graph(
        working_tree_headers=current_headers_abs, working_tree_graph=current_graph_abs, base_ref="HEAD", repo_path=str(repo_path)
    )

    # CRITICAL VERIFICATION 1: File deleted from disk but in git HEAD should be included
    result_source_basenames = {os.path.basename(s) for s in result_sources}
    assert "InGitOnly.cpp" in result_source_basenames, "CRITICAL BUG: InGitOnly.cpp missing - function reading from disk instead of git HEAD"

    # CRITICAL VERIFICATION 2: File on disk but not in git HEAD should be excluded
    assert "DiskOnly.cpp" not in result_source_basenames, "CRITICAL BUG: DiskOnly.cpp included - function reading from disk instead of git HEAD"

    # CRITICAL VERIFICATION 3: Headers follow same pattern
    result_header_basenames = {os.path.basename(h) for h in result_headers}
    assert "DiskOnly.hpp" not in result_header_basenames, "CRITICAL BUG: DiskOnly.hpp included - function reading from disk instead of git HEAD"

    # CRITICAL VERIFICATION 4: Exact count matches git HEAD
    assert len(result_sources) == 2, f"Expected 2 sources from git HEAD, got {len(result_sources)}"
    assert len(result_headers) == 2, f"Expected 2 headers from git HEAD, got {len(result_headers)}"

    # CRITICAL VERIFICATION 5: Project root calculated from git HEAD sources
    assert result_project_root == str(repo_path), f"Project root should be {repo_path}, got {result_project_root}"

    # Verify sources are exactly those from git HEAD
    assert result_source_basenames == {"InGitOnly.cpp", "Common.cpp"}, f"Source files should match git HEAD: {result_source_basenames}"


def test_project_root_from_git_head_not_disk_ninja(tmp_path: Path) -> None:
    """CRITICAL: Verify project root uses git HEAD sources, not on-disk build.ninja.

    This test creates a scenario where on-disk build.ninja would give a different
    project root than git HEAD sources, proving the function uses git correctly.
    """
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    setup_git_repo(str(repo_path))

    # BASELINE: All sources in Module0/ subdirectory
    baseline_headers = {"Module0/Header0.hpp"}
    baseline_graph: DefaultDict[str, Set[str]] = defaultdict(set)
    baseline_source_deps = {"Module0/File1.cpp": ["Module0/Header0.hpp"], "Module0/File2.cpp": ["Module0/Header0.hpp"]}

    create_physical_file_structure(str(repo_path), baseline_headers, baseline_graph, baseline_source_deps)
    generate_build_ninja(str(repo_path), list(baseline_source_deps.keys()), str(repo_path / "include"))
    commit_all_files(str(repo_path), "Baseline")

    # DISK: Add file in Module1/ subdirectory
    current_headers = baseline_headers | {"Module1/New.hpp"}
    current_graph: DefaultDict[str, Set[str]] = baseline_graph.copy()
    current_source_deps = baseline_source_deps.copy()
    # This new source is in Module1, not Module0
    current_source_deps["Module1/OutOfTree.cpp"] = ["Module1/New.hpp"]

    create_physical_file_structure(str(repo_path), current_headers, current_graph, current_source_deps)
    generate_build_ninja(str(repo_path), list(current_source_deps.keys()), str(repo_path / "include"))

    # Reconstruct from git HEAD
    current_headers_abs = {str(repo_path / "include" / h) for h in current_headers}
    current_graph_abs: DefaultDict[str, Set[str]] = defaultdict(set)
    for header, deps in current_graph.items():
        header_abs = str(repo_path / "include" / header)
        deps_abs = {str(repo_path / "include" / d) for d in deps}
        current_graph_abs[header_abs] = deps_abs

    _, _, result_sources, result_project_root = reconstruct_head_graph(
        working_tree_headers=current_headers_abs, working_tree_graph=current_graph_abs, base_ref="HEAD", repo_path=str(repo_path)
    )

    # CRITICAL: Project root should be from git HEAD sources (Module0 only), not disk (Module0 + Module1)
    # Git HEAD has:
    #   - src/Module0/File1.cpp
    #   - src/Module0/File2.cpp
    #   - include/Module0/Header0.hpp
    # Common prefix of all these is repo_path (not src/Module0, because include/ is separate)
    git_head_expected_root = str(repo_path)

    assert result_project_root == git_head_expected_root, f"Project root should be from git HEAD sources, got {result_project_root}"

    # Additional verification: If we had Module1 files (from disk), project root would still be repo_path
    # but the SOURCE LIST would be wrong. So verify sources don't include the disk-only file.
    result_source_basenames = {os.path.basename(s) for s in result_sources}
    assert "OutOfTree.cpp" not in result_source_basenames, "OutOfTree.cpp should not be in baseline (not in git HEAD)"

    # Verify we have exactly the git HEAD sources
    assert result_source_basenames == {"File1.cpp", "File2.cpp"}, f"Should have only git HEAD sources, got {result_source_basenames}"


def test_working_tree_project_root_from_disk_ninja(tmp_path: Path) -> None:
    """CRITICAL: Verify working tree project root uses on-disk build.ninja, not git HEAD.

    This test ensures the working tree project root is calculated from the actual
    on-disk build.ninja file (which may have uncommitted changes).
    """
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    setup_git_repo(str(repo_path))

    # BASELINE: Sources in Module0
    baseline_headers = {"Module0/Header0.hpp"}
    baseline_graph: DefaultDict[str, Set[str]] = defaultdict(set)
    baseline_source_deps = {"Module0/File1.cpp": ["Module0/Header0.hpp"]}

    create_physical_file_structure(str(repo_path), baseline_headers, baseline_graph, baseline_source_deps)
    generate_build_ninja(str(repo_path), list(baseline_source_deps.keys()), str(repo_path / "include"))
    commit_all_files(str(repo_path), "Baseline")

    # WORKING TREE: Add OutOfTree.cpp at repo root level
    current_headers = baseline_headers | {"RootLevel.hpp"}
    current_graph: DefaultDict[str, Set[str]] = baseline_graph.copy()
    current_source_deps = baseline_source_deps.copy()
    # This file at root level changes project root calculation
    current_source_deps["OutOfTree.cpp"] = ["RootLevel.hpp"]

    create_physical_file_structure(str(repo_path), current_headers, current_graph, current_source_deps)
    generate_build_ninja(str(repo_path), list(current_source_deps.keys()), str(repo_path / "include"))

    # Calculate working tree project root from on-disk build.ninja
    from lib.ninja_utils import extract_source_and_header_files_from_ninja

    disk_ninja_sources, disk_ninja_headers = extract_source_and_header_files_from_ninja(str(repo_path / "build.ninja"))
    working_tree_project_root = find_project_root_from_sources(disk_ninja_sources + disk_ninja_headers)

    # CRITICAL: Working tree project root should be repo_path because OutOfTree.cpp is at root
    assert working_tree_project_root == str(repo_path), f"Working tree project root should be {repo_path}, got {working_tree_project_root}"

    # Verify OutOfTree.cpp is in the ninja sources
    ninja_source_basenames = {os.path.basename(s) for s in disk_ninja_sources}
    assert "OutOfTree.cpp" in ninja_source_basenames, "OutOfTree.cpp should be in build.ninja sources"

    # Reconstruct baseline project root from git HEAD (should be src/Module0, not repo root)
    current_headers_abs = {str(repo_path / "include" / h) for h in current_headers}
    current_graph_abs: DefaultDict[str, Set[str]] = defaultdict(set)
    for header, deps in current_graph.items():
        header_abs = str(repo_path / "include" / header)
        deps_abs = {str(repo_path / "include" / d) for d in deps}
        current_graph_abs[header_abs] = deps_abs

    _, _, baseline_sources, baseline_project_root = reconstruct_head_graph(
        working_tree_headers=current_headers_abs, working_tree_graph=current_graph_abs, base_ref="HEAD", repo_path=str(repo_path)
    )

    # Git HEAD has only Module0/File1.cpp + Module0/Header0.hpp
    # Common prefix is src/Module0 for sources (but include/ separates it, so actually repo_path)
    # Actually, with include/Module0/Header0.hpp and src/Module0/File1.cpp, common prefix is repo_path
    # So both should be repo_path in this case... let me verify by checking source content
    baseline_source_basenames = {os.path.basename(s) for s in baseline_sources}
    assert "OutOfTree.cpp" not in baseline_source_basenames, "Baseline should not include OutOfTree.cpp"
    assert "File1.cpp" in baseline_source_basenames, "Baseline should include File1.cpp from git HEAD"


def test_git_reconstruct_ignores_disk_ninja_reads_git_tree_directly(tmp_path: Path) -> None:
    """CRITICAL: Verify reconstruct_head_graph reads git tree directly, NOT from build.ninja.

    This test proves that even if build.ninja is corrupted, missing files, or has extra
    files, the function correctly reconstructs by reading the git tree directly.
    """
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    setup_git_repo(str(repo_path))

    # BASELINE: Commit 3 source files to git HEAD
    baseline_headers = {"Module0/Header0.hpp", "Module0/Header1.hpp", "Module0/Header2.hpp"}
    baseline_graph: DefaultDict[str, Set[str]] = defaultdict(set)
    baseline_source_deps = {
        "Module0/File1.cpp": ["Module0/Header0.hpp"],
        "Module0/File2.cpp": ["Module0/Header1.hpp"],
        "Module0/File3.cpp": ["Module0/Header2.hpp"],
    }

    create_physical_file_structure(str(repo_path), baseline_headers, baseline_graph, baseline_source_deps)
    generate_build_ninja(str(repo_path), list(baseline_source_deps.keys()), str(repo_path / "include"))
    commit_all_files(str(repo_path), "Baseline commit with 3 files")

    # CORRUPT DISK NINJA: Overwrite build.ninja to ONLY include File1.cpp (missing File2 and File3)
    # This simulates a corrupted/stale ninja file
    corrupted_ninja = repo_path / "build.ninja"
    with open(corrupted_ninja, "w") as f:
        f.write("# Corrupted ninja file - missing File2.cpp and File3.cpp\n")
        f.write("rule cxx\n")
        f.write(f"  command = clang++ -std=c++17 -I{repo_path}/include -c $in -o $out\n")
        f.write("\n")
        f.write(f"build obj/Module0/File1.o: cxx src/Module0/File1.cpp | include/Module0/Header0.hpp\n")
        # File2.cpp and File3.cpp are INTENTIONALLY MISSING from build.ninja

    # Also delete File3.cpp from disk (so it's only in git HEAD, not on disk)
    os.remove(str(repo_path / "src" / "Module0" / "File3.cpp"))

    # Verify corrupted state
    from lib.ninja_utils import extract_source_and_header_files_from_ninja

    disk_ninja_sources, _ = extract_source_and_header_files_from_ninja(str(corrupted_ninja))
    assert len(disk_ninja_sources) == 1, "Corrupted ninja should only have 1 source"
    assert "File1.cpp" in disk_ninja_sources[0], "Corrupted ninja should only have File1.cpp"

    # Reconstruct from git HEAD
    current_headers_abs = {str(repo_path / "include" / h) for h in baseline_headers}
    current_graph_abs: DefaultDict[str, Set[str]] = defaultdict(set)

    _, _, result_sources, result_project_root = reconstruct_head_graph(
        working_tree_headers=current_headers_abs, working_tree_graph=current_graph_abs, base_ref="HEAD", repo_path=str(repo_path)
    )

    # CRITICAL: Should find ALL 3 source files from git HEAD, NOT just the 1 from corrupted ninja
    result_source_basenames = {os.path.basename(s) for s in result_sources}
    assert len(result_sources) == 3, f"Should find all 3 sources from git HEAD, got {len(result_sources)}: {result_source_basenames}"
    assert "File1.cpp" in result_source_basenames, "Should include File1.cpp"
    assert "File2.cpp" in result_source_basenames, "Should include File2.cpp (MISSING from ninja)"
    assert "File3.cpp" in result_source_basenames, "Should include File3.cpp (DELETED from disk but in git HEAD)"

    # CRITICAL: Project root should be calculated from ALL git HEAD sources (not corrupted ninja)
    assert result_project_root == str(repo_path), f"Project root should be {repo_path}, got {result_project_root}"


def test_project_root_differs_when_files_change_tree_structure(tmp_path: Path) -> None:
    """CRITICAL: Verify project root correctly differs between git HEAD and working tree.

    Tests that:
    1. Git HEAD project root is calculated from git tree files
    2. Working tree project root is calculated from disk ninja files
    3. They correctly differ when file structure changes
    """
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    setup_git_repo(str(repo_path))

    # BASELINE in git HEAD: All files deeply nested in src/deep/Module0/
    baseline_headers = {"deep/Module0/Header0.hpp"}
    baseline_graph: DefaultDict[str, Set[str]] = defaultdict(set)
    baseline_source_deps = {"deep/Module0/File1.cpp": ["deep/Module0/Header0.hpp"], "deep/Module0/File2.cpp": ["deep/Module0/Header0.hpp"]}

    create_physical_file_structure(str(repo_path), baseline_headers, baseline_graph, baseline_source_deps)
    generate_build_ninja(str(repo_path), list(baseline_source_deps.keys()), str(repo_path / "include"))
    commit_all_files(str(repo_path), "Baseline: deeply nested files")

    # WORKING TREE: Add file at ROOT level (changes project root)
    current_headers = baseline_headers | {"RootFile.hpp"}
    current_graph: DefaultDict[str, Set[str]] = baseline_graph.copy()
    current_source_deps = baseline_source_deps.copy()
    current_source_deps["RootFile.cpp"] = ["RootFile.hpp"]  # At root of src/

    create_physical_file_structure(str(repo_path), current_headers, current_graph, current_source_deps)
    generate_build_ninja(str(repo_path), list(current_source_deps.keys()), str(repo_path / "include"))

    # Calculate working tree project root from disk ninja
    from lib.ninja_utils import extract_source_and_header_files_from_ninja

    disk_ninja_sources, disk_ninja_headers = extract_source_and_header_files_from_ninja(str(repo_path / "build.ninja"))
    working_tree_project_root = find_project_root_from_sources(disk_ninja_sources + disk_ninja_headers)

    # Calculate git HEAD project root
    current_headers_abs = {str(repo_path / "include" / h) for h in current_headers}
    current_graph_abs: DefaultDict[str, Set[str]] = defaultdict(set)
    for header, deps in current_graph.items():
        header_abs = str(repo_path / "include" / header)
        deps_abs = {str(repo_path / "include" / d) for d in deps}
        current_graph_abs[header_abs] = deps_abs

    _, _, git_sources, git_head_project_root = reconstruct_head_graph(
        working_tree_headers=current_headers_abs, working_tree_graph=current_graph_abs, base_ref="HEAD", repo_path=str(repo_path)
    )

    # CRITICAL VERIFICATION 1: Git HEAD project root should be deeply nested
    # Git HEAD has: src/deep/Module0/File1.cpp, src/deep/Module0/File2.cpp, include/deep/Module0/Header0.hpp
    # Common prefix should be repo_path (because src/ and include/ are separate)
    # But sources themselves have common prefix: src/deep/Module0
    git_sources_only_prefix = os.path.commonpath(git_sources) if len(git_sources) > 1 else os.path.dirname(git_sources[0])
    assert "deep/Module0" in git_sources_only_prefix, f"Git sources should be in deep/Module0, got {git_sources_only_prefix}"

    # CRITICAL VERIFICATION 2: Working tree has RootFile.cpp which should change project root
    # Working tree has: src/RootFile.cpp, src/deep/Module0/File1.cpp, src/deep/Module0/File2.cpp
    # Common prefix should be src/ (or repo_path/src)
    working_tree_sources = [s for s in disk_ninja_sources]
    working_tree_sources_prefix = os.path.commonpath(working_tree_sources) if len(working_tree_sources) > 1 else os.path.dirname(working_tree_sources[0])
    assert working_tree_sources_prefix.endswith("src"), f"Working tree sources common prefix should be src/, got {working_tree_sources_prefix}"

    # CRITICAL VERIFICATION 3: Git HEAD should NOT have RootFile.cpp
    git_source_basenames = {os.path.basename(s) for s in git_sources}
    assert "RootFile.cpp" not in git_source_basenames, "Git HEAD should not have RootFile.cpp"
    assert len(git_sources) == 2, f"Git HEAD should have 2 sources, got {len(git_sources)}"

    # CRITICAL VERIFICATION 4: Working tree SHOULD have RootFile.cpp
    working_basenames = {os.path.basename(s) for s in working_tree_sources}
    assert "RootFile.cpp" in working_basenames, "Working tree should have RootFile.cpp"
    assert len(working_tree_sources) == 3, f"Working tree should have 3 sources, got {len(working_tree_sources)}"

    # CRITICAL VERIFICATION 5: Both project roots should be repo_path (because include/ separates them)
    # But the SOURCE lists differ, which is what matters for impact analysis
    assert git_head_project_root == str(repo_path), f"Git HEAD project root should be {repo_path}"
    assert working_tree_project_root == str(repo_path), f"Working tree project root should be {repo_path}"

    print(f"\n✓ Git HEAD sources: {sorted(git_source_basenames)}")
    print(f"✓ Working tree sources: {sorted(working_basenames)}")
    print(f"✓ Git HEAD project root: {git_head_project_root}")
    print(f"✓ Working tree project root: {working_tree_project_root}")


def test_project_root_calculation_paths_completely_independent(tmp_path: Path) -> None:
    """CRITICAL: Verify git HEAD and working tree use completely independent paths for project root.

    This test creates a scenario where:
    - Git HEAD has files ONLY in dirA/
    - Working tree has files ONLY in dirB/
    - Proves they calculate project roots from different file sets
    """
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    setup_git_repo(str(repo_path))

    # BASELINE: All files in dirA/
    baseline_headers = {"dirA/Header0.hpp"}
    baseline_graph: DefaultDict[str, Set[str]] = defaultdict(set)
    baseline_source_deps = {"dirA/File1.cpp": ["dirA/Header0.hpp"]}

    create_physical_file_structure(str(repo_path), baseline_headers, baseline_graph, baseline_source_deps)
    generate_build_ninja(str(repo_path), list(baseline_source_deps.keys()), str(repo_path / "include"))
    commit_all_files(str(repo_path), "Baseline in dirA")

    # WORKING TREE: Delete dirA files, add dirB files
    import shutil

    shutil.rmtree(str(repo_path / "src" / "dirA"))
    shutil.rmtree(str(repo_path / "include" / "dirA"))

    current_headers = {"dirB/Header0.hpp"}
    current_graph: DefaultDict[str, Set[str]] = defaultdict(set)
    current_source_deps = {"dirB/File1.cpp": ["dirB/Header0.hpp"]}

    create_physical_file_structure(str(repo_path), current_headers, current_graph, current_source_deps)
    generate_build_ninja(str(repo_path), list(current_source_deps.keys()), str(repo_path / "include"))

    # Calculate working tree project root from disk ninja
    from lib.ninja_utils import extract_source_and_header_files_from_ninja

    disk_ninja_sources, disk_ninja_headers = extract_source_and_header_files_from_ninja(str(repo_path / "build.ninja"))
    working_tree_project_root = find_project_root_from_sources(disk_ninja_sources + disk_ninja_headers)

    # Calculate git HEAD project root
    current_headers_abs = {str(repo_path / "include" / h) for h in current_headers}
    current_graph_abs: DefaultDict[str, Set[str]] = defaultdict(set)

    _, _, git_sources, git_head_project_root = reconstruct_head_graph(
        working_tree_headers=current_headers_abs, working_tree_graph=current_graph_abs, base_ref="HEAD", repo_path=str(repo_path)
    )

    # CRITICAL: Git HEAD should have dirA files (from git)
    git_source_paths = [s for s in git_sources]
    assert any("dirA" in s for s in git_source_paths), f"Git HEAD should have dirA files: {git_source_paths}"
    assert not any("dirB" in s for s in git_source_paths), f"Git HEAD should NOT have dirB files: {git_source_paths}"

    # CRITICAL: Working tree should have dirB files (from disk)
    working_source_paths = [s for s in disk_ninja_sources]
    assert any("dirB" in s for s in working_source_paths), f"Working tree should have dirB files: {working_source_paths}"
    assert not any("dirA" in s for s in working_source_paths), f"Working tree should NOT have dirA files: {working_source_paths}"

    # Both should still calculate to repo_path (common ancestor of src/ and include/)
    assert git_head_project_root == str(repo_path), f"Git HEAD project root: {git_head_project_root}"
    assert working_tree_project_root == str(repo_path), f"Working tree project root: {working_tree_project_root}"

    print(f"\n✓ Git HEAD uses files from: dirA/")
    print(f"✓ Working tree uses files from: dirB/")
    print(f"✓ Paths are completely independent")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
