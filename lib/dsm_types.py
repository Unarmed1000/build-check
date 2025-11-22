#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#****************************************************************************************************************************************************
#* BSD 3-Clause License
#*
#* Copyright (c) 2025, Mana Battery
#* All rights reserved.
#*
#* Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#*
#* 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#* 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the
#*    documentation and/or other materials provided with the distribution.
#* 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this
#*    software without specific prior written permission.
#*
#* THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
#* THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
#* CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
#* PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
#* LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
#* EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#****************************************************************************************************************************************************
"""Type definitions for DSM analysis.

This module contains dataclasses and type definitions used across DSM analysis modules.
"""

from typing import Dict, Set, List, Tuple, Any, DefaultDict
from dataclasses import dataclass

import networkx as nx
from .graph_utils import DSMMetrics


@dataclass
class MatrixStatistics:
    """DSM matrix statistics.
    
    Attributes:
        total_headers: Total number of headers in the matrix
        total_actual_deps: Total number of actual dependencies
        total_possible_deps: Maximum possible dependencies
        sparsity: Percentage of missing dependencies (0-100)
        avg_deps: Average dependencies per header
        health: Health description string
        health_color: Color code for health display
    """
    total_headers: int
    total_actual_deps: int
    total_possible_deps: int
    sparsity: float
    avg_deps: float
    health: str
    health_color: str


@dataclass
class DSMAnalysisResults:
    """Container for DSM analysis results.
    
    Attributes:
        metrics: Per-header metrics (fan-in, fan-out, coupling, stability)
        cycles: List of circular dependency groups
        headers_in_cycles: Set of headers that are part of cycles
        feedback_edges: Edges that should be removed to break cycles
        directed_graph: NetworkX directed graph of dependencies
        layers: Dependency layers (topological ordering)
        header_to_layer: Mapping of headers to their layer number
        has_cycles: Whether the graph contains cycles
        stats: Matrix statistics (sparsity, coupling, etc.)
        sorted_headers: Headers sorted by coupling (descending)
        reverse_deps: Reverse dependency mapping
        header_to_headers: Forward dependency mapping
    """
    metrics: Dict[str, 'DSMMetrics']
    cycles: List[Set[str]]
    headers_in_cycles: Set[str]
    feedback_edges: List[Tuple[str, str]]
    directed_graph: 'nx.DiGraph[Any]'  # NetworkX DiGraph (required dependency)
    layers: List[List[str]]
    header_to_layer: Dict[str, int]
    has_cycles: bool
    stats: 'MatrixStatistics'
    sorted_headers: List[str]
    reverse_deps: Dict[str, Set[str]]
    header_to_headers: DefaultDict[str, Set[str]]


@dataclass
class DSMDelta:
    """Differences between two DSM analysis results.
    
    Attributes:
        headers_added: Headers present in current but not baseline
        headers_removed: Headers present in baseline but not current
        cycles_added: Number of new cycles introduced
        cycles_removed: Number of cycles eliminated
        coupling_increased: Headers with increased coupling (header -> delta)
        coupling_decreased: Headers with decreased coupling (header -> delta)
        layer_changes: Headers that moved layers (header -> (old_layer, new_layer))
        new_cycle_participants: Headers newly involved in cycles
        resolved_cycle_participants: Headers no longer in cycles
    """
    headers_added: Set[str]
    headers_removed: Set[str]
    cycles_added: int
    cycles_removed: int
    coupling_increased: Dict[str, int]
    coupling_decreased: Dict[str, int]
    layer_changes: Dict[str, Tuple[int, int]]
    new_cycle_participants: Set[str]
    resolved_cycle_participants: Set[str]
