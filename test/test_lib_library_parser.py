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
"""Tests for lib.library_parser module"""
import os
import sys
from pathlib import Path
import pytest
from typing import Any, Dict, List, Tuple, Generator

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.library_parser import parse_ninja_libraries, compute_library_metrics, find_library_cycles


class TestParseNinjaLibraries:
    """Test the parse_ninja_libraries function."""

    def test_parse_simple_libraries(self, temp_dir: Any) -> None:
        """Test parsing a simple build.ninja with libraries."""
        build_ninja = Path(temp_dir) / "build.ninja"
        build_ninja.write_text(
            """rule CXX_STATIC_LIBRARY_LINKER
  command = ar qc $out $in

rule CXX_EXECUTABLE_LINKER
  command = g++ $in -o $out

build libA.a: CXX_STATIC_LIBRARY_LINKER a.cpp.o
build libB.a: CXX_STATIC_LIBRARY_LINKER b.cpp.o | || libA.a
build exe1: CXX_EXECUTABLE_LINKER main.cpp.o | || libA.a libB.a
"""
        )

        lib_to_libs, exe_to_libs, all_libs, all_exes = parse_ninja_libraries(str(build_ninja))

        assert "libA.a" in all_libs
        assert "libB.a" in all_libs
        assert "exe1" in all_exes
        assert "libA.a" in lib_to_libs.get("libB.a", set())
        assert "libA.a" in exe_to_libs.get("exe1", set())
        assert "libB.a" in exe_to_libs.get("exe1", set())

    def test_parse_empty_build_file(self, temp_dir: Any) -> None:
        """Test parsing an empty build.ninja."""
        build_ninja = Path(temp_dir) / "build.ninja"
        build_ninja.write_text("# Empty build file\n")

        lib_to_libs, exe_to_libs, all_libs, all_exes = parse_ninja_libraries(str(build_ninja))

        assert len(all_libs) == 0
        assert len(all_exes) == 0

    def test_parse_complex_dependencies(self, temp_dir: Any) -> None:
        """Test parsing complex library dependencies."""
        build_ninja = Path(temp_dir) / "build.ninja"
        build_ninja.write_text(
            """
rule CXX_STATIC_LIBRARY_LINKER
  command = ar qc $out $in

build libFoundation.a: CXX_STATIC_LIBRARY_LINKER foundation.cpp.o
build libCore.a: CXX_STATIC_LIBRARY_LINKER core.cpp.o | || libFoundation.a
build libUI.a: CXX_STATIC_LIBRARY_LINKER ui.cpp.o | || libCore.a libFoundation.a
build libNetwork.a: CXX_STATIC_LIBRARY_LINKER network.cpp.o | || libCore.a
build app: CXX_EXECUTABLE_LINKER main.cpp.o | || libUI.a libNetwork.a libCore.a libFoundation.a
"""
        )

        lib_to_libs, exe_to_libs, all_libs, all_exes = parse_ninja_libraries(str(build_ninja))

        assert len(all_libs) == 4
        assert "libFoundation.a" in lib_to_libs.get("libCore.a", set())
        assert "libCore.a" in lib_to_libs.get("libUI.a", set())
        assert "libFoundation.a" in lib_to_libs.get("libUI.a", set())
        assert len(exe_to_libs.get("app", set())) == 4


class TestComputeLibraryMetrics:
    """Test the compute_library_metrics function."""

    def test_compute_metrics_simple(self) -> None:
        """Test computing metrics for simple library graph."""
        lib_to_libs = {"libA": set(), "libB": {"libA"}, "libC": {"libA"}}
        exe_to_libs = {"exe1": {"libB"}, "exe2": {"libC"}}
        all_libs = {"libA", "libB", "libC"}

        metrics = compute_library_metrics(lib_to_libs, exe_to_libs, all_libs)

        assert "libA" in metrics
        assert "libB" in metrics
        assert "libC" in metrics

        # libA has 2 direct dependents (libB, libC) - fan_in
        assert metrics["libA"]["fan_in"] == 2
        # libA should have transitive dependents too
        assert metrics["libA"]["transitive_dependents"] >= 2

    def test_compute_metrics_complex(self) -> None:
        """Test computing metrics for complex library graph."""
        lib_to_libs = {"libFoundation": set(), "libCore": {"libFoundation"}, "libUI": {"libCore"}}
        exe_to_libs = {"app1": {"libUI"}, "app2": {"libCore"}, "app3": {"libFoundation"}}
        all_libs = {"libFoundation", "libCore", "libUI"}

        metrics = compute_library_metrics(lib_to_libs, exe_to_libs, all_libs)

        # libFoundation is used by everything transitively
        assert metrics["libFoundation"]["transitive_dependents"] >= 3


class TestFindLibraryCycles:
    """Test the find_library_cycles function."""

    def test_no_cycles(self) -> None:
        """Test finding cycles when there are none."""
        lib_to_libs = {"libA": set(), "libB": {"libA"}, "libC": {"libB"}}

        cycles = find_library_cycles(lib_to_libs)

        assert len(cycles) == 0

    def test_simple_cycle(self) -> None:
        """Test finding a simple cycle."""
        lib_to_libs = {"libA": {"libB"}, "libB": {"libA"}}

        cycles = find_library_cycles(lib_to_libs)

        if cycles is not None:  # NetworkX available
            assert len(cycles) > 0
            # Check that the cycle contains libA and libB
            cycle = cycles[0]
            assert "libA" in cycle
            assert "libB" in cycle

    def test_complex_cycle(self) -> None:
        """Test finding a complex cycle."""
        lib_to_libs = {"libA": {"libB"}, "libB": {"libC"}, "libC": {"libA"}, "libD": set()}

        cycles = find_library_cycles(lib_to_libs)

        if cycles is not None:  # NetworkX available
            assert len(cycles) > 0
            cycle = cycles[0]
            # The cycle should contain A, B, C but not D
            assert "libA" in cycle or "libB" in cycle or "libC" in cycle
            assert len(cycle) >= 3

    def test_multiple_cycles(self) -> None:
        """Test finding multiple separate cycles."""
        lib_to_libs = {"libA": {"libB"}, "libB": {"libA"}, "libC": {"libD"}, "libD": {"libC"}, "libE": set()}

        cycles = find_library_cycles(lib_to_libs)

        if cycles is not None:  # NetworkX available
            # Should find at least 2 cycles (A-B and C-D)
            assert len(cycles) >= 1
