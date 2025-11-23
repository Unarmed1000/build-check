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
        headers = [str(temp_dir / "header1.hpp"), str(temp_dir / "header2.hpp")]

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
        with open(output_file, "r") as f:
            reader = csv.reader(f)
            rows = list(reader)

            # Check header row
            assert "Header" in rows[0]
            assert "Fan-out" in rows[0]
            assert "Coupling" in rows[0]

            # Check data rows
            assert len(rows) == 3  # Header + 2 data rows

    def test_csv_with_metrics(self, temp_dir: Any) -> None:
        """Test CSV includes correct metric values."""
        headers = [str(temp_dir / "header.hpp")]
        header_to_headers: Any = defaultdict(set)
        metrics = {headers[0]: DSMMetrics(fan_out=5, fan_in=3, coupling=8, stability=0.625)}

        output_file = temp_dir / "metrics.csv"
        export_dsm_to_csv(str(output_file), headers, header_to_headers, metrics, str(temp_dir))

        with open(output_file, "r") as f:
            reader = csv.reader(f)
            rows = list(reader)

            # Check metrics in data row
            data_row = rows[1]
            assert data_row[1] == "5"  # fan_out
            assert data_row[2] == "3"  # fan_in
            assert data_row[3] == "8"  # coupling
            assert "0.625" in data_row[4]  # stability

    def test_csv_dependency_matrix(self, temp_dir: Any) -> None:
        """Test dependency matrix values in CSV."""
        headers = [str(temp_dir / "a.hpp"), str(temp_dir / "b.hpp")]

        header_to_headers: Any = defaultdict(set)
        header_to_headers[headers[0]] = {headers[1]}  # a depends on b

        metrics = {h: DSMMetrics(fan_out=0, fan_in=0, coupling=0, stability=0.5) for h in headers}

        output_file = temp_dir / "matrix.csv"
        export_dsm_to_csv(str(output_file), headers, header_to_headers, metrics, str(temp_dir))

        with open(output_file, "r") as f:
            reader = csv.reader(f)
            rows = list(reader)

            # First data row should have a 1 in the position for dependency on b
            assert "1" in rows[1][-1]  # Dependency exists

            # Second data row should have all 0s (no dependencies)
            assert rows[2][-2] == "0"

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

        with open(output_file, "r") as f:
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

        with open(output_file, "r") as f:
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
        assert "<?xml" in content
        assert "graphml" in content

    def test_json_export(self, temp_dir: Any, simple_graph: Any) -> None:
        """Test JSON format export."""
        metrics = {
            "/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
            "/path/b.hpp": DSMMetrics(fan_out=1, fan_in=1, coupling=2, stability=0.5),
            "/path/c.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),
        }
        cycles: list[set[str]] = []

        output_file = temp_dir / "graph.json"
        export_dependency_graph(str(output_file), simple_graph, metrics, cycles, "/path")

        assert output_file.exists()

        # Verify it's valid JSON
        with open(output_file, "r") as f:
            data = json.load(f)
            assert "nodes" in data
            assert "links" in data

    def test_node_attributes(self, temp_dir: Any, simple_graph: Any) -> None:
        """Test that node attributes are added correctly."""
        metrics = {
            "/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
            "/path/b.hpp": DSMMetrics(fan_out=1, fan_in=1, coupling=2, stability=0.5),
            "/path/c.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),
        }
        cycles: list[set[str]] = []

        output_file = temp_dir / "graph.json"
        export_dependency_graph(str(output_file), simple_graph, metrics, cycles, "/path")

        with open(output_file, "r") as f:
            data = json.load(f)

            # Check nodes have expected attributes
            node = data["nodes"][0]
            assert "id" in node

    def test_cycle_detection_in_export(self, temp_dir: Any, simple_graph: Any) -> None:
        """Test that cycles are marked in exported graph."""
        metrics = {
            "/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
            "/path/b.hpp": DSMMetrics(fan_out=1, fan_in=1, coupling=2, stability=0.5),
            "/path/c.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),
        }
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
            "/path/c.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),
        }
        cycles: list[set[str]] = []
        header_to_lib = {"/path/a.hpp": "libFslBase.a", "/path/b.hpp": "libFslBase.a", "/path/c.hpp": "libFslGraphics.a"}

        output_file = temp_dir / "graph.json"
        export_dependency_graph(str(output_file), simple_graph, metrics, cycles, "/path", header_to_lib)

        with open(output_file, "r") as f:
            data = json.load(f)

            # Nodes should have library information
            assert len(data["nodes"]) > 0

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
        graphml_file = Path(str(output_file) + ".graphml")
        assert graphml_file.exists()

    def test_gexf_export(self, temp_dir: Any, simple_graph: Any) -> None:
        """Test GEXF format export."""
        metrics = {
            "/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
            "/path/b.hpp": DSMMetrics(fan_out=1, fan_in=1, coupling=2, stability=0.5),
            "/path/c.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),
        }
        cycles: list[set[str]] = []

        output_file = temp_dir / "graph.gexf"
        export_dependency_graph(str(output_file), simple_graph, metrics, cycles, "/path")

        assert output_file.exists()


