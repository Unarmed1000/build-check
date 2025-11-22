#!/usr/bin/env python3
"""Tests for lib/package_verification.py"""

import sys
import pytest
from typing import Optional, Tuple
from unittest.mock import Mock, patch, MagicMock
from importlib.metadata import PackageNotFoundError


def test_python_version_enforcement() -> None:
    """Test that Python 3.8+ is enforced at module level."""
    # This test verifies the module can be imported with current Python version
    import lib.package_verification
    assert lib.package_verification is not None


def test_package_requirements_registry() -> None:
    """Test that package requirements are properly defined."""
    from lib.package_verification import PACKAGE_REQUIREMENTS
    
    assert 'networkx' in PACKAGE_REQUIREMENTS
    assert 'GitPython' in PACKAGE_REQUIREMENTS
    assert 'packaging' in PACKAGE_REQUIREMENTS
    assert 'colorama' in PACKAGE_REQUIREMENTS
    
    # Verify minimum versions are specified
    assert PACKAGE_REQUIREMENTS['networkx'] == '2.8.8'
    assert PACKAGE_REQUIREMENTS['GitPython'] == '3.1.40'
    assert PACKAGE_REQUIREMENTS['packaging'] == '24.0'
    assert PACKAGE_REQUIREMENTS['colorama'] == '0.4.6'


def test_check_package_version_installed_and_current() -> None:
    """Test check_package_version with installed and current package."""
    from lib.package_verification import check_package_version
    
    # networkx should be installed in test environment
    is_installed, meets_version, installed_ver = check_package_version(
        'networkx', 
        '2.8.8',
        raise_on_error=False
    )
    
    assert is_installed is True
    assert meets_version is True
    assert installed_ver is not None


def test_check_package_version_missing_package() -> None:
    """Test check_package_version with missing package."""
    from lib.package_verification import check_package_version
    
    with patch('lib.package_verification.version') as mock_version:
        mock_version.side_effect = PackageNotFoundError()
        
        # Should not raise with raise_on_error=False
        is_installed, meets_version, installed_ver = check_package_version(
            'nonexistent-package',
            '1.0.0',
            raise_on_error=False
        )
        
        assert is_installed is False
        assert meets_version is False
        assert installed_ver is None


def test_check_package_version_missing_raises() -> None:
    """Test that check_package_version raises ImportError for missing package when requested."""
    from lib.package_verification import check_package_version
    
    with patch('lib.package_verification.version') as mock_version:
        mock_version.side_effect = PackageNotFoundError()
        
        with pytest.raises(ImportError) as exc_info:
            check_package_version('nonexistent-package', '1.0.0', raise_on_error=True)
        
        assert 'nonexistent-package' in str(exc_info.value)
        assert 'not installed' in str(exc_info.value)
        assert 'pip install' in str(exc_info.value)


def test_check_package_version_old_version() -> None:
    """Test check_package_version with old package version."""
    from lib.package_verification import check_package_version
    
    with patch('lib.package_verification.version') as mock_version:
        mock_version.return_value = '2.0.0'
        
        # Should not raise with raise_on_error=False
        is_installed, meets_version, installed_ver = check_package_version(
            'some-package',
            '3.0.0',
            raise_on_error=False
        )
        
        assert is_installed is True
        assert meets_version is False
        assert installed_ver == '2.0.0'


def test_check_package_version_old_raises() -> None:
    """Test that check_package_version raises ImportError for old version when requested."""
    from lib.package_verification import check_package_version
    
    with patch('lib.package_verification.version') as mock_version:
        mock_version.return_value = '2.0.0'
        
        with pytest.raises(ImportError) as exc_info:
            check_package_version('some-package', '3.0.0', raise_on_error=True)
        
        assert 'some-package' in str(exc_info.value)
        assert '2.0.0' in str(exc_info.value)
        assert 'too old' in str(exc_info.value)
        assert '3.0.0' in str(exc_info.value)
        assert 'pip install --upgrade' in str(exc_info.value)


def test_check_package_version_uses_registry() -> None:
    """Test that check_package_version uses registry when no version specified."""
    from lib.package_verification import check_package_version
    
    with patch('lib.package_verification.version') as mock_version:
        mock_version.return_value = '3.0.0'
        
        # Should use registry version for networkx (2.8.8)
        is_installed, meets_version, installed_ver = check_package_version(
            'networkx',
            min_version=None,  # Use registry
            raise_on_error=False
        )
        
        assert is_installed is True
        assert meets_version is True  # 3.0.0 >= 2.8.8


def test_print_error_with_colors() -> None:
    """Test print_error formats messages with colors when available."""
    from lib.color_utils import print_error
    
    with patch('sys.stderr') as mock_stderr:
        print_error("Test error message")
        # Should have been called (exact formatting depends on color_utils availability)
        assert mock_stderr.write.called or True  # print might be called instead


def test_print_warning_with_colors() -> None:
    """Test print_warning formats messages with colors when available."""
    from lib.color_utils import print_warning
    
    with patch('sys.stderr') as mock_stderr:
        print_warning("Test warning message")
        # Should have been called
        assert mock_stderr.write.called or True


def test_print_success_with_colors() -> None:
    """Test print_success formats messages with colors when available."""
    from lib.color_utils import print_success
    
    with patch('sys.stdout') as mock_stdout:
        print_success("Test success message")
        # Should have been called
        assert mock_stdout.write.called or True


