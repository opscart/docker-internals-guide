#!/usr/bin/env python3
"""
Docker Performance Statistical Analysis
========================================
Analyzes CSV results from statistical-benchmark.sh
Computes: mean, median, std dev, 95% CI, Mann-Whitney U tests
Generates: summary tables suitable for academic paper

Usage:
    python3 analyze_results.py results/azure-premium-ssd
    python3 analyze_results.py --compare results/azure-premium-ssd results/azure-standard-hdd results/macos-docker-desktop

Author: Shamsher Khan
Repository: https://github.com/opscart/docker-internals-guide
"""

import os
import sys
import csv
import math
from pathlib import Path
from collections import defaultdict

# Try to import scipy for Mann-Whitney U test
# If not available, skip significance testing
try:
    from scipy import stats as scipy_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    print("Note: scipy not installed. Skipping significance tests.")
    print("Install with: pip install scipy")
    print()


def load_csv(filepath):
    """Load CSV file and return list of dicts."""
    rows = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def compute_stats(values):
    """Compute descriptive statistics for a list of numeric values."""
    values = [v for v in values if v is not None and v != 'N/A']
    if not values:
        return None

    n = len(values)
    mean = sum(values) / n
    median = sorted(values)[n // 2]

    if n > 1:
        variance = sum((x - mean) ** 2 for x in values) / (n - 1)
        std = math.sqrt(variance)
    else:
        std = 0.0

    # 95% confidence interval (Z-distribution, appropriate for n >= 30)
    if n >= 30:
        ci_95 = 1.96 * std / math.sqrt(n)
    else:
        # Use t-distribution approximation for smaller samples
        # t-value for 95% CI with n-1 df (approximate)
        t_val = 2.045 if n >= 20 else 2.262 if n >= 10 else 2.776
        ci_95 = t_val * std / math.sqrt(n)

    return {
        'n': n,
        'mean': round(mean, 2),
        'median': round(median, 2),
        'std': round(std, 2),
        'ci_95': round(ci_95, 2),
        'min': round(min(values), 2),
        'max': round(max(values), 2),
        'ci_lower': round(mean - ci_95, 2),
        'ci_upper': round(mean + ci_95, 2),
    }


def mann_whitney_u(group_a, group_b):
    """Perform Mann-Whitney U test (non-parametric)."""
    if not HAS_SCIPY:
        return None
    if len(group_a) < 5 or len(group_b) < 5:
        return None

    u_stat, p_value = scipy_stats.mannwhitneyu(
        group_a, group_b, alternative='two-sided'
    )

    # Cliff's delta for effect size
    n1, n2 = len(group_a), len(group_b)
    cliffs_d = (2 * u_stat / (n1 * n2)) - 1

    return {
        'u_statistic': round(u_stat, 2),
        'p_value': round(p_value, 6),
        'significant': p_value < 0.05,
        'cliffs_delta': round(cliffs_d, 3),
        'effect_size': (
            'negligible' if abs(cliffs_d) < 0.147 else
            'small' if abs(cliffs_d) < 0.33 else
            'medium' if abs(cliffs_d) < 0.474 else
            'large'
        )
    }


def print_header(title):
    """Print formatted section header."""
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_stats_table(label, stats_dict):
    """Print a formatted statistics table."""
    print(f"\n  {label}")
    print(f"  {'─' * 60}")
    print(f"  {'Metric':<20} {'Value':>12}")
    print(f"  {'─' * 60}")
    print(f"  {'n (samples)':<20} {stats_dict['n']:>12}")
    print(f"  {'Mean':<20} {stats_dict['mean']:>12.2f} ms")
    print(f"  {'Median':<20} {stats_dict['median']:>12.2f} ms")
    print(f"  {'Std Dev (σ)':<20} {stats_dict['std']:>12.2f} ms")
    print(f"  {'95% CI':<20} {'±':>6}{stats_dict['ci_95']:>6.2f} ms")
    print(f"  {'95% CI range':<20} [{stats_dict['ci_lower']:.2f}, {stats_dict['ci_upper']:.2f}]")
    print(f"  {'Min':<20} {stats_dict['min']:>12.2f} ms")
    print(f"  {'Max':<20} {stats_dict['max']:>12.2f} ms")


def analyze_startup_latency(results_dir):
    """Analyze container startup latency results."""
    filepath = os.path.join(results_dir, "01-startup-latency.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 01-startup-latency.csv not found")
        return {}

    rows = load_csv(filepath)

    # Group by image and mode
    groups = defaultdict(list)
    for row in rows:
        key = (row['image'], row['mode'])
        try:
            groups[key].append(float(row['startup_ms']))
        except (ValueError, KeyError):
            pass

    print_header("TEST 1: Container Startup Latency")

    all_stats = {}
    for (image, mode), values in sorted(groups.items()):
        label = f"{image} ({mode} start)"
        s = compute_stats(values)
        if s:
            print_stats_table(label, s)
            all_stats[f"{image}_{mode}"] = s

    return all_stats


def analyze_copyup(results_dir):
    """Analyze copy-up overhead results."""
    filepath = os.path.join(results_dir, "02-copyup-overhead.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 02-copyup-overhead.csv not found")
        return {}

    rows = load_csv(filepath)
    values = []
    for row in rows:
        try:
            values.append(float(row['copyup_ms']))
        except (ValueError, KeyError):
            pass

    print_header("TEST 2: Copy-up Overhead (100MB file)")

    s = compute_stats(values)
    if s:
        print_stats_table("Copy-up latency", s)
        return {'copyup_100mb': s}

    return {}


def analyze_cpu_throttling(results_dir):
    """Analyze CPU throttling accuracy results."""
    filepath = os.path.join(results_dir, "03-cpu-throttling.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 03-cpu-throttling.csv not found")
        return {}

    rows = load_csv(filepath)
    measured = []
    variances = []
    for row in rows:
        try:
            measured.append(float(row['measured_pct']))
            variances.append(abs(float(row['variance_pct'])))
        except (ValueError, KeyError):
            pass

    print_header("TEST 3: CPU Throttling Accuracy (target: 50%)")

    s_measured = compute_stats(measured)
    s_variance = compute_stats(variances)
    if s_measured:
        print_stats_table("Measured CPU %", s_measured)
    if s_variance:
        print_stats_table("Absolute variance from 50%", s_variance)

    return {'cpu_measured': s_measured, 'cpu_variance': s_variance}


def analyze_write_performance(results_dir):
    """Analyze sequential write performance."""
    filepath = os.path.join(results_dir, "04-write-performance.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 04-write-performance.csv not found")
        return {}

    rows = load_csv(filepath)

    groups = defaultdict(list)
    for row in rows:
        try:
            groups[row['mode']].append(float(row['write_speed_mbps']))
        except (ValueError, KeyError):
            pass

    print_header("TEST 4: Sequential Write Performance (MB/s)")

    all_stats = {}
    for mode, values in sorted(groups.items()):
        s = compute_stats(values)
        if s:
            # Relabel for write speed
            print(f"\n  {mode}")
            print(f"  {'─' * 60}")
            print(f"  {'n':<20} {s['n']:>12}")
            print(f"  {'Mean':<20} {s['mean']:>12.2f} MB/s")
            print(f"  {'Std Dev':<20} {s['std']:>12.2f} MB/s")
            print(f"  {'95% CI':<20} {'±':>6}{s['ci_95']:>6.2f} MB/s")
            all_stats[mode] = s

    return all_stats


def analyze_metadata(results_dir):
    """Analyze metadata operations."""
    filepath = os.path.join(results_dir, "05-metadata-operations.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 05-metadata-operations.csv not found")
        return {}

    rows = load_csv(filepath)

    groups = defaultdict(list)
    for row in rows:
        try:
            groups[row['mode']].append(float(row['duration_ms']))
        except (ValueError, KeyError):
            pass

    print_header("TEST 5: Metadata Operations (500 file creation)")

    all_stats = {}
    for mode, values in sorted(groups.items()):
        s = compute_stats(values)
        if s:
            print_stats_table(f"{mode} (500 files)", s)
            all_stats[mode] = s

    # Compute overhead if both present
    if 'overlayfs' in groups and 'volume' in groups:
        overlay_mean = compute_stats(groups['overlayfs'])['mean']
        vol_mean = compute_stats(groups['volume'])['mean']
        if vol_mean > 0:
            overhead_pct = ((overlay_mean - vol_mean) / vol_mean) * 100
            print(f"\n  OverlayFS overhead vs volume: {overhead_pct:.1f}%")

    return all_stats


def analyze_pull_time(results_dir):
    """Analyze image pull times."""
    filepath = os.path.join(results_dir, "06-image-pull-time.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 06-image-pull-time.csv not found")
        return {}

    rows = load_csv(filepath)

    groups = defaultdict(list)
    for row in rows:
        try:
            groups[row['image']].append(float(row['pull_time_ms']))
        except (ValueError, KeyError):
            pass

    print_header("TEST 6: Image Pull Time")

    all_stats = {}
    for image, values in sorted(groups.items()):
        s = compute_stats(values)
        if s:
            print_stats_table(image, s)
            all_stats[image] = s

    return all_stats


def cross_platform_comparison(platform_dirs):
    """Compare results across multiple platforms with significance tests."""
    print_header("CROSS-PLATFORM COMPARISON")

    # Load startup latency data from each platform
    platform_data = {}
    for pdir in platform_dirs:
        platform_name = os.path.basename(pdir)
        filepath = os.path.join(pdir, "01-startup-latency.csv")
        if not os.path.exists(filepath):
            continue

        rows = load_csv(filepath)
        groups = defaultdict(list)
        for row in rows:
            key = (row['image'], row['mode'])
            try:
                groups[key].append(float(row['startup_ms']))
            except (ValueError, KeyError):
                pass
        platform_data[platform_name] = groups

    if len(platform_data) < 2:
        print("  Need at least 2 platforms for comparison.")
        return

    # --- Comparison table for paper ---
    print("\n  TABLE FOR PAPER: Warm Startup Latency (Alpine)")
    print(f"  {'─' * 70}")
    print(f"  {'Platform':<30} {'Mean (ms)':>10} {'σ':>8} {'95% CI':>14} {'n':>6}")
    print(f"  {'─' * 70}")

    alpine_data = {}
    for platform, groups in sorted(platform_data.items()):
        key = ('alpine', 'warm')
        if key in groups:
            s = compute_stats(groups[key])
            alpine_data[platform] = groups[key]
            print(f"  {platform:<30} {s['mean']:>10.1f} {s['std']:>8.1f} "
                  f"[{s['ci_lower']:.1f}, {s['ci_upper']:.1f}] {s['n']:>6}")
    print(f"  {'─' * 70}")

    # --- Mann-Whitney U tests between all platform pairs ---
    if HAS_SCIPY and len(alpine_data) >= 2:
        print("\n  SIGNIFICANCE TESTS (Mann-Whitney U)")
        print(f"  {'─' * 70}")
        platforms = sorted(alpine_data.keys())
        for i in range(len(platforms)):
            for j in range(i + 1, len(platforms)):
                p1, p2 = platforms[i], platforms[j]
                result = mann_whitney_u(alpine_data[p1], alpine_data[p2])
                if result:
                    sig = "YES ✓" if result['significant'] else "NO"
                    print(f"  {p1} vs {p2}:")
                    print(f"    U = {result['u_statistic']}, "
                          f"p = {result['p_value']:.6f}, "
                          f"significant: {sig}")
                    print(f"    Cliff's δ = {result['cliffs_delta']} "
                          f"({result['effect_size']} effect)")
                    print()


def generate_latex_table(platform_dirs):
    """Generate LaTeX table ready for paper."""
    print_header("LATEX TABLE (copy into paper)")

    print(r"""
\begin{table}[h]
\centering
\caption{Container startup latency across three infrastructure tiers (Alpine image, warm start).
Values reported as mean $\pm$ 95\% CI with standard deviation ($\sigma$), $n=50$ iterations per platform.}
\label{tab:startup-latency}
\begin{tabular}{lccccc}
\toprule
\textbf{Platform} & \textbf{Mean (ms)} & \textbf{$\sigma$ (ms)} & \textbf{95\% CI} & \textbf{Min} & \textbf{Max} \\
\midrule""")

    for pdir in platform_dirs:
        platform_name = os.path.basename(pdir)
        filepath = os.path.join(pdir, "01-startup-latency.csv")
        if not os.path.exists(filepath):
            continue

        rows = load_csv(filepath)
        values = []
        for row in rows:
            if row.get('image') == 'alpine' and row.get('mode') == 'warm':
                try:
                    values.append(float(row['startup_ms']))
                except (ValueError, KeyError):
                    pass

        if values:
            s = compute_stats(values)
            clean_name = platform_name.replace('-', ' ').replace('_', ' ').title()
            print(f"{clean_name} & {s['mean']:.1f} & {s['std']:.1f} & "
                  f"[{s['ci_lower']:.1f}, {s['ci_upper']:.1f}] & "
                  f"{s['min']:.1f} & {s['max']:.1f} \\\\")

    print(r"""\bottomrule
\end{tabular}
\end{table}""")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Single platform:   python3 analyze_results.py results/azure-premium-ssd")
        print("  Compare platforms: python3 analyze_results.py --compare results/platform1 results/platform2 ...")
        sys.exit(1)

    if sys.argv[1] == '--compare':
        platform_dirs = sys.argv[2:]
        if len(platform_dirs) < 2:
            print("Need at least 2 platform directories for comparison.")
            sys.exit(1)

        # Analyze each platform individually
        for pdir in platform_dirs:
            print(f"\n{'#' * 70}")
            print(f"# Platform: {os.path.basename(pdir)}")
            print(f"{'#' * 70}")
            analyze_startup_latency(pdir)
            analyze_copyup(pdir)
            analyze_cpu_throttling(pdir)

        # Cross-platform comparison
        cross_platform_comparison(platform_dirs)
        generate_latex_table(platform_dirs)

    else:
        results_dir = sys.argv[1]
        if not os.path.isdir(results_dir):
            print(f"Error: {results_dir} is not a directory")
            sys.exit(1)

        print(f"Analyzing: {results_dir}")
        print(f"Platform:  {os.path.basename(results_dir)}")

        analyze_startup_latency(results_dir)
        analyze_copyup(results_dir)
        analyze_cpu_throttling(results_dir)
        analyze_write_performance(results_dir)
        analyze_metadata(results_dir)
        analyze_pull_time(results_dir)

        print_header("ANALYSIS COMPLETE")
        print(f"  Results directory: {results_dir}")
        print(f"  To compare across platforms, re-run with --compare flag")
        print()


if __name__ == '__main__':
    main()