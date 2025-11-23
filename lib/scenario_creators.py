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
"""Shared scenario creator functions for DSM analysis demonstrations and tests.

This module contains functions that create baseline and scenario DSMAnalysisResults
for testing and demonstrating architectural patterns. These scenarios are used by:
  - test/test_dsm_scenario_patterns.py (architectural pattern validation)
  - test/test_dsm_scenario_metrics.py (metrics equivalence testing)
  - test/test_git_scenario_equivalence.py (git-based analysis validation)
  - demo/demo_scenario_validation.py (demonstration)

Each scenario represents a specific architectural pattern or anti-pattern.
"""

from collections import defaultdict
from typing import DefaultDict, Dict, List, Set, Tuple

from lib.dsm_analysis import run_dsm_analysis
from lib.dsm_types import DSMAnalysisResults


def build_source_to_deps_from_graph(all_headers: Set[str], header_to_headers: DefaultDict[str, Set[str]]) -> Dict[str, List[str]]:
    """Generate source file dependencies for ripple impact analysis.

    Creates .cpp files for each header, where each cpp depends on:
    - Its own header
    - Headers that the header depends on (direct dependencies only)

    Args:
        all_headers: Set of all headers
        header_to_headers: Mapping of headers to their direct dependencies

    Returns:
        Mapping of source files (.cpp) to their header dependencies
    """
    source_to_deps: Dict[str, List[str]] = {}

    for header in all_headers:
        source_file = header.replace(".hpp", ".cpp")
        deps: List[str] = [header]  # Always includes its own header

        # Add direct dependencies
        if header in header_to_headers:
            deps.extend(list(header_to_headers[header]))

        source_to_deps[source_file] = deps

    return source_to_deps


def create_baseline_scenario() -> tuple[DSMAnalysisResults, DefaultDict[str, Set[str]], Set[str], Dict[str, List[str]]]:
    """Create the standard baseline scenario used in most scenarios.

    This represents a stable starting architecture with:
    - 10 headers across 4 subsystems (Engine, Graphics, Game, UI)
    - 12 dependencies
    - 0 cycles
    - Layered architecture

    Returns:
        Tuple of (DSMAnalysisResults, header_to_headers graph, all_headers set, source_to_deps dict)
    """
    all_headers = {
        "Engine/Core.hpp",
        "Engine/Renderer.hpp",
        "Graphics/Shader.hpp",
        "Graphics/Texture.hpp",
        "Utils/Logger.hpp",
        "Utils/Math.hpp",
        "Game/Player.hpp",
        "Game/World.hpp",
        "UI/Menu.hpp",
        "UI/HUD.hpp",
    }

    header_to_headers = defaultdict(set)
    edges = [
        ("Game/Player.hpp", "Engine/Core.hpp"),
        ("Game/Player.hpp", "Graphics/Texture.hpp"),
        ("Game/Player.hpp", "Utils/Logger.hpp"),
        ("Game/World.hpp", "Engine/Core.hpp"),
        ("Game/World.hpp", "Utils/Math.hpp"),
        ("Engine/Core.hpp", "Utils/Logger.hpp"),
        ("Engine/Renderer.hpp", "Graphics/Shader.hpp"),
        ("Engine/Renderer.hpp", "Utils/Math.hpp"),
        ("Graphics/Shader.hpp", "Engine/Core.hpp"),
        ("Graphics/Shader.hpp", "Utils/Math.hpp"),
        ("UI/Menu.hpp", "Engine/Renderer.hpp"),
        ("UI/HUD.hpp", "Engine/Renderer.hpp"),
    ]

    for src, dst in edges:
        header_to_headers[src].add(dst)

    source_to_deps = build_source_to_deps_from_graph(all_headers, header_to_headers)

    dsm_results = run_dsm_analysis(
        all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=True, show_progress=False, source_to_deps=source_to_deps
    )

    return (dsm_results, header_to_headers, all_headers, source_to_deps)


