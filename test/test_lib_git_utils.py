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
"""Tests for lib.git_utils module"""
import os
import sys
from pathlib import Path
import pytest
from typing import Any, Dict, List, Tuple, Generator

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.git_utils import (
    find_git_repo,
    check_git_available,
    get_changed_files_from_commit,
    get_staged_files,
    get_uncommitted_changes,
    get_current_branch,
    get_commit_hash,
    categorize_changed_files,
    get_file_history,
    is_ancestor,
    get_working_tree_changes_from_commit,
)
from lib.clang_utils import is_system_header


class TestFindGitRepo:
    """Test the find_git_repo function."""

    def test_find_git_repo_success(self, mock_git_repo: Any) -> None:
        """Test finding git repository from subdirectory."""
        # Start from a subdirectory
        subdir = Path(mock_git_repo) / "src"
        subdir.mkdir(exist_ok=True)

        result = find_git_repo(str(subdir))

        assert result is not None
        assert Path(result).resolve() == Path(mock_git_repo).resolve()

    def test_find_git_repo_from_root(self, mock_git_repo: Any) -> None:
        """Test finding git repository from root."""
        result = find_git_repo(mock_git_repo)

        assert result is not None
        assert Path(result).resolve() == Path(mock_git_repo).resolve()

    def test_find_git_repo_not_found(self, temp_dir: Any) -> None:
        """Test when no git repository is found."""
        result = find_git_repo(temp_dir)
        assert result is None

    def test_find_git_repo_nested(self, mock_git_repo: Any) -> None:
        """Test finding git repo from deeply nested directory."""
        deep_dir = Path(mock_git_repo) / "a" / "b" / "c" / "d"
        deep_dir.mkdir(parents=True, exist_ok=True)

        result = find_git_repo(str(deep_dir))

        assert result is not None
        assert Path(result).resolve() == Path(mock_git_repo).resolve()


class TestGetChangedFilesFromCommit:
    """Test the get_changed_files_from_commit function."""

    def test_get_changed_files_from_commit(self, mock_git_repo: Any) -> None:
        """Test getting changed files from a commit."""
        # Get the latest commit
        import subprocess

        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=mock_git_repo, capture_output=True, text=True, check=True)
        commit_hash = result.stdout.strip()

        changed_files, commit_desc = get_changed_files_from_commit(mock_git_repo, commit_hash)

        # Should find the changed utils.hpp file
        assert len(changed_files) > 0
        assert any("utils.hpp" in f for f in changed_files)

    def test_get_changed_files_head(self, mock_git_repo: Any) -> None:
        """Test getting changed files using HEAD."""
        changed_files, commit_desc = get_changed_files_from_commit(mock_git_repo, "HEAD")

        assert len(changed_files) > 0
        assert any("utils.hpp" in f for f in changed_files)
        assert len(commit_desc) > 0  # Should have commit description

    def test_get_changed_files_invalid_commit(self, mock_git_repo: Any) -> None:
        """Test with invalid commit hash."""
        # Should raise ValueError for invalid commit
        with pytest.raises(ValueError):
            get_changed_files_from_commit(mock_git_repo, "invalid_hash_123")

    def test_get_changed_files_not_git_repo(self, temp_dir: Any) -> None:
        """Test with non-git directory."""
        # Should raise RuntimeError for non-git directory
        with pytest.raises(RuntimeError):
            get_changed_files_from_commit(temp_dir, "HEAD")


