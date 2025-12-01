#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for file classification functionality in lib/clang_utils.py."""

import os
import tempfile
import pytest
from pathlib import Path

from lib.clang_utils import FileType, classify_file, is_third_party_file, is_generated_file
from lib.file_utils import FileClassificationStats, filter_by_file_type


class TestFileType:
    """Tests for FileType enum."""

    def test_file_type_values(self) -> None:
        """Test FileType enum has correct integer values for JSON serialization."""
        assert int(FileType.SYSTEM) == 1
        assert int(FileType.THIRD_PARTY) == 2
        assert int(FileType.GENERATED) == 3
        assert int(FileType.PROJECT) == 4

    def test_file_type_from_int(self) -> None:
        """Test FileType can be constructed from integers."""
        assert FileType(1) == FileType.SYSTEM
        assert FileType(2) == FileType.THIRD_PARTY
        assert FileType(3) == FileType.GENERATED
        assert FileType(4) == FileType.PROJECT


class TestIsGeneratedFile:
    """Tests for is_generated_file() function."""

    def test_protobuf_headers(self) -> None:
        """Test protobuf generated header detection."""
        assert is_generated_file("/path/to/message.pb.h") is True
        assert is_generated_file("/path/to/service.pb.hpp") is True

    def test_protobuf_sources(self) -> None:
        """Test protobuf generated source detection."""
        assert is_generated_file("/path/to/message.pb.cc") is True
        assert is_generated_file("/path/to/service.pb.cpp") is True

    def test_qt_moc_files(self) -> None:
        """Test Qt moc generated file detection."""
        assert is_generated_file("/path/to/moc_widget.h") is True
        assert is_generated_file("/path/to/moc_window.cpp") is True

    def test_qt_ui_files(self) -> None:
        """Test Qt UI generated file detection."""
        assert is_generated_file("/path/to/ui_mainwindow.h") is True

    def test_qt_qrc_files(self) -> None:
        """Test Qt resource generated file detection."""
        assert is_generated_file("/path/to/qrc_resources.h") is True
        assert is_generated_file("/path/to/qrc_icons.cpp") is True

    def test_cmake_config_files(self) -> None:
        """Test CMake generated config file detection."""
        assert is_generated_file("/path/to/ProjectConfig.h") is True
        assert is_generated_file("/path/to/LibraryConfig.hpp") is True

    def test_cmake_export_files(self) -> None:
        """Test CMake generated export file detection."""
        assert is_generated_file("/path/to/library_export.h") is True
        assert is_generated_file("/path/to/MyLibExport.h") is True

    def test_generic_autogen_files(self) -> None:
        """Test generic autogen pattern detection."""
        assert is_generated_file("/path/to/parser_generated.h") is True
        assert is_generated_file("/path/to/lexer_autogen.cpp") is True
        assert is_generated_file("/path/to/codegen_autogen.h") is True

    def test_non_generated_files(self) -> None:
        """Test that normal project files are not classified as generated."""
        assert is_generated_file("/path/to/MyClass.h") is False
        assert is_generated_file("/path/to/main.cpp") is False
        assert is_generated_file("/path/to/util.hpp") is False
        assert is_generated_file("/path/to/test_something.cpp") is False

    def test_case_sensitivity(self) -> None:
        """Test that pattern matching is case-sensitive."""
        # Lowercase extensions should not match if pattern expects .h/.cpp
        assert is_generated_file("/path/to/message.PB.H") is False
        assert is_generated_file("/path/to/MOC_widget.h") is False


