#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
"""Dependency analysis utilities for header cooccurrence and relationship tracking."""

import logging
import time
from collections import defaultdict
from typing import Dict, List, Set, DefaultDict, Optional, Callable, ItemsView, Tuple, Any
from dataclasses import dataclass

from lib.color_utils import Colors, print_warning

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


def compute_header_usage(source_to_deps: Dict[str, Set[str]], file_types: Dict[str, Any]) -> Dict[str, int]:
    """Count how many source files include each header (directly or transitively).

    Args:
        source_to_deps: Mapping of source files to their dependencies
        file_types: Dictionary mapping file paths to FileType classification

    Returns:
        Dictionary mapping headers to usage count
    """
    header_usage_count: Dict[str, int] = defaultdict(int)
    print(f"{Colors.DIM}  Analyzing {len(source_to_deps)} source files...{Colors.RESET}")

    for idx, (_, deps) in enumerate(source_to_deps.items(), 1):
        if idx % 100 == 0:
            print(f"\r{Colors.DIM}  Progress: {idx}/{len(source_to_deps)} sources analyzed{Colors.RESET}", end="", flush=True)
        for dep in deps:
            # Use file classification to filter project headers only
            from lib.clang_utils import FileType

            if dep.endswith((".h", ".hpp", ".hxx")) and file_types.get(dep, FileType.PROJECT) == FileType.PROJECT:
                header_usage_count[dep] += 1

    if len(source_to_deps) >= 100:
        print()  # New line after progress

    return dict(header_usage_count)


def identify_problematic_headers(
    header_transitive_deps: Dict[str, int],
    header_usage_count: Dict[str, int],
    header_reverse_impact: Dict[str, int],
    header_max_chain_length: Dict[str, int],
    threshold: int,
) -> List[Tuple[str, int, int, int, int]]:
    """Identify headers exceeding the threshold.

    Args:
        header_transitive_deps: Transitive dependency counts
        header_usage_count: Usage counts per header
        header_reverse_impact: Reverse impact counts
        header_max_chain_length: Maximum chain lengths
        threshold: Minimum transitive dependency count

    Returns:
        List of tuples (header, trans_count, usage_count, reverse_impact, chain_length)
    """
    problematic = []
    print(f"{Colors.BLUE}Checking for headers exceeding threshold ({threshold})...{Colors.RESET}")

    for header, trans_count in header_transitive_deps.items():
        if trans_count > threshold:
            usage_count = header_usage_count.get(header, 0)
            reverse_impact = header_reverse_impact.get(header, 0)
            chain_length = header_max_chain_length.get(header, 0)
            problematic.append((header, trans_count, usage_count, reverse_impact, chain_length))

    if problematic:
        print_warning(f"  Found {len(problematic)} headers exceeding threshold", prefix=False)

    return sorted(problematic, key=lambda x: x[1], reverse=True)


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
            "problematic": self.problematic,
            "source_to_deps": self.source_to_deps,
            "base_types": self.base_types,
            "header_usage_count": self.header_usage_count,
            "header_reverse_impact": self.header_reverse_impact,
            "header_max_chain_length": self.header_max_chain_length,
        }


