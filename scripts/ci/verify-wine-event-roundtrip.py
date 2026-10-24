#!/usr/bin/env python3
"""Verify a bounded synthetic Wine event stream through the session-local adapter.

Fail closed and emit only fixed public status lines; never echo raw events.
"""
import json
import sys
from event_bridge import EventBridge


def fail(reason: str) -> int:
    print("FAIL: " + reason)
    return 1


def main() -> int:
    if len(sys.argv) != 2:
        return fail("bridge_usage")
    try:
        # readlines(131) is a *byte hint*, not a maximum line count. It can
        # silently omit the show/location records after a valid ready header.
        # Bound actual bytes independently of file metadata / concurrent writes.
        with open(sys.argv[1], "rb") as stream:
            data = stream.read(24_577)
        if len(data) > 24_576:
            return fail("bridge_input_oversized")
        if not data.endswith(b"\n"):
            return fail("bridge_input_incomplete")
        lines = data.decode("utf-8").splitlines(keepends=True)
    except (OSError, UnicodeError):
        return fail("bridge_input_read")
    if not 1 <= len(lines) <= 130:
        return fail("bridge_input_count")
    # Independent fixed-schema source check; print classification only, never data.
    try:
        source_records = [json.loads(line) for line in lines]
        source_kinds = {x["kind"] for x in source_records}
    except (ValueError, TypeError, KeyError):
        return fail("roundtrip_invalid_source")
    if not {"show", "location"}.issubset(source_kinds):
        return fail("roundtrip_source_disagrees_with_validator")
    print("PASS: adapter_source_fixture_semantics")
    bridge = EventBridge(capacity=128)
    for line in lines:
        if not bridge.ingest(line):
            return fail("bridge_ingest")
    # Cursor-paged consumption models concurrent, read-only audience views.
    observed = []
    cursor = 0
    for _ in range(130):
        view = bridge.observe(after=cursor, limit=3)
        if view["state"] != "ready":
            return fail("bridge_snapshot")
        observed.extend(view["events"])
        if not view["events"]:
            break
        cursor = view["next_cursor"]
    else:
        return fail("bridge_cursor_loop")
    kinds = {x["kind"] for x in observed}
    if not {"show", "location"}.issubset(kinds):
        return fail("bridge_projection_disagrees_with_source")
    if not observed:
        return fail("bridge_empty")
    bridge.close()
    if bridge.observe()["events"]:
        return fail("bridge_close")
    print("PASS: live_wine_event_adapter_ingest")
    print("PASS: live_wine_event_cursor_readback")
    print("PASS: live_wine_event_close_clears_state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