def create_scenario_1_architectural_regressions() -> tuple[DSMAnalysisResults, DefaultDict[str, Set[str]], Set[str], Dict[str, List[str]]]:
    """Scenario 1: Architectural Regressions.

    Simulates feature addition that introduces architectural problems:
    - Adds Graphics/PostProcess.hpp (new header)
    - Increases coupling across multiple headers
    - Introduces circular dependency in Engine subsystem

    Returns:
        Tuple of (DSMAnalysisResults, header_to_headers graph, all_headers set, source_to_deps dict)
    """
    all_headers = {
        "Engine/Core.hpp",
        "Engine/Renderer.hpp",
        "Graphics/Shader.hpp",
        "Graphics/Texture.hpp",
        "Utils/Logger.hpp",
        "Utils/Math.hpp",
        "Game/Player.hpp",
        "Game/World.hpp",
        "UI/Menu.hpp",
        "UI/HUD.hpp",
        "Graphics/PostProcess.hpp",  # NEW header
    }

    header_to_headers = defaultdict(set)
    edges = [
        ("Game/Player.hpp", "Engine/Core.hpp"),
        ("Game/Player.hpp", "Graphics/Texture.hpp"),
        ("Game/Player.hpp", "Graphics/PostProcess.hpp"),  # New dependency
        ("Game/Player.hpp", "Utils/Logger.hpp"),
        ("Game/World.hpp", "Engine/Core.hpp"),
        ("Game/World.hpp", "Utils/Math.hpp"),
        ("Engine/Core.hpp", "Utils/Logger.hpp"),
        ("Engine/Renderer.hpp", "Graphics/Shader.hpp"),
        ("Engine/Renderer.hpp", "Utils/Math.hpp"),
        ("Graphics/Shader.hpp", "Engine/Core.hpp"),
        ("Graphics/Shader.hpp", "Utils/Math.hpp"),
        ("UI/Menu.hpp", "Engine/Renderer.hpp"),
        ("UI/HUD.hpp", "Engine/Renderer.hpp"),
        # New dependencies creating a cycle
        ("Engine/Core.hpp", "Graphics/PostProcess.hpp"),
        ("Graphics/PostProcess.hpp", "Engine/Renderer.hpp"),
        ("Engine/Renderer.hpp", "Engine/Core.hpp"),  # Creates cycle!
    ]

    for src, dst in edges:
        header_to_headers[src].add(dst)

    source_to_deps = build_source_to_deps_from_graph(all_headers, header_to_headers)

    dsm_results = run_dsm_analysis(
        all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=True, show_progress=False, source_to_deps=source_to_deps
    )

    return (dsm_results, header_to_headers, all_headers, source_to_deps)


def create_scenario_2_architectural_improvements() -> tuple[DSMAnalysisResults, DefaultDict[str, Set[str]], Set[str], Dict[str, List[str]]]:
    """Scenario 2: Architectural Improvements.

    Demonstrates successful refactoring through forward declarations:
    - Reduces coupling via forward declarations
    - Maintains clean layered architecture
    - No circular dependencies

    Returns:
        Tuple of (DSMAnalysisResults, header_to_headers graph, all_headers set, source_to_deps dict)
    """
    all_headers = {
        "Engine/Core.hpp",
        "Engine/Renderer.hpp",
        "Graphics/Shader.hpp",
        "Graphics/Texture.hpp",
        "Utils/Logger.hpp",
        "Utils/Math.hpp",
        "Game/Player.hpp",
        "Game/World.hpp",
        "UI/Menu.hpp",
        "UI/HUD.hpp",
    }

    header_to_headers = defaultdict(set)
    edges = [
        ("Game/Player.hpp", "Engine/Core.hpp"),
        # REMOVED: ("Game/Player.hpp", "Graphics/Texture.hpp"),  # Forward declaration instead
        ("Game/Player.hpp", "Utils/Logger.hpp"),
        ("Game/World.hpp", "Engine/Core.hpp"),
        ("Game/World.hpp", "Utils/Math.hpp"),
        ("Engine/Core.hpp", "Utils/Logger.hpp"),
        ("Engine/Renderer.hpp", "Graphics/Shader.hpp"),
        ("Engine/Renderer.hpp", "Utils/Math.hpp"),
        ("Graphics/Shader.hpp", "Engine/Core.hpp"),
        ("Graphics/Shader.hpp", "Utils/Math.hpp"),
        ("UI/Menu.hpp", "Engine/Renderer.hpp"),
        ("UI/HUD.hpp", "Engine/Renderer.hpp"),
    ]

    for src, dst in edges:
        header_to_headers[src].add(dst)

    source_to_deps = build_source_to_deps_from_graph(all_headers, header_to_headers)

    dsm_results = run_dsm_analysis(
        all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=True, show_progress=False, source_to_deps=source_to_deps
    )

    return (dsm_results, header_to_headers, all_headers, source_to_deps)


