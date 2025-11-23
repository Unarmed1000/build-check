# BuildCheck Demo Summary

## Overview

This directory contains demonstration scripts that showcase BuildCheck's DSM analysis capabilities across 10 predefined architectural scenarios.

## Available Demos

| Demo Script | Purpose | Analysis Method | Output |
|-------------|---------|-----------------|--------|
| `demo_dsm_scenario_patterns.py` | Demonstrates DSM baseline comparison workflow | Creates git repos, saves baseline, runs `buildCheckDSM.py --load-baseline` | Authentic differential analysis with architectural insights |
| `demo_git_scenario_equivalence.py` | Demonstrates git working tree analysis | Creates git repos, runs `buildCheckDSM.py --git-impact` | Authentic tool output with architectural insights |

## Demo: demo_dsm_scenario_patterns.py

### Purpose
Demonstrates the DSM baseline comparison workflow using predefined architectural scenarios. Shows how to save a baseline and compare against it using `buildCheckDSM.py --load-baseline`.

### Key Features
- Creates git repositories with baseline committed to HEAD
- Saves baseline using --save-results
- Applies scenario changes and commits them
- Runs --load-baseline for differential analysis
- Shows full architectural insights (statistics, ripple impact, severity recommendations)
- Demonstrates complete workflow users would follow
### Usage Examples

**Basic Run:**
```bash
python demo/demo_dsm_scenario_patterns.py
```

**With Verbose Output:**
```bash
python demo/demo_dsm_scenario_patterns.py --verbose
```

## Demo: demo_git_scenario_equivalence.py

### Purpose
Demonstrates real-world git working tree impact analysis by creating physical git repositories and running `buildCheckDSM.py --git-impact` on each scenario.

### Key Features
- Creates temporary git repositories with baseline committed to HEAD
- Leaves scenario changes uncommitted in working tree
- Calls actual `buildCheckDSM.py --git-impact` command
- Shows authentic tool output with full architectural insights
- Demonstrates realistic developer workflow

### What It Shows
For each scenario, displays:
- Changed headers and source files
- Rebuild percentage and impact estimation
- Architectural risks (new cycles, coupling increases)
- Statistical coupling analysis (μ, σ, P95, P99)
- Severity-based recommendations (🔴 Critical, 🟡 Moderate, 🟢 Positive)
- Ripple impact assessment

### Usage Examples

**Basic Run:**
```bash
python demo/demo_git_scenario_equivalence.py
```

**With Verbose buildCheckDSM.py Output:**
```bash
python demo/demo_git_scenario_equivalence.py --verbose
```

## Architectural Scenarios

All demos use the same 10 predefined architectural scenarios:

1. **Architectural Regressions** - Introducing circular dependencies
2. **Architectural Improvements** - Reducing coupling effectively
3. **Refactoring Trade-offs** - Interface extraction patterns
4. **Pure Rebuild Reduction** - Using forward declarations
5. **Cycle Churn** - Architectural instability patterns
6. **Hidden Instability** - Stability threshold crossings
7. **Dependency Hotspot** - High-coupling concentration
8. **ROI Break-even** - Refactoring cost/benefit analysis
9. **Outlier Detection** - Hidden architectural debt
10. **Critical Breaking Edges** - Strategic cycle resolution

## Benefits

### For Developers
✅ **Real Tool Output**: See exactly what buildCheckDSM.py shows
✅ **Quick Learning**: Understand git impact analysis through examples
✅ **Workflow Validation**: Test architectural changes before committing

### For Teams
✅ **Training Resource**: Onboard developers on architectural analysis
✅ **Pattern Library**: Reference implementations of common scenarios
✅ **Best Practices**: Learn how to interpret DSM analysis results

## Technical Details

### Implementation
- Uses `lib.scenario_creators` to generate git repositories
- Calls `buildCheckDSM.py` as subprocess with `--git-impact` flag
- Captures and displays authentic tool output
- Automatic cleanup of temporary repositories

### Performance
- Each scenario takes 2-5 seconds (git creation + analysis)
- Total demo runtime: ~30-60 seconds for all 10 scenarios
- Scales with scenario complexity

---

Run the demos yourself:
```bash
# Validate DSM analysis directly
python demo/demo_dsm_scenario_patterns.py

# See real git impact analysis
python demo/demo_git_scenario_equivalence.py
