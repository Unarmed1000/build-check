#!/usr/bin/env python3
"""Additional tests for lib/graph_utils.py - Testing new functionality."""

import pytest
from typing import Any, Dict, List, Set, Tuple
import tempfile
from pathlib import Path

try:
    import networkx as nx

    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False

from lib.graph_utils import (
    compute_reverse_dependencies,
    compute_transitive_metrics,
    compute_chain_lengths,
    identify_critical_headers,
    compute_pagerank_centrality,
    calculate_dsm_metrics,
    visualize_dsm,
    compute_minimum_feedback_arc_set,
    DSMMetrics,
)


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestComputeReverseDependencies:
    """Tests for compute_reverse_dependencies function."""

    @pytest.mark.unit
    def test_simple_reverse_deps(self) -> None:
        """Test computing reverse dependencies on a simple graph."""
        G: Any = nx.DiGraph()
        G.add_edge("a.hpp", "b.hpp")
        G.add_edge("b.hpp", "c.hpp")
        G.add_edge("d.hpp", "b.hpp")

        reverse_deps, tc = compute_reverse_dependencies(G)

        # b.hpp should have a.hpp and d.hpp as reverse dependencies
        assert "a.hpp" in reverse_deps.get("b.hpp", set())
        assert "d.hpp" in reverse_deps.get("b.hpp", set())
        # c.hpp should have b.hpp, a.hpp, d.hpp as transitive reverse deps
        assert "b.hpp" in reverse_deps.get("c.hpp", set())
        assert tc is not None

    @pytest.mark.unit
    def test_reverse_deps_with_cycle(self) -> None:
        """Test reverse dependencies with cycles in graph."""
        G: Any = nx.DiGraph()
        G.add_edge("a.hpp", "b.hpp")
        G.add_edge("b.hpp", "c.hpp")
        G.add_edge("c.hpp", "a.hpp")  # Create cycle

        reverse_deps, tc = compute_reverse_dependencies(G)

        # Should handle cycles gracefully
        assert reverse_deps is not None
        assert len(reverse_deps) > 0

    @pytest.mark.unit
    def test_reverse_deps_empty_graph(self) -> None:
        """Test reverse dependencies on empty graph."""
        G: Any = nx.DiGraph()

        reverse_deps, tc = compute_reverse_dependencies(G)

        assert reverse_deps == {}


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestComputeTransitiveMetrics:
    """Tests for compute_transitive_metrics function."""

    @pytest.mark.unit
    def test_simple_transitive_metrics(self) -> None:
        """Test computing transitive metrics on a simple graph."""
        G: Any = nx.DiGraph()
        G.add_edge("a.hpp", "b.hpp")
        G.add_edge("b.hpp", "c.hpp")

        tc = nx.transitive_closure_dag(G)
        reverse_deps = {"b.hpp": {"a.hpp"}, "c.hpp": {"a.hpp", "b.hpp"}}
        project_headers = ["a.hpp", "b.hpp", "c.hpp"]

        base_types, trans_deps, reverse_impact = compute_transitive_metrics(G, tc, project_headers, reverse_deps)

        # c.hpp is a base type (no outgoing edges)
        assert "c.hpp" in base_types
        # a.hpp should have 2 transitive deps (b.hpp, c.hpp)
        assert trans_deps["a.hpp"] == 2
        # c.hpp should have 2 reverse impact (a.hpp, b.hpp depend on it)
        assert reverse_impact["c.hpp"] == 2

    @pytest.mark.unit
    def test_transitive_metrics_no_tc(self) -> None:
        """Test transitive metrics when tc is None (fallback path)."""
        G: Any = nx.DiGraph()
        G.add_edge("a.hpp", "b.hpp")

        reverse_deps = {"b.hpp": {"a.hpp"}}
        project_headers = ["a.hpp", "b.hpp"]

        base_types, trans_deps, reverse_impact = compute_transitive_metrics(G, None, project_headers, reverse_deps)

        # Should still work without tc
        assert base_types is not None
        assert trans_deps is not None
        assert reverse_impact is not None

    @pytest.mark.unit
    def test_transitive_metrics_isolated_nodes(self) -> None:
        """Test transitive metrics with isolated nodes."""
        G: Any = nx.DiGraph()
        G.add_node("isolated.hpp")
        G.add_edge("a.hpp", "b.hpp")

        tc = nx.transitive_closure_dag(G)
        reverse_deps = {"b.hpp": {"a.hpp"}}
        project_headers = ["a.hpp", "b.hpp", "isolated.hpp"]

        base_types, trans_deps, reverse_impact = compute_transitive_metrics(G, tc, project_headers, reverse_deps)

        # Isolated node is a base type
        assert "isolated.hpp" in base_types
        # Isolated node has 0 transitive deps
        assert trans_deps["isolated.hpp"] == 0


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestComputeChainLengths:
    """Tests for compute_chain_lengths function."""

    @pytest.mark.unit
    def test_simple_chain_lengths(self) -> None:
        """Test computing chain lengths on a simple graph."""
        G: Any = nx.DiGraph()
        G.add_edge("a.hpp", "b.hpp")
        G.add_edge("b.hpp", "c.hpp")
        G.add_edge("c.hpp", "d.hpp")

        project_headers = ["a.hpp", "b.hpp", "c.hpp", "d.hpp"]
        base_types = {"d.hpp"}

        chain_lengths = compute_chain_lengths(G, project_headers, base_types)

        # a.hpp -> b.hpp -> c.hpp -> d.hpp (length 3)
        assert chain_lengths["a.hpp"] >= 2
        assert chain_lengths["d.hpp"] == 0  # Base type

    @pytest.mark.unit
    def test_chain_lengths_no_base_types(self) -> None:
        """Test chain lengths when there are no base types."""
        G: Any = nx.DiGraph()
        G.add_edge("a.hpp", "b.hpp")

        project_headers = ["a.hpp", "b.hpp"]
        base_types: Set[str] = set()

        chain_lengths = compute_chain_lengths(G, project_headers, base_types)

        # Should return 0 for all headers
        assert all(length == 0 for length in chain_lengths.values())

    @pytest.mark.unit
    def test_chain_lengths_with_cycle(self) -> None:
        """Test chain lengths with cycles (fallback to non-DAG method)."""
        G: Any = nx.DiGraph()
        G.add_edge("a.hpp", "b.hpp")
        G.add_edge("b.hpp", "a.hpp")  # Cycle

        project_headers = ["a.hpp", "b.hpp"]
        base_types = {"a.hpp"}

        chain_lengths = compute_chain_lengths(G, project_headers, base_types)

        # Should handle cycles gracefully
        assert chain_lengths is not None
        assert len(chain_lengths) == 2


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestIdentifyCriticalHeaders:
    """Tests for identify_critical_headers function."""

    @pytest.mark.unit
    def test_identify_critical_simple(self) -> None:
        """Test identifying critical headers in a simple graph."""
        G: Any = nx.DiGraph()
        G.add_edge("a.hpp", "common.hpp")
        G.add_edge("b.hpp", "common.hpp")
        G.add_edge("c.hpp", "common.hpp")

        critical = identify_critical_headers(G, top_n=2)

        # common.hpp should be identified as critical (high PageRank)
        assert len(critical) > 0
        header_names = [h for h, _ in critical]
        assert "common.hpp" in header_names

    @pytest.mark.unit
    def test_identify_critical_empty_graph(self) -> None:
        """Test identifying critical headers in empty graph."""
        G: Any = nx.DiGraph()

        critical = identify_critical_headers(G, top_n=5)

        assert critical == []

    @pytest.mark.unit
    def test_identify_critical_linear(self) -> None:
        """Test identifying critical headers in linear graph."""
        G: Any = nx.DiGraph()
        G.add_edge("a.hpp", "b.hpp")
        G.add_edge("b.hpp", "c.hpp")

        critical = identify_critical_headers(G, top_n=3)

        # Should return at most 3 headers
        assert len(critical) <= 3
        # All should have PageRank scores
        assert all(score > 0 for _, score in critical)


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestComputePageRankCentrality:
    """Tests for compute_pagerank_centrality function."""

    @pytest.mark.unit
    def test_pagerank_simple(self) -> None:
        """Test PageRank on a simple graph."""
        G: Any = nx.DiGraph()
        G.add_edge("a.hpp", "b.hpp")
        G.add_edge("c.hpp", "b.hpp")

        pagerank = compute_pagerank_centrality(G)

        assert len(pagerank) == 3
        # b.hpp should have higher PageRank (two incoming edges)
        assert pagerank["b.hpp"] > pagerank["a.hpp"]
        assert pagerank["b.hpp"] > pagerank["c.hpp"]

    @pytest.mark.unit
    def test_pagerank_custom_params(self) -> None:
        """Test PageRank with custom parameters."""
        G: Any = nx.DiGraph()
        G.add_edge("a.hpp", "b.hpp")

        pagerank = compute_pagerank_centrality(G, alpha=0.9, max_iter=50)

        assert len(pagerank) == 2
        assert all(0 <= score <= 1 for score in pagerank.values())

    @pytest.mark.unit
    def test_pagerank_empty_graph(self) -> None:
        """Test PageRank on empty graph."""
        G: Any = nx.DiGraph()

        pagerank = compute_pagerank_centrality(G)

        assert pagerank == {}


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestCalculateDSMMetrics:
    """Tests for calculate_dsm_metrics function."""

    @pytest.mark.unit
    def test_dsm_metrics_simple(self) -> None:
        """Test calculating DSM metrics for a header."""
        header_to_headers = {"a.hpp": {"b.hpp", "c.hpp"}, "b.hpp": {"c.hpp"}, "c.hpp": set()}
        reverse_deps = {"b.hpp": {"a.hpp"}, "c.hpp": {"a.hpp", "b.hpp"}}

        metrics = calculate_dsm_metrics("a.hpp", header_to_headers, reverse_deps)

        assert metrics.fan_out == 2  # Depends on b.hpp, c.hpp
        assert metrics.fan_in == 0  # Nothing depends on a.hpp
        assert metrics.coupling == 2  # fan_out + fan_in
        assert metrics.stability == 1.0  # fan_out / coupling

    @pytest.mark.unit
    def test_dsm_metrics_hub_header(self) -> None:
        """Test DSM metrics for a hub header (high fan-in)."""
        header_to_headers = {"a.hpp": {"hub.hpp"}, "b.hpp": {"hub.hpp"}, "c.hpp": {"hub.hpp"}, "hub.hpp": set()}
        reverse_deps = {"hub.hpp": {"a.hpp", "b.hpp", "c.hpp"}}

        metrics = calculate_dsm_metrics("hub.hpp", header_to_headers, reverse_deps)

        assert metrics.fan_out == 0  # Depends on nothing
        assert metrics.fan_in == 3  # Three headers depend on it
        assert metrics.coupling == 3
        assert metrics.stability == 0.0  # Very stable (low fan_out)

    @pytest.mark.unit
    def test_dsm_metrics_isolated(self) -> None:
        """Test DSM metrics for an isolated header."""
        header_to_headers: Dict[str, Set[str]] = {"isolated.hpp": set()}
        reverse_deps: Dict[str, Set[str]] = {}

        metrics = calculate_dsm_metrics("isolated.hpp", header_to_headers, reverse_deps)

        assert metrics.fan_out == 0
        assert metrics.fan_in == 0
        assert metrics.coupling == 0
        assert metrics.stability == 0.5  # Neutral


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestVisualizeDSM:
    """Tests for visualize_dsm function."""

    @pytest.mark.unit
    def test_visualize_dsm_simple(self, capsys: Any) -> None:
        """Test visualizing a simple DSM."""
        headers = ["/project/a.hpp", "/project/b.hpp"]
        header_to_headers = {"/project/a.hpp": {"/project/b.hpp"}, "/project/b.hpp": set()}
        headers_in_cycles: Set[str] = set()

        visualize_dsm(headers, header_to_headers, headers_in_cycles, "/project", top_n=2)

        captured = capsys.readouterr()
        assert "Dependency Structure Matrix" in captured.out
        assert "a.hpp" in captured.out
        assert "b.hpp" in captured.out

    @pytest.mark.unit
    def test_visualize_dsm_with_cycles(self, capsys: Any) -> None:
        """Test visualizing DSM with cycles highlighted."""
        headers = ["/project/a.hpp", "/project/b.hpp"]
        header_to_headers = {"/project/a.hpp": {"/project/b.hpp"}, "/project/b.hpp": {"/project/a.hpp"}}
        headers_in_cycles = {"/project/a.hpp", "/project/b.hpp"}

        visualize_dsm(headers, header_to_headers, headers_in_cycles, "/project", top_n=2)

        captured = capsys.readouterr()
        assert "Dependency Structure Matrix" in captured.out
        # Should show cycle indicators
        assert "circular dependency" in captured.out.lower()

    @pytest.mark.unit
    def test_visualize_dsm_empty(self, capsys: Any) -> None:
        """Test visualizing empty DSM."""
        headers: List[str] = []
        header_to_headers: Dict[str, Set[str]] = {}
        headers_in_cycles: Set[str] = set()

        visualize_dsm(headers, header_to_headers, headers_in_cycles, "/project", top_n=5)

        captured = capsys.readouterr()
        # Warning message goes to stderr via print_warning
        assert "No headers to display" in captured.err or "No headers to display" in captured.out


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestComputeMinimumFeedbackArcSet:
    """Tests for compute_minimum_feedback_arc_set function."""

    @pytest.mark.unit
    def test_feedback_simple_cycle(self) -> None:
        """Test feedback arc set on a simple cycle."""
        G: Any = nx.DiGraph()
        G.add_edge("a.hpp", "b.hpp")
        G.add_edge("b.hpp", "c.hpp")
        G.add_edge("c.hpp", "a.hpp")  # Cycle

        feedback = compute_minimum_feedback_arc_set(G)

        # Should return at least one edge to break the cycle
        assert len(feedback) >= 1
        # Verify it's an actual edge
        assert all(G.has_edge(u, v) for u, v in feedback)

    @pytest.mark.unit
    def test_feedback_no_cycle(self) -> None:
        """Test feedback arc set on acyclic graph."""
        G: Any = nx.DiGraph()
        G.add_edge("a.hpp", "b.hpp")
        G.add_edge("b.hpp", "c.hpp")

        feedback = compute_minimum_feedback_arc_set(G)

        # Should return empty list (no cycles to break)
        assert feedback == []

    @pytest.mark.unit
    def test_feedback_multiple_cycles(self) -> None:
        """Test feedback arc set with multiple cycles."""
        G: Any = nx.DiGraph()
        # Cycle 1: a -> b -> a
        G.add_edge("a.hpp", "b.hpp")
        G.add_edge("b.hpp", "a.hpp")
        # Cycle 2: c -> d -> c
        G.add_edge("c.hpp", "d.hpp")
        G.add_edge("d.hpp", "c.hpp")

        feedback = compute_minimum_feedback_arc_set(G)

        # Should return edges to break both cycles
        assert len(feedback) >= 2

    @pytest.mark.unit
    def test_feedback_empty_graph(self) -> None:
        """Test feedback arc set on empty graph."""
        G: Any = nx.DiGraph()

        feedback = compute_minimum_feedback_arc_set(G)

        assert feedback == []


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="networkx not available")
class TestDSMMetricsDataclass:
    """Tests for DSMMetrics dataclass."""

    @pytest.mark.unit
    def test_dsm_metrics_creation(self) -> None:
        """Test creating DSMMetrics instance."""
        metrics = DSMMetrics(fan_out=5, fan_in=10, coupling=15, stability=0.33)

        assert metrics.fan_out == 5
        assert metrics.fan_in == 10
        assert metrics.coupling == 15
        assert abs(metrics.stability - 0.33) < 0.01

    @pytest.mark.unit
    def test_dsm_metrics_stable_header(self) -> None:
        """Test DSMMetrics for a stable header (low stability value)."""
        metrics = DSMMetrics(fan_out=1, fan_in=20, coupling=21, stability=1 / 21)

        # Stable headers have low stability value (few dependencies, many dependents)
        assert metrics.stability < 0.1
        assert metrics.fan_in > metrics.fan_out

    @pytest.mark.unit
    def test_dsm_metrics_unstable_header(self) -> None:
        """Test DSMMetrics for an unstable header (high stability value)."""
        metrics = DSMMetrics(fan_out=20, fan_in=1, coupling=21, stability=20 / 21)

        # Unstable headers have high stability value (many dependencies, few dependents)
        assert metrics.stability > 0.9
        assert metrics.fan_out > metrics.fan_in
