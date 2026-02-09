#!/usr/bin/env python3
"""Generate a bounded, redacted WineBot support bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = "1.0"
REDACTION_VERSION = "1"
SECRET_KEY_RE = re.compile(
    r"(token|password|secret|api[_-]?key|authorization|cookie|vnc[_-]?password|private[_-]?key)",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(r"(authorization:\s*\S+|bearer\s+\S+|x-api-key:\s*\S+)", re.IGNORECASE)


@dataclass
class CopyState:
    max_bytes: int
    used_bytes: int = 0

    def reserve(self, amount: int) -> None:
        if self.used_bytes + amount > self.max_bytes:
            raise RuntimeError(
                f"bundle size cap exceeded: would use {self.used_bytes + amount} bytes (cap {self.max_bytes})"
            )
        self.used_bytes += amount


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def redact_value(value: str, secrets: set[str]) -> str:
    out = value
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        if len(secret) < 4:
            continue
        out = out.replace(secret, "***REDACTED***")
    out = SECRET_VALUE_RE.sub("***REDACTED***", out)
    return out


def redact_mapping(mapping: dict[str, str], secrets: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for k, v in mapping.items():
        if SECRET_KEY_RE.search(k):
            result[k] = "***REDACTED***"
        else:
            result[k] = redact_value(str(v), secrets)
    return result


def parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def resolve_session_dir(session_dir: str | None, session_id: str | None, session_root: Path) -> Path | None:
    if session_dir:
        p = Path(session_dir)
        return p if p.exists() else None

    env_session = os.getenv("WINEBOT_SESSION_DIR", "").strip()
    if env_session:
        p = Path(env_session)
        if p.exists():
            return p

    if session_id:
        direct = session_root / session_id
        if direct.exists():
            return direct
        for candidate in session_root.glob("*/session.json"):
            try:
                payload = json.loads(candidate.read_text())
            except Exception:
                continue
            if str(payload.get("session_id", "")) == session_id:
                return candidate.parent

    candidates = sorted(
        [p for p in session_root.glob("*") if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def copy_file(src: Path, dst: Path, state: CopyState) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    size = src.stat().st_size
    state.reserve(size)
    shutil.copy2(src, dst)


def copy_text_redacted(src: Path, dst: Path, state: CopyState, secrets: set[str]) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    content = src.read_text(errors="ignore")
    redacted = redact_value(content, secrets)
    encoded = redacted.encode("utf-8", errors="ignore")
    state.reserve(len(encoded))
    dst.write_bytes(encoded)


def iter_session_files(session_dir: Path) -> Iterable[Path]:
    patterns = [
        "session.json",
        "segment_*.json",
        "events_*.jsonl",
        "events_*.vtt",
        "events_*.ass",
        "logs/*.log",
        "logs/*.jsonl",
    ]
    seen: set[Path] = set()
    for pattern in patterns:
        for p in sorted(session_dir.glob(pattern)):
            if p.is_file() and p not in seen:
                seen.add(p)
                yield p


def build_manifest(root: Path, build_intent: str) -> dict:
    files = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        files.append({"path": rel, "size": p.stat().st_size, "sha256": digest})
    return {
        "schema_version": SCHEMA_VERSION,
        "redaction_version": REDACTION_VERSION,
        "timestamp_utc": utc_now(),
        "build_intent": build_intent,
        "platform": {"os": platform.system(), "release": platform.release(), "arch": platform.machine()},
        "host": socket.gethostname(),
        "files": files,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session-dir", default=None)
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--session-root", default="/artifacts/sessions")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-mb", type=int, default=200)
    ap.add_argument("--build-intent", default=os.getenv("BUILD_INTENT", "rel"))
    args = ap.parse_args()

    session_root = Path(args.session_root)
    session_dir = resolve_session_dir(args.session_dir, args.session_id, session_root)
    out_path = Path(args.out) if args.out else Path(f"/artifacts/support-bundle-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="winebot-support-") as td:
        bundle_root = Path(td) / "support-bundle"
        bundle_root.mkdir(parents=True, exist_ok=True)
        state = CopyState(max_bytes=args.max_mb * 1024 * 1024)

        env_map = dict(os.environ)
        secret_values = {
            v
            for k, v in env_map.items()
            if v and SECRET_KEY_RE.search(k)
        }

        # app/version.json
        version = (Path("/VERSION").read_text().strip() if Path("/VERSION").exists() else "unknown")
        version_payload = {
            "winebot_version": version,
            "build_intent": args.build_intent,
            "build_revision": os.getenv("VCS_REF", "unknown"),
            "generated_utc": utc_now(),
        }
        app_dir = bundle_root / "app"
        app_dir.mkdir(parents=True, exist_ok=True)
        version_bytes = json.dumps(version_payload, indent=2).encode("utf-8")
        state.reserve(len(version_bytes))
        (app_dir / "version.json").write_bytes(version_bytes)

        # app/config.redacted.json
        cfg = {}
        cfg.update(parse_env_file(Path("/wineprefix/winebot.env")))
        host_cfg = Path(f"/wineprefix/winebot.{socket.gethostname()}.env")
        cfg.update(parse_env_file(host_cfg))
        red_cfg = redact_mapping(cfg, secret_values)
        cfg_bytes = json.dumps(red_cfg, indent=2).encode("utf-8")
        state.reserve(len(cfg_bytes))
        (app_dir / "config.redacted.json").write_bytes(cfg_bytes)

        # system snapshots
        system_dir = bundle_root / "system"
        system_dir.mkdir(parents=True, exist_ok=True)
        os_payload = {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        }
        os_bytes = json.dumps(os_payload, indent=2).encode("utf-8")
        state.reserve(len(os_bytes))
        (system_dir / "os.json").write_bytes(os_bytes)
        red_env = redact_mapping(env_map, secret_values)
        env_bytes = json.dumps(red_env, indent=2).encode("utf-8")
        state.reserve(len(env_bytes))
        (system_dir / "env.redacted.json").write_bytes(env_bytes)

        # session artifacts (bounded subset, redacted logs/events)
        notes_lines = []
        if session_dir and session_dir.exists():
            dst_session = bundle_root / "session"
            dst_session.mkdir(parents=True, exist_ok=True)
            for src in iter_session_files(session_dir):
                rel = src.relative_to(session_dir)
                dst = dst_session / rel
                if src.suffix in {".log", ".jsonl", ".vtt", ".ass"}:
                    copy_text_redacted(src, dst, state, secret_values)
                else:
                    copy_file(src, dst, state)
            logs_dir = session_dir / "logs"
            if logs_dir.exists():
                dst_logs = app_dir / "logs"
                for p in sorted(logs_dir.glob("*")):
                    if p.is_file() and p.suffix in {".log", ".jsonl"}:
                        copy_text_redacted(p, dst_logs / p.name, state, secret_values)
            notes_lines.append(f"Session source: {session_dir}")
        else:
            notes_lines.append("No session directory found; bundle contains app/system diagnostics only.")

        notes_lines.append(f"Build intent: {args.build_intent}")
        notes_lines.append(f"Bundle cap bytes: {state.max_bytes}")
        notes_lines.append("No remote upload performed; local bundle generation only.")
        notes_content = "\n".join(notes_lines) + "\n"
        notes_bytes = notes_content.encode("utf-8")
        state.reserve(len(notes_bytes))
        (bundle_root / "notes.txt").write_bytes(notes_bytes)

        manifest = build_manifest(bundle_root, args.build_intent)
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
        state.reserve(len(manifest_bytes))
        (bundle_root / "manifest.json").write_bytes(manifest_bytes)

        tmp_out = out_path.with_suffix(out_path.suffix + ".tmp")
        with tarfile.open(tmp_out, "w:gz") as tf:
            tf.add(bundle_root, arcname="support-bundle")
        tmp_out.replace(out_path)

    print(json.dumps({"status": "ok", "bundle": str(out_path), "build_intent": args.build_intent}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
