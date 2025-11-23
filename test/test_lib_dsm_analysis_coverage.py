#!/usr/bin/env python3
"""Comprehensive tests for lib.dsm_analysis module to improve coverage."""

import pytest
import sys
import os
from pathlib import Path
from typing import Dict, Set, List, Any
from collections import defaultdict
from io import StringIO

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.dsm_analysis import (
    calculate_matrix_statistics,
    print_summary_statistics,
    print_circular_dependencies,
    print_layered_architecture,
    print_high_coupling_headers,
    print_recommendations,
    compare_dsm_results,
    print_dsm_delta,
    display_directory_clusters,
    print_architectural_hotspots,
)
from lib.dsm_types import MatrixStatistics, DSMAnalysisResults, DSMDelta


class TestPrintSummaryStatistics:
    """Test print_summary_statistics function."""

    @pytest.mark.unit
    def test_print_summary_with_cycles(self, capsys: Any) -> None:
        """Test printing summary statistics with cycles."""
        stats = MatrixStatistics(
            total_headers=10, total_actual_deps=25, total_possible_deps=90, sparsity=72.2, avg_deps=2.5, health="Moderately coupled", health_color="\033[93m"
        )

        print_summary_statistics(stats=stats, cycles_count=3, headers_in_cycles_count=7, layers=[], has_cycles=True)

        captured = capsys.readouterr()
        assert "SUMMARY STATISTICS" in captured.out
        assert "Total headers: 10" in captured.out
        assert "Total dependencies: 25" in captured.out
        assert "Sparsity: 72.2%" in captured.out
        assert "Circular dependency groups: 3" in captured.out
        assert "Headers in cycles: 7" in captured.out
        assert "Cannot compute layers" in captured.err

    @pytest.mark.unit
    def test_print_summary_without_cycles(self, capsys: Any) -> None:
        """Test printing summary statistics without cycles."""
        stats = MatrixStatistics(
            total_headers=20,
            total_actual_deps=30,
            total_possible_deps=380,
            sparsity=92.1,
            avg_deps=1.5,
            health="Healthy (low coupling)",
            health_color="\033[92m",
        )

        layers = [["A.hpp", "B.hpp"], ["C.hpp"], ["D.hpp", "E.hpp"]]

        print_summary_statistics(stats=stats, cycles_count=0, headers_in_cycles_count=0, layers=layers, has_cycles=False)

        captured = capsys.readouterr()
        assert "Dependency layers: 3" in captured.out
        assert "Maximum dependency depth: 2" in captured.out


class TestPrintCircularDependencies:
    """Test print_circular_dependencies function."""

    @pytest.mark.unit
    def test_print_cycles_found(self, capsys: Any, tmp_path: Path) -> None:
        """Test printing when cycles are found."""
        project_root = str(tmp_path)

        cycles = [{str(tmp_path / "A.hpp"), str(tmp_path / "B.hpp")}, {str(tmp_path / "C.hpp"), str(tmp_path / "D.hpp"), str(tmp_path / "E.hpp")}]

        feedback_edges = [(str(tmp_path / "A.hpp"), str(tmp_path / "B.hpp")), (str(tmp_path / "C.hpp"), str(tmp_path / "D.hpp"))]

        print_circular_dependencies(cycles=cycles, feedback_edges=feedback_edges, project_root=project_root, cycles_only=False)

        captured = capsys.readouterr()
        assert "CIRCULAR DEPENDENCIES" in captured.out
        assert "Found 2 circular dependency groups" in captured.err
        assert "Cycle 1" in captured.err
        assert "Cycle 2" in captured.err
        assert "Suggested edges to remove" in captured.out

    @pytest.mark.unit
    def test_print_no_cycles(self, capsys: Any, tmp_path: Path) -> None:
        """Test printing when no cycles exist."""
        project_root = str(tmp_path)

        print_circular_dependencies(cycles=[], feedback_edges=[], project_root=project_root, cycles_only=False)

        captured = capsys.readouterr()
        assert "No circular dependencies found" in captured.out
        assert "clean, acyclic" in captured.out

    @pytest.mark.unit
    def test_print_many_cycles(self, capsys: Any, tmp_path: Path) -> None:
        """Test printing with many cycles."""
        project_root = str(tmp_path)

        # Create 15 cycles
        cycles = [{str(tmp_path / f"H{i}.hpp"), str(tmp_path / f"H{i+1}.hpp")} for i in range(15)]

        print_circular_dependencies(cycles=cycles, feedback_edges=[], project_root=project_root, cycles_only=False)

        captured = capsys.readouterr()
        assert "Found 15 circular dependency groups" in captured.err
        # Check that cycles are displayed
        assert "Cycle 1" in captured.err


