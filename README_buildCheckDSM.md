# buildCheckDSM.py - Dependency Structure Matrix Analysis

## Overview

`buildCheckDSM.py` visualizes C++ header dependencies as a **Dependency Structure Matrix (DSM)**, providing a comprehensive architectural view of your codebase. It identifies circular dependencies, analyzes layered architecture, and highlights high-coupling headers that may need refactoring. It also provides proactive improvement analysis to suggest high-impact refactorings.

**Version**: 1.2.0

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
- **Architectural insights**: Coupling statistics, stability changes, ripple impact
- **Precise impact prediction**: Estimate source files affected by changes (default, use `--heuristic-only` for fast mode)
- **Statistical analysis**: Mean/median/percentile coupling trends, outlier detection
- Save/load baselines for flexible comparison workflows

### 7. **Advanced Metrics**
- **PageRank centrality**: Measures architectural importance and influence
- **Betweenness centrality**: Identifies architectural bottlenecks
- **Hub analysis**: Finds headers with high combined degree (fan-in + fan-out)
- **Quality scores**: Architecture quality (0-100), ADP score, interface ratio

### 8. **Export and Filtering**
- Export full matrix to CSV for offline analysis
- Filter by glob patterns (e.g., "FslBase/*")
- Cluster display by directory structure

### 9. **Proactive Improvement Analysis** (NEW in v1.2.0)
- Identifies high-impact refactoring opportunities WITHOUT requiring a baseline
- Detects 5 anti-patterns: god objects, cycles, coupling outliers, unstable interfaces, hub nodes
- Calculates ROI scores and break-even analysis for each candidate
- Uses precise transitive closure for accurate rebuild impact estimation
- Severity-based prioritization: 🟢 Quick Wins, 🔴 Critical, 🟡 Moderate
- Actionable refactoring steps with effort estimates
- Team impact estimation (hours saved per year, payback time)

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

#### Method 1: Compare Two Build Directories

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

#### Method 2: Save Baseline and Compare Later (Recommended)

```bash
# Step 1: Analyze and save baseline
git checkout main
./prepare.sh
FslBuild.py -c debug
./buildCheckDSM.py ../build/debug/ --save-results baseline.dsm.json.gz

# Step 2: Switch to feature branch and compare (precise impact by default)
git checkout feature-branch
./prepare.sh
FslBuild.py -c debug
./buildCheckDSM.py ../build/debug/ --load-baseline baseline.dsm.json.gz

# Step 3: Use fast heuristic mode for quick iteration (instant)
./buildCheckDSM.py ../build/debug/ --load-baseline baseline.dsm.json.gz --heuristic-only

# Step 4: Verbose output for detailed analysis
./buildCheckDSM.py ../build/debug/ --load-baseline baseline.dsm.json.gz --verbose

# Step 5: Filter to specific module with fast heuristic mode
./buildCheckDSM.py ../build/debug/ --load-baseline baseline.dsm.json.gz --filter "Graphics/*" --heuristic-only
```

**Notes**:
- `--save-results` saves unfiltered dependency data for later comparison
- `--load-baseline` applies current filters to both baseline and current for fair comparison
- **Default**: Precise transitive closure analysis (10-30s for >5000 headers, 95% confidence)
- `--heuristic-only`: Fast heuristic estimation (instant, ±5% confidence) for quick iterations

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

### Proactive Improvement Analysis (NEW)

```bash
# Analyze current codebase for improvement opportunities (no baseline required)
./buildCheckDSM.py ../build/release/ --suggest-improvements

# Focus on specific module
./buildCheckDSM.py ../build/release/ --suggest-improvements --filter "FslBase/*"

# Show detailed breakdown with verbose mode
./buildCheckDSM.py ../build/release/ --suggest-improvements --verbose

# Show more candidates
./buildCheckDSM.py ../build/release/ --suggest-improvements --top 20

# Exclude third-party code from suggestions
./buildCheckDSM.py ../build/release/ --suggest-improvements --exclude "*/ThirdParty/*"
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

### 8. Proactive Improvement Analysis Output (with `--suggest-improvements`)

NEW in v1.2.0: Identifies refactoring opportunities without requiring a baseline.

```
================================================================================
PROACTIVE ARCHITECTURAL IMPROVEMENT ANALYSIS
================================================================================

Summary:
  Total Improvement Candidates: 23
  🟢 Quick Wins (ROI ≥60, break-even ≤5 commits): 5
  🔴 Critical (cycles or ROI ≥40): 12
  🟡 Moderate (ROI <40): 6
  Estimated Total Rebuild Reduction: 34.2%
  Average Break-Even Point: 7 commits
  Architectural Debt Score: 42/100 (Moderate)

