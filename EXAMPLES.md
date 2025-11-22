# BuildCheck Usage Examples

This guide provides practical examples for using BuildCheck tools in real-world scenarios.

## Quick Start

### 1. Basic Rebuild Analysis
**Scenario**: You want to see what changed and will rebuild.

```bash
# Run in your build directory
./buildCheckSummary.py ../build/release/

# With detailed file list
./buildCheckSummary.py ../build/release/ --detailed

# Save as JSON for CI/CD
./buildCheckSummary.py ../build/release/ --format json --output rebuild-report.json
```

**Expected Output**:
```
=== Rebuild Summary ===
Rebuilt files: 47

Reasons:
   35  → input source changed
   12  → output missing

Root Causes (from explain output):
  include/core/Types.hpp → triggered 18 rebuilds
  include/utils/Logger.hpp → triggered 12 rebuilds
```

---

### 2. Impact Analysis
**Scenario**: You modified a header and want to know the rebuild impact.

```bash
# Check which headers are causing rebuilds
./buildCheckImpact.py ../build/release/

# See all high-impact headers (not just changed)
./buildCheckImpact.py ../build/release/ --all-headers
```

**Expected Output**:
```
=== Changed Headers Impact ===
  include/core/Types.hpp → affects 156 targets
  include/utils/Config.hpp → affects 89 targets

=== Summary ===
Total changed headers: 2
Total affected targets: 245
```

---

### 3. Git Commit Ripple Effect
**Scenario**: Before committing, estimate CI/CD build time impact.

```bash
# Analyze last commit
./buildCheckRippleEffect.py ../build/release/

# Analyze specific commit
./buildCheckRippleEffect.py ../build/release/ --commit abc123f

# Analyze commit range
./buildCheckRippleEffect.py ../build/release/ --commit HEAD~5..HEAD

# Specify different repo location
./buildCheckRippleEffect.py ../build/release/ --repo ~/projects/myapp
```

**Expected Output**:
```
=== Git Ripple Effect Analysis ===

Changed Files (last commit):
  Headers (2):
    • include/core/Types.hpp
    • include/utils/Logger.hpp
  
  Source Files (1):
    • src/main.cpp

Rebuild Impact:
  Types.hpp affects 156 source files
  Logger.hpp affects 89 source files
  main.cpp affects 1 source file (itself)

Summary:
  Total changed files: 3
  Total affected sources: 246
  Rebuild percentage: 12.3% (246/2000)

Impact: MODERATE (10-30% rebuild)
```

---

### 4. Find Dependency Hell Headers
**Scenario**: Identify headers with excessive transitive dependencies.

```bash
# Full analysis (all headers)
./buildCheckDependencyHell.py ../build/release/

# Only analyze changed headers (faster)
./buildCheckDependencyHell.py ../build/release/ --changed

# Detailed per-header breakdown
./buildCheckDependencyHell.py ../build/release/ --detailed

# Stricter threshold (30 instead of 50)
./buildCheckDependencyHell.py ../build/release/ --threshold 30 --top 20

# Quick check with minimal output
./buildCheckDependencyHell.py ../build/release/ --top 5
```

**Expected Output**:
```
=== Dependency Hell Analysis ===

Found 15 headers with excessive dependencies (threshold: 50)

Worst Offenders (by transitive deps):
  1. include/core/Engine.hpp
     Transitive deps: 247
     Direct deps: 12
     Used by: 89 sources
     Severity: CRITICAL

Build Impact (deps × usage = total cost):
  1. include/core/Types.hpp
     Build impact: 18,564 (119 deps × 156 uses)
     Severity: CRITICAL

Rebuild Cost (if changed):
  1. include/utils/Logger.hpp
     Rebuild cost: 7,832
     Used by: 89 sources
     Dependents: 87 headers
```

---

### 5. Include Graph & Gateway Headers
**Scenario**: Find headers that pull in many dependencies.

```bash
# Analyze changed headers
./buildCheckIncludeGraph.py ../build/release/

# Full analysis of all gateway headers
./buildCheckIncludeGraph.py ../build/release/ --full

# Show top 30 most expensive headers
./buildCheckIncludeGraph.py ../build/release/ --full --top 30
```

