# Docker Security Hardening: Production Configuration Examples

This document provides battle-tested security configurations for Docker containers, complementing the "Beyond Containers" technical article.

## Table of Contents
1. [Minimal Capability Container](#minimal-capability-container)
2. [Seccomp Profiles](#seccomp-profiles)
3. [AppArmor/SELinux Policies](#apparmorselinux-policies)
4. [User Namespace Remapping](#user-namespace-remapping)
5. [Network Isolation Patterns](#network-isolation-patterns)
6. [Read-Only Root Filesystem](#read-only-root-filesystem)
7. [Resource Limits](#resource-limits)
8. [Image Signing & Verification](#image-signing--verification)

---

## Minimal Capability Container

Drop all capabilities and add back only what's needed:

```bash
# Absolute minimum for most applications
docker run -d \
  --name minimal-app \
  --cap-drop=ALL \
  --cap-add=CHOWN \
  --cap-add=SETUID \
  --cap-add=SETGID \
  --cap-add=NET_BIND_SERVICE \
  --security-opt=no-new-privileges \
  --read-only \
  --tmpfs /tmp \
  --tmpfs /run \
  myapp:latest
```

### Capability Reference

| Capability | Purpose | Risk if granted |
|-----------|---------|----------------|
| CAP_CHOWN | Change file ownership | Medium - can chown to other users |
| CAP_DAC_OVERRIDE | Bypass file permissions | HIGH - read/write any file |
| CAP_NET_BIND_SERVICE | Bind to ports <1024 | Low - networking only |
| CAP_NET_RAW | Raw socket operations | HIGH - network sniffing/spoofing |
| CAP_SYS_ADMIN | Mount filesystems, more | CRITICAL - near-root equivalent |
| CAP_SYS_PTRACE | Trace processes | HIGH - can inspect other containers |
| CAP_SYS_MODULE | Load kernel modules | CRITICAL - kernel-level access |

### Check Current Capabilities

```bash
# Inside container
cat /proc/self/status | grep Cap

# Decode capabilities (requires libcap2-bin)
capsh --decode=00000000a80425fb

# List all capabilities for running container
docker exec myapp sh -c 'cat /proc/1/status | grep Cap'
```

---

## Seccomp Profiles

### Strict Seccomp Profile

Create `strict-seccomp.json`:

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "defaultErrnoRet": 1,
  "archMap": [
    {
      "architecture": "SCMP_ARCH_X86_64",
      "subArchitectures": [
        "SCMP_ARCH_X86",
        "SCMP_ARCH_X32"
      ]
    }
  ],
  "syscalls": [
    {
      "names": [
        "accept",
        "accept4",
        "access",
        "bind",
        "brk",
        "chdir",
        "chmod",
        "chown",
        "clock_gettime",
        "clone",
        "close",
        "connect",
        "dup",
        "dup2",
        "epoll_create",
        "epoll_ctl",
        "epoll_wait",
        "execve",
        "exit",
        "exit_group",
        "fcntl",
        "fstat",
        "fstatfs",
        "futex",
        "getcwd",
        "getdents",
        "getegid",
        "geteuid",
        "getgid",
        "getpid",
        "getppid",
        "getrlimit",
        "getsockname",
        "getsockopt",
        "gettid",
        "getuid",
        "ioctl",
        "listen",
        "lseek",
        "madvise",
        "mmap",
        "mprotect",
        "munmap",
        "nanosleep",
        "open",
        "openat",
        "pipe",
        "poll",
        "read",
        "recvfrom",
        "recvmsg",
        "rt_sigaction",
        "rt_sigprocmask",
        "rt_sigreturn",
        "sendmsg",
        "sendto",
        "set_robust_list",
        "setsockopt",
        "shutdown",
        "sigaltstack",
        "socket",
        "stat",
        "statfs",
        "write"
      ],
      "action": "SCMP_ACT_ALLOW"
    }
  ]
}
```

Apply profile:

```bash
docker run --security-opt seccomp=strict-seccomp.json myapp
```

### Audit Mode (Log Blocked Syscalls)

```json
{
  "defaultAction": "SCMP_ACT_LOG",
  "syscalls": [
    {
      "names": ["mount", "umount2", "ptrace", "process_vm_readv"],
      "action": "SCMP_ACT_ERRNO"
    }
  ]
}
```

Check kernel logs for blocked syscalls:

```bash
dmesg | grep seccomp
journalctl -k | grep audit
```

---

## AppArmor/SELinux Policies

### AppArmor Profile

Create `/etc/apparmor.d/docker-myapp`:

```
#include <tunables/global>

profile docker-myapp flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>
  
  # Network access
  network inet tcp,
  network inet udp,
  
  # Allow reading specific directories
  /app/** r,
  /usr/lib/** r,
  /usr/bin/** r,
  
  # Allow writing to logs only
  /var/log/myapp/** rw,
  
  # Deny everything else
  /** deny,
  
  # Deny raw socket operations
  deny network raw,
  deny network packet,
  
  # Deny capability escalation
  deny capability sys_admin,
  deny capability sys_module,
  deny capability sys_ptrace,
  
  # Allow minimal capabilities
  capability chown,
  capability setuid,
  capability setgid,
  capability net_bind_service,
}
```

Load profile:

```bash
sudo apparmor_parser -r /etc/apparmor.d/docker-myapp

# Run container with profile
docker run --security-opt apparmor=docker-myapp myapp
```

### SELinux Context

```bash
# Run container with confined SELinux type
docker run --security-opt label=type:svirt_sandbox_file_t myapp

# View SELinux denials
ausearch -m avc -ts recent
```

---

## User Namespace Remapping

### Enable Userns Remap

Edit `/etc/docker/daemon.json`:

```json
{
  "userns-remap": "default",
  "userns-remap": "dockremap:dockremap"
}
```

Or manually:

```json
{
  "userns-remap": "testuser"
}
```

Create subuid/subgid mappings:

```bash
# /etc/subuid
testuser:100000:65536

# /etc/subgid
testuser:100000:65536
```

Restart Docker:

```bash
systemctl restart docker
```

Verify remapping:

```bash
# Inside container: uid=0
docker run --rm alpine id
# uid=0(root) gid=0(root)

# On host: uid=100000
ps aux | grep alpine
# 100000 ... /bin/sh
```

### Limitations of Userns

- Cannot use host networking (--network host)
- Some volume mounts may have permission issues
- Privileged mode disabled
- Device access limited

---

## Network Isolation Patterns

### Internal Networks (No Internet)

```bash
# Create isolated network
docker network create --internal isolated-net

# Containers can communicate but no external access
docker run -d --network isolated-net --name db postgres
docker run -d --network isolated-net --name app myapp

# Test: app can reach db, but not internet
docker exec app ping db  # Works
docker exec app ping 8.8.8.8  # Fails
```

### Network Segmentation

```bash
# Frontend network (internet-facing)
docker network create frontend

# Backend network (internal only)
docker network create --internal backend

# Database on backend only
docker run -d --network backend --name db postgres

# API server on both networks
docker run -d --name api myapp
docker network connect frontend api
docker network connect backend api

# Frontend on frontend only
docker run -d --network frontend --name web nginx
```

### Egress Filtering

```bash
# Allow only specific destinations
docker run -d \
  --name restricted \
  --cap-add=NET_ADMIN \
  --cap-add=NET_RAW \
  myapp

# Inside container, set up iptables
docker exec restricted iptables -A OUTPUT -d 10.0.0.0/8 -j ACCEPT
docker exec restricted iptables -A OUTPUT -d 192.168.0.0/16 -j ACCEPT
docker exec restricted iptables -A OUTPUT -j DROP
```

---

## Read-Only Root Filesystem

Force immutable containers:

```bash
docker run -d \
  --read-only \
  --tmpfs /tmp:rw,size=100m,mode=1777 \
  --tmpfs /run:rw,size=50m \
  --tmpfs /var/log:rw,size=200m \
  --name immutable \
  myapp
```

### Dockerfile Best Practices for Read-Only

```dockerfile
FROM alpine:latest

# Create non-root user
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Copy app
COPY --chown=appuser:appgroup app /app

# Create directories for tmpfs mounts
RUN mkdir -p /tmp /run /var/log && \
    chown appuser:appgroup /tmp /run /var/log

USER appuser

CMD ["/app/server"]
```

---

## Resource Limits

### Comprehensive Limits

```bash
docker run -d \
  --name limited-app \
  \
  # Memory limits
  --memory=512m \
  --memory-reservation=256m \
  --memory-swap=512m \
  --oom-kill-disable=false \
  \
  # CPU limits
  --cpus=1.5 \
  --cpu-shares=1024 \
  --cpuset-cpus=0-1 \
  \
  # I/O limits
  --device-read-bps=/dev/sda:10mb \
  --device-write-bps=/dev/sda:5mb \
  \
  # Process limits
  --pids-limit=100 \
  \
  # File descriptor limits
  --ulimit nofile=1024:2048 \
  \
  myapp
```

### Monitor Resource Usage

```bash
# Real-time stats
docker stats limited-app

# Check cgroup limits
docker inspect limited-app | jq '.[0].HostConfig'

# Detailed cgroup metrics
cat /sys/fs/cgroup/system.slice/docker-<ID>.scope/memory.max
cat /sys/fs/cgroup/system.slice/docker-<ID>.scope/cpu.stat
```

---

## Image Signing & Verification

### Docker Content Trust (Notary v1)

```bash
# Enable content trust
export DOCKER_CONTENT_TRUST=1

# Sign image during push
docker tag myapp:latest registry.example.com/myapp:v1.0
docker push registry.example.com/myapp:v1.0
# Prompts for root and repository key passphrase

# Pull only signed images
docker pull registry.example.com/myapp:v1.0
```

### Cosign (Modern Approach)

```bash
# Generate key pair
cosign generate-key-pair

# Sign image
cosign sign --key cosign.key myregistry.com/myapp:v1

# Verify before running
cosign verify --key cosign.pub myregistry.com/myapp:v1

# Integration with Kubernetes
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: cosign-keys
data:
  cosign.pub: |
    -----BEGIN PUBLIC KEY-----
    ...
    -----END PUBLIC KEY-----
EOF
```

### Policy Controller (Sigstore)

```yaml
# Kubernetes admission controller
apiVersion: policy.sigstore.dev/v1alpha1
kind: ClusterImagePolicy
metadata:
  name: require-signed-images
spec:
  images:
    - glob: "myregistry.com/*"
  authorities:
    - keyless:
        url: https://fulcio.sigstore.dev
        identities:
          - issuer: https://token.actions.githubusercontent.com
            subject: https://github.com/myorg/*
```

---

## Complete Production Example

Combining all best practices:

```bash
#!/bin/bash

# Create secure network
docker network create --internal app-net

# Run hardened application container
docker run -d \
  --name production-app \
  \
  # Network
  --network app-net \
  --dns 8.8.8.8 \
  --hostname app-server \
  \
  # Security
  --cap-drop=ALL \
  --cap-add=NET_BIND_SERVICE \
  --security-opt=no-new-privileges \
  --security-opt=seccomp=strict-seccomp.json \
  --security-opt=apparmor=docker-default \
  --read-only \
  \
  # Filesystem
  --tmpfs /tmp:rw,noexec,nosuid,size=100m \
  --tmpfs /run:rw,noexec,nosuid,size=50m \
  -v /app/data:/data:ro \
  -v app-logs:/var/log \
  \
  # Resources
  --memory=2g \
  --memory-reservation=1g \
  --memory-swap=2g \
  --cpus=2.0 \
  --pids-limit=200 \
  \
  # Restart policy
  --restart=unless-stopped \
  \
  # Logging
  --log-driver=json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  \
  # Health check
  --health-cmd='curl -f http://localhost:8080/health || exit 1' \
  --health-interval=30s \
  --health-timeout=5s \
  --health-retries=3 \
  \
  myapp:v1.0.0@sha256:abcdef123456...

echo "Container started with hardened security profile"
docker logs -f production-app
```

---

## Security Checklist

Before deploying containers to production, verify:

- [ ] Running as non-root user (USER directive in Dockerfile)
- [ ] Minimal base image (alpine, distroless, scratch)
- [ ] All capabilities dropped except necessary ones
- [ ] No privileged mode (--privileged)
- [ ] No Docker socket mounted (-v /var/run/docker.sock)
- [ ] Read-only root filesystem where possible
- [ ] Tmpfs for writable directories
- [ ] Resource limits set (memory, CPU, PIDs)
- [ ] Seccomp profile applied
- [ ] AppArmor/SELinux profile configured
- [ ] User namespace remapping enabled
- [ ] Network isolation configured
- [ ] No host networking (--network host)
- [ ] Image signed and verified
- [ ] No secrets in environment variables (use secrets management)
- [ ] Health checks configured
- [ ] Log rotation configured
- [ ] Restart policy appropriate for workload

---

## Automated Security Scanning

### Trivy (Vulnerability Scanner)

```bash
# Scan image for CVEs
trivy image myapp:latest

# Scan with severity threshold
trivy image --severity HIGH,CRITICAL myapp:latest

# Scan filesystem
trivy fs /path/to/code

# CI/CD integration
trivy image --exit-code 1 --severity CRITICAL myapp:latest
```

### Docker Bench Security

```bash
# Run Docker CIS benchmark
docker run --rm \
  --net host \
  --pid host \
  --userns host \
  --cap-add audit_control \
  -e DOCKER_CONTENT_TRUST=$DOCKER_CONTENT_TRUST \
  -v /var/lib:/var/lib \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /etc:/etc \
  --label docker_bench_security \
  docker/docker-bench-security
```

---

## Incident Response

### Suspicious Container Detection

```bash
# Find privileged containers
docker ps --filter "status=running" --format "{{.Names}}" | while read c; do
  docker inspect $c --format='{{.HostConfig.Privileged}} {{.Name}}'
done | grep true

# Find containers with Docker socket
docker ps --format "{{.Names}}" | while read c; do
  docker inspect $c --format='{{range .Mounts}}{{if eq .Source "/var/run/docker.sock"}}{{$.Name}}{{end}}{{end}}'
done

# Find containers with host PID namespace
docker ps --format "{{.Names}}" | while read c; do
  docker inspect $c --format='{{.HostConfig.PidMode}} {{.Name}}'
done | grep host
```

### Container Forensics

```bash
# Capture container state before stopping
docker pause suspicious-container
docker export suspicious-container > suspicious-container.tar
docker cp suspicious-container:/var/log /tmp/container-logs

# Inspect network connections
docker exec suspicious-container netstat -tunap

# Check process tree
docker exec suspicious-container ps auxf

# Examine filesystem changes
docker diff suspicious-container

# Extract binary for analysis
docker cp suspicious-container:/suspicious/binary /tmp/malware-sample

# Now safe to stop
docker stop suspicious-container
docker rm suspicious-container
```

---

## References

- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker)
- [NIST Container Security Guide](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-190.pdf)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [Seccomp Documentation](https://docs.docker.com/engine/security/seccomp/)
- [AppArmor for Docker](https://docs.docker.com/engine/security/apparmor/)
- [Sigstore Project](https://www.sigstore.dev/)

---

**Last Updated**: October 2025  
**Tested On**: Docker Engine 28.0, containerd 2.1, Ubuntu 24.04