#!/usr/bin/env python3
"""Tests for new DSM metrics and improvements."""
import pytest
from typing import Dict
from collections import defaultdict

# Add parent directory to path for imports
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.graph_utils import (
    DSMMetrics,
    calculate_architecture_quality_score,
    calculate_adp_score,
    detect_god_objects,
    calculate_interface_implementation_ratio,
    detect_coupling_outliers,
)
from lib.dsm_analysis import calculate_matrix_statistics
from lib.dsm_types import MatrixStatistics


class TestArchitectureQualityScore:
    """Tests for architecture quality score calculation."""

    def test_perfect_score(self) -> None:
        """Test perfect architecture (high sparsity, no cycles, good coupling)."""
        score = calculate_architecture_quality_score(
            sparsity=98.0, num_cycles=0, total_headers=100, coupling_p95=5.0, coupling_p99=8.0, num_stable_interfaces=40
        )

        # Should be near perfect (95-100)
        assert score >= 90.0, f"Expected score >= 90, got {score}"
        assert score <= 100.0

    def test_poor_score(self) -> None:
        """Test poor architecture (low sparsity, many cycles, high coupling)."""
        score = calculate_architecture_quality_score(
            sparsity=70.0, num_cycles=20, total_headers=100, coupling_p95=30.0, coupling_p99=50.0, num_stable_interfaces=5
        )

        # Should be low (< 40)
        assert score < 40.0, f"Expected score < 40, got {score}"
        assert score >= 0.0

    def test_moderate_score(self) -> None:
        """Test moderate architecture (middle ground)."""
        score = calculate_architecture_quality_score(
            sparsity=92.0, num_cycles=5, total_headers=100, coupling_p95=12.0, coupling_p99=20.0, num_stable_interfaces=20
        )

        # Should be moderate (40-80)
        assert 40.0 <= score <= 80.0, f"Expected 40 <= score <= 80, got {score}"

    def test_without_optional_params(self) -> None:
        """Test score calculation with minimal parameters."""
        score = calculate_architecture_quality_score(sparsity=95.0, num_cycles=0, total_headers=100)

        # Should still compute (defaults to neutral scoring)
        assert 0.0 <= score <= 100.0


class TestADPScore:
    """Tests for Acyclic Dependencies Principle score."""

    def test_no_cycles(self) -> None:
        """Test perfect ADP compliance (no cycles)."""
        score = calculate_adp_score(total_headers=100, headers_in_cycles=0)
        assert score == 100.0

    def test_all_in_cycles(self) -> None:
        """Test zero ADP compliance (all in cycles)."""
        score = calculate_adp_score(total_headers=100, headers_in_cycles=100)
        assert score == 0.0

    def test_partial_cycles(self) -> None:
        """Test partial ADP compliance."""
        score = calculate_adp_score(total_headers=100, headers_in_cycles=20)
        assert score == 80.0

    def test_empty_project(self) -> None:
        """Test empty project."""
        score = calculate_adp_score(total_headers=0, headers_in_cycles=0)
        assert score == 100.0


class TestGodObjectDetection:
    """Tests for God Object anti-pattern detection."""

    def test_no_god_objects(self) -> None:
        """Test project with no God Objects."""
        metrics = {
            "/a.hpp": DSMMetrics(fan_out=10, fan_in=5, fan_out_project=10, fan_out_external=0, coupling=15, stability=0.67),
            "/b.hpp": DSMMetrics(fan_out=20, fan_in=10, fan_out_project=20, fan_out_external=0, coupling=30, stability=0.67),
            "/c.hpp": DSMMetrics(fan_out=30, fan_in=15, fan_out_project=30, fan_out_external=0, coupling=45, stability=0.67),
        }

        god_objects = detect_god_objects(metrics, threshold=50)
        assert len(god_objects) == 0

    def test_with_god_objects(self) -> None:
        """Test detection of God Objects."""
        metrics = {
            "/a.hpp": DSMMetrics(fan_out=10, fan_in=5, fan_out_project=10, fan_out_external=0, coupling=15, stability=0.67),
            "/god.hpp": DSMMetrics(fan_out=100, fan_in=20, fan_out_project=100, fan_out_external=0, coupling=120, stability=0.83),
            "/mega_god.hpp": DSMMetrics(fan_out=200, fan_in=10, fan_out_project=200, fan_out_external=0, coupling=210, stability=0.95),
        }

        god_objects = detect_god_objects(metrics, threshold=50)

        assert len(god_objects) == 2
        # Should be sorted by fan_out descending
        assert god_objects[0][0] == "/mega_god.hpp"
        assert god_objects[0][1] == 200
        assert god_objects[1][0] == "/god.hpp"
        assert god_objects[1][1] == 100

    def test_custom_threshold(self) -> None:
        """Test custom threshold."""
        metrics = {
            "/a.hpp": DSMMetrics(fan_out=60, fan_in=5, fan_out_project=60, fan_out_external=0, coupling=65, stability=0.92),
            "/b.hpp": DSMMetrics(fan_out=40, fan_in=10, fan_out_project=40, fan_out_external=0, coupling=50, stability=0.80),
        }

        # With threshold=50, both qualify
        god_objects = detect_god_objects(metrics, threshold=50)
        assert len(god_objects) == 1
        assert god_objects[0][0] == "/a.hpp"


