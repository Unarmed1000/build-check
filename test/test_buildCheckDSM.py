#!/usr/bin/env python3
# ****************************************************************************************************************************************************
# * BSD 3-Clause License
# *
# * Copyright (c) 2025, Mana Battery
# * All rights reserved.
# *
# * Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
# *
# * 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
# * 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the
# *    documentation and/or other materials provided with the distribution.
# * 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this
# *    software without specific prior written permission.
# *
# * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# * THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# * PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# * LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
# * EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# ****************************************************************************************************************************************************
"""Tests for buildCheckDSM.py and related DSM analysis modules."""
import os
import sys
import tempfile
from pathlib import Path
import pytest
from typing import Any, Dict, List, Tuple, Generator
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.dsm_analysis import calculate_matrix_statistics, print_summary_statistics, run_dsm_analysis
from lib.dsm_types import DSMAnalysisResults
from lib.ninja_utils import validate_build_directory_with_feedback
from lib.graph_utils import calculate_dsm_metrics, build_reverse_dependencies
from lib.color_utils import Colors
from lib.constants import HIGH_COUPLING_THRESHOLD, MODERATE_COUPLING_THRESHOLD, SPARSITY_HEALTHY, SPARSITY_MODERATE

# Import refactored functions from buildCheckDSM
import buildCheckDSM
import argparse


class TestValidateBuildDirectory:
    """Tests for validate_build_directory_with_feedback function."""

    def test_valid_build_directory(self, tmp_path: Any) -> None:
        """Test that a valid build directory passes validation."""
        build_ninja = tmp_path / "build.ninja"
        build_ninja.write_text("# Ninja build file\n")

        # Should not raise an exception
        try:
            build_dir, _ = validate_build_directory_with_feedback(str(tmp_path), verbose=False)
            assert build_dir == str(tmp_path.resolve())
        except (ValueError, RuntimeError):
            pytest.fail("validate_build_directory_with_feedback raised exception for valid directory")

    def test_missing_build_ninja(self, tmp_path: Any, capsys: Any) -> None:
        """Test that missing build.ninja is detected."""
        with pytest.raises(ValueError) as exc_info:
            validate_build_directory_with_feedback(str(tmp_path), verbose=False)
        assert "build.ninja not found" in str(exc_info.value)

    def test_nonexistent_directory(self, tmp_path: Any, capsys: Any) -> None:
        """Test that non-existent directory is rejected."""
        fake_dir = tmp_path / "nonexistent"
        with pytest.raises(ValueError) as exc_info:
            validate_build_directory_with_feedback(str(fake_dir), verbose=False)
        # The function checks for build.ninja existence, so error mentions that
        assert "build.ninja not found" in str(exc_info.value)


