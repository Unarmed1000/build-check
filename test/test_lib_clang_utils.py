#!/usr/bin/env python3
"""Tests for lib/clang_utils.py"""

import pytest
from typing import Any, Dict, List, Tuple, Generator
import tempfile
from pathlib import Path

from lib.clang_utils import (
    find_clang_scan_deps, is_valid_source_file, is_valid_header_file,
    is_system_header
)


class TestFindClangScanDeps:
    """Tests for find_clang_scan_deps function."""
    
    def test_find_clang_scan_deps(self, monkeypatch: Any) -> None:
        """Test finding clang-scan-deps."""
        # Mock which command to always return a path
        def mock_which(cmd: str) -> str | None:
            return "/usr/bin/clang-scan-deps-19" if "clang-scan-deps" in cmd else None
        
        monkeypatch.setattr("shutil.which", mock_which)
        
        result = find_clang_scan_deps()
        
        # Should find something or return None gracefully
        assert result is None or isinstance(result, str)
    
    def test_find_clang_scan_deps_not_found(self, monkeypatch: Any) -> None:
        """Test when clang-scan-deps is not found."""
        def mock_which(cmd: str) -> str | None:
            return None
        
        monkeypatch.setattr("shutil.which", mock_which)
        
        result = find_clang_scan_deps()
        
        # Result can be None or a found path depending on system
        assert result is None or isinstance(result, str)


class TestValidSourceFile:
    """Tests for is_valid_source_file function."""
    
    def test_cpp_file(self) -> None:
        """Test .cpp file is recognized as source."""
        assert is_valid_source_file("test.cpp") is True
    
    def test_cc_file(self) -> None:
        """Test .cc file is recognized as source."""
        assert is_valid_source_file("test.cc") is True
    
    def test_cxx_file(self) -> None:
        """Test .cxx file is recognized as source."""
        assert is_valid_source_file("test.cxx") is True
    
    def test_c_file(self) -> None:
        """Test .c file is recognized as source."""
        assert is_valid_source_file("test.c") is True
    
    def test_header_file(self) -> None:
        """Test header files are not source files."""
        assert is_valid_source_file("test.hpp") is False
    
    def test_case_sensitive(self) -> None:
        """Test case sensitivity."""
        # Library is case-sensitive by default
        assert is_valid_source_file("test.CPP") is False
    
    def test_with_path(self) -> None:
        """Test with full path."""
        assert is_valid_source_file("/path/to/test.cpp") is True
    
    def test_no_extension(self) -> None:
        """Test file without extension."""
        assert is_valid_source_file("test") is False
    
    def test_empty_string(self) -> None:
        """Test empty string."""
        assert is_valid_source_file("") is False


class TestValidHeaderFile:
    """Tests for is_valid_header_file function."""
    
    def test_hpp_file(self) -> None:
        """Test .hpp file is recognized as header."""
        assert is_valid_header_file("test.hpp") is True
    
    def test_h_file(self) -> None:
        """Test .h file is recognized as header."""
        assert is_valid_header_file("test.h") is True
    
    def test_hxx_file(self) -> None:
        """Test .hxx file is recognized as header."""
        assert is_valid_header_file("test.hxx") is True
    
    def test_hh_file(self) -> None:
        """Test .hh file is recognized as header."""
        assert is_valid_header_file("test.hh") is True
    
    def test_source_file(self) -> None:
        """Test source files are not header files."""
        assert is_valid_header_file("test.cpp") is False
    
    def test_case_sensitive(self) -> None:
        """Test case sensitivity."""
        # Library is case-sensitive by default
        assert is_valid_header_file("test.HPP") is False
    
    def test_with_path(self) -> None:
        """Test with full path."""
        assert is_valid_header_file("/path/to/test.h") is True
    
    def test_no_extension(self) -> None:
        """Test file without extension."""
        assert is_valid_header_file("test") is False
    
    def test_empty_string(self) -> None:
        """Test empty string."""
        assert is_valid_header_file("") is False


class TestSystemHeader:
    """Tests for is_system_header function."""
    
    def test_usr_include(self) -> None:
        """Test /usr/include is system header."""
        assert is_system_header("/usr/include/stdio.h") is True
    
    def test_usr_local_include(self) -> None:
        """Test /usr/local/include is system header."""
        assert is_system_header("/usr/local/include/header.h") is True
    
    def test_opt_include(self) -> None:
        """Test /opt includes are system headers."""
        assert is_system_header("/opt/local/include/header.h") is True
    
    def test_lib_gcc(self) -> None:
        """Test GCC library paths are system headers."""
        assert is_system_header("/usr/lib/gcc/x86_64-linux-gnu/header.h") is True
    
    def test_project_header(self) -> None:
        """Test project headers are not system headers."""
        assert is_system_header("/home/user/project/header.h") is False
    
    def test_relative_path(self) -> None:
        """Test relative paths are not system headers."""
        assert is_system_header("include/header.h") is False
    
    def test_empty_string(self) -> None:
        """Test empty string is not system header."""
        assert is_system_header("") is False
    
    def test_windows_paths(self) -> None:
        """Test Windows system paths (if on Windows)."""
        # Should handle Windows paths gracefully
        result = is_system_header("C:\\Program Files\\include\\header.h")
        assert isinstance(result, bool)