class TestInterfaceImplementationRatio:
    """Tests for interface/implementation ratio calculation."""

    def test_all_interfaces(self) -> None:
        """Test project with all stable interfaces."""
        metrics = {
            "/a.hpp": DSMMetrics(fan_out=1, fan_in=10, fan_out_project=1, fan_out_external=0, coupling=11, stability=0.09),
            "/b.hpp": DSMMetrics(fan_out=2, fan_in=20, fan_out_project=2, fan_out_external=0, coupling=22, stability=0.09),
            "/c.hpp": DSMMetrics(fan_out=0, fan_in=30, fan_out_project=0, fan_out_external=0, coupling=30, stability=0.0),
        }

        ratio, num_interfaces, total = calculate_interface_implementation_ratio(metrics, stability_threshold=0.3)

        assert ratio == 100.0
        assert num_interfaces == 3
        assert total == 3

    def test_no_interfaces(self) -> None:
        """Test project with no stable interfaces."""
        metrics = {
            "/a.hpp": DSMMetrics(fan_out=10, fan_in=1, fan_out_project=10, fan_out_external=0, coupling=11, stability=0.91),
            "/b.hpp": DSMMetrics(fan_out=20, fan_in=2, fan_out_project=20, fan_out_external=0, coupling=22, stability=0.91),
            "/c.hpp": DSMMetrics(fan_out=30, fan_in=0, fan_out_project=30, fan_out_external=0, coupling=30, stability=1.0),
        }

        ratio, num_interfaces, total = calculate_interface_implementation_ratio(metrics, stability_threshold=0.3)

        assert ratio == 0.0
        assert num_interfaces == 0
        assert total == 3

    def test_mixed_interfaces(self) -> None:
        """Test project with mixed interface/implementation."""
        metrics = {
            "/interface.hpp": DSMMetrics(fan_out=0, fan_in=10, fan_out_project=0, fan_out_external=0, coupling=10, stability=0.0),
            "/impl1.hpp": DSMMetrics(fan_out=10, fan_in=1, fan_out_project=10, fan_out_external=0, coupling=11, stability=0.91),
            "/impl2.hpp": DSMMetrics(fan_out=20, fan_in=2, fan_out_project=20, fan_out_external=0, coupling=22, stability=0.91),
        }

        ratio, num_interfaces, total = calculate_interface_implementation_ratio(metrics, stability_threshold=0.3)

        assert ratio == pytest.approx(33.3, rel=0.1)
        assert num_interfaces == 1
        assert total == 3

    def test_empty_metrics(self) -> None:
        """Test with empty metrics."""
        ratio, num_interfaces, total = calculate_interface_implementation_ratio({}, stability_threshold=0.3)

        assert ratio == 0.0
        assert num_interfaces == 0
        assert total == 0


