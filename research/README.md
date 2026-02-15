# Research: Decomposing Container Startup Performance

> Measurement data and analysis scripts supporting the paper:  
> **"Decomposing Container Startup Performance: A Three-Tier Measurement Study of Docker on Heterogeneous Infrastructure"**

## Overview

This directory contains the reproducible measurement framework and raw data
for a systematic study of Docker container performance across three
infrastructure tiers:

| Platform                | Storage          | Purpose                    |
|-------------------------|------------------|----------------------------|
| macOS Docker Desktop    | NVMe SSD (APFS)  | Development baseline       |
| Azure Premium SSD       | Managed P10 SSD   | Production-optimized       |
| Azure Standard HDD      | Managed HDD       | Production-budget          |

## Quick Start

### Run benchmarks (on each platform)

```bash
# Requires: Docker Engine, sudo access
# Estimated time: ~3.5 hours per platform
sudo bash statistical-benchmark.sh 50 <platform-label>

# Example:
sudo bash statistical-benchmark.sh 50 azure-premium-ssd
```

### Analyze results

```bash
# Requires: Python 3.8+, scipy (optional, for significance tests)
pip install scipy

# Single platform
python3 analyze_results.py results/azure-premium-ssd

# Cross-platform comparison
python3 analyze_results.py --compare \
    results/azure-premium-ssd \
    results/azure-standard-hdd \
    results/macos-docker-desktop
```

## Measurements

The benchmark script measures 7 dimensions, each with 50 iterations
(except pull time: 10 iterations):

| # | Test                    | Output CSV                    | Key Metric                |
|---|-------------------------|-------------------------------|---------------------------|
| 1 | Container startup       | 01-startup-latency.csv        | Warm/cold start time (ms) |
| 2 | Copy-up overhead        | 02-copyup-overhead.csv        | 100MB copy-up time (ms)   |
| 3 | CPU throttling          | 03-cpu-throttling.csv         | Accuracy vs 50% target    |
| 4 | Sequential writes       | 04-write-performance.csv      | OverlayFS vs volume MB/s  |
| 5 | Metadata operations     | 05-metadata-operations.csv    | 500-file creation time    |
| 6 | Image pull time         | 06-image-pull-time.csv        | Cold pull latency (ms)    |
| 7 | Namespace overhead      | 07-namespace-overhead.csv     | Isolation primitive cost   |

## Statistical Methods

- **Sample size:** 50 iterations per test (30+ required for Z-distribution CI)
- **Reported metrics:** Mean (μ), standard deviation (σ), 95% confidence interval
- **Significance testing:** Mann-Whitney U test (non-parametric, α = 0.05)
- **Effect size:** Cliff's delta (d)
- **Cache control:** `sync && echo 3 > /proc/sys/vm/drop_caches` between cold-start iterations

## Platform Specifications

Controlled variables across Azure VMs:
- VM Size: Standard_D2s_v3 (2 vCPU, 8GB RAM)
- Docker Engine: 29.1.3
- Kernel: 6.8.0-1044-azure (Ubuntu 22.04)
- Container images: alpine:latest, nginx:latest, python:3.11-slim

## Reproducing Our Results

1. Provision infrastructure matching the specifications above
2. Clone this repository
3. Run `statistical-benchmark.sh` on each platform
4. Run `analyze_results.py --compare` to generate comparison tables
5. Raw CSV data enables independent verification of all reported statistics

## Citation

If you use this data or methodology, please cite:

```bibtex
@article{khan2025docker,
  title={Decomposing Container Startup Performance: A Three-Tier 
         Measurement Study of Docker on Heterogeneous Infrastructure},
  author={Khan, Shamsher},
  year={2025},
  note={Preprint}
}
```

## Author

**Shamsher Khan**  
Senior DevOps Engineer, GlobalLogic (Hitachi Group)  
IEEE Senior Member  
GitHub: [@opscart](https://github.com/opscart)