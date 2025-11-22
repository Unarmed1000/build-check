#!/usr/bin/env python3
"""Dependency analysis utilities for header cooccurrence and relationship tracking."""

import logging
import time
from collections import defaultdict
from typing import Dict, List, Set, DefaultDict, Optional, Callable, Union, ItemsView, Tuple, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class SourceDependencyMap:
    """Encapsulates the mapping between source files and their dependencies.
    
    This class provides a clean interface for managing and querying build target
    dependencies, making the relationship between sources and their headers explicit.
    
    Attributes:
        _target_to_dependencies: Internal mapping of build targets to dependency lists
    """
    
    def __init__(self, target_to_dependencies: Optional[Dict[str, List[str]]] = None):
        """Initialize the source dependency map.
        
        Args:
            target_to_dependencies: Optional initial mapping of targets to their dependencies.
                                   Keys are build targets (e.g., 'main.cpp.o'), values are
                                   lists of file paths the target depends on.
        """
        self._target_to_dependencies: Dict[str, List[str]] = target_to_dependencies or {}
    
    def add_target(self, target_name: str, dependencies: List[str]) -> None:
        """Add or update a build target and its dependencies.
        
        Args:
            target_name: Name of the build target (e.g., 'src/main.cpp.o')
            dependencies: List of file paths this target depends on
        """
        self._target_to_dependencies[target_name] = dependencies
    
    def get_dependencies(self, target_name: str) -> List[str]:
        """Get the dependencies for a specific target.
        
        Args:
            target_name: Name of the build target
            
        Returns:
            List of dependency file paths, or empty list if target not found
        """
        return self._target_to_dependencies.get(target_name, [])
    
    def get_all_targets(self) -> List[str]:
        """Get all build target names.
        
        Returns:
            List of all target names in the map
        """
        return list(self._target_to_dependencies.keys())
    
    def get_target_count(self) -> int:
        """Get the number of targets in the map.
        
        Returns:
            Count of build targets
        """
        return len(self._target_to_dependencies)
    
    def to_dict(self) -> Dict[str, List[str]]:
        """Export the mapping as a dictionary.
        
        Returns:
            Dictionary mapping target names to their dependency lists
        """
        return self._target_to_dependencies.copy()
    
    def items(self) -> ItemsView[str, List[str]]:
        """Iterate over target-dependency pairs.
        
        Returns:
            ItemsView of (target_name, dependencies_list) tuples
        """
        return self._target_to_dependencies.items()
    
    def __len__(self) -> int:
        """Get the number of targets in the map."""
        return len(self._target_to_dependencies)
    
    def __contains__(self, target_name: str) -> bool:
        """Check if a target exists in the map."""
        return target_name in self._target_to_dependencies
    
    def __repr__(self) -> str:
        """String representation of the map."""
        return f"SourceDependencyMap(targets={len(self._target_to_dependencies)})"


