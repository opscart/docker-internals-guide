# Docker Internals Guide

> An educational toolkit for understanding Docker's kernel-level behavior through systematic measurement and analysis.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-29.1-blue.svg)](https://www.docker.com/)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS-lightgrey.svg)](https://github.com/opscart/docker-internals-guide)

---

## 📖 What This Is

An educational toolkit that demonstrates how Linux kernel primitives (namespaces, cgroups, OverlayFS) shape container performance, security, and operational characteristics through reproducible experiments.

**This is NOT:**
- A production monitoring tool (use Prometheus/Datadog for that)
- A storage benchmark suite (use fio/sysbench for that)
- A security scanner (use trivy/grype for that)

**This IS:**
- A learning tool for understanding Docker internals
- A reference implementation for measuring kernel behavior
- A baseline for comparing your own infrastructure
- A companion to the research article (see below)

**Related Article:** *Understanding Docker Performance Across Platforms: From Development to Cloud Infrastructure*  
> Technical analysis based on three-platform testing (macOS, Azure Premium SSD, Azure Standard HDD)  
> Published on InfoQ - [Read Article](#) (Coming January 2025)

---

## 🚀 Quick Start

### Prerequisites
- Docker Engine 20.10+ (tested on 28.4 and 29.1)
- Linux (Ubuntu 22.04+) or macOS with Docker Desktop
- Root/sudo access for system inspection
- Optional: strace, perf, bpftrace for advanced tracing

### Run the Analysis Toolkit
```bash
git clone https://github.com/opscart/docker-internals-guide.git
cd docker-internals-guide/toolkit
chmod +x docker-analysis-toolkit.sh
sudo ./docker-analysis-toolkit.sh
```

**Execution time:** ~2-3 minutes  
**Output:** Comprehensive report covering 10 dimensions of container behavior

---

## 📊 What Gets Measured

### Performance Characteristics
- **Container startup latency** - Decomposed into pull, runtime, and kernel operations
- **OverlayFS behavior** - Layer structure, copy-up overhead, metadata operations
- **I/O patterns** - Sequential writes, volume vs OverlayFS comparison
- **CPU isolation** - Throttling accuracy and cgroup enforcement
- **Network modes** - Bridge vs host mode connectivity
- **Memory efficiency** - Page cache sharing across containers

### Security Posture
- **Linux capabilities** - Default vs restricted capability sets
- **Privileged containers** - Detection of dangerous configurations
- **Docker socket exposure** - Root-equivalent access risks
- **Namespace isolation** - PID, network, mount namespace verification

---

## 📂 Repository Structure
```
docker-internals-guide/
├── toolkit/
│   ├── docker-analysis-toolkit.sh         # Main measurement script
│   └── examples/
│       ├── sample-output-macos.txt        # macOS Docker Desktop results
│       ├── sample-output-azure-premium.txt    # Azure Premium SSD results
│       └── sample-output-azure-standard.txt   # Azure Standard HDD results
├── security-configs/                      # Hardening guides (future article)
│   ├── docker-security-hardening.md
│   └── examples/
└── README.md
```

---

## 🔬 Sample Results

### Container Startup (from article research):

| Platform | Runtime Overhead | Copy-up (100MB) | CPU Throttling |
|----------|------------------|-----------------|----------------|
| **macOS Docker Desktop** | 303ms | 88ms | 50.32% (99.4% accurate) |
| **Azure Premium SSD** | 501ms | 64ms | 49.97% (99.9% accurate) |
| **Azure Standard HDD** | 837ms | 63ms | 50.17% (99.7% accurate) |

**Key insight:** Container startup varies 2.8x from development to production budget cloud, but copy-up overhead remains consistent (~60-90ms), and CPU throttling is deterministic across all platforms (<1% variance).

---

## 💡 Key Findings from Three-Platform Testing

### 1. **Runtime Overhead Decomposition**
- Kernel operations (namespace creation, cgroup setup): Single-digit milliseconds
- Storage operations (OverlayFS mount, disk I/O): 300-800ms (platform-dependent)
- Platform overhead (containerd shim, managed disk): 100-300ms in cloud

### 2. **Copy-up is Architecturally Consistent**
- 60-90ms for 100MB file across all platforms
- Proves it's an architectural operation with minimal storage dependency

### 3. **CPU Throttling is Truly Invariant**
- All platforms: 49.97% - 50.32% measured vs 50% target
- <1% variance proves kernel-level determinism

### 4. **Storage Tier Matters for I/O**
- OverlayFS writes: 140 MB/s (HDD) → 354 MB/s (Premium SSD) → 1.8 GB/s (macOS)
- Metadata operations: 2-5% overhead regardless of storage tier

---

## 🛠️ Installation

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y docker.io strace jq linux-tools-generic
```

**macOS:**
```bash
# Install Docker Desktop from docker.com
# Most tools (strace, perf) not available on macOS
# The script will skip unsupported tests automatically
```

---

## 🔐 Security Hardening Example
```bash
# Production-ready container configuration
docker run -d \
  --name secure-nginx \
  --cap-drop=ALL \
  --cap-add=NET_BIND_SERVICE \
  --read-only \
  --tmpfs /tmp \
  --tmpfs /var/run \
  --security-opt=no-new-privileges \
  --memory=512m \
  --cpus=0.5 \
  nginx:alpine
```

See `security-configs/` for comprehensive hardening guide (detailed article coming Q1 2025).

---

## 📚 Platform-Specific Notes

### macOS Docker Desktop
- Volume mount tests are skipped (APFS/LinuxKit compatibility issues)
- Some system inspection tests require Linux kernel features
- Results still valuable for development baseline measurements

### Linux (Native Docker)
- Full test suite supported
- Requires sudo/root for namespace and capability inspection
- Tested on Ubuntu 22.04 with kernel 6.8

### Cloud Platforms (Azure, AWS, GCP)
- Managed disk caching affects I/O results
- CPU steal time may add variance in shared tenancy
- Network-attached storage (EBS, Azure Disk) adds latency

---

## 🎯 Use Cases

**For Learning:**
- Understand how Docker primitives work under the hood
- See actual kernel behavior (namespaces, cgroups, OverlayFS)
- Compare your environment to research baselines

**For Infrastructure Decisions:**
- Quantify storage tier impact (Premium SSD vs Standard HDD)
- Understand when optimization matters vs when it doesn't
- Establish baseline performance for your platform

**For Security Auditing:**
- Identify privileged containers and Docker socket mounts
- Verify capability restrictions
- Check namespace isolation

---

## 🤝 Contributing

This is primarily a research repository accompanying published articles. If you find issues or have suggestions:

1. Open an issue describing the problem
2. Include your platform (OS, Docker version, kernel version)
3. Attach relevant output from the toolkit

Pull requests for bug fixes are welcome.

---

## 📜 License

MIT License - Free for personal and commercial use.

---

## 👤 Author

**Shamsher Khan**
- Senior DevOps Engineer | IEEE Senior Member
- GitHub: [@opscart](https://github.com/opscart)
- LinkedIn: [Shamsher Khan](https://linkedin.com/in/shamsher-khan)
- DZone: [@shamsherkhan](https://dzone.com/users/4855907/shamsherkhan.html)

---

## ⭐ If You Find This Useful

- Star this repository
- Share the accompanying article
- Reference in your own research or blog posts
- Provide feedback on what else you'd like to see measured

---

**Last Updated:** December 2024  
**Status:** Active - Article publication in progress  
**Next Update:** Post-publication with article links (January 2025)