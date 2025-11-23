#!/usr/bin/env python3
"""Tests for lib/file_utils.py"""

import pytest
from typing import Any, Dict, List, Tuple, Generator
import os
import tempfile
from pathlib import Path

from lib.file_utils import filter_headers_by_pattern, cluster_headers_by_directory


class TestFilterHeadersByPattern:
    """Tests for filter_headers_by_pattern function."""

    def test_basic_pattern_matching(self, temp_dir: Any) -> None:
        """Test basic glob pattern matching."""
        headers = {
            str(temp_dir / "FslBase" / "include" / "header1.hpp"),
            str(temp_dir / "FslGraphics" / "include" / "header2.hpp"),
            str(temp_dir / "FslBase" / "source" / "header3.hpp"),
            str(temp_dir / "Other" / "header4.hpp"),
        }

        result = filter_headers_by_pattern(headers, "FslBase/*", str(temp_dir))

        assert len(result) == 2
        assert all("FslBase" in h for h in result)

    def test_wildcard_matching(self, temp_dir: Any) -> None:
        """Test wildcard pattern matching."""
        headers = {str(temp_dir / "src" / "math" / "vector.hpp"), str(temp_dir / "src" / "graphics" / "renderer.hpp"), str(temp_dir / "include" / "api.hpp")}

        result = filter_headers_by_pattern(headers, "src/*", str(temp_dir))

        assert len(result) == 2
        assert all("src" in h for h in result)

    def test_double_wildcard(self, temp_dir: Any) -> None:
        """Test ** pattern for recursive matching."""
        headers = {str(temp_dir / "lib" / "core" / "types.hpp"), str(temp_dir / "lib" / "util" / "string.hpp"), str(temp_dir / "test" / "unit.hpp")}

        result = filter_headers_by_pattern(headers, "lib/**", str(temp_dir))

        assert len(result) == 2

    def test_extension_matching(self, temp_dir: Any) -> None:
        """Test matching by file extension."""
        headers = {str(temp_dir / "file1.hpp"), str(temp_dir / "file2.h"), str(temp_dir / "file3.hxx")}

        result = filter_headers_by_pattern(headers, "*.hpp", str(temp_dir))

        assert len(result) == 1
        assert str(temp_dir / "file1.hpp") in result

    def test_no_matches(self, temp_dir: Any) -> None:
        """Test when pattern matches nothing."""
        headers = {str(temp_dir / "src" / "file.hpp")}

        result = filter_headers_by_pattern(headers, "nonexistent/*", str(temp_dir))

        assert len(result) == 0

    def test_all_match(self, temp_dir: Any) -> None:
        """Test pattern that matches all files."""
        headers = {str(temp_dir / "a.hpp"), str(temp_dir / "b.hpp")}

        result = filter_headers_by_pattern(headers, "*", str(temp_dir))

        assert len(result) == 2

    def test_absolute_path_handling(self, temp_dir: Any) -> None:
        """Test that absolute paths are handled correctly."""
        headers = {str(temp_dir / "module" / "header.hpp")}

        result = filter_headers_by_pattern(headers, "module/*", str(temp_dir))

        assert len(result) == 1

    def test_empty_headers_set(self, temp_dir: Any) -> None:
        """Test with empty headers set."""
        result = filter_headers_by_pattern(set(), "*.hpp", str(temp_dir))

        assert len(result) == 0


class TestClusterHeadersByDirectory:
    """Tests for cluster_headers_by_directory function."""

    def test_basic_clustering(self, temp_dir: Any) -> None:
        """Test basic directory clustering."""
        headers = [
            str(temp_dir / "FslBase" / "include" / "header1.hpp"),
            str(temp_dir / "FslBase" / "include" / "header2.hpp"),
            str(temp_dir / "FslGraphics" / "include" / "header3.hpp"),
        ]

        result = cluster_headers_by_directory(headers, str(temp_dir))

        assert "FslBase" in result
        assert "FslGraphics" in result
        assert len(result["FslBase"]) == 2
        assert len(result["FslGraphics"]) == 1

    def test_multiple_subdirectories(self, temp_dir: Any) -> None:
        """Test clustering with multiple subdirectories."""
        headers = [str(temp_dir / "lib" / "core" / "a.hpp"), str(temp_dir / "lib" / "util" / "b.hpp"), str(temp_dir / "src" / "main.cpp")]

        result = cluster_headers_by_directory(headers, str(temp_dir))

        assert "lib" in result
        assert "src" in result
        assert len(result["lib"]) == 2
        assert len(result["src"]) == 1

    def test_root_level_files(self, temp_dir: Any) -> None:
        """Test files at project root level."""
        headers = [str(temp_dir / "header.hpp")]

        result = cluster_headers_by_directory(headers, str(temp_dir))

        assert "root" in result
        assert len(result["root"]) == 1

    def test_deep_nesting(self, temp_dir: Any) -> None:
        """Test deeply nested directories."""
        headers = [str(temp_dir / "a" / "b" / "c" / "d" / "file.hpp"), str(temp_dir / "a" / "other" / "file2.hpp")]

        result = cluster_headers_by_directory(headers, str(temp_dir))

        # Should cluster by top-level directory
        assert "a" in result
        assert len(result["a"]) == 2

    def test_empty_list(self, temp_dir: Any) -> None:
        """Test with empty headers list."""
        result = cluster_headers_by_directory([], str(temp_dir))

        assert len(result) == 0

    def test_single_directory(self, temp_dir: Any) -> None:
        """Test all files in same directory."""
        headers = [str(temp_dir / "module" / "a.hpp"), str(temp_dir / "module" / "b.hpp"), str(temp_dir / "module" / "c.hpp")]

        result = cluster_headers_by_directory(headers, str(temp_dir))

        assert len(result) == 1
        assert "module" in result
        assert len(result["module"]) == 3

    def test_relative_path_outside_project(self, temp_dir: Any) -> None:
        """Test headers that don't start with project_root."""
        headers = ["/some/absolute/path/header.hpp", str(temp_dir / "module" / "header2.hpp")]

        result = cluster_headers_by_directory(headers, str(temp_dir))

        # Should handle both relative and non-matching paths
        assert len(result) >= 1

    def test_preservation_of_order(self, temp_dir: Any) -> None:
        """Test that headers are preserved in clusters."""
        headers = [str(temp_dir / "lib" / "a.hpp"), str(temp_dir / "lib" / "b.hpp"), str(temp_dir / "lib" / "c.hpp")]

        result = cluster_headers_by_directory(headers, str(temp_dir))

        assert len(result["lib"]) == 3
        # All original headers should be in the cluster
        for header in headers:
            assert header in result["lib"]


@pytest.fixture
def temp_dir() -> Any:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
