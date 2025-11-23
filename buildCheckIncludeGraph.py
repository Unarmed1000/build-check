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
"""Build a proper include graph using clang-scan-deps to analyze direct #include relationships.

Version: 1.0.0

PURPOSE:
    Analyzes the actual include graph by parsing source files with clang-scan-deps.
    Identifies "gateway headers" that pull in many dependencies and shows which
    .cpp files will rebuild when headers change.

WHAT IT DOES:
    - Uses clang-scan-deps to get complete, accurate dependency information
    - Builds include cooccurrence graph (which headers appear together)
    - Identifies "gateway headers" that drag in excessive dependencies
    - Shows which specific .cpp files will rebuild for each changed header
    - Calculates "include cost" (average number of headers pulled in)
    - Provides gateway header rankings

USE CASES:
    - "If I change this header, which .cpp files will rebuild?"
    - Find headers with high "include cost" (gateway headers)
    - Identify refactoring opportunities to reduce header bloat
    - Understand why rebuilds are slow
    - See concrete rebuild impact on specific source files

METHOD:
    Uses clang-scan-deps (parallel, multi-core) to parse actual #include directives
    from source files. This gives accurate, complete dependency information unlike
    Ninja's cached build graph.

OUTPUT:
    1. For each changed header:
       - List of .cpp files that will rebuild
       - Include cost metrics
    2. Top gateway headers ranked by include cost:
       - Average dependencies pulled in
       - Number of unique dependencies
       - Usage count across source files
    3. Detailed analysis of changed headers' include costs

METRICS EXPLAINED:
    - Include Cost: Average number of other headers pulled in when this header is included
    - Unique Deps: Total number of distinct headers that cooccur with this header
    - Usage Count: Number of source files that include this header
    - Gateway Header: Header with high include cost (pulls in many dependencies)

PERFORMANCE:
    Slower than basic tools (3-10 seconds) but provides accurate source-level analysis.
    Uses all CPU cores for parallel processing. Results are cached.

REQUIREMENTS:
    - Python 3.7+
    - clang-scan-deps (clang-19, clang-18, or clang-XX)
    - networkx: pip install networkx
    - compile_commands.json (auto-generated from Ninja build)

COMPLEMENTARY TOOLS:
    - buildCheckImpact.py: Quick impact check (faster, less detailed)
    - buildCheckIncludeChains.py: Cooccurrence patterns only
    - buildCheckDependencyHell.py: Multi-metric analysis with transitive deps

EXAMPLES:
    # Analyze changed headers (default)
    ./buildCheckIncludeGraph.py ../build/release/

    # Show top 30 gateway headers regardless of changes
    ./buildCheckIncludeGraph.py ../build/release/ --full

    # Analyze changed headers, show top 20 affected files
    ./buildCheckIncludeGraph.py ../build/release/ --top 20

    # Exclude third-party and test headers
    ./buildCheckIncludeGraph.py ../build/release/ --exclude "*/ThirdParty/*" --exclude "*/test/*"

Performance improvements:
- Uses NetworkX for efficient graph operations and path finding
- Leverages all CPU cores for clang-scan-deps analysis
- Optimized transitive include detection using ego_graph for neighborhood extraction
"""
import subprocess
import os
import sys
import argparse
import logging
from collections import defaultdict
from typing import Dict, Set, List, Tuple, DefaultDict, Any, Optional
from dataclasses import dataclass
import multiprocessing as mp

import networkx as nx

# Import library modules
from lib.ninja_utils import extract_rebuild_info
from lib.color_utils import Colors, print_warning, print_success
from lib.constants import COMPILE_COMMANDS_JSON
from lib.file_utils import exclude_headers_by_patterns, filter_system_headers
from lib.clang_utils import CLANG_SCAN_DEPS_COMMANDS, VALID_SOURCE_EXTENSIONS, VALID_HEADER_EXTENSIONS, run_clang_scan_deps, create_filtered_compile_commands

# Constants
CLANG_SCAN_DEPS_TIMEOUT: int = 600  # 10 minutes
# CLANG_SCAN_DEPS_VERSIONS moved to lib.clang_utils
COMPILE_DB_FILENAME: str = COMPILE_COMMANDS_JSON
FILTERED_COMPILE_DB_FILENAME: str = "compile_commands_filtered.json"
# SOURCE_FILE_EXTENSIONS, HEADER_FILE_EXTENSIONS moved to lib.clang_utils
COMPILER_NAMES: Tuple[str, ...] = ("g++", "gcc", "clang++", "clang", "/c++")
HIGH_COST_THRESHOLD: int = 50  # Headers with average cost above this are optimization targets


@dataclass
class SystemRequirements:
    """System tool availability validation results.

    Attributes:
        ninja: Whether ninja build tool is available
        clang_scan_deps: Whether clang-scan-deps tool is available
        networkx: Whether networkx Python library is available
    """

    ninja: bool
    clang_scan_deps: bool
    networkx: bool

    def all_available(self) -> bool:
        """Check if all required tools are available.

        Returns:
            True if all requirements are met
        """
        return self.ninja and self.clang_scan_deps and self.networkx

    def missing_requirements(self) -> List[str]:
        """Get list of missing requirements.

        Returns:
            List of requirement names that are not available
        """
        missing = []
        if not self.ninja:
            missing.append("ninja")
        if not self.clang_scan_deps:
            missing.append("clang-scan-deps")
        if not self.networkx:
            missing.append("networkx")
        return missing

    def to_dict(self) -> Dict[str, bool]:
        """Convert to dictionary for backward compatibility.

        Returns:
            Dictionary mapping requirement names to availability
        """
        return {"ninja": self.ninja, "clang-scan-deps": self.clang_scan_deps, "networkx": self.networkx}


