#!/usr/bin/env python3
# ****************************************************************************************************************************************************
# * BSD 3-Clause License
# *
# * Copyright (c) 2025, Mana Battery
# * All rights reserved.
# *
# * Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
# *
# * 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
# * 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the
# *    documentation and/or other materials provided with the distribution.
# * 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this
# *    software without specific prior written permission.
# *
# * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# * THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# * PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# * LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
# * EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# ****************************************************************************************************************************************************
"""Tests for lib.ninja_utils module"""
import os
import sys
import subprocess
import re
from pathlib import Path
from typing import Any, Dict, Set, List
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.constants import COMPILE_COMMANDS_JSON
from lib.ninja_utils import (
    normalize_reason,
    extract_rebuild_info,
    get_dependencies,
    check_ninja_available,
    validate_build_directory,
    validate_and_prepare_build_dir,
    check_missing_source_files,
    run_full_ninja_build,
    parse_ninja_generated_files,
    compute_file_hash,
    load_generated_files_cache,
    save_generated_files_cache,
    check_generated_files_changed,
    update_generated_files_cache,
    clean_stale_cache_entries,
    get_relative_build_path,
    parse_ninja_explain_line,
)


class TestNormalizeReason:
    """Test the normalize_reason function."""

    def test_normalize_reason_missing_output(self) -> None:
        """Test normalizing 'output missing' reason."""
        msg = "output main.cpp.o doesn't exist"
        result = normalize_reason(msg)
        assert result == "output missing (initial build)"

    def test_normalize_reason_input_changed(self) -> None:
        """Test normalizing 'input changed' reason."""
        msg = "output utils.cpp.o older than most recent input src/utils.hpp"
        result = normalize_reason(msg)
        assert result == "input source changed"

    def test_normalize_reason_command_line_changed(self) -> None:
        """Test normalizing 'command line changed' reason."""
        msg = "command line changed for utils.cpp.o"
        result = normalize_reason(msg)
        assert result == "command line changed (compile flags/options)"

    def test_normalize_reason_build_ninja_changed(self) -> None:
        """Test normalizing 'build.ninja changed' reason."""
        msg = "build.ninja changed"
        result = normalize_reason(msg)
        assert result == "build.ninja changed (cmake reconfigure)"

    def test_normalize_reason_unknown(self) -> None:
        """Test normalizing unknown reason."""
        msg = "some weird unknown reason"
        result = normalize_reason(msg)
        assert msg in result

    def test_normalize_reason_edge_cases(self) -> None:
        """Test edge cases for normalize_reason."""
        assert "output missing" in normalize_reason("doesn't exist")
        assert "input source changed" in normalize_reason("older than most recent input")
        assert "unknown reason" in normalize_reason("")


class TestExtractRebuildInfo:
    """Test the extract_rebuild_info function."""

    def test_extract_rebuild_info_with_mock_build(self, mock_build_dir: str, monkeypatch: Any) -> None:
        """Test extracting rebuild info from a mock build directory."""
        # Mock subprocess.run to return controlled output
        mock_stderr = """ninja explain: output main.cpp.o doesn't exist
ninja explain: output utils.cpp.o older than most recent input src/utils.hpp
"""

        class MockResult:
            def __init__(self) -> None:
                self.stdout = ""
                self.stderr = mock_stderr
                self.returncode = 0

        def mock_run(*args: Any, **kwargs: Any) -> MockResult:
            return MockResult()

        monkeypatch.setattr(subprocess, "run", mock_run)

        # Test extraction
        rebuild_entries, reasons, root_causes = extract_rebuild_info(mock_build_dir, verbose=False)

        assert len(rebuild_entries) == 2
        assert reasons["output missing (initial build)"] == 1
        assert reasons["input source changed"] == 1
        assert "src/utils.hpp" in root_causes

    def test_extract_rebuild_info_invalid_directory(self) -> None:
        """Test handling of invalid build directory."""
        from lib.constants import BuildDirectoryError

        with pytest.raises(BuildDirectoryError) as exc_info:
            extract_rebuild_info("/nonexistent/directory")
        assert "Cannot change to directory" in str(exc_info.value)

    def test_extract_rebuild_info_ninja_not_found(self, mock_build_dir: str, monkeypatch: Any) -> None:
        """Test handling when ninja is not found."""
        from lib.constants import NinjaError

        def mock_run(*args: Any, **kwargs: Any) -> Any:
            raise FileNotFoundError("ninja not found")

        monkeypatch.setattr(subprocess, "run", mock_run)

        with pytest.raises(NinjaError) as exc_info:
            extract_rebuild_info(mock_build_dir)
        assert "ninja command not found" in str(exc_info.value)

    def test_extract_rebuild_info_verbose_mode(self, mock_build_dir: str, monkeypatch: Any) -> None:
        """Test verbose mode output."""
        mock_stderr = """ninja explain: output main.cpp.o doesn't exist
"""

        class MockResult:
            def __init__(self) -> None:
                self.stdout = ""
                self.stderr = mock_stderr
                self.returncode = 0

        def mock_run(*args: Any, **kwargs: Any) -> MockResult:
            return MockResult()

        monkeypatch.setattr(subprocess, "run", mock_run)

        rebuild_entries, reasons, root_causes = extract_rebuild_info(mock_build_dir, verbose=True)

        assert len(rebuild_entries) == 1


