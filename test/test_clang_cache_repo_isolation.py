#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test clang-scan-deps cache isolation between different repositories.

This test suite validates that the caching mechanism in build_include_graph()
properly isolates cache data between different repository instances to prevent
cache contamination that causes incorrect analysis results.

Critical bugs this catches:
1. Cache data leaking between different repository paths
2. Inconsistent results when scanning the same scenario multiple times
3. Stale cache returning wrong number of headers/edges
"""

import sys
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Generator

import pytest

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.clang_utils import build_include_graph
from lib.scenario_creators import create_git_repo_from_scenario
from lib.constants import CACHE_DIR


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


class TestCacheRepoIsolation:
    """Test that cache properly isolates between different repository instances."""

    def test_different_repos_get_independent_cache_directories(self) -> None:
        """Verify each repo gets its own .buildcheck_cache directory.

        This is the FUNDAMENTAL requirement - each repo must have its own cache dir.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create two separate repos
            repo1_path = Path(tmp_dir) / "repo1"
            repo2_path = Path(tmp_dir) / "repo2"

            for repo_path in [repo1_path, repo2_path]:
                create_git_repo_from_scenario(scenario_id=9, repo_path=str(repo_path), baseline_as_head=True, current_as_working=True)

            # Scan both repos
            _ = build_include_graph(str(repo1_path), verbose=False)
            _ = build_include_graph(str(repo2_path), verbose=False)

            # Verify each has its own cache directory
            cache1 = repo1_path / CACHE_DIR
            cache2 = repo2_path / CACHE_DIR

            assert cache1.exists(), f"Repo1 should have cache dir: {cache1}"
            assert cache2.exists(), f"Repo2 should have cache dir: {cache2}"
            assert cache1 != cache2, "Cache directories must be different"

            # Verify cache files exist and are different
            cache_file1 = cache1 / "clang_scan_deps_output.pickle"
            cache_file2 = cache2 / "clang_scan_deps_output.pickle"

            assert cache_file1.exists(), f"Repo1 cache file should exist: {cache_file1}"
            assert cache_file2.exists(), f"Repo2 cache file should exist: {cache_file2}"

            # Even though they're the same scenario, files should be in different locations
            assert cache_file1 != cache_file2, "Cache files must be at different paths"

    def test_cache_doesnt_leak_between_repo_instances(self) -> None:
        """CRITICAL: Verify cache doesn't cause wrong results across repo instances.

        This is the BUG that was detected: scanning scenario 9 multiple times
        was returning 25 headers first time (correct) but 23 headers second time (wrong).

        Regression test for: Cache miss shows 25 headers, cache hit shows 23 headers.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create first repo instance
            repo1_path = Path(tmp_dir) / "instance1"
            create_git_repo_from_scenario(scenario_id=9, repo_path=str(repo1_path), baseline_as_head=True, current_as_working=True)

            # Scan first instance (cache miss)
            scan1 = build_include_graph(str(repo1_path), verbose=False)
            headers1 = len(scan1.all_headers)
            edges1 = sum(len(deps) for deps in scan1.include_graph.values())
            sources1 = len(scan1.source_to_deps)

            # DEBUG: Log what was found
            print(f"\n[DEBUG] Repo1 scan results:")
            print(f"  Headers found: {headers1}")
            print(f"  Sources found: {sources1}")
            print(f"  Sample headers: {sorted(list(scan1.all_headers))[:5]}")

            # Create second repo instance with DIFFERENT path but SAME content
            repo2_path = Path(tmp_dir) / "instance2"
            create_git_repo_from_scenario(scenario_id=9, repo_path=str(repo2_path), baseline_as_head=True, current_as_working=True)

            # Scan second instance (potentially cache hit if bug exists)
            scan2 = build_include_graph(str(repo2_path), verbose=False)
            headers2 = len(scan2.all_headers)
            edges2 = sum(len(deps) for deps in scan2.include_graph.values())
            sources2 = len(scan2.source_to_deps)

            # DEBUG: Log what was found
            print(f"\n[DEBUG] Repo2 scan results:")
            print(f"  Headers found: {headers2}")
            print(f"  Sources found: {sources2}")
            print(f"  Sample headers: {sorted(list(scan2.all_headers))[:5]}")

            # Check files on disk
            import os

            actual_headers_repo1 = list((Path(repo1_path) / "include").rglob("*.hpp"))
            actual_headers_repo2 = list((Path(repo2_path) / "include").rglob("*.hpp"))
            print(f"\n[DEBUG] Actual files on disk:")
            print(f"  Repo1 .hpp files: {len(actual_headers_repo1)}")
            print(f"  Repo2 .hpp files: {len(actual_headers_repo2)}")

            # CRITICAL ASSERTION: Both scans must return IDENTICAL results
            assert headers1 == headers2, (
                f"Cache contamination detected!\n"
                f"First scan (cache miss): {headers1} headers\n"
                f"Second scan (cache hit?): {headers2} headers\n"
                f"Expected: Same header count for identical scenarios\n"
                f"This indicates cache is leaking data between repo instances."
            )

            assert edges1 == edges2, (
                f"Cache contamination detected!\n"
                f"First scan: {edges1} edges, Second scan: {edges2} edges\n"
                f"Edge count mismatch indicates cache pollution."
            )

            assert sources1 == sources2, f"Cache contamination detected!\n" f"First scan: {sources1} sources, Second scan: {sources2} sources"

            # Verify scenario 9 has the expected 25 headers (5 modules × 5 headers)
            assert headers1 == 25, (
                f"Scenario 9 should have exactly 25 headers (5 modules × 5 headers each), "
                f"but got {headers1}. This may indicate cache is returning stale data."
            )

    def test_same_repo_multiple_scans_produces_consistent_results(self) -> None:
        """Verify scanning the SAME repo multiple times gives consistent results.

        This catches bugs where cache state changes between invocations.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_path = Path(tmp_dir) / "test_repo"
            create_git_repo_from_scenario(scenario_id=9, repo_path=str(repo_path), baseline_as_head=True, current_as_working=True)

            # Scan three times
            results: List[Dict[str, Any]] = []
            for i in range(3):
                scan = build_include_graph(str(repo_path), verbose=False)
                results.append(
                    {
                        "headers": len(scan.all_headers),
                        "edges": sum(len(deps) for deps in scan.include_graph.values()),
                        "sources": len(scan.source_to_deps),
                        "scan_num": i + 1,
                    }
                )

            # All scans should return identical results
            first = results[0]
            for i, result in enumerate(results[1:], start=2):
                assert result["headers"] == first["headers"], (
                    f"Scan #{i} returned {result['headers']} headers, "
                    f"but scan #1 returned {first['headers']} headers. "
                    f"Cache state is changing between scans!"
                )
                assert result["edges"] == first["edges"], f"Scan #{i} returned {result['edges']} edges, " f"but scan #1 returned {first['edges']} edges"
                assert result["sources"] == first["sources"], (
                    f"Scan #{i} returned {result['sources']} sources, " f"but scan #1 returned {first['sources']} sources"
                )

    def test_cache_properly_invalidates_on_file_changes(self) -> None:
        """Verify cache invalidates when repository files change.

        This ensures cache doesn't serve stale data after modifications.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_path = Path(tmp_dir) / "test_repo"
            create_git_repo_from_scenario(scenario_id=9, repo_path=str(repo_path), baseline_as_head=True, current_as_working=True)

            # Initial scan
            scan1 = build_include_graph(str(repo_path), verbose=False)
            initial_headers = len(scan1.all_headers)

            # Add a new header file
            new_header = repo_path / "include" / "Module0" / "NewHeader.hpp"
            new_header.write_text("#pragma once\n")
            new_source = repo_path / "src" / "Module0" / "NewHeader.cpp"
            new_source.write_text('#include "Module0/NewHeader.hpp"\n')

            # Update compile_commands.json
            import json

            compile_commands_path = repo_path / "compile_commands.json"
            with open(compile_commands_path, "r") as f:
                compile_commands = json.load(f)
            compile_commands.append(
                {
                    "directory": str(repo_path),
                    "command": f"clang++ -std=c++17 -I{repo_path}/include -c {new_source} -o obj/Module0/NewHeader.o",
                    "file": str(new_source),
                }
            )

            # Add a small delay to ensure mtime changes (filesystem timestamp granularity)
            time.sleep(0.01)

            with open(compile_commands_path, "w") as f:
                json.dump(compile_commands, f, indent=2)

            # Scan again - should detect the new file
            scan2 = build_include_graph(str(repo_path), verbose=False)
            updated_headers = len(scan2.all_headers)

            # Should have one more header now
            assert updated_headers > initial_headers, (
                f"Cache failed to invalidate after adding file. " f"Expected more than {initial_headers} headers, got {updated_headers}"
            )

    def test_cache_isolation_with_different_scenarios(self) -> None:
        """Verify cache properly differentiates between different scenarios.

        Scenario 8 and 9 have different structures, cache should not mix them.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create repos for different scenarios in same temp dir
            repo8 = Path(tmp_dir) / "scenario_8"
            repo9 = Path(tmp_dir) / "scenario_9"

            create_git_repo_from_scenario(8, str(repo8), True, True)
            create_git_repo_from_scenario(9, str(repo9), True, True)

            # Scan both
            scan8 = build_include_graph(str(repo8), verbose=False)
            scan9 = build_include_graph(str(repo9), verbose=False)

            headers8 = len(scan8.all_headers)
            headers9 = len(scan9.all_headers)

            # Verify expected header counts for each scenario
            assert headers8 == 15, f"Scenario 8 should have 15 headers, got {headers8}"
            assert headers9 == 25, f"Scenario 9 should have 25 headers, got {headers9}"

            # Verify each has independent cache
            cache8 = repo8 / CACHE_DIR / "clang_scan_deps_output.pickle"
            cache9 = repo9 / CACHE_DIR / "clang_scan_deps_output.pickle"

            assert cache8.exists(), "Scenario 8 should have its own cache"
            assert cache9.exists(), "Scenario 9 should have its own cache"
            assert cache8 != cache9, "Different scenarios must have different cache files"


