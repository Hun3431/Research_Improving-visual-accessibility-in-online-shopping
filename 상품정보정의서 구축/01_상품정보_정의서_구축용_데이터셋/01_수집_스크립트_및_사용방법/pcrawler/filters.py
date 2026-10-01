# -*- coding: utf-8 -*-
"""목록 페이지 필터링.

1) 광고(is_ad) 제거          — 카테고리 organic이 아닌 스폰서 노출
2) 카탈로그(is_catalog) 제거  — '가격비교' 버튼이 붙은, 하위 여러 판매자를 묶는 상품
3) 완전 동일 상품 dedupe      — 같은 product_id, 또는 정규화된 이름이 완전히 같은 것
"""
import re


def _norm_name(name):
    if not name:
        return ""
    n = re.sub(r"\[[^\]]*\]", "", name)          # [브랜드] 류 대괄호 제거
    n = re.sub(r"\s+", "", n)                      # 모든 공백 제거
    return n.lower()


def filter_listing(cards):
    """필터 결과와 통계를 함께 반환: (kept, stats)."""
    stats = {"total": len(cards), "ad": 0, "catalog": 0, "dup": 0, "no_id": 0, "kept": 0}
    kept = []
    seen_ids = set()
    seen_names = set()
    for c in cards:
        if c.get("is_ad"):
            stats["ad"] += 1
            continue
        if c.get("is_catalog"):
            stats["catalog"] += 1
            continue
        pid = c.get("product_id")
        if not pid:
            stats["no_id"] += 1
            continue
        nkey = _norm_name(c.get("name_raw"))
        if pid in seen_ids or (nkey and nkey in seen_names):
            stats["dup"] += 1
            continue
        seen_ids.add(pid)
        if nkey:
            seen_names.add(nkey)
        kept.append(c)
    stats["kept"] = len(kept)
    return kept, stats
