#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
"""Shared scenario definitions for architectural demo scripts.

This module defines the 10 architectural scenarios used in both:
  - demo_architectural_insights.py (DSM-direct analysis)
  - demo_git_impact.py (git working tree analysis)

Each scenario is defined with expected architectural outcomes to enable
equivalence testing between the two approaches.
"""

from dataclasses import dataclass
from enum import Enum


class SeverityLevel(Enum):
    """Expected severity level for architectural changes."""

    CRITICAL = "critical"
    MODERATE = "moderate"
    POSITIVE = "positive"
    NEUTRAL = "neutral"


class CouplingTrend(Enum):
    """Expected trend in coupling statistics."""

    INCREASE = "increase"
    DECREASE = "decrease"
    STABLE = "stable"
    MIXED = "mixed"


@dataclass
class ExpectedArchitecturalOutcome:
    """Expected architectural metrics for a scenario.

    Attributes:
        cycles_delta: Expected change in cycle count (positive=added, negative=removed, 0=no change)
        coupling_trend: Expected direction of coupling changes
        has_new_headers: Whether new headers are added
        has_removed_headers: Whether headers are removed
        stability_crossings: Expected number of stability threshold crossings
        severity_level: Expected overall severity classification
        has_layer_violations: Whether layering violations are expected
        has_interface_extraction: Whether interface extraction pattern is used
        rebuild_impact_trend: Expected trend in rebuild impact (increase/decrease/stable)
        cycle_complexity_change: Expected change in cycle complexity (larger/smaller/stable)
        description: Human-readable description of the scenario
    """

    cycles_delta: int
    coupling_trend: CouplingTrend
    has_new_headers: bool
    has_removed_headers: bool
    stability_crossings: int
    severity_level: SeverityLevel
    has_layer_violations: bool = False
    has_interface_extraction: bool = False
    rebuild_impact_trend: str = "stable"  # "increase", "decrease", "stable"
    cycle_complexity_change: str = "stable"  # "larger", "smaller", "stable"
    description: str = ""


@dataclass
class ScenarioDefinition:
    """Definition of an architectural scenario.

    Attributes:
        scenario_id: Unique scenario identifier (1-10)
        name: Short scenario name
        description: Detailed description of what the scenario demonstrates
        expected_outcome: Expected architectural metrics
        tolerance_pct: Tolerance percentage for metric comparisons (default 5%)
        key_architectural_patterns: List of key patterns being demonstrated
    """

    scenario_id: int
    name: str
    description: str
    expected_outcome: ExpectedArchitecturalOutcome
    tolerance_pct: float = 5.0
    key_architectural_patterns: list[str] | None = None

    def __post_init__(self) -> None:
        if self.key_architectural_patterns is None:
            self.key_architectural_patterns = []


# Define the 10 standard architectural scenarios
SCENARIO_1_ARCHITECTURAL_REGRESSIONS = ScenarioDefinition(
    scenario_id=1,
    name="Architectural Regressions",
    description="Simulates feature addition that introduces architectural problems: " "new header with increased coupling and circular dependency creation",
    expected_outcome=ExpectedArchitecturalOutcome(
        cycles_delta=1,  # One new cycle introduced
        coupling_trend=CouplingTrend.INCREASE,
        has_new_headers=True,
        has_removed_headers=False,
        stability_crossings=0,  # No stability changes expected
        severity_level=SeverityLevel.MODERATE,  # DSM analysis typically uses moderate
        description="Introduces PostProcess.hpp creating Engine subsystem cycle",
    ),
    key_architectural_patterns=["cycle_introduction", "coupling_increase"],
)

SCENARIO_2_ARCHITECTURAL_IMPROVEMENTS = ScenarioDefinition(
    scenario_id=2,
    name="Architectural Improvements",
    description="Simulates successful refactoring: reduced coupling through " "dependency removal and forward declarations",
    expected_outcome=ExpectedArchitecturalOutcome(
        cycles_delta=0,  # No cycle changes
        coupling_trend=CouplingTrend.DECREASE,
        has_new_headers=False,
        has_removed_headers=False,
        stability_crossings=0,
        severity_level=SeverityLevel.MODERATE,
        rebuild_impact_trend="decrease",
        description="Reduces coupling via forward declarations in Player.hpp",
    ),
    key_architectural_patterns=["coupling_reduction", "forward_declarations"],
)

