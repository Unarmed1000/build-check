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
"""Export utilities for writing analysis results to various file formats."""

import os
import csv
import json
import logging
from typing import Dict, Set, List, DefaultDict, Any, Optional

import networkx as nx
from networkx.readwrite import json_graph

from lib.color_utils import print_error, print_success
from lib.graph_utils import DSMMetrics

logger = logging.getLogger(__name__)


def export_dsm_to_csv(
    filename: str, headers: List[str], header_to_headers: DefaultDict[str, Set[str]], metrics: Dict[str, DSMMetrics], project_root: str
) -> None:
    """Export full DSM (Dependency Structure Matrix) to CSV file.

    Args:
        filename: Output CSV filename
        headers: List of all headers
        header_to_headers: Mapping of headers to their dependencies
        metrics: Per-header metrics (DSMMetrics)
        project_root: Root directory of the project
    """
    try:
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # Create relative paths for headers
            rel_headers = []
            for header in headers:
                rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                rel_headers.append(rel_path)

            # Write header row (with metrics columns)
            header_row = ["Header", "Fan-out", "Fan-in", "Coupling", "Stability"] + rel_headers
            writer.writerow(header_row)

            # Write data rows
            for i, header in enumerate(headers):
                rel_header = rel_headers[i]
                m = metrics.get(header)

                if m is not None:
                    row = [rel_header, m.fan_out, m.fan_in, m.coupling, f"{m.stability:.3f}"]
                else:
                    row = [rel_header, 0, 0, 0, "0.000"]

                # Add dependency cells
                deps = header_to_headers.get(header, set())
                for other_header in headers:
                    row.append(1 if other_header in deps else 0)

                writer.writerow(row)

        logger.info("Exported DSM to %s", filename)
        print_success(f"Exported full matrix to {filename}")

    except IOError as e:
        logger.error("Failed to export CSV: %s", e)
        print_error(f"Failed to export CSV: {e}")


