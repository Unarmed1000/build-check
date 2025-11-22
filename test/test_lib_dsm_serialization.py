#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#****************************************************************************************************************************************************
#* BSD 3-Clause License
#*
#* Copyright (c) 2025, Mana Battery
#* All rights reserved.
#****************************************************************************************************************************************************
"""Tests for lib.dsm_serialization module."""

import os
import sys
import json
import gzip
import tempfile
import socket
from pathlib import Path
from typing import Any, Dict, Set
from collections import defaultdict
from unittest.mock import patch, MagicMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.dsm_serialization import (
    save_dsm_results,
    load_dsm_results,
    _get_git_commit,
    _get_hostname,
    _serialize_dsm_metrics,
    _serialize_matrix_statistics,
    _deserialize_dsm_metrics,
    _deserialize_matrix_statistics,
    SCHEMA_VERSION,
)
from lib.dsm_types import DSMAnalysisResults, MatrixStatistics
from lib.graph_utils import DSMMetrics


class TestHelperFunctions:
    """Test helper functions for metadata collection."""

    def test_get_hostname_success(self) -> None:
        """Test hostname retrieval."""
        hostname = _get_hostname()
        assert isinstance(hostname, str)
        assert len(hostname) > 0

    def test_get_hostname_failure(self) -> None:
        """Test hostname retrieval when socket.gethostname fails."""
        with patch('socket.gethostname', side_effect=Exception("Socket error")):
            hostname = _get_hostname()
            assert hostname == "unknown"

    def test_get_git_commit_success(self) -> None:
        """Test git commit retrieval."""
        commit = _get_git_commit()
        assert isinstance(commit, str)
        # Either valid commit hash (40 chars) or "unknown"
        assert len(commit) > 0

    def test_get_git_commit_no_git(self) -> None:
        """Test git commit retrieval when git is not available."""
        with patch('subprocess.run', side_effect=FileNotFoundError("git not found")):
            commit = _get_git_commit()
            assert commit == "unknown"

    def test_get_git_commit_timeout(self) -> None:
        """Test git commit retrieval with timeout."""
        import subprocess
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("git", 5)):
            commit = _get_git_commit()
            assert commit == "unknown"

    def test_get_git_commit_error(self) -> None:
        """Test git commit retrieval with error return code."""
        mock_result = MagicMock()
        mock_result.returncode = 128
        with patch('subprocess.run', return_value=mock_result):
            commit = _get_git_commit()
            assert commit == "unknown"


class TestSerialization:
    """Test serialization of DSM components."""

    def test_serialize_dsm_metrics(self) -> None:
        """Test DSMMetrics serialization."""
        metrics = DSMMetrics(
            fan_out=5,
            fan_in=3,
            coupling=8,
            stability=0.625
        )
        
        result = _serialize_dsm_metrics(metrics)
        
        assert result == {
            "coupling": 8,
            "fan_in": 3,
            "fan_out": 5,
            "stability": 0.625,
        }
        # Verify keys are sorted
        keys = list(result.keys())
        assert keys == sorted(keys)

    def test_serialize_matrix_statistics(self) -> None:
        """Test MatrixStatistics serialization."""
        stats = MatrixStatistics(
            total_headers=100,
            total_actual_deps=250,
            total_possible_deps=9900,
            sparsity=97.5,
            avg_deps=2.5,
            health="Healthy",
            health_color="green"
        )
        
        result = _serialize_matrix_statistics(stats)
        
        assert result == {
            "avg_deps": 2.5,
            "health": "Healthy",
            "health_color": "green",
            "sparsity": 97.5,
            "total_actual_deps": 250,
            "total_headers": 100,
            "total_possible_deps": 9900,
        }
        # Verify keys are sorted
        keys = list(result.keys())
        assert keys == sorted(keys)

    def test_deserialize_dsm_metrics(self) -> None:
        """Test DSMMetrics deserialization."""
        data = {
            "fan_out": 5,
            "fan_in": 3,
            "coupling": 8,
            "stability": 0.625,
        }
        
        metrics = _deserialize_dsm_metrics(data)
        
        assert metrics.fan_out == 5
        assert metrics.fan_in == 3
        assert metrics.coupling == 8
        assert metrics.stability == 0.625

    def test_deserialize_matrix_statistics(self) -> None:
        """Test MatrixStatistics deserialization."""
        data = {
            "total_headers": 100,
            "total_actual_deps": 250,
            "total_possible_deps": 9900,
            "sparsity": 97.5,
            "avg_deps": 2.5,
            "health": "Healthy",
            "health_color": "green",
        }
        
        stats = _deserialize_matrix_statistics(data)
        
        assert stats.total_headers == 100
        assert stats.total_actual_deps == 250
        assert stats.total_possible_deps == 9900
        assert stats.sparsity == 97.5
        assert stats.avg_deps == 2.5
        assert stats.health == "Healthy"
        assert stats.health_color == "green"


