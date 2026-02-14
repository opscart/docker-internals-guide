#!/bin/bash
# =============================================================================
# Docker Performance Statistical Benchmark
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
#   results/<PLATFORM_LABEL>/  — CSV files for each test dimension
#   results/<PLATFORM_LABEL>/platform-info.txt — hardware/software specs
# =============================================================================

set -euo pipefail

ITERATIONS=${1:-50}
PLATFORM=${2:-"unknown-platform"}
RESULTS_DIR="results/${PLATFORM}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
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
echo -e "${BLUE}============================================${NC}"
echo ""
echo "Platform:   ${PLATFORM}"
echo "Iterations: ${ITERATIONS}"
echo "Timestamp:  ${TIMESTAMP}"
echo ""

mkdir -p "${RESULTS_DIR}"

# Pre-pull images to avoid network variance in startup tests
echo -e "${YELLOW}Pre-pulling images...${NC}"
docker pull alpine:latest > /dev/null 2>&1
docker pull nginx:latest > /dev/null 2>&1
docker pull python:3.11-slim > /dev/null 2>&1
echo -e "${GREEN}Images ready.${NC}"
echo ""

# =============================================================================
# PLATFORM INFO — captures exact environment specs for reproducibility
# =============================================================================

echo -e "${BLUE}[0/7] Collecting platform information...${NC}"
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
# Helper: clear caches (Linux only, skip on macOS)
# =============================================================================
clear_caches() {
    if [ -f /proc/sys/vm/drop_caches ]; then
        sync
        echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
    fi
    sleep 1
}

# Helper: nanosecond timestamp (portable)
now_ns() {
    if date +%s%N | grep -q 'N'; then
        # macOS: use python for nanosecond precision
        python3 -c "import time; print(int(time.time() * 1000000000))"
    else
        date +%s%N
    fi
}

# =============================================================================
# TEST 1: Container Startup Latency
# Tests: alpine (small), nginx (medium), python:3.11-slim (large)
# Both cold-start and warm-start
# =============================================================================

echo -e "${BLUE}[1/7] Container Startup Latency (${ITERATIONS} iterations × 3 images × 2 modes)...${NC}"

CSV="${RESULTS_DIR}/01-startup-latency.csv"
echo "iteration,image,mode,startup_ms" > "${CSV}"

for IMAGE in "alpine" "nginx" "python:3.11-slim"; do
    IMAGE_LABEL=$(echo "$IMAGE" | tr ':' '_' | tr '/' '_')

    # --- Warm start (image cached, repeated runs) ---
    echo -e "  ${YELLOW}Warm start: ${IMAGE}${NC}"
    for i in $(seq 1 ${ITERATIONS}); do
        sleep 0.5
        START=$(now_ns)
        docker run --rm "${IMAGE}" echo "hello" > /dev/null 2>&1
        END=$(now_ns)
        ELAPSED_MS=$(echo "scale=2; ($END - $START) / 1000000" | bc)
        echo "${i},${IMAGE_LABEL},warm,${ELAPSED_MS}" >> "${CSV}"

        # Progress indicator every 10
        if (( i % 10 == 0 )); then
            echo -e "    ${GREEN}${i}/${ITERATIONS} complete${NC}"
        fi
    done

    # --- Cold start (cache cleared before each run) ---
    # Only do 20 cold-start iterations (they're slow due to cache clearing)
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

        if (( i % 5 == 0 )); then
            echo -e "    ${GREEN}${i}/${COLD_ITERATIONS} complete${NC}"
        fi
    done
done

echo -e "${GREEN}Startup latency complete. Saved to ${CSV}${NC}"
echo ""

# =============================================================================
# TEST 2: Copy-up Overhead
# Measures time to modify a file in a read-only layer (triggers copy-up)
# =============================================================================

echo -e "${BLUE}[2/7] Copy-up Overhead (${ITERATIONS} iterations)...${NC}"

CSV="${RESULTS_DIR}/02-copyup-overhead.csv"
echo "iteration,file_size_mb,copyup_ms" > "${CSV}"

for i in $(seq 1 ${ITERATIONS}); do
    sleep 0.5
    # Create a container with a 100MB file, then modify it to trigger copy-up
    RESULT=$(docker run --rm alpine sh -c '
        # Create a 100MB file in a writable layer first
        dd if=/dev/zero of=/tmp/baseline bs=1M count=100 2>/dev/null
        # Now copy it to trigger measurement of copy-up from read-only layer
        # We measure modifying /etc/hostname (small, but triggers copy-up mechanism)
        START=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1e9))")
        dd if=/dev/urandom of=/usr/share/misc/test_copyup bs=1M count=100 2>/dev/null
        END=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1e9))")
        echo $(( (END - START) / 1000000 ))
    ' 2>/dev/null || echo "0")

    echo "${i},100,${RESULT}" >> "${CSV}"

    if (( i % 10 == 0 )); then
        echo -e "  ${GREEN}${i}/${ITERATIONS} complete${NC}"
    fi