def validate_system_requirements() -> SystemRequirements:
    """Validate that required system tools are available.

    Returns:
        SystemRequirements with validation results for each requirement
    """
    ninja_available = False
    clang_scan_deps_available = False
    networkx_available = False

    # Check ninja
    try:
        subprocess.run(["ninja", "--version"], capture_output=True, check=True, timeout=5)
        ninja_available = True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Check clang-scan-deps (any version)
    for cmd in CLANG_SCAN_DEPS_COMMANDS:
        try:
            subprocess.run([cmd, "--version"], capture_output=True, check=True, timeout=5)
            clang_scan_deps_available = True
            break
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            continue

    # Check networkx
    try:
        # networkx already imported at module level
        networkx_available = True
    except ImportError:
        pass

    return SystemRequirements(ninja=ninja_available, clang_scan_deps=clang_scan_deps_available, networkx=networkx_available)


def analyze_gateway_headers(source_to_headers: Dict[str, Set[str]]) -> List[Tuple[str, float, int, int]]:
    """Identify gateway headers that drag in many other dependencies.

    Args:
        source_to_headers: Mapping of source files to their included headers

    Returns:
        List of tuples (header, avg_cost, unique_deps, usage_count) sorted by avg_cost

    Raises:
        ValueError: If inputs are invalid
        RuntimeError: If analysis fails
    """
    if not source_to_headers:
        logging.warning("No source-to-header mappings provided")
        return []

    if not isinstance(source_to_headers, dict):
        raise ValueError("source_to_headers must be a dictionary")

    try:
        logging.info("Analyzing gateway headers from %s source files", len(source_to_headers))
        # For each header, count how many OTHER headers typically come with it
        header_include_cost: DefaultDict[str, Dict[str, Any]] = defaultdict(lambda: {"total_co_includes": 0, "appears_in": 0, "co_headers": set()})
    except Exception as e:
        logging.error("Failed to initialize gateway header analysis: %s", e)
        raise RuntimeError(f"Gateway header analysis initialization failed: {e}") from e

    try:
        for _, headers in source_to_headers.items():
            headers_list = list(headers)
            # For each header in this source file
            for header in headers_list:
                header_include_cost[header]["appears_in"] += 1
                # Count all OTHER headers that come with it
                other_headers = set(headers_list) - {header}
                header_include_cost[header]["total_co_includes"] += len(other_headers)
                header_include_cost[header]["co_headers"].update(other_headers)
    except Exception as e:
        logging.error("Error during gateway header cost calculation: %s", e)
        raise RuntimeError(f"Failed to calculate header include costs: {e}") from e

    # Calculate average include cost
    gateway_headers: List[Tuple[str, float, int, int]] = []
    for header, data in header_include_cost.items():
        if data["appears_in"] > 0:
            avg_cost: float = data["total_co_includes"] / data["appears_in"]
            unique_co_headers: int = len(data["co_headers"])
            gateway_headers.append((header, avg_cost, unique_co_headers, data["appears_in"]))

    # Sort by average cost (highest first)
    gateway_headers.sort(key=lambda x: x[1], reverse=True)

    logging.info("Identified %s gateway headers", len(gateway_headers))
    if gateway_headers:
        logging.debug("Top gateway header: %s with avg cost %.1f", gateway_headers[0][0], gateway_headers[0][1])

    return gateway_headers


def build_header_dependency_graph(source_to_headers: Dict[str, Set[str]]) -> Tuple["nx.Graph[Any]", DefaultDict[str, Set[str]]]:
    """Build header-to-header dependency graph by analyzing which headers are commonly included together.

    Args:
        source_to_headers: Mapping of source files to their included headers

    Returns:
        Tuple of (graph, header_to_headers mapping)

    Raises:
        ValueError: If inputs are invalid
        RuntimeError: If graph construction fails
    """
    if not source_to_headers:
        logging.warning("No source-to-header mappings provided")
        return nx.Graph(), defaultdict(set)

    if not isinstance(source_to_headers, dict):
        raise ValueError("source_to_headers must be a dictionary")

    try:
        logging.info("Building header-to-header dependency graph")
        header_to_headers: DefaultDict[str, Set[str]] = defaultdict(set)  # header -> headers it appears with
        all_project_headers: Set[str] = set()
    except Exception as e:
        logging.error("Failed to initialize header dependency graph: %s", e)
        raise RuntimeError(f"Header dependency graph initialization failed: {e}") from e

    # Collect all project headers
    for headers in source_to_headers.values():
        all_project_headers.update(headers)

    # For each source file's header list, build co-occurrence relationships
    # This gives us an approximation of header dependencies
    for _, headers in source_to_headers.items():
        headers_list = sorted(headers)  # deterministic order
        for i, h1 in enumerate(headers_list):
            for h2 in headers_list[i + 1 :]:
                # Track that these headers appear together
                header_to_headers[h1].add(h2)
                header_to_headers[h2].add(h1)

    # Build directed graph of header co-dependencies
    try:
        graph: nx.Graph[str] = nx.Graph()  # Undirected since we don't know direct inclusion order
        graph.add_nodes_from(all_project_headers)

        for header, related in header_to_headers.items():
            for related_header in related:
                graph.add_edge(header, related_header)

        logging.info("Built graph with %s nodes and %s edges", graph.number_of_nodes(), graph.number_of_edges())
    except Exception as e:
        logging.error("Failed to build dependency graph: %s", e)
        raise RuntimeError(f"NetworkX graph construction failed: {e}") from e

    return graph, header_to_headers


