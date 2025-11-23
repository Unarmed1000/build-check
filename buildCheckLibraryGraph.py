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
"""
Library Dependency Graph Analyzer

Analyzes static library and executable dependencies from build.ninja to show
module-level dependency relationships. This provides a coarser-grained view than
header-level analysis, focusing on the build system's library structure.

USAGE:
    python3 buildCheckLibraryGraph.py <build_dir> [options]

EXAMPLES:
    # Show library dependency graph
    python3 buildCheckLibraryGraph.py ./build

    # Show only libraries (exclude executables)
    python3 buildCheckLibraryGraph.py ./build --libs-only

    # Find what depends on a specific library
    python3 buildCheckLibraryGraph.py ./build --find-dependents libFslBase.a

    # Show executables that depend on a library
    python3 buildCheckLibraryGraph.py ./build --impacted-by libFslBase.a

    # Export to GraphViz DOT format
    python3 buildCheckLibraryGraph.py ./build --export library_graph.dot

    # Show circular library dependencies
    python3 buildCheckLibraryGraph.py ./build --cycles-only

    # Exclude third-party and test libraries
    python3 buildCheckLibraryGraph.py ./build --exclude "*/ThirdParty/*" --exclude "*Test*"

METHOD:
    Parses build.ninja to extract:
    - Static library build rules (CXX_STATIC_LIBRARY_LINKER)
    - Executable build rules (CXX_EXECUTABLE_LINKER)
    - Library dependencies (from || order-only dependencies section)

    Builds directed graph showing:
    - Library → Library dependencies
    - Executable → Library dependencies

    Analyzes:
    - Most depended-on libraries (fan-in)
    - Most dependencies (fan-out)
    - Circular library dependencies
    - Build impact (transitive dependents)
    - Critical path depth
"""

import os
import sys
import argparse
from typing import Dict, Set, List, Tuple
from pathlib import Path
from collections import deque

import networkx as nx

# Import library modules
from lib.library_parser import parse_ninja_libraries, compute_library_metrics
from lib.graph_utils import find_strongly_connected_components
from lib.color_utils import Colors, print_warning, print_success
from lib.file_utils import exclude_headers_by_patterns


def find_cycles(lib_to_libs: Dict[str, Set[str]]) -> List[Set[str]]:
    """Find circular dependencies among libraries using Tarjan's algorithm."""

    # Build directed graph
    G: nx.DiGraph[str] = nx.DiGraph()
    for lib, deps in lib_to_libs.items():
        G.add_node(lib)
        for dep in deps:
            G.add_edge(lib, dep)

    # Use library function to find cycles
    cycles, self_loops = find_strongly_connected_components(G)

    return cycles


def find_impacted_targets(library: str, lib_to_libs: Dict[str, Set[str]], exe_to_libs: Dict[str, Set[str]]) -> Tuple[Set[str], Set[str]]:
    """
    Find all libraries and executables that would be impacted by changes to the given library.
    Returns (impacted_libs, impacted_exes)
    """
    impacted_libs = set()
    impacted_exes = set()

    # Build reverse dependency graph
    visited = set()
    queue = deque([library])

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        # Find libraries that depend on current
        for lib, deps in lib_to_libs.items():
            if current in deps and lib not in visited:
                impacted_libs.add(lib)
                queue.append(lib)

        # Find executables that depend on current
        for exe, deps in exe_to_libs.items():
            if current in deps:
                impacted_exes.add(exe)

    return impacted_libs, impacted_exes


