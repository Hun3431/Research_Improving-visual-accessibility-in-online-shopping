# -*- coding: utf-8 -*-
"""수집 현황 집계: 플랫폼 × 상품군 표 + 부족분 산출.

사용법:
  python -m pcrawler.status_report                 # 표 출력
  python -m pcrawler.status_report --need 20       # 20건 이하 항목만 표시
"""
import argparse
import glob
import json
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CATEGORY_MAP = ROOT / "configs" / "category_map.yaml"
PLATFORMS = [("11st", "11번가"), ("gmarket", "G마켓"), ("auction", "옥션")]


def leaf_list():
    cfg = yaml.safe_load(CATEGORY_MAP.read_text(encoding="utf-8"))
    return [(l["unified"], l["name"]) for l in cfg["leaves"] if l.get("schema_unit")]


def load_valid(platform):
    """중복 제거 + 상세가 실제로 채워진 레코드만."""
    seen, out = set(), []
    patterns = [str(ROOT / "data" / "raw" / platform / "*.json")]
    if platform == "gmarket":   # 차단 전 정상분 보존본 포함
        patterns.append(str(ROOT / "data" / "raw" / "_partial" / "gmarket_ok_before_block.json"))
    for pat in patterns:
        for f in sorted(glob.glob(pat)):
            if "_test" in f or "merged" in f:
                continue
            try:
                recs = json.loads(Path(f).read_text(encoding="utf-8"))
            except Exception:
                continue
            for r in recs:
                pid = r["source"].get("product_id")
                if not pid or pid in seen:
                    continue
                d = r.get("detail", {})
                if not (d.get("price") or d.get("description_image_urls")):
                    continue
                seen.add(pid)
                out.append(r)
    return out


def collect_counts():
    counts = {}
    for key, _ in PLATFORMS:
        c = defaultdict(int)
        for r in load_valid(key):
            c[r["source"]["unified_category"]] += 1
        counts[key] = c
    return counts


def report(target=50, need_below=None):
    leaves = leaf_list()
    counts = collect_counts()
    print(f"{'상품군':<14}{'11번가':>8}{'G마켓':>8}{'옥션':>8}{'합계':>8}")
    print("-" * 54)
    tot = defaultdict(int)
    grand = 0
    for u, name in leaves:
        row = [counts[k].get(u, 0) for k, _ in PLATFORMS]
        s = sum(row)
        grand += s
        for (k, _), v in zip(PLATFORMS, row):
            tot[k] += v
        print(f"{name:<14}{row[0]:>8}{row[1]:>8}{row[2]:>8}{s:>8}")
    print("-" * 54)
    print(f"{'합계':<14}{tot['11st']:>8}{tot['gmarket']:>8}{tot['auction']:>8}{grand:>8}")
    goal = target * len(leaves) * len(PLATFORMS)
    print(f"\n목표 {target}건 × 상품군 {len(leaves)} × {len(PLATFORMS)}사 = {goal}건 | "
          f"현재 {grand}건 ({grand*100//goal}%)")

    if need_below is not None:
        print(f"\n=== {need_below}건 이하 (재수집 대상) ===")
        any_need = False
        for k, label in PLATFORMS:
            need = [(n, counts[k].get(u, 0)) for u, n in leaves if counts[k].get(u, 0) <= need_below]
            if need:
                any_need = True
                print(f"  [{label}] " + ", ".join(f"{n}({c})" for n, c in need))
        if not any_need:
            print("  없음 ✅")
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=50)
    ap.add_argument("--need", type=int, default=None, help="이 수치 이하 항목을 재수집 대상으로 표시")
    a = ap.parse_args()
    report(a.target, a.need)
