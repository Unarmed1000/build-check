#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#****************************************************************************************************************************************************
#* BSD 3-Clause License
#*
#* Copyright (c) 2025, Mana Battery
#* All rights reserved.
#*
#* Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#*
#* 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#* 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the
#*    documentation and/or other materials provided with the distribution.
#* 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this
#*    software without specific prior written permission.
#*
#* THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
#* THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
#* CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
#* PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
#* LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
#* EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#****************************************************************************************************************************************************
"""Serialization/deserialization of DSM analysis results to/from compressed JSON.

This module provides functions to save and load DSMAnalysisResults objects with:
- Deterministic JSON serialization (sorted keys, sorted collections)
- Schema versioning with strict validation
- Metadata tracking (timestamp, build directory, git commit, hostname)
- Gzip compression for storage efficiency
- Absolute paths for all file references

Schema version changes require explicit migration logic. No automatic migration supported.
"""

import os
import json
import gzip
import socket
import logging
import subprocess
from datetime import datetime
from typing import Dict, Set, List, Tuple, Any, Optional, DefaultDict
from collections import defaultdict
from dataclasses import asdict

import networkx as nx
from networkx.readwrite import json_graph

from .dsm_types import DSMAnalysisResults, MatrixStatistics
from .graph_utils import DSMMetrics
from .color_utils import print_error, print_success, print_warning

logger = logging.getLogger(__name__)

# Current schema version - increment when format changes
SCHEMA_VERSION = "1.1"


