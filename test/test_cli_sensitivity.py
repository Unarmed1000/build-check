#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for CLI --sensitivity flag integration (Phase 3C)."""

import pytest
from unittest.mock import patch, MagicMock
from lib.sensitivity_thresholds import SensitivityLevel, DetectionThresholds


class TestSensitivityCLIIntegration:
    """Tests for --sensitivity flag integration with buildCheckDSM.py."""

    @patch("lib.dsm_analysis.run_dsm_analysis")
    @patch("lib.dsm_analysis.build_include_graph")
    @patch("lib.dsm_analysis.identify_improvement_candidates")
    @patch("lib.dsm_analysis.estimate_improvement_roi")
    @patch("lib.dsm_analysis.rank_improvements_by_impact")
    def test_sensitivity_low_creates_low_thresholds(
        self, mock_rank: MagicMock, mock_roi: MagicMock, mock_identify: MagicMock, mock_build_graph: MagicMock, mock_run_dsm: MagicMock
    ) -> None:
        """Verify 'low' sensitivity creates LOW thresholds."""
        from lib.dsm_analysis import run_proactive_improvement_analysis
        from lib.dsm_types import DSMAnalysisResults, ImprovementCandidate
        from lib.clang_utils import IncludeGraphScanResult

        # Mock build_include_graph
        mock_scan_result = MagicMock(spec=IncludeGraphScanResult)
        mock_scan_result.include_graph = {}
        mock_scan_result.all_headers = set()
        mock_scan_result.source_to_deps = {}
        mock_scan_result.file_types = {}
        mock_scan_result.scan_time = 0.5
        mock_build_graph.return_value = mock_scan_result

        # Mock run_dsm_analysis to return valid results
        mock_results = MagicMock(spec=DSMAnalysisResults)
        mock_results.metrics = {}
        mock_run_dsm.return_value = mock_results

        # Mock identify to return empty list
        mock_identify.return_value = []

        # Mock rank to return empty list
        mock_rank.return_value = []

        # Run with low sensitivity
        result = run_proactive_improvement_analysis(build_dir="/fake/build", project_root="/fake/project", sensitivity="low")

        # Verify identify_improvement_candidates was called with LOW thresholds
        assert mock_identify.called
        call_args = mock_identify.call_args
        thresholds = call_args[0][2]  # Third positional argument
        assert isinstance(thresholds, DetectionThresholds)
        assert thresholds.god_object_fanout == 70  # LOW threshold
        assert thresholds.outlier_sigma == 3.0

    @patch("lib.dsm_analysis.run_dsm_analysis")
    @patch("lib.dsm_analysis.build_include_graph")
    @patch("lib.dsm_analysis.identify_improvement_candidates")
    @patch("lib.dsm_analysis.estimate_improvement_roi")
    @patch("lib.dsm_analysis.rank_improvements_by_impact")
    def test_sensitivity_medium_creates_medium_thresholds(
        self, mock_rank: MagicMock, mock_roi: MagicMock, mock_identify: MagicMock, mock_build_graph: MagicMock, mock_run_dsm: MagicMock
    ) -> None:
        """Verify 'medium' sensitivity creates MEDIUM thresholds."""
        from lib.dsm_analysis import run_proactive_improvement_analysis
        from lib.dsm_types import DSMAnalysisResults
        from lib.clang_utils import IncludeGraphScanResult

        mock_scan_result = MagicMock(spec=IncludeGraphScanResult)
        mock_scan_result.include_graph = {}
        mock_scan_result.all_headers = set()
        mock_scan_result.source_to_deps = {}
        mock_scan_result.file_types = {}
        mock_scan_result.scan_time = 0.5
        mock_build_graph.return_value = mock_scan_result

        mock_results = MagicMock(spec=DSMAnalysisResults)
        mock_results.metrics = {}
        mock_run_dsm.return_value = mock_results
        mock_identify.return_value = []
        mock_rank.return_value = []

        result = run_proactive_improvement_analysis(build_dir="/fake/build", project_root="/fake/project", sensitivity="medium")

        assert mock_identify.called
        thresholds = mock_identify.call_args[0][2]
        assert thresholds.god_object_fanout == 50  # MEDIUM threshold
        assert thresholds.outlier_sigma == 2.5

    @patch("lib.dsm_analysis.run_dsm_analysis")
    @patch("lib.dsm_analysis.build_include_graph")
    @patch("lib.dsm_analysis.identify_improvement_candidates")
    @patch("lib.dsm_analysis.estimate_improvement_roi")
    @patch("lib.dsm_analysis.rank_improvements_by_impact")
    def test_sensitivity_high_creates_high_thresholds(
        self, mock_rank: MagicMock, mock_roi: MagicMock, mock_identify: MagicMock, mock_build_graph: MagicMock, mock_run_dsm: MagicMock
    ) -> None:
        """Verify 'high' sensitivity creates HIGH thresholds."""
        from lib.dsm_analysis import run_proactive_improvement_analysis
        from lib.dsm_types import DSMAnalysisResults
        from lib.clang_utils import IncludeGraphScanResult

        mock_scan_result = MagicMock(spec=IncludeGraphScanResult)
        mock_scan_result.include_graph = {}
        mock_scan_result.all_headers = set()
        mock_scan_result.source_to_deps = {}
        mock_scan_result.file_types = {}
        mock_scan_result.scan_time = 0.5
        mock_build_graph.return_value = mock_scan_result

        mock_results = MagicMock(spec=DSMAnalysisResults)
        mock_results.metrics = {}
        mock_run_dsm.return_value = mock_results
        mock_identify.return_value = []
        mock_rank.return_value = []

        result = run_proactive_improvement_analysis(build_dir="/fake/build", project_root="/fake/project", sensitivity="high")

        assert mock_identify.called
        thresholds = mock_identify.call_args[0][2]
        assert thresholds.god_object_fanout == 30  # HIGH threshold
        assert thresholds.outlier_sigma == 1.5

    @patch("lib.dsm_analysis.display_improvement_suggestions")
    @patch("lib.dsm_analysis.run_dsm_analysis")
    @patch("lib.dsm_analysis.build_include_graph")
    @patch("lib.dsm_analysis.identify_improvement_candidates")
    @patch("lib.dsm_analysis.estimate_improvement_roi")
    @patch("lib.dsm_analysis.rank_improvements_by_impact")
    def test_roi_estimation_receives_thresholds(
        self, mock_rank: MagicMock, mock_roi: MagicMock, mock_identify: MagicMock, mock_build_graph: MagicMock, mock_run_dsm: MagicMock, mock_display: MagicMock
    ) -> None:
        """Verify estimate_improvement_roi receives thresholds parameter."""
        from lib.dsm_analysis import run_proactive_improvement_analysis
        from lib.dsm_types import DSMAnalysisResults, ImprovementCandidate
        from lib.clang_utils import IncludeGraphScanResult

        mock_scan_result = MagicMock(spec=IncludeGraphScanResult)
        mock_scan_result.include_graph = {}
        mock_scan_result.all_headers = set()
        mock_scan_result.source_to_deps = {}
        mock_scan_result.file_types = {}
        mock_scan_result.scan_time = 0.5
        mock_build_graph.return_value = mock_scan_result

        mock_results = MagicMock(spec=DSMAnalysisResults)
        mock_results.metrics = {}
        mock_run_dsm.return_value = mock_results  # Return a candidate that needs ROI estimation
        mock_candidate = MagicMock(spec=ImprovementCandidate)
        mock_identify.return_value = [mock_candidate]

        # Mock ROI to return the same candidate
        mock_roi.return_value = mock_candidate
        mock_rank.return_value = [mock_candidate]

        result = run_proactive_improvement_analysis(build_dir="/fake/build", project_root="/fake/project", sensitivity="high")

        # Verify estimate_improvement_roi was called with thresholds
        assert mock_roi.called
        call_kwargs = mock_roi.call_args
        # Should have thresholds as 4th positional arg or keyword arg
        if len(call_kwargs[0]) >= 4:
            thresholds = call_kwargs[0][3]
        else:
            thresholds = call_kwargs[1].get("thresholds")
        assert thresholds is not None
        assert isinstance(thresholds, DetectionThresholds)
        assert thresholds.god_object_fanout == 30  # HIGH threshold

    def test_sensitivity_default_is_medium(self) -> None:
        """Verify default sensitivity parameter is 'medium'."""
        from lib.dsm_analysis import run_proactive_improvement_analysis
        import inspect

        sig = inspect.signature(run_proactive_improvement_analysis)
        sensitivity_param = sig.parameters["sensitivity"]
        assert sensitivity_param.default == "medium"

    @patch("lib.dsm_analysis.run_dsm_analysis")
    @patch("lib.dsm_analysis.build_include_graph")
    @patch("lib.dsm_analysis.identify_improvement_candidates")
    @patch("lib.dsm_analysis.rank_improvements_by_impact")
    def test_invalid_sensitivity_defaults_to_medium(
        self, mock_rank: MagicMock, mock_identify: MagicMock, mock_build_graph: MagicMock, mock_run_dsm: MagicMock
    ) -> None:
        """Verify invalid sensitivity string defaults to MEDIUM."""
        from lib.dsm_analysis import run_proactive_improvement_analysis
        from lib.dsm_types import DSMAnalysisResults
        from lib.clang_utils import IncludeGraphScanResult

        mock_scan_result = MagicMock(spec=IncludeGraphScanResult)
        mock_scan_result.include_graph = {}
        mock_scan_result.all_headers = set()
        mock_scan_result.source_to_deps = {}
        mock_scan_result.file_types = {}
        mock_scan_result.scan_time = 0.5
        mock_build_graph.return_value = mock_scan_result

        mock_results = MagicMock(spec=DSMAnalysisResults)
        mock_results.metrics = {}
        mock_run_dsm.return_value = mock_results
        mock_identify.return_value = []
        mock_rank.return_value = []

        result = run_proactive_improvement_analysis(build_dir="/fake/build", project_root="/fake/project", sensitivity="INVALID")  # Invalid value

        # Should fall back to MEDIUM
        assert mock_identify.called
        thresholds = mock_identify.call_args[0][2]
        assert thresholds.god_object_fanout == 50  # MEDIUM threshold
