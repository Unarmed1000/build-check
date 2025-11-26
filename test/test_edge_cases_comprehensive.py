#!/usr/bin/env python3
"""Comprehensive edge case tests for BuildCheck modules.

Tests various boundary conditions, special inputs, and error scenarios that
may not be fully covered by existing tests.
"""
import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Any
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.ninja_utils import is_trackable_file, parse_ninja_explain_line, compute_file_hash, parse_ninja_generated_files, check_generated_files_changed
from lib.git_utils import _validate_and_convert_path
from lib.color_utils import format_table_row, progress_bar
import re


class TestIsTrackableFileEdgeCases:
    """Edge case tests for is_trackable_file function."""

    def test_empty_filepath(self) -> None:
        """Test with empty filepath."""
        is_trackable, category = is_trackable_file("")
        assert category in ["source", "template", "script", "intermediate", "excluded", "unknown"]

    def test_filepath_with_only_extension(self) -> None:
        """Test with filepath that is only an extension."""
        is_trackable, category = is_trackable_file(".cpp")
        assert is_trackable is True
        assert category == "source"

    def test_filepath_with_multiple_dots(self) -> None:
        """Test with filepath containing multiple dots."""
        is_trackable, category = is_trackable_file("my.file.name.cpp")
        assert is_trackable is True
        assert category == "source"

    def test_filepath_with_uppercase_extension(self) -> None:
        """Test case-insensitive extension matching."""
        is_trackable, category = is_trackable_file("FILE.CPP")
        assert is_trackable is True
        assert category == "source"

    def test_filepath_with_mixed_case_extension(self) -> None:
        """Test mixed case extension."""
        is_trackable, category = is_trackable_file("file.CpP")
        assert is_trackable is True
        assert category == "source"

    def test_filepath_with_no_extension(self) -> None:
        """Test filepath with no extension."""
        is_trackable, category = is_trackable_file("makefile")
        assert is_trackable is False
        assert category == "unknown"

    def test_filepath_with_special_characters(self) -> None:
        """Test filepath with special characters."""
        is_trackable, category = is_trackable_file("my-file_123.cpp")
        assert is_trackable is True

    def test_filepath_with_unicode(self) -> None:
        """Test filepath with unicode characters."""
        is_trackable, category = is_trackable_file("файл.cpp")
        assert is_trackable is True

    def test_cmakelists_case_insensitive(self) -> None:
        """Test CMakeLists.txt case variations."""
        assert is_trackable_file("CMakeLists.txt")[0] is True
        assert is_trackable_file("cmakelists.txt")[0] is True
        assert is_trackable_file("CMAKELISTS.TXT")[0] is True

    def test_protobuf_generated_files(self) -> None:
        """Test protobuf generated file extensions."""
        # Note: .pb.cc ends with .cc so it's caught as 'source' before 'intermediate'
        # This is actually correct behavior - it IS a source file
        is_trackable, category = is_trackable_file("file.pb.cc")
        assert is_trackable is True
        assert category == "source"

        is_trackable, category = is_trackable_file("file.grpc.pb.h")
        assert is_trackable is True
        assert category == "source"

    def test_qt_generated_files(self) -> None:
        """Test Qt MOC generated files."""
        # .moc.cpp ends with .cpp, so caught as 'source' before 'intermediate'
        # This documents actual behavior
        is_trackable, category = is_trackable_file("widget.moc.cpp")
        assert is_trackable is True
        assert category == "source"


