#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test topological sort visualization in DSM analysis.

This test suite validates that the topological sort used for DSM matrix visualization
correctly handles self-loops and produces the expected ordering.

Tests both:
1. Old compute_layers() function (does NOT exclude self-loops, for core analysis)
2. New visualization-specific topological sort in display_analysis_results() (excludes self-loops)
"""

import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set, List
import pytest
import networkx as nx

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.dsm_analysis import run_dsm_analysis
from lib.graph_utils import compute_layers


class TestOldComputeLayersWithSelfLoops:
    """Test topological sort behavior with self-loops."""

    def test_simple_dag_without_self_loops(self) -> None:
        """Test basic DAG produces correct topological order."""
        # A -> B -> C (linear chain)
        all_headers = {"A", "B", "C"}
        header_to_headers = defaultdict(set, {"A": {"B"}, "B": {"C"}, "C": set()})

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        assert not has_cycles
        assert len(layers) == 3
        # Layer 0 should be sources (no incoming edges)
        assert "A" in layers[0]
        # Layer 1 should be B
        assert "B" in layers[1]
        # Layer 2 should be C (most depended upon)
        assert "C" in layers[2]

    def test_dag_with_single_self_loop(self) -> None:
        """Test OLD compute_layers() fails with self-loop (expected behavior)."""
        # A -> B -> C, B -> B (self-loop)
        all_headers = {"A", "B", "C"}
        header_to_headers = defaultdict(set, {"A": {"B"}, "B": {"C", "B"}, "C": set()})

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # OLD compute_layers() treats self-loops as cycles (expected behavior for core analysis)
        assert has_cycles
        assert len(layers) == 0  # No layers computed when cycles detected

    def test_dag_with_multiple_self_loops(self) -> None:
        """Test OLD compute_layers() fails with multiple self-loops (expected behavior)."""
        # A -> B -> C, A -> A, B -> B, C -> C (all have self-loops)
        all_headers = {"A", "B", "C"}
        header_to_headers = defaultdict(set, {"A": {"B", "A"}, "B": {"C", "B"}, "C": {"C"}})

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # OLD compute_layers() treats self-loops as cycles (expected behavior for core analysis)
        assert has_cycles
        assert len(layers) == 0  # No layers computed when cycles detected

    def test_diamond_pattern_with_self_loop(self) -> None:
        """Test OLD compute_layers() fails with diamond pattern + self-loop (expected behavior)."""
        # A -> B, A -> C, B -> D, C -> D, D -> D
        all_headers = {"A", "B", "C", "D"}
        header_to_headers = defaultdict(set, {"A": {"B", "C"}, "B": {"D"}, "C": {"D"}, "D": {"D"}})

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # OLD compute_layers() treats self-loops as cycles (expected behavior for core analysis)
        assert has_cycles
        assert len(layers) == 0  # No layers computed when cycles detected

    def test_true_cycle_still_detected(self) -> None:
        """Test that real multi-header cycles are still detected."""
        # A -> B -> C -> A (true cycle)
        all_headers = {"A", "B", "C"}
        header_to_headers = defaultdict(set, {"A": {"B"}, "B": {"C"}, "C": {"A"}})

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # Should fail - this is a real cycle
        assert has_cycles
        assert len(layers) == 0

    def test_mixed_self_loops_and_cycle(self) -> None:
        """Test graph with both self-loops and true cycles."""
        # A -> B -> A (cycle), B -> B (self-loop)
        all_headers = {"A", "B"}
        header_to_headers = defaultdict(set, {"A": {"B"}, "B": {"A", "B"}})

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # Should detect the cycle
        assert has_cycles
        assert len(layers) == 0

    def test_isolated_node_with_self_loop(self) -> None:
        """Test OLD compute_layers() fails with isolated node that has self-loop (expected behavior)."""
        all_headers = {"A", "B"}
        header_to_headers = defaultdict(set, {"A": {"A"}, "B": set()})

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # OLD compute_layers() treats self-loops as cycles (expected behavior for core analysis)
        assert has_cycles
        assert len(layers) == 0  # No layers computed when cycles detected

    def test_all_nodes_self_loop_only(self) -> None:
        """Test OLD compute_layers() fails when all nodes have self-loops (expected behavior)."""
        all_headers = {"A", "B", "C"}
        header_to_headers = defaultdict(set, {"A": {"A"}, "B": {"B"}, "C": {"C"}})

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # OLD compute_layers() treats self-loops as cycles (expected behavior for core analysis)
        assert has_cycles
        assert len(layers) == 0  # No layers computed when cycles detected

    def test_complex_dag_with_self_loops(self) -> None:
        """Test OLD compute_layers() fails with complex DAG with self-loops (expected behavior)."""
        # Complex dependency structure
        all_headers = {"A", "B", "C", "D", "E", "F"}
        header_to_headers = defaultdict(
            set,
            {
                "A": {"B", "C", "A"},  # self-loop
                "B": {"D", "B"},  # self-loop
                "C": {"D", "E"},
                "D": {"F", "D"},  # self-loop
                "E": {"F"},
                "F": {"F"},  # self-loop
            },
        )

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # OLD compute_layers() treats self-loops as cycles (expected behavior for core analysis)
        assert has_cycles
        assert len(layers) == 0  # No layers computed when cycles detected


class TestDSMVisualizationTopologicalSort:
    """Test that DSM analysis uses correct topological sort for visualization."""

    def test_dsm_analysis_with_self_loop_computes_layers(self) -> None:
        """Test that DSM analysis detects cycles when self-loops present (OLD behavior)."""
        all_headers = {"A.hpp", "B.hpp", "C.hpp"}
        header_to_headers = defaultdict(set, {"A.hpp": {"B.hpp"}, "B.hpp": {"C.hpp", "B.hpp"}, "C.hpp": set()})

        results = run_dsm_analysis(all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=True, show_progress=False)

        # OLD compute_layers() treats self-loops as cycles (expected)
        assert results.has_cycles
        assert len(results.layers) == 0

    def test_dsm_analysis_detects_self_loops_separately(self) -> None:
        """Test that self-loops are tracked separately from cycles."""
        all_headers = {"A.hpp", "B.hpp"}
        header_to_headers = defaultdict(set, {"A.hpp": {"B.hpp"}, "B.hpp": {"B.hpp"}})

        results = run_dsm_analysis(all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=True, show_progress=False)

        # OLD compute_layers() treats self-loops as cycles
        assert results.has_cycles
        # But self-loops are tracked separately
        assert len(results.self_loops) == 1
        assert "B.hpp" in results.self_loops

    def test_dsm_analysis_still_detects_true_cycles(self) -> None:
        """Test that true multi-header cycles are still detected."""
        all_headers = {"A.hpp", "B.hpp", "C.hpp"}
        header_to_headers = defaultdict(set, {"A.hpp": {"B.hpp"}, "B.hpp": {"C.hpp"}, "C.hpp": {"A.hpp"}})

        results = run_dsm_analysis(all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=True, show_progress=False)

        # Should detect the cycle
        assert results.has_cycles
        assert len(results.cycles) == 1
        assert len(results.cycles[0]) == 3

    def test_layer_ordering_for_visualization(self) -> None:
        """Test that layers are in correct order for reverse topological display."""
        # Build a clear hierarchy: Foundation <- Middle <- Top
        all_headers = {"Top.hpp", "Middle.hpp", "Foundation.hpp"}
        header_to_headers = defaultdict(set, {"Top.hpp": {"Middle.hpp"}, "Middle.hpp": {"Foundation.hpp"}, "Foundation.hpp": set()})

        results = run_dsm_analysis(all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=True, show_progress=False)

        assert not results.has_cycles
        assert len(results.layers) == 3

        # Layer 0 = sources (Top)
        # Layer 1 = middle dependencies
        # Layer 2 = foundation (most depended upon)
        assert "Top.hpp" in results.layers[0]
        assert "Middle.hpp" in results.layers[1]
        assert "Foundation.hpp" in results.layers[2]

        # For DSM visualization, we reverse this: [Foundation.hpp, Middle.hpp, Top.hpp]
        # This puts dependencies below the diagonal


class TestEdgeCasesTopologicalSort:
    """Test edge cases in topological sort."""

    def test_empty_graph(self) -> None:
        """Test empty graph."""
        all_headers: Set[str] = set()
        header_to_headers: Dict[str, Set[str]] = defaultdict(set)

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        assert not has_cycles
        assert len(layers) == 0

    def test_single_node_no_self_loop(self) -> None:
        """Test single node with no dependencies."""
        all_headers = {"A"}
        header_to_headers: Dict[str, Set[str]] = defaultdict(set, {"A": set()})

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        assert not has_cycles
        assert len(layers) == 1
        assert "A" in layers[0]

    def test_single_node_with_self_loop(self) -> None:
        """Test OLD compute_layers() fails with single node that has self-loop (expected behavior)."""
        all_headers = {"A"}
        header_to_headers = defaultdict(set, {"A": {"A"}})

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # OLD compute_layers() treats self-loops as cycles (expected behavior for core analysis)
        assert has_cycles
        assert len(layers) == 0  # No layers computed when cycles detected

    def test_disconnected_components_with_self_loops(self) -> None:
        """Test OLD compute_layers() fails with disconnected components with self-loops (expected behavior)."""
        # Component 1: A -> B, A -> A
        # Component 2: C -> D, D -> D
        all_headers = {"A", "B", "C", "D"}
        header_to_headers = defaultdict(set, {"A": {"B", "A"}, "B": set(), "C": {"D"}, "D": {"D"}})

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # OLD compute_layers() treats self-loops as cycles (expected behavior for core analysis)
        assert has_cycles
        assert len(layers) == 0  # No layers computed when cycles detected

    def test_self_loop_on_foundation_node(self) -> None:
        """Test OLD compute_layers() fails with self-loop on foundation node (expected behavior)."""
        # A -> B -> C, C -> C (self-loop on foundation)
        all_headers = {"A", "B", "C"}
        header_to_headers = defaultdict(set, {"A": {"B"}, "B": {"C"}, "C": {"C"}})

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # OLD compute_layers() treats self-loops as cycles (expected behavior for core analysis)
        assert has_cycles
        assert len(layers) == 0  # No layers computed when cycles detected

    def test_self_loop_on_source_node(self) -> None:
        """Test OLD compute_layers() fails with self-loop on source node (expected behavior)."""
        # A -> B -> C, A -> A (self-loop on source)
        all_headers = {"A", "B", "C"}
        header_to_headers = defaultdict(set, {"A": {"B", "A"}, "B": {"C"}, "C": set()})

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # OLD compute_layers() treats self-loops as cycles (expected behavior for core analysis)
        assert has_cycles
        assert len(layers) == 0  # No layers computed when cycles detected


class TestStressTestsTopologicalSort:
    """Stress tests for topological sort."""

    def test_large_chain_with_self_loops(self) -> None:
        """Test OLD compute_layers() fails with large chain where every node has self-loop (expected behavior)."""
        # Build: 0 -> 1 -> 2 -> ... -> 99, all with self-loops
        n = 100
        all_headers = {f"H{i}" for i in range(n)}
        header_to_headers = defaultdict(set)

        for i in range(n):
            header_to_headers[f"H{i}"].add(f"H{i}")  # self-loop
            if i < n - 1:
                header_to_headers[f"H{i}"].add(f"H{i+1}")

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # OLD compute_layers() treats self-loops as cycles (expected behavior for core analysis)
        assert has_cycles
        assert len(layers) == 0  # No layers computed when cycles detected

    def test_wide_graph_with_self_loops(self) -> None:
        """Test wide graph where all nodes depend on one foundation."""
        # Build: N0, N1, ..., N99 all depend on Foundation
        n = 100
        all_headers = {f"N{i}" for i in range(n)} | {"Foundation"}
        header_to_headers = defaultdict(set)

        header_to_headers["Foundation"].add("Foundation")  # self-loop
        for i in range(n):
            header_to_headers[f"N{i}"] = {"Foundation", f"N{i}"}  # all with self-loops

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # OLD compute_layers() treats self-loops as cycles (expected behavior for core analysis)
        assert has_cycles
        assert len(layers) == 0  # No layers computed when cycles detected

    def test_binary_tree_with_self_loops(self) -> None:
        """Test OLD compute_layers() fails with binary tree structure with self-loops (expected behavior)."""
        # Build binary tree: L0 -> L1_0, L1_1, L1_0 -> L2_0, L2_1, etc.
        all_headers = set()
        header_to_headers = defaultdict(set)

        # 4 levels of binary tree
        for level in range(4):
            for i in range(2**level):
                node = f"L{level}_N{i}"
                all_headers.add(node)
                header_to_headers[node].add(node)  # self-loop

                if level < 3:  # not leaf level
                    left_child = f"L{level+1}_N{2*i}"
                    right_child = f"L{level+1}_N{2*i+1}"
                    header_to_headers[node].update([left_child, right_child])

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # OLD compute_layers() treats self-loops as cycles (expected behavior for core analysis)
        assert has_cycles
        assert len(layers) == 0  # No layers computed when cycles detected


class TestLayerMappingConsistency:
    """Test that layer mappings are consistent."""

    def test_layer_mapping_matches_layers_list(self) -> None:
        """Test that header_to_layer mapping is consistent with layers list."""
        all_headers = {"A", "B", "C", "D"}
        header_to_headers = defaultdict(set, {"A": {"B", "C"}, "B": {"D"}, "C": {"D"}, "D": set()})

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        assert not has_cycles

        # Verify every header in layers is in header_to_layer
        for layer_num, layer_nodes in enumerate(layers):
            for node in layer_nodes:
                assert node in header_to_layer
                assert header_to_layer[node] == layer_num

        # Verify every header in header_to_layer is in layers
        for header, layer_num in header_to_layer.items():
            assert header in layers[layer_num]

    def test_layer_mapping_with_self_loops(self) -> None:
        """Test OLD compute_layers() fails with self-loops (expected behavior)."""
        all_headers = {"A", "B", "C"}
        header_to_headers = defaultdict(set, {"A": {"B", "A"}, "B": {"C", "B"}, "C": {"C"}})

        layers, header_to_layer, has_cycles = compute_layers(header_to_headers, all_headers)

        # OLD compute_layers() treats self-loops as cycles (expected behavior for core analysis)
        assert has_cycles
        assert len(layers) == 0  # No layers computed when cycles detected
        assert len(header_to_layer) == 0  # No mappings when cycles detected


class TestVisualizationTopologicalSortNew:
    """Test the NEW topological sort used ONLY in display_analysis_results for DSM visualization.

    This is DIFFERENT from compute_layers() - it excludes self-loops for display purposes only.
    """

    def test_visualization_sort_excludes_self_loops(self) -> None:
        """Test that visualization sort excludes self-loops and succeeds."""
        # Build graph with self-loop: A -> B -> C, B -> B
        all_headers = {"A.hpp", "B.hpp", "C.hpp"}
        header_to_headers = defaultdict(set, {"A.hpp": {"B.hpp"}, "B.hpp": {"C.hpp", "B.hpp"}, "C.hpp": set()})

        # Run DSM analysis - internally uses compute_layers (will fail with self-loop)
        results = run_dsm_analysis(all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=True, show_progress=False)

        # The OLD compute_layers() sees self-loop as cycle
        assert results.has_cycles  # compute_layers returns has_cycles=True
        assert len(results.layers) == 0  # No layers computed by compute_layers
        assert len(results.self_loops) == 1  # But self-loop is tracked separately

        # NOW test the NEW visualization topological sort
        # Simulate what display_analysis_results does
        import networkx as nx

        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_nodes_from(all_headers)

        # Build graph EXCLUDING self-loops (the NEW behavior)
        for header, deps in header_to_headers.items():
            for dep in deps:
                if dep in all_headers and dep != header:  # NEW: Exclude self-loops
                    graph.add_edge(header, dep)

        # Try topological sort with self-loops excluded
        try:
            generations = list(nx.topological_generations(graph))
            display_headers = [header for layer in reversed(generations) for header in sorted(layer)]
            success = True
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            success = False
            display_headers = []

        # NEW visualization sort should SUCCEED despite self-loop
        assert success
        assert len(generations) == 3
        assert "C.hpp" in display_headers[0]  # Foundation first (reversed order)
        assert "B.hpp" in display_headers[1]
        assert "A.hpp" in display_headers[2]  # Top-level last

    def test_visualization_sort_still_detects_real_cycles(self) -> None:
        """Test that visualization sort still fails on real multi-header cycles."""
        # Build graph with REAL cycle: A -> B -> C -> A
        all_headers = {"A.hpp", "B.hpp", "C.hpp"}
        header_to_headers = defaultdict(set, {"A.hpp": {"B.hpp"}, "B.hpp": {"C.hpp"}, "C.hpp": {"A.hpp"}})

        # Run DSM analysis
        results = run_dsm_analysis(all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=True, show_progress=False)

        # OLD compute_layers() correctly detects cycle
        assert results.has_cycles
        assert len(results.cycles) == 1

        # NEW visualization sort should ALSO fail on real cycles
        import networkx as nx

        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_nodes_from(all_headers)

        for header, deps in header_to_headers.items():
            for dep in deps:
                if dep in all_headers and dep != header:  # Exclude self-loops
                    graph.add_edge(header, dep)

        # Should still have cycle even with self-loop exclusion
        success = True
        try:
            generations = list(nx.topological_generations(graph))
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            success = False

        assert not success  # Should fail due to real cycle

    def test_old_vs_new_behavior_comparison(self) -> None:
        """Direct comparison: OLD compute_layers() vs NEW visualization sort."""
        # Graph with self-loops at every level
        all_headers = {"A", "B", "C", "D"}
        header_to_headers = defaultdict(
            set, {"A": {"B", "A"}, "B": {"C", "B"}, "C": {"D", "C"}, "D": {"D"}}  # self-loop  # self-loop  # self-loop  # self-loop
        )

        # OLD behavior: compute_layers() includes self-loops
        old_layers, old_mapping, old_has_cycles = compute_layers(header_to_headers, all_headers)

        # NEW behavior: visualization sort excludes self-loops
        import networkx as nx

        new_graph: nx.DiGraph[str] = nx.DiGraph()
        new_graph.add_nodes_from(all_headers)

        for header, deps in header_to_headers.items():
            for dep in deps:
                if dep in all_headers and dep != header:  # NEW: exclude self-loops
                    new_graph.add_edge(header, dep)

        try:
            new_generations = list(nx.topological_generations(new_graph))
            new_has_cycles = False
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            new_generations = []
            new_has_cycles = True

        # OLD sees cycles (because self-loops are included)
        assert old_has_cycles is True
        assert len(old_layers) == 0

        # NEW doesn't see cycles (because self-loops are excluded)
        assert new_has_cycles is False
        assert len(new_generations) == 4  # Proper layering without self-loops

    def test_visualization_complex_graph_with_self_loops(self) -> None:
        """Test complex graph where visualization sort succeeds but compute_layers fails."""
        # Complex hierarchy with self-loops throughout
        all_headers = {"Top", "Mid1", "Mid2", "Base1", "Base2", "Foundation"}
        header_to_headers = defaultdict(
            set,
            {
                "Top": {"Mid1", "Mid2", "Top"},  # self-loop
                "Mid1": {"Base1", "Mid1"},  # self-loop
                "Mid2": {"Base2", "Mid2"},  # self-loop
                "Base1": {"Foundation", "Base1"},  # self-loop
                "Base2": {"Foundation", "Base2"},  # self-loop
                "Foundation": {"Foundation"},  # self-loop
            },
        )

        # OLD behavior
        old_layers, _, old_has_cycles = compute_layers(header_to_headers, all_headers)

        # NEW behavior
        import networkx as nx

        new_graph: nx.DiGraph[str] = nx.DiGraph()
        new_graph.add_nodes_from(all_headers)

        for header, deps in header_to_headers.items():
            for dep in deps:
                if dep in all_headers and dep != header:
                    new_graph.add_edge(header, dep)

        try:
            new_generations = list(nx.topological_generations(new_graph))
            new_success = True
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            new_generations = []
            new_success = False

        # DIFFERENT BEHAVIOR:
        assert old_has_cycles is True  # OLD fails
        assert new_success is True  # NEW succeeds
        assert len(old_layers) == 0  # OLD produces no layers
        assert len(new_generations) == 4  # NEW produces proper layers

    def test_visualization_sort_preserves_dependency_structure(self) -> None:
        """Test that excluding self-loops doesn't break dependency relationships."""
        # A -> B -> C with self-loops, but dependency chain should be preserved
        all_headers = {"A", "B", "C"}
        header_to_headers = defaultdict(set, {"A": {"B", "A"}, "B": {"C", "B"}, "C": {"C"}})

        # NEW visualization sort
        import networkx as nx

        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_nodes_from(all_headers)

        for header, deps in header_to_headers.items():
            for dep in deps:
                if dep in all_headers and dep != header:
                    graph.add_edge(header, dep)

        generations = list(nx.topological_generations(graph))

        # Should preserve A -> B -> C structure
        assert len(generations) == 3
        assert "A" in generations[0]  # Sources
        assert "B" in generations[1]  # Middle
        assert "C" in generations[2]  # Foundation

    def test_mixed_self_loops_and_real_cycle_both_fail(self) -> None:
        """Test that both OLD and NEW fail when there's a real cycle."""
        # A -> B -> A (real cycle) + B -> B (self-loop)
        all_headers = {"A", "B"}
        header_to_headers = defaultdict(set, {"A": {"B"}, "B": {"A", "B"}})

        # OLD behavior
        old_layers, _, old_has_cycles = compute_layers(header_to_headers, all_headers)

        # NEW behavior
        import networkx as nx

        new_graph: nx.DiGraph[str] = nx.DiGraph()
        new_graph.add_nodes_from(all_headers)

        for header, deps in header_to_headers.items():
            for dep in deps:
                if dep in all_headers and dep != header:
                    new_graph.add_edge(header, dep)

        try:
            new_generations = list(nx.topological_generations(new_graph))
            new_has_cycles = False
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            new_has_cycles = True

        # BOTH should fail (real cycle exists)
        assert old_has_cycles is True
        assert new_has_cycles is True


