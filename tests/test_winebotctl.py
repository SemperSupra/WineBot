import json
import os
import subprocess
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "winebotctl"


def make_curl_stub(tmpdir: Path, responses: dict) -> dict:
    stub = tmpdir / "curl"
    responses_path = tmpdir / "responses.json"
    count_path = tmpdir / "count.txt"
    body_log = tmpdir / "body.log"
    with open(responses_path, "w", encoding="utf-8") as f:
        json.dump(responses, f)
    stub.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

count_file="${CURL_COUNT_FILE:-}"
if [ -n "$count_file" ]; then
  count=$(cat "$count_file" 2>/dev/null || echo 0)
  echo $((count + 1)) > "$count_file"
fi

method="GET"
body=""
url=""
with_status="0"

while [ $# -gt 0 ]; do
  case "$1" in
    -X)
      method="$2"
      shift 2
      ;;
    -d)
      body="$2"
      shift 2
      ;;
    -H|-D|-o)
      shift 2
      ;;
    -w)
      with_status="1"
      shift 2
      ;;
    -s|-S)
      shift
      ;;
    *)
      url="$1"
      shift
      ;;
  esac
done

if [ -n "${CURL_BODY_LOG:-}" ]; then
  printf '%s\\t%s\\t%s\\n' "$method" "$url" "$body" >> "$CURL_BODY_LOG"
fi

status="200"
payload="{}"
if [ -n "${CURL_RESPONSES:-}" ]; then
status=""
payload=""
{ read -r status; read -r payload; } < <(python3 - <<'PY' "$CURL_RESPONSES" "$method" "$url"
import json
import sys

path = sys.argv[1]
method = sys.argv[2]
url = sys.argv[3]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

key = f"{method} {url}"
resp = data.get(key) or data.get(url) or {}
status = resp.get("status", 200)
body = resp.get("body", {})
if isinstance(body, (dict, list)):
    body = json.dumps(body, separators=(",", ":"))
print(status)
print(body)
PY
  )
fi

if [ "$with_status" = "1" ]; then
  printf '%s\\n__HTTP_STATUS__:%s__' "$payload" "$status"
else
  printf '%s' "$payload"