class TestIsThirdPartyFile:
    """Tests for is_third_party_file() function.

    NOTE: is_third_party_file() cannot accurately determine third-party status
    without project root context. It returns False by design. Actual classification
    is done by classify_file() using compile_commands.json data.
    """

    def test_third_party_outside_build_dir(self) -> None:
        """Test that function returns False (cannot determine without project context)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = os.path.join(tmpdir, "build")
            os.makedirs(build_dir)

            # File outside build directory - cannot determine third-party status
            third_party_file = "/some/external/lib/header.h"
            # Function returns False because it cannot determine without project root
            assert is_third_party_file(third_party_file, build_dir) is False

    def test_project_file_inside_build_dir(self) -> None:
        """Test that files inside build_dir return False (indeterminate)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = os.path.join(tmpdir, "build")
            os.makedirs(build_dir)

            # File inside build directory
            project_file = os.path.join(build_dir, "../src/MyClass.h")
            project_file = os.path.realpath(project_file)

            # Create parent directory to make realpath work correctly
            src_dir = os.path.dirname(project_file)
            os.makedirs(src_dir, exist_ok=True)
            Path(project_file).touch()

            assert is_third_party_file(project_file, build_dir) is False

    def test_system_headers_not_third_party(self) -> None:
        """Test that system headers are correctly identified as not third-party."""
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = os.path.join(tmpdir, "build")
            os.makedirs(build_dir)

            # System headers are explicitly recognized
            assert is_third_party_file("/usr/include/stdio.h", build_dir) is False
            assert is_third_party_file("/usr/local/include/boost/shared_ptr.hpp", build_dir) is False
            assert is_third_party_file("/lib/x86_64-linux-gnu/glib-2.0/include/glibconfig.h", build_dir) is False

    def test_symlink_resolution(self) -> None:
        """Test that symlinks don't affect the result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = os.path.join(tmpdir, "build")
            os.makedirs(build_dir)

            # Create a file inside build directory
            src_dir = os.path.join(os.path.dirname(build_dir), "src")
            os.makedirs(src_dir, exist_ok=True)
            real_file = os.path.join(src_dir, "real.h")
            Path(real_file).touch()

            # Create symlink outside build directory pointing to real file
            link_dir = os.path.join(tmpdir, "links")
            os.makedirs(link_dir, exist_ok=True)
            link_file = os.path.join(link_dir, "link.h")
            os.symlink(real_file, link_file)

            # Returns False (cannot determine without project context)
            assert is_third_party_file(link_file, build_dir) is False


class TestClassifyFile:
    """Tests for classify_file() function."""

    def test_classify_system_headers(self) -> None:
        """Test system header classification has highest priority."""
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = os.path.join(tmpdir, "build")
            os.makedirs(build_dir)

            assert classify_file("/usr/include/stdio.h", build_dir) == FileType.SYSTEM
            assert classify_file("/usr/local/include/boost/shared_ptr.hpp", build_dir) == FileType.SYSTEM

    def test_classify_generated_files(self) -> None:
        """Test generated file classification (after system check)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = os.path.join(tmpdir, "build")
            os.makedirs(build_dir)

            # Generated file outside build directory
            assert classify_file("/external/lib/message.pb.h", build_dir) == FileType.GENERATED
            assert classify_file("/external/lib/moc_widget.cpp", build_dir) == FileType.GENERATED

    def test_classify_third_party_files(self) -> None:
        """Test third-party file classification.

        Note: Without project root, classify_file cannot distinguish third-party
        from project files. Files outside system/generated will default to PROJECT.
        Use classify_file_with_project_root for accurate third-party detection.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = os.path.join(tmpdir, "build")
            os.makedirs(build_dir)

            # Without project context, cannot determine third-party status
            # These will be classified as PROJECT (default)
            assert classify_file("/external/lib/library.h", build_dir) == FileType.PROJECT
            assert classify_file("/home/user/vendor/include/custom.hpp", build_dir) == FileType.PROJECT

    def test_classify_project_files(self) -> None:
        """Test project file classification (default case)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = os.path.join(tmpdir, "build")
            os.makedirs(build_dir)

            # Files inside project (parent of build dir)
            src_dir = os.path.join(os.path.dirname(build_dir), "src")
            os.makedirs(src_dir, exist_ok=True)

            project_file = os.path.join(src_dir, "MyClass.h")
            Path(project_file).touch()

            assert classify_file(project_file, build_dir) == FileType.PROJECT

    def test_classification_priority_order(self) -> None:
        """Test that classification checks happen in correct priority order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = os.path.join(tmpdir, "build")
            os.makedirs(build_dir)

            # System-like generated file (system has priority)
            # Note: Actual /usr files would be system, this tests the logic
            assert classify_file("/usr/local/include/config.pb.h", build_dir) == FileType.SYSTEM

            # Third-party generated file (generated has priority over third-party)
            assert classify_file("/vendor/lib/proto.pb.h", build_dir) == FileType.GENERATED


class TestFileClassificationStats:
    """Tests for FileClassificationStats dataclass."""

    def test_stats_creation(self) -> None:
        """Test FileClassificationStats can be created with all fields."""
        stats = FileClassificationStats(total=1000, system=350, third_party=120, generated=80, project=450)

        assert stats.total == 1000
        assert stats.system == 350
        assert stats.third_party == 120
        assert stats.generated == 80
        assert stats.project == 450

    def test_stats_sum_validation(self) -> None:
        """Test that category counts sum to total."""
        stats = FileClassificationStats(total=1000, system=350, third_party=120, generated=80, project=450)

        assert stats.system + stats.third_party + stats.generated + stats.project == stats.total


class TestFilterByFileType:
    """Tests for filter_by_file_type() function."""

    def test_filter_system_headers(self) -> None:
        """Test filtering out system headers."""
        files = {"/usr/include/stdio.h", "/project/src/MyClass.h", "/usr/local/include/boost/ptr.hpp", "/project/src/main.cpp"}

        file_types = {
            "/usr/include/stdio.h": FileType.SYSTEM,
            "/project/src/MyClass.h": FileType.PROJECT,
            "/usr/local/include/boost/ptr.hpp": FileType.SYSTEM,
            "/project/src/main.cpp": FileType.PROJECT,
        }

        filtered, stats = filter_by_file_type(files, file_types, exclude_types={FileType.SYSTEM})

        assert filtered == {"/project/src/MyClass.h", "/project/src/main.cpp"}
        assert stats.total == 4
        assert stats.system == 2
        assert stats.project == 2

    def test_filter_multiple_types(self) -> None:
        """Test filtering multiple file types."""
        files = {"/usr/include/stdio.h", "/project/src/MyClass.h", "/vendor/lib/third.h", "/project/build/generated.pb.h", "/project/src/main.cpp"}

        file_types = {
            "/usr/include/stdio.h": FileType.SYSTEM,
            "/project/src/MyClass.h": FileType.PROJECT,
            "/vendor/lib/third.h": FileType.THIRD_PARTY,
            "/project/build/generated.pb.h": FileType.GENERATED,
            "/project/src/main.cpp": FileType.PROJECT,
        }

        filtered, stats = filter_by_file_type(files, file_types, exclude_types={FileType.SYSTEM, FileType.GENERATED})

        assert filtered == {"/project/src/MyClass.h", "/vendor/lib/third.h", "/project/src/main.cpp"}
        assert stats.total == 5
        assert stats.system == 1
        assert stats.generated == 1
        assert stats.third_party == 1
        assert stats.project == 2

    def test_filter_no_exclusions(self) -> None:
        """Test that empty exclude_types returns all files."""
        files = {"/usr/include/stdio.h", "/project/src/MyClass.h"}

        file_types = {"/usr/include/stdio.h": FileType.SYSTEM, "/project/src/MyClass.h": FileType.PROJECT}

        filtered, stats = filter_by_file_type(files, file_types, exclude_types=set())

        assert filtered == files
        assert stats.total == 2
        assert stats.system == 1
        assert stats.project == 1

    def test_filter_preserves_files_not_in_type_map(self) -> None:
        """Test that files not in file_types map are preserved (default to project)."""
        files = {"/project/src/MyClass.h", "/project/src/unknown.h"}

        file_types = {
            "/project/src/MyClass.h": FileType.PROJECT,
            # unknown.h intentionally missing
        }

        filtered, stats = filter_by_file_type(files, file_types, exclude_types={FileType.SYSTEM})

        # Both files should be kept (unknown treated as PROJECT by default)
        assert filtered == files
        assert stats.total == 2
        assert stats.project == 2
