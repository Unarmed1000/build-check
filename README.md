# BuildCheck Tools

A comprehensive suite of production-ready tools for analyzing C/C++ build dependencies, identifying rebuild bottlenecks, and optimizing compilation times in large projects.

## 📋 Overview

BuildCheck provides nine complementary tools that help you understand and optimize your C/C++ build process. Each tool focuses on a specific aspect of dependency analysis, from quick rebuild impact checks to comprehensive dependency hell detection and architectural structure analysis.

## 🛠️ Tools

### 1. buildCheckSummary.py - Quick Rebuild Analysis

**Purpose**: Fast analysis of what will rebuild and why.

**What it does**:
- Runs `ninja -n -d explain` to show rebuild reasons
- Categorizes rebuild causes
- Identifies root cause files triggering cascading rebuilds
- Provides summary statistics

**Use when**:
- You want a quick overview of rebuild reasons
- Checking what changed since last build
- Understanding ninja's rebuild decisions

**Performance**: Very fast (< 1 second)

**Requirements**:
- Python 3.7+
- ninja build system
- colorama (optional)

**Examples**:
```bash
# Basic analysis
./buildCheckSummary.py ../build/release/

# Detailed file list
./buildCheckSummary.py ../build/release/ --detailed

# JSON output
./buildCheckSummary.py ../build/release/ --format json
```

---

### 2. buildCheckImpact.py - Changed Header Impact Analysis

**Purpose**: Shows which headers are causing rebuilds and their impact.

**What it does**:
- Detects changed headers from ninja explain output
- Uses `ninja -t deps` to map header → target dependencies
- Shows how many compilation targets each changed header affects
- Can optionally show all high-impact headers

**Use when**:
- You've made changes and want to know what will rebuild
- Identifying which specific headers have the widest impact
- Quick baseline analysis without heavy dependencies

**Performance**: Very fast (< 1 second)

**Requirements**:
- Python 3.7+
- ninja build system
- colorama (optional)

**Examples**:
```bash
# Show changed headers and their impact
./buildCheckImpact.py ../build/release/

# Show all high-impact headers (not just changed)
./buildCheckImpact.py ../build/release/ --all-headers
```

**Key Metrics**:
- **Impact Count**: Number of targets that depend on each header

---

### 3. buildCheckIncludeChains.py - Cooccurrence Pattern Analysis

**Purpose**: Identifies which headers frequently appear together to find include chains.

**What it does**:
- Builds cooccurrence matrix showing which headers appear together
- For each changed header, shows frequently co-included headers
- Reveals coupling patterns and transitive include relationships
- Helps identify "gateway" headers pulling in dependencies

**Use when**:
- "Why is this header being included everywhere?"
- Finding which parent headers cause transitive includes
- Understanding coupling between seemingly unrelated headers
- Discovering refactoring opportunities

**Performance**: Fast (1-2 seconds)

**Requirements**:
- Python 3.7+
- ninja build system
- colorama (optional)

**Examples**:
```bash
# Show cooccurrence patterns for changed headers
./buildCheckIncludeChains.py ../build/release/

# Only show headers appearing together 10+ times
./buildCheckIncludeChains.py ../build/release/ --threshold 10
```

**Interpretation**:
- High cooccurrence = likely dependency relationship (direct or transitive)
- Use with buildCheckIncludeGraph.py to see actual include relationships

---

### 4. buildCheckIncludeGraph.py - Gateway Header Analysis

**Purpose**: Analyzes actual include graph using clang-scan-deps to find gateway headers.

**What it does**:
- Parses source files with clang-scan-deps for accurate dependencies
- Identifies "gateway headers" that pull in excessive dependencies
- Shows which specific .cpp files will rebuild for each changed header
- Calculates "include cost" metrics
- Provides gateway header rankings

**Use when**:
- "If I change this header, which .cpp files will rebuild?"
- Finding headers with high "include cost"
- Understanding why rebuilds are slow
- Identifying refactoring opportunities to reduce header bloat

**Performance**: Moderate (3-10 seconds, uses all CPU cores)

**Requirements**:
- Python 3.7+
- clang-scan-deps (clang-18, clang-19, or clang-XX)
- networkx: `pip install networkx`
- compile_commands.json (auto-generated)

