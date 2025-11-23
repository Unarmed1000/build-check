#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
"""Utilities for Git operations."""

import os
import re
import logging
import subprocess
from typing import Any, Callable, DefaultDict, Dict, List, Optional, Set, Tuple
from collections import defaultdict

from git import Repo, GitCommandError, InvalidGitRepositoryError, BadName, BadObject
from git.exc import GitError

logger = logging.getLogger(__name__)


def _validate_and_convert_path(relative_path: str, repo_dir: str) -> Optional[str]:
    """Validate and convert a relative path to absolute path with security checks.

    Args:
        relative_path: Relative path from git
        repo_dir: Repository root directory

    Returns:
        Absolute path if valid and exists, None otherwise
    """
    # Security: Reject paths attempting traversal outside repo
    if ".." in relative_path or relative_path.startswith("/"):
        logger.warning("Skipping potentially malicious path: %s", relative_path)
        return None

    abs_path = os.path.abspath(os.path.join(repo_dir, relative_path))
    # Verify the resolved path is within the repo
    try:
        if not abs_path.startswith(os.path.abspath(repo_dir)):
            logger.warning("Skipping path outside repository: %s", relative_path)
            return None
    except (OSError, ValueError):
        logger.warning("Skipping invalid path: %s", relative_path)
        return None

    if os.path.exists(abs_path):
        return abs_path

    logger.debug("Changed file not found: %s", abs_path)
    return None


def _extract_files_from_diffs(diffs: Any, repo_dir: str) -> List[str]:
    """Extract file paths from git diff objects.

    Args:
        diffs: GitPython diff object
        repo_dir: Repository root directory

    Returns:
        List of absolute file paths
    """
    changed_files = []
    for diff_item in diffs:
        # Get the path (handle renames by using b_path which is the new path)
        path = diff_item.b_path if diff_item.b_path else diff_item.a_path
        if path:
            abs_path = _validate_and_convert_path(path, repo_dir)
            if abs_path:
                changed_files.append(abs_path)
    return changed_files


def find_git_repo(start_path: str) -> Optional[str]:
    """Find the git repository root by searching upward from start_path.

    Args:
        start_path: Directory to start searching from

    Returns:
        Absolute path to git repository root, or None if not found
    """
    try:
        repo = Repo(start_path, search_parent_directories=True)
        repo_root = repo.working_dir
        if repo_root is not None:
            logger.debug("Found git repository at: %s", repo_root)
            return str(repo_root)
    except (InvalidGitRepositoryError, GitError):
        pass
    return None


def check_git_available() -> bool:
    """Check if git is available in PATH.

    Returns:
        True if git is available, False otherwise
    """
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True, timeout=5)
        logger.debug("Found git: %s", result.stdout.strip())
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False


