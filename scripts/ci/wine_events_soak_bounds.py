"""Synthetic Wine RDTE: finite cgroup-v2 resource envelope, not host telemetry.

The scope is the entire disposable, network-disabled container; these
measurements CANNOT be attributed to the Wine observer process alone.
No machine identity, raw /proc dumps, filesystem secrets or verbose logs.
"""
from dataclasses import dataclass
from pathlib import Path


class ResourceUnqualified(Exception):
    """Fixed-class local failure. Never print underlying OS errors."""


@dataclass(frozen=True)
class ResourceSample:
    elapsed: float
    cpu_usec: int
    memory_bytes: int
    pids: int
    oom_kill: int


def _nonnegative_integer(value):
    if not value.isdecimal():
        raise ResourceUnqualified("invalid_metric")
    return int(value)


def read_cgroup_v2(root="/sys/fs/cgroup", *, elapsed=0.0):
    """Read only four bounded, nonsensitive aggregate cgroup counters."""
    try:
        base = Path(root)
        cpu = {}
        for line in (base / "cpu.stat").read_text(encoding="ascii").splitlines():
            fields = line.split()
            if len(fields) != 2 or fields[0] in cpu:
                raise ResourceUnqualified("invalid_cpu_stat")
            cpu[fields[0]] = _nonnegative_integer(fields[1])
        events = {}
        for line in (base / "memory.events").read_text(encoding="ascii").splitlines():
            fields = line.split()
            if len(fields) != 2 or fields[0] in events:
                raise ResourceUnqualified("invalid_mem_stat")
            events[fields[0]] = _nonnegative_integer(fields[1])
        memory = _nonnegative_integer((base / "memory.current").read_text().strip())
        pids = _nonnegative_integer((base / "pids.current").read_text().strip())
        if "usage_usec" not in cpu or "oom_kill" not in events:
            raise ResourceUnqualified("missing_cgroup_metric")
    except (OSError, UnicodeError, ValueError) as exc:
        raise ResourceUnqualified("metrics_unavailable") from None
    if type(elapsed) not in (float, int) or elapsed < 0:
        raise ResourceUnqualified("invalid_sample_clock")
    return ResourceSample(float(elapsed), cpu["usage_usec"],
                          memory, pids, events["oom_kill"])


def assess_envelope(samples, *, quiet_stop_seconds):
    """Enforce limits on measured cgroup data; output only a safe verdict.

    Container hard caps are 4GiB and 256 PIDs at Docker admission. The
    softer headroom here detects runaway consumption before reaching caps.
    """
    if len(samples) < 45 or samples[-1].elapsed - samples[0].elapsed < 60:
        return "soak_insufficient_duration"
    if not (15 <= quiet_stop_seconds <= 30):
        return "soak_bad_quiet_window"
    last = samples[0]
    if last.elapsed < 0 or min(last.cpu_usec, last.memory_bytes,
                               last.pids, last.oom_kill) < 0:
        return "soak_invalid_measurement"
    for now in samples[1:]:
        if (now.elapsed <= last.elapsed or now.cpu_usec < last.cpu_usec
                or now.oom_kill < last.oom_kill or
                min(now.cpu_usec, now.memory_bytes, now.pids, now.oom_kill) < 0):
            return "soak_invalid_measurement"
        last = now
    if any(s.oom_kill != samples[0].oom_kill for s in samples):
        return "soak_oom_kill"
    if max(s.memory_bytes for s in samples) >= 3 * 1024 ** 3 + 512 * 1024 ** 2:
        return "soak_memory_ceiling"
    if max(s.pids for s in samples) >= 220:
        return "soak_pid_ceiling"
    if max(s.memory_bytes for s in samples) - samples[0].memory_bytes >= 1024 ** 3:
        return "soak_memory_growth"
    # Includes all Wine/Xvfb/API and synthetic fixture activity. Not
    # observer-specific CPU. A 2-vCPU cgroup has at most ~2e6 us/sec.
    elapsed = samples[-1].elapsed - samples[0].elapsed
    if samples[-1].cpu_usec - samples[0].cpu_usec > elapsed * 2_200_000:
        return "soak_cpu_accounting"
    first_quiet = samples[0]
    quiet = next((s for s in samples if s.elapsed >= quiet_stop_seconds), None)
    if quiet is None or quiet.elapsed - first_quiet.elapsed < 14:
        return "soak_insufficient_quiet"
    # Bound aggregate idle CPU to under one full core (50% of 2-vCPU quota).
    if (quiet.cpu_usec - first_quiet.cpu_usec >
            (quiet.elapsed - first_quiet.elapsed) * 1_000_000):
        return "soak_busy_quiet"
    return "ok"