def create_scenario_3_refactoring_tradeoffs() -> tuple[DSMAnalysisResults, DefaultDict[str, Set[str]], Set[str], Dict[str, List[str]]]:
    """Scenario 3: Refactoring Trade-offs.

    Demonstrates interface extraction pattern:
    - Splits Utils/Logger.hpp into ILogger (interface) + LoggerImpl (implementation)
    - Clients depend on stable interface, not volatile implementation
    - Trade-off: More headers but better isolation

    Returns:
        Tuple of (DSMAnalysisResults, header_to_headers graph, all_headers set, source_to_deps dict)
    """
    all_headers = {
        "Engine/Core.hpp",
        "Engine/Renderer.hpp",
        "Graphics/Shader.hpp",
        "Graphics/Texture.hpp",
        "Utils/ILogger.hpp",  # NEW: Interface
        "Utils/LoggerImpl.hpp",  # NEW: Implementation
        "Utils/Math.hpp",
        "Game/Player.hpp",
        "Game/World.hpp",
        "UI/Menu.hpp",
        "UI/HUD.hpp",
    }

    header_to_headers = defaultdict(set)
    edges = [
        ("Game/Player.hpp", "Engine/Core.hpp"),
        ("Game/Player.hpp", "Graphics/Texture.hpp"),
        ("Game/World.hpp", "Engine/Core.hpp"),
        ("Game/World.hpp", "Utils/Math.hpp"),
        ("Engine/Core.hpp", "Utils/ILogger.hpp"),  # Interface only!
        ("Engine/Renderer.hpp", "Graphics/Shader.hpp"),
        ("Engine/Renderer.hpp", "Utils/Math.hpp"),
        ("Graphics/Shader.hpp", "Engine/Core.hpp"),
        ("Graphics/Shader.hpp", "Utils/Math.hpp"),
        ("UI/Menu.hpp", "Engine/Renderer.hpp"),
        ("UI/HUD.hpp", "Engine/Renderer.hpp"),
        ("Utils/LoggerImpl.hpp", "Utils/ILogger.hpp"),  # Impl depends on interface
        ("Game/Player.hpp", "Utils/ILogger.hpp"),  # Players use interface
    ]

    for src, dst in edges:
        header_to_headers[src].add(dst)

    source_to_deps = build_source_to_deps_from_graph(all_headers, header_to_headers)

    dsm_results = run_dsm_analysis(
        all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=True, show_progress=False, source_to_deps=source_to_deps
    )

    return (dsm_results, header_to_headers, all_headers, source_to_deps)


def create_scenario_4_pure_rebuild_reduction() -> tuple[DSMAnalysisResults, DefaultDict[str, Set[str]], Set[str], Dict[str, List[str]]]:
    """Scenario 4: Pure Rebuild Reduction.

    Same as scenario 2 - demonstrates coupling reduction through forward declarations.
    This is the "ideal" refactoring: better boundaries without adding complexity.

    Returns:
        Tuple of (DSMAnalysisResults, header_to_headers graph, all_headers set, source_to_deps dict)
    """
    return create_scenario_2_architectural_improvements()


def create_scenario_5_cycle_churn() -> tuple[DSMAnalysisResults, DefaultDict[str, Set[str]], Set[str], Dict[str, List[str]]]:
    """Scenario 5: Cycle Churn.

    Demonstrates architectural instability - breaks one cycle but creates two new ones:
    - Resolves: Engine/Core ↔ Graphics/Shader cycle
    - Adds: Game/Player ↔ Game/World cycle
    - Adds: UI/Menu ↔ UI/HUD cycle
    - Net result: +1 cycle (indicates unstable refactoring)

    NOTE: Uses different baseline (create_baseline_for_scenario_5)

    Returns:
        Tuple of (DSMAnalysisResults, header_to_headers graph, all_headers set, source_to_deps dict)
    """
    all_headers = {
        "Engine/Core.hpp",
        "Engine/Renderer.hpp",
        "Graphics/Shader.hpp",
        "Graphics/Texture.hpp",
        "Game/Player.hpp",
        "Game/World.hpp",
        "UI/Menu.hpp",
        "UI/HUD.hpp",
    }

    header_to_headers = defaultdict(set)
    edges = [
        # Resolved: Engine/Core ↔ Graphics/Shader (now acyclic)
        ("Engine/Core.hpp", "Graphics/Shader.hpp"),
        # NEW Cycle 1: Game/Player ↔ Game/World
        ("Game/Player.hpp", "Game/World.hpp"),
        ("Game/World.hpp", "Game/Player.hpp"),
        # NEW Cycle 2: UI/Menu ↔ UI/HUD
        ("UI/Menu.hpp", "UI/HUD.hpp"),
        ("UI/HUD.hpp", "UI/Menu.hpp"),
        # Other dependencies
        ("Engine/Renderer.hpp", "Engine/Core.hpp"),
        ("Graphics/Texture.hpp", "Graphics/Shader.hpp"),
    ]

    for src, dst in edges:
        header_to_headers[src].add(dst)

    source_to_deps = build_source_to_deps_from_graph(all_headers, header_to_headers)

    dsm_results = run_dsm_analysis(
        all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=False, show_progress=False, source_to_deps=source_to_deps
    )

    return (dsm_results, header_to_headers, all_headers, source_to_deps)