**Examples**:
```bash
# Analyze changed headers (default)
./buildCheckIncludeGraph.py ../build/release/

# Show top 30 gateway headers regardless of changes
./buildCheckIncludeGraph.py ../build/release/ --full

# Analyze changed headers, show top 20 affected files
./buildCheckIncludeGraph.py ../build/release/ --top 20
```

**Key Metrics**:
- **Include Cost**: Average number of headers pulled in when this header is included
- **Unique Deps**: Total distinct headers that cooccur with this header
- **Usage Count**: Number of source files that include this header
- **Gateway Header**: Header with high include cost

---

### 5. buildCheckDependencyHell.py - Comprehensive Dependency Analysis

**Purpose**: Multi-dimensional analysis of header dependency problems using graph theory.

**What it does**:
- Builds complete transitive dependency graph with NetworkX
- Calculates multiple impact metrics per header:
  - Transitive dependency count
  - Build impact (deps × usage = total compilation cost)
  - Rebuild cost (sources that rebuild if changed)
  - Reverse impact (architectural bottlenecks)
  - Hub headers (highly connected nodes)
  - Maximum chain length (deepest include path)
- Classifies headers by severity (CRITICAL/HIGH/MODERATE)
- Provides multiple ranked lists for refactoring priorities

**Use when**:
- "Which headers should I refactor first to improve build times?"
- Finding architectural bottlenecks (hub headers)
- Identifying headers causing most compilation work
- Prioritizing technical debt reduction
- Comprehensive build optimization analysis

**Performance**: Slower but comprehensive (5-10 seconds, uses all CPU cores)

**Requirements**:
- Python 3.7+
- clang-scan-deps (clang-18, clang-19, or clang-XX)
- networkx: `pip install networkx`
- compile_commands.json (auto-generated)

**Examples**:
```bash
# Full analysis with all metrics
./buildCheckDependencyHell.py ../build/release/

# Show top 50 worst offenders
./buildCheckDependencyHell.py ../build/release/ --top 50

# Analyze specific header
./buildCheckDependencyHell.py ../build/release/ --header include/MyClass.hpp
```

**Key Metrics**:
- **Transitive Deps**: Total headers pulled in (direct + indirect)
- **Build Impact**: deps × usage = total header compilations
- **Rebuild Cost**: usage × (1 + dependents) = rebuild expense
- **Reverse Impact**: Number of headers depending on this one
- **Hub Header**: Architectural bottleneck with high reverse impact
- **Max Chain**: Longest include path through header

**Severity Levels**:
- **CRITICAL**: Combined score > 500 (urgent refactoring needed)
- **HIGH**: Combined score 300-500 (should refactor soon)
- **MODERATE**: Combined score < 300 (monitor)

---

### 6. buildCheckDSM.py - Dependency Structure Matrix Analysis

**Purpose**: Visualizes header dependencies as a matrix, revealing architectural structure at a glance.

**What it does**:
- Builds Dependency Structure Matrix showing header-to-header dependencies
- Detects circular dependencies using strongly connected components
- Computes architectural layers via topological sorting
- Calculates per-header metrics: fan-in, fan-out, stability, coupling
- Identifies headers that violate layered architecture
- Provides compact matrix visualization with color coding
- Exports full matrix to CSV for detailed offline analysis

**Use when**:
- "What's the overall dependency structure of my codebase?"
- "Which headers are in circular dependencies?"
- "Is my architecture properly layered?"
- "What's the safest order to refactor headers?"
- "Which headers have the highest coupling?"
- "Are my module boundaries clean?"

**Performance**: Moderate (3-10 seconds, uses all CPU cores)

**Requirements**:
- Python 3.7+
- clang-scan-deps (clang-18, clang-19, or clang-XX)
- networkx: `pip install networkx`
- compile_commands.json (auto-generated)

**Examples**:
```bash
# Basic DSM analysis
./buildCheckDSM.py ../build/release/

# Show only top 50 most coupled headers
./buildCheckDSM.py ../build/release/ --top 50

# Focus on circular dependencies
./buildCheckDSM.py ../build/release/ --cycles-only

# Show dependency layers
./buildCheckDSM.py ../build/release/ --show-layers

# Export full matrix to CSV
./buildCheckDSM.py ../build/release/ --export matrix.csv

# Filter to specific module
./buildCheckDSM.py ../build/release/ --filter "FslBase/*"

# Cluster by directory
./buildCheckDSM.py ../build/release/ --cluster-by-directory
```