class TestCalculateDSMMetrics:
    """Tests for calculate_dsm_metrics function."""

    def test_isolated_header(self) -> None:
        """Test metrics for a header with no dependencies."""
        header = "/path/to/isolated.hpp"
        header_to_headers: defaultdict[str, set[str]] = defaultdict(set)
        reverse_deps: dict[str, set[str]] = {}

        metrics = calculate_dsm_metrics(header, header_to_headers, reverse_deps)

        assert metrics.fan_out == 0
        assert metrics.fan_in == 0
        assert metrics.coupling == 0
        assert metrics.stability == 0.5  # Neutral for isolated

    def test_header_with_dependencies(self) -> None:
        """Test metrics for a header with both forward and reverse dependencies."""
        header = "/path/to/middle.hpp"
        header_to_headers: defaultdict[str, set[str]] = defaultdict(set, {header: {"/path/to/base.hpp", "/path/to/utils.hpp"}})
        reverse_deps = {header: {"/path/to/derived.hpp", "/path/to/consumer.hpp"}}

        metrics = calculate_dsm_metrics(header, header_to_headers, reverse_deps)

        assert metrics.fan_out == 2
        assert metrics.fan_in == 2
        assert metrics.coupling == 4
        assert metrics.stability == 0.5  # Equal dependencies

    def test_stable_header(self) -> None:
        """Test metrics for a stable header (many dependents, few dependencies)."""
        header = "/path/to/stable.hpp"
        header_to_headers: defaultdict[str, set[str]] = defaultdict(set, {header: set()})  # No dependencies
        reverse_deps = {header: {f"/path/to/user{i}.hpp" for i in range(10)}}

        metrics = calculate_dsm_metrics(header, header_to_headers, reverse_deps)

        assert metrics.fan_out == 0
        assert metrics.fan_in == 10
        assert metrics.coupling == 10
        assert metrics.stability == 0.0  # Very stable

    def test_unstable_header(self) -> None:
        """Test metrics for an unstable header (few dependents, many dependencies)."""
        header = "/path/to/unstable.hpp"
        header_to_headers: defaultdict[str, set[str]] = defaultdict(set, {header: {f"/path/to/dep{i}.hpp" for i in range(10)}})
        reverse_deps: dict[str, set[str]] = {header: set()}  # No dependents

        metrics = calculate_dsm_metrics(header, header_to_headers, reverse_deps)

        assert metrics.fan_out == 10
        assert metrics.fan_in == 0
        assert metrics.coupling == 10
        assert metrics.stability == 1.0  # Very unstable


class TestBuildReverseDependencies:
    """Tests for build_reverse_dependencies function."""

    def test_simple_chain(self) -> None:
        """Test reverse dependencies for a simple A -> B -> C chain."""
        header_to_headers = defaultdict(set, {"/a.hpp": {"/b.hpp"}, "/b.hpp": {"/c.hpp"}, "/c.hpp": set()})
        all_headers = {"/a.hpp", "/b.hpp", "/c.hpp"}

        reverse_deps = build_reverse_dependencies(header_to_headers, all_headers)

        assert reverse_deps.get("/b.hpp") == {"/a.hpp"}
        assert reverse_deps.get("/c.hpp") == {"/b.hpp"}
        assert "/a.hpp" not in reverse_deps

    def test_fan_out(self) -> None:
        """Test reverse dependencies with fan-out pattern."""
        header_to_headers = defaultdict(set, {"/hub.hpp": {"/a.hpp", "/b.hpp", "/c.hpp"}, "/a.hpp": set(), "/b.hpp": set(), "/c.hpp": set()})
        all_headers = {"/hub.hpp", "/a.hpp", "/b.hpp", "/c.hpp"}

        reverse_deps = build_reverse_dependencies(header_to_headers, all_headers)

        assert reverse_deps.get("/a.hpp") == {"/hub.hpp"}
        assert reverse_deps.get("/b.hpp") == {"/hub.hpp"}
        assert reverse_deps.get("/c.hpp") == {"/hub.hpp"}
        assert "/hub.hpp" not in reverse_deps