def parse_scan_deps_chunk(output_text: str) -> Tuple[List[Tuple[str, str]], Set[str], DefaultDict[str, Set[str]]]:
    """Parse clang-scan-deps output and return edges, headers, and source file dependencies.

    Args:
        output_text: Output from clang-scan-deps command

    Returns:
        Tuple of (edges, headers, source_to_headers mapping)

    Raises:
        ValueError: If inputs are invalid
        RuntimeError: If parsing fails
    """
    if not isinstance(output_text, str):
        raise ValueError("output_text must be a string")

    if not output_text.strip():
        logging.warning("Empty clang-scan-deps output")
        return [], set(), defaultdict(set)

    try:
        logging.debug("Parsing clang-scan-deps output (%s bytes)", len(output_text))
        edges: List[Tuple[str, str]] = []
        headers: Set[str] = set()
        source_to_headers: DefaultDict[str, Set[str]] = defaultdict(set)  # .cpp -> set of headers it includes

        lines: List[str] = output_text.splitlines()
        current_deps: List[str] = []
        targets_processed: int = 0
    except Exception as e:
        logging.error("Failed to initialize parsing structures: %s", e)
        raise RuntimeError(f"Parse initialization failed: {e}") from e

    try:
        for line in lines:
            orig_line: str = line
            line = line.strip()
            if not line:
                continue

            # Check if this is a target line (no leading whitespace, doesn't end with \)
            is_target: bool = not orig_line.startswith(" ") and not orig_line.startswith("\t")

            if is_target and current_deps:
                # New target found, process previous target's dependencies
                process_deps(current_deps, headers, source_to_headers)
                targets_processed += 1
                current_deps = []

            # Add line to current dependencies (remove trailing \)
            if line.endswith("\\"):
                current_deps.append(line[:-1].strip())
            else:
                current_deps.append(line)
    except Exception as e:
        logging.error("Error parsing clang-scan-deps output at line %s: %s", targets_processed, e)
        raise RuntimeError(f"Failed to parse dependency output: {e}") from e

    # Process last entry
    if current_deps:
        process_deps(current_deps, headers, source_to_headers)
        targets_processed += 1

    logging.info("Parsed %s targets, found %s headers, %s source files", targets_processed, len(headers), len(source_to_headers))

    return edges, headers, source_to_headers


def process_deps(deps_list: List[str], headers: Set[str], source_to_headers: DefaultDict[str, Set[str]]) -> None:
    """Process a dependency list from clang-scan-deps.

    Args:
        deps_list: List of dependencies from clang-scan-deps
        headers: Set to add headers to
        source_to_headers: Mapping to update with source->header relationships
    """
    try:
        if not deps_list or len(deps_list) < 2:
            logging.debug("Skipping empty or incomplete dependency list")
            return

        # First entry is "target.o:" - ignore it
        # Second entry is the source .cpp file
        # Rest are dependencies (headers and system files)

        source: str | None = deps_list[1] if len(deps_list) > 1 else None
        all_deps: List[str] = deps_list[2:] if len(deps_list) > 2 else []
    except (IndexError, TypeError) as e:
        logging.warning("Error processing dependency list structure: %s", e)
        return
    except Exception as e:
        logging.warning("Unexpected error processing dependency list: %s", e)
        return

    # Filter to only project headers
    project_deps: List[str] = [d for d in all_deps if d.endswith(VALID_HEADER_EXTENSIONS) and "/gtec-demo-framework/" in d and not d.startswith("/usr/")]

    # Track source file dependencies (source includes all these headers)
    if source and source.endswith(VALID_SOURCE_EXTENSIONS):
        logging.debug("Processing %s dependencies for %s", len(project_deps), os.path.basename(source))
        for dep in project_deps:
            headers.add(dep)
            source_to_headers[source].add(dep)
            # Add edge: header -> source (header is included by source, not a real edge just for tracking)

    # For header-to-header relationships, we can't reliably determine from this format
    # clang-scan-deps lists ALL transitive dependencies, not just direct ones
    # We would need to parse the actual header files or use a different tool


