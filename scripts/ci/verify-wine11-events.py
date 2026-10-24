#!/usr/bin/env python3
"""Fail-closed public-safe schema validator for synthetic Wine WinEvent data.

The script never prints the content of its input, only fixed generic verdicts.
"""
import json
import pathlib
import sys

SCHEMA = "winebot.wine.event.v1"
KINDS = frozenset({
    "ready", "create", "show", "hide", "destroy",
    "focus", "location", "foreground",
})
ALLOWED_KEYS = frozenset({"schema", "kind", "sequence"})


def validate(lines: list[str]) -> tuple[bool, str]:
    if not 1 <= len(lines) <= 130:
        return False, "event_count"
    parsed = []
    try:
        for line in lines:
            obj = json.loads(line)
            if (
                not isinstance(obj, dict)
                or set(obj) != ALLOWED_KEYS
                or obj["schema"] != SCHEMA
                or obj["kind"] not in KINDS
                or type(obj["sequence"]) is not int
                or obj["sequence"] < 0
            ):
                return False, "schema"
            parsed.append(obj)
    except (ValueError, TypeError):
        return False, "json"
    if parsed[0]["kind"] != "ready" or parsed[0]["sequence"] != 0:
        return False, "ready"
    seq = [record["sequence"] for record in parsed[1:]]
    if seq != list(range(1, len(seq) + 1)):
        return False, "sequence"
    observed = {record["kind"] for record in parsed}
    if not {"show", "location"}.issubset(observed):
        return False, "missing_event"
    return True, "synthetic_events"


def self_test() -> bool:
    good = [
        '{"schema":"winebot.wine.event.v1","kind":"ready","sequence":0}',
        '{"schema":"winebot.wine.event.v1","kind":"show","sequence":1}',
        '{"schema":"winebot.wine.event.v1","kind":"location","sequence":2}',
    ]
    adversarial = [
        [good[0], good[1]],
        [good[0], good[2], good[1]],
        [good[0], '{"schema":"winebot.wine.event.v1","kind":"show","sequence":1,"hwnd":"sensitive"}', good[2]],
        [good[0], '{"schema":"winebot.wine.event.v1","kind":"overflow","sequence":1}', good[2]],
        [good[0], '{"schema":"winebot.wine.event.v1","kind":"show","sequence":true}', good[2]],
        [good[0]] * 131,
        ['not-json'],
    ]
    return validate(good)[0] and all(not validate(case)[0] for case in adversarial)


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        if self_test():
            print("PASS: event_schema_self_test")
            return 0
        print("FAIL: event_schema_self_test")
        return 1
    if len(sys.argv) != 2:
        print("FAIL: usage")
        return 2
    try:
        path = pathlib.Path(sys.argv[1])
        if path.stat().st_size > 24_576:
            print("FAIL: event_size")
            return 1
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        print("FAIL: event_read")
        return 1
    valid, verdict = validate(lines)
    if valid:
        print("PASS: read_only_win32_event_stream")
        print("PASS: bounded_schema_no_identifiers")
        return 0
    print("FAIL: " + verdict)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
