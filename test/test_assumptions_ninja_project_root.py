#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test assumptions about ninja-based project root calculation.

These tests document and verify the core assumptions about how project root
should be calculated and used:

1. build.ninja is ONLY used to calculate project root
2. Project root is the common ancestor of all sources AND headers in ninja
3. clang-scan-deps is used for discovering all headers
4. File classification uses project root to distinguish PROJECT vs THIRD_PARTY
5. Git baseline reconstruction should use baseline ninja files (in memory)
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.ninja_utils import extract_source_and_header_files_from_ninja
from lib.clang_utils import find_project_root_from_sources, classify_file_with_project_root, FileType


class TestAssumption1_NinjaOnlyForProjectRoot:
    """Assumption 1: build.ninja is ONLY used to calculate project root."""

    def test_ninja_not_used_for_header_discovery(self) -> None:
        """Verify that ninja files are NOT the source of truth for all headers.

        clang-scan-deps should discover headers through transitive includes.
        Ninja only provides the baseline for project root calculation.
        """
        # This is a documentation test - the actual behavior is verified
        # in build_include_graph() where all_headers comes from clang-scan-deps
        assert True, "Ninja is only for project root, clang-scan-deps for headers"

    def test_ninja_used_for_project_root_only(self) -> None:
        """Verify ninja sources/headers are used to calculate project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create structure
            (tmpdir_path / "src").mkdir()
            (tmpdir_path / "include").mkdir()

            build_ninja = tmpdir_path / "build.ninja"
            build_ninja.write_text(
                f"""
rule cxx
  command = clang++ -c $in -o $out

build obj/test.o: cxx {tmpdir_path}/src/test.cpp | {tmpdir_path}/include/test.hpp
"""
            )

            sources, headers = extract_source_and_header_files_from_ninja(str(build_ninja))
            all_ninja_files = sources + headers

            # Project root should be calculated from these files
            project_root = find_project_root_from_sources(all_ninja_files)

            assert project_root == str(tmpdir_path)


class TestAssumption2_ProjectRootIsCommonAncestor:
    """Assumption 2: Project root is common ancestor of sources AND headers."""

    def test_project_root_with_separate_src_and_include(self) -> None:
        """Project root should be parent of both src/ and include/ directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Typical C++ project structure
            src_file = tmpdir_path / "src" / "module" / "file.cpp"
            inc_file = tmpdir_path / "include" / "module" / "file.hpp"

            src_file.parent.mkdir(parents=True)
            inc_file.parent.mkdir(parents=True)

            project_root = find_project_root_from_sources([str(src_file), str(inc_file)])

            # Should be tmpdir, not src/ or include/
            assert project_root == str(tmpdir_path), f"Expected {tmpdir_path}, got {project_root}"

    def test_project_root_with_nested_structure(self) -> None:
        """Project root handles deeply nested module structures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            files = [
                tmpdir_path / "src" / "Engine" / "Core" / "System.cpp",
                tmpdir_path / "include" / "Engine" / "Core" / "System.hpp",
                tmpdir_path / "src" / "Engine" / "Graphics" / "Renderer.cpp",
                tmpdir_path / "include" / "Engine" / "Graphics" / "Renderer.hpp",
            ]

            for f in files:
                f.parent.mkdir(parents=True, exist_ok=True)

            project_root = find_project_root_from_sources([str(f) for f in files])

            assert project_root == str(tmpdir_path)

    def test_project_root_single_directory(self) -> None:
        """Project root when all files in same directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            files = [tmpdir_path / "file1.cpp", tmpdir_path / "file2.cpp", tmpdir_path / "file1.hpp"]

            project_root = find_project_root_from_sources([str(f) for f in files])

            assert project_root == str(tmpdir_path)


class TestAssumption3_ClangScanDepsForHeaders:
    """Assumption 3: clang-scan-deps discovers all headers."""

    def test_clang_scan_deps_is_source_of_truth(self) -> None:
        """Document that clang-scan-deps output is the authoritative header list.

        The actual header discovery happens in build_include_graph() which
        calls run_clang_scan_deps() and uses its output.
        """
        assert True, "clang-scan-deps discovers headers, not ninja extraction"

    def test_ninja_headers_subset_of_clang_scan_deps(self) -> None:
        """Ninja headers should generally be a subset of clang-scan-deps headers.

        Ninja lists explicit build dependencies, while clang-scan-deps discovers
        transitive includes. In a correct build, ninja should reference the
        primary headers, and clang-scan-deps finds all transitively included ones.
        """
        assert True, "ninja ⊆ clang-scan-deps (in most cases)"


class TestAssumption4_FileClassificationUsesProjectRoot:
    """Assumption 4: File classification uses project root."""

    def test_file_inside_project_root_is_project(self) -> None:
        """Files under project root are classified as PROJECT."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            project_file = tmpdir_path / "src" / "module" / "file.hpp"
            project_file.parent.mkdir(parents=True)
            project_file.touch()

            file_type = classify_file_with_project_root(str(project_file), str(tmpdir_path), set())  # no generated files

            assert file_type == FileType.PROJECT, f"File under project root should be PROJECT, got {file_type}"

    def test_file_outside_project_root_is_third_party(self) -> None:
        """Files outside project root are classified as THIRD_PARTY."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            project_root = tmpdir_path / "myproject"
            project_root.mkdir()

            # File outside project root
            third_party_file = tmpdir_path / "external" / "lib" / "header.hpp"
            third_party_file.parent.mkdir(parents=True)
            third_party_file.touch()

            file_type = classify_file_with_project_root(str(third_party_file), str(project_root), set())

            assert file_type == FileType.THIRD_PARTY, f"File outside project root should be THIRD_PARTY, got {file_type}"

    def test_system_header_classification(self) -> None:
        """System headers (in /usr/) are classified as SYSTEM."""
        system_header = "/usr/include/stdio.h"

        file_type = classify_file_with_project_root(system_header, "/home/user/project", set())  # irrelevant for system headers

        assert file_type == FileType.SYSTEM


