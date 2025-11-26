# buildCheckLibraryGraph.py - Library Dependency Analysis

**Version:** 1.0.0

## Overview

`buildCheckLibraryGraph.py` analyzes your build system's library dependencies by parsing `build.ninja` to understand which static libraries depend on each other and which executables depend on which libraries. This provides a **coarser-grained view** than header-level analysis, focusing on module-level architecture and build impact.

## Key Features

### 1. **Build Impact Analysis**
Answers: "If I change library X, what needs to rebuild?"
- Computes transitive dependencies
- Shows all impacted libraries and executables
- Calculates rebuild percentage

### 2. **Library Dependency Graph**
- Shows library→library dependencies
- Shows executable→library dependencies
- Detects circular library dependencies
- Ranks libraries by various metrics

### 3. **Metric Calculation**
For each library:
- **Fan-in**: How many targets depend on it (popularity)
- **Fan-out**: How many libraries it depends on (complexity)
- **Transitive dependents**: Total build impact
- **Depth**: Position in dependency hierarchy

### 4. **Visualization Export**
- GraphViz DOT format for creating diagrams
- Easy to visualize with `dot` tool

## Use Cases

### "Which library changes cause the biggest rebuild impact?"
```bash
./buildCheckLibraryGraph.py ../build/release/
```
Shows libraries ranked by transitive dependents - those at the top affect the most targets.

### "If I change libFslBase, what rebuilds?"
```bash
./buildCheckLibraryGraph.py ../build/release/ --impacted-by libFslBase.a
```
**Output:**
```
BUILD IMPACT ANALYSIS: libFslBase.a

Impacted Libraries (87):
  • libFslAssimp.a
  • libFslDataBinding.App.a
  • libFslDataBinding.Base.a
  [... 84 more ...]

Impacted Executables (8):
  • Console.BasicThread
  • Console.BasicThreadAsync
  [... 6 more ...]

Total Rebuild Impact: 95 targets (97.9% of build)
⚠ Warning: High impact library - changes affect >50% of build
```

### "What depends on libFslGraphics?"
```bash
./buildCheckLibraryGraph.py ../build/release/ --find-dependents libFslGraphics.a
```
Lists all libraries and executables that directly or transitively depend on the specified library.

### "Are there circular library dependencies?"
```bash
./buildCheckLibraryGraph.py ../build/release/ --cycles-only
```
Detects if any libraries have circular dependencies (which is usually a design problem).

### "Show me the library architecture"
```bash
# Generate DOT file
./buildCheckLibraryGraph.py ../build/release/ --export library_graph.dot

# Render to PNG
dot -Tpng library_graph.dot -o library_graph.png

# Or render with fdp for large graphs
fdp -Tpng library_graph.dot -o library_graph.png
```

### "Focus on libraries only, ignore executables"
```bash
./buildCheckLibraryGraph.py ../build/release/ --libs-only
```
Useful for understanding library layering without executable noise.

## Sample Output

### Main Analysis
```
================================================================================
LIBRARY DEPENDENCY GRAPH
================================================================================

Graph Properties:
  Total libraries: 89
  Total executables: 8
  Library→Library edges: 758
  Executable→Library edges: 119
  Average dependencies per library: 8.5
  Leaf libraries (no dependencies): 2
  Unused libraries: 43

================================================================================
TOP LIBRARIES BY IMPACT
================================================================================

Most Impactful Libraries (by transitive dependents):
Changes to these libraries affect the most targets

 1. libFslGraphics.a
    Fan-in: 84 | Fan-out: 1 | Transitive dependents: 84 | Depth: 1
 2. libFslService.Consumer.a
    Fan-in: 68 | Fan-out: 1 | Transitive dependents: 68 | Depth: 1
 3. libFslDemoApp.Shared.a
    Fan-in: 63 | Fan-out: 2 | Transitive dependents: 63 | Depth: 1

Most Depended-On Libraries (by direct dependents):
These libraries are directly used by many targets

 1. libFslBase.a
    Fan-in: 95 | Fan-out: 0 | Transitive dependents: 0 | Depth: 0
 2. libFslGraphics.a
    Fan-in: 84 | Fan-out: 1 | Transitive dependents: 84 | Depth: 1

Libraries with Most Dependencies:
These libraries depend on many other libraries

 1. libShared.AntiAliasing.a
    Fan-in: 0 | Fan-out: 20 | Transitive dependents: 0 | Depth: 1
 2. libShared.Bloom.a
    Fan-in: 0 | Fan-out: 20 | Transitive dependents: 0 | Depth: 1

================================================================================
RECOMMENDATIONS
================================================================================

Build optimization opportunity:
  • 5 libraries impact >50 targets
  • Consider splitting these libraries to improve build parallelism
  • Top offenders: libFslBase.a, libFslGraphics.a, libFslService.Consumer.a
```

