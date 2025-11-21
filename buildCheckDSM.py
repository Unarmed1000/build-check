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
"""Dependency Structure Matrix (DSM) analysis for C++ header dependencies.

Version: 1.0.0

PURPOSE:
    Visualizes header dependencies as a Dependency Structure Matrix, providing a
    comprehensive architectural view of the codebase. Identifies circular dependencies,
    analyzes layered architecture, and highlights high-coupling headers that may need
    refactoring.

WHAT IT DOES:
    - Builds a Dependency Structure Matrix showing header-to-header dependencies
    - Detects circular dependencies (strongly connected components)
    - Computes architectural layers using topological ordering
    - Calculates per-header metrics: fan-in, fan-out, stability, coupling
    - Identifies headers that violate layered architecture
    - Provides compact matrix visualization with color coding
    - Exports full matrix to CSV for detailed offline analysis

USE CASES:
    - "Show me the overall dependency structure of my codebase"
    - "Which headers are in circular dependencies?"
    - "Is my architecture properly layered?"
    - "What's the safest order to refactor headers?"
    - "Which headers have the highest coupling?"
    - "Are my module boundaries clean?"

METHOD:
    Parses header files directly using buildCheckDependencyHell's build_include_graph()
    to build an accurate directed dependency graph, then constructs a Dependency Structure
    Matrix showing which headers include which. Applies graph algorithms (SCC detection,
    topological sorting) to analyze architectural properties.

OUTPUT:
    1. Summary Statistics:
       - Matrix size, sparsity, total dependencies
       - Cycle count, layer count
    
    2. Dependency Structure Matrix (Visual):
       - Compact matrix view (top N×N most coupled headers)
       - Color-coded by coupling strength (green/yellow/red)
    
    3. Circular Dependencies:
       - List of cycles with participants
       - Suggested edges to break cycles
    
    4. Layered Architecture:
       - Headers grouped by dependency layer
       - Layer violations (back-edges)
    
    5. High-Coupling Headers:
       - Headers with highest fan-in/fan-out
       - Stability analysis

METRICS EXPLAINED:
    - Fan-out: Number of headers this header includes
    - Fan-in: Number of headers that include this header
    - Coupling: Total dependencies (fan-in + fan-out)
    - Stability: Fan-out / (Fan-in + Fan-out) - measures resistance to change
    - Sparsity: Percentage of empty cells in matrix
    - Layer: Topological level in dependency hierarchy (0 = foundation)

PERFORMANCE:
    Similar to buildCheckIncludeGraph.py (3-10 seconds). Uses NetworkX for efficient
    graph analysis. Results can be cached.

REQUIREMENTS:
    - Python 3.7+
    - networkx: pip install networkx
    - colorama: pip install colorama (optional, for colored output)
    - clang-scan-deps (clang-19, clang-18, or clang-XX)
    - compile_commands.json (auto-generated from Ninja build)

COMPLEMENTARY TOOLS:
    - buildCheckSummary.py: What changed and will rebuild
    - buildCheckImpact.py: Quick impact check
    - buildCheckIncludeGraph.py: Gateway header analysis
    - buildCheckDependencyHell.py: Multi-metric dependency analysis
    - buildCheckIncludeChains.py: Cooccurrence patterns

EXAMPLES:
    # Basic DSM of all project headers
    ./buildCheckDSM.py ../build/release/
    
    # Show only top 50 most coupled headers
    ./buildCheckDSM.py ../build/release/ --top 50
    
    # Focus on cycle analysis only
    ./buildCheckDSM.py ../build/release/ --cycles-only
    
    # Show hierarchical layers
    ./buildCheckDSM.py ../build/release/ --show-layers
    
    # Export full matrix to CSV
    ./buildCheckDSM.py ../build/release/ --export matrix.csv
    
    # Export dependency graph for visualization (with library metadata)
    ./buildCheckDSM.py ../build/release/ --export-graph graph.graphml
    ./buildCheckDSM.py ../build/release/ --export-graph graph.json
    ./buildCheckDSM.py ../build/release/ --export-graph graph.gexf
    
    # Export with enhanced library grouping information
    ./buildCheckDSM.py ../build/release/ --show-library-boundaries --export-graph graph.graphml
    
    # Filter to specific directory/module
    ./buildCheckDSM.py ../build/release/ --filter "FslBase/*"
    
    # Cluster by directory structure
    ./buildCheckDSM.py ../build/release/ --cluster-by-directory

Note: This tool provides the architectural "big picture" view that complements the
      detailed analysis provided by other buildCheck tools.
      
      Graph exports can be visualized with:
      - GraphML (.graphml): Gephi, yEd, Cytoscape
      - JSON (.json): D3.js, custom visualization tools
      - GEXF (.gexf): Gephi
      - DOT (.dot): Graphviz (requires pydot: pip install pydot)
"""
import subprocess
import os
import sys
import argparse
import json
import logging
import csv
import fnmatch
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, Set, List, Tuple, DefaultDict, Any, Optional

try:
    import networkx as nx
except ImportError:
    print("Error: networkx is required. Install with: pip install networkx", file=sys.stderr)
    sys.exit(1)

try:
    from colorama import Fore, Style, init
    init(autoreset=False)
except ImportError:
    class Fore:
        RED = YELLOW = GREEN = BLUE = MAGENTA = CYAN = WHITE = LIGHTBLACK_EX = RESET = ''
    class Style:
        RESET_ALL = BRIGHT = DIM = ''