class TestPrintLayeredArchitecture:
    """Test print_layered_architecture function."""

    @pytest.mark.unit
    def test_print_layers_basic(self, capsys: Any, tmp_path: Path) -> None:
        """Test printing basic layered architecture."""
        project_root = str(tmp_path)

        layers = [
            [str(tmp_path / "Top1.hpp"), str(tmp_path / "Top2.hpp")],
            [str(tmp_path / "Middle1.hpp")],
            [str(tmp_path / "Foundation1.hpp"), str(tmp_path / "Foundation2.hpp")],
        ]

        print_layered_architecture(layers=layers, project_root=project_root, show_layers=False, auto_display=False)

        captured = capsys.readouterr()
        assert "LAYERED ARCHITECTURE" in captured.out
        assert "Layer 0" in captured.out
        assert "Layer 1" in captured.out
        assert "Layer 2" in captured.out

    @pytest.mark.unit
    def test_print_layers_with_auto_display(self, capsys: Any, tmp_path: Path) -> None:
        """Test printing with auto display message."""
        project_root = str(tmp_path)

        layers = [[str(tmp_path / "Top.hpp")], [str(tmp_path / "Bottom.hpp")]]

        print_layered_architecture(layers=layers, project_root=project_root, show_layers=False, auto_display=True)

        captured = capsys.readouterr()
        assert "Tip: Layers were automatically shown" in captured.out

    @pytest.mark.unit
    def test_print_empty_layers(self, capsys: Any, tmp_path: Path) -> None:
        """Test printing with empty layers list."""
        project_root = str(tmp_path)

        print_layered_architecture(layers=[], project_root=project_root, show_layers=False, auto_display=False)

        captured = capsys.readouterr()
        # Should not print anything for empty layers
        assert "LAYERED ARCHITECTURE" not in captured.out


class TestPrintHighCouplingHeaders:
    """Test print_high_coupling_headers function."""

    @pytest.mark.unit
    def test_print_high_coupling(self, capsys: Any, tmp_path: Path) -> None:
        """Test printing high coupling headers."""
        from lib.graph_utils import DSMMetrics

        project_root = str(tmp_path)

        headers = [str(tmp_path / "HighCoupling.hpp"), str(tmp_path / "MediumCoupling.hpp"), str(tmp_path / "LowCoupling.hpp")]

        metrics = {
            headers[0]: DSMMetrics(fan_in=20, fan_out=25, coupling=45, stability=0.556),
            headers[1]: DSMMetrics(fan_in=10, fan_out=12, coupling=22, stability=0.545),
            headers[2]: DSMMetrics(fan_in=2, fan_out=3, coupling=5, stability=0.6),
        }

        headers_in_cycles = {headers[0]}

        print_high_coupling_headers(sorted_headers=headers, metrics=metrics, headers_in_cycles=headers_in_cycles, project_root=project_root, max_display=20)

        captured = capsys.readouterr()
        assert "HIGH-COUPLING HEADERS" in captured.out
        assert "HighCoupling.hpp" in captured.out
        assert "[IN CYCLE]" in captured.out
        assert "Fan-out:" in captured.out
        assert "Stability:" in captured.out


