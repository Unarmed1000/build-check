#!/usr/bin/env python3
"""Quick test script to verify library module imports work correctly."""

import sys

def test_imports() -> int:
    """Test that all library modules can be imported."""
    
    print("Testing library module imports...")
    errors = []
    
    # Test ninja_utils
    try:
        from lib.ninja_utils import check_ninja_available, extract_rebuild_info
        print("✓ lib.ninja_utils")
    except Exception as e:
        errors.append(f"✗ lib.ninja_utils: {e}")
    
    # Test clang_utils
    try:
        from lib.clang_utils import find_clang_scan_deps, is_valid_source_file
        print("✓ lib.clang_utils")
    except Exception as e:
        errors.append(f"✗ lib.clang_utils: {e}")
    
    # Test graph_utils
    try:
        from lib.graph_utils import build_dependency_graph
        print("✓ lib.graph_utils")
    except Exception as e:
        errors.append(f"✗ lib.graph_utils: {e}")
    
    # Test library_parser
    try:
        from lib.library_parser import parse_ninja_libraries
        print("✓ lib.library_parser")
    except Exception as e:
        errors.append(f"✗ lib.library_parser: {e}")
    
    # Test git_utils
    try:
        from lib.git_utils import find_git_repo, check_git_available
        print("✓ lib.git_utils")
    except Exception as e:
        errors.append(f"✗ lib.git_utils: {e}")
    
    # Test color_utils
    try:
        from lib.color_utils import Colors, print_success
        print("✓ lib.color_utils")
    except Exception as e:
        errors.append(f"✗ lib.color_utils: {e}")
    
    # Test file_utils
    try:
        from lib.file_utils import filter_headers_by_pattern, cluster_headers_by_directory
        print("✓ lib.file_utils")
    except Exception as e:
        errors.append(f"✗ lib.file_utils: {e}")
    
    # Test export_utils
    try:
        from lib.export_utils import export_dsm_to_csv, export_dependency_graph
        print("✓ lib.export_utils")
    except Exception as e:
        errors.append(f"✗ lib.export_utils: {e}")
    
    if errors:
        print("\nErrors found:")
        for error in errors:
            print(f"  {error}")
        return 1
    else:
        print("\n✓ All library modules imported successfully!")
        return 0


def test_script_imports() -> int:
    """Test that updated scripts can still import properly."""
    
    print("\nTesting updated script imports...")
    errors = []
    
    scripts = [
        'buildCheckSummary',
        'buildCheckImpact',
        'buildCheckIncludeChains',
        'buildCheckDependencyHell',
        'buildCheckIncludeGraph',
        'buildCheckRippleEffect',
        'buildCheckDSM',
        'buildCheckLibraryGraph',
        'buildCheckOptimize'
    ]
    
    for script in scripts:
        try:
            __import__(script)
            print(f"✓ {script}.py")
        except Exception as e:
            errors.append(f"✗ {script}.py: {e}")
    
    if errors:
        print("\nErrors found:")
        for error in errors:
            print(f"  {error}")
        return 1
    else:
        print("\n✓ All scripts imported successfully!")
        return 0


if __name__ == "__main__":
    result1 = test_imports()
    result2 = test_script_imports()
    sys.exit(max(result1, result2))
