#!/usr/bin/env python3
"""Tests for git_utils.validate_ancestor_relationship function."""

import pytest
import os
import tempfile
from pathlib import Path
from typing import Generator
from git import Repo
from lib.git_utils import validate_ancestor_relationship


class TestValidateAncestorRelationship:
    """Test suite for validate_ancestor_relationship function."""
    
    @pytest.fixture
    def temp_git_repo(self) -> Generator[tuple[str, Repo], None, None]:
        """Create a temporary git repository with commit history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = tmpdir
            repo = Repo.init(repo_path)
            
            # Configure git user for commits
            with repo.config_writer() as git_config:
                git_config.set_value('user', 'email', 'test@example.com')
                git_config.set_value('user', 'name', 'Test User')
            
            # Create initial commit
            test_file = Path(repo_path) / "file1.txt"
            test_file.write_text("initial content")
            repo.index.add([str(test_file)])
            repo.index.commit("Initial commit")
            
            # Create second commit
            test_file.write_text("second content")
            repo.index.add([str(test_file)])
            repo.index.commit("Second commit")
            
            # Create third commit
            test_file.write_text("third content")
            repo.index.add([str(test_file)])
            repo.index.commit("Third commit")
            
            yield repo_path, repo
    
    def test_validate_head_is_ancestor_of_itself(self, temp_git_repo: tuple[str, Repo]) -> None:
        """Test that HEAD is considered an ancestor of itself."""
        repo_path, _ = temp_git_repo
        # Should not raise
        validate_ancestor_relationship(repo_path, 'HEAD', 'HEAD')
    
    def test_validate_parent_commit_is_ancestor(self, temp_git_repo: tuple[str, Repo]) -> None:
        """Test that parent commit (HEAD~1) is a valid ancestor of HEAD."""
        repo_path, _ = temp_git_repo
        # Should not raise
        validate_ancestor_relationship(repo_path, 'HEAD~1', 'HEAD')
    
    def test_validate_grandparent_commit_is_ancestor(self, temp_git_repo: tuple[str, Repo]) -> None:
        """Test that grandparent commit (HEAD~2) is a valid ancestor of HEAD."""
        repo_path, _ = temp_git_repo
        # Should not raise
        validate_ancestor_relationship(repo_path, 'HEAD~2', 'HEAD')
    
    def test_validate_tag_as_ancestor(self, temp_git_repo: tuple[str, Repo]) -> None:
        """Test that a tag pointing to an ancestor commit is valid."""
        repo_path, repo = temp_git_repo
        
        # Create a tag at HEAD~1
        repo.create_tag('v1.0.0', 'HEAD~1')
        
        # Should not raise
        validate_ancestor_relationship(repo_path, 'v1.0.0', 'HEAD')
    
    def test_validate_branch_as_ancestor(self, temp_git_repo: tuple[str, Repo]) -> None:
        """Test that a branch pointing to an ancestor commit is valid."""
        repo_path, repo = temp_git_repo
        
        # Create a branch at HEAD~1
        repo.create_head('old-branch', 'HEAD~1')
        
        # Should not raise
        validate_ancestor_relationship(repo_path, 'old-branch', 'HEAD')
    
    def test_validate_divergent_branch_not_ancestor(self, temp_git_repo: tuple[str, Repo]) -> None:
        """Test that a divergent branch is not considered an ancestor."""
        repo_path, repo = temp_git_repo
        
        # Create a branch at HEAD~1
        feature_branch = repo.create_head('feature-branch', 'HEAD~1')
        
        # Switch to feature branch and make a commit
        feature_branch.checkout()
        test_file = Path(repo_path) / "feature.txt"
        test_file.write_text("feature content")
        repo.index.add([str(test_file)])
        repo.index.commit("Feature commit")
        
        # Switch back to main/master
        repo.heads.master.checkout()
        
        # feature-branch HEAD should not be an ancestor of main/master HEAD
        with pytest.raises(ValueError) as exc_info:
            validate_ancestor_relationship(repo_path, 'feature-branch', 'HEAD')
        
        assert "not a linear ancestor" in str(exc_info.value).lower()
        assert "git merge-base" in str(exc_info.value)
    
    def test_validate_future_commit_not_ancestor(self, temp_git_repo: tuple[str, Repo]) -> None:
        """Test that a newer commit cannot be an ancestor of an older commit."""
        repo_path, _ = temp_git_repo
        
        # HEAD cannot be an ancestor of HEAD~1 (child is not ancestor of parent)
        with pytest.raises(ValueError) as exc_info:
            validate_ancestor_relationship(repo_path, 'HEAD', 'HEAD~1')
        
        assert "not a linear ancestor" in str(exc_info.value).lower()
    
    def test_validate_invalid_from_ref(self, temp_git_repo: tuple[str, Repo]) -> None:
        """Test that invalid from_ref raises ValueError."""
        repo_path, _ = temp_git_repo
        
        with pytest.raises(ValueError) as exc_info:
            validate_ancestor_relationship(repo_path, 'nonexistent-ref', 'HEAD')
        
        assert "invalid git reference" in str(exc_info.value).lower()
    
    def test_validate_invalid_to_ref(self, temp_git_repo: tuple[str, Repo]) -> None:
        """Test that invalid to_ref raises ValueError."""
        repo_path, _ = temp_git_repo
        
        with pytest.raises(ValueError) as exc_info:
            validate_ancestor_relationship(repo_path, 'HEAD~1', 'nonexistent-ref')
        
        assert "invalid git reference" in str(exc_info.value).lower()
    
    def test_validate_invalid_repo_path(self) -> None:
        """Test that invalid repository path raises RuntimeError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # tmpdir exists but is not a git repo
            with pytest.raises(RuntimeError) as exc_info:
                validate_ancestor_relationship(tmpdir, 'HEAD', 'HEAD')
            
            assert "not a git repository" in str(exc_info.value).lower()
    
    def test_validate_commit_hash_as_ancestor(self, temp_git_repo: tuple[str, Repo]) -> None:
        """Test that commit hashes work as ancestor references."""
        repo_path, repo = temp_git_repo
        
        # Get commit hash of HEAD~1
        parent_commit = repo.commit('HEAD~1')
        parent_hash = parent_commit.hexsha
        
        # Should not raise
        validate_ancestor_relationship(repo_path, parent_hash, 'HEAD')
    
    def test_validate_short_commit_hash_as_ancestor(self, temp_git_repo: tuple[str, Repo]) -> None:
        """Test that short commit hashes work as ancestor references."""
        repo_path, repo = temp_git_repo
        
        # Get short hash of HEAD~1
        parent_commit = repo.commit('HEAD~1')
        short_hash = parent_commit.hexsha[:7]
        
        # Should not raise
        validate_ancestor_relationship(repo_path, short_hash, 'HEAD')
    
    def test_error_message_includes_helpful_commands(self, temp_git_repo: tuple[str, Repo]) -> None:
        """Test that error messages include helpful git commands."""
        repo_path, repo = temp_git_repo
        
        # Create divergent branch
        feature_branch = repo.create_head('divergent', 'HEAD~1')
        feature_branch.checkout()
        test_file = Path(repo_path) / "divergent.txt"
        test_file.write_text("divergent content")
        repo.index.add([str(test_file)])
        repo.index.commit("Divergent commit")
        repo.heads.master.checkout()
        
        with pytest.raises(ValueError) as exc_info:
            validate_ancestor_relationship(repo_path, 'divergent', 'HEAD')
        
        error_msg = str(exc_info.value)
        assert "git merge-base" in error_msg
        assert "git log --oneline --graph" in error_msg
        assert "diverged" in error_msg.lower()


