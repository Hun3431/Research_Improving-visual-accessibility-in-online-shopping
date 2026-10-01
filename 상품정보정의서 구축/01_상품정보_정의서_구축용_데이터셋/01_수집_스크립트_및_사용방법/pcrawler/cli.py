# -*- coding: utf-8 -*-
"""사용법:
  # 테스트(각 leaf 1~3개만)
  python -m pcrawler.cli 11st --test
  # 본수집 (욕실용품 100개)
  python -m pcrawler.cli 11st --limit 100
"""
import argparse

from .pipeline import run


def main():
    ap = argparse.ArgumentParser(description="카테고리 기반 상품 수집 (OCR 전단계)")
    ap.add_argument("platform", help="플랫폼 (예: 11st)")
    ap.add_argument("--limit", type=int, default=100, help="플랫폼당 총 수집 개수")
    ap.add_argument("--per-leaf", type=int, default=None, help="세분류별 상한 (기본: limit/leaf수)")
    ap.add_argument("--test", action="store_true", help="소량 테스트(leaf 2개, 총 3개)")
    ap.add_argument("--headless", action="store_true", help="헤드리스 실행")
    ap.add_argument("--out", default=None, help="출력 디렉토리")
    ap.add_argument("--leaves", default=None, help="특정 unified leaf만 (쉼표구분, 이어받기용)")
    args = ap.parse_args()
    only = args.leaves.split(",") if args.leaves else None
    run(args.platform, limit=args.limit, per_leaf=args.per_leaf,
        test=args.test, headless=args.headless, out_dir=args.out, only_leaves=only)


if __name__ == "__main__":
    main()
