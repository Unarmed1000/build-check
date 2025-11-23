#!/usr/bin/env python3
"""DSM-specific test fixtures with multiple complexity levels."""

import pytest
from typing import Dict, Set, List, Any
from collections import defaultdict
import networkx as nx

from lib.dsm_types import DSMAnalysisResults, DSMDelta, MatrixStatistics
from lib.graph_utils import DSMMetrics


@pytest.fixture(scope="module")
def mock_dsm_graph_simple() -> Any:
    """Simple DSM graph with 5 nodes and 1 cycle.

    Structure:
        A -> B -> C -> D -> E
             ^         |
             |_________|
    (D->B creates a cycle: B->C->D->B)
    """
    G: Any = nx.DiGraph()
    nodes = ["A.hpp", "B.hpp", "C.hpp", "D.hpp", "E.hpp"]
    G.add_nodes_from(nodes)

    edges = [("A.hpp", "B.hpp"), ("B.hpp", "C.hpp"), ("C.hpp", "D.hpp"), ("D.hpp", "E.hpp"), ("D.hpp", "B.hpp")]  # Creates cycle
    G.add_edges_from(edges)

    return G


@pytest.fixture(scope="module")
def mock_dsm_graph_medium() -> Any:
    """Medium DSM graph with 20 nodes and 3 cycles.

    Represents a more realistic module structure with:
    - Core layer (5 nodes)
    - Service layer (8 nodes)
    - UI layer (7 nodes)
    - 3 circular dependencies across layers
    """

    G: Any = nx.DiGraph()

    # Core layer
    core = [f"Core{i}.hpp" for i in range(5)]
    # Service layer
    service = [f"Service{i}.hpp" for i in range(8)]
    # UI layer
    ui = [f"UI{i}.hpp" for i in range(7)]

    G.add_nodes_from(core + service + ui)

    # Core layer dependencies
    for i in range(4):
        G.add_edge(core[i], core[i + 1])

    # Service depends on core
    for s in service:
        G.add_edge(s, core[0])
        G.add_edge(s, core[2])

    # UI depends on service
    for u in ui:
        G.add_edge(u, service[0])
        G.add_edge(u, service[3])

    # Add 3 cycles
    G.add_edge("Service1.hpp", "Service3.hpp")
    G.add_edge("Service3.hpp", "Service1.hpp")  # Cycle 1

    G.add_edge("UI2.hpp", "UI4.hpp")
    G.add_edge("UI4.hpp", "UI2.hpp")  # Cycle 2

    G.add_edge("Core3.hpp", "Core1.hpp")  # Cycle 3 (with Core1->Core2->Core3)

    return G


@pytest.fixture(scope="module")
def mock_dsm_graph_complex() -> Any:
    """Complex DSM graph with 100 nodes and 8 cycles.

    Simulates a large project with:
    - 25 foundation headers
    - 35 library headers
    - 40 application headers
    - Multiple circular dependencies
    - Cross-module dependencies
    """

    G: Any = nx.DiGraph()

    # Foundation layer
    foundation = [f"Foundation/Base{i}.hpp" for i in range(25)]
    # Library layer
    library = [f"Library/Lib{i}.hpp" for i in range(35)]
    # Application layer
    application = [f"App/Module{i}.hpp" for i in range(40)]

    all_nodes = foundation + library + application
    G.add_nodes_from(all_nodes)

    # Foundation internal dependencies
    for i in range(len(foundation) - 1):
        G.add_edge(foundation[i], foundation[i + 1])

    # Library depends on foundation
    for lib in library:
        import random

        random.seed(hash(lib))
        deps = random.sample(foundation, k=min(3, len(foundation)))
        for dep in deps:
            G.add_edge(lib, dep)

    # Application depends on library
    for app in application:
        import random

        random.seed(hash(app))
        deps = random.sample(library, k=min(5, len(library)))
        for dep in deps:
            G.add_edge(app, dep)

    # Add 8 cycles at different levels
    cycles_to_add = [
        ("Foundation/Base5.hpp", "Foundation/Base7.hpp", "Foundation/Base5.hpp"),
        ("Library/Lib3.hpp", "Library/Lib8.hpp", "Library/Lib3.hpp"),
        ("Library/Lib12.hpp", "Library/Lib15.hpp", "Library/Lib18.hpp", "Library/Lib12.hpp"),
        ("App/Module5.hpp", "App/Module10.hpp", "App/Module5.hpp"),
        ("App/Module15.hpp", "App/Module20.hpp", "App/Module22.hpp", "App/Module15.hpp"),
        ("Foundation/Base15.hpp", "Foundation/Base18.hpp", "Foundation/Base15.hpp"),
        ("Library/Lib25.hpp", "Library/Lib28.hpp", "Library/Lib25.hpp"),
        ("App/Module30.hpp", "App/Module35.hpp", "App/Module30.hpp"),
    ]

    for cycle in cycles_to_add:
        for i in range(len(cycle) - 1):
            G.add_edge(cycle[i], cycle[i + 1])

    return G