## Understanding the Metrics

### Fan-in (Afferent Coupling)
Number of libraries/executables that directly depend on this library.
- **High fan-in** = Widely used, foundational library (e.g., libFslBase.a with 95 dependents)
- **Low fan-in** = Niche library or unused

**Interpretation:**
- High fan-in libraries should be very stable
- Changes to high fan-in libraries cause massive rebuilds
- Consider splitting very high fan-in libraries if possible

### Fan-out (Efferent Coupling)
Number of libraries this library directly depends on.
- **High fan-out** = Complex, depends on many things (e.g., libShared.AntiAliasing.a with 20 dependencies)
- **Low fan-out** = Simple, self-contained

**Interpretation:**
- High fan-out libraries are harder to test in isolation
- Consider if all dependencies are truly necessary
- May indicate violation of single responsibility

### Transitive Dependents (Build Impact)
Total number of libraries and executables that would need to rebuild if this library changes.
- **High impact** = Many targets transitively depend on this
- **Low impact** = Changes are isolated

**Critical for:**
- Prioritizing CI/CD optimization
- Understanding which libraries need extra care
- Planning library refactoring

### Depth
Longest path from this library to any leaf library in the dependency graph.
- **Depth 0** = Leaf library (no dependencies)
- **Higher depth** = More layers below it

**Interpretation:**
- Foundation libraries typically have high depth
- Helps understand architectural layering

## Comparison with Header-Level Tools

| Aspect | buildCheckLibraryGraph | buildCheckDSM / buildCheckDependencyHell |
|--------|----------------------|------------------------------------------|
| **Granularity** | Library level | Header level |
| **Speed** | Very fast (< 1s) | Moderate (3-10s) |
| **Use case** | Build impact, module architecture | Code coupling, refactoring |
| **Input** | build.ninja | compile_commands.json + headers |
| **Detects** | Library circular deps | Header circular deps |
| **Best for** | "What rebuilds?" | "How to refactor?" |

**When to use library-level:**
- Quick build impact checks
- Understanding module boundaries
- Build time optimization
- CI/CD planning

**When to use header-level:**
- Code refactoring
- Architectural cleanup
- Reducing compile times
- Finding specific coupling issues

## Command Reference

```bash
# Basic analysis
./buildCheckLibraryGraph.py <build_dir>

# Show top N libraries
./buildCheckLibraryGraph.py <build_dir> --top 30

# Build impact analysis
./buildCheckLibraryGraph.py <build_dir> --impacted-by <library.a>

# Find dependents
./buildCheckLibraryGraph.py <build_dir> --find-dependents <library.a>

# Check for cycles only
./buildCheckLibraryGraph.py <build_dir> --cycles-only

# Libraries only (no executables)
./buildCheckLibraryGraph.py <build_dir> --libs-only

# Export to DOT
./buildCheckLibraryGraph.py <build_dir> --export graph.dot

# Visualize
./buildCheckLibraryGraph.py <build_dir> --export graph.dot
dot -Tpng graph.dot -o graph.png
```

## Requirements