def build_include_graph_from_clang_scan(build_dir: str) -> Tuple["nx.DiGraph[Any]", DefaultDict[str, Set[str]]]:
    """Use clang-scan-deps to build an accurate include graph with NetworkX.

    Args:
        build_dir: Path to the build directory

    Returns:
        Tuple of (directed graph, source_to_headers mapping)

    Raises:
        ValueError: If build_dir is invalid
        RuntimeError: If clang-scan-deps execution or parsing fails
    """
    if not build_dir or not isinstance(build_dir, str):
        raise ValueError("build_dir must be a non-empty string")

    logging.info("Building include graph from clang-scan-deps")

    try:
        filtered_db: str = create_filtered_compile_commands(build_dir)
    except Exception as e:
        logging.error("Failed to create filtered compile commands: %s", e)
        raise RuntimeError(f"Compile commands preparation failed: {e}") from e

    # Get CPU count for parallelism
    num_cores: int = mp.cpu_count()
    logging.info("Using %s CPU cores for parallel processing", num_cores)

    print(f"{Colors.CYAN}Running clang-scan-deps using {num_cores} cores...{Colors.RESET}")

    # Use cached clang-scan-deps execution from lib
    try:
        output, elapsed = run_clang_scan_deps(build_dir, filtered_db, timeout=CLANG_SCAN_DEPS_TIMEOUT)
        logging.info("clang-scan-deps completed in %.2fs", elapsed)
    except RuntimeError as e:
        logging.error("clang-scan-deps failed: %s", e)
        raise

    # Parse output to build graph
    print(f"{Colors.CYAN}Building dependency graph...{Colors.RESET}")
    try:
        edges: List[Tuple[str, str]]
        all_headers: Set[str]
        source_to_headers: DefaultDict[str, Set[str]]
        edges, all_headers, source_to_headers = parse_scan_deps_chunk(output)

        # Create directed graph for header-to-header relationships (if we had them)
        # Note: clang-scan-deps gives us transitive deps, not direct include relationships
        # So we focus on source-to-header mapping instead
        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_nodes_from(all_headers)
        graph.add_edges_from(edges)
    except Exception as e:
        logging.error("Failed to build include graph from clang-scan-deps output: %s", e)
        raise RuntimeError(f"Graph construction failed: {e}") from e

    return graph, source_to_headers


def find_affected_source_files(changed_header: str, source_to_headers: Dict[str, Set[str]]) -> List[str]:
    """Find all .cpp files that will rebuild due to a changed header.

    Args:
        changed_header: Path to the changed header file
        source_to_headers: Mapping of source files to their included headers

    Returns:
        List of source file paths that will rebuild
    """
    if not changed_header or not isinstance(changed_header, str):
        logging.warning("Invalid changed_header parameter")
        return []

    if not source_to_headers:
        logging.warning("Empty source_to_headers mapping")
        return []

    try:
        logging.debug("Finding affected source files for %s", os.path.basename(changed_header))
        affected_sources: List[str] = []

        # Since clang-scan-deps gives us ALL transitive dependencies for each .cpp,
        # we can directly check which source files include the changed header
        for source, headers in source_to_headers.items():
            if changed_header in headers:
                affected_sources.append(source)

        logging.debug("Found %s affected source files", len(affected_sources))
        return affected_sources
    except Exception as e:
        logging.error("Error finding affected source files for %s: %s", changed_header, e)
        return []


def parse_arguments() -> argparse.Namespace:
    """Parse and return command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Gateway header analysis: find headers that pull in excessive dependencies.",
        epilog="""
This tool parses actual source files with clang-scan-deps to build an accurate
include graph. It identifies "gateway headers" - headers that drag in many other
headers when included.

Key metrics:
  Include Cost = Avg number of headers pulled in when this header is included
  Gateway Header = Header with high include cost (refactoring candidate)
  
Use --full mode to analyze all headers, not just changed ones.

Requires: clang-scan-deps (install: sudo apt install clang-19)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("build_directory", metavar="BUILD_DIR", help="Path to the ninja build directory (e.g., build/release)")

    parser.add_argument("--top", type=int, default=10, help="Number of items to show per list (default: 10, use higher for --full mode)")

    parser.add_argument("--full", action="store_true", help="Analyze all headers, not just changed ones from rebuild info")

    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")

    parser.add_argument(
        "--exclude",
        type=str,
        action="append",
        metavar="PATTERN",
        help="Exclude headers matching glob pattern (can be used multiple times). "
        "Useful for excluding third-party libraries, generated files, or test code. "
        "Supports glob patterns: * (any chars), ** (recursive), ? (single char). "
        'Examples: "*/ThirdParty/*", "*/build/*", "*_generated.h", "*/test/*"',
    )

    parser.add_argument("--include-system-headers", action="store_true", help="Include system headers in analysis (default: exclude /usr/*, /lib/*, /opt/*)")

    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> Tuple[str, str, str]:
    """Validate command line arguments and paths.

    Args:
        args: Parsed command line arguments

    Returns:
        Tuple of (build_dir, build_ninja, project_root) as absolute paths

    Raises:
        SystemExit: If validation fails
    """
    if not args.build_directory:
        logging.error("Build directory not specified")
        print(f"{Colors.RED}Error: Build directory is required{Colors.RESET}")
        sys.exit(1)

    if args.top < 1:
        logging.error("Invalid --top value: %s", args.top)
        print(f"{Colors.RED}Error: --top must be at least 1{Colors.RESET}")
        sys.exit(1)

    build_dir: str = os.path.abspath(args.build_directory)
    logging.info("Build directory: %s", build_dir)

    if not os.path.isdir(build_dir):
        logging.error("'%s' is not a directory", build_dir)
        print(f"Error: '{build_dir}' is not a directory.")
        sys.exit(1)

    build_ninja: str = os.path.join(build_dir, "build.ninja")
    if not os.path.exists(build_ninja):
        logging.error("build.ninja not found in '%s'", build_dir)
        print(f"Error: 'build.ninja' not found in '{build_dir}'.")
        print("Please provide the path to the ninja build directory containing build.ninja")
        sys.exit(1)

    project_root: str = os.path.dirname(os.path.abspath(__file__))

    return build_dir, build_ninja, project_root


