#!/bin/bash
# =============================================================================
# Docker Performance Statistical Benchmark (Complete — All 10 Tests)
# For academic paper: "Decomposing Container Startup Performance"
# Author: Shamsher Khan
# Repository: https://github.com/opscart/docker-internals-guide
#
# Usage:
#   sudo ./statistical-benchmark.sh [ITERATIONS] [PLATFORM_LABEL]
#
# Examples:
#   sudo ./statistical-benchmark.sh 50 azure-premium-ssd
#   sudo ./statistical-benchmark.sh 50 azure-standard-hdd
#   sudo ./statistical-benchmark.sh 50 macos-docker-desktop
#
# Output:
#   results/<PLATFORM_LABEL>/  — CSV files + platform info
#
# Tests:
#   1. Container Startup Latency (50 iter × 3 images × cold/warm)
#   2. Copy-up Overhead (50 iter)
#   3. CPU Throttling Accuracy (50 iter)
#   4. Sequential Write Performance — OverlayFS vs Volume (50 iter)
#   5. Metadata Operations — 500 file creation (50 iter)
#   6. Image Pull Time (10 iter × 3 images)
#   7. Namespace Creation Overhead (50 iter, Linux only)
#   8. Network Latency — Bridge vs Host (50 iter)
#   9. Memory Efficiency — Page Cache Sharing (50 iter)
#  10. Qualitative Observations (single run — strace, OverlayFS, security)
# =============================================================================

set -euo pipefail

ITERATIONS=${1:-50}
PLATFORM=${2:-"unknown-platform"}
RESULTS_DIR="results/${PLATFORM}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# =============================================================================
# SETUP
# =============================================================================

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE} Docker Performance Statistical Benchmark${NC}"
echo -e "${BLUE} All 10 Tests — Academic Paper Edition${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo "Platform:   ${PLATFORM}"
echo "Iterations: ${ITERATIONS}"
echo "Timestamp:  ${TIMESTAMP}"
echo ""

mkdir -p "${RESULTS_DIR}"

echo -e "${YELLOW}Pre-pulling images...${NC}"
docker pull alpine:latest > /dev/null 2>&1
docker pull nginx:latest > /dev/null 2>&1
docker pull nginx:alpine > /dev/null 2>&1
docker pull python:3.11-slim > /dev/null 2>&1
echo -e "${GREEN}Images ready.${NC}"
echo ""

# =============================================================================
# PLATFORM INFO
# =============================================================================

echo -e "${BLUE}[0/10] Collecting platform information...${NC}"
{
    echo "=== Platform Information ==="
    echo "Collected: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Platform Label: ${PLATFORM}"
    echo ""
    echo "--- OS ---"
    uname -a
    echo ""
    if [ -f /etc/os-release ]; then
        cat /etc/os-release
    elif command -v sw_vers &>/dev/null; then
        sw_vers
    fi
    echo ""
    echo "--- CPU ---"
    if [ -f /proc/cpuinfo ]; then
        grep "model name" /proc/cpuinfo | head -1
        echo "CPU cores: $(nproc)"
    elif command -v sysctl &>/dev/null; then
        sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "N/A"
        echo "CPU cores: $(sysctl -n hw.ncpu 2>/dev/null || echo 'N/A')"
    fi
    echo ""
    echo "--- Memory ---"
    if command -v free &>/dev/null; then
        free -h
    elif command -v sysctl &>/dev/null; then
        echo "Total: $(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1024 / 1024 / 1024 )) GB"
    fi
    echo ""
    echo "--- Storage ---"
    df -h / 2>/dev/null || true
    if [ -f /sys/block/sda/queue/rotational ]; then
        ROT=$(cat /sys/block/sda/queue/rotational)
        if [ "$ROT" = "0" ]; then echo "Disk type: SSD"; else echo "Disk type: HDD"; fi
    fi
    echo ""
    echo "--- Docker ---"
    docker version --format '{{.Server.Version}}' 2>/dev/null || docker --version
    docker info --format '{{.Driver}}' 2>/dev/null || true
    echo ""
    echo "--- Kernel ---"
    uname -r
    echo ""
} > "${RESULTS_DIR}/platform-info.txt" 2>&1
echo -e "${GREEN}Platform info saved.${NC}"

