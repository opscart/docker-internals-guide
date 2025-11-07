#!/bin/bash
# Docker Performance & Security Analysis Toolkit
# Companion to "Beyond Containers: Deconstructing Docker's Architecture"
# 
# Requirements: docker, strace, perf, bpftrace (optional), jq
# Usage: sudo ./docker-analysis-toolkit.sh

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"
    
    local missing=0
    
    if ! command -v docker &> /dev/null; then
        print_error "docker not found"
        missing=1
    else
        print_success "docker found: $(docker --version)"
    fi
    
    if ! command -v strace &> /dev/null; then
        print_warning "strace not found (optional for syscall tracing)"
    else
        print_success "strace found"
    fi
    
    if ! command -v perf &> /dev/null; then
        print_warning "perf not found (optional for CPU profiling)"
    else
        print_success "perf found"
    fi
    
    if ! command -v jq &> /dev/null; then
        print_warning "jq not found (optional for JSON parsing)"
    else
        print_success "jq found"
    fi
    
    if ! command -v bpftrace &> /dev/null; then
        print_warning "bpftrace not found (optional for eBPF tracing)"
    else
        print_success "bpftrace found"
    fi
    
    if [ $missing -eq 1 ]; then
        print_error "Missing required tools. Install with: apt-get install docker.io strace linux-tools-generic jq"
        exit 1
    fi
}

# Test 1: Container Startup Latency
test_startup_latency() {
    print_header "Test 1: Container Startup Latency"
    
    echo "Measuring cold start time (no cached layers)..."
    docker rmi alpine:latest 2>/dev/null || true
    
    local start=$(date +%s%N)
    docker run --rm alpine true
    local end=$(date +%s%N)
    
    local duration=$(( (end - start) / 1000000 ))
    echo "Cold start (with pull): ${duration}ms"
    
    echo -e "\nMeasuring warm start time (cached layers)..."
    start=$(date +%s%N)
    docker run --rm alpine true
    end=$(date +%s%N)
    
    duration=$(( (end - start) / 1000000 ))
    echo "Warm start (cached): ${duration}ms"
    
    echo -e "\nRunning 10 iterations to get average..."
    local total=0
    for i in {1..10}; do
        start=$(date +%s%N)
        docker run --rm alpine true 2>/dev/null
        end=$(date +%s%N)
        local iter_duration=$(( (end - start) / 1000000 ))
        total=$((total + iter_duration))
    done
    
    local avg=$((total / 10))
    echo "Average startup time: ${avg}ms"
    
    if [ $avg -lt 150 ]; then
        print_success "Excellent startup performance (<150ms)"
    elif [ $avg -lt 300 ]; then
        print_warning "Acceptable startup performance (150-300ms)"
    else
        print_error "Slow startup performance (>300ms) - check storage driver"
    fi
}

# Test 2: Syscall Tracing
test_syscall_trace() {
    print_header "Test 2: Syscall Analysis"
    
    if ! command -v strace &> /dev/null; then
        print_warning "strace not available, skipping"
        return
    fi
    
    echo "Tracing syscalls for container creation..."
    echo "(This will show namespace creation, mounts, etc.)"
    
    local trace_file="/tmp/docker-syscall-trace.log"
    
    # Run strace on docker command
    strace -f -e trace=clone,unshare,mount,setns,execve -o "$trace_file" \
        docker run --rm alpine echo "syscall traced" 2>/dev/null || true
    
    echo -e "\nKey syscalls detected:"
    
    # Count different syscall types
    local clone_count=$(grep -c "clone(" "$trace_file" 2>/dev/null || echo 0)
    local unshare_count=$(grep -c "unshare(" "$trace_file" 2>/dev/null || echo 0)
    local mount_count=$(grep -c "mount(" "$trace_file" 2>/dev/null || echo 0)
    local setns_count=$(grep -c "setns(" "$trace_file" 2>/dev/null || echo 0)
    local execve_count=$(grep -c "execve(" "$trace_file" 2>/dev/null || echo 0)
    
    echo "  clone() calls (process creation): $clone_count"
    echo "  unshare() calls (namespace creation): $unshare_count"
    echo "  mount() calls (filesystem setup): $mount_count"
    echo "  setns() calls (namespace switching): $setns_count"
    echo "  execve() calls (program execution): $execve_count"
    
    echo -e "\nFirst few clone() syscalls with namespace flags:"
    grep "clone(" "$trace_file" | head -3 || echo "No clone calls found"
    
    echo -e "\nFull trace saved to: $trace_file"
}

