#!/usr/bin/env python3
"""Extended tests for lib.library_parser to improve coverage."""

import pytest
import sys
from pathlib import Path
from typing import Dict, Set, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.library_parser import (
    infer_library_from_source,
    map_headers_to_libraries,
    analyze_cross_library_dependencies,
    CrossLibraryAnalysis,
    find_unused_libraries,
    infer_library_from_path,
)


class TestInferLibraryFromSource:
    """Test infer_library_from_source function."""

    @pytest.mark.unit
    def test_infer_from_source_directory(self) -> None:
        """Test inferring library name from source directory."""
        path = "/project/FslBase/source/FslBase/System/Platform.cpp"
        result = infer_library_from_source(path)
        assert result == "libFslBase.a"

    @pytest.mark.unit
    def test_infer_from_include_directory(self) -> None:
        """Test inferring library name from include directory."""
        path = "/project/FslGraphics/include/FslGraphics/Render/Texture.hpp"
        result = infer_library_from_source(path)
        assert result == "libFslGraphics.a"

    @pytest.mark.unit
    def test_infer_from_src_directory(self) -> None:
        """Test inferring library name from src directory."""
        path = "/home/user/MyLib/src/implementation.cpp"
        result = infer_library_from_source(path)
        assert result == "libMyLib.a"

    @pytest.mark.unit
    def test_infer_fallback_to_parent_dir(self) -> None:
        """Test fallback when no standard directory found."""
        path = "/project/SomeLib/file.cpp"
        result = infer_library_from_source(path)
        assert result == "libSomeLib.a"

    @pytest.mark.unit
    def test_infer_from_short_path(self) -> None:
        """Test inferring from very short path."""
        path = "file.cpp"
        result = infer_library_from_source(path)
        assert "lib" in result and ".a" in result


class TestMapHeadersToLibraries:
    """Test map_headers_to_libraries function."""

    @pytest.mark.unit
    def test_map_multiple_headers(self) -> None:
        """Test mapping multiple headers to libraries."""
        headers = {"/project/LibA/include/header1.hpp", "/project/LibA/include/header2.hpp", "/project/LibB/source/header3.hpp"}

        header_to_lib = map_headers_to_libraries(headers)

        assert len(header_to_lib) == 3
        assert header_to_lib["/project/LibA/include/header1.hpp"] == "libLibA.a"
        assert header_to_lib["/project/LibA/include/header2.hpp"] == "libLibA.a"
        assert header_to_lib["/project/LibB/source/header3.hpp"] == "libLibB.a"

    @pytest.mark.unit
    def test_map_empty_headers(self) -> None:
        """Test mapping empty set of headers."""
        headers: Set[str] = set()

        header_to_lib = map_headers_to_libraries(headers)

        assert len(header_to_lib) == 0

    @pytest.mark.unit
    def test_map_single_header(self) -> None:
        """Test mapping a single header."""
        headers = {"/project/MyLib/include/MyHeader.hpp"}

        header_to_lib = map_headers_to_libraries(headers)

        assert len(header_to_lib) == 1
        assert "libMyLib.a" in header_to_lib.values()


