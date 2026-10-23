#!/usr/bin/env python3
"""Opt-in, fail-closed software 3D renderer qualification for WineBot.

No host identifiers, environment dumps, raw stdout, or stderr enter JSON results.
"""

import argparse
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

PROFILES = {
    "cpu-opengl-llvmpipe": ("opengl", "llvmpipe"),
    "cpu-vulkan-lavapipe": ("vulkan", "lavapipe"),
    "cpu-vulkan-swiftshader": ("vulkan", "swiftshader"),
}


class RendererUnavailable(Exception):
    pass


def _icd(profile, override):
    if override:
        candidates = [override]
    elif profile == "cpu-vulkan-lavapipe":
        candidates = sorted(glob.glob("/usr/share/vulkan/icd.d/lvp_icd.*.json"))
    else:
        candidates = [os.environ.get("WINEBOT_SWIFTSHADER_ICD", "")]
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        filename = Path(candidate).name.lower()
        if profile == "cpu-vulkan-lavapipe" and not filename.startswith("lvp_icd."):
            continue
        if profile == "cpu-vulkan-swiftshader" and "swiftshader" not in filename:
            continue
        return str(Path(candidate).resolve())
    raise RendererUnavailable("icd_unavailable")


def environment(profile, icd=None, threads=4, environ=None):
    if profile not in PROFILES:
        raise RendererUnavailable("unknown_profile")
    if not 1 <= threads <= 32:
        raise RendererUnavailable("invalid_thread_limit")
    env = dict(os.environ if environ is None else environ)
    # Never accidentally select a host GPU or inherit an unrelated Vulkan ICD.
    for key in ("VK_DRIVER_FILES", "VK_ICD_FILENAMES", "VK_ADD_DRIVER_FILES"):
        env.pop(key, None)
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    env["GALLIUM_DRIVER"] = "llvmpipe"
    env["LP_NUM_THREADS"] = str(threads)
    if PROFILES[profile][0] == "vulkan":
        selected = _icd(profile, icd)
        env["VK_DRIVER_FILES"] = selected
        env["VK_ICD_FILENAMES"] = selected  # Older loader compatibility.
    return env


def _run(argv, env, timeout):
    if shutil.which(argv[0], path=env.get("PATH")) is None:
        raise RendererUnavailable("tool_unavailable")
    try:
        return subprocess.run(
            argv, env=env, capture_output=True, text=True, timeout=timeout,
            check=False, errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        raise RendererUnavailable("command_timeout") from exc
    except OSError as exc:
        raise RendererUnavailable("command_failed") from exc


def renderer_identified(profile, stdout):
    # Check the renderer DEVICE, not merely a software driver listed elsewhere.
    if profile == "cpu-opengl-llvmpipe":
        return bool(re.search(r"^OpenGL renderer string:\s*.*llvmpipe", stdout, re.I | re.M))
    device_lines = "\n".join(
        line.split("=", 1)[-1] for line in stdout.splitlines()
        if re.match(r"\s*deviceName\s*=", line)
    ).lower()
    expected = ("llvmpipe", "lavapipe") if profile == "cpu-vulkan-lavapipe" else ("swiftshader",)
    return any(token in device_lines for token in expected)


def probe(profile, env, timeout=15):
    argv = ["glxinfo", "-B"] if PROFILES[profile][0] == "opengl" else ["vulkaninfo", "--summary"]
    result = _run(argv, env, timeout)
    if result.returncode != 0:
        raise RendererUnavailable("probe_failed")
    if not renderer_identified(profile, result.stdout):
        raise RendererUnavailable("unexpected_renderer")
    return {"profile": profile, "api": PROFILES[profile][0], "renderer": PROFILES[profile][1], "probe": "passed"}


def _glxgears(env, seconds):
    if shutil.which("glxgears", path=env.get("PATH")) is None:
        raise RendererUnavailable("tool_unavailable")
    proc = subprocess.Popen(["glxgears"], env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            out, _ = proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            out, _ = proc.communicate()
    samples = re.findall(r"(\d+) frames in (\d+(?:\.\d+)?) seconds = (\d+(?:\.\d+)?) FPS", out)
    if not samples:
        raise RendererUnavailable("no_frame_sample")
    frames, duration, fps = samples[-1]
    return {"frames": int(frames), "sample_seconds": float(duration), "fps_observed": float(fps),
            "benchmark": "glxgears", "qualification": "smoke_not_comparable"}


def _vkcube(env, frames, timeout):
    started = time.monotonic()
    result = _run(["vkcube", "--c", str(frames)], env, timeout)
    elapsed = time.monotonic() - started
    if result.returncode != 0:
        raise RendererUnavailable("render_failed")
    return {"frames_requested": frames, "wall_seconds": round(elapsed, 3),
            "fps_estimate_including_startup": round(frames / elapsed, 3),
            "benchmark": "vkcube", "qualification": "smoke_not_steady_state"}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("profiles", "probe", "benchmark", "exec"))
    p.add_argument("--profile", choices=sorted(PROFILES))
    p.add_argument("--icd", help="Explicit software Vulkan ICD JSON path (never uploaded)")
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--seconds", type=int, default=7)
    p.add_argument("--frames", type=int, default=60)
    p.add_argument("--timeout", type=int, default=45)
    p.add_argument("command", nargs=argparse.REMAINDER)
    args = p.parse_args(argv)
    if args.action == "profiles":
        print(json.dumps({"profiles": sorted(PROFILES)}))
        return 0
    if not args.profile:
        p.error("--profile is required")
    if not 6 <= args.seconds <= 30 or not 1 <= args.frames <= 600 or not 5 <= args.timeout <= 120:
        p.error("seconds (6..30), frames (1..600), timeout (5..120) must be bounded")
    try:
        env = environment(args.profile, args.icd, args.threads)
        if args.action == "exec":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            if not command:
                p.error("exec requires -- command [args...]")
            if shutil.which(command[0], path=env.get("PATH")) is None:
                raise RendererUnavailable("tool_unavailable")
            return subprocess.run(command, env=env, check=False).returncode
        report = probe(args.profile, env, args.timeout)
        if args.action == "benchmark":
            report.update(_glxgears(env, args.seconds) if PROFILES[args.profile][0] == "opengl"
                          else _vkcube(env, args.frames, args.timeout))
        print(json.dumps(report, sort_keys=True))
        return 0
    except RendererUnavailable as exc:
        # No raw diagnostic streams, host paths, GPU/CPU identifiers or input env.
        print(json.dumps({"profile": args.profile, "result": "unqualified", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
