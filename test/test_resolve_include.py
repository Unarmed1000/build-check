#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for _resolve_include_to_header() function.

Tests the include path resolution logic used by reconstruct_head_graph()
to match #include directives to actual header file paths.
"""

import sys
from pathlib import Path

import pytest
from typing import Any, Dict, Set

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.git_utils import _resolve_include_to_header


class TestResolveIncludeToHeaderBasic:
    """Test basic include resolution functionality."""

    def test_exact_filename_match(self) -> None:
        """Test resolving with exact filename match."""
        headers = {"/project/include/header.h", "/project/include/other.h"}
        result = _resolve_include_to_header("header.h", headers)
        assert result == "/project/include/header.h"

    def test_path_suffix_match(self) -> None:
        """Test resolving with path suffix match."""
        headers = {"/project/include/utils/helper.h", "/project/include/core.h"}
        result = _resolve_include_to_header("utils/helper.h", headers)
        assert result == "/project/include/utils/helper.h"

    def test_deep_path_suffix_match(self) -> None:
        """Test resolving with deep nested path suffix."""
        headers = {"/project/include/deep/nested/path/header.hpp"}
        result = _resolve_include_to_header("deep/nested/path/header.hpp", headers)
        assert result == "/project/include/deep/nested/path/header.hpp"

    def test_no_match_returns_none(self) -> None:
        """Test that unresolved includes return None."""
        headers = {"/project/include/header.h"}
        result = _resolve_include_to_header("nonexistent.h", headers)
        assert result is None

    def test_empty_headers_set(self) -> None:
        """Test resolution with empty headers set."""
        result = _resolve_include_to_header("header.h", set())
        assert result is None


class TestResolveIncludeToHeaderBasenameMatching:
    """Test basename fallback matching."""

    def test_basename_fallback_when_no_path_match(self) -> None:
        """Test that basename matching works when path doesn't match."""
        headers = {"/project/include/actual/path/header.h"}
        # Request with wrong path, but correct filename
        result = _resolve_include_to_header("wrong/path/header.h", headers)
        assert result == "/project/include/actual/path/header.h"

    def test_basename_match_single_file(self) -> None:
        """Test basename matching with single file."""
        headers = {"/project/include/subdir/file.hpp"}
        result = _resolve_include_to_header("file.hpp", headers)
        assert result == "/project/include/subdir/file.hpp"

    def test_prefers_suffix_over_basename(self) -> None:
        """Test that suffix match is preferred over basename match."""
        headers = {
            "/project/include/a/header.h",  # Basename matches
            "/project/include/b/header.h",  # Basename matches
            "/project/include/utils/header.h",  # Both basename and suffix match
        }
        # Should prefer the one with matching suffix
        result = _resolve_include_to_header("utils/header.h", headers)
        assert result == "/project/include/utils/header.h"


class TestResolveIncludeToHeaderAmbiguity:
    """Test resolution with multiple potential matches."""

    def test_multiple_basename_matches_returns_first(self) -> None:
        """Test that first match is returned when multiple basenames match."""
        # Note: Set iteration order is not guaranteed in Python < 3.7
        # but this tests the current behavior
        headers = {"/project/include/a/header.h", "/project/include/b/header.h", "/project/include/c/header.h"}
        result = _resolve_include_to_header("wrong/path/header.h", headers)
        # Should match one of them (implementation returns first found)
        assert result in headers
        assert result.endswith("header.h")

    def test_suffix_match_unique_when_multiple_basenames(self) -> None:
        """Test that correct suffix match is found among multiple same-basename files."""
        headers = {"/project/include/utils/helper.h", "/project/include/core/helper.h", "/project/include/test/helper.h"}
        result = _resolve_include_to_header("core/helper.h", headers)
        assert result == "/project/include/core/helper.h"


class TestResolveIncludeToHeaderPathSeparators:
    """Test resolution with different path separator scenarios."""

    def test_unix_path_separator(self) -> None:
        """Test resolution with Unix-style path separators."""
        headers = {"/project/include/sub/dir/header.h"}
        result = _resolve_include_to_header("sub/dir/header.h", headers)
        assert result == "/project/include/sub/dir/header.h"

    def test_windows_path_separator(self) -> None:
        """Test resolution with Windows-style path separators in header."""
        # In practice, git and clang typically use forward slashes
        # but test the behavior with backslashes
        headers = {r"/project/include/sub\dir\header.h"}
        result = _resolve_include_to_header(r"sub\dir\header.h", headers)
        assert result == r"/project/include/sub\dir\header.h"

    def test_mixed_path_separators(self) -> None:
        """Test that mixed separators don't match on Linux (backslash is literal character)."""
        headers = {"/project/include/sub/dir/header.h"}
        # Include with backslash won't match Unix path via suffix
        # On Linux, os.path.basename(r"sub\dir\header.h") == r"sub\dir\header.h" (whole string)
        # so basename matching also fails
        result = _resolve_include_to_header(r"sub\dir\header.h", headers)
        # No match because backslash is treated as literal character on Linux
        assert result is None