# =============================================================================
# HELPERS
# =============================================================================

clear_caches() {
    if [ -f /proc/sys/vm/drop_caches ]; then
        sync
        echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
    fi
    sleep 1
}

now_ns() {
    if date +%s%N | grep -q 'N'; then
        python3 -c "import time; print(int(time.time() * 1000000000))"
    else
        date +%s%N
    fi
}

# =============================================================================
# TEST 1: Container Startup Latency
# =============================================================================

echo -e "${BLUE}[1/10] Container Startup Latency (${ITERATIONS} warm + 20 cold × 3 images)...${NC}"

CSV="${RESULTS_DIR}/01-startup-latency.csv"
echo "iteration,image,mode,startup_ms" > "${CSV}"

for IMAGE in "alpine" "nginx" "python:3.11-slim"; do
    IMAGE_LABEL=$(echo "$IMAGE" | tr ':' '_' | tr '/' '_')

    echo -e "  ${YELLOW}Warm start: ${IMAGE}${NC}"
    for i in $(seq 1 ${ITERATIONS}); do
        sleep 0.5
        START=$(now_ns)
        docker run --rm "${IMAGE}" echo "hello" > /dev/null 2>&1
        END=$(now_ns)
        ELAPSED_MS=$(echo "scale=2; ($END - $START) / 1000000" | bc)
        echo "${i},${IMAGE_LABEL},warm,${ELAPSED_MS}" >> "${CSV}"
        if (( i % 10 == 0 )); then echo -e "    ${GREEN}${i}/${ITERATIONS}${NC}"; fi
    done

    COLD_ITERATIONS=20
    echo -e "  ${YELLOW}Cold start: ${IMAGE} (${COLD_ITERATIONS} iterations)${NC}"
    for i in $(seq 1 ${COLD_ITERATIONS}); do
        clear_caches
        sleep 2
        START=$(now_ns)
        docker run --rm "${IMAGE}" echo "hello" > /dev/null 2>&1
        END=$(now_ns)
        ELAPSED_MS=$(echo "scale=2; ($END - $START) / 1000000" | bc)
        echo "${i},${IMAGE_LABEL},cold,${ELAPSED_MS}" >> "${CSV}"
        if (( i % 5 == 0 )); then echo -e "    ${GREEN}${i}/${COLD_ITERATIONS}${NC}"; fi
    done
done

echo -e "${GREEN}Test 1 complete.${NC}"
echo ""

# =============================================================================
# TEST 2: Copy-up Overhead
# =============================================================================

echo -e "${BLUE}[2/10] Copy-up Overhead (${ITERATIONS} iterations)...${NC}"

CSV="${RESULTS_DIR}/02-copyup-overhead.csv"
echo "iteration,file_size_mb,copyup_ms" > "${CSV}"

for i in $(seq 1 ${ITERATIONS}); do
    sleep 0.5
    RESULT=$(docker run --rm alpine sh -c '
        START=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1e9))")
        dd if=/dev/urandom of=/usr/share/misc/test_copyup bs=1M count=100 2>/dev/null
        END=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1e9))")
        echo $(( (END - START) / 1000000 ))
    ' 2>/dev/null || echo "0")
    echo "${i},100,${RESULT}" >> "${CSV}"
    if (( i % 10 == 0 )); then echo -e "  ${GREEN}${i}/${ITERATIONS}${NC}"; fi
done

echo -e "${GREEN}Test 2 complete.${NC}"
echo ""

# =============================================================================
# TEST 3: CPU Throttling Accuracy
# =============================================================================

echo -e "${BLUE}[3/10] CPU Throttling Accuracy (${ITERATIONS} iterations)...${NC}"

CSV="${RESULTS_DIR}/03-cpu-throttling.csv"
echo "iteration,target_pct,measured_pct,variance_pct" > "${CSV}"

