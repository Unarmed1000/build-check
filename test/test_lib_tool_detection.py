#!/usr/bin/env python3
"""Tests for lib/tool_detection.py"""

import pytest
import json
import subprocess
from typing import Any, List
from unittest.mock import Mock, patch, MagicMock

from lib.tool_detection import (
    ToolInfo,
    clear_cache,
    find_clang_scan_deps,
    find_ninja,
    find_mypy,
    find_pylint,
    find_pytest,
    find_pytest_cov,
    check_all_tools,
    CLANG_SCAN_DEPS_COMMANDS,
    NINJA_COMMANDS,
    MYPY_COMMANDS,
    PYLINT_COMMANDS,
    PYTEST_COMMANDS,
    PYTEST_COV_COMMANDS,
    _tool_cache,
)


class TestToolInfo:
    """Tests for ToolInfo dataclass."""

    def test_is_found_with_command(self) -> None:
        """Test is_found returns True when command is set."""
        tool_info = ToolInfo(command="ninja", full_command="ninja", version="1.11.1")
        assert tool_info.is_found() is True

    def test_is_found_without_command(self) -> None:
        """Test is_found returns False when command is None."""
        tool_info = ToolInfo(command=None, full_command=None, version=None)
        assert tool_info.is_found() is False

    def test_tool_info_attributes(self) -> None:
        """Test ToolInfo stores all attributes correctly."""
        tool_info = ToolInfo(command="python3", full_command="python3 -m mypy", version="mypy 1.8.0")
        assert tool_info.command == "python3"
        assert tool_info.full_command == "python3 -m mypy"
        assert tool_info.version == "mypy 1.8.0"

    def test_tool_info_with_error_message(self) -> None:
        """Test ToolInfo stores error message when tool not found."""
        tool_info = ToolInfo(command=None, full_command=None, version=None, error_message="not in PATH")
        assert not tool_info.is_found()
        assert tool_info.error_message == "not in PATH"

    def test_tool_info_with_detailed_error_message(self) -> None:
        """Test ToolInfo stores detailed error message with tried commands."""
        error_msg = "not in PATH (tried: ninja, ninja-build)"
        tool_info = ToolInfo(command=None, full_command=None, version=None, error_message=error_msg)
        assert not tool_info.is_found()
        assert tool_info.error_message is not None
        assert "tried:" in tool_info.error_message
        assert "ninja" in tool_info.error_message


class TestConstants:
    """Tests for exported command constants."""

    def test_clang_scan_deps_commands(self) -> None:
        """Test CLANG_SCAN_DEPS_COMMANDS is correct."""
        assert CLANG_SCAN_DEPS_COMMANDS == ["clang-scan-deps-20", "clang-scan-deps-19", "clang-scan-deps-18", "clang-scan-deps"]

    def test_ninja_commands(self) -> None:
        """Test NINJA_COMMANDS is correct."""
        assert NINJA_COMMANDS == ["ninja", "ninja-build"]

    def test_mypy_commands(self) -> None:
        """Test MYPY_COMMANDS includes python3 -m variant first."""
        assert MYPY_COMMANDS == [["python3", "-m", "mypy"], ["mypy"]]

    def test_pylint_commands(self) -> None:
        """Test PYLINT_COMMANDS includes python3 -m variant first."""
        assert PYLINT_COMMANDS == [["python3", "-m", "pylint"], ["pylint"]]

    def test_pytest_commands(self) -> None:
        """Test PYTEST_COMMANDS includes python3 -m variant first."""
        assert PYTEST_COMMANDS == [["python3", "-m", "pytest"], ["pytest"]]


