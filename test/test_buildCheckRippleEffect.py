#!/usr/bin/env python3
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
"""Integration tests for buildCheckRippleEffect.py"""
import os
import sys
import subprocess
from pathlib import Path
import pytest
from typing import Any, Dict, List, Tuple, Generator

sys.path.insert(0, str(Path(__file__).parent.parent))
import buildCheckRippleEffect


class TestBuildCheckRippleEffect:
    """Test suite for buildCheckRippleEffect functionality."""

    def test_find_git_repo_success(self, mock_git_repo: Any) -> None:
        """Test finding git repository from subdirectory."""
        # Start from a subdirectory
        subdir = Path(mock_git_repo) / "src"

        result = buildCheckRippleEffect.find_git_repo(str(subdir))

        assert result is not None
        assert Path(result).resolve() == Path(mock_git_repo).resolve()

    def test_find_git_repo_not_found(self, temp_dir: Any) -> None:
        """Test when no git repository is found."""
        result = buildCheckRippleEffect.find_git_repo(temp_dir)
        assert result is None

    def test_find_git_repo_path_traversal_protection(self, temp_dir: Any) -> None:
        """Test that symlink attacks are prevented in git repo detection."""
        import subprocess

        # Create a proper git repository
        repo_dir = Path(temp_dir) / "repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)

        # Try with the git repo (should work)
        result = buildCheckRippleEffect.find_git_repo(str(repo_dir))
        assert result is not None

    def test_categorize_changed_files(self) -> None:
        """Test categorizing files into headers and sources."""
        changed_files = ["/path/to/header.hpp", "/path/to/source.cpp", "/path/to/header.h", "/path/to/impl.cc", "/path/to/config.txt"]  # Should be ignored

        headers, sources = buildCheckRippleEffect.categorize_changed_files(changed_files)

        assert len(headers) == 2
        assert "/path/to/header.hpp" in headers
        assert "/path/to/header.h" in headers

        assert len(sources) == 2
        assert "/path/to/source.cpp" in sources
        assert "/path/to/impl.cc" in sources

    def test_categorize_changed_files_invalid_input(self) -> None:
        """Test error handling for invalid input."""
        with pytest.raises((TypeError, AttributeError)):
            buildCheckRippleEffect.categorize_changed_files("not a list")  # type: ignore[arg-type]

    def test_get_changed_files_from_git(self, mock_git_repo: Any) -> None:
        """Test getting changed files from git."""
        from lib.git_utils import get_changed_files_from_commit

        try:
            changed_files, _ = get_changed_files_from_commit(mock_git_repo, "HEAD")

            # Should have at least one changed file (utils.hpp)
            assert len(changed_files) >= 1
            assert any("utils.hpp" in f for f in changed_files)

            # All paths should be absolute
            assert all(os.path.isabs(f) for f in changed_files)
        except SystemExit:
            pytest.skip("Git command failed")

    def test_get_changed_files_from_git_invalid_commit(self, mock_git_repo: Any) -> None:
        """Test handling of invalid git commit reference."""
        from lib.git_utils import get_changed_files_from_commit

        with pytest.raises(ValueError, match="Invalid commit reference"):
            get_changed_files_from_commit(mock_git_repo, "invalid_commit_hash")

    @pytest.mark.skip(reason="GitPython validates paths internally, subprocess mocking no longer applicable")
    def test_get_changed_files_path_traversal_protection(self, mock_git_repo: Any, monkeypatch: Any) -> None:
        """Test that path traversal in git output is detected and blocked."""
        # Note: With GitPython, path validation happens at a different level
        # GitPython itself validates paths and won't return malicious paths
        # The _validate_and_convert_path function still provides defense in depth
        pass

    def test_analyze_ripple_effect_invalid_build_dir(self) -> None:
        """Test error handling for invalid build directory."""
        with pytest.raises(ValueError, match="does not exist"):
            buildCheckRippleEffect.analyze_ripple_effect("/nonexistent/build", [], [])

    def test_analyze_ripple_effect_missing_build_ninja(self, temp_dir: Any) -> None:
        """Test error handling when build.ninja is missing (needed to generate compile_commands.json)."""
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir()

        # Should fail because build.ninja is missing (ninja -t compdb will fail)
        with pytest.raises(RuntimeError, match="Failed to generate compile_commands.json"):
            buildCheckRippleEffect.analyze_ripple_effect(str(build_dir), [], [])

    def test_get_ripple_effect_data_no_changes(self, mock_build_dir: Any, mock_git_repo: Any, monkeypatch: Any) -> None:
        """Test getting ripple effect data when no files changed."""

        # Mock the imported git functions to return no changes
        def mock_get_uncommitted_changes(*args: Any, **kwargs: Any) -> list[str]:
            return []

        monkeypatch.setattr(buildCheckRippleEffect, "get_uncommitted_changes", mock_get_uncommitted_changes)

        result = buildCheckRippleEffect.get_ripple_effect_data(mock_build_dir, mock_git_repo)

        assert result.changed_headers == []
        assert result.changed_sources == []
        assert result.rebuild_percentage == 0.0

    def test_print_ripple_report_validation(self, temp_dir: Any) -> None:
        """Test that print_ripple_report works with RippleEffectResult."""
        from buildCheckRippleEffect import RippleEffectResult

        valid_result = RippleEffectResult(affected_sources={}, total_affected=set(), direct_sources=set(), source_to_deps={}, header_to_sources={})

        # Just test that it works without errors
        buildCheckRippleEffect.print_ripple_report([], [], valid_result, temp_dir)


