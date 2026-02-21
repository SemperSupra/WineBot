# Build Performance & Resource Utilization Report

This report analyzes the WineBot build process, identifies resource-heavy stages, and proposes strategies for optimization.

## 1. Build Performance Metrics (Baseline)

Based on a clean `--no-cache` build of the `intent-test` target (Total Time: ~650s):

| Stage | Task | Time (s) | Resource Impact |
| :--- | :--- | :--- | :--- |
| **base-system** | OS, Wine, X11, Python Install | ~180s | High CPU/Network |
| **prefix-warmer**| Wine Registry & Theme Init | ~160s | High CPU (Xvfb/Wine) |
| **exporting** | Image Layer Compression | ~130s | High Disk I/O |
| **tools-builder** | Windows Binaries Download | ~50s | Moderate Network |
| **base-logic** | Application Code Copy | ~15s | Low |

### Analysis of High-Resource Tasks
1. **`base-system` (Apt)**: Installing Wine 10.0 and its multi-arch (i386) dependencies is the single largest consumer of network and time.
2. **`prefix-warmer`**: Running a full Xvfb session during build to initialize the Wine Registry is computationally expensive and serializes the build process.
3. **`exporting`**: Due to the large size of the pre-warmed prefix (~1.4GB), Docker spends significant time compressing and writing layers.

---

## 2. Strategies for Optimization

### Strategy A: True Base Image Split (Recommended)
**Recommendation**: Decouple the "System" from the "Application."
- **Action**: Move everything in `base-system` and `prefix-warmer` into a separate repository or a dedicated `base.Dockerfile`.
- **Benefit**: Reduces local build time from 10 minutes to **under 60 seconds** for 95% of developer iterations (code changes).
- **Tradeoff**: Infrastructure management overhead (maintaining two images).

### Strategy B: Parallelize Tool Downloads
**Recommendation**: Use multi-stage builds more effectively for tool fetching.
- **Action**: Current `tools-builder` downloads binaries sequentially. Refactor to use separate stages per tool, allowing Docker to fetch AutoIt, AHK, and Python in parallel.
- **Benefit**: Saves ~30s on cold builds.

### Strategy C: Optimize Layer Caching
**Recommendation**: Reorder layers to minimize cache invalidation.
- **Action**: Move the `VERSION` file copy to the very end of the `base-logic` stage. Currently, every version bump invalidates the code copy and permission fixing layers.
- **Benefit**: Prevents redundant `chown -R` runs (which take ~10s).

---

## 3. Recommended Actions

| Item | Action | Priority | Options |
| :--- | :--- | :--- | :--- |
| **1. Registry Split** | Move Wine/System layers to permanent base image. | **Critical** | Ignore/Implement/Defer |
| **2. Cache Reorder** | Move `VERSION` and `Dockerfile` copies to final layers. | **High** | Ignore/Implement/Defer |
| **3. Parallel Fetch** | Refactor `download_tools.sh` into parallel Docker stages. | **Medium** | Ignore/Implement/Defer |

**How would you like to proceed?** I recommend implementing **Item 2** immediately as it is a pure win with zero tradeoffs. For **Item 1**, I can prepare the `base.Dockerfile` if you want to move toward a multi-repo/image structure.