class TestCalculateMatrixStatistics:
    """Tests for calculate_matrix_statistics function."""

    def test_empty_headers(self) -> None:
        """Test statistics for empty header set."""
        all_headers: set[str] = set()
        header_to_headers: defaultdict[str, set[str]] = defaultdict(set)

        stats = calculate_matrix_statistics(all_headers, header_to_headers)

        assert stats.total_headers == 0
        assert stats.total_actual_deps == 0
        assert stats.sparsity == 100.0
        assert stats.avg_deps == 0

    def test_isolated_headers(self) -> None:
        """Test statistics for isolated headers (no dependencies)."""
        all_headers = {f"/header{i}.hpp" for i in range(10)}
        header_to_headers: defaultdict[str, set[str]] = defaultdict(set)

        stats = calculate_matrix_statistics(all_headers, header_to_headers)

        assert stats.total_headers == 10
        assert stats.total_actual_deps == 0
        assert stats.sparsity == 100.0
        assert stats.avg_deps == 0
        assert "Healthy" in stats.health

    def test_fully_connected(self) -> None:
        """Test statistics for fully connected headers."""
        all_headers = {"/a.hpp", "/b.hpp", "/c.hpp"}
        header_to_headers: defaultdict[str, set[str]] = defaultdict(
            set, {"/a.hpp": {"/b.hpp", "/c.hpp"}, "/b.hpp": {"/a.hpp", "/c.hpp"}, "/c.hpp": {"/a.hpp", "/b.hpp"}}
        )

        stats = calculate_matrix_statistics(all_headers, header_to_headers)

        assert stats.total_headers == 3
        assert stats.total_actual_deps == 6
        assert stats.total_possible_deps == 6  # 3 * 2
        assert stats.sparsity == 0.0  # Fully connected
        assert "coupled" in stats.health.lower()

    def test_partially_connected(self) -> None:
        """Test statistics for partially connected headers."""
        all_headers = {f"/header{i}.hpp" for i in range(100)}
        # Only 100 dependencies out of 9900 possible
        header_to_headers: defaultdict[str, set[str]] = defaultdict(set)
        for i in range(100):
            if i < 50:
                header_to_headers[f"/header{i}.hpp"].add(f"/header{i+1}.hpp")

        stats = calculate_matrix_statistics(all_headers, header_to_headers)

        assert stats.total_headers == 100
        assert stats.total_actual_deps == 50
        assert stats.sparsity > SPARSITY_HEALTHY  # Very sparse
        assert "Healthy" in stats.health


class TestConstants:
    """Tests for constants imported from lib.constants."""

    def test_coupling_thresholds(self) -> None:
        """Verify coupling thresholds are in correct order."""
        assert LOW_COUPLING_THRESHOLD < MODERATE_COUPLING_THRESHOLD < HIGH_COUPLING_THRESHOLD

    def test_sparsity_thresholds(self) -> None:
        """Verify sparsity thresholds are in correct order."""
        assert SPARSITY_MODERATE < SPARSITY_HEALTHY

    def test_thresholds_reasonable(self) -> None:
        """Verify thresholds have reasonable values."""
        assert 0 < HIGH_COUPLING_THRESHOLD < 100
        assert 0 < SPARSITY_HEALTHY <= 100


class TestIntegration:
    """Integration tests for full DSM analysis workflow."""

    def test_simple_dependency_analysis(self) -> None:
        """Test complete analysis workflow on simple dependency graph."""
        # Create a simple graph: A -> B -> C, A -> C
        all_headers = {"/a.hpp", "/b.hpp", "/c.hpp"}
        header_to_headers = defaultdict(set, {"/a.hpp": {"/b.hpp", "/c.hpp"}, "/b.hpp": {"/c.hpp"}, "/c.hpp": set()})

        # Build reverse dependencies
        reverse_deps = build_reverse_dependencies(header_to_headers, all_headers)

        # Calculate metrics
        metrics = {}
        for header in all_headers:
            metrics[header] = calculate_dsm_metrics(header, header_to_headers, reverse_deps)

        # Verify metrics
        assert metrics["/a.hpp"].fan_out == 2
        assert metrics["/a.hpp"].fan_in == 0
        assert metrics["/c.hpp"].fan_out == 0
        assert metrics["/c.hpp"].fan_in == 2

        # Calculate statistics
        stats = calculate_matrix_statistics(all_headers, header_to_headers)
        assert stats.total_headers == 3
        assert stats.total_actual_deps == 3

    def test_circular_dependency_detection(self) -> None:
        """Test detection of circular dependencies."""
        # Create a cycle: A -> B -> C -> A
        all_headers = {"/a.hpp", "/b.hpp", "/c.hpp"}
        header_to_headers = defaultdict(set, {"/a.hpp": {"/b.hpp"}, "/b.hpp": {"/c.hpp"}, "/c.hpp": {"/a.hpp"}})

        # Build metrics
        reverse_deps = build_reverse_dependencies(header_to_headers, all_headers)

        # Each header should have exactly 1 fan-in and 1 fan-out
        for header in all_headers:
            metrics = calculate_dsm_metrics(header, header_to_headers, reverse_deps)
            assert metrics.fan_out == 1
            assert metrics.fan_in == 1
            assert metrics.coupling == 2