def _get_git_commit() -> str:
    """Get current git commit hash.
    
    Returns:
        Git commit hash or "unknown" if not in a git repository or git unavailable
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug("Failed to get git commit: %s", e)
    
    return "unknown"


def _get_hostname() -> str:
    """Get current hostname.
    
    Returns:
        Hostname or "unknown" if unavailable
    """
    try:
        return socket.gethostname()
    except Exception as e:
        logger.debug("Failed to get hostname: %s", e)
        return "unknown"


def _serialize_dsm_metrics(metrics: DSMMetrics) -> Dict[str, Any]:
    """Serialize DSMMetrics to dict with sorted keys.
    
    Args:
        metrics: DSMMetrics instance
        
    Returns:
        Dictionary representation with sorted keys
    """
    return {
        "coupling": metrics.coupling,
        "fan_in": metrics.fan_in,
        "fan_out": metrics.fan_out,
        "stability": metrics.stability,
    }


def _serialize_matrix_statistics(stats: MatrixStatistics) -> Dict[str, Any]:
    """Serialize MatrixStatistics to dict with sorted keys.
    
    Args:
        stats: MatrixStatistics instance
        
    Returns:
        Dictionary representation with sorted keys
    """
    return {
        "avg_deps": stats.avg_deps,
        "health": stats.health,
        "health_color": stats.health_color,
        "sparsity": stats.sparsity,
        "total_actual_deps": stats.total_actual_deps,
        "total_headers": stats.total_headers,
        "total_possible_deps": stats.total_possible_deps,
    }


def save_dsm_results(
    results: DSMAnalysisResults,
    unfiltered_headers: Set[str],
    unfiltered_include_graph: DefaultDict[str, Set[str]],
    filename: str,
    build_directory: str,
    filter_pattern: Optional[str] = None,
    exclude_patterns: Optional[List[str]] = None
) -> None:
    """Save DSM analysis results to compressed JSON file.
    
    Saves the UNFILTERED header set and include graph to allow applying different
    filters when loading the baseline. This makes baselines more flexible and reusable.
    
    Args:
        results: DSMAnalysisResults to save (computed from filtered headers)
        unfiltered_headers: Complete set of headers before any filtering
        unfiltered_include_graph: Complete include graph before any filtering
        filename: Output filename (will be gzip compressed)
        build_directory: Absolute path to build directory
        filter_pattern: Optional filter pattern that was applied (saved for reference)
        exclude_patterns: Optional list of exclude patterns that were applied (saved for reference)
        
    Raises:
        IOError: If file cannot be written
    """
    logger.info("Saving DSM results to %s", filename)
    
    # Build metadata
    metadata = {
        "build_directory": os.path.abspath(build_directory),
        "filter_pattern": filter_pattern or "",
        "exclude_patterns": sorted(exclude_patterns or []),
        "git_commit": _get_git_commit(),
        "hostname": _get_hostname(),
        "timestamp": datetime.now().isoformat(),
        "unfiltered_header_count": len(unfiltered_headers),
        "filtered_header_count": len(results.sorted_headers),
    }
    
    # Serialize metrics (sorted by header name)
    metrics_dict = {
        header: _serialize_dsm_metrics(metric)
        for header, metric in sorted(results.metrics.items())
    }
    
    # Serialize cycles (convert sets to sorted lists)
    cycles_list = [
        sorted(list(cycle))
        for cycle in results.cycles
    ]
    cycles_list.sort()  # Sort cycles themselves for determinism
    
    # Serialize graph using NetworkX json_graph
    graph_data = json_graph.node_link_data(results.directed_graph)
    # Sort nodes and edges for determinism
    graph_data['nodes'] = sorted(graph_data['nodes'], key=lambda x: x['id'])
    graph_data['links'] = sorted(graph_data['links'], key=lambda x: (x['source'], x['target']))
    
    # Serialize layers (already lists, just ensure determinism)
    layers_list = [sorted(layer) for layer in results.layers]
    
    # Serialize unfiltered data (for re-applying filters on load)
    unfiltered_headers_list = sorted(list(unfiltered_headers))
    unfiltered_include_graph_dict = {
        header: sorted(list(deps))
        for header, deps in sorted(unfiltered_include_graph.items())
    }
    
    # Build complete data structure with sorted keys
    data = {
        "_description": "DSM analysis results - DO NOT EDIT MANUALLY",
        "_schema_version": SCHEMA_VERSION,
        "cycles": cycles_list,
        "feedback_edges": sorted([list(edge) for edge in results.feedback_edges]),
        "graph": graph_data,
        "has_cycles": results.has_cycles,
        "header_to_headers": {
            header: sorted(list(deps))
            for header, deps in sorted(results.header_to_headers.items())
        },
        "header_to_layer": dict(sorted(results.header_to_layer.items())),
        "headers_in_cycles": sorted(list(results.headers_in_cycles)),
        "layers": layers_list,
        "metadata": metadata,
        "metrics": metrics_dict,
        "reverse_deps": {
            header: sorted(list(deps))
            for header, deps in sorted(results.reverse_deps.items())
        },
        "sorted_headers": results.sorted_headers,
        "stats": _serialize_matrix_statistics(results.stats),
        "unfiltered_headers": unfiltered_headers_list,
        "unfiltered_include_graph": unfiltered_include_graph_dict,
    }
    
    # Write to gzip-compressed JSON with sorted keys
    try:
        with gzip.open(filename, 'wt', encoding='utf-8') as f:
            json.dump(data, f, indent=2, sort_keys=True)
        
        file_size = os.path.getsize(filename)
        size_kb = file_size / 1024
        logger.info("Saved DSM results: %.1f KB", size_kb)
        print_success(f"Saved DSM analysis results to {filename} ({size_kb:.1f} KB)")
        
    except IOError as e:
        logger.error("Failed to save DSM results: %s", e)
        raise IOError(f"Failed to save DSM results to {filename}: {e}") from e


def _deserialize_dsm_metrics(data: Dict[str, Any]) -> DSMMetrics:
    """Deserialize DSMMetrics from dict.
    
    Args:
        data: Dictionary representation
        
    Returns:
        DSMMetrics instance
    """
    return DSMMetrics(
        fan_out=data["fan_out"],
        fan_in=data["fan_in"],
        coupling=data["coupling"],
        stability=data["stability"],
    )


def _deserialize_matrix_statistics(data: Dict[str, Any]) -> MatrixStatistics:
    """Deserialize MatrixStatistics from dict.
    
    Args:
        data: Dictionary representation
        
    Returns:
        MatrixStatistics instance
    """
    return MatrixStatistics(
        total_headers=data["total_headers"],
        total_actual_deps=data["total_actual_deps"],
        total_possible_deps=data["total_possible_deps"],
        sparsity=data["sparsity"],
        avg_deps=data["avg_deps"],
        health=data["health"],
        health_color=data["health_color"],
    )


def load_dsm_results(
    filename: str,
    current_build_directory: str,
    filter_pattern: Optional[str] = None,
    exclude_patterns: Optional[List[str]] = None,
    project_root: Optional[str] = None
) -> DSMAnalysisResults:
    """Load DSM analysis results from compressed JSON file and apply filters.
    
    Loads the unfiltered baseline data and re-applies filters, allowing users to
    compare with different filter settings than the original baseline.
    
    Args:
        filename: Input filename (gzip compressed JSON)
        current_build_directory: Current build directory for validation
        filter_pattern: Optional filter pattern to apply (inherits from baseline if None)
        exclude_patterns: Optional exclude patterns to apply (inherits from baseline if None)
        project_root: Project root for filter path resolution (required if filters specified)
        
    Returns:
        DSMAnalysisResults instance with filters applied
        
    Raises:
        ValueError: If schema version mismatches or validation fails
        IOError: If file cannot be read
    """
    logger.info("Loading DSM results from %s", filename)
    
    try:
        with gzip.open(filename, 'rt', encoding='utf-8') as f:
            data = json.load(f)
    except (IOError, OSError) as e:
        logger.error("Failed to load DSM results: %s", e)
        raise IOError(f"Failed to load DSM results from {filename}: {e}") from e
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in DSM file: %s", e)
        raise ValueError(f"Invalid JSON in {filename}: {e}") from e
    
    # Validate schema version (strict check)
    file_version = data.get("_schema_version", "unknown")
    if file_version != SCHEMA_VERSION:
        raise ValueError(
            f"Schema version mismatch: file has version {file_version}, "
            f"but this tool requires version {SCHEMA_VERSION}. "
            f"Please regenerate the baseline with the current version of buildCheckDSM.py"
        )
    
    # Extract and validate metadata
    metadata = data.get("metadata", {})
    baseline_build_dir = metadata.get("build_directory", "unknown")
    baseline_hostname = metadata.get("hostname", "unknown")
    
    current_build_dir_abs = os.path.abspath(current_build_directory)
    current_hostname = _get_hostname()
    
    # Strict validation: build directory and hostname must match
    if baseline_build_dir != current_build_dir_abs or baseline_hostname != current_hostname:
        error_msg = (
            f"Baseline must be from the same build directory and system.\n"
            f"  Expected: {baseline_build_dir} on {baseline_hostname}\n"
            f"  Got:      {current_build_dir_abs} on {current_hostname}"
        )
        logger.error("Build directory or hostname mismatch")
        raise ValueError(error_msg)
    
    logger.info("Baseline metadata validated successfully")
    logger.debug("Baseline timestamp: %s", metadata.get("timestamp", "unknown"))
    logger.debug("Baseline git commit: %s", metadata.get("git_commit", "unknown"))
    
    # Load unfiltered data
    unfiltered_headers = set(data.get("unfiltered_headers", data["sorted_headers"]))
    unfiltered_include_graph_data = data.get("unfiltered_include_graph", data["header_to_headers"])
    
    # Inherit filter settings from baseline if not specified
    baseline_filter = metadata.get("filter_pattern", "")
    baseline_excludes = metadata.get("exclude_patterns", [])
    
    if filter_pattern is None:
        filter_pattern = baseline_filter
        if baseline_filter:
            logger.info("Inheriting filter pattern from baseline: %s", baseline_filter)
    
    if exclude_patterns is None:
        exclude_patterns = baseline_excludes
        if baseline_excludes:
            logger.info("Inheriting exclude patterns from baseline: %s", baseline_excludes)
    
    # Apply filters to unfiltered data
    filtered_headers = unfiltered_headers
    
    if filter_pattern and project_root:
        from lib.file_utils import filter_headers_by_pattern
        filtered_headers = filter_headers_by_pattern(filtered_headers, filter_pattern, project_root)
        logger.info("Applied filter '%s': %d -> %d headers", filter_pattern, len(unfiltered_headers), len(filtered_headers))
    
    if exclude_patterns and project_root:
        from lib.file_utils import exclude_headers_by_patterns
        filtered_headers, excluded_count, _ = exclude_headers_by_patterns(filtered_headers, exclude_patterns, project_root)
        logger.info("Applied %d exclude patterns: excluded %d headers", len(exclude_patterns), excluded_count)
    
    if not filtered_headers:
        raise ValueError("No headers remaining after applying filters to baseline")
    
    # Rebuild include graph with only filtered headers
    unfiltered_include_graph = defaultdict(set)
    for header, deps in unfiltered_include_graph_data.items():
        unfiltered_include_graph[header] = set(deps)
    
    # Re-run DSM analysis on filtered data
    from lib.dsm_analysis import run_dsm_analysis
    logger.info("Re-computing DSM analysis on filtered baseline (%d headers)", len(filtered_headers))
    results = run_dsm_analysis(
        filtered_headers,
        unfiltered_include_graph,
        compute_layers=True,
        show_progress=False
    )
    
    file_size = os.path.getsize(filename)
    size_kb = file_size / 1024
    print_success(f"Loaded baseline DSM analysis results from {filename} ({size_kb:.1f} KB)")
    logger.info("Baseline: %d headers (filtered from %d unfiltered headers)", 
                len(results.sorted_headers), len(unfiltered_headers))
    
    return results