class TestGetDependencies:
    """Test the get_dependencies function."""

    def test_get_dependencies(self, mock_build_dir: str, monkeypatch: Any) -> None:
        """Test getting dependencies for a target."""
        mock_output = """main.cpp.o:
  ../src/main.cpp
  ../src/utils.hpp
  ../src/config.hpp
"""

        class MockResult:
            def __init__(self) -> None:
                self.stdout = mock_output
                self.stderr = ""
                self.returncode = 0

        def mock_run(*args: Any, **kwargs: Any) -> MockResult:
            return MockResult()

        monkeypatch.setattr(subprocess, "run", mock_run)

        deps = get_dependencies(mock_build_dir, "main.cpp.o")

        assert len(deps) == 3
        assert "../src/main.cpp" in deps
        assert "../src/utils.hpp" in deps
        assert "../src/config.hpp" in deps

    def test_get_dependencies_timeout(self, mock_build_dir: str, monkeypatch: Any) -> None:
        """Test handling of timeout when getting dependencies."""

        def mock_run(*args: Any, **kwargs: Any) -> Any:
            raise subprocess.TimeoutExpired("ninja", 30)

        monkeypatch.setattr(subprocess, "run", mock_run)

        deps = get_dependencies(mock_build_dir, "main.cpp.o")
        assert deps == []

    def test_get_dependencies_empty_output(self, mock_build_dir: str, monkeypatch: Any) -> None:
        """Test handling of empty output."""

        class MockResult:
            def __init__(self) -> None:
                self.stdout = ""
                self.stderr = ""
                self.returncode = 0

        def mock_run(*args: Any, **kwargs: Any) -> MockResult:
            return MockResult()

        monkeypatch.setattr(subprocess, "run", mock_run)

        deps = get_dependencies(mock_build_dir, "nonexistent.o")
        assert deps == []

    def test_get_dependencies_error(self, mock_build_dir: str, monkeypatch: Any) -> None:
        """Test handling of ninja error."""

        class MockResult:
            def __init__(self) -> None:
                self.stdout = ""
                self.stderr = "ninja: error: unknown target 'invalid.o'"
                self.returncode = 1

        def mock_run(*args: Any, **kwargs: Any) -> MockResult:
            return MockResult()

        monkeypatch.setattr(subprocess, "run", mock_run)

        deps = get_dependencies(mock_build_dir, "invalid.o")
        assert deps == []


