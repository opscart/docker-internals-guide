# Docker Analysis Toolkit

Automated performance benchmarking and security analysis for Docker containers.

## 🎯 What It Does

This toolkit runs 10 comprehensive tests to analyze your Docker environment:

1. **Container Startup Latency** - Measures cold and warm start times
2. **Syscall Tracing** - Analyzes namespace creation (requires strace)
3. **OverlayFS Layer Inspection** - Examines image layer structure
4. **I/O Performance** - Tests write speed and copy-up overhead
5. **Network Performance** - Compares bridge vs host mode latency
6. **Memory Efficiency** - Analyzes page cache sharing
7. **Security Posture** - Audits capabilities, privileged containers, socket exposure
8. **CPU Performance** - Detects throttling and cgroup limits
9. **Namespace Isolation** - Verifies PID and network isolation
10. **eBPF Tracing** - Advanced syscall monitoring (optional, requires bpftrace)

## 🚀 Quick Start

```bash
cd toolkit
chmod +x docker-analysis-toolkit.sh
sudo ./docker-analysis-toolkit.sh
```

**Expected runtime:** 2-5 minutes depending on system

## 📋 Requirements

### Minimum
- Docker 20.10+
- Bash 4.0+
- Linux or macOS
- Root/sudo access

### Recommended
- strace (for syscall analysis)
- jq (for JSON parsing)
- perf (for CPU profiling)
- bpftrace (for eBPF tracing)

### Installing Dependencies

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y docker.io strace jq linux-tools-generic
```

**RHEL/CentOS/Fedora:**
```bash
sudo dnf install -y docker strace jq perf
sudo systemctl start docker
```

**macOS:**
```bash
brew install jq
# Note: strace not available on macOS
# Some tests will be skipped
```

## 📊 Understanding the Output

### Test 1: Container Startup Latency

```
Cold start (with pull): 847ms    ← First run, downloads image
Warm start (cached): 142ms        ← Subsequent runs, uses cache
Average startup time: 138ms       ← Average of 10 runs
```

**Good:** <150ms  
**Acceptable:** 150-300ms  
**Needs optimization:** >300ms

**If slow, check:**
- Image layer count (use multi-stage builds)
- Storage driver (overlay2 recommended)
- Disk I/O (use SSD if possible)

### Test 4: I/O Performance

```
Sequential write: 387 MB/s       ← Raw write performance
Copy-up operation time: 234ms    ← OverlayFS overhead
```

**Copy-up happens when:**
- Container modifies a file from the image
- Entire file is copied to upper layer
- Only occurs on first write to that file

**Optimization:**
- Use volumes for write-heavy workloads
- Minimize image file modifications
- Keep writable data in dedicated volumes

### Test 7: Security Posture

```
Default capabilities: 14 detected
✓ No privileged containers
✗ WARNING: Docker socket mounted
```

**Critical issues:**
- Privileged containers (--privileged)
- Docker socket mounted (-v /var/run/docker.sock)
- Excessive capabilities

**Fix by:**
- Dropping all capabilities: `--cap-drop=ALL`
- Adding only needed: `--cap-add=NET_BIND_SERVICE`
- Removing socket mounts

## 🔧 Usage Examples

### Run Full Suite

```bash
sudo ./docker-analysis-toolkit.sh
```

### Run With Custom Options (Future)

```bash
# Run only performance tests
./docker-analysis-toolkit.sh --tests=performance

# Skip tests requiring strace
./docker-analysis-toolkit.sh --skip-syscall

# Output to JSON
./docker-analysis-toolkit.sh --json > results.json
```

### Automated Testing

```bash
# Run daily and log results
cat > /etc/cron.daily/docker-audit << 'EOF'
#!/bin/bash
cd /opt/docker-internals-guide/toolkit
./docker-analysis-toolkit.sh >> /var/log/docker-audit.log 2>&1
EOF

chmod +x /etc/cron.daily/docker-audit
```

## 📈 Benchmarking

### Establish Baseline

Run multiple times to establish baseline:

```bash
for i in {1..5}; do
  echo "=== Run $i ===" | tee -a baseline.log
  sudo ./docker-analysis-toolkit.sh 2>&1 | tee -a baseline.log
  sleep 10
done

