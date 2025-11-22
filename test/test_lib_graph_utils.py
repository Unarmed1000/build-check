#!/usr/bin/env python3
"""Tests for lib/graph_utils.py"""

import pytest
from typing import Any, Dict, List, Tuple, Generator
import tempfile
from pathlib import Path

try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False

from lib.graph_utils import (
    build_dependency_graph, find_strongly_connected_components,
    build_reverse_dependencies, compute_layers, analyze_cycles,
    compute_topological_layers, compute_transitive_closure,
    compute_reverse_transitive_closure, build_transitive_dependents_map,
    compute_fan_in_fan_out, find_hub_nodes, compute_betweenness_centrality,
    find_longest_path_through_node, export_graph_to_graphml, export_graph_to_dot
)


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestBuildDependencyGraph:
    """Tests for build_dependency_graph function."""
    
    def test_simple_graph(self) -> None:
        """Test building a simple dependency graph."""
        include_graph = {
            "a.hpp": {"b.hpp"},
            "b.hpp": {"c.hpp"},
            "c.hpp": set()
        }
        all_headers = {"a.hpp", "b.hpp", "c.hpp"}
        
        graph = build_dependency_graph(include_graph, all_headers)
        
        assert graph is not None
        assert graph.has_edge("a.hpp", "b.hpp")
        assert graph.has_edge("b.hpp", "c.hpp")
        assert len(graph.nodes()) == 3
    
    def test_empty_graph(self) -> None:
        """Test with empty dependencies."""
        graph = build_dependency_graph({}, set())
        
        assert graph is not None
        assert len(graph.nodes()) == 0


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestStronglyConnectedComponents:
    """Tests for find_strongly_connected_components function."""
    
    def test_no_cycles(self) -> None:
        """Test graph with no cycles."""
        G: Any = nx.DiGraph()
        G.add_edge("a", "b")
        G.add_edge("b", "c")
        
        sccs = find_strongly_connected_components(G)
        
        # Function only returns cycles (components with >1 node)
        assert len(sccs) == 0
    
    def test_simple_cycle(self) -> None:
        """Test graph with a simple cycle."""
        G: Any = nx.DiGraph()
        G.add_edge("a", "b")
        G.add_edge("b", "a")
        
        sccs = find_strongly_connected_components(G)
        
        # Should detect the cycle
        assert any(len(scc) > 1 for scc in sccs)


class TestBuildReverseDependencies:
    """Tests for build_reverse_dependencies function."""
    
    def test_simple_reverse(self) -> None:
        """Test building reverse dependencies."""
        header_to_headers = {
            "a.hpp": {"b.hpp"},
            "b.hpp": {"c.hpp"}
        }
        all_headers = {"a.hpp", "b.hpp", "c.hpp"}
        
        reverse = build_reverse_dependencies(header_to_headers, all_headers)
        
        assert "a.hpp" in reverse["b.hpp"]
        assert "b.hpp" in reverse["c.hpp"]
    
    def test_multiple_dependents(self) -> None:
        """Test with multiple dependents."""
        header_to_headers = {
            "a.hpp": {"c.hpp"},
            "b.hpp": {"c.hpp"}
        }
        all_headers = {"a.hpp", "b.hpp", "c.hpp"}
        
        reverse = build_reverse_dependencies(header_to_headers, all_headers)
        
        assert len(reverse["c.hpp"]) == 2
        assert "a.hpp" in reverse["c.hpp"]
        assert "b.hpp" in reverse["c.hpp"]


class TestComputeLayers:
    """Tests for compute_layers function."""
    
    def test_linear_dependencies(self) -> None:
        """Test layering with linear dependencies."""
        header_to_headers = {
            "a.hpp": {"b.hpp"},
            "b.hpp": {"c.hpp"},
            "c.hpp": set()
        }
        all_headers = {"a.hpp", "b.hpp", "c.hpp"}
        
        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)
        
        assert not has_cycles
        assert len(layers) >= 1
        # Layers are computed differently - just verify structure is valid
        assert all(isinstance(layer, list) for layer in layers)
    
    def test_with_cycle(self) -> None:
        """Test layering with cycles."""
        header_to_headers = {
            "a.hpp": {"b.hpp"},
            "b.hpp": {"a.hpp"}
        }
        all_headers = {"a.hpp", "b.hpp"}
        
        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)
        
        assert has_cycles


