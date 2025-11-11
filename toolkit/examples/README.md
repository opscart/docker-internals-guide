# Toolkit Output Examples

Example outputs from running the Docker Analysis Toolkit on different platforms.

---

## 📁 Files

### sample-output-linux-azure.txt
Complete output from **Ubuntu 22.04 on Azure VM** (250 lines)

- **All 10 tests:** ✅ Complete
- **Platform:** Azure Standard_DS1_v2 (2 vCPU, 4GB RAM)
- **Storage:** Standard HDD
- **Key metrics:** 629ms startup, 327 MB/s I/O, 99ms copy-up

### sample-output-macos.txt
Output from **macOS Docker Desktop 28.4.0** (~184 lines)

- **Tests:** 7/10 (strace, bpftrace, some metrics unavailable - expected)
- **Platform:** macOS with Docker Desktop
- **Key metrics:** 196ms startup (3x faster), 3.4 GB/s I/O (10x faster)

---

## 🔍 Quick Comparison

| Platform | Tests | Startup | I/O | Best For |
|----------|-------|---------|-----|----------|
| **Linux (Azure)** | 10/10 ✅ | 629ms | 327 MB/s | Production benchmarking |
| **macOS Desktop** | 7/10 ⚠️ | 196ms | 3.4 GB/s | Development |

**Key Finding:** macOS is 3x faster, but this is NOT production-representative.
Always benchmark on Linux for accurate cloud performance metrics.

---

## 💡 Which Output Should You Compare To?

### Use Linux Output When:
- Benchmarking for production deployment
- Need accurate cloud performance metrics
- Planning infrastructure capacity
- Optimizing for production workloads

### Use macOS Output When:
- Local development reference
- Quick sanity checks
- Learning the toolkit
- Security audit baseline
---

## 📊 Detailed Analysis

For comprehensive benchmark comparison with performance targets and optimization recommendations, see **[benchmark-results.md](benchmark-results.md)**.

---

## 🚀 Running Your Own Tests
```bash
# Clone and run:
git clone https://github.com/opscart/docker-internals-guide.git
cd docker-internals-guide/toolkit
sudo ./docker-analysis-toolkit.sh | tee my-output.txt

# Compare to baselines:
grep "Average startup" my-output.txt
# Your result vs 629ms (Linux) or 196ms (macOS)
```

---

## 🤝 Contributing

Tested on another platform? We'd love baseline results from:
- AWS EC2 (gp3 storage)
- Google Cloud (SSD persistent disk)
- Bare metal with NVMe
- Windows WSL2

Submit via PR with complete output!

---

**See [benchmark-results.md](benchmark-results.md) for detailed performance analysis.**