**Expected Output**:
```
=== Include Graph Analysis ===

Changed Headers:
  include/core/Engine.hpp
    Include cost: 127 (avg headers pulled in)
    Unique dependencies: 156
    Used by 45 .cpp files:
      • src/core/Application.cpp
      • src/game/GameState.cpp
      ...

Top Gateway Headers:
  1. include/pch/Precompiled.hpp
     Include cost: 289
     Unique deps: 312
     Used by: 523 sources
```

---

### 6. Header Cooccurrence Patterns
**Scenario**: Understand which headers frequently appear together.

```bash
# Analyze changed headers
./buildCheckIncludeChains.py ../build/release/

# Specify threshold for cooccurrence
./buildCheckIncludeChains.py ../build/release/ --threshold 10
```

**Expected Output**:
```
=== Include Cooccurrence Analysis ===

Changed header: include/core/Types.hpp (156 occurrences)
  Frequently appears with:
    • include/core/Config.hpp (156 cooccurrences, 100%)
    • include/utils/Memory.hpp (142 cooccurrences, 91%)
    • include/utils/String.hpp (128 cooccurrences, 82%)

Interpretation:
  Types.hpp is almost always included with Config.hpp
  Consider: Are these coupled by design or accident?
```

---

### 7. Dependency Structure Matrix (DSM)
**Scenario**: Visualize architecture and find circular dependencies.

```bash
# Full DSM analysis
./buildCheckDSM.py ../build/release/

# Export full matrix to CSV
./buildCheckDSM.py ../build/release/ --export dsm-matrix.csv

# Show more headers in visual matrix
./buildCheckDSM.py ../build/release/ --top 50

# Summary only (no matrix display)
./buildCheckDSM.py ../build/release/ --top 0

# Compare two builds (differential analysis)
./buildCheckDSM.py ../build/feature/ --compare-with ../build/main/
```

**Expected Output**:
```
=== Dependency Structure Matrix ===

Matrix Statistics:
  Size: 487 × 487 headers
  Sparsity: 94.2% (28,124 of 237,169 cells empty)
  Total dependencies: 8,945
  Cycles: 3 circular dependency groups
  Layers: 12 architectural levels

Circular Dependencies:
  Cycle 1 (3 headers):
    • include/core/Engine.hpp
    • include/render/Renderer.hpp
    • include/scene/Scene.hpp
    Suggested edge to break: Scene.hpp → Engine.hpp

Layered Architecture:
  Layer 0 (Top-level sources): 8 headers
    • include/app/Application.hpp
  ...
  Layer 11 (Foundation): 45 headers
    • include/utils/Types.hpp
    • include/utils/Config.hpp

High-Coupling Headers:
  1. include/core/Engine.hpp (coupling: 89)
     Fan-in: 67, Fan-out: 22
     Stability: 0.25 (stable)
```

**Differential Analysis Output** (with `--compare-with`):
```
=== DSM Differential Analysis ===

Baseline: ../build/main/ (487 headers)
Current:  ../build/feature/ (492 headers)

Architecture Changes:
  Headers added: 5
  Cycles added: 1
  Headers with increased coupling: 12
  Layer changes: 7

New Cycles:
  Cycle (4 headers):
    • include/feature/NewFeature.hpp
    • include/core/Engine.hpp
    • include/render/Renderer.hpp
    • include/scene/Scene.hpp

Coupling Changes (threshold: ±5):
  Increased:
    include/core/Engine.hpp: 89 → 97 (+8)
    include/render/Renderer.hpp: 56 → 63 (+7)
```

---

### 8. Library Dependency Graph
**Scenario**: Analyze library-level dependencies (not headers).

```bash
# Basic library analysis
./buildCheckLibraryGraph.py ../build/release/

# Export to GraphML for visualization
./buildCheckLibraryGraph.py ../build/release/ --export libs.graphml

# Detailed analysis
./buildCheckLibraryGraph.py ../build/release/ --detailed

# Filter to specific library
./buildCheckLibraryGraph.py ../build/release/ --filter MyLibrary
```