Top 10 Improvement Opportunities:

🟢 #1. FslBase/include/FslBase/Math/MathHelper.hpp
   Anti-Pattern: god_object, coupling_outlier
   Current Metrics: fan-in=89, fan-out=67, coupling=156, stability=0.43
   ROI Score: 78.5/100
   Estimated Impact: 47 coupling reduction, 8.2% rebuild reduction
   Effort: High
   Break-Even: 3 commits

   Issues Detected:
     • Includes 67 headers (god object pattern)
     • Coupling 156 is 3.2σ above mean (48.5)

   Actionable Steps:
     → Split into focused modules (target: <20 includes each)
     → Extract common utilities to separate headers
     → Reduce coupling by 47 to reach mean

   Affects 89 downstream headers

🔴 #2. FslGraphics/Render/Adapter.hpp
   Anti-Pattern: cycle_participant, unstable_interface
   Current Metrics: fan-in=45, fan-out=23, coupling=68, stability=0.66
   ROI Score: 65.2/100
   Estimated Impact: 18 coupling reduction, 5.1% rebuild reduction
   Effort: Medium
   Break-Even: 4 commits

   Issues Detected:
     • Part of circular dependency group #2 (8 headers)
     • High instability (0.66) with 45 dependents
     • Changes ripple to 45 headers

   Actionable Steps:
     → Break circular dependency by introducing interface layer
     → Use forward declarations to reduce includes
     → Extract stable interface (reduce fan-out to <5)
     → Move implementation details to separate .cpp or impl header

🟡 #3. FslUtil/String/StringParser.hpp
   Anti-Pattern: hub_node
   Current Metrics: fan-in=34, fan-out=12, coupling=46, stability=0.26
   ROI Score: 42.3/100
   Estimated Impact: 12 coupling reduction, 3.2% rebuild reduction
   Effort: Medium
   Break-Even: 8 commits

   Issues Detected:
     • Critical hub node (betweenness: 0.087)
     • Bottleneck in dependency graph

   Actionable Steps:
     → Reduce centrality by extracting interfaces
     → Consider breaking into multiple focused headers

Recommended Action Plan:

  1. START WITH QUICK WINS (5 candidates)
     Low effort, high reward. Break-even in ≤5 commits.
     • FslBase/Math/MathHelper.hpp
     • FslGraphics/Render/Adapter.hpp
     • FslUtil/Config/ConfigParser.hpp

  2. ADDRESS CRITICAL ISSUES (12 candidates)
     Focus on cycle elimination and high-impact refactorings.
     Priority: 8 headers in circular dependencies

  3. PLAN MODERATE REFACTORINGS (6 candidates)
     Schedule for future iterations based on team capacity.

  Team Impact Estimation:
     Average payback time: 1.4 weeks
     Estimated developer-hours saved/year: 312 hours
     Equivalent to: 2.0 developer-months/year
```

**Anti-Patterns Detected:**
- **God Objects**: Headers with fan-out >50 (includes too many other headers)
- **Cycle Participants**: Headers in circular dependency groups  
- **Coupling Outliers**: Headers with coupling >2.5σ above mean
- **Unstable Interfaces**: High instability (>0.5) with many dependents (≥10)
- **Hub Nodes**: Critical bottlenecks with high betweenness centrality

**ROI Calculation:**
- **ROI Score (0-100)**: Composite metric
  - 40%: Cycle elimination (highest priority)
  - 30%: Rebuild reduction (ongoing benefit)
  - 20%: Coupling decrease (architectural health)
  - 10%: Ease of change (effort estimate)
- **Break-Even Commits**: Estimated commits until benefits exceed refactoring costs
- **Effort Levels**: Low (5 hours), Medium (20 hours), High (40 hours)

**Severity Classification:**
- 🟢 **Quick Wins**: ROI ≥60, break-even ≤5 commits (low-hanging fruit)
- 🔴 **Critical**: Cycles or ROI ≥40 (high-impact, must address)
- 🟡 **Moderate**: ROI <40 (beneficial but lower priority)

### 9. Architectural Insights (with `--compare-with` or `--load-baseline`)

When comparing builds, additional architectural insights are displayed:

#### Coupling Statistics
```
=== COUPLING STATISTICS ===

