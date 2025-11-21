#!/usr/bin/env python3
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
"""Find headers that lead to dependency hell (excessive transitive dependencies).

PURPOSE:
    Comprehensive, multi-dimensional analysis of header dependency problems using
    graph theory and transitive dependency tracking. Identifies headers that cause
    excessive compilation costs through deep dependency chains.

WHAT IT DOES:
    - Builds complete transitive dependency graph using clang-scan-deps + NetworkX
    - Calculates multiple impact metrics for each header:
      * Transitive dependency count (how many headers this pulls in)
      * Build impact (deps × usage = total compilation cost)
      * Rebuild cost (if changed, how many sources rebuild)
      * Reverse impact (how many headers depend on this one)
      * Hub headers (architectural bottlenecks)
      * Maximum chain length (deepest include path)
    - Classifies headers by severity (CRITICAL/HIGH/MODERATE)
    - Identifies base type headers (no project includes)
    - Provides multiple ranked lists for different refactoring priorities

USE CASES:
    - "Which headers should I refactor first to improve build times?"
    - Find architectural bottlenecks (hub headers with many dependents)
    - Identify headers causing the most compilation work (build impact)
    - Find headers that would cause expensive rebuilds if changed
    - Prioritize technical debt reduction
    - Track dependency complexity over time
    - Validate architectural decisions

METHOD:
    1. Uses clang-scan-deps (parallel) to parse all #include directives
    2. Builds directed graph with NetworkX
    3. Computes transitive closures (descendants/ancestors)
    4. Calculates multiple impact metrics
    5. Ranks headers by different criteria

OUTPUT:
    Multiple ranked lists:
    1. Worst Offenders: By transitive dependency count
    2. Build Impact: By (deps × usage) - total compilation cost
    3. Rebuild Cost: By (usage × dependents) - rebuild expense if changed
    4. Hub Headers: By reverse dependency count - architectural bottlenecks
    
    Severity classification:
    - CRITICAL: Combined score > 500 (urgent refactoring needed)
    - HIGH: Combined score 300-500 (should refactor soon)
    - MODERATE: Combined score < 300 (monitor)

METRICS EXPLAINED:
    - Transitive Deps: Total headers pulled in (direct + indirect)
    - Build Impact: deps × usage = total header compilations across project
    - Rebuild Cost: usage × (1 + dependents) = sources rebuilt if header changes
    - Reverse Impact: Number of other headers that depend on this one
    - Hub Header: Header with high reverse impact (architectural bottleneck)
    - Max Chain: Longest include path through this header
    - Fanout: Number of headers frequently pulled in together
    - Base Type: Header with no outgoing project includes

PERFORMANCE:
    Moderate (5-10 seconds for large projects). Uses all CPU cores.
    Most expensive but most comprehensive analysis.

REQUIREMENTS:
    - Python 3.7+
    - clang-scan-deps (clang-19, clang-18, or clang-XX)
    - networkx: pip install networkx
    - compile_commands.json (auto-generated)

COMPLEMENTARY TOOLS:
    This is the most comprehensive tool. Use the others for quick checks:
    - buildCheckImpact.py: Quick impact check (1 second)
    - buildCheckIncludeChains.py: Simple cooccurrence patterns
    - buildCheckIncludeGraph.py: Gateway headers and .cpp rebuild lists

REFACTORING GUIDE:
    1. Start with CRITICAL severity headers
    2. Look at "Rebuild Cost" list first - these cause most pain when changed
    3. Use "Hub Headers" to find architectural bottlenecks
    4. Use "Build Impact" to find headers slowing compilation
    5. Use --detailed to see per-header analysis with recommendations

EXAMPLES:
    # Analyze all headers with default threshold (50 deps)
    ./buildCheckDependencyHell.py ../build/release/
    
    # Only analyze changed headers (faster, focused)
    ./buildCheckDependencyHell.py ../build/release/ --changed
    
    # Show detailed per-header analysis
    ./buildCheckDependencyHell.py ../build/release/ --detailed
    
    # More strict threshold (30 deps) and show top 20
    ./buildCheckDependencyHell.py ../build/release/ --threshold 30 --top 20
    
    # Analyze only changed headers with details
    ./buildCheckDependencyHell.py ../build/release/ --changed --detailed
"""
import subprocess
import re
import os
import sys
import argparse
import time
import json
import logging
import multiprocessing as mp
from collections import defaultdict
from typing import Dict, Set, List, Tuple, Optional, DefaultDict
from pathlib import Path

try:
    import networkx as nx
except ImportError:
    print("Error: networkx is required. Install with: pip install networkx")
    sys.exit(1)

# Import helper function from buildCheckSummary
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from buildCheckSummary import extract_rebuild_info
except ImportError:
    print("Error: buildCheckSummary.py not found in the same directory")
    sys.exit(1)

try:
    from colorama import Fore, Style, init
    init(autoreset=False)
except ImportError:
    class Fore:
        RED = YELLOW = GREEN = BLUE = MAGENTA = CYAN = WHITE = LIGHTBLACK_EX = RESET = ''
    class Style:
        RESET_ALL = BRIGHT = DIM = ''

