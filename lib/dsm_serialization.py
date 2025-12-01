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
from typing import Dict, Set, List, Any, Optional, DefaultDict, Tuple, TypedDict
from collections import defaultdict

from networkx.readwrite import json_graph

from .dsm_types import DSMAnalysisResults, MatrixStatistics
from .graph_utils import DSMMetrics
from .color_utils import print_success
from .clang_utils import FileType
from .constants import BuildCheckError, EXIT_INVALID_ARGS

logger = logging.getLogger(__name__)

# Current schema version - increment when format changes
SCHEMA_VERSION = "1.2"


class FileRecord(TypedDict):
    """File record with path and classification type.

    Used in baseline serialization (v1.2+) to store file classifications.

    Attributes:
        path: Absolute file path
        type: FileType as integer (SYSTEM=1, THIRD_PARTY=2, GENERATED=3, PROJECT=4)
    """

    path: str
    type: int


class SchemaVersionError(BuildCheckError):
    """Baseline schema version is incompatible.

    Raised when attempting to load a baseline with an outdated schema version.
    No automatic migration is supported - user must regenerate the baseline.
    """

    def __init__(self, version: str):
        super().__init__(
            f"Baseline schema v{version} is outdated. " f"Please regenerate baseline with current buildCheckDSM.py (v{SCHEMA_VERSION}+)",
            exit_code=EXIT_INVALID_ARGS,
        )