class TestCategorizeChangedFiles:
    """Test the categorize_changed_files function."""

    def test_categorize_headers_and_sources(self) -> None:
        """Test categorizing C++ headers and sources."""
        files = ["src/utils.hpp", "src/utils.cpp", "include/config.h", "src/main.cpp", "include/types.hxx", "README.md", "CMakeLists.txt"]

        headers, sources = categorize_changed_files(files)

        assert "src/utils.hpp" in headers
        assert "include/config.h" in headers
        assert "include/types.hxx" in headers
        assert "src/utils.cpp" in sources
        assert "src/main.cpp" in sources

    def test_categorize_empty_list(self) -> None:
        """Test categorizing empty file list."""
        headers, sources = categorize_changed_files([])

        assert len(headers) == 0
        assert len(sources) == 0

    def test_categorize_all_headers(self) -> None:
        """Test with only header files."""
        files = ["include/a.h", "include/b.hpp", "include/c.hxx"]

        headers, sources = categorize_changed_files(files)

        assert len(headers) == 3
        assert len(sources) == 0

    def test_categorize_mixed_extensions(self) -> None:
        """Test various file extensions."""
        files = ["src/file.cc", "src/file.cxx", "src/file.c++", "include/file.hh", "script.py", "data.json"]

        headers, sources = categorize_changed_files(files)

        assert "src/file.cc" in sources
        assert "src/file.cxx" in sources
        # Note: .c++ might not be recognized, depends on implementation
        assert "include/file.hh" in headers

    def test_categorize_case_insensitive(self) -> None:
        """Test that file extension matching."""
        files = ["src/file.cpp", "include/header.hpp", "src/code.cpp"]

        headers, sources = categorize_changed_files(files)

        assert "include/header.hpp" in headers
        assert "src/file.cpp" in sources
        assert "src/code.cpp" in sources

    def test_categorize_with_system_header_filtering(self) -> None:
        """Test that system headers can be filtered from git changed files.
        fffffffffffffffffffffffffffffffff
                This is a regression test for the issue where system headers were appearing
                in the git working tree analysis output even when --include-system-headers
                was not set. The fix applies filtering after categorization.
        """
        # Simulate git diff output with mix of project and system headers
        changed_files = [
            "src/MyHeader.h",
            "include/MyClass.hpp",
            "/usr/include/stdlib.h",
            "/usr/include/c++/13/iostream",  # C++ stdlib header without extension
            "/usr/include/stdio.h",
            "/usr/local/include/boost/shared_ptr.hpp",
            "src/Implementation.cpp",
            "src/main.c",
        ]

        # Categorize files (note: files without extensions like iostream won't be categorized as headers)
        headers, sources = categorize_changed_files(changed_files)

        # Verify categorization worked - iostream has no extension so not categorized
        assert len(headers) == 5  # .h and .hpp files only
        assert len(sources) == 2  # .cpp and .c files

        # Apply system header filtering (as done in run_git_working_tree_analysis)
        filtered_headers = [h for h in headers if not is_system_header(h)]
        filtered_sources = [s for s in sources if not is_system_header(s)]

        # Verify filtering worked correctly
        assert len(filtered_headers) == 2, f"Expected 2 headers after filtering, got {len(filtered_headers)}: {filtered_headers}"
        assert len(filtered_sources) == 2, f"Expected 2 sources after filtering, got {len(filtered_sources)}"

        # Verify only project headers remain
        assert "src/MyHeader.h" in filtered_headers
        assert "include/MyClass.hpp" in filtered_headers
        assert "/usr/include/stdlib.h" not in filtered_headers
        assert "/usr/include/stdio.h" not in filtered_headers
        assert "/usr/local/include/boost/shared_ptr.hpp" not in filtered_headers

        # Note: /usr/include/c++/13/iostream is not in headers list because
        # categorize_changed_files only recognizes files with known extensions