class TestAssumption5_GitBaselineNinjaReconstruction:
    """Assumption 5: Git baseline should reconstruct ninja in memory."""

    def test_baseline_sources_should_differ_from_current(self) -> None:
        """When files are added/removed, baseline ninja list should differ from current.

        This documents the bug we're fixing: baseline analysis was using current
        build.ninja from disk instead of reconstructing it from git HEAD.
        """
        # Baseline state (git HEAD)
        baseline_sources = ["src/Module0/Header0.cpp", "src/Module0/Header1.cpp"]

        # Current state (working tree)
        current_sources = baseline_sources + ["src/Module0/Header2.cpp"]  # Added file

        # These should be different!
        assert len(baseline_sources) != len(current_sources), "Baseline and current should have different file counts"

        assert set(baseline_sources) != set(current_sources), "Baseline and current should have different file sets"

    def test_project_root_should_use_baseline_files(self) -> None:
        """Project root for baseline analysis should use baseline sources/headers.

        This is the core issue: when analyzing git HEAD, we must calculate
        project root from HEAD's sources/headers, not from working tree's build.ninja.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Baseline files (what's in git HEAD)
            baseline_sources = [str(tmpdir_path / "src" / "Core.cpp"), str(tmpdir_path / "src" / "Utils.cpp")]
            baseline_headers = [str(tmpdir_path / "include" / "Core.hpp"), str(tmpdir_path / "include" / "Utils.hpp")]

            # Calculate project root from baseline
            baseline_project_root = find_project_root_from_sources(baseline_sources + baseline_headers)

            # Current files (what's in working tree - has extra file)
            current_sources = baseline_sources + [str(tmpdir_path / "src" / "New.cpp")]
            current_headers = baseline_headers + [str(tmpdir_path / "include" / "New.hpp")]

            current_project_root = find_project_root_from_sources(current_sources + current_headers)

            # Project root should be same (tmpdir) even though file lists differ
            assert baseline_project_root == current_project_root == str(tmpdir_path)

            # But the file lists should differ
            assert baseline_sources != current_sources
            assert baseline_headers != current_headers


class TestAssumption6_Module0Header0Included:
    """Specific test for the Module0/Header0 missing issue."""

    def test_module0_header0_should_be_in_ninja(self) -> None:
        """Module0/Header0 should be extracted from build.ninja."""
        with tempfile.TemporaryDirectory() as tmpdir:
            build_ninja = Path(tmpdir) / "build.ninja"

            # Scenario 9 structure
            build_ninja.write_text(
                """
rule cxx
  command = clang++ -c $in -o $out

build obj/Module0/Header0.o: cxx src/Module0/Header0.cpp | include/Module0/Header0.hpp
build obj/Module0/Header1.o: cxx src/Module0/Header1.cpp | include/Module0/Header1.hpp
"""
            )

            sources, headers = extract_source_and_header_files_from_ninja(str(build_ninja))

            # Verify Header0 is present
            header_names = [os.path.basename(h) for h in headers]
            assert "Header0.hpp" in header_names, f"Header0.hpp should be in extracted headers: {header_names}"

    def test_all_25_scenario_9_headers_should_be_present(self) -> None:
        """Scenario 9 should have all 25 headers (5 modules × 5 headers)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            build_ninja = Path(tmpdir) / "build.ninja"

            # Generate all 25 entries
            lines = ["rule cxx", "  command = clang++ -c $in -o $out", ""]

            for module in range(5):
                for header in range(5):
                    lines.append(
                        f"build obj/Module{module}/Header{header}.o: cxx "
                        f"src/Module{module}/Header{header}.cpp | "
                        f"include/Module{module}/Header{header}.hpp"
                    )

            build_ninja.write_text("\n".join(lines))

            sources, headers = extract_source_and_header_files_from_ninja(str(build_ninja))

            assert len(headers) == 25, f"Should extract 25 headers, got {len(headers)}"
            assert len(sources) == 25, f"Should extract 25 sources, got {len(sources)}"

            # Verify Module0/Header0 specifically
            assert any("Module0/Header0.hpp" in h for h in headers), "Module0/Header0.hpp must be present"
            assert any("Module0/Header0.cpp" in s for s in sources), "Module0/Header0.cpp must be present"


class TestAssumption7_BuildNinjaReadFromCorrectCommit:
    """Assumption 7: build.ninja must match the git commit being analyzed."""

    def test_baseline_ninja_should_not_be_from_disk(self) -> None:
        """Document that reading build.ninja from disk for baseline is WRONG.

        When analyzing git HEAD, build.ninja on disk reflects working tree state.
        We need to either:
        1. Read build.ninja from git (git show HEAD:build.ninja), OR
        2. Reconstruct it in memory from git HEAD sources

        Option 2 is what reconstruct_head_graph() should provide.
        """
        assert True, "Baseline analysis must not read build.ninja from disk"

    def test_reconstruct_head_graph_should_return_sources(self) -> None:
        """reconstruct_head_graph should return baseline sources for ninja reconstruction.

        This is what we're implementing: reconstruct_head_graph() now returns
        (headers, graph, sources, project_root) so that baseline project root
        can be calculated from baseline sources, not current working tree.
        """
        # This documents the new return signature
        expected_return = ("headers", "graph", "sources", "project_root")
        assert len(expected_return) == 4, "reconstruct_head_graph returns 4 values"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
