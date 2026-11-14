"""Portable health/system resource contract, using synthetic memory data only."""

from unittest.mock import patch

from api.routers.health import health_system


def test_health_system_reports_byte_normalized_memory_without_dropping_legacy_fields():
    with patch(
        "api.routers.health.meminfo_summary",
        return_value={"mem_total_kb": 4096, "mem_available_kb": 1024},
    ), patch(
        "api.core.discovery.discovery_manager.status", return_value={}
    ), patch(
        "api.routers.health.platform.node", return_value="synthetic-test-host"
    ):
        payload = health_system()

    assert payload["memory"] == {
        "total_bytes": 4096 * 1024,
        "available_bytes": 1024 * 1024,
    }
    assert payload["mem_total_kb"] == 4096
    assert payload["mem_available_kb"] == 1024
    assert "cpu_count" in payload


def test_health_system_memory_shape_remains_defined_without_proc_meminfo():
    with patch(
        "api.routers.health.meminfo_summary", return_value={}
    ), patch(
        "api.core.discovery.discovery_manager.status", return_value={}
    ):
        payload = health_system()

    assert payload["memory"] == {"total_bytes": 0, "available_bytes": 0}
