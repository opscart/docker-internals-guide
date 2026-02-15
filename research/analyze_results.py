#!/usr/bin/env python3
"""
Docker Performance Statistical Analysis v3
===========================================
Analyzes CSV results from statistical-benchmark.sh v3
Computes: mean, median, std dev, 95% CI, Mann-Whitney U, Cliff's delta
Generates: summary tables + LaTeX tables for academic paper

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
from collections import defaultdict

try:
    from scipy import stats as scipy_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    print("Note: scipy not installed. Skipping significance tests.")
    print("Install with: pip3 install scipy")
    print()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def load_csv(filepath):
    """Load CSV file into list of dicts."""
    with open(filepath, 'r') as f:
        return list(csv.DictReader(f))


def parse_float(val):
    """
    Safely parse a float from a string.
    Handles: "2.142 ms", "695.2MB/s", "N/A", empty strings, etc.
    """
    if val is None:
        return None
    val = str(val).strip()
    if val in ('', 'N/A', 'null', 'None'):
        return None
    # Strip common unit suffixes
    for suffix in [' ms', 'ms', ' MB/s', 'MB/s', ' MB', 'MB',
                   ' KB', 'KB', ' MiB', 'MiB', ' GiB', 'GiB', '%']:
        if val.endswith(suffix):
            val = val[:-len(suffix)].strip()
    try:
        return float(val)
    except ValueError:
        return None


def compute_stats(values):
    """
    Compute descriptive statistics.
    Returns: dict with n, mean, median, std, ci_95, min, max, ci_lower, ci_upper
    Uses t-distribution for n<30, z-distribution for n>=30.
    """
    values = [v for v in values if v is not None]
    if not values:
        return None

    n = len(values)
    mean = sum(values) / n
    sorted_vals = sorted(values)
    median = sorted_vals[n // 2]

    if n > 1:
        variance = sum((x - mean) ** 2 for x in values) / (n - 1)
        std = math.sqrt(variance)
    else:
        std = 0.0

    # 95% confidence interval
    if n >= 30:
        # Large sample: z-distribution
        ci_95 = 1.96 * std / math.sqrt(n)
    elif n >= 20:
        ci_95 = 2.045 * std / math.sqrt(n)
    elif n >= 10:
        ci_95 = 2.262 * std / math.sqrt(n)
    else:
        ci_95 = 2.776 * std / math.sqrt(n)

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
    """
    Non-parametric significance test.
    Returns: U statistic, p-value, significance, Cliff's delta, effect size label.
    """
    if not HAS_SCIPY:
        return None
    if len(group_a) < 5 or len(group_b) < 5:
        return None

    u_stat, p_value = scipy_stats.mannwhitneyu(
        group_a, group_b, alternative='two-sided'
    )
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


# =============================================================================
# DISPLAY HELPERS
# =============================================================================

def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def print_stats_table(label, s, unit="ms"):
    print(f"\n  {label}")
    print(f"  {'─' * 60}")
    print(f"  {'Metric':<20} {'Value':>15}")
    print(f"  {'─' * 60}")
    print(f"  {'n (samples)':<20} {s['n']:>15}")
    print(f"  {'Mean':<20} {s['mean']:>12.2f} {unit}")
    print(f"  {'Median':<20} {s['median']:>12.2f} {unit}")
    print(f"  {'Std Dev (σ)':<20} {s['std']:>12.2f} {unit}")
    print(f"  {'95% CI':<20} {'±':>6}{s['ci_95']:>6.2f} {unit}")
    print(f"  {'95% CI range':<20} [{s['ci_lower']:.2f}, {s['ci_upper']:.2f}]")
    print(f"  {'Min':<20} {s['min']:>12.2f} {unit}")
    print(f"  {'Max':<20} {s['max']:>12.2f} {unit}")


def check_all_zero(values, test_name=""):
    """Warn if all collected values are zero — indicates data collection bug."""
    if values and all(v == 0.0 for v in values):
        print(f"  ⚠ WARNING: All values are 0.0 for {test_name}")
        print(f"    This is likely a data collection bug from the old script (v1/v2).")
        print(f"    Re-run with statistical-benchmark.sh v3 to fix.")
        return True
    return False


# =============================================================================
# INDIVIDUAL TEST ANALYZERS
# =============================================================================

def analyze_startup_latency(results_dir):
    """Test 1: Container startup latency — warm and cold, 3 images."""
    filepath = os.path.join(results_dir, "01-startup-latency.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 01-startup-latency.csv not found")
        return {}

    rows = load_csv(filepath)
    groups = defaultdict(list)
    for row in rows:
        val = parse_float(row.get('startup_ms'))
        if val is not None:
            groups[(row['image'], row['mode'])].append(val)

    print_header("TEST 1: Container Startup Latency")

    all_stats = {}
    for (image, mode), values in sorted(groups.items()):
        s = compute_stats(values)
        if s:
            print_stats_table(f"{image} ({mode} start)", s)
            all_stats[f"{image}_{mode}"] = s

    return all_stats


def analyze_copyup(results_dir):
    """Test 2: Copy-up overhead (100MB file write in OverlayFS)."""
    filepath = os.path.join(results_dir, "02-copyup-overhead.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 02-copyup-overhead.csv not found")
        return {}

    rows = load_csv(filepath)
    values = [v for v in (parse_float(r.get('copyup_ms')) for r in rows) if v is not None]

    print_header("TEST 2: Copy-up Overhead (100MB file)")

    if check_all_zero(values, "copy-up"):
        return {}

    s = compute_stats(values)
    if s:
        print_stats_table("Copy-up latency", s)
        return {'copyup_100mb': s}
    return {}


def analyze_cpu_throttling(results_dir):
    """Test 3: CPU throttling accuracy (target: 50%)."""
    filepath = os.path.join(results_dir, "03-cpu-throttling.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 03-cpu-throttling.csv not found")
        return {}

    rows = load_csv(filepath)
    measured = [v for v in (parse_float(r.get('measured_pct')) for r in rows) if v is not None]
    variances = [abs(v) for v in (parse_float(r.get('variance_pct')) for r in rows) if v is not None]

    print_header("TEST 3: CPU Throttling Accuracy (target: 50%)")

    all_stats = {}
    s = compute_stats(measured)
    if s:
        print_stats_table("Measured CPU %", s, unit="%")
        all_stats['cpu_measured'] = s

    s = compute_stats(variances)
    if s:
        print_stats_table("Absolute variance from 50%", s, unit="%")
        all_stats['cpu_variance'] = s

    return all_stats


def analyze_write_performance(results_dir):
    """Test 4: Sequential write performance — OverlayFS vs volume mount."""
    filepath = os.path.join(results_dir, "04-write-performance.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 04-write-performance.csv not found")
        return {}

    rows = load_csv(filepath)
    groups = defaultdict(list)
    for row in rows:
        val = parse_float(row.get('write_speed_mbps'))
        if val is not None:
            groups[row['mode']].append(val)

    print_header("TEST 4: Sequential Write Performance (256MB)")

    all_stats = {}
    for mode, values in sorted(groups.items()):
        if check_all_zero(values, f"write {mode}"):
            continue
        s = compute_stats(values)
        if s:
            print_stats_table(mode, s, unit="MB/s")
            all_stats[mode] = s

    # OverlayFS vs Volume ratio
    if 'overlayfs' in all_stats and 'volume' in all_stats:
        if all_stats['volume']['mean'] > 0:
            ratio = all_stats['overlayfs']['mean'] / all_stats['volume']['mean']
            print(f"\n  OverlayFS / Volume ratio: {ratio:.2f}×")

        # Significance test
        if HAS_SCIPY and 'overlayfs' in groups and 'volume' in groups:
            result = mann_whitney_u(groups['overlayfs'], groups['volume'])
            if result:
                sig = "YES" if result['significant'] else "NO"
                print(f"  Significant difference: {sig} (p={result['p_value']:.6f})")
                print(f"  Cliff's delta: {result['cliffs_delta']} ({result['effect_size']})")

    return all_stats


def analyze_metadata(results_dir):
    """Test 5: Metadata operations — 500 file creation OverlayFS vs volume."""
    filepath = os.path.join(results_dir, "05-metadata-operations.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 05-metadata-operations.csv not found")
        return {}

    rows = load_csv(filepath)
    groups = defaultdict(list)
    for row in rows:
        val = parse_float(row.get('duration_ms'))
        if val is not None:
            groups[row['mode']].append(val)

    print_header("TEST 5: Metadata Operations (500 file creation)")

    all_stats = {}
    for mode, values in sorted(groups.items()):
        if check_all_zero(values, f"metadata {mode}"):
            continue
        s = compute_stats(values)
        if s:
            print_stats_table(f"{mode} (500 files)", s)
            all_stats[mode] = s

    if 'overlayfs' in all_stats and 'volume' in all_stats:
        overlay_mean = all_stats['overlayfs']['mean']
        vol_mean = all_stats['volume']['mean']
        if vol_mean > 0:
            overhead_pct = ((overlay_mean - vol_mean) / vol_mean) * 100
            print(f"\n  OverlayFS overhead vs volume: {overhead_pct:.1f}%")

    return all_stats


def analyze_pull_time(results_dir):
    """Test 6: Image pull time (cold pull after removing image)."""
    filepath = os.path.join(results_dir, "06-image-pull-time.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 06-image-pull-time.csv not found")
        return {}

    rows = load_csv(filepath)
    groups = defaultdict(list)
    for row in rows:
        val = parse_float(row.get('pull_time_ms'))
        if val is not None:
            groups[row['image']].append(val)

    print_header("TEST 6: Image Pull Time")

    all_stats = {}
    for image, values in sorted(groups.items()):
        s = compute_stats(values)
        if s:
            print_stats_table(image, s)
            all_stats[image] = s

    return all_stats


def analyze_namespace_overhead(results_dir):
    """Test 7: Namespace creation overhead (Linux only)."""
    filepath = os.path.join(results_dir, "07-namespace-overhead.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 07-namespace-overhead.csv not found")
        return {}

    rows = load_csv(filepath)
    values = [v for v in (parse_float(r.get('duration_ms')) for r in rows) if v is not None]

    print_header("TEST 7: Namespace Creation Overhead")

    if not values:
        print("  Skipped on this platform (expected on macOS)")
        return {}

    s = compute_stats(values)
    if s:
        print_stats_table("Namespace creation (unshare)", s)
        return {'namespace_create': s}
    return {}


def analyze_network_latency(results_dir):
    """Test 8: Network latency — bridge vs host mode."""
    filepath = os.path.join(results_dir, "08-network-latency.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 08-network-latency.csv not found")
        return {}

    rows = load_csv(filepath)
    groups = defaultdict(list)
    for row in rows:
        val = parse_float(row.get('avg_rtt_ms'))
        if val is not None and val > 0:
            groups[row['mode']].append(val)

    if not any(groups.values()):
        print_header("TEST 8: Network Latency")
        print("  No valid data found")
        return {}

    print_header("TEST 8: Network Latency — Bridge vs Host (avg RTT)")

    all_stats = {}
    for mode, values in sorted(groups.items()):
        s = compute_stats(values)
        if s:
            print_stats_table(f"{mode} mode", s)
            all_stats[mode] = s

    if 'bridge' in all_stats and 'host' in all_stats:
        overhead = all_stats['bridge']['mean'] - all_stats['host']['mean']
        print(f"\n  Bridge overhead vs host: {overhead:.2f} ms")

        if HAS_SCIPY:
            result = mann_whitney_u(groups['bridge'], groups['host'])
            if result:
                sig = "YES" if result['significant'] else "NO"
                print(f"  Significant difference: {sig} (p={result['p_value']:.6f})")
                print(f"  Cliff's delta: {result['cliffs_delta']} ({result['effect_size']})")

    return all_stats


def analyze_memory_efficiency(results_dir):
    """Test 9: Memory efficiency — page cache sharing (3× nginx)."""
    filepath = os.path.join(results_dir, "09-memory-efficiency.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 09-memory-efficiency.csv not found")
        return {}

    rows = load_csv(filepath)

    # v3 uses per_container_mem_mb / total_mem_mb
    # v1/v2 used per_container_rss_kb / total_rss_kb
    # Handle both formats
    per_container = []
    totals = []
    unit = "MB"

    for r in rows:
        # Try v3 format first
        pc = parse_float(r.get('per_container_mem_mb'))
        tot = parse_float(r.get('total_mem_mb'))
        if pc is not None and tot is not None:
            per_container.append(pc)
            totals.append(tot)
            continue
        # Fall back to v1/v2 format
        pc = parse_float(r.get('per_container_rss_kb'))
        tot = parse_float(r.get('total_rss_kb'))
        if pc is not None and tot is not None:
            per_container.append(pc)
            totals.append(tot)
            unit = "KB"

    print_header("TEST 9: Memory Efficiency — Page Cache Sharing (3× nginx)")

    if not per_container:
        print("  No valid data found")
        print("  (On macOS, ensure v3 script is used — it uses docker stats instead of /proc)")
        return {}

    all_stats = {}
    s_per = compute_stats(per_container)
    s_total = compute_stats(totals)

    if s_per:
        print_stats_table(f"Per-container memory", s_per, unit=unit)
        all_stats['per_container'] = s_per
    if s_total:
        print_stats_table(f"Total memory (3 containers)", s_total, unit=unit)
        all_stats['total'] = s_total

    if s_per and s_total:
        theoretical = s_per['mean'] * 3
        actual = s_total['mean']
        if theoretical > 0:
            sharing_pct = ((theoretical - actual) / theoretical) * 100
            print(f"\n  Page cache sharing efficiency: {sharing_pct:.1f}%")
            print(f"  (3× individual = {theoretical:.1f} {unit} vs actual {actual:.1f} {unit})")

    return all_stats


# =============================================================================
# CROSS-PLATFORM COMPARISON
# =============================================================================

def cross_platform_comparison(platform_dirs):
    """Compare results across 2+ platforms with significance tests."""
    print_header("CROSS-PLATFORM COMPARISON")

    # Load startup data for all platforms
    platform_startup = {}
    for pdir in platform_dirs:
        pname = os.path.basename(pdir)
        filepath = os.path.join(pdir, "01-startup-latency.csv")
        if not os.path.exists(filepath):
            continue
        rows = load_csv(filepath)
        groups = defaultdict(list)
        for row in rows:
            val = parse_float(row.get('startup_ms'))
            if val is not None:
                groups[(row['image'], row['mode'])].append(val)
        platform_startup[pname] = groups

    if len(platform_startup) < 2:
        print("  Need at least 2 platforms with startup data for comparison.")
        return

    # --- Startup latency comparison ---
    for image_label in ['alpine', 'nginx', 'python_3.11-slim']:
        print(f"\n  TABLE: Warm Startup Latency — {image_label}")
        print(f"  {'─' * 72}")
        print(f"  {'Platform':<30} {'Mean (ms)':>10} {'σ':>8} {'95% CI':>18} {'n':>5}")
        print(f"  {'─' * 72}")

        image_data = {}
        for platform, groups in sorted(platform_startup.items()):
            key = (image_label, 'warm')
            if key in groups:
                s = compute_stats(groups[key])
                image_data[platform] = groups[key]
                print(f"  {platform:<30} {s['mean']:>10.1f} {s['std']:>8.1f} "
                      f"[{s['ci_lower']:.1f}, {s['ci_upper']:.1f}] {s['n']:>5}")
        print(f"  {'─' * 72}")

        # Significance tests between all pairs
        if HAS_SCIPY and len(image_data) >= 2:
            print(f"\n  SIGNIFICANCE TESTS ({image_label})")
            platforms = sorted(image_data.keys())
            for i in range(len(platforms)):
                for j in range(i + 1, len(platforms)):
                    p1, p2 = platforms[i], platforms[j]
                    result = mann_whitney_u(image_data[p1], image_data[p2])
                    if result:
                        sig = "YES ✓" if result['significant'] else "NO"
                        print(f"    {p1} vs {p2}: "
                              f"U={result['u_statistic']}, "
                              f"p={result['p_value']:.6f}, "
                              f"sig: {sig}, "
                              f"Cliff's δ={result['cliffs_delta']} ({result['effect_size']})")

    # --- Other test comparisons ---
    comparisons = [
        ("Copy-up Overhead (100MB)", "02-copyup-overhead.csv", "copyup_ms", "ms"),
        ("CPU Throttling (target 50%)", "03-cpu-throttling.csv", "measured_pct", "%"),
        ("Namespace Creation", "07-namespace-overhead.csv", "duration_ms", "ms"),
    ]

    for label, csv_file, field, unit in comparisons:
        print(f"\n  TABLE: {label}")
        print(f"  {'─' * 65}")
        for pdir in platform_dirs:
            pname = os.path.basename(pdir)
            fp = os.path.join(pdir, csv_file)
            if os.path.exists(fp):
                rows = load_csv(fp)
                values = [v for v in (parse_float(r.get(field)) for r in rows)
                          if v is not None and v > 0]
                if values:
                    s = compute_stats(values)
                    print(f"  {pname:<30} {s['mean']:>8.2f} ± {s['ci_95']:.2f} {unit} "
                          f"(σ={s['std']:.2f}, n={s['n']})")
                else:
                    print(f"  {pname:<30} N/A (no valid data)")
            else:
                print(f"  {pname:<30} [file not found]")
        print(f"  {'─' * 65}")

    # --- Network latency comparison ---
    print(f"\n  TABLE: Network Latency (Bridge vs Host RTT)")
    print(f"  {'─' * 65}")
    for pdir in platform_dirs:
        pname = os.path.basename(pdir)
        fp = os.path.join(pdir, "08-network-latency.csv")
        if os.path.exists(fp):
            rows = load_csv(fp)
            bridge = [v for r in rows if r.get('mode') == 'bridge'
                      for v in [parse_float(r.get('avg_rtt_ms'))] if v and v > 0]
            host = [v for r in rows if r.get('mode') == 'host'
                    for v in [parse_float(r.get('avg_rtt_ms'))] if v and v > 0]
            if bridge and host:
                sb = compute_stats(bridge)
                sh = compute_stats(host)
                print(f"  {pname:<30} bridge={sb['mean']:.2f}ms  host={sh['mean']:.2f}ms  "
                      f"overhead={sb['mean'] - sh['mean']:.2f}ms")
            else:
                print(f"  {pname:<30} N/A")
    print(f"  {'─' * 65}")

    # --- Memory comparison ---
    print(f"\n  TABLE: Memory (Per-container)")
    print(f"  {'─' * 65}")
    for pdir in platform_dirs:
        pname = os.path.basename(pdir)
        fp = os.path.join(pdir, "09-memory-efficiency.csv")
        if os.path.exists(fp):
            rows = load_csv(fp)
            # Handle both v1/v2 (KB) and v3 (MB) formats
            vals = [v for r in rows
                    for v in [parse_float(r.get('per_container_mem_mb')) or
                              parse_float(r.get('per_container_rss_kb'))]
                    if v is not None and v > 0]
            if vals:
                s = compute_stats(vals)
                # Detect unit from column name
                sample_row = rows[0] if rows else {}
                unit = "MB" if 'per_container_mem_mb' in sample_row else "KB"
                print(f"  {pname:<30} {s['mean']:>8.2f} ± {s['ci_95']:.2f} {unit}/container")
            else:
                print(f"  {pname:<30} N/A")
    print(f"  {'─' * 65}")


def generate_latex_table(platform_dirs):
    """Generate LaTeX table for direct insertion into paper."""
    print_header("LATEX TABLE (copy into paper)")

    print(r"""