class TestSaveLoadResults:
    """Test save/load functionality for DSMAnalysisResults."""

    @pytest.fixture
    def sample_results(self) -> DSMAnalysisResults:
        """Create sample DSMAnalysisResults for testing."""
        import networkx as nx
        
        # Create simple graph
        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_edge("/project/a.hpp", "/project/b.hpp")
        graph.add_edge("/project/b.hpp", "/project/c.hpp")
        
        metrics = {
            "/project/a.hpp": DSMMetrics(fan_out=1, fan_in=0, coupling=1, stability=1.0),
            "/project/b.hpp": DSMMetrics(fan_out=1, fan_in=1, coupling=2, stability=0.5),
            "/project/c.hpp": DSMMetrics(fan_out=0, fan_in=1, coupling=1, stability=0.0),
        }
        
        stats = MatrixStatistics(
            total_headers=3,
            total_actual_deps=2,
            total_possible_deps=6,
            sparsity=66.7,
            avg_deps=0.67,
            health="Healthy",
            health_color="green"
        )
        
        header_to_headers = defaultdict(set)
        header_to_headers["/project/a.hpp"] = {"/project/b.hpp"}
        header_to_headers["/project/b.hpp"] = {"/project/c.hpp"}
        
        reverse_deps = {
            "/project/b.hpp": {"/project/a.hpp"},
            "/project/c.hpp": {"/project/b.hpp"},
        }
        
        return DSMAnalysisResults(
            metrics=metrics,
            cycles=[],
            headers_in_cycles=set(),
            feedback_edges=[],
            directed_graph=graph,
            layers=[["/project/a.hpp"], ["/project/b.hpp"], ["/project/c.hpp"]],
            header_to_layer={"/project/a.hpp": 0, "/project/b.hpp": 1, "/project/c.hpp": 2},
            has_cycles=False,
            stats=stats,
            sorted_headers=["/project/b.hpp", "/project/a.hpp", "/project/c.hpp"],
            reverse_deps=reverse_deps,
            header_to_headers=header_to_headers,
        )

    def test_save_results_success(self, sample_results: DSMAnalysisResults, tmp_path: Path) -> None:
        """Test successful save of DSM results."""
        output_file = tmp_path / "test.dsm.json.gz"
        build_dir = "/project/build"
        
        save_dsm_results(sample_results, str(output_file), build_dir, "FslBase/*")
        
        assert output_file.exists()
        assert output_file.stat().st_size > 0
        
        # Verify it's gzip compressed
        with gzip.open(output_file, 'rt') as f:
            data = json.load(f)
        
        assert data["_schema_version"] == SCHEMA_VERSION
        assert "_description" in data
        assert data["metadata"]["build_directory"] == os.path.abspath(build_dir)
        assert data["metadata"]["filter_pattern"] == "FslBase/*"
        assert "timestamp" in data["metadata"]
        assert "hostname" in data["metadata"]
        assert "git_commit" in data["metadata"]

    def test_save_results_without_filter(self, sample_results: DSMAnalysisResults, tmp_path: Path) -> None:
        """Test save without filter pattern."""
        output_file = tmp_path / "test.dsm.json.gz"
        build_dir = "/project/build"
        
        save_dsm_results(sample_results, str(output_file), build_dir, None)
        
        with gzip.open(output_file, 'rt') as f:
            data = json.load(f)
        
        assert data["metadata"]["filter_pattern"] == ""

    def test_save_results_deterministic(self, sample_results: DSMAnalysisResults, tmp_path: Path) -> None:
        """Test that saves are deterministic (same content = same file)."""
        file1 = tmp_path / "test1.dsm.json.gz"
        file2 = tmp_path / "test2.dsm.json.gz"
        build_dir = "/project/build"
        
        # Mock timestamp and git commit for determinism
        with patch('lib.dsm_serialization.datetime') as mock_dt, \
             patch('lib.dsm_serialization._get_git_commit', return_value="abc123"), \
             patch('lib.dsm_serialization._get_hostname', return_value="testhost"):
            mock_dt.now.return_value.isoformat.return_value = "2025-01-01T00:00:00"
            
            save_dsm_results(sample_results, str(file1), build_dir)
            save_dsm_results(sample_results, str(file2), build_dir)
        
        # Compare decompressed content (gzip header includes filename, so raw bytes differ)
        with gzip.open(file1, 'rt') as f1:
            content1 = f1.read()
        with gzip.open(file2, 'rt') as f2:
            content2 = f2.read()
        
        assert content1 == content2

    def test_save_results_keys_sorted(self, sample_results: DSMAnalysisResults, tmp_path: Path) -> None:
        """Test that all JSON keys are sorted."""
        output_file = tmp_path / "test.dsm.json.gz"
        
        save_dsm_results(sample_results, str(output_file), "/project/build")
        
        with gzip.open(output_file, 'rt') as f:
            content = f.read()
            data = json.loads(content)
        
        # Check top-level keys are sorted
        top_keys = list(data.keys())
        assert top_keys == sorted(top_keys)
        
        # Check metadata keys are sorted
        meta_keys = list(data["metadata"].keys())
        assert meta_keys == sorted(meta_keys)
        
        # Check metrics keys are sorted
        for header_metrics in data["metrics"].values():
            metric_keys = list(header_metrics.keys())
            assert metric_keys == sorted(metric_keys)

    def test_save_results_collections_sorted(self, sample_results: DSMAnalysisResults, tmp_path: Path) -> None:
        """Test that all collections (lists, sets) are sorted."""
        output_file = tmp_path / "test.dsm.json.gz"
        
        save_dsm_results(sample_results, str(output_file), "/project/build")
        
        with gzip.open(output_file, 'rt') as f:
            data = json.load(f)
        
        # Check sorted_headers
        assert data["sorted_headers"] == sample_results.sorted_headers
        
        # Check headers_in_cycles is sorted
        if data["headers_in_cycles"]:
            assert data["headers_in_cycles"] == sorted(data["headers_in_cycles"])
        
        # Check header_to_headers values are sorted
        for deps in data["header_to_headers"].values():
            assert deps == sorted(deps)

    def test_save_results_io_error(self, sample_results: DSMAnalysisResults) -> None:
        """Test save with IO error."""
        with pytest.raises(IOError):
            save_dsm_results(sample_results, "/invalid/path/test.dsm.json.gz", "/project/build")

    def test_load_results_success(self, sample_results: DSMAnalysisResults, tmp_path: Path) -> None:
        """Test successful load of DSM results."""
        output_file = tmp_path / "test.dsm.json.gz"
        build_dir = os.path.abspath("/project/build")
        
        # Save first
        with patch('lib.dsm_serialization._get_hostname', return_value="testhost"):
            save_dsm_results(sample_results, str(output_file), build_dir)
        
        # Load back
        with patch('lib.dsm_serialization._get_hostname', return_value="testhost"):
            loaded = load_dsm_results(str(output_file), build_dir)
        
        assert len(loaded.metrics) == len(sample_results.metrics)
        assert loaded.has_cycles == sample_results.has_cycles
        assert len(loaded.sorted_headers) == len(sample_results.sorted_headers)
        assert loaded.stats.total_headers == sample_results.stats.total_headers

    def test_load_results_schema_version_mismatch(self, tmp_path: Path) -> None:
        """Test load with mismatched schema version."""
        output_file = tmp_path / "test.dsm.json.gz"
        
        # Create file with wrong schema version
        data = {
            "_schema_version": "0.9",
            "_description": "Test",
            "metadata": {}
        }
        
        with gzip.open(output_file, 'wt') as f:
            json.dump(data, f)
        
        with pytest.raises(ValueError, match="Schema version mismatch"):
            load_dsm_results(str(output_file), "/project/build")

    def test_load_results_build_dir_mismatch(self, sample_results: DSMAnalysisResults, tmp_path: Path) -> None:
        """Test load with mismatched build directory."""
        output_file = tmp_path / "test.dsm.json.gz"
        original_build_dir = os.path.abspath("/project/build")
        different_build_dir = os.path.abspath("/other/build")
        
        # Save with one build dir
        with patch('lib.dsm_serialization._get_hostname', return_value="testhost"):
            save_dsm_results(sample_results, str(output_file), original_build_dir)
        
        # Try to load with different build dir
        with patch('lib.dsm_serialization._get_hostname', return_value="testhost"), \
             pytest.raises(ValueError, match="Baseline must be from the same build directory and system"):
            load_dsm_results(str(output_file), different_build_dir)

    def test_load_results_hostname_mismatch(self, sample_results: DSMAnalysisResults, tmp_path: Path) -> None:
        """Test load with mismatched hostname."""
        output_file = tmp_path / "test.dsm.json.gz"
        build_dir = os.path.abspath("/project/build")
        
        # Save with one hostname
        with patch('lib.dsm_serialization._get_hostname', return_value="host1"):
            save_dsm_results(sample_results, str(output_file), build_dir)
        
        # Try to load with different hostname
        with patch('lib.dsm_serialization._get_hostname', return_value="host2"), \
             pytest.raises(ValueError, match="Baseline must be from the same build directory and system"):
            load_dsm_results(str(output_file), build_dir)

    def test_load_results_error_message_format(self, sample_results: DSMAnalysisResults, tmp_path: Path) -> None:
        """Test that error message shows expected vs actual values."""
        output_file = tmp_path / "test.dsm.json.gz"
        build_dir1 = os.path.abspath("/project/build1")
        build_dir2 = os.path.abspath("/project/build2")
        
        with patch('lib.dsm_serialization._get_hostname', return_value="host1"):
            save_dsm_results(sample_results, str(output_file), build_dir1)
        
        with patch('lib.dsm_serialization._get_hostname', return_value="host2"):
            try:
                load_dsm_results(str(output_file), build_dir2)
                pytest.fail("Should have raised ValueError")
            except ValueError as e:
                error_msg = str(e)
                assert "Expected:" in error_msg
                assert "Got:" in error_msg
                assert build_dir1 in error_msg
                assert build_dir2 in error_msg
                assert "host1" in error_msg
                assert "host2" in error_msg

    def test_load_results_io_error(self) -> None:
        """Test load with missing file."""
        with pytest.raises(IOError):
            load_dsm_results("/nonexistent/file.dsm.json.gz", "/project/build")

    def test_load_results_invalid_json(self, tmp_path: Path) -> None:
        """Test load with invalid JSON."""
        output_file = tmp_path / "invalid.dsm.json.gz"
        
        with gzip.open(output_file, 'wt') as f:
            f.write("not valid json {")
        
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_dsm_results(str(output_file), "/project/build")

    def test_round_trip_with_cycles(self, tmp_path: Path) -> None:
        """Test save/load round trip with cycles."""
        import networkx as nx
        
        # Create graph with cycle
        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_edge("/a.hpp", "/b.hpp")
        graph.add_edge("/b.hpp", "/c.hpp")
        graph.add_edge("/c.hpp", "/a.hpp")
        
        results = DSMAnalysisResults(
            metrics={
                "/a.hpp": DSMMetrics(1, 1, 2, 0.5),
                "/b.hpp": DSMMetrics(1, 1, 2, 0.5),
                "/c.hpp": DSMMetrics(1, 1, 2, 0.5),
            },
            cycles=[{"/a.hpp", "/b.hpp", "/c.hpp"}],
            headers_in_cycles={"/a.hpp", "/b.hpp", "/c.hpp"},
            feedback_edges=[("/c.hpp", "/a.hpp")],
            directed_graph=graph,
            layers=[],
            header_to_layer={},
            has_cycles=True,
            stats=MatrixStatistics(3, 3, 6, 50.0, 1.0, "Moderate", "yellow"),
            sorted_headers=["/a.hpp", "/b.hpp", "/c.hpp"],
            reverse_deps={"/a.hpp": {"/c.hpp"}, "/b.hpp": {"/a.hpp"}, "/c.hpp": {"/b.hpp"}},
            header_to_headers=defaultdict(set, {
                "/a.hpp": {"/b.hpp"},
                "/b.hpp": {"/c.hpp"},
                "/c.hpp": {"/a.hpp"}
            }),
        )
        
        output_file = tmp_path / "cycles.dsm.json.gz"
        build_dir = "/test/build"
        
        with patch('lib.dsm_serialization._get_hostname', return_value="testhost"):
            save_dsm_results(results, str(output_file), build_dir)
            loaded = load_dsm_results(str(output_file), build_dir)
        
        assert loaded.has_cycles
        assert len(loaded.cycles) == 1
        assert len(loaded.headers_in_cycles) == 3
        assert len(loaded.feedback_edges) == 1

    def test_round_trip_preserves_graph_structure(self, sample_results: DSMAnalysisResults, tmp_path: Path) -> None:
        """Test that graph structure is preserved after save/load."""
        output_file = tmp_path / "graph.dsm.json.gz"
        build_dir = "/test/build"
        
        with patch('lib.dsm_serialization._get_hostname', return_value="testhost"):
            save_dsm_results(sample_results, str(output_file), build_dir)
            loaded = load_dsm_results(str(output_file), build_dir)
        
        # Check graph has same nodes and edges
        assert set(loaded.directed_graph.nodes()) == set(sample_results.directed_graph.nodes())
        assert set(loaded.directed_graph.edges()) == set(sample_results.directed_graph.edges())


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_save_load_baseline_comparison_workflow(self, tmp_path: Path) -> None:
        """Test complete workflow: save baseline, modify, load and compare."""
        import networkx as nx
        
        # Create baseline
        baseline_graph: nx.DiGraph[str] = nx.DiGraph()
        baseline_graph.add_edge("/a.hpp", "/b.hpp")
        
        baseline = DSMAnalysisResults(
            metrics={"/a.hpp": DSMMetrics(1, 0, 1, 1.0), "/b.hpp": DSMMetrics(0, 1, 1, 0.0)},
            cycles=[],
            headers_in_cycles=set(),
            feedback_edges=[],
            directed_graph=baseline_graph,
            layers=[["/a.hpp"], ["/b.hpp"]],
            header_to_layer={"/a.hpp": 0, "/b.hpp": 1},
            has_cycles=False,
            stats=MatrixStatistics(2, 1, 2, 50.0, 0.5, "Healthy", "green"),
            sorted_headers=["/a.hpp", "/b.hpp"],
            reverse_deps={"/b.hpp": {"/a.hpp"}},
            header_to_headers=defaultdict(set, {"/a.hpp": {"/b.hpp"}}),
        )
        
        baseline_file = tmp_path / "baseline.dsm.json.gz"
        build_dir = "/test/build"
        
        # Save baseline
        with patch('lib.dsm_serialization._get_hostname', return_value="testhost"):
            save_dsm_results(baseline, str(baseline_file), build_dir)
            
            # Load it back
            loaded = load_dsm_results(str(baseline_file), build_dir)
        
        assert len(loaded.sorted_headers) == 2
        assert not loaded.has_cycles


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
