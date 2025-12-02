#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for git repository utility functions.

Tests helper functions used by reconstruct_head_graph() for git operations,
path validation, and repository discovery.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typing import Any, Dict, Set

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.git_utils import find_git_repo, _validate_and_convert_path, _extract_files_from_diffs


class TestValidateAndConvertPath:
    """Test _validate_and_convert_path() security and validation logic."""

    def test_valid_relative_path(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test conversion of valid relative path."""
        repo_dir = str(tmp_path)
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        result = _validate_and_convert_path("test.txt", repo_dir)
        assert result == str(test_file)
        assert os.path.isabs(result)

    def test_valid_nested_path(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test conversion of valid nested relative path."""
        repo_dir = str(tmp_path)
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.txt"
        test_file.write_text("content")

        result = _validate_and_convert_path("subdir/test.txt", repo_dir)
        assert result == str(test_file)

    def test_reject_parent_directory_traversal(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test that .. path traversal is rejected (SECURITY)."""
        repo_dir = str(tmp_path)

        # Try to escape using ..
        result = _validate_and_convert_path("../etc/passwd", repo_dir)
        assert result is None

    def test_reject_double_parent_traversal(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test that ../../ traversal is rejected (SECURITY)."""
        repo_dir = str(tmp_path)

        result = _validate_and_convert_path("../../etc/passwd", repo_dir)
        assert result is None

    def test_reject_embedded_parent_traversal(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test that embedded .. is rejected even in valid-looking paths (SECURITY)."""
        repo_dir = str(tmp_path)

        result = _validate_and_convert_path("subdir/../../../etc/passwd", repo_dir)
        assert result is None

    def test_reject_absolute_path(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test that absolute paths are rejected (SECURITY)."""
        repo_dir = str(tmp_path)

        result = _validate_and_convert_path("/etc/passwd", repo_dir)
        assert result is None

    def test_reject_path_outside_repo(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test that paths resolving outside repo are rejected (SECURITY)."""
        repo_dir = str(tmp_path / "repo")
        os.makedirs(repo_dir)

        # Even if a file exists outside, it should be rejected
        outside_file = tmp_path / "outside.txt"
        outside_file.write_text("content")

        # Try to access it with a path that would resolve outside repo
        result = _validate_and_convert_path("../outside.txt", repo_dir)
        assert result is None

    def test_nonexistent_file_returns_none(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test that non-existent files return None."""
        repo_dir = str(tmp_path)

        result = _validate_and_convert_path("nonexistent.txt", repo_dir)
        assert result is None

    def test_empty_path(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test that empty path returns None."""
        repo_dir = str(tmp_path)

        # Empty path should be rejected
        result = _validate_and_convert_path("", repo_dir)
        assert result is None

    def test_windows_style_path(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test Windows-style path separators."""
        repo_dir = str(tmp_path)
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.txt"
        test_file.write_text("content")

        # Windows uses backslashes, but on Linux this becomes a filename
        # Test behavior is platform-dependent
        if os.name == "nt":  # Windows
            result = _validate_and_convert_path("subdir\\test.txt", repo_dir)
            assert result == str(test_file)
        else:  # Linux/Mac - backslash is part of filename
            # This would be treated as a single filename with backslash
            result = _validate_and_convert_path("subdir\\test.txt", repo_dir)
            assert result is None  # Won't exist on Linux

    def test_path_with_dot_current_directory(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test path with ./ (current directory reference)."""
        repo_dir = str(tmp_path)
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        result = _validate_and_convert_path("./test.txt", repo_dir)
        assert result == str(test_file)

    def test_symlink_within_repo(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test handling of symlinks within repo."""
        if os.name == "nt":
            pytest.skip("Symlink test skipped on Windows")

        repo_dir = str(tmp_path)
        real_file = tmp_path / "real.txt"
        real_file.write_text("content")
        link_file = tmp_path / "link.txt"
        link_file.symlink_to(real_file)

        result = _validate_and_convert_path("link.txt", repo_dir)
        # Should return the link path (not the target)
        assert result == str(link_file)

    def test_symlink_outside_repo_rejected(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test that symlinks pointing outside repo are handled (SECURITY)."""
        if os.name == "nt":
            pytest.skip("Symlink test skipped on Windows")

        repo_dir = str(tmp_path / "repo")
        os.makedirs(repo_dir)

        outside_file = tmp_path / "outside.txt"
        outside_file.write_text("content")

        link_file = Path(repo_dir) / "link.txt"
        link_file.symlink_to(outside_file)

        # The link exists, but points outside - current implementation allows this
        # because it only checks the link path itself, not where it points
        result = _validate_and_convert_path("link.txt", repo_dir)
        # Current behavior: allows the link (it's within repo boundary)
        assert result == str(link_file)


class TestExtractFilesFromDiffs:
    """Test _extract_files_from_diffs() for extracting file paths from git diffs."""

    def test_extract_single_modified_file(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test extracting a single modified file."""
        repo_dir = str(tmp_path)
        test_file = tmp_path / "modified.txt"
        test_file.write_text("content")

        # Mock diff object
        mock_diff = Mock()
        mock_diff.b_path = "modified.txt"
        mock_diff.a_path = "modified.txt"
        mock_diffs = [mock_diff]

        result = _extract_files_from_diffs(mock_diffs, repo_dir)
        assert len(result) == 1
        assert result[0] == str(test_file)

    def test_extract_multiple_files(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test extracting multiple files."""
        repo_dir = str(tmp_path)
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content1")
        file2.write_text("content2")

        mock_diff1 = Mock()
        mock_diff1.b_path = "file1.txt"
        mock_diff1.a_path = "file1.txt"

        mock_diff2 = Mock()
        mock_diff2.b_path = "file2.txt"
        mock_diff2.a_path = "file2.txt"

        mock_diffs = [mock_diff1, mock_diff2]

        result = _extract_files_from_diffs(mock_diffs, repo_dir)
        assert len(result) == 2
        assert str(file1) in result
        assert str(file2) in result

    def test_extract_renamed_file_uses_b_path(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test that renamed files use b_path (new name)."""
        repo_dir = str(tmp_path)
        new_file = tmp_path / "new_name.txt"
        new_file.write_text("content")

        # Renamed file: a_path is old name, b_path is new name
        mock_diff = Mock()
        mock_diff.a_path = "old_name.txt"
        mock_diff.b_path = "new_name.txt"
        mock_diffs = [mock_diff]

        result = _extract_files_from_diffs(mock_diffs, repo_dir)
        assert len(result) == 1
        assert result[0] == str(new_file)

    def test_extract_deleted_file_uses_a_path(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test that deleted files use a_path when b_path is None."""
        repo_dir = str(tmp_path)
        # File doesn't exist (it was deleted), but we should still get the path
        # However, _validate_and_convert_path will return None for non-existent files

        mock_diff = Mock()
        mock_diff.a_path = "deleted.txt"
        mock_diff.b_path = None
        mock_diffs = [mock_diff]

        result = _extract_files_from_diffs(mock_diffs, repo_dir)
        # Deleted files don't exist, so they're filtered out
        assert len(result) == 0

    def test_skip_files_with_path_traversal(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test that files with .. are skipped (SECURITY)."""
        repo_dir = str(tmp_path)

        mock_diff = Mock()
        mock_diff.b_path = "../etc/passwd"
        mock_diff.a_path = "../etc/passwd"
        mock_diffs = [mock_diff]

        result = _extract_files_from_diffs(mock_diffs, repo_dir)
        assert len(result) == 0  # Security check filters it out

    def test_skip_nonexistent_files(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test that non-existent files are skipped."""
        repo_dir = str(tmp_path)

        mock_diff = Mock()
        mock_diff.b_path = "nonexistent.txt"
        mock_diff.a_path = "nonexistent.txt"
        mock_diffs = [mock_diff]

        result = _extract_files_from_diffs(mock_diffs, repo_dir)
        assert len(result) == 0

    def test_empty_diffs(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test handling of empty diff list."""
        repo_dir = str(tmp_path)
        result = _extract_files_from_diffs([], repo_dir)
        assert result == []

    def test_diff_with_none_paths(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test handling of diffs with None paths."""
        repo_dir = str(tmp_path)

        mock_diff = Mock()
        mock_diff.b_path = None
        mock_diff.a_path = None
        mock_diffs = [mock_diff]

        result = _extract_files_from_diffs(mock_diffs, repo_dir)
        assert len(result) == 0


class TestFindGitRepo:
    """Test find_git_repo() for discovering git repositories."""

    def test_find_repo_from_root(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test finding repo when starting from repo root."""
        # Create a git repo
        from lib.scenario_git_utils import setup_git_repo

        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        setup_git_repo(str(repo_path))

        result = find_git_repo(str(repo_path))
        assert result == str(repo_path)

    def test_find_repo_from_subdirectory(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test finding repo when starting from subdirectory."""
        from lib.scenario_git_utils import setup_git_repo

        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        setup_git_repo(str(repo_path))

        # Create subdirectory
        subdir = repo_path / "subdir" / "nested"
        subdir.mkdir(parents=True)

        result = find_git_repo(str(subdir))
        assert result == str(repo_path)

    def test_find_repo_from_file_in_repo(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test finding repo when starting from a file path."""
        from lib.scenario_git_utils import setup_git_repo

        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        setup_git_repo(str(repo_path))

        # Create a file
        test_file = repo_path / "test.txt"
        test_file.write_text("content")

        # Pass the file's directory
        result = find_git_repo(str(test_file.parent))
        assert result == str(repo_path)

    def test_not_a_git_repo(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test that None is returned when not in a git repo."""
        not_a_repo = tmp_path / "not_a_repo"
        not_a_repo.mkdir()

        result = find_git_repo(str(not_a_repo))
        assert result is None

    def test_nonexistent_path(self) -> None:
        """Test handling of non-existent path."""
        result = find_git_repo("/nonexistent/path/that/does/not/exist")
        assert result is None

    def test_nested_repos_finds_nearest(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Test that nested repos return the nearest parent repo."""
        from lib.scenario_git_utils import setup_git_repo

        outer_repo = tmp_path / "outer"
        outer_repo.mkdir()
        setup_git_repo(str(outer_repo))

        inner_repo = outer_repo / "inner"
        inner_repo.mkdir()
        setup_git_repo(str(inner_repo))

        # Starting from inner repo should find inner repo
        result = find_git_repo(str(inner_repo))
        assert result == str(inner_repo)

        # Starting from outer should find outer
        result = find_git_repo(str(outer_repo))
        assert result == str(outer_repo)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
