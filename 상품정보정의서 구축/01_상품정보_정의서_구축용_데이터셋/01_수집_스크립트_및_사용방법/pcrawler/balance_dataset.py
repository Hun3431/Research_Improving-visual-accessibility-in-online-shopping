# -*- coding: utf-8 -*-
"""상품군마다 정확히 N개를, 플랫폼 비율이 최대한 균등하도록 뽑아 별도 데이터셋으로 복제.

- 원본(data/raw/*)은 건드리지 않는다.
- 플랫폼별 보유량이 목표 몫보다 적으면 있는 만큼만 쓰고, 남은 몫을 여유 있는
  플랫폼에 재분배한다(water-filling). → 가능한 한 33/33/34 에 가깝게.

사용법:
  python -m pcrawler.balance_dataset --per-group 100 \
      --out data/datasets/kitchen/kitchen_100each.json
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
    seen, out = set(), []
    pats = [str(ROOT / "data" / "raw" / platform / "*.json")]
    if platform == "gmarket":
        pats.append(str(ROOT / "data" / "raw" / "_partial" / "gmarket_ok_before_block.json"))
    for pat in pats:
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


def water_fill(avail, total):
    """avail: {platform: 보유수}. total 개를 최대한 균등 분배(보유량 상한)."""
    alloc = {p: 0 for p in avail}
    remaining, n = total, len(avail)
    for p in sorted(avail, key=lambda x: avail[x]):     # 적게 가진 플랫폼부터
        if n == 0:
            break
        share = -(-remaining // n)                       # ceil
        take = min(avail[p], share)
        alloc[p] = take
        remaining -= take
        n -= 1
    return alloc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-group", type=int, default=100)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    leaves = leaf_list()
    # (unified, platform) → 레코드 리스트
    pool = defaultdict(list)
    for key, _ in PLATFORMS:
        for r in load_valid(key):
            pool[(r["source"]["unified_category"], key)].append(r)

    selected = []
    print(f"{'상품군':<14}{'11번가':>8}{'G마켓':>8}{'옥션':>8}{'합계':>7}   (보유량)")
    print("-" * 66)
    for u, name in leaves:
        avail = {k: len(pool[(u, k)]) for k, _ in PLATFORMS}
        total_avail = sum(avail.values())
        alloc = water_fill(avail, min(args.per_group, total_avail))
        for k, _ in PLATFORMS:
            selected.extend(pool[(u, k)][:alloc[k]])
        row = f"{alloc['11st']:>8}{alloc['gmarket']:>8}{alloc['auction']:>8}{sum(alloc.values()):>7}"
        av = f"   ({avail['11st']}/{avail['gmarket']}/{avail['auction']})"
        print(f"{name:<14}{row}{av}")
    print("-" * 66)
    # 플랫폼별 합
    from collections import Counter
    bp = Counter(r["source"]["platform"] for r in selected)
    print(f"{'합계':<14}{bp['11st']:>8}{bp['gmarket']:>8}{bp['auction']:>8}{len(selected):>7}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {out}  ({len(selected)}건)")


if __name__ == "__main__":
    main()
