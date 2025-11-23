#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for exclude_headers_by_patterns function in lib.file_utils."""

import os
import pytest
from typing import Set, List
from lib.file_utils import exclude_headers_by_patterns


class TestExcludeHeadersByPatterns:
    """Test exclude_headers_by_patterns function."""

    def test_exclude_single_pattern(self) -> None:
        """Test exclusion with single pattern."""
        headers = {"/project/src/core/Engine.hpp", "/project/src/ThirdParty/lib.hpp", "/project/src/utils/Helper.hpp"}
        exclude_patterns = ["*/ThirdParty/*"]
        project_root = "/project"

        filtered, excluded_count, no_matches, _ = exclude_headers_by_patterns(headers, exclude_patterns, project_root)

        assert len(filtered) == 2
        assert "/project/src/core/Engine.hpp" in filtered
        assert "/project/src/utils/Helper.hpp" in filtered
        assert "/project/src/ThirdParty/lib.hpp" not in filtered
        assert excluded_count == 1
        assert len(no_matches) == 0

    def test_exclude_multiple_patterns(self) -> None:
        """Test exclusion with multiple patterns."""
        headers = {
            "/project/src/core/Engine.hpp",
            "/project/src/ThirdParty/lib.hpp",
            "/project/src/test/Test.hpp",
            "/project/src/build/generated.hpp",  # Changed to be under src/
            "/project/src/utils/Helper.hpp",
        }
        exclude_patterns = ["*/ThirdParty/*", "*/test/*", "*/build/*"]
        project_root = "/project"

        filtered, excluded_count, no_matches, _ = exclude_headers_by_patterns(headers, exclude_patterns, project_root)

        assert len(filtered) == 2
        assert "/project/src/core/Engine.hpp" in filtered
        assert "/project/src/utils/Helper.hpp" in filtered
        assert excluded_count == 3
        assert len(no_matches) == 0

    def test_exclude_by_extension(self) -> None:
        """Test exclusion by file extension pattern."""
        headers = {"/project/src/Engine.hpp", "/project/src/generated.h", "/project/src/auto_generated.h", "/project/src/Helper.hpp"}
        exclude_patterns = ["*_generated.h"]
        project_root = "/project"

        filtered, excluded_count, no_matches, _ = exclude_headers_by_patterns(headers, exclude_patterns, project_root)

        assert len(filtered) == 3
        assert "/project/src/auto_generated.h" not in filtered
        assert excluded_count == 1

    def test_exclude_no_patterns(self) -> None:
        """Test that empty pattern list returns original set."""
        headers = {"/project/src/Engine.hpp", "/project/src/Helper.hpp"}
        exclude_patterns: List[str] = []
        project_root = "/project"

        filtered, excluded_count, no_matches, _ = exclude_headers_by_patterns(headers, exclude_patterns, project_root)

        assert filtered == headers
        assert excluded_count == 0
        assert len(no_matches) == 0

    def test_exclude_pattern_no_matches(self) -> None:
        """Test that pattern with no matches is reported."""
        headers = {"/project/src/Engine.hpp", "/project/src/Helper.hpp"}
        exclude_patterns = ["*/ThirdParty/*", "*/NonExistent/*"]
        project_root = "/project"

        filtered, excluded_count, no_matches, _ = exclude_headers_by_patterns(headers, exclude_patterns, project_root)

        assert len(filtered) == 2
        assert excluded_count == 0
        assert len(no_matches) == 2
        assert "*/ThirdParty/*" in no_matches
        assert "*/NonExistent/*" in no_matches

    def test_exclude_all_headers(self) -> None:
        """Test exclusion of all headers."""
        headers = {"/project/src/ThirdParty/lib1.hpp", "/project/src/ThirdParty/lib2.hpp"}
        exclude_patterns = ["*/ThirdParty/*"]
        project_root = "/project"

        filtered, excluded_count, no_matches, _ = exclude_headers_by_patterns(headers, exclude_patterns, project_root)

        assert len(filtered) == 0
        assert excluded_count == 2
        assert len(no_matches) == 0

    def test_exclude_wildcards(self) -> None:
        """Test various wildcard patterns."""
        headers = {
            "/project/src/core/Engine.hpp",
            "/project/src/test/unit/Test1.hpp",
            "/project/src/test/integration/Test2.hpp",
            "/project/include/public/API.hpp",
        }
        exclude_patterns = ["*/test/*"]
        project_root = "/project"

        filtered, excluded_count, no_matches, _ = exclude_headers_by_patterns(headers, exclude_patterns, project_root)

        # Should exclude both unit and integration tests
        assert len(filtered) == 2
        assert "/project/src/core/Engine.hpp" in filtered
        assert "/project/include/public/API.hpp" in filtered
        assert excluded_count == 2

    def test_exclude_relative_paths(self) -> None:
        """Test exclusion works with relative path conversion."""
        headers = {"/home/user/project/src/Engine.hpp", "/home/user/project/ThirdParty/lib.hpp"}
        exclude_patterns = ["ThirdParty/*"]
        project_root = "/home/user/project"

        filtered, excluded_count, no_matches, _ = exclude_headers_by_patterns(headers, exclude_patterns, project_root)

        assert len(filtered) == 1
        assert "/home/user/project/src/Engine.hpp" in filtered
        assert excluded_count == 1

    def test_exclude_case_sensitive(self) -> None:
        """Test that pattern matching is case-sensitive."""
        headers = {"/project/src/thirdparty/lib.hpp", "/project/src/ThirdParty/lib2.hpp"}
        exclude_patterns = ["*/ThirdParty/*"]
        project_root = "/project"

        filtered, excluded_count, no_matches, _ = exclude_headers_by_patterns(headers, exclude_patterns, project_root)

        # Only exact case match should be excluded
        assert len(filtered) == 1
        assert "/project/src/thirdparty/lib.hpp" in filtered
        assert excluded_count == 1

    def test_exclude_mixed_results(self) -> None:
        """Test with some patterns matching and some not."""
        headers = {"/project/src/Engine.hpp", "/project/src/ThirdParty/lib.hpp", "/project/src/Helper.hpp"}
        exclude_patterns = ["*/ThirdParty/*", "*/NonExistent/*", "*/test/*"]
        project_root = "/project"

        filtered, excluded_count, no_matches, _ = exclude_headers_by_patterns(headers, exclude_patterns, project_root)

        assert len(filtered) == 2
        assert excluded_count == 1
        assert len(no_matches) == 2
        assert "*/NonExistent/*" in no_matches
        assert "*/test/*" in no_matches


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