def create_baseline_for_scenario_5() -> tuple[DSMAnalysisResults, DefaultDict[str, Set[str]], Set[str], Dict[str, List[str]]]:
    """Create baseline for scenario 5 - has 1 cycle (Core ↔ Shader).

    Returns:
        DSMAnalysisResults for scenario 5 baseline
    """
    all_headers = {
        "Engine/Core.hpp",
        "Engine/Renderer.hpp",
        "Graphics/Shader.hpp",
        "Graphics/Texture.hpp",
        "Game/Player.hpp",
        "Game/World.hpp",
        "UI/Menu.hpp",
        "UI/HUD.hpp",
    }

    header_to_headers = defaultdict(set)
    edges = [
        # Cycle 1: Engine/Core ↔ Graphics/Shader
        ("Engine/Core.hpp", "Graphics/Shader.hpp"),
        ("Graphics/Shader.hpp", "Engine/Core.hpp"),
        # Other dependencies
        ("Engine/Renderer.hpp", "Engine/Core.hpp"),
        ("Graphics/Texture.hpp", "Graphics/Shader.hpp"),
        ("Game/Player.hpp", "Engine/Core.hpp"),
        ("Game/World.hpp", "Engine/Core.hpp"),
        ("UI/Menu.hpp", "Engine/Renderer.hpp"),
        ("UI/HUD.hpp", "Engine/Renderer.hpp"),
    ]

    for src, dst in edges:
        header_to_headers[src].add(dst)

    source_to_deps = build_source_to_deps_from_graph(all_headers, header_to_headers)

    dsm_results = run_dsm_analysis(
        all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=False, show_progress=False, source_to_deps=source_to_deps
    )

    return (dsm_results, header_to_headers, all_headers, source_to_deps)


def create_scenario_5_technical_debt_accumulation() -> tuple[DSMAnalysisResults, DefaultDict[str, Set[str]], Set[str], Dict[str, List[str]]]:
    """Scenario 6: Hidden Instability.

    Demonstrates stability threshold crossings - low coupling masks stability problems:
    - Graphics/Shader crosses stability threshold (becomes unstable)
    - Coupling decreased overall (looks good!)
    - But stability decreased (hidden problem!)

    Returns:
        DSMAnalysisResults for scenario 6
    """
    all_headers = {
        "Engine/Core.hpp",
        "Engine/Renderer.hpp",
        "Graphics/Shader.hpp",
        "Graphics/Texture.hpp",
        "Utils/Logger.hpp",
        "Utils/Math.hpp",
        "Game/Player.hpp",
        "Game/World.hpp",
        "UI/Menu.hpp",
        "UI/HUD.hpp",
    }

    header_to_headers = defaultdict(set)
    edges = [
        ("Game/Player.hpp", "Graphics/Shader.hpp"),  # NEW: increases Shader fan_in
        ("Game/Player.hpp", "Engine/Core.hpp"),
        ("Game/Player.hpp", "Utils/Logger.hpp"),
        ("Game/World.hpp", "Graphics/Shader.hpp"),  # NEW: increases Shader fan_in
        ("Game/World.hpp", "Utils/Math.hpp"),
        ("Engine/Core.hpp", "Utils/Logger.hpp"),
        ("Engine/Renderer.hpp", "Graphics/Shader.hpp"),
        ("Engine/Renderer.hpp", "Graphics/Texture.hpp"),
        ("Engine/Renderer.hpp", "Utils/Math.hpp"),
        ("Graphics/Shader.hpp", "Engine/Core.hpp"),  # Only 1 fan_out now
        ("UI/Menu.hpp", "Engine/Renderer.hpp"),
        ("UI/HUD.hpp", "Engine/Renderer.hpp"),
    ]

    for src, dst in edges:
        header_to_headers[src].add(dst)

    source_to_deps = build_source_to_deps_from_graph(all_headers, header_to_headers)

    dsm_results = run_dsm_analysis(
        all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=True, show_progress=False, source_to_deps=source_to_deps
    )

    return (dsm_results, header_to_headers, all_headers, source_to_deps)


