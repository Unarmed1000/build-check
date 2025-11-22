#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for exclude functionality in buildCheckDSM.py."""

import os
import pytest
from argparse import Namespace
from typing import Set, Dict
from unittest.mock import Mock

# Import functions to test
from buildCheckDSM import apply_exclude_filters, apply_all_filters


class TestApplyExcludeFilters:
    """Test apply_exclude_filters function."""
    
    def test_apply_exclude_single_pattern(self) -> None:
        """Test applying single exclude pattern."""
        headers = {
            "/project/src/Engine.hpp",
            "/project/ThirdParty/lib.hpp",
            "/project/src/Helper.hpp",
        }
        exclude_patterns = ["ThirdParty/*"]
        project_root = "/project"
        
        filtered, excluded_count, no_matches = apply_exclude_filters(
            headers, exclude_patterns, project_root
        )
        
        assert len(filtered) == 2
        assert excluded_count == 1
        assert len(no_matches) == 0
    
    def test_apply_exclude_multiple_patterns(self) -> None:
        """Test applying multiple exclude patterns."""
        headers = {
            "/project/src/Engine.hpp",
            "/project/ThirdParty/lib.hpp",
            "/project/test/Test.hpp",
            "/project/src/Helper.hpp",
        }
        exclude_patterns = ["ThirdParty/*", "test/*"]
        project_root = "/project"
        
        filtered, excluded_count, no_matches = apply_exclude_filters(
            headers, exclude_patterns, project_root
        )
        
        assert len(filtered) == 2
        assert excluded_count == 2
    
    def test_apply_exclude_empty_list(self) -> None:
        """Test that empty exclude list returns original headers."""
        headers = {
            "/project/src/Engine.hpp",
            "/project/src/Helper.hpp",
        }
        exclude_patterns: list[str] = []
        project_root = "/project"
        
        filtered, excluded_count, no_matches = apply_exclude_filters(
            headers, exclude_patterns, project_root
        )
        
        assert filtered == headers
        assert excluded_count == 0
        assert len(no_matches) == 0


class TestApplyAllFiltersWithExclude:
    """Test apply_all_filters with exclude patterns."""
    
    def test_filter_then_exclude(self) -> None:
        """Test that include filter is applied before exclude."""
        headers = {
            "/project/FslBase/Engine.hpp",
            "/project/FslBase/ThirdParty/lib.hpp",
            "/project/FslGraphics/Renderer.hpp",
            "/project/FslGraphics/ThirdParty/lib2.hpp",
        }
        
        # Mock args with filter and exclude
        args = Namespace(
            library_filter=None,
            filter="FslBase/*",
            exclude=["*/ThirdParty/*"]
        )
        header_to_lib: Dict[str, str] = {}
        project_root = "/project"
        
        filtered = apply_all_filters(args, headers, header_to_lib, project_root)
        
        # Should include FslBase but exclude ThirdParty within it
        assert len(filtered) == 1
        assert "/project/FslBase/Engine.hpp" in filtered
        assert "/project/FslBase/ThirdParty/lib.hpp" not in filtered
    
    def test_exclude_without_filter(self) -> None:
        """Test exclude patterns without include filter."""
        headers = {
            "/project/src/Engine.hpp",
            "/project/ThirdParty/lib.hpp",
            "/project/src/Helper.hpp",
        }
        
        args = Namespace(
            library_filter=None,
            filter=None,
            exclude=["ThirdParty/*"]
        )
        header_to_lib: Dict[str, str] = {}
        project_root = "/project"
        
        filtered = apply_all_filters(args, headers, header_to_lib, project_root)
        
        assert len(filtered) == 2
        assert "/project/ThirdParty/lib.hpp" not in filtered
    
    def test_no_exclude_attribute(self) -> None:
        """Test that missing exclude attribute is handled gracefully."""
        headers = {
            "/project/src/Engine.hpp",
            "/project/src/Helper.hpp",
        }
        
        # Args without exclude attribute
        args = Namespace(
            library_filter=None,
            filter=None
        )
        header_to_lib: Dict[str, str] = {}
        project_root = "/project"
        
        filtered = apply_all_filters(args, headers, header_to_lib, project_root)
        
        assert filtered == headers
    
    def test_exclude_results_in_empty_set(self) -> None:
        """Test that excluding all headers raises ValueError."""
        headers = {
            "/project/ThirdParty/lib1.hpp",
            "/project/ThirdParty/lib2.hpp",
        }
        
        args = Namespace(
            library_filter=None,
            filter=None,
            exclude=["ThirdParty/*"]
        )
        header_to_lib: Dict[str, str] = {}
        project_root = "/project"
        
        with pytest.raises(ValueError, match="No headers found after filtering and exclusions"):
            apply_all_filters(args, headers, header_to_lib, project_root)
    
    def test_multiple_exclude_patterns(self) -> None:
        """Test multiple exclude patterns together."""
        headers = {
            "/project/src/Engine.hpp",
            "/project/ThirdParty/lib.hpp",
            "/project/test/Test.hpp",
            "/project/build/generated.hpp",
            "/project/src/Helper.hpp",
        }
        
        args = Namespace(
            library_filter=None,
            filter=None,
            exclude=["ThirdParty/*", "test/*", "build/*"]
        )
        header_to_lib: Dict[str, str] = {}
        project_root = "/project"
        
        filtered = apply_all_filters(args, headers, header_to_lib, project_root)
        
        assert len(filtered) == 2
        assert "/project/src/Engine.hpp" in filtered
        assert "/project/src/Helper.hpp" in filtered


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