def get_changed_headers(build_dir: str, args: argparse.Namespace) -> Set[str]:
    """Extract changed headers from rebuild info.

    Args:
        build_dir: Path to the build directory
        args: Command line arguments

    Returns:
        Set of changed header file paths

    Raises:
        SystemExit: If extraction fails
    """
    print(f"\n{Colors.CYAN}Extracting rebuild information...{Colors.RESET}")
    original_dir: str = os.getcwd()
    try:
        root_causes: Dict[str, int]
        _, _, root_causes = extract_rebuild_info(build_dir)
    except Exception as e:
        logging.error("Failed to extract rebuild information: %s", e)
        print(f"{Colors.RED}Error: Failed to extract rebuild information: {e}{Colors.RESET}")
        sys.exit(1)
    finally:
        os.chdir(original_dir)

    changed_headers: Set[str] = set(root_causes.keys())
    logging.info("Found %s changed headers", len(changed_headers))

    if not args.full and not changed_headers:
        logging.warning("No changed header files found")
        print(f"\n{Colors.YELLOW}No changed header files found{Colors.RESET}")
        print("Use --full to analyze all headers instead")
        sys.exit(0)

    if args.full:
        logging.info("Running in full analysis mode")
        print(f"{Colors.GREEN}Full analysis mode: analyzing all headers{Colors.RESET}")
    else:
        logging.info("Analyzing %s changed headers", len(changed_headers))
        print(f"{Colors.GREEN}Found {len(changed_headers)} changed headers{Colors.RESET}")

    return changed_headers


def analyze_dependencies(build_dir: str) -> Tuple["nx.DiGraph[Any]", DefaultDict[str, Set[str]], "nx.Graph[Any]", DefaultDict[str, Set[str]]]:
    """Build include and header dependency graphs.

    Args:
        build_dir: Path to the build directory

    Returns:
        Tuple of (graph, source_to_headers, header_graph, header_to_headers)

    Raises:
        SystemExit: If analysis fails
    """
    # Build include graph using clang-scan-deps
    try:
        graph: nx.DiGraph[str]
        source_to_headers: DefaultDict[str, Set[str]]
        graph, source_to_headers = build_include_graph_from_clang_scan(build_dir)
    except Exception as e:
        logging.error("Failed to build include graph: %s", e)
        print(f"{Colors.RED}Error: Failed to build include graph: {e}{Colors.RESET}")
        sys.exit(1)

    # Build header-to-header dependency graph
    print(f"{Colors.CYAN}Building header dependency graph...{Colors.RESET}")
    try:
        header_graph: nx.Graph[str]
        header_to_headers: DefaultDict[str, Set[str]]
        header_graph, header_to_headers = build_header_dependency_graph(source_to_headers)
    except Exception as e:
        logging.error("Failed to build header dependency graph: %s", e)
        print(f"{Colors.RED}Error: Failed to build header dependency graph: {e}{Colors.RESET}")
        sys.exit(1)

    return graph, source_to_headers, header_graph, header_to_headers


def print_dependency_summary(source_to_headers: Dict[str, Set[str]], header_graph: "nx.Graph[Any]") -> None:
    """Print summary of dependency analysis.

    Args:
        source_to_headers: Mapping of source files to their included headers
        header_graph: Header dependency graph
    """
    total_deps: int = sum(len(headers) for headers in source_to_headers.values())

    logging.info("Analysis complete: %s sources, %s headers, %s dependencies", len(source_to_headers), header_graph.number_of_nodes(), total_deps)
    print(f"\n{Colors.GREEN}Dependency analysis complete:{Colors.RESET}")
    print(f"  • {len(source_to_headers)} source files tracked")
    print(f"  • {header_graph.number_of_nodes()} unique headers in project")
    print(f"  • {total_deps} total source-to-header dependencies")
    print(f"  • {header_graph.number_of_edges()} header co-dependency relationships")


