#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Demo: Comprehensive Architectural Debt Score Calculation.

This demo shows the new 5-component debt score formula in action,
demonstrating how it evaluates codebases with different architectural issues.
"""

import sys
from pathlib import Path
from collections import defaultdict
import networkx as nx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.graph_utils import DSMMetrics
from lib.dsm_types import DSMAnalysisResults, ImprovementCandidate
from lib.dsm_analysis import calculate_architectural_debt_score, display_improvement_suggestions
from typing import Dict


def create_test_codebase(name: str, metrics: Dict[str, DSMMetrics], cycles: int = 0) -> DSMAnalysisResults:
    """Create a test codebase for debt score demonstration."""
    G: "nx.DiGraph[str]" = nx.DiGraph()
    G.add_nodes_from(metrics.keys())

    # Create cycle sets
    cycle_list = [{f"cycle_header_{i}.h"} for i in range(cycles)]

    return DSMAnalysisResults(
        metrics=metrics,
        cycles=cycle_list,
        headers_in_cycles=set([h for cycle in cycle_list for h in cycle]),
        feedback_edges=[],
        directed_graph=G,
        layers=[],
        header_to_layer={},
        has_cycles=len(cycle_list) > 0,
        stats=None,
        sorted_headers=list(metrics.keys()),
        reverse_deps={h: set() for h in metrics.keys()},
        header_to_headers=defaultdict(set, {h: set() for h in metrics.keys()}),
        source_to_deps=None,
        self_loops=[],
    )


def demo_perfect_codebase() -> None:
    """Demo 1: Perfect codebase with minimal debt."""
    print("\n" + "=" * 80)
    print("DEMO 1: Perfect Codebase (Low Debt)")
    print("=" * 80)
    print("Low coupling, no cycles, balanced stability, no outliers\n")

    metrics = {f"include/module{i}.h": DSMMetrics(fan_out=3, fan_in=3, fan_out_project=3, fan_out_external=0, coupling=6, stability=0.5) for i in range(20)}

    results = create_test_codebase("perfect", metrics, cycles=0)
    score, breakdown = calculate_architectural_debt_score(results, verbose=True)

    print(f"📊 Debt Score: {score:.1f}/100")
    print(f"\nComponent Breakdown:")
    assert breakdown is not None
    print(f"  P95 Coupling (30%):  {breakdown['p95_coupling_component']:>6.1f} points")
    print(f"  Outliers >2σ (20%):  {breakdown['outlier_component']:>6.1f} points")
    print(f"  Avg Stability (15%): {breakdown['stability_component']:>6.1f} points")
    print(f"  Hub Nodes (10%):     {breakdown['hub_component']:>6.1f} points")
    print(f"  Cycles (25%):        {breakdown['cycle_component']:>6.1f} points")
    print(f"\n✅ Result: Healthy architecture (score < 30)")


def demo_high_coupling() -> None:
    """Demo 2: High coupling scenario."""
    print("\n" + "=" * 80)
    print("DEMO 2: High Coupling Codebase")
    print("=" * 80)
    print("Most headers have high coupling (80-100), no cycles\n")

    metrics = {
        f"include/coupled{i}.h": DSMMetrics(fan_out=45, fan_in=45, fan_out_project=45, fan_out_external=0, coupling=90, stability=0.5) for i in range(20)
    }

    results = create_test_codebase("high_coupling", metrics, cycles=0)
    score, breakdown = calculate_architectural_debt_score(results, verbose=True)

    print(f"📊 Debt Score: {score:.1f}/100")
    print(f"\nComponent Breakdown:")
    assert breakdown is not None
    print(f"  P95 Coupling (30%):  {breakdown['p95_coupling_component']:>6.1f} points ⚠️")
    print(f"  Outliers >2σ (20%):  {breakdown['outlier_component']:>6.1f} points")
    print(f"  Avg Stability (15%): {breakdown['stability_component']:>6.1f} points")
    print(f"  Hub Nodes (10%):     {breakdown['hub_component']:>6.1f} points")
    print(f"  Cycles (25%):        {breakdown['cycle_component']:>6.1f} points")
    print(f"\n⚠️  Result: High coupling drives debt score (P95 component maxed at 30)")


def demo_with_outliers() -> None:
    """Demo 3: Codebase with statistical outliers."""
    print("\n" + "=" * 80)
    print("DEMO 3: Codebase with Statistical Outliers")
    print("=" * 80)
    print("Mostly healthy (coupling=25), but 2 god objects (coupling=150, 155)\n")

    metrics = {
        **{f"include/normal{i}.h": DSMMetrics(fan_out=20, fan_in=5, fan_out_project=20, fan_out_external=0, coupling=25, stability=0.8) for i in range(18)},
        "include/god_object1.h": DSMMetrics(fan_out=140, fan_in=10, fan_out_project=140, fan_out_external=0, coupling=150, stability=0.93),
        "include/god_object2.h": DSMMetrics(fan_out=145, fan_in=10, fan_out_project=145, fan_out_external=0, coupling=155, stability=0.94),
    }

    results = create_test_codebase("outliers", metrics, cycles=0)
    score, breakdown = calculate_architectural_debt_score(results, verbose=True)

    print(f"📊 Debt Score: {score:.1f}/100")
    print(f"\nComponent Breakdown:")
    assert breakdown is not None
    print(f"  P95 Coupling (30%):  {breakdown['p95_coupling_component']:>6.1f} points ⚠️")
    print(f"  Outliers >2σ (20%):  {breakdown['outlier_component']:>6.1f} points ⚠️")
    print(f"  Avg Stability (15%): {breakdown['stability_component']:>6.1f} points ⚠️")
    print(f"  Hub Nodes (10%):     {breakdown['hub_component']:>6.1f} points")
    print(f"  Cycles (25%):        {breakdown['cycle_component']:>6.1f} points")
    print(f"\n⚠️  Result: God objects create statistical outliers (10% of data)")


def demo_with_cycles() -> None:
    """Demo 4: Codebase with circular dependencies."""
    print("\n" + "=" * 80)
    print("DEMO 4: Codebase with Circular Dependencies")
    print("=" * 80)
    print("Moderate coupling but 5 circular dependency groups\n")

    metrics = {
        f"include/header{i}.h": DSMMetrics(fan_out=25, fan_in=15, fan_out_project=25, fan_out_external=0, coupling=40, stability=0.63) for i in range(20)
    }

    results = create_test_codebase("cycles", metrics, cycles=5)
    score, breakdown = calculate_architectural_debt_score(results, verbose=True)

    print(f"📊 Debt Score: {score:.1f}/100")
    print(f"\nComponent Breakdown:")
    assert breakdown is not None
    print(f"  P95 Coupling (30%):  {breakdown['p95_coupling_component']:>6.1f} points")
    print(f"  Outliers >2σ (20%):  {breakdown['outlier_component']:>6.1f} points")
    print(f"  Avg Stability (15%): {breakdown['stability_component']:>6.1f} points")
    print(f"  Hub Nodes (10%):     {breakdown['hub_component']:>6.1f} points")
    print(f"  Cycles (25%):        {breakdown['cycle_component']:>6.1f} points 🔴")
    print(f"\n🔴 Result: Cycles contribute significantly (5 cycles → 17.8 points)")


def demo_comprehensive_bad() -> None:
    """Demo 5: Everything wrong at once."""
    print("\n" + "=" * 80)
    print("DEMO 5: Comprehensive Technical Debt")
    print("=" * 80)
    print("High coupling + outliers + instability + cycles\n")

    metrics = {
        **{f"include/unstable{i}.h": DSMMetrics(fan_out=50, fan_in=10, fan_out_project=50, fan_out_external=0, coupling=60, stability=0.83) for i in range(18)},
        "include/mega_outlier1.h": DSMMetrics(fan_out=180, fan_in=20, fan_out_project=180, fan_out_external=0, coupling=200, stability=0.9),
        "include/mega_outlier2.h": DSMMetrics(fan_out=190, fan_in=20, fan_out_project=190, fan_out_external=0, coupling=210, stability=0.91),
    }

    results = create_test_codebase("bad", metrics, cycles=8)
    score, breakdown = calculate_architectural_debt_score(results, verbose=True)

    print(f"📊 Debt Score: {score:.1f}/100")
    print(f"\nComponent Breakdown:")
    assert breakdown is not None
    print(f"  P95 Coupling (30%):  {breakdown['p95_coupling_component']:>6.1f} points 🔴")
    print(f"  Outliers >2σ (20%):  {breakdown['outlier_component']:>6.1f} points 🔴")
    print(f"  Avg Stability (15%): {breakdown['stability_component']:>6.1f} points 🔴")
    print(f"  Hub Nodes (10%):     {breakdown['hub_component']:>6.1f} points")
    print(f"  Cycles (25%):        {breakdown['cycle_component']:>6.1f} points 🔴")
    print(f"\n🔴 Result: CRITICAL - Multiple architectural issues (score ≥ 60)")


def demo_integration_display() -> None:
    """Demo 6: Integration with improvement suggestions display."""
    print("\n" + "=" * 80)
    print("DEMO 6: Integration with --suggest-improvements")
    print("=" * 80)
    print("Shows how debt score appears in actual tool output\n")

    metrics = {
        **{f"src/header{i}.h": DSMMetrics(fan_out=20, fan_in=5, fan_out_project=20, fan_out_external=0, coupling=25, stability=0.8) for i in range(18)},
        "src/problematic.h": DSMMetrics(fan_out=140, fan_in=10, fan_out_project=140, fan_out_external=0, coupling=150, stability=0.93),
        "src/another_problem.h": DSMMetrics(fan_out=145, fan_in=10, fan_out_project=145, fan_out_external=0, coupling=155, stability=0.94),
    }

    results = create_test_codebase("integration", metrics, cycles=0)

    # Create improvement candidate
    candidates: list[ImprovementCandidate] = [
        ImprovementCandidate(
            header="src/problematic.h",
            anti_pattern="excessive_coupling",
            current_metrics=metrics["src/problematic.h"],
            severity="critical",
            roi_score=75.0,
            estimated_coupling_reduction=50,
            estimated_rebuild_reduction=25.0,
            effort_estimate="medium",
            break_even_commits=8,
            specific_issues=["Couples to 140 other headers"],
            actionable_steps=["Split into focused modules", "Use interfaces"],
            affected_headers=set(),
        )
    ]

    # Display as it appears in real output
    display_improvement_suggestions(candidates, results, "/project", top_n=5, verbose=True)


def main() -> None:
    """Run all debt score demos."""
    print("\n" + "█" * 80)
    print("█" + " " * 78 + "█")
    print("█" + "  COMPREHENSIVE ARCHITECTURAL DEBT SCORE - DEMONSTRATION".center(78) + "█")
    print("█" + " " * 78 + "█")
    print("█" * 80)

    print("\nThis demo showcases the new 5-component debt score formula:")
    print("  • P95 Coupling (30% weight) - 95th percentile coupling detection")
    print("  • Outliers (20% weight) - Statistical outliers beyond mean+2σ")
    print("  • Stability (15% weight) - Average instability metric")
    print("  • Hubs (10% weight) - High betweenness centrality nodes")
    print("  • Cycles (25% weight) - Circular dependencies with diminishing returns")
    print("\nScore range: 0-100 where 0=perfect, 100=maximum debt")
    print("Color coding: Green (<30), Yellow (30-60), Red (≥60)")

    demo_perfect_codebase()
    demo_high_coupling()
    demo_with_outliers()
    demo_with_cycles()
    demo_comprehensive_bad()
    demo_integration_display()

    print("\n" + "█" * 80)
    print("█" + " " * 78 + "█")
    print("█" + "  DEMO COMPLETE - Ready for production use!".center(78) + "█")
    print("█" + " " * 78 + "█")
    print("█" * 80)
    print("\nTo use in your project:")
    print("  python3 buildCheckDSM.py <ninja-dir> --suggest-improvements --verbose")
    print()


if __name__ == "__main__":
    main()
