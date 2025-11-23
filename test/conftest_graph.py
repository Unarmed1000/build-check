#!/usr/bin/env python3
"""Graph-specific test fixtures for dependency analysis."""

import pytest
from typing import Dict, Set, List, Any
from collections import defaultdict
import networkx as nx


@pytest.fixture(scope="module")
def sample_dependency_graph_simple() -> Dict[str, Set[str]]:
    """Simple linear dependency chain: A->B->C"""
    return {"A.hpp": {"B.hpp"}, "B.hpp": {"C.hpp"}, "C.hpp": set()}


@pytest.fixture(scope="module")
def sample_dependency_graph_medium() -> Dict[str, Set[str]]:
    """Medium tree structure with 15 nodes.

    Structure:
        Root
        ├── Branch1
        │   ├── Leaf1
        │   ├── Leaf2
        │   └── Leaf3
        ├── Branch2
        │   ├── Leaf4
        │   ├── Leaf5
        │   └── Leaf6
        └── Branch3
            ├── Leaf7
            ├── Leaf8
            └── Leaf9
    """
    return {
        "Root.hpp": {"Branch1.hpp", "Branch2.hpp", "Branch3.hpp"},
        "Branch1.hpp": {"Leaf1.hpp", "Leaf2.hpp", "Leaf3.hpp"},
        "Branch2.hpp": {"Leaf4.hpp", "Leaf5.hpp", "Leaf6.hpp"},
        "Branch3.hpp": {"Leaf7.hpp", "Leaf8.hpp", "Leaf9.hpp"},
        "Leaf1.hpp": set(),
        "Leaf2.hpp": set(),
        "Leaf3.hpp": set(),
        "Leaf4.hpp": set(),
        "Leaf5.hpp": set(),
        "Leaf6.hpp": set(),
        "Leaf7.hpp": set(),
        "Leaf8.hpp": set(),
        "Leaf9.hpp": set(),
    }


@pytest.fixture(scope="module")
def sample_dependency_graph_complex() -> Dict[str, Set[str]]:
    """Complex DAG with 50 nodes and multiple paths."""
    graph: Dict[str, Set[str]] = {}

    # Layer 0: Foundation (10 nodes)
    for i in range(10):
        graph[f"Foundation{i}.hpp"] = set()

    # Layer 1: Core (15 nodes, depends on foundation)
    for i in range(15):
        deps = {f"Foundation{j}.hpp" for j in range(min(3, 10))}
        graph[f"Core{i}.hpp"] = deps

    # Layer 2: Services (15 nodes, depends on core)
    for i in range(15):
        deps = {f"Core{j}.hpp" for j in range(min(4, 15))}
        graph[f"Service{i}.hpp"] = deps

    # Layer 3: Application (10 nodes, depends on services)
    for i in range(10):
        deps = {f"Service{j}.hpp" for j in range(min(5, 15))}
        graph[f"App{i}.hpp"] = deps

    return graph


@pytest.fixture
def mock_cycles_simple() -> List[Set[str]]:
    """Single 3-node cycle."""
    return [{"A.hpp", "B.hpp", "C.hpp"}]


@pytest.fixture
def mock_cycles_complex() -> List[Set[str]]:
    """Multiple nested cycles and SCCs."""
    return [
        {"Core1.hpp", "Core2.hpp", "Core3.hpp"},
        {"Service1.hpp", "Service2.hpp"},
        {"App1.hpp", "App2.hpp", "App3.hpp", "App4.hpp"},
        {"Util1.hpp", "Util2.hpp"},
        {"UI1.hpp", "UI2.hpp", "UI3.hpp"},
    ]


@pytest.fixture
def mock_topological_layers() -> Dict[str, int]:
    """Mock layer assignments for headers."""
    return {
        "Foundation1.hpp": 0,
        "Foundation2.hpp": 0,
        "Core1.hpp": 1,
        "Core2.hpp": 1,
        "Core3.hpp": 1,
        "Service1.hpp": 2,
        "Service2.hpp": 2,
        "App1.hpp": 3,
        "App2.hpp": 3,
    }


@pytest.fixture
def mock_networkx_graph_simple() -> Any:
    """Simple NetworkX graph for testing."""

    G: Any = nx.DiGraph()
    G.add_edges_from([("A.hpp", "B.hpp"), ("B.hpp", "C.hpp"), ("C.hpp", "D.hpp")])
    return G


@pytest.fixture
def mock_networkx_graph_with_cycle() -> Any:
    """NetworkX graph containing a cycle."""

    G: Any = nx.DiGraph()
    G.add_edges_from([("A.hpp", "B.hpp"), ("B.hpp", "C.hpp"), ("C.hpp", "A.hpp"), ("D.hpp", "E.hpp")])  # Creates cycle
    return G


@pytest.fixture(params=["simple", "medium", "complex"])
def sample_dependency_graph_parametrized(request: Any) -> Any:
    """Parametrized fixture for all graph complexity levels."""
    if request.param == "simple":
        return request.getfixturevalue("sample_dependency_graph_simple")
    elif request.param == "medium":
        return request.getfixturevalue("sample_dependency_graph_medium")
    else:
        return request.getfixturevalue("sample_dependency_graph_complex")