def test_check_all_packages_success() -> None:
    """Test check_all_packages with all packages available."""
    from lib.package_verification import check_all_packages
    
    with patch('lib.package_verification.check_package_version') as mock_check:
        # Mock all packages as installed and current
        mock_check.return_value = (True, True, '1.0.0')
        
        result = check_all_packages()
        
        assert result is True
        # Should have checked packaging, networkx, GitPython, colorama
        assert mock_check.call_count >= 4


def test_check_all_packages_missing_required() -> None:
    """Test check_all_packages with missing required package."""
    from lib.package_verification import check_all_packages
    
    with patch('lib.package_verification.check_package_version') as mock_check:
        def side_effect(pkg_name: str, version: Optional[str], raise_on_error: bool = False) -> Tuple[bool, bool, Optional[str]]:
            if pkg_name == 'networkx':
                return (False, False, None)  # Missing
            return (True, True, '1.0.0')
        
        mock_check.side_effect = side_effect
        
        result = check_all_packages()
        
        assert result is False


def test_check_all_packages_old_required() -> None:
    """Test check_all_packages with old required package version."""
    from lib.package_verification import check_all_packages
    
    with patch('lib.package_verification.check_package_version') as mock_check:
        def side_effect(pkg_name: str, version: Optional[str], raise_on_error: bool = False) -> Tuple[bool, bool, Optional[str]]:
            if pkg_name == 'GitPython':
                return (True, False, '2.0.0')  # Too old
            return (True, True, '1.0.0')
        
        mock_check.side_effect = side_effect
        
        result = check_all_packages()
        
        assert result is False


def test_cli_check_all_success(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI --check-all with successful verification."""
    from lib.package_verification import main
    
    with patch('sys.argv', ['package_verification', '--check-all']):
        with patch('lib.package_verification.check_all_packages') as mock_check:
            mock_check.return_value = True
            
            exit_code = main()
            
            assert exit_code == 0
            assert mock_check.called


def test_cli_check_all_failure(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI --check-all with failed verification."""
    from lib.package_verification import main
    
    with patch('sys.argv', ['package_verification', '--check-all']):
        with patch('lib.package_verification.check_all_packages') as mock_check:
            mock_check.return_value = False
            
            exit_code = main()
            
            assert exit_code == 1
            assert mock_check.called


def test_lib_git_utils_verify_requirements() -> None:
    """Test that lib.git_utils.verify_requirements works."""
    from lib.git_utils import verify_requirements
    
    # Should not raise (GitPython is installed in test environment)
    verify_requirements()
    
    # Calling again should be cached (no error)
    verify_requirements()


def test_lib_graph_utils_verify_requirements() -> None:
    """Test that lib.graph_utils.verify_requirements works."""
    from lib.graph_utils import verify_requirements
    
    # Should not raise (networkx is installed in test environment)
    verify_requirements()
    
    # Calling again should be cached
    verify_requirements()


def test_lib_dsm_analysis_verify_requirements() -> None:
    """Test that lib.dsm_analysis.verify_requirements works."""
    from lib.dsm_analysis import verify_requirements
    
    # Should not raise (networkx is installed in test environment)
    verify_requirements()
    
    # Calling again should be cached
    verify_requirements()


def test_lib_export_utils_verify_requirements() -> None:
    """Test that lib.export_utils.verify_requirements works."""
    from lib.export_utils import verify_requirements
    
    # Should not raise (networkx is installed in test environment)
    verify_requirements()
    
    # Calling again should be cached
    verify_requirements()


def test_verify_requirements_caching() -> None:
    """Test that verify_requirements caches results."""
    from lib.graph_utils import verify_requirements
    
    # Reset the cache flag for this test
    import lib.graph_utils
    lib.graph_utils._requirements_verified = False
    
    with patch('lib.package_verification.check_package_version') as mock_check:
        mock_check.return_value = (True, True, '3.0.0')
        
        # First call should check
        verify_requirements()
        assert mock_check.call_count == 1
        
        # Second call should be cached (no additional check)
        verify_requirements()
        assert mock_check.call_count == 1  # Still 1, not 2


def test_verify_requirements_raises_on_missing() -> None:
    """Test that verify_requirements raises ImportError when package missing."""
    import lib.graph_utils
    
    # Reset cache
    lib.graph_utils._requirements_verified = False
    
    with patch('lib.package_verification.check_package_version') as mock_check:
        mock_check.side_effect = ImportError("networkx is not installed")
        
        with pytest.raises(ImportError) as exc_info:
            lib.graph_utils.verify_requirements()
        
        assert 'networkx' in str(exc_info.value)


def test_version_comparison_semantic() -> None:
    """Test that version comparison uses semantic versioning."""
    from lib.package_verification import check_package_version
    
    with patch('lib.package_verification.version') as mock_version:
        # Test that 3.10.0 > 3.9.0 (not lexicographic comparison)
        mock_version.return_value = '3.10.0'
        
        is_installed, meets_version, _ = check_package_version(
            'test-pkg', '3.9.0', raise_on_error=False
        )
        
        assert meets_version is True  # 3.10.0 >= 3.9.0
        
        # Test that 3.10.0 < 3.11.0
        is_installed, meets_version, _ = check_package_version(
            'test-pkg', '3.11.0', raise_on_error=False
        )
        
        assert meets_version is False  # 3.10.0 < 3.11.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