\begin{table}[h]
\centering
\caption{Container startup latency across three infrastructure tiers (warm start).
Values: mean $\pm$ 95\% CI with standard deviation ($\sigma$).
All measurements in milliseconds. n=50 iterations per configuration.}
\label{tab:startup-latency}
\begin{tabular}{llccccc}
\toprule
\textbf{Platform} & \textbf{Image} & \textbf{Mean (ms)} & \textbf{$\sigma$} & \textbf{95\% CI} & \textbf{n} \\
\midrule""")

    for pdir in platform_dirs:
        platform_name = os.path.basename(pdir).replace('-', ' ').replace('_', ' ').title()
        filepath = os.path.join(pdir, "01-startup-latency.csv")
        if not os.path.exists(filepath):
            continue

        rows = load_csv(filepath)
        groups = defaultdict(list)
        for row in rows:
            if row.get('mode') == 'warm':
                val = parse_float(row.get('startup_ms'))
                if val is not None:
                    groups[row['image']].append(val)

        first = True
        for image in sorted(groups.keys()):
            s = compute_stats(groups[image])
            if s:
                pname = platform_name if first else ""
                first = False
                print(f"{pname} & {image} & {s['mean']:.1f} & {s['std']:.1f} & "
                      f"[{s['ci_lower']:.1f}, {s['ci_upper']:.1f}] & {s['n']} \\\\")
        print(r"\midrule")

    print(r"""\bottomrule
