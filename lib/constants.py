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
"""Shared constants for buildCheck tools.

This module provides centralized constants used across multiple buildCheck tools
to ensure consistency and make it easy to adjust thresholds and defaults.
"""

# =============================================================================
# Exit Codes
# =============================================================================

EXIT_SUCCESS = 0
EXIT_INVALID_ARGS = 1
EXIT_RUNTIME_ERROR = 2
EXIT_KEYBOARD_INTERRUPT = 130

# =============================================================================
# DSM Analysis Constants
# =============================================================================

# Coupling thresholds for DSM analysis
HIGH_COUPLING_THRESHOLD = 20  # Headers with coupling above this are highlighted as critical
MODERATE_COUPLING_THRESHOLD = 10  # Moderate coupling threshold
LOW_COUPLING_THRESHOLD = 5  # Low coupling threshold

# Matrix display defaults
DEFAULT_TOP_N = 30  # Default number of headers to show in DSM matrix
MAX_DSM_DISPLAY = 100  # Maximum headers to display in matrix

# Matrix visualization symbols
CYCLE_HIGHLIGHT = "●"  # Symbol for headers in cycles
DEPENDENCY_MARKER = "X"  # Symbol for dependencies in matrix
EMPTY_CELL = "·"  # Symbol for no dependency

# Architecture health thresholds (matrix sparsity %)
SPARSITY_HEALTHY = 95.0  # Above this = healthy (low coupling)
SPARSITY_MODERATE = 90.0  # Above this = moderate coupling
# Below SPARSITY_MODERATE = highly coupled

# =============================================================================
# Dependency Hell Analysis Constants
# =============================================================================

# Dependency thresholds
DEFAULT_DEPENDENCY_THRESHOLD = 50  # Default threshold for "dependency hell"
DEFAULT_TOP_N_DEPS = 10  # Default number of top headers to show
FANOUT_THRESHOLD = 5  # Minimum fanout to highlight

# Severity levels (number of dependencies)
SEVERITY_CRITICAL = 500  # Critical dependency count
SEVERITY_HIGH = 300  # High dependency count
SEVERITY_MODERATE = 100  # Moderate dependency count

# =============================================================================
# Include Chain Analysis Constants
# =============================================================================

MAX_AMBIGUOUS_DISPLAY = 10  # Maximum ambiguous inclusions to display
MIN_COOCCURRENCE_THRESHOLD = 2  # Minimum cooccurrence count to consider

# =============================================================================
# Performance Constants
# =============================================================================

# Timeouts (seconds)
CLANG_SCAN_DEPS_TIMEOUT = 300  # Timeout for clang-scan-deps
GIT_COMMAND_TIMEOUT = 30  # Timeout for git commands
NINJA_COMMAND_TIMEOUT = 60  # Timeout for ninja commands

# Parallel processing
DEFAULT_MAX_WORKERS = None  # None = use all CPU cores

# =============================================================================
# Display Limits
# =============================================================================

MAX_HEADERS_DISPLAY = 50  # Maximum headers to show in various listings
MAX_CYCLES_DISPLAY = 20  # Maximum cycles to display
MAX_LAYERS_DISPLAY = 10  # Maximum layers to display
MAX_RECOMMENDATIONS = 5  # Maximum recommendations to show

# =============================================================================
# File Size Limits
# =============================================================================

MAX_OUTPUT_SIZE_KB = 1024  # Maximum size for output files before warning (KB)
TRUNCATE_OUTPUT_KB = 60  # Truncate terminal output after this size (KB)

# =============================================================================
# Build System Constants
# =============================================================================

COMPILE_COMMANDS_JSON = "compile_commands.json"  # Standard compilation database filename

# =============================================================================
# Cache Constants
# =============================================================================

CACHE_DIR = ".buildcheck_cache"  # Cache directory name in build directory
CLANG_SCAN_DEPS_CACHE_FILE = "clang_scan_deps_output.pickle"  # Cached clang-scan-deps output
MAX_CACHE_AGE_HOURS = 168  # Maximum cache age in hours (7 days)

# =============================================================================
# Graph Export Constants
# =============================================================================

SUPPORTED_GRAPH_FORMATS = [".graphml", ".dot", ".gexf", ".json"]
DEFAULT_GRAPH_FORMAT = "graphml"

# =============================================================================
# Color Severity Mapping
# =============================================================================

# These map to Colors class attributes in color_utils.py
COLOR_CRITICAL = "RED"
COLOR_HIGH = "YELLOW"
COLOR_MODERATE = "CYAN"
COLOR_LOW = "GREEN"
COLOR_INFO = "WHITE"
COLOR_DIM = "DIM"
COLOR_BRIGHT = "BRIGHT"

# =============================================================================
# Additional Exit Codes
# =============================================================================

EXIT_NINJA_FAILED = 2  # Ninja command failed or not found
EXIT_UNEXPECTED = 1  # Unexpected error occurred

# =============================================================================
# Exception Classes
# =============================================================================


class BuildCheckError(Exception):
    """Base exception for all buildCheck errors.

    All buildCheck exceptions carry an exit_code attribute that indicates
    what exit code the program should use when this error is caught at the
    main entry point.
    """

    def __init__(self, message: str, exit_code: int = EXIT_RUNTIME_ERROR):
        super().__init__(message)
        self.exit_code = exit_code


# Validation errors (EXIT_INVALID_ARGS)
class ValidationError(BuildCheckError):
    """Raised when input validation fails (arguments, paths, etc)."""

    def __init__(self, message: str):
        super().__init__(message, EXIT_INVALID_ARGS)


class BuildDirectoryError(ValidationError):
    """Raised when build directory is invalid or inaccessible."""


class ArgumentError(ValidationError):
    """Raised when command-line arguments are invalid."""


class GitRepositoryError(ValidationError):
    """Raised when git repository validation fails."""


# External tool errors
class ExternalToolError(BuildCheckError):
    """Raised when external tools (ninja, clang, git) fail."""

    def __init__(self, message: str, exit_code: int = EXIT_RUNTIME_ERROR):  # pylint: disable=useless-parent-delegation
        super().__init__(message, exit_code)


class NinjaError(ExternalToolError):
    """Raised when ninja command fails or is not found."""

    def __init__(self, message: str):  # pylint: disable=useless-parent-delegation
        super().__init__(message, EXIT_NINJA_FAILED)


class ClangError(ExternalToolError):
    """Raised when clang-scan-deps or other clang tools fail."""


# Analysis/processing errors (EXIT_RUNTIME_ERROR)
class AnalysisError(BuildCheckError):
    """Raised when analysis or processing operations fail."""


class GraphBuildError(AnalysisError):
    """Raised when dependency graph construction fails."""


class DependencyAnalysisError(AnalysisError):
    """Raised when dependency analysis fails."""
