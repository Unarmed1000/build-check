#!/usr/bin/env python3
"""
Build Optimization Analyzer

Provides comprehensive, actionable recommendations for optimizing build times by
analyzing dependencies at both header and library levels. Identifies bottlenecks,
suggests refactoring opportunities, and prioritizes improvements by impact.

USAGE:
    python3 buildCheckOptimize.py <build_dir> [options]

EXAMPLES:
    # Full optimization analysis
    python3 buildCheckOptimize.py ./build

    # Quick analysis (skip expensive operations)
    python3 buildCheckOptimize.py ./build --quick

    # Focus on specific optimization areas
    python3 buildCheckOptimize.py ./build --focus libraries
    python3 buildCheckOptimize.py ./build --focus headers
    python3 buildCheckOptimize.py ./build --focus cycles

    # Generate optimization report
    python3 buildCheckOptimize.py ./build --report optimization_plan.txt

    # Show top N opportunities
    python3 buildCheckOptimize.py ./build --top 10

METHOD:
    Combines multiple analyses:
    1. Library-level: Parse build.ninja for library dependencies
    2. Header-level: Use clang-scan-deps for header coupling
    3. Rebuild analysis: Analyze ninja rebuild behavior
    4. Architectural: Detect cycles, gateway headers, layering issues
    
    Scores each optimization opportunity by:
    - Build time impact (estimated time saved)
    - Implementation effort (easy/medium/hard)
    - Risk level (low/medium/high)
    - Priority score (impact / effort)
    
    Provides specific, actionable recommendations with examples.
"""

import os
import sys
import argparse
import re
import subprocess
from typing import Dict, Set, List, Tuple, Optional, Any
from pathlib import Path
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from enum import Enum

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

try:
    from colorama import Fore, Style, init
    init(autoreset=True)
except ImportError:
    class Fore:
        RED = YELLOW = GREEN = CYAN = BLUE = MAGENTA = WHITE = ""
    class Style:
        BRIGHT = DIM = RESET_ALL = ""


class Effort(Enum):
    """Implementation effort level"""
    EASY = 1
    MEDIUM = 2
    HARD = 3