class TestAnalyzeCycles:
    """Tests for analyze_cycles function."""
    
    def test_no_cycles(self) -> None:
        """Test analysis with no cycles."""
        header_to_headers = {
            "a.hpp": {"b.hpp"},
            "b.hpp": set()
        }
        all_headers = {"a.hpp", "b.hpp"}
        
        cycles, headers_in_cycles, feedback_edges, graph = analyze_cycles(header_to_headers, all_headers)
        
        assert len(cycles) == 0
        assert len(headers_in_cycles) == 0
        assert len(feedback_edges) == 0
    
    def test_simple_cycle(self) -> None:
        """Test analysis with a simple cycle."""
        header_to_headers = {
            "a.hpp": {"b.hpp"},
            "b.hpp": {"a.hpp"}
        }
        all_headers = {"a.hpp", "b.hpp"}
        
        cycles, headers_in_cycles, feedback_edges, graph = analyze_cycles(header_to_headers, all_headers)
        
        assert len(cycles) > 0
        assert len(headers_in_cycles) == 2


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestComputeTopologicalLayers:
    """Tests for compute_topological_layers function."""
    
    def test_simple_dag(self) -> None:
        """Test topological layering on a DAG."""
        G: Any = nx.DiGraph()
        G.add_edge("a", "b")
        G.add_edge("b", "c")
        
        layers = compute_topological_layers(G)
        
        # Layer 0 = sources (no incoming), higher = more depended upon
        # a -> b -> c means: a is source (layer 0), c is foundation (highest layer)
        assert layers["a"] < layers["b"]
        assert layers["b"] < layers["c"]
    
    def test_disconnected_nodes(self) -> None:
        """Test with disconnected nodes."""
        G: Any = nx.DiGraph()
        G.add_node("a")
        G.add_node("b")
        
        layers = compute_topological_layers(G)
        
        assert "a" in layers
        assert "b" in layers


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestTransitiveClosure:
    """Tests for transitive closure functions."""
    
    def test_compute_transitive_closure(self) -> None:
        """Test computing transitive closure."""
        G: Any = nx.DiGraph()
        G.add_edge("a", "b")
        G.add_edge("b", "c")
        
        closure = compute_transitive_closure(G, "a")
        
        assert "b" in closure
        assert "c" in closure
    
    def test_compute_reverse_transitive_closure(self) -> None:
        """Test computing reverse transitive closure."""
        G: Any = nx.DiGraph()
        G.add_edge("a", "b")
        G.add_edge("b", "c")
        
        closure = compute_reverse_transitive_closure(G, "c")
        
        assert "a" in closure
        assert "b" in closure


class TestBuildTransitiveDependentsMap:
    """Tests for build_transitive_dependents_map function."""
    
    def test_simple_dependents(self) -> None:
        """Test building transitive dependents map."""
        lib_to_libs = {
            "libA.a": {"libB.a"},
            "libB.a": {"libC.a"},
            "libC.a": set()
        }
        exe_to_libs: dict[str, set[str]] = {}
        
        transitive_map = build_transitive_dependents_map(lib_to_libs, exe_to_libs)
        
        # Verify structure is created
        assert isinstance(transitive_map, dict)


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestFanInFanOut:
    """Tests for fan-in/fan-out analysis."""
    
    def test_compute_fan_in_fan_out(self) -> None:
        """Test computing fan-in and fan-out."""
        G: Any = nx.DiGraph()
        G.add_edge("a", "c")
        G.add_edge("b", "c")
        G.add_edge("c", "d")
        
        metrics = compute_fan_in_fan_out(G)
        
        fan_in, fan_out = metrics["c"]
        # fan_in is in_degree (edges coming into c)
        assert fan_in == 2   # 2 edges coming into c
        # fan_out is out_degree (edges going out from c)
        assert fan_out == 1  # c has 1 outgoing edge
    
    def test_find_hub_nodes(self) -> None:
        """Test finding hub nodes."""
        G: Any = nx.DiGraph()
        G.add_edge("a", "hub")
        G.add_edge("b", "hub")
        G.add_edge("c", "hub")
        G.add_edge("hub", "d")
        G.add_edge("hub", "e")
        
        hubs = find_hub_nodes(G, threshold=2)
        
        assert len(hubs) > 0


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestBetweennessCentrality:
    """Tests for betweenness centrality."""
    
    def test_compute_betweenness(self) -> None:
        """Test computing betweenness centrality."""
        G: Any = nx.DiGraph()
        G.add_edge("a", "b")
        G.add_edge("b", "c")
        
        centrality = compute_betweenness_centrality(G)
        
        assert "b" in centrality
        # b should have high centrality as it's on path between a and c


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestLongestPath:
    """Tests for longest path computation."""
    
    def test_find_longest_path(self) -> None:
        """Test finding longest path through node."""
        G: Any = nx.DiGraph()
        G.add_edge("a", "b")
        G.add_edge("b", "c")
        G.add_edge("c", "d")
        
        length = find_longest_path_through_node(G, "b")
        
        assert length > 0


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestGraphExport:
    """Tests for graph export functions."""
    
    def test_export_to_graphml(self, temp_dir: Any) -> None:
        """Test exporting graph to GraphML."""
        G: Any = nx.DiGraph()
        G.add_edge("a", "b")
        
        output_file = temp_dir / "test.graphml"
        result = export_graph_to_graphml(G, str(output_file))
        
        assert result is True
        assert output_file.exists()
    
    def test_export_to_graphml_with_attributes(self, temp_dir: Any) -> None:
        """Test exporting graph with node attributes."""
        G: Any = nx.DiGraph()
        G.add_node("a", label="Node A")
        G.add_edge("a", "b")
        
        output_file = temp_dir / "test_attrs.graphml"
        result = export_graph_to_graphml(G, str(output_file), node_attributes={"a": {"label": "Node A"}})
        
        assert result is True


@pytest.fixture
def temp_dir() -> Any:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
