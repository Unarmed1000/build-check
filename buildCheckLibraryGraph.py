#!/usr/bin/env python3
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
import re
from typing import Dict, Set, List, Tuple, Optional
from pathlib import Path
from collections import defaultdict, deque

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    print("WARNING: networkx not available. Some features will be limited.", file=sys.stderr)

try:
    from colorama import Fore, Style, init
    init(autoreset=True)
except ImportError:
    # Fallback if colorama not available
    class Fore:
        RED = YELLOW = GREEN = CYAN = BLUE = MAGENTA = ""
    class Style:
        BRIGHT = DIM = RESET_ALL = ""


def parse_ninja_build_file(build_ninja_path: str) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]], Set[str], Set[str]]:
    """
    Parse build.ninja to extract library and executable dependencies.
    
    Returns:
        Tuple of:
        - lib_to_libs: Library → Libraries it depends on
        - exe_to_libs: Executable → Libraries it depends on
        - all_libs: Set of all library names
        - all_exes: Set of all executable names
    """
    lib_to_libs: Dict[str, Set[str]] = defaultdict(set)
    exe_to_libs: Dict[str, Set[str]] = defaultdict(set)
    all_libs: Set[str] = set()
    all_exes: Set[str] = set()
    
    # Regex patterns for build rules
    # Format: build path/to/lib.a: CXX_STATIC_LIBRARY_LINKER ... || dependencies
    lib_pattern = re.compile(r'^build\s+(\S+\.a):\s+CXX_STATIC_LIBRARY_LINKER')
    exe_pattern = re.compile(r'^build\s+(\S+):\s+CXX_EXECUTABLE_LINKER')
    
    print(f"Parsing {build_ninja_path}...", file=sys.stderr)
    
    with open(build_ninja_path, 'r') as f:
        current_target = None
        current_type = None  # 'lib' or 'exe'
        
        for line_num, line in enumerate(f, 1):
            line = line.rstrip()
            
            # Check for library build rule
            lib_match = lib_pattern.match(line)
            if lib_match:
                lib_path = lib_match.group(1)
                lib_name = os.path.basename(lib_path)
                all_libs.add(lib_name)
                current_target = lib_name
                current_type = 'lib'
                
                # Extract dependencies from the || section
                if '||' in line:
                    deps_section = line.split('||')[1]
                    # Extract .a files from dependencies
                    deps = re.findall(r'(\S+\.a)', deps_section)
                    for dep_path in deps:
                        dep_name = os.path.basename(dep_path)
                        if dep_name != lib_name:  # Avoid self-dependencies
                            lib_to_libs[lib_name].add(dep_name)
                            all_libs.add(dep_name)
                continue
            
            # Check for executable build rule
            exe_match = exe_pattern.match(line)
            if exe_match:
                exe_path = exe_match.group(1)
                exe_name = os.path.basename(exe_path)
                all_exes.add(exe_name)
                current_target = exe_name
                current_type = 'exe'
                
                # Extract library dependencies from the || section
                if '||' in line:
                    deps_section = line.split('||')[1]
                    deps = re.findall(r'(\S+\.a)', deps_section)
                    for dep_path in deps:
                        dep_name = os.path.basename(dep_path)
                        exe_to_libs[exe_name].add(dep_name)
                        all_libs.add(dep_name)
                continue
    
    print(f"Found {len(all_libs)} libraries and {len(all_exes)} executables", file=sys.stderr)
    return dict(lib_to_libs), dict(exe_to_libs), all_libs, all_exes