# Test 3: OverlayFS Layer Inspection
test_overlayfs_layers() {
    print_header "Test 3: OverlayFS Layer Analysis"
    
    echo "Pulling multi-layer image (nginx)..."
    docker pull nginx:alpine >/dev/null 2>&1
    
    echo -e "\nImage layers:"
    if command -v jq &> /dev/null; then
        docker image inspect nginx:alpine | jq '.[0].RootFS.Layers[]'
    else
        docker image inspect nginx:alpine | grep -A 20 '"Layers"'
    fi
    
    echo -e "\nPhysical layer storage:"
    local nginx_id=$(docker image inspect nginx:alpine --format='{{.Id}}' | cut -d':' -f2)
    echo "Image ID: $nginx_id"
    
    if [ -d "/var/lib/docker/overlay2" ]; then
        echo -e "\nLayer directories in /var/lib/docker/overlay2/:"
        sudo find /var/lib/docker/overlay2 -maxdepth 1 -type d | head -10
        
        echo -e "\nExample layer structure:"
        local layer=$(sudo find /var/lib/docker/overlay2 -maxdepth 1 -type d -name '*-init' | head -1)
        if [ -n "$layer" ]; then
            echo "Layer: $(basename $layer)"
            sudo ls -la "$layer" 2>/dev/null | head -10 || echo "Cannot access layer directory"
        fi
    else
        print_warning "/var/lib/docker/overlay2 not accessible (may require root)"
    fi
}

# Test 4: Container I/O Performance
test_io_performance() {
    print_header "Test 4: I/O Performance Analysis"
    
    echo "Testing sequential write performance..."
    docker run --rm alpine dd if=/dev/zero of=/tmp/test bs=1M count=100 oflag=direct 2>&1 | grep -E 'MB/s|copied'
    
    echo -e "\nTesting with volume mount (should be faster)..."
    docker run --rm -v /tmp:/mnt alpine dd if=/dev/zero of=/mnt/test bs=1M count=100 oflag=direct 2>&1 | grep -E 'MB/s|copied'
    rm -f /tmp/test
    
    echo -e "\nTesting copy-up overhead..."
    echo "Creating container with large file..."
    docker run -d --name io-test alpine sh -c "dd if=/dev/zero of=/bigfile bs=1M count=50 && sleep 60" >/dev/null 2>&1
    
    sleep 2
    
    echo "Modifying file (triggers copy-up)..."
    local start=$(date +%s%N)
    docker exec io-test sh -c "echo 'modified' >> /bigfile"
    local end=$(date +%s%N)
    
    local copyup_time=$(( (end - start) / 1000000 ))
    echo "Copy-up operation time: ${copyup_time}ms"
    
    if [ $copyup_time -gt 100 ]; then
        print_warning "High copy-up latency detected - avoid modifying large image files"
    fi
    
    docker rm -f io-test >/dev/null 2>&1
}

# Test 5: Network Performance
test_network_performance() {
    print_header "Test 5: Network Performance"
    
    echo "Testing bridge network latency..."
    docker run --rm alpine ping -c 10 -i 0.1 8.8.8.8 2>&1 | grep -E 'rtt|packets'
    
    echo -e "\nTesting host network latency (for comparison)..."
    docker run --rm --network host alpine ping -c 10 -i 0.1 8.8.8.8 2>&1 | grep -E 'rtt|packets'
    
    echo -e "\nNetwork overhead comparison:"
    echo "Bridge mode typically adds 0.1-0.3ms latency vs host mode"
}

