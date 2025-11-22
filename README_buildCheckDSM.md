# buildCheckDSM.py - Dependency Structure Matrix Analysis

## Overview

`buildCheckDSM.py` visualizes C++ header dependencies as a **Dependency Structure Matrix (DSM)**, providing a comprehensive architectural view of your codebase. It identifies circular dependencies, analyzes layered architecture, and highlights high-coupling headers that may need refactoring.

**Version**: 1.0.0

## What is a Dependency Structure Matrix?

A DSM is a square matrix representation where:
- **Rows and columns** represent the same set of headers
- **Cell [i,j]** shows if header `i` depends on header `j`
- The matrix reveals architectural patterns at a glance
- Cycles, layers, and coupling issues become visually apparent

## Key Features

### 1. **Matrix Visualization**
- Compact matrix view showing header-to-header dependencies
- Color-coded cells (green/yellow/red) indicating coupling levels
- Visual markers for headers in circular dependencies
- Configurable size (show top N most coupled headers)

### 2. **Circular Dependency Detection**
- Uses strongly connected component (SCC) analysis
- Lists all circular dependency groups
- Identifies minimum feedback set (edges to break cycles)
- Highlights cycle participants in the matrix

### 3. **Layered Architecture Analysis**
- Computes dependency layers via topological sorting
- Layer 0 = top-level sources (no incoming dependencies from other headers)
- Higher layers = foundation (depended upon by lower layers)
- Detects layer violations (back-edges)

### 4. **Coupling Metrics**
- **Fan-out**: Number of headers this header includes
- **Fan-in**: Number of headers that include this header
- **Coupling**: Total dependencies (fan-in + fan-out)
- **Stability**: Fan-out / (Fan-in + Fan-out) — resistance to change
- **Sparsity**: Percentage of empty cells in matrix

### 5. **Module Analysis**
- Groups headers by directory structure
- Calculates intra-module vs inter-module dependencies
- Measures module cohesion (higher = better encapsulation)

### 6. **Differential Analysis**
- Compare DSM between two builds (baseline vs current)
- Identify architectural changes: new/removed headers, cycles, coupling shifts
- Track layer changes and cycle participants
- Quantify impact of refactoring or feature additions
- User manages builds manually (no git automation)

### 7. **Export and Filtering**
- Export full matrix to CSV for offline analysis
- Filter by glob patterns (e.g., "FslBase/*")
- Cluster display by directory structure

## Usage

### Basic Usage

```bash
# Analyze all project headers
./buildCheckDSM.py ../build/release/
```

### Show More Headers in Matrix

```bash
# Display top 50 most coupled headers
./buildCheckDSM.py ../build/release/ --top 50
```

### Focus on Specific Analysis

```bash
# Show only circular dependencies
./buildCheckDSM.py ../build/release/ --cycles-only

# Show dependency layers
./buildCheckDSM.py ../build/release/ --show-layers
```

### Differential Analysis (Compare Two Builds)

```bash
# Step 1: Build baseline version (e.g., main branch)
git checkout main
./prepare.sh
FslBuild.py -c debug
# Creates ../build/debug/ with compile_commands.json

# Step 2: Build current version (e.g., feature branch)
git checkout feature-branch
./prepare.sh
FslBuild.py -c debug
# Updates ../build/debug/ with new compile_commands.json

# Step 3: Compare architectures
./buildCheckDSM.py ../build/debug/ --compare-with ../build-baseline/debug/

# Alternative: Use separate build directories
# Build baseline in ../build-main/
# Build current in ../build-feature/
./buildCheckDSM.py ../build-feature/debug/ --compare-with ../build-main/debug/
```

### Filter by Module/Directory

```bash
# Analyze only FslBase headers
./buildCheckDSM.py ../build/release/ --filter "FslBase/*"

# Analyze specific subdirectory
./buildCheckDSM.py ../build/release/ --filter "DemoFramework/FslGraphics/*"
```

### Export and Clustering

```bash
# Export full matrix to CSV
./buildCheckDSM.py ../build/release/ --export dsm_matrix.csv

# Show module-level analysis
./buildCheckDSM.py ../build/release/ --cluster-by-directory
```

### Debug Mode

```bash
# Enable verbose logging
./buildCheckDSM.py ../build/release/ --verbose
```

## Output Sections

### 1. Summary Statistics
```
Matrix Properties:
  Total headers: 250
  Total dependencies: 1,523
  Matrix size: 250 × 250
  Sparsity: 97.6% (lower is more coupled)
  Average dependencies per header: 6.1

Structural Properties:
  Circular dependency groups: 3
  Headers in cycles: 12
  Dependency layers: 8
  Maximum dependency depth: 7
```