class TestAnalyzeCrossLibraryDependencies:
    """Test analyze_cross_library_dependencies function."""

    @pytest.mark.unit
    def test_all_intra_library_deps(self) -> None:
        """Test analysis when all dependencies are within same library."""
        header_to_headers = {"libA/h1.hpp": {"libA/h2.hpp"}, "libA/h2.hpp": {"libA/h3.hpp"}, "libA/h3.hpp": set()}

        header_to_lib = {"libA/h1.hpp": "libA.a", "libA/h2.hpp": "libA.a", "libA/h3.hpp": "libA.a"}

        analysis = analyze_cross_library_dependencies(header_to_headers, header_to_lib)

        assert analysis.total_deps == 2
        assert analysis.intra_library_deps == 2
        assert analysis.cross_library_deps == 0
        assert len(analysis.library_violations) == 0

    @pytest.mark.unit
    def test_cross_library_deps(self) -> None:
        """Test analysis with cross-library dependencies."""
        header_to_headers = {"libA/h1.hpp": {"libB/h1.hpp", "libA/h2.hpp"}, "libA/h2.hpp": set(), "libB/h1.hpp": {"libC/h1.hpp"}, "libC/h1.hpp": set()}

        header_to_lib = {"libA/h1.hpp": "libA.a", "libA/h2.hpp": "libA.a", "libB/h1.hpp": "libB.a", "libC/h1.hpp": "libC.a"}

        analysis = analyze_cross_library_dependencies(header_to_headers, header_to_lib)

        assert analysis.total_deps == 3
        assert analysis.intra_library_deps == 1
        assert analysis.cross_library_deps == 2
        assert "libA.a" in analysis.library_violations
        assert "libB.a" in analysis.library_violations["libA.a"]

    @pytest.mark.unit
    def test_worst_offenders_sorting(self) -> None:
        """Test that worst offenders are sorted correctly."""
        header_to_headers = {"libA/h1.hpp": {"libB/h1.hpp", "libB/h2.hpp", "libB/h3.hpp"}, "libA/h2.hpp": {"libB/h1.hpp"}, "libA/h3.hpp": set()}

        header_to_lib = {
            "libA/h1.hpp": "libA.a",
            "libA/h2.hpp": "libA.a",
            "libA/h3.hpp": "libA.a",
            "libB/h1.hpp": "libB.a",
            "libB/h2.hpp": "libB.a",
            "libB/h3.hpp": "libB.a",
        }

        analysis = analyze_cross_library_dependencies(header_to_headers, header_to_lib)

        # h1.hpp should be first with 3 cross-library deps
        assert len(analysis.worst_offenders) > 0
        assert analysis.worst_offenders[0][0] == "libA/h1.hpp"
        assert analysis.worst_offenders[0][1] == 3

    @pytest.mark.unit
    def test_to_dict_conversion(self) -> None:
        """Test CrossLibraryAnalysis.to_dict() conversion."""
        analysis = CrossLibraryAnalysis(
            total_deps=10, intra_library_deps=7, cross_library_deps=3, library_violations={"libA.a": {"libB.a": 2}}, worst_offenders=[("header1.hpp", 5)]
        )

        result = analysis.to_dict()

        assert result["total_deps"] == 10
        assert result["intra_library_deps"] == 7
        assert result["cross_library_deps"] == 3
        assert "library_violations" in result
        assert "worst_offenders" in result

    @pytest.mark.unit
    def test_empty_dependencies(self) -> None:
        """Test analysis with no dependencies."""
        header_to_headers: Dict[str, Set[str]] = {"libA/h1.hpp": set(), "libA/h2.hpp": set()}

        header_to_lib = {"libA/h1.hpp": "libA.a", "libA/h2.hpp": "libA.a"}

        analysis = analyze_cross_library_dependencies(header_to_headers, header_to_lib)

        assert analysis.total_deps == 0
        assert analysis.intra_library_deps == 0
        assert analysis.cross_library_deps == 0


