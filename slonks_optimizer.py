#!/usr/bin/env python3
"""Optimize merge pairs from pairs.csv into ranked_pairs.csv and merge_plan.csv."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List


def read_pairs(path: Path) -> List[Dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows


def write_csv(path: Path, rows: List[Dict[str, str]], headers: List[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)


def to_float(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return float("-inf")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="pairs.csv")
    ap.add_argument("--ranked", default="ranked_pairs.csv")
    ap.add_argument("--plan", default="merge_plan.csv")
    args = ap.parse_args()

    rows = read_pairs(Path(args.pairs))
    ok_rows = [r for r in rows if r.get("status") == "ok" and r.get("result_slop")]

    ranked = sorted(ok_rows, key=lambda r: to_float(r["result_slop"]), reverse=True)
    for i, r in enumerate(ranked, start=1):
        r["rank"] = str(i)

    write_csv(
        Path(args.ranked),
        ranked,
        ["rank", "survivor_token_id", "donor_token_id", "level", "result_slop", "status", "note"],
    )

    used = set()
    plan: List[Dict[str, str]] = []
    for r in ranked:
        s = r["survivor_token_id"]
        d = r["donor_token_id"]
        if s in used or d in used:
            continue
        plan.append(r)
        used.add(s)
        used.add(d)

    write_csv(
        Path(args.plan),
        plan,
        ["survivor_token_id", "donor_token_id", "level", "result_slop", "status", "note"],
    )
    print(f"done: ranked={args.ranked}, plan={args.plan}, candidates={len(ranked)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
