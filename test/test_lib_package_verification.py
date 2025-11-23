#!/usr/bin/env python3
"""Tests for lib/package_verification.py."""

import sys
import pytest
from unittest.mock import patch, MagicMock
from typing import Any
from importlib.metadata import PackageNotFoundError


@pytest.mark.unit
class TestCheckPackageVersion:
    """Test check_package_version function."""

    @pytest.mark.unit
    def test_check_installed_meets_version(self) -> None:
        """Test checking an installed package that meets version requirement."""
        from lib.package_verification import check_package_version

        # networkx should be installed
        is_installed, meets_version, installed_ver = check_package_version("networkx", "2.0.0", raise_on_error=False)

        assert is_installed is True
        assert meets_version is True
        assert installed_ver is not None
        assert len(installed_ver) > 0

    @pytest.mark.unit
    def test_check_installed_below_version(self) -> None:
        """Test checking an installed package below required version."""
        from lib.package_verification import check_package_version

        # networkx should be installed but we'll require impossibly high version
        is_installed, meets_version, installed_ver = check_package_version("networkx", "999.0.0", raise_on_error=False)

        assert is_installed is True
        assert meets_version is False
        assert installed_ver is not None

    @pytest.mark.unit
    def test_check_not_installed(self) -> None:
        """Test checking a package that is not installed."""
        from lib.package_verification import check_package_version

        # Use a package name that doesn't exist
        is_installed, meets_version, installed_ver = check_package_version("nonexistent_package_xyz123", "1.0.0", raise_on_error=False)

        assert is_installed is False
        assert meets_version is False
        assert installed_ver is None

    @pytest.mark.unit
    def test_check_raise_on_missing_package(self) -> None:
        """Test that ImportError is raised when package is missing and raise_on_error=True."""
        from lib.package_verification import check_package_version

        with pytest.raises(ImportError, match="is not installed"):
            check_package_version("nonexistent_package_xyz123", "1.0.0", raise_on_error=True)

    @pytest.mark.unit
    def test_check_raise_on_old_version(self) -> None:
        """Test that ImportError is raised when version is too old and raise_on_error=True."""
        from lib.package_verification import check_package_version

        with pytest.raises(ImportError, match="is too old"):
            check_package_version("networkx", "999.0.0", raise_on_error=True)

    @pytest.mark.unit
    def test_check_use_registry_version(self) -> None:
        """Test using PACKAGE_REQUIREMENTS registry when min_version is None."""
        from lib.package_verification import check_package_version

        # Should use version from PACKAGE_REQUIREMENTS
        is_installed, meets_version, installed_ver = check_package_version("networkx", min_version=None, raise_on_error=False)

        assert is_installed is True
        assert installed_ver is not None

    @pytest.mark.unit
    def test_check_unknown_package_no_version(self) -> None:
        """Test that ValueError is raised when package has no registry entry and min_version is None."""
        from lib.package_verification import check_package_version

        with pytest.raises(ValueError, match="No version requirement specified"):
            check_package_version("unknown_pkg_xyz", min_version=None, raise_on_error=False)


@pytest.mark.unit
class TestRequirePackage:
    """Test require_package function."""

    @pytest.mark.unit
    def test_require_available_package(self) -> None:
        """Test requiring a package that is available and meets version."""
        from lib.package_verification import require_package

        # networkx should be available
        require_package("networkx", "test context")
        # Should not raise or exit

    @pytest.mark.unit
    def test_require_missing_package(self, capsys: Any) -> None:
        """Test requiring a missing package exits with error."""
        from lib.package_verification import require_package
        from lib.constants import EXIT_RUNTIME_ERROR

        with pytest.raises(SystemExit) as exc_info:
            require_package("nonexistent_package_xyz123", "test feature")

        assert exc_info.value.code == EXIT_RUNTIME_ERROR

        captured = capsys.readouterr()
        assert "Unknown package 'nonexistent_package_xyz123'" in captured.err

    @pytest.mark.unit
    def test_require_old_version(self, capsys: Any) -> None:
        """Test requiring a package with version too old exits with error."""
        from lib.package_verification import require_package, PACKAGE_REQUIREMENTS
        from lib.constants import EXIT_RUNTIME_ERROR

        # Temporarily patch PACKAGE_REQUIREMENTS to require impossibly high version
        original_version = PACKAGE_REQUIREMENTS.get("networkx")
        PACKAGE_REQUIREMENTS["networkx"] = "999.0.0"

        try:
            with pytest.raises(SystemExit) as exc_info:
                require_package("networkx", "test feature")

            assert exc_info.value.code == EXIT_RUNTIME_ERROR

            captured = capsys.readouterr()
            assert "is too old" in captured.err
        finally:
            # Restore original version
            if original_version:
                PACKAGE_REQUIREMENTS["networkx"] = original_version

    @pytest.mark.unit
    def test_require_unknown_package(self, capsys: Any) -> None:
        """Test requiring a package not in registry exits with error."""
        from lib.package_verification import require_package
        from lib.constants import EXIT_RUNTIME_ERROR

        with pytest.raises(SystemExit) as exc_info:
            require_package("unknown_package_not_in_registry", "test")

        assert exc_info.value.code == EXIT_RUNTIME_ERROR

        captured = capsys.readouterr()
        assert "Unknown package" in captured.err