def get_changed_files_from_commit(repo_dir: str, commit: str = "HEAD") -> Tuple[List[str], str]:
    """Get list of changed files from a git commit or range.

    Args:
        repo_dir: Path to git repository
        commit: Git commit reference (e.g., 'HEAD', 'abc123', 'HEAD~5..HEAD')

    Returns:
        Tuple of (list of changed file paths as absolute paths, commit description)

    Raises:
        RuntimeError: If git command fails
        ValueError: If commit format is invalid
    """
    try:
        repo = Repo(repo_dir)
    except InvalidGitRepositoryError as e:
        raise RuntimeError(f"Not a git repository: {repo_dir}") from e

    try:
        # Validate commit format
        if ".." in commit:
            # Range format: HEAD~5..HEAD
            parts = commit.split("..")
            if len(parts) != 2:
                raise ValueError(f"Invalid commit range format: {commit}")
            start_commit, end_commit = parts

            # Get commit description from end commit
            try:
                end_commit_obj = repo.commit(end_commit)
                summary = end_commit_obj.summary.decode("utf-8") if isinstance(end_commit_obj.summary, bytes) else end_commit_obj.summary
                commit_desc = f"{end_commit_obj.hexsha[:7]} {summary}"
            except (BadName, BadObject) as e:
                raise ValueError(f"Invalid commit reference: {end_commit}") from e

            # Get changed files in range
            try:
                start_commit_obj = repo.commit(start_commit)
                diffs = start_commit_obj.diff(end_commit_obj)
            except (BadName, BadObject) as e:
                raise ValueError(f"Invalid commit reference: {start_commit}") from e

            changed_files = _extract_files_from_diffs(diffs, repo_dir)
        else:
            # Single commit format
            try:
                commit_obj = repo.commit(commit)
            except (BadName, BadObject) as e:
                raise ValueError(f"Invalid commit reference: {commit}") from e

            # Get commit description
            summary = commit_obj.summary.decode("utf-8") if isinstance(commit_obj.summary, bytes) else commit_obj.summary
            commit_desc = f"{commit_obj.hexsha[:7]} {summary}"

            # Get changed files (compare with parent)
            if commit_obj.parents:
                diffs = commit_obj.parents[0].diff(commit_obj)
                changed_files = _extract_files_from_diffs(diffs, repo_dir)
            else:
                # First commit - all files are new
                changed_files = []
                for item in commit_obj.tree.traverse():
                    # GitPython tree traversal returns complex union types
                    if hasattr(item, "type") and hasattr(item, "path"):
                        if item.type == "blob":  # type: ignore[union-attr]
                            path = str(item.path)  # type: ignore[union-attr]
                            abs_path = _validate_and_convert_path(path, repo_dir)
                            if abs_path:
                                changed_files.append(abs_path)

        logger.info("Found %s changed files in %s", len(changed_files), commit)
        return changed_files, commit_desc

    except (ValueError, InvalidGitRepositoryError):
        raise
    except GitCommandError as e:
        error_msg = str(e)
        if "unknown revision" in error_msg.lower() or "bad revision" in error_msg.lower():
            raise ValueError(f"Invalid commit reference: {commit}") from e
        raise RuntimeError(f"Git command failed: {error_msg}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error getting changed files: {e}") from e


def get_staged_files(repo_dir: str) -> Tuple[List[str], str]:
    """Get list of staged files ready to be committed.

    Args:
        repo_dir: Path to git repository

    Returns:
        Tuple of (list of staged file paths as absolute paths, description)

    Raises:
        RuntimeError: If git command fails
    """
    try:
        repo = Repo(repo_dir)

        # Get staged changes (diff between HEAD and index)
        diffs = repo.index.diff("HEAD")
        changed_files = _extract_files_from_diffs(diffs, repo_dir)

        logger.info("Found %s staged files", len(changed_files))
        description = f"Staged changes ({len(changed_files)} files)"
        return changed_files, description

    except InvalidGitRepositoryError as e:
        raise RuntimeError(f"Not a git repository: {repo_dir}") from e
    except GitCommandError as e:
        raise RuntimeError(f"Git command failed: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error getting staged files: {e}") from e


def get_uncommitted_changes(repo_dir: str) -> List[str]:
    """Get list of uncommitted changed files (staged and unstaged).

    Args:
        repo_dir: Path to git repository

    Returns:
        List of changed file paths (absolute paths)

    Raises:
        RuntimeError: If git command fails
    """
    try:
        repo = Repo(repo_dir)

        # Get both staged and unstaged changes (diff between HEAD and working tree)
        diffs = repo.head.commit.diff(None)
        changed_files = _extract_files_from_diffs(diffs, repo_dir)

        logger.info("Found %s uncommitted changes", len(changed_files))
        return changed_files

    except InvalidGitRepositoryError as e:
        raise RuntimeError(f"Not a git repository: {repo_dir}") from e
    except GitCommandError as e:
        raise RuntimeError(f"Git command failed: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error getting uncommitted changes: {e}") from e


def get_current_branch(repo_dir: str) -> Optional[str]:
    """Get the current git branch name.

    Args:
        repo_dir: Path to git repository

    Returns:
        Current branch name, or None if detached HEAD
    """
    try:
        repo = Repo(repo_dir)
        # This will raise TypeError if HEAD is detached
        branch_name = repo.active_branch.name
        return branch_name
    except TypeError:
        # Detached HEAD state
        return None
    except Exception as e:
        logger.debug("Could not get current branch: %s", e)
        return None


def get_commit_hash(repo_dir: str, commit: str = "HEAD") -> Optional[str]:
    """Get the full commit hash for a commit reference.

    Args:
        repo_dir: Path to git repository
        commit: Git commit reference

    Returns:
        Full commit hash, or None if not found
    """
    try:
        repo = Repo(repo_dir)
        commit_obj = repo.commit(commit)
        return commit_obj.hexsha
    except Exception as e:
        logger.debug("Could not get commit hash for %s: %s", commit, e)
        return None