Distribution Analysis:
  Mean coupling:    Baseline: 12.3 → Current: 13.1 (+6.5%)
  Median coupling:  Baseline: 8.0 → Current: 9.0 (+12.5%)
  95th percentile:  Baseline: 28 → Current: 31 (+10.7%)

Outliers (>2σ above mean):
  Baseline: 8 headers → Current: 12 headers (+50.0%)

Top Coupling Increases:
  • FslGraphics/Render/Basic.hpp: +8 (15 → 23)
  • FslBase/Math/Vector3.hpp: +5 (18 → 23)
```

#### Stability Changes
```
=== STABILITY CHANGES ===

Headers Became Unstable (stability > 0.5):
  • FslGraphics/Render/Context.hpp: 0.45 → 0.62

Headers Became Stable (stability ≤ 0.5):
  • FslBase/Interface/IRenderer.hpp: 0.55 → 0.33
```

#### Ripple Impact (Precise Analysis - Default)
```
=== RIPPLE IMPACT ANALYSIS ===

Changed Headers Ripple Effect:
  • FslGraphics/Render/Basic.hpp
    Direct dependents: 23 headers
    Transitive impact: 156 source files (7.8% of codebase)

Total Estimated Rebuild Impact: 390 source files (19.5%)
```

#### Architectural Recommendations
```
=== RECOMMENDATIONS ===

🔴 CRITICAL: 1 new circular dependency introduced
   Break cycle by removing: FslGraphics/Render/NewFeature.hpp → Context.hpp

🟡 MODERATE: 2 headers became unstable (stability > 0.5)
   Consider inverting dependencies

🟢 POSITIVE: 2 headers reduced coupling
   Continue this trend

Overall Assessment: Architecture degraded slightly
  Quality Score: 78.5 → 76.2 (-2.3 points)
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

### PageRank
Measures architectural importance using Google's PageRank algorithm. Headers with high PageRank are influential in the dependency graph and changes to them have wide-reaching effects.

### Betweenness Centrality
Measures how often a header appears on shortest paths between other headers. High betweenness indicates architectural bottlenecks — headers that connect different parts of the system.

### Architecture Quality Score (0-100)
Composite metric based on:
- Sparsity (40%): Lower coupling is better
- Cycles (30%): Fewer cycles is better
- High coupling outliers (20%): Fewer high-coupling headers is better
- Stable interfaces (10%): More stable interfaces is better

Score interpretation:
- **90-100**: Excellent architecture
- **75-89**: Good architecture
- **60-74**: Acceptable with room for improvement
- **<60**: Needs architectural refactoring

## Use Cases

### 1. Proactive Improvement Planning (NEW)
**Question**: "What should I refactor to improve my codebase?"

```bash
./buildCheckDSM.py ../build/release/ --suggest-improvements
```

Get ROI-ranked recommendations for:
- Breaking circular dependencies
- Splitting god objects  
- Reducing coupling outliers
- Stabilizing volatile interfaces
- Removing architectural bottlenecks

No baseline required — analyzes current state only.

**Follow-up questions:**
- "Which refactorings give the best return on investment?"
- "What are the quick wins I can tackle first?"
- "How many commits until this refactoring pays for itself?"

### 2. Architectural Review
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
| **buildCheckDSM.py --suggest-improvements** | Proactive refactoring opportunities | Identifying improvement candidates, ROI analysis |
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

# 6. 🆕 Get proactive improvement recommendations
./buildCheckDSM.py ../build/release/ --suggest-improvements --top 20
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

- **1.2.0** (2025-11-23): Proactive improvement analysis
  - Added `--suggest-improvements` for single-run refactoring recommendations
  - Anti-pattern detection: god objects, cycles, outliers, unstable interfaces, hub nodes
  - ROI calculation with break-even analysis
  - Severity-based prioritization (🟢 Quick Wins, 🔴 Critical, 🟡 Moderate)
  - Precise transitive closure for accurate rebuild impact estimation
  - Team impact estimation (hours saved, payback time)
  - No baseline required — analyzes current state only

- **1.1.0** (2025-11-21): Differential analysis enhancements
  - Added `--save-results` and `--load-baseline` for flexible baseline workflows
  - Comprehensive architectural insights with coupling statistics
  - Precise ripple impact analysis (default) with `--heuristic-only` fast mode
  - Statistical analysis: mean/median/percentile coupling trends
  - Stability change tracking and interface extraction detection
  - Layer movement analysis and ROI-based recommendations
  - Severity-scored recommendations (🔴 Critical, 🟡 Moderate, 🟢 Positive)

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
