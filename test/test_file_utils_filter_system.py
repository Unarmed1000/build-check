#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for system header filtering in file_utils.py."""

import pytest
from lib.file_utils import filter_by_file_type, FilterStatistics, FileClassificationStats
from lib.clang_utils import FileType


class TestFilterSystemHeaders:
    """Test filter_system_headers function."""

    def test_filter_system_headers_basic(self) -> None:
        """Test basic system header filtering."""
        headers = {"/usr/include/iostream", "/usr/include/stdio.h", "/home/project/MyHeader.hpp", "/usr/lib/gcc/stddef.h", "/home/project/Utils.h"}

        # Create file_types mapping
        file_types = {
            "/usr/include/iostream": FileType.SYSTEM,
            "/usr/include/stdio.h": FileType.SYSTEM,
            "/home/project/MyHeader.hpp": FileType.PROJECT,
            "/usr/lib/gcc/stddef.h": FileType.SYSTEM,
            "/home/project/Utils.h": FileType.PROJECT,
        }

        filtered, stats = filter_by_file_type(headers, file_types, exclude_types={FileType.SYSTEM}, show_progress=False)

        # Should keep only project headers
        assert len(filtered) == 2
        assert "/home/project/MyHeader.hpp" in filtered
        assert "/home/project/Utils.h" in filtered

        # Check statistics
        assert stats.system == 3
        assert stats.project == 2

    def test_filter_system_headers_no_system_headers(self) -> None:
        """Test filtering when no system headers present."""
        headers = {"/home/project/Header1.hpp", "/home/project/Header2.hpp"}

        # Create file_types mapping - all project files
        file_types = {"/home/project/Header1.hpp": FileType.PROJECT, "/home/project/Header2.hpp": FileType.PROJECT}

        filtered, stats = filter_by_file_type(headers, file_types, exclude_types={FileType.SYSTEM}, show_progress=False)

        assert filtered == headers
        assert stats.system == 0
        assert stats.project == 2

    def test_filter_system_headers_all_system(self) -> None:
        """Test filtering when all headers are system headers."""
        headers = {"/usr/include/iostream", "/usr/include/vector", "/lib/x86_64-linux-gnu/glibc.h"}

        # Create file_types mapping - all system files
        file_types = {"/usr/include/iostream": FileType.SYSTEM, "/usr/include/vector": FileType.SYSTEM, "/lib/x86_64-linux-gnu/glibc.h": FileType.SYSTEM}

        filtered, stats = filter_by_file_type(headers, file_types, exclude_types={FileType.SYSTEM}, show_progress=False)

        assert len(filtered) == 0
        assert stats.system == 3

    def test_filter_system_headers_large_set(self) -> None:
        """Test filtering a large set of system headers."""
        headers = set()
        # Add many system headers
        for i in range(10):
            headers.add(f"/usr/include/header{i}.h")

        # Create file_types mapping - all system files
        file_types = {h: FileType.SYSTEM for h in headers}

        filtered, stats = filter_by_file_type(headers, file_types, exclude_types={FileType.SYSTEM}, show_progress=False)

        # Should have all excluded
        assert len(filtered) == 0
        assert stats.system == 10
        assert stats.total == 10


class TestFilterStatistics:
    """Test FilterStatistics dataclass."""

    def test_filter_statistics_concise_format(self) -> None:
        """Test concise format output."""
        file_stats = FileClassificationStats(system=100, third_party=0, generated=0, project=400, total=500)
        stats = FilterStatistics(initial_count=1000, final_count=500, system_headers=file_stats, exclude_patterns={"total_excluded": 50, "by_pattern": {}})

        concise = stats.format_concise()
        assert "1,000" in concise
        assert "500" in concise
        assert "100" in concise  # system headers excluded
        assert "50" in concise  # pattern excluded

    def test_filter_statistics_verbose_format(self) -> None:
        """Test verbose format output."""
        file_stats = FileClassificationStats(system=100, third_party=50, generated=0, project=350, total=500)
        stats = FilterStatistics(
            initial_count=1000,
            final_count=500,
            system_headers=file_stats,
            exclude_patterns={"total_excluded": 50, "by_pattern": {"*/ThirdParty/*": {"count": 50, "examples": ["/project/ThirdParty/lib.hpp"]}}},
        )

        verbose = stats.format_verbose("/project")
        assert "File Classification" in verbose
        assert "System:" in verbose or "100" in verbose
        assert "ThirdParty" in verbose

    def test_filter_statistics_no_exclusions(self) -> None:
        """Test statistics with no exclusions."""
        file_stats = FileClassificationStats(system=0, third_party=0, generated=0, project=100, total=100)
        stats = FilterStatistics(initial_count=100, final_count=100, system_headers=file_stats, exclude_patterns={})

        concise = stats.format_concise()
        assert "100" in concise
        verbose = stats.format_verbose("/project")
        # Should handle empty stats gracefully
        assert isinstance(verbose, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