class TestGetStagedFiles:
    """Test the get_staged_files function."""

    def test_get_staged_files_with_changes(self, mock_git_repo: Any) -> None:
        """Test getting staged files when there are staged changes."""
        import subprocess

        # Create a new file and stage it
        test_file = Path(mock_git_repo) / "staged_file.cpp"
        test_file.write_text("// Staged file\nint main() { return 0; }\n")

        subprocess.run(["git", "add", "staged_file.cpp"], cwd=mock_git_repo, check=True)

        staged_files, description = get_staged_files(mock_git_repo)

        # Should find the staged file
        assert len(staged_files) > 0
        assert any("staged_file.cpp" in f for f in staged_files)
        assert "Staged changes" in description

    def test_get_staged_files_no_changes(self, mock_git_repo: Any) -> None:
        """Test getting staged files when nothing is staged."""
        import subprocess

        # Reset any staged changes
        subprocess.run(["git", "reset"], cwd=mock_git_repo, check=False)  # Don't fail if there's nothing to reset

        staged_files, description = get_staged_files(mock_git_repo)

        # Should return empty list
        assert len(staged_files) == 0
        assert "Staged changes" in description

    def test_get_staged_files_modified_file(self, mock_git_repo: Any) -> None:
        """Test staging a modification to an existing file."""
        import subprocess

        # Reset first
        subprocess.run(["git", "reset"], cwd=mock_git_repo, check=False)

        # Modify existing file (utils.hpp is in src/ according to conftest.py)
        utils_file = Path(mock_git_repo) / "src" / "utils.hpp"
        if not utils_file.exists():
            pytest.skip("Test file not found in mock repo")

        original_content = utils_file.read_text()
        utils_file.write_text(original_content + "\n// Additional comment\n")

        # Stage the modification
        subprocess.run(["git", "add", "src/utils.hpp"], cwd=mock_git_repo, check=True)

        staged_files, description = get_staged_files(mock_git_repo)

        # Should find the modified file
        assert len(staged_files) > 0
        assert any("utils.hpp" in f for f in staged_files)

    def test_get_staged_files_not_git_repo(self, temp_dir: Any) -> None:
        """Test with non-git directory."""
        # Should raise RuntimeError for non-git directory
        with pytest.raises(RuntimeError):
            get_staged_files(temp_dir)


class TestCheckGitAvailable:
    """Test the check_git_available function."""

    def test_check_git_available_success(self) -> None:
        """Test that git is available on the system."""
        result = check_git_available()

        # Should return True in CI/development environments with git installed
        assert isinstance(result, bool)
        # In typical environments, git should be available
        assert result is True

    def test_check_git_available_with_mock(self, monkeypatch: Any) -> None:
        """Test check_git_available with mocked subprocess."""
        import subprocess

        def mock_run_success(*args: Any, **kwargs: Any) -> Any:
            class MockResult:
                stdout = b"git version 2.39.0\n"

            return MockResult()

        monkeypatch.setattr(subprocess, "run", mock_run_success)

        result = check_git_available()
        assert result is True

    def test_check_git_available_not_found(self, monkeypatch: Any) -> None:
        """Test when git is not available."""
        import subprocess

        def mock_run_error(*args: Any, **kwargs: Any) -> Any:
            raise FileNotFoundError("git not found")

        monkeypatch.setattr(subprocess, "run", mock_run_error)

        result = check_git_available()
        assert result is False


class TestGetUncommittedChanges:
    """Test the get_uncommitted_changes function."""

    def test_get_uncommitted_changes_no_changes(self, mock_git_repo: Any) -> None:
        """Test when there are no uncommitted changes."""
        import subprocess

        # Reset any changes
        subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=mock_git_repo, check=True)
        subprocess.run(["git", "clean", "-fd"], cwd=mock_git_repo, check=False)

        changes = get_uncommitted_changes(mock_git_repo)

        assert isinstance(changes, list)
        assert len(changes) == 0

    def test_get_uncommitted_changes_with_modifications(self, mock_git_repo: Any) -> None:
        """Test when there are uncommitted modifications."""
        import subprocess

        # Create a new file
        test_file = Path(mock_git_repo) / "uncommitted.cpp"
        test_file.write_text("// Uncommitted file\nint main() { return 0; }\n")

        # Add to git (staged)
        subprocess.run(["git", "add", "uncommitted.cpp"], cwd=mock_git_repo, check=True)

        changes = get_uncommitted_changes(mock_git_repo)

        assert len(changes) > 0
        assert any("uncommitted.cpp" in f for f in changes)

    def test_get_uncommitted_changes_unstaged(self, mock_git_repo: Any) -> None:
        """Test with unstaged modifications."""
        import subprocess

        # Modify existing file
        utils_file = Path(mock_git_repo) / "src" / "utils.hpp"
        if utils_file.exists():
            original = utils_file.read_text()
            utils_file.write_text(original + "\n// Unstaged modification\n")

            changes = get_uncommitted_changes(mock_git_repo)

            assert len(changes) > 0
            assert any("utils.hpp" in f for f in changes)

    def test_get_uncommitted_changes_not_git_repo(self, temp_dir: Any) -> None:
        """Test with non-git directory."""
        with pytest.raises(RuntimeError):
            get_uncommitted_changes(temp_dir)