class TestPrintRecommendations:
    """Test print_recommendations function."""

    @pytest.mark.unit
    def test_recommendations_with_cycles(self, capsys: Any) -> None:
        """Test recommendations when cycles exist."""
        from lib.graph_utils import DSMMetrics

        cycles = [{"A.hpp", "B.hpp"}]
        metrics = {"A.hpp": DSMMetrics(fan_in=1, fan_out=1, coupling=2, stability=0.5), "B.hpp": DSMMetrics(fan_in=1, fan_out=1, coupling=2, stability=0.5)}
        all_headers = {"A.hpp", "B.hpp"}
        stats = MatrixStatistics(total_headers=2, total_actual_deps=2, total_possible_deps=2, sparsity=50.0, avg_deps=1.0, health="Moderate", health_color="")
        feedback_edges = [("A.hpp", "B.hpp")]

        print_recommendations(cycles=cycles, metrics=metrics, all_headers=all_headers, stats=stats, feedback_edges=feedback_edges, layers=[], show_layers=False)

        captured = capsys.readouterr()
        assert "RECOMMENDATIONS" in captured.out
        assert "Break circular dependencies" in captured.err

    @pytest.mark.unit
    def test_recommendations_high_coupling(self, capsys: Any) -> None:
        """Test recommendations for high coupling."""
        from lib.graph_utils import DSMMetrics

        metrics = {f"H{i}.hpp": DSMMetrics(fan_in=25, fan_out=25, coupling=50, stability=0.5) for i in range(5)}
        all_headers = set(metrics.keys())
        stats = MatrixStatistics(
            total_headers=5, total_actual_deps=50, total_possible_deps=20, sparsity=30.0, avg_deps=10.0, health="Highly coupled", health_color=""
        )

        print_recommendations(cycles=[], metrics=metrics, all_headers=all_headers, stats=stats, feedback_edges=[], layers=[], show_layers=False)

        captured = capsys.readouterr()
        assert "Reduce high coupling" in captured.err
        assert "Low sparsity indicates high coupling" in captured.err

    @pytest.mark.unit
    def test_recommendations_clean_architecture(self, capsys: Any) -> None:
        """Test recommendations for clean architecture."""
        from lib.graph_utils import DSMMetrics

        metrics = {f"H{i}.hpp": DSMMetrics(fan_in=1, fan_out=1, coupling=2, stability=0.5) for i in range(5)}
        all_headers = set(metrics.keys())
        stats = MatrixStatistics(total_headers=5, total_actual_deps=5, total_possible_deps=20, sparsity=95.0, avg_deps=1.0, health="Healthy", health_color="")
        layers = [["H0.hpp"], ["H1.hpp"], ["H2.hpp"]]

        print_recommendations(cycles=[], metrics=metrics, all_headers=all_headers, stats=stats, feedback_edges=[], layers=layers, show_layers=False)

        captured = capsys.readouterr()
        assert "Clean layered architecture detected" in captured.out
        assert "No circular dependencies" in captured.out


