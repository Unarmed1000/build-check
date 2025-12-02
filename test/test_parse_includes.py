#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for parse_includes_from_content() function.

Tests the include directive parsing logic used by reconstruct_head_graph()
to extract dependencies from historical file content.
"""

import sys
from pathlib import Path

import pytest
from typing import Any, Dict, Set

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.git_utils import parse_includes_from_content


class TestParseIncludesBasic:
    """Test basic include parsing functionality."""

    def test_parse_quoted_includes(self) -> None:
        """Test parsing of quoted includes (project headers)."""
        content = """
#include "my_header.h"
#include "subfolder/other_header.hpp"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["my_header.h", "subfolder/other_header.hpp"]

    def test_parse_angled_includes_when_not_skipped(self) -> None:
        """Test parsing of angled includes when skip_system_headers=False."""
        content = """
#include <iostream>
#include <vector>
#include <string>
        """
        result = parse_includes_from_content(content, skip_system_headers=False)
        assert result == ["iostream", "vector", "string"]

    def test_skip_angled_includes_by_default(self) -> None:
        """Test that angled includes are skipped by default."""
        content = """
#include <iostream>
#include "my_header.h"
#include <vector>
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["my_header.h"]

    def test_mixed_includes(self) -> None:
        """Test parsing mixed quoted and angled includes."""
        content = """
#include <iostream>
#include "my_header.h"
#include <vector>
#include "another_header.hpp"
        """
        # With skip_system_headers=True
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["my_header.h", "another_header.hpp"]

        # With skip_system_headers=False
        result = parse_includes_from_content(content, skip_system_headers=False)
        assert result == ["iostream", "my_header.h", "vector", "another_header.hpp"]

    def test_empty_content(self) -> None:
        """Test parsing empty content."""
        result = parse_includes_from_content("", skip_system_headers=True)
        assert result == []

    def test_no_includes(self) -> None:
        """Test content with no include directives."""
        content = """
// This is a comment
int main() {
    return 0;
}
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == []


class TestParseIncludesWhitespace:
    """Test include parsing with various whitespace patterns."""

    def test_spaces_before_hash(self) -> None:
        """Test includes with leading spaces before #."""
        content = """
  #include "header1.h"
    #include "header2.h"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["header1.h", "header2.h"]

    def test_spaces_after_hash(self) -> None:
        """Test includes with spaces after #."""
        content = """
#  include "header1.h"
#    include "header2.h"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["header1.h", "header2.h"]

    def test_spaces_after_include(self) -> None:
        """Test includes with spaces after include keyword."""
        content = """
#include  "header1.h"
#include    "header2.h"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["header1.h", "header2.h"]

    def test_tabs_and_mixed_whitespace(self) -> None:
        """Test includes with tabs and mixed whitespace."""
        content = """
\t#include "header1.h"
\t#\tinclude\t"header2.h"
  \t  #  \t  include  \t  "header3.h"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["header1.h", "header2.h", "header3.h"]


class TestParseIncludesComments:
    """Test include parsing with comments."""

    def test_cpp_comment_after_include(self) -> None:
        """Test includes with C++ comments after the directive."""
        content = """
#include "header1.h" // Main header
#include "header2.h" // Secondary header
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["header1.h", "header2.h"]

    def test_cpp_comment_before_include(self) -> None:
        """Test that commented-out includes are ignored."""
        content = """
// #include "commented_out.h"
#include "real_header.h"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["real_header.h"]

    def test_cpp_comment_with_spaces(self) -> None:
        """Test includes with comments containing spaces."""
        content = """
#include "header.h" // This is a longer comment with spaces
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["header.h"]

    def test_partial_comment_in_path(self) -> None:
        """Test that // in the include path itself is handled correctly."""
        # Note: This is an edge case - file paths shouldn't contain //
        # but we test the current behavior
        content = """#include "header.h" // comment"""
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["header.h"]