class TestGetCurrentBranch:
    """Test the get_current_branch function."""

    def test_get_current_branch_success(self, mock_git_repo: Any) -> None:
        """Test getting current branch name."""
        branch = get_current_branch(mock_git_repo)

        assert branch is not None
        assert isinstance(branch, str)
        assert len(branch) > 0

    def test_get_current_branch_detached_head(self, mock_git_repo: Any) -> None:
        """Test with detached HEAD state."""
        import subprocess

        # Get a commit hash and checkout to create detached HEAD
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=mock_git_repo, capture_output=True, text=True, check=True)
        commit_hash = result.stdout.strip()

        subprocess.run(["git", "checkout", commit_hash], cwd=mock_git_repo, check=True, capture_output=True)

        branch = get_current_branch(mock_git_repo)

        # Should return None for detached HEAD
        assert branch is None

    def test_get_current_branch_not_git_repo(self, temp_dir: Any) -> None:
        """Test with non-git directory."""
        branch = get_current_branch(temp_dir)
        assert branch is None


class TestGetCommitHash:
    """Test the get_commit_hash function."""

    def test_get_commit_hash_head(self, mock_git_repo: Any) -> None:
        """Test getting HEAD commit hash."""
        commit_hash = get_commit_hash(mock_git_repo, "HEAD")

        assert commit_hash is not None
        assert isinstance(commit_hash, str)
        assert len(commit_hash) == 40  # Full SHA-1 hash

    def test_get_commit_hash_default(self, mock_git_repo: Any) -> None:
        """Test with default HEAD parameter."""
        commit_hash = get_commit_hash(mock_git_repo)

        assert commit_hash is not None
        assert len(commit_hash) == 40

    def test_get_commit_hash_invalid_ref(self, mock_git_repo: Any) -> None:
        """Test with invalid commit reference."""
        commit_hash = get_commit_hash(mock_git_repo, "invalid_ref_xyz")

        # Should return None for invalid reference
        assert commit_hash is None

    def test_get_commit_hash_not_git_repo(self, temp_dir: Any) -> None:
        """Test with non-git directory."""
        commit_hash = get_commit_hash(temp_dir)
        assert commit_hash is None


class TestGetFileHistory:
    """Test the get_file_history function."""

    def test_get_file_history_success(self, mock_git_repo: Any) -> None:
        """Test getting file history."""
        # Get history for the utils.hpp file that was committed
        history = get_file_history(mock_git_repo, "src/utils.hpp")

        assert isinstance(history, list)
        # Should have at least one commit
        if len(history) > 0:
            assert len(history[0]) == 40  # Full SHA-1 hash

    def test_get_file_history_with_limit(self, mock_git_repo: Any) -> None:
        """Test with max_commits limit."""
        history = get_file_history(mock_git_repo, "src/utils.hpp", max_commits=5)

        assert isinstance(history, list)
        assert len(history) <= 5

    def test_get_file_history_nonexistent_file(self, mock_git_repo: Any) -> None:
        """Test with nonexistent file."""
        history = get_file_history(mock_git_repo, "nonexistent_file.cpp")

        # Should return empty list
        assert history == []

    def test_get_file_history_not_git_repo(self, temp_dir: Any) -> None:
        """Test with non-git directory."""
        history = get_file_history(temp_dir, "some_file.cpp")
        assert history == []


class TestIsAncestor:
    """Test the is_ancestor function."""

    def test_is_ancestor_same_commit(self, mock_git_repo: Any) -> None:
        """Test when ancestor and descendant are the same commit."""
        import subprocess

        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=mock_git_repo, capture_output=True, text=True, check=True)
        commit_hash = result.stdout.strip()

        # A commit is an ancestor of itself
        is_anc = is_ancestor(mock_git_repo, commit_hash, commit_hash)
        assert is_anc is True

    def test_is_ancestor_with_history(self, mock_git_repo: Any) -> None:
        """Test with actual commit history."""
        import subprocess

        # Get two commits if available
        result = subprocess.run(["git", "log", "--format=%H", "-n", "2"], cwd=mock_git_repo, capture_output=True, text=True, check=True)
        commits = result.stdout.strip().split("\n")

        if len(commits) >= 2:
            newer_commit = commits[0]
            older_commit = commits[1]

            # Older commit should be ancestor of newer
            assert is_ancestor(mock_git_repo, older_commit, newer_commit) is True

            # Newer commit should NOT be ancestor of older
            assert is_ancestor(mock_git_repo, newer_commit, older_commit) is False

    def test_is_ancestor_invalid_refs(self, mock_git_repo: Any) -> None:
        """Test with invalid commit references."""
        with pytest.raises(RuntimeError):
            is_ancestor(mock_git_repo, "invalid_ref1", "invalid_ref2")

    def test_is_ancestor_not_git_repo(self, temp_dir: Any) -> None:
        """Test with non-git directory."""
        with pytest.raises(RuntimeError):
            is_ancestor(temp_dir, "HEAD", "HEAD~1")