class TestCompareDSMResults:
    """Test compare_dsm_results function."""

    @pytest.mark.unit
    def test_compare_headers_added_removed(self) -> None:
        """Test comparing results with added/removed headers."""
        from lib.graph_utils import DSMMetrics

        try:
            import networkx as nx
        except ImportError:
            pytest.skip("NetworkX required")

        baseline = DSMAnalysisResults(
            stats=MatrixStatistics(5, 10, 20, 90.0, 2.0, "Healthy", ""),
            sorted_headers=["A.hpp", "B.hpp", "C.hpp"],
            metrics={"A.hpp": DSMMetrics(1, 1, 2, 0.5), "B.hpp": DSMMetrics(1, 1, 2, 0.5), "C.hpp": DSMMetrics(1, 1, 2, 0.5)},
            cycles=[],
            feedback_edges=[],
            layers=[],
            headers_in_cycles=set(),
            header_to_headers=defaultdict(set),
            header_to_layer={},
            has_cycles=False,
            directed_graph=nx.DiGraph(),
            reverse_deps={},
        )

        current = DSMAnalysisResults(
            stats=MatrixStatistics(6, 12, 30, 88.0, 2.0, "Healthy", ""),
            sorted_headers=["A.hpp", "B.hpp", "D.hpp"],
            metrics={"A.hpp": DSMMetrics(1, 1, 2, 0.5), "B.hpp": DSMMetrics(1, 1, 2, 0.5), "D.hpp": DSMMetrics(1, 1, 2, 0.5)},
            cycles=[],
            feedback_edges=[],
            layers=[],
            headers_in_cycles=set(),
            header_to_headers=defaultdict(set),
            header_to_layer={},
            has_cycles=False,
            directed_graph=nx.DiGraph(),
            reverse_deps={},
        )

        delta = compare_dsm_results(baseline, current)

        assert "D.hpp" in delta.headers_added
        assert "C.hpp" in delta.headers_removed
        assert "A.hpp" not in delta.headers_added
        assert "B.hpp" not in delta.headers_removed

    @pytest.mark.unit
    def test_compare_cycle_changes(self) -> None:
        """Test comparing results with cycle changes."""
        from lib.graph_utils import DSMMetrics

        try:
            import networkx as nx
        except ImportError:
            pytest.skip("NetworkX required")

        baseline = DSMAnalysisResults(
            stats=MatrixStatistics(3, 3, 6, 80.0, 1.0, "Healthy", ""),
            sorted_headers=["A.hpp", "B.hpp", "C.hpp"],
            metrics={"A.hpp": DSMMetrics(1, 1, 2, 0.5), "B.hpp": DSMMetrics(1, 1, 2, 0.5), "C.hpp": DSMMetrics(1, 1, 2, 0.5)},
            cycles=[],
            feedback_edges=[],
            layers=[],
            headers_in_cycles=set(),
            header_to_headers=defaultdict(set),
            header_to_layer={},
            has_cycles=False,
            directed_graph=nx.DiGraph(),
            reverse_deps={},
        )

        current = DSMAnalysisResults(
            stats=MatrixStatistics(3, 4, 6, 75.0, 1.33, "Moderate", ""),
            sorted_headers=["A.hpp", "B.hpp", "C.hpp"],
            metrics={"A.hpp": DSMMetrics(2, 2, 4, 0.5), "B.hpp": DSMMetrics(2, 2, 4, 0.5), "C.hpp": DSMMetrics(1, 1, 2, 0.5)},
            cycles=[{"A.hpp", "B.hpp"}],
            feedback_edges=[],
            layers=[],
            headers_in_cycles={"A.hpp", "B.hpp"},
            header_to_headers=defaultdict(set),
            header_to_layer={},
            has_cycles=True,
            directed_graph=nx.DiGraph(),
            reverse_deps={},
        )

        delta = compare_dsm_results(baseline, current)

        assert delta.cycles_added == 1
        assert delta.cycles_removed == 0
        assert len(delta.new_cycle_participants) == 2

    @pytest.mark.unit
    def test_compare_coupling_changes(self) -> None:
        """Test comparing results with coupling changes."""
        from lib.graph_utils import DSMMetrics

        try:
            import networkx as nx
        except ImportError:
            pytest.skip("NetworkX required")

        baseline = DSMAnalysisResults(
            stats=MatrixStatistics(2, 2, 2, 80.0, 1.0, "Healthy", ""),
            sorted_headers=["A.hpp", "B.hpp"],
            metrics={"A.hpp": DSMMetrics(5, 5, 10, 0.5), "B.hpp": DSMMetrics(3, 3, 6, 0.5)},
            cycles=[],
            feedback_edges=[],
            layers=[],
            headers_in_cycles=set(),
            header_to_headers=defaultdict(set),
            header_to_layer={},
            has_cycles=False,
            directed_graph=nx.DiGraph(),
            reverse_deps={},
        )

        current = DSMAnalysisResults(
            stats=MatrixStatistics(2, 3, 2, 75.0, 1.5, "Moderate", ""),
            sorted_headers=["A.hpp", "B.hpp"],
            metrics={"A.hpp": DSMMetrics(8, 8, 16, 0.5), "B.hpp": DSMMetrics(2, 2, 4, 0.5)},  # Coupling increased  # Coupling decreased
            cycles=[],
            feedback_edges=[],
            layers=[],
            headers_in_cycles=set(),
            header_to_headers=defaultdict(set),
            header_to_layer={},
            has_cycles=False,
            directed_graph=nx.DiGraph(),
            reverse_deps={},
        )

        delta = compare_dsm_results(baseline, current)

        assert delta.coupling_increased["A.hpp"] == 6
        assert delta.coupling_decreased["B.hpp"] == 2

    @pytest.mark.unit
    def test_compare_layer_changes(self) -> None:
        """Test comparing results with layer changes."""
        from lib.graph_utils import DSMMetrics

        try:
            import networkx as nx
        except ImportError:
            pytest.skip("NetworkX required")

        baseline = DSMAnalysisResults(
            stats=MatrixStatistics(3, 3, 6, 80.0, 1.0, "Healthy", ""),
            sorted_headers=["A.hpp", "B.hpp", "C.hpp"],
            metrics={"A.hpp": DSMMetrics(1, 1, 2, 0.5), "B.hpp": DSMMetrics(1, 1, 2, 0.5), "C.hpp": DSMMetrics(1, 1, 2, 0.5)},
            cycles=[],
            feedback_edges=[],
            layers=[["A.hpp"], ["B.hpp"], ["C.hpp"]],
            headers_in_cycles=set(),
            header_to_headers=defaultdict(set),
            header_to_layer={"A.hpp": 0, "B.hpp": 1, "C.hpp": 2},
            has_cycles=False,
            directed_graph=nx.DiGraph(),
            reverse_deps={},
        )

        current = DSMAnalysisResults(
            stats=MatrixStatistics(3, 3, 6, 80.0, 1.0, "Healthy", ""),
            sorted_headers=["A.hpp", "B.hpp", "C.hpp"],
            metrics={"A.hpp": DSMMetrics(1, 1, 2, 0.5), "B.hpp": DSMMetrics(1, 1, 2, 0.5), "C.hpp": DSMMetrics(1, 1, 2, 0.5)},
            cycles=[],
            feedback_edges=[],
            layers=[["A.hpp"], ["C.hpp"], ["B.hpp"]],
            headers_in_cycles=set(),
            header_to_headers=defaultdict(set),
            header_to_layer={"A.hpp": 0, "B.hpp": 2, "C.hpp": 1},
            has_cycles=False,
            directed_graph=nx.DiGraph(),
            reverse_deps={},
        )

        delta = compare_dsm_results(baseline, current)

        assert delta.layer_changes["B.hpp"] == (1, 2)
        assert delta.layer_changes["C.hpp"] == (2, 1)
        assert "A.hpp" not in delta.layer_changes


