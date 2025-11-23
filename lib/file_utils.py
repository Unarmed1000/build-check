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
"""File and path utilities for filtering and manipulating file paths."""

import os
import fnmatch
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Set, List, Dict, DefaultDict, Tuple, Optional, Any

from .clang_utils import is_system_header, SYSTEM_PATH_PREFIXES
from .color_utils import Colors, print_info

logger = logging.getLogger(__name__)


@dataclass
class FilterStatistics:
    """Statistics about header filtering operations.

    Tracks filtering at each stage: system headers, library filters,
    pattern filters, and exclude patterns. Provides formatted output
    for both concise and verbose reporting.

    Attributes:
        initial_count: Number of headers before any filtering
        final_count: Number of headers after all filtering
        system_headers: System header statistics by prefix
        exclude_patterns: Exclude pattern statistics by pattern
        filter_pattern: Pattern filter statistics (optional)
        library_filter: Library filter statistics (optional)
    """

    initial_count: int
    final_count: int
    system_headers: Dict[str, Any] = field(default_factory=dict)
    exclude_patterns: Dict[str, Any] = field(default_factory=dict)
    filter_pattern: Optional[Dict[str, Any]] = None
    library_filter: Optional[Dict[str, Any]] = None

    def format_concise(self) -> str:
        """Format concise single-line summary.

        Returns:
            Formatted string like "2,500 → 1,234 | Excluded: 243 system, 89 patterns, 934 outside filter"
        """
        parts = [f"{Colors.CYAN}{self.initial_count:,}{Colors.RESET} → {Colors.CYAN}{self.final_count:,}{Colors.RESET}"]

        excluded_parts = []

        # System headers
        if self.system_headers and self.system_headers.get("total_excluded", 0) > 0:
            count = self.system_headers["total_excluded"]
            excluded_parts.append(f"{Colors.CYAN}{count}{Colors.RESET} {Colors.DIM}system{Colors.RESET}")

        # Exclude patterns
        if self.exclude_patterns and self.exclude_patterns.get("total_excluded", 0) > 0:
            count = self.exclude_patterns["total_excluded"]
            excluded_parts.append(f"{Colors.CYAN}{count}{Colors.RESET} {Colors.DIM}by patterns{Colors.RESET}")

        # Filter pattern (calculated as reduction)
        if self.filter_pattern and self.filter_pattern.get("reduced_by", 0) > 0:
            count = self.filter_pattern["reduced_by"]
            excluded_parts.append(f"{Colors.CYAN}{count}{Colors.RESET} {Colors.DIM}outside filter{Colors.RESET}")

        # Library filter (calculated as reduction)
        if self.library_filter and self.library_filter.get("reduced_by", 0) > 0:
            count = self.library_filter["reduced_by"]
            excluded_parts.append(f"{Colors.CYAN}{count}{Colors.RESET} {Colors.DIM}outside library{Colors.RESET}")

        if excluded_parts:
            parts.append(f"| {Colors.DIM}Excluded:{Colors.RESET} " + ", ".join(excluded_parts))

        return " ".join(parts)

    def format_verbose(self, project_root: str) -> str:
        """Format verbose multi-line detailed breakdown.

        Args:
            project_root: Project root directory for relative paths

        Returns:
            Multi-line formatted string with detailed statistics
        """
        lines = []

        # System headers breakdown
        if self.system_headers and self.system_headers.get("total_excluded", 0) > 0:
            lines.append(f"\n{Colors.BRIGHT}System Headers Excluded:{Colors.RESET}")
            lines.append(f"  Total: {Colors.CYAN}{self.system_headers['total_excluded']}{Colors.RESET}")

            by_prefix = self.system_headers.get("by_prefix", {})
            # Sort by count descending, take top 3
            sorted_prefixes = sorted(by_prefix.items(), key=lambda x: x[1]["count"], reverse=True)[:3]

            for prefix, info in sorted_prefixes:
                count = info["count"]
                examples = info.get("examples", [])
                if examples:
                    example_str = ", ".join(examples[:5])
                    lines.append(f"  {prefix}: {Colors.CYAN}{count}{Colors.RESET} {Colors.DIM}({example_str}){Colors.RESET}")
                else:
                    lines.append(f"  {prefix}: {Colors.CYAN}{count}{Colors.RESET}")

        # Exclude patterns breakdown
        if self.exclude_patterns and self.exclude_patterns.get("total_excluded", 0) > 0:
            lines.append(f"\n{Colors.BRIGHT}Excluded by Patterns:{Colors.RESET}")
            lines.append(f"  Total: {Colors.CYAN}{self.exclude_patterns['total_excluded']}{Colors.RESET}")

            by_pattern = self.exclude_patterns.get("by_pattern", {})
            for pattern, info in sorted(by_pattern.items()):
                count = info["count"]
                examples = info.get("examples", [])
                if examples:
                    # Convert to relative paths
                    rel_examples = []
                    for ex in examples[:3]:
                        rel_path = os.path.relpath(ex, project_root) if ex.startswith(project_root) else ex
                        rel_examples.append(rel_path)
                    example_str = ", ".join(rel_examples)
                    lines.append(f"  '{pattern}': {Colors.CYAN}{count}{Colors.RESET} {Colors.DIM}({example_str}){Colors.RESET}")
                else:
                    lines.append(f"  '{pattern}': {Colors.CYAN}{count}{Colors.RESET}")

        # Filter pattern info
        if self.filter_pattern:
            lines.append(f"\n{Colors.BRIGHT}Pattern Filter:{Colors.RESET}")
            lines.append(f"  Pattern: '{self.filter_pattern.get('pattern', 'N/A')}'")
            lines.append(f"  Matched: {Colors.CYAN}{self.filter_pattern.get('matched', 0)}{Colors.RESET}")

        # Library filter info
        if self.library_filter:
            lines.append(f"\n{Colors.BRIGHT}Library Filter:{Colors.RESET}")
            lines.append(f"  Library: '{self.library_filter.get('library', 'N/A')}'")
            lines.append(f"  Matched: {Colors.CYAN}{self.library_filter.get('matched', 0)}{Colors.RESET}")

        return "\n".join(lines)


