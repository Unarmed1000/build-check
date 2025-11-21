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

Performance improvements:
- Uses NetworkX for efficient graph operations and path finding
- Leverages all CPU cores for clang-scan-deps analysis
- Optimized transitive include detection using ego_graph for neighborhood extraction
"""
import subprocess
import re
import os
import sys
import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import networkx as nx
from typing import Dict, Set, List, Tuple, DefaultDict, Any

try:
    from colorama import Fore, Style, init
    init(autoreset=False)
except ImportError:
    class Fore:
        RED = YELLOW = GREEN = BLUE = MAGENTA = CYAN = WHITE = LIGHTBLACK_EX = RESET = ''
    class Style:
        RESET_ALL = BRIGHT = DIM = ''

# Constants
CLANG_SCAN_DEPS_TIMEOUT: int = 600  # 10 minutes
CLANG_SCAN_DEPS_VERSIONS: List[str] = ['clang-scan-deps-19', 'clang-scan-deps-18', 'clang-scan-deps']
COMPILE_DB_FILENAME: str = 'compile_commands.json'
FILTERED_COMPILE_DB_FILENAME: str = 'compile_commands_filtered.json'
SOURCE_FILE_EXTENSIONS: Tuple[str, ...] = ('.cpp', '.c', '.cc', '.cxx')
HEADER_FILE_EXTENSIONS: Tuple[str, ...] = ('.h', '.hpp', '.hxx')
COMPILER_NAMES: Tuple[str, ...] = ('g++', 'gcc', 'clang++', 'clang', '/c++')
HIGH_COST_THRESHOLD: int = 50  # Headers with average cost above this are optimization targets

# Import helper function from buildCheckSummary
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from buildCheckSummary import extract_rebuild_info
except ImportError:
    try:
        from buildCheckSummary import extract_rebuild_info
    except ImportError as e:
        print(f"Error: Could not import extract_rebuild_info from buildCheckSummary or buildCheckSummary: {e}", file=sys.stderr)
        sys.exit(1)


def validate_system_requirements() -> Dict[str, bool]:
    """Validate that required system tools are available.
    
    Returns:
        Dictionary with validation results for each requirement
    """
    requirements: Dict[str, bool] = {
        'ninja': False,
        'clang-scan-deps': False,
        'networkx': False,
    }
    
    # Check ninja
    try:
        subprocess.run(['ninja', '--version'], capture_output=True, check=True, timeout=5)
        requirements['ninja'] = True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Check clang-scan-deps (any version)
    for cmd in CLANG_SCAN_DEPS_VERSIONS:
        try:
            subprocess.run([cmd, '--version'], capture_output=True, check=True, timeout=5)
            requirements['clang-scan-deps'] = True
            break
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            continue
    
    # Check networkx
    try:
        import networkx
        requirements['networkx'] = True
    except ImportError:
        pass
    
    return requirements


def create_filtered_compile_commands(build_dir: str) -> str:
    """Create a filtered compile_commands.json with only C/C++ compilation entries.
    
    Args:
        build_dir: Path to the build directory containing build.ninja
        
    Returns:
        Path to the filtered compile_commands.json file
        
    Raises:
        ValueError: If build_dir is invalid
        RuntimeError: If compilation database generation fails
    """
    if not build_dir or not isinstance(build_dir, str):
        raise ValueError("build_dir must be a non-empty string")
    
    logging.info(f"Creating filtered compile commands for build directory: {build_dir}")
    build_dir: str = os.path.realpath(os.path.abspath(build_dir))
    
    if not os.path.isdir(build_dir):
        raise ValueError(f"Build directory does not exist: {build_dir}")
    
    compile_db: str = os.path.realpath(os.path.join(build_dir, COMPILE_DB_FILENAME))
    filtered_db: str = os.path.realpath(os.path.join(build_dir, FILTERED_COMPILE_DB_FILENAME))
    build_ninja: str = os.path.realpath(os.path.join(build_dir, 'build.ninja'))
    
    # Validate paths are within build_dir (prevent path traversal)
    for path in [compile_db, filtered_db, build_ninja]:
        if not path.startswith(build_dir + os.sep):
            raise ValueError(f"Path traversal detected: {path}")
    
    # Check if compile_commands.json needs regeneration (if build.ninja is newer)
    try:
        if os.path.exists(build_ninja) and os.path.exists(compile_db):
            if os.path.getmtime(build_ninja) > os.path.getmtime(compile_db):
                logging.warning("build.ninja is newer than compile_commands.json - regenerating")
                print(f"{Fore.YELLOW}build.ninja is newer than compile_commands.json - regenerating{Style.RESET_ALL}")
                os.remove(compile_db)
                # Also remove filtered DB to force full regeneration
                if os.path.exists(filtered_db):
                    os.remove(filtered_db)
    except OSError as e:
        logging.error(f"Failed to check or remove compilation database files: {e}")
        raise RuntimeError(f"File operation failed: {e}") from e
    
    # Check if filtered DB exists and is newer than both build.ninja and compile_commands.json
    try:
        if os.path.exists(filtered_db):
            filtered_mtime: float = os.path.getmtime(filtered_db)
            rebuild_needed: bool = False
            
            if os.path.exists(build_ninja) and os.path.getmtime(build_ninja) > filtered_mtime:
                rebuild_needed = True
            if os.path.exists(compile_db) and os.path.getmtime(compile_db) > filtered_mtime:
                rebuild_needed = True
                
            if not rebuild_needed:
                logging.info("Using cached filtered compile database")
                print(f"{Fore.GREEN}Using cached filtered compile database{Style.RESET_ALL}")
                return filtered_db
    except OSError as e:
        logging.warning(f"Failed to check filtered DB timestamps: {e}. Will regenerate.")
    
    # Generate if compile_commands.json doesn't exist
    if not os.path.exists(compile_db):
        logging.info("Generating compile_commands.json from ninja")
        print(f"{Fore.CYAN}Generating compile_commands.json...{Style.RESET_ALL}")
        try:
            result = subprocess.run(
                ["ninja", "-t", "compdb"],
                capture_output=True,
                text=True,
                cwd=build_dir,
                check=True
            )
            with open(compile_db, 'w') as f:
                f.write(result.stdout)
            logging.debug(f"Generated compile_commands.json with {len(result.stdout)} bytes")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to generate compile_commands.json: {e}")
            raise RuntimeError(f"ninja compdb failed: {e.stderr}") from e
        except IOError as e:
            logging.error(f"Failed to write compile_commands.json: {e}")
            raise RuntimeError(f"Failed to write compilation database: {e}") from e
        except FileNotFoundError:
            logging.error("ninja command not found")
            raise RuntimeError("ninja not found. Please ensure ninja is installed and in PATH.") from None
    
    # Filter to valid C/C++ entries
    logging.info("Filtering compilation database")
    print(f"{Fore.CYAN}Filtering compilation database...{Style.RESET_ALL}")
    try:
        with open(compile_db, 'r') as f:
            data: List[Dict[str, Any]] = json.load(f)
        logging.debug(f"Loaded {len(data)} entries from compile_commands.json")
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in compile_commands.json: {e}")
        raise RuntimeError(f"Failed to parse compile_commands.json: {e}") from e
    except IOError as e:
        logging.error(f"Failed to read compile_commands.json: {e}")
        raise RuntimeError(f"Failed to read compilation database: {e}") from e
    
    valid_entries: List[Dict[str, Any]] = []
    for entry in data:
        cmd = entry.get('command', '')
        file = entry.get('file', '')
        
        # Must be a source file with a compilation command (has -c flag)
        if any(ext in file for ext in SOURCE_FILE_EXTENSIONS) and \
           any(compiler in cmd for compiler in COMPILER_NAMES) and \
           ' -c ' in cmd:
            valid_entries.append(entry)
    
    try:
        with open(filtered_db, 'w') as f:
            json.dump(valid_entries, f, indent=2)
    except IOError as e:
        logging.error(f"Failed to write filtered database: {e}")
        raise RuntimeError(f"Failed to write filtered compilation database: {e}") from e
    
    logging.info(f"Filtered {len(data)} → {len(valid_entries)} entries")
    print(f"{Fore.GREEN}Filtered {len(data)} → {len(valid_entries)} entries{Style.RESET_ALL}")
    return filtered_db


def analyze_gateway_headers(source_to_headers: Dict[str, Set[str]], project_root: str) -> List[Tuple[str, float, int, int]]:
    """Identify gateway headers that drag in many other dependencies.
    
    Args:
        source_to_headers: Mapping of source files to their included headers
        project_root: Root directory of the project
        
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
        logging.info(f"Analyzing gateway headers from {len(source_to_headers)} source files")
        # For each header, count how many OTHER headers typically come with it
        header_include_cost: DefaultDict[str, Dict[str, Any]] = defaultdict(lambda: {'total_co_includes': 0, 'appears_in': 0, 'co_headers': set()})
    except Exception as e:
        logging.error(f"Failed to initialize gateway header analysis: {e}")
        raise RuntimeError(f"Gateway header analysis initialization failed: {e}") from e
    
    try:
        for source, headers in source_to_headers.items():
            headers_list = list(headers)
            # For each header in this source file
            for header in headers_list:
                header_include_cost[header]['appears_in'] += 1
                # Count all OTHER headers that come with it
                other_headers = set(headers_list) - {header}
                header_include_cost[header]['total_co_includes'] += len(other_headers)
                header_include_cost[header]['co_headers'].update(other_headers)
    except Exception as e:
        logging.error(f"Error during gateway header cost calculation: {e}")
        raise RuntimeError(f"Failed to calculate header include costs: {e}") from e
    
    # Calculate average include cost
    gateway_headers: List[Tuple[str, float, int, int]] = []
    for header, data in header_include_cost.items():
        if data['appears_in'] > 0:
            avg_cost: float = data['total_co_includes'] / data['appears_in']
            unique_co_headers: int = len(data['co_headers'])
            gateway_headers.append((header, avg_cost, unique_co_headers, data['appears_in']))
    
    # Sort by average cost (highest first)
    gateway_headers.sort(key=lambda x: x[1], reverse=True)
    
    logging.info(f"Identified {len(gateway_headers)} gateway headers")
    if gateway_headers:
        logging.debug(f"Top gateway header: {gateway_headers[0][0]} with avg cost {gateway_headers[0][1]:.1f}")
    
    return gateway_headers