def export_dependency_graph(
    filename: str,
    directed_graph: Any,  # nx.DiGraph
    metrics: Dict[str, Any],
    cycles: List[Set[str]],
    project_root: str,
    header_to_lib: Optional[Dict[str, str]] = None,
    header_to_headers: Optional[DefaultDict[str, Set[str]]] = None,
    include_advanced_metrics: bool = True,
) -> None:
    """Export dependency graph to various formats with comprehensive metrics.

    Supports: GraphML (.graphml), DOT (.dot), GEXF (.gexf), JSON (.json)

    Node attributes (basic):
        - label: File basename
        - path: Full file path
        - fan_in, fan_out, coupling, stability: Dependency metrics
        - in_cycle: Whether node participates in circular dependency
        - library: Library name (e.g., "libFslBase.a") if header_to_lib provided
        - library_type: "executable" or "library"
        - library_name: Clean library name (e.g., "FslBase")

    Node attributes (advanced, if include_advanced_metrics=True):
        - pagerank: PageRank centrality score (architectural importance)
        - betweenness: Betweenness centrality (bottleneck indicator)
        - is_hub: Boolean indicating hub node (high connectivity)
        - is_god_object: Boolean indicating god object anti-pattern
        - is_interface: Boolean indicating stable interface (stability < 0.3)
        - z_score: Coupling outlier z-score

    Edge attributes (when header_to_lib provided):
        - cross_library: Boolean indicating cross-library dependency
        - source_library: Source node's library
        - target_library: Target node's library

    Args:
        filename: Output filename (extension determines format)
        directed_graph: NetworkX directed graph
        metrics: Per-header metrics
        cycles: List of circular dependency groups
        project_root: Root directory of the project
        header_to_lib: Optional mapping of headers to library names
        header_to_headers: Optional full dependency mapping to include all edges
        include_advanced_metrics: Whether to compute and include advanced metrics (default: True)
    """
    try:
        # Determine format from extension
        ext = os.path.splitext(filename)[1].lower()

        # Create a copy of the graph with attributes for visualization
        G = directed_graph.copy()

        # Add missing edges from header_to_headers (for filtered graphs)
        if header_to_headers:
            for header in list(G.nodes()):
                if header in header_to_headers:
                    for dep in header_to_headers[header]:
                        # Add edge even if dep is not in the filtered node set
                        # This preserves all outgoing dependencies
                        if not G.has_node(dep):
                            G.add_node(dep)
                        if not G.has_edge(header, dep):
                            G.add_edge(header, dep)

        # Identify headers in cycles
        headers_in_cycles = set()
        for cycle in cycles:
            headers_in_cycles.update(cycle)

        # Compute advanced metrics if requested
        pagerank_scores: Dict[str, float] = {}
        betweenness_scores: Dict[str, float] = {}
        hub_nodes: Set[str] = set()
        god_objects: Set[str] = set()
        outliers: Set[str] = set()
        z_scores: Dict[str, float] = {}

        if include_advanced_metrics:
            try:
                from lib.graph_utils import (
                    compute_pagerank_centrality,
                    compute_betweenness_centrality,
                    find_hub_nodes,
                    detect_god_objects,
                    detect_coupling_outliers,
                )

                # PageRank (architectural importance)
                pagerank_scores = compute_pagerank_centrality(G)

                # Betweenness centrality (bottleneck detection)
                # Sample for large graphs to keep it fast
                k = min(1000, len(G.nodes())) if len(G.nodes()) > 2000 else None
                betweenness_scores = compute_betweenness_centrality(G, k=k)

                # Hub nodes (high connectivity)
                hubs = find_hub_nodes(G, threshold=15)
                hub_nodes = {h[0] for h in hubs}

                # God objects (extreme fan-out)
                gods = detect_god_objects(metrics, threshold=50)
                god_objects = {g[0] for g in gods}

                # Coupling outliers (z-score analysis)
                outlier_list, mean, stddev = detect_coupling_outliers(metrics, z_threshold=2.5)
                outliers = {o[0] for o in outlier_list}
                z_scores = {o[0]: o[2] for o in outlier_list}

            except Exception as e:
                logger.warning("Could not compute advanced metrics: %s", e)

        # Add node attributes
        for node in G.nodes():
            m = metrics.get(node)
            rel_path = os.path.relpath(node, project_root) if node.startswith(project_root) else node

            G.nodes[node]["label"] = os.path.basename(node)
            G.nodes[node]["path"] = rel_path
            if m is not None:
                G.nodes[node]["fan_in"] = m.fan_in
                G.nodes[node]["fan_out"] = m.fan_out
                G.nodes[node]["coupling"] = m.coupling
                G.nodes[node]["stability"] = m.stability
            else:
                G.nodes[node]["fan_in"] = 0
                G.nodes[node]["fan_out"] = 0
                G.nodes[node]["coupling"] = 0
                G.nodes[node]["stability"] = 0.0
            G.nodes[node]["in_cycle"] = node in headers_in_cycles

            # Add advanced metrics
            if include_advanced_metrics:
                G.nodes[node]["pagerank"] = pagerank_scores.get(node, 0.0)
                G.nodes[node]["betweenness"] = betweenness_scores.get(node, 0.0)
                G.nodes[node]["is_hub"] = node in hub_nodes
                G.nodes[node]["is_god_object"] = node in god_objects
                G.nodes[node]["is_interface"] = m.stability < 0.3 if m else False
                G.nodes[node]["is_outlier"] = node in outliers
                G.nodes[node]["z_score"] = z_scores.get(node, 0.0)

            # Add library/module grouping information
            if header_to_lib:
                library = header_to_lib.get(node, "unknown")
                G.nodes[node]["library"] = library
                # Determine if this is an executable or library
                G.nodes[node]["library_type"] = "executable" if library.startswith("bin") else "library"
                # Extract library category (e.g., "FslBase" from "libFslBase.a")
                if library.startswith("lib") and library.endswith(".a"):
                    lib_name = library[3:-2]  # Remove "lib" prefix and ".a" suffix
                else:
                    lib_name = library
                G.nodes[node]["library_name"] = lib_name

        # Add edge attributes for cross-library dependencies
        if header_to_lib:
            for u, v in G.edges():
                lib_u = header_to_lib.get(u, "unknown")
                lib_v = header_to_lib.get(v, "unknown")
                G.edges[u, v]["cross_library"] = lib_u != lib_v
                G.edges[u, v]["source_library"] = lib_u
                G.edges[u, v]["target_library"] = lib_v

        # Export based on format
        if ext == ".graphml":
            nx.write_graphml(G, filename)
        elif ext == ".dot":
            nx.drawing.nx_pydot.write_dot(G, filename)
        elif ext == ".gexf":
            nx.write_gexf(G, filename)
        elif ext == ".json":
            data = json_graph.node_link_data(G)
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        else:
            logger.warning("Unsupported graph format: %s. Defaulting to GraphML.", ext)
            nx.write_graphml(G, filename + ".graphml")
            filename = filename + ".graphml"

        logger.info("Exported dependency graph to %s", filename)
        print_success(f"Exported dependency graph to {filename}")

    except ImportError:
        logger.error("Missing dependency for graph export")
        print_error("Missing dependency for graph export. Install pydot for DOT format.")
    except Exception as e:
        logger.error("Failed to export graph: %s", e)
        print_error(f"Failed to export graph: {e}")