def create_scenario_7_layering_violations() -> tuple[DSMAnalysisResults, DefaultDict[str, Set[str]], Set[str], Dict[str, List[str]]]:
    """Scenario 7: Dependency Hotspot.

    Demonstrates dependency concentration creating a hotspot:
    - Engine/Core becomes dependency hotspot with dramatically increased fan-in
    - Many modules converge on single component
    - Critical dependency affects rebuild times and architectural flexibility

    Returns:
        Tuple of (DSMAnalysisResults, header_to_headers graph, all_headers set, source_to_deps dict)
    """
    all_headers = {
        "Engine/Core.hpp",
        "Engine/Renderer.hpp",
        "Graphics/Shader.hpp",
        "Graphics/Texture.hpp",
        "Utils/Logger.hpp",
        "Utils/Math.hpp",
        "Game/Player.hpp",
        "Game/World.hpp",
        "UI/Menu.hpp",
        "UI/HUD.hpp",
    }

    header_to_headers = defaultdict(set)
    edges = [
        # Keep baseline dependencies
        ("Game/Player.hpp", "Engine/Core.hpp"),
        ("Game/Player.hpp", "Graphics/Texture.hpp"),
        ("Game/Player.hpp", "Utils/Logger.hpp"),
        ("Game/World.hpp", "Engine/Core.hpp"),
        ("Game/World.hpp", "Utils/Math.hpp"),
        ("Engine/Core.hpp", "Utils/Logger.hpp"),
        ("Engine/Renderer.hpp", "Graphics/Shader.hpp"),
        ("Engine/Renderer.hpp", "Utils/Math.hpp"),
        ("Graphics/Shader.hpp", "Engine/Core.hpp"),
        ("Graphics/Shader.hpp", "Utils/Math.hpp"),
        ("UI/Menu.hpp", "Engine/Renderer.hpp"),
        ("UI/HUD.hpp", "Engine/Renderer.hpp"),
        # NEW: Make Engine/Core a dependency hotspot
        ("Engine/Renderer.hpp", "Engine/Core.hpp"),
        ("Graphics/Texture.hpp", "Engine/Core.hpp"),
        ("UI/Menu.hpp", "Engine/Core.hpp"),
        ("UI/HUD.hpp", "Engine/Core.hpp"),
        # Add more coupling to reach critical severity
        ("Game/Player.hpp", "Engine/Renderer.hpp"),
        ("Game/World.hpp", "Engine/Renderer.hpp"),
        ("UI/Menu.hpp", "Graphics/Shader.hpp"),
        ("UI/HUD.hpp", "Graphics/Shader.hpp"),
        ("Graphics/Texture.hpp", "Utils/Logger.hpp"),
    ]

    for src, dst in edges:
        header_to_headers[src].add(dst)

    source_to_deps = build_source_to_deps_from_graph(all_headers, header_to_headers)

    dsm_results = run_dsm_analysis(
        all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=True, show_progress=False, source_to_deps=source_to_deps
    )

    return (dsm_results, header_to_headers, all_headers, source_to_deps)


def create_scenario_8_roi_breakeven() -> tuple[DSMAnalysisResults, DefaultDict[str, Set[str]], Set[str], Dict[str, List[str]]]:
    """Scenario 8: ROI Break-even Analysis.

    Demonstrates interface extraction refactoring pattern:
    - REMOVES Utils/Logger.hpp (high fan-in = 13)
    - ADDS Utils/ILogger.hpp (interface) + Utils/LoggerImpl.hpp (implementation)
    - Clients redirect to thin interface
    - Implementation is isolated (zero fan-in)

    NOTE: Uses different baseline (create_baseline_for_scenario_8)

    Returns:
        Tuple of (DSMAnalysisResults, header_to_headers graph, all_headers set, source_to_deps dict)
    """
    all_headers = {
        "Engine/Core.hpp",
        "Engine/Renderer.hpp",
        "Graphics/Shader.hpp",
        "Graphics/Texture.hpp",
        "Utils/ILogger.hpp",  # NEW: Interface
        "Utils/LoggerImpl.hpp",  # NEW: Implementation
        "Utils/Math.hpp",
        "Game/Player.hpp",
        "Game/World.hpp",
        "UI/Menu.hpp",
        "UI/HUD.hpp",
        "Network/Client.hpp",
        "Network/Server.hpp",
        "Audio/Sound.hpp",
        "Audio/Music.hpp",
    }

    header_to_headers = defaultdict(set)
    edges = [
        # All former Logger dependents now use ILogger interface
        ("Game/Player.hpp", "Utils/ILogger.hpp"),
        ("Game/World.hpp", "Utils/ILogger.hpp"),
        ("Engine/Core.hpp", "Utils/ILogger.hpp"),
        ("Engine/Renderer.hpp", "Utils/ILogger.hpp"),
        ("Graphics/Shader.hpp", "Utils/ILogger.hpp"),
        ("Graphics/Texture.hpp", "Utils/ILogger.hpp"),
        ("UI/Menu.hpp", "Utils/ILogger.hpp"),
        ("UI/HUD.hpp", "Utils/ILogger.hpp"),
        ("Network/Client.hpp", "Utils/ILogger.hpp"),
        ("Network/Server.hpp", "Utils/ILogger.hpp"),
        ("Audio/Sound.hpp", "Utils/ILogger.hpp"),
        ("Audio/Music.hpp", "Utils/ILogger.hpp"),
        ("Utils/Math.hpp", "Utils/ILogger.hpp"),
        # Implementation depends on interface (fan-in = 1)
        ("Utils/LoggerImpl.hpp", "Utils/ILogger.hpp"),
        # Other baseline deps
        ("Game/Player.hpp", "Engine/Core.hpp"),
        ("Game/World.hpp", "Engine/Core.hpp"),
        ("Engine/Renderer.hpp", "Graphics/Shader.hpp"),
        ("Graphics/Shader.hpp", "Engine/Core.hpp"),
        ("UI/Menu.hpp", "Engine/Renderer.hpp"),
        ("UI/HUD.hpp", "Engine/Renderer.hpp"),
        ("Network/Client.hpp", "Network/Server.hpp"),
    ]

    for src, dst in edges:
        header_to_headers[src].add(dst)

    source_to_deps = build_source_to_deps_from_graph(all_headers, header_to_headers)

    dsm_results = run_dsm_analysis(
        all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=True, show_progress=False, source_to_deps=source_to_deps
    )

    return (dsm_results, header_to_headers, all_headers, source_to_deps)