for i in $(seq 1 ${ITERATIONS}); do
    sleep 0.5
    MEASURED=$(docker run --rm --cpus=0.5 alpine sh -c '
        START=$(date +%s); COUNT=0
        while true; do
            NOW=$(date +%s); ELAPSED=$((NOW - START))
            if [ $ELAPSED -ge 2 ]; then break; fi
            COUNT=$((COUNT + 1))
        done; echo $COUNT
    ' 2>/dev/null)

    BASELINE=$(docker run --rm alpine sh -c '
        START=$(date +%s); COUNT=0
        while true; do
            NOW=$(date +%s); ELAPSED=$((NOW - START))
            if [ $ELAPSED -ge 2 ]; then break; fi
            COUNT=$((COUNT + 1))
        done; echo $COUNT
    ' 2>/dev/null)

    if [ -n "$MEASURED" ] && [ -n "$BASELINE" ] && [ "$BASELINE" -gt 0 ] 2>/dev/null; then
        ACTUAL_PCT=$(echo "scale=2; ($MEASURED * 100) / $BASELINE" | bc)
        VARIANCE=$(echo "scale=2; $ACTUAL_PCT - 50.00" | bc)
        echo "${i},50.00,${ACTUAL_PCT},${VARIANCE}" >> "${CSV}"
    fi
    if (( i % 10 == 0 )); then echo -e "  ${GREEN}${i}/${ITERATIONS}${NC}"; fi
done

echo -e "${GREEN}Test 3 complete.${NC}"
echo ""

# =============================================================================
# TEST 4: Sequential Write Performance (OverlayFS vs Volume)
# =============================================================================

echo -e "${BLUE}[4/10] Sequential Write Performance (${ITERATIONS} iterations)...${NC}"

CSV="${RESULTS_DIR}/04-write-performance.csv"
echo "iteration,mode,write_speed_mbps" > "${CSV}"

docker volume create perf_test_vol > /dev/null 2>&1

for i in $(seq 1 ${ITERATIONS}); do
    sleep 0.5

    OVERLAY_SPEED=$(docker run --rm alpine sh -c '
        dd if=/dev/zero of=/tmp/testfile bs=1M count=256 2>&1 | grep -o "[0-9.]* [MG]B/s" | head -1
    ' 2>/dev/null || echo "0 MB/s")
    OVERLAY_NUM=$(echo "$OVERLAY_SPEED" | grep -o "[0-9.]*" | head -1)

    VOL_SPEED=$(docker run --rm -v perf_test_vol:/data alpine sh -c '
        dd if=/dev/zero of=/data/testfile bs=1M count=256 2>&1 | grep -o "[0-9.]* [MG]B/s" | head -1
    ' 2>/dev/null || echo "0 MB/s")
    VOL_NUM=$(echo "$VOL_SPEED" | grep -o "[0-9.]*" | head -1)

    echo "${i},overlayfs,${OVERLAY_NUM:-0}" >> "${CSV}"
    echo "${i},volume,${VOL_NUM:-0}" >> "${CSV}"
    if (( i % 10 == 0 )); then echo -e "  ${GREEN}${i}/${ITERATIONS}${NC}"; fi
done

docker volume rm perf_test_vol > /dev/null 2>&1 || true
echo -e "${GREEN}Test 4 complete.${NC}"
echo ""

# =============================================================================
# TEST 5: Metadata Operations (500 file creation)
# =============================================================================

echo -e "${BLUE}[5/10] Metadata Operations (${ITERATIONS} iterations)...${NC}"

CSV="${RESULTS_DIR}/05-metadata-operations.csv"
echo "iteration,mode,file_count,duration_ms" > "${CSV}"

docker volume create meta_test_vol > /dev/null 2>&1

for i in $(seq 1 ${ITERATIONS}); do
    sleep 0.5

    OVERLAY_MS=$(docker run --rm alpine sh -c '
        START=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1e9))")
        for j in $(seq 1 500); do echo "data" > /tmp/file_$j; done
        END=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1e9))")
        echo $(( (END - START) / 1000000 ))
    ' 2>/dev/null || echo "0")

    VOL_MS=$(docker run --rm -v meta_test_vol:/data alpine sh -c '
        START=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1e9))")
        for j in $(seq 1 500); do echo "data" > /data/file_$j; done
        END=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1e9))")
        echo $(( (END - START) / 1000000 ))
    ' 2>/dev/null || echo "0")

    echo "${i},overlayfs,500,${OVERLAY_MS}" >> "${CSV}"
    echo "${i},volume,500,${VOL_MS}" >> "${CSV}"
    if (( i % 10 == 0 )); then echo -e "  ${GREEN}${i}/${ITERATIONS}${NC}"; fi
