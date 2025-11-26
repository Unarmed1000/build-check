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
"""Utilities for interacting with clang-scan-deps and analyzing C/C++ dependencies."""

import os
import json
import shlex
import logging
import subprocess
import multiprocessing as mp
import time
import re
from typing import List, Tuple, Set, Dict, DefaultDict, Optional
from collections import defaultdict
from dataclasses import dataclass

try:
    import networkx as nx
except ImportError:
    nx = None  # type: ignore

from lib.constants import COMPILE_COMMANDS_JSON, CLANG_SCAN_DEPS_CACHE_FILE, NINJA_COMMANDS_CACHE_FILE, MAX_CACHE_AGE_HOURS
from lib.color_utils import print_success, print_info, print_highlight
from lib.cache_utils import ensure_cache_dir, get_cache_path, load_cache, save_cache, cleanup_old_caches
from lib.package_verification import PACKAGE_REQUIREMENTS
from lib.tool_detection import CLANG_SCAN_DEPS_COMMANDS, find_clang_scan_deps, find_ninja

logger = logging.getLogger(__name__)

__all__ = ["find_clang_scan_deps", "is_valid_source_file", "is_valid_header_file", "build_include_graph", "IncludeGraphScanResult"]

# Constants
VALID_SOURCE_EXTENSIONS = (".cpp", ".c", ".cc", ".cxx")
VALID_HEADER_EXTENSIONS = (".h", ".hpp", ".hxx", ".hh")
COMPILER_NAMES = ("g++", "gcc", "clang++", "clang", "/c++")
SYSTEM_PATH_PREFIXES = ("/usr/", "/lib/", "/lib64/", "/opt/")


@dataclass
class IncludeGraphScanResult:
    """Result from building an include graph via clang-scan-deps.

    Attributes:
        source_to_deps: Mapping of source files to their dependency lists
        include_graph: Mapping of headers to the headers they directly include
        all_headers: Set of all discovered project headers
        scan_time: Time taken to run clang-scan-deps (in seconds)
    """

    source_to_deps: Dict[str, List[str]]
    include_graph: DefaultDict[str, Set[str]]
    all_headers: Set[str]
    scan_time: float

    def to_tuple(self) -> Tuple[Dict[str, List[str]], DefaultDict[str, Set[str]], Set[str], float]:
        """Convert to tuple for backward compatibility.

        Returns:
            Tuple of (source_to_deps, include_graph, all_headers, scan_time)
        """
        return (self.source_to_deps, self.include_graph, self.all_headers, self.scan_time)


def is_valid_source_file(filepath: str) -> bool:
    """Check if a file is a valid C/C++ source file.

    Args:
        filepath: Path to the file

    Returns:
        True if the file is a valid C/C++ source file
    """
    return any(filepath.endswith(ext) for ext in VALID_SOURCE_EXTENSIONS)


def is_valid_header_file(filepath: str) -> bool:
    """Check if a file is a valid C/C++ header file.

    Args:
        filepath: Path to the file

    Returns:
        True if the file is a valid C/C++ header file
    """
    return any(filepath.endswith(ext) for ext in VALID_HEADER_EXTENSIONS)


def is_system_header(filepath: str) -> bool:
    """Check if a header is a system header.

    Detects system headers including:
    - Standard prefixes: /usr/, /lib/, /lib64/, /opt/
    - C++ standard library headers under system paths (e.g., /usr/include/c++/*/iostream)

    Args:
        filepath: Path to the header file

    Returns:
        True if the header is a system header
    """
    # Check standard system path prefixes first
    # This catches most cases including /usr/include/c++/13/iostream
    for prefix in SYSTEM_PATH_PREFIXES:
        if filepath.startswith(prefix):
            return True

    return False


