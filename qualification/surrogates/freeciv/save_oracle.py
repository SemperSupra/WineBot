#!/usr/bin/env python3
"""Freeciv save/reload semantic oracle. Source-known, public-safe, not SMAC parity.

Only bounded derived fields leave the disposable runner. No game files or logs
are published. This is a separate real-game control from the strace pilot.
"""

import argparse
import bz2
import gzip
import hashlib
import json
import lzma
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCHEMA = "freeciv-save-reload/v0.1"
MAX_COMPRESSED = 8 * 1024 * 1024
MAX_EXPANDED = 32 * 1024 * 1024
FIELDS = ("turn", "year", "phase", "server_state", "save_players")
SAFE_STATES = {"S_S_INITIAL", "S_S_RUNNING", "S_S_OVER"}
EXPECTED_FAILURES = {
    "INVALID_SAVE_BOUNDARY", "SAVE_EXPANSION_EXCEEDS_BUDGET",
    "DUPLICATE_GAME_FIELD", "MISSING_OR_DUPLICATE_GAME_SECTION_FIELD",
    "NONINTEGER_GAME_STATE", "GAME_STATE_OUT_OF_BOUNDS", "INVALID_GAME_STATE_ENUM",
    "FREECIV_BINARY_MISSING", "SERVER_EXITED_BEFORE_COMMAND",
    "SERVER_LOOPBACK_NOT_READY", "SERVER_QUIT_TIMEOUT", "SERVER_EXIT_NONZERO",
    "SAVEFILE_COUNT_UNEXPECTED",
}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for data in iter(lambda: fh.read(65536), b""):
            h.update(data)
    return h.hexdigest()


def bounded_save_text(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not (0 < path.stat().st_size <= MAX_COMPRESSED):
        raise ValueError("INVALID_SAVE_BOUNDARY")
    openers = {".xz": lzma.open, ".gz": gzip.open, ".bz2": bz2.open}
    with openers.get(path.suffix.lower(), open)(path, "rb") as inp:
        contents = inp.read(MAX_EXPANDED + 1)
    if len(contents) > MAX_EXPANDED:
        raise ValueError("SAVE_EXPANSION_EXCEEDS_BUDGET")
    return contents.decode("utf-8", errors="replace")


def game_fingerprint(text):
    """Parse exactly one [game] section, detecting ambiguous/missing fields.

    This deliberately avoids exporting arbitrary game data and does NOT
    purport to be a complete Freeciv save parser.
    """
    game_sections = 0
    in_game = False
    fields = {}
    players = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        m = re.fullmatch(r"\[([A-Za-z0-9_]+)\]", line)
        if m:
            name = m.group(1)
            if name == "game":
                game_sections += 1
            in_game = name == "game"
            if re.fullmatch(r"player[0-9]+", name):
                players.add(name)
            continue
        if in_game:
            k = re.fullmatch(r"([A-Za-z0-9_]+)\s*=\s*(.*?)", line)
            if k and k.group(1) in FIELDS:
                key, value = k.groups()
                if key in fields:
                    raise ValueError("DUPLICATE_GAME_FIELD")
                fields[key] = value.strip().strip('"')
    if game_sections != 1 or any(k not in fields for k in FIELDS):
        raise ValueError("MISSING_OR_DUPLICATE_GAME_SECTION_FIELD")
    try:
        ints = {key: int(fields[key]) for key in ("turn", "year", "phase")}
    except ValueError as exc:
        raise ValueError("NONINTEGER_GAME_STATE") from exc
    if not (0 <= ints["turn"] < 100000 and -100000 < ints["year"] < 100000 and 0 <= ints["phase"] < 10000):
        raise ValueError("GAME_STATE_OUT_OF_BOUNDS")
    if fields["server_state"] not in SAFE_STATES or fields["save_players"].upper() not in ("TRUE", "FALSE"):
        raise ValueError("INVALID_GAME_STATE_ENUM")
    return {**ints, "server_state": fields["server_state"],
            "save_players": fields["save_players"].upper() == "TRUE", "player_sections": len(players)}


def compare_fingerprints(original, restored):
    # Same fields must roundtrip; timestamps and binary hashes are deliberately
    # excluded because Freeciv can update save metadata on every write.
    keys = ("turn", "year", "phase", "server_state", "save_players", "player_sections")
    return all(original.get(key) == restored.get(key) for key in keys)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def ready(port, seconds=7):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def emit(proc, command):
    if proc.poll() is not None or proc.stdin is None:
        raise RuntimeError("SERVER_EXITED_BEFORE_COMMAND")
    proc.stdin.write(command + "\n")
    proc.stdin.flush()
    time.sleep(0.15)


def server_transaction(executable, root, name, commands, load_file=None):
    root = Path(root)
    port = free_port()
    saves = root / (name + "-saves")
    saves.mkdir()
    argv = [executable, "--bind", "127.0.0.1", "--Announce", "none", "--port", str(port), "--saves", str(saves)]
    if load_file:
        argv += ["--file", str(load_file)]
    log = root / (name + ".log")
    with log.open("wb") as log_fh:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=log_fh,
                                stderr=subprocess.STDOUT, text=True, cwd=root,
                                start_new_session=True,
                                env={**os.environ, "HOME": str(root), "TZ": "UTC", "LANG": "C.UTF-8"})
        try:
            if not ready(port):
                raise RuntimeError("SERVER_LOOPBACK_NOT_READY")
            for cmd in commands:
                emit(proc, cmd)
            time.sleep(1.6)
            emit(proc, "quit")
            try:
                exit_code = proc.wait(timeout=12)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("SERVER_QUIT_TIMEOUT") from exc
            if exit_code != 0:
                raise RuntimeError("SERVER_EXIT_NONZERO")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=4)
            if proc.stdin:
                proc.stdin.close()
    candidates = [p for p in saves.iterdir() if p.is_file() and p.name.startswith(name + "-")
                  and (".sav" in p.name)]
    if len(candidates) != 1:
        raise RuntimeError("SAVEFILE_COUNT_UNEXPECTED")
    return candidates[0]


