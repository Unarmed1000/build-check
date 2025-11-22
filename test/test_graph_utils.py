#!/usr/bin/env python3
"""Unit tests for graph_utils module."""

import pytest
import networkx as nx
from collections import defaultdict
from lib.graph_utils import (
    compute_pagerank_centrality,
    identify_critical_headers,
    compute_minimum_feedback_arc_set,
    build_dependency_graph,
    find_strongly_connected_components,
    analyze_cycles,
    compute_layers,
    build_transitive_dependents_map,
    compute_fan_in_fan_out,
    find_hub_nodes,
    compute_betweenness_centrality,
    DSMMetrics,
)


class TestNetworkXIntegration:
    """Test NetworkX integration (no fallbacks)."""
    
    def test_networkx_is_required(self) -> None:
        """Verify NetworkX is imported and available."""
        # This should not raise ImportError
        import networkx as nx
        assert nx is not None
    
    def test_build_dependency_graph(self) -> None:
        """Test building a NetworkX graph from include relationships."""
        include_graph = {
            'A': {'B', 'D'},
            'B': {'C'},
            'C': {'D'},
            'D': {'B'}
        }
        all_headers = {'A', 'B', 'C', 'D'}
        
        graph = build_dependency_graph(include_graph, all_headers)
        
        assert isinstance(graph, nx.DiGraph)
        assert graph.number_of_nodes() == 4
        assert graph.number_of_edges() == 5
        assert graph.has_edge('A', 'B')
        assert graph.has_edge('D', 'B')


class TestPageRankAnalysis:
    """Test PageRank centrality computation."""
    
    def test_pagerank_simple_graph(self) -> None:
        """Test PageRank on a simple directed graph."""
        G: nx.DiGraph[str] = nx.DiGraph()
        G.add_edges_from([('A', 'B'), ('B', 'C'), ('C', 'D'), ('D', 'B'), ('A', 'D')])
        
        pr = compute_pagerank_centrality(G)
        
        assert len(pr) == 4
        assert all(0 <= score <= 1 for score in pr.values())
        # Sum should be approximately 1.0
        assert abs(sum(pr.values()) - 1.0) < 0.01
    
    def test_pagerank_empty_graph(self) -> None:
        """Test PageRank on empty graph."""
        G: nx.DiGraph[str] = nx.DiGraph()
        
        pr = compute_pagerank_centrality(G)
        
        assert pr == {}
    
    def test_pagerank_single_node(self) -> None:
        """Test PageRank on single node graph."""
        G: nx.DiGraph[str] = nx.DiGraph()
        G.add_node('A')
        
        pr = compute_pagerank_centrality(G)
        
        assert len(pr) == 1
        assert abs(pr['A'] - 1.0) < 0.01
    
    def test_identify_critical_headers(self) -> None:
        """Test identifying critical headers."""
        G: nx.DiGraph[str] = nx.DiGraph()
        G.add_edges_from([('A', 'B'), ('B', 'C'), ('C', 'D'), ('D', 'B'), ('A', 'D')])
        
        critical = identify_critical_headers(G, top_n=3)
        
        assert len(critical) == 3
        assert all(isinstance(item, tuple) and len(item) == 2 for item in critical)
        # Results should be sorted by score descending
        scores = [score for _, score in critical]
        assert scores == sorted(scores, reverse=True)
    
    def test_identify_critical_headers_more_than_available(self) -> None:
        """Test requesting more critical headers than exist."""
        G: nx.DiGraph[str] = nx.DiGraph()
        G.add_edges_from([('A', 'B'), ('B', 'C')])
        
        critical = identify_critical_headers(G, top_n=10)
        
        # Should return all 3 nodes
        assert len(critical) == 3


class TestFeedbackArcSet:
    """Test minimum feedback arc set computation."""
    
    def test_feedback_arc_set_with_cycle(self) -> None:
        """Test feedback arc set on graph with cycle."""
        G: nx.DiGraph[str] = nx.DiGraph()
        G.add_edges_from([('A', 'B'), ('B', 'C'), ('C', 'D'), ('D', 'B')])
        
        fas = compute_minimum_feedback_arc_set(G)
        
        # Should find at least one edge to break the cycle
        assert len(fas) > 0
        
        # Verify removing these edges makes graph acyclic
        G_copy = G.copy()
        for u, v in fas:
            G_copy.remove_edge(u, v)
        
        # Should have no cycles now
        cycles = list(nx.simple_cycles(G_copy))
        assert len(cycles) == 0
    
    def test_feedback_arc_set_acyclic(self) -> None:
        """Test feedback arc set on acyclic graph."""
        G: nx.DiGraph[str] = nx.DiGraph()
        G.add_edges_from([('A', 'B'), ('B', 'C'), ('C', 'D')])
        
        fas = compute_minimum_feedback_arc_set(G)
        
        # Acyclic graph should need no edges removed
        assert len(fas) == 0
    
    def test_feedback_arc_set_self_loop(self) -> None:
        """Test feedback arc set with self-loop."""
        G: nx.DiGraph[str] = nx.DiGraph()
        G.add_edges_from([('A', 'A')])
        
        fas = compute_minimum_feedback_arc_set(G)
        
        assert len(fas) == 1
        assert fas[0] == ('A', 'A')


