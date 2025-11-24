#!/usr/bin/env python3
"""
Verification script to demonstrate improved statistical accuracy with NumPy.

Compares old manual percentile calculation vs. NumPy's proper percentile calculation.
"""

import numpy as np

# Example coupling distribution
couplings = [1, 1, 1, 1, 2, 2, 2, 3, 3, 5]

print("Coupling Distribution:", couplings)
print(f"Sample size: {len(couplings)}")
print()

# OLD METHOD (manual index calculation - INCORRECT)
print("❌ OLD METHOD (Manual Index Calculation):")
couplings_sorted = sorted(couplings)
p95_idx = int(len(couplings_sorted) * 0.95)
p99_idx = int(len(couplings_sorted) * 0.99)
old_p95 = couplings_sorted[p95_idx] if p95_idx < len(couplings_sorted) else couplings_sorted[-1]
old_p99 = couplings_sorted[p99_idx] if p99_idx < len(couplings_sorted) else couplings_sorted[-1]
print(f"  P95 index: {p95_idx} → value: {old_p95}")
print(f"  P99 index: {p99_idx} → value: {old_p99}")
print()

# NEW METHOD (NumPy percentile with proper interpolation)
print("✅ NEW METHOD (NumPy with Linear Interpolation):")
new_p95 = np.percentile(couplings, 95)
new_p99 = np.percentile(couplings, 99)
print(f"  P95: {new_p95:.2f}")
print(f"  P99: {new_p99:.2f}")
print()

# Show the difference
print("📊 IMPROVEMENT:")
print(f"  P95 difference: {abs(new_p95 - old_p95):.2f}")
print(f"  P99 difference: {abs(new_p99 - old_p99):.2f}")
print()

# Additional statistics using NumPy
print("📈 Complete Statistical Analysis (NumPy):")
print(f"  Mean (μ):     {np.mean(couplings):.2f}")
print(f"  Std Dev (σ):  {np.std(couplings, ddof=1):.2f}")  # Sample std dev
print(f"  Median:       {np.median(couplings):.2f}")
print(f"  Min:          {np.min(couplings)}")
print(f"  Max:          {np.max(couplings)}")
print(f"  P50 (median): {np.percentile(couplings, 50):.2f}")
print(f"  P75:          {np.percentile(couplings, 75):.2f}")
print(f"  P95:          {np.percentile(couplings, 95):.2f}")
print(f"  P99:          {np.percentile(couplings, 99):.2f}")
print()

print("✨ NumPy provides:")
print("  • Proper interpolation for percentiles")
print("  • Consistent with statistical standards")
print("  • More accurate for small sample sizes")
print("  • Sample standard deviation (ddof=1)")
print("  • Vectorized operations (faster for large datasets)")