def build_header_dependency_graph(source_to_headers: Dict[str, Set[str]], project_root: str) -> Tuple[nx.Graph, DefaultDict[str, Set[str]]]:
    """Build header-to-header dependency graph by analyzing which headers are commonly included together.
    
    Args:
        source_to_headers: Mapping of source files to their included headers
        project_root: Root directory of the project
        
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
        logging.error(f"Failed to initialize header dependency graph: {e}")
        raise RuntimeError(f"Header dependency graph initialization failed: {e}") from e
    
    # Collect all project headers
    for headers in source_to_headers.values():
        all_project_headers.update(headers)
    
    # For each source file's header list, build co-occurrence relationships
    # This gives us an approximation of header dependencies
    for source, headers in source_to_headers.items():
        headers_list = sorted(headers)  # deterministic order
        for i, h1 in enumerate(headers_list):
            for h2 in headers_list[i+1:]:
                # Track that these headers appear together
                header_to_headers[h1].add(h2)
                header_to_headers[h2].add(h1)
    
    # Build directed graph of header co-dependencies
    try:
        graph: nx.Graph = nx.Graph()  # Undirected since we don't know direct inclusion order
        graph.add_nodes_from(all_project_headers)
        
        for header, related in header_to_headers.items():
            for related_header in related:
                graph.add_edge(header, related_header)
        
        logging.info(f"Built graph with {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges")
    except Exception as e:
        logging.error(f"Failed to build dependency graph: {e}")
        raise RuntimeError(f"NetworkX graph construction failed: {e}") from e
    
    return graph, header_to_headers


def parse_scan_deps_chunk(output_text: str, project_root: str) -> Tuple[List[Tuple[str, str]], Set[str], DefaultDict[str, Set[str]]]:
    """Parse clang-scan-deps output and return edges, headers, and source file dependencies.
    
    Args:
        output_text: Output from clang-scan-deps command
        project_root: Root directory of the project
        
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
        logging.debug(f"Parsing clang-scan-deps output ({len(output_text)} bytes)")
        edges: List[Tuple[str, str]] = []
        headers: Set[str] = set()
        source_to_headers: DefaultDict[str, Set[str]] = defaultdict(set)  # .cpp -> set of headers it includes
        
        lines: List[str] = output_text.splitlines()
        current_deps: List[str] = []
        targets_processed: int = 0
    except Exception as e:
        logging.error(f"Failed to initialize parsing structures: {e}")
        raise RuntimeError(f"Parse initialization failed: {e}") from e
    
    try:
        for line in lines:
            orig_line: str = line
            line = line.strip()
            if not line:
                continue
            
            # Check if this is a target line (no leading whitespace, doesn't end with \)
            is_target: bool = not orig_line.startswith(' ') and not orig_line.startswith('\t')
            
            if is_target and current_deps:
                # New target found, process previous target's dependencies
                process_deps(current_deps, edges, headers, source_to_headers)
                targets_processed += 1
                current_deps = []
            
            # Add line to current dependencies (remove trailing \)
            if line.endswith('\\'):
                current_deps.append(line[:-1].strip())
            else:
                current_deps.append(line)
    except Exception as e:
        logging.error(f"Error parsing clang-scan-deps output at line {targets_processed}: {e}")
        raise RuntimeError(f"Failed to parse dependency output: {e}") from e
    
    # Process last entry
    if current_deps:
        process_deps(current_deps, edges, headers, source_to_headers)
        targets_processed += 1
    
    logging.info(f"Parsed {targets_processed} targets, found {len(headers)} headers, {len(source_to_headers)} source files")
    
    return edges, headers, source_to_headers