# Constants
HIGH_COUPLING_THRESHOLD: int = 20  # Headers with coupling above this are highlighted
MODERATE_COUPLING_THRESHOLD: int = 10  # Moderate coupling threshold
DEFAULT_TOP_N: int = 30  # Default number of headers to show in matrix
CYCLE_HIGHLIGHT: str = '●'  # Symbol for headers in cycles
DEPENDENCY_MARKER: str = 'X'  # Symbol for dependencies in matrix
EMPTY_CELL: str = '·'  # Symbol for no dependency

# Import helper functions from other buildCheck tools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from buildCheckDependencyHell import build_include_graph
except ImportError as e:
    print(f"Error: Could not import from buildCheckDependencyHell: {e}", file=sys.stderr)
    print("Make sure buildCheckDependencyHell.py is in the same directory.", file=sys.stderr)
    sys.exit(1)


def calculate_dsm_metrics(header: str, 
                          header_to_headers: DefaultDict[str, Set[str]], 
                          reverse_deps: DefaultDict[str, Set[str]]) -> Dict[str, Any]:
    """Calculate DSM metrics for a single header.
    
    Args:
        header: Path to the header file
        header_to_headers: Mapping of headers to headers they depend on
        reverse_deps: Mapping of headers to headers that depend on them
        
    Returns:
        Dictionary with metrics: fan_out, fan_in, coupling, stability
    """
    fan_out: int = len(header_to_headers.get(header, set()))
    fan_in: int = len(reverse_deps.get(header, set()))
    coupling: int = fan_out + fan_in
    
    # Stability: 0 = very stable (many dependents, few dependencies)
    #            1 = very unstable (few dependents, many dependencies)
    if coupling > 0:
        stability: float = fan_out / coupling
    else:
        stability = 0.5  # Neutral if isolated
    
    return {
        'fan_out': fan_out,
        'fan_in': fan_in,
        'coupling': coupling,
        'stability': stability
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
        if part in ['source', 'src', 'include'] and i > 0:
            lib_name = parts[i-1]
            return f"lib{lib_name}.a"
    
    # Fallback: use directory containing the file
    if len(parts) >= 2:
        lib_name = parts[-2]
        return f"lib{lib_name}.a"
    
    return "libUnknown.a"


def map_headers_to_libraries(all_headers: Set[str], 
                              source_to_deps: Dict[str, List[str]]) -> Dict[str, str]:
    """Map each header to its containing library based on the header's path.
    
    Headers belong to the library they're physically part of, determined by
    their directory structure (e.g., FslBase/include -> libFslBase.a).
    
    Args:
        all_headers: Set of all header paths
        source_to_deps: Dict mapping source files to their header dependencies (unused but kept for API compatibility)
        
    Returns:
        Dict mapping header path to library name
    """
    header_to_lib: Dict[str, str] = {}
    
    # Each header belongs to the library indicated by its path structure
    for header in all_headers:
        header_to_lib[header] = infer_library_from_source(header)
    
    return header_to_lib


def analyze_cross_library_dependencies(header_to_headers: DefaultDict[str, Set[str]],
                                       header_to_lib: Dict[str, str]) -> Dict[str, Any]:
    """Analyze dependencies that cross library boundaries.
    
    Returns statistics about cross-library coupling.
    """
    stats = {
        'total_deps': 0,
        'intra_library_deps': 0,
        'cross_library_deps': 0,
        'library_violations': defaultdict(lambda: defaultdict(int)),  # from_lib -> to_lib -> count
        'worst_offenders': []  # Headers with most cross-library deps
    }
    
    header_cross_lib_counts: Dict[str, int] = defaultdict(int)
    
    for header, deps in header_to_headers.items():
        header_lib = header_to_lib.get(header, 'unknown')
        
        for dep in deps:
            stats['total_deps'] += 1
            dep_lib = header_to_lib.get(dep, 'unknown')
            
            if header_lib == dep_lib:
                stats['intra_library_deps'] += 1
            else:
                stats['cross_library_deps'] += 1
                stats['library_violations'][header_lib][dep_lib] += 1
                header_cross_lib_counts[header] += 1
    
    # Find worst offenders (headers with most cross-library deps)
    sorted_offenders = sorted(header_cross_lib_counts.items(), 
                             key=lambda x: x[1], reverse=True)
    stats['worst_offenders'] = sorted_offenders[:10]
    
    return stats


def build_reverse_dependencies(header_to_headers: DefaultDict[str, Set[str]], 
                               all_headers: Set[str]) -> DefaultDict[str, Set[str]]:
    """Build reverse dependency mapping (who depends on whom).
    
    Args:
        header_to_headers: Forward dependencies (header -> headers it includes)
        all_headers: Set of all headers
        
    Returns:
        Reverse dependencies (header -> headers that include it)
    """
    reverse_deps: DefaultDict[str, Set[str]] = defaultdict(set)
    
    for header in all_headers:
        for dep in header_to_headers.get(header, set()):
            reverse_deps[dep].add(header)
    
    return reverse_deps


def analyze_cycles(header_to_headers: DefaultDict[str, Set[str]], 
                   all_headers: Set[str]) -> Tuple[List[Set[str]], Set[str], List[Tuple[str, str]], nx.DiGraph]:
    """Detect circular dependencies using strongly connected components.
    
    Args:
        header_to_headers: Forward dependencies (header -> headers it includes)
        all_headers: Set of all headers
        
    Returns:
        Tuple of (list of cycles, set of headers in cycles, feedback edges to break cycles, directed graph)
    """
    # Build directed graph from include relationships
    directed_graph = nx.DiGraph()
    directed_graph.add_nodes_from(all_headers)
    
    for header, deps in header_to_headers.items():
        for dep in deps:
            if dep in all_headers:
                directed_graph.add_edge(header, dep)
    
    # Find strongly connected components
    sccs: List[Set[str]] = list(nx.strongly_connected_components(directed_graph))
    
    # Filter to only cycles (SCCs with more than one node or self-loops)
    cycles: List[Set[str]] = []
    headers_in_cycles: Set[str] = set()
    
    for scc in sccs:
        if len(scc) > 1:
            cycles.append(scc)
            headers_in_cycles.update(scc)
        elif len(scc) == 1:
            # Check for self-loop
            node = list(scc)[0]
            if directed_graph.has_edge(node, node):
                cycles.append(scc)
                headers_in_cycles.add(node)
    
    # Find minimum feedback arc set (edges to remove to break all cycles)
    # Using a greedy approximation since NetworkX doesn't have minimum_feedback_arc_set
    feedback_edges: List[Tuple[str, str]] = []
    if cycles:
        try:
            # Simple greedy approach: find edges within each SCC
            for scc in cycles:
                if len(scc) > 1:
                    # For multi-node cycles, find all back edges
                    scc_subgraph = directed_graph.subgraph(scc)
                    for u, v in scc_subgraph.edges():
                        feedback_edges.append((u, v))
                else:
                    # For self-loops
                    node = list(scc)[0]
                    if directed_graph.has_edge(node, node):
                        feedback_edges.append((node, node))
        except Exception as e:
            logging.warning(f"Could not compute feedback arc set: {e}")
    
    return cycles, headers_in_cycles, feedback_edges, directed_graph


def compute_layers(header_to_headers: DefaultDict[str, Set[str]], 
                   all_headers: Set[str]) -> Tuple[List[List[str]], Dict[str, int], bool]:
    """Compute dependency layers using topological sorting.
    
    Args:
        header_to_headers: Mapping of headers to their dependencies
        all_headers: Set of all headers
        
    Returns:
        Tuple of (layers list, header->layer mapping, has_cycles flag)
    """
    # Build directed graph for topological sort
    graph = nx.DiGraph()
    graph.add_nodes_from(all_headers)
    
    for header, deps in header_to_headers.items():
        for dep in deps:
            if dep in all_headers:
                graph.add_edge(header, dep)
    
    # Try topological sort
    try:
        # Use topological_generations to get layers
        generations = list(nx.topological_generations(graph))
        
        # Build layer mapping
        header_to_layer: Dict[str, int] = {}
        for layer_num, layer_nodes in enumerate(generations):
            for node in layer_nodes:
                header_to_layer[node] = layer_num
        
        return generations, header_to_layer, False
        
    except (nx.NetworkXError, nx.NetworkXUnfeasible):
        # Graph has cycles, can't create layers
        logging.warning("Dependency graph contains cycles - cannot compute layers")
        return [], {}, True


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


def visualize_dsm(headers: List[str], 
                  header_to_headers: DefaultDict[str, Set[str]], 
                  headers_in_cycles: Set[str],
                  project_root: str,
                  top_n: int = DEFAULT_TOP_N) -> None:
    """Display a compact Dependency Structure Matrix.
    
    Args:
        headers: List of headers to show (sorted by coupling)
        header_to_headers: Mapping of headers to their dependencies
        headers_in_cycles: Set of headers that are in cycles
        project_root: Root directory of the project
        top_n: Number of headers to show
    """
    if not headers:
        print(f"{Fore.YELLOW}No headers to display in matrix{Style.RESET_ALL}")
        return
    
    # Limit to top N
    display_headers = headers[:top_n]
    n = len(display_headers)
    
    # Create short labels for headers (last 2 path components)
    labels: List[str] = []
    for header in display_headers:
        rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
        parts = rel_path.split(os.sep)
        if len(parts) >= 2:
            label = os.sep.join(parts[-2:])
        else:
            label = parts[-1]
        # Truncate if too long
        if len(label) > 30:
            label = "..." + label[-27:]
        labels.append(label)
    
    # Find max label width for alignment
    max_label_width = max(len(label) for label in labels) if labels else 0
    
    print(f"\n{Style.BRIGHT}Dependency Structure Matrix (Top {n} headers):{Style.RESET_ALL}")
    print(f"{Style.DIM}Rows include columns (row depends on column){Style.RESET_ALL}\n")
    
    # Print column headers (rotated 90 degrees would be ideal, but use indices)
    header_line = " " * (max_label_width + 2)
    for i in range(n):
        header_line += f"{i:2d} "
    print(f"{Style.DIM}{header_line}{Style.RESET_ALL}")
    
    # Print matrix rows
    for i, header in enumerate(display_headers):
        # Row label
        label = labels[i]
        in_cycle = header in headers_in_cycles
        cycle_marker = f"{Fore.RED}{CYCLE_HIGHLIGHT}{Style.RESET_ALL}" if in_cycle else " "
        
        row = f"{cycle_marker}{label:<{max_label_width}} {Style.DIM}{i:2d}{Style.RESET_ALL} "
        
        # Row cells
        deps = header_to_headers.get(header, set())
        for j, other_header in enumerate(display_headers):
            if i == j:
                # Diagonal - self
                cell = f"{Style.DIM}─{Style.RESET_ALL}"
            elif other_header in deps:
                # Dependency exists
                # Color by whether it's in a cycle
                if header in headers_in_cycles and other_header in headers_in_cycles:
                    cell = f"{Fore.RED}{DEPENDENCY_MARKER}{Style.RESET_ALL}"
                else:
                    cell = f"{Fore.YELLOW}{DEPENDENCY_MARKER}{Style.RESET_ALL}"
            else:
                # No dependency
                cell = f"{Style.DIM}{EMPTY_CELL}{Style.RESET_ALL}"
            
            row += f" {cell} "
        
        print(row)
    
    # Legend
    print(f"\n{Style.BRIGHT}Legend:{Style.RESET_ALL}")
    print(f"  {DEPENDENCY_MARKER} = dependency exists")
    print(f"  {EMPTY_CELL} = no dependency")
    print(f"  {Fore.RED}{CYCLE_HIGHLIGHT}{Style.RESET_ALL} = header is in a circular dependency")
    print(f"  {Fore.RED}{DEPENDENCY_MARKER}{Style.RESET_ALL} = dependency within cycle")
    print(f"  {Fore.YELLOW}{DEPENDENCY_MARKER}{Style.RESET_ALL} = normal dependency")
    
    if len(headers) > top_n:
        print(f"\n{Style.DIM}Showing top {top_n} of {len(headers)} headers{Style.RESET_ALL}")


def export_to_csv(filename: str,
                  headers: List[str],
                  header_to_headers: DefaultDict[str, Set[str]],
                  metrics: Dict[str, Dict[str, Any]],
                  project_root: str) -> None:
    """Export full DSM to CSV file.
    
    Args:
        filename: Output CSV filename
        headers: List of all headers
        header_to_headers: Mapping of headers to their dependencies
        metrics: Per-header metrics
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
                m = metrics.get(header, {})
                
                row = [
                    rel_header,
                    m.get('fan_out', 0),
                    m.get('fan_in', 0),
                    m.get('coupling', 0),
                    f"{m.get('stability', 0):.3f}"
                ]
                
                # Add dependency cells
                deps = header_to_headers.get(header, set())
                for other_header in headers:
                    row.append(1 if other_header in deps else 0)
                
                writer.writerow(row)
        
        logging.info(f"Exported DSM to {filename}")
        print(f"{Fore.GREEN}Exported full matrix to {filename}{Style.RESET_ALL}")
        
    except IOError as e:
        logging.error(f"Failed to export CSV: {e}")
        print(f"{Fore.RED}Error: Failed to export CSV: {e}{Style.RESET_ALL}")


def export_graph(filename: str,
                directed_graph: nx.DiGraph,
                metrics: Dict[str, Dict[str, Any]],
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
        - module: Alias for library (compatibility)
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
            m = metrics.get(node, {})
            rel_path = os.path.relpath(node, project_root) if node.startswith(project_root) else node
            
            G.nodes[node]['label'] = os.path.basename(node)
            G.nodes[node]['path'] = rel_path
            G.nodes[node]['fan_in'] = m.get('fan_in', 0)
            G.nodes[node]['fan_out'] = m.get('fan_out', 0)
            G.nodes[node]['coupling'] = m.get('coupling', 0)
            G.nodes[node]['stability'] = m.get('stability', 0.0)
            G.nodes[node]['in_cycle'] = node in headers_in_cycles
            
            # Add library/module grouping information
            if header_to_lib:
                library = header_to_lib.get(node, 'unknown')
                G.nodes[node]['library'] = library
                G.nodes[node]['module'] = library  # Alias for compatibility
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
            logging.warning(f"Unsupported graph format: {ext}. Defaulting to GraphML.")
            nx.write_graphml(G, filename + '.graphml')
            filename = filename + '.graphml'
        
        logging.info(f"Exported graph to {filename}")
        print(f"{Fore.GREEN}Exported dependency graph to {filename}{Style.RESET_ALL}")
        
    except ImportError as e:
        logging.error(f"Missing dependency for graph export: {e}")
        print(f"{Fore.RED}Error: Missing dependency for graph export. Install pydot for DOT format.{Style.RESET_ALL}")
    except Exception as e:
        logging.error(f"Failed to export graph: {e}")
        print(f"{Fore.RED}Error: Failed to export graph: {e}{Style.RESET_ALL}")


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


def main() -> None:
    """Main entry point for the DSM analysis tool."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description='Dependency Structure Matrix (DSM) analysis for C++ headers.',
        epilog='''
This tool visualizes header dependencies as a matrix, identifies circular
dependencies, analyzes layered architecture, and highlights high-coupling headers.

The DSM provides an architectural "big picture" view showing:
  • Which headers depend on which (matrix visualization)
  • Circular dependency groups (strongly connected components)
  • Architectural layers (topological ordering)
  • Per-header coupling metrics (fan-in, fan-out, stability)

Use this tool for architectural reviews, refactoring planning, and validating
that module boundaries are clean.

Requires: clang-scan-deps (install: sudo apt install clang-19)
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'build_directory',
        metavar='BUILD_DIR',
        help='Path to the ninja build directory (e.g., build/release)'
    )
    
    parser.add_argument(
        '--top',
        type=int,
        default=DEFAULT_TOP_N,
        help=f'Number of headers to show in matrix (default: {DEFAULT_TOP_N}, use 0 to disable matrix display)'
    )
    
    parser.add_argument(
        '--cycles-only',
        action='store_true',
        help='Show only circular dependency analysis'
    )
    
    parser.add_argument(
        '--show-layers',
        action='store_true',
        help='Show hierarchical layer structure (automatically shown if architecture is clean)'
    )
    
    parser.add_argument(
        '--export',
        type=str,
        metavar='FILE.csv',
        help='Export full matrix to CSV file'
    )
    
    parser.add_argument(
        '--export-graph',
        type=str,
        metavar='FILE',
        help='Export dependency graph with library/module grouping (formats: .graphml, .dot, .gexf, .json). '
             'Includes library attributes for visualization tools (Gephi, yEd, Cytoscape). '
             'Use with --show-library-boundaries for enhanced library metadata.'
    )
    
    parser.add_argument(
        '--filter',
        type=str,
        metavar='PATTERN',
        help='Filter headers by glob pattern (e.g., "FslBase/*")'
    )
    
    parser.add_argument(
        '--cluster-by-directory',
        action='store_true',
        help='Group headers by directory in output'
    )
    
    parser.add_argument(
        '--show-library-boundaries',
        action='store_true',
        help='Show which library each header belongs to and analyze cross-library dependencies'
    )
    
    parser.add_argument(
        '--library-filter',
        type=str,
        metavar='LIBRARY',
        help='Show only headers from specified library (e.g., "libFslBase.a")'
    )
    
    parser.add_argument(
        '--cross-library-only',
        action='store_true',
        help='Show only dependencies that cross library boundaries (identifies boundary violations)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose debug logging'
    )
    
    args: argparse.Namespace = parser.parse_args()
    
    # Set logging level based on verbose flag
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Verbose logging enabled")
    
    # Validate arguments
    if not args.build_directory:
        logging.error("Build directory not specified")
        print(f"{Fore.RED}Error: Build directory is required{Style.RESET_ALL}")
        sys.exit(1)
    
    if args.top < 0:
        logging.error(f"Invalid --top value: {args.top}")
        print(f"{Fore.RED}Error: --top must be non-negative{Style.RESET_ALL}")
        sys.exit(1)
    
    build_dir: str = os.path.abspath(args.build_directory)
    logging.info(f"Build directory: {build_dir}")

    if not os.path.isdir(build_dir):
        logging.error(f"'{build_dir}' is not a directory")
        print(f"Error: '{build_dir}' is not a directory.")
        sys.exit(1)
    
    build_ninja: str = os.path.join(build_dir, 'build.ninja')
    if not os.path.exists(build_ninja):
        logging.error(f"build.ninja not found in '{build_dir}'")
        print(f"Error: 'build.ninja' not found in '{build_dir}'.")
        print(f"Please provide the path to the ninja build directory containing build.ninja")
        sys.exit(1)

    project_root: str = os.path.dirname(os.path.abspath(__file__))
    
    # Build include graph using direct parsing (not clang-scan-deps co-occurrence)
    print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}DEPENDENCY STRUCTURE MATRIX ANALYSIS{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}\n")
    
    try:
        source_to_deps: Dict[str, List[str]]
        header_to_headers: DefaultDict[str, Set[str]]
        all_headers: Set[str]
        elapsed: float
        source_to_deps, header_to_headers, all_headers, elapsed = build_include_graph(build_dir)
    except Exception as e:
        logging.error(f"Failed to build include graph: {e}")
        print(f"{Fore.RED}Error: Failed to build include graph: {e}{Style.RESET_ALL}")
        sys.exit(1)
    
    print(f"{Fore.GREEN}Built directed include graph with {len(all_headers)} headers in {elapsed:.1f}s{Style.RESET_ALL}")
    
    # Map headers to libraries if needed
    header_to_lib: Dict[str, str] = {}
    
    if args.show_library_boundaries or args.library_filter or args.cross_library_only:
        logging.info("Mapping headers to libraries using source file dependencies")
        header_to_lib = map_headers_to_libraries(all_headers, source_to_deps)
        
        num_libs = len(set(header_to_lib.values()))
        print(f"{Fore.CYAN}Mapped {len(header_to_lib)} headers to {num_libs} libraries{Style.RESET_ALL}")
    
    # Apply library filter if specified
    if args.library_filter:
        if not header_to_lib:
            print(f"{Fore.RED}Error: Library mapping failed{Style.RESET_ALL}")
            sys.exit(1)
        
        # Filter to headers from this library
        filtered_headers = set()
        for header in all_headers:
            if header_to_lib.get(header) == args.library_filter:
                filtered_headers.add(header)
        
        if not filtered_headers:
            print(f"{Fore.RED}Error: No headers found for library '{args.library_filter}'{Style.RESET_ALL}")
            available_libs = sorted(set(header_to_lib.values()))[:10]
            print(f"Available libraries: {', '.join(available_libs)}...")
            sys.exit(1)
        
        print(f"{Fore.GREEN}Filtered to {len(filtered_headers)} headers from {args.library_filter}{Style.RESET_ALL}")
        all_headers = filtered_headers
    
    # Show helpful suggestions for large projects
    if len(all_headers) > 500 and not args.filter and not args.library_filter:
        print(f"{Fore.YELLOW}Large project detected ({len(all_headers)} headers). Consider using --filter to focus analysis.{Style.RESET_ALL}")
        print(f"{Style.DIM}Examples: --filter '*FslBase/*' or --filter '*Graphics/*'{Style.RESET_ALL}")
        if header_to_lib:
            example_lib = next(iter(set(header_to_lib.values())))
            print(f"{Style.DIM}Or filter by library: --library-filter '{example_lib}'{Style.RESET_ALL}")
    
    # Apply filter if specified
    if args.filter:
        logging.info(f"Applying filter: {args.filter}")
        all_headers = filter_headers_by_pattern(all_headers, args.filter, project_root)
        print(f"{Fore.GREEN}Filtered to {len(all_headers)} headers matching '{args.filter}'{Style.RESET_ALL}")
    
    if not all_headers:
        print(f"{Fore.YELLOW}No headers found after filtering{Style.RESET_ALL}")
        sys.exit(0)
    
    # Build reverse dependencies
    reverse_deps: DefaultDict[str, Set[str]] = build_reverse_dependencies(header_to_headers, all_headers)
    
    # Calculate metrics for all headers
    print(f"{Fore.CYAN}Calculating dependency metrics...{Style.RESET_ALL}")
    metrics: Dict[str, Dict[str, Any]] = {}
    for header in all_headers:
        metrics[header] = calculate_dsm_metrics(header, header_to_headers, reverse_deps)
    
    # Analyze cycles
    print(f"{Fore.CYAN}Analyzing circular dependencies...{Style.RESET_ALL}")
    cycles: List[Set[str]]
    headers_in_cycles: Set[str]
    feedback_edges: List[Tuple[str, str]]
    directed_graph: nx.DiGraph
    cycles, headers_in_cycles, feedback_edges, directed_graph = analyze_cycles(header_to_headers, all_headers)
    
    # Compute layers if requested
    layers: List[List[str]] = []
    header_to_layer: Dict[str, int] = {}
    has_cycles: bool = False
    
    if args.show_layers or not args.cycles_only:
        print(f"{Fore.CYAN}Computing dependency layers...{Style.RESET_ALL}")
        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)
    
    # Calculate matrix statistics
    total_possible_deps = len(all_headers) * (len(all_headers) - 1)  # Exclude diagonal
    total_actual_deps = sum(len(deps) for deps in header_to_headers.values())
    sparsity = 100.0 * (1 - total_actual_deps / total_possible_deps) if total_possible_deps > 0 else 100.0
    
    # Summary Statistics
    print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}SUMMARY STATISTICS{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    
    print(f"\n{Style.BRIGHT}Matrix Properties:{Style.RESET_ALL}")
    print(f"  Total headers: {len(all_headers)}")
    print(f"  Total dependencies: {total_actual_deps}")
    print(f"  Matrix size: {len(all_headers)} × {len(all_headers)}")
    print(f"  Sparsity: {sparsity:.1f}% (lower is more coupled)")
    avg_deps = total_actual_deps / len(all_headers) if len(all_headers) > 0 else 0
    print(f"  Average dependencies per header: {avg_deps:.1f}")
    
    # Architecture health indicator
    if sparsity > 95:
        health = f"{Fore.GREEN}Healthy - low coupling{Style.RESET_ALL}"
    elif sparsity > 90:
        health = f"{Fore.YELLOW}Moderate coupling{Style.RESET_ALL}"
    else:
        health = f"{Fore.RED}Highly coupled{Style.RESET_ALL}"
    print(f"  Architecture health: {health}")
    
    print(f"\n{Style.BRIGHT}Structural Properties:{Style.RESET_ALL}")
    print(f"  Circular dependency groups: {len(cycles)}")
    print(f"  Headers in cycles: {len(headers_in_cycles)}")
    
    if not has_cycles and layers:
        print(f"  Dependency layers: {len(layers)}")
        print(f"  Maximum dependency depth: {len(layers) - 1}")
    elif has_cycles:
        print(f"  {Fore.YELLOW}Cannot compute layers: graph contains cycles{Style.RESET_ALL}")
    
    # Sort headers by coupling for display
    sorted_headers = sorted(all_headers, key=lambda h: metrics[h]['coupling'], reverse=True)
    
    # Show matrix visualization (unless cycles-only mode or --top 0)
    if not args.cycles_only and args.top > 0:
        visualize_dsm(sorted_headers, header_to_headers, headers_in_cycles, project_root, args.top)
    
    # Circular Dependencies Analysis
    if cycles or not args.cycles_only:
        print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
        print(f"{Style.BRIGHT}CIRCULAR DEPENDENCIES{Style.RESET_ALL}")
        print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
        
        if cycles:
            print(f"\n{Fore.RED}Found {len(cycles)} circular dependency groups:{Style.RESET_ALL}\n")
            
            for i, cycle in enumerate(sorted(cycles, key=len, reverse=True), 1):
                print(f"{Fore.RED}Cycle {i} ({len(cycle)} headers):{Style.RESET_ALL}")
                for header in sorted(cycle):
                    rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                    print(f"  • {rel_path}")
                print()
            
            if feedback_edges:
                print(f"{Style.BRIGHT}Suggested edges to remove to break cycles:{Style.RESET_ALL}")
                print(f"{Style.DIM}(Breaking these {len(feedback_edges)} dependencies would eliminate all cycles){Style.RESET_ALL}\n")
                
                for src, dst in feedback_edges[:10]:  # Show first 10
                    src_rel = os.path.relpath(src, project_root) if src.startswith(project_root) else src
                    dst_rel = os.path.relpath(dst, project_root) if dst.startswith(project_root) else dst
                    print(f"  {Fore.YELLOW}{src_rel}{Style.RESET_ALL} → {dst_rel}")
                
                if len(feedback_edges) > 10:
                    print(f"  {Style.DIM}... and {len(feedback_edges) - 10} more{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.GREEN}✓ No circular dependencies found!{Style.RESET_ALL}")
            print(f"  The codebase has a clean, acyclic dependency structure.")
    
    # Layered Architecture Analysis (auto-show if clean, or if explicitly requested)
    show_layers = args.show_layers or (not cycles and layers and not args.cycles_only and len(layers) <= 20)
    if show_layers and layers:
        print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
        print(f"{Style.BRIGHT}LAYERED ARCHITECTURE{Style.RESET_ALL}")
        print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
        
        print(f"\n{Style.BRIGHT}Dependency layers (from foundation to top):{Style.RESET_ALL}")
        print(f"{Style.DIM}Layer 0 = foundation (no dependencies), higher layers depend on lower{Style.RESET_ALL}\n")
        
        max_layers_to_show = 10 if not args.show_layers else len(layers)
        for layer_num, layer_headers in enumerate(layers[:max_layers_to_show]):
            print(f"{Fore.CYAN}Layer {layer_num} ({len(layer_headers)} headers):{Style.RESET_ALL}")
            
            # Show sample headers from this layer
            sample_size = min(5, len(layer_headers))
            for header in sorted(layer_headers)[:sample_size]:
                rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                print(f"  • {rel_path}")
            
            if len(layer_headers) > sample_size:
                print(f"  {Style.DIM}... and {len(layer_headers) - sample_size} more{Style.RESET_ALL}")
            print()
        
        if len(layers) > max_layers_to_show and not args.show_layers:
            print(f"{Style.DIM}... and {len(layers) - max_layers_to_show} more layers (use --show-layers to see all){Style.RESET_ALL}\n")
        
        # Show tip if layers were auto-displayed
        if not args.show_layers:
            print(f"{Style.DIM}💡 Tip: Layers were automatically shown because of clean architecture.{Style.RESET_ALL}\n")
    
    # High-Coupling Headers
    if not args.cycles_only:
        print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
        print(f"{Style.BRIGHT}HIGH-COUPLING HEADERS{Style.RESET_ALL}")
        print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
        
        print(f"\n{Style.BRIGHT}Top {min(20, len(sorted_headers))} headers by coupling:{Style.RESET_ALL}")
        print(f"{Style.DIM}(Coupling = Fan-in + Fan-out){Style.RESET_ALL}\n")
        
        for header in sorted_headers[:20]:
            rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
            m = metrics[header]
            
            # Color by coupling level
            coupling = m['coupling']
            if coupling >= HIGH_COUPLING_THRESHOLD:
                color = Fore.RED
            elif coupling >= MODERATE_COUPLING_THRESHOLD:
                color = Fore.YELLOW
            else:
                color = Fore.GREEN
            
            in_cycle = header in headers_in_cycles
            cycle_marker = f" {Fore.RED}[IN CYCLE]{Style.RESET_ALL}" if in_cycle else ""
            
            print(f"{color}{rel_path}{Style.RESET_ALL}{cycle_marker}")
            print(f"  Fan-out: {m['fan_out']} | Fan-in: {m['fan_in']} | " +
                  f"Coupling: {coupling} | Stability: {m['stability']:.3f}")
    
    # Library Boundary Analysis
    if args.show_library_boundaries and header_to_lib and not args.cycles_only:
        print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
        print(f"{Style.BRIGHT}LIBRARY BOUNDARY ANALYSIS{Style.RESET_ALL}")
        print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
        
        cross_lib_stats = analyze_cross_library_dependencies(header_to_headers, header_to_lib)
        
        total = cross_lib_stats['total_deps']
        intra = cross_lib_stats['intra_library_deps']
        cross = cross_lib_stats['cross_library_deps']
        
        if total > 0:
            intra_pct = (intra / total) * 100
            cross_pct = (cross / total) * 100
            
            print(f"\n{Style.BRIGHT}Dependency Distribution:{Style.RESET_ALL}")
            print(f"  Total dependencies: {total}")
            print(f"  Intra-library (within same library): {intra} ({intra_pct:.1f}%)")
            print(f"  Cross-library (between libraries): {cross} ({cross_pct:.1f}%)")
            
            if cross_pct > 50:
                print(f"  {Fore.YELLOW}⚠ High cross-library coupling - consider refactoring{Style.RESET_ALL}")
            elif cross_pct > 30:
                print(f"  {Fore.YELLOW}⚠ Moderate cross-library coupling{Style.RESET_ALL}")
            else:
                print(f"  {Fore.GREEN}✓ Good library cohesion{Style.RESET_ALL}")
            
            # Show top library-to-library couplings
            lib_violations = cross_lib_stats['library_violations']
            if lib_violations:
                print(f"\n{Style.BRIGHT}Top Cross-Library Dependencies:{Style.RESET_ALL}")
                print(f"{Style.DIM}(Library A → Library B: count){Style.RESET_ALL}\n")
                
                # Flatten and sort
                all_violations = []
                for from_lib, to_libs in lib_violations.items():
                    for to_lib, count in to_libs.items():
                        all_violations.append((from_lib, to_lib, count))
                
                all_violations.sort(key=lambda x: x[2], reverse=True)
                
                for from_lib, to_lib, count in all_violations[:15]:
                    color = Fore.RED if count > 50 else Fore.YELLOW if count > 20 else Fore.WHITE
                    print(f"  {color}{from_lib} → {to_lib}: {count} dependencies{Style.RESET_ALL}")
            
            # Show headers with most cross-library dependencies
            if cross_lib_stats['worst_offenders']:
                print(f"\n{Style.BRIGHT}Headers with Most Cross-Library Dependencies:{Style.RESET_ALL}")
                print(f"{Style.DIM}(These headers heavily couple different libraries){Style.RESET_ALL}\n")
                
                for header, count in cross_lib_stats['worst_offenders'][:10]:
                    rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
                    lib_name = header_to_lib.get(header, 'unknown')
                    print(f"  {rel_path}")
                    print(f"    Library: {lib_name} | Cross-library deps: {count}")
    
    # Directory clustering
    if args.cluster_by_directory and not args.cycles_only:
        print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
        print(f"{Style.BRIGHT}MODULE ANALYSIS (by directory){Style.RESET_ALL}")
        print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
        
        clusters = cluster_headers_by_directory(list(all_headers), project_root)
        
        # Calculate inter-module vs intra-module dependencies
        for module_name in sorted(clusters.keys()):
            module_headers = set(clusters[module_name])
            
            intra_deps = 0
            inter_deps = 0
            
            for header in module_headers:
                for dep in header_to_headers.get(header, set()):
                    if dep in module_headers:
                        intra_deps += 1
                    else:
                        inter_deps += 1
            
            total = intra_deps + inter_deps
            if total > 0:
                cohesion = 100.0 * intra_deps / total
                print(f"\n{Fore.CYAN}{module_name}:{Style.RESET_ALL}")
                print(f"  Headers: {len(module_headers)}")
                print(f"  Internal dependencies: {intra_deps}")
                print(f"  External dependencies: {inter_deps}")
                print(f"  Cohesion: {cohesion:.1f}% (higher is better)")
    
    # Export to CSV
    if args.export:
        export_to_csv(args.export, sorted_headers, header_to_headers, metrics, project_root)
    
    # Export graph
    if args.export_graph:
        export_graph(args.export_graph, directed_graph, metrics, cycles, project_root, header_to_lib, header_to_headers)
    
    # Final summary
    print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}RECOMMENDATIONS{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}\n")
    
    if cycles:
        print(f"{Fore.YELLOW}Priority: Break circular dependencies{Style.RESET_ALL}")
        print(f"  • {len(cycles)} circular dependency groups found")
        print(f"  • Consider removing {len(feedback_edges)} dependencies to eliminate cycles")
        print()
    
    high_coupling_count = sum(1 for h in all_headers if metrics[h]['coupling'] >= HIGH_COUPLING_THRESHOLD)
    if high_coupling_count > 0:
        print(f"{Fore.YELLOW}Refactoring opportunity: Reduce high coupling{Style.RESET_ALL}")
        print(f"  • {high_coupling_count} headers have coupling ≥ {HIGH_COUPLING_THRESHOLD}")
        print(f"  • Consider splitting, using forward declarations, or reducing dependencies")
        print()
    
    if sparsity < 90:
        print(f"{Fore.YELLOW}Architecture note: Low sparsity indicates high coupling{Style.RESET_ALL}")
        print(f"  • Matrix sparsity: {sparsity:.1f}%")
        print(f"  • Consider modularizing to reduce global coupling")
        print()
    
    if not cycles and layers:
        print(f"{Fore.GREEN}✓ Clean layered architecture detected{Style.RESET_ALL}")
        print(f"  • No circular dependencies")
        print(f"  • {len(layers)} clear dependency layers")
        print(f"  • Maximum depth: {len(layers) - 1}")
        if not show_layers:
            print(f"\n{Style.DIM}Tip: Layers were automatically shown above. Use --show-layers to force display.{Style.RESET_ALL}")
    elif not cycles:
        print(f"{Fore.GREEN}✓ No circular dependencies{Style.RESET_ALL}")
        print(f"  • Clean acyclic dependency structure")
        print(f"  • Good foundation for refactoring")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        print(f"\n{Fore.YELLOW}Interrupted by user{Style.RESET_ALL}")
        sys.exit(130)
    except ValueError as e:
        logging.error(f"Validation error: {e}")
        print(f"\n{Fore.RED}Validation error: {e}{Style.RESET_ALL}")
        sys.exit(1)
    except RuntimeError as e:
        logging.error(f"Runtime error: {e}")
        print(f"\n{Fore.RED}Runtime error: {e}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Run with --verbose for more details{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        logging.critical(f"Unexpected error: {e}", exc_info=True)
        print(f"\n{Fore.RED}Fatal error: {e}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Run with --verbose for more details{Style.RESET_ALL}")
        sys.exit(1)