fi
""",
        encoding="utf-8",
    )
    os.chmod(stub, 0o755)
    return {
        "stub": str(stub),
        "responses": str(responses_path),
        "count": str(count_path),
        "body_log": str(body_log),
    }


def run_cli(args, env):
    return subprocess.run([str(SCRIPT)] + args, env=env, capture_output=True, text=True)


def test_winebotctl_health():
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        stub_info = make_curl_stub(
            tmpdir,
            {
                "GET http://localhost:8000/health": {
                    "status": 200,
                    "body": {"status": "ok"},
                }
            },
        )
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{tmpdir}{os.pathsep}{env.get('PATH', '')}",
                "CURL_RESPONSES": stub_info["responses"],
                "CURL_COUNT_FILE": stub_info["count"],
                "WINEBOT_API_URL": "http://localhost:8000",
            }
        )
        result = run_cli(["health"], env)
        assert result.returncode == 0
        payload = json.loads(result.stdout.strip())
        assert payload["status"] == "ok"


def test_winebotctl_idempotent_cache():
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        stub_info = make_curl_stub(
            tmpdir,
            {
                "POST http://localhost:8000/sessions/suspend": {
                    "status": 200,
                    "body": {"status": "suspended"},
                }
            },
        )
        cache_path = tmpdir / "cache.json"
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{tmpdir}{os.pathsep}{env.get('PATH', '')}",
                "CURL_RESPONSES": stub_info["responses"],
                "CURL_COUNT_FILE": stub_info["count"],
                "WINEBOT_IDEMPOTENT_CACHE": str(cache_path),
                "WINEBOT_API_URL": "http://localhost:8000",
            }
        )
        result1 = run_cli(
            ["api", "POST", "/sessions/suspend", "--json", '{"shutdown_wine":true}'],
            env,
        )
        assert result1.returncode == 0
        result2 = run_cli(
            ["api", "POST", "/sessions/suspend", "--json", '{"shutdown_wine":true}'],
            env,
        )
        assert result2.returncode == 0
        count = int(Path(stub_info["count"]).read_text().strip())
        assert count == 1


def test_winebotctl_recording_start_payload():
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        stub_info = make_curl_stub(
            tmpdir,
            {
                "GET http://localhost:8000/health/recording": {
                    "status": 200,
                    "body": {"state": "idle"},
                },
                "POST http://localhost:8000/recording/start": {
                    "status": 200,
                    "body": {"status": "started"},
                },
            },
        )
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{tmpdir}{os.pathsep}{env.get('PATH', '')}",
                "CURL_RESPONSES": stub_info["responses"],
                "CURL_COUNT_FILE": stub_info["count"],
                "CURL_BODY_LOG": stub_info["body_log"],
                "WINEBOT_API_URL": "http://localhost:8000",
            }
        )
        result = run_cli(["recording", "start"], env)
        assert result.returncode == 0
        body_log = (
            Path(stub_info["body_log"]).read_text(encoding="utf-8").strip().splitlines()
        )
        assert body_log
        # The last logged line should be the /recording/start payload.
        method, url, body = body_log[-1].split("\t", 2)
        assert method == "POST"
        assert url.endswith("/recording/start")
        payload = json.loads(body)
        assert payload.get("new_session") is False


def test_winebotctl_lifecycle_shutdown_requires_confirmation():
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        stub_info = make_curl_stub(
            tmpdir,
            {
                "POST http://localhost:8000/lifecycle/shutdown": {
                    "status": 200,
                    "body": {"status": "shutting_down"},
                }
            },
        )
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{tmpdir}{os.pathsep}{env.get('PATH', '')}",
                "CURL_RESPONSES": stub_info["responses"],
                "CURL_COUNT_FILE": stub_info["count"],
                "WINEBOT_API_URL": "http://localhost:8000",
            }
        )
        result = run_cli(["lifecycle", "shutdown"], env)
        assert result.returncode != 0
        assert "requires confirmation" in result.stderr
        count_path = Path(stub_info["count"])
        count = int(count_path.read_text().strip()) if count_path.exists() else 0
        assert count == 0


def test_winebotctl_lifecycle_shutdown_with_yes_calls_api():
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        stub_info = make_curl_stub(
            tmpdir,
            {
                "POST http://localhost:8000/lifecycle/shutdown": {
                    "status": 200,
                    "body": {"status": "shutting_down"},
                }
            },
        )
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{tmpdir}{os.pathsep}{env.get('PATH', '')}",
                "CURL_RESPONSES": stub_info["responses"],
                "CURL_COUNT_FILE": stub_info["count"],
                "WINEBOT_API_URL": "http://localhost:8000",
            }
        )
        result = run_cli(["lifecycle", "shutdown", "--yes"], env)
        assert result.returncode == 0
        payload = json.loads(result.stdout.strip())
        assert payload["status"] == "shutting_down"


def test_winebotctl_perf_summary():
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        stub_info = make_curl_stub(
            tmpdir,
            {
                "GET http://localhost:8000/recording/perf/summary": {
                    "status": 200,
                    "body": {
                        "session_dir": "/artifacts/sessions/session-1",
                        "metrics": {
                            "recording.api_pause.latency": {
                                "count": 2,
                                "p95_ms": 22.0,
                            }
                        },
                    },
                }
            },
        )
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{tmpdir}{os.pathsep}{env.get('PATH', '')}",
                "CURL_RESPONSES": stub_info["responses"],
                "CURL_COUNT_FILE": stub_info["count"],
                "WINEBOT_API_URL": "http://localhost:8000",
            }
        )
        result = run_cli(["perf", "summary"], env)
        assert result.returncode == 0
        payload = json.loads(result.stdout.strip())
        assert payload["metrics"]["recording.api_pause.latency"]["count"] == 2