# Import the actual constant values from the newly created constants module
# This ensures tests stay in sync with actual values
try:
    from lib.constants import LOW_COUPLING_THRESHOLD
except ImportError:
    # Fallback if constant not yet added
    LOW_COUPLING_THRESHOLD = 5


class TestRefactoredFunctions:
    """Tests for refactored buildCheckDSM functions."""

    def test_validate_and_prepare_args_valid(self, tmp_path: Any) -> None:
        """Test validate_and_prepare_args with valid arguments."""
        build_ninja = tmp_path / "build.ninja"
        build_ninja.write_text("# Ninja build file\n")

        args = argparse.Namespace(build_directory=str(tmp_path), top=30)

        build_dir, project_root = buildCheckDSM.validate_and_prepare_args(args)

        assert os.path.isabs(build_dir)
        assert os.path.isabs(project_root)
        assert build_dir == str(tmp_path.resolve())

    def test_validate_and_prepare_args_missing_directory(self) -> None:
        """Test validate_and_prepare_args with missing directory."""
        args = argparse.Namespace(build_directory="", top=30)

        with pytest.raises(ValueError, match="Build directory not specified"):
            buildCheckDSM.validate_and_prepare_args(args)

    def test_validate_and_prepare_args_negative_top(self, tmp_path: Any) -> None:
        """Test validate_and_prepare_args with negative --top value."""
        build_ninja = tmp_path / "build.ninja"
        build_ninja.write_text("# Ninja build file\n")

        args = argparse.Namespace(build_directory=str(tmp_path), top=-5)

        with pytest.raises(ValueError, match="--top must be non-negative"):
            buildCheckDSM.validate_and_prepare_args(args)

    def test_validate_and_prepare_args_nonexistent_build_dir(self, tmp_path: Any) -> None:
        """Test validate_and_prepare_args with non-existent build directory."""
        args = argparse.Namespace(build_directory=str(tmp_path / "nonexistent"), top=30)

        with pytest.raises(ValueError):
            buildCheckDSM.validate_and_prepare_args(args)

    def test_setup_library_mapping_disabled(self) -> None:
        """Test setup_library_mapping when not requested."""
        args = argparse.Namespace(show_library_boundaries=False, library_filter=None, cross_library_only=False)
        all_headers = {"/path/to/header.hpp"}

        result = buildCheckDSM.setup_library_mapping(args, all_headers)

        assert result == {}

    def test_apply_all_filters_no_filters(self) -> None:
        """Test apply_all_filters with no filters applied."""
        args = argparse.Namespace(library_filter=None, filter=None, file_scope="system")
        all_headers = {"/a.hpp", "/b.hpp", "/c.hpp"}
        header_to_lib: dict[str, str] = {}
        project_root = "/project"

        result_headers, stats = buildCheckDSM.apply_all_filters(args, all_headers, header_to_lib, project_root, {})

        assert result_headers == all_headers
        assert stats.initial_count == 3
        assert stats.final_count == 3

    def test_apply_all_filters_empty_result_raises(self) -> None:
        """Test apply_all_filters raises when filtering results in empty set."""
        args = argparse.Namespace(library_filter=None, filter="nonexistent/*")
        all_headers = {"/a.hpp", "/b.hpp"}
        header_to_lib: dict[str, str] = {}
        project_root = "/project"

        # Mock filter_headers_by_pattern to return empty set
        file_types: dict[str, Any] = {}
        original_filter = buildCheckDSM.filter_headers_by_pattern
        buildCheckDSM.filter_headers_by_pattern = lambda *args, **kwargs: set()

        try:
            with pytest.raises(ValueError, match="No headers found after filtering"):
                buildCheckDSM.apply_all_filters(args, all_headers, header_to_lib, project_root, file_types)
        finally:
            buildCheckDSM.filter_headers_by_pattern = original_filter

    def test_dsm_analysis_results_dataclass(self) -> None:
        """Test DSMAnalysisResults dataclass creation."""
        from lib.graph_utils import DSMMetrics
        from lib.dsm_analysis import MatrixStatistics

        metrics = {"/a.hpp": DSMMetrics(fan_out=2, fan_in=1, fan_out_project=2, fan_out_external=0, coupling=3, stability=0.5)}
        cycles = [{"/a.hpp", "/b.hpp"}]
        headers_in_cycles = {"/a.hpp", "/b.hpp"}
        feedback_edges = [("/a.hpp", "/b.hpp")]
        import networkx as nx
        from typing import Any

        directed_graph: nx.DiGraph[Any] = nx.DiGraph()  # Mock graph
        layers = [["/c.hpp"], ["/a.hpp", "/b.hpp"]]
        header_to_layer = {"/c.hpp": 0, "/a.hpp": 1, "/b.hpp": 1}
        has_cycles = True
        stats = MatrixStatistics(
            total_headers=3, total_actual_deps=1, total_possible_deps=6, sparsity=50.0, avg_deps=0.33, health="Healthy", health_color=Colors.GREEN
        )
        sorted_headers = ["/a.hpp", "/b.hpp", "/c.hpp"]
        reverse_deps = {"/b.hpp": {"/a.hpp"}}
        header_to_headers = defaultdict(set, {"/a.hpp": {"/b.hpp"}})

        results = DSMAnalysisResults(
            metrics=metrics,
            cycles=cycles,
            headers_in_cycles=headers_in_cycles,
            feedback_edges=feedback_edges,
            directed_graph=directed_graph,
            layers=layers,
            header_to_layer=header_to_layer,
            has_cycles=has_cycles,
            stats=stats,
            sorted_headers=sorted_headers,
            reverse_deps=reverse_deps,
            header_to_headers=header_to_headers,
        )

        assert results.metrics["/a.hpp"].fan_in == 1
        assert results.metrics["/a.hpp"].coupling == 3
        assert results.cycles == cycles
        assert results.has_cycles is True
        assert len(results.layers) == 2
        assert results.stats.total_headers == 3