- **Python 3.7+** (required)
- **build.ninja file** (generated by CMake with Ninja generator)
- **networkx>=2.8.8** (optional, for cycle detection): `pip install networkx`
- **colorama>=0.4.6** (optional, for colored output): `pip install colorama`

**Note:** This tool does NOT require NumPy or clang-scan-deps. It analyzes build.ninja directly.

## How It Works

### 1. Parse build.ninja
Extracts build rules for:
- Static libraries (`.a` files): `CXX_STATIC_LIBRARY_LINKER` rules
- Executables: `CXX_EXECUTABLE_LINKER` rules

### 2. Extract Dependencies
From the `||` (order-only) section of build rules:
```ninja
build libFoo.a: CXX_STATIC_LIBRARY_LINKER ... || libBar.a libBaz.a
                                                  ^^^^^^^^^^^^^^^^^
                                                  Dependencies
```

### 3. Build Directed Graph
- Nodes = libraries and executables
- Edges = dependency relationships
- Library A → Library B means "A depends on B"

### 4. Compute Metrics
- Direct dependencies (fan-in/fan-out)
- Transitive closure (BFS for all reachable dependents)
- Strongly connected components (cycle detection via NetworkX)
- Depth calculation (longest path via BFS)

### 5. Analyze & Report
- Rank libraries by impact
- Identify optimization opportunities
- Detect architectural issues

## Tips & Best Practices

### For Large Projects (>100 libraries)
1. **Start with `--top 10`** to see biggest issues
2. **Use `--impacted-by`** for specific libraries you're working on
3. **Export to DOT** and filter in Graphviz for visualization

### Interpreting Results

**Healthy patterns:**
- Few libraries with very high fan-in (good reuse of foundation)
- Most libraries have low-moderate fan-out (simple dependencies)
- No circular library dependencies
- Clear layering (foundation libs have high fan-in, zero fan-out)

**Warning signs:**
- Many libraries with fan-out >15 (overly complex)
- Circular library dependencies (architectural problem)
- >50% of libraries marked as unused (build system bloat)
- One library impacts >80% of build (consider splitting)

### Build Optimization Strategy
1. **Identify high-impact libraries** (use main analysis)
2. **Split if possible** - Large foundation libraries can often be split into smaller modules
3. **Reduce unnecessary dependencies** - Review high fan-out libraries
4. **Break circular dependencies** - These prevent parallel builds

## Troubleshooting

### "build.ninja not found"
Ensure you're pointing to the build directory containing build.ninja:
```bash
./buildCheckLibraryGraph.py path/to/build/directory/
```

### "Library 'libXYZ.a' not found"
Check the exact library name in build.ninja:
```bash
grep "\.a:" path/to/build/build.ninja | head -20
```
Library names are case-sensitive and include the `.a` extension.

### No colors in output
Install colorama:
```bash
pip install colorama
```

### NetworkX warnings
Install networkx for cycle detection:
```bash
pip install networkx
```
The tool works without it, but can't detect circular dependencies.

## Integration with Other Tools

### With buildCheckDSM.py
```bash
# Library level (fast overview)
./buildCheckLibraryGraph.py ../build/ --impacted-by libFslGraphics.a

# Header level (detailed coupling)
./buildCheckDSM.py ../build/ --filter "*FslGraphics/*"
```

### With buildCheckDependencyHell.py
```bash
# Library level: which libraries are problematic
./buildCheckLibraryGraph.py ../build/ --top 10

# Header level: which headers in those libraries are worst
./buildCheckDependencyHell.py ../build/ --top 20
```

### With buildCheckRippleEffect.py
```bash
# Library level: overall impact
./buildCheckLibraryGraph.py ../build/ --impacted-by libFslBase.a

# Commit level: specific impact of your changes
./buildCheckRippleEffect.py ../build/ HEAD~1..HEAD
```

## See Also

- [README.md](README.md) - Main BuildCheck documentation
- [README_buildCheckDSM.md](README_buildCheckDSM.md) - Header-level dependency structure matrix
- [README_buildCheckSummary.md](README_buildCheckSummary.md) - Quick rebuild analysis
