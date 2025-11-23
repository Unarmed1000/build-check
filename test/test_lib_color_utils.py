#!/usr/bin/env python3
"""Tests for lib/color_utils.py"""

import pytest
from typing import Any, Dict, List, Tuple, Generator
import sys
import io

from lib.color_utils import (
    Colors,
    colored,
    print_colored,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_highlight,
    is_color_supported,
    should_use_color,
    get_severity_color,
    print_severity,
    format_table_row,
    progress_bar,
)


class TestColored:
    """Tests for colored function."""

    def test_basic_coloring(self) -> None:
        """Test basic color application."""
        result = colored("test", Colors.RED)
        assert "test" in result

    def test_with_style(self) -> None:
        """Test color with style."""
        result = colored("test", Colors.GREEN, Colors.BRIGHT)
        assert "test" in result

    def test_empty_string(self) -> None:
        """Test with empty string."""
        result = colored("", Colors.BLUE)
        assert result is not None

    def test_no_color(self) -> None:
        """Test without color codes."""
        result = colored("test", "", "")
        assert "test" in result


class TestPrintFunctions:
    """Tests for print_* convenience functions."""

    def test_print_success(self) -> None:
        """Test print_success function."""
        output = io.StringIO()
        print_success("Success message", file=output)
        result = output.getvalue()
        assert "Success message" in result

    def test_print_error(self) -> None:
        """Test print_error function."""
        output = io.StringIO()
        print_error("Error message", file=output)
        result = output.getvalue()
        assert "Error message" in result

    def test_print_warning(self) -> None:
        """Test print_warning function."""
        output = io.StringIO()
        print_warning("Warning message", file=output)
        result = output.getvalue()
        assert "Warning message" in result

    def test_print_info(self) -> None:
        """Test print_info function."""
        output = io.StringIO()
        print_info("Info message", file=output)
        result = output.getvalue()
        assert "Info message" in result

    def test_print_highlight(self) -> None:
        """Test print_highlight function."""
        output = io.StringIO()
        print_highlight("Highlighted", file=output)
        result = output.getvalue()
        assert "Highlighted" in result


class TestColorSupport:
    """Tests for color support detection."""

    def test_is_color_supported(self) -> None:
        """Test color support detection."""
        result = is_color_supported()
        assert isinstance(result, bool)

    def test_should_use_color_default(self) -> None:
        """Test should_use_color with defaults."""
        result = should_use_color()
        assert isinstance(result, bool)

    def test_should_use_color_force(self) -> None:
        """Test should_use_color with force_color=True."""
        result = should_use_color(force_color=True)
        assert result is True

    def test_should_use_color_no_color(self) -> None:
        """Test should_use_color with no_color=True."""
        result = should_use_color(no_color=True)
        assert result is False

    def test_should_use_color_both_flags(self) -> None:
        """Test should_use_color with conflicting flags."""
        result = should_use_color(force_color=True, no_color=True)
        # no_color should take precedence
        assert result is False


class TestSeverity:
    """Tests for severity-related functions."""

    def test_get_severity_color_high(self) -> None:
        """Test get_severity_color for high severity."""
        color, style = get_severity_color("high")
        assert color is not None
        assert style is not None

    def test_get_severity_color_medium(self) -> None:
        """Test get_severity_color for medium severity."""
        color, style = get_severity_color("medium")
        assert color is not None

    def test_get_severity_color_low(self) -> None:
        """Test get_severity_color for low severity."""
        color, style = get_severity_color("low")
        assert color is not None

    def test_get_severity_color_unknown(self) -> None:
        """Test get_severity_color for unknown severity."""
        color, style = get_severity_color("unknown")
        assert color is not None

    def test_print_severity(self) -> None:
        """Test print_severity function."""
        output = io.StringIO()
        print_severity("Test message", "high", file=output)
        result = output.getvalue()
        assert "Test message" in result


class TestTableFormatting:
    """Tests for table formatting functions."""

    def test_format_table_row_basic(self) -> None:
        """Test basic table row formatting."""
        columns = ["Col1", "Col2", "Col3"]
        widths = [10, 15, 20]

        result = format_table_row(columns, widths)

        assert "Col1" in result
        assert "Col2" in result
        assert "Col3" in result

    def test_format_table_row_with_colors(self) -> None:
        """Test table row with colors."""
        columns = ["A", "B", "C"]
        widths = [5, 5, 5]
        colors = [Colors.RED, Colors.GREEN, Colors.BLUE]

        result = format_table_row(columns, widths, colors)

        assert "A" in result
        assert "B" in result
        assert "C" in result

    def test_format_table_row_mismatched_lengths(self) -> None:
        """Test table row with mismatched column/width counts."""
        columns = ["A", "B"]
        widths = [5, 5, 5]

        result = format_table_row(columns, widths)

        # Should handle gracefully
        assert "A" in result

    def test_format_table_row_empty(self) -> None:
        """Test empty table row."""
        result = format_table_row([], [])

        assert isinstance(result, str)

    def test_format_table_row_truncation(self) -> None:
        """Test column truncation for long text."""
        columns = ["VeryLongColumnName"]
        widths = [5]

        result = format_table_row(columns, widths)

        # Should be truncated or handled appropriately
        assert isinstance(result, str)


class TestProgressBar:
    """Tests for progress_bar function."""

    def test_progress_bar_zero_percent(self) -> None:
        """Test progress bar at 0%."""
        result = progress_bar(0, 100)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_progress_bar_fifty_percent(self) -> None:
        """Test progress bar at 50%."""
        result = progress_bar(50, 100)

        assert isinstance(result, str)
        assert "50" in result or "%" in result

    def test_progress_bar_complete(self) -> None:
        """Test progress bar at 100%."""
        result = progress_bar(100, 100)

        assert isinstance(result, str)
        assert "100" in result or "%" in result

    def test_progress_bar_custom_width(self) -> None:
        """Test progress bar with custom width."""
        result = progress_bar(25, 100, width=20)

        assert isinstance(result, str)

    def test_progress_bar_basic_params(self) -> None:
        """Test progress bar with basic parameters."""
        result = progress_bar(75, 100, width=30)

        assert isinstance(result, str)

    def test_progress_bar_different_width(self) -> None:
        """Test progress bar with different width."""
        result = progress_bar(50, 100, width=60)

        assert isinstance(result, str)

    def test_progress_bar_zero_total(self) -> None:
        """Test progress bar with zero total."""
        result = progress_bar(0, 0)

        # Should handle edge case gracefully
        assert isinstance(result, str)

    def test_progress_bar_exceeds_total(self) -> None:
        """Test progress bar when current exceeds total."""
        result = progress_bar(150, 100)

        # Should handle gracefully (clamp to 100% or handle appropriately)
        assert isinstance(result, str)


class TestColorsClass:
    """Tests for Colors class constants."""

    def test_colors_defined(self) -> None:
        """Test that color constants are defined."""
        assert hasattr(Colors, "RED")
        assert hasattr(Colors, "GREEN")
        assert hasattr(Colors, "YELLOW")
        assert hasattr(Colors, "BLUE")
        assert hasattr(Colors, "RESET")

    def test_styles_defined(self) -> None:
        """Test that style constants are defined."""
        assert hasattr(Colors, "DIM")
        assert hasattr(Colors, "BRIGHT")

    def test_color_values_are_strings(self) -> None:
        """Test that color values are strings."""
        assert isinstance(Colors.RED, str)
        assert isinstance(Colors.GREEN, str)
        assert isinstance(Colors.RESET, str)
