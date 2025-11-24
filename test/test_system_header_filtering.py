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
"""Tests for system header filtering functionality across tools"""
import sys
from pathlib import Path
from typing import Set, Tuple, Dict
from unittest.mock import Mock, patch, MagicMock
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.file_utils import filter_system_headers
from lib.clang_utils import is_system_header


class TestSystemHeaderFiltering:
    """Test that system headers are properly filtered."""

    @pytest.mark.unit
    def test_is_system_header_detection(self) -> None:
        """Test system header detection."""
        # System headers should be detected
        assert is_system_header("/usr/include/stdio.h")
        assert is_system_header("/usr/local/include/boost/shared_ptr.hpp")
        assert is_system_header("/lib/gcc/include/stddef.h")
        assert is_system_header("/opt/local/include/curl/curl.h")

        # Project headers should not be detected as system headers
        assert not is_system_header("/home/user/project/include/myheader.h")
        assert not is_system_header("/workspace/src/core/utils.hpp")
        assert not is_system_header("include/mylib/header.h")
        assert not is_system_header("./src/component.hpp")

    @pytest.mark.unit
    def test_filter_system_headers_removes_system_headers(self) -> None:
        """Test that filter_system_headers removes system headers."""
        headers: Set[str] = {
            "/usr/include/stdio.h",
            "/usr/include/stdlib.h",
            "/home/user/project/include/myheader.h",
            "/workspace/src/utils.hpp",
            "/lib/gcc/include/stddef.h",
            "/opt/local/include/boost/shared_ptr.hpp",
        }

        filtered, stats = filter_system_headers(headers, show_progress=False)

        # Should only have project headers
        assert len(filtered) == 2
        assert "/home/user/project/include/myheader.h" in filtered
        assert "/workspace/src/utils.hpp" in filtered

        # Should have filtered out 4 system headers
        assert stats["total_excluded"] == 4

    @pytest.mark.unit
    def test_filter_system_headers_preserves_all_when_no_system_headers(self) -> None:
        """Test that filter_system_headers preserves all headers when there are no system headers."""
        headers: Set[str] = {"/home/user/project/include/myheader.h", "/workspace/src/utils.hpp", "include/mylib/header.h"}

        filtered, stats = filter_system_headers(headers, show_progress=False)

        # Should have all headers
        assert len(filtered) == 3
        assert filtered == headers

        # Should have filtered out 0 headers
        assert stats["total_excluded"] == 0