class TestParseIncludesEdgeCases:
    """Test include parsing edge cases and malformed input."""

    def test_include_with_path_separators(self) -> None:
        """Test includes with directory paths."""
        content = """
#include "folder/subfolder/header.h"
#include "deep/path/to/file.hpp"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["folder/subfolder/header.h", "deep/path/to/file.hpp"]

    def test_include_with_dots_in_path(self) -> None:
        """Test includes with relative path components."""
        content = """
#include "../parent/header.h"
#include "../../grandparent/header.hpp"
#include "./current/header.h"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["../parent/header.h", "../../grandparent/header.hpp", "./current/header.h"]

    def test_different_header_extensions(self) -> None:
        """Test includes with various header file extensions."""
        content = """
#include "header.h"
#include "header.hpp"
#include "header.hxx"
#include "header.hh"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["header.h", "header.hpp", "header.hxx", "header.hh"]

    def test_malformed_include_no_closing_quote(self) -> None:
        """Test that malformed includes (no closing quote) are ignored."""
        content = """
#include "header.h
#include "valid_header.h"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        # Only the valid one should be parsed
        assert result == ["valid_header.h"]

    def test_malformed_include_no_opening_quote(self) -> None:
        """Test that malformed includes (no opening quote) are ignored."""
        content = """
#include header.h"
#include "valid_header.h"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["valid_header.h"]

    def test_empty_include_path(self) -> None:
        """Test that empty include paths are ignored (filtered out)."""
        content = """
#include ""
#include "valid_header.h"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        # Empty strings are filtered out by the regex
        assert result == ["valid_header.h"]

    def test_include_without_space_after_directive(self) -> None:
        """Test include directive without space (invalid C++)."""
        content = """
#include"header.h"
#include "valid_header.h"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        # The regex requires space after include, so first is ignored
        assert result == ["valid_header.h"]

    def test_multiline_content_with_code(self) -> None:
        """Test parsing includes from realistic file content."""
        content = """
// File: example.cpp
#include <iostream>
#include "my_class.h"
#include "utils/helper.hpp"

namespace MyNamespace {
    // Some code
    void function() {
        // #include "this_is_a_comment.h"
        std::cout << "Hello" << std::endl;
    }
}

#include "late_include.h"  // This is valid but unusual
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["my_class.h", "utils/helper.hpp", "late_include.h"]

    def test_unicode_content(self) -> None:
        """Test parsing includes from content with unicode characters."""
        content = """
// UTF-8 comment: 你好世界
#include "header.h"
// More unicode: こんにちは
#include "other.hpp"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["header.h", "other.hpp"]

    def test_windows_path_separators(self) -> None:
        """Test includes with Windows-style path separators."""
        content = r"""
#include "folder\subfolder\header.h"
#include "path\to\file.hpp"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == [r"folder\subfolder\header.h", r"path\to\file.hpp"]


class TestParseIncludesDocumentation:
    """Test examples from the function's docstring."""

    def test_docstring_example_skip_system(self) -> None:
        """Test the example from the docstring with skip_system_headers=True."""
        content = """
#include <iostream>
#include "my_header.h"
#include <vector>
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["my_header.h"]

    def test_docstring_example_include_system(self) -> None:
        """Test the example from the docstring with skip_system_headers=False."""
        content = """
#include <iostream>
#include "my_header.h"
#include <vector>
        """
        result = parse_includes_from_content(content, skip_system_headers=False)
        assert result == ["iostream", "my_header.h", "vector"]


class TestParseIncludesOrderPreservation:
    """Test that include order is preserved."""

    def test_order_is_preserved(self) -> None:
        """Test that includes are returned in the order they appear."""
        content = """
#include "z_header.h"
#include "a_header.h"
#include "m_header.h"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["z_header.h", "a_header.h", "m_header.h"]

    def test_duplicate_includes_preserved(self) -> None:
        """Test that duplicate includes are preserved (not deduplicated)."""
        content = """
#include "header.h"
#include "other.h"
#include "header.h"
        """
        result = parse_includes_from_content(content, skip_system_headers=True)
        assert result == ["header.h", "other.h", "header.h"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