@pytest.fixture
def mock_dsm_metrics_simple(mock_dsm_graph_simple: Any) -> Dict[str, DSMMetrics]:
    """DSM metrics for simple graph."""
    metrics = {}
    for node in mock_dsm_graph_simple.nodes():
        fan_out = mock_dsm_graph_simple.out_degree(node)
        fan_in = mock_dsm_graph_simple.in_degree(node)
        coupling = fan_out + fan_in
        stability = fan_out / coupling if coupling > 0 else 0.0

        metrics[node] = DSMMetrics(fan_out=fan_out, fan_in=fan_in, coupling=coupling, stability=stability)

    return metrics


@pytest.fixture
def mock_dsm_metrics_medium(mock_dsm_graph_medium: Any) -> Dict[str, DSMMetrics]:
    """DSM metrics for medium graph."""
    metrics = {}
    for node in mock_dsm_graph_medium.nodes():
        fan_out = mock_dsm_graph_medium.out_degree(node)
        fan_in = mock_dsm_graph_medium.in_degree(node)
        coupling = fan_out + fan_in
        stability = fan_out / coupling if coupling > 0 else 0.0

        metrics[node] = DSMMetrics(fan_out=fan_out, fan_in=fan_in, coupling=coupling, stability=stability)

    return metrics


@pytest.fixture
def mock_dsm_metrics_complex(mock_dsm_graph_complex: Any) -> Dict[str, DSMMetrics]:
    """DSM metrics for complex graph."""
    metrics = {}
    for node in mock_dsm_graph_complex.nodes():
        fan_out = mock_dsm_graph_complex.out_degree(node)
        fan_in = mock_dsm_graph_complex.in_degree(node)
        coupling = fan_out + fan_in
        stability = fan_out / coupling if coupling > 0 else 0.0

        metrics[node] = DSMMetrics(fan_out=fan_out, fan_in=fan_in, coupling=coupling, stability=stability)

    return metrics


@pytest.fixture
def mock_dsm_analysis_results_simple(mock_dsm_graph_simple: Any, mock_dsm_metrics_simple: Dict[str, DSMMetrics]) -> DSMAnalysisResults:
    """Complete DSM analysis results for simple graph."""

    cycles = [{"B.hpp", "C.hpp", "D.hpp"}]
    headers_in_cycles = set.union(*cycles) if cycles else set()

    # Sort headers by coupling
    sorted_headers = sorted(mock_dsm_metrics_simple.keys(), key=lambda h: mock_dsm_metrics_simple[h].coupling, reverse=True)

    # Build reverse dependencies
    reverse_deps: Dict[str, Set[str]] = defaultdict(set)
    for node in mock_dsm_graph_simple.nodes():
        for successor in mock_dsm_graph_simple.successors(node):
            reverse_deps[successor].add(node)

    # Build forward dependencies
    header_to_headers: Dict[str, Set[str]] = defaultdict(set)
    for node in mock_dsm_graph_simple.nodes():
        header_to_headers[node] = set(mock_dsm_graph_simple.successors(node))

    stats = MatrixStatistics(total_headers=5, total_actual_deps=5, total_possible_deps=20, sparsity=75.0, avg_deps=1.0, health="Good", health_color="\033[32m")

    return DSMAnalysisResults(
        metrics=mock_dsm_metrics_simple,
        cycles=cycles,
        headers_in_cycles=headers_in_cycles,
        feedback_edges=[("D.hpp", "B.hpp")],
        directed_graph=mock_dsm_graph_simple,
        layers=[["E.hpp"], ["A.hpp"], ["B.hpp", "C.hpp", "D.hpp"]],
        header_to_layer={"E.hpp": 0, "A.hpp": 1, "B.hpp": 2, "C.hpp": 2, "D.hpp": 2},
        has_cycles=True,
        stats=stats,
        sorted_headers=sorted_headers,
        reverse_deps=dict(reverse_deps),
        header_to_headers=defaultdict(set, header_to_headers),
    )


@pytest.fixture
def mock_dsm_delta() -> DSMDelta:
    """Mock DSM delta for differential analysis testing."""
    return DSMDelta(
        headers_added={"NewHeader.hpp", "AnotherNew.hpp"},
        headers_removed={"OldHeader.hpp"},
        cycles_added=1,
        cycles_removed=2,
        coupling_increased={"A.hpp": 3, "B.hpp": 5},
        coupling_decreased={"C.hpp": -2, "D.hpp": -1},
        layer_changes={"E.hpp": (2, 3), "F.hpp": (1, 2)},
        new_cycle_participants={"NewHeader.hpp", "A.hpp"},
        resolved_cycle_participants={"OldCycle.hpp", "C.hpp"},
    )


@pytest.fixture(params=["simple", "medium", "complex"])
def mock_dsm_graph_parametrized(request: Any) -> Any:
    """Parametrized fixture providing all complexity levels."""
    if request.param == "simple":
        return request.getfixturevalue("mock_dsm_graph_simple")
    elif request.param == "medium":
        return request.getfixturevalue("mock_dsm_graph_medium")
    else:
        return request.getfixturevalue("mock_dsm_graph_complex")