def process_deps(deps_list: List[str], edges: List[Tuple[str, str]], headers: Set[str], source_to_headers: DefaultDict[str, Set[str]]) -> None:
    """Process a dependency list from clang-scan-deps.
    
    Args:
        deps_list: List of dependencies from clang-scan-deps
        edges: List to append edges to
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
        logging.warning(f"Error processing dependency list structure: {e}")
        return
    except Exception as e:
        logging.warning(f"Unexpected error processing dependency list: {e}")
        return
    
    # Filter to only project headers
    project_deps: List[str] = [
        d for d in all_deps 
        if d.endswith(HEADER_FILE_EXTENSIONS) 
        and '/gtec-demo-framework/' in d
        and not d.startswith('/usr/')
    ]
    
    # Track source file dependencies (source includes all these headers)
    if source and source.endswith(SOURCE_FILE_EXTENSIONS):
        logging.debug(f"Processing {len(project_deps)} dependencies for {os.path.basename(source)}")
        for dep in project_deps:
            headers.add(dep)
            source_to_headers[source].add(dep)
            # Add edge: header -> source (header is included by source, not a real edge just for tracking)
    
    # For header-to-header relationships, we can't reliably determine from this format
    # clang-scan-deps lists ALL transitive dependencies, not just direct ones
    # We would need to parse the actual header files or use a different tool


def build_include_graph_from_clang_scan(build_dir: str) -> Tuple[nx.DiGraph, DefaultDict[str, Set[str]]]:
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
        logging.error(f"Failed to create filtered compile commands: {e}")
        raise RuntimeError(f"Compile commands preparation failed: {e}") from e
    
    # Get CPU count for parallelism
    num_cores: int = mp.cpu_count()
    logging.info(f"Using {num_cores} CPU cores for parallel processing")
    
    print(f"{Fore.CYAN}Running clang-scan-deps using {num_cores} cores...{Style.RESET_ALL}")
    
    # Run clang-scan-deps with parallel jobs
    # Try multiple versions of clang-scan-deps
    clang_cmd: str | None = None
    for cmd in CLANG_SCAN_DEPS_VERSIONS:
        try:
            subprocess.run([cmd, "--version"], capture_output=True, check=True, timeout=5)
            clang_cmd = cmd
            logging.info(f"Found {cmd}")
            break
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            continue
    
    if not clang_cmd:
        logging.error("No clang-scan-deps found")
        versions_str = ', '.join(CLANG_SCAN_DEPS_VERSIONS)
        raise RuntimeError(
            f"clang-scan-deps not found. Please install one of: {versions_str}\n"
            "Ubuntu/Debian: sudo apt install clang-19\n"
            "Fedora: sudo dnf install clang-tools-extra"
        )
    
    logging.info(f"Executing {clang_cmd}")
    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            [clang_cmd, "-compilation-database=" + filtered_db, "-format=make", "-j", str(num_cores)],
            capture_output=True,
            text=True,
            cwd=build_dir,
            timeout=CLANG_SCAN_DEPS_TIMEOUT
        )
        logging.debug(f"{clang_cmd} completed with return code {result.returncode}")
    except subprocess.TimeoutExpired:
        timeout_minutes = CLANG_SCAN_DEPS_TIMEOUT // 60
        logging.error(f"{clang_cmd} timed out after {timeout_minutes} minutes")
        raise RuntimeError(
            f"{clang_cmd} timed out after {timeout_minutes} minutes. "
            "The project may be too large or clang is hanging."
        ) from None
    except FileNotFoundError:
        logging.error(f"{clang_cmd} not found after version check")
        raise RuntimeError(f"{clang_cmd} disappeared. This should not happen.") from None
    except Exception as e:
        logging.error(f"Failed to run {clang_cmd}: {e}")
        raise RuntimeError(f"{clang_cmd} execution failed: {e}") from e
    
    if result.returncode != 0:
        logging.warning(f"clang-scan-deps had errors (return code {result.returncode})")
        print(f"{Fore.YELLOW}Warning: clang-scan-deps had some errors (possibly missing dependencies like OpenCV){Style.RESET_ALL}")
        if result.stderr:
            logging.debug(f"clang-scan-deps stderr: {result.stderr[:500]}...")
            # Show first few errors but continue
            error_lines = result.stderr.split('\n')[:10]
            for line in error_lines:
                if line.strip():
                    print(f"  {Fore.LIGHTBLACK_EX}{line}{Style.RESET_ALL}")
            if len(result.stderr.split('\n')) > 10:
                print(f"  {Fore.LIGHTBLACK_EX}... (additional errors omitted){Style.RESET_ALL}")
        print(f"{Fore.CYAN}Continuing with partial results...{Style.RESET_ALL}")
    
    project_root: str = os.path.dirname(os.path.abspath(__file__))
    
    # Parse output to build graph
    print(f"{Fore.CYAN}Building dependency graph...{Style.RESET_ALL}")
    try:
        edges: List[Tuple[str, str]]
        all_headers: Set[str]
        source_to_headers: DefaultDict[str, Set[str]]
        edges, all_headers, source_to_headers = parse_scan_deps_chunk(result.stdout, project_root)
        
        # Create directed graph for header-to-header relationships (if we had them)
        # Note: clang-scan-deps gives us transitive deps, not direct include relationships
        # So we focus on source-to-header mapping instead
        graph: nx.DiGraph = nx.DiGraph()
        graph.add_nodes_from(all_headers)
        graph.add_edges_from(edges)
    except Exception as e:
        logging.error(f"Failed to build include graph from clang-scan-deps output: {e}")
        raise RuntimeError(f"Graph construction failed: {e}") from e
    
    return graph, source_to_headers


def find_affected_source_files(changed_header: str, graph: nx.DiGraph, source_to_headers: Dict[str, Set[str]], project_root: str) -> List[str]:
    """Find all .cpp files that will rebuild due to a changed header.
    
    Args:
        changed_header: Path to the changed header file
        graph: Dependency graph
        source_to_headers: Mapping of source files to their included headers
        project_root: Root directory of the project
        
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
        logging.debug(f"Finding affected source files for {os.path.basename(changed_header)}")
        affected_sources: List[str] = []
        
        # Since clang-scan-deps gives us ALL transitive dependencies for each .cpp,
        # we can directly check which source files include the changed header
        for source, headers in source_to_headers.items():
            if changed_header in headers:
                affected_sources.append(source)
        
        logging.debug(f"Found {len(affected_sources)} affected source files")
        return affected_sources
    except Exception as e:
        logging.error(f"Error finding affected source files for {changed_header}: {e}")
        return []