# Test 6: Memory Analysis
test_memory_efficiency() {
    print_header "Test 6: Memory Efficiency & Page Cache Sharing"
    
    echo "Starting 3 identical nginx containers..."
    docker run -d --name nginx1 nginx:alpine >/dev/null 2>&1
    docker run -d --name nginx2 nginx:alpine >/dev/null 2>&1
    docker run -d --name nginx3 nginx:alpine >/dev/null 2>&1
    
    sleep 3
    
    echo -e "\nIndividual container memory usage:"
    docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}" nginx1 nginx2 nginx3
    
    echo -e "\nPhysical memory (RSS) per container:"
    for container in nginx1 nginx2 nginx3; do
        local pid=$(docker inspect $container --format='{{.State.Pid}}')
        local rss=$(ps -p $pid -o rss= 2>/dev/null || echo "N/A")
        echo "$container (PID $pid): $rss KB"
    done
    
    echo -e "\nNote: Shared pages (like nginx binary) are counted once in physical memory"
    echo "Total reported may exceed actual RAM usage due to page cache sharing"
    
    docker rm -f nginx1 nginx2 nginx3 >/dev/null 2>&1
}

# Test 7: Security Analysis
test_security_posture() {
    print_header "Test 7: Security Posture Analysis"
    
    echo "Checking default container capabilities..."
    docker run --rm alpine sh -c 'cat /proc/self/status | grep Cap'
    
    echo -e "\nCapability names (requires libcap):"
    if command -v capsh &> /dev/null; then
        docker run --rm alpine sh -c 'cat /proc/self/status | grep CapEff' | awk '{print $2}' | xargs capsh --decode
    else
        echo "Install libcap2-bin to decode capabilities"
    fi
    
    echo -e "\nTesting restricted container (no capabilities):"
    docker run --rm --cap-drop=ALL alpine sh -c 'cat /proc/self/status | grep Cap'
    
    echo -e "\nChecking for privileged containers (security risk):"
    local privileged=$(docker ps -a --filter "status=running" --format "{{.Names}}" | while read container; do
        docker inspect $container --format='{{.HostConfig.Privileged}} {{.Name}}' 2>/dev/null
    done | grep "true")
    
    if [ -n "$privileged" ]; then
        print_error "WARNING: Privileged containers detected:"
        echo "$privileged"
    else
        print_success "No privileged containers running"
    fi
    
    echo -e "\nChecking Docker socket mounts (security risk):"
    local socket_mounts=$(docker ps -a --filter "status=running" --format "{{.Names}}" | while read container; do
        docker inspect $container --format='{{range .Mounts}}{{if eq .Source "/var/run/docker.sock"}}{{$.Name}}{{end}}{{end}}' 2>/dev/null
    done)
    
    if [ -n "$socket_mounts" ]; then
        print_error "WARNING: Containers with Docker socket access:"
        echo "$socket_mounts"
        echo "These containers have root-equivalent access to the host!"
    else
        print_success "No containers with Docker socket access"
    fi
}

# Test 8: CPU Performance & Throttling
test_cpu_performance() {
    print_header "Test 8: CPU Performance & Throttling"
    
    echo "Starting CPU-intensive container without limits..."
    docker run -d --name cpu-test alpine sh -c 'while true; do echo "stress" > /dev/null; done' >/dev/null 2>&1
    
    sleep 3
    
    echo "CPU usage:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}" cpu-test
    
    docker rm -f cpu-test >/dev/null 2>&1
    
    echo -e "\nStarting CPU-limited container (50% of 1 core)..."
    docker run -d --name cpu-limited --cpu-period=100000 --cpu-quota=50000 alpine sh -c 'while true; do echo "stress" > /dev/null; done' >/dev/null 2>&1
    
    sleep 3
    
    echo "CPU usage (should be ~50%):"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}" cpu-limited
    
    echo -e "\nChecking for CPU throttling..."
    local container_id=$(docker inspect cpu-limited --format='{{.Id}}')
    local cgroup_path=$(find /sys/fs/cgroup -name "*$container_id*" -type d 2>/dev/null | grep cpu | head -1)
    
    if [ -n "$cgroup_path" ] && [ -f "$cgroup_path/cpu.stat" ]; then
        echo "CPU statistics:"
        sudo cat "$cgroup_path/cpu.stat" 2>/dev/null || echo "Cannot read cgroup stats (requires root)"
    fi
    
    docker rm -f cpu-limited >/dev/null 2>&1
}

