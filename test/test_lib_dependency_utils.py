#!/usr/bin/env python3
"""Tests for lib.dependency_utils module."""

import pytest
from typing import Any, Dict, List, Tuple, Generator
from lib.dependency_utils import (
    compute_header_cooccurrence,
    compute_header_cooccurrence_from_deps_lists,
    find_dependency_fanout,
    build_reverse_dependency_map,
    compute_affected_sources,
    SourceDependencyMap
)


class TestComputeHeaderCooccurrence:
    """Test compute_header_cooccurrence function."""
    
    def test_basic_cooccurrence(self) -> None:
        """Test basic cooccurrence calculation."""
        source_to_deps = {
            'main.cpp': ['main.cpp', 'foo.h', 'bar.h', 'baz.h'],
            'test.cpp': ['test.cpp', 'foo.h', 'bar.h'],
            'util.cpp': ['util.cpp', 'baz.h']
        }
        
        def is_header(path: str) -> bool:
            return path.endswith('.h')
        
        def is_system(path: str) -> bool:
            return False
        
        dependency_map = SourceDependencyMap(source_to_deps)
        result = compute_header_cooccurrence(dependency_map, is_header, is_system)
        
        # foo.h and bar.h appear together in 2 files
        assert result['foo.h']['bar.h'] == 2
        assert result['bar.h']['foo.h'] == 2
        
        # foo.h and baz.h appear together in 1 file
        assert result['foo.h']['baz.h'] == 1
        assert result['baz.h']['foo.h'] == 1
        
        # bar.h and baz.h appear together in 1 file
        assert result['bar.h']['baz.h'] == 1
        assert result['baz.h']['bar.h'] == 1
    
    def test_targeted_cooccurrence(self) -> None:
        """Test cooccurrence calculation for specific target headers."""
        source_to_deps = {
            'main.cpp': ['main.cpp', 'foo.h', 'bar.h', 'baz.h'],
            'test.cpp': ['test.cpp', 'foo.h', 'bar.h'],
            'util.cpp': ['util.cpp', 'baz.h', 'qux.h']
        }
        
        def is_header(path: str) -> bool:
            return path.endswith('.h')
        
        def is_system(path: str) -> bool:
            return False
        
        # Only compute cooccurrence for foo.h
        dependency_map = SourceDependencyMap(source_to_deps)
        result = compute_header_cooccurrence(
            dependency_map, is_header, is_system, target_headers=['foo.h']
        )
        
        # Result should only contain foo.h as a key
        assert 'foo.h' in result
        assert 'bar.h' not in result
        assert 'baz.h' not in result
        
        # foo.h cooccurs with bar.h and baz.h
        assert result['foo.h']['bar.h'] == 2
        assert result['foo.h']['baz.h'] == 1
        assert 'qux.h' not in result['foo.h']
    
    def test_system_header_filtering(self) -> None:
        """Test that system headers are filtered out."""
        source_to_deps = {
            'main.cpp': ['main.cpp', 'foo.h', '/usr/include/stdio.h', 'bar.h'],
            'test.cpp': ['test.cpp', 'foo.h', '/usr/include/stdlib.h']
        }
        
        def is_header(path: str) -> bool:
            return path.endswith('.h')
        
        def is_system(path: str) -> bool:
            return path.startswith('/usr/')
        
        dependency_map = SourceDependencyMap(source_to_deps)
        result = compute_header_cooccurrence(dependency_map, is_header, is_system)
        
        # System headers should not appear in results
        assert '/usr/include/stdio.h' not in result
        assert '/usr/include/stdlib.h' not in result
        
        # Only project headers
        assert 'foo.h' in result
        assert 'bar.h' in result['foo.h']
    
    def test_empty_target_headers(self) -> None:
        """Test with empty target headers list."""
        source_to_deps = {'main.cpp': ['main.cpp', 'foo.h', 'bar.h']}
        
        def is_header(path: str) -> bool:
            return path.endswith('.h')
        
        def is_system(path: str) -> bool:
            return False
        
        dependency_map = SourceDependencyMap(source_to_deps)
        result = compute_header_cooccurrence(
            dependency_map, is_header, is_system, target_headers=[]
        )
        
        # Should return empty dict
        assert result == {}
    
    def test_no_headers(self) -> None:
        """Test with no headers in dependencies."""
        source_to_deps = {
            'main.cpp': ['main.cpp'],
            'test.cpp': ['test.cpp']
        }
        
        def is_header(path: str) -> bool:
            return path.endswith('.h')
        
        def is_system(path: str) -> bool:
            return False
        
        dependency_map = SourceDependencyMap(source_to_deps)
        result = compute_header_cooccurrence(dependency_map, is_header, is_system)
        
        # Should return empty dict
        assert result == {}