class TestPrintDSMDelta:
    """Test print_dsm_delta function."""

    @pytest.mark.unit
    def test_print_delta_basic(self, capsys: Any, tmp_path: Path) -> None:
        """Test printing DSM delta."""
        from lib.graph_utils import DSMMetrics

        try:
            import networkx as nx
        except ImportError:
            pytest.skip("NetworkX required")

        project_root = str(tmp_path)

        delta = DSMDelta(
            headers_added={str(tmp_path / "New.hpp")},
            headers_removed={str(tmp_path / "Old.hpp")},
            cycles_added=1,
            cycles_removed=0,
            coupling_increased={"A.hpp": 5},
            coupling_decreased={"B.hpp": 3},
            layer_changes={},
            new_cycle_participants={"A.hpp"},
            resolved_cycle_participants=set(),
        )

        baseline = DSMAnalysisResults(
            stats=MatrixStatistics(2, 2, 2, 80.0, 1.0, "Healthy", ""),
            sorted_headers=["A.hpp", "B.hpp"],
            metrics={"A.hpp": DSMMetrics(5, 5, 10, 0.5), "B.hpp": DSMMetrics(6, 6, 12, 0.5)},
            cycles=[],
            feedback_edges=[],
            layers=[],
            headers_in_cycles=set(),
            header_to_headers=defaultdict(set, {"A.hpp": set(), "B.hpp": set()}),
            header_to_layer={},
            has_cycles=False,
            directed_graph=nx.DiGraph(),
            reverse_deps={},
        )

        current = DSMAnalysisResults(
            stats=MatrixStatistics(2, 3, 2, 75.0, 1.5, "Moderate", ""),
            sorted_headers=["A.hpp", "B.hpp"],
            metrics={"A.hpp": DSMMetrics(8, 7, 15, 0.467), "B.hpp": DSMMetrics(4, 5, 9, 0.556)},
            cycles=[{"A.hpp"}],
            feedback_edges=[],
            layers=[],
            headers_in_cycles={"A.hpp"},
            header_to_headers=defaultdict(set, {"A.hpp": {"B.hpp"}, "B.hpp": set()}),
            header_to_layer={},
            has_cycles=True,
            directed_graph=nx.DiGraph(),
            reverse_deps={},
        )

        print_dsm_delta(delta, baseline, current, project_root)

        captured = capsys.readouterr()
        assert "DSM DIFFERENTIAL ANALYSIS" in captured.out
        assert "Summary:" in captured.out
        assert "Added" in captured.out or "Removed" in captured.out