class TestCheckNinjaAvailable:
    """Test the check_ninja_available function."""

    def test_ninja_available(self, monkeypatch: Any) -> None:
        """Test when ninja is available."""

        class MockResult:
            def __init__(self) -> None:
                self.returncode = 0
                self.stdout = b"ninja version 1.10.0"
                self.stderr = b""

        def mock_run(*args: Any, **kwargs: Any) -> MockResult:
            return MockResult()

        monkeypatch.setattr(subprocess, "run", mock_run)

        # Should not raise
        check_ninja_available()

    def test_ninja_not_available(self, monkeypatch: Any) -> None:
        """Test when ninja is not available."""

        def mock_run(*args: Any, **kwargs: Any) -> Any:
            raise FileNotFoundError("ninja not found")

        monkeypatch.setattr(subprocess, "run", mock_run)

        # Should return False when ninja is not available
        result = check_ninja_available()
        assert result is False

    @pytest.mark.unit
    def test_ninja_timeout(self, monkeypatch: Any) -> None:
        """Test when ninja --version times out."""

        def mock_run(*args: Any, **kwargs: Any) -> Any:
            raise subprocess.TimeoutExpired("ninja", 5)

        monkeypatch.setattr(subprocess, "run", mock_run)

        result = check_ninja_available()
        assert result is False

    @pytest.mark.unit
    def test_ninja_called_process_error(self, monkeypatch: Any) -> None:
        """Test when ninja returns non-zero exit code."""

        def mock_run(*args: Any, **kwargs: Any) -> Any:
            raise subprocess.CalledProcessError(1, "ninja")

        monkeypatch.setattr(subprocess, "run", mock_run)

        result = check_ninja_available()
        assert result is False

    @pytest.mark.unit
    def test_ninja_generic_exception(self, monkeypatch: Any) -> None:
        """Test when ninja check raises generic exception."""

        def mock_run(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("Unexpected error")

        monkeypatch.setattr(subprocess, "run", mock_run)

        result = check_ninja_available()
        assert result is False


class TestValidateBuildDirectory:
    """Test the validate_build_directory function."""

    def test_valid_build_directory(self, mock_build_dir: str) -> None:
        """Test validation of a valid build directory."""
        # Should not raise
        validate_build_directory(mock_build_dir)

    def test_nonexistent_directory(self) -> None:
        """Test validation of nonexistent directory."""
        with pytest.raises(ValueError):
            validate_build_directory("/nonexistent/directory")

    def test_directory_without_build_ninja(self, temp_dir: str) -> None:
        """Test validation of directory without build.ninja."""
        with pytest.raises(ValueError):
            validate_build_directory(temp_dir)

    def test_path_traversal_prevention(self, temp_dir: str) -> None:
        """Test that path traversal attempts are blocked."""
        # Create a malicious build directory path
        malicious_path = os.path.join(temp_dir, "..", "..", "etc", "passwd")

        # This should fail validation
        with pytest.raises(ValueError):
            validate_build_directory(malicious_path)

    @pytest.mark.unit
    def test_file_instead_of_directory(self, tmp_path: Path) -> None:
        """Test validation when path is a file, not directory."""
        file_path = tmp_path / "notadir.txt"
        file_path.write_text("content")

        with pytest.raises(ValueError, match="not a directory"):
            validate_build_directory(str(file_path))


class TestValidateAndPrepareBuildDir:
    """Test the validate_and_prepare_build_dir function."""

    def test_valid_build_directory(self, mock_build_dir: str, monkeypatch: Any) -> None:
        """Test validation and preparation of a valid build directory."""
        # Create compile_commands.json
        compile_commands_path = os.path.join(mock_build_dir, COMPILE_COMMANDS_JSON)
        with open(compile_commands_path, "w") as f:
            f.write("[]")

        # Should return normalized paths
        build_dir, compile_commands = validate_and_prepare_build_dir(mock_build_dir, verbose=False)

        assert os.path.isabs(build_dir)
        assert os.path.isabs(compile_commands)
        assert os.path.exists(compile_commands)

    def test_nonexistent_directory(self) -> None:
        """Test with nonexistent directory."""
        with pytest.raises(ValueError, match="Build directory does not exist"):
            validate_and_prepare_build_dir("/nonexistent/directory")

    def test_generates_compile_commands(self, mock_build_dir: str, monkeypatch: Any) -> None:
        """Test that compile_commands.json is generated if missing."""
        compile_commands_path = os.path.join(mock_build_dir, COMPILE_COMMANDS_JSON)

        # Mock subprocess.run to simulate ninja -t compdb
        class MockResult:
            def __init__(self) -> None:
                self.returncode = 0
                self.stdout = '[{"directory": "/tmp", "command": "g++ -c test.cpp", "file": "test.cpp"}]'

        def mock_run(*args: Any, **kwargs: Any) -> MockResult:
            return MockResult()

        monkeypatch.setattr(subprocess, "run", mock_run)

        # Remove compile_commands.json if it exists
        if os.path.exists(compile_commands_path):
            os.remove(compile_commands_path)

        # Should generate compile_commands.json
        build_dir, compile_commands = validate_and_prepare_build_dir(mock_build_dir, verbose=False)

        assert os.path.exists(compile_commands)

    def test_regenerates_outdated_compile_commands(self, mock_build_dir: str, monkeypatch: Any) -> None:
        """Test that compile_commands.json is regenerated if older than build.ninja."""
        import time

        compile_commands_path = os.path.join(mock_build_dir, COMPILE_COMMANDS_JSON)
        build_ninja_path = os.path.join(mock_build_dir, "build.ninja")

        # Create compile_commands.json
        with open(compile_commands_path, "w") as f:
            f.write("[]")

        # Wait a bit and touch build.ninja to make it newer
        time.sleep(0.01)
        Path(build_ninja_path).touch()

        # Mock subprocess.run
        class MockResult:
            def __init__(self) -> None:
                self.returncode = 0
                self.stdout = '[{"directory": "/tmp", "command": "g++ -c test.cpp", "file": "test.cpp"}]'

        def mock_run(*args: Any, **kwargs: Any) -> MockResult:
            return MockResult()

        monkeypatch.setattr(subprocess, "run", mock_run)

        # Should regenerate compile_commands.json
        build_dir, compile_commands = validate_and_prepare_build_dir(mock_build_dir, verbose=False)

        assert os.path.exists(compile_commands)

    def test_path_traversal_protection(self, mock_build_dir: str) -> None:
        """Test protection against symlink-based path traversal."""
        # Create compile_commands.json
        compile_commands_path = os.path.join(mock_build_dir, COMPILE_COMMANDS_JSON)
        with open(compile_commands_path, "w") as f:
            f.write("[]")

        # Create a symlink that points outside the build directory
        symlink_path = os.path.join(mock_build_dir, "evil_link.json")
        try:
            os.symlink("/etc/passwd", symlink_path)

            # This should not cause issues - we're checking compile_commands.json specifically
            build_dir, compile_commands = validate_and_prepare_build_dir(mock_build_dir, verbose=False)

            # The compile_commands should still be within build_dir
            assert compile_commands.startswith(build_dir)
        except OSError:
            # Skip test if symlinks are not supported
            pytest.skip("Symlinks not supported on this system")
        finally:
            if os.path.islink(symlink_path):
                os.unlink(symlink_path)

    def test_ninja_compdb_failure(self, mock_build_dir: str, monkeypatch: Any) -> None:
        """Test handling of ninja -t compdb failure."""
        compile_commands_path = os.path.join(mock_build_dir, COMPILE_COMMANDS_JSON)

        # Remove compile_commands.json if it exists
        if os.path.exists(compile_commands_path):
            os.remove(compile_commands_path)

        # Mock subprocess.run to simulate failure
        def mock_run(*args: Any, **kwargs: Any) -> Any:
            raise subprocess.CalledProcessError(1, "ninja", stderr="error message")

        monkeypatch.setattr(subprocess, "run", mock_run)

        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="Failed to generate compile_commands.json"):
            validate_and_prepare_build_dir(mock_build_dir, verbose=False)

    def test_verbose_mode(self, mock_build_dir: str, monkeypatch: Any, capsys: Any) -> None:
        """Test verbose output mode."""
        compile_commands_path = os.path.join(mock_build_dir, COMPILE_COMMANDS_JSON)

        # Remove compile_commands.json to trigger generation
        if os.path.exists(compile_commands_path):
            os.remove(compile_commands_path)

        # Mock subprocess.run
        class MockResult:
            def __init__(self) -> None:
                self.returncode = 0
                self.stdout = "[]"

        def mock_run(*args: Any, **kwargs: Any) -> MockResult:
            return MockResult()

        monkeypatch.setattr(subprocess, "run", mock_run)

        # Call with verbose=True
        validate_and_prepare_build_dir(mock_build_dir, verbose=True)

        # Check that verbose message was printed
        captured = capsys.readouterr()
        assert "Generating compile_commands.json" in captured.out