class TestComputeHeaderCooccurrenceFromDepsLists:
    """Test compute_header_cooccurrence_from_deps_lists function."""
    
    def test_basic_functionality(self) -> None:
        """Test basic functionality with progress tracking."""
        deps_by_target = {
            'main.o': ['main.cpp', 'foo.h', 'bar.h'],
            'test.o': ['test.cpp', 'foo.h', 'baz.h']
        }
        
        def is_header(path: str) -> bool:
            return path.endswith('.h')
        
        def is_system(path: str) -> bool:
            return False
        
        dependency_map = SourceDependencyMap(deps_by_target)
        result = compute_header_cooccurrence_from_deps_lists(
            dependency_map, is_header, is_system, show_progress=False
        )
        
        # foo.h appears with bar.h once and baz.h once
        assert result['foo.h']['bar.h'] == 1
        assert result['foo.h']['baz.h'] == 1
        assert result['bar.h']['foo.h'] == 1
        assert result['baz.h']['foo.h'] == 1
    
    def test_progress_logging(self) -> None:
        """Test that progress logging doesn't cause errors."""
        deps_by_target = {
            f'target{i}.o': ['source.cpp', 'header.h'] for i in range(200)
        }
        
        def is_header(path: str) -> bool:
            return path.endswith('.h')
        
        def is_system(path: str) -> bool:
            return False
        
        # Should not raise any errors with progress logging
        dependency_map = SourceDependencyMap(deps_by_target)
        result = compute_header_cooccurrence_from_deps_lists(
            dependency_map, is_header, is_system, show_progress=True
        )
        
        # With only one header, no cooccurrence
        assert result == {}


class TestFindDependencyFanout:
    """Test find_dependency_fanout function."""
    
    def test_basic_fanout(self) -> None:
        """Test basic fanout analysis for target headers."""
        source_to_deps = {
            'main.cpp': ['main.cpp', 'foo.h', 'bar.h', 'baz.h'],
            'test.cpp': ['test.cpp', 'foo.h', 'bar.h'],
            'util.cpp': ['util.cpp', 'baz.h', 'qux.h']
        }
        
        def is_header(path: str) -> bool:
            return path.endswith('.h')
        
        def is_system(path: str) -> bool:
            return False
        
        # Analyze fanout for foo.h
        dependency_map = SourceDependencyMap(source_to_deps)
        result = find_dependency_fanout(
            target_headers=['foo.h'],
            dependency_map=dependency_map,
            is_header_filter=is_header,
            is_system_filter=is_system
        )
        
        # foo.h should show which headers it cooccurs with
        assert 'foo.h' in result
        assert result['foo.h']['bar.h'] == 2  # Appears with bar.h in main.cpp and test.cpp
        assert result['foo.h']['baz.h'] == 1  # Appears with baz.h in main.cpp
        assert 'qux.h' not in result['foo.h']  # Never appears with qux.h
    
    def test_multiple_target_headers(self) -> None:
        """Test fanout for multiple target headers."""
        source_to_deps = {
            'main.cpp': ['main.cpp', 'foo.h', 'bar.h'],
            'test.cpp': ['test.cpp', 'foo.h', 'baz.h'],
            'util.cpp': ['util.cpp', 'bar.h', 'baz.h']
        }
        
        def is_header(path: str) -> bool:
            return path.endswith('.h')
        
        def is_system(path: str) -> bool:
            return False
        
        # Analyze fanout for both foo.h and bar.h
        dependency_map = SourceDependencyMap(source_to_deps)
        result = find_dependency_fanout(
            target_headers=['foo.h', 'bar.h'],
            dependency_map=dependency_map,
            is_header_filter=is_header,
            is_system_filter=is_system
        )
        
        # Should have results for both target headers
        assert 'foo.h' in result
        assert 'bar.h' in result
        
        # Check foo.h fanout
        assert result['foo.h']['bar.h'] == 1
        assert result['foo.h']['baz.h'] == 1
        
        # Check bar.h fanout
        assert result['bar.h']['foo.h'] == 1
        assert result['bar.h']['baz.h'] == 1
    
    def test_empty_target_headers(self) -> None:
        """Test with no target headers."""
        source_to_deps = {'main.cpp': ['main.cpp', 'foo.h', 'bar.h']}
        
        def is_header(path: str) -> bool:
            return path.endswith('.h')
        
        def is_system(path: str) -> bool:
            return False
        
        dependency_map = SourceDependencyMap(source_to_deps)
        result = find_dependency_fanout(
            target_headers=[],
            dependency_map=dependency_map,
            is_header_filter=is_header,
            is_system_filter=is_system
        )
        
        # Should return empty dict
        assert result == {}
    
    def test_system_header_filtering(self) -> None:
        """Test that system headers are filtered from fanout results."""
        source_to_deps = {
            'main.cpp': ['main.cpp', 'foo.h', '/usr/include/stdio.h', 'bar.h'],
        }
        
        def is_header(path: str) -> bool:
            return path.endswith('.h')
        
        def is_system(path: str) -> bool:
            return path.startswith('/usr/')
        
        dependency_map = SourceDependencyMap(source_to_deps)
        result = find_dependency_fanout(
            target_headers=['foo.h'],
            dependency_map=dependency_map,
            is_header_filter=is_header,
            is_system_filter=is_system
        )
        
        # System headers should not appear in fanout
        assert '/usr/include/stdio.h' not in result['foo.h']
        assert 'bar.h' in result['foo.h']


