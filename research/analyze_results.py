#!/usr/bin/env python3
"""
Docker Performance Statistical Analysis (Complete — All 10 Tests)
=================================================================
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
    values = [v for v in values if v is not None and str(v) != 'N/A']
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

    if n >= 30:
        ci_95 = 1.96 * std / math.sqrt(n)
    else:
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
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_stats_table(label, stats_dict):
    print(f"\n  {label}")
    print(f"  {'─' * 60}")
    print(f"  {'Metric':<20} {'Value':>12}")
    print(f"  {'─' * 60}")
    print(f"  {'n (samples)':<20} {stats_dict['n']:>12}")
    print(f"  {'Mean':<20} {stats_dict['mean']:>12.2f}")
    print(f"  {'Median':<20} {stats_dict['median']:>12.2f}")
    print(f"  {'Std Dev (σ)':<20} {stats_dict['std']:>12.2f}")
    print(f"  {'95% CI':<20} {'±':>6}{stats_dict['ci_95']:>6.2f}")
    print(f"  {'95% CI range':<20} [{stats_dict['ci_lower']:.2f}, {stats_dict['ci_upper']:.2f}]")
    print(f"  {'Min':<20} {stats_dict['min']:>12.2f}")
    print(f"  {'Max':<20} {stats_dict['max']:>12.2f}")


# =============================================================================
# TEST ANALYZERS
# =============================================================================

def analyze_startup_latency(results_dir):
    """Test 1: Container startup latency."""
    filepath = os.path.join(results_dir, "01-startup-latency.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 01-startup-latency.csv not found")
        return {}

    rows = load_csv(filepath)
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
        label = f"{image} ({mode} start) — ms"
        s = compute_stats(values)
        if s:
            print_stats_table(label, s)
            all_stats[f"{image}_{mode}"] = s

    return all_stats


def analyze_copyup(results_dir):
    """Test 2: Copy-up overhead."""
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

    print_header("TEST 2: Copy-up Overhead (100MB file) — ms")

    s = compute_stats(values)
    if s:
        print_stats_table("Copy-up latency", s)
        return {'copyup_100mb': s}
    return {}


def analyze_cpu_throttling(results_dir):
    """Test 3: CPU throttling accuracy."""
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
    """Test 4: Sequential write performance."""
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
            print_stats_table(f"{mode} — MB/s", s)
            all_stats[mode] = s

    if 'overlayfs' in all_stats and 'volume' in all_stats:
        ratio = all_stats['overlayfs']['mean'] / all_stats['volume']['mean'] if all_stats['volume']['mean'] > 0 else 0
        print(f"\n  OverlayFS / Volume ratio: {ratio:.2f}×")

    return all_stats


def analyze_metadata(results_dir):
    """Test 5: Metadata operations."""
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

    print_header("TEST 5: Metadata Operations (500 file creation) — ms")

    all_stats = {}
    for mode, values in sorted(groups.items()):
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
    """Test 6: Image pull time."""
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

    print_header("TEST 6: Image Pull Time — ms")

    all_stats = {}
    for image, values in sorted(groups.items()):
        s = compute_stats(values)
        if s:
            print_stats_table(image, s)
            all_stats[image] = s

    return all_stats


def analyze_namespace_overhead(results_dir):
    """Test 7: Namespace creation overhead."""
    filepath = os.path.join(results_dir, "07-namespace-overhead.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 07-namespace-overhead.csv not found")
        return {}

    rows = load_csv(filepath)
    values = []
    for row in rows:
        try:
            val = row.get('duration_ms', 'N/A')
            if val != 'N/A':
                values.append(float(val))
        except (ValueError, KeyError):
            pass

    if not values:
        print_header("TEST 7: Namespace Creation Overhead")
        print("  Skipped on this platform (expected on macOS)")
        return {}

    print_header("TEST 7: Namespace Creation Overhead — ms")

    s = compute_stats(values)
    if s:
        print_stats_table("Namespace creation (unshare)", s)
        return {'namespace_create': s}
    return {}


def analyze_network_latency(results_dir):
    """Test 8: Network latency (bridge vs host)."""
    filepath = os.path.join(results_dir, "08-network-latency.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 08-network-latency.csv not found")
        return {}

    rows = load_csv(filepath)
    groups = defaultdict(list)
    for row in rows:
        try:
            val = float(row['avg_rtt_ms'])
            if val > 0:
                groups[row['mode']].append(val)
        except (ValueError, KeyError):
            pass

    print_header("TEST 8: Network Latency — Bridge vs Host (avg RTT ms)")

    all_stats = {}
    for mode, values in sorted(groups.items()):
        s = compute_stats(values)
        if s:
            print_stats_table(f"{mode} mode (avg RTT ms)", s)
            all_stats[mode] = s

    if 'bridge' in groups and 'host' in groups:
        bridge_mean = compute_stats(groups['bridge'])['mean']
        host_mean = compute_stats(groups['host'])['mean']
        overhead = bridge_mean - host_mean
        print(f"\n  Bridge overhead vs host: {overhead:.2f} ms")

        if HAS_SCIPY:
            result = mann_whitney_u(groups['bridge'], groups['host'])
            if result:
                sig = "YES" if result['significant'] else "NO"
                print(f"  Significant difference: {sig} (p={result['p_value']:.6f})")

    return all_stats


def analyze_memory_efficiency(results_dir):
    """Test 9: Memory page cache sharing efficiency."""
    filepath = os.path.join(results_dir, "09-memory-efficiency.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] 09-memory-efficiency.csv not found")
        return {}

    rows = load_csv(filepath)
    per_container = []
    totals = []
    for row in rows:
        try:
            per_container.append(float(row['per_container_rss_kb']))
            totals.append(float(row['total_rss_kb']))
        except (ValueError, KeyError):
            pass

    print_header("TEST 9: Memory Efficiency — Page Cache Sharing (3× nginx)")

    all_stats = {}
    s_per = compute_stats(per_container)
    s_total = compute_stats(totals)

    if s_per:
        print_stats_table("Per-container RSS (KB)", s_per)
        all_stats['per_container_rss_kb'] = s_per
    if s_total:
        print_stats_table("Total RSS for 3 containers (KB)", s_total)
        all_stats['total_rss_kb'] = s_total

        if s_per:
            theoretical = s_per['mean'] * 3
            actual = s_total['mean']
            if theoretical > 0:
                sharing_pct = ((theoretical - actual) / theoretical) * 100
                print(f"\n  Page cache sharing efficiency: {sharing_pct:.1f}%")
                print(f"  (3× individual = {theoretical:.0f} KB vs actual {actual:.0f} KB)")

    return all_stats


# =============================================================================
# CROSS-PLATFORM COMPARISON
# =============================================================================

def cross_platform_comparison(platform_dirs):
    """Compare results across multiple platforms with significance tests."""
    print_header("CROSS-PLATFORM COMPARISON")

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

    # --- Per-image comparison ---
    for image_label in ['alpine', 'nginx', 'python_3.11-slim']:
        print(f"\n  TABLE: Warm Startup Latency ({image_label})")
        print(f"  {'─' * 70}")
        print(f"  {'Platform':<30} {'Mean (ms)':>10} {'σ':>8} {'95% CI':>14} {'n':>6}")
        print(f"  {'─' * 70}")

        image_data = {}
        for platform, groups in sorted(platform_data.items()):
            key = (image_label, 'warm')
            if key in groups:
                s = compute_stats(groups[key])
                image_data[platform] = groups[key]
                print(f"  {platform:<30} {s['mean']:>10.1f} {s['std']:>8.1f} "
                      f"[{s['ci_lower']:.1f}, {s['ci_upper']:.1f}] {s['n']:>6}")
        print(f"  {'─' * 70}")

        # Mann-Whitney U between all pairs
        if HAS_SCIPY and len(image_data) >= 2:
            print(f"\n  SIGNIFICANCE TESTS ({image_label})")
            platforms = sorted(image_data.keys())
            for i in range(len(platforms)):
                for j in range(i + 1, len(platforms)):
                    p1, p2 = platforms[i], platforms[j]
                    result = mann_whitney_u(image_data[p1], image_data[p2])
                    if result:
                        sig = "YES ✓" if result['significant'] else "NO"
                        print(f"    {p1} vs {p2}: U={result['u_statistic']}, "
                              f"p={result['p_value']:.6f}, sig: {sig}, "
                              f"Cliff's δ={result['cliffs_delta']} ({result['effect_size']})")

    # --- Copy-up comparison ---
    print(f"\n\n  TABLE: Copy-up Overhead (100MB)")
    print(f"  {'─' * 50}")
    for pdir in platform_dirs:
        pname = os.path.basename(pdir)
        fp = os.path.join(pdir, "02-copyup-overhead.csv")
        if os.path.exists(fp):
            rows = load_csv(fp)
            values = [float(r['copyup_ms']) for r in rows if r.get('copyup_ms', '0') != '0']
            if values:
                s = compute_stats(values)
                print(f"  {pname:<30} {s['mean']:>8.1f} ± {s['ci_95']:.1f} ms")
    print(f"  {'─' * 50}")

    # --- CPU throttling comparison ---
    print(f"\n  TABLE: CPU Throttling Accuracy (target: 50%)")
    print(f"  {'─' * 55}")
    for pdir in platform_dirs:
        pname = os.path.basename(pdir)
        fp = os.path.join(pdir, "03-cpu-throttling.csv")
        if os.path.exists(fp):
            rows = load_csv(fp)
            values = [float(r['measured_pct']) for r in rows if r.get('measured_pct')]
            if values:
                s = compute_stats(values)
                variance = abs(s['mean'] - 50.0)
                print(f"  {pname:<30} {s['mean']:>7.2f}% (±{s['ci_95']:.2f}%) "
                      f"variance: {variance:.2f}%")
    print(f"  {'─' * 55}")


def generate_latex_table(platform_dirs):
    """Generate LaTeX table ready for paper."""
    print_header("LATEX TABLE (copy into paper)")

    print(r"""