**Key Metrics**:
- **Fan-out**: Number of headers this header includes
- **Fan-in**: Number of headers that include this header
- **Coupling**: Total dependencies (fan-in + fan-out)
- **Stability**: Fan-out / (Fan-in + Fan-out) — resistance to change
- **Sparsity**: Percentage of empty cells in matrix (higher = better)
- **Module Cohesion**: Intra-module vs inter-module dependencies

**Matrix Visualization**:
```
        0  1  2  3  4  5
●Header1                0  ─  X  ·  ·  ·  · 
 Header2                1  ·  ─  X  ·  ·  · 
●Header3                2  X  X  ─  X  ·  · 
 Header4                3  X  ·  X  ─  X  · 
 Header5                4  X  X  X  X  ─  X 
●Header6                5  X  X  ·  X  X  ─ 

Legend: X = dependency, · = none, ● = in cycle
```

---

### 7. buildCheckLibraryGraph.py - Library Dependency Analysis

**Purpose**: Analyzes library and executable dependencies at the build system level.

**What it does**:
- Parses build.ninja to extract static library (.a) dependencies
- Builds library-to-library dependency graph
- Shows which executables depend on which libraries
- Calculates build impact (what rebuilds if you change a library)
- Detects circular library dependencies
- Identifies most impactful libraries for build optimization
- Ranks libraries by fan-in, fan-out, and transitive dependencies
- Exports to GraphViz DOT format for visualization

**Use when**:
- "If I change libFslBase, what needs to rebuild?"
- "Which libraries are used by the most targets?"
- "Are there circular dependencies between libraries?"
- "Which library changes cause the biggest rebuild impact?"
- "What's the module-level architecture?"
- Planning library refactoring or splitting

**Performance**: Very fast (< 1 second)

**Requirements**:
- Python 3.7+
- build.ninja file
- networkx (optional, for cycle detection): `pip install networkx`
- colorama (optional, for colors)

**Examples**:
```bash
# Show library dependency graph
./buildCheckLibraryGraph.py ../build/release/

# Show impact of changing a specific library
./buildCheckLibraryGraph.py ../build/release/ --impacted-by libFslBase.a

# Find what depends on a library
./buildCheckLibraryGraph.py ../build/release/ --find-dependents libFslGraphics.a

# Show only libraries (exclude executables)
./buildCheckLibraryGraph.py ../build/release/ --libs-only

# Export to GraphViz DOT for visualization
./buildCheckLibraryGraph.py ../build/release/ --export library_graph.dot

# Check for circular library dependencies
./buildCheckLibraryGraph.py ../build/release/ --cycles-only
```

**Key Metrics**:
- **Fan-in**: Number of targets that directly depend on this library
- **Fan-out**: Number of libraries this library directly depends on
- **Transitive dependents**: Total targets affected by changes (build impact)
- **Depth**: Longest dependency path from library to any leaf

**Sample Output**:
```
Top Impactful Libraries:
  1. libFslBase.a
     Fan-in: 95 | Fan-out: 0 | Transitive dependents: 95 | Depth: 0
     
  2. libFslGraphics.a
     Fan-in: 84 | Fan-out: 1 | Transitive dependents: 84 | Depth: 1

BUILD IMPACT ANALYSIS: libFslBase.a
  If you modify libFslBase.a, the following need rebuild:
  - 87 libraries
  - 8 executables
  Total Rebuild Impact: 95 targets (97.9% of build)
```

**Visualization**:
```bash
# Generate GraphViz visualization
./buildCheckLibraryGraph.py ../build/ --export graph.dot
dot -Tpng graph.dot -o graph.png
```

---

### 8. buildCheckOptimize.py - Build Optimization Analyzer

**Purpose**: Provides comprehensive, actionable recommendations for optimizing build times.

**What it does**:
- Analyzes dependencies at library and header levels
- Identifies bottlenecks and optimization opportunities
- Scores each opportunity by impact, effort, and risk
- Prioritizes improvements by return on investment
- Provides specific, actionable recommendations
- Detects unused libraries, missing build tools (ccache, PCH)
- Suggests architectural improvements
- Generates optimization reports