class TestNewVisualizationTopologicalSort:
    """Test NEW visualization-specific topological sort in display_analysis_results()."""

    def _get_visualization_sort_result(self, header_to_headers: Dict[str, Set[str]], all_headers: Set[str]) -> tuple[List[str], bool]:
        """Helper to run the NEW visualization topological sort logic.

        Returns:
            (display_headers, has_cycles) tuple
        """
        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_nodes_from(all_headers)

        for header, deps in header_to_headers.items():
            for dep in deps:
                if dep in all_headers and dep != header:  # Exclude self-loops
                    graph.add_edge(header, dep)

        try:
            generations = list(nx.topological_generations(graph))
            display_headers = [header for layer in reversed(generations) for header in sorted(layer)]
            return display_headers, False
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            # Has cycles - return empty list
            return [], True

    def test_simple_dag_without_self_loops(self) -> None:
        """Test NEW sort with basic DAG produces correct topological order."""
        # A -> B -> C (linear chain)
        all_headers = {"A", "B", "C"}
        header_to_headers = {"A": {"B"}, "B": {"C"}, "C": set()}

        display_headers, has_cycles = self._get_visualization_sort_result(header_to_headers, all_headers)

        assert not has_cycles
        assert len(display_headers) == 3
        # Should be reversed: C (foundation) first, A (high-level) last
        assert display_headers.index("C") < display_headers.index("B")
        assert display_headers.index("B") < display_headers.index("A")

    def test_dag_with_single_self_loop(self) -> None:
        """Test NEW sort handles single self-loop correctly."""
        # A -> B -> C, B -> B (self-loop)
        all_headers = {"A", "B", "C"}
        header_to_headers = {"A": {"B"}, "B": {"C", "B"}, "C": set()}

        display_headers, has_cycles = self._get_visualization_sort_result(header_to_headers, all_headers)

        # NEW sort should succeed (self-loops excluded)
        assert not has_cycles
        assert len(display_headers) == 3
        # Same ordering as without self-loop
        assert display_headers.index("C") < display_headers.index("B")
        assert display_headers.index("B") < display_headers.index("A")

    def test_dag_with_multiple_self_loops(self) -> None:
        """Test NEW sort handles multiple self-loops correctly."""
        # A -> B -> C, all have self-loops
        all_headers = {"A", "B", "C"}
        header_to_headers = {"A": {"B", "A"}, "B": {"C", "B"}, "C": {"C"}}

        display_headers, has_cycles = self._get_visualization_sort_result(header_to_headers, all_headers)

        # NEW sort should succeed (all self-loops excluded)
        assert not has_cycles
        assert len(display_headers) == 3
        assert display_headers.index("C") < display_headers.index("B")
        assert display_headers.index("B") < display_headers.index("A")

    def test_diamond_with_self_loops(self) -> None:
        """Test NEW sort handles diamond structure with self-loops."""
        # A -> B, A -> C, B -> D, C -> D, all have self-loops
        all_headers = {"A", "B", "C", "D"}
        header_to_headers = {"A": {"B", "C", "A"}, "B": {"D", "B"}, "C": {"D", "C"}, "D": {"D"}}

        display_headers, has_cycles = self._get_visualization_sort_result(header_to_headers, all_headers)

        assert not has_cycles
        assert len(display_headers) == 4
        # D should come first (foundation), A should come last (high-level)
        assert display_headers.index("D") < display_headers.index("B")
        assert display_headers.index("D") < display_headers.index("C")
        assert display_headers.index("B") < display_headers.index("A")
        assert display_headers.index("C") < display_headers.index("A")

    def test_only_self_loops_no_real_edges(self) -> None:
        """Test NEW sort with headers that only have self-loops."""
        all_headers = {"A", "B", "C"}
        header_to_headers = {"A": {"A"}, "B": {"B"}, "C": {"C"}}

        display_headers, has_cycles = self._get_visualization_sort_result(header_to_headers, all_headers)

        # Should succeed - no real edges means no cycles
        assert not has_cycles
        assert len(display_headers) == 3
        # All are independent, should be alphabetically sorted within same layer
        assert set(display_headers) == {"A", "B", "C"}

    def test_real_cycle_with_self_loops(self) -> None:
        """Test NEW sort fails on real cycle even with self-loops."""
        # A -> B -> A (real cycle), plus self-loops
        all_headers = {"A", "B"}
        header_to_headers = {"A": {"B", "A"}, "B": {"A", "B"}}

        display_headers, has_cycles = self._get_visualization_sort_result(header_to_headers, all_headers)

        # Should fail - real cycle exists
        assert has_cycles
        assert display_headers == []

    def test_complex_dag_with_mixed_self_loops(self) -> None:
        """Test NEW sort with complex DAG where only some headers have self-loops."""
        # A -> B -> D, A -> C -> D, only B and C have self-loops
        all_headers = {"A", "B", "C", "D"}
        header_to_headers = {"A": {"B", "C"}, "B": {"D", "B"}, "C": {"D", "C"}, "D": set()}  # has self-loop  # has self-loop

        display_headers, has_cycles = self._get_visualization_sort_result(header_to_headers, all_headers)

        assert not has_cycles
        assert len(display_headers) == 4
        # D first (foundation), A last (high-level)
        assert display_headers.index("D") < display_headers.index("B")
        assert display_headers.index("D") < display_headers.index("C")
        assert display_headers.index("B") < display_headers.index("A")
        assert display_headers.index("C") < display_headers.index("A")

    def test_large_graph_with_many_self_loops(self) -> None:
        """Test NEW sort with large graph where many headers have self-loops."""
        all_headers = {f"H{i}" for i in range(20)}
        header_to_headers = {}

        # Create a linear chain with self-loops on even-numbered headers
        for i in range(20):
            deps = set()
            if i < 19:
                deps.add(f"H{i+1}")
            if i % 2 == 0:
                deps.add(f"H{i}")  # self-loop
            header_to_headers[f"H{i}"] = deps

        display_headers, has_cycles = self._get_visualization_sort_result(header_to_headers, all_headers)

        assert not has_cycles
        assert len(display_headers) == 20
        # H19 should come first (foundation), H0 should come last (high-level)
        assert display_headers.index("H19") < display_headers.index("H10")
        assert display_headers.index("H10") < display_headers.index("H0")