**Expected Output**:
```
=== Library Dependency Graph ===

Found 42 libraries

Top-Level Applications (3):
  • MyApp (depth: 0)
  • TestRunner (depth: 0)

Most Depended Upon:
  1. Core (23 reverse dependencies)
  2. Utils (19 reverse dependencies)

Circular Library Dependencies:
  Found 1 cycle:
    Graphics → Renderer → Scene → Graphics
```

---

### 9. Build Optimization Recommendations
**Scenario**: Get actionable advice for improving build times.

```bash
# Full optimization analysis
./buildCheckOptimize.py ../build/release/

# Quick analysis (skip expensive operations)
./buildCheckOptimize.py ../build/release/ --quick

# Focus on specific area
./buildCheckOptimize.py ../build/release/ --focus headers
./buildCheckOptimize.py ../build/release/ --focus libraries
./buildCheckOptimize.py ../build/release/ --focus cycles

# Generate detailed report
./buildCheckOptimize.py ../build/release/ --report optimization-plan.txt

# Show top 10 opportunities only
./buildCheckOptimize.py ../build/release/ --top 10
```

**Expected Output**:
```
=== Build Optimization Analysis ===

Found 24 optimization opportunities
Sorted by priority score (impact / effort × risk)

================================================================================
OPTIMIZATION #1: Split Monolithic Header 'Engine.hpp'
================================================================================

Category: header
Priority Score: 33.3 (higher = better)
Impact: 100/100 (estimated time saved)
Effort: EASY
Risk: LOW

Problem:
  Engine.hpp pulls in 247 transitive dependencies and is included by
  89 source files, causing massive rebuild cascades.

Current State:
  Every change to Engine.hpp triggers 89 source rebuilds and affects
  87 other headers.

Target State:
  Split into Engine_fwd.hpp (forward declarations) and Engine.hpp
  (implementation). Most consumers only need forward declarations.

Action Items:
  1. Create Engine_fwd.hpp with forward declarations
  2. Move implementation details to Engine.hpp
  3. Update consumers to include Engine_fwd.hpp where possible
  4. Add include guards and documentation

Affected Targets (89):
  • src/core/Application.cpp
  • src/game/GameState.cpp
  ...

Evidence:
  • Transitive dependencies: 247
  • Direct includers: 89
  • Current rebuild cost: 21,983
  • Estimated time saved: 60-80% of rebuild time
```

---

## Common Workflows

### CI/CD Integration
```bash
#!/bin/bash
# pre-commit hook or CI script

# 1. Check rebuild impact
./buildCheckRippleEffect.py ./build --format json --output impact.json

# 2. Fail if rebuild is too large
REBUILD_PCT=$(jq '.summary.rebuild_percentage' impact.json)
if (( $(echo "$REBUILD_PCT > 50" | bc -l) )); then
    echo "ERROR: Commit affects ${REBUILD_PCT}% of codebase"
    exit 1
fi

# 3. Generate report
./buildCheckSummary.py ./build --output rebuild-summary.json
```

### Refactoring Workflow
```bash
# 1. Find problem headers
./buildCheckDependencyHell.py ./build --top 10 > problem-headers.txt

# 2. Analyze specific header's impact
./buildCheckIncludeGraph.py ./build | grep "MyHeader.hpp"

# 3. Check what it pulls in
./buildCheckIncludeChains.py ./build | grep "MyHeader.hpp"

# 4. Get optimization suggestions
./buildCheckOptimize.py ./build --focus headers
```

### Architecture Review
```bash
# 1. Generate DSM
./buildCheckDSM.py ./build --export architecture-dsm.csv

# 2. Check library structure
./buildCheckLibraryGraph.py ./build --export libs.graphml

# 3. Find circular dependencies
./buildCheckDSM.py ./build | grep -A 20 "Circular Dependencies"
```

### Before/After Comparison
```bash
# 1. Build baseline (before changes)
git checkout main
./prepare.sh && build_project
mkdir -p ../build-baseline
cp -r ./build ../build-baseline/

# 2. Build feature (after changes)
git checkout feature-branch
./prepare.sh && build_project

# 3. Compare architectures
./buildCheckDSM.py ./build --compare-with ../build-baseline/build

# 4. Verify improvements
# - Check for new cycles
# - Review coupling changes
# - Validate layer shifts
```