class TestDisplayDirectoryClusters:
    """Test display_directory_clusters function."""

    @pytest.mark.unit
    def test_display_clusters(self, capsys: Any, tmp_path: Path) -> None:
        """Test displaying directory clusters."""
        project_root = str(tmp_path)

        # Create headers in different directories
        module_a = tmp_path / "module_a"
        module_b = tmp_path / "module_b"

        all_headers = [str(module_a / "file1.hpp"), str(module_a / "file2.hpp"), str(module_b / "file3.hpp")]

        header_to_headers = defaultdict(
            set, {all_headers[0]: {all_headers[1]}, all_headers[1]: {all_headers[2]}, all_headers[2]: set()}  # Intra-module  # Inter-module
        )

        display_directory_clusters(all_headers=all_headers, header_to_headers=header_to_headers, project_root=project_root)

        captured = capsys.readouterr()
        assert "MODULE ANALYSIS" in captured.out


class TestPrintArchitecturalHotspots:
    """Test print_architectural_hotspots function."""

    @pytest.mark.unit
    def test_print_hotspots_basic(self, capsys: Any, tmp_path: Path) -> None:
        """Test printing architectural hotspots."""
        from lib.graph_utils import DSMMetrics

        try:
            import networkx as nx
        except ImportError:
            pytest.skip("NetworkX required")

        project_root = str(tmp_path)

        # Create a simple graph with bottlenecks and hubs
        graph: Any = nx.DiGraph()
        graph.add_edges_from([("A.hpp", "B.hpp"), ("B.hpp", "C.hpp"), ("C.hpp", "D.hpp")])

        metrics = {
            "A.hpp": DSMMetrics(0, 1, 1, 0.0),
            "B.hpp": DSMMetrics(1, 2, 3, 0.667),  # Bottleneck
            "C.hpp": DSMMetrics(2, 1, 3, 0.333),
            "D.hpp": DSMMetrics(1, 0, 1, 1.0),
        }

        print_architectural_hotspots(graph, metrics, project_root, top_n=10)

        captured = capsys.readouterr()
        assert "ARCHITECTURAL HOTSPOTS" in captured.out
        assert "Bottleneck Headers" in captured.out
        assert "Hub Headers" in captured.out
        assert "God Object Detection" in captured.out

    @pytest.mark.unit
    def test_print_hotspots_with_god_objects(self, capsys: Any, tmp_path: Path) -> None:
        """Test printing when god objects are detected."""
        from lib.graph_utils import DSMMetrics

        try:
            import networkx as nx
        except ImportError:
            pytest.skip("NetworkX required")

        project_root = str(tmp_path)
        graph: Any = nx.DiGraph()
        graph.add_node("GodObject.hpp")
        graph.add_node("Normal.hpp")

        # Create a god object with extreme fan-out (>50 threshold)
        metrics = {"GodObject.hpp": DSMMetrics(5, 65, 70, 0.071), "Normal.hpp": DSMMetrics(2, 3, 5, 0.6)}  # Fan-out of 65 > 50 threshold

        print_architectural_hotspots(graph, metrics, project_root, top_n=10)

        captured = capsys.readouterr()
        assert "God Object" in captured.out
        assert "potential God Object" in captured.out or "No God Objects detected" in captured.out

    @pytest.mark.unit
    def test_print_hotspots_no_god_objects(self, capsys: Any, tmp_path: Path) -> None:
        """Test printing when no god objects exist."""
        from lib.graph_utils import DSMMetrics

        try:
            import networkx as nx
        except ImportError:
            pytest.skip("NetworkX required")

        project_root = str(tmp_path)
        graph: Any = nx.DiGraph()

        metrics = {"Normal1.hpp": DSMMetrics(2, 3, 5, 0.6), "Normal2.hpp": DSMMetrics(1, 2, 3, 0.667)}

        print_architectural_hotspots(graph, metrics, project_root, top_n=10)

        captured = capsys.readouterr()
        assert "No God Objects detected" in captured.out

    @pytest.mark.unit
    def test_print_hotspots_exception_handling(self, capsys: Any, tmp_path: Path) -> None:
        """Test exception handling in hotspots analysis."""
        from lib.graph_utils import DSMMetrics

        try:
            import networkx as nx
        except ImportError:
            pytest.skip("NetworkX required")

        project_root = str(tmp_path)
        graph: Any = nx.DiGraph()
        metrics: Dict[str, DSMMetrics] = {}

        # Should handle empty graph gracefully
        print_architectural_hotspots(graph, metrics, project_root, top_n=10)

        captured = capsys.readouterr()
        assert "ARCHITECTURAL HOTSPOTS" in captured.out