class TestCouplingOutliers:
    """Tests for coupling outlier detection using z-scores."""

    def test_no_outliers(self) -> None:
        """Test dataset with no outliers."""
        metrics = {f"/header{i}.hpp": DSMMetrics(fan_out=10, fan_in=10, fan_out_project=10, fan_out_external=0, coupling=20, stability=0.5) for i in range(10)}

        outliers, mean, stddev = detect_coupling_outliers(metrics, z_threshold=2.5)

        assert len(outliers) == 0
        assert mean == 20.0
        assert stddev == 0.0

    def test_with_outliers(self) -> None:
        """Test detection of outliers."""
        # Need more data points for z-score to be meaningful
        metrics = {f"/normal{i}.hpp": DSMMetrics(fan_out=10, fan_in=10, fan_out_project=10, fan_out_external=0, coupling=20, stability=0.5) for i in range(10)}
        metrics["/outlier.hpp"] = DSMMetrics(fan_out=100, fan_in=100, fan_out_project=100, fan_out_external=0, coupling=200, stability=0.5)

        outliers, mean, stddev = detect_coupling_outliers(metrics, z_threshold=2.0)

        assert len(outliers) >= 1
        assert outliers[0][0] == "/outlier.hpp"
        assert outliers[0][1] == 200
        assert outliers[0][2] > 2.0  # z-score should be > 2.0

    def test_multiple_outliers(self) -> None:
        """Test multiple outliers sorted by z-score."""
        # Create dataset with clear outliers
        metrics = {f"/normal{i}.hpp": DSMMetrics(fan_out=5, fan_in=5, fan_out_project=5, fan_out_external=0, coupling=10, stability=0.5) for i in range(20)}
        metrics["/outlier1.hpp"] = DSMMetrics(fan_out=30, fan_in=30, fan_out_project=30, fan_out_external=0, coupling=60, stability=0.5)
        metrics["/outlier2.hpp"] = DSMMetrics(fan_out=50, fan_in=50, fan_out_project=50, fan_out_external=0, coupling=100, stability=0.5)

        outliers, _, _ = detect_coupling_outliers(metrics, z_threshold=2.0)

        assert len(outliers) >= 2
        # Should be sorted by absolute z-score descending
        assert outliers[0][1] == 100  # Highest coupling first
        assert outliers[1][1] == 60

    def test_empty_metrics(self) -> None:
        """Test with empty metrics."""
        outliers, mean, stddev = detect_coupling_outliers({}, z_threshold=2.5)

        assert len(outliers) == 0
        assert mean == 0.0
        assert stddev == 0.0


class TestMatrixStatisticsWithAdvancedMetrics:
    """Tests for enhanced matrix statistics calculation."""

    def test_statistics_with_metrics(self) -> None:
        """Test statistics calculation with advanced metrics."""
        all_headers = {"/a.hpp", "/b.hpp", "/c.hpp"}
        header_to_headers = defaultdict(set, {"/a.hpp": {"/b.hpp"}, "/b.hpp": {"/c.hpp"}, "/c.hpp": set()})
        metrics = {
            "/a.hpp": DSMMetrics(fan_out=1, fan_in=0, fan_out_project=1, fan_out_external=0, coupling=1, stability=1.0),
            "/b.hpp": DSMMetrics(fan_out=1, fan_in=1, fan_out_project=1, fan_out_external=0, coupling=2, stability=0.5),
            "/c.hpp": DSMMetrics(fan_out=0, fan_in=1, fan_out_project=0, fan_out_external=0, coupling=1, stability=0.0),
        }
        headers_in_cycles: set[str] = set()
        num_cycles = 0

        stats = calculate_matrix_statistics(all_headers, header_to_headers, metrics=metrics, headers_in_cycles=headers_in_cycles, num_cycles=num_cycles)

        # Check basic stats
        assert stats.total_headers == 3
        assert stats.total_actual_deps == 2

        # Check advanced metrics are present
        assert stats.quality_score > 0
        assert stats.adp_score == 100.0  # No cycles
        assert stats.interface_ratio >= 0

    def test_statistics_without_advanced_metrics(self) -> None:
        """Test statistics calculation without advanced metrics (backward compatibility)."""
        all_headers = {"/a.hpp", "/b.hpp"}
        header_to_headers = defaultdict(set, {"/a.hpp": {"/b.hpp"}})

        stats = calculate_matrix_statistics(all_headers, header_to_headers)

        # Should still work
        assert stats.total_headers == 2
        assert stats.total_actual_deps == 1
        # Advanced metrics should default to 0
        assert stats.quality_score == 0.0
        assert stats.adp_score == 0.0
        assert stats.interface_ratio == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