done

docker volume rm meta_test_vol > /dev/null 2>&1 || true
echo -e "${GREEN}Test 5 complete.${NC}"
echo ""

# =============================================================================
# TEST 6: Image Pull Time (10 iterations × 3 images)
# =============================================================================

echo -e "${BLUE}[6/10] Image Pull Time (10 iterations × 3 images)...${NC}"

CSV="${RESULTS_DIR}/06-image-pull-time.csv"
echo "iteration,image,pull_time_ms" > "${CSV}"

PULL_ITERATIONS=10

for IMAGE in "alpine" "nginx" "python:3.11-slim"; do
    IMAGE_LABEL=$(echo "$IMAGE" | tr ':' '_' | tr '/' '_')
    echo -e "  ${YELLOW}Pull test: ${IMAGE}${NC}"

    for i in $(seq 1 ${PULL_ITERATIONS}); do
        docker rmi "${IMAGE}" > /dev/null 2>&1 || true
        clear_caches
        sleep 2

        START=$(now_ns)
        docker pull "${IMAGE}" > /dev/null 2>&1
        END=$(now_ns)
        ELAPSED_MS=$(echo "scale=2; ($END - $START) / 1000000" | bc)
        echo "${i},${IMAGE_LABEL},${ELAPSED_MS}" >> "${CSV}"
        echo -e "    ${GREEN}${i}/${PULL_ITERATIONS}${NC}"
    done
done

docker pull alpine:latest > /dev/null 2>&1
docker pull nginx:latest > /dev/null 2>&1
docker pull nginx:alpine > /dev/null 2>&1
docker pull python:3.11-slim > /dev/null 2>&1

echo -e "${GREEN}Test 6 complete.${NC}"
echo ""

# =============================================================================
# TEST 7: Namespace Creation Overhead (Linux only)
# =============================================================================

echo -e "${BLUE}[7/10] Namespace creation overhead (${ITERATIONS} iterations)...${NC}"

CSV="${RESULTS_DIR}/07-namespace-overhead.csv"
echo "iteration,operation,duration_ms" > "${CSV}"

if command -v unshare &>/dev/null && [ -f /proc/self/ns/pid ]; then
    for i in $(seq 1 ${ITERATIONS}); do
        sleep 0.3
        START=$(now_ns)
        unshare --pid --fork --mount-proc echo "ns_test" > /dev/null 2>&1 || true
        END=$(now_ns)
        ELAPSED_MS=$(echo "scale=2; ($END - $START) / 1000000" | bc)
        echo "${i},namespace_create,${ELAPSED_MS}" >> "${CSV}"
        if (( i % 10 == 0 )); then echo -e "  ${GREEN}${i}/${ITERATIONS}${NC}"; fi
    done
else
    echo -e "  ${YELLOW}Skipping — unshare not available on this platform${NC}"
    echo "0,namespace_create,N/A" >> "${CSV}"
fi

echo -e "${GREEN}Test 7 complete.${NC}"
echo ""

# =============================================================================
# TEST 8: Network Latency — Bridge vs Host
# =============================================================================

echo -e "${BLUE}[8/10] Network Latency: Bridge vs Host (${ITERATIONS} iterations)...${NC}"

CSV="${RESULTS_DIR}/08-network-latency.csv"
echo "iteration,mode,avg_rtt_ms" > "${CSV}"

for i in $(seq 1 ${ITERATIONS}); do
    sleep 0.5

    BRIDGE_RTT=$(docker run --rm alpine ping -c 5 -q 8.8.8.8 2>/dev/null \
        | grep 'avg' | awk -F'/' '{print $5}' || echo "0")

    HOST_RTT=$(docker run --rm --network host alpine ping -c 5 -q 8.8.8.8 2>/dev/null \
        | grep 'avg' | awk -F'/' '{print $5}' || echo "0")

    echo "${i},bridge,${BRIDGE_RTT}" >> "${CSV}"
    echo "${i},host,${HOST_RTT}" >> "${CSV}"
    if (( i % 10 == 0 )); then echo -e "  ${GREEN}${i}/${ITERATIONS}${NC}"; fi