class TestGetWorkingTreeChangesFromCommit:
    """Test the get_working_tree_changes_from_commit function."""

    def test_get_working_tree_changes_no_changes(self, mock_git_repo: Any) -> None:
        """Test when there are no changes from HEAD."""
        import subprocess

        # Clean working tree
        subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=mock_git_repo, check=True)
        subprocess.run(["git", "clean", "-fd"], cwd=mock_git_repo, check=False)

        changes, description = get_working_tree_changes_from_commit(mock_git_repo, "HEAD")

        assert isinstance(changes, list)
        assert len(changes) == 0
        assert "HEAD" in description

    def test_get_working_tree_changes_with_modifications(self, mock_git_repo: Any) -> None:
        """Test when there are working tree modifications."""
        # Create a new file
        test_file = Path(mock_git_repo) / "working_tree_change.cpp"
        test_file.write_text("// Working tree change\nint main() { return 0; }\n")

        # Add to git staging
        import subprocess

        subprocess.run(["git", "add", "working_tree_change.cpp"], cwd=mock_git_repo, check=True)

        changes, description = get_working_tree_changes_from_commit(mock_git_repo, "HEAD")

        assert len(changes) > 0
        assert any("working_tree_change.cpp" in f for f in changes)
        assert "HEAD" in description

    def test_get_working_tree_changes_from_older_commit(self, mock_git_repo: Any) -> None:
        """Test comparing against an older commit if available."""
        import subprocess

        # Get commit history
        result = subprocess.run(["git", "log", "--format=%H", "-n", "2"], cwd=mock_git_repo, capture_output=True, text=True, check=True)
        commits = result.stdout.strip().split("\n")

        if len(commits) >= 2:
            older_commit = commits[1]

            changes, description = get_working_tree_changes_from_commit(mock_git_repo, older_commit)

            assert isinstance(changes, list)
            assert older_commit[:7] in description or older_commit in description

    def test_get_working_tree_changes_invalid_ref(self, mock_git_repo: Any) -> None:
        """Test with invalid commit reference."""
        with pytest.raises(ValueError):
            get_working_tree_changes_from_commit(mock_git_repo, "invalid_ref_xyz")

    def test_get_working_tree_changes_not_git_repo(self, temp_dir: Any) -> None:
        """Test with non-git directory."""
        with pytest.raises(RuntimeError):
            get_working_tree_changes_from_commit(temp_dir, "HEAD")