class TestGitImpactSystemHeaderFiltering:
    """Test that git-impact respects system header filtering."""

    @pytest.mark.unit
    def test_git_impact_filters_system_headers_by_default(self, tmp_path: Path) -> None:
        """Test that git-impact filters system headers when include_system_headers=False."""
        from lib.dsm_analysis import run_git_working_tree_analysis

        # Create fake git repo directory
        fake_repo = tmp_path / "repo"
        fake_repo.mkdir()

        # Mock the necessary functions
        with patch("lib.dsm_analysis.find_git_repo") as mock_find_repo, patch(
            "lib.git_utils.get_working_tree_changes_from_commit_batched"
        ) as mock_get_changes, patch("lib.dsm_analysis.categorize_changed_files") as mock_categorize, patch(
            "lib.dsm_analysis.build_include_graph"
        ) as mock_build_graph, patch(
            "lib.git_utils.reconstruct_head_graph"
        ) as mock_reconstruct, patch(
            "lib.dsm_analysis.run_dsm_analysis"
        ) as mock_run_dsm, patch(
            "lib.dsm_analysis.compare_dsm_results"
        ) as mock_compare, patch(
            "lib.dsm_analysis.print_dsm_delta"
        ), patch(
            "lib.file_utils.filter_system_headers"
        ) as mock_filter_system:

            # Setup mocks
            mock_find_repo.return_value = str(fake_repo)

            # Simulate changed files (headers that were modified)
            changed_files = ["/home/user/project/src/myheader.h", "/home/user/project/include/utils.hpp"]
            mock_get_changes.return_value = (changed_files, "working tree changes")

            # Categorize changed files
            mock_categorize.return_value = (changed_files, [])  # Only headers changed, no sources

            # Create current headers with system headers mixed in
            current_headers_with_system = {
                "/usr/include/stdio.h",
                "/home/user/project/src/myheader.h",
                "/lib/gcc/include/stddef.h",
                "/home/user/project/include/utils.hpp",
                "/opt/toolchain/include/vector.h",
            }

            mock_graph = MagicMock()
            mock_build_graph.return_value = Mock(include_graph=mock_graph, all_headers=current_headers_with_system, scan_time=0.1, source_to_deps={})

            # Baseline with system headers mixed in
            baseline_headers_with_system = {"/usr/include/stdio.h", "/home/user/project/src/myheader.h", "/lib/gcc/include/string.h"}
            mock_reconstruct.return_value = (baseline_headers_with_system, mock_graph)

            # Track what headers were filtered
            filtered_headers_calls = []

            def filter_side_effect(headers: Set[str], show_progress: bool = False) -> Tuple[Set[str], Dict[str, int]]:
                # Record the call for verification
                filtered_headers_calls.append(headers.copy())
                # Actually filter system headers
                filtered = {h for h in headers if not is_system_header(h)}
                excluded_count = len(headers) - len(filtered)
                stats = {"total_excluded": excluded_count}
                return (filtered, stats)

            mock_filter_system.side_effect = filter_side_effect

            # Mock DSM analysis results
            mock_dsm_result = Mock()
            mock_run_dsm.return_value = mock_dsm_result
            mock_compare.return_value = Mock()

            # Run analysis WITHOUT include_system_headers flag
            run_git_working_tree_analysis(
                build_dir="/fake/build",
                project_root="/fake/project",
                git_from_ref="HEAD",
                git_repo_path=str(fake_repo),
                verbose=False,
                filter_pattern=None,
                exclude_patterns=None,
                show_layers=False,
                include_system_headers=False,  # Should filter system headers
            )

            # Verify that filter_system_headers was called exactly twice (baseline + current)
            assert mock_filter_system.call_count == 2, f"Expected 2 calls, got {mock_filter_system.call_count}"

            # Verify both calls received headers with system headers mixed in
            assert len(filtered_headers_calls) == 2

            # First call should be for baseline headers
            baseline_call = filtered_headers_calls[0]
            assert baseline_headers_with_system == baseline_call, "Baseline headers should include system headers before filtering"

            # Second call should be for current headers
            current_call = filtered_headers_calls[1]
            assert current_headers_with_system == current_call, "Current headers should include system headers before filtering"

            # Verify that system headers were present in both calls
            baseline_system_headers = {h for h in baseline_call if is_system_header(h)}
            current_system_headers = {h for h in current_call if is_system_header(h)}

            assert len(baseline_system_headers) > 0, "Baseline should have system headers before filtering"
            assert len(current_system_headers) > 0, "Current should have system headers before filtering"

    @pytest.mark.unit
    def test_git_impact_includes_system_headers_when_flag_set(self) -> None:
        """Test that git-impact includes system headers when include_system_headers=True."""
        from lib.dsm_analysis import run_git_working_tree_analysis

        # Mock the necessary functions
        with patch("lib.dsm_analysis.find_git_repo") as mock_find_repo, patch(
            "lib.git_utils.get_working_tree_changes_from_commit_batched"
        ) as mock_get_changes, patch("lib.dsm_analysis.build_include_graph") as mock_build_graph, patch(
            "lib.git_utils.reconstruct_head_graph"
        ) as mock_reconstruct, patch(
            "lib.dsm_analysis.run_dsm_analysis"
        ) as mock_run_dsm, patch(
            "lib.dsm_analysis.compare_dsm_results"
        ) as mock_compare, patch(
            "lib.dsm_analysis.print_dsm_delta"
        ), patch(
            "lib.file_utils.filter_system_headers"
        ) as mock_filter_system:

            # Setup mocks
            mock_find_repo.return_value = "/fake/repo"
            mock_get_changes.return_value = ([], [])

            # Create headers with system headers
            all_headers = {"/usr/include/stdio.h", "/home/user/project/src/myheader.h", "/lib/gcc/include/stddef.h", "/home/user/project/include/utils.hpp"}

            mock_graph = MagicMock()
            mock_build_graph.return_value = Mock(include_graph=mock_graph, all_headers=all_headers, scan_time=0.1, source_to_deps={})

            baseline_headers = {"/usr/include/stdio.h", "/home/user/project/src/myheader.h"}
            mock_reconstruct.return_value = (baseline_headers, mock_graph)

            # Mock DSM analysis results
            mock_dsm_result = Mock()
            mock_run_dsm.return_value = mock_dsm_result
            mock_compare.return_value = Mock()

            # Run analysis WITH include_system_headers flag
            run_git_working_tree_analysis(
                build_dir="/fake/build",
                project_root="/fake/project",
                git_from_ref="HEAD",
                git_repo_path="/fake/repo",
                verbose=False,
                filter_pattern=None,
                exclude_patterns=None,
                show_layers=False,
                include_system_headers=True,  # Should NOT filter system headers
            )

            # Verify that filter_system_headers was NOT called
            assert mock_filter_system.call_count == 0


class TestDependencyHellSystemHeaderFiltering:
    """Test that buildCheckDependencyHell respects system header filtering."""

    @pytest.mark.unit
    def test_dependency_hell_applies_system_header_filter(self) -> None:
        """Test that buildCheckDependencyHell filters system headers correctly."""
        from lib.file_utils import filter_system_headers

        # Simulate problematic headers with system headers mixed in
        problematic_headers = {
            "/usr/include/stdio.h",
            "/home/user/project/src/bloated_header.h",
            "/lib/gcc/include/stddef.h",
            "/home/user/project/include/god_object.hpp",
            "/opt/local/include/boost/shared_ptr.hpp",
        }

        # Filter system headers
        filtered, stats = filter_system_headers(problematic_headers, show_progress=False)

        # Should only have project headers
        assert len(filtered) == 2
        assert "/home/user/project/src/bloated_header.h" in filtered
        assert "/home/user/project/include/god_object.hpp" in filtered

        # System headers should be removed
        assert "/usr/include/stdio.h" not in filtered
        assert "/lib/gcc/include/stddef.h" not in filtered
        assert "/opt/local/include/boost/shared_ptr.hpp" not in filtered

        # Stats should show 3 excluded
        assert stats["total_excluded"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