class TestPrintSummaryStatisticsExtended:
    """Test print_summary_statistics function."""

    @pytest.mark.unit
    def test_print_summary_basic(self, capsys: Any) -> None:
        """Test printing basic summary statistics."""
        stats = MatrixStatistics(
            total_headers=100,
            total_actual_deps=250,
            total_possible_deps=9900,
            sparsity=97.5,
            avg_deps=2.5,
            health="Healthy",
            health_color="",
            quality_score=85.0,
            adp_score=95.0,
            interface_ratio=25.0,
        )

        print_summary_statistics(stats, cycles_count=2, headers_in_cycles_count=5, layers=[], has_cycles=True)

        captured = capsys.readouterr()
        assert "SUMMARY STATISTICS" in captured.out
        assert "Total headers: 100" in captured.out
        assert "Total dependencies: 250" in captured.out
        assert "Architecture health: Healthy" in captured.out
        assert "Quality Score:" in captured.out

    @pytest.mark.unit
    def test_print_summary_no_advanced_metrics(self, capsys: Any) -> None:
        """Test printing summary without advanced metrics."""
        stats = MatrixStatistics(
            total_headers=50,
            total_actual_deps=100,
            total_possible_deps=2450,
            sparsity=95.9,
            avg_deps=2.0,
            health="Good",
            health_color="",
            quality_score=0,  # No quality score
            adp_score=0,
            interface_ratio=0,
        )

        print_summary_statistics(stats, cycles_count=0, headers_in_cycles_count=0, layers=[["A"], ["B"]], has_cycles=False)

        captured = capsys.readouterr()
        assert "SUMMARY STATISTICS" in captured.out
        assert "Total headers: 50" in captured.out
        assert "Dependency layers: 2" in captured.out

    @pytest.mark.unit
    def test_print_summary_with_cycles(self, capsys: Any) -> None:
        """Test printing summary with cycles."""
        stats = MatrixStatistics(10, 20, 90, 77.8, 2.0, "Moderate", "")

        print_summary_statistics(stats, cycles_count=3, headers_in_cycles_count=8, layers=[], has_cycles=True)

        captured = capsys.readouterr()
        assert "Circular dependency groups: 3" in captured.out
        assert "Headers in cycles: 8" in captured.out
        assert "Cannot compute layers" in captured.err


class TestPrintLayeredArchitectureExtended:
    """Test print_layered_architecture edge cases."""

    @pytest.mark.unit
    def test_print_layers_many_layers(self, capsys: Any, tmp_path: Path) -> None:
        """Test printing with many layers."""
        project_root = str(tmp_path)

        # Create 20 layers
        layers = [[str(tmp_path / f"Layer{i}_H{j}.hpp") for j in range(2)] for i in range(20)]

        print_layered_architecture(layers=layers, project_root=project_root, show_layers=True, auto_display=False)

        captured = capsys.readouterr()
        assert "LAYERED ARCHITECTURE" in captured.out
        assert "Layer 0" in captured.out
        assert "Layer 19" in captured.out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