**Use when**:
- "How can I speed up my builds?"
- "What are the biggest build time bottlenecks?"
- Planning build system improvements
- Evaluating refactoring opportunities
- Setting up new development environments
- Optimizing CI/CD build times

**Performance**: Fast to moderate (2-10 seconds depending on analysis depth)

**Requirements**:
- Python 3.7+
- build.ninja file
- networkx (optional): `pip install networkx`
- colorama (optional)

**Examples**:
```bash
# Full optimization analysis
./buildCheckOptimize.py ../build/release/

# Quick analysis (skip expensive operations)
./buildCheckOptimize.py ../build/release/ --quick

# Focus on specific area
./buildCheckOptimize.py ../build/release/ --focus libraries
./buildCheckOptimize.py ../build/release/ --focus build-system

# Show only top 5 opportunities
./buildCheckOptimize.py ../build/release/ --top 5

# Generate detailed report
./buildCheckOptimize.py ../build/release/ --report optimization_plan.txt

# Show only high-impact optimizations
./buildCheckOptimize.py ../build/release/ --min-impact 70
```

**Key Metrics**:
- **Priority Score**: Impact / (Effort × Risk) - higher is better
- **Impact Score**: 0-100, estimated time saved
- **Effort**: EASY, MEDIUM, or HARD to implement
- **Risk**: LOW, MEDIUM, or HIGH risk of breaking things

**Sample Output**:
```
BUILD OPTIMIZATION SUMMARY

Total opportunities identified: 36

🎯 QUICK WINS (High Impact, Easy Implementation):
  • Enable ccache for faster rebuilds (Priority: 90.0)
  • Remove 43 unused libraries (Priority: 50.0)
  • Enable precompiled headers (Priority: 40.0)

🔥 TOP 5 PRIORITIES (by priority score):
  1. Enable ccache for faster rebuilds
     Priority: 90.0 | Impact: 90 | Effort: E | Risk: L
  2. Run detailed header analysis
     Priority: 70.0 | Impact: 70 | Effort: E | Risk: L
  3. Remove 43 unused libraries
     Priority: 50.0 | Impact: 50 | Effort: E | Risk: L

DETAILED OPTIMIZATION #1: Enable ccache
  Problem: ccache caches compilation results
  Action Items:
    1. Install: sudo apt install ccache
    2. Configure CMake: cmake -DCMAKE_CXX_COMPILER_LAUNCHER=ccache ..
    3. Expected benefit: 5-10x faster rebuilds
```

**Optimization Categories**:
- **library**: Library-level refactoring (split, reduce dependencies)
- **header**: Header-level improvements (forward declarations, PIMPL)
- **cycle**: Breaking circular dependencies
- **architecture**: Architectural patterns (layering, separation)
- **build-system**: Build tools and configuration (ccache, PCH, unity builds)

---

### 9. buildCheckRippleEffect.py - Git Commit Impact Analysis

**Purpose**: Shows what will recompile based on git changes.

**What it does**:
- Detects changed files from git commit (or commit range)
- Uses clang-scan-deps to build complete dependency graph
- For changed headers: finds all source files that transitively depend on them
- For changed source files: marks them for recompilation
- Calculates total rebuild impact with detailed breakdown

**Use when**:
- "If I commit this change, what will rebuild?"
- Estimating CI/CD build time before pushing
- Reviewing code changes with rebuild cost in mind
- Identifying high-impact changes needing extra testing

**Performance**: Moderate (5-10 seconds, uses all CPU cores)

**Requirements**:
- Python 3.7+
- git repository
- ninja build directory with compile_commands.json
- clang-scan-deps (clang-18, clang-19, or clang-XX)
- networkx: `pip install networkx`

**Examples**:
```bash
# Analyze last commit's impact
./buildCheckRippleEffect.py ../build/release/

# Analyze specific commit
./buildCheckRippleEffect.py ../build/release/ --commit abc123

# Specify git repository location
./buildCheckRippleEffect.py ../build/release/ --repo ~/projects/myproject

# Analyze commit range (cumulative impact)
./buildCheckRippleEffect.py ../build/release/ --commit HEAD~5..HEAD
```