def qualify(root, seed):
    executable = shutil.which("freeciv-server") or "/usr/games/freeciv-server"
    if not Path(executable).is_file():
        raise RuntimeError("FREECIV_BINARY_MISSING")
    commands = ("set minplayers 0", "set aifill 2", f"set gameseed {seed}",
                f"set mapseed {seed}", "set timeout 1", "create Caesar",
                "aitoggle Caesar", "start", "save baseline-first")
    before_save = server_transaction(executable, root, "baseline", commands)
    first = game_fingerprint(bounded_save_text(before_save))
    # Explicitly create a *new* server process. No game data is taken from the
    # first live process; restart with Freeciv's documented --file interface.
    after_save = server_transaction(executable, root, "reloaded", ("save reloaded-first",), load_file=before_save)
    second = game_fingerprint(bounded_save_text(after_save))
    return {
        "schema": SCHEMA,
        "status": "PASS" if compare_fingerprints(first, second) and first["save_players"] and first["player_sections"] >= 2 else "FAIL",
        "execution_class": "REAL_OPEN_SOURCE_FREECIV_SAVE_RELOAD_FIELDS_ONLY",
        "seed": seed,
        "binary_sha256": sha256(executable),
        "stage_digests": {"original": sha256(before_save), "reloaded": sha256(after_save)},
        "fingerprints": {"original": first, "reloaded": second},
        "signals": {"save_reloaded_in_second_process": True,
                    "semantic_fields_match": compare_fingerprints(first, second),
                    "players_present": first["player_sections"] >= 2 and first["save_players"]},
        "limitations": ["Only bounded save-file semantics are checked, not native Ghidra execution or whole-game parity",
                        "No proof of turn advancement or equivalence of unsampled game state",
                        "No proprietary SMAC bytes or private observatory implementation present"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, choices=(42, 43), required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="freeciv-semantic-") as scratch:
        try:
            result = qualify(scratch, args.seed)
        except (OSError, ValueError, RuntimeError, EOFError, lzma.LZMAError, subprocess.SubprocessError) as exc:
            code = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else ""
            if code not in EXPECTED_FAILURES:
                code = "BOUNDED_NATIVE_ORACLE_FAILURE"
            result = {"schema": SCHEMA, "seed": args.seed, "status": "UNQUALIFIED",
                      "execution_class": "SAVE_RELOAD_NOT_VERIFIED", "error_code": code}
        target.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"schema": SCHEMA, "seed": args.seed, "status": result["status"]}, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