class TestCaching:
    """Tests for session caching functionality."""

    def test_clear_cache(self) -> None:
        """Test clear_cache empties the cache."""
        # Populate cache
        _tool_cache["test_key"] = ToolInfo(command="test", full_command="test", version="1.0")
        assert len(_tool_cache) > 0

        # Clear cache
        clear_cache()
        assert len(_tool_cache) == 0

    def test_find_uses_cache(self, monkeypatch: Any) -> None:
        """Test that find functions use cache on second call."""
        # Mock subprocess to return success
        mock_result = MagicMock()
        mock_result.stdout = "clang-scan-deps version 19.1.3"
        mock_run = Mock(return_value=mock_result)
        monkeypatch.setattr("subprocess.run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: f"/usr/bin/{x}")

        # First call should invoke subprocess
        clear_cache()
        tool_info1 = find_clang_scan_deps()
        assert mock_run.call_count == 1
        assert tool_info1.is_found()

        # Second call should use cache
        tool_info2 = find_clang_scan_deps()
        assert mock_run.call_count == 1  # No additional call
        assert tool_info2 is tool_info1  # Same object

    def test_cache_key_by_function(self, monkeypatch: Any) -> None:
        """Test cache is keyed by function name."""
        clear_cache()

        # Mock different tools
        def mock_run(cmd: List[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            if "ninja" in cmd[0]:
                result.stdout = "1.11.1"
            else:
                result.stdout = "clang-scan-deps version 19.1.3"
            return result

        monkeypatch.setattr("subprocess.run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: f"/usr/bin/{x}")

        # Call different functions
        clang_info = find_clang_scan_deps()
        ninja_info = find_ninja()

        # Both should be cached separately
        assert "find_clang_scan_deps" in _tool_cache
        assert "find_ninja" in _tool_cache
        assert clang_info.command != ninja_info.command


class TestFindClangScanDeps:
    """Tests for find_clang_scan_deps function."""

    def test_find_clang_scan_deps_found_first(self, monkeypatch: Any) -> None:
        """Test finding clang-scan-deps-19 when version 20 is not available."""
        clear_cache()

        def mock_run(cmd: List[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            if "20" in cmd[0]:
                raise FileNotFoundError()
            result.stdout = "clang-scan-deps version 19.1.3\nLLVM version 19.1.3"
            return result

        monkeypatch.setattr("subprocess.run", mock_run)

        tool_info = find_clang_scan_deps()
        assert tool_info.is_found()
        assert tool_info.command == "clang-scan-deps-19"
        assert tool_info.version == "clang-scan-deps version 19.1.3"

    def test_find_clang_scan_deps_fallback(self, monkeypatch: Any) -> None:
        """Test falling back to clang-scan-deps-18 when 20 and 19 not found."""
        clear_cache()

        def mock_run(cmd: List[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            if "20" in cmd[0] or "19" in cmd[0]:
                raise FileNotFoundError()
            result.stdout = "clang-scan-deps version 18.1.0"
            return result

        monkeypatch.setattr("subprocess.run", mock_run)

        tool_info = find_clang_scan_deps()
        assert tool_info.is_found()
        assert tool_info.command == "clang-scan-deps-18"

    def test_find_clang_scan_deps_not_found(self, monkeypatch: Any) -> None:
        """Test when clang-scan-deps is not available."""
        clear_cache()
        monkeypatch.setattr("subprocess.run", Mock(side_effect=FileNotFoundError()))
        monkeypatch.setattr("shutil.which", lambda x: None)

        tool_info = find_clang_scan_deps()
        assert not tool_info.is_found()
        assert tool_info.command is None
        assert tool_info.version is None


class TestFindNinja:
    """Tests for find_ninja function."""

    def test_find_ninja_found(self, monkeypatch: Any) -> None:
        """Test finding ninja."""
        clear_cache()
        mock_result = MagicMock()
        mock_result.stdout = "1.11.1"
        monkeypatch.setattr("subprocess.run", Mock(return_value=mock_result))
        monkeypatch.setattr("shutil.which", lambda x: f"/usr/bin/{x}")

        tool_info = find_ninja()
        assert tool_info.is_found()
        assert tool_info.command == "ninja"
        assert tool_info.version == "1.11.1"

    def test_find_ninja_build_fallback(self, monkeypatch: Any) -> None:
        """Test falling back to ninja-build."""
        clear_cache()

        def mock_run(cmd: List[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            if cmd[0] == "ninja":
                raise FileNotFoundError()
            result.stdout = "1.10.2"
            return result

        monkeypatch.setattr("subprocess.run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: f"/usr/bin/{x}" if x == "ninja-build" else None)

        tool_info = find_ninja()
        assert tool_info.is_found()
        assert tool_info.command == "ninja-build"

    def test_find_ninja_not_found(self, monkeypatch: Any) -> None:
        """Test when ninja is not available at all."""
        clear_cache()
        monkeypatch.setattr("subprocess.run", Mock(side_effect=FileNotFoundError()))
        monkeypatch.setattr("shutil.which", lambda x: None)

        tool_info = find_ninja()
        assert not tool_info.is_found()
        assert tool_info.command is None
        assert tool_info.error_message is not None
        assert "not in PATH" in tool_info.error_message
        assert "ninja" in tool_info.error_message
        assert "ninja-build" in tool_info.error_message

    def test_find_ninja_usr_bin_path(self, monkeypatch: Any) -> None:
        """Test finding ninja specifically in /usr/bin/ninja."""
        clear_cache()
        mock_result = MagicMock()
        mock_result.stdout = "1.11.1"
        monkeypatch.setattr("subprocess.run", Mock(return_value=mock_result))
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/ninja" if x == "ninja" else None)

        tool_info = find_ninja()
        assert tool_info.is_found()
        assert tool_info.command == "ninja"
        assert tool_info.version == "1.11.1"

    def test_find_ninja_version_fails_but_which_succeeds(self, monkeypatch: Any) -> None:
        """Test when ninja --version fails but which finds it."""
        clear_cache()
        # Version command fails
        monkeypatch.setattr("subprocess.run", Mock(side_effect=subprocess.CalledProcessError(1, ["ninja", "--version"])))
        # But which finds it
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/ninja" if x == "ninja" else None)

        tool_info = find_ninja()
        # Should not be found since --version failed
        assert not tool_info.is_found()

    def test_find_ninja_timeout(self, monkeypatch: Any) -> None:
        """Test when ninja --version times out."""
        clear_cache()
        monkeypatch.setattr("subprocess.run", Mock(side_effect=subprocess.TimeoutExpired(["ninja", "--version"], 5)))
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/ninja" if x == "ninja" else None)

        tool_info = find_ninja()
        assert not tool_info.is_found()

    def test_find_ninja_which_returns_none_despite_success(self, monkeypatch: Any) -> None:
        """Test that ninja is found when subprocess.run succeeds, regardless of shutil.which."""
        clear_cache()
        mock_result = MagicMock()
        mock_result.stdout = "1.11.1"
        monkeypatch.setattr("subprocess.run", Mock(return_value=mock_result))
        # which returns None (ninja not in PATH according to shutil) - but we no longer check this
        monkeypatch.setattr("shutil.which", lambda x: None)

        tool_info = find_ninja()
        # Should be found since subprocess.run succeeded
        assert tool_info.is_found()
        assert tool_info.command == "ninja"


class TestFindMypy:
    """Tests for find_mypy function."""

    def test_find_mypy_python_module_first(self, monkeypatch: Any) -> None:
        """Test preferring python3 -m mypy over direct mypy."""
        clear_cache()
        mock_result = MagicMock()
        mock_result.stdout = "mypy 1.8.0 (compiled: yes)"
        monkeypatch.setattr("subprocess.run", Mock(return_value=mock_result))
        monkeypatch.setattr("shutil.which", lambda x: f"/usr/bin/{x}")

        tool_info = find_mypy()
        assert tool_info.is_found()
        assert tool_info.command == "python3"
        assert tool_info.full_command == "python3 -m mypy"
        assert tool_info.version is not None
        assert "mypy 1.8.0" in tool_info.version

    def test_find_mypy_fallback_to_direct(self, monkeypatch: Any) -> None:
        """Test falling back to direct mypy command."""
        clear_cache()

        def mock_run(cmd: List[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            if len(cmd) > 1 and cmd[1] == "-m":
                raise FileNotFoundError()
            result.stdout = "mypy 1.7.0"
            return result

        monkeypatch.setattr("subprocess.run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: f"/usr/bin/{x}" if x == "mypy" else None)

        tool_info = find_mypy()
        assert tool_info.is_found()
        assert tool_info.command == "mypy"
        assert tool_info.full_command == "mypy"


class TestFindPylint:
    """Tests for find_pylint function."""

    def test_find_pylint_python_module(self, monkeypatch: Any) -> None:
        """Test finding pylint via python3 -m."""
        clear_cache()
        mock_result = MagicMock()
        mock_result.stdout = "pylint 3.0.0"
        monkeypatch.setattr("subprocess.run", Mock(return_value=mock_result))
        monkeypatch.setattr("shutil.which", lambda x: f"/usr/bin/{x}")

        tool_info = find_pylint()
        assert tool_info.is_found()
        assert tool_info.command == "python3"
        assert tool_info.full_command == "python3 -m pylint"


class TestFindPytest:
    """Tests for find_pytest function."""

    def test_find_pytest(self, monkeypatch: Any) -> None:
        """Test finding pytest."""
        clear_cache()
        mock_result = MagicMock()
        mock_result.stdout = "pytest 7.4.3"
        monkeypatch.setattr("subprocess.run", Mock(return_value=mock_result))
        monkeypatch.setattr("shutil.which", lambda x: f"/usr/bin/{x}")

        tool_info = find_pytest()
        assert tool_info.is_found()


class TestCheckAllJSON:
    """Tests for check_all_tools function."""

    def test_check_all_tools_all_found(self, monkeypatch: Any) -> None:
        """Test check_all_tools when all tools are found."""
        clear_cache()

        # Mock all tools as found
        def mock_find_tool(cache_key: str, cmd: str, ver: str) -> ToolInfo:
            return ToolInfo(command=cmd, full_command=cmd, version=ver)

        monkeypatch.setattr("lib.tool_detection.find_clang_scan_deps", lambda: mock_find_tool("", "clang-scan-deps-19", "19.1.3"))
        monkeypatch.setattr("lib.tool_detection.find_ninja", lambda: mock_find_tool("", "ninja", "1.11.1"))
        monkeypatch.setattr("lib.tool_detection.find_mypy", lambda: mock_find_tool("", "python3", "mypy 1.8.0"))
        monkeypatch.setattr("lib.tool_detection.find_pylint", lambda: mock_find_tool("", "python3", "pylint 3.0.0"))
        monkeypatch.setattr("lib.tool_detection.find_pytest", lambda: mock_find_tool("", "python3", "pytest 7.4.3"))
        monkeypatch.setattr("lib.tool_detection.find_pytest_cov", lambda: mock_find_tool("", "python3", "pytest-cov 4.0.0"))

        tools = check_all_tools()
        assert "ninja" in tools
        assert "clang-scan-deps" in tools
        assert "mypy" in tools
        assert tools["ninja"]["command"] == "ninja"
        assert tools["ninja"]["version"] == "1.11.1"

    def test_check_all_tools_missing_tools_omitted(self, monkeypatch: Any) -> None:
        """Test that missing tools are omitted from results."""
        clear_cache()

        # Mock ninja found, clang-scan-deps not found
        monkeypatch.setattr("lib.tool_detection.find_clang_scan_deps", lambda: ToolInfo(None, None, None))
        monkeypatch.setattr("lib.tool_detection.find_ninja", lambda: ToolInfo("ninja", "ninja", "1.11.1"))
        monkeypatch.setattr("lib.tool_detection.find_mypy", lambda: ToolInfo(None, None, None))
        monkeypatch.setattr("lib.tool_detection.find_pylint", lambda: ToolInfo(None, None, None))
        monkeypatch.setattr("lib.tool_detection.find_pytest", lambda: ToolInfo(None, None, None))
        monkeypatch.setattr("lib.tool_detection.find_pytest_cov", lambda: ToolInfo(None, None, None))

        tools = check_all_tools()
        assert "ninja" in tools
        assert "clang-scan-deps" not in tools
        assert "mypy" not in tools


class TestCLI:
    """Tests for CLI interface."""

    def test_cli_find_tool_found(self, monkeypatch: Any, capsys: Any) -> None:
        """Test CLI returns command when tool is found."""
        clear_cache()
        mock_result = MagicMock()
        mock_result.stdout = "1.11.1"
        monkeypatch.setattr("subprocess.run", Mock(return_value=mock_result))
        monkeypatch.setattr("shutil.which", lambda x: f"/usr/bin/{x}")
        monkeypatch.setattr("sys.argv", ["tool_detection.py", "--find-ninja"])

        from lib.tool_detection import main

        exit_code = main()
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "ninja" in captured.out

    def test_cli_find_tool_not_found(self, monkeypatch: Any, capsys: Any) -> None:
        """Test CLI returns exit 1 when tool not found."""
        clear_cache()
        monkeypatch.setattr("subprocess.run", Mock(side_effect=FileNotFoundError()))
        monkeypatch.setattr("shutil.which", lambda x: None)
        monkeypatch.setattr("sys.argv", ["tool_detection.py", "--find-ninja"])

        from lib.tool_detection import main

        exit_code = main()
        captured = capsys.readouterr()
        assert exit_code == 1
        assert captured.out == ""

    def test_cli_check_all_json(self, monkeypatch: Any, capsys: Any) -> None:
        """Test CLI --check-all returns valid JSON."""
        clear_cache()
        monkeypatch.setattr("lib.tool_detection.check_all_tools", lambda: {"ninja": {"command": "ninja", "version": "1.11.1"}})
        monkeypatch.setattr("sys.argv", ["tool_detection.py", "--check-all"])

        from lib.tool_detection import main

        exit_code = main()
        captured = capsys.readouterr()
        assert exit_code == 0

        # Parse JSON
        data = json.loads(captured.out)
        assert "tools" in data
        assert "ninja" in data["tools"]
        assert data["tools"]["ninja"]["command"] == "ninja"


class TestVerboseLogging:
    """Tests for verbose logging functionality."""

    def test_verbose_logs_attempts(self, monkeypatch: Any, caplog: Any) -> None:
        """Test that verbose mode logs all attempts."""
        import logging

        clear_cache()

        # Mock first command to fail, second to succeed
        call_count = [0]

        def mock_run(cmd: List[str], **kwargs: Any) -> MagicMock:
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                raise FileNotFoundError()
            result.stdout = "1.11.1"
            return result

        monkeypatch.setattr("subprocess.run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: f"/usr/bin/{x}" if "build" in x else None)

        # Enable DEBUG logging
        with caplog.at_level(logging.DEBUG, logger="lib.tool_detection"):
            tool_info = find_ninja()

        # Check that both attempts were logged
        assert tool_info.is_found()
        assert tool_info.command == "ninja-build"
        # Verify logging happened (both attempts should be in caplog)
        log_text = " ".join(record.message for record in caplog.records)
        assert "ninja" in log_text.lower()


class TestCommandValidation:
    """Tests for command validation using shutil.which."""

    def test_command_validated_with_which(self, monkeypatch: Any) -> None:
        """Test that commands are validated via subprocess.run, not shutil.which."""
        clear_cache()
        mock_result = MagicMock()
        mock_result.stdout = "1.11.1"
        monkeypatch.setattr("subprocess.run", Mock(return_value=mock_result))

        # Mock which to return None - should not affect detection anymore
        which_mock = Mock(return_value=None)
        monkeypatch.setattr("shutil.which", which_mock)

        tool_info = find_ninja()
        # Tool should be found since subprocess.run succeeded
        assert tool_info.is_found()
        assert tool_info.command == "ninja"

    def test_multiword_command_validation(self, monkeypatch: Any) -> None:
        """Test validation of multi-word commands (python3 -m mypy)."""
        clear_cache()
        mock_result = MagicMock()
        mock_result.stdout = "mypy 1.8.0"
        monkeypatch.setattr("subprocess.run", Mock(return_value=mock_result))

        # Only validate first part (python3)
        which_mock = Mock(return_value="/usr/bin/python3")
        monkeypatch.setattr("shutil.which", which_mock)

        tool_info = find_mypy()
        assert tool_info.is_found()
        which_mock.assert_called_with("python3")
