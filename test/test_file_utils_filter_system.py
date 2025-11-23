#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for system header filtering in file_utils.py."""

import pytest
from lib.file_utils import filter_system_headers, FilterStatistics


class TestFilterSystemHeaders:
    """Test filter_system_headers function."""

    def test_filter_system_headers_basic(self) -> None:
        """Test basic system header filtering."""
        headers = {"/usr/include/iostream", "/usr/include/stdio.h", "/home/project/MyHeader.hpp", "/usr/lib/gcc/stddef.h", "/home/project/Utils.h"}

        filtered, stats = filter_system_headers(headers, show_progress=False)

        # Should keep only project headers
        assert len(filtered) == 2
        assert "/home/project/MyHeader.hpp" in filtered
        assert "/home/project/Utils.h" in filtered

        # Check statistics
        assert stats["total_excluded"] == 3
        assert "/usr/" in stats["by_prefix"]

    def test_filter_system_headers_no_system_headers(self) -> None:
        """Test filtering when no system headers present."""
        headers = {"/home/project/Header1.hpp", "/home/project/Header2.hpp"}

        filtered, stats = filter_system_headers(headers, show_progress=False)

        assert filtered == headers
        assert stats["total_excluded"] == 0
        assert len(stats["by_prefix"]) == 0

    def test_filter_system_headers_all_system(self) -> None:
        """Test filtering when all headers are system headers."""
        headers = {"/usr/include/iostream", "/usr/include/vector", "/lib/x86_64-linux-gnu/glibc.h"}

        filtered, stats = filter_system_headers(headers, show_progress=False)

        assert len(filtered) == 0
        assert stats["total_excluded"] == 3

    def test_filter_system_headers_examples_limit(self) -> None:
        """Test that examples are limited to 5 per prefix."""
        headers = set()
        # Add many system headers from same prefix
        for i in range(10):
            headers.add(f"/usr/include/header{i}.h")

        filtered, stats = filter_system_headers(headers, show_progress=False)

        # Should have all excluded
        assert stats["total_excluded"] == 10
        # But examples should be limited to 5
        assert len(stats["by_prefix"]["/usr/"]["examples"]) == 5


class TestFilterStatistics:
    """Test FilterStatistics dataclass."""

    def test_filter_statistics_concise_format(self) -> None:
        """Test concise format output."""
        stats = FilterStatistics(
            initial_count=1000,
            final_count=500,
            system_headers={"total_excluded": 100, "by_prefix": {}},
            exclude_patterns={"total_excluded": 50, "by_pattern": {}},
        )

        concise = stats.format_concise()
        assert "1,000" in concise
        assert "500" in concise
        assert "100 system" in concise or "100" in concise
        assert "50" in concise

    def test_filter_statistics_verbose_format(self) -> None:
        """Test verbose format output."""
        stats = FilterStatistics(
            initial_count=1000,
            final_count=500,
            system_headers={
                "total_excluded": 100,
                "by_prefix": {"/usr/include": {"count": 80, "examples": ["iostream", "vector"]}, "/usr/lib": {"count": 20, "examples": ["stddef.h"]}},
            },
            exclude_patterns={"total_excluded": 50, "by_pattern": {"*/ThirdParty/*": {"count": 50, "examples": ["/project/ThirdParty/lib.hpp"]}}},
        )

        verbose = stats.format_verbose("/project")
        assert "System Headers Excluded" in verbose
        assert "/usr/include" in verbose
        assert "iostream" in verbose
        assert "ThirdParty" in verbose

    def test_filter_statistics_no_exclusions(self) -> None:
        """Test statistics with no exclusions."""
        stats = FilterStatistics(initial_count=100, final_count=100, system_headers={"total_excluded": 0, "by_prefix": {}}, exclude_patterns={})

        concise = stats.format_concise()
        assert "100" in concise
        verbose = stats.format_verbose("/project")
        # Should handle empty stats gracefully
        assert isinstance(verbose, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