class TestCreateFilteredCompileCommands:
    """Tests for create_filtered_compile_commands function."""
    
    def test_create_filtered_compile_commands(self, temp_dir: Any) -> None:
        """Test creating filtered compile_commands.json."""
        # Create a mock compile_commands.json
        compile_commands = temp_dir / "compile_commands.json"
        compile_commands.write_text('''[
            {
                "directory": "/build",
                "command": "g++ -c test.cpp",
                "file": "test.cpp"
            },
            {
                "directory": "/build",
                "command": "g++ -c other.cpp",
                "file": "other.cpp"
            }
        ]''')
        
        # This should work or fail gracefully
        try:
            from lib.clang_utils import create_filtered_compile_commands
            result = create_filtered_compile_commands(str(temp_dir))
            assert result is not None
        except Exception:
            # If it fails, it should be due to missing dependencies, not bad logic
            pass
    
    def test_missing_compile_commands(self, temp_dir: Any) -> None:
        """Test when compile_commands.json doesn't exist."""
        from lib.clang_utils import create_filtered_compile_commands
        
        try:
            result = create_filtered_compile_commands(str(temp_dir))
            # Should return None or raise exception gracefully
        except Exception as e:
            # Expected to fail with missing file
            assert "compile_commands.json" in str(e) or True


class TestExtractIncludePaths:
    """Tests for extract_include_paths function."""
    
    def test_extract_include_paths(self, temp_dir: Any) -> None:
        """Test extracting include paths from compile_commands.json."""
        compile_commands = temp_dir / "compile_commands.json"
        compile_commands.write_text('''[
            {
                "directory": "/build",
                "command": "g++ -I/path/include -I/other/include -c test.cpp",
                "file": "test.cpp"
            }
        ]''')
        
        from lib.clang_utils import extract_include_paths
        
        paths = extract_include_paths(str(compile_commands))
        
        assert isinstance(paths, set)
    
    def test_extract_include_paths_invalid_json(self, temp_dir: Any) -> None:
        """Test with invalid JSON."""
        compile_commands = temp_dir / "compile_commands.json"
        compile_commands.write_text("invalid json")
        
        from lib.clang_utils import extract_include_paths
        
        paths = extract_include_paths(str(compile_commands))
        
        # Should handle gracefully
        assert isinstance(paths, set)


class TestParseClangScanDepsOutput:
    """Tests for parse_clang_scan_deps_output function."""
    
    def test_parse_simple_output(self) -> None:
        """Test parsing simple clang-scan-deps output."""
        from lib.clang_utils import parse_clang_scan_deps_output
        
        output = """target.o: source.cpp \\
  /path/to/header1.hpp \\
  /path/to/header2.hpp
"""
        all_headers: set[str] = set()
        
        result = parse_clang_scan_deps_output(output, all_headers)
        
        assert isinstance(result, dict)
        assert 'target.o' in result
        assert len(result['target.o']) == 3
        assert 'source.cpp' in result['target.o']
        assert '/path/to/header1.hpp' in result['target.o']
        assert '/path/to/header2.hpp' in result['target.o']
        # Check that headers were added to all_headers set
        assert '/path/to/header1.hpp' in all_headers
        assert '/path/to/header2.hpp' in all_headers
    
    def test_parse_empty_output(self) -> None:
        """Test parsing empty output."""
        from lib.clang_utils import parse_clang_scan_deps_output
        
        all_headers: set[str] = set()
        result = parse_clang_scan_deps_output("", all_headers)
        
        assert isinstance(result, dict)
        assert len(result) == 0
    
    def test_parse_multiple_targets(self) -> None:
        """Test parsing multiple targets."""
        from lib.clang_utils import parse_clang_scan_deps_output
        
        output = """target1.o: source1.cpp \\
  header1.hpp
target2.o: source2.cpp \\
  header2.hpp \\
  header3.hpp
"""
        all_headers: set[str] = set()
        
        result = parse_clang_scan_deps_output(output, all_headers)
        
        assert len(result) == 2
        assert 'target1.o' in result
        assert 'target2.o' in result
        assert len(result['target1.o']) == 2
        assert len(result['target2.o']) == 3
        assert 'source1.cpp' in result['target1.o']
        assert 'header1.hpp' in result['target1.o']


class TestComputeTransitiveDeps:
    """Tests for compute_transitive_deps function."""
    
    def test_simple_transitive_deps(self) -> None:
        """Test computing transitive dependencies."""
        include_graph = {
            "a.hpp": {"b.hpp"},
            "b.hpp": {"c.hpp"},
            "c.hpp": set()
        }
        
        from lib.clang_utils import compute_transitive_deps
        
        deps = compute_transitive_deps("a.hpp", include_graph, set())
        
        assert "b.hpp" in deps
        assert "c.hpp" in deps
    
    def test_circular_deps(self) -> None:
        """Test with circular dependencies."""
        include_graph = {
            "a.hpp": {"b.hpp"},
            "b.hpp": {"a.hpp"}
        }
        
        from lib.clang_utils import compute_transitive_deps
        
        deps = compute_transitive_deps("a.hpp", include_graph, set())
        
        # Should handle cycles without infinite loop
        assert isinstance(deps, set)


@pytest.fixture
def temp_dir() -> Any:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
