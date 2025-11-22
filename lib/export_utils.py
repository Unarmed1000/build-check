#!/usr/bin/env python3
"""Export utilities for writing analysis results to various file formats."""

import os
import csv
import json
import logging
from collections import defaultdict
from typing import Dict, Set, List, DefaultDict, Any, Optional, TYPE_CHECKING, cast

if TYPE_CHECKING:
    import networkx as nx
    NX_AVAILABLE: bool = True
else:
    try:
        import networkx as nx
        NX_AVAILABLE = True
    except ImportError:
        nx = None  # type: ignore[assignment]
        NX_AVAILABLE = False

from lib.color_utils import Colors, print_error, print_success
from lib.graph_utils import DSMMetrics

logger = logging.getLogger(__name__)

# Verification flag (cached to avoid repeated checks)
_requirements_verified = False


def verify_requirements() -> None:
    """Verify that networkx is installed with correct version.
    
    This should be called by scripts that use export_utils graph features before processing.
    Raises ImportError if requirements are not met. Results are cached.
    
    Raises:
        ImportError: If networkx is missing or version is too old
    """
    global _requirements_verified
    
    if _requirements_verified:
        return
    
    from lib.package_verification import check_package_version
    
    # This will raise ImportError if networkx is missing or too old
    check_package_version('networkx', raise_on_error=True)
    
    _requirements_verified = True


def export_dsm_to_csv(filename: str,
                      headers: List[str],
                      header_to_headers: DefaultDict[str, Set[str]],
                      metrics: Dict[str, DSMMetrics],
                      project_root: str) -> None:
    """Export full DSM (Dependency Structure Matrix) to CSV file.
    
    Args:
        filename: Output CSV filename
        headers: List of all headers
        header_to_headers: Mapping of headers to their dependencies
        metrics: Per-header metrics (DSMMetrics)
        project_root: Root directory of the project
    """
    try:
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Create relative paths for headers
            rel_headers = []
            for header in headers:
                rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                rel_headers.append(rel_path)
            
            # Write header row (with metrics columns)
            header_row = ['Header', 'Fan-out', 'Fan-in', 'Coupling', 'Stability'] + rel_headers
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
        
        logger.info(f"Exported DSM to {filename}")
        print_success(f"Exported full matrix to {filename}")
        
    except IOError as e:
        logger.error(f"Failed to export CSV: {e}")
        print_error(f"Failed to export CSV: {e}")


def export_dependency_graph(filename: str,
                            directed_graph: Any,  # nx.DiGraph
                            metrics: Dict[str, Any],
                            cycles: List[Set[str]],
                            project_root: str,
                            header_to_lib: Optional[Dict[str, str]] = None,
                            header_to_headers: Optional[DefaultDict[str, Set[str]]] = None) -> None:
    """Export dependency graph to various formats.
    
    Supports: GraphML (.graphml), DOT (.dot), GEXF (.gexf), JSON (.json)
    
    Node attributes:
        - label: File basename
        - path: Full file path
        - fan_in, fan_out, coupling, stability: Dependency metrics
        - in_cycle: Whether node participates in circular dependency
        - library: Library name (e.g., "libFslBase.a") if header_to_lib provided
        - library_type: "executable" or "library" 
        - library_name: Clean library name (e.g., "FslBase")
    
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
    """
    if not NX_AVAILABLE:
        logger.error("networkx is required for graph export")
        print_error("networkx is required for graph export. Install with: pip install networkx")
        return
    
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
        
        # Add node attributes
        for node in G.nodes():
            m = metrics.get(node)
            rel_path = os.path.relpath(node, project_root) if node.startswith(project_root) else node
            
            G.nodes[node]['label'] = os.path.basename(node)
            G.nodes[node]['path'] = rel_path
            if m is not None:
                G.nodes[node]['fan_in'] = m.fan_in
                G.nodes[node]['fan_out'] = m.fan_out
                G.nodes[node]['coupling'] = m.coupling
                G.nodes[node]['stability'] = m.stability
            else:
                G.nodes[node]['fan_in'] = 0
                G.nodes[node]['fan_out'] = 0
                G.nodes[node]['coupling'] = 0
                G.nodes[node]['stability'] = 0.0
            G.nodes[node]['in_cycle'] = node in headers_in_cycles
            
            # Add library/module grouping information
            if header_to_lib:
                library = header_to_lib.get(node, 'unknown')
                G.nodes[node]['library'] = library
                # Determine if this is an executable or library
                G.nodes[node]['library_type'] = 'executable' if library.startswith('bin') else 'library'
                # Extract library category (e.g., "FslBase" from "libFslBase.a")
                if library.startswith('lib') and library.endswith('.a'):
                    lib_name = library[3:-2]  # Remove "lib" prefix and ".a" suffix
                else:
                    lib_name = library
                G.nodes[node]['library_name'] = lib_name
        
        # Add edge attributes for cross-library dependencies
        if header_to_lib:
            for u, v in G.edges():
                lib_u = header_to_lib.get(u, 'unknown')
                lib_v = header_to_lib.get(v, 'unknown')
                G.edges[u, v]['cross_library'] = (lib_u != lib_v)
                G.edges[u, v]['source_library'] = lib_u
                G.edges[u, v]['target_library'] = lib_v
        
        # Export based on format
        if ext == '.graphml':
            nx.write_graphml(G, filename)
        elif ext == '.dot':
            nx.drawing.nx_pydot.write_dot(G, filename)
        elif ext == '.gexf':
            nx.write_gexf(G, filename)
        elif ext == '.json':
            from networkx.readwrite import json_graph
            data = json_graph.node_link_data(G)
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
        else:
            logger.warning(f"Unsupported graph format: {ext}. Defaulting to GraphML.")
            nx.write_graphml(G, filename + '.graphml')
            filename = filename + '.graphml'
        
        logger.info(f"Exported dependency graph to {filename}")
        print_success(f"Exported dependency graph to {filename}")
        
    except ImportError:
        logger.error("Missing dependency for graph export")
        print_error("Missing dependency for graph export. Install pydot for DOT format.")
    except Exception as e:
        logger.error(f"Failed to export graph: {e}")
        print_error(f"Failed to export graph: {e}")