def categorize_changed_files(
    changed_files: List[str], header_exts: Tuple[str, ...] = (".h", ".hpp", ".hxx", ".hh"), source_exts: Tuple[str, ...] = (".cpp", ".c", ".cc", ".cxx")
) -> Tuple[List[str], List[str]]:
    """Categorize changed files into headers and sources.

    Args:
        changed_files: List of file paths
        header_exts: Tuple of header file extensions
        source_exts: Tuple of source file extensions

    Returns:
        Tuple of (header_files, source_files)

    Raises:
        TypeError: If changed_files is not a list
    """
    if not isinstance(changed_files, list):
        raise TypeError(f"changed_files must be a list, got {type(changed_files).__name__}")

    headers = []
    sources = []

    for filepath in changed_files:
        if any(filepath.endswith(ext) for ext in header_exts):
            headers.append(filepath)
        elif any(filepath.endswith(ext) for ext in source_exts):
            sources.append(filepath)

    logger.debug("Categorized: %s headers, %s sources", len(headers), len(sources))
    return headers, sources


def get_file_history(repo_dir: str, filepath: str, max_commits: int = 10) -> List[str]:
    """Get commit history for a specific file.

    Args:
        repo_dir: Path to git repository
        filepath: Path to file (relative to repo root)
        max_commits: Maximum number of commits to retrieve

    Returns:
        List of commit hashes (most recent first)
    """
    try:
        repo = Repo(repo_dir)
        commits = list(repo.iter_commits(paths=filepath, max_count=max_commits))
        return [commit.hexsha for commit in commits]
    except Exception as e:
        logger.debug("Could not get file history for %s: %s", filepath, e)
        return []


def is_ancestor(repo_dir: str, ancestor_ref: str, descendant_ref: str) -> bool:
    """Check if ancestor_ref is an ancestor of descendant_ref.

    Uses git merge-base --is-ancestor to verify linear ancestry.

    Args:
        repo_dir: Path to git repository
        ancestor_ref: The potentially older commit reference
        descendant_ref: The potentially newer commit reference

    Returns:
        True if ancestor_ref is an ancestor of descendant_ref, False otherwise

    Raises:
        RuntimeError: If git command fails for reasons other than ancestry check
    """
    try:
        repo = Repo(repo_dir)
        ancestor_commit = repo.commit(ancestor_ref)
        descendant_commit = repo.commit(descendant_ref)
        result = repo.is_ancestor(ancestor_commit, descendant_commit)
        if result:
            logger.debug("%s is ancestor of %s", ancestor_ref, descendant_ref)
        else:
            logger.debug("%s is NOT ancestor of %s", ancestor_ref, descendant_ref)
        return result
    except (BadName, BadObject) as e:
        raise RuntimeError(f"Invalid commit reference: {e}") from e
    except InvalidGitRepositoryError as e:
        raise RuntimeError(f"Not a git repository: {repo_dir}") from e
    except GitCommandError as e:
        raise RuntimeError(f"Git command failed: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error checking ancestry: {e}") from e


def validate_ancestor_relationship(repo_dir: str, from_ref: str, to_ref: str = "HEAD") -> None:
    """Validate that from_ref is a linear ancestor of to_ref.

    This ensures that comparing from_ref to working tree represents a linear
    progression of changes, not divergent branches.

    Args:
        repo_dir: Path to git repository
        from_ref: Git reference that should be an ancestor
        to_ref: Git reference to check against (default: HEAD)

    Raises:
        ValueError: If from_ref is not a linear ancestor of to_ref
        RuntimeError: If git operations fail
    """
    try:
        repo = Repo(repo_dir)
    except InvalidGitRepositoryError as e:
        raise RuntimeError(f"Not a git repository: {repo_dir}") from e

    try:
        # Verify both references exist
        try:
            from_commit = repo.commit(from_ref)
            to_commit = repo.commit(to_ref)
        except (BadName, BadObject) as e:
            raise ValueError(f"Invalid git reference: {e}") from e

        # Check if from_ref is an ancestor of to_ref
        if not repo.is_ancestor(from_commit, to_commit):
            # Get short hashes for error message
            from_hash = from_commit.hexsha[:7]
            to_hash = to_commit.hexsha[:7]

            error_msg = (
                f"Reference '{from_ref}' ({from_hash}) is not a linear ancestor of '{to_ref}' ({to_hash}).\n"
                f"This usually means the branches have diverged.\n\n"
                f"To find a common ancestor, use:\n"
                f"  git merge-base {from_ref} {to_ref}\n\n"
                f"To visualize the branch structure, use:\n"
                f"  git log --oneline --graph --all"
            )
            raise ValueError(error_msg)

        logger.debug("Validated: %s is an ancestor of %s", from_ref, to_ref)

    except ValueError:
        raise
    except InvalidGitRepositoryError as exc:
        raise RuntimeError(f"Not a git repository: {repo_dir}") from exc
    except GitCommandError as e:
        raise RuntimeError(f"Git command failed: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error validating ancestry: {e}") from e