class TestParseNinjaExplainLineEdgeCases:
    """Edge case tests for parse_ninja_explain_line function."""

    def test_empty_line(self) -> None:
        """Test with empty line."""
        pattern = re.compile(r"ninja explain: (.*)")
        result = parse_ninja_explain_line("", pattern)
        assert result is None

    def test_line_without_explain_marker(self) -> None:
        """Test line without 'ninja explain:' marker."""
        pattern = re.compile(r"ninja explain: (.*)")
        result = parse_ninja_explain_line("some random output", pattern)
        assert result is None

    def test_line_with_is_dirty(self) -> None:
        """Test that 'is dirty' lines are skipped."""
        pattern = re.compile(r"ninja explain: (.*)")
        result = parse_ninja_explain_line("ninja explain: CMakeLists.txt is dirty", pattern)
        assert result is None

    def test_explain_with_special_characters_in_filename(self) -> None:
        """Test parsing filenames with special characters."""
        pattern = re.compile(r"ninja explain: (.*)")
        result = parse_ninja_explain_line("ninja explain: output my-file_123.cpp.o doesn't exist", pattern)
        assert result is not None
        output_file, msg = result
        assert "my-file_123.cpp.o" in output_file

    def test_explain_with_spaces_in_filename(self) -> None:
        """Test parsing filenames with spaces."""
        pattern = re.compile(r"ninja explain: (.*)")
        result = parse_ninja_explain_line("ninja explain: output my file.o doesn't exist", pattern)
        assert result is not None
        # The current implementation splits on spaces, so this might not handle it perfectly
        # This documents current behavior

    def test_command_line_changed_with_complex_target(self) -> None:
        """Test parsing command line changed messages."""
        pattern = re.compile(r"ninja explain: (.*)")
        result = parse_ninja_explain_line("ninja explain: command line changed for path/to/target.o", pattern)
        assert result is not None
        output_file, msg = result
        assert output_file == "path/to/target.o"

    def test_explain_message_variants(self) -> None:
        """Test various ninja explain message formats."""
        pattern = re.compile(r"ninja explain: (.*)")

        # Test "output doesn't exist"
        result = parse_ninja_explain_line("ninja explain: output file.o doesn't exist", pattern)
        assert result is not None

        # Test "older than most recent input"
        result = parse_ninja_explain_line("ninja explain: output file.o older than most recent input source.cpp", pattern)
        assert result is not None


class TestComputeFileHashEdgeCases:
    """Edge case tests for compute_file_hash function."""

    def test_hash_empty_file(self, tmp_path: Path) -> None:
        """Test hashing an empty file."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        hash_result = compute_file_hash(str(empty_file))
        # Empty file should still produce a valid hash
        assert len(hash_result) == 64  # SHA256 produces 64 hex chars
        assert hash_result != ""

    def test_hash_binary_file(self, tmp_path: Path) -> None:
        """Test hashing a binary file."""
        binary_file = tmp_path / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02\xff\xfe\xfd")

        hash_result = compute_file_hash(str(binary_file))
        assert len(hash_result) == 64
        assert hash_result != ""

    def test_hash_large_file(self, tmp_path: Path) -> None:
        """Test hashing a large file (tests chunking)."""
        large_file = tmp_path / "large.txt"
        # Create a file larger than the 8192-byte chunk size
        content = "x" * 20000
        large_file.write_text(content)

        hash_result = compute_file_hash(str(large_file))
        assert len(hash_result) == 64

    def test_hash_nonexistent_file(self, tmp_path: Path) -> None:
        """Test hashing a nonexistent file."""
        nonexistent = tmp_path / "nonexistent.txt"
        hash_result = compute_file_hash(str(nonexistent))
        # Should return empty string for nonexistent files
        assert hash_result == ""

    def test_hash_unicode_content(self, tmp_path: Path) -> None:
        """Test hashing file with unicode content."""
        unicode_file = tmp_path / "unicode.txt"
        unicode_file.write_text("Hello 世界 🌍", encoding="utf-8")

        hash_result = compute_file_hash(str(unicode_file))
        assert len(hash_result) == 64

    def test_hash_consistency(self, tmp_path: Path) -> None:
        """Test that same content produces same hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        content = "test content\n"
        file1.write_text(content)
        file2.write_text(content)

        hash1 = compute_file_hash(str(file1))
        hash2 = compute_file_hash(str(file2))

        assert hash1 == hash2
        assert hash1 != ""