# Extract averages
grep "Average startup" baseline.log | awk '{print $4}'
```

### Compare Environments

```bash
# Production environment
ssh prod-server 'cd /opt/toolkit && sudo ./docker-analysis-toolkit.sh' > prod-results.txt

# Staging environment  
ssh staging-server 'cd /opt/toolkit && sudo ./docker-analysis-toolkit.sh' > staging-results.txt

# Compare
diff -y prod-results.txt staging-results.txt
```

## 🐛 Troubleshooting

### Permission Denied

```
Error: permission denied while trying to connect to Docker daemon
```

**Solution:**
```bash
# Option 1: Run with sudo
sudo ./docker-analysis-toolkit.sh

# Option 2: Add user to docker group (less secure)
sudo usermod -aG docker $USER
newgrp docker
```

### Docker Daemon Not Running

```
Error: Cannot connect to Docker daemon
```

**Solution:**
```bash
# Start Docker
sudo systemctl start docker

# Enable on boot
sudo systemctl enable docker
```

### Strace Not Found

```
Warning: strace not found (optional for syscall tracing)
```

**Solution:**
```bash
sudo apt-get install strace  # Ubuntu/Debian
sudo dnf install strace      # RHEL/Fedora
```

Test will be skipped if strace is missing (non-critical).

### OverlayFS Path Not Found

```
Warning: Cannot find overlay storage
```

**Possible causes:**
- Different storage driver (devicemapper, btrfs, zfs)
- Docker Desktop on macOS/Windows (different paths)
- Custom Docker configuration

**Check storage driver:**
```bash
docker info | grep "Storage Driver"
```

### Tests Failing on macOS

Some tests are Linux-specific:
- Syscall tracing (no strace on macOS)
- Direct cgroup inspection
- eBPF monitoring

**This is expected.** Toolkit will skip these tests automatically.

## 📝 Output Files

### Logs

Toolkit creates logs in `/tmp/`:
- `/tmp/docker-syscall-trace.log` - Syscall trace output
- Test results are printed to stdout

### Saving Results

```bash
# Save to file
sudo ./docker-analysis-toolkit.sh > results-$(date +%Y%m%d).txt

# Save with timestamps
sudo ./docker-analysis-toolkit.sh 2>&1 | tee results-$(date +%Y%m%d-%H%M).log
```

## 🎓 What Each Test Measures

### Performance Tests

| Test | Measures | Why It Matters |
|------|----------|----------------|
| Startup | Container initialization time | Affects scaling speed |
| I/O | Write performance and CoW overhead | Database/log performance |
| Network | Latency through Docker networking | API response times |
| Memory | Page cache efficiency | Resource optimization |
| CPU | Throttling and cgroup limits | Workload performance |

### Security Tests

| Test | Checks | Risk Level |
|------|--------|-----------|
| Capabilities | Default and custom caps | Medium-High |
| Privileged | --privileged flag | Critical |
| Socket | Docker socket mounts | Critical |
| Namespaces | Isolation verification | Medium |
| Resources | CPU/memory limits | Low-Medium |

## 💡 Tips & Best Practices

### Before Testing

1. **Stop unnecessary containers** - For accurate benchmarks
2. **Close heavy applications** - Reduce system load
3. **Run multiple times** - Get consistent results
4. **Document baseline** - Compare future results

### After Testing

1. **Review warnings** - Fix critical security issues first
2. **Compare to baseline** - Track performance trends
3. **Optimize bottlenecks** - Use test recommendations
4. **Re-test** - Verify improvements

### Regular Auditing

Run toolkit:
- **Weekly** - Production environments
- **Before deployments** - Staging validation
- **After changes** - Verify no regressions
- **During incidents** - Identify issues

## 🔗 Related Documentation

- **Main README** - [`../README.md`](../README.md)
- **Security Hardening** - [`../security-configs/docker-security-hardening.md`](../security-configs/docker-security-hardening.md)
- **Architecture** - [`../docs/architecture.md`](../docs/architecture.md)

## 🤝 Contributing

Found a bug or want to add a test? See [`../CONTRIBUTING.md`](../CONTRIBUTING.md)

Ideas for new tests:
- GPU performance monitoring
- Network bandwidth testing
- Disk IOPS measurement
- Container density limits
- Image scanning integration

---

**Questions?** Open an issue on GitHub!