def get_working_tree_changes_from_commit(repo_dir: str, base_ref: str) -> Tuple[List[str], str]:
    """Get all changes from base_ref to current working tree (staged + unstaged).

    This includes all committed changes from base_ref to HEAD, plus all uncommitted changes.

    Args:
        repo_dir: Path to git repository
        base_ref: Base commit reference to compare against

    Returns:
        Tuple of (list of changed file paths as absolute paths, description)

    Raises:
        RuntimeError: If git command fails
        ValueError: If base_ref is invalid
    """
    try:
        repo = Repo(repo_dir)
    except InvalidGitRepositoryError as e:
        raise RuntimeError(f"Not a git repository: {repo_dir}") from e

    try:
        # Get all changes from base_ref to current working tree
        # This includes committed + staged + unstaged changes
        try:
            base_commit = repo.commit(base_ref)
        except (BadName, BadObject) as e:
            raise ValueError(f"Invalid commit reference: {base_ref}") from e

        # Diff from base_ref to working tree (None means working tree)
        diffs = base_commit.diff(None)
        changed_files = _extract_files_from_diffs(diffs, repo_dir)

        logger.info("Found %s changes from %s to working tree", len(changed_files), base_ref)
        description = f"Working tree changes from {base_ref} ({len(changed_files)} files)"
        return changed_files, description

    except (ValueError, InvalidGitRepositoryError):
        raise
    except GitCommandError as e:
        error_msg = str(e)
        if "unknown revision" in error_msg.lower() or "bad revision" in error_msg.lower():
            raise ValueError(f"Invalid commit reference: {base_ref}") from e
        raise RuntimeError(f"Git command failed: {error_msg}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error getting working tree changes: {e}") from e


def compute_change_frequency(headers: set[str], repo_path: Optional[str] = None, max_commits: int = 100, since: Optional[str] = None) -> dict[str, int]:
    """Compute change frequency for headers from git history.

    Analyzes git commit history to identify which headers change most frequently.
    Volatile headers with high fan-in are the worst combination for build times.

    Args:
        headers: Set of header file paths to analyze
        repo_path: Git repository path (auto-detected if None)
        max_commits: Maximum number of commits to analyze (default: 100)
        since: Only commits since this time (e.g., "1 month ago", "2024-01-01")

    Returns:
        Dictionary mapping header path to number of times it was changed

    Raises:
        InvalidGitRepositoryError: If not in a git repository
        RuntimeError: If git operation fails
    """
    if not headers:
        return {}

    # Find repository
    if repo_path is None:
        # Try to find repo from first header path
        sample_header = next(iter(headers))
        repo_path = find_git_repo(os.path.dirname(sample_header))
        if repo_path is None:
            logger.warning("Not in a git repository - cannot compute change frequency")
            return {}

    try:
        repo = Repo(repo_path)
        repo_dir = str(repo.working_dir)

        # Build set of relative paths for fast lookup
        rel_headers = set()
        abs_to_rel = {}
        for header in headers:
            try:
                rel_path = os.path.relpath(header, repo_dir)
                rel_headers.add(rel_path)
                abs_to_rel[header] = rel_path
            except (ValueError, OSError):
                # Header outside repo or path error
                continue

        if not rel_headers:
            logger.warning("No headers found in git repository")
            return {}

        # Count changes per header
        change_counts: dict[str, int] = {header: 0 for header in headers}

        # Build iterator for commits
        kwargs: dict[str, Any] = {"max_count": max_commits}
        if since:
            kwargs["since"] = since

        commits = list(repo.iter_commits(**kwargs))
        logger.debug("Analyzing %d commits for change frequency", len(commits))

        # Analyze each commit
        for i, commit in enumerate(commits):
            if i == 0:
                # First commit - compare with HEAD
                continue

            try:
                # Get files changed in this commit
                parent = commit.parents[0] if commit.parents else None
                if parent is None:
                    continue

                diffs = parent.diff(commit)

                for diff_item in diffs:
                    # Check both old and new paths (handles renames)
                    for path in [diff_item.a_path, diff_item.b_path]:
                        if path and path in rel_headers:
                            # Find the absolute path
                            for abs_path, rel_path in abs_to_rel.items():
                                if rel_path == path:
                                    change_counts[abs_path] += 1
                                    break

            except (GitCommandError, BadObject) as e:
                logger.debug("Skipping commit %s: %s", commit.hexsha[:8], e)
                continue

        # Filter out headers with zero changes
        result = {h: count for h, count in change_counts.items() if count > 0}

        logger.info("Computed change frequency for %d/%d headers", len(result), len(headers))
        return result

    except InvalidGitRepositoryError:
        logger.warning("Not in a valid git repository")
        return {}
    except Exception as e:
        logger.error("Error computing change frequency: %s", e)
        return {}