def sanitize_compile_command(command: str) -> str:
    """Sanitize compile command to remove problematic arguments for clang-scan-deps.

    Removes:
    - ccache wrapper and environment variables
    - linker-specific flags that clang-scan-deps doesn't understand
    - Response files (@file) that may cause issues

    Args:
        command: Original compile command string

    Returns:
        Sanitized command string suitable for clang-scan-deps
    """
    try:
        parts = shlex.split(command)
    except ValueError:
        # If we can't parse it, return as-is
        logger.debug("Failed to parse command for sanitization: %s", command[:100])
        return command

    sanitized_parts = []
    skip_next = False
    compiler_found = False

    # List of environment variable patterns that cause issues
    problematic_env_patterns = ["CCACHE_", "CC_", "CXX_"]

    # List of flags that should be removed entirely
    problematic_flags = ["-Wl,", "-Xlinker", "--linker-option"]  # Linker flags

    for i, part in enumerate(parts):
        if skip_next:
            skip_next = False
            continue

        # Skip environment variable assignments (KEY=VALUE format)
        if "=" in part and not part.startswith("-"):
            var_name = part.split("=", 1)[0]
            if any(var_name.startswith(pattern) for pattern in problematic_env_patterns):
                continue

        # Skip ccache wrapper
        if part == "ccache" or part.endswith("/ccache"):
            continue

        # Skip response files (they may contain ccache options)
        if part.startswith("@"):
            continue

        # Skip problematic linker flags
        if any(part.startswith(flag) for flag in problematic_flags):
            continue

        # Skip -Xlinker and its argument
        if part == "-Xlinker" and i + 1 < len(parts):
            skip_next = True
            continue

        # Track if we found the compiler
        if not compiler_found and any(compiler in part for compiler in COMPILER_NAMES):
            compiler_found = True

        sanitized_parts.append(part)

    # If no compiler was found in the sanitized command, log a warning
    if not compiler_found and sanitized_parts:
        logger.debug("Warning: No compiler found in sanitized command")

    return shlex.join(sanitized_parts) if sanitized_parts else command


