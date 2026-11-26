"""Offline, fail-closed validation of the point-in-time WineBot remote census.

This never contacts GitHub and never authorizes remote ref/worktree deletion.
"""
import argparse
import json
import re
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")
SCHEMA = "winebot/reconciliation/r040/v1"


def validate(census):
    if not isinstance(census, dict) or census.get("schema") != SCHEMA:
        raise ValueError("unknown manifest schema")
    if census.get("repository") != "SemperSupra/WineBot":
        raise ValueError("unexpected repository")
    branches = census.get("remote_branches")
    prs = census.get("open_prs")
    closed = census.get("closed_prs")
    counts = census.get("counts")
    if not all(isinstance(x, list) for x in (branches, prs, closed)):
        raise ValueError("manifest collection absent")
    if not isinstance(counts, dict):
        raise ValueError("manifest counts absent")
    bmap = {}
    for b in branches:
        if not isinstance(b, dict):
            raise ValueError("invalid branch record")
        name, sha = b.get("name"), b.get("sha")
        if not isinstance(name, str) or not name or name in bmap:
            raise ValueError("invalid or duplicate remote ref")
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise ValueError("invalid ref digest")
        for key in ("protected", "open_pr_head", "open_pr_base", "closed_pr_head"):
            if type(b.get(key)) is not bool:
                raise ValueError("invalid ref classification")
        bmap[name] = b
    main = bmap.get("main")
    if (not main or not main["protected"]
            or main["sha"] != census.get("main_sha")
            or not SHA.fullmatch(census["main_sha"])):
        raise ValueError("protected main identity mismatch")
    open_numbers = set()
    open_heads = set()
    open_bases = set()
    for p in prs:
        num, head, base, sha = (
            p.get("number"), p.get("head"), p.get("base"), p.get("head_sha")
        )
        if (type(num) is not int or num < 1 or num in open_numbers
                or head not in bmap or base not in bmap
                or bmap[head]["sha"] != sha):
            raise ValueError("open PR source ref mismatch")
        open_numbers.add(num)
        open_heads.add(head)
        open_bases.add(base)
    closed_numbers = set()
    closed_heads = set()
    for p in closed:
        num, head, sha = p.get("number"), p.get("head"), p.get("head_sha")
        if (type(num) is not int or num < 1 or num in closed_numbers
                or not isinstance(head, str) or not SHA.fullmatch(sha)
                or type(p.get("merged")) is not bool):
            raise ValueError("invalid closed PR record")
        closed_numbers.add(num)
        closed_heads.add(head)
    if open_numbers & closed_numbers:
        raise ValueError("PR simultaneously open and closed")
    for name, b in bmap.items():
        if (b["open_pr_head"] != (name in open_heads)
                or b["open_pr_base"] != (name in open_bases)
                or b["closed_pr_head"] != (name in closed_heads)):
            raise ValueError("ref classification mismatch")
    unref = [
        b for name, b in bmap.items()
        if name != "main" and name not in open_heads and name not in open_bases
    ]
    with_closed = [b for b in unref if b["closed_pr_head"]]
    expected = {
        "remote_branches": len(branches),
        "open_prs": len(prs),
        "branches_neither_open_pr_head_nor_base": len(unref),
        "closed_prs_queried": len(closed),
        "remote_branches_unreferenced_by_open_pr_but_head_of_closed_pr": len(with_closed),
        "remote_branches_no_known_open_or_closed_pr_head": len(unref)-len(with_closed),
    }
    if any(counts.get(k) != n or type(counts.get(k)) is not int
           for k, n in expected.items()):
        raise ValueError("census inconsistent")
    for superseded in census.get("closed_as_superseded", []):
        if (superseded.get("pr") not in closed_numbers
                or superseded.get("successor") not in open_numbers
                or not SHA.fullmatch(superseded.get("source_sha", ""))):
            raise ValueError("supersession provenance inconsistent")
    merged = census.get("feature_merge")
    if (not isinstance(merged, dict) or merged.get("pr") not in open_numbers
            or not SHA.fullmatch(merged.get("commit", ""))
            or type(merged.get("protected_main_merged")) is not bool
            or merged.get("protected_main_merged") is not False
            or not isinstance(merged.get("parents"), list)
            or len(merged["parents"]) != 2
            or any(not SHA.fullmatch(p) for p in merged["parents"])):
        raise ValueError("unqualified merge metadata")
    if not census.get("limitations") or "snapshot_date" not in census:
        raise ValueError("manifest limitations omitted")
    return expected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="docs/reconciliation/r040-remote-ref-census-2026-11-23.json",
    )
    arguments = parser.parse_args()
    try:
        data = json.loads(Path(arguments.input).read_text(encoding="utf-8"))
        validate(data)
    except (OSError, ValueError, TypeError, KeyError):
        print("WINEBOT_REF_CENSUS=REJECTED")
        return 1
    print("WINEBOT_REF_CENSUS=VALIDATED_SNAPSHOT_ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