def parse_includes_from_content(content: str, skip_system_headers: bool = True) -> List[str]:
    """Parse #include directives from file content.

    Extracts include directives from C/C++ source/header content, distinguishing
    between system headers (<...>) and project headers ("...").

    Args:
        content: File content to parse
        skip_system_headers: If True, skip #include <...> directives (default: True)

    Returns:
        List of raw include paths (not resolved to absolute paths)

    Example:
        >>> content = '''
        ... #include <iostream>
        ... #include "my_header.h"
        ... #include <vector>
        ... '''
        >>> parse_includes_from_content(content, skip_system_headers=True)
        ['my_header.h']
        >>> parse_includes_from_content(content, skip_system_headers=False)
        ['iostream', 'my_header.h', 'vector']
    """
    includes = []

    # Regex patterns for different include styles
    quoted_include = re.compile(r'^\s*#\s*include\s+"([^"]+)"')  # #include "file.h"
    angled_include = re.compile(r"^\s*#\s*include\s+<([^>]+)>")  # #include <file.h>

    for line in content.splitlines():
        # Skip C++ comments
        if "//" in line:
            line = line[: line.index("//")]

        # Check for quoted includes (project headers)
        match = quoted_include.match(line)
        if match:
            includes.append(match.group(1))
            continue

        # Check for angled includes (system headers)
        if not skip_system_headers:
            match = angled_include.match(line)
            if match:
                includes.append(match.group(1))

    return includes


