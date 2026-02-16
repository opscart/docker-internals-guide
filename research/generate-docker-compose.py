#!/usr/bin/env python3
"""
Generate publication-quality figures for Docker performance paper.
Run this in the research/ directory where results/ folders exist.

Usage:
    pip3 install matplotlib numpy scipy
    python3 generate_figures.py

Output: figures/ directory with PNG files for the paper.

Author: Shamsher Khan
"""

import os
import csv
import numpy as np
from collections import defaultdict

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
except ImportError:
    print("Install matplotlib: pip3 install matplotlib")
    exit(1)

# --- Config ---
PLATFORMS = {
    'azure-premium-ssd': {'label': 'Azure Premium SSD', 'color': '#2196F3', 'short': 'Premium SSD'},
    'azure-standard-hdd': {'label': 'Azure Standard HDD', 'color': '#FF9800', 'short': 'Standard HDD'},
    'macos-docker-desktop': {'label': 'macOS Docker Desktop', 'color': '#4CAF50', 'short': 'macOS DD'},
}
RESULTS_BASE = 'results'
FIGURES_DIR = 'figures'
os.makedirs(FIGURES_DIR, exist_ok=True)

plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 11,
    'axes.titlesize': 13,
    'axes.labelsize': 12,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 10,
    'figure.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.1,
})


def load_csv(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, 'r') as f:
        return list(csv.DictReader(f))


def parse_float(val):
    if val is None:
        return None
    val = str(val).strip()
    for suffix in [' ms', 'ms', ' MB/s', 'MB/s', ' MB', 'MB', ' KB', 'KB', '%']:
        if val.endswith(suffix):
            val = val[:-len(suffix)].strip()
    try:
        return float(val)
    except ValueError:
        return None


def get_values(platform, csv_file, field, mode_filter=None, mode_field='mode'):
    fp = os.path.join(RESULTS_BASE, platform, csv_file)
    rows = load_csv(fp)
    vals = []
    for r in rows:
        if mode_filter and r.get(mode_field) != mode_filter:
            continue
        v = parse_float(r.get(field))
        if v is not None:
            vals.append(v)
    return vals


# =========================================================================
# FIGURE 1: Warm Startup Latency Comparison (grouped bar chart)
# =========================================================================
def fig1_startup_comparison():
    images = ['alpine', 'nginx', 'python_3.11-slim']
    image_labels = ['alpine\n(5 MB)', 'nginx\n(67 MB)', 'python:3.11-slim\n(155 MB)']

    fig, ax = plt.subplots(figsize=(10, 5.5))

    x = np.arange(len(images))
    width = 0.25
    offsets = [-width, 0, width]

    for idx, (platform, cfg) in enumerate(PLATFORMS.items()):
        means, cis = [], []
        for img in images:
            vals = get_values(platform, '01-startup-latency.csv', 'startup_ms',
                              mode_filter='warm', mode_field='mode')
            # Filter by image
            fp = os.path.join(RESULTS_BASE, platform, '01-startup-latency.csv')
            rows = load_csv(fp)
            img_vals = [parse_float(r['startup_ms']) for r in rows
                        if r.get('image') == img and r.get('mode') == 'warm'
                        and parse_float(r.get('startup_ms')) is not None]

            if img_vals:
                m = np.mean(img_vals)
                ci = 1.96 * np.std(img_vals, ddof=1) / np.sqrt(len(img_vals))
                means.append(m)
                cis.append(ci)
            else:
                means.append(0)
                cis.append(0)

        bars = ax.bar(x + offsets[idx], means, width, yerr=cis,
                      label=cfg['short'], color=cfg['color'], alpha=0.85,
                      capsize=4, edgecolor='white', linewidth=0.5)

        # Add value labels on bars
        for bar, m in zip(bars, means):
            ax.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 30,
                    f'{m:.0f}', ha='center', va='bottom', fontsize=8, fontweight='bold')

    ax.set_xlabel('Container Image')
    ax.set_ylabel('Startup Latency (ms)')
    ax.set_title('Container Warm-Start Latency Across Infrastructure Tiers (n=50)')
    ax.set_xticks(x)
    ax.set_xticklabels(image_labels)
    ax.legend(loc='upper left')
    ax.grid(axis='y', alpha=0.3)
    ax.set_ylim(0, max(2200, ax.get_ylim()[1]))

    plt.savefig(os.path.join(FIGURES_DIR, 'fig1-startup-latency.png'))
    plt.savefig(os.path.join(FIGURES_DIR, 'fig1-startup-latency.pdf'))
    plt.close()
    print("  Generated: fig1-startup-latency.png")