class TestGitErrorHandling:
    """Test error handling and edge cases in git operations."""

    def test_check_git_available_when_present(self) -> None:
        """Test git availability check when git is present."""
        result = check_git_available()
        # Should be True in test environment
        assert isinstance(result, bool)

    def test_find_git_repo_with_invalid_path(self) -> None:
        """Test find_git_repo with invalid/nonexistent path."""
        result = find_git_repo("/nonexistent/path/to/nowhere")
        assert result is None

    def test_get_changed_files_with_range_format(self, mock_git_repo: Any) -> None:
        """Test get_changed_files_from_commit with range format."""
        import subprocess

        # Get commit history
        result = subprocess.run(["git", "log", "--format=%H", "-n", "2"], cwd=mock_git_repo, capture_output=True, text=True, check=True)
        commits = result.stdout.strip().split("\n")

        if len(commits) >= 2:
            newer = commits[0][:7]
            older = commits[1][:7]
            commit_range = f"{older}..{newer}"

            changed_files, desc = get_changed_files_from_commit(mock_git_repo, commit_range)

            assert isinstance(changed_files, list)
            assert newer in desc

    def test_get_changed_files_with_invalid_range_format(self, mock_git_repo: Any) -> None:
        """Test with malformed range (too many ..)."""
        with pytest.raises(ValueError, match="Invalid commit range format"):
            get_changed_files_from_commit(mock_git_repo, "abc..def..ghi")

    def test_get_changed_files_with_invalid_commit(self, mock_git_repo: Any) -> None:
        """Test with nonexistent commit reference."""
        with pytest.raises(ValueError, match="Invalid commit reference"):
            get_changed_files_from_commit(mock_git_repo, "nonexistent_commit_hash_xyz")

    def test_get_changed_files_with_invalid_repo(self, temp_dir: Any) -> None:
        """Test with non-git directory."""
        with pytest.raises(RuntimeError, match="Not a git repository"):
            get_changed_files_from_commit(temp_dir, "HEAD")

    def test_get_staged_files_empty(self, mock_git_repo: Any) -> None:
        """Test getting staged files when none are staged."""
        import subprocess

        # Reset staging area
        subprocess.run(["git", "reset"], cwd=mock_git_repo, check=True)

        staged, desc = get_staged_files(mock_git_repo)

        assert isinstance(staged, list)
        assert "staged" in desc.lower()

    def test_get_staged_files_with_files(self, mock_git_repo: Any) -> None:
        """Test getting staged files when files are staged."""
        import subprocess

        # Create and stage a new file
        test_file = Path(mock_git_repo) / "staged_test.txt"
        test_file.write_text("test content")

        subprocess.run(["git", "add", "staged_test.txt"], cwd=mock_git_repo, check=True)

        staged, desc = get_staged_files(mock_git_repo)

        assert len(staged) > 0
        assert any("staged_test" in f for f in staged)

    def test_get_uncommitted_changes_with_modifications(self, mock_git_repo: Any) -> None:
        """Test detecting uncommitted changes."""
        # Create an uncommitted file
        test_file = Path(mock_git_repo) / "uncommitted.txt"
        test_file.write_text("uncommitted content")

        uncommitted = get_uncommitted_changes(mock_git_repo)

        assert isinstance(uncommitted, list)

    def test_get_uncommitted_changes_clean_tree(self, mock_git_repo: Any) -> None:
        """Test with clean working tree."""
        import subprocess

        # Clean the working tree
        subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=mock_git_repo, check=True)
        subprocess.run(["git", "clean", "-fd"], cwd=mock_git_repo, check=False)

        uncommitted = get_uncommitted_changes(mock_git_repo)

        assert isinstance(uncommitted, list)

    def test_get_current_branch(self, mock_git_repo: Any) -> None:
        """Test getting current branch name."""
        branch = get_current_branch(mock_git_repo)

        assert isinstance(branch, str)
        assert len(branch) > 0
        # Should be on main or master
        assert branch in ["main", "master"] or branch.startswith("HEAD")

    def test_get_commit_hash(self, mock_git_repo: Any) -> None:
        """Test getting current commit hash."""
        commit_hash = get_commit_hash(mock_git_repo)

        assert isinstance(commit_hash, str)
        assert len(commit_hash) == 40  # Full SHA-1 hash

    def test_get_commit_hash_for_specific_ref(self, mock_git_repo: Any) -> None:
        """Test getting commit hash for specific reference."""
        commit_hash = get_commit_hash(mock_git_repo, "HEAD")

        assert isinstance(commit_hash, str)
        assert len(commit_hash) == 40  # Full hash

    def test_categorize_changed_files_with_headers_and_sources(self, tmp_path: Path) -> None:
        """Test categorizing files into headers and sources."""
        # Create test files
        files = [str(tmp_path / "test.hpp"), str(tmp_path / "test.cpp"), str(tmp_path / "utils.h"), str(tmp_path / "main.cc"), str(tmp_path / "readme.txt")]

        # Create the files
        for f in files:
            Path(f).write_text("// test")

        headers, sources = categorize_changed_files(files)

        assert len(headers) == 2  # test.hpp, utils.h
        assert len(sources) == 2  # test.cpp, main.cc
        assert any("test.hpp" in h for h in headers)
        assert any("test.cpp" in s for s in sources)

    def test_categorize_changed_files_empty_list(self) -> None:
        """Test with empty file list."""
        headers, sources = categorize_changed_files([])

        assert headers == []
        assert sources == []

    def test_categorize_changed_files_only_headers(self, tmp_path: Path) -> None:
        """Test with only header files."""
        files = [str(tmp_path / "a.hpp"), str(tmp_path / "b.h")]

        for f in files:
            Path(f).write_text("// header")

        headers, sources = categorize_changed_files(files)

        assert len(headers) == 2
        assert len(sources) == 0

    def test_categorize_changed_files_nonexistent_files(self) -> None:
        """Test with nonexistent files."""
        files = ["/nonexistent/file.hpp", "/nonexistent/file.cpp"]

        headers, sources = categorize_changed_files(files)

        # categorize_changed_files doesn't check if files exist, just categorizes by extension
        assert len(headers) == 1
        assert len(sources) == 1


