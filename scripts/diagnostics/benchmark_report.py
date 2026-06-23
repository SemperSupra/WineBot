#!/usr/bin/env python3
"""Generate a Markdown report from benchmark results JSON.

Produces statistically rigorous comparison tables with confidence intervals,
ranking tables, and ASCII latency distribution charts.

Usage:
  python3 scripts/diagnostics/benchmark_report.py results.json > REPORT.md
"""

import argparse
import json
import sys
from datetime import datetime, timezone


def _markdown_table(headers: list, rows: list, align: list = None) -> str:
    """Build a Markdown table."""
    if not align:
        align = ["---"] * len(headers)
    lines = [
        "| " + " | ".join(str(h) for h in headers) + " |",
        "|" + "|".join(f" {a} " for a in align) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def _ci_str(stats: dict) -> str:
    """Format CI as 'mean (ci_low–ci_high)'."""
    ci_low = stats.get("ci95_low", 0)
    ci_high = stats.get("ci95_high", 0)
    mean = stats.get("mean_ms", 0)
    return f"{mean:.0f} ({ci_low:.0f}–{ci_high:.0f})"


def _sig_diff(a: dict, b: dict) -> str:
    """Check if two results are significantly different (non-overlapping 95% CIs)."""
    a_lo, a_hi = a.get("ci95_low", 0), a.get("ci95_high", 0)
    b_lo, b_hi = b.get("ci95_low", 0), b.get("ci95_high", 0)
    if a_hi < b_lo:
        return "SIG slower"
    elif b_hi < a_lo:
        return "SIG faster"
    return "~ within noise"


def _latency_chart(results: list, width: int = 50) -> str:
    """ASCII horizontal bar chart of mean latencies."""
    if not results:
        return ""

    max_ms = max(r["summary"]["mean_ms"] for r in results)
    lines = ["```"]
    for r in results:
        name = f"{r['engine']['ui_detector']:>12}+{r['engine']['ocr_backend']:<12}"
        bar_len = int(r["summary"]["mean_ms"] / max(max_ms, 1) * width)
        bar = "#" * bar_len
        ci = _ci_str(r["summary"])
        lines.append(f"  {name} |{bar:<{width}}| {ci}ms")
    lines.append("```")
    return "\n".join(lines)


def generate_report(benchmark_data: dict) -> str:
    """Generate a full Markdown benchmark report."""
    bm_id = benchmark_data.get("benchmark_id", "unknown")
    ts = benchmark_data.get("timestamp_utc", "")
    config = benchmark_data.get("config", {})
    results = benchmark_data.get("results", [])
    available = [r for r in results if r.get("available")]

    sections = []

    # ── Header ─────────────────────────────────────────────────────────
    sections.append(f"# WineBot CV/OCR Engine Benchmark Report")
    sections.append(f"**Benchmark ID:** `{bm_id}`  ")
    sections.append(f"**Date:** {ts[:19].replace('T', ' ')} UTC  ")
    sections.append(f"**Frames:** {config.get('total_frames', '?')} total "
                    f"({config.get('benchmark_frames', '?')} benchmark, "
                    f"{config.get('warmup_frames', '?')} warmup)  ")
    sections.append(f"**Iterations:** {config.get('iterations', '?')} per frame per engine  ")
    sections.append(f"**Confidence:** {config.get('confidence', 0.95) * 100:.0f}% CI (t-distribution)  ")
    sections.append("")

    # ── Engine Availability ───────────────────────────────────────────
    sections.append("## Engine Availability")
    sections.append("")
    rows = []
    for r in results:
        eng = r["engine"]
        avail = "yes" if r.get("available") else "NO"
        error = r.get("error", "")
        rows.append([eng["ui_detector"], eng["ocr_backend"], avail, error])
    sections.append(_markdown_table(
        ["UI Detector", "OCR Engine", "Available", "Error"],
        rows,
        [":---", ":---", ":---:", ":---"],
    ))
    sections.append("")

    if not available:
        sections.append("**No engines available — benchmark aborted.**")
        return "\n".join(sections)

    # ── Latency Comparison ────────────────────────────────────────────
    sections.append("## Latency Comparison")
    sections.append("")
    sections.append(_latency_chart(available))
    sections.append("")

    # ── Detailed Timing Table ─────────────────────────────────────────
    sections.append("## Detailed Timing Statistics")
    sections.append("")
    sections.append("All times in milliseconds. CI = 95% confidence interval.")
    sections.append("")

    headers = ["UI Detector", "OCR", "Mean", "p50", "p95", "p99", "σ", "CI95", "FPS", "Sig"]
    rows = []
    baseline = available[0] if available else None
    for r in available:
        s = r["summary"]
        eng = r["engine"]
        sig = _sig_diff(baseline["summary"], s) if baseline and r != baseline else "baseline"
        rows.append([
            f"`{eng['ui_detector']}`",
            f"`{eng['ocr_backend']}`",
            f"{s['mean_ms']:.0f}",
            f"{s['p50_ms']:.0f}",
            f"{s['p95_ms']:.0f}",
            f"{s['p99_ms']:.0f}",
            f"±{s['std_ms']:.0f}",
            f"{_ci_str(s)}",
            f"{s['effective_fps']:.1f}",
            sig,
        ])
    sections.append(_markdown_table(
        headers, rows,
        [":---", ":---", "---:", "---:", "---:", "---:", "---:", "---:", "---:", ":---:"],
    ))
    sections.append("")

    # ── Detection Quality ─────────────────────────────────────────────
    sections.append("## Detection Quality")
    sections.append("")
    sections.append("Average UI elements detected per frame. More is not always better — "
                    "contour may over-detect, YOLO may miss elements.")
    sections.append("")

    headers = ["UI Detector", "OCR", "UI Elements", "Interactive", "OCR Regions"]
    rows = []
    for r in available:
        s = r["summary"]
        eng = r["engine"]
        rows.append([
            f"`{eng['ui_detector']}`",
            f"`{eng['ocr_backend']}`",
            f"{s['mean_ui_elements']:.1f}",
            f"{s['mean_interactive']:.1f}",
            f"{s['mean_ocr_regions']:.1f}",
        ])
    sections.append(_markdown_table(headers, rows, [":---", ":---", "---:", "---:", "---:"]))
    sections.append("")

    # ── Accuracy vs Ground Truth ──────────────────────────────────────
    acc_results = [r for r in available if "accuracy" in r]
    if acc_results:
        sections.append("## Accuracy vs Ground Truth")
        sections.append("")
        sections.append("Measured against synthetic UI images with known text and element positions.")
        sections.append("")

        sections.append("### OCR Accuracy (F1 Score)")
        sections.append("")
        headers = ["UI Detector", "OCR", "Precision", "Recall", "F1", "TP/Det/Exp"]
        rows = []
        for r in acc_results:
            acc = r["accuracy"]["ocr"]
            eng = r["engine"]
            rows.append([
                f"`{eng['ui_detector']}`",
                f"`{eng['ocr_backend']}`",
                f"{acc['precision']:.3f}",
                f"{acc['recall']:.3f}",
                f"**{acc['f1']:.3f}**",
                f"{acc['true_positives']}/{acc['detected_count']}/{acc['expected_count']}",
            ])
        sections.append(_markdown_table(headers, rows, [":---", ":---", "---:", "---:", "---:", ":---:"]))
        sections.append("")

        sections.append("### Detection Accuracy (F1 Score)")
        sections.append("")
        headers = ["UI Detector", "OCR", "Precision", "Recall", "F1", "IoU Matches", "Det/Exp"]
        rows = []
        for r in acc_results:
            acc = r["accuracy"]["detection"]
            eng = r["engine"]
            rows.append([
                f"`{eng['ui_detector']}`",
                f"`{eng['ocr_backend']}`",
                f"{acc['precision']:.3f}",
                f"{acc['recall']:.3f}",
                f"**{acc['f1']:.3f}**",
                str(acc['iou_matches']),
                f"{acc['detected_count']}/{acc['expected_count']}",
            ])
        sections.append(_markdown_table(headers, rows, [":---", ":---", "---:", "---:", "---:", ":---:", ":---:"]))
        sections.append("")

    # ── Per-Frame Variability ─────────────────────────────────────────
    if available and any("per_frame" in r for r in available):
        sections.append("## Per-Frame Variability")
        sections.append("")
        sections.append("Minimum and maximum frame times show worst/best case spread. "
                        "High variance may indicate engine initialization overhead or "
                        "content-dependent performance.")
        sections.append("")

        headers = ["UI Detector", "OCR", "Min (ms)", "Max (ms)", "Range", "CV%"]
        rows = []
        for r in available:
            frames = r.get("per_frame", [])
            if not frames:
                continue
            mins = [f["min_ms"] for f in frames]
            maxes = [f["max_ms"] for f in frames]
            means = [f["mean_ms"] for f in frames]
            avg_min = sum(mins) / len(mins)
            avg_max = sum(maxes) / len(maxes)
            avg_mean = sum(means) / len(means)
            cv = (sum((m - avg_mean) ** 2 for m in means) / len(means)) ** 0.5 / max(avg_mean, 0.001) * 100
            eng = r["engine"]
            rows.append([
                f"`{eng['ui_detector']}`",
                f"`{eng['ocr_backend']}`",
                f"{avg_min:.0f}",
                f"{avg_max:.0f}",
                f"{avg_max - avg_min:.0f}",
                f"{cv:.1f}%",
            ])
        sections.append(_markdown_table(headers, rows, [":---", ":---", "---:", "---:", "---:", "---:"]))
        sections.append("")

    # ── Recommendations ───────────────────────────────────────────────
    sections.append("## Recommendations")
    sections.append("")

    if available:
        # Find best by category
        fastest = min(available, key=lambda r: r["summary"]["mean_ms"])
        most_elements = max(available, key=lambda r: r["summary"]["mean_ui_elements"])
        most_accurate = None
        if acc_results:
            most_accurate = max(acc_results, key=lambda r: r["accuracy"]["ocr"]["f1"])

        fe = fastest["engine"]
        me = most_elements["engine"]
        sections.append(f"1. **Fastest pipeline:** `{fe['ui_detector']}+{fe['ocr_backend']}` "
                        f"({fastest['summary']['mean_ms']:.0f}ms, "
                        f"{fastest['summary']['effective_fps']:.1f} fps)")

        if me != fe:
            sections.append(f"2. **Best element coverage:** `{me['ui_detector']}+{me['ocr_backend']}` "
                            f"({most_elements['summary']['mean_ui_elements']:.1f} elements/frame)")

        if most_accurate:
            ma = most_accurate["engine"]
            sections.append(f"3. **Best OCR accuracy:** `{ma['ui_detector']}+{ma['ocr_backend']}` "
                            f"(F1={most_accurate['accuracy']['ocr']['f1']:.3f})")

        sections.append("")
        sections.append("### Methodology Notes")
        sections.append("")
        sections.append(f"- **Warmup:** {config.get('warmup_frames', '?')} frames discarded per engine to account for CUDA kernel compilation and model lazy-loading")
        sections.append(f"- **Replication:** {config.get('iterations', '?')} runs per frame to quantify measurement noise")
        sections.append(f"- **CI:** {config.get('confidence', 0.95) * 100:.0f}% confidence intervals via t-distribution (accounts for small sample sizes)")
        sections.append("- **Significance:** 'SIG faster/slower' = non-overlapping 95% CIs vs baseline. '~ within noise' = overlapping CIs.")
        sections.append("- **Hardware:** Benchmark run inside Docker with `--gpus all`. GPU availability depends on container runtime.")

    sections.append("")
    sections.append(f"---")
    sections.append(f"*Report generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC*")

    return "\n".join(sections)


def main():
    parser = argparse.ArgumentParser(
        description="Generate Markdown benchmark report from JSON results"
    )
    parser.add_argument("input", nargs="?", help="Benchmark JSON file (default: stdin)")
    parser.add_argument("--output", "-o", help="Output Markdown file (default: stdout)")
    args = parser.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    report = generate_report(data)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Report saved to: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