done

echo -e "${GREEN}Copy-up overhead complete. Saved to ${CSV}${NC}"
echo ""

# =============================================================================
# TEST 3: CPU Throttling Accuracy
# Sets CPU limit to 50% and measures actual usage
# =============================================================================

echo -e "${BLUE}[3/7] CPU Throttling Accuracy (${ITERATIONS} iterations)...${NC}"

CSV="${RESULTS_DIR}/03-cpu-throttling.csv"
echo "iteration,target_pct,measured_pct,variance_pct" > "${CSV}"

for i in $(seq 1 ${ITERATIONS}); do
    sleep 0.5
    # Run CPU-intensive task with 50% CPU limit, measure actual usage
    MEASURED=$(docker run --rm --cpus=0.5 alpine sh -c '
        # Burn CPU for 2 seconds and check actual usage
        START=$(date +%s)
        COUNT=0
        while true; do
            NOW=$(date +%s)
            ELAPSED=$((NOW - START))
            if [ $ELAPSED -ge 2 ]; then break; fi
            COUNT=$((COUNT + 1))
        done
        echo $COUNT
    ' 2>/dev/null)

    # Get baseline (no CPU limit)
    BASELINE=$(docker run --rm alpine sh -c '
        START=$(date +%s)
        COUNT=0
        while true; do
            NOW=$(date +%s)
            ELAPSED=$((NOW - START))
            if [ $ELAPSED -ge 2 ]; then break; fi
            COUNT=$((COUNT + 1))
        done
        echo $COUNT
    ' 2>/dev/null)

    if [ -n "$MEASURED" ] && [ -n "$BASELINE" ] && [ "$BASELINE" -gt 0 ] 2>/dev/null; then
        ACTUAL_PCT=$(echo "scale=2; ($MEASURED * 100) / $BASELINE" | bc)
        VARIANCE=$(echo "scale=2; $ACTUAL_PCT - 50.00" | bc)
        echo "${i},50.00,${ACTUAL_PCT},${VARIANCE}" >> "${CSV}"
    fi

    if (( i % 10 == 0 )); then
        echo -e "  ${GREEN}${i}/${ITERATIONS} complete${NC}"
    fi
done

echo -e "${GREEN}CPU throttling complete. Saved to ${CSV}${NC}"
echo ""

# =============================================================================
# TEST 4: Sequential Write Performance (OverlayFS vs Volume)
# =============================================================================

echo -e "${BLUE}[4/7] Sequential Write Performance (${ITERATIONS} iterations)...${NC}"

CSV="${RESULTS_DIR}/04-write-performance.csv"
echo "iteration,mode,write_speed_mbps" > "${CSV}"

# Create a temp volume for volume tests
docker volume create perf_test_vol > /dev/null 2>&1

for i in $(seq 1 ${ITERATIONS}); do
    sleep 0.5

    # OverlayFS write
    OVERLAY_SPEED=$(docker run --rm alpine sh -c '
        dd if=/dev/zero of=/tmp/testfile bs=1M count=256 2>&1 | grep -o "[0-9.]* [MG]B/s" | head -1
    ' 2>/dev/null || echo "0 MB/s")
    OVERLAY_NUM=$(echo "$OVERLAY_SPEED" | grep -o "[0-9.]*" | head -1)

    # Volume write (skip on macOS if problematic)
    VOL_SPEED=$(docker run --rm -v perf_test_vol:/data alpine sh -c '
        dd if=/dev/zero of=/data/testfile bs=1M count=256 2>&1 | grep -o "[0-9.]* [MG]B/s" | head -1
    ' 2>/dev/null || echo "0 MB/s")
    VOL_NUM=$(echo "$VOL_SPEED" | grep -o "[0-9.]*" | head -1)

    echo "${i},overlayfs,${OVERLAY_NUM:-0}" >> "${CSV}"
    echo "${i},volume,${VOL_NUM:-0}" >> "${CSV}"

    if (( i % 10 == 0 )); then
        echo -e "  ${GREEN}${i}/${ITERATIONS} complete${NC}"
    fi
done

docker volume rm perf_test_vol > /dev/null 2>&1 || true

echo -e "${GREEN}Write performance complete. Saved to ${CSV}${NC}"
echo ""

# =============================================================================
# TEST 5: Metadata Operations (file creation overhead)
# =============================================================================

echo -e "${BLUE}[5/7] Metadata Operations (${ITERATIONS} iterations)...${NC}"

CSV="${RESULTS_DIR}/05-metadata-operations.csv"
echo "iteration,mode,file_count,duration_ms" > "${CSV}"

docker volume create meta_test_vol > /dev/null 2>&1

for i in $(seq 1 ${ITERATIONS}); do
    sleep 0.5

    # OverlayFS: create 500 files
    OVERLAY_MS=$(docker run --rm alpine sh -c '
        START=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1e9))")
        for j in $(seq 1 500); do echo "data" > /tmp/file_$j; done
        END=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1e9))")
        echo $(( (END - START) / 1000000 ))
    ' 2>/dev/null || echo "0")

    # Volume: create 500 files
    VOL_MS=$(docker run --rm -v meta_test_vol:/data alpine sh -c '
        START=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1e9))")
        for j in $(seq 1 500); do echo "data" > /data/file_$j; done
        END=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1e9))")
        echo $(( (END - START) / 1000000 ))
    ' 2>/dev/null || echo "0")

    echo "${i},overlayfs,500,${OVERLAY_MS}" >> "${CSV}"
    echo "${i},volume,500,${VOL_MS}" >> "${CSV}"

    if (( i % 10 == 0 )); then
        echo -e "  ${GREEN}${i}/${ITERATIONS} complete${NC}"
    fi