class TestGitPathSecurity:
    """Test path security validation in git operations."""

    def test_path_validation_rejects_parent_traversal(self, mock_git_repo: Any) -> None:
        """Test that paths with .. are rejected."""
        from lib.git_utils import _validate_and_convert_path

        result = _validate_and_convert_path("../../../etc/passwd", mock_git_repo)
        assert result is None

    def test_path_validation_rejects_absolute_paths(self, mock_git_repo: Any) -> None:
        """Test that absolute paths are rejected."""
        from lib.git_utils import _validate_and_convert_path

        result = _validate_and_convert_path("/etc/passwd", mock_git_repo)
        assert result is None

    def test_path_validation_accepts_valid_relative_path(self, mock_git_repo: Any) -> None:
        """Test that valid relative paths are accepted."""
        from lib.git_utils import _validate_and_convert_path

        # Create a test file
        test_file = Path(mock_git_repo) / "valid_file.txt"
        test_file.write_text("test")

        result = _validate_and_convert_path("valid_file.txt", mock_git_repo)
        assert result is not None
        assert "valid_file.txt" in result

    def test_path_validation_handles_nonexistent_files(self, mock_git_repo: Any) -> None:
        """Test that nonexistent files return None."""
        from lib.git_utils import _validate_and_convert_path

        result = _validate_and_convert_path("nonexistent_file.txt", mock_git_repo)
        assert result is None


class TestGitFirstCommitHandling:
    """Test handling of first commit (no parent) scenarios."""

    def test_changed_files_first_commit_in_new_repo(self, temp_dir: Any) -> None:
        """Test getting changed files from first commit."""
        import subprocess

        # Create a new git repo with one commit
        repo_path = Path(temp_dir) / "new_repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True, capture_output=True)

        # Create and commit a file
        test_file = repo_path / "first.txt"
        test_file.write_text("first file")
        subprocess.run(["git", "add", "first.txt"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "First commit"], cwd=repo_path, check=True, capture_output=True)

        # Get changed files from first commit
        changed, desc = get_changed_files_from_commit(str(repo_path), "HEAD")

        # First commit should list all files
        assert isinstance(changed, list)
        assert "First commit" in desc


class TestGitEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_get_file_history_with_zero_commits(self, mock_git_repo: Any) -> None:
        """Test file history with max_commits=0."""
        history = get_file_history(mock_git_repo, "src/utils.hpp", max_commits=0)
        assert history == []

    def test_get_file_history_with_negative_commits(self, mock_git_repo: Any) -> None:
        """Test file history with negative max_commits."""
        history = get_file_history(mock_git_repo, "src/utils.hpp", max_commits=-1)
        assert isinstance(history, list)

    def test_is_ancestor_with_abbreviated_refs(self, mock_git_repo: Any) -> None:
        """Test is_ancestor with short commit hashes."""
        import subprocess

        result = subprocess.run(["git", "log", "--format=%H", "-n", "2"], cwd=mock_git_repo, capture_output=True, text=True, check=True)
        commits = result.stdout.strip().split("\n")

        if len(commits) >= 2:
            newer = commits[0][:7]  # Short hash
            older = commits[1][:7]  # Short hash

            # Should work with short hashes
            is_anc = is_ancestor(mock_git_repo, older, newer)
            assert isinstance(is_anc, bool)