\end{tabular}
\end{table}""")


# =============================================================================
# MAIN
# =============================================================================

def main():
    if len(sys.argv) < 2:
        print("Docker Performance Statistical Analysis v3")
        print("=" * 50)
        print()
        print("Usage:")
        print("  Single platform:   python3 analyze_results.py results/azure-premium-ssd")
        print("  Compare platforms: python3 analyze_results.py --compare results/p1 results/p2 ...")
        print()
        print("Output can be saved: python3 analyze_results.py results/p1 | tee analysis.txt")
        sys.exit(1)

    if sys.argv[1] == '--compare':
        platform_dirs = sys.argv[2:]
        if len(platform_dirs) < 2:
            print("Need at least 2 platform directories for comparison.")
            sys.exit(1)

        # First show individual platform summaries
        for pdir in platform_dirs:
            print(f"\n{'#' * 70}")
            print(f"# Platform: {os.path.basename(pdir)}")
            print(f"{'#' * 70}")
            analyze_startup_latency(pdir)
            analyze_copyup(pdir)
            analyze_cpu_throttling(pdir)
            analyze_write_performance(pdir)
            analyze_metadata(pdir)
            analyze_pull_time(pdir)
            analyze_namespace_overhead(pdir)
            analyze_network_latency(pdir)
            analyze_memory_efficiency(pdir)

        # Then cross-platform comparison
        cross_platform_comparison(platform_dirs)
        generate_latex_table(platform_dirs)

    else:
        results_dir = sys.argv[1]
        if not os.path.isdir(results_dir):
            print(f"Error: '{results_dir}' is not a directory")
            sys.exit(1)

        print(f"Analyzing: {results_dir}")
        print(f"Platform:  {os.path.basename(results_dir)}")

        analyze_startup_latency(results_dir)
        analyze_copyup(results_dir)
        analyze_cpu_throttling(results_dir)
        analyze_write_performance(results_dir)
        analyze_metadata(results_dir)
        analyze_pull_time(results_dir)
        analyze_namespace_overhead(results_dir)
        analyze_network_latency(results_dir)
        analyze_memory_efficiency(results_dir)

        print_header("ANALYSIS COMPLETE")
        csv_count = len([f for f in os.listdir(results_dir) if f.endswith('.csv')])
        print(f"  Results directory: {results_dir}")
        print(f"  CSV files analyzed: {csv_count}")
        print(f"  Scipy available: {'YES' if HAS_SCIPY else 'NO'}")
        print()
        print(f"  Save output: python3 analyze_results.py {results_dir} | tee {results_dir}/analysis.txt")
        print(f"  Compare:     python3 analyze_results.py --compare results/p1 results/p2 results/p3")
        print()


if __name__ == '__main__':
    main()