**Output**:
- List of changed files (headers and sources)
- For each changed header: affected source files
- Summary: files changed, sources affected, rebuild percentage
- Color-coded severity based on rebuild impact

---

## 🎯 Which Tool Should I Use?

### Quick Checks (< 1 second)
- **buildCheckSummary.py** - "What changed and why is ninja rebuilding?"
- **buildCheckImpact.py** - "Which changed headers affect the most targets?"

### Pattern Analysis (1-2 seconds)
- **buildCheckIncludeChains.py** - "Why do these headers always appear together?"

### Source-Level Analysis (3-10 seconds)
- **buildCheckIncludeGraph.py** - "Which .cpp files rebuild if I change this header?"
- **buildCheckDependencyHell.py** - "Which headers are the worst offenders?"
- **buildCheckDSM.py** - "What's the architectural structure? Any cycles?"
- **buildCheckRippleEffect.py** - "What will rebuild if I commit this change?"

### Workflow Recommendations

**Daily Development**:
1. `buildCheckSummary.py` - Quick check after pulling changes
2. `buildCheckImpact.py` - See what your changes affect

**Before Committing**:
1. `buildCheckRippleEffect.py` - Estimate rebuild impact
2. Review affected files and test accordingly

**Architectural Review**:
1. `buildCheckDSM.py` - View overall structure and identify cycles
2. `buildCheckDependencyHell.py` - Find worst offenders
3. `buildCheckIncludeGraph.py` - Understand gateway headers
4. Plan refactoring based on DSM layers and coupling metrics

**Refactoring / Optimization**:
1. `buildCheckDSM.py` - Identify cycles and high-coupling headers
2. `buildCheckDependencyHell.py` - Prioritize by impact scores
3. `buildCheckIncludeGraph.py` - Find gateway headers
4. `buildCheckIncludeChains.py` - Understand coupling patterns
5. Refactor high-impact headers first, break cycles

---

## 🚀 Installation

### Prerequisites

**Required** (all tools):
```bash
# Python 3.7 or higher
python3 --version

# Ninja build system
ninja --version
```

**Optional** (for colored output):
```bash
pip install colorama
```

**Required** (for tools 4, 5, 6):
```bash
# NetworkX for graph analysis
pip install networkx

# clang-scan-deps (part of LLVM/Clang)
# Ubuntu/Debian:
sudo apt install clang-19
# or
sudo apt install clang-18

# Verify installation
clang-scan-deps-19 --version
# or
clang-scan-deps-18 --version
```

### Setup

1. Clone or download the BuildCheck tools
2. Make scripts executable:
```bash
chmod +x buildCheck*.py
```

3. Ensure your project has `compile_commands.json`:
```bash
# Generated automatically by CMake with:
cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

# Or manually from Ninja build directory:
ninja -t compdb > compile_commands.json
```

---

## 📊 Understanding the Output

### Color Coding

All tools use consistent color coding (when colorama is available):

- 🔴 **Red**: Critical issues or high-impact items
- 🟡 **Yellow**: Warnings or moderate-impact items
- 🟢 **Green**: Success or low-impact items
- 🔵 **Cyan**: File paths and identifiers
- ⚪ **White**: Headers and section titles

### Common Metrics Across Tools

- **Dependency Count**: Number of headers a file depends on
- **Usage Count**: Number of source files that include a header
- **Impact Score**: Various formulas combining dependency and usage counts
- **Rebuild Cost**: Estimated compilation cost (files × compilations)

---

## 🏗️ Architecture

### Tool Dependencies

```
buildCheckSummary.py ──────┐
                           ├──> ninja only
buildCheckImpact.py ───────┤
                           │
buildCheckIncludeChains.py ┘

buildCheckIncludeGraph.py ──┐
                            ├──> ninja + clang-scan-deps + networkx
buildCheckDependencyHell.py ┤
                            │
buildCheckDSM.py ───────────┤
                            │
buildCheckRippleEffect.py ──┴──> + git
```

### Data Flow

1. **Ninja Layer** (buildCheckSummary, buildCheckImpact, buildCheckIncludeChains)
   - Uses ninja's cached build graph
   - Fast but limited to what ninja knows
   - Good for quick checks