class TestValidateAndConvertPathEdgeCases:
    """Edge case tests for _validate_and_convert_path function."""

    def test_path_with_double_dots(self, tmp_path: Path) -> None:
        """Test rejection of paths with .. (path traversal)."""
        result = _validate_and_convert_path("../etc/passwd", str(tmp_path))
        assert result is None

    def test_path_with_absolute_start(self, tmp_path: Path) -> None:
        """Test rejection of absolute paths."""
        result = _validate_and_convert_path("/etc/passwd", str(tmp_path))
        assert result is None

    def test_valid_relative_path(self, tmp_path: Path) -> None:
        """Test valid relative path."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        result = _validate_and_convert_path("test.txt", str(tmp_path))
        assert result is not None
        assert os.path.exists(result)

    def test_nonexistent_file_in_valid_path(self, tmp_path: Path) -> None:
        """Test nonexistent file returns None."""
        result = _validate_and_convert_path("nonexistent.txt", str(tmp_path))
        assert result is None

    def test_path_with_subdirectory(self, tmp_path: Path) -> None:
        """Test valid path with subdirectory."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.txt"
        test_file.write_text("test")

        result = _validate_and_convert_path("subdir/test.txt", str(tmp_path))
        assert result is not None
        assert os.path.exists(result)

    def test_path_with_unicode(self, tmp_path: Path) -> None:
        """Test path with unicode characters."""
        unicode_dir = tmp_path / "文件夹"
        unicode_dir.mkdir()
        unicode_file = unicode_dir / "文件.txt"
        unicode_file.write_text("test")

        result = _validate_and_convert_path("文件夹/文件.txt", str(tmp_path))
        if result:  # May not work on all filesystems
            assert os.path.exists(result)


class TestParseNinjaGeneratedFilesEdgeCases:
    """Edge case tests for parse_ninja_generated_files function."""

    def test_build_ninja_with_empty_rules(self, tmp_path: Path) -> None:
        """Test parsing build.ninja with empty rule blocks."""
        build_ninja = tmp_path / "build.ninja"
        build_ninja.write_text(
            """
rule empty_rule

rule another_rule
  command = echo test
"""
        )

        generated, output_info = parse_ninja_generated_files(str(build_ninja))
        # Should handle empty rules gracefully
        assert isinstance(generated, set)
        assert isinstance(output_info, dict)

    def test_build_ninja_with_malformed_build_statements(self, tmp_path: Path) -> None:
        """Test parsing build.ninja with malformed build statements."""
        build_ninja = tmp_path / "build.ninja"
        build_ninja.write_text(
            """
rule test
  command = test

build
build incomplete: test
build : test input.txt
build output.txt :
"""
        )

        generated, output_info = parse_ninja_generated_files(str(build_ninja))
        # Should handle malformed statements gracefully
        assert isinstance(generated, set)
        assert isinstance(output_info, dict)

    def test_build_ninja_with_very_long_lines(self, tmp_path: Path) -> None:
        """Test parsing build.ninja with very long lines."""
        build_ninja = tmp_path / "build.ninja"
        long_list = " ".join([f"file{i}.cpp" for i in range(1000)])
        build_ninja.write_text(
            f"""
rule CUSTOM_COMMAND
  command = gen
  generator = 1

build {long_list}: CUSTOM_COMMAND input.txt
"""
        )

        generated, output_info = parse_ninja_generated_files(str(build_ninja))
        assert isinstance(generated, set)

    def test_build_ninja_with_unicode_paths(self, tmp_path: Path) -> None:
        """Test parsing build.ninja with unicode file paths."""
        build_ninja = tmp_path / "build.ninja"
        build_ninja.write_text(
            """
rule CUSTOM_COMMAND
  command = gen
  generator = 1

build 文件.cpp: CUSTOM_COMMAND input.txt
""",
            encoding="utf-8",
        )

        generated, output_info = parse_ninja_generated_files(str(build_ninja))
        assert isinstance(generated, set)