\begin{table}[h]
\centering
\caption{Container startup latency across three infrastructure tiers (warm start).
Values: mean $\pm$ 95\% CI with standard deviation ($\sigma$).}
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
                try:
                    groups[row['image']].append(float(row['startup_ms']))
                except (ValueError, KeyError):
                    pass

        first = True
        for image in sorted(groups.keys()):
            s = compute_stats(groups[image])
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
        print("Usage:")
        print("  Single platform:   python3 analyze_results.py results/azure-premium-ssd")
        print("  Compare platforms: python3 analyze_results.py --compare results/p1 results/p2 ...")
        sys.exit(1)

    if sys.argv[1] == '--compare':
        platform_dirs = sys.argv[2:]
        if len(platform_dirs) < 2:
            print("Need at least 2 platform directories for comparison.")
            sys.exit(1)

        for pdir in platform_dirs:
            print(f"\n{'#' * 70}")
            print(f"# Platform: {os.path.basename(pdir)}")
            print(f"{'#' * 70}")
            analyze_startup_latency(pdir)
            analyze_copyup(pdir)
            analyze_cpu_throttling(pdir)
            analyze_network_latency(pdir)
            analyze_memory_efficiency(pdir)

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
        analyze_namespace_overhead(results_dir)
        analyze_network_latency(results_dir)
        analyze_memory_efficiency(results_dir)

        print_header("ANALYSIS COMPLETE")
        print(f"  Results directory: {results_dir}")
        print(f"  Files analyzed: {len([f for f in os.listdir(results_dir) if f.endswith('.csv')])}")
        print(f"  To compare across platforms, re-run with --compare flag")
        print()


if __name__ == '__main__':
    main()