# -*- coding: utf-8 -*-
"""플랫폼을 교차(rotate)하며 조금씩 수집한다.

한 사이트에 요청을 몰면 차단되므로(실제로 G마켓이 500건 연속 수집 중 403),
플랫폼 A 100건 → 휴식 → 플랫폼 B 100건 → 휴식 … 식으로 번갈아 돈다.
각 회차는 별도 파일로 저장되며, 파이프라인의 차단 감지가 걸리면 그 회차만 조기 종료된다.

사용법:
  python -u -m pcrawler.collect_rotate --platforms auction,11st --chunk 100 --rounds 5
"""
import argparse
import subprocess
import sys
import time
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_chunk(platform, chunk, per_leaf, sleep_scale):
    cmd = [sys.executable, "-u", "-m", "pcrawler.cli", platform,
           "--limit", str(chunk), "--per-leaf", str(per_leaf)]
    env_prefix = f"PCRAWLER_SLEEP_SCALE={sleep_scale} "
    print(f"\n{'='*66}\n▶ {platform} {chunk}건 수집 시작 (대기배율 {sleep_scale}x)\n{'='*66}", flush=True)
    p = subprocess.run(cmd, cwd=ROOT, env={**__import__("os").environ,
                                           "PCRAWLER_SLEEP_SCALE": str(sleep_scale)},
                       capture_output=True, text=True)
    out = p.stdout
    print(out[-3000:], flush=True)          # 회차 로그 꼬리만
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
    ap.add_argument("--platforms", default="auction,11st", help="교차할 플랫폼(쉼표)")
    ap.add_argument("--chunk", type=int, default=100, help="회차당 수집 건수")
    ap.add_argument("--per-leaf", type=int, default=50, help="상품군당 상한")
    ap.add_argument("--rounds", type=int, default=5, help="플랫폼별 최대 회차 수")
    ap.add_argument("--rest", type=int, default=90, help="회차 사이 휴식(초)")
    ap.add_argument("--sleep-scale", type=float, default=2.0, help="요청 간 대기 배율")
    args = ap.parse_args()

    plats = [p.strip() for p in args.platforms.split(",") if p.strip()]
    totals = {p: 0 for p in plats}
    dead = set()   # 차단된 플랫폼은 이후 회차에서 제외

    for rnd in range(1, args.rounds + 1):
        alive = [p for p in plats if p not in dead]
        if not alive:
            print("\n모든 플랫폼이 차단 상태 → 종료", flush=True)
            break
        print(f"\n########## ROUND {rnd}/{args.rounds}  대상={alive} ##########", flush=True)
        for plat in alive:
            got, blocked = run_chunk(plat, args.chunk, args.per_leaf, args.sleep_scale)
            totals[plat] += got
            print(f"◀ {plat} 회차 결과 {got}건 (누적 {totals[plat]})"
                  + ("  ⛔차단감지 → 이 플랫폼 중단" if blocked else ""), flush=True)
            if blocked:
                dead.add(plat)
                continue
            rest = args.rest + random.randint(0, 30)
            print(f"   … {rest}초 휴식", flush=True)
            time.sleep(rest)

    print("\n" + "=" * 66)
    print("교차 수집 종료. 플랫폼별 누적:", flush=True)
    for p in plats:
        print(f"  {p}: {totals[p]}건" + ("  (차단으로 중단)" if p in dead else ""), flush=True)


if __name__ == "__main__":
    main()