SCENARIO_3_REFACTORING_TRADEOFFS = ScenarioDefinition(
    scenario_id=3,
    name="Refactoring Trade-offs",
    description="Major refactoring with interface extraction: isolates implementation " "changes but adds structural complexity",
    expected_outcome=ExpectedArchitecturalOutcome(
        cycles_delta=0,  # No cycle changes
        coupling_trend=CouplingTrend.STABLE,  # Net stable due to tradeoffs
        has_new_headers=True,  # ILogger, LoggerImpl interfaces
        has_removed_headers=True,  # Logger.hpp removed
        stability_crossings=0,
        severity_level=SeverityLevel.MODERATE,
        has_interface_extraction=False,  # Not automatically detected,
        rebuild_impact_trend="decrease",
        description="Extracts ILogger interface, creates LoggerImpl separation",
    ),
    key_architectural_patterns=["interface_extraction", "rebuild_reduction"],
)

SCENARIO_4_PURE_REBUILD_REDUCTION = ScenarioDefinition(
    scenario_id=4,
    name="Pure Rebuild Reduction",
    description="Pure rebuild reduction through forward declarations: no structural " "changes, only dependency reduction",
    expected_outcome=ExpectedArchitecturalOutcome(
        cycles_delta=0,
        coupling_trend=CouplingTrend.DECREASE,
        has_new_headers=False,
        has_removed_headers=False,
        stability_crossings=0,
        severity_level=SeverityLevel.MODERATE,
        rebuild_impact_trend="decrease",
        description="Uses forward declarations to break Player → Texture dependency",
    ),
    key_architectural_patterns=["forward_declarations", "rebuild_reduction"],
)

SCENARIO_5_CYCLE_CHURN = ScenarioDefinition(
    scenario_id=5,
    name="Cycle Churn",
    description="Architectural instability: breaks one cycle but creates two new ones. "
    "NOTE: Uses different baseline (1 cycle) → current (2 cycles) = +1 net",
    expected_outcome=ExpectedArchitecturalOutcome(
        cycles_delta=1,  # Baseline has 1 cycle, current has 2 cycles (net +1)
        coupling_trend=CouplingTrend.MIXED,
        has_new_headers=False,
        has_removed_headers=False,
        stability_crossings=5,  # Structural changes cause stability shifts
        severity_level=SeverityLevel.MODERATE,
        cycle_complexity_change="stable",
        description="Breaks Shader↔Core cycle, creates Player↔World + Menu↔HUD cycles",
    ),
    key_architectural_patterns=["cycle_churn", "architectural_instability"],
)

SCENARIO_6_HIDDEN_INSTABILITY = ScenarioDefinition(
    scenario_id=6,
    name="Hidden Instability",
    description="Low coupling but high instability: headers cross stability threshold, " "indicating hidden architectural debt",
    expected_outcome=ExpectedArchitecturalOutcome(
        cycles_delta=0,
        coupling_trend=CouplingTrend.MIXED,  # Redistribution of edges causes both increases and decreases
        has_new_headers=False,
        has_removed_headers=False,
        stability_crossings=2,  # Multiple headers cross 0.5 threshold
        severity_level=SeverityLevel.MODERATE,
        description="Increases fan-out creating stability threshold crossings",
    ),
    key_architectural_patterns=["stability_threshold", "hidden_debt"],
)

SCENARIO_7_DEPENDENCY_HOTSPOT = ScenarioDefinition(
    scenario_id=7,
    name="Dependency Hotspot",
    description="Concentrated coupling: Engine/Core becomes dependency hotspot with " "dramatically increased fan-in, creating critical rebuild bottleneck",
    expected_outcome=ExpectedArchitecturalOutcome(
        cycles_delta=0,  # No cycles - just increased coupling concentration
        coupling_trend=CouplingTrend.INCREASE,
        has_new_headers=False,
        has_removed_headers=False,
        stability_crossings=3,  # Engine/Core and other headers cross stability thresholds
        severity_level=SeverityLevel.CRITICAL,
        has_layer_violations=False,
        description="Engine/Core fan-in increases from 3 to 7, becoming dependency hotspot",
    ),
    key_architectural_patterns=["dependency_hotspot", "coupling_concentration"],
)

SCENARIO_8_ROI_BREAKEVEN = ScenarioDefinition(
    scenario_id=8,
    name="ROI Break-even Analysis",
    description="Demonstrates ROI calculation: upfront refactoring cost vs. long-term " "rebuild savings, computing break-even point",
    expected_outcome=ExpectedArchitecturalOutcome(
        cycles_delta=0,
        coupling_trend=CouplingTrend.STABLE,  # Same total edge count, redirected
        has_new_headers=True,  # ILogger + LoggerImpl added
        has_removed_headers=True,  # Logger removed (high fan-in)
        stability_crossings=1,  # Interface/impl split affects stability
        severity_level=SeverityLevel.POSITIVE,  # Architectural improvement
        has_interface_extraction=True,  # Detected: removed high fan-in, added interface/impl
        rebuild_impact_trend="decrease",
        description="Interface extraction: Logger (fan-in=13) → ILogger + LoggerImpl (isolated)",
    ),
    key_architectural_patterns=["roi_analysis", "interface_extraction", "rebuild_reduction"],
)