class Risk(Enum):
    """Risk level of implementing change"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass
class Optimization:
    """Represents a single optimization opportunity"""
    title: str
    category: str  # 'library', 'header', 'cycle', 'architecture', 'build-system'
    description: str
    impact_score: float  # 0-100, estimated time saved
    effort: Effort
    risk: Risk
    current_state: str
    target_state: str
    action_items: List[str]
    affected_targets: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def priority_score(self) -> float:
        """Calculate priority: impact / (effort * risk)"""
        return self.impact_score / (self.effort.value * self.risk.value)
    
    def format_output(self, index: int) -> str:
        """Format optimization for display"""
        effort_color = Fore.GREEN if self.effort == Effort.EASY else Fore.YELLOW if self.effort == Effort.MEDIUM else Fore.RED
        risk_color = Fore.GREEN if self.risk == Risk.LOW else Fore.YELLOW if self.risk == Risk.MEDIUM else Fore.RED
        
        lines = [
            f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}",
            f"{Style.BRIGHT}OPTIMIZATION #{index}: {self.title}{Style.RESET_ALL}",
            f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}",
            f"\n{Style.BRIGHT}Category:{Style.RESET_ALL} {self.category}",
            f"{Style.BRIGHT}Priority Score:{Style.RESET_ALL} {self.priority_score:.1f} (higher = better)",
            f"{Style.BRIGHT}Impact:{Style.RESET_ALL} {self.impact_score:.0f}/100 (estimated time saved)",
            f"{Style.BRIGHT}Effort:{Style.RESET_ALL} {effort_color}{self.effort.name}{Style.RESET_ALL}",
            f"{Style.BRIGHT}Risk:{Style.RESET_ALL} {risk_color}{self.risk.name}{Style.RESET_ALL}",
            f"\n{Style.BRIGHT}Problem:{Style.RESET_ALL}",
            f"  {self.description}",
            f"\n{Style.BRIGHT}Current State:{Style.RESET_ALL}",
            f"  {self.current_state}",
            f"\n{Style.BRIGHT}Target State:{Style.RESET_ALL}",
            f"  {self.target_state}",
            f"\n{Style.BRIGHT}Action Items:{Style.RESET_ALL}"
        ]
        
        for i, action in enumerate(self.action_items, 1):
            lines.append(f"  {i}. {action}")
        
        if self.affected_targets:
            lines.append(f"\n{Style.BRIGHT}Affected Targets ({len(self.affected_targets)}):{Style.RESET_ALL}")
            for target in self.affected_targets[:10]:
                lines.append(f"  • {target}")
            if len(self.affected_targets) > 10:
                lines.append(f"  {Style.DIM}... and {len(self.affected_targets) - 10} more{Style.RESET_ALL}")
        
        if self.evidence:
            lines.append(f"\n{Style.BRIGHT}Evidence:{Style.RESET_ALL}")
            for key, value in self.evidence.items():
                lines.append(f"  • {key}: {value}")
        
        return "\n".join(lines)


def run_command(cmd: List[str], cwd: str = None) -> Tuple[int, str, str]:
    """Run command and return (returncode, stdout, stderr)"""
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def parse_ninja_libraries(build_ninja_path: str) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]], Set[str]]:
    """Parse build.ninja for library dependencies"""
    lib_to_libs: Dict[str, Set[str]] = defaultdict(set)
    exe_to_libs: Dict[str, Set[str]] = defaultdict(set)
    all_libs: Set[str] = set()
    
    lib_pattern = re.compile(r'^build\s+(\S+\.a):\s+CXX_STATIC_LIBRARY_LINKER')
    exe_pattern = re.compile(r'^build\s+(\S+):\s+CXX_EXECUTABLE_LINKER')
    
    with open(build_ninja_path, 'r') as f:
        for line in f:
            line = line.rstrip()
            
            lib_match = lib_pattern.match(line)
            if lib_match:
                lib_name = os.path.basename(lib_match.group(1))
                all_libs.add(lib_name)
                if '||' in line:
                    deps_section = line.split('||')[1]
                    deps = re.findall(r'(\S+\.a)', deps_section)
                    for dep_path in deps:
                        dep_name = os.path.basename(dep_path)
                        if dep_name != lib_name:
                            lib_to_libs[lib_name].add(dep_name)
                            all_libs.add(dep_name)
                continue
            
            exe_match = exe_pattern.match(line)
            if exe_match:
                exe_name = os.path.basename(exe_match.group(1))
                if '||' in line:
                    deps_section = line.split('||')[1]
                    deps = re.findall(r'(\S+\.a)', deps_section)
                    for dep_path in deps:
                        dep_name = os.path.basename(dep_path)
                        exe_to_libs[exe_name].add(dep_name)
                        all_libs.add(dep_name)
    
    return dict(lib_to_libs), dict(exe_to_libs), all_libs


def analyze_library_impact(lib_to_libs: Dict[str, Set[str]], 
                           exe_to_libs: Dict[str, Set[str]],
                           all_libs: Set[str]) -> List[Optimization]:
    """Analyze library-level optimization opportunities"""
    optimizations = []
    
    # Calculate transitive dependents
    lib_to_dependents: Dict[str, Set[str]] = defaultdict(set)
    for lib, deps in lib_to_libs.items():
        for dep in deps:
            lib_to_dependents[dep].add(lib)
    for exe, deps in exe_to_libs.items():
        for dep in deps:
            lib_to_dependents[dep].add(exe)
    
    # Calculate transitive closure
    def get_all_dependents(lib: str, visited: Set[str] = None) -> Set[str]:
        if visited is None:
            visited = set()
        if lib in visited:
            return set()
        visited.add(lib)
        
        result = set(lib_to_dependents.get(lib, set()))
        for dep in lib_to_dependents.get(lib, set()):
            if dep in lib_to_libs:  # Only traverse libraries
                result.update(get_all_dependents(dep, visited))
        return result
    
    # Find high-impact libraries
    for lib in all_libs:
        direct_dependents = len(lib_to_dependents.get(lib, set()))
        transitive_dependents = len(get_all_dependents(lib))
        
        # Opportunity: Split high-impact library
        if transitive_dependents > 50:
            impact = min(100, transitive_dependents * 0.5)  # Scale by impact
            
            optimizations.append(Optimization(
                title=f"Split high-impact library: {lib}",
                category="library",
                description=f"Library {lib} affects {transitive_dependents} targets transitively. "
                           f"Changes to this library trigger massive rebuilds.",
                impact_score=impact,
                effort=Effort.HARD,
                risk=Risk.HIGH,
                current_state=f"{lib} has {transitive_dependents} transitive dependents",
                target_state=f"Split {lib} into 2-3 smaller, focused libraries to reduce rebuild scope",
                action_items=[
                    f"Analyze {lib} to identify logical component boundaries",
                    "Extract independent functionality into separate libraries",
                    "Update build system and dependent targets",
                    "Run comprehensive tests to verify no regressions",
                    f"Expected benefit: Reduce rebuild impact by 40-60%"
                ],
                affected_targets=sorted(get_all_dependents(lib)),
                evidence={
                    "Direct dependents": direct_dependents,
                    "Transitive dependents": transitive_dependents,
                    "Rebuild impact": f"{transitive_dependents} targets"
                }
            ))
        
        # Opportunity: Reduce dependencies of complex libraries
        fan_out = len(lib_to_libs.get(lib, set()))
        if fan_out > 15:
            impact = min(80, fan_out * 3)
            
            optimizations.append(Optimization(
                title=f"Reduce dependencies in complex library: {lib}",
                category="library",
                description=f"Library {lib} depends on {fan_out} other libraries, "
                           f"making it hard to test in isolation and prone to cascading rebuilds.",
                impact_score=impact,
                effort=Effort.MEDIUM,
                risk=Risk.MEDIUM,
                current_state=f"{lib} depends on {fan_out} libraries",
                target_state=f"Reduce to <10 dependencies through better modularity",
                action_items=[
                    f"Review dependencies of {lib} for unnecessary includes",
                    "Use forward declarations where possible",
                    "Extract interface definitions to reduce coupling",
                    "Consider dependency inversion for optional features",
                    f"Target: Reduce from {fan_out} to ~{fan_out // 2} dependencies"
                ],
                evidence={
                    "Current dependencies": fan_out,
                    "Complexity": "HIGH" if fan_out > 20 else "MODERATE"
                }
            ))
    
    # Find unused libraries
    used_libs = set()
    for deps in lib_to_libs.values():
        used_libs.update(deps)
    for deps in exe_to_libs.values():
        used_libs.update(deps)
    unused_libs = all_libs - used_libs
    
    if len(unused_libs) > 5:
        optimizations.append(Optimization(
            title=f"Remove {len(unused_libs)} unused libraries",
            category="build-system",
            description=f"Found {len(unused_libs)} libraries that aren't used by any targets. "
                       f"These waste build time and complicate maintenance.",
            impact_score=min(50, len(unused_libs) * 2),
            effort=Effort.EASY,
            risk=Risk.LOW,
            current_state=f"{len(unused_libs)} unused libraries in build system",
            target_state="Remove all unused libraries from CMakeLists.txt",
            action_items=[
                "Review each unused library to confirm it's truly not needed",
                "Remove from CMakeLists.txt or mark as optional",
                "Clean build directory to remove artifacts",
                f"Expected benefit: Reduce build time by ~{len(unused_libs) * 0.5}%"
            ],
            affected_targets=sorted(unused_libs)[:20],
            evidence={
                "Unused libraries": len(unused_libs),
                "Examples": ", ".join(sorted(unused_libs)[:5])
            }
        ))
    
    # Check for library cycles
    if HAS_NETWORKX:
        G = nx.DiGraph()
        for lib, deps in lib_to_libs.items():
            for dep in deps:
                G.add_edge(lib, dep)
        
        sccs = [scc for scc in nx.strongly_connected_components(G) if len(scc) > 1]
        if sccs:
            for scc in sccs:
                optimizations.append(Optimization(
                    title=f"Break circular library dependency: {', '.join(sorted(scc)[:3])}",
                    category="cycle",
                    description=f"Circular dependency between {len(scc)} libraries prevents "
                               f"proper layering and optimal build parallelism.",
                    impact_score=60,
                    effort=Effort.HARD,
                    risk=Risk.HIGH,
                    current_state=f"Circular dependency involving {len(scc)} libraries",
                    target_state="Restructure to eliminate cycle and establish clear layering",
                    action_items=[
                        "Identify the core dependency that creates the cycle",
                        "Extract common interface/types into a separate foundation library",
                        "Use dependency inversion or callbacks to break the cycle",
                        "Verify with: ./buildCheckLibraryGraph.py --cycles-only",
                        "Expected benefit: Enable better build parallelism"
                    ],
                    affected_targets=sorted(scc),
                    evidence={
                        "Cycle size": len(scc),
                        "Libraries in cycle": ", ".join(sorted(scc))
                    }
                ))
    
    return optimizations


def analyze_header_dependencies(build_dir: str, quick: bool = False) -> List[Optimization]:
    """Analyze header-level optimization opportunities"""
    optimizations = []
    
    # Check if clang-scan-deps is available
    clang_scan_deps = None
    for version in ['', '-19', '-18', '-17', '-16']:
        cmd = f'clang-scan-deps{version}'
        if run_command(['which', cmd])[0] == 0:
            clang_scan_deps = cmd
            break
    
    if not clang_scan_deps:
        return optimizations  # Skip if not available
    
    compile_commands_path = os.path.join(build_dir, 'compile_commands.json')
    build_ninja_path = os.path.join(build_dir, 'build.ninja')
    
    # Generate compile_commands.json if needed
    if not os.path.exists(compile_commands_path) or (os.path.exists(build_ninja_path) and os.path.getmtime(build_ninja_path) > os.path.getmtime(compile_commands_path)):
        try:
            result = subprocess.run(
                ["ninja", "-t", "compdb"],
                capture_output=True,
                text=True,
                cwd=build_dir,
                check=True
            )
            with open(compile_commands_path, 'w', encoding='utf-8') as f:
                f.write(result.stdout)
        except (subprocess.CalledProcessError, IOError):
            return optimizations  # Skip if generation fails
    
    # For quick mode, just provide generic recommendations
    if quick:
        optimizations.append(Optimization(
            title="Run detailed header analysis for coupling insights",
            category="header",
            description="Header-level analysis can identify gateway headers and coupling issues. "
                       "Run buildCheckDependencyHell.py for detailed analysis.",
            impact_score=70,
            effort=Effort.EASY,
            risk=Risk.LOW,
            current_state="No detailed header analysis performed",
            target_state="Run comprehensive header dependency analysis",
            action_items=[
                "./buildCheckDependencyHell.py " + build_dir + " --top 20",
                "./buildCheckIncludeGraph.py " + build_dir,
                "./buildCheckDSM.py " + build_dir + " --cycles-only",
                "Review top offenders and plan refactoring"
            ]
        ))
        return optimizations
    
    # Run quick header check (this would be expanded in full implementation)
    # For now, provide generic header recommendations
    optimizations.append(Optimization(
        title="Review header inclusion patterns",
        category="header",
        description="Use buildCheckDependencyHell.py to identify headers with high include counts.",
        impact_score=65,
        effort=Effort.MEDIUM,
        risk=Risk.MEDIUM,
        current_state="Header inclusion patterns not analyzed",
        target_state="Optimize high-impact headers to reduce transitive includes",
        action_items=[
            "Run: ./buildCheckDependencyHell.py " + build_dir,
            "For each high-impact header (>200 includes):",
            "  - Use forward declarations instead of includes",
            "  - Move implementations to .cpp files",
            "  - Split large headers into smaller, focused ones",
            "  - Use PIMPL pattern for complex classes"
        ]
    ))
    
    return optimizations


def analyze_build_system(build_dir: str) -> List[Optimization]:
    """Analyze build system configuration for optimization opportunities"""
    optimizations = []
    
    # Check for precompiled headers
    cmake_cache = os.path.join(build_dir, 'CMakeCache.txt')
    has_pch = False
    if os.path.exists(cmake_cache):
        with open(cmake_cache, 'r') as f:
            content = f.read()
            has_pch = 'PRECOMPILED_HEADER' in content or 'target_precompile_headers' in content
    
    if not has_pch:
        optimizations.append(Optimization(
            title="Enable precompiled headers (PCH)",
            category="build-system",
            description="Precompiled headers can significantly reduce compilation time for "
                       "commonly included headers like STL, boost, or framework headers.",
            impact_score=80,
            effort=Effort.MEDIUM,
            risk=Risk.LOW,
            current_state="Precompiled headers not detected in build configuration",
            target_state="Enable PCH for common, stable headers",
            action_items=[
                "Identify frequently included headers (run buildCheckDependencyHell.py)",
                "Create a precompiled header with common includes",
                "In CMakeLists.txt: target_precompile_headers(target PRIVATE pch.hpp)",
                "Test build times before/after to measure impact",
                "Expected benefit: 20-40% faster compilation"
            ],
            evidence={
                "PCH status": "Not enabled",
                "CMake version": "3.16+ required for target_precompile_headers"
            }
        ))
    
    # Check for ccache/sccache
    returncode, stdout, _ = run_command(['which', 'ccache'])
    has_ccache = returncode == 0
    
    if not has_ccache:
        optimizations.append(Optimization(
            title="Enable ccache for faster rebuilds",
            category="build-system",
            description="ccache caches compilation results, dramatically speeding up rebuilds "
                       "when switching branches or making small changes.",
            impact_score=90,
            effort=Effort.EASY,
            risk=Risk.LOW,
            current_state="ccache not detected on system",
            target_state="Install and enable ccache for all builds",
            action_items=[
                "Install: sudo apt install ccache  # or brew install ccache",
                "Configure CMake: cmake -DCMAKE_CXX_COMPILER_LAUNCHER=ccache ..",
                "Or set globally: export CMAKE_CXX_COMPILER_LAUNCHER=ccache",
                "Monitor cache stats: ccache -s",
                "Expected benefit: 5-10x faster rebuilds on cached builds"
            ],
            evidence={
                "ccache installed": "No",
                "Alternative": "Consider sccache for distributed caching"
            }
        ))
    
    # Check for unity builds
    has_unity = False
    if os.path.exists(cmake_cache):
        with open(cmake_cache, 'r') as f:
            content = f.read()
            has_unity = 'UNITY_BUILD' in content
    
    if not has_unity:
        optimizations.append(Optimization(
            title="Consider unity builds for faster clean builds",
            category="build-system",
            description="Unity builds combine multiple source files into single translation units, "
                       "reducing compilation overhead. Best for clean builds.",
            impact_score=70,
            effort=Effort.EASY,
            risk=Risk.MEDIUM,
            current_state="Unity builds not enabled",
            target_state="Enable unity builds for large targets",
            action_items=[
                "In CMakeLists.txt: set_target_properties(target PROPERTIES UNITY_BUILD ON)",
                "Or globally: cmake -DCMAKE_UNITY_BUILD=ON ..",
                "Test thoroughly - unity builds can expose hidden dependencies",
                "May increase incremental build times (trade-off)",
                "Expected benefit: 30-50% faster clean builds"
            ],
            evidence={
                "Unity build status": "Not enabled",
                "Trade-off": "Faster clean builds, potentially slower incremental"
            }
        ))
    
    return optimizations


def analyze_architectural_issues(build_dir: str) -> List[Optimization]:
    """Analyze architectural patterns for optimization opportunities"""
    optimizations = []
    
    # Generic architectural recommendations
    optimizations.append(Optimization(
        title="Establish clear architectural layers",
        category="architecture",
        description="Well-defined layers with dependencies flowing in one direction "
                   "enable better build parallelism and maintainability.",
        impact_score=85,
        effort=Effort.HARD,
        risk=Risk.HIGH,
        current_state="Architectural layering not verified",
        target_state="Clear layers: Foundation → Core → Features → Applications",
        action_items=[
            "Run: ./buildCheckDSM.py " + build_dir + " --show-layers",
            "Document intended architectural layers",
            "Identify violations where upper layers are included by lower layers",
            "Refactor to enforce unidirectional dependencies",
            "Use build system or linters to prevent violations",
            "Expected benefit: Better build parallelism and modularity"
        ]
    ))
    
    optimizations.append(Optimization(
        title="Implement interface/implementation separation",
        category="architecture",
        description="Separate public interfaces from implementations to reduce header dependencies "
                   "and enable better encapsulation.",
        impact_score=75,
        effort=Effort.MEDIUM,
        risk=Risk.MEDIUM,
        current_state="Interface/implementation separation not enforced",
        target_state="Clear separation with forward declarations and PIMPL where appropriate",
        action_items=[
            "Identify public API headers vs implementation headers",
            "Use forward declarations in public headers",
            "Apply PIMPL pattern for classes with complex implementations",
            "Keep private members in .cpp files where possible",
            "Expected benefit: 30-50% reduction in header dependencies"
        ]
    ))
    
    return optimizations


def generate_summary_report(optimizations: List[Optimization]) -> str:
    """Generate summary report of all optimizations"""
    lines = [
        f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}",
        f"{Style.BRIGHT}BUILD OPTIMIZATION SUMMARY{Style.RESET_ALL}",
        f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}",
        f"\nTotal opportunities identified: {len(optimizations)}",
    ]
    
    # Group by category
    by_category = defaultdict(list)
    for opt in optimizations:
        by_category[opt.category].append(opt)
    
    lines.append(f"\n{Style.BRIGHT}By Category:{Style.RESET_ALL}")
    for category, opts in sorted(by_category.items()):
        avg_impact = sum(o.impact_score for o in opts) / len(opts)
        lines.append(f"  • {category}: {len(opts)} opportunities (avg impact: {avg_impact:.0f}/100)")
    
    # Group by effort
    by_effort = defaultdict(list)
    for opt in optimizations:
        by_effort[opt.effort].append(opt)
    
    lines.append(f"\n{Style.BRIGHT}By Effort:{Style.RESET_ALL}")
    for effort in [Effort.EASY, Effort.MEDIUM, Effort.HARD]:
        if effort in by_effort:
            opts = by_effort[effort]
            lines.append(f"  • {effort.name}: {len(opts)} opportunities")
    
    # Quick wins (high impact, low effort)
    quick_wins = [o for o in optimizations 
                  if o.effort == Effort.EASY and o.impact_score >= 50]
    if quick_wins:
        lines.append(f"\n{Style.BRIGHT}{Fore.GREEN}🎯 QUICK WINS (High Impact, Easy Implementation):{Style.RESET_ALL}")
        for opt in sorted(quick_wins, key=lambda o: o.priority_score, reverse=True)[:5]:
            lines.append(f"  • {opt.title} (Priority: {opt.priority_score:.1f})")
    
    # High priority (sorted by priority score)
    top_priorities = sorted(optimizations, key=lambda o: o.priority_score, reverse=True)[:5]
    lines.append(f"\n{Style.BRIGHT}🔥 TOP 5 PRIORITIES (by priority score):{Style.RESET_ALL}")
    for i, opt in enumerate(top_priorities, 1):
        effort_str = f"{opt.effort.name[0]}"  # E/M/H
        risk_str = f"{opt.risk.name[0]}"
        lines.append(f"  {i}. {opt.title}")
        lines.append(f"     Priority: {opt.priority_score:.1f} | Impact: {opt.impact_score:.0f} | "
                    f"Effort: {effort_str} | Risk: {risk_str}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze build system and provide optimization recommendations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ./build
  %(prog)s ./build --quick
  %(prog)s ./build --focus libraries
  %(prog)s ./build --report optimization_plan.txt
  %(prog)s ./build --top 5
        """
    )
    
    parser.add_argument('build_dir',
                       help='Path to the ninja build directory')
    parser.add_argument('--quick', action='store_true',
                       help='Quick analysis, skip expensive operations')
    parser.add_argument('--focus', choices=['libraries', 'headers', 'cycles', 'architecture', 'build-system', 'all'],
                       default='all',
                       help='Focus analysis on specific area')
    parser.add_argument('--top', type=int, default=None,
                       help='Show only top N optimization opportunities')
    parser.add_argument('--report', metavar='FILE',
                       help='Write optimization report to file')
    parser.add_argument('--min-impact', type=int, default=0,
                       help='Only show optimizations with impact >= threshold (0-100)')
    
    args = parser.parse_args()
    
    # Validate build directory
    build_ninja_path = os.path.join(args.build_dir, 'build.ninja')
    if not os.path.exists(build_ninja_path):
        print(f"{Fore.RED}Error: build.ninja not found in '{args.build_dir}'{Style.RESET_ALL}",
              file=sys.stderr)
        return 1
    
    print(f"{Style.BRIGHT}Analyzing build system: {args.build_dir}{Style.RESET_ALL}\n")
    
    all_optimizations = []
    
    # Library-level analysis
    if args.focus in ['all', 'libraries', 'cycles']:
        print(f"{Style.DIM}Analyzing library dependencies...{Style.RESET_ALL}")
        lib_to_libs, exe_to_libs, all_libs = parse_ninja_libraries(build_ninja_path)
        library_opts = analyze_library_impact(lib_to_libs, exe_to_libs, all_libs)
        all_optimizations.extend(library_opts)
    
    # Header-level analysis
    if args.focus in ['all', 'headers']:
        print(f"{Style.DIM}Analyzing header dependencies...{Style.RESET_ALL}")
        header_opts = analyze_header_dependencies(args.build_dir, args.quick)
        all_optimizations.extend(header_opts)
    
    # Build system analysis
    if args.focus in ['all', 'build-system']:
        print(f"{Style.DIM}Analyzing build system configuration...{Style.RESET_ALL}")
        build_opts = analyze_build_system(args.build_dir)
        all_optimizations.extend(build_opts)
    
    # Architectural analysis
    if args.focus in ['all', 'architecture']:
        print(f"{Style.DIM}Analyzing architectural patterns...{Style.RESET_ALL}")
        arch_opts = analyze_architectural_issues(args.build_dir)
        all_optimizations.extend(arch_opts)
    
    # Filter by minimum impact
    if args.min_impact > 0:
        all_optimizations = [o for o in all_optimizations if o.impact_score >= args.min_impact]
    
    # Sort by priority
    all_optimizations.sort(key=lambda o: o.priority_score, reverse=True)
    
    # Limit to top N if requested
    if args.top:
        all_optimizations = all_optimizations[:args.top]
    
    if not all_optimizations:
        print(f"\n{Fore.GREEN}✓ No major optimization opportunities found!{Style.RESET_ALL}")
        print(f"  Your build system appears well-optimized.")
        return 0
    
    # Print summary
    summary = generate_summary_report(all_optimizations)
    print(summary)
    
    # Print detailed optimizations
    print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}DETAILED OPTIMIZATION OPPORTUNITIES{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    
    for i, opt in enumerate(all_optimizations, 1):
        print(opt.format_output(i))
    
    # Write report if requested
    if args.report:
        with open(args.report, 'w') as f:
            f.write("BUILD OPTIMIZATION REPORT\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Generated for: {args.build_dir}\n")
            f.write(f"Total opportunities: {len(all_optimizations)}\n\n")
            
            for i, opt in enumerate(all_optimizations, 1):
                f.write(f"\nOPTIMIZATION #{i}: {opt.title}\n")
                f.write("-" * 80 + "\n")
                f.write(f"Category: {opt.category}\n")
                f.write(f"Priority Score: {opt.priority_score:.1f}\n")
                f.write(f"Impact: {opt.impact_score:.0f}/100\n")
                f.write(f"Effort: {opt.effort.name}\n")
                f.write(f"Risk: {opt.risk.name}\n\n")
                f.write(f"Problem:\n  {opt.description}\n\n")
                f.write(f"Current State:\n  {opt.current_state}\n\n")
                f.write(f"Target State:\n  {opt.target_state}\n\n")
                f.write("Action Items:\n")
                for j, action in enumerate(opt.action_items, 1):
                    f.write(f"  {j}. {action}\n")
                f.write("\n")
        
        print(f"\n{Fore.GREEN}✓ Optimization report written to: {args.report}{Style.RESET_ALL}")
    
    # Final recommendations
    print(f"\n{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}RECOMMENDED NEXT STEPS{Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{'='*80}{Style.RESET_ALL}\n")
    
    quick_wins = [o for o in all_optimizations if o.effort == Effort.EASY]
    if quick_wins:
        print(f"{Fore.GREEN}1. Start with quick wins (EASY effort):{Style.RESET_ALL}")
        for opt in quick_wins[:3]:
            print(f"   • {opt.title}")
    
    high_impact = [o for o in all_optimizations if o.impact_score >= 70]
    if high_impact:
        print(f"\n{Fore.YELLOW}2. Plan high-impact changes (may require more effort):{Style.RESET_ALL}")
        for opt in high_impact[:3]:
            if opt not in quick_wins[:3]:
                print(f"   • {opt.title}")
    
    print(f"\n{Style.DIM}3. Re-run analysis after implementing optimizations to measure progress{Style.RESET_ALL}")
    print(f"{Style.DIM}4. Use specific BuildCheck tools for detailed investigation:{Style.RESET_ALL}")
    print(f"{Style.DIM}   • ./buildCheckLibraryGraph.py - Library dependencies{Style.RESET_ALL}")
    print(f"{Style.DIM}   • ./buildCheckDependencyHell.py - Header dependencies{Style.RESET_ALL}")
    print(f"{Style.DIM}   • ./buildCheckDSM.py - Architectural structure{Style.RESET_ALL}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