def create_baseline_for_scenario_8() -> tuple[DSMAnalysisResults, DefaultDict[str, Set[str]], Set[str], Dict[str, List[str]]]:
    """Create baseline for scenario 8 - Logger with high fan-in (interface extraction target).

    Returns:
        DSMAnalysisResults for scenario 8 baseline
    """
    baseline_headers = {
        "Engine/Core.hpp",
        "Engine/Renderer.hpp",
        "Graphics/Shader.hpp",
        "Graphics/Texture.hpp",
        "Utils/Logger.hpp",  # High fan-in target
        "Utils/Math.hpp",
        "Game/Player.hpp",
        "Game/World.hpp",
        "UI/Menu.hpp",
        "UI/HUD.hpp",
        "Network/Client.hpp",
        "Network/Server.hpp",
        "Audio/Sound.hpp",
        "Audio/Music.hpp",
    }

    baseline_deps = defaultdict(set)
    edges = [
        # Make Utils/Logger have high fan-in (13 dependents)
        ("Game/Player.hpp", "Utils/Logger.hpp"),
        ("Game/World.hpp", "Utils/Logger.hpp"),
        ("Engine/Core.hpp", "Utils/Logger.hpp"),
        ("Engine/Renderer.hpp", "Utils/Logger.hpp"),
        ("Graphics/Shader.hpp", "Utils/Logger.hpp"),
        ("Graphics/Texture.hpp", "Utils/Logger.hpp"),
        ("UI/Menu.hpp", "Utils/Logger.hpp"),
        ("UI/HUD.hpp", "Utils/Logger.hpp"),
        ("Network/Client.hpp", "Utils/Logger.hpp"),
        ("Network/Server.hpp", "Utils/Logger.hpp"),
        ("Audio/Sound.hpp", "Utils/Logger.hpp"),
        ("Audio/Music.hpp", "Utils/Logger.hpp"),
        ("Utils/Math.hpp", "Utils/Logger.hpp"),
        # Other baseline deps
        ("Game/Player.hpp", "Engine/Core.hpp"),
        ("Game/World.hpp", "Engine/Core.hpp"),
        ("Engine/Renderer.hpp", "Graphics/Shader.hpp"),
        ("Graphics/Shader.hpp", "Engine/Core.hpp"),
        ("UI/Menu.hpp", "Engine/Renderer.hpp"),
        ("UI/HUD.hpp", "Engine/Renderer.hpp"),
        ("Network/Client.hpp", "Network/Server.hpp"),
    ]

    for src, dst in edges:
        baseline_deps[src].add(dst)

    source_to_deps = build_source_to_deps_from_graph(baseline_headers, baseline_deps)

    dsm_results = run_dsm_analysis(
        all_headers=baseline_headers, header_to_headers=baseline_deps, compute_layers=True, show_progress=False, source_to_deps=source_to_deps
    )

    return (dsm_results, baseline_deps, baseline_headers, source_to_deps)


def create_scenario_9_outlier_detection() -> tuple[DSMAnalysisResults, DefaultDict[str, Set[str]], Set[str], Dict[str, List[str]]]:
    """Scenario 9: Outlier Detection.

    Demonstrates coupling outliers hiding architectural debt:
    - Most headers have uniform coupling (2 deps)
    - Module0/Header0 is outlier with 6 deps (3x normal)
    - Mean coupling looks reasonable, but variance is high
    - Statistical analysis reveals hidden architectural problems

    NOTE: Uses different baseline (create_baseline_for_scenario_9)

    Returns:
        Tuple of (DSMAnalysisResults, header_to_headers graph, all_headers set, source_to_deps dict)
    """
    all_headers = {f"Module{i}/Header{j}.hpp" for i in range(5) for j in range(5)}

    header_to_headers = defaultdict(set)
    headers_list = sorted(list(all_headers))

    # Keep baseline uniform coupling for most headers (2 deps each)
    for i, header in enumerate(headers_list[1:], start=1):  # Skip first header
        if i + 1 < len(headers_list):
            header_to_headers[header].add(headers_list[i + 1])
        if i + 2 < len(headers_list):
            header_to_headers[header].add(headers_list[i + 2])

    # Make Module0/Header0 an OUTLIER (moderate coupling increase)
    god_object = headers_list[0]
    for i in range(1, min(7, len(headers_list))):  # Depends on 6 other headers
        header_to_headers[god_object].add(headers_list[i])

    source_to_deps = build_source_to_deps_from_graph(all_headers, header_to_headers)

    dsm_results = run_dsm_analysis(
        all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=True, show_progress=False, source_to_deps=source_to_deps
    )

    return (dsm_results, header_to_headers, all_headers, source_to_deps)


