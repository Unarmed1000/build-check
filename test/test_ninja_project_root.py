#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test ninja-based project root calculation.

Verifies that project root is calculated correctly from build.ninja files,
and that it works correctly with git baseline reconstruction.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.ninja_utils import extract_source_and_header_files_from_ninja
from lib.clang_utils import find_project_root_from_sources


def test_extract_sources_and_headers_from_ninja() -> None:
    """Test that we can extract sources and headers from build.ninja."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a simple build.ninja
        build_ninja = Path(tmpdir) / "build.ninja"
        build_ninja.write_text(
            """
rule cxx
  command = clang++ -std=c++17 -Iinclude -c $in -o $out

build obj/Module0/Header0.o: cxx src/Module0/Header0.cpp | include/Module0/Header0.hpp
build obj/Module0/Header1.o: cxx src/Module0/Header1.cpp | include/Module0/Header1.hpp
build obj/Module1/Header0.o: cxx src/Module1/Header0.cpp | include/Module1/Header0.hpp
"""
        )

        sources, headers = extract_source_and_header_files_from_ninja(str(build_ninja))

        # Verify we extracted all sources
        assert len(sources) == 3, f"Expected 3 sources, got {len(sources)}"
        source_names = [os.path.basename(s) for s in sources]
        assert "Header0.cpp" in source_names
        assert "Header1.cpp" in source_names

        # Verify we extracted all headers
        assert len(headers) == 3, f"Expected 3 headers, got {len(headers)}"
        header_names = [os.path.basename(h) for h in headers]
        assert "Header0.hpp" in header_names
        assert "Header1.hpp" in header_names


def test_project_root_from_ninja_files() -> None:
    """Test that project root is calculated from ninja sources and headers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create directory structure
        src_dir = tmpdir_path / "src" / "Module0"
        inc_dir = tmpdir_path / "include" / "Module0"
        src_dir.mkdir(parents=True)
        inc_dir.mkdir(parents=True)

        # Create files
        (src_dir / "Test.cpp").write_text("// test source")
        (inc_dir / "Test.hpp").write_text("// test header")

        # Create build.ninja
        build_ninja = tmpdir_path / "build.ninja"
        build_ninja.write_text(
            f"""
rule cxx
  command = clang++ -std=c++17 -I{inc_dir.parent} -c $in -o $out

build obj/Module0/Test.o: cxx {src_dir / "Test.cpp"} | {inc_dir / "Test.hpp"}
"""
        )

        sources, headers = extract_source_and_header_files_from_ninja(str(build_ninja))
        all_files = sources + headers

        project_root = find_project_root_from_sources(all_files)

        # Project root should be tmpdir (common ancestor of src/ and include/)
        assert project_root == str(tmpdir_path), f"Expected {tmpdir_path}, got {project_root}"


def test_ninja_extraction_with_multiple_modules() -> None:
    """Test ninja extraction with multiple modules."""
    with tempfile.TemporaryDirectory() as tmpdir:
        build_ninja = Path(tmpdir) / "build.ninja"

        # Create build.ninja with multiple modules
        build_ninja.write_text(
            """
rule cxx
  command = clang++ -c $in -o $out

build obj/ModuleA/File1.o: cxx src/ModuleA/File1.cpp | include/ModuleA/File1.hpp
build obj/ModuleA/File2.o: cxx src/ModuleA/File2.cpp | include/ModuleA/File2.hpp
build obj/ModuleB/File1.o: cxx src/ModuleB/File1.cpp | include/ModuleB/File1.hpp
build obj/ModuleB/File2.o: cxx src/ModuleB/File2.cpp | include/ModuleB/File2.hpp
build obj/ModuleC/File1.o: cxx src/ModuleC/File1.cpp | include/ModuleC/File1.hpp
"""
        )

        sources, headers = extract_source_and_header_files_from_ninja(str(build_ninja))

        assert len(sources) == 5, f"Expected 5 sources, got {len(sources)}"
        assert len(headers) == 5, f"Expected 5 headers, got {len(headers)}"

        # Check that we have all modules
        source_paths = [s for s in sources]
        assert any("ModuleA" in s for s in source_paths)
        assert any("ModuleB" in s for s in source_paths)
        assert any("ModuleC" in s for s in source_paths)