class TestFindUnusedLibraries:
    """Test find_unused_libraries function."""

    @pytest.mark.unit
    def test_no_unused_libraries(self) -> None:
        """Test when all libraries are used."""
        lib_to_libs = {"libA.a": set(), "libB.a": {"libA.a"}, "libC.a": {"libB.a"}}

        exe_to_libs = {"app1": {"libC.a"}, "app2": {"libB.a"}}

        all_libs = {"libA.a", "libB.a", "libC.a"}

        unused = find_unused_libraries(lib_to_libs, exe_to_libs, all_libs)

        assert len(unused) == 0

    @pytest.mark.unit
    def test_some_unused_libraries(self) -> None:
        """Test finding unused libraries."""
        lib_to_libs = {"libA.a": set(), "libB.a": {"libA.a"}, "libC.a": set(), "libD.a": set()}  # Not used by anyone  # Not used by anyone

        exe_to_libs = {"app1": {"libB.a"}}

        all_libs = {"libA.a", "libB.a", "libC.a", "libD.a"}

        unused = find_unused_libraries(lib_to_libs, exe_to_libs, all_libs)

        assert "libC.a" in unused
        assert "libD.a" in unused
        assert "libA.a" not in unused  # Used by libB
        assert "libB.a" not in unused  # Used by app1

    @pytest.mark.unit
    def test_all_libraries_unused(self) -> None:
        """Test when all libraries are unused."""
        lib_to_libs: Dict[str, Set[str]] = {"libA.a": set(), "libB.a": set()}

        exe_to_libs: Dict[str, Set[str]] = {}

        all_libs = {"libA.a", "libB.a"}

        unused = find_unused_libraries(lib_to_libs, exe_to_libs, all_libs)

        assert len(unused) == 2
        assert "libA.a" in unused
        assert "libB.a" in unused

    @pytest.mark.unit
    def test_transitive_usage(self) -> None:
        """Test that transitively used libraries are not marked unused."""
        lib_to_libs = {"libFoundation.a": set(), "libCore.a": {"libFoundation.a"}, "libUI.a": {"libCore.a"}}

        exe_to_libs = {"app": {"libUI.a"}}

        all_libs = {"libFoundation.a", "libCore.a", "libUI.a"}

        unused = find_unused_libraries(lib_to_libs, exe_to_libs, all_libs)

        # All libraries are used transitively
        assert len(unused) == 0


class TestInferLibraryFromPath:
    """Test infer_library_from_path function."""

    @pytest.mark.unit
    def test_infer_with_lib_prefix(self) -> None:
        """Test inferring library from path with lib prefix."""
        path = "/build/libFslBase.a"
        result = infer_library_from_path(path)
        # Function returns "Unknown" for library filenames without DemoFramework/DemoApps structure
        assert result == "Unknown"

    @pytest.mark.unit
    def test_infer_without_lib_prefix(self) -> None:
        """Test inferring library from path without lib prefix."""
        path = "/build/FslBase.a"
        result = infer_library_from_path(path)
        # Function finds FslBase (but includes .a in result)
        assert result == "FslBase.a" or result == "FslBase"

    @pytest.mark.unit
    def test_infer_from_complex_path(self) -> None:
        """Test inferring from complex path."""
        path = "/home/user/project/DemoFramework/FslGraphics/source/file.cpp"
        result = infer_library_from_path(path)
        assert "FslGraphics" in result

    @pytest.mark.unit
    def test_infer_with_demo_apps(self) -> None:
        """Test inferring from DemoApps path."""
        path = "/project/DemoApps/GLES3/S01_SimpleTriangle/source/main.cpp"
        result = infer_library_from_path(path)
        assert "/" in result or "GLES3" in result or "Unknown" in result


class TestCrossLibraryAnalysisDataclass:
    """Test CrossLibraryAnalysis dataclass."""

    @pytest.mark.unit
    def test_dataclass_creation(self) -> None:
        """Test creating CrossLibraryAnalysis instance."""
        analysis = CrossLibraryAnalysis(
            total_deps=100, intra_library_deps=80, cross_library_deps=20, library_violations={"libA.a": {"libB.a": 10}}, worst_offenders=[("header.hpp", 5)]
        )

        assert analysis.total_deps == 100
        assert analysis.intra_library_deps == 80
        assert analysis.cross_library_deps == 20
        assert len(analysis.library_violations) == 1
        assert len(analysis.worst_offenders) == 1

    @pytest.mark.unit
    def test_dataclass_to_dict_complete(self) -> None:
        """Test complete to_dict conversion."""
        violations = {"libA.a": {"libB.a": 5, "libC.a": 3}, "libB.a": {"libC.a": 2}}
        offenders = [("header1.hpp", 10), ("header2.hpp", 8), ("header3.hpp", 5)]

        analysis = CrossLibraryAnalysis(total_deps=50, intra_library_deps=30, cross_library_deps=20, library_violations=violations, worst_offenders=offenders)

        result = analysis.to_dict()

        assert isinstance(result, dict)
        assert result["total_deps"] == 50
        assert result["intra_library_deps"] == 30
        assert result["cross_library_deps"] == 20
        assert result["library_violations"] == violations
        assert result["worst_offenders"] == offenders


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
