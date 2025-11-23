#!/usr/bin/env python3
"""Demo test showing fixture usage with multiple complexity levels."""

import pytest
from typing import Any, Dict, Set


@pytest.mark.unit
def test_dsm_graph_simple(mock_dsm_graph_simple: Any) -> None:
    """Test simple DSM graph fixture."""
    assert mock_dsm_graph_simple.number_of_nodes() == 5
    assert mock_dsm_graph_simple.number_of_edges() == 5


@pytest.mark.unit
def test_dsm_graph_medium(mock_dsm_graph_medium: Any) -> None:
    """Test medium DSM graph fixture."""
    assert mock_dsm_graph_medium.number_of_nodes() == 20
    assert mock_dsm_graph_medium.number_of_edges() > 20


@pytest.mark.unit
@pytest.mark.parametrized
def test_dsm_graph_parametrized(mock_dsm_graph_parametrized: Any) -> None:
    """Test runs 3 times with different complexity levels."""
    # This test runs 3 times: simple, medium, complex
    assert mock_dsm_graph_parametrized.number_of_nodes() > 0
    assert mock_dsm_graph_parametrized.number_of_edges() >= 0


@pytest.mark.unit
def test_library_mapping_simple(mock_library_mapping_simple: Dict[str, str]) -> None:
    """Test simple library mapping fixture."""
    assert len(mock_library_mapping_simple) == 10
    assert "libCore.a" in mock_library_mapping_simple.values()


@pytest.mark.unit
def test_dependency_graph_simple(sample_dependency_graph_simple: Dict[str, Set[str]]) -> None:
    """Test simple dependency graph fixture."""
    assert len(sample_dependency_graph_simple) == 3
    assert "A.hpp" in sample_dependency_graph_simple
