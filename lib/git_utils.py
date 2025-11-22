#!/usr/bin/env python3
"""Utilities for Git operations."""

import os
import logging
from typing import Any, List, Optional, Tuple
from pathlib import Path

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
    if '..' in relative_path or relative_path.startswith('/'):
        logger.warning(f"Skipping potentially malicious path: {relative_path}")
        return None
    
    abs_path = os.path.abspath(os.path.join(repo_dir, relative_path))
    # Verify the resolved path is within the repo
    try:
        if not abs_path.startswith(os.path.abspath(repo_dir)):
            logger.warning(f"Skipping path outside repository: {relative_path}")
            return None
    except (OSError, ValueError):
        logger.warning(f"Skipping invalid path: {relative_path}")
        return None
    
    if os.path.exists(abs_path):
        return abs_path
    else:
        logger.debug(f"Changed file not found: {abs_path}")
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
            logger.debug(f"Found git repository at: {repo_root}")
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
        import subprocess
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        logger.debug(f"Found git: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False


def get_changed_files_from_commit(repo_dir: str, commit: str = 'HEAD') -> Tuple[List[str], str]:
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
        if '..' in commit:
            # Range format: HEAD~5..HEAD
            parts = commit.split('..')
            if len(parts) != 2:
                raise ValueError(f"Invalid commit range format: {commit}")
            start_commit, end_commit = parts
            
            # Get commit description from end commit
            try:
                end_commit_obj = repo.commit(end_commit)
                summary = end_commit_obj.summary.decode('utf-8') if isinstance(end_commit_obj.summary, bytes) else end_commit_obj.summary
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
            summary = commit_obj.summary.decode('utf-8') if isinstance(commit_obj.summary, bytes) else commit_obj.summary
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
                    if hasattr(item, 'type') and hasattr(item, 'path'):
                        if item.type == 'blob':  # type: ignore[union-attr]
                            path = str(item.path)  # type: ignore[union-attr]
                            abs_path = _validate_and_convert_path(path, repo_dir)
                            if abs_path:
                                changed_files.append(abs_path)
        
        logger.info(f"Found {len(changed_files)} changed files in {commit}")
        return changed_files, commit_desc
        
    except (ValueError, InvalidGitRepositoryError):
        raise
    except GitCommandError as e:
        error_msg = str(e)
        if "unknown revision" in error_msg.lower() or "bad revision" in error_msg.lower():
            raise ValueError(f"Invalid commit reference: {commit}")
        raise RuntimeError(f"Git command failed: {error_msg}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error getting changed files: {e}")


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
        
        logger.info(f"Found {len(changed_files)} staged files")
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
        
        logger.info(f"Found {len(changed_files)} uncommitted changes")
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
        logger.debug(f"Could not get current branch: {e}")
        return None


def get_commit_hash(repo_dir: str, commit: str = 'HEAD') -> Optional[str]:
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
        logger.debug(f"Could not get commit hash for {commit}: {e}")
        return None


def categorize_changed_files(changed_files: List[str], 
                             header_exts: Tuple[str, ...] = ('.h', '.hpp', '.hxx', '.hh'),
                             source_exts: Tuple[str, ...] = ('.cpp', '.c', '.cc', '.cxx')) -> Tuple[List[str], List[str]]:
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
    
    logger.debug(f"Categorized: {len(headers)} headers, {len(sources)} sources")
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
        logger.debug(f"Could not get file history for {filepath}: {e}")
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
            logger.debug(f"{ancestor_ref} is ancestor of {descendant_ref}")
        else:
            logger.debug(f"{ancestor_ref} is NOT ancestor of {descendant_ref}")
        return result
    except (BadName, BadObject) as e:
        raise RuntimeError(f"Invalid commit reference: {e}") from e
    except InvalidGitRepositoryError as e:
        raise RuntimeError(f"Not a git repository: {repo_dir}") from e
    except GitCommandError as e:
        raise RuntimeError(f"Git command failed: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error checking ancestry: {e}") from e


def validate_ancestor_relationship(repo_dir: str, from_ref: str, to_ref: str = 'HEAD') -> None:
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
        
        logger.debug(f"Validated: {from_ref} is an ancestor of {to_ref}")
        
    except ValueError:
        raise
    except InvalidGitRepositoryError:
        raise RuntimeError(f"Not a git repository: {repo_dir}")
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
        
        logger.info(f"Found {len(changed_files)} changes from {base_ref} to working tree")
        description = f"Working tree changes from {base_ref} ({len(changed_files)} files)"
        return changed_files, description
        
    except (ValueError, InvalidGitRepositoryError):
        raise
    except GitCommandError as e:
        error_msg = str(e)
        if "unknown revision" in error_msg.lower() or "bad revision" in error_msg.lower():
            raise ValueError(f"Invalid commit reference: {base_ref}")
        raise RuntimeError(f"Git command failed: {error_msg}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error getting working tree changes: {e}") from e