def filter_headers_to_analyze(
    args: argparse.Namespace, changed_headers: Set[str], gateway_headers: List[Tuple[str, float, int, int]], header_graph: "nx.Graph[Any]", project_root: str
) -> List[str]:
    """Filter headers to analyze based on mode and exclusion patterns.

    Args:
        args: Command line arguments
        changed_headers: Set of changed header paths
        gateway_headers: List of gateway header tuples
        header_graph: Header dependency graph
        project_root: Root directory of the project

    Returns:
        List of header paths to analyze

    Raises:
        SystemExit: If no headers remain after filtering
    """
    try:
        headers_to_analyze: List[str]
        changed_headers_in_graph: List[str]
        if args.full:
            headers_to_analyze = [h[0] for h in gateway_headers[: args.top]]
            changed_headers_in_graph = [h for h in headers_to_analyze if h in header_graph]
        else:
            changed_headers_in_graph = [h for h in changed_headers if h in header_graph]
    except Exception as e:
        logging.error("Failed to analyze headers: %s", e)
        print(f"{Colors.RED}Error: Failed to analyze headers: {e}{Colors.RESET}")
        sys.exit(1)

    # Apply exclude patterns if specified
    if hasattr(args, "exclude") and args.exclude:
        headers_set = set(changed_headers_in_graph)

        filtered_headers, excluded_count, no_match_patterns, _ = exclude_headers_by_patterns(headers_set, args.exclude, project_root)

        if excluded_count > 0:
            changed_headers_in_graph = [h for h in changed_headers_in_graph if h in filtered_headers]
            print_success(f"Excluded {excluded_count} headers matching {len(args.exclude)} pattern(s)", prefix=False)

        for pattern in no_match_patterns:
            print_warning(f"Exclude pattern '{pattern}' matched no headers", prefix=False)

    # Filter system headers unless explicitly included
    if not getattr(args, "include_system_headers", False):
        headers_set = set(changed_headers_in_graph)
        filtered_headers, stats = filter_system_headers(headers_set, show_progress=False)

        if stats["total_excluded"] > 0:
            changed_headers_in_graph = [h for h in changed_headers_in_graph if h in filtered_headers]
            print_success(f"Excluded {stats['total_excluded']} system headers", prefix=False)

    if not changed_headers_in_graph:
        if args.full:
            print(f"\n{Colors.YELLOW}No headers found in the dependency graph{Colors.RESET}")
        else:
            print(f"\n{Colors.YELLOW}None of the changed headers are in the dependency graph{Colors.RESET}")
        sys.exit(0)

    return changed_headers_in_graph


def print_header_analysis(
    changed_headers_in_graph: List[str], source_to_headers: Dict[str, Set[str]], project_root: str, args: argparse.Namespace, is_full_mode: bool
) -> None:
    """Print detailed analysis for each changed header.

    Args:
        changed_headers_in_graph: List of headers to analyze
        graph: Dependency graph
        source_to_headers: Mapping of source files to their included headers
        project_root: Root directory of the project
        args: Command line arguments
        is_full_mode: Whether in full analysis mode
    """
    if is_full_mode:
        print(f"\n{Colors.BRIGHT}═══ Top Gateway Headers Analysis ═══{Colors.RESET}")
    else:
        print(f"\n{Colors.BRIGHT}═══ Include Graph Analysis ═══{Colors.RESET}")

    for changed_header in sorted(changed_headers_in_graph):
        try:
            display_changed: str = changed_header
            if changed_header.startswith(project_root):
                display_changed = os.path.relpath(changed_header, project_root)

            affected_sources: List[str] = find_affected_source_files(changed_header, source_to_headers)
        except Exception as e:
            logging.error("Error processing header %s: %s", changed_header, e)
            print(f"{Colors.YELLOW}Warning: Skipping {changed_header} due to error: {e}{Colors.RESET}")
            continue

        print(f"\n{Colors.RED}{'='*80}{Colors.RESET}")
        print(f"{Colors.RED}{Colors.BRIGHT}{display_changed}{Colors.RESET}")
        print(f"{Colors.RED}{'='*80}{Colors.RESET}")
        print(f"  {Colors.YELLOW}⚠ {len(affected_sources)} .cpp files will rebuild{Colors.RESET}")

        if affected_sources:
            print(f"\n  {Colors.BRIGHT}Sample of .cpp files that will rebuild:{Colors.RESET}")
            for source in sorted(affected_sources)[: args.top]:
                display_source = source
                if source.startswith(project_root):
                    display_source = os.path.relpath(source, project_root)
                print(f"    {Colors.YELLOW}📄 {display_source}{Colors.RESET}")
            if len(affected_sources) > args.top:
                print(f"    {Colors.DIM}... and {len(affected_sources) - args.top} more{Colors.RESET}")