def compute_header_cooccurrence(
    dependency_map: SourceDependencyMap,
    is_header_filter: Callable[[str], bool],
    is_system_filter: Callable[[str], bool],
    target_headers: Optional[List[str]] = None,
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

        logger.info("Computing cooccurrence for %s target headers...", len(target_headers))

        # Targeted cooccurrence: only compute for specific headers
        for _, deps in dependency_map.items():
            headers = [d for d in deps if is_header_filter(d) and not is_system_filter(d)]
            for target_header in target_headers:
                if target_header in headers:
                    for h in headers:
                        if h != target_header:
                            cooccurrence[target_header][h] += 1
    else:
        # Full cooccurrence matrix: compute for all headers
        logger.info("Computing full cooccurrence matrix for all headers...")

        for _, deps in dependency_map.items():
            headers = [d for d in deps if is_header_filter(d) and not is_system_filter(d)]

            # Build cooccurrence matrix for all header pairs
            for h1 in headers:
                for h2 in headers:
                    if h1 != h2:
                        cooccurrence[h1][h2] += 1

    elapsed = time.time() - start_time
    # Convert to regular dict with proper type annotation
    result: Dict[str, Dict[str, int]] = {k: dict(v) for k, v in cooccurrence.items()}
    logger.info("Cooccurrence computation complete in %.2fs (%s headers)", elapsed, len(result))
    return result


def find_dependency_fanout(
    target_headers: List[str], dependency_map: SourceDependencyMap, is_header_filter: Callable[[str], bool], is_system_filter: Callable[[str], bool]
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
    return compute_header_cooccurrence(dependency_map, is_header_filter=is_header_filter, is_system_filter=is_system_filter, target_headers=target_headers)


def compute_header_cooccurrence_from_deps_lists(
    dependency_map: SourceDependencyMap, is_header_filter: Callable[[str], bool], is_system_filter: Callable[[str], bool], show_progress: bool = False
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
        logger.info("Analyzing %s targets...", total)

    cooccurrence: DefaultDict[str, DefaultDict[str, int]] = defaultdict(lambda: defaultdict(int))

    for idx, (_, deps) in enumerate(dependency_map.items(), 1):
        if show_progress and (idx % 100 == 0 or idx == total):
            logger.info("Progress: %s/%s targets processed", idx, total)

        headers = [d for d in deps if is_header_filter(d) and not is_system_filter(d)]

        # Build cooccurrence matrix
        for h1 in headers:
            for h2 in headers:
                if h1 != h2:
                    cooccurrence[h1][h2] += 1

    # Convert to regular dict with proper type annotation
    result: Dict[str, Dict[str, int]] = {k: dict(v) for k, v in cooccurrence.items()}
    if show_progress:
        logger.info("Built cooccurrence graph with %s headers", len(result))

    return result


def build_reverse_dependency_map(
    dependency_map: SourceDependencyMap, header_extensions: tuple[str, ...] = (".h", ".hpp", ".hxx", ".hh")
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
        if source.endswith(".o"):
            source_file = source[:-2]

        # Add this source to all headers it depends on (transitively)
        for dep in deps:
            if dep.endswith(header_extensions):
                header_to_sources[dep].add(source_file)

    # Convert to regular dict
    return dict(header_to_sources.items())


def compute_affected_sources(changed_headers: List[str], header_to_sources: Dict[str, Set[str]]) -> Dict[str, List[str]]:
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


def compute_affected_sources_batch(
    changed_headers: List[str], header_graph: Any, header_to_sources: Dict[str, Set[str]], use_memoization: bool = True
) -> Set[str]:
    """Compute all affected sources for multiple changed headers efficiently.

    This optimized version processes multiple changed headers together, computing
    the transitive closure once and reusing intermediate results through memoization.
    This is significantly faster than calling compute_affected_sources separately
    for each header when analyzing large changesets.

    Args:
        changed_headers: List of header file paths that have changed
        header_graph: NetworkX DiGraph of header dependencies
        header_to_sources: Reverse dependency map (header -> set of dependent sources)
        use_memoization: Enable caching of transitive dependency results (default: True)

    Returns:
        Set of all source files affected by any of the changed headers

    Example:
        >>> import networkx as nx
        >>> graph = nx.DiGraph()
        >>> graph.add_edges_from([('a.h', 'b.h'), ('b.h', 'c.h')])
        >>> header_to_sources = {'a.h': {'main.cpp'}, 'b.h': {'util.cpp'}, 'c.h': {'test.cpp'}}
        >>> affected = compute_affected_sources_batch(['c.h'], graph, header_to_sources)
        >>> # Returns all sources that transitively depend on c.h
    """
    import networkx as nx

    all_affected = set()
    descendants_cache: Dict[str, Set[str]] = {}

    for changed_header in changed_headers:
        # Check if header exists in graph
        if changed_header not in header_graph:
            # Header not in dependency graph, check direct dependents only
            if changed_header in header_to_sources:
                all_affected.update(header_to_sources[changed_header])
            continue

        # Compute transitive dependencies (all headers that depend on this one)
        if use_memoization and changed_header in descendants_cache:
            transitive_deps = descendants_cache[changed_header]
        else:
            try:
                # nx.descendants returns all nodes reachable from changed_header
                # In a dependency graph, these are all headers that transitively include it
                transitive_deps = nx.descendants(header_graph, changed_header)
                transitive_deps.add(changed_header)  # Include the header itself

                if use_memoization:
                    descendants_cache[changed_header] = transitive_deps
            except nx.NetworkXError:
                transitive_deps = {changed_header}

        # Collect all sources that depend on any of these headers
        for header in transitive_deps:
            if header in header_to_sources:
                all_affected.update(header_to_sources[header])

    return all_affected