### 2. Dependency Structure Matrix
```
        0  1  2  3  4  5
●FslBase/ITag.hpp                0  ─  X  ·  ·  ·  · 
 FslBase/BasicTypes.hpp          1  ·  ─  X  ·  ·  · 
●FslBase/Math/Vector3.hpp        2  X  X  ─  X  ·  · 
 FslGraphics/Render/Basic.hpp    3  X  ·  X  ─  X  · 
 FslGraphics3D/Camera.hpp        4  X  X  X  X  ─  X 
●FslSimpleUI/Base/Control.hpp    5  X  X  ·  X  X  ─ 

Legend:
  X = dependency exists
  · = no dependency
  ● = header is in a circular dependency
```

### 3. Circular Dependencies
```
Found 3 circular dependency groups:

Cycle 1 (4 headers):
  • FslBase/ITag.hpp
  • FslBase/Collections/HandleVector.hpp
  • FslGraphics/Render/Basic.hpp
  • FslSimpleUI/Base/Control.hpp

Suggested edges to remove to break cycles:
  FslBase/ITag.hpp → FslBase/Collections/HandleVector.hpp
  FslSimpleUI/Base/Control.hpp → FslGraphics/Render/Basic.hpp
```

### 4. Layered Architecture
```
Layer 0 (42 headers) - Top-level sources:
  • FslBase/Math/Vector3.hpp
  • FslGraphics/Color.hpp
  ...

Layer 1 (25 headers) - Foundation:
  • FslBase/BasicTypes.hpp
  • FslBase/Math/MathHelper.hpp
  • FslBase/Span.hpp
  ...
```

### 5. High-Coupling Headers
```
Top 20 headers by coupling:

FslGraphics/Render/Basic.hpp [IN CYCLE]
  Fan-out: 15 | Fan-in: 23 | Coupling: 38 | Stability: 0.395

FslBase/Math/Vector3.hpp
  Fan-out: 8 | Fan-in: 45 | Coupling: 53 | Stability: 0.151
```

### 6. Module Analysis (with `--cluster-by-directory`)
```
FslBase:
  Headers: 85
  Internal dependencies: 142
  External dependencies: 28
  Cohesion: 83.5% (higher is better)

FslGraphics:
  Headers: 63
  Internal dependencies: 98
  External dependencies: 67
  Cohesion: 59.4% (higher is better)
```

### 7. Differential Analysis Output (with `--compare-with`)
```
=== DSM Differential Analysis ===

Baseline: ../build-baseline/debug/ (250 headers)
Current:  ../build-feature/debug/ (253 headers)

Architecture Changes:
  Headers added: 3
  Headers removed: 0
  Cycles added: 1
  Cycles removed: 0
  Headers with increased coupling: 8
  Headers with decreased coupling: 2
  Layer changes: 5

New Headers:
  • FslGraphics/Render/NewFeature.hpp (Layer 3, Coupling: 12)
  • FslUtil/Helper/Config.hpp (Layer 2, Coupling: 5)
  • FslBase/NewDataType.hpp (Layer 1, Coupling: 8)

Removed Headers:
  (none)

New Cycles:
  Cycle (4 headers):
    • FslGraphics/Render/NewFeature.hpp
    • FslGraphics/Render/Basic.hpp
    • FslSimpleUI/Base/Control.hpp
    • FslBase/ITag.hpp
  
  Headers newly participating in cycles:
    • FslGraphics/Render/NewFeature.hpp

Resolved Cycles:
  (none)

Coupling Changes (threshold: ±5):
  Increased:
    FslGraphics/Render/Basic.hpp: 38 → 45 (+7)
    FslSimpleUI/Base/Control.hpp: 25 → 32 (+7)
    FslBase/ITag.hpp: 15 → 21 (+6)
  
  Decreased:
    FslUtil/String/StringUtil.hpp: 28 → 22 (-6)

Layer Changes:
  FslGraphics/Render/Basic.hpp: Layer 4 → Layer 5
  FslSimpleUI/Base/Control.hpp: Layer 5 → Layer 6
  FslGraphics3D/Camera.hpp: Layer 6 → Layer 7
```

## Metrics Explained

### Fan-out
Number of headers this header **includes** (outgoing dependencies). High fan-out indicates this header depends on many others.

### Fan-in
Number of headers that **include** this header (incoming dependencies). High fan-in indicates this header is widely used.

### Coupling
Total dependencies: `Fan-in + Fan-out`. Higher coupling = more connections = harder to change.

### Stability
`Fan-out / (Fan-in + Fan-out)`
- **0.0** = Very stable (many dependents, few dependencies) — hard to change, affects many
- **1.0** = Very unstable (few dependents, many dependencies) — easy to change, affects few
- **0.5** = Balanced

### Sparsity
Percentage of empty cells in the matrix: `100% × (1 - actual_deps / possible_deps)`
- **High sparsity (>95%)**: Low coupling, modular design
- **Low sparsity (<90%)**: High coupling, tight integration

