#!/usr/bin/env python3
"""File and path utilities for filtering and manipulating file paths."""

import os
import fnmatch
import logging
from collections import defaultdict
from typing import Set, List, Dict, DefaultDict

logger = logging.getLogger(__name__)


def filter_headers_by_pattern(headers: Set[str], pattern: str, project_root: str) -> Set[str]:
    """Filter headers by glob pattern.
    
    Args:
        headers: Set of header paths
        pattern: Glob pattern (e.g., "FslBase/*")
        project_root: Root directory of the project
        
    Returns:
        Filtered set of headers matching pattern
    """
    filtered: Set[str] = set()
    
    for header in headers:
        rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
        if fnmatch.fnmatch(rel_path, pattern):
            filtered.add(header)
    
    return filtered


def exclude_headers_by_patterns(headers: Set[str], exclude_patterns: List[str], project_root: str) -> tuple[Set[str], int, List[str]]:
    """Exclude headers matching any of the provided glob patterns.
    
    Args:
        headers: Set of header paths
        exclude_patterns: List of glob patterns to exclude (e.g., ["*/ThirdParty/*", "*/test/*"])
        project_root: Root directory of the project
        
    Returns:
        Tuple of (filtered_headers, excluded_count, patterns_with_no_matches)
        - filtered_headers: Set of headers after exclusions
        - excluded_count: Number of headers excluded
        - patterns_with_no_matches: List of patterns that matched no headers
    """
    if not exclude_patterns:
        return headers, 0, []
    
    filtered: Set[str] = set()
    pattern_match_counts: Dict[str, int] = {pattern: 0 for pattern in exclude_patterns}
    
    for header in headers:
        rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
        
        # Check if header matches any exclude pattern
        excluded = False
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                excluded = True
                pattern_match_counts[pattern] += 1
                break
        
        if not excluded:
            filtered.add(header)
    
    excluded_count = len(headers) - len(filtered)
    patterns_with_no_matches = [pattern for pattern, count in pattern_match_counts.items() if count == 0]
    
    logger.info(f"Excluded {excluded_count} headers using {len(exclude_patterns)} patterns")
    for pattern, count in pattern_match_counts.items():
        logger.debug(f"Pattern '{pattern}' matched {count} headers")
    
    return filtered, excluded_count, patterns_with_no_matches


def cluster_headers_by_directory(headers: List[str], project_root: str) -> Dict[str, List[str]]:
    """Group headers by their parent directory.
    
    Args:
        headers: List of header paths
        project_root: Root directory of the project
        
    Returns:
        Dictionary mapping directory names to lists of headers
    """
    clusters: DefaultDict[str, List[str]] = defaultdict(list)
    
    for header in headers:
        rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
        parent_dir = os.path.dirname(rel_path)
        
        # Use top-level directory as cluster name
        parts = parent_dir.split(os.sep)
        cluster_name = parts[0] if parts and parts[0] else "root"
        
        clusters[cluster_name].append(header)
    
    return dict(clusters)