class TestRefactoredIntegration:
    """Integration tests for refactored functions working together."""

    def test_run_dsm_analysis_basic(self) -> None:
        """Test run_dsm_analysis with simple graph."""
        all_headers = {"/a.hpp", "/b.hpp", "/c.hpp"}
        header_to_headers = defaultdict(set, {"/a.hpp": {"/b.hpp"}, "/b.hpp": {"/c.hpp"}, "/c.hpp": set()})

        results = run_dsm_analysis(all_headers, header_to_headers, compute_layers=False, show_progress=False)

        assert isinstance(results, DSMAnalysisResults)
        assert len(results.metrics) == 3
        assert len(results.sorted_headers) == 3
        assert results.stats.total_headers == 3
        assert len(results.reverse_deps) > 0

    def test_run_dsm_analysis_with_cycles(self) -> None:
        """Test run_dsm_analysis detects cycles."""
        all_headers = {"/a.hpp", "/b.hpp", "/c.hpp"}
        header_to_headers = defaultdict(set, {"/a.hpp": {"/b.hpp"}, "/b.hpp": {"/c.hpp"}, "/c.hpp": {"/a.hpp"}})  # Creates cycle

        results = run_dsm_analysis(all_headers, header_to_headers, compute_layers=False, show_progress=False)

        assert len(results.cycles) > 0
        assert len(results.headers_in_cycles) == 3
        assert results.has_cycles is True
        assert len(results.feedback_edges) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