def build_transitive_dependents(lib_to_libs: Dict[str, Set[str]], 
                                 exe_to_libs: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    """
    Build reverse dependency map showing all transitive dependents of each library.
    
    Returns mapping: library → set of all libraries/executables that depend on it (transitively)
    """
    transitive_deps: Dict[str, Set[str]] = defaultdict(set)
    
    # Build direct reverse dependencies
    lib_to_direct_dependents: Dict[str, Set[str]] = defaultdict(set)
    
    for lib, deps in lib_to_libs.items():
        for dep in deps:
            lib_to_direct_dependents[dep].add(lib)
    
    for exe, deps in exe_to_libs.items():
        for dep in deps:
            lib_to_direct_dependents[dep].add(exe)
    
    # Compute transitive closure using BFS
    for start_lib in lib_to_libs.keys():
        visited = set()
        queue = deque([start_lib])
        
        while queue:
            lib = queue.popleft()
            if lib in visited:
                continue
            visited.add(lib)
            
            for dependent in lib_to_direct_dependents.get(lib, set()):
                if dependent not in visited:
                    transitive_deps[start_lib].add(dependent)
                    queue.append(dependent)
    
    return dict(transitive_deps)


def find_cycles(lib_to_libs: Dict[str, Set[str]]) -> List[Set[str]]:
    """Find circular dependencies among libraries using Tarjan's algorithm."""
    if not HAS_NETWORKX:
        return []
    
    # Build directed graph
    G = nx.DiGraph()
    for lib, deps in lib_to_libs.items():
        G.add_node(lib)
        for dep in deps:
            G.add_edge(lib, dep)
    
    # Find strongly connected components
    sccs = list(nx.strongly_connected_components(G))
    
    # Filter out single-node SCCs (unless they have self-loops)
    cycles = []
    for scc in sccs:
        if len(scc) > 1:
            cycles.append(scc)
        elif len(scc) == 1:
            lib = next(iter(scc))
            if lib in lib_to_libs.get(lib, set()):
                cycles.append(scc)
    
    return cycles


def compute_library_metrics(lib_to_libs: Dict[str, Set[str]], 
                             exe_to_libs: Dict[str, Set[str]],
                             all_libs: Set[str]) -> Dict[str, Dict[str, int]]:
    """
    Compute metrics for each library:
    - fan_out: Number of direct library dependencies
    - fan_in: Number of libraries/executables that directly depend on this
    - transitive_dependents: Total number of libraries/executables that transitively depend on this
    - depth: Maximum depth in dependency tree (0 = leaf, higher = more foundational)
    """
    metrics = {}
    
    # Calculate fan-out (direct dependencies)
    for lib in all_libs:
        metrics[lib] = {
            'fan_out': len(lib_to_libs.get(lib, set())),
            'fan_in': 0,
            'transitive_dependents': 0,
            'depth': 0
        }
    
    # Calculate fan-in (direct dependents)
    for deps in lib_to_libs.values():
        for dep in deps:
            if dep in metrics:
                metrics[dep]['fan_in'] += 1
    
    for deps in exe_to_libs.values():
        for dep in deps:
            if dep in metrics:
                metrics[dep]['fan_in'] += 1
    
    # Calculate transitive dependents
    transitive_deps = build_transitive_dependents(lib_to_libs, exe_to_libs)
    for lib in all_libs:
        if lib in transitive_deps:
            metrics[lib]['transitive_dependents'] = len(transitive_deps[lib])
    
    # Calculate depth (longest path from this lib to any leaf)
    if HAS_NETWORKX:
        G = nx.DiGraph()
        for lib, deps in lib_to_libs.items():
            for dep in deps:
                G.add_edge(lib, dep)
        
        # Add all libraries as nodes (even isolated ones)
        for lib in all_libs:
            G.add_node(lib)
        
        try:
            # For each library, compute longest path to any reachable node
            for lib in all_libs:
                max_depth = 0
                if lib in G:
                    # BFS to find max distance
                    distances = nx.single_source_shortest_path_length(G, lib)
                    if distances:
                        max_depth = max(distances.values())
                metrics[lib]['depth'] = max_depth
        except Exception as e:
            print(f"Warning: Could not compute depths: {e}", file=sys.stderr)
    
    return metrics


def find_impacted_targets(library: str, 
                          lib_to_libs: Dict[str, Set[str]], 
                          exe_to_libs: Dict[str, Set[str]]) -> Tuple[Set[str], Set[str]]:
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


def visualize_library_graph(lib_to_libs: Dict[str, Set[str]], 
                             exe_to_libs: Dict[str, Set[str]],
                             metrics: Dict[str, Dict[str, int]],
                             all_libs: Set[str],
                             all_exes: Set[str],
                             top_n: int = 20,
                             libs_only: bool = False):
    """Display library dependency graph statistics and top libraries."""
    
    print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}LIBRARY DEPENDENCY GRAPH{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    
    # Summary statistics
    total_lib_deps = sum(len(deps) for deps in lib_to_libs.values())
    total_exe_deps = sum(len(deps) for deps in exe_to_libs.values())
    avg_lib_deps = total_lib_deps / len(all_libs) if all_libs else 0
    
    print(f"\n{Style.BRIGHT}Graph Properties:{Style.RESET_ALL}")
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
        print(f"  {Fore.YELLOW}Unused libraries: {len(unused_libs)}{Style.RESET_ALL}")
    
    # Top libraries by different metrics
    print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}TOP LIBRARIES BY IMPACT{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    
    # Sort by transitive dependents (build impact)
    sorted_by_impact = sorted(all_libs, 
                              key=lambda lib: metrics[lib]['transitive_dependents'], 
                              reverse=True)
    
    print(f"\n{Style.BRIGHT}Most Impactful Libraries (by transitive dependents):{Style.RESET_ALL}")
    print(f"{Style.DIM}Changes to these libraries affect the most targets{Style.RESET_ALL}\n")
    
    for i, lib in enumerate(sorted_by_impact[:top_n], 1):
        m = metrics[lib]
        impact_color = Fore.RED if m['transitive_dependents'] > 50 else Fore.YELLOW if m['transitive_dependents'] > 20 else Fore.GREEN
        print(f"{i:2}. {impact_color}{lib}{Style.RESET_ALL}")
        print(f"    Fan-in: {m['fan_in']} | Fan-out: {m['fan_out']} | "
              f"Transitive dependents: {m['transitive_dependents']} | Depth: {m['depth']}")
    
    # Sort by fan-in (most depended on directly)
    sorted_by_fanin = sorted(all_libs, key=lambda lib: metrics[lib]['fan_in'], reverse=True)
    
    print(f"\n{Style.BRIGHT}Most Depended-On Libraries (by direct dependents):{Style.RESET_ALL}")
    print(f"{Style.DIM}These libraries are directly used by many targets{Style.RESET_ALL}\n")
    
    for i, lib in enumerate(sorted_by_fanin[:top_n], 1):
        m = metrics[lib]
        print(f"{i:2}. {Fore.CYAN}{lib}{Style.RESET_ALL}")
        print(f"    Fan-in: {m['fan_in']} | Fan-out: {m['fan_out']} | "
              f"Transitive dependents: {m['transitive_dependents']} | Depth: {m['depth']}")
    
    # Sort by fan-out (most dependencies)
    sorted_by_fanout = sorted(all_libs, key=lambda lib: metrics[lib]['fan_out'], reverse=True)
    
    print(f"\n{Style.BRIGHT}Libraries with Most Dependencies:{Style.RESET_ALL}")
    print(f"{Style.DIM}These libraries depend on many other libraries{Style.RESET_ALL}\n")
    
    for i, lib in enumerate(sorted_by_fanout[:min(10, top_n)], 1):
        m = metrics[lib]
        print(f"{i:2}. {Fore.MAGENTA}{lib}{Style.RESET_ALL}")
        print(f"    Fan-in: {m['fan_in']} | Fan-out: {m['fan_out']} | "
              f"Transitive dependents: {m['transitive_dependents']} | Depth: {m['depth']}")
    
    if not libs_only:
        # Show some executables
        print(f"\n{Style.BRIGHT}Sample Executables:{Style.RESET_ALL}")
        for i, exe in enumerate(sorted(all_exes)[:10], 1):
            dep_count = len(exe_to_libs.get(exe, set()))
            print(f"  {exe} ({dep_count} library dependencies)")
        
        if len(all_exes) > 10:
            print(f"  {Style.DIM}... and {len(all_exes) - 10} more executables{Style.RESET_ALL}")


def export_to_dot(lib_to_libs: Dict[str, Set[str]], 
                  exe_to_libs: Dict[str, Set[str]],
                  output_path: str,
                  libs_only: bool = False):
    """Export dependency graph to GraphViz DOT format."""
    
    with open(output_path, 'w') as f:
        f.write("digraph LibraryDependencies {\n")
        f.write("  rankdir=LR;\n")
        f.write("  node [shape=box];\n\n")
        
        # Write library nodes
        f.write("  // Libraries\n")
        for lib in lib_to_libs.keys():
            label = lib.replace('.a', '').replace('lib', '')
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
    
    print(f"\n{Fore.GREEN}Exported to {output_path}{Style.RESET_ALL}")
    print(f"Visualize with: dot -Tpng {output_path} -o {output_path}.png")


def main():
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
        """
    )
    
    parser.add_argument('build_dir', 
                        help='Path to the ninja build directory containing build.ninja')
    parser.add_argument('--top', type=int, default=20,
                        help='Number of top libraries to display (default: 20)')
    parser.add_argument('--libs-only', action='store_true',
                        help='Show only libraries, exclude executables')
    parser.add_argument('--find-dependents', metavar='LIBRARY',
                        help='Find all targets that depend on the specified library')
    parser.add_argument('--impacted-by', metavar='LIBRARY',
                        help='Show what would be impacted by changes to the specified library')
    parser.add_argument('--export', metavar='FILE',
                        help='Export dependency graph to GraphViz DOT file')
    parser.add_argument('--cycles-only', action='store_true',
                        help='Only show circular library dependencies')
    
    args = parser.parse_args()
    
    # Validate build directory
    build_ninja_path = os.path.join(args.build_dir, 'build.ninja')
    if not os.path.exists(build_ninja_path):
        print(f"{Fore.RED}Error: build.ninja not found in '{args.build_dir}'{Style.RESET_ALL}", 
              file=sys.stderr)
        print(f"Please provide the path to the ninja build directory containing build.ninja", 
              file=sys.stderr)
        return 1
    
    # Parse build.ninja
    lib_to_libs, exe_to_libs, all_libs, all_exes = parse_ninja_build_file(build_ninja_path)
    
    # Find cycles if requested or if using NetworkX
    cycles = []
    if HAS_NETWORKX:
        cycles = find_cycles(lib_to_libs)
        if cycles:
            print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
            print(f"{Style.BRIGHT}CIRCULAR LIBRARY DEPENDENCIES{Style.RESET_ALL}")
            print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
            print(f"\n{Fore.RED}Found {len(cycles)} circular dependency groups:{Style.RESET_ALL}\n")
            
            for i, cycle in enumerate(sorted(cycles, key=len, reverse=True), 1):
                print(f"{Fore.RED}Cycle {i} ({len(cycle)} libraries):{Style.RESET_ALL}")
                for lib in sorted(cycle):
                    print(f"  • {lib}")
                print()
        else:
            if not args.cycles_only:
                print(f"\n{Fore.GREEN}✓ No circular library dependencies found{Style.RESET_ALL}")
    
    if args.cycles_only:
        return 0
    
    # Handle specific queries
    if args.find_dependents:
        lib = args.find_dependents
        if lib not in all_libs:
            print(f"{Fore.RED}Error: Library '{lib}' not found{Style.RESET_ALL}", file=sys.stderr)
            print(f"Available libraries: {', '.join(sorted(list(all_libs)[:10]))}...", file=sys.stderr)
            return 1
        
        impacted_libs, impacted_exes = find_impacted_targets(lib, lib_to_libs, exe_to_libs)
        
        print(f"\n{Style.BRIGHT}Targets depending on {lib}:{Style.RESET_ALL}\n")
        print(f"{Style.BRIGHT}Libraries ({len(impacted_libs)}):{Style.RESET_ALL}")
        for dep_lib in sorted(impacted_libs):
            print(f"  • {dep_lib}")
        
        print(f"\n{Style.BRIGHT}Executables ({len(impacted_exes)}):{Style.RESET_ALL}")
        for exe in sorted(impacted_exes):
            print(f"  • {exe}")
        
        print(f"\n{Style.BRIGHT}Total impact: {len(impacted_libs)} libraries + {len(impacted_exes)} executables = {len(impacted_libs) + len(impacted_exes)} targets{Style.RESET_ALL}")
        return 0
    
    if args.impacted_by:
        lib = args.impacted_by
        if lib not in all_libs:
            print(f"{Fore.RED}Error: Library '{lib}' not found{Style.RESET_ALL}", file=sys.stderr)
            return 1
        
        impacted_libs, impacted_exes = find_impacted_targets(lib, lib_to_libs, exe_to_libs)
        
        print(f"\n{Style.BRIGHT}BUILD IMPACT ANALYSIS: {lib}{Style.RESET_ALL}\n")
        print(f"If you modify {lib}, the following targets will need to be rebuilt:\n")
        
        print(f"{Style.BRIGHT}Impacted Libraries ({len(impacted_libs)}):{Style.RESET_ALL}")
        for dep_lib in sorted(impacted_libs)[:20]:
            print(f"  • {dep_lib}")
        if len(impacted_libs) > 20:
            print(f"  {Style.DIM}... and {len(impacted_libs) - 20} more{Style.RESET_ALL}")
        
        print(f"\n{Style.BRIGHT}Impacted Executables ({len(impacted_exes)}):{Style.RESET_ALL}")
        for exe in sorted(impacted_exes)[:20]:
            print(f"  • {exe}")
        if len(impacted_exes) > 20:
            print(f"  {Style.DIM}... and {len(impacted_exes) - 20} more{Style.RESET_ALL}")
        
        total_impact = len(impacted_libs) + len(impacted_exes)
        impact_pct = (total_impact / (len(all_libs) + len(all_exes))) * 100 if (all_libs or all_exes) else 0
        
        print(f"\n{Style.BRIGHT}Total Rebuild Impact: {total_impact} targets ({impact_pct:.1f}% of build){Style.RESET_ALL}")
        
        if total_impact > (len(all_libs) + len(all_exes)) * 0.5:
            print(f"{Fore.YELLOW}⚠ Warning: High impact library - changes affect >50% of build{Style.RESET_ALL}")
        
        return 0
    
    # Export if requested
    if args.export:
        export_to_dot(lib_to_libs, exe_to_libs, args.export, args.libs_only)
        if not args.libs_only:
            return 0
    
    # Compute metrics
    metrics = compute_library_metrics(lib_to_libs, exe_to_libs, all_libs)
    
    # Display main visualization
    visualize_library_graph(lib_to_libs, exe_to_libs, metrics, all_libs, all_exes, 
                            args.top, args.libs_only)
    
    # Recommendations
    print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}RECOMMENDATIONS{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}\n")
    
    if cycles:
        print(f"{Fore.RED}Priority: Break circular library dependencies{Style.RESET_ALL}")
        print(f"  • {len(cycles)} circular dependency groups found")
        print(f"  • Consider restructuring to eliminate cycles\n")
    
    # Find high-impact libraries
    high_impact = [lib for lib in all_libs if metrics[lib]['transitive_dependents'] > 50]
    if high_impact:
        print(f"{Fore.YELLOW}Build optimization opportunity:{Style.RESET_ALL}")
        print(f"  • {len(high_impact)} libraries impact >50 targets")
        print(f"  • Consider splitting these libraries to improve build parallelism")
        print(f"  • Top offenders: {', '.join(sorted(high_impact, key=lambda l: metrics[l]['transitive_dependents'], reverse=True)[:5])}\n")
    
    if len(lib_to_libs) == 0 and len(all_libs) > 0:
        print(f"{Fore.GREEN}Clean architecture:{Style.RESET_ALL}")
        print(f"  • No library→library dependencies (all libraries are independent)")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