def _get_git_commit() -> str:
    """Get current git commit hash.

    Returns:
        Git commit hash or "unknown" if not in a git repository or git unavailable
    """
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=False)
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
        "fan_out_external": metrics.fan_out_external,
        "fan_out_project": metrics.fan_out_project,
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
    all_files: Set[str],
    unfiltered_include_graph: DefaultDict[str, Set[str]],
    file_types: Dict[str, FileType],
    filename: str,
    build_directory: str,
    filter_pattern: Optional[str] = None,
    exclude_patterns: Optional[List[str]] = None,
) -> None:
    """Save DSM analysis results to compressed JSON file (schema v1.2).

    Saves the UNFILTERED file set with classifications and include graph to allow
    applying different filters when loading the baseline. This makes baselines more
    flexible and reusable.

    Args:
        results: DSMAnalysisResults to save (computed from filtered headers)
        all_files: Complete set of files (headers + sources) before any filtering
        unfiltered_include_graph: Complete include graph before any filtering
        file_types: Pre-computed file type classifications for all files
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
        "unfiltered_file_count": len(all_files),
        "filtered_header_count": len(results.sorted_headers),
    }

    # Serialize metrics (sorted by header name)
    metrics_dict = {header: _serialize_dsm_metrics(metric) for header, metric in sorted(results.metrics.items())}

    # Serialize cycles (convert sets to sorted lists)
    cycles_list = [sorted(list(cycle)) for cycle in results.cycles]
    cycles_list.sort()  # Sort cycles themselves for determinism

    # Serialize graph using NetworkX json_graph
    graph_data = json_graph.node_link_data(results.directed_graph)
    # Sort nodes and edges for determinism
    graph_data["nodes"] = sorted(graph_data["nodes"], key=lambda x: x["id"])
    graph_data["links"] = sorted(graph_data["links"], key=lambda x: (x["source"], x["target"]))

    # Serialize layers (already lists, just ensure determinism)
    layers_list = [sorted(layer) for layer in results.layers]

    # Serialize unfiltered data with file classifications (schema v1.2)
    # FileRecord format: {"path": str, "type": int}
    files_list: List[FileRecord] = [{"path": p, "type": int(file_types[p])} for p in sorted(all_files)]
    unfiltered_include_graph_dict = {header: sorted(list(deps)) for header, deps in sorted(unfiltered_include_graph.items())}

    # Build complete data structure with sorted keys
    data = {
        "_description": "DSM analysis results - DO NOT EDIT MANUALLY",
        "_schema_version": SCHEMA_VERSION,
        "cycles": cycles_list,
        "feedback_edges": sorted([list(edge) for edge in results.feedback_edges]),
        "files": files_list,
        "graph": graph_data,
        "has_cycles": results.has_cycles,
        "header_to_headers": {header: sorted(list(deps)) for header, deps in sorted(results.header_to_headers.items())},
        "header_to_layer": dict(sorted(results.header_to_layer.items())),
        "headers_in_cycles": sorted(list(results.headers_in_cycles)),
        "layers": layers_list,
        "metadata": metadata,
        "metrics": metrics_dict,
        "reverse_deps": {header: sorted(list(deps)) for header, deps in sorted(results.reverse_deps.items())},
        "sorted_headers": results.sorted_headers,
        "stats": _serialize_matrix_statistics(results.stats),
        "unfiltered_include_graph": unfiltered_include_graph_dict,
    }

    # Write to gzip-compressed JSON with sorted keys
    try:
        with gzip.open(filename, "wt", encoding="utf-8") as f:
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
        fan_out_project=data["fan_out_project"],
        fan_out_external=data["fan_out_external"],
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


def load_dsm_results(filename: str, current_build_directory: str, project_root: str) -> Tuple[Set[str], DefaultDict[str, Set[str]], Dict[str, FileType]]:
    """Load DSM analysis results from compressed JSON file (returns unfiltered data).

    Loads the unfiltered baseline data for re-filtering by caller. This ensures
    100% identical filtering logic is applied to both current and baseline analysis.

    Schema v1.2+ includes file type classifications pre-computed at baseline creation.

    Args:
        filename: Input filename (gzip compressed JSON)
        current_build_directory: Current build directory for validation
        project_root: Project root directory

    Returns:
        Tuple of (unfiltered_headers, unfiltered_include_graph, file_types)
        - unfiltered_headers: Set of all headers before filtering
        - unfiltered_include_graph: Include graph before filtering
        - file_types: Pre-computed file classifications

    Raises:
        SchemaVersionError: If schema version is outdated (< 1.2)
        ValueError: If validation fails
        IOError: If file cannot be read
    """
    logger.info("Loading DSM results from %s", filename)

    try:
        with gzip.open(filename, "rt", encoding="utf-8") as f:
            data = json.load(f)
    except (IOError, OSError) as e:
        logger.error("Failed to load DSM results: %s", e)
        raise IOError(f"Failed to load DSM results from {filename}: {e}") from e
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in DSM file: %s", e)
        raise ValueError(f"Invalid JSON in {filename}: {e}") from e

    # Validate schema version (strict check - no backward compatibility)
    file_version = data.get("_schema_version", "unknown")
    if file_version != SCHEMA_VERSION:
        raise SchemaVersionError(file_version)

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

    # Load unfiltered data with file classifications (schema v1.2)
    files_list: List[FileRecord] = data["files"]

    # Extract headers (filter out source files) and file_types
    unfiltered_headers: Set[str] = set()
    file_types: Dict[str, FileType] = {}

    for file_record in files_list:
        path = file_record["path"]
        file_type = FileType(file_record["type"])
        file_types[path] = file_type

        # Add to headers if it's a header file (has header extension)
        if any(path.endswith(ext) for ext in (".h", ".hpp", ".hxx", ".hh")):
            unfiltered_headers.add(path)

    unfiltered_include_graph_data = data["unfiltered_include_graph"]

    # Rebuild include graph
    unfiltered_include_graph: DefaultDict[str, Set[str]] = defaultdict(set)
    for header, deps in unfiltered_include_graph_data.items():
        unfiltered_include_graph[header] = set(deps)

    file_size = os.path.getsize(filename)
    size_kb = file_size / 1024
    print_success(f"Loaded baseline DSM results from {filename} ({size_kb:.1f} KB)")
    logger.info("Baseline: %d files, %d headers loaded", len(file_types), len(unfiltered_headers))

    return unfiltered_headers, unfiltered_include_graph, file_types