def main() -> None:
    """Main entry point for the include graph analysis tool."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description='Gateway header analysis: find headers that pull in excessive dependencies.',
        epilog='''
This tool parses actual source files with clang-scan-deps to build an accurate
include graph. It identifies "gateway headers" - headers that drag in many other
headers when included.

Key metrics:
  Include Cost = Avg number of headers pulled in when this header is included
  Gateway Header = Header with high include cost (refactoring candidate)
  
Use --full mode to analyze all headers, not just changed ones.

Requires: clang-scan-deps (install: sudo apt install clang-19)
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'build_directory',
        metavar='BUILD_DIR',
        help='Path to the ninja build directory (e.g., build/release)'
    )
    
    parser.add_argument(
        '--top',
        type=int,
        default=10,
        help='Number of items to show per list (default: 10, use higher for --full mode)'
    )
    
    parser.add_argument(
        '--full',
        action='store_true',
        help='Analyze all headers, not just changed ones from rebuild info'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose debug logging'
    )
    
    args: argparse.Namespace = parser.parse_args()
    
    # Set logging level based on verbose flag
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Verbose logging enabled")
    
    # Validate system requirements
    if args.verbose:
        print(f"{Fore.CYAN}Checking system requirements...{Style.RESET_ALL}")
        requirements = validate_system_requirements()
        for req, available in requirements.items():
            status = f"{Fore.GREEN}✓" if available else f"{Fore.RED}✗"
            print(f"  {status} {req}{Style.RESET_ALL}")
        
        missing = [req for req, available in requirements.items() if not available]
        if missing:
            logging.warning(f"Missing requirements: {', '.join(missing)}")
            print(f"{Fore.YELLOW}Warning: Some requirements are missing{Style.RESET_ALL}")
    
    # Validate arguments
    if not args.build_directory:
        logging.error("Build directory not specified")
        print(f"{Fore.RED}Error: Build directory is required{Style.RESET_ALL}")
        sys.exit(1)
    
    if args.top < 1:
        logging.error(f"Invalid --top value: {args.top}")
        print(f"{Fore.RED}Error: --top must be at least 1{Style.RESET_ALL}")
        sys.exit(1)
    
    build_dir: str = os.path.abspath(args.build_directory)
    logging.info(f"Build directory: {build_dir}")

    if not os.path.isdir(build_dir):
        logging.error(f"'{build_dir}' is not a directory")
        print(f"Error: '{build_dir}' is not a directory.")
        sys.exit(1)
    
    build_ninja: str = os.path.join(build_dir, 'build.ninja')
    if not os.path.exists(build_ninja):
        logging.error(f"build.ninja not found in '{build_dir}'")
        print(f"Error: 'build.ninja' not found in '{build_dir}'.")
        print(f"Please provide the path to the ninja build directory containing build.ninja")
        sys.exit(1)

    project_root: str = os.path.dirname(os.path.abspath(__file__))
    
    # Get changed headers from rebuild info
    print(f"\n{Fore.CYAN}Extracting rebuild information...{Style.RESET_ALL}")
    # Save current directory and restore after extract_rebuild_info
    original_dir: str = os.getcwd()
    try:
        rebuild_entries: List[Any]
        reasons: Dict[str, str]
        root_causes: Dict[str, Any]
        rebuild_entries, reasons, root_causes = extract_rebuild_info(build_dir)
    except Exception as e:
        logging.error(f"Failed to extract rebuild information: {e}")
        print(f"{Fore.RED}Error: Failed to extract rebuild information: {e}{Style.RESET_ALL}")
        sys.exit(1)
    finally:
        os.chdir(original_dir)
    
    changed_headers: Set[str] = set(root_causes.keys())
    logging.info(f"Found {len(changed_headers)} changed headers")
    
    if not args.full and not changed_headers:
        logging.warning("No changed header files found")
        print(f"\n{Fore.YELLOW}No changed header files found{Style.RESET_ALL}")
        print(f"Use --full to analyze all headers instead")
        return
    
    if args.full:
        logging.info("Running in full analysis mode")
        print(f"{Fore.GREEN}Full analysis mode: analyzing all headers{Style.RESET_ALL}")
    else:
        logging.info(f"Analyzing {len(changed_headers)} changed headers")
        print(f"{Fore.GREEN}Found {len(changed_headers)} changed headers{Style.RESET_ALL}")
    
    # Build include graph using clang-scan-deps
    try:
        graph: nx.DiGraph
        source_to_headers: DefaultDict[str, Set[str]]
        graph, source_to_headers = build_include_graph_from_clang_scan(build_dir)
    except Exception as e:
        logging.error(f"Failed to build include graph: {e}")
        print(f"{Fore.RED}Error: Failed to build include graph: {e}{Style.RESET_ALL}")
        sys.exit(1)
    
    # Build header-to-header dependency graph
    print(f"{Fore.CYAN}Building header dependency graph...{Style.RESET_ALL}")
    try:
        header_graph: nx.Graph
        header_to_headers: DefaultDict[str, Set[str]]
        header_graph, header_to_headers = build_header_dependency_graph(source_to_headers, project_root)
    except Exception as e:
        logging.error(f"Failed to build header dependency graph: {e}")
        print(f"{Fore.RED}Error: Failed to build header dependency graph: {e}{Style.RESET_ALL}")
        sys.exit(1)
    
    # Calculate total dependency relationships
    total_deps: int = sum(len(headers) for headers in source_to_headers.values())
    
    logging.info(f"Analysis complete: {len(source_to_headers)} sources, {header_graph.number_of_nodes()} headers, {total_deps} dependencies")
    print(f"\n{Fore.GREEN}Dependency analysis complete:{Style.RESET_ALL}")
    print(f"  • {len(source_to_headers)} source files tracked")
    print(f"  • {header_graph.number_of_nodes()} unique headers in project")
    print(f"  • {total_deps} total source-to-header dependencies")
    print(f"  • {header_graph.number_of_edges()} header co-dependency relationships")
    
    # Filter changed headers to those in graph, or use all headers in full mode
    try:
        headers_to_analyze: List[str]
        changed_headers_in_graph: List[str]
        if args.full:
            # In full mode, analyze top gateway headers by include cost
            gateway_headers: List[Tuple[str, float, int, int]] = analyze_gateway_headers(source_to_headers, project_root)
            # Take top N gateway headers for detailed analysis
            headers_to_analyze = [h[0] for h in gateway_headers[:args.top]]
            changed_headers_in_graph = [h for h in headers_to_analyze if h in header_graph]
        else:
            changed_headers_in_graph = [h for h in changed_headers if h in header_graph]
    except Exception as e:
        logging.error(f"Failed to analyze headers: {e}")
        print(f"{Fore.RED}Error: Failed to analyze headers: {e}{Style.RESET_ALL}")
        sys.exit(1)
    
    if not changed_headers_in_graph:
        if args.full:
            print(f"\n{Fore.YELLOW}No headers found in the dependency graph{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}None of the changed headers are in the dependency graph{Style.RESET_ALL}")
        return
    
    # Analyze each changed header
    if args.full:
        print(f"\n{Style.BRIGHT}═══ Top Gateway Headers Analysis ═══{Style.RESET_ALL}")
    else:
        print(f"\n{Style.BRIGHT}═══ Include Graph Analysis ═══{Style.RESET_ALL}")
    
    for changed_header in sorted(changed_headers_in_graph):
        try:
            display_changed: str = changed_header
            if changed_header.startswith(project_root):
                display_changed = os.path.relpath(changed_header, project_root)
            
            # Find affected source files
            affected_sources: List[str] = find_affected_source_files(changed_header, graph, source_to_headers, project_root)
        except Exception as e:
            logging.error(f"Error processing header {changed_header}: {e}")
            print(f"{Fore.YELLOW}Warning: Skipping {changed_header} due to error: {e}{Style.RESET_ALL}")
            continue
        
        print(f"\n{Fore.RED}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.RED}{Style.BRIGHT}{display_changed}{Style.RESET_ALL}")
        print(f"{Fore.RED}{'='*80}{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}⚠ {len(affected_sources)} .cpp files will rebuild{Style.RESET_ALL}")
        
        # Show affected source files
        if affected_sources:
            print(f"\n  {Style.BRIGHT}Sample of .cpp files that will rebuild:{Style.RESET_ALL}")
            for source in sorted(affected_sources)[:args.top]:
                display_source = source
                if source.startswith(project_root):
                    display_source = os.path.relpath(source, project_root)
                print(f"    {Fore.YELLOW}📄 {display_source}{Style.RESET_ALL}")
            if len(affected_sources) > args.top:
                print(f"    {Style.DIM}... and {len(affected_sources) - args.top} more{Style.RESET_ALL}")
    
    # Gateway Header Analysis
    print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}GATEWAY HEADER ANALYSIS{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    print(f"Gateway headers = headers that drag in many other dependencies\n")
    
    gateway_headers = analyze_gateway_headers(source_to_headers, project_root)
    
    # Show top gateway headers overall
    top_count: int = 30 if args.full else 20
    print(f"{Style.BRIGHT}Top {top_count} gateway headers (highest include cost):{Style.RESET_ALL}")
    for header, avg_cost, unique_deps, usage_count in gateway_headers[:top_count]:
        display_header: str = header
        if header.startswith(project_root):
            display_header = os.path.relpath(header, project_root)
        
        # Highlight if this is a changed header
        is_changed: bool = header in changed_headers
        color: str = Fore.RED if is_changed else Fore.YELLOW if avg_cost > 100 else Fore.WHITE
        marker: str = " ⚠️ CHANGED" if is_changed else ""
        
        print(f"  {color}{display_header}{Style.RESET_ALL}")
        print(f"    Avg deps: {avg_cost:.1f} | Unique deps: {unique_deps} | Used by: {usage_count} files{marker}")
    
    # Analyze changed headers specifically
    if args.full:
        print(f"\n{Style.BRIGHT}Detailed analysis of top gateway headers:{Style.RESET_ALL}")
    else:
        print(f"\n{Style.BRIGHT}Changed headers and their include costs:{Style.RESET_ALL}")
    
    for changed_header in sorted(changed_headers_in_graph):
        display_changed = changed_header
        if changed_header.startswith(project_root):
            display_changed = os.path.relpath(changed_header, project_root)
        
        # Find this header in gateway analysis
        header_info = next((h for h in gateway_headers if h[0] == changed_header), None)
        if header_info:
            _, avg_cost, unique_deps, usage_count = header_info
            affected_sources = find_affected_source_files(changed_header, graph, source_to_headers, project_root)
            
            print(f"\n{Fore.RED}{display_changed}{Style.RESET_ALL}")
            print(f"  Direct impact: {len(affected_sources)} .cpp files rebuild")
            print(f"  Include cost: Drags in avg {avg_cost:.1f} other headers ({unique_deps} unique)")
            print(f"  Total compilation cost: {len(affected_sources)} files × {avg_cost:.1f} avg headers = {len(affected_sources) * avg_cost:.0f} header compilations")
            
            # Show which headers are most commonly dragged in by this one
            co_included: DefaultDict[str, int] = defaultdict(int)
            for source, headers in source_to_headers.items():
                if changed_header in headers:
                    for other_h in headers:
                        if other_h != changed_header:
                            co_included[other_h] += 1
            
            if co_included:
                sorted_co: List[Tuple[str, int]] = sorted(co_included.items(), key=lambda x: x[1], reverse=True)[:5]
                print(f"  Most commonly dragged in:")
                for co_header, count in sorted_co:
                    display_co = co_header
                    if co_header.startswith(project_root):
                        display_co = os.path.relpath(co_header, project_root)
                    pct = 100 * count / len(affected_sources)
                    print(f"    → {display_co} ({count}/{len(affected_sources)} = {pct:.0f}% of uses)")
    
    # Summary
    print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}REBUILD IMPACT SUMMARY{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    
    # Calculate unique .cpp files that will rebuild across all changed headers
    all_affected_sources: Set[str] = set()
    for changed_header in changed_headers_in_graph:
        affected: List[str] = find_affected_source_files(changed_header, graph, source_to_headers, project_root)
        all_affected_sources.update(affected)
    
    print(f"{Fore.YELLOW}Total unique .cpp files that will rebuild: {len(all_affected_sources)}{Style.RESET_ALL}")
    if len(source_to_headers) > 0:
        percentage: float = 100.0 * len(all_affected_sources) / len(source_to_headers)
        print(f"Out of {len(source_to_headers)} total source files tracked ({percentage:.1f}% of codebase)")
    else:
        print(f"Out of {len(source_to_headers)} total source files tracked")
    print(f"\nChanged headers causing most rebuilds:")
    
    if not args.full:
        header_impacts: List[Tuple[str, int]] = []
        for changed_header in changed_headers_in_graph:
            affected = find_affected_source_files(changed_header, graph, source_to_headers, project_root)
            header_impacts.append((changed_header, len(affected)))
        
        for header, count in sorted(header_impacts, key=lambda x: x[1], reverse=True):
            display_header = header
            if header.startswith(project_root):
                display_header = os.path.relpath(header, project_root)
            print(f"  {Fore.RED}{display_header}: {count} files{Style.RESET_ALL}")
    else:
        # In full mode, show summary of analyzed headers
        print(f"Analyzed top {len(changed_headers_in_graph)} gateway headers by include cost")
        print(f"Total source files in project: {len(source_to_headers)}")
    
    # Optimization opportunities
    print(f"\n{Style.BRIGHT}Optimization opportunities:{Style.RESET_ALL}")
    if args.full:
        print(f"Headers with high include cost are good candidates for optimization.")
    else:
        print(f"Look for gateway headers with high include cost but low actual usage.")
    print(f"These are good candidates for:")
    print(f"  1. Forward declarations instead of includes")
    print(f"  2. Moving implementations to .cpp files")
    print(f"  3. Splitting into smaller, more focused headers")
    
    # Find gateway headers that could be optimized
    optimization_candidates: List[Tuple[str, float, int]] = []
    for header in changed_headers_in_graph:
        header_info: Tuple[str, float, int, int] | None = next((h for h in gateway_headers if h[0] == header), None)
        if header_info:
            _, avg_cost, unique_deps, usage_count = header_info
            affected = find_affected_source_files(header, graph, source_to_headers, project_root)
            if avg_cost > HIGH_COST_THRESHOLD:  # High include cost
                optimization_candidates.append((header, avg_cost, len(affected)))
    
    if optimization_candidates:
        if args.full:
            print(f"\n  High-cost headers (top optimization targets):")
        else:
            print(f"\n  Priority targets (high-cost changed headers):")
        for header, cost, impact in sorted(optimization_candidates, key=lambda x: x[1] * x[2], reverse=True):
            display_header = header
            if header.startswith(project_root):
                display_header = os.path.relpath(header, project_root)
            total_cost = cost * impact
            print(f"    {Fore.YELLOW}{display_header}{Style.RESET_ALL}")
            print(f"      Cost: {cost:.0f} deps × {impact} files = {total_cost:.0f} total header compilations")



if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        print(f"\n{Fore.YELLOW}Interrupted by user{Style.RESET_ALL}")
        sys.exit(130)
    except ValueError as e:
        logging.error(f"Validation error: {e}")
        print(f"\n{Fore.RED}Validation error: {e}{Style.RESET_ALL}")
        sys.exit(1)
    except RuntimeError as e:
        logging.error(f"Runtime error: {e}")
        print(f"\n{Fore.RED}Runtime error: {e}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Run with --verbose for more details{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        logging.critical(f"Unexpected error: {e}", exc_info=True)
        print(f"\n{Fore.RED}Fatal error: {e}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Run with --verbose for more details{Style.RESET_ALL}")
        sys.exit(1)