done

echo -e "${GREEN}Test 8 complete.${NC}"
echo ""

# =============================================================================
# TEST 9: Memory Efficiency — Page Cache Sharing (3× nginx)
# =============================================================================

echo -e "${BLUE}[9/10] Memory Efficiency: Page Cache Sharing (${ITERATIONS} iterations)...${NC}"

CSV="${RESULTS_DIR}/09-memory-efficiency.csv"
echo "iteration,container_count,per_container_rss_kb,total_rss_kb" > "${CSV}"

for i in $(seq 1 ${ITERATIONS}); do
    sleep 0.5

    docker run -d --name mem_test_1 nginx:alpine > /dev/null 2>&1
    docker run -d --name mem_test_2 nginx:alpine > /dev/null 2>&1
    docker run -d --name mem_test_3 nginx:alpine > /dev/null 2>&1
    sleep 2

    TOTAL_RSS=0
    COUNT=0
    for NAME in mem_test_1 mem_test_2 mem_test_3; do
        PID=$(docker inspect "$NAME" --format='{{.State.Pid}}' 2>/dev/null || echo "0")
        if [ "$PID" != "0" ] && [ -n "$PID" ]; then
            RSS=$(ps -p "$PID" -o rss= 2>/dev/null | tr -d ' ' || echo "0")
            if [ -n "$RSS" ] && [ "$RSS" != "0" ]; then
                TOTAL_RSS=$((TOTAL_RSS + RSS))
                COUNT=$((COUNT + 1))
            fi
        fi
    done

    if [ "$COUNT" -gt 0 ]; then
        PER_CONTAINER=$((TOTAL_RSS / COUNT))
        echo "${i},${COUNT},${PER_CONTAINER},${TOTAL_RSS}" >> "${CSV}"
    fi

    docker rm -f mem_test_1 mem_test_2 mem_test_3 > /dev/null 2>&1
    if (( i % 10 == 0 )); then echo -e "  ${GREEN}${i}/${ITERATIONS}${NC}"; fi
done

echo -e "${GREEN}Test 9 complete.${NC}"
echo ""

# =============================================================================
# TEST 10: Qualitative Observations (single run)
# =============================================================================

echo -e "${BLUE}[10/10] Qualitative observations (single run)...${NC}"

