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
"""Integration tests for buildCheckSummary.py"""
import os
import sys
import json
import subprocess
from pathlib import Path
import pytest
from typing import Any, Dict, List, Tuple, Generator

# Import the module to test
sys.path.insert(0, str(Path(__file__).parent.parent))
import buildCheckSummary


class TestBuildCheckSummary:
    """Test suite for buildCheckSummary main script functionality."""

    def test_format_json_output(self) -> None:
        """Test JSON output formatting."""
        rebuild_entries = [("main.cpp.o", "output missing (initial build)"), ("utils.cpp.o", "input source changed")]
        reasons = {"output missing (initial build)": 1, "input source changed": 1}
        root_causes = {"src/utils.hpp": 1}

        json_output = buildCheckSummary.format_json_output(rebuild_entries, reasons, root_causes)

        data = json.loads(json_output)
        assert data["summary"]["total_files"] == 2
        assert len(data["files"]) == 2
        assert data["reasons"]["input source changed"] == 1
        assert data["root_causes"]["src/utils.hpp"] == 1


class TestBuildCheckSummaryEndToEnd:
    """End-to-end tests for buildCheckSummary."""

    @pytest.mark.skipif(subprocess.run(["which", "ninja"], capture_output=True).returncode != 0, reason="ninja not available")
    def test_main_with_valid_build_dir(self, mock_build_dir: Any, monkeypatch: Any, capsys: Any) -> None:
        """Test main function with a valid build directory."""
        # Mock subprocess to return controlled ninja output
        mock_stderr = """ninja explain: output main.cpp.o doesn't exist
ninja: no work to do.
"""

        class MockResult:
            def __init__(self) -> None:
                self.stdout = ""
                self.stderr = mock_stderr
                self.returncode = 0

        def mock_run(*args: Any, **kwargs: Any) -> Any:
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