class TestCachePathConstruction:
    """Test that cache paths are correctly constructed for isolation."""

    def test_cache_path_includes_build_dir(self) -> None:
        """Verify cache path is built from build_dir, ensuring isolation."""
        from lib.cache_utils import get_cache_path

        build_dir1 = "/tmp/repo1"
        build_dir2 = "/tmp/repo2"
        cache_filename = "test.pickle"

        path1 = get_cache_path(build_dir1, cache_filename)
        path2 = get_cache_path(build_dir2, cache_filename)

        # Paths must be different because build_dirs are different
        assert path1 != path2, (
            f"Cache paths must differ for different build_dirs:\n" f"  build_dir1: {build_dir1} -> {path1}\n" f"  build_dir2: {build_dir2} -> {path2}"
        )

        # Both should contain their respective build_dir
        assert build_dir1 in path1, f"Cache path should contain build_dir: {path1}"
        assert build_dir2 in path2, f"Cache path should contain build_dir: {path2}"

    def test_cache_stored_in_buildcheck_cache_subdir(self) -> None:
        """Verify cache is stored in .buildcheck_cache subdirectory."""
        from lib.cache_utils import get_cache_path
        from lib.constants import CACHE_DIR

        build_dir = "/tmp/test_repo"
        cache_file = "test.pickle"

        path = get_cache_path(build_dir, cache_file)

        # Should contain .buildcheck_cache
        assert CACHE_DIR in path, f"Cache path should contain '{CACHE_DIR}' subdirectory: {path}"

        expected = os.path.join(build_dir, CACHE_DIR, cache_file)
        assert path == expected, f"Expected {expected}, got {path}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