SCENARIO_9_OUTLIER_DETECTION = ScenarioDefinition(
    scenario_id=9,
    name="Outlier Detection",
    description="Identifies coupling outliers: headers with significantly higher coupling " "than mean, indicating hidden architectural debt",
    expected_outcome=ExpectedArchitecturalOutcome(
        cycles_delta=0,
        coupling_trend=CouplingTrend.INCREASE,  # Focused increases creating outliers
        has_new_headers=False,
        has_removed_headers=False,
        stability_crossings=0,
        severity_level=SeverityLevel.MODERATE,
        description="Creates coupling outliers >1σ and >2σ from mean",
    ),
    key_architectural_patterns=["outlier_detection", "statistical_analysis"],
)

SCENARIO_10_CRITICAL_BREAKING_EDGES = ScenarioDefinition(
    scenario_id=10,
    name="Critical Breaking Edges",
    description="Strategic cycle resolution: identifies critical edges with high " "betweenness centrality that break multiple cycles when removed",
    expected_outcome=ExpectedArchitecturalOutcome(
        cycles_delta=1,  # Creates 1 large interconnected cycle (cycles merge)
        coupling_trend=CouplingTrend.INCREASE,
        has_new_headers=True,  # Scenario 10 adds new headers to create complex cycle structure
        has_removed_headers=False,
        stability_crossings=4,  # Multiple new headers with different stability profiles
        severity_level=SeverityLevel.CRITICAL,
        cycle_complexity_change="larger",
        description="Creates multiple interdependent cycles that merge into one large cycle",
    ),
    key_architectural_patterns=["critical_edges", "betweenness_centrality", "cycle_resolution"],
)

# Scenario registry for easy lookup
ALL_SCENARIOS = {
    1: SCENARIO_1_ARCHITECTURAL_REGRESSIONS,
    2: SCENARIO_2_ARCHITECTURAL_IMPROVEMENTS,
    3: SCENARIO_3_REFACTORING_TRADEOFFS,
    4: SCENARIO_4_PURE_REBUILD_REDUCTION,
    5: SCENARIO_5_CYCLE_CHURN,
    6: SCENARIO_6_HIDDEN_INSTABILITY,
    7: SCENARIO_7_DEPENDENCY_HOTSPOT,
    8: SCENARIO_8_ROI_BREAKEVEN,
    9: SCENARIO_9_OUTLIER_DETECTION,
    10: SCENARIO_10_CRITICAL_BREAKING_EDGES,
}


def get_scenario(scenario_id: int) -> ScenarioDefinition | None:
    """Get scenario definition by ID.

    Args:
        scenario_id: Scenario identifier (1-10)

    Returns:
        ScenarioDefinition if found, None otherwise
    """
    return ALL_SCENARIOS.get(scenario_id)


def get_all_scenario_ids() -> list[int]:
    """Get list of all valid scenario IDs.

    Returns:
        List of scenario IDs (1-10)
    """
    return sorted(ALL_SCENARIOS.keys())


def print_scenario_header(scenario_id: int, scenario_name: str) -> None:
    """Print a formatted header for a scenario.

    Args:
        scenario_id: Scenario number
        scenario_name: Scenario name
    """
    from lib.color_utils import Colors

    separator = "=" * 80
    print(f"\n{Colors.CYAN}{Colors.BRIGHT}{separator}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BRIGHT}Scenario {scenario_id}: {scenario_name}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BRIGHT}{separator}{Colors.RESET}\n")


def print_scenario_summary(scenario_id: int) -> None:
    """Print a summary of what the scenario demonstrates.

    Args:
        scenario_id: Scenario number
    """
    from lib.color_utils import Colors

    scenario_def = ALL_SCENARIOS.get(scenario_id)
    if not scenario_def:
        return

    print(f"{Colors.YELLOW}Description:{Colors.RESET}")
    print(f"  {scenario_def.description}\n")

    print(f"{Colors.YELLOW}Expected Outcome:{Colors.RESET}")
    exp = scenario_def.expected_outcome
    print(f"  • Cycles: {exp.cycles_delta:+d}")
    print(f"  • Coupling: {exp.coupling_trend.value}")
    print(f"  • Severity: {exp.severity_level.value}")

    if exp.has_new_headers:
        print(f"  • Adds new headers")
    if exp.has_removed_headers:
        print(f"  • Removes headers")
    if exp.has_layer_violations:
        print(f"  • Has layer violations")
    if exp.has_interface_extraction:
        print(f"  • Demonstrates interface extraction")

    print()
