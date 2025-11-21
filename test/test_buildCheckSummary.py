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
"""Integration tests for buildCheckSummary.py"""
import os
import sys
import json
import subprocess
from pathlib import Path
import pytest

# Import the module to test
sys.path.insert(0, str(Path(__file__).parent.parent))
import buildCheckSummary


class TestBuildCheckSummary:
    """Test suite for buildCheckSummary functionality."""
    
    def test_normalize_reason_missing_output(self):
        """Test normalizing 'output missing' reason."""
        msg = "output main.cpp.o doesn't exist"
        result = buildCheckSummary.normalize_reason(msg)
        assert result == "output missing (initial build)"
    
    def test_normalize_reason_input_changed(self):
        """Test normalizing 'input changed' reason."""
        msg = "output utils.cpp.o older than most recent input src/utils.hpp"
        result = buildCheckSummary.normalize_reason(msg)
        assert result == "input source changed"
    
    def test_normalize_reason_command_line_changed(self):
        """Test normalizing 'command line changed' reason."""
        msg = "command line changed for utils.cpp.o"
        result = buildCheckSummary.normalize_reason(msg)
        assert result == "command line changed (compile flags/options)"
    
    def test_normalize_reason_build_ninja_changed(self):
        """Test normalizing 'build.ninja changed' reason."""
        msg = "build.ninja changed"
        result = buildCheckSummary.normalize_reason(msg)
        assert result == "build.ninja changed (cmake reconfigure)"
    
    def test_normalize_reason_unknown(self):
        """Test normalizing unknown reason."""
        msg = "some weird unknown reason"
        result = buildCheckSummary.normalize_reason(msg)
        assert msg in result
    
    def test_extract_rebuild_info_with_mock_build(self, mock_build_dir, monkeypatch):
        """Test extracting rebuild info from a mock build directory."""
        # Mock subprocess.run to return controlled output
        mock_stderr = """ninja explain: output main.cpp.o doesn't exist
ninja explain: output utils.cpp.o older than most recent input src/utils.hpp
"""
        
        class MockResult:
            def __init__(self):
                self.stdout = ""
                self.stderr = mock_stderr
                self.returncode = 0
        
        def mock_run(*args, **kwargs):
            return MockResult()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        
        # Test extraction
        rebuild_entries, reasons, root_causes = buildCheckSummary.extract_rebuild_info(
            mock_build_dir, verbose=False
        )
        
        assert len(rebuild_entries) == 2
        assert reasons["output missing (initial build)"] == 1
        assert reasons["input source changed"] == 1
        assert "src/utils.hpp" in root_causes
    
    def test_format_json_output(self):
        """Test JSON output formatting."""
        rebuild_entries = [
            ("main.cpp.o", "output missing (initial build)"),
            ("utils.cpp.o", "input source changed")
        ]
        reasons = {
            "output missing (initial build)": 1,
            "input source changed": 1
        }
        root_causes = {"src/utils.hpp": 1}
        
        json_output = buildCheckSummary.format_json_output(
            rebuild_entries, reasons, root_causes
        )
        
        data = json.loads(json_output)
        assert data["summary"]["total_files"] == 2
        assert len(data["files"]) == 2
        assert data["reasons"]["input source changed"] == 1
        assert data["root_causes"]["src/utils.hpp"] == 1
    
    def test_invalid_build_directory(self):
        """Test handling of invalid build directory."""
        with pytest.raises(SystemExit) as exc_info:
            buildCheckSummary.extract_rebuild_info("/nonexistent/directory")
        assert exc_info.value.code == buildCheckSummary.EXIT_INVALID_ARGS
    
    def test_ninja_not_found(self, mock_build_dir, monkeypatch):
        """Test handling when ninja is not found."""
        def mock_run(*args, **kwargs):
            raise FileNotFoundError("ninja not found")
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        
        with pytest.raises(SystemExit) as exc_info:
            buildCheckSummary.extract_rebuild_info(mock_build_dir)
        assert exc_info.value.code == buildCheckSummary.EXIT_NINJA_FAILED
    
    def test_path_traversal_prevention(self, temp_dir):
        """Test that path traversal attempts are blocked."""
        # Create a malicious build directory path
        malicious_path = os.path.join(temp_dir, "..", "..", "etc", "passwd")
        
        # This should fail validation before any file operations
        with pytest.raises(SystemExit):
            buildCheckSummary.extract_rebuild_info(malicious_path)


class TestBuildCheckSummaryEndToEnd:
    """End-to-end tests for buildCheckSummary."""
    
    @pytest.mark.skipif(
        subprocess.run(["which", "ninja"], capture_output=True).returncode != 0,
        reason="ninja not available"
    )
    def test_main_with_valid_build_dir(self, mock_build_dir, monkeypatch, capsys):
        """Test main function with a valid build directory."""
        # Mock subprocess to return controlled ninja output
        mock_stderr = """ninja explain: output main.cpp.o doesn't exist
ninja: no work to do.
"""
        
        class MockResult:
            def __init__(self):
                self.stdout = ""
                self.stderr = mock_stderr
                self.returncode = 0
        
        def mock_run(*args, **kwargs):
            if args[0][0] == "ninja" and "--version" in args[0]:
                return MockResult()
            return MockResult()
        
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr(sys, "argv", ["buildCheckSummary.py", mock_build_dir])
        
        # Run main - should exit with code 0 (success)
        try:
            buildCheckSummary.main()
        except SystemExit as e:
            # Expected for successful completion
            assert e.code == buildCheckSummary.EXIT_SUCCESS