QUAL_FILE="${RESULTS_DIR}/10-qualitative-observations.txt"
{
    echo "=== Qualitative Observations ==="
    echo "Collected: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Platform: ${PLATFORM}"
    echo ""

    echo "--- OverlayFS Layer Structure (nginx:alpine) ---"
    docker image inspect nginx:alpine --format='{{json .RootFS.Layers}}' 2>/dev/null \
        | python3 -m json.tool 2>/dev/null || \
        docker image inspect nginx:alpine | grep -A 20 '"Layers"' || true
    echo "Layer count: $(docker image inspect nginx:alpine --format='{{len .RootFS.Layers}}' 2>/dev/null || echo 'N/A')"
    echo ""

    echo "--- Physical Layer Storage ---"
    if [ -d "/var/lib/docker/overlay2" ]; then
        echo "Layer directories:"
        find /var/lib/docker/overlay2 -maxdepth 1 -type d 2>/dev/null | head -10 || true
    else
        echo "/var/lib/docker/overlay2 not accessible (macOS uses VM-based storage)"
    fi
    echo ""

    echo "--- Storage Driver ---"
    docker info --format '{{.Driver}}' 2>/dev/null || echo "N/A"
    echo ""

    echo "--- Docker Daemon Info ---"
    docker info 2>/dev/null | grep -E 'Storage Driver|Kernel Version|Operating System|CPUs|Total Memory' || true
    echo ""

    echo "--- Default Container Capabilities ---"
    docker run --rm alpine sh -c 'cat /proc/self/status | grep Cap' 2>/dev/null || echo "N/A"
    echo ""

    echo "--- Restricted Capabilities (--cap-drop=ALL) ---"
    docker run --rm --cap-drop=ALL alpine sh -c 'cat /proc/self/status | grep Cap' 2>/dev/null || echo "N/A"
    echo ""

    echo "--- Privileged Container Check ---"
    PRIV=$(docker ps -a --filter "status=running" --format "{{.Names}}" 2>/dev/null | while read container; do
        docker inspect "$container" --format='{{.HostConfig.Privileged}} {{.Name}}' 2>/dev/null
    done | grep "true" || true)
    if [ -n "$PRIV" ]; then echo "WARNING: Privileged containers: $PRIV"
    else echo "No privileged containers running"; fi
    echo ""

    echo "--- Docker Socket Mount Check ---"
    SOCKET=$(docker ps -a --filter "status=running" --format "{{.Names}}" 2>/dev/null | while read container; do
        docker inspect "$container" --format='{{range .Mounts}}{{if eq .Source "/var/run/docker.sock"}}{{$.Name}}{{end}}{{end}}' 2>/dev/null
    done || true)
    if [ -n "$SOCKET" ]; then echo "WARNING: Docker socket access: $SOCKET"
    else echo "No containers with Docker socket access"; fi
    echo ""

    echo "--- Namespace Isolation ---"
    docker run -d --name ns_qual_test alpine sleep 30 > /dev/null 2>&1
    NS_PID=$(docker inspect ns_qual_test --format='{{.State.Pid}}' 2>/dev/null || echo "0")
    if [ "$NS_PID" != "0" ] && [ -d "/proc/$NS_PID/ns" ]; then
        echo "Container PID: $NS_PID"
        echo "Container namespaces:"
        ls -la /proc/$NS_PID/ns/ 2>/dev/null || echo "Cannot access"
        echo "Host namespaces (PID 1):"
        ls -la /proc/1/ns/ 2>/dev/null || echo "Cannot access"
        echo "Container process view:"
        docker exec ns_qual_test ps aux 2>/dev/null || echo "N/A"
    else
        echo "Namespace inspection not available (expected on macOS)"
    fi
    docker rm -f ns_qual_test > /dev/null 2>&1
    echo ""

    echo "--- Syscall Trace (strace) ---"
    if command -v strace &>/dev/null; then
        TRACE_FILE="/tmp/docker-syscall-trace-${PLATFORM}.log"
        strace -f -e trace=clone,unshare,mount,setns,execve \
            -o "$TRACE_FILE" \
            docker run --rm alpine echo "traced" 2>/dev/null || true
        echo "clone() calls: $(grep -c 'clone(' "$TRACE_FILE" 2>/dev/null || echo 0)"
        echo "unshare() calls: $(grep -c 'unshare(' "$TRACE_FILE" 2>/dev/null || echo 0)"
        echo "mount() calls: $(grep -c 'mount(' "$TRACE_FILE" 2>/dev/null || echo 0)"
        echo "setns() calls: $(grep -c 'setns(' "$TRACE_FILE" 2>/dev/null || echo 0)"
        echo "execve() calls: $(grep -c 'execve(' "$TRACE_FILE" 2>/dev/null || echo 0)"
        echo "Full trace: $TRACE_FILE"
    else
        echo "strace not available (expected on macOS)"
    fi
    echo ""

    echo "--- eBPF Tracing ---"
    if command -v bpftrace &>/dev/null; then echo "bpftrace available"
    else echo "bpftrace not available (expected on macOS)"; fi

} > "${QUAL_FILE}" 2>&1

echo -e "${GREEN}Test 10 complete.${NC}"
echo ""

# =============================================================================
# FINAL SUMMARY
# =============================================================================

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE} All 10 Tests Complete!${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo "Results saved to: ${RESULTS_DIR}/"
echo ""
ls -la "${RESULTS_DIR}/"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Analyze:  python3 analyze_results.py ${RESULTS_DIR}"
echo "  2. Commit:   git add ${RESULTS_DIR}/ && git commit -m 'research: benchmark data (${PLATFORM})'"
echo "  3. Compare:  python3 analyze_results.py --compare results/platform1 results/platform2"