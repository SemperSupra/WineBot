#!/usr/bin/env python3
import argparse
import datetime as dt
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence


@dataclass(frozen=True)
class Rule:
    section: str
    feature_set: str
    capability: str
    keywords: Sequence[str]


RULES: Sequence[Rule] = (
    Rule(
        section="Runtime Foundation",
        feature_set="Startup and health/resilience",
        capability="Startup flow, healthcheck reliability, route/auth hardening",
        keywords=("healthcheck", "health", "startup", "entrypoint", "routing", "auth"),
    ),
    Rule(
        section="Build, Images, and Intents",
        feature_set="Build intents and image lifecycle",
        capability="Intent targets, base image pinning, Docker build pipeline",
        keywords=("build intent", "intent", "dockerfile", "base image", "image"),
    ),
    Rule(
        section="Session and Lifecycle Management",
        feature_set="Lifecycle/session management",
        capability="Session suspend/resume/shutdown and lifecycle correctness",
        keywords=("lifecycle", "session", "suspend", "resume", "shutdown"),
    ),
    Rule(
        section="Control, Input, and Automation",
        feature_set="Control policy and input tracing",
        capability="Control grant/revoke, input routing, trace lifecycle",
        keywords=("control", "input", "trace", "agent", "policy", "automation"),
    ),
    Rule(
        section="Recording and Artifacts",
        feature_set="Recording pipeline and artifacts",
        capability="Recording lifecycle, subtitle/artifact generation, recording diagnostics",
        keywords=("record", "recorder", "artifact", "subtitle", "ffmpeg"),
    ),
    Rule(
        section="UI, Dashboard, and UX",
        feature_set="Dashboard and UX reliability",
        capability="UI state correctness, e2e synchronization, dashboard behavior",
        keywords=("dashboard", "ui", "ux", "novnc", "spa", "playwright"),
    ),
    Rule(
        section="Security, Policy, and Release Governance",
        feature_set="Security/release governance",
        capability="Token/auth policy, release verification, supply-chain controls",
        keywords=("security", "token", "release", "cosign", "cve", "governance", "policy"),
    ),
    Rule(
        section="CI/CD and Quality Gates",
        feature_set="CI/CD and verification",
        capability="Containerized checks, lint/test reliability, workflow stabilization",
        keywords=("ci", "workflow", "lint", "mypy", "smoke", "test", "github actions"),
    ),
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def git_log(limit: int, cwd: Path) -> List[str]:
    cmd = ["git", "log", f"--max-count={limit}", "--pretty=%h|%s"]
    out = subprocess.check_output(cmd, cwd=str(cwd), text=True)
    return [line.strip() for line in out.splitlines() if line.strip()]


def match_rule(subject: str) -> Rule | None:
    lowered = subject.lower()
    for rule in RULES:
        if any(k in lowered for k in rule.keywords):
            return rule
    return None


def render(rows_by_section: Dict[str, List[tuple[str, str, str]]], limit: int) -> str:
    lines: List[str] = []
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    lines.append("# Auto-Generated Feature/Capability Commit Map (Draft)")
    lines.append("")
    lines.append("This file is generated from commit subjects using keyword classification.")
    lines.append("It is a draft intended to reduce manual maintenance for the curated map.")
    lines.append("")
    lines.append(f"- Generated at: `{now}`")
    lines.append(f"- Commit window: last `{limit}` commits")
    lines.append("")
    lines.append("Source script: `scripts/internal/generate-feature-commit-map.py`")
    lines.append("")

    for section in [r.section for r in RULES] + ["Uncategorized"]:
        rows = rows_by_section.get(section, [])
        if not rows:
            continue
        lines.append(f"## {section}")
        lines.append("")
        lines.append("| Feature/Capability Set | Capability (Inferred) | Associated Commit |")
        lines.append("| :--- | :--- | :--- |")
        for feature_set, capability, commit in rows:
            lines.append(f"| {feature_set} | {capability} | `{commit}` |")
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a draft feature/capability commit map")
    parser.add_argument("--limit", type=int, default=200, help="Number of commits to analyze")
    parser.add_argument(
        "--output",
        default="docs/feature-capability-commit-map.auto.md",
        help="Output markdown file path (repo-relative)",
    )
    args = parser.parse_args()

    root = repo_root()
    commits = git_log(args.limit, cwd=root)

    rows_by_section: Dict[str, List[tuple[str, str, str]]] = {}
    for item in commits:
        if "|" not in item:
            continue
        short_hash, subject = item.split("|", 1)
        rule = match_rule(subject)
        if rule is None:
            rows_by_section.setdefault("Uncategorized", []).append(
                ("Uncategorized", subject, short_hash)
            )
            continue
        rows_by_section.setdefault(rule.section, []).append(
            (rule.feature_set, rule.capability, short_hash)
        )

    output_path = root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render(rows_by_section, args.limit), encoding="utf-8")
    print(f"Wrote draft map: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
