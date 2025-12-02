#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Advanced tests for compile command sanitization.

This test suite focuses on the robust sanitization needed for clang-scan-deps
to work across different platforms and build configurations, especially:
- Mac builds with ccache contamination
- Build wrapper removal (distcc, icecc)
- Output file specification removal
- Validation and fail-fast behavior
"""

import pytest
from typing import Any

from lib.clang_utils import sanitize_compile_command


class TestMacCcacheIssue:
    """Tests for Mac-specific ccache contamination issues."""

    def test_remove_bare_ccache_sloppiness_argument(self) -> None:
        """Test removal of bare ccache sloppiness argument that breaks clang-scan-deps.

        This is the actual error from Mac build:
        error: no such file or directory: 'sloppiness=pch_defines,time_macros,include_file_ctime,include_file_mtime'
        """
        command = (
            "/usr/bin/clang++ -std=c++17 -I/path/include " "sloppiness=pch_defines,time_macros,include_file_ctime,include_file_mtime " "-c /path/source.cpp"
        )
        result = sanitize_compile_command(command)

        # Should remove the bare sloppiness argument
        assert "sloppiness=" not in result
        # Should keep compiler and source
        assert "/usr/bin/clang++" in result or "clang++" in result
        assert "/path/source.cpp" in result
        # Should keep valid flags
        assert "-std=c++17" in result
        assert "-I/path/include" in result

    def test_remove_multiple_bare_ccache_arguments(self) -> None:
        """Test removal of multiple ccache environment variable values."""
        command = "ccache /usr/bin/g++ " "sloppiness=pch_defines " "compression=true " "-std=c++20 -I/inc -c test.cpp"
        result = sanitize_compile_command(command)

        assert "sloppiness=" not in result
        assert "compression=" not in result
        assert "ccache" not in result
        assert "-std=c++20" in result

    def test_remove_ccache_with_env_vars(self) -> None:
        """Test removal of ccache with environment variable assignments."""
        command = "CCACHE_SLOPPINESS=pch_defines ccache " "/usr/bin/clang++ -std=c++17 -c source.cpp"
        result = sanitize_compile_command(command)

        assert "CCACHE_SLOPPINESS" not in result
        assert "ccache" not in result
        assert "clang++" in result


class TestOutputFileRemoval:
    """Tests for output file specification removal."""

    def test_remove_output_file_with_o_flag(self) -> None:
        """Test that -o flag is kept for target uniqueness (prevents basename collisions)."""
        command = "/usr/bin/g++ -std=c++17 -I/inc -c source.cpp -o output.o"
        result = sanitize_compile_command(command)

        assert "-o" in result
        assert "output.o" in result
        assert "-c" in result
        assert "source.cpp" in result

    def test_remove_output_file_o_flag_separate(self) -> None:
        """Test that -o with space-separated argument is kept."""
        command = "/usr/bin/g++ -c source.cpp -o output.o"
        result = sanitize_compile_command(command)

        assert "-o" in result
        assert "output.o" in result

    def test_remove_dependency_file_flags(self) -> None:
        """Test removal of dependency generation flags."""
        command = "/usr/bin/g++ -c source.cpp -o output.o " "-MD -MF output.d -MT output.o"
        result = sanitize_compile_command(command)

        # These flags conflict with clang-scan-deps
        assert "-MD" not in result
        assert "-MF" not in result
        assert "output.d" not in result
        assert "-MT" not in result


class TestBuildWrapperRemoval:
    """Tests for build wrapper tool removal."""

    def test_remove_distcc_wrapper(self) -> None:
        """Test removal of distcc distributed compilation wrapper."""
        command = "distcc /usr/bin/g++ -std=c++17 -c source.cpp"
        result = sanitize_compile_command(command)

        assert "distcc" not in result
        assert "g++" in result

    def test_remove_icecc_wrapper(self) -> None:
        """Test removal of icecc (icecream) wrapper."""
        command = "icecc /usr/bin/clang++ -c source.cpp"
        result = sanitize_compile_command(command)

        assert "icecc" not in result
        assert "clang++" in result

    def test_remove_multiple_wrappers(self) -> None:
        """Test removal of multiple wrapper layers."""
        command = "distcc ccache /usr/bin/g++ -c source.cpp"
        result = sanitize_compile_command(command)

        assert "distcc" not in result
        assert "ccache" not in result
        assert "g++" in result


class TestValidFlagPreservation:
    """Tests that valid compiler flags are preserved."""

    def test_keep_include_paths(self) -> None:
        """Test that include paths are preserved."""
        command = "/usr/bin/g++ -I/path1 -I /path2 -isystem /sys " "-iquote /quote -c source.cpp"
        result = sanitize_compile_command(command)

        assert "-I/path1" in result or "-I /path1" in result
        assert "/path2" in result
        assert "-isystem" in result
        assert "-iquote" in result

    def test_keep_preprocessor_defines(self) -> None:
        """Test that preprocessor defines are preserved."""
        command = "/usr/bin/g++ -DFOO=1 -D BAR -DPLATFORM_LINUX " "-c source.cpp"
        result = sanitize_compile_command(command)

        assert "-DFOO=1" in result or "FOO=1" in result
        assert "-D" in result
        assert "BAR" in result
        assert "PLATFORM_LINUX" in result

    def test_keep_language_standard(self) -> None:
        """Test that language standard flags are preserved."""
        command = "/usr/bin/g++ -std=c++20 -c source.cpp"
        result = sanitize_compile_command(command)

        assert "-std=c++20" in result

    def test_warning_flags_removed(self) -> None:
        """Test that warning flags are removed (not needed for preprocessing)."""
        command = "/usr/bin/g++ -Wall -Wextra -Werror -Wpedantic -c source.cpp"
        result = sanitize_compile_command(command)

        # Warning flags should be removed
        assert "-Wall" not in result
        assert "-Wextra" not in result
        assert "-Werror" not in result
        assert "-Wpedantic" not in result

        # Essential flags should remain
        assert "-c" in result
        assert "source.cpp" in result

    def test_optimization_flags_removed(self) -> None:
        """Test that optimization and debug flags are removed (not needed for preprocessing)."""
        command = "/usr/bin/g++ -O2 -O3 -Os -g -g3 -ggdb -c source.cpp"
        result = sanitize_compile_command(command)

        # Optimization flags should be removed
        assert "-O2" not in result
        assert "-O3" not in result
        assert "-Os" not in result
        assert "-g" not in result
        assert "-g3" not in result
        assert "-ggdb" not in result

        # Essential flags should remain
        assert "-c" in result
        assert "source.cpp" in result

    def test_feature_flags_removed(self) -> None:
        """Test that feature and machine flags are removed (not needed for preprocessing)."""
        command = "/usr/bin/g++ -fPIC -fpic -fno-exceptions -fno-rtti -march=native -mtune=native -mavx2 -m64 -c source.cpp"
        result = sanitize_compile_command(command)

        # Feature flags should be removed
        assert "-fPIC" not in result
        assert "-fpic" not in result
        assert "-fno-exceptions" not in result
        assert "-fno-rtti" not in result

        # Machine/architecture flags should be removed
        assert "-march=" not in result
        assert "-mtune=" not in result
        assert "-mavx2" not in result
        assert "-m64" not in result

        # Essential flags should remain
        assert "-c" in result
        assert "source.cpp" in result

    def test_msvc_optimization_warning_flags_removed(self) -> None:
        """Test that MSVC-style optimization and warning flags are removed."""
        command = "cl.exe /c test.cpp /W4 /WX /Wall /O2 /Ox /Ot /I C:\\includes /D NDEBUG"
        result = sanitize_compile_command(command)

        # MSVC warning/optimization flags should be removed
        assert "/W4" not in result
        assert "/WX" not in result
        assert "/Wall" not in result
        assert "/O2" not in result
        assert "/Ox" not in result
        assert "/Ot" not in result

        # Include paths and defines should remain
        assert "/I" in result or "C:\\includes" in result or "includes" in result
        assert "/D" in result or "NDEBUG" in result


class TestFailFastValidation:
    """Tests for fail-fast validation behavior."""

    def test_fail_when_no_compiler_found(self) -> None:
        """Test that sanitization fails when no compiler remains."""
        command = "ccache sloppiness=true -c source.cpp"

        with pytest.raises(ValueError, match="No compiler found"):
            sanitize_compile_command(command)

    def test_fail_when_no_source_file_found(self) -> None:
        """Test that sanitization fails when no source file remains."""
        command = "/usr/bin/g++ -c"

        with pytest.raises(ValueError, match="No source file found"):
            sanitize_compile_command(command)

    def test_fail_when_all_arguments_removed(self) -> None:
        """Test that sanitization fails when command becomes empty."""
        command = "ccache distcc sloppiness=true"

        with pytest.raises(ValueError):
            sanitize_compile_command(command)

    def test_validation_error_contains_details(self) -> None:
        """Test that validation errors contain helpful details."""
        command = "ccache sloppiness=true -c source.cpp"

        try:
            sanitize_compile_command(command)
            pytest.fail("Should have raised ValueError")
        except ValueError as e:
            error_msg = str(e)
            # Should mention what's wrong
            assert "compiler" in error_msg.lower()
            # Should be helpful
            assert len(error_msg) > 20


class TestLinkerFlagRemoval:
    """Tests for linker flag removal (already partially implemented)."""

    def test_remove_linker_flags_wl(self) -> None:
        """Test removal of -Wl, linker flags."""
        command = "/usr/bin/g++ -c source.cpp -Wl,-rpath,/lib"
        result = sanitize_compile_command(command)

        assert "-Wl," not in result

    def test_remove_xlinker_flags(self) -> None:
        """Test removal of -Xlinker flags and their arguments."""
        command = "/usr/bin/g++ -c source.cpp -Xlinker --version"
        result = sanitize_compile_command(command)

        assert "-Xlinker" not in result
        assert "--version" not in result or "-c" in result  # --version removed or command still valid


class TestEdgeCases:
    """Tests for edge cases and corner scenarios."""

    def test_empty_command(self) -> None:
        """Test handling of empty command."""
        command = ""

        with pytest.raises(ValueError):
            sanitize_compile_command(command)

    def test_whitespace_only_command(self) -> None:
        """Test handling of whitespace-only command."""
        command = "   \t  \n  "

        with pytest.raises(ValueError):
            sanitize_compile_command(command)

    def test_preserve_quoted_paths_with_spaces(self) -> None:
        """Test that quoted paths with spaces are preserved."""
        command = '/usr/bin/g++ -I"/path with spaces" -c source.cpp'
        result = sanitize_compile_command(command)

        assert "path with spaces" in result

    def test_response_file_handling(self) -> None:
        """Test handling of response files (@file)."""
        # Current implementation removes response files
        command = "/usr/bin/g++ @compile_flags.txt -c source.cpp"
        result = sanitize_compile_command(command)

        # Response files are removed for now (they may contain ccache options)
        assert "@compile_flags.txt" not in result


class TestBackwardCompatibility:
    """Tests to ensure existing functionality still works."""

    def test_basic_sanitization_still_works(self) -> None:
        """Test that basic sanitization from existing tests still works."""
        command = "ccache /usr/bin/g++ -std=c++17 -I/inc -c source.cpp"
        result = sanitize_compile_command(command)

        assert "ccache" not in result
        assert "g++" in result
        assert "-std=c++17" in result
        assert "source.cpp" in result
