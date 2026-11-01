#!/usr/bin/env python3
"""RDTE-only, hermetic Wine 11 package staging/verification fixture.

This is NOT the Windows PowerShell installer and does not assert production
installer parity. It validates real Win32 binaries installed within a fresh
Wine prefix, and refuses modified packages, path traversal and overwrites.
No network, PII, registry changes, or control service.
"""
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile

NAMES = ("bin/win_event_observer.exe", "bin/win_event_fixture.exe")
SCHEMA = "winebot.toolkit.package.v0"
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def refuse_symlinks(path):
    p = pathlib.Path(os.path.abspath(path))
    for item in (p, *p.parents):
        if item.is_symlink():
            raise ValueError("reparse_or_symlink_refused")


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def checks(root):
    refuse_symlinks(root)
    manifest_path = pathlib.Path(root) / "manifest.json"
    refuse_symlinks(manifest_path)
    obj = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (not isinstance(obj, dict)
            or set(obj) != {"schema", "status", "target", "files"}
            or obj["schema"] != SCHEMA
            or obj["status"] != "synthetic-rdte-only"
            or obj["target"] != "win-x64"
            or not isinstance(obj["files"], dict)
            or set(obj["files"]) != set(NAMES)):
        raise ValueError("invalid_manifest")
    for name in NAMES:
        path = pathlib.Path(root) / name
        refuse_symlinks(path)
        expected = obj["files"][name]
        if (not isinstance(expected, str) or len(expected) != 64
                or any(c not in "0123456789abcdef" for c in expected)
                or not path.is_file() or digest(path) != expected):
            raise ValueError("package_integrity_failure")
    return obj


def prepare(source, package):
    src, dest = pathlib.Path(source), pathlib.Path(package)
    refuse_symlinks(src)
    refuse_symlinks(dest)
    if dest.exists():
        raise ValueError("package_already_exists")
    (dest / "bin").mkdir(parents=True)
    try:
        files = {}
        for name in NAMES:
            original = src / pathlib.Path(name).name
            refuse_symlinks(original)
            if not original.is_file():
                raise ValueError("missing_source_binary")
            target = dest / name
            shutil.copyfile(original, target)
            files[name] = digest(original)
        (dest / "manifest.json").write_text(
            json.dumps({"schema": SCHEMA, "target": "win-x64",
                        "status": "synthetic-rdte-only", "files": files},
                       sort_keys=True), encoding="utf-8")
        checks(dest)
    except Exception:
        shutil.rmtree(dest)
        raise


def install(package, root, version):
    if not VERSION.fullmatch(version) or version in (".", ".."):
        raise ValueError("unsafe_version")
    checks(package)
    root = pathlib.Path(root)
    refuse_symlinks(root)
    root.mkdir(parents=True, exist_ok=True)
    dest = root / version
    refuse_symlinks(dest)
    if dest.exists():
        raise ValueError("destination_exists_no_overwrite")
    stage = pathlib.Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
    try:
        (stage / "bin").mkdir()
        for name in NAMES:
            shutil.copyfile(pathlib.Path(package) / name, stage / name)
        shutil.copyfile(pathlib.Path(package) / "manifest.json",
                        stage / "manifest.json")
        checks(stage)
        refuse_symlinks(root)
        if dest.exists():
            raise ValueError("destination_exists_no_overwrite")
        stage.rename(dest)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    checks(dest)


def uninstall(root, version):
    if not VERSION.fullmatch(version):
        raise ValueError("unsafe_version")
    dest = pathlib.Path(root) / version
    refuse_symlinks(dest)
    if not dest.exists():
        return
    checks(dest)
    expected = set(NAMES) | {"manifest.json"}
    found = {str(p.relative_to(dest)).replace(os.sep, "/")
             for p in dest.rglob("*") if p.is_file()}
    if found != expected:
        raise ValueError("uninstall_unowned_files")
    shutil.rmtree(dest)


def main():
    if len(sys.argv) < 2:
        raise ValueError("operation_required")
    op = sys.argv[1]
    if op == "prepare" and len(sys.argv) == 4:
        prepare(sys.argv[2], sys.argv[3])
    elif op == "install" and len(sys.argv) == 5:
        install(sys.argv[2], sys.argv[3], sys.argv[4])
    elif op == "verify" and len(sys.argv) == 3:
        checks(sys.argv[2])
    elif op == "uninstall" and len(sys.argv) == 4:
        uninstall(sys.argv[2], sys.argv[3])
    else:
        raise ValueError("incorrect_arguments")
    print("PASS: wine11_package_" + op)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        # Do not echo paths or package bytes into public CI logs.
        print("FAIL: wine11_package_" + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