# Test 9: Container Namespace Inspection
test_namespace_isolation() {
    print_header "Test 9: Namespace Isolation Inspection"
    
    echo "Starting test container..."
    docker run -d --name ns-test alpine sleep 60 >/dev/null 2>&1
    
    local pid=$(docker inspect ns-test --format='{{.State.Pid}}')
    echo "Container PID: $pid"
    
    echo -e "\nNamespace links for container process:"
    sudo ls -l /proc/$pid/ns/ 2>/dev/null || echo "Cannot access namespaces (requires root)"
    
    echo -e "\nComparing to host namespaces:"
    echo "Host PID namespace:"
    sudo ls -l /proc/1/ns/pid 2>/dev/null || echo "Requires root"
    echo "Container PID namespace:"
    sudo ls -l /proc/$pid/ns/pid 2>/dev/null || echo "Requires root"
    
    echo -e "\nContainer's view of processes (should only see itself):"
    docker exec ns-test ps aux
    
    docker rm -f ns-test >/dev/null 2>&1
}

# Test 10: eBPF-based Deep Tracing (if available)
test_ebpf_tracing() {
    print_header "Test 10: eBPF-based Syscall Tracing (Advanced)"
    
    if ! command -v bpftrace &> /dev/null; then
        print_warning "bpftrace not available, skipping"
        return
    fi
    
    echo "Starting container for eBPF trace..."
    docker run -d --name ebpf-test alpine sh -c 'for i in $(seq 1 100); do echo $i; sleep 0.1; done' >/dev/null 2>&1
    
    sleep 1
    
    local pid=$(docker inspect ebpf-test --format='{{.State.Pid}}')
    echo "Tracing syscalls for PID $pid (10 second sample)..."
    
    timeout 10 sudo bpftrace -e "tracepoint:raw_syscalls:sys_enter /pid == $pid/ { @[args->id] = count(); }" 2>/dev/null || echo "eBPF tracing requires kernel CONFIG_BPF and root"
    
    docker rm -f ebpf-test >/dev/null 2>&1
}

# Generate report
generate_report() {
    print_header "Performance Analysis Summary"
    
    echo "Docker daemon info:"
    docker info | grep -E 'Storage Driver|Kernel Version|Operating System|CPUs|Total Memory'
    
    echo -e "\n${GREEN}Analysis complete!${NC}"
    echo -e "\nKey findings:"
    echo "1. Check startup latency - should be <150ms for good performance"
    echo "2. OverlayFS copy-up operations add latency for large file modifications"
    echo "3. Use volumes for write-heavy workloads to bypass storage driver"
    echo "4. Host networking reduces latency by ~0.2ms but sacrifices isolation"
    echo "5. Page cache sharing makes multiple identical containers memory-efficient"
    echo "6. Avoid privileged containers and Docker socket mounts in production"
    
    echo -e "\n${YELLOW}Recommendations:${NC}"
    echo "• Use multi-stage builds to reduce image size"
    echo "• Minimize layer count (combine RUN commands)"
    echo "• Drop unnecessary capabilities (--cap-drop=ALL)"
    echo "• Set resource limits (--memory, --cpus) for production"
    echo "• Use read-only root filesystem where possible (--read-only)"
    echo "• Enable user namespace remapping for additional security"
}

# Main execution
main() {
    echo -e "${GREEN}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║   Docker Performance & Security Analysis Toolkit           ║"
    echo "║   Deep-dive companion for container optimization           ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    check_prerequisites
    
    # Run all tests
    test_startup_latency
    test_syscall_trace
    test_overlayfs_layers
    test_io_performance
    test_network_performance
    test_memory_efficiency
    test_security_posture
    test_cpu_performance
    test_namespace_isolation
    test_ebpf_tracing
    
    generate_report
    
    echo -e "\n${GREEN}All tests completed!${NC}"
    echo "Logs and traces saved in /tmp/"
}

# Run main function
main "$@"