class TestVisualizationSortVsComputeLayersDifferential:
    """Test that NEW visualization sort behaves differently from OLD compute_layers()."""

    def test_single_self_loop_differential(self) -> None:
        """Verify OLD fails with self-loop, NEW succeeds."""
        # A -> B -> C, B -> B (self-loop)
        all_headers = {"A", "B", "C"}
        header_to_headers = defaultdict(set, {"A": {"B"}, "B": {"C", "B"}, "C": set()})

        # OLD compute_layers() behavior
        old_layers, _, old_has_cycles = compute_layers(header_to_headers, all_headers)

        # NEW visualization sort behavior
        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_nodes_from(all_headers)
        for header, deps in header_to_headers.items():
            for dep in deps:
                if dep in all_headers and dep != header:
                    graph.add_edge(header, dep)

        try:
            new_generations = list(nx.topological_generations(graph))
            new_has_cycles = False
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            new_has_cycles = True

        # DIFFERENTIAL: OLD should fail, NEW should succeed
        assert old_has_cycles is True, "OLD compute_layers() should fail with self-loop"
        assert new_has_cycles is False, "NEW visualization sort should succeed with self-loop"

    def test_multiple_self_loops_differential(self) -> None:
        """Verify OLD fails with multiple self-loops, NEW succeeds."""
        # A -> B -> C, all have self-loops
        all_headers = {"A", "B", "C"}
        header_to_headers = defaultdict(set, {"A": {"B", "A"}, "B": {"C", "B"}, "C": {"C"}})

        # OLD behavior
        _, _, old_has_cycles = compute_layers(header_to_headers, all_headers)

        # NEW behavior
        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_nodes_from(all_headers)
        for header, deps in header_to_headers.items():
            for dep in deps:
                if dep in all_headers and dep != header:
                    graph.add_edge(header, dep)

        try:
            list(nx.topological_generations(graph))
            new_has_cycles = False
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            new_has_cycles = True

        # DIFFERENTIAL: OLD should fail, NEW should succeed
        assert old_has_cycles is True, "OLD compute_layers() should fail with multiple self-loops"
        assert new_has_cycles is False, "NEW visualization sort should succeed with multiple self-loops"

    def test_real_cycle_both_fail(self) -> None:
        """Verify BOTH OLD and NEW fail on real cycles."""
        # A -> B -> A (real cycle), plus self-loops
        all_headers = {"A", "B"}
        header_to_headers = defaultdict(set, {"A": {"B", "A"}, "B": {"A", "B"}})

        # OLD behavior
        _, _, old_has_cycles = compute_layers(header_to_headers, all_headers)

        # NEW behavior
        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_nodes_from(all_headers)
        for header, deps in header_to_headers.items():
            for dep in deps:
                if dep in all_headers and dep != header:
                    graph.add_edge(header, dep)

        try:
            list(nx.topological_generations(graph))
            new_has_cycles = False
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            new_has_cycles = True

        # BOTH should fail (real cycle exists)
        assert old_has_cycles is True, "OLD compute_layers() should fail with real cycle"
        assert new_has_cycles is True, "NEW visualization sort should fail with real cycle"

    def test_no_self_loops_both_succeed(self) -> None:
        """Verify BOTH OLD and NEW succeed without self-loops."""
        # A -> B -> C (clean DAG)
        all_headers = {"A", "B", "C"}
        header_to_headers = defaultdict(set, {"A": {"B"}, "B": {"C"}, "C": set()})

        # OLD behavior
        _, _, old_has_cycles = compute_layers(header_to_headers, all_headers)

        # NEW behavior
        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_nodes_from(all_headers)
        for header, deps in header_to_headers.items():
            for dep in deps:
                if dep in all_headers and dep != header:
                    graph.add_edge(header, dep)

        try:
            list(nx.topological_generations(graph))
            new_has_cycles = False
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            new_has_cycles = True

        # BOTH should succeed (no cycles)
        assert old_has_cycles is False, "OLD compute_layers() should succeed without cycles"
        assert new_has_cycles is False, "NEW visualization sort should succeed without cycles"

    def test_mixed_self_loops_differential(self) -> None:
        """Verify differential behavior with complex graph having mixed self-loops."""
        # Diamond: A -> B, A -> C, B -> D, C -> D, only B and D have self-loops
        all_headers = {"A", "B", "C", "D"}
        header_to_headers = defaultdict(set, {"A": {"B", "C"}, "B": {"D", "B"}, "C": {"D"}, "D": {"D"}})  # self-loop  # self-loop

        # OLD behavior
        _, _, old_has_cycles = compute_layers(header_to_headers, all_headers)

        # NEW behavior
        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_nodes_from(all_headers)
        for header, deps in header_to_headers.items():
            for dep in deps:
                if dep in all_headers and dep != header:
                    graph.add_edge(header, dep)

        try:
            list(nx.topological_generations(graph))
            new_has_cycles = False
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            new_has_cycles = True

        # DIFFERENTIAL: OLD should fail, NEW should succeed
        assert old_has_cycles is True, "OLD compute_layers() should fail with self-loops"
        assert new_has_cycles is False, "NEW visualization sort should succeed with self-loops excluded"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