def test_ninja_extraction_empty_file() -> None:
    """Test that extraction handles empty or missing build.ninja gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        build_ninja = Path(tmpdir) / "build.ninja"
        build_ninja.write_text("")  # Empty file

        sources, headers = extract_source_and_header_files_from_ninja(str(build_ninja))

        assert len(sources) == 0
        assert len(headers) == 0


def test_ninja_extraction_no_headers() -> None:
    """Test extraction when build rules have no implicit headers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        build_ninja = Path(tmpdir) / "build.ninja"

        # Build rules without implicit headers (no |)
        build_ninja.write_text(
            """
rule cxx
  command = clang++ -c $in -o $out

build obj/File1.o: cxx src/File1.cpp
build obj/File2.o: cxx src/File2.cpp
"""
        )

        sources, headers = extract_source_and_header_files_from_ninja(str(build_ninja))

        assert len(sources) == 2, f"Expected 2 sources, got {len(sources)}"
        assert len(headers) == 0, f"Expected 0 headers, got {len(headers)}"


def test_ninja_extraction_case_insensitive_rule() -> None:
    """Test that rule matching is case-insensitive (cxx vs CXX)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        build_ninja = Path(tmpdir) / "build.ninja"

        # Mix of cxx and CXX rules
        build_ninja.write_text(
            """
rule cxx
  command = clang++ -c $in -o $out

rule CXX
  command = g++ -c $in -o $out

build obj/File1.o: cxx src/File1.cpp | include/File1.hpp
build obj/File2.o: CXX src/File2.cpp | include/File2.hpp
"""
        )

        sources, headers = extract_source_and_header_files_from_ninja(str(build_ninja))

        # Should find both
        assert len(sources) == 2, f"Expected 2 sources, got {len(sources)}"
        assert len(headers) == 2, f"Expected 2 headers, got {len(headers)}"


def test_baseline_sources_reconstruction() -> None:
    """Test that baseline sources can be reconstructed correctly.

    This simulates the git scenario where we need to reconstruct baseline
    build.ninja in memory from git HEAD sources.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create baseline structure (what's in git HEAD)
        baseline_sources = [
            str(tmpdir_path / "src" / "Module0" / "Header0.cpp"),
            str(tmpdir_path / "src" / "Module0" / "Header1.cpp"),
            str(tmpdir_path / "src" / "Module1" / "Header0.cpp"),
        ]

        baseline_headers = [
            str(tmpdir_path / "include" / "Module0" / "Header0.hpp"),
            str(tmpdir_path / "include" / "Module0" / "Header1.hpp"),
            str(tmpdir_path / "include" / "Module1" / "Header0.hpp"),
        ]

        # Calculate project root from baseline sources/headers
        all_baseline_files = baseline_sources + baseline_headers
        baseline_project_root = find_project_root_from_sources(all_baseline_files)

        # Should be tmpdir
        assert baseline_project_root == str(tmpdir_path)

        # Now simulate current state with one additional file
        current_sources = baseline_sources + [str(tmpdir_path / "src" / "Module1" / "Header1.cpp")]
        current_headers = baseline_headers + [str(tmpdir_path / "include" / "Module1" / "Header1.hpp")]

        all_current_files = current_sources + current_headers
        current_project_root = find_project_root_from_sources(all_current_files)

        # Project root should be the same
        assert baseline_project_root == current_project_root

        # But the file lists should be different
        assert len(baseline_sources) == 3
        assert len(current_sources) == 4


def test_all_ninja_files_extracted() -> None:
    """Test that ALL files in build.ninja are extracted, including Module0/Header0.

    This is a regression test for the issue where Module0/Header0 was being missed.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        build_ninja = Path(tmpdir) / "build.ninja"

        # Create build.ninja with all Module0 headers including Header0
        build_ninja.write_text(
            """
rule cxx
  command = clang++ -c $in -o $out

build obj/Module0/Header0.o: cxx src/Module0/Header0.cpp | include/Module0/Header0.hpp
build obj/Module0/Header1.o: cxx src/Module0/Header1.cpp | include/Module0/Header1.hpp
build obj/Module0/Header2.o: cxx src/Module0/Header2.cpp | include/Module0/Header2.hpp
build obj/Module0/Header3.o: cxx src/Module0/Header3.cpp | include/Module0/Header3.hpp
build obj/Module0/Header4.o: cxx src/Module0/Header4.cpp | include/Module0/Header4.hpp
"""
        )

        sources, headers = extract_source_and_header_files_from_ninja(str(build_ninja))

        # Verify all 5 headers are extracted
        assert len(headers) == 5, f"Expected 5 headers, got {len(headers)}: {headers}"

        # Specifically check for Header0
        header_basenames = {os.path.basename(h) for h in headers}
        assert "Header0.hpp" in header_basenames, f"Header0.hpp missing from {header_basenames}"

        # Check all headers are present
        for i in range(5):
            assert f"Header{i}.hpp" in header_basenames, f"Header{i}.hpp missing"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
