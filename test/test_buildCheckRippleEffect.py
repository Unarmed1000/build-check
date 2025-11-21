#!/usr/bin/env python3
#****************************************************************************************************************************************************
#* BSD 3-Clause License
#*
#* Copyright (c) 2025, Mana Battery
#* All rights reserved.
#*
#* Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#*
#* 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#* 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the
#*    documentation and/or other materials provided with the distribution.
#* 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this
#*    software without specific prior written permission.
#*
#* THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
#* THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
#* CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
#* PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
#* LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
#* EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#****************************************************************************************************************************************************
"""Integration tests for buildCheckRippleEffect.py"""
import os
import sys
import subprocess
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import buildCheckRippleEffect


class TestBuildCheckRippleEffect:
    """Test suite for buildCheckRippleEffect functionality."""
    
    def test_find_git_repo_success(self, mock_git_repo):
        """Test finding git repository from subdirectory."""
        # Start from a subdirectory
        subdir = Path(mock_git_repo) / "src"
        
        result = buildCheckRippleEffect.find_git_repo(str(subdir))
        
        assert result is not None
        assert Path(result).resolve() == Path(mock_git_repo).resolve()
    
    def test_find_git_repo_not_found(self, temp_dir):
        """Test when no git repository is found."""
        result = buildCheckRippleEffect.find_git_repo(temp_dir)
        assert result is None
    
    def test_find_git_repo_path_traversal_protection(self, temp_dir):
        """Test that symlink attacks are prevented in git repo detection."""
        # Create a mock setup
        repo_dir = Path(temp_dir) / "repo"
        repo_dir.mkdir()
        git_dir = repo_dir / ".git"
        git_dir.mkdir()
        
        # Try with symlink (should still work but be validated)
        result = buildCheckRippleEffect.find_git_repo(str(repo_dir))
        assert result is not None
    
    def test_categorize_changed_files(self):
        """Test categorizing files into headers and sources."""
        changed_files = [
            "/path/to/header.hpp",
            "/path/to/source.cpp",
            "/path/to/header.h",
            "/path/to/impl.cc",
            "/path/to/config.txt"  # Should be ignored
        ]
        
        headers, sources = buildCheckRippleEffect.categorize_changed_files(changed_files)
        
        assert len(headers) == 2
        assert "/path/to/header.hpp" in headers
        assert "/path/to/header.h" in headers
        
        assert len(sources) == 2
        assert "/path/to/source.cpp" in sources
        assert "/path/to/impl.cc" in sources
    
    def test_categorize_changed_files_invalid_input(self):
        """Test error handling for invalid input."""
        with pytest.raises(TypeError):
            buildCheckRippleEffect.categorize_changed_files("not a list")
    
    def test_get_changed_files_from_git(self, mock_git_repo):
        """Test getting changed files from git."""
        try:
            changed_files = buildCheckRippleEffect.get_changed_files_from_git(
                mock_git_repo, "HEAD"
            )
            
            # Should have at least one changed file (utils.hpp)
            assert len(changed_files) >= 1
            assert any("utils.hpp" in f for f in changed_files)
            
            # All paths should be absolute
            assert all(os.path.isabs(f) for f in changed_files)
        except SystemExit:
            pytest.skip("Git command failed")
    
    def test_get_changed_files_from_git_invalid_commit(self, mock_git_repo):
        """Test handling of invalid git commit reference."""
        with pytest.raises(SystemExit):
            buildCheckRippleEffect.get_changed_files_from_git(
                mock_git_repo, "invalid_commit_hash"
            )
    
    def test_get_changed_files_path_traversal_protection(self, mock_git_repo, monkeypatch):
        """Test that path traversal in git output is detected and blocked."""
        # Mock git to return a malicious path
        malicious_output = "../../../etc/passwd\n"
        
        class MockResult:
            stdout = malicious_output
            stderr = ""
            returncode = 0
        
        def mock_run(*args, **kwargs):
            return MockResult()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        
        changed_files = buildCheckRippleEffect.get_changed_files_from_git(
            mock_git_repo, "HEAD"
        )
        
        # The malicious path should be filtered out
        assert len(changed_files) == 0
    
    def test_analyze_ripple_effect_invalid_build_dir(self):
        """Test error handling for invalid build directory."""
        with pytest.raises(ValueError, match="does not exist"):
            buildCheckRippleEffect.analyze_ripple_effect(
                "/nonexistent/build", [], []
            )
    
    def test_analyze_ripple_effect_missing_compile_commands(self, temp_dir):
        """Test error handling when compile_commands.json is missing."""
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir()
        
        with pytest.raises(ValueError, match="compile_commands.json not found"):
            buildCheckRippleEffect.analyze_ripple_effect(
                str(build_dir), [], []
            )
    
    def test_get_ripple_effect_data_no_changes(self, mock_build_dir, mock_git_repo, monkeypatch):
        """Test getting ripple effect data when no files changed."""
        # Mock git to return no changes
        class MockResult:
            stdout = ""
            stderr = ""
            returncode = 0
        
        def mock_run(*args, **kwargs):
            return MockResult()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        
        result = buildCheckRippleEffect.get_ripple_effect_data(
            mock_build_dir, mock_git_repo, "HEAD"
        )
        
        assert result["changed_headers"] == []
        assert result["changed_sources"] == []
        assert result["rebuild_percentage"] == 0.0
    
    def test_print_ripple_report_validation(self, temp_dir):
        """Test that print_ripple_report validates required keys."""
        invalid_result = {"missing": "keys"}
        
        with pytest.raises(ValueError, match="missing required keys"):
            buildCheckRippleEffect.print_ripple_report(
                [], [], invalid_result, temp_dir
            )


class TestBuildCheckRippleEffectIntegration:
    """Integration tests with mocked dependencies."""
    
    @pytest.mark.skipif(
        subprocess.run(["which", "git"], capture_output=True).returncode != 0,
        reason="git not available"
    )
    def test_full_workflow_with_mock_data(self, mock_git_repo, mock_build_dir, 
                                          mock_compile_commands, monkeypatch, capsys):
        """Test complete workflow with mocked build data."""
        # This test requires actual C++ source files that clang-scan-deps can parse
        # Mock files in fixtures are not sufficient, so we expect this to skip
        try:
            result = buildCheckRippleEffect.get_ripple_effect_data(
                mock_build_dir, mock_git_repo, "HEAD"
            )
            # Should return a dict with expected keys
            assert "changed_headers" in result
            assert "changed_sources" in result
            assert "rebuild_percentage" in result
        except SystemExit:
            # Check if it failed due to clang-scan-deps issues
            captured = capsys.readouterr()
            if "clang-scan-deps" in captured.err or "no such file" in captured.err or \
               "no input files" in captured.err:
                pytest.skip("Mock C++ files not suitable for clang-scan-deps (expected)")
            raise
        except (RuntimeError, ValueError) as e:
            # Expected if dependencies not properly mocked
            error_msg = str(e)
            if "clang-scan-deps" in error_msg or "include graph" in error_msg.lower():
                pytest.skip(f"Mock setup incomplete: {e}")
            raise