def filter_system_headers(headers: Set[str], show_progress: bool = False) -> Tuple[Set[str], Dict[str, Any]]:
    """Filter out system headers from header set.

    Categorizes excluded system headers by prefix and collects example paths.

    Args:
        headers: Set of header paths
        show_progress: Show progress message for large header sets (>5000 headers)

    Returns:
        Tuple of (filtered_headers, statistics_dict)
        - filtered_headers: Headers with system headers removed
        - statistics_dict: {"total_excluded": int, "by_prefix": {prefix: {"count": int, "examples": List[str]}}}
    """
    if show_progress and len(headers) > 5000:
        print_info("Filtering system headers...")

    filtered_headers: Set[str] = set()
    excluded_by_prefix: DefaultDict[str, List[str]] = defaultdict(list)

    for header in headers:
        if is_system_header(header):
            # Find which prefix matches
            for prefix in SYSTEM_PATH_PREFIXES:
                if header.startswith(prefix):
                    # Store up to 5 examples per prefix (just basenames)
                    if len(excluded_by_prefix[prefix]) < 5:
                        excluded_by_prefix[prefix].append(os.path.basename(header))
                    else:
                        # Still count but don't store more examples
                        excluded_by_prefix[prefix].append("")  # Placeholder for counting
                    break
        else:
            filtered_headers.add(header)

    # Build statistics dict
    total_excluded = len(headers) - len(filtered_headers)
    by_prefix = {}

    for prefix, examples_list in excluded_by_prefix.items():
        # Filter out empty placeholders and get actual examples
        actual_examples = [ex for ex in examples_list if ex][:5]
        by_prefix[prefix] = {"count": len(examples_list), "examples": actual_examples}

    stats = {"total_excluded": total_excluded, "by_prefix": by_prefix}

    logger.info("Filtered %d system headers from %d total headers", total_excluded, len(headers))

    return filtered_headers, stats


def filter_headers_by_pattern(headers: Set[str], pattern: str, project_root: str) -> Set[str]:
    """Filter headers by glob pattern.

    Args:
        headers: Set of header paths
        pattern: Glob pattern (e.g., "FslBase/*")
        project_root: Root directory of the project

    Returns:
        Filtered set of headers matching pattern
    """
    filtered: Set[str] = set()

    for header in headers:
        rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
        if fnmatch.fnmatch(rel_path, pattern):
            filtered.add(header)

    return filtered


def exclude_headers_by_patterns(headers: Set[str], exclude_patterns: List[str], project_root: str) -> tuple[Set[str], int, List[str], Dict[str, Any]]:
    """Exclude headers matching any of the provided glob patterns.

    Args:
        headers: Set of header paths
        exclude_patterns: List of glob patterns to exclude (e.g., ["*/ThirdParty/*", "*/test/*"])
        project_root: Root directory of the project

    Returns:
        Tuple of (filtered_headers, excluded_count, patterns_with_no_matches, statistics_dict)
        - filtered_headers: Set of headers after exclusions
        - excluded_count: Number of headers excluded
        - patterns_with_no_matches: List of patterns that matched no headers
        - statistics_dict: {"total_excluded": int, "by_pattern": {pattern: {"count": int, "examples": List[str]}}}
    """
    if not exclude_patterns:
        return headers, 0, [], {}

    filtered: Set[str] = set()
    pattern_match_counts: Dict[str, int] = {pattern: 0 for pattern in exclude_patterns}
    pattern_examples: DefaultDict[str, List[str]] = defaultdict(list)

    for header in headers:
        rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header

        # Check if header matches any exclude pattern
        excluded = False
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                excluded = True
                pattern_match_counts[pattern] += 1
                # Store up to 3 examples per pattern
                if len(pattern_examples[pattern]) < 3:
                    pattern_examples[pattern].append(header)
                break

        if not excluded:
            filtered.add(header)

    excluded_count = len(headers) - len(filtered)
    patterns_with_no_matches = [pattern for pattern, count in pattern_match_counts.items() if count == 0]

    logger.info("Excluded %s headers using %s patterns", excluded_count, len(exclude_patterns))
    for pattern, count in pattern_match_counts.items():
        logger.debug("Pattern '%s' matched %s headers", pattern, count)

    # Build statistics dict
    by_pattern = {}
    for pattern in exclude_patterns:
        if pattern_match_counts[pattern] > 0:
            by_pattern[pattern] = {"count": pattern_match_counts[pattern], "examples": pattern_examples[pattern]}

    stats = {"total_excluded": excluded_count, "by_pattern": by_pattern}

    return filtered, excluded_count, patterns_with_no_matches, stats


def cluster_headers_by_directory(headers: List[str], project_root: str) -> Dict[str, List[str]]:
    """Group headers by their parent directory.

    Args:
        headers: List of header paths
        project_root: Root directory of the project

    Returns:
        Dictionary mapping directory names to lists of headers
    """
    clusters: DefaultDict[str, List[str]] = defaultdict(list)

    for header in headers:
        rel_path = os.path.relpath(header, project_root) if header.startswith(project_root) else header
        parent_dir = os.path.dirname(rel_path)

        # Use top-level directory as cluster name
        parts = parent_dir.split(os.sep)
        cluster_name = parts[0] if parts and parts[0] else "root"

        clusters[cluster_name].append(header)

    return dict(clusters)
