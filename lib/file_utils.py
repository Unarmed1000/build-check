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