2. **Source Analysis Layer** (buildCheckIncludeGraph, buildCheckDependencyHell)
   - Parses actual source files with clang-scan-deps
   - Accurate and comprehensive
   - Slower but more detailed

3. **Git Integration Layer** (buildCheckRippleEffect)
   - Combines git changes with source analysis
   - Shows commit-level impact
   - Requires git repository

---

## 🔧 Common Issues

### "clang-scan-deps not found"

Tools 4, 5, and 6 require clang-scan-deps. Install clang-18 or clang-19:
```bash
sudo apt install clang-19
```

If you have multiple versions, the tools will automatically try:
- `clang-scan-deps-19`
- `clang-scan-deps-18`
- `clang-scan-deps`

### "compile_commands.json not found"

Most tools now auto-generate `compile_commands.json` from your `build.ninja` file.

If you need to generate it manually:
```bash
cd build/
ninja -t compdb > compile_commands.json
```

Or configure CMake to generate it automatically:
```bash
cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON ..
```

### "No module named 'networkx'"

Install networkx:
```bash
pip install networkx
```

### Slow Performance

For large projects:
- Use quick tools first (buildCheckSummary, buildCheckImpact)
- Run comprehensive tools (buildCheckDependencyHell) periodically
- Results are often cached by clang-scan-deps

---

## 📖 Examples

### Example 1: Daily Development Workflow

```bash
# Morning: Check what changed overnight
./buildCheckSummary.py ../build/release/

# After making header changes
./buildCheckImpact.py ../build/release/

# Before committing
./buildCheckRippleEffect.py ../build/release/
```

### Example 2: Investigating Slow Rebuilds

```bash
# Start with optimization analyzer for comprehensive overview
./buildCheckOptimize.py ../build/release/ --quick

# Find worst offenders
./buildCheckDependencyHell.py ../build/release/ --top 20

# Check library-level dependencies
./buildCheckLibraryGraph.py ../build/release/

# See which libraries cause biggest rebuild impact
./buildCheckLibraryGraph.py ../build/release/ --impacted-by libFslBase.a

# Identify gateway headers
./buildCheckIncludeGraph.py ../build/release/ --full

# Understand coupling
./buildCheckIncludeChains.py ../build/release/
```

### Example 3: Refactoring a Header

```bash
# Before: Check current impact
./buildCheckIncludeGraph.py ../build/release/ --header include/MyClass.hpp

# Make changes...

# After: Verify improvement
./buildCheckIncludeGraph.py ../build/release/ --header include/MyClass.hpp
```

---

## 🧪 Testing

The BuildCheck suite includes comprehensive tests:

```bash
cd test/
./run_tests.sh
```

See `test/README.md` and `TEST_SUITE_SUMMARY.md` for details.

---

## 📄 License

BSD 3-Clause License

Copyright (c) 2025, Mana Battery
All rights reserved.

See individual script files for full license text.

---

## 🤝 Contributing

Contributions are welcome! Please ensure:
- Code follows existing style and conventions
- New features include tests
- Documentation is updated
- Scripts remain Python 3.7+ compatible

---

## 📚 Additional Documentation

- `README_buildCheckIncludeChains.md` - Detailed buildCheckIncludeChains.py documentation
- `README_buildCheckSummary.md` - Detailed buildCheckSummary.py documentation
- `TEST_SUITE_SUMMARY.md` - Test suite documentation
- `test/README.md` - Testing guide

---

## 🔍 FAQ

**Q: Do these tools modify my source code?**  
A: No, all tools are read-only analysis tools.

**Q: Can I run these on any C/C++ project?**  
A: Yes, as long as you use ninja as your build system and have compile_commands.json.

**Q: Which tool is the most accurate?**  
A: buildCheckDependencyHell.py and buildCheckIncludeGraph.py use clang-scan-deps for source-level analysis, making them the most accurate.

**Q: Can I use these with CMake?**  
A: Yes, CMake can generate ninja build files and compile_commands.json.

**Q: Do these work on Windows?**  
A: Yes, though they're primarily tested on Linux. Ensure Python, ninja, and optionally clang are in your PATH.

**Q: How often should I run these tools?**  
A: Quick tools (1-2) daily; comprehensive tools (4-6) weekly or when optimizing.

---

## 📞 Support

For issues, questions, or contributions, please refer to the project repository or contact the maintainers.