class TestValidateAncestorRelationshipEdgeCases:
    """Test edge cases for validate_ancestor_relationship."""
    
    def test_validate_with_merge_commits(self) -> None:
        """Test validation with merge commits in history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repo.init(tmpdir)
            
            # Configure git user
            with repo.config_writer() as git_config:
                git_config.set_value('user', 'email', 'test@example.com')
                git_config.set_value('user', 'name', 'Test User')
            
            # Create initial commit on master
            test_file = Path(tmpdir) / "file.txt"
            test_file.write_text("initial")
            repo.index.add([str(test_file)])
            commit1 = repo.index.commit("Initial commit")
            
            # Create feature branch and commit with different file to avoid conflicts
            feature = repo.create_head('feature', commit1)
            feature.checkout()
            feature_file = Path(tmpdir) / "feature.txt"
            feature_file.write_text("feature content")
            repo.index.add([str(feature_file)])
            repo.index.commit("Feature commit")
            
            # Go back to master and make commit
            repo.heads.master.checkout()
            master_file = Path(tmpdir) / "master.txt"
            master_file.write_text("master content")
            repo.index.add([str(master_file)])
            repo.index.commit("Master commit")
            
            # Merge feature into master (no conflicts)
            repo.git.merge('feature', no_ff=True, m="Merge feature")
            
            # commit1 should still be an ancestor of current HEAD
            validate_ancestor_relationship(tmpdir, commit1.hexsha, 'HEAD')
    
    def test_validate_with_detached_head(self) -> None:
        """Test validation when HEAD is detached."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repo.init(tmpdir)
            
            # Configure git user
            with repo.config_writer() as git_config:
                git_config.set_value('user', 'email', 'test@example.com')
                git_config.set_value('user', 'name', 'Test User')
            
            # Create commits
            test_file = Path(tmpdir) / "file.txt"
            test_file.write_text("initial")
            repo.index.add([str(test_file)])
            commit1 = repo.index.commit("Initial commit")
            
            test_file.write_text("second")
            repo.index.add([str(test_file)])
            commit2 = repo.index.commit("Second commit")
            
            # Detach HEAD to previous commit
            repo.git.checkout(commit1.hexsha)
            
            # Should still work with detached HEAD - commit1 is ancestor of itself
            validate_ancestor_relationship(tmpdir, commit1.hexsha, 'HEAD')