def get_working_tree_changes_from_commit_batched(
    base_ref: str = "HEAD", repo_path: Optional[str] = None, batch_size: int = 100, progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Tuple[List[str], str]:
    """Get changed files from base_ref to working tree, with batched processing.

    This is a batched version of get_working_tree_changes_from_commit() that
    yields results in chunks for better progress reporting on large diffs.

    Args:
        base_ref: Git reference to compare against (default: "HEAD")
        repo_path: Git repository path (auto-detected if None)
        batch_size: Number of files to process per batch (default: 100)
        progress_callback: Optional callback function(current, total, message)
                          called after processing each batch

    Returns:
        Tuple of (list of changed file paths, description string)

    Raises:
        ValueError: If base_ref is invalid
        InvalidGitRepositoryError: If not in a git repository
        RuntimeError: If git operation fails
    """
    # Auto-detect repo path if not provided
    if repo_path is None:
        try:
            repo = Repo(search_parent_directories=True)
            repo_path = str(repo.working_dir)
        except InvalidGitRepositoryError as e:
            raise RuntimeError("Not in a git repository and no repo_path provided") from e

    # Get all changes first
    all_changes, description = get_working_tree_changes_from_commit(repo_path, base_ref)

    if not all_changes:
        return all_changes, description

    # Process in batches for progress reporting
    total_files = len(all_changes)
    num_batches = (total_files + batch_size - 1) // batch_size

    if progress_callback and num_batches > 1:
        for batch_idx in range(num_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, total_files)
            batch_count = end_idx - start_idx

            progress_callback(end_idx, total_files, f"Processing changes: batch {batch_idx + 1}/{num_batches} ({batch_count} files)")

    return all_changes, description


def reconstruct_head_graph(
    working_tree_headers: Set[str],
    working_tree_graph: DefaultDict[str, Set[str]],
    base_ref: str = "HEAD",
    repo_path: Optional[str] = None,
    compile_commands_db: Optional[Any] = None,
    project_root: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Tuple[Set[str], DefaultDict[str, Set[str]]]:
    """Reconstruct the baseline dependency graph from git history.

    Builds the dependency graph as it existed at base_ref by:
    1. Starting with the working tree graph
    2. Removing files added in working tree (not in baseline)
    3. Restoring files deleted in working tree (were in baseline)
    4. For modified files: fetch HEAD version, parse includes, resolve dependencies

    Args:
        working_tree_headers: Set of headers in working tree build
        working_tree_graph: Header-to-header dependency graph from working tree
        base_ref: Git reference for baseline (default: "HEAD")
        repo_path: Git repository path (auto-detected if None)
        compile_commands_db: Compilation database for include resolution
        project_root: Project root directory for path resolution
        progress_callback: Optional callback(current, total, message) for progress

    Returns:
        Tuple of (baseline_headers, baseline_graph)

    Raises:
        ValueError: If base_ref is invalid
        InvalidGitRepositoryError: If not in a git repository
        RuntimeError: If git operations fail

    Note:
        This function skips system headers (#include <...>) during parsing.
        Only project headers (#include "...") are added to the baseline graph.
    """
    # Find repository
    if repo_path is None:
        sample_path = next(iter(working_tree_headers)) if working_tree_headers else os.getcwd()
        repo_path = find_git_repo(os.path.dirname(sample_path))
        if repo_path is None:
            raise InvalidGitRepositoryError("Not in a git repository")

    try:
        repo = Repo(repo_path)
        repo_dir = str(repo.working_dir)

        # Get diff from base_ref to working tree
        try:
            base_commit = repo.commit(base_ref)
        except (BadName, BadObject) as e:
            raise ValueError(f"Invalid commit reference: {base_ref}") from e

        diffs = base_commit.diff(None)

        # Categorize changes
        added_files = []  # New in working tree, not in baseline
        deleted_files = []  # In baseline, removed in working tree
        modified_files = []  # In both, but content differs

        # Track all headers that exist in HEAD
        headers_in_head = set()

        for diff_item in diffs:
            path = diff_item.b_path if diff_item.b_path else diff_item.a_path
            if not path:
                continue

            abs_path = os.path.abspath(os.path.join(repo_dir, path))

            # Only process headers
            if not abs_path.endswith((".h", ".hpp", ".hxx", ".hh")):
                continue

            if diff_item.new_file:
                added_files.append(abs_path)
            elif diff_item.deleted_file:
                deleted_files.append(abs_path)
            elif diff_item.a_blob:  # File exists in HEAD - it's modified
                modified_files.append((abs_path, path))  # Store both absolute and relative
                headers_in_head.add(abs_path)

        # Also check for untracked headers (not in git diff, but in working_tree_headers)
        # These are headers detected by clang-scan-deps that don't exist in HEAD
        try:
            # Get all files tracked in HEAD
            for item in base_commit.tree.traverse():
                # Type check: only process items with path attribute (Blob/Tree, not tuples)
                if not hasattr(item, "path"):
                    continue
                item_path = getattr(item, "path", None)
                if item_path is None:
                    continue
                abs_path = os.path.abspath(os.path.join(repo_dir, item_path))
                if abs_path.endswith((".h", ".hpp", ".hxx", ".hh")):
                    headers_in_head.add(abs_path)
        except Exception as e:
            logger.warning("Failed to enumerate HEAD tree: %s", e)

        # Any header in working tree but not in HEAD is a new file
        for header in working_tree_headers:
            if header not in headers_in_head and header not in added_files:
                added_files.append(header)

        # Step 1: Clone working tree graph
        baseline_headers = working_tree_headers.copy()
        baseline_graph: DefaultDict[str, Set[str]] = defaultdict(set)
        for header, deps in working_tree_graph.items():
            baseline_graph[header] = deps.copy()

        total_operations = len(added_files) + len(deleted_files) + len(modified_files)
        current_operation = 0

        # Step 2: Remove files added in working tree (not in baseline)
        for added_file in added_files:
            if added_file in baseline_headers:
                baseline_headers.remove(added_file)
            if added_file in baseline_graph:
                del baseline_graph[added_file]
            # Remove references to this file from other headers' dependencies
            for header in baseline_graph:
                baseline_graph[header].discard(added_file)

            current_operation += 1
            if progress_callback and total_operations > 50:
                progress_callback(current_operation, total_operations, f"Removing added files from baseline: {os.path.basename(added_file)}")

        # Step 3: Restore deleted files (were in baseline)
        for deleted_file in deleted_files:
            try:
                # Get file content from base_ref
                rel_path = os.path.relpath(deleted_file, repo_dir)
                blob_content = base_commit.tree[rel_path].data_stream.read().decode("utf-8", errors="ignore")

                # Parse includes (skip system headers)
                includes = parse_includes_from_content(blob_content, skip_system_headers=True)

                # Resolve includes to absolute paths
                resolved_deps = set()
                for include_path in includes:
                    # Try to match by relative path suffix first (more accurate)
                    matched = False
                    for header in working_tree_headers:
                        if header.endswith(include_path) or header.endswith(os.path.sep + include_path):
                            resolved_deps.add(header)
                            matched = True
                            break

                    # Fallback to basename matching if suffix match fails
                    if not matched:
                        include_basename = os.path.basename(include_path)
                        for header in working_tree_headers:
                            if os.path.basename(header) == include_basename:
                                resolved_deps.add(header)
                                break

                # Add to baseline
                baseline_headers.add(deleted_file)
                baseline_graph[deleted_file] = resolved_deps

            except Exception as e:
                logger.warning("Failed to restore deleted file %s: %s", deleted_file, e)

            current_operation += 1
            if progress_callback and total_operations > 50:
                progress_callback(current_operation, total_operations, f"Restoring deleted files: {os.path.basename(deleted_file)}")

        # Step 4: Update modified files with baseline content
        for abs_path, rel_path in modified_files:
            try:
                # Get HEAD version content
                blob_content = base_commit.tree[rel_path].data_stream.read().decode("utf-8", errors="ignore")

                # Parse includes (skip system headers)
                includes = parse_includes_from_content(blob_content, skip_system_headers=True)

                # Resolve includes to absolute paths
                resolved_deps = set()
                for include_path in includes:
                    # Try to match by relative path suffix first (more accurate)
                    matched = False
                    for header in baseline_headers:
                        if header.endswith(include_path) or header.endswith(os.path.sep + include_path):
                            resolved_deps.add(header)
                            matched = True
                            break

                    # Fallback to basename matching if suffix match fails
                    if not matched:
                        include_basename = os.path.basename(include_path)
                        for header in baseline_headers:
                            if os.path.basename(header) == include_basename:
                                resolved_deps.add(header)
                                break

                # Update baseline graph with HEAD version dependencies
                baseline_graph[abs_path] = resolved_deps

            except Exception as e:
                logger.warning("Failed to parse modified file %s from HEAD: %s", abs_path, e)
                # Keep working tree version as fallback

            current_operation += 1
            if progress_callback and total_operations > 50:
                progress_callback(current_operation, total_operations, f"Parsing modified files: {os.path.basename(abs_path)}")

        logger.info(
            "Reconstructed baseline graph: %d headers, %d added, %d deleted, %d modified",
            len(baseline_headers),
            len(added_files),
            len(deleted_files),
            len(modified_files),
        )

        return baseline_headers, baseline_graph

    except (ValueError, InvalidGitRepositoryError):
        raise
    except GitCommandError as e:
        error_msg = str(e)
        if "unknown revision" in error_msg.lower() or "bad revision" in error_msg.lower():
            raise ValueError(f"Invalid commit reference: {base_ref}") from e
        raise RuntimeError(f"Git command failed: {error_msg}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error reconstructing baseline: {e}") from e
