# -*- coding: utf-8 -*-
"""부족한 상품군만 골라 교차(rotate) 수집하는 보충 수집기.

collect_rotate 의 문제: 회차마다 cli 를 새로 호출하는데 이전 회차 수집분을 몰라
항상 첫 상품군부터 다시 시작 → 같은 상품을 반복 수집했다(옥션 570건 중 고유 133건).

여기서는 매 회차 시작 전에 **디스크의 기존 수집분을 다시 세어** 아직 목표에 못 미친
상품군만 --leaves 로 넘긴다. 그래서 회차가 갈수록 남은 상품군에 집중된다.

사용법:
  python -u -m pcrawler.collect_fill --platforms auction,11st --target 50 --rounds 8
"""
import argparse
import glob
import json
import os
import random
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CATEGORY_MAP = ROOT / "configs" / "category_map.yaml"


def leaf_list():
    cfg = yaml.safe_load(CATEGORY_MAP.read_text(encoding="utf-8"))
    return [(l["unified"], l["name"]) for l in cfg["leaves"] if l.get("schema_unit")]


def current_counts(platform):
    """디스크의 기존 수집분에서 상품군별 유효 건수를 센다(중복 제거)."""
    seen, cnt = set(), defaultdict(int)
    for f in sorted(glob.glob(str(ROOT / "data" / "raw" / platform / "*.json"))):
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
                continue          # 차단 등으로 상세가 빈 레코드는 미달로 간주
            seen.add(pid)
            cnt[r["source"]["unified_category"]] += 1
    return cnt


def run_chunk(platform, leaves, per_leaf, need_total, sleep_scale):
    cmd = [sys.executable, "-u", "-m", "pcrawler.cli", platform,
           "--limit", str(need_total), "--per-leaf", str(per_leaf),
           "--leaves", ",".join(leaves)]
    print(f"\n{'='*66}\n▶ {platform}: 부족 상품군 {len(leaves)}개 수집 "
          f"(목표 {need_total}건, 배율 {sleep_scale}x)\n{'='*66}", flush=True)
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True,
                       env={**os.environ, "PCRAWLER_SLEEP_SCALE": str(sleep_scale)})
    out = p.stdout
    print(out[-2500:], flush=True)
    blocked = "차단으로 판단" in out
    got = 0
    for line in out.splitlines():
        if line.startswith("완료:"):
            try:
                got = int(line.split("완료:")[1].split("건")[0].strip())
            except Exception:
                pass
    return got, blocked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platforms", default="auction,11st")
    ap.add_argument("--target", type=int, default=50, help="상품군별 목표 건수")
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--chunk-leaves", type=int, default=3, help="회차당 다룰 상품군 수")
    ap.add_argument("--rest", type=int, default=90)
    ap.add_argument("--sleep-scale", type=float, default=2.0)
    args = ap.parse_args()

    plats = [p.strip() for p in args.platforms.split(",") if p.strip()]
    leaves = leaf_list()
    dead = set()

    for rnd in range(1, args.rounds + 1):
        alive = [p for p in plats if p not in dead]
        if not alive:
            print("\n모든 플랫폼 차단 → 종료", flush=True)
            break
        progressed = False
        print(f"\n########## ROUND {rnd}/{args.rounds} ##########", flush=True)
        for plat in alive:
            cnt = current_counts(plat)
            need = [(u, n, args.target - cnt.get(u, 0)) for u, n in leaves
                    if cnt.get(u, 0) < args.target]
            if not need:
                print(f"  {plat}: 모든 상품군 목표 달성 ✅", flush=True)
                dead.add(plat)
                continue
            need.sort(key=lambda x: -x[2])                 # 가장 부족한 것부터
            batch = need[:args.chunk_leaves]
            print(f"  {plat} 부족: " + ", ".join(f"{n}({args.target-d if False else d}부족)"
                                                 for _, n, d in batch), flush=True)
            got, blocked = run_chunk(plat, [u for u, _, _ in batch],
                                     args.target, sum(d for _, _, d in batch),
                                     args.sleep_scale)
            print(f"◀ {plat} 회차 결과 {got}건" + ("  ⛔차단 → 중단" if blocked else ""), flush=True)
            if blocked:
                dead.add(plat)
                continue
            if got > 0:
                progressed = True
            rest = args.rest + random.randint(0, 30)
            print(f"   … {rest}초 휴식", flush=True)
            time.sleep(rest)
        if not progressed:
            print("\n이번 회차에 아무것도 수집되지 않음 → 종료", flush=True)
            break

    print("\n" + "=" * 66)
    print("보충 수집 종료. 상품군별 최종:", flush=True)
    for plat in plats:
        cnt = current_counts(plat)
        line = ", ".join(f"{n} {cnt.get(u,0)}" for u, n in leaves)
        print(f"  [{plat}] {line}", flush=True)


if __name__ == "__main__":
    main()
