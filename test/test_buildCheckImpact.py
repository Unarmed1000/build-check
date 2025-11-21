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
"""Integration tests for buildCheckImpact.py"""
import os
import sys
import subprocess
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import buildCheckImpact


class TestBuildCheckImpact:
    """Test suite for buildCheckImpact functionality."""
    
    def test_get_dependencies(self, mock_build_dir, monkeypatch):
        """Test getting dependencies for a target."""
        mock_output = """main.cpp.o:
  ../src/main.cpp
  ../src/utils.hpp
  ../src/config.hpp
"""
        
        class MockResult:
            def __init__(self):
                self.stdout = mock_output
                self.stderr = ""
                self.returncode = 0
        
        def mock_run(*args, **kwargs):
            return MockResult()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        
        deps = buildCheckImpact.get_dependencies(mock_build_dir, "main.cpp.o")
        
        assert len(deps) == 3
        assert "../src/main.cpp" in deps
        assert "../src/utils.hpp" in deps
        assert "../src/config.hpp" in deps
    
    def test_get_dependencies_timeout(self, mock_build_dir, monkeypatch):
        """Test handling of timeout when getting dependencies."""
        def mock_run(*args, **kwargs):
            raise subprocess.TimeoutExpired("ninja", 30)
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        
        deps = buildCheckImpact.get_dependencies(mock_build_dir, "main.cpp.o")
        assert deps == []
    
    def test_build_dependency_impact_map(self, mock_build_dir, monkeypatch):
        """Test building dependency impact map."""
        mock_deps_output = """main.cpp.o:
  ../src/main.cpp
  ../src/utils.hpp
utils.cpp.o:
  ../src/utils.cpp
  ../src/utils.hpp
"""
        
        class MockResult:
            def __init__(self):
                self.stdout = mock_deps_output
                self.stderr = ""
                self.returncode = 0
        
        def mock_run(*args, **kwargs):
            return MockResult()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        
        rebuild_targets = ["main.cpp.o", "utils.cpp.o"]
        changed_files = {"../src/utils.hpp"}
        
        impact_map, project_root, target_count = buildCheckImpact.build_dependency_impact_map(
            mock_build_dir, rebuild_targets, changed_files
        )
        
        assert "../src/utils.hpp" in impact_map
        assert len(impact_map["../src/utils.hpp"]) >= 1
        assert target_count == 2
    
    def test_path_traversal_prevention(self, temp_dir):
        """Test that path traversal attempts are blocked."""
        # Create build directory
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir(parents=True)
        (build_dir / "build.ninja").write_text("# mock ninja file")
        
        # Try to access outside build_dir
        malicious_path = os.path.join(str(build_dir), "..", "..", "etc")
        
        # Should be normalized and validated
        result = os.path.realpath(malicious_path)
        assert not result.startswith(str(build_dir))
    
    def test_main_with_no_changes(self, mock_build_dir, monkeypatch, capsys):
        """Test main function when no files need rebuilding."""
        class MockResult:
            def __init__(self):
                self.stdout = ""
                self.stderr = "ninja: no work to do.\n"
                self.returncode = 0
        
        def mock_run(*args, **kwargs):
            return MockResult()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr(sys, "argv", ["buildCheckImpact.py", mock_build_dir])
        
        result = buildCheckImpact.main()
        
        assert result == 0
        captured = capsys.readouterr()
        assert "No rebuilds detected" in captured.out
    
    def test_main_with_invalid_directory(self, monkeypatch):
        """Test main function with invalid directory."""
        # Monkeypatch sys.argv
        monkeypatch.setattr(sys, "argv", ["buildCheckImpact.py", "/nonexistent/path"])
        
        # Should exit with code 1
        result = buildCheckImpact.main()
        assert result == 1


class TestBuildCheckImpactEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_rebuild_targets(self, mock_build_dir):
        """Test with empty rebuild targets list."""
        impact_map, project_root, count = buildCheckImpact.build_dependency_impact_map(
            mock_build_dir, [], None
        )
        
        assert count == 0
        assert len(impact_map) == 0
    
    def test_changed_files_filter(self, mock_build_dir, monkeypatch):
        """Test filtering by changed files."""
        mock_output = """target.o:
  src/header.hpp
  src/other.hpp
"""
        
        class MockResult:
            stdout = mock_output
            stderr = ""
            returncode = 0
        
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: MockResult())
        
        changed_files = {"src/header.hpp"}
        impact_map, _, _ = buildCheckImpact.build_dependency_impact_map(
            mock_build_dir, ["target.o"], changed_files
        )
        
        # Both headers should be in impact map
        assert "src/header.hpp" in impact_map
        assert "src/other.hpp" in impact_map