class TestResolveIncludeToHeaderEdgeCases:
    """Test edge cases and unusual scenarios."""

    def test_relative_path_with_dots(self) -> None:
        """Test that ../ in include path works (though unusual)."""
        headers = {"/project/include/utils/helper.h"}
        # Include with .. won't match suffix but will match basename
        result = _resolve_include_to_header("../utils/helper.h", headers)
        assert result == "/project/include/utils/helper.h"

    def test_absolute_path_in_include(self) -> None:
        """Test that absolute path in include (unusual) won't match."""
        headers = {"/project/include/header.h"}
        # Absolute path won't match unless header also starts with /
        result = _resolve_include_to_header("/project/include/header.h", headers)
        assert result == "/project/include/header.h"

    def test_empty_include_path(self) -> None:
        """Test empty include path returns None."""
        headers = {"/project/include/header.h"}
        result = _resolve_include_to_header("", headers)
        # Empty include paths should be rejected
        assert result is None

    def test_include_path_just_slash(self) -> None:
        """Test include path with just slash."""
        headers = {"/project/include/header.h"}
        result = _resolve_include_to_header("/", headers)
        assert result is None

    def test_different_file_extensions(self) -> None:
        """Test resolution works with different extensions."""
        headers = {"/project/include/header.h", "/project/include/header.hpp", "/project/include/header.hxx"}
        assert _resolve_include_to_header("header.h", headers) == "/project/include/header.h"
        assert _resolve_include_to_header("header.hpp", headers) == "/project/include/header.hpp"
        assert _resolve_include_to_header("header.hxx", headers) == "/project/include/header.hxx"

    def test_header_without_extension(self) -> None:
        """Test resolution of headers without extensions (C++ stdlib style)."""
        headers = {"/usr/include/c++/13/iostream", "/usr/include/c++/13/vector"}
        result = _resolve_include_to_header("iostream", headers)
        assert result == "/usr/include/c++/13/iostream"


class TestResolveIncludeToHeaderRealistic:
    """Test realistic project scenarios."""

    def test_typical_project_structure(self) -> None:
        """Test resolution in typical project with src/include separation."""
        headers = {
            "/project/include/MyClass.h",
            "/project/include/utils/StringUtils.h",
            "/project/include/utils/FileUtils.h",
            "/project/include/core/Engine.h",
            "/project/include/core/Config.h",
        }

        # Test various includes
        assert _resolve_include_to_header("MyClass.h", headers) == "/project/include/MyClass.h"
        assert _resolve_include_to_header("utils/StringUtils.h", headers) == "/project/include/utils/StringUtils.h"
        assert _resolve_include_to_header("core/Engine.h", headers) == "/project/include/core/Engine.h"

    def test_module_based_project(self) -> None:
        """Test resolution in module-based project structure."""
        headers = {
            "/project/modules/ModuleA/include/ComponentA.hpp",
            "/project/modules/ModuleB/include/ComponentB.hpp",
            "/project/modules/Common/include/Base.hpp",
        }

        assert _resolve_include_to_header("ModuleA/include/ComponentA.hpp", headers) == "/project/modules/ModuleA/include/ComponentA.hpp"
        assert _resolve_include_to_header("ComponentA.hpp", headers) == "/project/modules/ModuleA/include/ComponentA.hpp"

    def test_header_only_library(self) -> None:
        """Test resolution with header-only library structure."""
        headers = {"/project/include/lib/algorithm.hpp", "/project/include/lib/container.hpp", "/project/include/lib/detail/impl.hpp"}

        assert _resolve_include_to_header("lib/algorithm.hpp", headers) == "/project/include/lib/algorithm.hpp"
        assert _resolve_include_to_header("lib/detail/impl.hpp", headers) == "/project/include/lib/detail/impl.hpp"


class TestResolveIncludeToHeaderDocumentation:
    """Test examples from the function's docstring."""

    def test_docstring_example_suffix_match(self) -> None:
        """Test the suffix match example from docstring."""
        headers = {"/project/include/utils/helper.h", "/project/include/core.h"}
        result = _resolve_include_to_header("utils/helper.h", headers)
        assert result == "/project/include/utils/helper.h"

    def test_docstring_example_basename_match(self) -> None:
        """Test the basename match example from docstring."""
        headers = {"/project/include/utils/helper.h", "/project/include/core.h"}
        result = _resolve_include_to_header("core.h", headers)
        assert result == "/project/include/core.h"

    def test_docstring_example_no_match(self) -> None:
        """Test the no match example from docstring."""
        headers = {"/project/include/utils/helper.h", "/project/include/core.h"}
        result = _resolve_include_to_header("nonexistent.h", headers)
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