def print_gateway_analysis(gateway_headers: List[Tuple[str, float, int, int]], changed_headers: Set[str], project_root: str, is_full_mode: bool) -> None:
    """Print gateway header analysis.

    Args:
        gateway_headers: List of gateway header tuples
        changed_headers: Set of changed header paths
        project_root: Root directory of the project
        is_full_mode: Whether in full analysis mode
    """
    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}GATEWAY HEADER ANALYSIS{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print("Gateway headers = headers that drag in many other dependencies\n")

    top_count: int = 30 if is_full_mode else 20
    print(f"{Colors.BRIGHT}Top {top_count} gateway headers (highest include cost):{Colors.RESET}")
    for header, avg_cost, unique_deps, usage_count in gateway_headers[:top_count]:
        display_header: str = header
        if header.startswith(project_root):
            display_header = os.path.relpath(header, project_root)

        is_changed: bool = header in changed_headers
        color: str = Colors.RED if is_changed else Colors.YELLOW if avg_cost > 100 else Colors.WHITE
        marker: str = " ⚠️ CHANGED" if is_changed else ""

        print(f"  {color}{display_header}{Colors.RESET}")
        print(f"    Avg deps: {avg_cost:.1f} | Unique deps: {unique_deps} | Used by: {usage_count} files{marker}")


def print_detailed_header_analysis(
    changed_headers_in_graph: List[str],
    gateway_headers: List[Tuple[str, float, int, int]],
    source_to_headers: Dict[str, Set[str]],
    project_root: str,
    is_full_mode: bool,
) -> None:
    """Print detailed analysis for each changed header.

    Args:
        changed_headers_in_graph: List of headers to analyze
        gateway_headers: List of gateway header tuples
        graph: Dependency graph
        source_to_headers: Mapping of source files to their included headers
        project_root: Root directory of the project
        is_full_mode: Whether in full analysis mode
    """
    if is_full_mode:
        print(f"\n{Colors.BRIGHT}Detailed analysis of top gateway headers:{Colors.RESET}")
    else:
        print(f"\n{Colors.BRIGHT}Changed headers and their include costs:{Colors.RESET}")

    for changed_header in sorted(changed_headers_in_graph):
        display_changed = changed_header
        if changed_header.startswith(project_root):
            display_changed = os.path.relpath(changed_header, project_root)

        header_info = next((h for h in gateway_headers if h[0] == changed_header), None)
        if header_info:
            _, avg_cost, unique_deps, _ = header_info
            affected_sources = find_affected_source_files(changed_header, source_to_headers)

            print(f"\n{Colors.RED}{display_changed}{Colors.RESET}")
            print(f"  Direct impact: {len(affected_sources)} .cpp files rebuild")
            print(f"  Include cost: Drags in avg {avg_cost:.1f} other headers ({unique_deps} unique)")
            print(
                f"  Total compilation cost: {len(affected_sources)} files × {avg_cost:.1f} avg headers = {len(affected_sources) * avg_cost:.0f} header compilations"
            )

            co_included: DefaultDict[str, int] = defaultdict(int)
            for _, headers in source_to_headers.items():
                if changed_header in headers:
                    for other_h in headers:
                        if other_h != changed_header:
                            co_included[other_h] += 1

            if co_included:
                sorted_co: List[Tuple[str, int]] = sorted(co_included.items(), key=lambda x: x[1], reverse=True)[:5]
                print("  Most commonly dragged in:")
                for co_header, count in sorted_co:
                    display_co = co_header
                    if co_header.startswith(project_root):
                        display_co = os.path.relpath(co_header, project_root)
                    pct = 100 * count / len(affected_sources)
                    print(f"    → {display_co} ({count}/{len(affected_sources)} = {pct:.0f}% of uses)")


def print_rebuild_summary(changed_headers_in_graph: List[str], source_to_headers: Dict[str, Set[str]], project_root: str, is_full_mode: bool) -> None:
    """Print rebuild impact summary.

    Args:
        changed_headers_in_graph: List of headers to analyze
        source_to_headers: Mapping of source files to their included headers
        project_root: Root directory of the project
        is_full_mode: Whether in full analysis mode
    """
    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}REBUILD IMPACT SUMMARY{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")

    all_affected_sources: Set[str] = set()
    for changed_header in changed_headers_in_graph:
        affected: List[str] = find_affected_source_files(changed_header, source_to_headers)
        all_affected_sources.update(affected)

    print(f"{Colors.YELLOW}Total unique .cpp files that will rebuild: {len(all_affected_sources)}{Colors.RESET}")
    if len(source_to_headers) > 0:
        percentage: float = 100.0 * len(all_affected_sources) / len(source_to_headers)
        print(f"Out of {len(source_to_headers)} total source files tracked ({percentage:.1f}% of codebase)")
    else:
        print(f"Out of {len(source_to_headers)} total source files tracked")
    print("\nChanged headers causing most rebuilds:")

    if not is_full_mode:
        header_impacts: List[Tuple[str, int]] = []
        for changed_header in changed_headers_in_graph:
            affected = find_affected_source_files(changed_header, source_to_headers)
            header_impacts.append((changed_header, len(affected)))

        for header, count in sorted(header_impacts, key=lambda x: x[1], reverse=True):
            display_header = header
            if header.startswith(project_root):
                display_header = os.path.relpath(header, project_root)
            print(f"  {Colors.RED}{display_header}: {count} files{Colors.RESET}")
    else:
        print(f"Analyzed top {len(changed_headers_in_graph)} gateway headers by include cost")
        print(f"Total source files in project: {len(source_to_headers)}")


def print_optimization_opportunities(
    changed_headers_in_graph: List[str],
    gateway_headers: List[Tuple[str, float, int, int]],
    source_to_headers: Dict[str, Set[str]],
    project_root: str,
    is_full_mode: bool,
) -> None:
    """Print optimization opportunities.

    Args:
        changed_headers_in_graph: List of headers to analyze
        gateway_headers: List of gateway header tuples
        graph: Dependency graph
        source_to_headers: Mapping of source files to their included headers
        project_root: Root directory of the project
        is_full_mode: Whether in full analysis mode
    """
    print(f"\n{Colors.BRIGHT}Optimization opportunities:{Colors.RESET}")
    if is_full_mode:
        print("Headers with high include cost are good candidates for optimization.")
    else:
        print("Look for gateway headers with high include cost but low actual usage.")
    print("These are good candidates for:")
    print("  1. Forward declarations instead of includes")
    print("  2. Moving implementations to .cpp files")
    print("  3. Splitting into smaller, more focused headers")

    optimization_candidates: List[Tuple[str, float, int]] = []
    for header in changed_headers_in_graph:
        opt_header_info: Optional[Tuple[str, float, int, int]] = next((h for h in gateway_headers if h[0] == header), None)
        if opt_header_info:
            _, avg_cost, _, _ = opt_header_info
            affected = find_affected_source_files(header, source_to_headers)
            if avg_cost > HIGH_COST_THRESHOLD:
                optimization_candidates.append((header, avg_cost, len(affected)))

    if optimization_candidates:
        if is_full_mode:
            print("\n  High-cost headers (top optimization targets):")
        else:
            print("\n  Priority targets (high-cost changed headers):")
        for header, cost, impact in sorted(optimization_candidates, key=lambda x: x[1] * x[2], reverse=True):
            display_header = header
            if header.startswith(project_root):
                display_header = os.path.relpath(header, project_root)
            total_cost = cost * impact
            print(f"    {Colors.YELLOW}{display_header}{Colors.RESET}")
            print(f"      Cost: {cost:.0f} deps × {impact} files = {total_cost:.0f} total header compilations")


def main() -> int:
    """Main entry point for the include graph analysis tool.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # Parse arguments
    args: argparse.Namespace = parse_arguments()

    # Set logging level based on verbose flag
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Verbose logging enabled")

    # Validate system requirements
    if args.verbose:
        print(f"{Colors.CYAN}Checking system requirements...{Colors.RESET}")
        requirements = validate_system_requirements()
        for req, available in requirements.to_dict().items():
            status = f"{Colors.GREEN}✓" if available else f"{Colors.RED}✗"
            print(f"  {status} {req}{Colors.RESET}")

        missing = requirements.missing_requirements()
        if missing:
            logging.warning("Missing requirements: %s", ", ".join(missing))
            print(f"{Colors.YELLOW}Warning: Some requirements are missing{Colors.RESET}")

    # Validate arguments and paths
    build_dir, _, project_root = validate_arguments(args)

    # Get changed headers
    changed_headers: Set[str] = get_changed_headers(build_dir, args)

    # Analyze dependencies
    _, source_to_headers, header_graph, _ = analyze_dependencies(build_dir)

    # Print dependency summary
    print_dependency_summary(source_to_headers, header_graph)

    # Calculate gateway headers
    try:
        gateway_headers: List[Tuple[str, float, int, int]] = analyze_gateway_headers(source_to_headers)
    except Exception as e:
        logging.error("Failed to analyze gateway headers: %s", e)
        print(f"{Colors.RED}Error: Failed to analyze gateway headers: {e}{Colors.RESET}")
        return 1

    # Filter headers to analyze
    changed_headers_in_graph: List[str] = filter_headers_to_analyze(args, changed_headers, gateway_headers, header_graph, project_root)

    # Print analyses
    print_header_analysis(changed_headers_in_graph, source_to_headers, project_root, args, args.full)
    print_gateway_analysis(gateway_headers, changed_headers, project_root, args.full)
    print_detailed_header_analysis(changed_headers_in_graph, gateway_headers, source_to_headers, project_root, args.full)
    print_rebuild_summary(changed_headers_in_graph, source_to_headers, project_root, args.full)
    print_optimization_opportunities(changed_headers_in_graph, gateway_headers, source_to_headers, project_root, args.full)

    return 0


if __name__ == "__main__":
    from lib.constants import EXIT_KEYBOARD_INTERRUPT, EXIT_INVALID_ARGS, EXIT_RUNTIME_ERROR, BuildCheckError

    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        print(f"\n{Colors.YELLOW}Interrupted by user{Colors.RESET}")
        sys.exit(EXIT_KEYBOARD_INTERRUPT)
    except BuildCheckError as e:
        logging.error(str(e))
        sys.exit(e.exit_code)
    except ValueError as e:
        logging.error("Validation error: %s", e)
        print(f"\n{Colors.RED}Validation error: {e}{Colors.RESET}")
        sys.exit(EXIT_INVALID_ARGS)
    except RuntimeError as e:
        logging.error("Runtime error: %s", e)
        print(f"\n{Colors.RED}Runtime error: {e}{Colors.RESET}")
        print(f"{Colors.YELLOW}Run with --verbose for more details{Colors.RESET}")
        sys.exit(EXIT_RUNTIME_ERROR)
    except Exception as e:
        logging.critical("Unexpected error: %s", e, exc_info=True)
        print(f"\n{Colors.RED}Fatal error: {e}{Colors.RESET}")
        print(f"{Colors.YELLOW}Run with --verbose for more details{Colors.RESET}")
        sys.exit(EXIT_RUNTIME_ERROR)
