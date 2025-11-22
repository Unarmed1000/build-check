#!/usr/bin/env python3
"""Tests for lib/export_utils.py"""

import pytest
from typing import Any, Dict, List, Tuple, Generator
import os
import csv
import json
import tempfile
from pathlib import Path
from collections import defaultdict

from lib.export_utils import export_dsm_to_csv, export_dependency_graph
from lib.graph_utils import DSMMetrics


class TestExportDsmToCsv:
    """Tests for export_dsm_to_csv function."""
    
    def test_basic_csv_export(self, temp_dir: Any) -> None:
        """Test basic CSV export functionality."""
        headers = [
            str(temp_dir / "header1.hpp"),
            str(temp_dir / "header2.hpp"),
        ]
        
        header_to_headers = defaultdict(set)
        header_to_headers[headers[0]] = {headers[1]}
        
        metrics = {
            headers[0]: DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
            headers[1]: DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),
        }
        
        output_file = temp_dir / "test.csv"
        export_dsm_to_csv(str(output_file), headers, header_to_headers, metrics, str(temp_dir))
        
        assert output_file.exists()
        
        # Read and verify CSV content
        with open(output_file, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
            
            # Check header row
            assert 'Header' in rows[0]
            assert 'Fan-out' in rows[0]
            assert 'Coupling' in rows[0]
            
            # Check data rows
            assert len(rows) == 3  # Header + 2 data rows
    
    def test_csv_with_metrics(self, temp_dir: Any) -> None:
        """Test CSV includes correct metric values."""
        headers = [str(temp_dir / "header.hpp")]
        header_to_headers: Any = defaultdict(set)
        metrics = {
            headers[0]: DSMMetrics(fan_out=5, fan_in=3, coupling=8, stability=0.625),
        }
        
        output_file = temp_dir / "metrics.csv"
        export_dsm_to_csv(str(output_file), headers, header_to_headers, metrics, str(temp_dir))
        
        with open(output_file, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
            
            # Check metrics in data row
            data_row = rows[1]
            assert data_row[1] == '5'  # fan_out
            assert data_row[2] == '3'  # fan_in
            assert data_row[3] == '8'  # coupling
            assert '0.625' in data_row[4]  # stability
    
    def test_csv_dependency_matrix(self, temp_dir: Any) -> None:
        """Test dependency matrix values in CSV."""
        headers = [
            str(temp_dir / "a.hpp"),
            str(temp_dir / "b.hpp"),
        ]
        
        header_to_headers: Any = defaultdict(set)
        header_to_headers[headers[0]] = {headers[1]}  # a depends on b
        
        metrics = {h: DSMMetrics(fan_out=0, fan_in=0, coupling=0, stability=0.5) for h in headers}
        
        output_file = temp_dir / "matrix.csv"
        export_dsm_to_csv(str(output_file), headers, header_to_headers, metrics, str(temp_dir))
        
        with open(output_file, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
            
            # First data row should have a 1 in the position for dependency on b
            assert '1' in rows[1][-1]  # Dependency exists
            
            # Second data row should have all 0s (no dependencies)
            assert rows[2][-2] == '0'
    
    def test_empty_headers_list(self, temp_dir: Any) -> None:
        """Test export with empty headers."""
        output_file = temp_dir / "empty.csv"
        header_to_headers: Any = defaultdict(set)
        export_dsm_to_csv(str(output_file), [], header_to_headers, {}, str(temp_dir))
        
        assert output_file.exists()
    
    def test_large_matrix(self, temp_dir: Any) -> None:
        """Test export with many headers."""
        num_headers = 50
        headers = [str(temp_dir / f"header{i}.hpp") for i in range(num_headers)]
        
        header_to_headers: Any = defaultdict(set)
        metrics = {h: DSMMetrics(fan_out=0, fan_in=0, coupling=0, stability=0.5) for h in headers}
        
        output_file = temp_dir / "large.csv"
        export_dsm_to_csv(str(output_file), headers, header_to_headers, metrics, str(temp_dir))
        
        assert output_file.exists()
        
        with open(output_file, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
            
            # Should have header + num_headers data rows
            assert len(rows) == num_headers + 1
    
    def test_relative_path_conversion(self, temp_dir: Any) -> None:
        """Test that absolute paths are converted to relative."""
        headers = [str(temp_dir / "module" / "header.hpp")]
        header_to_headers: Any = defaultdict(set)
        metrics = {headers[0]: DSMMetrics(fan_out=0, fan_in=0, coupling=0, stability=0.5)}
        
        output_file = temp_dir / "paths.csv"
        export_dsm_to_csv(str(output_file), headers, header_to_headers, metrics, str(temp_dir))
        
        with open(output_file, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
            
            # Path should be relative, not absolute
            assert str(temp_dir) not in rows[1][0]
            assert "module" in rows[1][0]


class TestExportDependencyGraph:
    """Tests for export_dependency_graph function."""
    
    @pytest.fixture
    def simple_graph(self: Any) -> Any:
        """Create a simple test graph."""
        try:
            import networkx as nx
            G: Any = nx.DiGraph()
            G.add_edge("/path/a.hpp", "/path/b.hpp")
            G.add_edge("/path/b.hpp", "/path/c.hpp")
            return G
        except ImportError:
            pytest.skip("networkx not available")
    
    def test_graphml_export(self, temp_dir: Any, simple_graph: Any) -> None:
        """Test GraphML format export."""
        metrics = {
            "/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
            "/path/b.hpp": DSMMetrics(fan_out=1, fan_in=1, coupling=2, stability=0.5),
            "/path/c.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),
        }
        cycles: list[set[str]] = []
        
        output_file = temp_dir / "graph.graphml"
        export_dependency_graph(str(output_file), simple_graph, metrics, cycles, "/path")
        
        assert output_file.exists()
        
        # Verify it's valid XML
        content = output_file.read_text()
        assert '<?xml' in content
        assert 'graphml' in content
    
    def test_json_export(self, temp_dir: Any, simple_graph: Any) -> None:
        """Test JSON format export."""
        metrics = {
            "/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
            "/path/b.hpp": DSMMetrics(fan_out=1, fan_in=1, coupling=2, stability=0.5),
            "/path/c.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),        }
        cycles: list[set[str]] = []
        
        output_file = temp_dir / "graph.json"
        export_dependency_graph(str(output_file), simple_graph, metrics, cycles, "/path")
        
        assert output_file.exists()
        
        # Verify it's valid JSON
        with open(output_file, 'r') as f:
            data = json.load(f)
            assert 'nodes' in data
            assert 'links' in data
    
    def test_node_attributes(self, temp_dir: Any, simple_graph: Any) -> None:
        """Test that node attributes are added correctly."""
        metrics = {
            "/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
            "/path/b.hpp": DSMMetrics(fan_out=1, fan_in=1, coupling=2, stability=0.5),
            "/path/c.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),        }
        cycles: list[set[str]] = []
        
        output_file = temp_dir / "graph.json"
        export_dependency_graph(str(output_file), simple_graph, metrics, cycles, "/path")
        
        with open(output_file, 'r') as f:
            data = json.load(f)
            
            # Check nodes have expected attributes
            node = data['nodes'][0]
            assert 'id' in node
    
    def test_cycle_detection_in_export(self, temp_dir: Any, simple_graph: Any) -> None:
        """Test that cycles are marked in exported graph."""
        metrics = {
            "/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
            "/path/b.hpp": DSMMetrics(fan_out=1, fan_in=1, coupling=2, stability=0.5),
            "/path/c.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),        }
        cycles: list[set[str]] = [{"/path/a.hpp", "/path/b.hpp"}]
        
        output_file = temp_dir / "graph.json"
        export_dependency_graph(str(output_file), simple_graph, metrics, cycles, "/path")
        
        # Should complete without error
        assert output_file.exists()
    
    def test_library_attributes(self, temp_dir: Any, simple_graph: Any) -> None:
        """Test library grouping attributes."""
        metrics = {
            "/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
            "/path/b.hpp": DSMMetrics(fan_out=1, fan_in=1, coupling=2, stability=0.5),
            "/path/c.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),        }
        cycles: list[set[str]] = []
        header_to_lib = {
            "/path/a.hpp": "libFslBase.a",
            "/path/b.hpp": "libFslBase.a",
            "/path/c.hpp": "libFslGraphics.a",
        }
        
        output_file = temp_dir / "graph.json"
        export_dependency_graph(str(output_file), simple_graph, metrics, cycles, "/path", header_to_lib)
        
        with open(output_file, 'r') as f:
            data = json.load(f)
            
            # Nodes should have library information
            assert len(data['nodes']) > 0
    
    def test_unsupported_format_fallback(self, temp_dir: Any, simple_graph: Any) -> None:
        """Test fallback to GraphML for unsupported format."""
        metrics = {
            "/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
            "/path/b.hpp": DSMMetrics(fan_out=1, fan_in=1, coupling=2, stability=0.5),
            "/path/c.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),
        }
        cycles: list[set[str]] = []
        
        output_file = temp_dir / "graph.unknown"
        export_dependency_graph(str(output_file), simple_graph, metrics, cycles, "/path")
        
        # Should create .graphml file for unsupported formats
        graphml_file = Path(str(output_file) + '.graphml')
        assert graphml_file.exists()
    
    def test_gexf_export(self, temp_dir: Any, simple_graph: Any) -> None:
        """Test GEXF format export."""
        metrics = {
            "/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
            "/path/b.hpp": DSMMetrics(fan_out=1, fan_in=1, coupling=2, stability=0.5),
            "/path/c.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),        }
        cycles: list[set[str]] = []
        
        output_file = temp_dir / "graph.gexf"
        export_dependency_graph(str(output_file), simple_graph, metrics, cycles, "/path")
        
        assert output_file.exists()


@pytest.fixture
def temp_dir() -> Any:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