def visualize_library_graph(
    lib_to_libs: Dict[str, Set[str]],
    exe_to_libs: Dict[str, Set[str]],
    metrics: Dict[str, Dict[str, int]],
    all_libs: Set[str],
    all_exes: Set[str],
    top_n: int = 20,
    libs_only: bool = False,
) -> None:
    """Display library dependency graph statistics and top libraries."""

    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}LIBRARY DEPENDENCY GRAPH{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")

    # Summary statistics
    total_lib_deps = sum(len(deps) for deps in lib_to_libs.values())
    total_exe_deps = sum(len(deps) for deps in exe_to_libs.values())
    avg_lib_deps = total_lib_deps / len(all_libs) if all_libs else 0

    print(f"\n{Colors.BRIGHT}Graph Properties:{Colors.RESET}")
    print(f"  Total libraries: {len(all_libs)}")
    print(f"  Total executables: {len(all_exes)}")
    print(f"  Library→Library edges: {total_lib_deps}")
    print(f"  Executable→Library edges: {total_exe_deps}")
    print(f"  Average dependencies per library: {avg_lib_deps:.1f}")

    # Leaf libraries (no dependencies)
    leaf_libs = [lib for lib in all_libs if not lib_to_libs.get(lib)]
    if leaf_libs:
        print(f"  Leaf libraries (no dependencies): {len(leaf_libs)}")

    # Unused libraries (nothing depends on them)
    used_libs = set()
    for deps in lib_to_libs.values():
        used_libs.update(deps)
    for deps in exe_to_libs.values():
        used_libs.update(deps)
    unused_libs = all_libs - used_libs
    if unused_libs:
        print(f"  {Colors.YELLOW}Unused libraries: {len(unused_libs)}{Colors.RESET}")

    # Top libraries by different metrics
    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}TOP LIBRARIES BY IMPACT{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")

    # Sort by transitive dependents (build impact)
    sorted_by_impact = sorted(all_libs, key=lambda lib: metrics[lib]["transitive_dependents"], reverse=True)

    print(f"\n{Colors.BRIGHT}Most Impactful Libraries (by transitive dependents):{Colors.RESET}")
    print(f"{Colors.DIM}Changes to these libraries affect the most targets{Colors.RESET}\n")

    for i, lib in enumerate(sorted_by_impact[:top_n], 1):
        m = metrics[lib]
        impact_color = Colors.RED if m["transitive_dependents"] > 50 else Colors.YELLOW if m["transitive_dependents"] > 20 else Colors.GREEN
        print(f"{i:2}. {impact_color}{lib}{Colors.RESET}")
        print(f"    Fan-in: {m['fan_in']} | Fan-out: {m['fan_out']} | " f"Transitive dependents: {m['transitive_dependents']} | Depth: {m['depth']}")

    # Sort by fan-in (most depended on directly)
    sorted_by_fanin = sorted(all_libs, key=lambda lib: metrics[lib]["fan_in"], reverse=True)

    print(f"\n{Colors.BRIGHT}Most Depended-On Libraries (by direct dependents):{Colors.RESET}")
    print(f"{Colors.DIM}These libraries are directly used by many targets{Colors.RESET}\n")

    for i, lib in enumerate(sorted_by_fanin[:top_n], 1):
        m = metrics[lib]
        print(f"{i:2}. {Colors.CYAN}{lib}{Colors.RESET}")
        print(f"    Fan-in: {m['fan_in']} | Fan-out: {m['fan_out']} | " f"Transitive dependents: {m['transitive_dependents']} | Depth: {m['depth']}")

    # Sort by fan-out (most dependencies)
    sorted_by_fanout = sorted(all_libs, key=lambda lib: metrics[lib]["fan_out"], reverse=True)

    print(f"\n{Colors.BRIGHT}Libraries with Most Dependencies:{Colors.RESET}")
    print(f"{Colors.DIM}These libraries depend on many other libraries{Colors.RESET}\n")

    for i, lib in enumerate(sorted_by_fanout[: min(10, top_n)], 1):
        m = metrics[lib]
        print(f"{i:2}. {Colors.MAGENTA}{lib}{Colors.RESET}")
        print(f"    Fan-in: {m['fan_in']} | Fan-out: {m['fan_out']} | " f"Transitive dependents: {m['transitive_dependents']} | Depth: {m['depth']}")

    if not libs_only:
        # Show some executables
        print(f"\n{Colors.BRIGHT}Sample Executables:{Colors.RESET}")
        for i, exe in enumerate(sorted(all_exes)[:10], 1):
            dep_count = len(exe_to_libs.get(exe, set()))
            print(f"  {exe} ({dep_count} library dependencies)")

        if len(all_exes) > 10:
            print(f"  {Colors.DIM}... and {len(all_exes) - 10} more executables{Colors.RESET}")


def export_to_dot(lib_to_libs: Dict[str, Set[str]], exe_to_libs: Dict[str, Set[str]], output_path: str, libs_only: bool = False) -> None:
    """Export dependency graph to GraphViz DOT format."""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("digraph LibraryDependencies {\n")
        f.write("  rankdir=LR;\n")
        f.write("  node [shape=box];\n\n")

        # Write library nodes
        f.write("  // Libraries\n")
        for lib in lib_to_libs.keys():
            label = lib.replace(".a", "").replace("lib", "")
            f.write(f'  "{lib}" [label="{label}", style=filled, fillcolor=lightblue];\n')

        if not libs_only:
            # Write executable nodes
            f.write("\n  // Executables\n")
            for exe in exe_to_libs.keys():
                f.write(f'  "{exe}" [label="{exe}", style=filled, fillcolor=lightgreen];\n')

        # Write library → library edges
        f.write("\n  // Library dependencies\n")
        for lib, deps in lib_to_libs.items():
            for dep in deps:
                f.write(f'  "{lib}" -> "{dep}";\n')

        if not libs_only:
            # Write executable → library edges
            f.write("\n  // Executable dependencies\n")
            for exe, deps in exe_to_libs.items():
                for dep in deps:
                    f.write(f'  "{exe}" -> "{dep}" [color=green];\n')

        f.write("}\n")

    print(f"\n{Colors.GREEN}Exported to {output_path}{Colors.RESET}")
    print(f"Visualize with: dot -Tpng {output_path} -o {output_path}.png")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze library dependency graph from build.ninja",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ./build
  %(prog)s ./build --libs-only
  %(prog)s ./build --find-dependents libFslBase.a
  %(prog)s ./build --impacted-by libFslBase.a
  %(prog)s ./build --export graph.dot
  %(prog)s ./build --cycles-only
  %(prog)s ./build --exclude "*/ThirdParty/*" --exclude "*Test*"
        """,
    )

    parser.add_argument("build_dir", help="Path to the ninja build directory containing build.ninja")
    parser.add_argument("--top", type=int, default=20, help="Number of top libraries to display (default: 20)")
    parser.add_argument("--libs-only", action="store_true", help="Show only libraries, exclude executables")
    parser.add_argument("--find-dependents", metavar="LIBRARY", help="Find all targets that depend on the specified library")
    parser.add_argument("--impacted-by", metavar="LIBRARY", help="Show what would be impacted by changes to the specified library")
    parser.add_argument("--export", metavar="FILE", help="Export dependency graph to GraphViz DOT file")
    parser.add_argument("--cycles-only", action="store_true", help="Only show circular library dependencies")
    parser.add_argument(
        "--exclude",
        type=str,
        action="append",
        metavar="PATTERN",
        help="Exclude libraries matching glob pattern (can be used multiple times). "
        "Useful for excluding third-party libraries, generated files, or test code. "
        "Supports glob patterns: * (any chars), ** (recursive), ? (single char). "
        'Examples: "*/ThirdParty/*", "*/build/*", "*Test*", "*/test/*"',
    )

    args = parser.parse_args()

    # Validate build directory
    build_ninja_path = os.path.join(args.build_dir, "build.ninja")
    if not os.path.exists(build_ninja_path):
        print(f"{Colors.RED}Error: build.ninja not found in '{args.build_dir}'{Colors.RESET}", file=sys.stderr)
        print("Please provide the path to the ninja build directory containing build.ninja", file=sys.stderr)
        return 1

    # Parse build.ninja
    lib_to_libs, exe_to_libs, all_libs, all_exes = parse_ninja_libraries(build_ninja_path)

    # Apply exclude patterns if specified
    if hasattr(args, "exclude") and args.exclude:
        try:
            project_root = str(Path(args.build_dir).parent)
        except Exception:
            project_root = os.path.dirname(os.path.abspath(args.build_dir))

        filtered_libs, excluded_count, no_match_patterns, _ = exclude_headers_by_patterns(all_libs, args.exclude, project_root)

        if excluded_count > 0:
            # Filter libraries from the dependency maps and executable dependencies
            excluded_libs = all_libs - filtered_libs
            lib_to_libs = {k: v - excluded_libs for k, v in lib_to_libs.items() if k in filtered_libs}
            exe_to_libs = {k: v - excluded_libs for k, v in exe_to_libs.items()}
            all_libs = filtered_libs
            print_success(f"Excluded {excluded_count} libraries matching {len(args.exclude)} pattern(s)", prefix=False)

        # Warn about patterns that matched nothing
        for pattern in no_match_patterns:
            print_warning(f"Exclude pattern '{pattern}' matched no libraries", prefix=False)

    # Find cycles if requested
    cycles = find_cycles(lib_to_libs)
    if cycles:
        print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
        print(f"{Colors.BRIGHT}CIRCULAR LIBRARY DEPENDENCIES{Colors.RESET}")
        print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}")
        print(f"\n{Colors.RED}Found {len(cycles)} circular dependency groups:{Colors.RESET}\n")

        for i, cycle in enumerate(sorted(cycles, key=len, reverse=True), 1):
            print(f"{Colors.RED}Cycle {i} ({len(cycle)} libraries):{Colors.RESET}")
            for lib in sorted(cycle):
                print(f"  • {lib}")
                print()

        if not cycles and not args.cycles_only:
            print(f"\n{Colors.GREEN}✓ No circular library dependencies found{Colors.RESET}")

    if args.cycles_only:
        return 0

    # Handle specific queries
    if args.find_dependents:
        lib = args.find_dependents
        if lib not in all_libs:
            print(f"{Colors.RED}Error: Library '{lib}' not found{Colors.RESET}", file=sys.stderr)
            print(f"Available libraries: {', '.join(sorted(list(all_libs)[:10]))}...", file=sys.stderr)
            return 1

        impacted_libs, impacted_exes = find_impacted_targets(lib, lib_to_libs, exe_to_libs)

        print(f"\n{Colors.BRIGHT}Targets depending on {lib}:{Colors.RESET}\n")
        print(f"{Colors.BRIGHT}Libraries ({len(impacted_libs)}):{Colors.RESET}")
        for dep_lib in sorted(impacted_libs):
            print(f"  • {dep_lib}")

        print(f"\n{Colors.BRIGHT}Executables ({len(impacted_exes)}):{Colors.RESET}")
        for exe in sorted(impacted_exes):
            print(f"  • {exe}")

        print(
            f"\n{Colors.BRIGHT}Total impact: {len(impacted_libs)} libraries + {len(impacted_exes)} executables = {len(impacted_libs) + len(impacted_exes)} targets{Colors.RESET}"
        )
        return 0

    if args.impacted_by:
        lib = args.impacted_by
        if lib not in all_libs:
            print(f"{Colors.RED}Error: Library '{lib}' not found{Colors.RESET}", file=sys.stderr)
            return 1

        impacted_libs, impacted_exes = find_impacted_targets(lib, lib_to_libs, exe_to_libs)

        print(f"\n{Colors.BRIGHT}BUILD IMPACT ANALYSIS: {lib}{Colors.RESET}\n")
        print(f"If you modify {lib}, the following targets will need to be rebuilt:\n")

        print(f"{Colors.BRIGHT}Impacted Libraries ({len(impacted_libs)}):{Colors.RESET}")
        for dep_lib in sorted(impacted_libs)[:20]:
            print(f"  • {dep_lib}")
        if len(impacted_libs) > 20:
            print(f"  {Colors.DIM}... and {len(impacted_libs) - 20} more{Colors.RESET}")

        print(f"\n{Colors.BRIGHT}Impacted Executables ({len(impacted_exes)}):{Colors.RESET}")
        for exe in sorted(impacted_exes)[:20]:
            print(f"  • {exe}")
        if len(impacted_exes) > 20:
            print(f"  {Colors.DIM}... and {len(impacted_exes) - 20} more{Colors.RESET}")

        total_impact = len(impacted_libs) + len(impacted_exes)
        impact_pct = (total_impact / (len(all_libs) + len(all_exes))) * 100 if (all_libs or all_exes) else 0

        print(f"\n{Colors.BRIGHT}Total Rebuild Impact: {total_impact} targets ({impact_pct:.1f}% of build){Colors.RESET}")

        if total_impact > (len(all_libs) + len(all_exes)) * 0.5:
            print(f"{Colors.YELLOW}⚠ Warning: High impact library - changes affect >50% of build{Colors.RESET}")

        return 0

    # Export if requested
    if args.export:
        export_to_dot(lib_to_libs, exe_to_libs, args.export, args.libs_only)
        if not args.libs_only:
            return 0

    # Compute metrics
    metrics = compute_library_metrics(lib_to_libs, exe_to_libs, all_libs)

    # Display main visualization
    visualize_library_graph(lib_to_libs, exe_to_libs, metrics, all_libs, all_exes, args.top, args.libs_only)

    # Recommendations
    print(f"\n{Colors.BRIGHT}{'='*80}{Colors.RESET}")
    print(f"{Colors.BRIGHT}RECOMMENDATIONS{Colors.RESET}")
    print(f"{Colors.BRIGHT}{'='*80}{Colors.RESET}\n")

    if cycles:
        print(f"{Colors.RED}Priority: Break circular library dependencies{Colors.RESET}")
        print(f"  • {len(cycles)} circular dependency groups found")
        print("  • Consider restructuring to eliminate cycles\n")

    # Find high-impact libraries
    high_impact = [lib for lib in all_libs if metrics[lib]["transitive_dependents"] > 50]
    if high_impact:
        print(f"{Colors.YELLOW}Build optimization opportunity:{Colors.RESET}")
        print(f"  • {len(high_impact)} libraries impact >50 targets")
        print("  • Consider splitting these libraries to improve build parallelism")
        print(f"  • Top offenders: {', '.join(sorted(high_impact, key=lambda l: metrics[l]['transitive_dependents'], reverse=True)[:5])}\n")

    if len(lib_to_libs) == 0 and len(all_libs) > 0:
        print(f"{Colors.GREEN}Clean architecture:{Colors.RESET}")
        print("  • No library→library dependencies (all libraries are independent)")

    return 0


if __name__ == "__main__":
    from lib.constants import EXIT_KEYBOARD_INTERRUPT, EXIT_RUNTIME_ERROR, BuildCheckError

    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(EXIT_KEYBOARD_INTERRUPT)
    except BuildCheckError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(e.exit_code)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(EXIT_RUNTIME_ERROR)
