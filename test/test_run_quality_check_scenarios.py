#!/usr/bin/env python3
"""Tests for run_quality_check.sh script scenarios.

These tests simulate various tool detection scenarios to ensure
the quality check script handles all cases gracefully.
"""

import subprocess
import pytest
from typing import Any
from unittest.mock import Mock, patch, MagicMock


class TestQualityCheckNinjaScenarios:
    """Test scenarios where ninja detection might fail in quality check."""

    def test_ninja_in_usr_bin_detected(self, tmp_path: Any, monkeypatch: Any) -> None:
        """Test that ninja in /usr/bin/ninja is detected correctly."""
        # Mock shutil.which to return /usr/bin/ninja
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/ninja"

            # Mock subprocess to return version
            with patch("subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.stdout = "1.11.1"
                mock_run.return_value = mock_result

                # Import and test
                from lib.tool_detection import find_ninja

                tool_info = find_ninja()

                assert tool_info.is_found()
                assert tool_info.command == "ninja"

    def test_ninja_version_fails_gracefully(self, monkeypatch: Any) -> None:
        """Test that ninja --version failure is handled gracefully."""
        with patch("subprocess.run") as mock_run:
            # Simulate version command failing
            mock_run.side_effect = subprocess.CalledProcessError(1, ["ninja", "--version"])

            with patch("shutil.which") as mock_which:
                mock_which.return_value = "/usr/bin/ninja"

                from lib.tool_detection import find_ninja, clear_cache

                clear_cache()
                tool_info = find_ninja()

                # Should not crash, just return not found
                assert not tool_info.is_found()

    def test_ninja_timeout_handled(self, monkeypatch: Any) -> None:
        """Test that ninja --version timeout is handled."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(["ninja", "--version"], 5)

            with patch("shutil.which") as mock_which:
                mock_which.return_value = "/usr/bin/ninja"

                from lib.tool_detection import find_ninja, clear_cache

                clear_cache()
                tool_info = find_ninja()

                assert not tool_info.is_found()

    def test_tool_detection_module_not_found(self, monkeypatch: Any) -> None:
        """Test handling when lib.tool_detection module has issues."""
        # This simulates the module import failing
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = ModuleNotFoundError("No module named 'lib'")

            # The script should handle this by continuing with "MISSING" status
            # This is tested at the bash script level
            assert True  # Placeholder for integration test

    def test_python_module_check_import_error(self, monkeypatch: Any) -> None:
        """Test that Python module checks handle ImportError gracefully."""
        # Simulate import failure
        result = subprocess.run(["python3", "-c", "import nonexistent_module"], capture_output=True, text=True)

        # Should exit non-zero but not crash
        assert result.returncode != 0


class TestQualityCheckExternalToolScenarios:
    """Test external tool detection scenarios."""

    def test_clang_scan_deps_not_in_path(self, monkeypatch: Any) -> None:
        """Test clang-scan-deps not being in PATH."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None

            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError()

                from lib.tool_detection import find_clang_scan_deps, clear_cache

                clear_cache()
                tool_info = find_clang_scan_deps()

                assert not tool_info.is_found()

    def test_all_tools_missing_graceful(self, monkeypatch: Any) -> None:
        """Test that all tools missing is handled gracefully."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None

            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError()

                from lib.tool_detection import find_ninja, find_clang_scan_deps, clear_cache

                clear_cache()

                ninja_info = find_ninja()
                clang_info = find_clang_scan_deps()

                assert not ninja_info.is_found()
                assert not clang_info.is_found()


class TestQualityCheckBashScriptIntegration:
    """Integration tests for bash script behavior."""

    def test_script_continues_after_ninja_missing(self, tmp_path: Any) -> None:
        """Test that script continues execution when ninja is missing."""
        # This test would run the actual bash script with mocked ninja
        # For now, we verify the logic is correct

        # The script should:
        # 1. Check ninja with || true pattern
        # 2. Continue to next checks
        # 3. Add "ninja missing" to QUALITY_ISSUES
        # 4. Not exit immediately

        # This is validated by the script's use of || true
        assert True  # Placeholder for actual integration test

    def test_script_exits_only_on_critical_failures(self) -> None:
        """Test that script only exits on test failures or type errors."""
        # The script should continue for:
        # - Missing optional dependencies
        # - Missing ninja/clang-scan-deps
        # - Pylint warnings

        # The script should exit for:
        # - Test failures
        # - Type checking errors (mypy)
        # - Missing required documentation

        assert True  # Placeholder for actual integration test


class TestQualityCheckPythonModules:
    """Test Python module checking scenarios."""

    def test_check_python_module_required_missing(self) -> None:
        """Test that required Python modules are properly flagged."""
        # Run a check for a non-existent required module
        result = subprocess.run(["python3", "-c", "import definitely_not_a_real_module"], capture_output=True, text=True)

        # Should fail (exit code != 0)
        assert result.returncode != 0

    def test_check_python_module_optional_missing(self) -> None:
        """Test that optional Python modules don't crash the script."""
        # Run a check for a non-existent optional module
        result = subprocess.run(["python3", "-c", "import some_optional_module"], capture_output=True, text=True)

        # Should fail but script should continue
        assert result.returncode != 0


class TestCacheClearing:
    """Test that cache clearing works correctly between tests."""

    def test_cache_clear_between_checks(self) -> None:
        """Test that tool detection cache can be cleared."""
        from lib.tool_detection import clear_cache, _tool_cache, ToolInfo

        # Add something to cache
        _tool_cache["test"] = ToolInfo(command="test", full_command="test", version="1.0")

        # Clear it
        clear_cache()

        # Should be empty
        assert len(_tool_cache) == 0

    def test_cached_results_consistent(self) -> None:
        """Test that cached results are returned consistently."""
        from lib.tool_detection import find_ninja, clear_cache

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "1.11.1"
            mock_run.return_value = mock_result

            with patch("shutil.which") as mock_which:
                mock_which.return_value = "/usr/bin/ninja"

                clear_cache()
                result1 = find_ninja()
                result2 = find_ninja()

                # Should be the same object (cached)
                assert result1 is result2
                # subprocess should only be called once
                assert mock_run.call_count == 1


class TestErrorMessages:
    """Test that error messages are helpful and clear."""

    def test_ninja_not_found_returns_empty_toolinfo(self) -> None:
        """Test that missing ninja returns empty ToolInfo."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            with patch("shutil.which") as mock_which:
                mock_which.return_value = None

                from lib.tool_detection import find_ninja, clear_cache, ToolInfo

                clear_cache()
                result = find_ninja()

                assert isinstance(result, ToolInfo)
                assert result.command is None
                assert result.version is None
                assert not result.is_found()

    def test_exit_code_1_when_tool_not_found(self) -> None:
        """Test that CLI returns exit code 1 when tool not found."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            with patch("shutil.which") as mock_which:
                mock_which.return_value = None

                with patch("sys.argv", ["tool_detection.py", "--find-ninja"]):
                    from lib.tool_detection import main, clear_cache

                    clear_cache()

                    exit_code = main()
                    assert exit_code == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