class TestBuildReverseDependencyMap:
    """Test build_reverse_dependency_map function."""
    
    def test_basic_reverse_map(self) -> None:
        """Test basic reverse dependency mapping."""
        source_to_deps = {
            'main.cpp.o': ['main.cpp', 'foo.h', 'bar.h'],
            'test.cpp.o': ['test.cpp', 'foo.h', 'baz.h'],
            'util.cpp.o': ['util.cpp', 'bar.h']
        }
        
        dependency_map = SourceDependencyMap(source_to_deps)
        result = build_reverse_dependency_map(dependency_map)
        
        # foo.h is used by main.cpp and test.cpp
        assert result['foo.h'] == {'main.cpp', 'test.cpp'}
        
        # bar.h is used by main.cpp and util.cpp
        assert result['bar.h'] == {'main.cpp', 'util.cpp'}
        
        # baz.h is used only by test.cpp
        assert result['baz.h'] == {'test.cpp'}
    
    def test_no_object_extension(self) -> None:
        """Test with source files that don't have .o extension."""
        source_to_deps = {
            'main.cpp': ['main.cpp', 'foo.h'],
            'test.cpp': ['test.cpp', 'foo.h']
        }
        
        dependency_map = SourceDependencyMap(source_to_deps)
        result = build_reverse_dependency_map(dependency_map)
        
        # Should work with or without .o extension
        assert result['foo.h'] == {'main.cpp', 'test.cpp'}
    
    def test_custom_header_extensions(self) -> None:
        """Test with custom header extensions."""
        source_to_deps = {
            'main.cpp.o': ['main.cpp', 'foo.hh', 'bar.hpp'],
            'test.cpp.o': ['test.cpp', 'baz.hxx']
        }
        
        dependency_map = SourceDependencyMap(source_to_deps)
        result = build_reverse_dependency_map(dependency_map, header_extensions=('.hh', '.hpp', '.hxx'))
        
        assert result['foo.hh'] == {'main.cpp'}
        assert result['bar.hpp'] == {'main.cpp'}
        assert result['baz.hxx'] == {'test.cpp'}
    
    def test_empty_dependencies(self) -> None:
        """Test with no dependencies."""
        source_to_deps = {
            'main.cpp.o': ['main.cpp']
        }
        
        dependency_map = SourceDependencyMap(source_to_deps)
        result = build_reverse_dependency_map(dependency_map)
        
        # Should return empty dict when no headers
        assert result == {}
    
    def test_no_headers_in_deps(self) -> None:
        """Test when dependencies contain only source files."""
        source_to_deps = {
            'main.cpp.o': ['main.cpp', 'other.cpp']
        }
        
        dependency_map = SourceDependencyMap(source_to_deps)
        result = build_reverse_dependency_map(dependency_map)
        
        # Should return empty dict when no headers
        assert result == {}
    
    def test_multiple_sources_same_header(self) -> None:
        """Test when multiple sources depend on the same header."""
        source_to_deps = {
            'main.cpp.o': ['main.cpp', 'common.h'],
            'test.cpp.o': ['test.cpp', 'common.h'],
            'util.cpp.o': ['util.cpp', 'common.h'],
            'app.cpp.o': ['app.cpp', 'common.h']
        }
        
        dependency_map = SourceDependencyMap(source_to_deps)
        result = build_reverse_dependency_map(dependency_map)
        
        assert result['common.h'] == {'main.cpp', 'test.cpp', 'util.cpp', 'app.cpp'}
        assert len(result['common.h']) == 4