# =========================================================================
# FIGURE 2: Startup Variance Box Plot
# =========================================================================
def fig2_startup_variance():
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.5), sharey=True)

    for idx, (platform, cfg) in enumerate(PLATFORMS.items()):
        fp = os.path.join(RESULTS_BASE, platform, '01-startup-latency.csv')
        rows = load_csv(fp)

        data = []
        labels = []
        for img, lbl in [('alpine', 'alpine'), ('nginx', 'nginx'), ('python_3.11-slim', 'python')]:
            vals = [parse_float(r['startup_ms']) for r in rows
                    if r.get('image') == img and r.get('mode') == 'warm'
                    and parse_float(r.get('startup_ms')) is not None]
            if vals:
                data.append(vals)
                labels.append(lbl)

        if data:
            bp = axes[idx].boxplot(data, labels=labels, patch_artist=True,
                                    medianprops=dict(color='black', linewidth=1.5))
            for patch in bp['boxes']:
                patch.set_facecolor(cfg['color'])
                patch.set_alpha(0.6)

        axes[idx].set_title(cfg['short'])
        axes[idx].grid(axis='y', alpha=0.3)
        if idx == 0:
            axes[idx].set_ylabel('Startup Latency (ms)')

    fig.suptitle('Startup Latency Distribution by Platform (Warm Start, n=50)', fontsize=13)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'fig2-startup-variance.png'))
    plt.savefig(os.path.join(FIGURES_DIR, 'fig2-startup-variance.pdf'))
    plt.close()
    print("  Generated: fig2-startup-variance.png")