def create_baseline_for_scenario_9() -> tuple[DSMAnalysisResults, DefaultDict[str, Set[str]], Set[str], Dict[str, List[str]]]:
    """Create baseline for scenario 9 - uniform coupling for outlier comparison.

    Returns:
        Tuple of (DSMAnalysisResults, header_to_headers graph, all_headers set, source_to_deps dict)
    """
    baseline_headers = {f"Module{i}/Header{j}.hpp" for i in range(5) for j in range(5)}
    baseline_deps = defaultdict(set)

    # Each header depends on exactly 2 headers (uniform coupling)
    headers_list = sorted(list(baseline_headers))
    for i, header in enumerate(headers_list):
        if i + 1 < len(headers_list):
            baseline_deps[header].add(headers_list[i + 1])
        if i + 2 < len(headers_list):
            baseline_deps[header].add(headers_list[i + 2])

    source_to_deps = build_source_to_deps_from_graph(baseline_headers, baseline_deps)

    dsm_results = run_dsm_analysis(
        all_headers=baseline_headers, header_to_headers=baseline_deps, compute_layers=True, show_progress=False, source_to_deps=source_to_deps
    )

    return (dsm_results, baseline_deps, baseline_headers, source_to_deps)


def create_scenario_10_critical_breaking_edges() -> tuple[DSMAnalysisResults, DefaultDict[str, Set[str]], Set[str], Dict[str, List[str]]]:
    """Scenario 10: Critical Breaking Edges.

    Demonstrates strategic cycle resolution using betweenness centrality:
    - Multiple interconnected circular dependencies
    - One critical edge connects cycle groups (high betweenness)
    - Removing critical edge breaks multiple cycles at once

    NOTE: Uses different baseline (create_baseline_for_scenario_10)

    Returns:
        Tuple of (DSMAnalysisResults, header_to_headers graph, all_headers set, source_to_deps dict)
    """
    all_headers = {
        "Engine/Core.hpp",
        "Engine/Renderer.hpp",
        "Engine/Physics.hpp",
        "Graphics/Shader.hpp",
        "Graphics/Texture.hpp",
        "Graphics/Pipeline.hpp",
        "Game/Player.hpp",
        "Game/World.hpp",
        "UI/Menu.hpp",
        "UI/HUD.hpp",
    }

    header_to_headers = defaultdict(set)
    edges = [
        # Cycle 1: Engine/Core ↔ Graphics/Shader ↔ Engine/Renderer
        ("Engine/Core.hpp", "Graphics/Shader.hpp"),
        ("Graphics/Shader.hpp", "Engine/Renderer.hpp"),
        ("Engine/Renderer.hpp", "Engine/Core.hpp"),
        # Cycle 2: Graphics/Pipeline ↔ Graphics/Texture ↔ Engine/Physics
        ("Graphics/Pipeline.hpp", "Graphics/Texture.hpp"),
        ("Graphics/Texture.hpp", "Engine/Physics.hpp"),
        ("Engine/Physics.hpp", "Graphics/Pipeline.hpp"),
        # CRITICAL EDGE: Connects both cycles
        ("Engine/Core.hpp", "Graphics/Pipeline.hpp"),
        ("Graphics/Pipeline.hpp", "Engine/Renderer.hpp"),
        # Game layer creates another cycle
        ("Game/Player.hpp", "Engine/Core.hpp"),
        ("Game/World.hpp", "Engine/Physics.hpp"),
        ("Engine/Core.hpp", "Game/Player.hpp"),
        # UI layer
        ("UI/Menu.hpp", "Engine/Renderer.hpp"),
        ("UI/HUD.hpp", "Game/World.hpp"),
    ]

    for src, dst in edges:
        header_to_headers[src].add(dst)

    source_to_deps = build_source_to_deps_from_graph(all_headers, header_to_headers)

    dsm_results = run_dsm_analysis(
        all_headers=all_headers, header_to_headers=header_to_headers, compute_layers=False, show_progress=False, source_to_deps=source_to_deps
    )

    return (dsm_results, header_to_headers, all_headers, source_to_deps)


def create_baseline_for_scenario_10() -> tuple[DSMAnalysisResults, DefaultDict[str, Set[str]], Set[str], Dict[str, List[str]]]:
    """Create baseline for scenario 10 - clean architecture (no cycles).

    Returns:
        DSMAnalysisResults for scenario 10 baseline
    """
    baseline_headers = {"Engine/Core.hpp", "Engine/Renderer.hpp", "Graphics/Shader.hpp", "Graphics/Texture.hpp", "Game/Player.hpp", "Game/World.hpp"}

    baseline_deps = defaultdict(set)
    baseline_edges = [
        ("Game/Player.hpp", "Engine/Core.hpp"),
        ("Game/World.hpp", "Engine/Core.hpp"),
        ("Engine/Renderer.hpp", "Graphics/Shader.hpp"),
        ("Graphics/Shader.hpp", "Graphics/Texture.hpp"),
    ]

    for src, dst in baseline_edges:
        baseline_deps[src].add(dst)

    source_to_deps = build_source_to_deps_from_graph(baseline_headers, baseline_deps)

    dsm_results = run_dsm_analysis(
        all_headers=baseline_headers, header_to_headers=baseline_deps, compute_layers=True, show_progress=False, source_to_deps=source_to_deps
    )

    return (dsm_results, baseline_deps, baseline_headers, source_to_deps)