### Cohesion (Module-level)
`100% × intra_module_deps / (intra_module_deps + inter_module_deps)`
- **High cohesion (>80%)**: Good module boundaries
- **Low cohesion (<60%)**: Module boundaries may need improvement

## Use Cases

### 1. Architectural Review
**Question**: "What's the overall structure of my codebase?"

```bash
./buildCheckDSM.py ../build/release/ --show-layers --cluster-by-directory
```

Review the matrix, layers, and module cohesion to understand architectural patterns.

### 2. Identify Circular Dependencies
**Question**: "Where are the circular dependencies in my code?"

```bash
./buildCheckDSM.py ../build/release/ --cycles-only
```

Focus on breaking the suggested feedback edges to eliminate cycles.

### 3. Refactoring Planning
**Question**: "Which headers should I refactor first?"

```bash
./buildCheckDSM.py ../build/release/ --top 50
```

Target headers with:
- High coupling (fan-in + fan-out > 20)
- Participation in cycles
- Low stability (close to 1.0)

### 4. Validate Layered Architecture
**Question**: "Is my codebase properly layered?"

```bash
./buildCheckDSM.py ../build/release/ --show-layers
```

Check if:
- No circular dependencies exist
- Layers are clearly defined
- No layer violations (back-edges)

### 5. Module Boundary Analysis
**Question**: "Are my module boundaries clean?"

```bash
./buildCheckDSM.py ../build/release/ --cluster-by-directory
```

Look for:
- High cohesion within modules (>80%)
- Low coupling between modules
- Clear separation of concerns

### 6. Track Improvements Over Time
**Question**: "Did my refactoring improve the architecture?"

**Option A: Differential Analysis (Recommended)**
```bash
# Build baseline (before refactoring)
git checkout main
./prepare.sh && FslBuild.py -c debug
mkdir -p ../build-baseline && cp -r ../build ../build-baseline/

# Build current (after refactoring)
git checkout refactor-branch
./prepare.sh && FslBuild.py -c debug

# Compare architectures
./buildCheckDSM.py ../build/debug/ --compare-with ../build-baseline/debug/
```

**Option B: Manual CSV Comparison**
```bash
# Before refactoring
./buildCheckDSM.py ../build/release/ --export baseline.csv

# After refactoring
./buildCheckDSM.py ../build/release/ --export improved.csv

# Compare the two CSV files (manually or with diff tools)
```

### 7. Impact Analysis for Features
**Question**: "What architectural impact will this feature have?"

```bash
# Build main branch
git checkout main
./prepare.sh && FslBuild.py -c debug
cp -r ../build/debug ../build-main

# Build feature branch
git checkout feature-xyz
./prepare.sh && FslBuild.py -c debug

# Analyze impact
./buildCheckDSM.py ../build/debug/ --compare-with ../build-main/
```

Look for:
- New cycles introduced
- Headers with increased coupling
- New layer violations
- Changed module boundaries

## Complementary Tools

`buildCheckDSM.py` provides a unique architectural perspective. Combine it with other buildCheck tools:

| Tool | Focus | When to Use |
|------|-------|-------------|
| **buildCheckDSM.py** | Architectural structure (DSM view) | Architectural reviews, refactoring planning |
| **buildCheckDSM.py --compare-with** | Architectural changes between builds | Impact analysis, before/after comparisons |
| **buildCheckSummary.py** | What changed, what will rebuild | After making changes, before builds |
| **buildCheckImpact.py** | Quick rebuild impact estimates | Fast impact checks |
| **buildCheckIncludeGraph.py** | Gateway headers, include costs | Identify headers causing slow rebuilds |
| **buildCheckDependencyHell.py** | Multi-metric deep analysis | Comprehensive dependency audit |
| **buildCheckIncludeChains.py** | Cooccurrence patterns | Find common inclusion patterns |
| **buildCheckRippleEffect.py** | Git-based historical impact | Understand long-term change patterns |

## Requirements

- **Python 3.7+**
- **networkx**: `pip install networkx`
- **colorama**: `pip install colorama` (optional, for colored output)
- **clang-scan-deps**: Install clang-19, clang-18, or later
  ```bash
  # Ubuntu/Debian
  sudo apt install clang-19
  
  # Fedora
  sudo dnf install clang-tools-extra
  ```
- **compile_commands.json**: Auto-generated from Ninja build

## Performance

- **Typical runtime**: 3-10 seconds for medium projects
- **Scales with**: Number of headers and dependencies
- **Optimization**: Results can be cached (uses same graph as buildCheckIncludeGraph.py)
- **Memory**: NetworkX graphs are memory-efficient

## Interpretation Tips

