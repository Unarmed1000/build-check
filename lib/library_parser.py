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
"""Parser for build.ninja to extract library dependency information."""

import os
import re
import logging
from typing import Dict, Set, Tuple, Any, List
from collections import defaultdict
from pathlib import Path
from dataclasses import dataclass

import networkx as nx
from lib.graph_utils import build_transitive_dependents_map, find_strongly_connected_components

logger = logging.getLogger(__name__)


@dataclass
class CrossLibraryAnalysis:
    """Result from analyzing cross-library dependency violations.

    Attributes:
        total_deps: Total number of dependencies analyzed
        intra_library_deps: Count of dependencies within the same library
        cross_library_deps: Count of dependencies crossing library boundaries
        library_violations: Mapping of library pairs to violation counts (lib -> lib -> count)
        worst_offenders: Top headers with most cross-library dependencies [(header, count), ...]
    """

    total_deps: int
    intra_library_deps: int
    cross_library_deps: int
    library_violations: Dict[str, Dict[str, int]]
    worst_offenders: List[Tuple[str, int]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility and JSON serialization.

        Returns:
            Dictionary with all analysis results
        """
        return {
            "total_deps": self.total_deps,
            "intra_library_deps": self.intra_library_deps,
            "cross_library_deps": self.cross_library_deps,
            "library_violations": self.library_violations,
            "worst_offenders": self.worst_offenders,
        }


def infer_library_from_source(source_path: str) -> str:
    """Infer library name from source file path.

    Args:
        source_path: Path to source file (e.g., /path/to/FslBase/source/file.cpp)

    Returns:
        Library name (e.g., 'libFslBase.a')
    """
    parts = source_path.split(os.sep)

    # Look for library directory (usually parent of source/ or include/)
    for i, part in enumerate(parts):
        if part in ["source", "src", "include"] and i > 0:
            lib_name = parts[i - 1]
            return f"lib{lib_name}.a"

    # Fallback: use directory containing the file
    if len(parts) >= 2:
        lib_name = parts[-2]
        return f"lib{lib_name}.a"

    return "libUnknown.a"


def map_headers_to_libraries(all_headers: Set[str]) -> Dict[str, str]:
    """Map each header to its containing library based on the header's path.

    Headers belong to the library they're physically part of, determined by
    their directory structure (e.g., FslBase/include -> libFslBase.a).

    Args:
        all_headers: Set of all header paths

    Returns:
        Dict mapping header path to library name
    """
    header_to_lib: Dict[str, str] = {}

    # Each header belongs to the library indicated by its path structure
    for header in all_headers:
        header_to_lib[header] = infer_library_from_source(header)

    return header_to_lib


def analyze_cross_library_dependencies(header_to_headers: Dict[str, Set[str]], header_to_lib: Dict[str, str]) -> CrossLibraryAnalysis:
    """Analyze dependencies that cross library boundaries.

    Returns statistics about cross-library coupling.

    Args:
        header_to_headers: Mapping of headers to their dependencies
        header_to_lib: Mapping of headers to their library names

    Returns:
        CrossLibraryAnalysis with statistics about cross-library dependencies
    """
    library_violations: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total_deps = 0
    intra_library_deps = 0
    cross_library_deps = 0

    header_cross_lib_counts: Dict[str, int] = defaultdict(int)

    for header, deps in header_to_headers.items():
        header_lib = header_to_lib.get(header, "unknown")

        for dep in deps:
            total_deps += 1
            dep_lib = header_to_lib.get(dep, "unknown")

            if header_lib == dep_lib:
                intra_library_deps += 1
            else:
                cross_library_deps += 1
                library_violations[header_lib][dep_lib] += 1
                header_cross_lib_counts[header] += 1

    # Find worst offenders (headers with most cross-library deps)
    sorted_offenders = sorted(header_cross_lib_counts.items(), key=lambda x: x[1], reverse=True)
    worst_offenders = sorted_offenders[:10]

    return CrossLibraryAnalysis(
        total_deps=total_deps,
        intra_library_deps=intra_library_deps,
        cross_library_deps=cross_library_deps,
        library_violations=dict(library_violations),
        worst_offenders=worst_offenders,
    )


def parse_ninja_libraries(build_ninja_path: str) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]], Set[str], Set[str]]:
    """Parse build.ninja to extract library and executable dependencies.

    Args:
        build_ninja_path: Path to build.ninja file

    Returns:
        Tuple of:
        - lib_to_libs: Library → Libraries it depends on
        - exe_to_libs: Executable → Libraries it depends on
        - all_libs: Set of all library names
        - all_exes: Set of all executable names
    """
    lib_to_libs: Dict[str, Set[str]] = defaultdict(set)
    exe_to_libs: Dict[str, Set[str]] = defaultdict(set)
    all_libs: Set[str] = set()
    all_exes: Set[str] = set()

    # Regex patterns for build rules
    lib_pattern = re.compile(r"^build\s+(\S+\.a):\s+CXX_STATIC_LIBRARY_LINKER")
    exe_pattern = re.compile(r"^build\s+(\S+):\s+CXX_EXECUTABLE_LINKER")

    logger.info("Parsing %s...", build_ninja_path)

    try:
        with open(build_ninja_path, "r", encoding="utf-8") as f:
            for _, line in enumerate(f, 1):
                line = line.rstrip()

                # Check for library build rule
                lib_match = lib_pattern.match(line)
                if lib_match:
                    lib_path = lib_match.group(1)
                    lib_name = os.path.basename(lib_path)
                    all_libs.add(lib_name)

                    # Extract dependencies from the || section
                    if "||" in line:
                        deps_section = line.split("||")[1]
                        deps = re.findall(r"(\S+\.a)", deps_section)
                        for dep_path in deps:
                            dep_name = os.path.basename(dep_path)
                            if dep_name != lib_name:  # Avoid self-dependencies
                                lib_to_libs[lib_name].add(dep_name)
                                all_libs.add(dep_name)
                    continue

                # Check for executable build rule
                exe_match = exe_pattern.match(line)
                if exe_match:
                    exe_path = exe_match.group(1)
                    exe_name = os.path.basename(exe_path)
                    all_exes.add(exe_name)

                    # Extract library dependencies from the || section
                    if "||" in line:
                        deps_section = line.split("||")[1]
                        deps = re.findall(r"(\S+\.a)", deps_section)
                        for dep_path in deps:
                            dep_name = os.path.basename(dep_path)
                            exe_to_libs[exe_name].add(dep_name)
                            all_libs.add(dep_name)
                    continue

    except IOError as e:
        logger.error("Failed to read %s: %s", build_ninja_path, e)
        raise

    logger.info("Found %s libraries and %s executables", len(all_libs), len(all_exes))
    return dict(lib_to_libs), dict(exe_to_libs), all_libs, all_exes


def compute_library_metrics(lib_to_libs: Dict[str, Set[str]], exe_to_libs: Dict[str, Set[str]], all_libs: Set[str]) -> Dict[str, Dict[str, int]]:
    """Compute metrics for each library.

    Args:
        lib_to_libs: Library → Libraries it depends on
        exe_to_libs: Executable → Libraries it depends on
        all_libs: Set of all library names

    Returns:
        Dictionary mapping library name to metrics:
        - fan_out: Number of direct library dependencies
        - fan_in: Number of libraries/executables that directly depend on this
        - transitive_dependents: Total transitive dependents
        - depth: Maximum depth in dependency tree
    """
    metrics = {}

    # Calculate fan-out (direct dependencies)
    for lib in all_libs:
        metrics[lib] = {"fan_out": len(lib_to_libs.get(lib, set())), "fan_in": 0, "transitive_dependents": 0, "depth": 0}

    # Calculate fan-in (direct dependents)
    for deps in lib_to_libs.values():
        for dep in deps:
            if dep in metrics:
                metrics[dep]["fan_in"] += 1

    for deps in exe_to_libs.values():
        for dep in deps:
            if dep in metrics:
                metrics[dep]["fan_in"] += 1

    # Calculate transitive dependents using graph_utils
    try:
        transitive_deps = build_transitive_dependents_map(lib_to_libs, exe_to_libs)
        for lib in all_libs:
            metrics[lib]["transitive_dependents"] = len(transitive_deps.get(lib, set()))
    except Exception as e:
        logger.debug("Could not compute transitive dependents: %s", e)

    # Calculate depth using NetworkX
    G: nx.DiGraph[str] = nx.DiGraph()
    for lib, deps in lib_to_libs.items():
        G.add_node(lib)
        for dep in deps:
            G.add_edge(lib, dep)

    # Depth = longest path from this node to any leaf
    for lib in all_libs:
        if lib not in G:
            continue
        try:
            descendants = list(nx.descendants(G, lib))
            if not descendants:
                metrics[lib]["depth"] = 0
            else:
                max_depth = 0
                for desc in descendants:
                    try:
                        path_len = nx.shortest_path_length(G, lib, desc)
                        max_depth = max(max_depth, int(path_len))
                    except nx.NetworkXNoPath:
                        continue
                metrics[lib]["depth"] = max_depth
        except Exception:
            metrics[lib]["depth"] = 0

    return metrics


def find_unused_libraries(lib_to_libs: Dict[str, Set[str]], exe_to_libs: Dict[str, Set[str]], all_libs: Set[str]) -> Set[str]:
    """Find libraries that are not used by any executable or other library.

    Args:
        lib_to_libs: Library → Libraries it depends on
        exe_to_libs: Executable → Libraries it depends on
        all_libs: Set of all library names

    Returns:
        Set of unused library names
    """
    used_libs = set()

    # Collect all libraries that are dependencies
    for deps in lib_to_libs.values():
        used_libs.update(deps)
    for deps in exe_to_libs.values():
        used_libs.update(deps)

    unused = all_libs - used_libs
    logger.info("Found %s unused libraries", len(unused))
    return unused


def find_library_cycles(lib_to_libs: Dict[str, Set[str]]) -> List[Set[str]]:
    """Find circular dependencies among libraries.

    Args:
        lib_to_libs: Library → Libraries it depends on

    Returns:
        List of cycles (each cycle is a set of library names)
    """
    # Build a simple graph structure
    all_libs = set(lib_to_libs.keys())
    for deps in lib_to_libs.values():
        all_libs.update(deps)

    # Build NetworkX graph
    G: nx.DiGraph[str] = nx.DiGraph()
    for lib, deps in lib_to_libs.items():
        G.add_node(lib)
        for dep in deps:
            G.add_edge(lib, dep)

    cycles, self_loops = find_strongly_connected_components(G)
    logger.info("Found %s circular dependencies", len(cycles))
    return cycles


def infer_library_from_path(file_path: str) -> str:
    """Infer library name from a file path.

    Heuristic: Extract the component name from paths like:
    - /path/to/DemoFramework/FslBase/source/...
    - /path/to/DemoApps/GLES3/S01_SimpleTriangle/...

    Args:
        file_path: Path to a source file

    Returns:
        Inferred library name or "Unknown"
    """
    path = Path(file_path)
    parts = path.parts

    # Look for DemoFramework or DemoApps components
    for i, part in enumerate(parts):
        if part in ("DemoFramework", "DemoApps"):
            if i + 1 < len(parts):
                component = parts[i + 1]
                # For DemoFramework, return FslXXX directly
                if part == "DemoFramework" and component.startswith("Fsl"):
                    return component
                # For DemoApps, return category/app
                if part == "DemoApps" and i + 2 < len(parts):
                    category = parts[i + 1]
                    app = parts[i + 2]
                    return f"{category}/{app}"

    # Fallback: try to find any Fsl* component
    for part in parts:
        if part.startswith("Fsl"):
            return part

    return "Unknown"