---

## Tips & Best Practices

### Performance Tips
1. **Use `--changed` flag** when possible to analyze only modified headers
2. **Cache results** - most tools generate compile_commands.json which can be reused
3. **Run in parallel** - different tools analyze different aspects independently
4. **Use `--quick`** mode for buildCheckOptimize.py in CI environments

### Interpreting Results
1. **Start with buildCheckSummary** - quick overview
2. **Use buildCheckImpact** for immediate concerns
3. **Run buildCheckDependencyHell** for strategic planning
4. **Use buildCheckOptimize** for actionable recommendations

### Prioritizing Fixes
1. **Critical severity** headers should be addressed immediately
2. **High rebuild cost** headers cause pain when changed frequently
3. **High build impact** headers slow down every compilation
4. **Hub headers** are architectural bottlenecks

### Integration Examples

#### CMake Integration
```cmake
# Add custom targets for analysis
add_custom_target(check-rebuild
    COMMAND ${PROJECT_SOURCE_DIR}/tools/buildCheckSummary.py ${CMAKE_BINARY_DIR}
    WORKING_DIRECTORY ${PROJECT_SOURCE_DIR}
)

add_custom_target(check-impact
    COMMAND ${PROJECT_SOURCE_DIR}/tools/buildCheckImpact.py ${CMAKE_BINARY_DIR}
    WORKING_DIRECTORY ${PROJECT_SOURCE_DIR}
)
```

#### GitHub Actions
```yaml
- name: Analyze Build Impact
  run: |
    ./buildCheckRippleEffect.py ./build --format json --output impact.json
    
- name: Upload Impact Report
  uses: actions/upload-artifact@v3
  with:
    name: build-impact
    path: impact.json
```

---

## Troubleshooting

### "ninja not found"
**Solution**: Install ninja build system
```bash
# Ubuntu/Debian
sudo apt-get install ninja-build

# macOS
brew install ninja

# Or use CMake's bundled ninja
cmake -G Ninja ...
```

### "clang-scan-deps not found"
**Solution**: Install clang with scan-deps support
```bash
# Ubuntu/Debian
sudo apt-get install clang-19

# macOS
brew install llvm
export PATH="/usr/local/opt/llvm/bin:$PATH"
```

### "networkx required"
**Solution**: Install Python dependencies
```bash
pip install networkx colorama
```

### "compile_commands.json not found"
**Solution**: Tools auto-generate this, but ensure ninja is working
```bash
cd build
ninja -t compdb > compile_commands.json
```

### Slow Performance
**Solutions**:
1. Use `--changed` flag to analyze only modified headers
2. Use `--quick` mode for buildCheckOptimize
3. Reduce `--top N` limit for fewer results
4. Run on a machine with more CPU cores (tools parallelize well)

---

## Advanced Usage

### Scripting with JSON Output
```python
#!/usr/bin/env python3
import json
import subprocess

# Run analysis
result = subprocess.run(
    ['./buildCheckSummary.py', './build', '--format', 'json'],
    capture_output=True, text=True
)

data = json.loads(result.stdout)
total_files = data['summary']['total_files']

if total_files > 100:
    print(f"WARNING: Large rebuild ({total_files} files)")
```

### Automated Reporting
```bash
#!/bin/bash
# Generate comprehensive build report

REPORT_DIR="build-reports/$(date +%Y%m%d)"
mkdir -p "$REPORT_DIR"

./buildCheckSummary.py ./build --format json > "$REPORT_DIR/summary.json"
./buildCheckImpact.py ./build --all-headers > "$REPORT_DIR/impact.txt"
./buildCheckDependencyHell.py ./build > "$REPORT_DIR/dependency-hell.txt"
./buildCheckDSM.py ./build --export "$REPORT_DIR/dsm-matrix.csv"

echo "Reports generated in $REPORT_DIR"
```

---

For more information, see individual tool documentation:
- README_buildCheckSummary.md
- README_buildCheckDSM.md
- README_buildCheckIncludeChains.md
- README_buildCheckLibraryGraph.md
