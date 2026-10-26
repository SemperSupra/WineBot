"""Fast deterministic red-team coverage for bounded synthetic cgroup receipts."""
import tempfile
import unittest
from pathlib import Path

from scripts.ci.wine_events_soak_bounds import (
    ResourceSample, ResourceUnqualified, assess_envelope, read_cgroup_v2,
)


def series(count=70, *, cpu_step=10_000, mem_step=0, pid=24):
    return [
        ResourceSample(float(i), 2_000_000 + i * cpu_step,
                       200_000_000 + i * mem_step, pid, 0)
        for i in range(count)
    ]


class SoakBoundsTests(unittest.TestCase):
    def test_nominal_observation(self):
        self.assertEqual(assess_envelope(series(), quiet_stop_seconds=20), "ok")

    def test_duration_and_sample_count(self):
        self.assertEqual(assess_envelope(series(44), quiet_stop_seconds=20),
                         "soak_insufficient_duration")
        samples = series()
        self.assertEqual(assess_envelope([samples[0], samples[-1]],
                                         quiet_stop_seconds=20),
                         "soak_insufficient_duration")

    def test_memory_ceiling_and_growth(self):
        self.assertEqual(assess_envelope(series(mem_step=55_000_000),
                                         quiet_stop_seconds=20), "soak_memory_ceiling")
        self.assertEqual(assess_envelope(series(mem_step=17_000_000),
                                         quiet_stop_seconds=20), "soak_memory_growth")

    def test_pid_and_oom_caps(self):
        self.assertEqual(assess_envelope(series(pid=220), quiet_stop_seconds=20),
                         "soak_pid_ceiling")
        values = series()
        values[35] = ResourceSample(35.0, values[35].cpu_usec, 200_000_000, 24, 1)
        for i in range(36, len(values)):
            values[i] = ResourceSample(float(i), values[i].cpu_usec, 200_000_000, 24, 1)
        self.assertEqual(assess_envelope(values, quiet_stop_seconds=20),
                         "soak_oom_kill")

    def test_clock_reversal_and_cpu_counter_loss(self):
        values = series()
        values[25] = ResourceSample(24.0, values[25].cpu_usec, 200_000_000, 24, 0)
        self.assertEqual(assess_envelope(values, quiet_stop_seconds=20),
                         "soak_invalid_measurement")
        values = series()
        values[25] = ResourceSample(25.0, 1, 200_000_000, 24, 0)
        self.assertEqual(assess_envelope(values, quiet_stop_seconds=20),
                         "soak_invalid_measurement")

    def test_busy_quiet_window(self):
        self.assertEqual(assess_envelope(series(cpu_step=1_100_000),
                                         quiet_stop_seconds=20), "soak_busy_quiet")

    def test_read_actual_cgroup_shape_with_synthetic_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "cpu.stat").write_text("usage_usec 250\nuser_usec 100\n")
            (root / "memory.current").write_text("4096\n")
            (root / "pids.current").write_text("3\n")
            (root / "memory.events").write_text("low 0\noom_kill 0\n")
            x = read_cgroup_v2(root, elapsed=4.0)
            self.assertEqual((x.elapsed, x.cpu_usec, x.memory_bytes, x.pids),
                             (4.0, 250, 4096, 3))

    def test_missing_metric_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ResourceUnqualified):
                read_cgroup_v2(td)

    def test_malformed_duplicate_and_negative_metric(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "cpu.stat").write_text("usage_usec -7\n")
            (root / "memory.current").write_text("100\n")
            (root / "pids.current").write_text("2\n")
            (root / "memory.events").write_text("oom_kill 0\n")
            with self.assertRaises(ResourceUnqualified):
                read_cgroup_v2(root)


if __name__ == "__main__":
    unittest.main()