class TestCycleAnalysis:
    """Test cycle detection and analysis."""
    
    def test_find_strongly_connected_components(self) -> None:
        """Test finding SCCs in a graph."""
        G: nx.DiGraph[str] = nx.DiGraph()
        G.add_edges_from([('A', 'B'), ('B', 'C'), ('C', 'B'), ('D', 'E')])
        
        sccs = find_strongly_connected_components(G)
        
        # Should find the B-C cycle
        cycle_found = any(scc == {'B', 'C'} for scc in sccs)
        assert cycle_found
    
    def test_analyze_cycles_integration(self) -> None:
        """Test full cycle analysis."""
        header_to_headers = defaultdict(set)
        header_to_headers['a.h'] = {'b.h', 'd.h'}
        header_to_headers['b.h'] = {'c.h'}
        header_to_headers['c.h'] = {'d.h'}
        header_to_headers['d.h'] = {'b.h'}
        all_headers = {'a.h', 'b.h', 'c.h', 'd.h'}
        
        cycles, headers_in_cycles, feedback_edges, directed_graph = analyze_cycles(
            header_to_headers, all_headers
        )
        
        assert len(cycles) == 1
        assert len(headers_in_cycles) == 3  # b.h, c.h, d.h
        assert len(feedback_edges) >= 1
        assert isinstance(directed_graph, nx.DiGraph)
        assert directed_graph.number_of_nodes() == 4


class TestLayerComputation:
    """Test dependency layer computation."""
    
    def test_compute_layers_acyclic(self) -> None:
        """Test layer computation on acyclic graph."""
        header_to_headers = {
            'a.h': {'b.h', 'c.h'},
            'b.h': {'d.h'},
            'c.h': {'d.h'},
            'd.h': set()
        }
        all_headers = {'a.h', 'b.h', 'c.h', 'd.h'}
        
        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)
        
        assert not has_cycles
        assert len(layers) == 3  # Three topological levels
        # Verify all headers have a layer assigned
        assert 'd.h' in header_to_layer
        assert 'a.h' in header_to_layer
        # a.h should be in layer 0 (no dependencies on it from within this set)
        assert header_to_layer['a.h'] == 0
        # d.h should be in the last layer (depended on by others)
        assert header_to_layer['d.h'] == 2
    
    def test_compute_layers_with_cycle(self) -> None:
        """Test layer computation with cycles."""
        header_to_headers = {
            'a.h': {'b.h'},
            'b.h': {'c.h'},
            'c.h': {'b.h'}
        }
        all_headers = {'a.h', 'b.h', 'c.h'}
        
        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)
        
        assert has_cycles


class TestTransitiveDependents:
    """Test transitive dependents computation."""
    
    def test_build_transitive_dependents_map(self) -> None:
        """Test building transitive dependents map."""
        lib_to_libs = {
            'libA': {'libB', 'libC'},
            'libB': {'libD'},
            'libC': {'libD'},
            'libD': set()
        }
        exe_to_libs = {
            'app1': {'libA'},
            'app2': {'libB'}
        }
        
        transitive_deps = build_transitive_dependents_map(lib_to_libs, exe_to_libs)
        
        # libD is used by everyone
        assert 'app1' in transitive_deps['libD']
        assert 'app2' in transitive_deps['libD']
        assert 'libB' in transitive_deps['libD']
        assert 'libC' in transitive_deps['libD']
        
        # libA is only used by app1
        assert transitive_deps['libA'] == {'app1'}


class TestGraphMetrics:
    """Test graph metrics computation."""
    
    def test_compute_fan_in_fan_out(self) -> None:
        """Test fan-in/fan-out computation."""
        G: nx.DiGraph[str] = nx.DiGraph()
        G.add_edges_from([('A', 'B'), ('A', 'C'), ('B', 'D'), ('C', 'D')])
        
        metrics = compute_fan_in_fan_out(G)
        
        assert metrics['A'] == (0, 2)  # fan_in=0, fan_out=2
        assert metrics['D'] == (2, 0)  # fan_in=2, fan_out=0
        assert metrics['B'] == (1, 1)  # fan_in=1, fan_out=1
    
    def test_find_hub_nodes(self) -> None:
        """Test finding hub nodes."""
        G: nx.DiGraph[str] = nx.DiGraph()
        G.add_edges_from([
            ('A', 'H'), ('B', 'H'), ('C', 'H'), ('D', 'H'), ('E', 'H'),
            ('H', 'X'), ('H', 'Y'), ('H', 'Z')
        ])
        
        hubs = find_hub_nodes(G, threshold=5)
        
        # H should be a hub with high connectivity
        assert len(hubs) > 0
        hub_nodes = [node for node, _, _ in hubs]
        assert 'H' in hub_nodes
    
    def test_compute_betweenness_centrality(self) -> None:
        """Test betweenness centrality."""
        G: nx.DiGraph[str] = nx.DiGraph()
        G.add_edges_from([('A', 'B'), ('B', 'C'), ('C', 'D')])
        
        bc = compute_betweenness_centrality(G)
        
        # B and C should have higher betweenness
        assert len(bc) == 4
        assert bc['B'] >= bc['A']
        assert bc['C'] >= bc['D']


class TestDSMMetrics:
    """Test DSMMetrics dataclass."""
    
    def test_dsm_metrics_creation(self) -> None:
        """Test creating DSMMetrics."""
        metrics = DSMMetrics(
            fan_out=5,
            fan_in=3,
            coupling=8,
            stability=0.625
        )
        
        assert metrics.fan_out == 5
        assert metrics.fan_in == 3
        assert metrics.coupling == 8
        assert metrics.stability == 0.625


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
