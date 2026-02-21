# Scalability Guide

This document outlines the architectural best practices for scaling WineBot from a single container to a large-scale automation fleet.

## 1. Multi-Instance Scaling

WineBot is designed to be horizontally scalable by running multiple containers. However, to avoid resource contention and corruption, follow these rules:

### A. Unique WINEPREFIX
Each WineBot instance **MUST** have its own unique `WINEPREFIX`. Wine's registry (`system.reg`) and RPC socket (`wineserver`) do not support concurrent access from multiple processes across different containers.
- **Implementation**: Use the `WINEPREFIX_VOL` environment variable in `docker-compose.yml` to map unique named volumes or host paths.

### B. Display Isolation
Each instance requires a unique X11 `DISPLAY` ID (e.g., `:99`, `:100`).
- **Implementation**: The `DISPLAY` environment variable is already configurable. Ensure it matches the mapping in your orchestrator (e.g., Kubernetes).

### C. Port Mapping
If using interactive mode, each instance must map host ports (`8000`, `5900`, `6080`) to unique values.

## 2. Resource Optimization

### A. Slim Build Intent
For high-density scaling, use the `BUILD_INTENT=slim` image. This reduces image size and startup overhead by skipping the 1.4GB prefix pre-warming, making it ideal for ephemeral CI runners.

### B. Inactivity Auto-Pause
Enable `WINEBOT_INACTIVITY_PAUSE_SECONDS` to automatically stop the CPU-intensive FFmpeg recorder when no automation activity is detected. This significantly reduces host CPU load when scaling many idle nodes.

## 3. Log Performance (O(1) Retrieval)

WineBot uses backward-seeking (`f.seek`) for all log event retrieval (`/input/events`, `/lifecycle/events`). This ensures that even if a session generates gigabytes of trace data, the API response time for the last 100 events remains constant and does not consume excessive memory.

## 4. Discovery & Management

### Local Network (mDNS)
Use the built-in mDNS discovery to locate nodes on the local network. The "WineBot Hub" pattern allows a single management plane to aggregate state from many distributed containers.

### Fleet Management
For deployments exceeding 50 nodes, we recommend using **Kubernetes** with the `rel-runner` intent. Since `rel-runner` lacks the VNC overhead, it offers the highest density for raw automation workloads.