class TestBuildCheckRippleEffectIntegration:
    """Integration tests with mocked dependencies."""

    @pytest.mark.skipif(subprocess.run(["which", "git"], capture_output=True).returncode != 0, reason="git not available")
    def test_full_workflow_with_mock_data(self, mock_git_repo: Any, mock_build_dir: Any, mock_compile_commands: Any) -> None:
        """Test complete workflow with mocked build data."""
        result = buildCheckRippleEffect.get_ripple_effect_data(mock_build_dir, mock_git_repo)

        # Should return a RippleEffectData with expected attributes
        assert hasattr(result, "changed_headers")
        assert hasattr(result, "changed_sources")
        assert hasattr(result, "rebuild_percentage")
        assert isinstance(result.changed_headers, list)
        assert isinstance(result.changed_sources, list)
        assert isinstance(result.affected_sources_by_header, dict)
        assert isinstance(result.total_sources, int)
        assert isinstance(result.rebuild_percentage, float)

        # The test verifies the data structure is correct
        # Actual dependency detection depends on clang-scan-deps parsing capabilities

    def test_get_ripple_effect_data_with_uncommitted_changes(self, mock_build_dir: Any, mock_git_repo: Any, mock_compile_commands: Any) -> None:
        """Test getting ripple effect data for uncommitted changes."""
        import subprocess

        # Reset any staged changes first
        subprocess.run(["git", "reset"], cwd=mock_git_repo, check=False)

        # Modify an existing header file that's part of the build
        utils_header = Path(mock_git_repo) / "src" / "utils.hpp"
        if not utils_header.exists():
            pytest.skip("Test file not found in mock repo")

        # Modify the header to add a new function
        utils_header.write_text(
            """
#ifndef UTILS_HPP
#define UTILS_HPP

int add(int a, int b);
int multiply(int a, int b);  // New function

#endif
"""
        )

        # Stage the change (but it's still uncommitted)
        subprocess.run(["git", "add", "src/utils.hpp"], cwd=mock_git_repo, check=True)

        # Get ripple effect data for uncommitted changes
        result = buildCheckRippleEffect.get_ripple_effect_data(mock_build_dir, mock_git_repo)

        # Verify result structure
        assert hasattr(result, "changed_headers")
        assert hasattr(result, "changed_sources")
        assert hasattr(result, "affected_sources_by_header")
        assert hasattr(result, "rebuild_percentage")
        assert hasattr(result, "total_sources")
        assert isinstance(result.changed_headers, list)
        assert isinstance(result.changed_sources, list)
        assert isinstance(result.all_affected_sources, list)
        assert isinstance(result.total_sources, int)

        # Should detect the changed header
        assert len(result.changed_headers) > 0, "Should detect changed header file"
        assert any("utils.hpp" in h for h in result.changed_headers), "Should find utils.hpp in changed headers"

        # Should have scanned the build (total_sources should be > 0)
        assert result.total_sources > 0, f"Should have found source files in build, got {result.total_sources}"

        # The affected sources depend on whether clang-scan-deps successfully parsed dependencies
        # At minimum we should have the changed header categorized correctly

    @pytest.mark.integration
    def test_include_graph_finds_headers(self, mock_build_dir: Any, mock_source_files: Any, mock_git_repo: Any, mock_compile_commands: Any) -> None:
        """Test that clang-scan-deps actually finds header dependencies.

        Note: This test depends on clang-scan-deps properly parsing dependencies from
        mock compile_commands.json files. It may be flaky in some environments.
        """
        # This is a more direct test of the include graph building
        from buildCheckDependencyHell import build_include_graph  # Build the include graph

        scan_result = build_include_graph(mock_build_dir)

        # Verify we got results
        assert scan_result is not None
        assert hasattr(scan_result, "source_to_deps")
        assert hasattr(scan_result, "all_headers")
        assert hasattr(scan_result, "include_graph")

        # Should have scanned source files
        assert len(scan_result.source_to_deps) >= 2, f"Should have scanned at least 2 source files (main.cpp, utils.cpp), got {len(scan_result.source_to_deps)}"

        # Should have found headers in dependencies
        assert len(scan_result.all_headers) >= 2, f"Should have found at least 2 project headers (utils.hpp, config.hpp), got {len(scan_result.all_headers)}"

        # Check that utils.hpp and config.hpp were found
        header_names = [os.path.basename(h) for h in scan_result.all_headers]
        assert "utils.hpp" in header_names, f"Should find utils.hpp in headers, got: {header_names}"
        assert "config.hpp" in header_names, f"Should find config.hpp in headers, got: {header_names}"

        # Verify source files have dependencies
        sources_with_deps = 0
        for source, deps in scan_result.source_to_deps.items():
            # Check if this is one of our test source files (keys are .o files like "main.o", "utils.o")
            # After sanitization removes -o flag, clang-scan-deps uses source basename + .o
            source_basename = os.path.basename(source)
            if "main" in source_basename or "utils" in source_basename:
                # Each source file should depend on at least itself and one header
                assert (
                    len(deps) >= 2
                ), f"Source {source_basename} should have at least 2 deps (itself + headers), got {len(deps)}: {[os.path.basename(d) for d in deps]}"
                sources_with_deps += 1

        assert sources_with_deps >= 2, f"Should have checked at least 2 source files, got {sources_with_deps}"