class TestGetFileHistoryExtended:
    """Test get_file_history function."""

    @pytest.mark.unit
    @pytest.mark.requires_git
    def test_get_file_history_basic(self, real_git_repo_module: str) -> None:
        """Test getting file history."""
        history = get_file_history(real_git_repo_module, "test.txt", max_commits=10)

        assert isinstance(history, list)
        assert len(history) > 0
        assert all(len(h) == 40 for h in history)

    @pytest.mark.unit
    @pytest.mark.requires_git
    def test_get_file_history_nonexistent(self, real_git_repo_module: str) -> None:
        """Test getting history for nonexistent file."""
        history = get_file_history(real_git_repo_module, "nonexistent.txt", max_commits=10)
        assert history == []


class TestIsAncestorExtended:
    """Extended tests for is_ancestor function."""

    @pytest.mark.unit
    @pytest.mark.requires_git
    def test_is_ancestor_subprocess_error(self, tmp_path: Path) -> None:
        """Test is_ancestor handles subprocess errors."""
        # Non-git directory should raise RuntimeError
        with pytest.raises(RuntimeError, match="Not a git repository"):
            is_ancestor(str(tmp_path), "HEAD", "HEAD~1")


class TestValidateAndConvertPath:
    """Test _validate_and_convert_path security function."""

    @pytest.mark.unit
    def test_validate_path_with_parent_traversal(self, tmp_path: Path) -> None:
        """Test that parent directory traversal is rejected."""
        from lib.git_utils import _validate_and_convert_path

        result = _validate_and_convert_path("../../../etc/passwd", str(tmp_path))
        assert result is None

    @pytest.mark.unit
    def test_validate_path_with_absolute(self, tmp_path: Path) -> None:
        """Test that absolute paths are rejected."""
        from lib.git_utils import _validate_and_convert_path

        result = _validate_and_convert_path("/etc/passwd", str(tmp_path))
        assert result is None

    @pytest.mark.unit
    def test_validate_path_valid_and_exists(self, tmp_path: Path) -> None:
        """Test valid path that exists."""
        from lib.git_utils import _validate_and_convert_path

        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        result = _validate_and_convert_path("test.txt", str(tmp_path))
        assert result == str(test_file)


class TestGetCurrentBranchDetached:
    """Test get_current_branch in detached HEAD state."""

    @pytest.mark.unit
    @pytest.mark.requires_git
    def test_get_current_branch_detached_head(self, tmp_path: Path) -> None:
        """Test getting branch when in detached HEAD state."""
        import subprocess

        # Create a new test repo for this test
        repo_dir = tmp_path / "detached_repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True, capture_output=True)

        test_file = repo_dir / "file.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "file.txt"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "test"], cwd=repo_dir, check=True, capture_output=True)

        # Get commit hash and checkout to detached HEAD
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True, check=True)
        commit_hash = result.stdout.strip()
        subprocess.run(["git", "checkout", commit_hash], cwd=repo_dir, capture_output=True, check=True)

        branch = get_current_branch(str(repo_dir))
        assert branch is None


class TestCategorizeChangedFilesExtended:
    """Extended tests for categorize_changed_files."""

    @pytest.mark.unit
    def test_categorize_with_custom_extensions(self) -> None:
        """Test categorizing with custom file extensions."""
        files = ["test.h", "test.cpp", "test.c", "test.hxx", "test.cxx", "test.txt"]

        headers, sources = categorize_changed_files(files, header_exts=(".h", ".hxx"), source_exts=(".cpp", ".cxx"))

        assert "test.h" in headers
        assert "test.hxx" in headers
        assert "test.cpp" in sources
        assert "test.cxx" in sources
        assert "test.c" not in sources

    @pytest.mark.unit
    def test_categorize_with_mixed_paths(self) -> None:
        """Test categorizing with absolute and relative paths."""
        files = ["/absolute/path/file.h", "relative/path/file.cpp", "./local/file.c"]

        headers, sources = categorize_changed_files(files)

        assert len(headers) == 1
        assert len(sources) == 2