@pytest.mark.unit
class TestCheckAllPackages:
    """Test check_all_packages function."""

    @pytest.mark.unit
    def test_check_all_packages_success(self, capsys: Any) -> None:
        """Test check_all_packages when all required packages are available."""
        from lib.package_verification import check_all_packages

        result = check_all_packages()

        # Should succeed since we have networkx and GitPython installed
        assert result is True

        captured = capsys.readouterr()
        assert "BuildCheck Package Verification" in captured.out
        assert "All required packages are available" in captured.out

    @pytest.mark.unit
    def test_check_all_packages_display_optional(self, capsys: Any) -> None:
        """Test that check_all_packages displays optional package status."""
        from lib.package_verification import check_all_packages

        check_all_packages()

        captured = capsys.readouterr()
        assert "colorama (optional)" in captured.out
        assert "scipy (optional)" in captured.out

    @pytest.mark.unit
    @patch("lib.package_verification.check_package_version")
    def test_check_all_packages_missing_required(self, mock_check: Any, capsys: Any) -> None:
        """Test check_all_packages when required packages are missing."""
        from lib.package_verification import check_all_packages

        # Simulate networkx missing
        def side_effect(pkg_name: str, min_ver: str, raise_on_error: bool = True) -> tuple[bool, bool, str | None]:
            if pkg_name == "networkx":
                return (False, False, None)
            elif pkg_name == "packaging":
                return (True, True, "24.0")
            elif pkg_name == "GitPython":
                return (True, True, "3.1.40")
            else:
                return (True, True, "1.0.0")

        mock_check.side_effect = side_effect

        result = check_all_packages()

        assert result is False

        captured = capsys.readouterr()
        assert "Some required packages are missing or too old" in captured.err

    @pytest.mark.unit
    @patch("lib.package_verification.check_package_version")
    def test_check_all_packages_old_version(self, mock_check: Any, capsys: Any) -> None:
        """Test check_all_packages when packages are too old."""
        from lib.package_verification import check_all_packages

        # Simulate networkx being too old
        def side_effect(pkg_name: str, min_ver: str, raise_on_error: bool = True) -> tuple[bool, bool, str | None]:
            if pkg_name == "networkx":
                return (True, False, "2.0.0")  # Too old
            elif pkg_name == "packaging":
                return (True, True, "24.0")
            elif pkg_name == "GitPython":
                return (True, True, "3.1.40")
            else:
                return (True, True, "1.0.0")

        mock_check.side_effect = side_effect

        result = check_all_packages()

        assert result is False

        captured = capsys.readouterr()
        assert "need >=" in captured.err

    @pytest.mark.unit
    @patch("lib.package_verification.check_package_version")
    def test_check_all_packages_exception_handling(self, mock_check: Any, capsys: Any) -> None:
        """Test check_all_packages handles exceptions gracefully."""
        from lib.package_verification import check_all_packages

        # Simulate exception during check
        def side_effect(pkg_name: str, min_ver: str, raise_on_error: bool = True) -> tuple[bool, bool, str | None]:
            if pkg_name == "networkx":
                raise RuntimeError("Test error")
            elif pkg_name == "packaging":
                return (True, True, "24.0")
            elif pkg_name == "GitPython":
                return (True, True, "3.1.40")
            else:
                return (True, True, "1.0.0")

        mock_check.side_effect = side_effect

        result = check_all_packages()

        assert result is False

        captured = capsys.readouterr()
        assert "check failed" in captured.err


@pytest.mark.unit
class TestPackageConstants:
    """Test package requirement constants."""

    @pytest.mark.unit
    def test_package_requirements_exist(self) -> None:
        """Test that PACKAGE_REQUIREMENTS is defined with expected packages."""
        from lib.package_verification import PACKAGE_REQUIREMENTS

        assert "networkx" in PACKAGE_REQUIREMENTS
        assert "GitPython" in PACKAGE_REQUIREMENTS
        assert "packaging" in PACKAGE_REQUIREMENTS
        assert "colorama" in PACKAGE_REQUIREMENTS

    @pytest.mark.unit
    def test_optional_packages_exist(self) -> None:
        """Test that OPTIONAL_PACKAGES is defined."""
        from lib.package_verification import OPTIONAL_PACKAGES

        assert "scipy" in OPTIONAL_PACKAGES

    @pytest.mark.unit
    def test_version_strings_format(self) -> None:
        """Test that version strings are in correct format."""
        from lib.package_verification import PACKAGE_REQUIREMENTS
        from packaging.version import parse

        for pkg, ver_str in PACKAGE_REQUIREMENTS.items():
            # Should be parseable
            version = parse(ver_str)
            assert version is not None


@pytest.mark.unit
class TestPythonVersionCheck:
    """Test Python version enforcement."""

    @pytest.mark.unit
    def test_current_python_version_supported(self) -> None:
        """Test that current Python version is 3.8+."""
        assert sys.version_info >= (3, 8), "Tests should run on Python 3.8+"


@pytest.mark.unit
class TestMainFunction:
    """Test main CLI function."""

    @pytest.mark.unit
    def test_main_check_all_success(self, capsys: Any) -> None:
        """Test main function with --check-all flag."""
        from lib.package_verification import main

        with patch("sys.argv", ["package_verification.py", "--check-all"]):
            exit_code = main()

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "BuildCheck Package Verification" in captured.out

    @pytest.mark.unit
    @patch("lib.package_verification.check_all_packages")
    def test_main_check_all_failure(self, mock_check_all: Any) -> None:
        """Test main function when checks fail."""
        from lib.package_verification import main

        mock_check_all.return_value = False

        with patch("sys.argv", ["package_verification.py", "--check-all"]):
            exit_code = main()

        assert exit_code == 1

    @pytest.mark.unit
    def test_main_no_args(self, capsys: Any) -> None:
        """Test main function with no arguments."""
        from lib.package_verification import main

        with patch("sys.argv", ["package_verification.py"]):
            exit_code = main()

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "usage:" in captured.out or "Verify build-check package dependencies" in captured.out
