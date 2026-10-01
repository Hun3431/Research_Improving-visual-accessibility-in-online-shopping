# -*- coding: utf-8 -*-
"""어댑터 공통 인터페이스. 플랫폼별 어댑터는 이걸 구현한다."""
import re
import statistics
from abc import ABC, abstractmethod

_OPT_LABEL = re.compile(r"^\[[^\]]*\]")          # '[옵션 1]' 같은 접두 라벨
_PLACEHOLDER = ("선택", "옵션선택", "옵션 선택", "선택하세요", "필수선택")


class BaseAdapter(ABC):
    platform = None      # "11st"
    home_url = None

    # ---------------- 옵션 / 모음전 판정 (플랫폼 공통) ----------------
    @staticmethod
    def collect_option_names(page):
        """상품 옵션명 수집. 이미지·수량 셀렉터에서 나오는 '01','02' 같은
        맨숫자와 플레이스홀더는 상품 옵션이 아니므로 제외한다."""
        names = []
        for sel in ["select option", "[class*='option'] li"]:
            for el in page.query_selector_all(sel):
                try:
                    t = (el.inner_text() or "").strip().split("\n")[0].strip()
                except Exception:
                    continue
                t = _OPT_LABEL.sub("", t).strip()
                if not t or t in _PLACEHOLDER:
                    continue
                if re.fullmatch(r"[\d,]+", t):   # 맨숫자(01, 02 …) → 옵션 아님
                    continue
                names.append(t)
            if names:
                break
        return names

    @staticmethod
    def is_bundle(names):
        """모음전(하나의 리스팅에 서로 다른 상품 여러 개) 판정.

        두 가지 신호를 쓴다.
        1) 옵션명이 '01.' '02.' 처럼 번호 목록
        2) 옵션명이 길다 — 모음전은 옵션마다 '커브 프라이팬/웍 1P', '법랑 냄비'처럼
           상품명이 통째로 들어가 길고, 사이즈('22cm')·색상('블랙') 변형은 짧다.
        """
        if len(names) < 5:
            return False
        numbered = sum(1 for n in names if re.match(r"^\d{1,2}\s*[.)]", n))
        if numbered >= max(3, len(names) * 0.5):
            return True
        return statistics.median(len(n) for n in names) >= 12

    @abstractmethod
    def browse_category(self, page, leaf_id, limit):
        """카테고리 leaf 목록을 훑어 ListCard(dict) 리스트를 반환.
        각 카드: {name, price_raw, product_url, product_id, is_ad, is_catalog, ...}
        필터링 전 원본(광고/카탈로그 포함)을 그대로 반환한다."""

    @abstractmethod
    def parse_detail(self, page, product_url):
        """상세페이지 진입 → {product_image_urls, description_image_urls,
        regular_price, price, seller_name, notice_raw} 등 원본 수집."""

    def canonical_url(self, product_id):
        return product_id
