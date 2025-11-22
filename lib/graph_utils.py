#!/usr/bin/env python3
"""Graph utilities for dependency analysis using NetworkX."""

import os
import logging
from typing import Dict, Set, List, Tuple, Optional, Any
from dataclasses import dataclass
from collections import defaultdict
from lib.color_utils import Colors, print_warning

import networkx as nx

logger = logging.getLogger(__name__)


@dataclass
class DSMMetrics:
    """Metrics for a single header in the DSM.
    
    Attributes:
        fan_out: Number of headers this header depends on
        fan_in: Number of headers that depend on this header
        coupling: Total coupling (fan_out + fan_in)
        stability: Stability metric (0=stable, 1=unstable)
    """
    fan_out: int
    fan_in: int
    coupling: int
    stability: float


def build_dependency_graph(include_graph: Dict[str, Set[str]], all_headers: Set[str]) -> 'nx.DiGraph[Any]':
    """Build a NetworkX directed graph from an include graph.
    
    Args:
        include_graph: Mapping of headers to their direct includes
        all_headers: Set of all header files
        
    Returns:
        NetworkX DiGraph
    """
    G: nx.DiGraph[Any] = nx.DiGraph()
    
    # Add all headers as nodes (batch operation)
    G.add_nodes_from(all_headers)
    
    # Add edges for direct includes (batch operation for better performance)
    edges = [(header, included) for header, includes in include_graph.items() 
             for included in includes]
    G.add_edges_from(edges)
    
    logger.debug(f"Built graph with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges")
    return G


def compute_reverse_dependencies(G: Any) -> Tuple[Dict[str, Set[str]], Optional[Any]]:
    """Compute reverse dependencies using transitive closure.
    
    Args:
        G: NetworkX directed graph
        
    Returns:
        Tuple of (reverse_deps dict, transitive_closure graph)
    """
    reverse_deps: Dict[str, Set[str]] = defaultdict(set)
    tc: Optional[Any] = None
    
    print(f"{Colors.BLUE}Computing reverse dependencies (rebuild blast radius)...{Colors.RESET}")
    print(f"{Colors.DIM}  Computing transitive closure...{Colors.RESET}")
    
    try:
        is_dag = nx.is_directed_acyclic_graph(G)
        if is_dag:
            tc = nx.transitive_closure_dag(G)
        else:
            logger.warning("Circular includes detected - using general transitive closure")
            tc = nx.transitive_closure(G)
        
        if tc is not None:
            for node in G.nodes():
                reverse_deps[node] = set(tc.predecessors(node))  # type: ignore[attr-defined]
        print(f"{Colors.DIM}  Computed reverse dependencies for {len(reverse_deps)} headers{Colors.RESET}")
    except (MemoryError, nx.NetworkXError) as e:
        logger.warning(f"Transitive closure failed ({type(e).__name__}), using slower per-node computation")
        tc = None
        for node in G.nodes():
            reverse_deps[node] = nx.ancestors(G, node)
    
    return dict(reverse_deps), tc


def compute_transitive_metrics(
    G: Any,
    tc: Optional[Any],
    project_headers: List[str],
    reverse_deps: Dict[str, Set[str]]
) -> Tuple[Set[str], Dict[str, int], Dict[str, int]]:
    """Compute transitive dependencies and identify base types.
    
    Args:
        G: NetworkX directed graph
        tc: Transitive closure graph (if available)
        project_headers: List of project header files
        reverse_deps: Reverse dependency mapping
        
    Returns:
        Tuple of (base_types, header_transitive_deps, header_reverse_impact)
    """
    base_types = set()
    header_transitive_deps: Dict[str, int] = {}
    header_reverse_impact: Dict[str, int] = {}
    
    print(f"{Colors.DIM}  Computing transitive dependencies...{Colors.RESET}")
    
    if tc is not None:
        # Use precomputed transitive closure
        for header in project_headers:
            if header in G:
                out_degree = G.out_degree(header)
                if out_degree == 0:
                    base_types.add(header)
                
                descendants = set(tc.successors(header)) if header in tc else set()
                header_transitive_deps[header] = len(descendants)
                header_reverse_impact[header] = len(reverse_deps.get(header, set()))
    else:
        # Fallback to individual queries
        for header in project_headers:
            if header in G:
                out_degree = G.out_degree(header)
                if out_degree == 0:
                    base_types.add(header)
                descendants = nx.descendants(G, header)
                header_transitive_deps[header] = len(descendants)
                header_reverse_impact[header] = len(reverse_deps.get(header, set()))
    
    return base_types, header_transitive_deps, header_reverse_impact