@dataclass
class DependencyAnalysisResult:
    """Result from comprehensive dependency hell analysis.
    
    Attributes:
        problematic: List of problematic headers with metrics (header, trans_count, usage_count, reverse_impact, chain_length)
        source_to_deps: Mapping of source files to their dependencies
        base_types: Set of base type headers (headers with no project dependencies)
        header_usage_count: Count of how many sources include each header
        header_reverse_impact: Count of headers that transitively depend on each header (rebuild blast radius)
        header_max_chain_length: Maximum include chain length for each header
    """
    problematic: List[Tuple[str, int, int, int, int]]
    source_to_deps: Dict[str, List[str]]
    base_types: Set[str]
    header_usage_count: Dict[str, int]
    header_reverse_impact: Dict[str, int]
    header_max_chain_length: Dict[str, int]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility and JSON serialization.
        
        Returns:
            Dictionary with all analysis results
        """
        return {
            'problematic': self.problematic,
            'source_to_deps': self.source_to_deps,
            'base_types': self.base_types,
            'header_usage_count': self.header_usage_count,
            'header_reverse_impact': self.header_reverse_impact,
            'header_max_chain_length': self.header_max_chain_length
        }


def compute_header_cooccurrence(
    dependency_map: SourceDependencyMap,
    is_header_filter: Callable[[str], bool],
    is_system_filter: Callable[[str], bool],
    target_headers: Optional[List[str]] = None
) -> Dict[str, Dict[str, int]]:
    """Compute cooccurrence matrix for headers appearing together in source files.
    
    This analyzes how often headers appear together in compilation units. High cooccurrence
    indicates dependency relationships (direct or transitive) and can reveal coupling patterns.
    
    Args:
        dependency_map: Source dependency mapping
        is_header_filter: Function to check if a path is a header file
        is_system_filter: Function to check if a path is a system header
        target_headers: Optional list of specific headers to analyze. If provided, only
                       computes cooccurrence for these headers. If None, analyzes all headers.
    
    Returns:
        Dictionary mapping header -> (header -> cooccurrence_count)
        - If target_headers is None: maps every header to all other headers it cooccurs with
        - If target_headers is provided: maps each target header to headers it cooccurs with
    
    Examples:
        >>> # Compute for all headers
        >>> cooccur = compute_header_cooccurrence(deps, is_header, is_system)
        >>> print(cooccur["foo.h"]["bar.h"])  # How often foo.h and bar.h appear together
        
        >>> # Compute for specific problematic headers only
        >>> cooccur = compute_header_cooccurrence(deps, is_header, is_system, ["foo.h"])
        >>> print(cooccur["foo.h"])  # All headers that cooccur with foo.h
    """
    start_time = time.time()
    cooccurrence: DefaultDict[str, DefaultDict[str, int]] = defaultdict(lambda: defaultdict(int))
    
    if target_headers is not None:
        if not target_headers:
            logger.warning("Empty target_headers list provided")
            return {}
        
        logger.info(f"Computing cooccurrence for {len(target_headers)} target headers...")
        
        # Targeted cooccurrence: only compute for specific headers
        target_set = set(target_headers)
        for source, deps in dependency_map.items():
            headers = [d for d in deps if is_header_filter(d) and not is_system_filter(d)]
            for target_header in target_headers:
                if target_header in headers:
                    for h in headers:
                        if h != target_header:
                            cooccurrence[target_header][h] += 1
    else:
        # Full cooccurrence matrix: compute for all headers
        logger.info(f"Computing full cooccurrence matrix for all headers...")
        
        for source, deps in dependency_map.items():
            headers = [d for d in deps if is_header_filter(d) and not is_system_filter(d)]
            
            # Build cooccurrence matrix for all header pairs
            for h1 in headers:
                for h2 in headers:
                    if h1 != h2:
                        cooccurrence[h1][h2] += 1
    
    elapsed = time.time() - start_time
    # Convert to regular dict with proper type annotation
    result: Dict[str, Dict[str, int]] = {k: dict(v) for k, v in cooccurrence.items()}
    logger.info(f"Cooccurrence computation complete in {elapsed:.2f}s ({len(result)} headers)")
    return result


def find_dependency_fanout(
    target_headers: List[str],
    dependency_map: SourceDependencyMap,
    is_header_filter: Callable[[str], bool],
    is_system_filter: Callable[[str], bool]
) -> Dict[str, Dict[str, int]]:
    """Find how often headers cooccur with target headers (fanout analysis).
    
    This function performs targeted cooccurrence analysis to understand which headers
    are frequently pulled in together with specific problematic headers. It's optimized
    for analyzing a subset of headers rather than computing a full cooccurrence matrix.
    
    Args:
        target_headers: List of specific headers to analyze for fanout
        dependency_map: Source dependency mapping
        is_header_filter: Function to check if a path is a header file
        is_system_filter: Function to check if a path is a system header
    
    Returns:
        Dictionary mapping each target header to headers it cooccurs with and their counts.
        For each target_header, returns a dict of {cooccurring_header: count}.
    
    Examples:
        >>> fanout = find_dependency_fanout(
        ...     ['problematic.h'], source_to_deps,
        ...     lambda p: p.endswith('.h'),
        ...     lambda p: p.startswith('/usr/')
        ... )
        >>> print(fanout['problematic.h']['other.h'])  # How often they appear together
        42
    
    Notes:
        This is a convenience wrapper around compute_header_cooccurrence() that provides
        a more specific API for fanout analysis with logging.
    """
    if not target_headers:
        logger.warning("No target headers provided for fanout analysis")
        return {}
    
    logger.info("Calculating header cooccurrence/fanout from cached data...")
    
    # Use the generic cooccurrence function with targeted analysis
    return compute_header_cooccurrence(
        dependency_map,
        is_header_filter=is_header_filter,
        is_system_filter=is_system_filter,
        target_headers=target_headers
    )


def compute_header_cooccurrence_from_deps_lists(
    dependency_map: SourceDependencyMap,
    is_header_filter: Callable[[str], bool],
    is_system_filter: Callable[[str], bool],
    show_progress: bool = False
) -> Dict[str, Dict[str, int]]:
    """Compute cooccurrence matrix from a mapping of targets to their dependency lists.
    
    This is a convenience wrapper around compute_header_cooccurrence that handles progress
    reporting for large analyses. Use this when you need to show progress to the user.
    
    Args:
        dependency_map: Source dependency mapping
        is_header_filter: Function to check if a path is a header file
        is_system_filter: Function to check if a path is a system header
        show_progress: Whether to log progress updates
    
    Returns:
        Dictionary mapping header -> (header -> cooccurrence_count)
    """
    total = len(dependency_map)
    
    if show_progress:
        logger.info(f"Analyzing {total} targets...")
    
    cooccurrence: DefaultDict[str, DefaultDict[str, int]] = defaultdict(lambda: defaultdict(int))
    
    for idx, (target, deps) in enumerate(dependency_map.items(), 1):
        if show_progress and (idx % 100 == 0 or idx == total):
            logger.info(f"Progress: {idx}/{total} targets processed")
        
        headers = [d for d in deps if is_header_filter(d) and not is_system_filter(d)]
        
        # Build cooccurrence matrix
        for h1 in headers:
            for h2 in headers:
                if h1 != h2:
                    cooccurrence[h1][h2] += 1
    
    # Convert to regular dict with proper type annotation
    result: Dict[str, Dict[str, int]] = {k: dict(v) for k, v in cooccurrence.items()}
    if show_progress:
        logger.info(f"Built cooccurrence graph with {len(result)} headers")
    
    return result


def build_reverse_dependency_map(
    dependency_map: SourceDependencyMap,
    header_extensions: tuple[str, ...] = ('.h', '.hpp', '.hxx', '.hh')
) -> Dict[str, Set[str]]:
    """Build reverse dependency map: header -> set of sources that depend on it.
    
    This is useful for ripple effect analysis - determining which source files
    will need to recompile when a header changes.
    
    Args:
        dependency_map: Source dependency mapping
        header_extensions: Tuple of header file extensions to consider
    
    Returns:
        Dictionary mapping each header file to the set of source files that depend on it
    
    Example:
        >>> deps = {
        ...     'main.cpp.o': ['main.cpp', 'foo.h', 'bar.h'],
        ...     'utils.cpp.o': ['utils.cpp', 'bar.h']
        ... }
        >>> dependency_map = SourceDependencyMap(deps)
        >>> reverse_map = build_reverse_dependency_map(dependency_map)
        >>> print(reverse_map['bar.h'])  # {'main.cpp', 'utils.cpp'}
    """
    header_to_sources: DefaultDict[str, Set[str]] = defaultdict(set)
    
    for source, deps in dependency_map.items():
        # Extract the source file path from the target
        # Targets are like "path/to/file.cpp.o", we want "path/to/file.cpp"
        source_file = source
        if source.endswith('.o'):
            source_file = source[:-2]
        
        # Add this source to all headers it depends on (transitively)
        for dep in deps:
            if dep.endswith(header_extensions):
                header_to_sources[dep].add(source_file)
    
    # Convert to regular dict
    return {k: v for k, v in header_to_sources.items()}


def compute_affected_sources(
    changed_headers: List[str],
    header_to_sources: Dict[str, Set[str]]
) -> Dict[str, List[str]]:
    """Compute which source files are affected by changed headers.
    
    Given a list of changed headers and a reverse dependency map, determines
    which source files will need to recompile.
    
    Args:
        changed_headers: List of header file paths that have changed
        header_to_sources: Reverse dependency map (header -> set of dependent sources)
    
    Returns:
        Dictionary mapping each changed header to a sorted list of affected source files.
        Headers with no dependents are excluded from the result.
    
    Example:
        >>> changed_headers = ['foo.h', 'bar.h']
        >>> header_to_sources = {
        ...     'foo.h': {'main.cpp', 'test.cpp'},
        ...     'bar.h': {'main.cpp'}
        ... }
        >>> affected = compute_affected_sources(changed_headers, header_to_sources)
        >>> print(affected['foo.h'])  # ['main.cpp', 'test.cpp']
    """
    affected_sources = {}
    
    for header in changed_headers:
        sources = header_to_sources.get(header, set())
        if sources:
            affected_sources[header] = sorted(sources)
    
    return affected_sources