class TestCheckMissingSourceFiles:
    """Test the check_missing_source_files function."""

    def test_check_missing_source_files_all_exist(self, tmp_path: Path) -> None:
        """Test when all source files exist."""
        # Create a temporary directory with source files
        src_file1 = tmp_path / "src" / "main.cpp"
        src_file1.parent.mkdir(parents=True)
        src_file1.write_text("int main() {}")

        src_file2 = tmp_path / "src" / "utils.cpp"
        src_file2.write_text("void func() {}")

        # Create compile_commands.json
        compile_commands = tmp_path / COMPILE_COMMANDS_JSON
        compile_commands.write_text(
            f"""[
            {{
                "directory": "{tmp_path}",
                "command": "g++ -c src/main.cpp",
                "file": "src/main.cpp"
            }},
            {{
                "directory": "{tmp_path}",
                "command": "g++ -c src/utils.cpp",
                "file": "src/utils.cpp"
            }}
        ]"""
        )

        missing = check_missing_source_files(str(compile_commands))
        assert missing == []

    def test_check_missing_source_files_some_missing(self, tmp_path: Path) -> None:
        """Test when some source files are missing (autogenerated)."""
        # Create only one source file
        src_file1 = tmp_path / "src" / "main.cpp"
        src_file1.parent.mkdir(parents=True)
        src_file1.write_text("int main() {}")

        # Create compile_commands.json with reference to missing file
        compile_commands = tmp_path / COMPILE_COMMANDS_JSON
        compile_commands.write_text(
            f"""[
            {{
                "directory": "{tmp_path}",
                "command": "g++ -c src/main.cpp",
                "file": "src/main.cpp"
            }},
            {{
                "directory": "{tmp_path}",
                "command": "g++ -c src/generated.cpp",
                "file": "src/generated.cpp"
            }}
        ]"""
        )

        missing = check_missing_source_files(str(compile_commands))
        assert len(missing) == 1
        assert "generated.cpp" in missing[0]

    def test_check_missing_source_files_absolute_paths(self, tmp_path: Path) -> None:
        """Test with absolute paths."""
        src_file = tmp_path / "main.cpp"
        src_file.write_text("int main() {}")

        missing_file = tmp_path / "missing.cpp"

        compile_commands = tmp_path / COMPILE_COMMANDS_JSON
        compile_commands.write_text(
            f"""[
            {{
                "directory": "{tmp_path}",
                "command": "g++ -c {src_file}",
                "file": "{src_file}"
            }},
            {{
                "directory": "{tmp_path}",
                "command": "g++ -c {missing_file}",
                "file": "{missing_file}"
            }}
        ]"""
        )

        missing = check_missing_source_files(str(compile_commands))
        assert len(missing) == 1
        assert str(missing_file) in missing[0]

    def test_check_missing_source_files_invalid_json(self, tmp_path: Path) -> None:
        """Test with invalid JSON."""
        compile_commands = tmp_path / COMPILE_COMMANDS_JSON
        compile_commands.write_text("invalid json")

        with pytest.raises(RuntimeError, match="Failed to read compile_commands.json"):
            check_missing_source_files(str(compile_commands))

    def test_check_missing_source_files_wrong_format(self, tmp_path: Path) -> None:
        """Test with wrong JSON format (not a list)."""
        compile_commands = tmp_path / COMPILE_COMMANDS_JSON
        compile_commands.write_text('{"not": "a list"}')

        with pytest.raises(RuntimeError, match="Invalid compile_commands.json format"):
            check_missing_source_files(str(compile_commands))