def compute_chain_lengths(
    G: Any,
    project_headers: List[str],
    base_types: Set[str]
) -> Dict[str, int]:
    """Compute maximum chain lengths for headers.
    
    Args:
        G: NetworkX directed graph
        project_headers: List of project header files
        base_types: Set of base type headers
        
    Returns:
        Dictionary mapping headers to maximum chain length
    """
    header_max_chain_length: Dict[str, int] = {}
    
    print(f"{Colors.DIM}  Computing maximum chain lengths...{Colors.RESET}")
    
    if not base_types:
        for header in project_headers:
            header_max_chain_length[header] = 0
        return header_max_chain_length
    
    try:
        if nx.is_directed_acyclic_graph(G):
            for header in project_headers:
                if header not in G:
                    header_max_chain_length[header] = 0
                    continue
                
                max_chain = 0
                descendants = set(nx.descendants(G, header))
                reachable_bases = descendants & base_types
                
                if reachable_bases:
                    try:
                        paths = nx.single_source_shortest_path_length(G, header)
                        max_chain = max(paths.get(base, 0) for base in reachable_bases)
                    except nx.NetworkXError:
                        max_chain = 0
                
                header_max_chain_length[header] = max_chain
        else:
            for header in project_headers:
                header_max_chain_length[header] = 0
    except (MemoryError, nx.NetworkXError) as e:
        logger.warning(f"Chain length computation failed ({type(e).__name__}): setting to 0")
        for header in project_headers:
            header_max_chain_length[header] = 0
    
    return header_max_chain_length


def find_strongly_connected_components(graph: 'nx.DiGraph[Any]') -> List[Set[str]]:
    """Find strongly connected components (cycles) in a directed graph.
    
    Args:
        graph: NetworkX DiGraph
        
    Returns:
        List of sets, each containing nodes in a cycle
    """
    sccs = list(nx.strongly_connected_components(graph))
    
    # Filter out single-node SCCs without self-loops
    cycles = []
    for scc in sccs:
        if len(scc) > 1:
            cycles.append(scc)
        elif len(scc) == 1:
            node = next(iter(scc))
            if graph.has_edge(node, node):
                cycles.append(scc)
    
    return cycles


def build_reverse_dependencies(header_to_headers: Dict[str, Set[str]], 
                               all_headers: Set[str]) -> Dict[str, Set[str]]:
    """Build reverse dependency mapping (who depends on whom).
    
    Uses NetworkX graph reversal for efficient computation.
    
    Args:
        header_to_headers: Forward dependencies (header -> headers it includes)
        all_headers: Set of all headers
        
    Returns:
        Reverse dependencies (header -> headers that include it)
    """
    # Build graph and reverse it using NetworkX (more efficient)
    G: nx.DiGraph[Any] = nx.DiGraph()
    G.add_nodes_from(all_headers)
    
    edges = [(header, dep) for header, deps in header_to_headers.items() 
             for dep in deps]
    G.add_edges_from(edges)
    
    # Reverse the graph
    G_reversed = G.reverse(copy=False)
    
    # Extract reverse dependencies
    reverse_deps: Dict[str, Set[str]] = {}
    for node in G_reversed.nodes():
        successors = set(G_reversed.successors(node))
        if successors:
            reverse_deps[node] = successors
    
    return reverse_deps


def compute_layers(header_to_headers: Dict[str, Set[str]], 
                   all_headers: Set[str]) -> Tuple[List[List[str]], Dict[str, int], bool]:
    """Compute dependency layers using topological sorting.
    
    Uses NetworkX's topological_generations() which assigns:
    - Layer 0: Sources with NO incoming dependencies from other headers in the set
    - Higher layers: Headers that are depended upon by others (foundation/bottom)
    
    Args:
        header_to_headers: Mapping of headers to their dependencies
        all_headers: Set of all headers
        
    Returns:
        Tuple of (layers list, header->layer mapping, has_cycles flag)
    """
    graph: nx.DiGraph[Any] = nx.DiGraph()
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
        logger.warning("Dependency graph contains cycles - cannot compute layers")
        return [], {}, True


