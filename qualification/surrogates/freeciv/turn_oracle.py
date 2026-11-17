#!/usr/bin/env python3
"""Bounded real Freeciv AI turn-transition + save/reload oracle.

This is a separately scored source-known game-control probe. It does not use
licensed SMAC bytes, guest virtualization, or private observatory source.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import save_oracle as common

SCHEMA = "freeciv-ai-turn-reload/v0.1"
KNOWN_FAILURES = common.EXPECTED_FAILURES | {"TURN_SAVE_COUNT_UNEXPECTED"}


def is_advanced(before, after, restored):
    """Require genuine increasing in-game turn, then serialized reload parity."""
    return (
        before["server_state"] == "S_S_RUNNING"
        and after["server_state"] == "S_S_RUNNING"
        and restored["server_state"] == "S_S_RUNNING"
        and after["turn"] > before["turn"]
        and after["year"] >= before["year"]
        and after["save_players"]
        and after["player_sections"] >= 2
        and common.compare_fingerprints(after, restored)
    )


def only_save(folder, stem):
    files = [p for p in Path(folder).iterdir() if p.is_file() and p.name.startswith(stem)
             and ".sav" in p.name]
    if len(files) != 1:
        raise RuntimeError("TURN_SAVE_COUNT_UNEXPECTED")
    return files[0]


def advance_game(root, seed):
    binary = shutil.which("freeciv-server") or "/usr/games/freeciv-server"
    if not Path(binary).is_file():
        raise RuntimeError("FREECIV_BINARY_MISSING")
    root = Path(root)
    saves = root / "turn-saves"
    saves.mkdir()
    port = common.free_port()
    argv = [binary, "--bind", "127.0.0.1", "--Announce", "none",
            "--port", str(port), "--saves", str(saves)]
    with (root / "ai-turn.log").open("wb") as log:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=log,
                                stderr=subprocess.STDOUT, text=True, cwd=root,
                                start_new_session=True,
                                env={**os.environ, "HOME": str(root), "LANG": "C.UTF-8", "TZ": "UTC"})
        try:
            if not common.ready(port):
                raise RuntimeError("SERVER_LOOPBACK_NOT_READY")
            for cmd in ("set minplayers 0", "set aifill 2", f"set gameseed {seed}",
                        f"set mapseed {seed}", "set timeout 3", "hard",
                        "create Caesar", "start"):
                common.emit(proc, cmd)
            common.emit(proc, "save before-turn")
            time.sleep(2)
            before_file = only_save(saves, "before-turn")
            before = common.game_fingerprint(common.bounded_save_text(before_file))
            time.sleep(9)
            common.emit(proc, "save after-turn")
            time.sleep(2)
            after_file = only_save(saves, "after-turn")
            after = common.game_fingerprint(common.bounded_save_text(after_file))
            common.emit(proc, "quit")
            if proc.wait(timeout=12) != 0:
                raise RuntimeError("SERVER_EXIT_NONZERO")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=4)
            if proc.stdin:
                proc.stdin.close()
    reloaded_file = common.server_transaction(binary, root, "turnreload",
                                              ("save turnreload-first",), load_file=after_file)
    restored = common.game_fingerprint(common.bounded_save_text(reloaded_file))
    qualified = is_advanced(before, after, restored)
    return {
        "schema": SCHEMA,
        "status": "PASS" if qualified else "UNQUALIFIED",
        "execution_class": "REAL_OPEN_SOURCE_FREECIV_AI_TURN_AND_SELECTED_RELOAD_FIELDS",
        "binary_sha256": common.sha256(binary),
        "seed": seed,
        "game_states": {"before": before, "after": after, "reloaded": restored},
        "signals": {"turn_advanced": after["turn"] > before["turn"],
                    "year_nonregressing": after["year"] >= before["year"],
                    "semantic_reload_match": common.compare_fingerprints(after, restored),
                    "game_running": before["server_state"] == after["server_state"] == "S_S_RUNNING"},
        "limitations": ["Turn advancement under AI-only Freeciv is not SMAC original-binary parity",
                        "Only selected save fields checked; no unit/city/map equivalence or PC witness"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, required=True, choices=(42, 43))
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="freeciv-turn-oracle-") as scratch:
        try:
            result = advance_game(scratch, args.seed)
        except (OSError, ValueError, RuntimeError, EOFError, subprocess.SubprocessError) as exc:
            code = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else ""
            if code not in KNOWN_FAILURES:
                code = "NATIVE_TURN_PROBE_FAILURE"
            result = {"schema": SCHEMA, "seed": args.seed, "status": "UNQUALIFIED",
                      "execution_class": "TURN_ORACLE_NOT_VERIFIED", "error_code": code}
        output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"seed": args.seed, "status": result["status"], "schema": SCHEMA}, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