### Good Architecture Signs
✅ High sparsity (>95%)  
✅ No circular dependencies  
✅ Clear layers (5-10 layers typical)  
✅ High module cohesion (>80%)  
✅ Stable foundation headers (stability ~0.0)  
✅ Unstable top-layer headers (stability ~1.0)  

### Warning Signs
⚠️ Low sparsity (<90%) — tightly coupled  
⚠️ Circular dependencies — refactor needed  
⚠️ Many high-coupling headers (coupling >20) — split or reduce deps  
⚠️ Headers with extreme fan-in (>50) — "god headers"  
⚠️ Low module cohesion (<60%) — unclear boundaries  
⚠️ Flat architecture (1-2 layers) — no clear hierarchy  

## CSV Export Format

When using `--export`, the CSV file contains:

```csv
Header,Fan-out,Fan-in,Coupling,Stability,Header1,Header2,Header3,...
FslBase/BasicTypes.hpp,0,45,45,0.000,0,0,0,...
FslBase/Math/Vector3.hpp,8,42,50,0.160,1,0,1,...
```

- **First columns**: Header path and metrics
- **Remaining columns**: Dependency matrix (1 = dependency, 0 = none)
- Can be imported into Excel, R, Python for custom analysis

## Troubleshooting

### "No headers found after filtering"
Your filter pattern didn't match any headers. Try:
```bash
# List available patterns
./buildCheckDSM.py ../build/release/ --verbose | grep "headers in project"
```

### "Cannot compute layers: graph contains cycles"
Your codebase has circular dependencies. Use `--cycles-only` to identify and break them:
```bash
./buildCheckDSM.py ../build/release/ --cycles-only
```

### "Matrix too large to display"
Use `--top` to show fewer headers or `--filter` to narrow scope:
```bash
./buildCheckDSM.py ../build/release/ --top 20 --filter "FslBase/*"
```

### Script runs slowly
This is normal for large projects (500+ headers). Use `--export` to save results and analyze offline.

## Examples Workflow

### Full Architectural Audit
```bash
# 1. Get overview
./buildCheckDSM.py ../build/release/

# 2. Check for cycles
./buildCheckDSM.py ../build/release/ --cycles-only

# 3. Analyze layers
./buildCheckDSM.py ../build/release/ --show-layers

# 4. Review module boundaries
./buildCheckDSM.py ../build/release/ --cluster-by-directory

# 5. Export for detailed analysis
./buildCheckDSM.py ../build/release/ --export full_dsm.csv
```

### Focus on Specific Module
```bash
# Analyze just FslGraphics module
./buildCheckDSM.py ../build/release/ --filter "FslGraphics/*" --show-layers

# Check for cycles in FslBase
./buildCheckDSM.py ../build/release/ --filter "FslBase/*" --cycles-only
```

### Differential Analysis Workflow
```bash
# 1. Create baseline build
git checkout main
./prepare.sh && FslBuild.py -c release
mkdir -p ../build-baseline
cp -r ../build/release ../build-baseline/

# 2. Build feature branch
git checkout feature-new-renderer
./prepare.sh && FslBuild.py -c release

# 3. Compare architectures
./buildCheckDSM.py ../build/release/ --compare-with ../build-baseline/release/

# 4. Analyze specific module impact
./buildCheckDSM.py ../build/release/ --compare-with ../build-baseline/release/ --filter "FslGraphics/*"

# 5. Check if refactoring reduced cycles
./buildCheckDSM.py ../build/release/ --compare-with ../build-baseline/release/ --cycles-only
```

### Pre-Merge Impact Check
```bash
# Check architectural impact before merging PR
git checkout main
./prepare.sh && FslBuild.py -c debug
cp -r ../build/debug ../build-main

git checkout pr-branch
./prepare.sh && FslBuild.py -c debug
./buildCheckDSM.py ../build/debug/ --compare-with ../build-main/

# Look for:
# - New cycles introduced
# - Significant coupling increases
# - New layer violations
```

## Tips for Refactoring

Based on DSM analysis, prioritize refactoring:

1. **Break cycles first** — Use feedback edge suggestions
2. **Split high-coupling headers** — Coupling >20 needs attention
3. **Reduce fan-out** — Use forward declarations, move implementations to .cpp
4. **Improve module cohesion** — Reorganize headers with <60% cohesion
5. **Establish clear layers** — Move foundation code to higher layers (depended upon by others)

## Version History

- **1.0.0** (2025-11-21): Initial release
  - Dependency Structure Matrix visualization
  - Circular dependency detection with SCC analysis
  - Layered architecture computation
  - Per-header coupling metrics
  - CSV export functionality
  - Directory clustering and module analysis

## License

BSD 3-Clause License (same as other buildCheck tools)

Copyright (c) 2025, Mana Battery

---

**Part of the BuildCheck suite** — Tools for analyzing and optimizing C++ build dependencies