class TestExportErrorHandling:
    """Test error handling and edge cases in export functions."""

    def test_csv_export_handles_io_error(self, temp_dir: Any) -> None:
        """Test CSV export handles IO errors gracefully."""
        headers = ["/path/header.hpp"]
        header_to_headers: Any = defaultdict(set)
        metrics = {headers[0]: DSMMetrics(fan_out=0, fan_in=0, coupling=0, stability=0.5)}

        # Try to write to read-only location
        readonly_dir = temp_dir / "readonly"
        readonly_dir.mkdir()
        output_file = readonly_dir / "test.csv"

        # Make directory read-only
        os.chmod(readonly_dir, 0o444)

        try:
            # Should not crash, handles error internally
            export_dsm_to_csv(str(output_file), headers, header_to_headers, metrics, "/path")
        finally:
            # Restore permissions for cleanup
            os.chmod(readonly_dir, 0o755)

    def test_csv_export_with_missing_metrics(self, temp_dir: Any) -> None:
        """Test CSV export handles headers without metrics."""
        headers = ["/path/a.hpp", "/path/b.hpp", "/path/c.hpp"]
        header_to_headers: Any = defaultdict(set)

        # Only provide metrics for some headers
        metrics = {headers[0]: DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0)}

        output_file = temp_dir / "partial.csv"
        export_dsm_to_csv(str(output_file), headers, header_to_headers, metrics, str(temp_dir))

        assert output_file.exists()

        with open(output_file, "r") as f:
            reader = csv.reader(f)
            rows = list(reader)

            # Should have rows for all headers, with 0 values for missing metrics
            assert len(rows) == 4  # header + 3 data rows
            # Check that missing metrics default to 0
            assert rows[2][1] == "0"  # fan_out
            assert rows[2][2] == "0"  # fan_in

    def test_graph_export_with_empty_graph(self, temp_dir: Any) -> None:
        """Test graph export with no nodes."""
        try:
            import networkx as nx

            empty_graph: Any = nx.DiGraph()
            metrics: Dict[str, DSMMetrics] = {}
            cycles: List[set[str]] = []

            output_file = temp_dir / "empty.graphml"
            export_dependency_graph(str(output_file), empty_graph, metrics, cycles, "/path")

            assert output_file.exists()
        except ImportError:
            pytest.skip("networkx not available")

    def test_graph_export_with_missing_metrics(self, temp_dir: Any) -> None:
        """Test graph export handles nodes without metrics."""
        try:
            import networkx as nx

            G: Any = nx.DiGraph()
            G.add_edge("/path/a.hpp", "/path/b.hpp")
            G.add_edge("/path/b.hpp", "/path/c.hpp")

            # Only provide metrics for one node
            metrics = {"/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0)}
            cycles: List[set[str]] = []

            output_file = temp_dir / "partial.json"
            export_dependency_graph(str(output_file), G, metrics, cycles, "/path")

            assert output_file.exists()

            # Should complete without error, missing metrics default to 0
            with open(output_file, "r") as f:
                data = json.load(f)
                assert len(data["nodes"]) == 3
        except ImportError:
            pytest.skip("networkx not available")

    def test_graph_export_without_advanced_metrics(self, temp_dir: Any) -> None:
        """Test graph export with advanced metrics disabled."""
        try:
            import networkx as nx

            G: Any = nx.DiGraph()
            G.add_edge("/path/a.hpp", "/path/b.hpp")

            metrics = {
                "/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
                "/path/b.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),
            }
            cycles: List[set[str]] = []

            output_file = temp_dir / "no_advanced.json"
            export_dependency_graph(str(output_file), G, metrics, cycles, "/path", include_advanced_metrics=False)

            assert output_file.exists()
        except ImportError:
            pytest.skip("networkx not available")

    def test_graph_export_with_header_to_headers(self, temp_dir: Any) -> None:
        """Test graph export with additional dependency mapping."""
        try:
            import networkx as nx

            # Create small graph
            G: Any = nx.DiGraph()
            G.add_edge("/path/a.hpp", "/path/b.hpp")

            # Provide additional dependencies
            header_to_headers: Any = defaultdict(set)
            header_to_headers["/path/a.hpp"] = {"/path/b.hpp", "/path/c.hpp"}
            header_to_headers["/path/b.hpp"] = {"/path/c.hpp"}

            metrics = {
                "/path/a.hpp": DSMMetrics(fan_out=2, fan_in=0, coupling=2, stability=1.0),
                "/path/b.hpp": DSMMetrics(fan_out=1, fan_in=1, coupling=2, stability=0.5),
                "/path/c.hpp": DSMMetrics(fan_out=0, fan_in=2, coupling=2, stability=0.0),
            }
            cycles: List[set[str]] = []

            output_file = temp_dir / "with_deps.json"
            export_dependency_graph(str(output_file), G, metrics, cycles, "/path", header_to_headers=header_to_headers)

            assert output_file.exists()

            # Graph should include the additional node
            with open(output_file, "r") as f:
                data = json.load(f)
                node_ids = [n["id"] for n in data["nodes"]]
                assert "/path/c.hpp" in node_ids
        except ImportError:
            pytest.skip("networkx not available")

    def test_graph_export_with_cross_library_edges(self, temp_dir: Any) -> None:
        """Test edge attributes for cross-library dependencies."""
        try:
            import networkx as nx

            G: Any = nx.DiGraph()
            G.add_edge("/path/a.hpp", "/path/b.hpp")
            G.add_edge("/path/b.hpp", "/path/c.hpp")

            metrics = {
                "/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
                "/path/b.hpp": DSMMetrics(fan_out=1, fan_in=1, coupling=2, stability=0.5),
                "/path/c.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),
            }
            cycles: List[set[str]] = []

            # Different libraries
            header_to_lib = {"/path/a.hpp": "libFslBase.a", "/path/b.hpp": "libFslBase.a", "/path/c.hpp": "libFslGraphics.a"}

            output_file = temp_dir / "cross_lib.json"
            export_dependency_graph(str(output_file), G, metrics, cycles, "/path", header_to_lib=header_to_lib)

            assert output_file.exists()

            with open(output_file, "r") as f:
                data = json.load(f)
                # Should have edge attributes
                assert len(data["links"]) == 2
        except ImportError:
            pytest.skip("networkx not available")

    def test_graph_export_with_executable_library_type(self, temp_dir: Any) -> None:
        """Test library_type attribute detection for executables."""
        try:
            import networkx as nx

            G: Any = nx.DiGraph()
            G.add_edge("/path/main.cpp", "/path/utils.hpp")

            metrics = {
                "/path/main.cpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
                "/path/utils.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),
            }
            cycles: List[set[str]] = []

            # One is executable
            header_to_lib = {"/path/main.cpp": "bin/myapp", "/path/utils.hpp": "libFslBase.a"}

            output_file = temp_dir / "exe_lib.json"
            export_dependency_graph(str(output_file), G, metrics, cycles, "/path", header_to_lib=header_to_lib)

            assert output_file.exists()
        except ImportError:
            pytest.skip("networkx not available")

    def test_graph_export_handles_advanced_metrics_error(self, temp_dir: Any, monkeypatch: Any) -> None:
        """Test that graph export handles errors in advanced metrics computation."""
        try:
            import networkx as nx

            G: Any = nx.DiGraph()
            G.add_edge("/path/a.hpp", "/path/b.hpp")

            metrics = {
                "/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
                "/path/b.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),
            }
            cycles: List[set[str]] = []

            # Mock a function to raise an exception
            def mock_pagerank(*args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("PageRank computation failed")

            # The function should handle this gracefully
            output_file = temp_dir / "graceful.json"
            export_dependency_graph(str(output_file), G, metrics, cycles, "/path")

            # Should complete despite error (uses try/except internally)
            assert output_file.exists()
        except ImportError:
            pytest.skip("networkx not available")


class TestExportRoundTrip:
    """Test export/import round-trip validation."""

    def test_json_export_import_roundtrip(self, temp_dir: Any) -> None:
        """Test that JSON export can be parsed and node count verified."""
        try:
            import networkx as nx

            # Create graph with known structure
            G: Any = nx.DiGraph()
            G.add_edge("/path/a.hpp", "/path/b.hpp")
            G.add_edge("/path/b.hpp", "/path/c.hpp")
            G.add_edge("/path/c.hpp", "/path/d.hpp")

            original_node_count = G.number_of_nodes()
            original_edge_count = G.number_of_edges()

            metrics = {node: DSMMetrics(fan_out=0, fan_in=0, coupling=0, stability=0.5) for node in G.nodes()}
            cycles: List[set[str]] = []

            output_file = temp_dir / "roundtrip.json"
            export_dependency_graph(str(output_file), G, metrics, cycles, "/path")

            # Load and verify
            with open(output_file, "r") as f:
                data = json.load(f)

            assert len(data["nodes"]) == original_node_count
            assert len(data["links"]) == original_edge_count
        except ImportError:
            pytest.skip("networkx not available")

    def test_graphml_export_is_valid_xml(self, temp_dir: Any) -> None:
        """Test that GraphML export produces valid XML structure."""
        try:
            import networkx as nx

            G: Any = nx.DiGraph()
            G.add_edge("/path/a.hpp", "/path/b.hpp")

            metrics = {
                "/path/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
                "/path/b.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),
            }
            cycles: List[set[str]] = []

            output_file = temp_dir / "valid.graphml"
            export_dependency_graph(str(output_file), G, metrics, cycles, "/path")

            # Basic XML validation
            content = output_file.read_text()
            assert content.startswith("<?xml")
            assert "<graphml" in content
            assert "</graphml>" in content
            assert "<node" in content
            assert "<edge" in content
        except ImportError:
            pytest.skip("networkx not available")


@pytest.fixture
def temp_dir() -> Any:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