# Constants
RE_OUTPUT = re.compile(r"ninja explain: (.*)")
VALID_HEADER_EXTENSIONS = ('.h', '.hpp', '.hxx')
VALID_SOURCE_EXTENSIONS = ('.cpp', '.c', '.cc', '.cxx')
SYSTEM_PREFIXES = ('/usr/', '/lib/')
CLANG_SCAN_DEPS_COMMANDS = ["clang-scan-deps-19", "clang-scan-deps-18", "clang-scan-deps"]
DEFAULT_THRESHOLD = 50
DEFAULT_TOP_N = 10
SEVERITY_CRITICAL = 500
SEVERITY_HIGH = 300
FANOUT_THRESHOLD = 5
MAX_AMBIGUOUS_DISPLAY = 10

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def create_filtered_compile_commands(build_dir: str) -> str:
    """Create a filtered compile_commands.json with only C/C++ compilation entries.
    
    Args:
        build_dir: Path to the build directory
        
    Returns:
        Path to the filtered compile_commands.json file
        
    Raises:
        FileNotFoundError: If build directory doesn't exist
        subprocess.CalledProcessError: If ninja command fails
        IOError: If file operations fail
    """
    build_dir = os.path.realpath(os.path.abspath(build_dir))
    if not os.path.isdir(build_dir):
        raise FileNotFoundError(f"Build directory not found: {build_dir}")
    
    compile_db = os.path.realpath(os.path.join(build_dir, 'compile_commands.json'))
    filtered_db = os.path.realpath(os.path.join(build_dir, 'compile_commands_filtered.json'))
    build_ninja = os.path.realpath(os.path.join(build_dir, 'build.ninja'))
    
    # Validate paths are within build_dir (prevent path traversal)
    for path in [compile_db, filtered_db, build_ninja]:
        if not path.startswith(build_dir + os.sep):
            raise ValueError(f"Path traversal detected: {path}")
    
    # Check if filtered DB exists and is newer than build.ninja
    if os.path.exists(filtered_db) and os.path.exists(build_ninja):
        if os.path.getmtime(filtered_db) > os.path.getmtime(build_ninja):
            logger.debug(f"Using cached filtered compile commands: {filtered_db}")
            return filtered_db
    
    # Generate compile_commands.json if needed
    if not os.path.exists(compile_db) or (os.path.exists(build_ninja) and os.path.getmtime(build_ninja) > os.path.getmtime(compile_db)):
        logger.info(f"Generating compile_commands.json...")
        try:
            result = subprocess.run(
                ["ninja", "-t", "compdb"],
                capture_output=True,
                text=True,
                cwd=build_dir,
                check=True
            )
            with open(compile_db, 'w', encoding='utf-8') as f:
                f.write(result.stdout)
            logger.debug(f"Generated: {compile_db}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to generate compile_commands.json: {e.stderr}") from e
        except IOError as e:
            raise IOError(f"Failed to write compile_commands.json: {e}") from e
    
    # Filter to valid C/C++ entries
    try:
        with open(compile_db, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to read compile_commands.json: {e}") from e
    
    if not isinstance(data, list):
        raise ValueError(f"Invalid compile_commands.json format: expected list, got {type(data)}")
    
    valid_entries = []
    for entry in data:
        if not isinstance(entry, dict):
            logger.warning(f"Skipping invalid entry in compile_commands.json: {entry}")
            continue
        cmd = entry.get('command', '')
        file = entry.get('file', '')
        if any(file.endswith(ext) for ext in VALID_SOURCE_EXTENSIONS) and ' -c ' in cmd:
            valid_entries.append(entry)
    
    if not valid_entries:
        raise ValueError("No valid C/C++ compilation entries found in compile_commands.json")
    
    try:
        with open(filtered_db, 'w', encoding='utf-8') as f:
            json.dump(valid_entries, f, indent=2)
        logger.info(f"Filtered to {len(valid_entries)} valid compilation entries")
    except IOError as e:
        raise IOError(f"Failed to write filtered compile commands: {e}") from e
    
    return filtered_db


def build_include_graph(build_dir: str) -> Tuple[Dict[str, List[str]], DefaultDict[str, Set[str]], Set[str], float]:
    """Build a complete include graph showing what each header directly includes.
    
    Args:
        build_dir: Path to the build directory
        
    Returns:
        Tuple of (source_to_deps, header_to_direct_includes, all_headers, elapsed_time)
        
    Raises:
        RuntimeError: If clang-scan-deps is not available or fails
        FileNotFoundError: If required files are missing
    """
    try:
        # Check if clang-scan-deps is available
        clang_cmd = None
        for cmd in CLANG_SCAN_DEPS_COMMANDS:
            try:
                result = subprocess.run([cmd, "--version"], capture_output=True, check=True, timeout=5)
                clang_cmd = cmd
                logger.debug(f"Found {cmd}: {result.stdout.decode('utf-8', errors='ignore').split()[0]}")
                break
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                continue
        
        if not clang_cmd:
            raise RuntimeError(
                f"clang-scan-deps not found. Please install clang (e.g., 'sudo apt install clang-19')"
            )
        
        try:
            filtered_db = create_filtered_compile_commands(build_dir)
        except Exception as e:
            raise RuntimeError(f"Failed to create filtered compile commands: {e}") from e
        
        if not os.path.exists(filtered_db):
            raise FileNotFoundError(f"Filtered compile commands not found: {filtered_db}")
        
        num_cores = mp.cpu_count()
        logger.info(f"Running {clang_cmd} using {num_cores} cores to build include graph...")
        
        start_time = time.time()
        try:
            result = subprocess.run(
                [clang_cmd, f"-compilation-database={filtered_db}", "-format=make", "-j", str(num_cores)],
                capture_output=True,
                text=True,
                cwd=build_dir,
                timeout=300  # 5 minute timeout
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"{clang_cmd} timed out after 300 seconds") from None
        
        elapsed = time.time() - start_time
        
        if result.returncode != 0:
            error_msg = f"{clang_cmd} failed with code {result.returncode}"
            if result.stderr:
                error_msg += f"\nError output: {result.stderr[:1000]}"
            raise RuntimeError(error_msg)
        
        # Parse makefile-style output to build include graph
        # Format is: target.o: source.cpp header1.hpp header2.hpp ...
        source_to_deps = {}
        header_to_direct_includes = defaultdict(set)
        all_headers = set()
        
        current_target = None
        current_deps = []
        
        for line in result.stdout.splitlines():
            # Check if this is a target line (ends with :)
            if ':' in line and not line.strip().startswith('/'):
                # This is a target line
                parts = line.split(':', 1)
                # Save previous target if exists
                if current_target and current_deps:
                    source_to_deps[current_target] = current_deps
                # Start new target
                current_target = parts[0].strip()
                current_deps = []
                # Process any deps on the same line
                if len(parts) > 1:
                    remainder = parts[1].strip()
                    if remainder and remainder != '\\':
                        current_deps.append(remainder.rstrip('\\').strip())
            else:
                # This is a dependency line
                line = line.strip()
                if line and line != '\\':
                    # Remove trailing backslash and whitespace
                    dep = line.rstrip('\\').strip()
                    if dep:
                        current_deps.append(dep)
        
        # Save last target
        if current_target and current_deps:
            source_to_deps[current_target] = current_deps
        
        print(f"{Fore.GREEN}Scanned {len(source_to_deps)} source files in {elapsed:.2f}s{Style.RESET_ALL}")
        
        # Now build the include graph by parsing what each file directly includes
        # We'll use clang -M to get direct includes for each header
        print(f"{Fore.CYAN}Building direct include relationships for headers...{Style.RESET_ALL}")
        
        # Collect all unique project headers
        for deps in source_to_deps.values():
            for dep in deps:
                if dep.endswith(('.h', '.hpp', '.hxx')) and not dep.startswith('/usr/') and not dep.startswith('/lib/'):
                    all_headers.add(dep)
        
        print(f"{Fore.BLUE}Found {len(all_headers)} unique project headers{Style.RESET_ALL}")
        
        # Build a map of include paths by finding common include roots
        # For each header, find the include root by looking for the include path suffix
        print(f"{Fore.CYAN}Identifying valid include paths from compile commands...{Style.RESET_ALL}")
        
        # Extract include paths from compile commands
        valid_include_roots = set()
        with open(filtered_db, 'r') as f:
            compile_db = json.load(f)
            for entry in compile_db:
                cmd = entry.get('command', '')
                # Extract -I paths
                import shlex
                parts = shlex.split(cmd)
                for i, part in enumerate(parts):
                    if part == '-I' and i + 1 < len(parts):
                        include_path = parts[i + 1]
                        if os.path.isabs(include_path):
                            valid_include_roots.add(include_path)
                    elif part.startswith('-I'):
                        include_path = part[2:]
                        if os.path.isabs(include_path):
                            valid_include_roots.add(include_path)
        
        print(f"{Fore.BLUE}Found {len(valid_include_roots)} valid include root directories{Style.RESET_ALL}")
        
        # For each header, parse its #include directives to find direct dependencies
        # We'll use a simple approach: read the file and parse #include lines
        import glob
        
        parse_errors = 0
        ambiguous_includes = []
        for header in all_headers:
            if not os.path.exists(header):
                continue
            
            try:
                with open(header, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('#include'):
                            # Extract the included file
                            if '"' in line:
                                # #include "file.hpp"
                                start = line.find('"')
                                end = line.find('"', start + 1)
                                if start != -1 and end != -1:
                                    included = line[start+1:end]
                                    # Resolve to absolute path
                                    header_dir = os.path.dirname(header)
                                    abs_included = os.path.abspath(os.path.join(header_dir, included))
                                    if os.path.exists(abs_included) and abs_included.endswith(('.h', '.hpp', '.hxx')):
                                        header_to_direct_includes[header].add(abs_included)
                            elif '<' in line:
                                # #include <FslBase/BasicTypes.hpp> or #include <cstdint>
                                start = line.find('<')
                                end = line.find('>')
                                if start != -1 and end != -1:
                                    included = line[start+1:end]
                                    # Skip system headers (no extension or standard library patterns)
                                    if not included.endswith(('.h', '.hpp', '.hxx')):
                                        continue  # System header like <cstdint>, <vector>, etc.
                                    if '/' not in included:
                                        continue  # System header like <stdint.h>, <stdio.h>
                                    # This looks like a project header - try to resolve it
                                    # Match only headers that can be resolved from valid include roots
                                    matches = []
                                    for root in valid_include_roots:
                                        candidate = os.path.join(root, included)
                                        if candidate in all_headers:
                                            matches.append(candidate)
                                    
                                    if len(matches) > 1:
                                        # Multiple matches - this is an ambiguity error
                                        ambiguous_includes.append((header, included, matches))
                                        # Use the shortest match to be deterministic, but this is still an error
                                        best_match = min(matches, key=len)
                                        header_to_direct_includes[header].add(best_match)
                                    elif len(matches) == 1:
                                        header_to_direct_includes[header].add(matches[0])
            except Exception as e:
                parse_errors += 1
        
        if parse_errors > 0:
            print(f"{Fore.YELLOW}Warning: {parse_errors} headers had parse errors{Style.RESET_ALL}")
        
        if ambiguous_includes:
            print(f"{Fore.RED}Warning: Found {len(ambiguous_includes)} ambiguous include paths!{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}These includes match multiple header files:{Style.RESET_ALL}")
            # Group by include path to avoid repetition
            by_include = defaultdict(list)
            for header, included, matches in ambiguous_includes:
                by_include[included].append((header, matches))
            
            for included, sources in sorted(by_include.items())[:10]:  # Show first 10
                print(f"  {Fore.CYAN}#include <{included}>{Style.RESET_ALL} matches:")
                for match in sorted(sources[0][1])[:5]:  # Show first 5 matches
                    print(f"    {Fore.MAGENTA}{match}{Style.RESET_ALL}")
                if len(sources[0][1]) > 5:
                    print(f"    {Style.DIM}... and {len(sources[0][1]) - 5} more{Style.RESET_ALL}")
                print(f"    {Style.DIM}Used in {len(sources)} different headers{Style.RESET_ALL}")
            
            if len(by_include) > 10:
                print(f"  {Style.DIM}... and {len(by_include) - 10} more ambiguous includes{Style.RESET_ALL}")
        
        print(f"{Fore.GREEN}Built include graph with {len(header_to_direct_includes)} headers{Style.RESET_ALL}")
        return source_to_deps, header_to_direct_includes, all_headers, elapsed
    except Exception as e:
        print(f"{Fore.RED}Error building include graph: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def compute_transitive_deps(header: str, include_graph: Dict[str, Set[str]], visited: Optional[Set[str]] = None, depth: int = 0) -> Set[str]:
    """Recursively compute all transitive dependencies of a header.
    
    Args:
        header: Header file path
        include_graph: Mapping of headers to their direct includes
        visited: Set of already visited headers (for cycle detection)
        depth: Current recursion depth
        
    Returns:
        Set of all transitive dependencies
        
    Raises:
        RecursionError: If maximum recursion depth exceeded
    """
    if visited is None:
        visited = set()
    
    if header in visited:
        return set()
    
    if depth > 1000:
        logger.warning(f"Maximum recursion depth exceeded for header: {header}")
        return set()
    
    visited.add(header)
    transitive = set()
    
    for direct_dep in include_graph.get(header, set()):
        transitive.add(direct_dep)
        transitive.update(compute_transitive_deps(direct_dep, include_graph, visited, depth + 1))
    
    return transitive


def is_system_header(header: str) -> bool:
    """Check if a header is a system header.
    
    Args:
        header: Header file path
        
    Returns:
        True if the header is a system header
    """
    return any(header.startswith(prefix) for prefix in SYSTEM_PREFIXES)


def build_dependency_graph(include_graph: Dict[str, Set[str]], all_headers: Set[str]) -> nx.DiGraph:
    """Build a NetworkX directed graph from the include relationships.
    
    Args:
        include_graph: Mapping of headers to their direct includes
        all_headers: Set of all header files
        
    Returns:
        Directed graph of include relationships
        
    Raises:
        ValueError: If input data is invalid
    """
    if not isinstance(all_headers, set):
        raise ValueError(f"all_headers must be a set, got {type(all_headers)}")
    
    G = nx.DiGraph()
    
    # Add only project headers as nodes
    project_headers = [h for h in all_headers if not is_system_header(h)]
    
    if not project_headers:
        raise ValueError("No project headers found in all_headers")
    
    G.add_nodes_from(project_headers)
    logger.debug(f"Added {len(project_headers)} project headers as nodes")
    
    # Add edges for direct includes (only between project headers)
    edge_count = 0
    for header, includes in include_graph.items():
        if is_system_header(header):
            continue  # Skip system headers as source
        for included_header in includes:
            # Only add edges to project headers
            if not is_system_header(included_header) and included_header in project_headers:
                G.add_edge(header, included_header)
                edge_count += 1
    
    logger.debug(f"Added {edge_count} edges to dependency graph")
    return G


def analyze_dependency_hell(build_dir: str, rebuild_targets: List[str], threshold: int = DEFAULT_THRESHOLD) -> Dict:
    """Find headers with excessive dependencies using include graph.
    
    Args:
        build_dir: Path to the build directory
        rebuild_targets: List of rebuild target files
        threshold: Minimum transitive dependency count to flag as problematic
        
    Returns:
        Dictionary containing analysis results
        
    Raises:
        ValueError: If inputs are invalid
        RuntimeError: If analysis fails
    """
    build_dir = os.path.realpath(os.path.abspath(build_dir))
    if not os.path.isdir(build_dir):
        raise ValueError(f"Invalid build directory: {build_dir}")
    
    if not rebuild_targets:
        logger.warning("No rebuild targets provided")
    
    if threshold <= 0:
        raise ValueError(f"Threshold must be positive, got {threshold}")
    
    start_time = time.time()
    
    # Build complete include graph
    try:
        source_to_deps, include_graph, all_headers, scan_time = build_include_graph(build_dir)
    except Exception as e:
        raise RuntimeError(f"Failed to build include graph: {e}") from e
    
    logger.info("Building dependency graph with NetworkX...")
    try:
        G = build_dependency_graph(include_graph, all_headers)
    except Exception as e:
        raise RuntimeError(f"Failed to build dependency graph: {e}") from e
    
    logger.info(f"Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    
    print(f"{Fore.BLUE}Computing transitive dependencies for all headers...{Style.RESET_ALL}")
    
    # Count how many source files include each header (directly or transitively)
    header_usage_count = defaultdict(int)
    for source, deps in source_to_deps.items():
        for dep in deps:
            if dep.endswith(('.h', '.hpp', '.hxx')) and not dep.startswith('/usr/') and not dep.startswith('/lib/'):
                header_usage_count[dep] += 1
    
    # Compute reverse dependencies (how many headers depend on each header)
    print(f"{Fore.BLUE}Computing reverse dependencies (rebuild blast radius)...{Style.RESET_ALL}")
    reverse_deps = defaultdict(set)  # headers that depend on this header (transitively)
    for node in G.nodes():
        # Get all ancestors (headers that include this one transitively)
        ancestors = nx.ancestors(G, node)
        reverse_deps[node] = ancestors
    
    # Identify base types: headers with zero out-degree (don't include any project headers)
    base_types = set()
    header_transitive_deps = {}
    header_reverse_impact = {}
    header_max_chain_length = {}
    
    # Only process project headers
    project_headers = [h for h in all_headers 
                      if not h.startswith('/usr/') and not h.startswith('/lib/')]
    
    print(f"{Fore.BLUE}Computing rebuild impact metrics...{Style.RESET_ALL}")
    for header in project_headers:
        # Base type = no outgoing edges (doesn't include other project headers)
        out_degree = G.out_degree(header) if header in G else 0
        if out_degree == 0:
            base_types.add(header)
        
        # Compute transitive dependencies using NetworkX descendants
        if header in G:
            descendants = nx.descendants(G, header)
            header_transitive_deps[header] = len(descendants)
            
            # Reverse impact: how many headers depend on this one
            header_reverse_impact[header] = len(reverse_deps[header])
            
            # Longest chain through this header
            # Find longest path from this node to any leaf (base type)
            try:
                # Get all paths from this header to base types
                max_chain = 0
                for base in base_types:
                    if base in descendants:
                        try:
                            path_len = nx.shortest_path_length(G, header, base)
                            max_chain = max(max_chain, path_len)
                        except nx.NetworkXNoPath:
                            pass
                header_max_chain_length[header] = max_chain
            except:
                header_max_chain_length[header] = 0
        else:
            header_transitive_deps[header] = 0
            header_reverse_impact[header] = 0
            header_max_chain_length[header] = 0
    
    elapsed = time.time() - start_time
    print(f"{Fore.BLUE}Finished dependency analysis in {elapsed:.2f}s{Style.RESET_ALL}")
    print(f"{Fore.BLUE}Total unique project headers: {len(project_headers)}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}Identified {len(base_types)} base type headers (no direct project includes){Style.RESET_ALL}")
    
    if base_types and len(base_types) < 50:
        print(f"{Fore.CYAN}Base type headers:{Style.RESET_ALL}")
        for bt in sorted(base_types):
            print(f"  {Fore.GREEN}{bt}{Style.RESET_ALL}")
    
    problematic = []
    print(f"{Fore.BLUE}Checking for headers exceeding threshold ({threshold})...{Style.RESET_ALL}")
    for header, trans_count in header_transitive_deps.items():
        if trans_count > threshold:
            usage_count = header_usage_count.get(header, 0)
            reverse_impact = header_reverse_impact.get(header, 0)
            chain_length = header_max_chain_length.get(header, 0)
            problematic.append((header, trans_count, usage_count, reverse_impact, chain_length))
    
    if problematic:
        print(f"{Fore.YELLOW}  Found {len(problematic)} headers exceeding threshold{Style.RESET_ALL}")
    print(f"{Fore.BLUE}Dependency analysis complete.{Style.RESET_ALL}")
    
    return_data = {
        'problematic': sorted(problematic, key=lambda x: x[1], reverse=True),
        'source_to_deps': source_to_deps,
        'base_types': base_types,
        'header_usage_count': header_usage_count,
        'header_reverse_impact': header_reverse_impact,
        'header_max_chain_length': header_max_chain_length
    }
    return return_data


def find_dependency_fanout(build_dir: str, rebuild_targets: List[str], target_headers: List[str], 
                          source_to_deps: Dict[str, List[str]]) -> DefaultDict[str, DefaultDict[str, int]]:
    """Find how often headers cooccur with target headers.
    
    Args:
        build_dir: Path to the build directory
        rebuild_targets: List of rebuild target files
        target_headers: List of headers to analyze
        source_to_deps: Mapping of source files to their dependencies
        
    Returns:
        Nested dictionary of cooccurrence counts
    """
    if not target_headers:
        logger.warning("No target headers provided for fanout analysis")
        return defaultdict(lambda: defaultdict(int))
    
    start_time = time.time()
    cooccurrence: DefaultDict[str, DefaultDict[str, int]] = defaultdict(lambda: defaultdict(int))
    
    logger.info("Calculating header cooccurrence/fanout from cached data...")
    
    for source, deps in source_to_deps.items():
        headers = [d for d in deps if d.endswith(VALID_HEADER_EXTENSIONS) and not is_system_header(d)]
        for target_header in target_headers:
            if target_header in headers:
                for h in headers:
                    if h != target_header:
                        cooccurrence[target_header][h] += 1
    
    elapsed = time.time() - start_time
    logger.info(f"Fanout calculation complete in {elapsed:.2f}s")
    return cooccurrence


def main() -> int:
    """Main entry point for the dependency hell analyzer.
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    parser = argparse.ArgumentParser(
        description='Comprehensive dependency analysis: find headers causing dependency hell.',
        epilog='''
This is the most comprehensive build analysis tool. It provides multiple ranked
lists to help prioritize refactoring:

  1. Worst Offenders: Most transitive dependencies
  2. Build Impact: Highest total compilation cost (deps × usage)
  3. Rebuild Cost: Most expensive if changed (usage × dependents)
  4. Hub Headers: Architectural bottlenecks (most dependents)

Severity levels:
  CRITICAL (>500): Urgent refactoring needed
  HIGH (300-500): Should refactor soon
  MODERATE (<300): Monitor and consider refactoring

Workflow:
  1. Run without flags to see all problematic headers
  2. Use --changed to focus on recently modified headers
  3. Use --detailed to see per-header recommendations
  4. Start refactoring from "Rebuild Cost" list (causes most pain)

Requires: clang-scan-deps, networkx (pip install networkx)
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'build_directory',
        metavar='BUILD_DIR',
        help='Path to the ninja build directory (e.g., build/release)'
    )
    
    parser.add_argument(
        '--threshold',
        type=int,
        default=50,
        help='Minimum transitive dependency count to flag as problematic (default: 50). '
             'Lower = more strict (e.g., 30), higher = less strict (e.g., 100)'
    )
    
    parser.add_argument(
        '--top',
        type=int,
        default=10,
        help='Number of items to show in each ranked list (default: 10). '
             'Use 20-30 for comprehensive view'
    )
    
    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Show detailed per-header analysis with metrics, severity, and '
             'frequently cooccurring headers. Use this for deep-dive analysis'
    )
    
    parser.add_argument(
        '--changed',
        action='store_true',
        help='Only analyze changed headers (from rebuild root causes). '
             'Faster and more focused on recent modifications'
    )
    
    args = parser.parse_args()
    build_dir = args.build_directory

    # Validate arguments
    if args.threshold <= 0:
        logger.error(f"Invalid threshold: {args.threshold}. Must be positive.")
        return 1
    
    if args.top <= 0:
        logger.error(f"Invalid top value: {args.top}. Must be positive.")
        return 1

    print(f"{Fore.CYAN}Starting dependency hell analysis...{Style.RESET_ALL}")
    if not os.path.isdir(build_dir):
        logger.error(f"Build directory not found: {build_dir}")
        return 1
    
    build_dir = os.path.abspath(build_dir)

    try:
        project_root = str(Path(build_dir).parent.parent.parent)
    except Exception as e:
        logger.error(f"Failed to determine project root: {e}")
        return 1

    # Get changed files if --changed is specified
    changed_headers: Set[str] = set()
    if args.changed:
        print(f"{Fore.BLUE}Extracting changed headers from rebuild root causes...{Style.RESET_ALL}")
        try:
            rebuild_entries, reasons, root_causes = extract_rebuild_info(build_dir)
            changed_headers = set(root_causes.keys())
        except Exception as e:
            logger.error(f"Failed to extract rebuild info: {e}")
            return 1

        if not changed_headers:
            print(f"\n{Fore.YELLOW}No changed header files found in rebuild root causes{Style.RESET_ALL}")
            return 0

        print(f"\n{Fore.CYAN}Found {len(changed_headers)} changed headers to analyze:{Style.RESET_ALL}")
        for header in sorted(changed_headers):
            display_header = header
            if header.startswith(project_root):
                display_header = os.path.relpath(header, project_root)
            print(f"  {Fore.MAGENTA}{display_header}{Style.RESET_ALL}")

    print(f"{Fore.BLUE}Running ninja dry-run to collect rebuild targets...{Style.RESET_ALL}")
    # Run ninja -n -d explain to get what would rebuild
    try:
        result = subprocess.run(
            ["ninja", "-n", "-d", "explain"],
            capture_output=True,
            text=True,
            check=True,
            cwd=build_dir,
            timeout=60
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Ninja command failed: {e.stderr}")
        return 1
    except subprocess.TimeoutExpired:
        logger.error("Ninja command timed out after 60 seconds")
        return 1
    except FileNotFoundError:
        logger.error("Ninja not found. Please ensure ninja is installed and in PATH.")
        return 1

    lines = result.stderr.splitlines()

    rebuild_targets = []

    for line in lines:
        m = RE_OUTPUT.search(line)
        if not m:
            continue

        explain_msg = m.group(1)

        # Skip "is dirty" lines - these are just CMake files
        if "is dirty" in explain_msg:
            continue

        output_file = "unknown"
        if explain_msg.startswith("output "):
            parts = explain_msg.split(" ", 2)
            if len(parts) > 1:
                output_file = parts[1]
        elif "command line changed for " in explain_msg:
            output_file = explain_msg.split("command line changed for ", 1)[1]
        
        # Only include actual object files
        if any(f'{ext}.o' in output_file for ext in VALID_SOURCE_EXTENSIONS):
            rebuild_targets.append(output_file)

    # If no rebuilds detected, get all object files instead
    if not rebuild_targets:
        print(f"{Fore.YELLOW}No rebuilds detected, analyzing all object files...{Style.RESET_ALL}")
        try:
            result = subprocess.run(
                ["ninja", "-t", "targets", "all"],
                capture_output=True,
                text=True,
                check=True,
                cwd=build_dir,
                timeout=30
            )
            for line in result.stdout.splitlines():
                target = line.split(':')[0].strip()
                if any(f'{ext}.o' in target for ext in VALID_SOURCE_EXTENSIONS):
                    rebuild_targets.append(target)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.warning(f"Failed to get ninja targets: {e}")

    if not rebuild_targets:
        logger.error("No compilation targets found.")
        return 1

    mode_desc = f"changed headers only" if args.changed else "all headers"
    print(f"\n{Fore.CYAN}Analyzing dependency hell ({len(rebuild_targets)} targets, {mode_desc})...{Style.RESET_ALL}")
    
    try:
        result = analyze_dependency_hell(build_dir, rebuild_targets, args.threshold)
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        logger.debug("Exception details:", exc_info=True)
        return 1
    
    problematic = result['problematic']
    source_to_deps = result['source_to_deps']
    base_types = result['base_types']
    header_usage_count = result['header_usage_count']
    header_reverse_impact = result['header_reverse_impact']
    header_max_chain_length = result['header_max_chain_length']
    
    # Filter to only changed headers if requested
    if args.changed and changed_headers:
        original_count = len(problematic)
        problematic = [(h, c, u, r, ch) for h, c, u, r, ch in problematic if h in changed_headers]
        if len(problematic) < original_count:
            filtered_out = original_count - len(problematic)
            print(f"{Fore.BLUE}Filtered to {len(problematic)} changed headers (excluded {filtered_out} unchanged headers){Style.RESET_ALL}")
    
    if not problematic:
        if args.changed:
            print(f"\n{Fore.YELLOW}No changed headers exceed threshold (threshold={args.threshold}){Style.RESET_ALL}")
            print(f"{Fore.CYAN}The changed headers are base types or have fewer than {args.threshold} transitive dependencies{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.GREEN}No headers with excessive dependencies found (threshold={args.threshold}){Style.RESET_ALL}")
        return 0
    
    # Always compute cooccurrence for all problematic headers to get accurate severity breakdown
    # This is needed for severity calculation even when not in detailed mode
    all_problematic_headers = [h for h, _, _, _, _ in problematic]
    cooccurrence = find_dependency_fanout(os.getcwd(), rebuild_targets, all_problematic_headers, source_to_deps)
    
    # Show detailed analysis if requested
    if args.detailed:
        print(f"\n{Style.BRIGHT}Detailed Analysis (showing all {len(problematic)} headers):{Style.RESET_ALL}")
        
        for header, dep_count, usage_count, reverse_impact, chain_length in problematic:
            display_path = header
            if header.startswith(project_root):
                display_path = os.path.relpath(header, project_root)
            
            # Calculate fanout (how many other headers it pulls in frequently)
            fanout = len([h for h, count in cooccurrence[header].items() if count > FANOUT_THRESHOLD]) if header in cooccurrence else 0
            
            # Rebuild cost: if this header changes, how expensive is the rebuild?
            rebuild_cost = usage_count * (1 + reverse_impact)
            
            # Combined score for severity
            combined_score = dep_count + (fanout * 10)
            
            if combined_score > SEVERITY_CRITICAL:
                severity = f"{Fore.RED}CRITICAL{Style.RESET_ALL}"
            elif combined_score > SEVERITY_HIGH:
                severity = f"{Fore.YELLOW}HIGH{Style.RESET_ALL}"
            else:
                severity = f"{Fore.CYAN}MODERATE{Style.RESET_ALL}"
            
            print(f"\n  {Fore.MAGENTA}{display_path}{Style.RESET_ALL}")
            print(f"    Transitive deps: {Style.BRIGHT}{dep_count}{Style.RESET_ALL}, Fanout: {fanout}, Usage: {usage_count} sources")
            print(f"    Reverse impact: {reverse_impact} headers depend on this, Max chain: {chain_length}, Rebuild cost: {rebuild_cost:,}")
            print(f"    Severity: {severity}")
            
            # Show top cooccurring headers
            if header in cooccurrence:
                top_cooccur = sorted(cooccurrence[header].items(), key=lambda x: x[1], reverse=True)[:5]
                if top_cooccur:
                    print(f"    Frequently pulls in:")
                    for coheader, count in top_cooccur:
                        display_co = coheader
                        if coheader.startswith(project_root):
                            display_co = os.path.relpath(coheader, project_root)
                        print(f"      {Style.DIM}{display_co}{Style.RESET_ALL} ({count} times)")
    
    # Calculate summary statistics
    total_problematic = len(problematic)
    critical_count = len([h for h, dc, _, _, _ in problematic if dc + (len([x for x, c in cooccurrence[h].items() if c > FANOUT_THRESHOLD]) * 10) > SEVERITY_CRITICAL])
    high_count = len([h for h, dc, _, _, _ in problematic if SEVERITY_HIGH < (dc + (len([x for x, c in cooccurrence[h].items() if c > FANOUT_THRESHOLD]) * 10)) <= SEVERITY_CRITICAL])
    moderate_count = total_problematic - critical_count - high_count
    
    # Print summary last
    print(f"\n{Style.BRIGHT}═══ Dependency Hell Summary ═══{Style.RESET_ALL}")
    print(f"  Analyzed: {len(rebuild_targets)} rebuild targets")
    print(f"  Method: clang-scan-deps (parallel, optimized)")
    print(f"  Found: {total_problematic} headers with >{args.threshold} transitive dependencies")
    print(f"  Severity breakdown: {Fore.RED}{critical_count} CRITICAL{Style.RESET_ALL}, "
          f"{Fore.YELLOW}{high_count} HIGH{Style.RESET_ALL}, "
          f"{Fore.CYAN}{moderate_count} MODERATE{Style.RESET_ALL}")
    print(f"\n{Style.BRIGHT}Metric Explanations:{Style.RESET_ALL}")
    print(f"  {Style.BRIGHT}Build Impact{Style.RESET_ALL} = deps × direct usage - measures compilation cost of header's dependencies")
    print(f"  {Style.BRIGHT}Rebuild Cost{Style.RESET_ALL} = usage × (1 + dependents) - measures rebuild impact if header changes")
    print(f"  {Style.BRIGHT}Hub Headers{Style.RESET_ALL} = reverse dependency count - shows architectural bottlenecks")
    
    # Show top 10 worst offenders
    if problematic:
        print(f"\n  {Style.BRIGHT}Top {args.top} Worst Offenders (by dependency count):{Style.RESET_ALL}")
        for i, (header, dep_count, usage_count, reverse_impact, chain_length) in enumerate(problematic[:args.top], 1):
            display_path = header
            if header.startswith(project_root):
                display_path = os.path.relpath(header, project_root)
            
            # Get severity color
            fanout = len([h for h, count in cooccurrence.get(header, {}).items() if count > FANOUT_THRESHOLD])
            combined_score = dep_count + (fanout * 10)
            
            if combined_score > SEVERITY_CRITICAL:
                severity_color = Fore.RED
            elif combined_score > SEVERITY_HIGH:
                severity_color = Fore.YELLOW
            else:
                severity_color = Fore.CYAN
            
            print(f"    {Style.DIM}{i:2}.{Style.RESET_ALL} {severity_color}{display_path}{Style.RESET_ALL} ({dep_count} deps, {usage_count} uses)")
        
        # Show top N by impact (deps * usage)
        print(f"\n  {Style.BRIGHT}Top {args.top} by Build Impact (deps × usage count):{Style.RESET_ALL}")
        by_impact = sorted(problematic, key=lambda x: x[1] * x[2], reverse=True)
        for i, (header, dep_count, usage_count, reverse_impact, chain_length) in enumerate(by_impact[:args.top], 1):
            display_path = header
            if header.startswith(project_root):
                display_path = os.path.relpath(header, project_root)
            
            impact = dep_count * usage_count
            
            # Color by impact
            if impact > 100000:
                impact_color = Fore.RED
            elif impact > 50000:
                impact_color = Fore.YELLOW
            else:
                impact_color = Fore.CYAN
            
            print(f"    {Style.DIM}{i:2}.{Style.RESET_ALL} {impact_color}{display_path}{Style.RESET_ALL} ({dep_count} deps × {usage_count} uses = {impact:,} total)")
        
        # NEW: Show top N by rebuild cost (what causes most expensive rebuilds if changed)
        print(f"\n  {Style.BRIGHT}Top {args.top} by Rebuild Cost (if changed, what causes worst rebuild):{Style.RESET_ALL}")
        by_rebuild_cost = sorted(problematic, key=lambda x: x[2] * (1 + x[3]), reverse=True)
        for i, (header, dep_count, usage_count, reverse_impact, chain_length) in enumerate(by_rebuild_cost[:args.top], 1):
            display_path = header
            if header.startswith(project_root):
                display_path = os.path.relpath(header, project_root)
            
            rebuild_cost = usage_count * (1 + reverse_impact)
            
            # Color by rebuild cost
            if rebuild_cost > 50000:
                cost_color = Fore.RED
            elif rebuild_cost > 20000:
                cost_color = Fore.YELLOW
            else:
                cost_color = Fore.CYAN
            
            print(f"    {Style.DIM}{i:2}.{Style.RESET_ALL} {cost_color}{display_path}{Style.RESET_ALL} "
                  f"({usage_count} uses × {reverse_impact} dependents = {rebuild_cost:,} source rebuilds)")
        
        # NEW: Show top N hub headers (most headers depend on these)
        print(f"\n  {Style.BRIGHT}Top {args.top} Hub Headers (most other headers depend on these):{Style.RESET_ALL}")
        by_hub = sorted(problematic, key=lambda x: x[3], reverse=True)
        for i, (header, dep_count, usage_count, reverse_impact, chain_length) in enumerate(by_hub[:args.top], 1):
            display_path = header
            if header.startswith(project_root):
                display_path = os.path.relpath(header, project_root)
            
            # Color by reverse impact
            if reverse_impact > 500:
                hub_color = Fore.RED
            elif reverse_impact > 200:
                hub_color = Fore.YELLOW
            else:
                hub_color = Fore.CYAN
            
            print(f"    {Style.DIM}{i:2}.{Style.RESET_ALL} {hub_color}{display_path}{Style.RESET_ALL} "
                  f"({reverse_impact} headers depend on this, max chain: {chain_length})")
    
    if not args.detailed and total_problematic > 0:
        print(f"\n  {Style.DIM}Use --detailed to see per-header analysis{Style.RESET_ALL}")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.debug("Exception details:", exc_info=True)
        sys.exit(1)