# =========================================================================
# FIGURE 3: CPU Throttling Accuracy
# =========================================================================
def fig3_cpu_throttling():
    fig, ax = plt.subplots(figsize=(8, 5))

    positions = []
    data = []
    colors = []
    labels = []

    for idx, (platform, cfg) in enumerate(PLATFORMS.items()):
        vals = get_values(platform, '03-cpu-throttling.csv', 'measured_pct')
        if vals:
            data.append(vals)
            positions.append(idx)
            colors.append(cfg['color'])
            labels.append(cfg['short'])

    if data:
        bp = ax.boxplot(data, positions=range(len(data)), patch_artist=True,
                        medianprops=dict(color='black', linewidth=1.5),
                        widths=0.6)
        for patch, color in zip(bp['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)

        ax.axhline(y=50, color='red', linestyle='--', linewidth=1.5, label='Target (50%)')
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels)

    ax.set_ylabel('Measured CPU Utilization (%)')
    ax.set_title('CPU Throttling Accuracy: --cpus=0.5 (target: 50%, n=50)')
    ax.legend(loc='upper right')
    ax.grid(axis='y', alpha=0.3)

    plt.savefig(os.path.join(FIGURES_DIR, 'fig3-cpu-throttling.png'))
    plt.savefig(os.path.join(FIGURES_DIR, 'fig3-cpu-throttling.pdf'))
    plt.close()
    print("  Generated: fig3-cpu-throttling.png")


# =========================================================================
# FIGURE 4: Write Performance (OverlayFS vs Volume)
# =========================================================================
def fig4_write_performance():
    fig, ax = plt.subplots(figsize=(9, 5))

    x = np.arange(len(PLATFORMS))
    width = 0.35

    overlay_means, overlay_cis = [], []
    vol_means, vol_cis = [], []
    plat_labels = []

    for platform, cfg in PLATFORMS.items():
        plat_labels.append(cfg['short'])

        ov = get_values(platform, '04-write-performance.csv', 'write_speed_mbps',
                        mode_filter='overlayfs')
        vo = get_values(platform, '04-write-performance.csv', 'write_speed_mbps',
                        mode_filter='volume')

        # Use median for skewed distributions
        if ov:
            overlay_means.append(np.median(ov))
            overlay_cis.append(np.std(ov, ddof=1) / np.sqrt(len(ov)) * 1.96)
        else:
            overlay_means.append(0)
            overlay_cis.append(0)

        if vo:
            vol_means.append(np.median(vo))
            vol_cis.append(np.std(vo, ddof=1) / np.sqrt(len(vo)) * 1.96)
        else:
            vol_means.append(0)
            vol_cis.append(0)

    ax.bar(x - width / 2, overlay_means, width, yerr=overlay_cis,
           label='OverlayFS', color='#e74c3c', alpha=0.85, capsize=4)
    ax.bar(x + width / 2, vol_means, width, yerr=vol_cis,
           label='Volume Mount', color='#2ecc71', alpha=0.85, capsize=4)

    ax.set_ylabel('Write Speed — Median (MB/s)')
    ax.set_title('Sequential Write Performance: OverlayFS vs Volume (256MB, n=50)')
    ax.set_xticks(x)
    ax.set_xticklabels(plat_labels)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    plt.savefig(os.path.join(FIGURES_DIR, 'fig4-write-performance.png'))
    plt.savefig(os.path.join(FIGURES_DIR, 'fig4-write-performance.pdf'))
    plt.close()
    print("  Generated: fig4-write-performance.png")


# =========================================================================
# FIGURE 5: Network Latency (Bridge vs Host)
# =========================================================================
def fig5_network_latency():
    fig, ax = plt.subplots(figsize=(9, 5))

    x = np.arange(len(PLATFORMS))
    width = 0.35

    bridge_means, host_means = [], []
    plat_labels = []

    for platform, cfg in PLATFORMS.items():
        plat_labels.append(cfg['short'])
        br = get_values(platform, '08-network-latency.csv', 'avg_rtt_ms',
                        mode_filter='bridge')
        ho = get_values(platform, '08-network-latency.csv', 'avg_rtt_ms',
                        mode_filter='host')
        br = [v for v in br if v > 0]
        ho = [v for v in ho if v > 0]
        bridge_means.append(np.mean(br) if br else 0)
        host_means.append(np.mean(ho) if ho else 0)

    ax.bar(x - width / 2, bridge_means, width, label='Bridge', color='#3498db', alpha=0.85)
    ax.bar(x + width / 2, host_means, width, label='Host', color='#e67e22', alpha=0.85)

    ax.set_ylabel('Average RTT (ms)')
    ax.set_title('Network Latency: Bridge vs Host Mode (5 pings × 50 iterations)')
    ax.set_xticks(x)
    ax.set_xticklabels(plat_labels)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    plt.savefig(os.path.join(FIGURES_DIR, 'fig5-network-latency.png'))
    plt.savefig(os.path.join(FIGURES_DIR, 'fig5-network-latency.pdf'))
    plt.close()
    print("  Generated: fig5-network-latency.png")


# =========================================================================
# FIGURE 6: Pull Time by Image Size
# =========================================================================
def fig6_pull_time():
    fig, ax = plt.subplots(figsize=(9, 5))

    images = ['alpine', 'nginx', 'python_3.11-slim']
    image_labels = ['alpine (5 MB)', 'nginx (67 MB)', 'python:3.11-slim (155 MB)']
    x = np.arange(len(images))
    width = 0.25
    offsets = [-width, 0, width]

    for idx, (platform, cfg) in enumerate(PLATFORMS.items()):
        fp = os.path.join(RESULTS_BASE, platform, '06-image-pull-time.csv')
        rows = load_csv(fp)
        means = []
        for img in images:
            vals = [parse_float(r['pull_time_ms']) for r in rows
                    if r.get('image') == img and parse_float(r.get('pull_time_ms')) is not None]
            means.append(np.mean(vals) / 1000 if vals else 0)  # Convert to seconds

        ax.bar(x + offsets[idx], means, width, label=cfg['short'],
               color=cfg['color'], alpha=0.85)

    ax.set_ylabel('Pull Time (seconds)')
    ax.set_title('Image Pull Time by Image Size (Cold Pull, n=10)')
    ax.set_xticks(x)
    ax.set_xticklabels(image_labels)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    plt.savefig(os.path.join(FIGURES_DIR, 'fig6-pull-time.png'))
    plt.savefig(os.path.join(FIGURES_DIR, 'fig6-pull-time.pdf'))
    plt.close()
    print("  Generated: fig6-pull-time.png")


# =========================================================================
# FIGURE 7: Overhead Decomposition (stacked bar)
# =========================================================================
def fig7_overhead_decomposition():
    fig, ax = plt.subplots(figsize=(8, 5))

    # Decompose startup into: namespace (~8ms) + remaining runtime
    # Values from the data
    platforms_data = {
        'Premium SSD': {'namespace': 7.94, 'remaining': 567.62 - 7.94, 'color': '#2196F3'},
        'Standard HDD': {'namespace': 8.45, 'remaining': 1157.49 - 8.45, 'color': '#FF9800'},
        'macOS DD': {'namespace': 8.0, 'remaining': 1528.09 - 8.0, 'color': '#4CAF50'},  # estimated
    }

    labels = list(platforms_data.keys())
    ns_vals = [d['namespace'] for d in platforms_data.values()]
    remain_vals = [d['remaining'] for d in platforms_data.values()]

    x = np.arange(len(labels))
    ax.bar(x, ns_vals, 0.5, label='Namespace Creation', color='#e74c3c', alpha=0.85)
    ax.bar(x, remain_vals, 0.5, bottom=ns_vals, label='Runtime Overhead\n(cgroup, OverlayFS, exec)',
           color='#3498db', alpha=0.7)

    # Annotate namespace percentage
    for i, (ns, total) in enumerate(zip(ns_vals, [v + ns_vals[i] for i, v in enumerate(remain_vals)])):
        pct = ns / total * 100
        ax.text(i, ns / 2, f'{ns:.1f}ms\n({pct:.1f}%)', ha='center', va='center',
                fontsize=9, fontweight='bold', color='white')

    ax.set_ylabel('Time (ms)')
    ax.set_title('Container Startup Decomposition (alpine, warm start)')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend(loc='upper left')
    ax.grid(axis='y', alpha=0.3)

    plt.savefig(os.path.join(FIGURES_DIR, 'fig7-overhead-decomposition.png'))
    plt.savefig(os.path.join(FIGURES_DIR, 'fig7-overhead-decomposition.pdf'))
    plt.close()
    print("  Generated: fig7-overhead-decomposition.png")


# =========================================================================
# MAIN
# =========================================================================
if __name__ == '__main__':
    print("Generating figures...")
    print()

    available = [p for p in PLATFORMS if os.path.isdir(os.path.join(RESULTS_BASE, p))]
    if not available:
        print(f"ERROR: No platform directories found in {RESULTS_BASE}/")
        print(f"Expected: {list(PLATFORMS.keys())}")
        exit(1)

    print(f"Found platforms: {available}")
    print()

    fig1_startup_comparison()
    fig2_startup_variance()
    fig3_cpu_throttling()
    fig4_write_performance()
    fig5_network_latency()
    fig6_pull_time()
    fig7_overhead_decomposition()

    print()
    print(f"All figures saved to {FIGURES_DIR}/")
    print("Both PNG (for review) and PDF (for LaTeX) formats generated.")