class TestComputeAffectedSources:
    """Test compute_affected_sources function."""
    
    def test_basic_affected_sources(self) -> None:
        """Test basic affected sources computation."""
        changed_headers = ['foo.h', 'bar.h']
        header_to_sources = {
            'foo.h': {'main.cpp', 'test.cpp'},
            'bar.h': {'main.cpp', 'util.cpp'},
            'baz.h': {'other.cpp'}
        }
        
        result = compute_affected_sources(changed_headers, header_to_sources)
        
        # foo.h affects main.cpp and test.cpp
        assert result['foo.h'] == ['main.cpp', 'test.cpp']
        
        # bar.h affects main.cpp and util.cpp
        assert result['bar.h'] == ['main.cpp', 'util.cpp']
        
        # baz.h is not in changed_headers, so not in result
        assert 'baz.h' not in result
    
    def test_header_with_no_dependents(self) -> None:
        """Test that headers with no dependents are excluded from result."""
        changed_headers = ['foo.h', 'orphan.h']
        header_to_sources = {
            'foo.h': {'main.cpp'},
            'orphan.h': set()  # No dependents
        }
        
        result = compute_affected_sources(changed_headers, header_to_sources)
        
        # foo.h should be in result
        assert 'foo.h' in result
        assert result['foo.h'] == ['main.cpp']
        
        # orphan.h should not be in result (no dependents)
        assert 'orphan.h' not in result
    
    def test_header_not_in_map(self) -> None:
        """Test when changed header is not in the dependency map."""
        changed_headers = ['foo.h', 'unknown.h']
        header_to_sources = {
            'foo.h': {'main.cpp'}
        }
        
        result = compute_affected_sources(changed_headers, header_to_sources)
        
        # foo.h should be in result
        assert 'foo.h' in result
        
        # unknown.h should not be in result (not in map)
        assert 'unknown.h' not in result
    
    def test_empty_changed_headers(self) -> None:
        """Test with no changed headers."""
        changed_headers: List[str] = []
        header_to_sources = {
            'foo.h': {'main.cpp'}
        }
        
        result = compute_affected_sources(changed_headers, header_to_sources)
        
        # Should return empty dict
        assert result == {}
    
    def test_sorted_output(self) -> None:
        """Test that output sources are sorted."""
        changed_headers = ['foo.h']
        header_to_sources = {
            'foo.h': {'z.cpp', 'a.cpp', 'm.cpp'}
        }
        
        result = compute_affected_sources(changed_headers, header_to_sources)
        
        # Should be sorted alphabetically
        assert result['foo.h'] == ['a.cpp', 'm.cpp', 'z.cpp']
    
    def test_multiple_headers_overlapping_sources(self) -> None:
        """Test when multiple changed headers affect overlapping sources."""
        changed_headers = ['foo.h', 'bar.h', 'baz.h']
        header_to_sources = {
            'foo.h': {'main.cpp', 'test.cpp'},
            'bar.h': {'main.cpp', 'util.cpp'},
            'baz.h': {'test.cpp', 'other.cpp'}
        }
        
        result = compute_affected_sources(changed_headers, header_to_sources)
        
        # Each header should have its own list of affected sources
        assert set(result['foo.h']) == {'main.cpp', 'test.cpp'}
        assert set(result['bar.h']) == {'main.cpp', 'util.cpp'}
        assert set(result['baz.h']) == {'test.cpp', 'other.cpp'}
        
        # All should be sorted
        assert result['foo.h'] == sorted(result['foo.h'])
        assert result['bar.h'] == sorted(result['bar.h'])
        assert result['baz.h'] == sorted(result['baz.h'])


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
