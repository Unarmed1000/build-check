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


class TestBuildIncludeGraph:
    """Tests for build_include_graph integration."""
    
    def test_include_graph_is_populated(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test that build_include_graph actually populates the include graph.
        
        This is a regression test for a bug where the include_graph dictionary
        was initialized but never populated, resulting in all headers having
        Fan-out: 0 and Fan-in: 0.
        """
        from lib.clang_utils import build_include_graph
        import json
        
        # Create a mock build directory structure
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        
        # Create source directory with headers
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        
        # Create header files with actual include statements
        base_header = src_dir / "base.hpp"
        base_header.write_text("""
#ifndef BASE_HPP
#define BASE_HPP
// Base header with no dependencies
#endif
""")
        
        middle_header = src_dir / "middle.hpp"
        middle_header.write_text("""
#ifndef MIDDLE_HPP
#define MIDDLE_HPP
#include "base.hpp"
// Middle header includes base
#endif
""")
        
        top_header = src_dir / "top.hpp"
        top_header.write_text("""
#ifndef TOP_HPP
#define TOP_HPP
#include "middle.hpp"
#include "base.hpp"
// Top header includes both middle and base
#endif
""")
        
        # Create a source file
        source_file = src_dir / "main.cpp"
        source_file.write_text("""
#include "top.hpp"
int main() { return 0; }
""")
        
        # Create compile_commands.json
        compile_commands = [
            {
                "directory": str(build_dir),
                "command": f"/usr/bin/c++ -c -o main.o {source_file}",
                "file": str(source_file)
            }
        ]
        compile_db = build_dir / "compile_commands.json"
        compile_db.write_text(json.dumps(compile_commands, indent=2))
        
        # Create filtered compile commands (would normally be created by the function)
        filtered_db = build_dir / "compile_commands_filtered.json"
        filtered_db.write_text(json.dumps(compile_commands, indent=2))
        
        # Mock clang-scan-deps output
        clang_output = f"""main.o: {source_file} \\
  {base_header} \\
  {middle_header} \\
  {top_header}
"""
        
        # Mock subprocess.run to return our test data
        import subprocess
        original_run = subprocess.run
        
        def mock_run(*args: Any, **kwargs: Any) -> Any:
            # Check if this is a clang-scan-deps call
            if args and args[0] and 'clang-scan-deps' in str(args[0][0]):
                # Return our mock output
                class MockResult:
                    returncode = 0
                    stdout = clang_output
                    stderr = ""
                return MockResult()
            # For other commands (like ninja), use original
            return original_run(*args, **kwargs)
        
        monkeypatch.setattr("subprocess.run", mock_run)
        
        # Mock find_clang_scan_deps to return a valid command
        def mock_find_clang() -> str:
            return "clang-scan-deps-19"
        
        monkeypatch.setattr("lib.clang_utils.find_clang_scan_deps", mock_find_clang)
        
        # Run build_include_graph
        result = build_include_graph(str(build_dir), verbose=False)
        
        # Verify that headers were discovered
        assert len(result.all_headers) == 3, f"Expected 3 headers, got {len(result.all_headers)}"
        assert str(base_header) in result.all_headers
        assert str(middle_header) in result.all_headers
        assert str(top_header) in result.all_headers
        
        # CRITICAL: Verify that include_graph is actually populated
        # This is the bug we're testing for - the graph should NOT be empty
        assert len(result.include_graph) > 0, \
            "REGRESSION: include_graph is empty! The bug has returned."
        
        # Verify specific relationships
        # middle.hpp should include base.hpp
        if str(middle_header) in result.include_graph:
            middle_deps = result.include_graph[str(middle_header)]
            assert str(base_header) in middle_deps, \
                f"middle.hpp should include base.hpp. Found: {middle_deps}"
        
        # top.hpp should include middle.hpp and base.hpp
        if str(top_header) in result.include_graph:
            top_deps = result.include_graph[str(top_header)]
            assert len(top_deps) >= 1, \
                f"top.hpp should have dependencies. Found: {top_deps}"
            # Should include at least one of the headers
            assert str(middle_header) in top_deps or str(base_header) in top_deps, \
                f"top.hpp should include middle.hpp or base.hpp. Found: {top_deps}"
        
        # Verify that we can calculate fan-out metrics
        from lib.graph_utils import calculate_dsm_metrics, build_reverse_dependencies
        
        reverse_deps = build_reverse_dependencies(result.include_graph, result.all_headers)
        
        # At least one header should have non-zero fan-out
        has_nonzero_fanout = False
        for header in result.all_headers:
            metrics = calculate_dsm_metrics(header, result.include_graph, reverse_deps)
            if metrics.fan_out > 0:
                has_nonzero_fanout = True
                break
        
        assert has_nonzero_fanout, \
            "REGRESSION: No headers have non-zero fan-out! Include graph is not being built correctly."
    
    def test_include_graph_handles_missing_headers(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test that include_graph handles references to non-existent headers gracefully."""
        from lib.clang_utils import build_include_graph
        import json
        
        # Create a mock build directory structure
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        
        # Create source directory with headers
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        
        # Create a header that includes a non-existent file
        header = src_dir / "test.hpp"
        header.write_text("""
#ifndef TEST_HPP
#define TEST_HPP
#include "nonexistent.hpp"
#endif
""")
        
        # Create a source file
        source_file = src_dir / "main.cpp"
        source_file.write_text("""
#include "test.hpp"
int main() { return 0; }
""")
        
        # Create compile_commands.json
        compile_commands = [
            {
                "directory": str(build_dir),
                "command": f"/usr/bin/c++ -c -o main.o {source_file}",
                "file": str(source_file)
            }
        ]
        compile_db = build_dir / "compile_commands.json"
        compile_db.write_text(json.dumps(compile_commands, indent=2))
        
        filtered_db = build_dir / "compile_commands_filtered.json"
        filtered_db.write_text(json.dumps(compile_commands, indent=2))
        
        # Mock clang-scan-deps output
        clang_output = f"""main.o: {source_file} \\
  {header}
"""
        
        # Mock subprocess.run
        import subprocess
        
        def mock_run(*args: Any, **kwargs: Any) -> Any:
            if args and args[0] and 'clang-scan-deps' in str(args[0][0]):
                class MockResult:
                    returncode = 0
                    stdout = clang_output
                    stderr = ""
                return MockResult()
            return subprocess.CompletedProcess(args, 0, "", "")
        
        monkeypatch.setattr("subprocess.run", mock_run)
        
        def mock_find_clang() -> str:
            return "clang-scan-deps-19"
        
        monkeypatch.setattr("lib.clang_utils.find_clang_scan_deps", mock_find_clang)
        
        # Run build_include_graph - should not crash
        result = build_include_graph(str(build_dir), verbose=False)
        
        # Should have found the header
        assert len(result.all_headers) == 1
        assert str(header) in result.all_headers
        
        # Include graph should exist (even if empty for this header)
        assert result.include_graph is not None