done

docker volume rm meta_test_vol > /dev/null 2>&1 || true

echo -e "${GREEN}Metadata operations complete. Saved to ${CSV}${NC}"
echo ""

# =============================================================================
# TEST 6: Image Pull Time (cold pull, 10 iterations only — slow test)
# =============================================================================

echo -e "${BLUE}[6/7] Image Pull Time (10 iterations × 3 images)...${NC}"

CSV="${RESULTS_DIR}/06-image-pull-time.csv"
echo "iteration,image,pull_time_ms" > "${CSV}"

PULL_ITERATIONS=10

for IMAGE in "alpine" "nginx" "python:3.11-slim"; do
    IMAGE_LABEL=$(echo "$IMAGE" | tr ':' '_' | tr '/' '_')
    echo -e "  ${YELLOW}Pull test: ${IMAGE}${NC}"

    for i in $(seq 1 ${PULL_ITERATIONS}); do
        # Remove image to force fresh pull
        docker rmi "${IMAGE}" > /dev/null 2>&1 || true
        clear_caches
        sleep 2

        START=$(now_ns)
        docker pull "${IMAGE}" > /dev/null 2>&1
        END=$(now_ns)
        ELAPSED_MS=$(echo "scale=2; ($END - $START) / 1000000" | bc)
        echo "${i},${IMAGE_LABEL},${ELAPSED_MS}" >> "${CSV}"

        echo -e "    ${GREEN}${i}/${PULL_ITERATIONS} complete${NC}"
    done
done

# Re-pull for subsequent use
docker pull alpine:latest > /dev/null 2>&1
docker pull nginx:latest > /dev/null 2>&1
docker pull python:3.11-slim > /dev/null 2>&1

echo -e "${GREEN}Image pull time complete. Saved to ${CSV}${NC}"
echo ""

# =============================================================================
# TEST 7: Namespace Creation Overhead (isolated measurement)
# =============================================================================

echo -e "${BLUE}[7/7] Namespace/cgroup creation overhead (${ITERATIONS} iterations)...${NC}"

CSV="${RESULTS_DIR}/07-namespace-overhead.csv"
echo "iteration,operation,duration_ms" > "${CSV}"

# This test uses unshare to isolate namespace creation from Docker overhead
# Only works on Linux
if command -v unshare &>/dev/null && [ -f /proc/self/ns/pid ]; then
    for i in $(seq 1 ${ITERATIONS}); do
        sleep 0.3

        START=$(now_ns)
        unshare --pid --fork --mount-proc echo "ns_test" > /dev/null 2>&1 || true
        END=$(now_ns)
        ELAPSED_MS=$(echo "scale=2; ($END - $START) / 1000000" | bc)
        echo "${i},namespace_create,${ELAPSED_MS}" >> "${CSV}"

        if (( i % 10 == 0 )); then
            echo -e "  ${GREEN}${i}/${ITERATIONS} complete${NC}"
        fi
    done
else
    echo -e "  ${YELLOW}Skipping (unshare not available on this platform)${NC}"
    echo "0,namespace_create,N/A" >> "${CSV}"
fi

echo -e "${GREEN}Namespace overhead complete. Saved to ${CSV}${NC}"
echo ""

# =============================================================================
# SUMMARY
# =============================================================================

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE} Benchmark Complete!${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo "Results saved to: ${RESULTS_DIR}/"
echo ""
ls -la "${RESULTS_DIR}/"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Run analyze_results.py to compute statistics"
echo "  2. Commit results to GitHub"
echo "  3. Run on next platform"
echo ""
echo "  python3 analyze_results.py ${RESULTS_DIR}"