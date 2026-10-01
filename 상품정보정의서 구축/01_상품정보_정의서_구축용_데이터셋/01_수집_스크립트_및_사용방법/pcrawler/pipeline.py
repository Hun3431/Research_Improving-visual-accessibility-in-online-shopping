# -*- coding: utf-8 -*-
"""수집 오케스트레이션: 카테고리 목록 → 필터 → 상세 → raw 저장.

범위: OCR 전단계까지 (이미지 URL은 보존, 이미지 내용 추출은 다음 단계).
"""
import json
import math
from itertools import zip_longest
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

from .adapters import ADAPTERS, CDP_PLATFORMS, SEARCH_PLATFORMS
from .browser import browser_session, cdp_session, warmup
from .filters import filter_listing

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
CATEGORY_MAP = ROOT / "configs" / "category_map.yaml"
BLOCK_STREAK = 8   # 상세 연속 실패 이 횟수면 차단으로 판단하고 중단


def load_leaves(platform):
    """schema_unit=True leaf 목록을 반환.
    - 카테고리 플랫폼(11st 등): 해당 플랫폼 카테고리 id 목록으로 수집
    - 검색 플랫폼(gmarket/auction, 욕실용품 카테고리 없음): search_query로 수집
    각 leaf: {unified, name, mode, targets(list)}"""
    cfg = yaml.safe_load(CATEGORY_MAP.read_text(encoding="utf-8"))
    scope = cfg["scope"]
    search_mode = platform in SEARCH_PLATFORMS
    leaves = []
    for lf in cfg["leaves"]:
        if not lf.get("schema_unit"):
            continue
        if search_mode:
            # search_queries(복수) 우선, 없으면 search_query(단수)
            qs = lf.get("search_queries") or ([lf["search_query"]] if lf.get("search_query") else [])
            if qs:
                leaves.append({"unified": lf["unified"], "name": lf["name"],
                               "mode": "search", "targets": list(qs)})
        else:
            ids = (lf.get("platforms") or {}).get(platform)
            if ids:
                leaves.append({"unified": lf["unified"], "name": lf["name"],
                               "mode": "category", "targets": ids})
    return scope, leaves


def run(platform, limit=100, per_leaf=None, test=False, headless=False, out_dir=None, only_leaves=None):
    if platform not in ADAPTERS:
        raise SystemExit(f"미지원 플랫폼: {platform} (지원: {list(ADAPTERS)})")
    adapter = ADAPTERS[platform]()
    scope, leaves = load_leaves(platform)
    if not leaves:
        raise SystemExit(f"{platform} 에 매핑된 schema_unit leaf 가 없습니다.")

    if only_leaves:  # 특정 unified leaf 만 (이어받기용)
        want = set(only_leaves)
        leaves = [lf for lf in leaves if lf["unified"] in want]
    if test:
        leaves = leaves[:2]
        limit = min(limit, 3)
    if per_leaf is None:
        per_leaf = max(1, math.ceil(limit / len(leaves)))

    use_cdp = platform in CDP_PLATFORMS
    run_id = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    print(f"[{platform}] scope={scope['name']} leaves={len(leaves)} limit={limit} "
          f"per_leaf={per_leaf} test={test} mode={'CDP-검색' if use_cdp else '카테고리'} run_id={run_id}")

    out_dir_p = Path(out_dir) if out_dir else (ROOT / "data" / "raw" / platform)
    out_dir_p.mkdir(parents=True, exist_ok=True)
    out_path = out_dir_p / f"{run_id}{'_test' if test else ''}.json"

    def save(recs):
        out_path.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")

    records = []
    consecutive_empty = 0
    blocked = False
    session_cm = cdp_session() if use_cdp else browser_session(headless=headless)
    with session_cm as page:
        ctx = page.context  # 페이지가 닫혔을 때 새 탭을 만들기 위해 보관
        if not use_cdp:
            warmup(page, adapter.home_url)
        for leaf in leaves:
            if len(records) >= limit or blocked:
                break
            print(f"\n── leaf {leaf['unified']} ({leaf['name']}) {leaf['mode']}={leaf['targets']}")
            # 타겟(검색어/카테고리)별로 모은 뒤 라운드로빈으로 섞는다.
            # 그냥 이어붙이면 앞쪽 질의 결과에 수집분이 쏠려 다양성이 떨어진다.
            per_target = []
            for tgt in leaf["targets"]:
                try:
                    per_target.append(adapter.browse_category(page, tgt, per_leaf))
                except Exception as e:
                    print(f"   목록 수집 실패 target={tgt}: {e}")
                    per_target.append([])
            all_cards = [c for grp in zip_longest(*per_target) for c in grp if c is not None]
            kept, stats = filter_listing(all_cards)
            print(f"   목록 {stats['total']} → 광고 -{stats['ad']} 카탈로그 -{stats['catalog']} "
                  f"중복 -{stats['dup']} = 깔끔 {stats['kept']}")

            # 후보를 순회하며 상세를 받고, 모음전(목록형)은 건너뛴 채 목표치를 채운다.
            got, skipped_bundle = 0, 0
            for card in kept:
                if len(records) >= limit or got >= per_leaf:
                    break
                if page.is_closed():  # 사용자가 탭을 닫는 등으로 죽으면 새 탭으로 복구
                    page = ctx.new_page()
                    print("   (페이지가 닫혀 새 탭으로 복구)")
                print(f"   [{got+1}/{per_leaf}] 상세수집: {(card['name_raw'] or '')[:34]}")
                rec = {
                    "source": {
                        "platform": platform,
                        "product_id": card["product_id"],
                        "product_url": card["product_url"],
                        "unified_category": leaf["unified"],
                        "leaf_name": leaf["name"],
                        "collected_at": datetime.now(KST).isoformat(),
                        "run_id": run_id,
                    },
                    "raw": {
                        "name_raw": card["name_raw"],
                        "list_price_raw": card["price_raw"],
                        "seller_raw": card.get("seller_raw"),
                    },
                    "detail": {},
                }
                try:
                    rec["detail"] = adapter.parse_detail(page, card["product_url"])
                except Exception as e:
                    rec["detail"] = {"error": str(e)}
                    print(f"       상세 실패: {str(e).splitlines()[0][:70]}")
                # 차단 감지: 상세가 연속으로 비어 나오면(가격·이미지 모두 없음) 사이트가
                # 막은 것이므로 즉시 중단한다. 계속 돌면 빈 레코드만 쌓이고 차단이 악화된다.
                if not rec["detail"].get("price") and not rec["detail"].get("description_image_urls"):
                    consecutive_empty += 1
                    if consecutive_empty >= BLOCK_STREAK:
                        blocked = True
                        print(f"\n⛔ 상세 연속 실패 {consecutive_empty}건 → 차단으로 판단, 수집 중단")
                        break
                else:
                    consecutive_empty = 0

                # 상세에서 판매자를 못 얻으면 목록 카드의 판매자로 보완
                if not rec["detail"].get("seller_name") and card.get("seller_raw"):
                    rec["detail"]["seller_name"] = card["seller_raw"]
                if rec["detail"].get("is_bundle"):
                    skipped_bundle += 1
                    print(f"       → 모음전(목록형) 제외 (옵션 {rec['detail'].get('option_count')}개)")
                    continue
                records.append(rec)
                got += 1
                if len(records) % 10 == 0:   # 중간 저장(중단돼도 유실 방지)
                    save(records)
            if skipped_bundle:
                print(f"   모음전 제외 {skipped_bundle}건")

    save(records)
    print(f"\n완료: {len(records)}건 → {out_path}")
    return records, out_path