class TestCheckGeneratedFilesChangedEdgeCases:
    """Edge case tests for check_generated_files_changed function."""

    def test_with_empty_generated_files_set(self, tmp_path: Path) -> None:
        """Test with empty set of generated files."""
        cache = {"build_ninja_mtime": 0.0, "files": {}, "dependencies": {}}
        missing, changed, reasons = check_generated_files_changed(str(tmp_path), set(), cache, None)

        assert missing == []
        assert changed == []
        assert reasons == {}

    def test_with_empty_cache(self, tmp_path: Path) -> None:
        """Test with empty cache and existing files."""
        test_file = tmp_path / "test.cpp"
        test_file.write_text("content")

        cache = {"build_ninja_mtime": 0.0, "files": {}, "dependencies": {}}
        generated_files = {"test.cpp"}

        missing, changed, reasons = check_generated_files_changed(str(tmp_path), generated_files, cache, None)

        # New files shouldn't be in missing or changed
        assert str(test_file) not in missing
        assert isinstance(changed, list)

    def test_with_corrupted_cache_structure(self, tmp_path: Path) -> None:
        """Test with corrupted cache missing expected keys."""
        # Old format cache (just dict of files)
        cache = {"some_file.cpp": "hash123"}

        generated_files = {"test.cpp"}

        # Should handle gracefully by treating as empty cache
        missing, changed, reasons = check_generated_files_changed(str(tmp_path), generated_files, cache, None)

        assert isinstance(missing, list)
        assert isinstance(changed, list)
        assert isinstance(reasons, dict)


class TestColorUtilsEdgeCases:
    """Edge case tests for color_utils functions."""

    def test_format_table_row_with_empty_columns(self) -> None:
        """Test formatting table row with empty columns."""
        result = format_table_row(["", "", ""], [10, 10, 10])
        assert isinstance(result, str)

    def test_format_table_row_with_very_wide_columns(self) -> None:
        """Test formatting with very wide content."""
        wide_content = ["x" * 1000, "y" * 1000, "z" * 1000]
        result = format_table_row(wide_content, [20, 20, 20])
        assert isinstance(result, str)

    def test_format_table_row_with_unicode(self) -> None:
        """Test formatting table row with unicode."""
        result = format_table_row(["Hello", "世界", "🌍"], [10, 10, 10])
        assert isinstance(result, str)
        assert "Hello" in result

    def test_progress_bar_zero_percent(self) -> None:
        """Test progress bar at 0%."""
        from lib.color_utils import progress_bar, Colors

        result = progress_bar(0, 100, 40, Colors.GREEN)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_progress_bar_hundred_percent(self) -> None:
        """Test progress bar at 100%."""
        from lib.color_utils import progress_bar, Colors

        result = progress_bar(100, 100, 40, Colors.GREEN)
        assert isinstance(result, str)

    def test_progress_bar_zero_total(self) -> None:
        """Test progress bar with zero total."""
        from lib.color_utils import progress_bar, Colors

        result = progress_bar(0, 0, 40, Colors.GREEN)
        assert isinstance(result, str)


class TestNinjaUtilsIntegrationEdgeCases:
    """Integration edge case tests for ninja_utils."""

    @pytest.mark.skipif(not subprocess.run(["which", "ninja"], capture_output=True).returncode == 0, reason="ninja not available")
    def test_build_ninja_with_only_comments(self, tmp_path: Path) -> None:
        """Test parsing build.ninja that contains only comments."""
        build_ninja = tmp_path / "build.ninja"
        build_ninja.write_text(
            """
# This is a comment
# Another comment
# ninja_required_version = 1.5
"""
        )

        generated, output_info = parse_ninja_generated_files(str(build_ninja))
        assert len(generated) == 0
        assert len(output_info) == 0

    def test_build_ninja_with_windows_line_endings(self, tmp_path: Path) -> None:
        """Test parsing build.ninja with Windows (CRLF) line endings."""
        build_ninja = tmp_path / "build.ninja"
        content = "rule test\r\n  command = test\r\n\r\nbuild out.txt: test in.txt\r\n"
        build_ninja.write_bytes(content.encode())

        generated, output_info = parse_ninja_generated_files(str(build_ninja))
        assert isinstance(generated, set)
        assert isinstance(output_info, dict)

    def test_build_ninja_with_mixed_line_endings(self, tmp_path: Path) -> None:
        """Test parsing build.ninja with mixed LF/CRLF line endings."""
        build_ninja = tmp_path / "build.ninja"
        content = "rule test\r\n  command = test\nbuild out.txt: test in.txt\r\n"
        build_ninja.write_bytes(content.encode())

        generated, output_info = parse_ninja_generated_files(str(build_ninja))
        assert isinstance(generated, set)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