def analyze_cycles(header_to_headers: Dict[str, Set[str]], 
                   all_headers: Set[str]) -> Tuple[List[Set[str]], Set[str], List[Tuple[str, str]], 'nx.DiGraph[Any]']:
    """Detect circular dependencies using strongly connected components.
    
    Args:
        header_to_headers: Forward dependencies (header -> headers it includes)
        all_headers: Set of all headers
        
    Returns:
        Tuple of (cycles, headers_in_cycles, feedback_edges, directed_graph)
    """
    # Build directed graph from include relationships
    directed_graph: nx.DiGraph[Any] = nx.DiGraph()
    directed_graph.add_nodes_from(all_headers)
    
    for header, deps in header_to_headers.items():
        for dep in deps:
            if dep in all_headers:
                directed_graph.add_edge(header, dep)
    
    # Use library function to find cycles
    cycles = find_strongly_connected_components(directed_graph)
    
    # Build set of headers in cycles
    headers_in_cycles: Set[str] = set()
    for cycle in cycles:
        headers_in_cycles.update(cycle)
    
    # Use improved feedback arc set computation
    feedback_edges: List[Tuple[str, str]] = []
    if cycles:
        feedback_edges = compute_minimum_feedback_arc_set(directed_graph)
    
    return cycles, headers_in_cycles, feedback_edges, directed_graph


def compute_topological_layers(graph: 'nx.DiGraph[Any]') -> Dict[str, int]:
    """Compute topological layers for nodes in a DAG.
    
    Uses the same convention as compute_layers():
    - Layer 0: Sources with NO incoming edges (top of dependency tree)
    - Higher layers: Nodes that are depended upon by others (foundation/bottom)
    
    Args:
        graph: NetworkX DiGraph (should be acyclic)
        
    Returns:
        Dictionary mapping node to its layer (0 = sources, higher = more depended upon)
    """
    # Remove cycles first by finding and breaking them
    G = graph.copy()
    try:
        cycles = list(nx.simple_cycles(G))
        if cycles:
            logger.warning(f"Found {len(cycles)} cycles, breaking them for layer analysis")
            for cycle in cycles:
                # Break cycle by removing one edge
                G.remove_edge(cycle[0], cycle[1])
    except nx.NetworkXNoCycle:
        pass
    
    layers = {}
    
    try:
        # Use topological_generations to get layers (same as compute_layers)
        generations = list(nx.topological_generations(G))
        for layer_num, layer_nodes in enumerate(generations):
            for node in layer_nodes:
                layers[node] = layer_num
    except Exception as e:
        logger.error(f"Error computing topological layers: {e}")
    
    return layers


def compute_transitive_closure(graph: 'nx.DiGraph[Any]', node: str) -> Set[str]:
    """Compute transitive closure (all reachable nodes) from a given node.
    
    Args:
        graph: NetworkX DiGraph
        node: Starting node
        
    Returns:
        Set of all nodes reachable from the starting node
    """
    try:
        return nx.descendants(graph, node)
    except nx.NetworkXError:
        return set()


def compute_reverse_transitive_closure(graph: 'nx.DiGraph[Any]', node: str) -> Set[str]:
    """Compute reverse transitive closure (all nodes that can reach this node).
    
    Args:
        graph: NetworkX DiGraph
        node: Target node
        
    Returns:
        Set of all nodes that can reach the target node
    """
    try:
        return nx.ancestors(graph, node)
    except nx.NetworkXError:
        return set()


