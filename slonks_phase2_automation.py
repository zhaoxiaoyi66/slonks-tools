#!/usr/bin/env python3
"""Stage-2 Slonks Merge Lab no-gas preview automation.

Reads holdings.csv, tests same-level NFT pairs in both directions on
https://slonks.xyz/merge-lab using Playwright UI automation, then writes pairs.csv
and calls slonks_optimizer.py to generate ranked_pairs.csv and merge_plan.csv.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


@dataclass
class Holding:
    token_id: int
    level: int


def read_holdings(path: Path) -> List[Holding]:
    rows: List[Holding] = []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"token_id", "level"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("holdings.csv 必须包含列: token_id, level")
        for row in reader:
            rows.append(Holding(token_id=int(row["token_id"]), level=int(row["level"])))
    return rows


def write_pairs(path: Path, rows: List[Dict[str, str]]) -> None:
    headers = [
        "survivor_token_id",
        "donor_token_id",
        "level",
        "result_slop",
        "status",
        "note",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)


def set_token_input(page, label_keyword: str, value: int) -> None:
    input_box = page.get_by_label(label_keyword, exact=False)
    if input_box.count() == 0:
        input_box = page.locator(f"input[placeholder*='{label_keyword}' i]")
    input_box.first.fill(str(value))


def read_preview_slop(page) -> str:
    candidates = [
        page.locator("text=/result\\s*slop/i").first,
        page.locator("text=/preview/i").first,
        page.locator("text=/slop/i").first,
    ]
    for loc in candidates:
        if loc.count() == 0:
            continue
        text = loc.inner_text(timeout=2000)
        # pull last number-like token
        parts = [p for p in text.replace(",", " ").split() if any(ch.isdigit() for ch in p)]
        if parts:
            return parts[-1]
    raise RuntimeError("未找到 preview 结果中的 slop 字段")


def run_preview_for_pair(page, survivor: int, donor: int, wait_s: float) -> Dict[str, str]:
    set_token_input(page, "survivor", survivor)
    set_token_input(page, "donor", donor)

    # click only preview/no-gas buttons
    preview_btn = page.get_by_role("button", name="preview")
    if preview_btn.count() == 0:
        preview_btn = page.get_by_text("preview", exact=False)
    if preview_btn.count() == 0:
        raise RuntimeError("页面上找不到 Preview 按钮")
    preview_btn.first.click()
    time.sleep(wait_s)

    result_slop = read_preview_slop(page)
    return {
        "survivor_token_id": str(survivor),
        "donor_token_id": str(donor),
        "result_slop": result_slop,
        "status": "ok",
        "note": "no-gas preview",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--holdings", default="holdings.csv")
    p.add_argument("--pairs", default="pairs.csv")
    p.add_argument("--optimizer", default="slonks_optimizer.py")
    p.add_argument("--headless", action="store_true", default=False)
    p.add_argument("--wait", type=float, default=1.2, help="seconds to wait after clicking preview")
    args = p.parse_args()

    holdings = read_holdings(Path(args.holdings))
    by_level: Dict[int, List[int]] = {}
    for h in holdings:
        by_level.setdefault(h.level, []).append(h.token_id)

    rows: List[Dict[str, str]] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=args.headless)
        page = browser.new_page()
        page.goto("https://slonks.xyz/merge-lab", wait_until="domcontentloaded", timeout=60000)

        # safety guard: never click merge/transaction buttons
        merge_like = page.get_by_role("button", name="merge")
        if merge_like.count() > 0:
            print("[safety] 检测到 merge 按钮，脚本不会点击它，仅使用 preview。")

        for level, ids in by_level.items():
            for a, b in itertools.combinations(ids, 2):
                for survivor, donor in ((a, b), (b, a)):
                    try:
                        r = run_preview_for_pair(page, survivor, donor, args.wait)
                        r["level"] = str(level)
                    except (RuntimeError, PlaywrightTimeoutError) as e:
                        r = {
                            "survivor_token_id": str(survivor),
                            "donor_token_id": str(donor),
                            "level": str(level),
                            "result_slop": "",
                            "status": "error",
                            "note": str(e),
                        }
                    rows.append(r)

        browser.close()

    write_pairs(Path(args.pairs), rows)

    proc = subprocess.run(
        [sys.executable, args.optimizer, "--pairs", args.pairs],
        check=False,
        text=True,
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