class TestRunFullNinjaBuild:
    """Test the run_full_ninja_build function."""

    def test_run_full_ninja_build_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test successful ninja build."""

        class MockResult:
            returncode = 0
            stdout = ""
            stderr = ""

        def mock_run(*args: Any, **kwargs: Any) -> MockResult:
            return MockResult()

        monkeypatch.setattr(subprocess, "run", mock_run)

        result = run_full_ninja_build(str(tmp_path))
        assert result is True

    def test_run_full_ninja_build_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test failed ninja build."""

        class MockResult:
            returncode = 1
            stdout = ""
            stderr = "Build failed"

        def mock_run(*args: Any, **kwargs: Any) -> MockResult:
            return MockResult()

        monkeypatch.setattr(subprocess, "run", mock_run)

        result = run_full_ninja_build(str(tmp_path))
        assert result is False

    def test_run_full_ninja_build_timeout(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test ninja build timeout."""

        def mock_run(*args: Any, **kwargs: Any) -> None:
            raise subprocess.TimeoutExpired("ninja", 10)

        monkeypatch.setattr(subprocess, "run", mock_run)

        result = run_full_ninja_build(str(tmp_path), timeout=10)
        assert result is False

    def test_run_full_ninja_build_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test when ninja is not found."""

        def mock_run(*args: Any, **kwargs: Any) -> None:
            raise FileNotFoundError("ninja not found")

        monkeypatch.setattr(subprocess, "run", mock_run)

        result = run_full_ninja_build(str(tmp_path))
        assert result is False


class TestParseNinjaGeneratedFiles:
    """Test the parse_ninja_generated_files function."""

    def test_parse_ninja_with_custom_commands(self, tmp_path: Path) -> None:
        """Test parsing build.ninja with CUSTOM_COMMAND rules."""
        build_ninja = tmp_path / "build.ninja"
        build_ninja.write_text(
            """
rule CUSTOM_COMMAND
  command = python gen.py

rule CXX_COMPILER
  command = g++ -c $in -o $out

build generated.cpp: CUSTOM_COMMAND input.txt

build main.o: CXX_COMPILER main.cpp

build app: CXX_EXECUTABLE_LINKER main.o
"""
        )

        generated = parse_ninja_generated_files(str(build_ninja))
        assert "generated.cpp" in generated
        assert "main.o" not in generated
        assert "app" not in generated

    def test_parse_ninja_with_generator_flag(self, tmp_path: Path) -> None:
        """Test parsing build.ninja with generator flag."""
        build_ninja = tmp_path / "build.ninja"
        build_ninja.write_text(
            """
rule CODEGEN
  command = codegen $in $out
  generator = 1

rule CXX_COMPILER
  command = g++ -c $in -o $out

build proto.cpp proto.h: CODEGEN proto.proto

build main.o: CXX_COMPILER main.cpp
"""
        )

        generated = parse_ninja_generated_files(str(build_ninja))
        assert "proto.cpp" in generated
        assert "proto.h" in generated
        assert "main.o" not in generated

    def test_parse_ninja_with_phony_targets(self, tmp_path: Path) -> None:
        """Test that phony targets are included as generated."""
        build_ninja = tmp_path / "build.ninja"
        build_ninja.write_text(
            """
rule phony
  command = :

build all: phony app lib

build app: CXX_EXECUTABLE_LINKER main.o
"""
        )

        generated = parse_ninja_generated_files(str(build_ninja))
        assert "all" in generated

    def test_parse_ninja_empty_file(self, tmp_path: Path) -> None:
        """Test parsing empty build.ninja."""
        build_ninja = tmp_path / "build.ninja"
        build_ninja.write_text("")

        generated = parse_ninja_generated_files(str(build_ninja))
        assert len(generated) == 0

    def test_parse_ninja_nonexistent_file(self, tmp_path: Path) -> None:
        """Test parsing nonexistent build.ninja."""
        build_ninja = tmp_path / "nonexistent.ninja"

        generated = parse_ninja_generated_files(str(build_ninja))
        assert len(generated) == 0


class TestComputeFileHash:
    """Test the compute_file_hash function."""

    def test_compute_hash_simple_file(self, tmp_path: Path) -> None:
        """Test computing hash of a simple file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        hash1 = compute_file_hash(str(test_file))
        hash2 = compute_file_hash(str(test_file))

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

    def test_compute_hash_different_content(self, tmp_path: Path) -> None:
        """Test that different content produces different hashes."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        file1.write_text("Content A")
        file2.write_text("Content B")

        hash1 = compute_file_hash(str(file1))
        hash2 = compute_file_hash(str(file2))

        assert hash1 != hash2

    def test_compute_hash_nonexistent_file(self, tmp_path: Path) -> None:
        """Test computing hash of nonexistent file."""
        nonexistent = tmp_path / "nonexistent.txt"

        hash_val = compute_file_hash(str(nonexistent))
        assert hash_val == ""


class TestGeneratedFilesCache:
    """Test the generated files cache functions."""

    def test_save_and_load_cache(self, tmp_path: Path) -> None:
        """Test saving and loading cache."""
        cache_data = {"file1.cpp": "hash1", "file2.cpp": "hash2"}

        cache_path = str(tmp_path / ".buildcheck_generated_cache.json")
        save_generated_files_cache(cache_path, cache_data)
        loaded = load_generated_files_cache(cache_path)

        assert loaded == cache_data

    def test_load_nonexistent_cache(self, tmp_path: Path) -> None:
        """Test loading nonexistent cache returns empty dict."""
        cache_path = str(tmp_path / ".buildcheck_generated_cache.json")
        loaded = load_generated_files_cache(cache_path)
        assert loaded == {}

    def test_load_corrupted_cache(self, tmp_path: Path) -> None:
        """Test loading corrupted cache returns empty dict."""
        cache_file = tmp_path / ".buildcheck_generated_cache.json"
        cache_file.write_text("invalid json {{{")

        loaded = load_generated_files_cache(str(cache_file))
        assert loaded == {}


class TestCheckGeneratedFilesChanged:
    """Test the check_generated_files_changed function."""

    def test_detect_missing_files(self, tmp_path: Path) -> None:
        """Test detecting missing generated files."""
        generated_files = {"src/missing.cpp", "src/exists.cpp"}

        # Create only one file
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "exists.cpp").write_text("int main() {}")

        # Empty cache
        cache: Dict[str, str] = {}
        missing, changed = check_generated_files_changed(str(tmp_path), generated_files, cache)

        assert len(missing) == 1
        assert "missing.cpp" in missing[0]
        # exists.cpp is not in cache, so it's not marked as changed (it's new)
        assert len(changed) == 0

    def test_detect_changed_files(self, tmp_path: Path) -> None:
        """Test detecting changed generated files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        gen_file = src_dir / "generated.cpp"
        gen_file.write_text("// Version 1")

        # Save initial cache
        generated_files = {"src/generated.cpp"}
        cache = {str(gen_file): compute_file_hash(str(gen_file))}
        cache_path = str(tmp_path / ".buildcheck_generated_cache.json")
        save_generated_files_cache(cache_path, cache)

        # Modify the file
        gen_file.write_text("// Version 2")

        # Load cache before checking
        cache = load_generated_files_cache(cache_path)
        missing, changed = check_generated_files_changed(str(tmp_path), generated_files, cache)

        assert len(missing) == 0
        assert len(changed) == 1
        assert str(gen_file) in changed[0]

    def test_no_changes(self, tmp_path: Path) -> None:
        """Test when no files are missing or changed."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        gen_file = src_dir / "generated.cpp"
        gen_file.write_text("int main() {}")

        # Save cache
        generated_files = {"src/generated.cpp"}
        cache_path = str(tmp_path / ".buildcheck_generated_cache.json")
        cache: Dict[str, str] = {}
        files_to_update = [str(gen_file)]
        update_generated_files_cache(cache, files_to_update, cache_path)

        # Load cache before checking
        cache = load_generated_files_cache(cache_path)
        missing, changed = check_generated_files_changed(str(tmp_path), generated_files, cache)

        assert len(missing) == 0
        assert len(changed) == 0

    def test_ignore_non_source_files(self, tmp_path: Path) -> None:
        """Test that non-source files are ignored."""
        generated_files = {"build.stamp", "config.txt", "data.bin"}

        cache: Dict[str, str] = {}
        missing, changed = check_generated_files_changed(str(tmp_path), generated_files, cache)

        # Should ignore all these files
        assert len(missing) == 0
        assert len(changed) == 0