def build_transitive_dependents_map(lib_to_libs: Dict[str, Set[str]], 
                                     exe_to_libs: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    """Build reverse dependency map showing all transitive dependents.
    
    Uses NetworkX for efficient transitive closure computation.
    
    Args:
        lib_to_libs: Library → Libraries it depends on
        exe_to_libs: Executable → Libraries it depends on
        
    Returns:
        Dictionary mapping library → set of all libraries/executables that depend on it
    """
    # Build graph using NetworkX
    G: nx.DiGraph[Any] = nx.DiGraph()
    
    # Add all libraries and executables as nodes
    G.add_nodes_from(lib_to_libs.keys())
    G.add_nodes_from(exe_to_libs.keys())
    
    # Add edges: lib/exe -> its dependencies
    for lib, deps in lib_to_libs.items():
        for dep in deps:
            G.add_edge(lib, dep)
    
    for exe, deps in exe_to_libs.items():
        for dep in deps:
            G.add_edge(exe, dep)
    
    # Compute transitive dependents using NetworkX ancestors (reverse of descendants)
    result: Dict[str, Set[str]] = {}
    for lib in lib_to_libs.keys():
        # ancestors() returns all nodes that can reach this node
        result[lib] = nx.ancestors(G, lib)
    
    return result


def compute_fan_in_fan_out(graph: 'nx.DiGraph[Any]') -> Dict[str, Tuple[int, int]]:
    """Compute fan-in and fan-out for each node in a graph.
    
    Uses NetworkX's degree views for efficient batch computation.
    
    Args:
        graph: NetworkX DiGraph
        
    Returns:
        Dictionary mapping node → (fan_in, fan_out)
    """
    # Use degree views for efficient batch access
    in_degrees = dict(graph.in_degree())
    out_degrees = dict(graph.out_degree())
    
    # Combine into single dictionary
    metrics = {node: (in_degrees[node], out_degrees[node]) for node in graph.nodes()}
    
    return metrics


def find_hub_nodes(graph: 'nx.DiGraph[Any]', threshold: int = 10) -> List[Tuple[str, int, int]]:
    """Find hub nodes with high connectivity.
    
    Uses NetworkX's degree views for efficient batch computation.
    
    Args:
        graph: NetworkX DiGraph
        threshold: Minimum total degree to be considered a hub
        
    Returns:
        List of (node, fan_in, fan_out) tuples for hub nodes
    """
    # Use degree views for efficient batch access
    in_degrees = dict(graph.in_degree())
    out_degrees = dict(graph.out_degree())
    
    hubs = [(node, in_degrees[node], out_degrees[node]) 
            for node in graph.nodes()
            if in_degrees[node] + out_degrees[node] >= threshold]
    
    return sorted(hubs, key=lambda x: x[1] + x[2], reverse=True)


def identify_critical_headers(graph: 'nx.DiGraph[Any]', top_n: int = 20) -> List[Tuple[str, float]]:
    """Identify critical headers using PageRank analysis.
    
    Critical headers are those that are important in the dependency structure.
    High PageRank indicates a header that is depended upon by many important headers.
    
    Args:
        graph: NetworkX DiGraph of dependencies
        top_n: Number of top critical headers to return
        
    Returns:
        List of (header, pagerank_score) tuples, sorted by importance
    """
    try:
        pagerank_scores = compute_pagerank_centrality(graph)
        if not pagerank_scores:
            return []
        
        # Sort by PageRank score descending
        sorted_headers = sorted(pagerank_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_headers[:top_n]
    except Exception as e:
        logger.error(f"Error identifying critical headers: {e}")
        return []


def compute_betweenness_centrality(graph: 'nx.DiGraph[Any]', k: Optional[int] = None) -> Dict[str, float]:
    """Compute betweenness centrality for nodes (how often they appear on shortest paths).
    
    Args:
        graph: NetworkX DiGraph
        k: Number of nodes to sample (None = all nodes, faster with sampling)
        
    Returns:
        Dictionary mapping node → centrality score
    """
    try:
        return nx.betweenness_centrality(graph, k=k)
    except Exception as e:
        logger.error(f"Error computing betweenness centrality: {e}")
        return {}


def compute_pagerank_centrality(graph: 'nx.DiGraph[Any]', alpha: float = 0.85, 
                                max_iter: int = 100) -> Dict[str, float]:
    """Compute PageRank centrality to identify critical headers in dependency graph.
    
    PageRank identifies headers that are important in the dependency structure.
    High PageRank indicates a header that is depended upon by many important headers.
    
    Note: NetworkX will use scipy if available for better performance, but works without it.
    
    Args:
        graph: NetworkX DiGraph
        alpha: Damping parameter (default 0.85)
        max_iter: Maximum iterations (default 100)
        
    Returns:
        Dictionary mapping node → PageRank score
    """
    try:
        # NetworkX PageRank (uses scipy if available for better performance)
        result: Dict[str, float] = nx.pagerank(graph, alpha=alpha, max_iter=max_iter, tol=1.0e-6)
        return result
    except Exception as e:
        logger.error(f"Error computing PageRank centrality: {e}")
        return {}


def find_longest_path_through_node(graph: 'nx.DiGraph[Any]', node: str) -> int:
    """Find the length of the longest path through a node.
    
    Args:
        graph: NetworkX DiGraph
        node: Node to analyze
        
    Returns:
        Maximum path length through the node
    """
    try:
        # Find longest path from any predecessor to any successor
        max_length = 0
        predecessors = list(graph.predecessors(node))
        successors = list(graph.successors(node))
        
        if not predecessors or not successors:
            return 0
        
        for pred in predecessors:
            for succ in successors:
                try:
                    # Find all simple paths (avoid cycles)
                    paths = list(nx.all_simple_paths(graph, pred, succ, cutoff=100))
                    for path in paths:
                        if node in path:
                            max_length = max(max_length, len(path) - 1)
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue
        
        return max_length
    except Exception as e:
        logger.debug(f"Error finding longest path through {node}: {e}")
        return 0


def export_graph_to_graphml(graph: 'nx.DiGraph[Any]', output_path: str, 
                            node_attributes: Optional[Dict[str, Dict[str, Any]]] = None) -> bool:
    """Export graph to GraphML format for visualization.
    
    Args:
        graph: NetworkX DiGraph
        output_path: Path to output file
        node_attributes: Optional dictionary of node → {attribute: value} mappings
        
    Returns:
        True if successful
    """
    try:
        # Add node attributes if provided
        if node_attributes:
            for node, attrs in node_attributes.items():
                if node in graph:
                    for key, value in attrs.items():
                        graph.nodes[node][key] = value
        
        nx.write_graphml(graph, output_path)
        logger.info(f"Exported graph to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to export graph: {e}")
        return False


def calculate_dsm_metrics(header: str, 
                          header_to_headers: Dict[str, Set[str]], 
                          reverse_deps: Dict[str, Set[str]]) -> DSMMetrics:
    """Calculate DSM metrics for a single header.
    
    Args:
        header: Path to the header file
        header_to_headers: Mapping of headers to headers they depend on
        reverse_deps: Mapping of headers to headers that depend on them
        
    Returns:
        DSMMetrics with fan_out, fan_in, coupling, and stability
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
    
    return DSMMetrics(
        fan_out=fan_out,
        fan_in=fan_in,
        coupling=coupling,
        stability=stability
    )


def visualize_dsm(headers: List[str], 
                  header_to_headers: Dict[str, Set[str]], 
                  headers_in_cycles: Set[str],
                  project_root: str,
                  top_n: int,
                  cycle_highlight: str = '●',
                  dependency_marker: str = 'X',
                  empty_cell: str = '·') -> None:
    """Display a compact Dependency Structure Matrix.
    
    Args:
        headers: List of headers to show (sorted by coupling)
        header_to_headers: Mapping of headers to their dependencies
        headers_in_cycles: Set of headers that are in cycles
        project_root: Root directory of the project
        top_n: Number of headers to show
        cycle_highlight: Symbol for headers in cycles
        dependency_marker: Symbol for dependencies
        empty_cell: Symbol for no dependency
    """
    if not headers:
        print_warning("No headers to display in matrix", prefix=False)
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
    
    print(f"\n{Colors.BRIGHT}Dependency Structure Matrix (Top {n} headers):{Colors.RESET}")
    print(f"{Colors.DIM}Rows include columns (row depends on column){Colors.RESET}\n")
    
    # Print column headers (rotated 90 degrees would be ideal, but use indices)
    header_line = " " * (max_label_width + 2)
    for i in range(n):
        header_line += f"{i:2d} "
    print(f"{Colors.DIM}{header_line}{Colors.RESET}")
    
    # Print matrix rows
    for i, header in enumerate(display_headers):
        # Row label
        label = labels[i]
        in_cycle = header in headers_in_cycles
        cycle_marker = f"{Colors.RED}{cycle_highlight}{Colors.RESET}" if in_cycle else " "
        
        row = f"{cycle_marker}{label:<{max_label_width}} {Colors.DIM}{i:2d}{Colors.RESET} "
        
        # Row cells
        deps = header_to_headers.get(header, set())
        for j, other_header in enumerate(display_headers):
            if i == j:
                # Diagonal - self
                cell = f"{Colors.DIM}─{Colors.RESET}"
            elif other_header in deps:
                # Dependency exists
                # Color by whether it's in a cycle
                if header in headers_in_cycles and other_header in headers_in_cycles:
                    cell = f"{Colors.RED}{dependency_marker}{Colors.RESET}"
                else:
                    cell = f"{Colors.YELLOW}{dependency_marker}{Colors.RESET}"
            else:
                # No dependency
                cell = f"{Colors.DIM}{empty_cell}{Colors.RESET}"
            
            row += f" {cell} "
        
        print(row)
    
    # Legend
    print(f"\n{Colors.BRIGHT}Legend:{Colors.RESET}")
    print(f"  {dependency_marker} = dependency exists")
    print(f"  {empty_cell} = no dependency")
    print(f"  {Colors.RED}{cycle_highlight}{Colors.RESET} = header is in a circular dependency")
    print(f"  {Colors.RED}{dependency_marker}{Colors.RESET} = dependency within cycle")
    print(f"  {Colors.YELLOW}{dependency_marker}{Colors.RESET} = normal dependency")
    
    if len(headers) > top_n:
        print(f"\n{Colors.DIM}Showing top {top_n} of {len(headers)} headers{Colors.RESET}")


def compute_minimum_feedback_arc_set(graph: 'nx.DiGraph[Any]') -> List[Tuple[str, str]]:
    """Compute approximate minimum feedback arc set to break all cycles.
    
    Uses NetworkX's built-in feedback arc set algorithm if available (NetworkX >= 2.6),
    otherwise falls back to a greedy approximation algorithm.
    
    Args:
        graph: NetworkX DiGraph
        
    Returns:
        List of edges (u, v) to remove to break cycles
    """
    try:
        # Try using NetworkX's built-in minimum_feedback_arc_set (available in NetworkX >= 2.6)
        try:
            from networkx.algorithms.cycles import minimum_feedback_arc_set  # type: ignore[attr-defined]
            feedback_edges_set = minimum_feedback_arc_set(graph)
            return list(feedback_edges_set)
        except (ImportError, AttributeError):
            # Fall back to greedy approach for older NetworkX versions
            logger.debug("Using greedy feedback arc set algorithm (NetworkX < 2.6)")
            pass
        
        # Greedy approach: repeatedly find and break cycles
        feedback_edges: List[Tuple[str, str]] = []
        G = graph.copy()
        
        # Pre-compute degrees for efficiency
        out_degrees = dict(G.out_degree())
        
        while True:
            try:
                # Try to find a cycle
                cycle = nx.find_cycle(G, orientation='original')
                if cycle:
                    # Remove the edge with highest out-degree node (greedy heuristic)
                    edge_to_remove = max(cycle, key=lambda e: out_degrees.get(e[0], 0))
                    feedback_edges.append((edge_to_remove[0], edge_to_remove[1]))
                    G.remove_edge(edge_to_remove[0], edge_to_remove[1])
                    # Update out-degree for removed edge source
                    if edge_to_remove[0] in out_degrees:
                        out_degrees[edge_to_remove[0]] -= 1
                else:
                    break
            except nx.NetworkXNoCycle:
                break
        
        return feedback_edges
    except Exception as e:
        logger.warning(f"Error computing feedback arc set: {e}")
        return []


def export_graph_to_dot(graph: 'nx.DiGraph[Any]', output_path: str) -> bool:
    """Export graph to DOT format for Graphviz.
    
    Args:
        graph: NetworkX DiGraph
        output_path: Path to output file
        
    Returns:
        True if successful
    """
    try:
        from networkx.drawing.nx_pydot import write_dot
        write_dot(graph, output_path)
        logger.info(f"Exported graph to {output_path}")
        return True
    except ImportError:
        logger.error("pydot required for DOT export: pip install pydot")
        return False
    except Exception as e:
        logger.error(f"Failed to export graph: {e}")
        return False