# Scenario registry mapping scenario IDs to creator functions
SCENARIO_CREATORS = {
    1: create_scenario_1_architectural_regressions,
    2: create_scenario_2_architectural_improvements,
    3: create_scenario_3_refactoring_tradeoffs,
    4: create_scenario_4_pure_rebuild_reduction,
    5: create_scenario_5_cycle_churn,
    6: create_scenario_5_technical_debt_accumulation,
    7: create_scenario_7_layering_violations,
    8: create_scenario_8_roi_breakeven,
    9: create_scenario_9_outlier_detection,
    10: create_scenario_10_critical_breaking_edges,
}

# Baseline registry for scenarios with custom baselines
BASELINE_CREATORS = {
    1: create_baseline_scenario,
    2: create_baseline_scenario,
    3: create_baseline_scenario,  # Scenario 3 uses standard baseline
    4: create_baseline_scenario,
    5: create_baseline_for_scenario_5,
    6: create_baseline_scenario,
    7: create_baseline_scenario,
    8: create_baseline_for_scenario_8,  # Scenario 8 uses high fan-in Logger baseline
    9: create_baseline_for_scenario_9,
    10: create_baseline_for_scenario_10,
}


def create_git_repo_from_scenario(scenario_id: int, repo_path: str, baseline_as_head: bool = True, current_as_working: bool = True) -> None:
    """Create a physical git repository from a scenario's dependency graphs.

    This function generates actual .hpp/.cpp files with correct #include statements,
    creates a build.ninja and compile_commands.json, initializes a git repo,
    and commits baseline (HEAD) and/or current (working tree) states.

    Args:
        scenario_id: Which scenario to generate (1-10)
        repo_path: Directory path where git repo should be created
        baseline_as_head: If True, commit baseline state to HEAD
        current_as_working: If True, leave current state in working tree (uncommitted)

    Raises:
        ValueError: If scenario_id is invalid or creators not found
    """
    from pathlib import Path
    from lib.scenario_git_utils import (
        create_physical_file_structure,
        generate_build_ninja,
        generate_compile_commands_from_ninja,
        setup_git_repo,
        commit_all_files,
    )

    # Get scenario and baseline creators
    scenario_creator = SCENARIO_CREATORS.get(scenario_id)
    baseline_creator = BASELINE_CREATORS.get(scenario_id)

    if not scenario_creator or not baseline_creator:
        raise ValueError(f"Invalid scenario_id: {scenario_id}")

    # Create baseline and current graphs
    _, baseline_graph, baseline_headers, baseline_src_deps = baseline_creator()
    _, current_graph, current_headers, current_src_deps = scenario_creator()

    repo_root = Path(repo_path)
    repo_root.mkdir(parents=True, exist_ok=True)

    # Initialize git repo first
    setup_git_repo(str(repo_root))

    # If baseline should be committed to HEAD
    if baseline_as_head:
        # Generate baseline file structure
        create_physical_file_structure(str(repo_root), baseline_headers, baseline_graph, baseline_src_deps)

        # Generate build files
        source_files = list(baseline_src_deps.keys())  # Keep full paths with .cpp
        generate_build_ninja(str(repo_root), source_files, str(repo_root / "include"))
        generate_compile_commands_from_ninja(str(repo_root))

        # Commit baseline
        commit_all_files(str(repo_root), f"Baseline for scenario {scenario_id}")

    # If current should be in working tree
    if current_as_working:
        # Determine which files were deleted
        deleted_headers = baseline_headers - current_headers

        # Delete removed headers/sources
        import os

        for header in deleted_headers:
            header_path = repo_root / "include" / header
            source_path = repo_root / "src" / header.replace(".hpp", ".cpp")
            if header_path.exists():
                os.remove(header_path)
            if source_path.exists():
                os.remove(source_path)

        # Regenerate all current files (will overwrite modified ones)
        create_physical_file_structure(str(repo_root), current_headers, current_graph, current_src_deps)

        # Regenerate build files
        source_files = list(current_src_deps.keys())  # Keep full paths with .cpp
        generate_build_ninja(str(repo_root), source_files, str(repo_root / "include"))
        generate_compile_commands_from_ninja(str(repo_root))

        # Leave uncommitted (working tree changes)


# Registry mapping scenario IDs to git repo creator function
GIT_SCENARIO_CREATORS = {i: lambda sid=i, **kwargs: create_git_repo_from_scenario(sid, **kwargs) for i in range(1, 11)}