class TestUpdateGeneratedFilesCache:
    """Test the update_generated_files_cache function."""

    def test_update_cache_with_new_files(self, tmp_path: Path) -> None:
        """Test updating cache with new generated files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        file1 = src_dir / "gen1.cpp"
        file2 = src_dir / "gen2.cpp"
        file1.write_text("// File 1")
        file2.write_text("// File 2")

        files_to_update = [str(file1), str(file2)]
        cache: Dict[str, str] = {}
        cache_path = str(tmp_path / ".buildcheck_generated_cache.json")
        update_generated_files_cache(cache, files_to_update, cache_path)

        loaded_cache = load_generated_files_cache(cache_path)

        assert str(file1) in loaded_cache
        assert str(file2) in loaded_cache
        assert loaded_cache[str(file1)] == compute_file_hash(str(file1))
        assert loaded_cache[str(file2)] == compute_file_hash(str(file2))

    def test_update_cache_skip_nonexistent(self, tmp_path: Path) -> None:
        """Test that nonexistent files are skipped."""
        missing_file = str(tmp_path / "src" / "missing.cpp")
        files_to_update = [missing_file]
        cache: Dict[str, str] = {}
        cache_path = str(tmp_path / ".buildcheck_generated_cache.json")
        update_generated_files_cache(cache, files_to_update, cache_path)

        loaded_cache = load_generated_files_cache(cache_path)
        assert len(loaded_cache) == 0


class TestCleanStaleCacheEntries:
    """Test the clean_stale_cache_entries function."""

    def test_remove_deleted_files(self, tmp_path: Path) -> None:
        """Test removing cache entries for deleted files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # Create initial file and cache
        file1 = src_dir / "gen1.cpp"
        file1.write_text("content")

        cache = {str(file1): "hash1", str(src_dir / "deleted.cpp"): "hash2"}  # This file doesn't exist

        generated_files = {"src/gen1.cpp", "src/deleted.cpp"}

        cleaned = clean_stale_cache_entries(cache, generated_files, str(tmp_path))

        # Only gen1.cpp should remain (exists and is in generated_files)
        assert len(cleaned) == 1
        assert str(file1) in cleaned
        assert str(src_dir / "deleted.cpp") not in cleaned

    def test_remove_no_longer_generated(self, tmp_path: Path) -> None:
        """Test removing cache entries for files no longer in generated_files list."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        file1 = src_dir / "gen1.cpp"
        file2 = src_dir / "gen2.cpp"
        file1.write_text("content1")
        file2.write_text("content2")

        cache = {str(file1): "hash1", str(file2): "hash2"}

        # Only file1 is still in generated_files
        generated_files = {"src/gen1.cpp"}

        cleaned = clean_stale_cache_entries(cache, generated_files, str(tmp_path))

        assert len(cleaned) == 1
        assert str(file1) in cleaned
        assert str(file2) not in cleaned


class TestRunFullNinjaBuildErrorHandling:
    """Test error handling in run_full_ninja_build."""

    @pytest.mark.unit
    def test_build_timeout(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test build timing out."""
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        (build_dir / "build.ninja").write_text("rule dummy\n  command = true\n")

        def mock_run(*args: Any, **kwargs: Any) -> Any:
            raise subprocess.TimeoutExpired("ninja", kwargs.get("timeout", 60))

        monkeypatch.setattr(subprocess, "run", mock_run)

        result = run_full_ninja_build(str(build_dir), verbose=False, timeout=10)
        assert result is False

    @pytest.mark.unit
    def test_build_ninja_not_found(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test build when ninja command is not found."""
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        (build_dir / "build.ninja").write_text("rule dummy\n  command = true\n")

        def mock_run(*args: Any, **kwargs: Any) -> Any:
            raise FileNotFoundError("ninja not found")

        monkeypatch.setattr(subprocess, "run", mock_run)

        result = run_full_ninja_build(str(build_dir), verbose=False)
        assert result is False

    @pytest.mark.unit
    def test_build_generic_exception(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test build with generic exception."""
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        (build_dir / "build.ninja").write_text("rule dummy\n  command = true\n")

        def mock_run(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("Unexpected error")

        monkeypatch.setattr(subprocess, "run", mock_run)

        result = run_full_ninja_build(str(build_dir), verbose=False)
        assert result is False

    @pytest.mark.unit
    def test_build_with_targets(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test build with specific targets."""
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        (build_dir / "build.ninja").write_text("rule dummy\n  command = true\n")

        called_with_targets = []

        def mock_run(cmd: List[str], *args: Any, **kwargs: Any) -> Any:
            called_with_targets.extend(cmd)

            class MockResult:
                returncode = 0

            return MockResult()

        monkeypatch.setattr(subprocess, "run", mock_run)

        result = run_full_ninja_build(str(build_dir), verbose=True, targets=["target1", "target2"])
        assert result is True
        assert "target1" in called_with_targets
        assert "target2" in called_with_targets


class TestGetRelativeBuildPath:
    """Test get_relative_build_path function."""

    @pytest.mark.unit
    def test_relative_path_inside_build_dir(self, tmp_path: Path) -> None:
        """Test converting absolute path inside build dir to relative."""
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        file_path = build_dir / "src" / "gen.cpp"

        rel_path = get_relative_build_path(str(file_path), str(build_dir))
        assert rel_path == os.path.join("src", "gen.cpp")

    @pytest.mark.unit
    def test_relative_path_outside_build_dir(self, tmp_path: Path) -> None:
        """Test path outside build dir returns basename."""
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        file_path = tmp_path / "other" / "file.cpp"

        rel_path = get_relative_build_path(str(file_path), str(build_dir))
        assert rel_path == "file.cpp"


class TestCheckMissingSourceFilesErrorHandling:
    """Test error handling in check_missing_source_files."""

    @pytest.mark.unit
    def test_invalid_json(self, tmp_path: Path) -> None:
        """Test handling of invalid JSON."""
        compile_commands = tmp_path / "compile_commands.json"
        compile_commands.write_text("{invalid json")

        with pytest.raises(RuntimeError, match="Failed to read"):
            check_missing_source_files(str(compile_commands))

    @pytest.mark.unit
    def test_not_a_list(self, tmp_path: Path) -> None:
        """Test handling when JSON is not a list."""
        compile_commands = tmp_path / "compile_commands.json"
        compile_commands.write_text('{"not": "a list"}')

        with pytest.raises(RuntimeError, match="expected list"):
            check_missing_source_files(str(compile_commands))

    @pytest.mark.unit
    def test_entry_not_dict(self, tmp_path: Path) -> None:
        """Test handling when entry is not a dict."""
        compile_commands = tmp_path / "compile_commands.json"
        compile_commands.write_text('["not a dict", 123]')

        # Should skip invalid entries
        missing = check_missing_source_files(str(compile_commands))
        assert missing == []

    @pytest.mark.unit
    def test_missing_file_field(self, tmp_path: Path) -> None:
        """Test handling when entry lacks 'file' field."""
        compile_commands = tmp_path / "compile_commands.json"
        compile_commands.write_text('[{"directory": "/tmp", "command": "gcc"}]')

        missing = check_missing_source_files(str(compile_commands))
        assert missing == []


class TestParseNinjaExplainLine:
    """Test parse_ninja_explain_line function."""

    @pytest.mark.unit
    def test_parse_output_line(self) -> None:
        """Test parsing 'output' explain line."""
        line = "ninja explain: output file.o doesn't exist"
        pattern = re.compile(r"ninja explain: (.*)")

        result = parse_ninja_explain_line(line, pattern)
        assert result is not None
        output_file, explain_msg = result
        assert output_file == "file.o"
        assert "doesn't exist" in explain_msg

    @pytest.mark.unit
    def test_parse_command_line_changed(self) -> None:
        """Test parsing 'command line changed' explain line."""
        line = "ninja explain: command line changed for target.o"
        pattern = re.compile(r"ninja explain: (.*)")

        result = parse_ninja_explain_line(line, pattern)
        assert result is not None
        output_file, explain_msg = result
        assert output_file == "target.o"
        assert "command line changed" in explain_msg

    @pytest.mark.unit
    def test_parse_dirty_line_ignored(self) -> None:
        """Test that 'is dirty' lines are ignored."""
        line = "ninja explain: CMakeLists.txt is dirty"
        pattern = re.compile(r"ninja explain: (.*)")

        result = parse_ninja_explain_line(line, pattern)
        assert result is None

    @pytest.mark.unit
    def test_parse_non_matching_line(self) -> None:
        """Test parsing line that doesn't match pattern."""
        line = "some other output"
        pattern = re.compile(r"ninja explain: (.*)")

        result = parse_ninja_explain_line(line, pattern)
        assert result is None


class TestValidateAndPrepareBuildDirErrorHandling:
    """Test error handling in validate_and_prepare_build_dir."""

    @pytest.mark.unit
    def test_symlink_path_traversal(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test detection of symlink-based path traversal."""
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        (build_dir / "build.ninja").write_text("rule dummy\n")

        # Mock realpath to simulate path traversal
        original_realpath = os.path.realpath

        def mock_realpath(path: str) -> str:
            if "compile_commands.json" in path:
                # Simulate symlink pointing outside build_dir
                return str(tmp_path.parent / "evil" / "compile_commands.json")
            return original_realpath(path)

        monkeypatch.setattr(os.path, "realpath", mock_realpath)

        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_and_prepare_build_dir(str(build_dir), verbose=False)


class TestCleanStaleCacheEntriesAdditional:
    """Additional tests for clean_stale_cache_entries."""

    def test_remove_no_longer_generated(self, tmp_path: Path) -> None:
        """Test removing cache entries for files no longer in generated_files list."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        file1 = src_dir / "gen1.cpp"
        file2 = src_dir / "gen2.cpp"
        file1.write_text("content1")
        file2.write_text("content2")

        cache = {str(file1): "hash1", str(file2): "hash2"}

        # Only file1 is still in generated_files
        generated_files = {"src/gen1.cpp"}

        cleaned = clean_stale_cache_entries(cache, generated_files, str(tmp_path))

        assert len(cleaned) == 1
        assert str(file1) in cleaned
        assert str(file2) not in cleaned

    def test_keep_all_valid_entries(self, tmp_path: Path) -> None:
        """Test that all valid entries are kept."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        file1 = src_dir / "gen1.cpp"
        file2 = src_dir / "gen2.cpp"
        file1.write_text("content1")
        file2.write_text("content2")

        cache = {str(file1): "hash1", str(file2): "hash2"}

        generated_files = {"src/gen1.cpp", "src/gen2.cpp"}

        cleaned = clean_stale_cache_entries(cache, generated_files, str(tmp_path))

        # Both should remain
        assert len(cleaned) == 2
        assert str(file1) in cleaned
        assert str(file2) in cleaned

    def test_ignore_non_source_files(self, tmp_path: Path) -> None:
        """Test that non-source files in cache are removed."""
        cache = {str(tmp_path / "file.txt"): "hash1", str(tmp_path / "data.bin"): "hash2"}

        generated_files = {"file.txt", "data.bin"}

        cleaned = clean_stale_cache_entries(cache, generated_files, str(tmp_path))

        # Non-source files should be removed
        assert len(cleaned) == 0

    def test_empty_cache(self, tmp_path: Path) -> None:
        """Test cleaning an empty cache."""
        cache: Dict[str, str] = {}
        generated_files = {"src/gen1.cpp"}

        cleaned = clean_stale_cache_entries(cache, generated_files, str(tmp_path))

        assert len(cleaned) == 0

    def test_empty_generated_files(self, tmp_path: Path) -> None:
        """Test cleaning when no files are generated anymore."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        file1 = src_dir / "gen1.cpp"
        file1.write_text("content")

        cache = {str(file1): "hash1"}
        generated_files: Set[str] = set()

        cleaned = clean_stale_cache_entries(cache, generated_files, str(tmp_path))

        # All entries should be removed
        assert len(cleaned) == 0