def create_filtered_compile_commands(build_dir: str) -> str:
    """Create a filtered compile_commands.json with only C/C++ compilation entries.

    Args:
        build_dir: Path to the build directory

    Returns:
        Path to the filtered compile_commands.json file

    Raises:
        FileNotFoundError: If build directory doesn't exist
        RuntimeError: If ninja or file operations fail
        ValueError: If compile_commands.json is invalid or empty
    """
    build_dir = os.path.realpath(os.path.abspath(build_dir))
    if not os.path.isdir(build_dir):
        raise FileNotFoundError(f"Build directory not found: {build_dir}")

    compile_db = os.path.realpath(os.path.join(build_dir, COMPILE_COMMANDS_JSON))
    filtered_db = os.path.realpath(os.path.join(build_dir, "compile_commands_filtered.json"))
    build_ninja = os.path.realpath(os.path.join(build_dir, "build.ninja"))

    # Validate paths are within build_dir (prevent path traversal)
    for path in [compile_db, filtered_db, build_ninja]:
        if not path.startswith(build_dir + os.sep):
            raise ValueError(f"Path traversal detected: {path}")

    # Check if filtered DB exists and is newer than build.ninja
    if os.path.exists(filtered_db) and os.path.exists(build_ninja):
        filtered_age = os.path.getmtime(filtered_db)
        build_age = os.path.getmtime(build_ninja)
        if filtered_age > build_age:
            cache_age_hours = (os.path.getctime(filtered_db) - filtered_age) / 3600
            logger.debug("Using cached filtered compile commands: %s (cache age: %.1fh)", filtered_db, cache_age_hours)
            return filtered_db

        logger.debug("Filtered DB outdated (build.ninja is newer), regenerating...")

    # Generate compile_commands.json if needed
    if not os.path.exists(compile_db) or (os.path.exists(build_ninja) and os.path.getmtime(build_ninja) > os.path.getmtime(compile_db)):
        logger.info("Generating compile_commands.json...")
        try:
            result = subprocess.run(["ninja", "-t", "compdb"], capture_output=True, text=True, cwd=build_dir, check=True, timeout=60)
            with open(compile_db, "w", encoding="utf-8") as f:
                f.write(result.stdout)
            logger.debug("Generated: %s", compile_db)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to generate compile_commands.json: {e.stderr}") from e
        except (subprocess.TimeoutExpired, IOError) as e:
            raise RuntimeError(f"Failed to create compile_commands.json: {e}") from e

    # Filter to valid C/C++ entries
    try:
        with open(compile_db, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to read compile_commands.json: {e}") from e

    if not isinstance(data, list):
        raise ValueError(f"Invalid compile_commands.json format: expected list, got {type(data)}")

    valid_entries = []
    for entry in data:
        if not isinstance(entry, dict):
            logger.warning("Skipping invalid entry in compile_commands.json: %s", entry)
            continue
        cmd = entry.get("command", "")
        file = entry.get("file", "")
        if is_valid_source_file(file) and " -c " in cmd:
            # Sanitize the command to remove ccache and other problematic arguments
            sanitized_cmd = sanitize_compile_command(cmd)
            # Create a new entry with the sanitized command
            sanitized_entry = entry.copy()
            sanitized_entry["command"] = sanitized_cmd
            valid_entries.append(sanitized_entry)

    if not valid_entries:
        raise ValueError("No valid C/C++ compilation entries found in compile_commands.json")

    try:
        with open(filtered_db, "w", encoding="utf-8") as f:
            json.dump(valid_entries, f, indent=2)
        logger.info("Filtered to %s valid compilation entries", len(valid_entries))
    except IOError as e:
        raise IOError(f"Failed to write filtered compile commands: {e}") from e

    return filtered_db


def extract_include_paths_from_ninja(build_dir: str, timeout: int = 60) -> Optional[Set[str]]:
    """Extract include paths from ninja -t commands with persistent caching.

    This function caches the ninja commands output to avoid redundant parsing.
    The cache is invalidated when build.ninja is modified or exceeds max age.

    Args:
        build_dir: Path to the build directory
        timeout: Command timeout in seconds (default: 60)

    Returns:
        Set of absolute include path directories, or None if ninja fails
    """
    # Ensure cache directory exists
    ensure_cache_dir(build_dir)

    # Get cache path
    cache_path = get_cache_path(build_dir, NINJA_COMMANDS_CACHE_FILE)

    # Get build.ninja path for validation
    build_ninja_path = os.path.join(build_dir, "build.ninja")
    if not os.path.exists(build_ninja_path):
        logger.warning("build.ninja not found in %s", build_dir)
        return None

    # For cache validation, we use build.ninja as the "filtered_db" since that's what matters
    # The cache will be invalidated when build.ninja changes
    cached_result = load_cache(cache_path, build_ninja_path, build_ninja_path, MAX_CACHE_AGE_HOURS)

    if cached_result is not None:
        logger.debug("Using cached ninja commands include paths")
        # Cast from Any to the correct return type
        return set(cached_result) if isinstance(cached_result, (set, list)) else cached_result

    # Cache miss - run ninja -t commands
    ninja_tool = find_ninja()
    if not ninja_tool.is_found():
        logger.warning("ninja not found - cannot extract include paths from ninja")
        return None

    assert ninja_tool.command is not None, "Tool command should not be None when found"

    logger.info("Running %s -t commands to extract include paths...", ninja_tool.command)

    start_time = time.time()
    try:
        result = subprocess.run([ninja_tool.command, "-t", "commands"], capture_output=True, text=True, cwd=build_dir, timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.error("ninja -t commands timed out after %s seconds", timeout)
        return None
    except FileNotFoundError:
        logger.warning("ninja command not found")
        return None
    except Exception as e:
        logger.error("Unexpected error running ninja -t commands: %s", e)
        return None

    elapsed = time.time() - start_time

    if result.returncode != 0:
        logger.warning("ninja -t commands failed with code %s", result.returncode)
        if result.stderr:
            logger.debug("Stderr: %s", result.stderr[:500])
        return None

    # Parse include paths from commands output
    include_paths: Set[str] = set()

    # Compile regex patterns for efficiency
    # Match: -I<path>, -I <path>, -isystem <path>, -isystem<path>, -iquote <path>, -iquote<path>
    # Also match MSVC: /I<path>, /I <path>, /external:I <path>, /external:I<path>
    include_flag_pattern = re.compile(r"(?:^|\s)(-I|-isystem|-iquote|/I|/external:I)(\S+)?")

    for line in result.stdout.splitlines():
        # Each line is a complete command for a target
        # We only care about compilation commands (containing -c or /c)
        if " -c " not in line and " /c " not in line:
            continue

        try:
            # Find all include flags in the command
            matches = include_flag_pattern.finditer(line)
            for match in matches:
                flag = match.group(1)
                path_after_flag = match.group(2)

                if path_after_flag:
                    # Flag and path are together: -I/path or /I/path
                    include_path = path_after_flag
                else:
                    # Flag and path are separate: -I /path
                    # Find the next token after the flag
                    flag_pos = match.end(1)
                    rest_of_line = line[flag_pos:].lstrip()
                    # Extract the path (up to next space or quote)
                    if rest_of_line:
                        # Handle quoted paths
                        if rest_of_line[0] in ('"', "'"):
                            quote = rest_of_line[0]
                            end_quote = rest_of_line.find(quote, 1)
                            if end_quote != -1:
                                include_path = rest_of_line[1:end_quote]
                            else:
                                continue
                        else:
                            # Unquoted path - take up to next space
                            space_pos = rest_of_line.find(" ")
                            if space_pos != -1:
                                include_path = rest_of_line[:space_pos]
                            else:
                                include_path = rest_of_line
                    else:
                        continue

                # Normalize and validate path
                include_path = include_path.strip()
                if not include_path:
                    continue

                # Convert to absolute path if relative
                if not os.path.isabs(include_path):
                    include_path = os.path.abspath(os.path.join(build_dir, include_path))

                # Normalize path
                include_path = os.path.normpath(include_path)
                include_paths.add(include_path)

        except Exception as e:
            # Skip malformed lines
            logger.debug("Failed to parse line: %s (error: %s)", line[:100], e)
            continue

    logger.info("Extracted %s include paths from ninja commands (%.2fs)", len(include_paths), elapsed)

    # Save to cache
    if save_cache(cache_path, include_paths, build_ninja_path, build_ninja_path):
        logger.debug("Saved ninja commands include paths to cache")

    return include_paths


def extract_include_paths(compile_db_path: str, build_dir: Optional[str] = None) -> Set[str]:
    """Extract include paths from ninja commands or compile_commands.json.

    This function first attempts to extract include paths from ninja -t commands,
    which provides fully expanded compiler invocations with all include paths.
    If ninja is unavailable or fails, it falls back to parsing compile_commands.json.

    Args:
        compile_db_path: Path to compile_commands.json
        build_dir: Optional path to build directory (for ninja extraction)

    Returns:
        Set of absolute include path directories
    """
    valid_include_roots: Set[str] = set()

    # Try ninja-based extraction first if build_dir is provided
    if build_dir:
        ninja_paths = extract_include_paths_from_ninja(build_dir)
        if ninja_paths is not None and ninja_paths:
            logger.info("Using include paths from ninja commands (%s paths)", len(ninja_paths))
            return ninja_paths
        else:
            logger.info("Falling back to compile_commands.json parsing")

    # Fallback to JSON parsing
    try:
        with open(compile_db_path, "r", encoding="utf-8") as f:
            compile_db = json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        logger.error("Failed to read compile_commands.json: %s", e)
        return valid_include_roots

    for entry in compile_db:
        cmd = entry.get("command", "")
        # Extract -I, -isystem, -iquote paths
        try:
            parts = shlex.split(cmd)
        except ValueError as e:
            logger.debug("Failed to parse command: %s", e)
            continue

        for i, part in enumerate(parts):
            # Handle -I /path format
            if part in ("-I", "-isystem", "-iquote") and i + 1 < len(parts):
                include_path = parts[i + 1]
                if os.path.isabs(include_path):
                    valid_include_roots.add(include_path)
            # Handle -I/path format
            elif part.startswith(("-I", "-isystem", "-iquote")):
                for prefix in ("-I", "-isystem", "-iquote"):
                    if part.startswith(prefix):
                        include_path = part[len(prefix) :]
                        if include_path and os.path.isabs(include_path):
                            valid_include_roots.add(include_path)
                        break

    logger.debug("Found %s include directories from JSON", len(valid_include_roots))
    return valid_include_roots


def run_clang_scan_deps(build_dir: str, filtered_db: str, timeout: int = 300) -> Tuple[str, float]:
    """Run clang-scan-deps to analyze dependencies with persistent caching.

    This function caches the expensive clang-scan-deps output to disk to avoid
    redundant scanning across multiple tool invocations. The cache is invalidated
    when either the filtered compile_commands.json or build.ninja is modified,
    or when it exceeds the maximum age.

    Args:
        build_dir: Path to the build directory
        filtered_db: Path to filtered compile_commands.json
        timeout: Command timeout in seconds (default: 300)

    Returns:
        Tuple of (stdout output, elapsed time)

    Raises:
        RuntimeError: If clang-scan-deps is not found or fails
    """
    # Ensure cache directory exists
    ensure_cache_dir(build_dir)

    # Get cache path
    cache_path = get_cache_path(build_dir, CLANG_SCAN_DEPS_CACHE_FILE)

    # Get build.ninja path for validation
    build_ninja_path: Optional[str]
    build_ninja_path_candidate = os.path.join(build_dir, "build.ninja")
    if not os.path.exists(build_ninja_path_candidate):
        build_ninja_path = None
    else:
        build_ninja_path = build_ninja_path_candidate

    # Try to load from cache
    cached_result = load_cache(cache_path, filtered_db, build_ninja_path, MAX_CACHE_AGE_HOURS)

    if cached_result is not None:
        output, elapsed = cached_result
        logger.info("Using cached clang-scan-deps output (original scan took %.2fs)", elapsed)
        print_info(f"📦 Loading from cache (original scan took {elapsed:.2f}s)")
        return output, elapsed

    # Cache miss - run clang-scan-deps
    clang_tool = find_clang_scan_deps()
    if not clang_tool.is_found():
        raise RuntimeError("clang-scan-deps not found. Please install clang (e.g., 'sudo apt install clang-19')")

    # Assertion for mypy: if is_found() is True, command is not None
    assert clang_tool.command is not None, "Tool command should not be None when found"

    num_cores = mp.cpu_count()
    logger.info("Running %s using %s cores...", clang_tool.command, num_cores)
    print_info(f"🔄 Cache miss - running {clang_tool.command} (this may take a while)...")

    start_time = time.time()
    try:
        result = subprocess.run(
            [clang_tool.command, f"-compilation-database={filtered_db}", "-format=make", "-j", str(num_cores)],
            capture_output=True,
            text=True,
            cwd=build_dir,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{clang_tool.command} timed out after {timeout} seconds") from exc

    elapsed = time.time() - start_time

    if result.returncode != 0:
        error_msg = f"{clang_tool.command} failed with code {result.returncode}"
        if result.stderr:
            error_msg += f"\nError output: {result.stderr[:1000]}"
        raise RuntimeError(error_msg)

    # Save to cache
    cache_result = (result.stdout, elapsed)
    if save_cache(cache_path, cache_result, filtered_db, build_ninja_path):
        print_success(f"💾 Saved results to cache ({elapsed:.2f}s scan time)")

    # Periodic cleanup of old caches
    removed = cleanup_old_caches(build_dir, MAX_CACHE_AGE_HOURS)
    if removed > 0:
        print_info(f"🧹 Cleaned up {removed} old cache file(s)")

    return result.stdout, elapsed


def parse_clang_scan_deps_output(output: str, all_headers: Set[str]) -> Dict[str, List[str]]:
    """Parse clang-scan-deps makefile output into source-to-dependencies mapping.

    Args:
        output: clang-scan-deps stdout in makefile format
        all_headers: Set to populate with discovered header files

    Returns:
        Dictionary mapping source files to their dependencies
    """
    source_to_deps = {}
    current_target = None
    current_deps: List[str] = []

    for line in output.splitlines():
        # Check if this is a target line (ends with :)
        if ":" in line and not line.strip().startswith("/"):
            # Save previous target if exists
            if current_target and current_deps:
                source_to_deps[current_target] = current_deps
            # Start new target
            parts = line.split(":", 1)
            current_target = parts[0].strip()
            current_deps = []
            # Process any deps on the same line
            if len(parts) > 1:
                remainder = parts[1].strip()
                if remainder and remainder != "\\":
                    current_deps.append(remainder.rstrip("\\").strip())
        else:
            # This is a dependency line
            line = line.strip()
            if line and line != "\\":
                dep = line.rstrip("\\").strip()
                if dep:
                    current_deps.append(dep)
                    # Track headers
                    if is_valid_header_file(dep) and not is_system_header(dep):
                        all_headers.add(dep)

    # Save last target
    if current_target and current_deps:
        source_to_deps[current_target] = current_deps

    return source_to_deps


def build_header_to_header_graph(all_headers: Set[str]) -> DefaultDict[str, Set[str]]:
    """Build header-to-header include graph by parsing header files.

    Parses each header file to extract #include directives and resolves them
    to absolute paths of project headers. Uses multiple resolution strategies:
    1. Relative to the header's directory
    2. Basename lookup with path suffix matching

    Args:
        all_headers: Set of all project header file paths

    Returns:
        DefaultDict mapping each header to the set of headers it directly includes
    """
    header_to_direct_includes: DefaultDict[str, Set[str]] = defaultdict(set)
    include_pattern = re.compile(r'^\s*#\s*include\s+["<]([^">]+)[">]')

    # Build a lookup dict for fast header name resolution
    # Map: basename -> list of full paths (for quick lookup)
    header_basename_map: DefaultDict[str, List[str]] = defaultdict(list)
    for header in all_headers:
        basename = os.path.basename(header)
        header_basename_map[basename].append(header)

    # Parse each header file to find what it includes
    for header in all_headers:
        try:
            with open(header, "r", encoding="utf-8", errors="ignore") as f:
                header_dir = os.path.dirname(header)

                for line in f:
                    match = include_pattern.match(line)
                    if match:
                        included_file = match.group(1)
                        included_basename = os.path.basename(included_file)

                        # Try to resolve the included file to an absolute path
                        resolved_path = None

                        # Strategy 1: Check if it's relative to the current header's directory
                        candidate = os.path.normpath(os.path.join(header_dir, included_file))
                        if candidate in all_headers:
                            resolved_path = candidate

                        # Strategy 2: Look up by basename in our header map
                        if not resolved_path and included_basename in header_basename_map:
                            candidates = header_basename_map[included_basename]
                            # If there's only one match, use it
                            if len(candidates) == 1:
                                resolved_path = candidates[0]
                            else:
                                # Multiple matches - try to find the best one
                                # Prefer headers with matching path suffix
                                for candidate in candidates:
                                    if candidate.endswith(included_file.replace("\\", "/")):
                                        resolved_path = candidate
                                        break
                                # If still no match, use first candidate
                                if not resolved_path:
                                    resolved_path = candidates[0]

                        # Add to graph if resolved and is a project header
                        if resolved_path and resolved_path in all_headers:
                            header_to_direct_includes[header].add(resolved_path)

        except (IOError, OSError) as e:
            logger.debug("Could not read header %s: %s", header, e)
            continue

    total_edges = sum(len(deps) for deps in header_to_direct_includes.values())
    logger.info("Built include graph with %s direct header-to-header dependencies", total_edges)

    return header_to_direct_includes


def compute_transitive_deps(header: str, include_graph: Dict[str, Set[str]], _visited: Optional[Set[str]] = None, _depth: int = 0) -> Set[str]:
    """Compute all transitive dependencies of a header using NetworkX.

    Args:
        header: Header file path
        include_graph: Mapping of headers to their direct includes
        _visited: Deprecated parameter, kept for compatibility
        _depth: Deprecated parameter, kept for compatibility

    Returns:
        Set of all transitive dependencies

    Raises:
        ImportError: If networkx is not available
    """
    # Note: nx should always be available due to requirements, but check defensively
    assert nx is not None, "networkx is required but was not imported"

    # Build a graph for this computation
    G: nx.DiGraph[str] = nx.DiGraph()

    # Add all nodes and edges from include_graph
    for src, dests in include_graph.items():
        G.add_node(src)
        for dest in dests:
            G.add_edge(src, dest)

    # Use NetworkX descendants for efficient transitive closure
    if header in G:
        return nx.descendants(G, header)

    return set()


def build_include_graph(build_dir: str, verbose: bool = True) -> IncludeGraphScanResult:
    """Build a complete include graph from clang-scan-deps output.

    This function uses clang-scan-deps to obtain complete dependency information
    for all source files. The dependency information from clang-scan-deps includes
    the full transitive closure of dependencies, which is more accurate and complete
    than manually parsing header files.

    Args:
        build_dir: Path to the build directory
        verbose: If True, print progress messages to console (default: True)

    Returns:
        IncludeGraphScanResult with source dependencies, include graph, headers, and scan time

    Raises:
        RuntimeError: If clang-scan-deps is not available or fails
        FileNotFoundError: If required files are missing
    """
    try:
        # Check if clang-scan-deps is available
        clang_tool = find_clang_scan_deps()

        if not clang_tool.is_found():
            raise RuntimeError("clang-scan-deps not found. Please install clang (e.g., 'sudo apt install clang-19')")

        # Assertion for mypy: if is_found() is True, command is not None
        assert clang_tool.command is not None, "Tool command should not be None when found"

        try:
            filtered_db = create_filtered_compile_commands(build_dir)
        except Exception as e:
            raise RuntimeError(f"Failed to create filtered compile commands: {e}") from e

        if not os.path.exists(filtered_db):
            raise FileNotFoundError(f"Filtered compile commands not found: {filtered_db}")

        # Use cached clang-scan-deps execution
        logger.info("Running %s using cached execution to build include graph...", clang_tool.command)
        output, elapsed = run_clang_scan_deps(build_dir, filtered_db, timeout=300)

        # Parse makefile-style output to build include graph
        # Format is: target.o: source.cpp header1.hpp header2.hpp ...
        source_to_deps = {}
        header_to_direct_includes: DefaultDict[str, Set[str]] = defaultdict(set)
        all_headers = set()

        current_target = None
        current_deps: List[str] = []

        for line in output.splitlines():
            # Check if this is a target line (ends with :)
            if ":" in line and not line.strip().startswith("/"):
                # This is a target line
                parts = line.split(":", 1)
                # Save previous target if exists
                if current_target and current_deps:
                    source_to_deps[current_target] = current_deps
                # Start new target
                current_target = parts[0].strip()
                current_deps = []
                # Process any deps on the same line
                if len(parts) > 1:
                    remainder = parts[1].strip()
                    if remainder and remainder != "\\":
                        current_deps.append(remainder.rstrip("\\").strip())
            else:
                # This is a dependency line
                line = line.strip()
                if line and line != "\\":
                    # Remove trailing backslash and whitespace
                    dep = line.rstrip("\\").strip()
                    if dep:
                        current_deps.append(dep)

        # Save last target
        if current_target and current_deps:
            source_to_deps[current_target] = current_deps

        # Collect all unique project headers from the dependency lists
        for deps in source_to_deps.values():
            for dep in deps:
                if is_valid_header_file(dep) and not is_system_header(dep):
                    all_headers.add(dep)

        logger.info("Scanned %s source files in %.2fs", len(source_to_deps), elapsed)
        logger.info("Found %s unique project headers", len(all_headers))

        # Build header-to-header include graph by parsing header files
        logger.info("Building header-to-header include graph...")
        header_to_direct_includes = build_header_to_header_graph(all_headers)

        total_edges = sum(len(deps) for deps in header_to_direct_includes.values())

        if verbose:
            print_success(f"Scanned {len(source_to_deps)} source files in {elapsed:.2f}s")
            print_info("Building include graph from clang-scan-deps output...")
            print_highlight(f"Found {len(all_headers)} unique project headers")
            print_success(f"Built dependency graph with {len(all_headers)} headers and {total_edges} dependencies")

        return IncludeGraphScanResult(source_to_deps=source_to_deps, include_graph=header_to_direct_includes, all_headers=all_headers, scan_time=elapsed)
    except Exception as e:
        logger.error("Error building include graph: %s", e)
        raise


def parse_headers_from_physical_files(
    repo_path: str, include_system_headers: bool = False
) -> Tuple[Set[str], DefaultDict[str, Set[str]], Dict[str, List[str]]]:
    """Parse headers from physical file structure (for testing scenarios).

    Scans the include/ directory for .hpp files and parses their #include statements.
    Also reads compile_commands.json to map source files to their dependencies.

    Args:
        repo_path: Path to repository root containing include/ and src/ directories
        include_system_headers: If True, include system headers (default: False)

    Returns:
        Tuple of (all_headers, header_to_headers, source_to_deps)

    Raises:
        FileNotFoundError: If include directory or compile_commands.json not found
    """
    import json

    include_dir = os.path.join(repo_path, "include")
    compile_commands_path = os.path.join(repo_path, "compile_commands.json")

    if not os.path.exists(include_dir):
        raise FileNotFoundError(f"Include directory not found: {include_dir}")

    if not os.path.exists(compile_commands_path):
        raise FileNotFoundError(f"compile_commands.json not found: {compile_commands_path}")

    # Collect all header files
    all_headers: Set[str] = set()
    for root, dirs, files in os.walk(include_dir):
        for file in files:
            if file.endswith((".h", ".hpp", ".hxx", ".hh")):
                full_path = os.path.abspath(os.path.join(root, file))
                all_headers.add(full_path)

    # Build header-to-header graph by parsing headers
    header_to_headers = build_header_to_header_graph(all_headers)

    # Parse compile_commands.json for source-to-deps mapping
    source_to_deps: Dict[str, List[str]] = {}

    try:
        with open(compile_commands_path, "r") as f:
            compile_commands = json.load(f)

        for entry in compile_commands:
            source_file = entry.get("file", "")
            if not source_file or not is_valid_source_file(source_file):
                continue

            # For each source file, determine which headers it includes
            # By default, assume source includes its corresponding header
            source_basename = os.path.basename(source_file).replace(".cpp", ".hpp")
            deps: List[str] = []

            # Find matching header
            for header in all_headers:
                if os.path.basename(header) == source_basename:
                    deps.append(header)
                    # Add transitive dependencies from the header
                    if header in header_to_headers:
                        deps.extend(list(header_to_headers[header]))
                    break

            if deps:
                source_to_deps[source_file] = deps

    except (json.JSONDecodeError, IOError) as e:
        logger.warning("Failed to parse compile_commands.json: %s", e)
        # Create minimal source_to_deps from headers
        source_to_deps = {}
        for header in all_headers:
            source_file = header.replace("/include/", "/src/").replace(".hpp", ".cpp")
            deps = [header]
            if header in header_to_headers:
                deps.extend(list(header_to_headers[header]))
            source_to_deps[source_file] = deps

    return all_headers, header_to_headers, source_to_deps
