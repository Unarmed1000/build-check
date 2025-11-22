#!/usr/bin/env python3
"""Extended tests for lib.dsm_analysis module focusing on coverage."""

import pytest
import sys
from pathlib import Path
from typing import Dict, Set, Any
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.dsm_analysis import (
    calculate_matrix_statistics,
    run_dsm_analysis,
)
from lib.dsm_types import MatrixStatistics


class TestDSMAnalysisIntegration:
    """Integration tests for DSM analysis functions."""
    
    @pytest.mark.integration
    def test_run_dsm_analysis_simple_graph(self, mock_dsm_graph_simple: Any) -> None:
        """Test running full DSM analysis on simple graph."""
        try:
            import networkx as nx
            
            # Create a simple dependency graph
            graph_dict = {
                'A.hpp': set(),
                'B.hpp': {'A.hpp'},
                'C.hpp': {'B.hpp'},
                'D.hpp': {'A.hpp'},
                'E.hpp': {'B.hpp', 'D.hpp'}
            }
            
            results = run_dsm_analysis(
                all_headers=set(graph_dict.keys()),
                header_to_headers=defaultdict(set, graph_dict),
                compute_layers=True,
                show_progress=False
            )
            
            assert results is not None
            assert results.stats.total_headers == 5
            assert len(results.metrics) == 5
            assert results.has_cycles == False
            
        except ImportError:
            pytest.skip("NetworkX required for DSM analysis")
    
    @pytest.mark.integration
    def test_run_dsm_analysis_with_cycles(self) -> None:
        """Test DSM analysis with circular dependencies."""
        try:
            import networkx as nx
            
            # Create a graph with a cycle
            graph_dict = {
                'A.hpp': {'B.hpp'},
                'B.hpp': {'C.hpp'},
                'C.hpp': {'A.hpp'},
                'D.hpp': set()
            }
            
            results = run_dsm_analysis(
                all_headers=set(graph_dict.keys()),
                header_to_headers=defaultdict(set, graph_dict),
                compute_layers=True,
                show_progress=False
            )
            
            assert results is not None
            assert results.has_cycles == True
            assert len(results.cycles) > 0
            assert len(results.headers_in_cycles) == 3
            
        except ImportError:
            pytest.skip("NetworkX required for DSM analysis")
    
    @pytest.mark.integration
    def test_run_dsm_analysis_complex_graph(self, mock_dsm_graph_medium: Any) -> None:
        """Test DSM analysis on medium complexity graph."""
        try:
            import networkx as nx
            
            # Create a more complex graph
            graph_dict: Dict[str, Set[str]] = {}
            # Foundation layer
            for i in range(5):
                graph_dict[f'Foundation{i}.hpp'] = set()
            
            # Middle layer depends on foundation
            for i in range(5):
                graph_dict[f'Middle{i}.hpp'] = {f'Foundation{j}.hpp' for j in range(2)}
            
            # Top layer depends on middle
            for i in range(5):
                graph_dict[f'Top{i}.hpp'] = {f'Middle{j}.hpp' for j in range(2)}
            
            results = run_dsm_analysis(
                all_headers=set(graph_dict.keys()),
                header_to_headers=defaultdict(set, graph_dict),
                compute_layers=True,
                show_progress=False
            )
            
            assert results is not None
            assert results.stats.total_headers == 15
            assert results.has_cycles == False
            assert len(results.layers) == 3  # Should have 3 layers
            
        except ImportError:
            pytest.skip("NetworkX required for DSM analysis")


class TestCalculateMatrixStatistics:
    """Test calculate_matrix_statistics with various scenarios."""
    
    @pytest.mark.unit
    def test_very_sparse_matrix(self) -> None:
        """Test statistics for very sparse graph."""
        headers = set([f'H{i}.hpp' for i in range(100)])
        deps: Dict[str, Set[str]] = {h: set() for h in headers}
        # Add just a few dependencies
        deps['H0.hpp'] = {'H1.hpp', 'H2.hpp'}
        deps['H50.hpp'] = {'H51.hpp'}
        
        stats = calculate_matrix_statistics(headers, deps)
        
        assert stats.total_headers == 100
        assert stats.total_actual_deps == 3
        assert stats.sparsity > 99.0  # Very sparse
        assert "Healthy" in stats.health
    
    @pytest.mark.unit
    def test_moderate_coupling(self) -> None:
        """Test statistics for moderately coupled graph."""
        headers = set([f'H{i}.hpp' for i in range(20)])
        deps: Dict[str, Set[str]] = {h: set() for h in headers}
        
        # Create moderate coupling
        for i in range(10):
            deps[f'H{i}.hpp'] = {f'H{j}.hpp' for j in range(10, 15)}
        
        stats = calculate_matrix_statistics(headers, deps)
        
        assert stats.total_headers == 20
        assert 50 <= stats.sparsity <= 95  # Moderate range
    
    @pytest.mark.unit
    def test_high_coupling(self) -> None:
        """Test statistics for highly coupled graph."""
        headers = {'A.hpp', 'B.hpp', 'C.hpp', 'D.hpp'}
        deps = {
            'A.hpp': {'B.hpp', 'C.hpp', 'D.hpp'},
            'B.hpp': {'A.hpp', 'C.hpp', 'D.hpp'},
            'C.hpp': {'A.hpp', 'B.hpp', 'D.hpp'},
            'D.hpp': {'A.hpp', 'B.hpp', 'C.hpp'}
        }
        
        stats = calculate_matrix_statistics(headers, deps)
        
        assert stats.total_headers == 4
        assert stats.sparsity < 50  # Highly coupled
        assert "coupled" in stats.health.lower()
    
    @pytest.mark.unit
    def test_linear_chain(self) -> None:
        """Test statistics for linear dependency chain."""
        headers = set([f'H{i}.hpp' for i in range(10)])
        deps = {f'H{i}.hpp': {f'H{i-1}.hpp'} if i > 0 else set() for i in range(10)}
        
        stats = calculate_matrix_statistics(headers, deps)
        
        assert stats.total_headers == 10
        assert stats.total_actual_deps == 9  # 9 edges in chain
        assert stats.avg_deps == 0.9  # 9 deps / 10 headers
    
    @pytest.mark.unit
    def test_star_topology(self) -> None:
        """Test statistics for star topology (one central header)."""
        headers = set(['Center.hpp'] + [f'Spoke{i}.hpp' for i in range(10)])
        deps: Dict[str, Set[str]] = {'Center.hpp': set()}
        for i in range(10):
            deps[f'Spoke{i}.hpp'] = {'Center.hpp'}
        
        stats = calculate_matrix_statistics(headers, deps)
        
        assert stats.total_headers == 11
        assert stats.total_actual_deps == 10  # 10 spokes point to center
        # High sparsity because most pairs don't have dependencies
        assert stats.sparsity > 90


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