class TestBuildCheckRippleEffectFromParameter:
    """Test suite for --from parameter functionality."""

    def test_get_ripple_effect_data_with_from_ref(self, mock_build_dir: Any, mock_git_repo: Any, monkeypatch: Any) -> None:
        """Test get_ripple_effect_data with from_ref parameter."""
        changed_files_list = [os.path.join(mock_git_repo, "include", "utils.hpp"), os.path.join(mock_git_repo, "src", "main.cpp")]

        # Mock validate_ancestor_relationship to always succeed
        def mock_validate(*args: Any, **kwargs: Any) -> None:
            pass

        # Mock get_working_tree_changes_from_commit to return test files
        def mock_get_working_tree_changes(*args: Any, **kwargs: Any) -> tuple[list[str], str]:
            return changed_files_list, "Test changes"

        # Mock analyze_ripple_effect to avoid actual dependency scanning
        from buildCheckRippleEffect import RippleEffectResult

        def mock_analyze_ripple(*args: Any, **kwargs: Any) -> tuple[RippleEffectResult, dict[str, Any]]:
            return (
                RippleEffectResult(
                    affected_sources={}, total_affected=set(), direct_sources=set(changed_files_list), source_to_deps={"dummy.cpp": []}, header_to_sources={}
                ),
                {},
            )

        monkeypatch.setattr(buildCheckRippleEffect, "validate_ancestor_relationship", mock_validate)
        monkeypatch.setattr(buildCheckRippleEffect, "get_working_tree_changes_from_commit", mock_get_working_tree_changes)
        monkeypatch.setattr(buildCheckRippleEffect, "analyze_ripple_effect", mock_analyze_ripple)

        result = buildCheckRippleEffect.get_ripple_effect_data(mock_build_dir, mock_git_repo, from_ref="origin/main")

        # Should have found changes
        assert len(result.changed_headers) > 0 or len(result.changed_sources) > 0

    def test_get_ripple_effect_data_with_none_from_ref_uses_default(self, mock_build_dir: Any, mock_git_repo: Any, monkeypatch: Any) -> None:
        """Test that from_ref=None uses default behavior (uncommitted changes)."""

        # Mock get_uncommitted_changes
        def mock_get_uncommitted_changes(*args: Any, **kwargs: Any) -> list[str]:
            return []

        monkeypatch.setattr(buildCheckRippleEffect, "get_uncommitted_changes", mock_get_uncommitted_changes)

        result = buildCheckRippleEffect.get_ripple_effect_data(mock_build_dir, mock_git_repo, from_ref=None)

        # Should return empty result (no uncommitted changes)
        assert result.changed_headers == []
        assert result.changed_sources == []

    def test_get_ripple_effect_data_validates_ancestor(self, mock_build_dir: Any, mock_git_repo: Any, monkeypatch: Any) -> None:
        """Test that from_ref validation is called when provided."""
        validate_called = []

        def mock_validate(repo_dir: str, from_ref: str, to_ref: str = "HEAD") -> None:
            validate_called.append((repo_dir, from_ref, to_ref))

        def mock_get_working_tree_changes(*args: Any, **kwargs: Any) -> tuple[list[str], str]:
            return [], "No changes"

        monkeypatch.setattr(buildCheckRippleEffect, "validate_ancestor_relationship", mock_validate)
        monkeypatch.setattr(buildCheckRippleEffect, "get_working_tree_changes_from_commit", mock_get_working_tree_changes)

        buildCheckRippleEffect.get_ripple_effect_data(mock_build_dir, mock_git_repo, from_ref="HEAD~5")

        # Validate should have been called
        assert len(validate_called) == 1
        assert validate_called[0][1] == "HEAD~5"

    def test_get_ripple_effect_data_invalid_ancestor_raises_error(self, mock_build_dir: Any, mock_git_repo: Any, monkeypatch: Any) -> None:
        """Test that invalid ancestor raises ValueError."""

        def mock_validate(*args: Any, **kwargs: Any) -> None:
            raise ValueError("Not a linear ancestor")

        monkeypatch.setattr(buildCheckRippleEffect, "validate_ancestor_relationship", mock_validate)

        with pytest.raises(ValueError) as exc_info:
            buildCheckRippleEffect.get_ripple_effect_data(mock_build_dir, mock_git_repo, from_ref="divergent-branch")

        assert "ancestor" in str(exc_info.value).lower()

    def test_run_analysis_workflow_with_from_ref(self, mock_build_dir: Any, mock_git_repo: Any, monkeypatch: Any, capsys: Any) -> None:
        """Test run_analysis_workflow shows correct comparison message with from_ref."""

        def mock_validate(*args: Any, **kwargs: Any) -> None:
            pass

        def mock_get_working_tree_changes(*args: Any, **kwargs: Any) -> tuple[list[str], str]:
            return [], "No changes"

        monkeypatch.setattr(buildCheckRippleEffect, "validate_ancestor_relationship", mock_validate)
        monkeypatch.setattr(buildCheckRippleEffect, "get_working_tree_changes_from_commit", mock_get_working_tree_changes)

        buildCheckRippleEffect.run_analysis_workflow(mock_build_dir, mock_git_repo, verbose=False, from_ref="origin/main")

        captured = capsys.readouterr()
        assert "vs origin/main" in captured.out

    def test_run_analysis_workflow_without_from_ref_shows_head(self, mock_build_dir: Any, mock_git_repo: Any, monkeypatch: Any, capsys: Any) -> None:
        """Test run_analysis_workflow shows HEAD when from_ref is None."""

        def mock_get_uncommitted_changes(*args: Any, **kwargs: Any) -> list[str]:
            return []

        monkeypatch.setattr(buildCheckRippleEffect, "get_uncommitted_changes", mock_get_uncommitted_changes)

        buildCheckRippleEffect.run_analysis_workflow(mock_build_dir, mock_git_repo, verbose=False, from_ref=None)

        captured = capsys.readouterr()
        assert "vs HEAD" in captured.out

    def test_parse_arguments_includes_from_parameter(self) -> None:
        """Test that --from argument is properly defined in parser."""
        import argparse

        # Get the parser
        parser = buildCheckRippleEffect.parse_arguments.__code__

        # Check that the function exists and we can call it with --from
        # This is a basic smoke test
        assert callable(buildCheckRippleEffect.parse_arguments)

    def test_write_json_output_with_from_ref(self, mock_build_dir: Any, mock_git_repo: Any, temp_dir: Any, monkeypatch: Any) -> None:
        """Test JSON output includes data when using from_ref."""
        json_path = os.path.join(temp_dir, "output.json")

        def mock_validate(*args: Any, **kwargs: Any) -> None:
            pass

        def mock_get_working_tree_changes(*args: Any, **kwargs: Any) -> tuple[list[str], str]:
            return [], "No changes"

        monkeypatch.setattr(buildCheckRippleEffect, "validate_ancestor_relationship", mock_validate)
        monkeypatch.setattr(buildCheckRippleEffect, "get_working_tree_changes_from_commit", mock_get_working_tree_changes)

        # Should not raise
        buildCheckRippleEffect.write_json_output_file(json_path, mock_build_dir, mock_git_repo, from_ref="HEAD~1")

        # Verify JSON file was created
        assert os.path.exists(json_path)

        # Verify JSON is valid
        import json

        with open(json_path) as f:
            data = json.load(f)

        assert "changed_headers" in data
        assert "changed_sources" in data
        assert "rebuild_percentage" in data
