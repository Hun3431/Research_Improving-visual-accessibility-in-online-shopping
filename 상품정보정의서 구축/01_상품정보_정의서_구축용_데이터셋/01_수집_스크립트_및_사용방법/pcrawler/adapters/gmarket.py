# -*- coding: utf-8 -*-
"""G마켓 어댑터 (CDP-진짜크롬 세션 전제).

이베이코리아엔 '욕실용품' 전용 카테고리가 없어 검색어 기반으로 leaf를 수집한다.
목록: /n/search (.box__item-container, 광고=.box__advertisement-container)
상세: item.gmarket.co.kr/Item?goodscode=... (상세 iframe ItemDetailV2)
"""
import re
import urllib.parse

from bs4 import BeautifulSoup

from .base import BaseAdapter
from ..browser import polite_sleep

SEARCH_URL = "https://www.gmarket.co.kr/n/search?keyword={q}"


class GmarketAdapter(BaseAdapter):
    platform = "gmarket"
    home_url = "https://www.gmarket.co.kr/"

    def canonical_url(self, product_id):
        return f"https://item.gmarket.co.kr/Item?goodscode={product_id}"

    # ---------------- 목록 (검색 기반) ----------------
    def browse_search(self, page, query, limit, max_pages=4):
        cards, seen = [], set()
        for pnum in range(1, max_pages + 1):
            url = SEARCH_URL.format(q=urllib.parse.quote(query))
            if pnum > 1:
                url += f"&p={pnum}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=40000)
            except Exception:
                break
            polite_sleep(1.5, 2.8)
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(1200)
            new = 0
            for c in self._parse_listing(page.content()):
                key = c["product_id"] or ("AD:" + (c["name_raw"] or ""))
                if key in seen:
                    continue
                seen.add(key)
                cards.append(c)
                new += 1
            clean = sum(1 for c in cards if c["product_id"] and not c["is_ad"] and not c["is_catalog"])
            if clean >= limit or new == 0:
                break
        return cards

    # 파이프라인 호환: leaf 수집 진입점
    def browse_category(self, page, leaf_query, limit):
        return self.browse_search(page, leaf_query, limit)

    @staticmethod
    def _parse_listing(html):
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for it in soup.select(".box__item-container"):
            a = it.select_one("a.link__item[href*='goodscode'], a[href*='goodscode']")
            href = (a.get("href") if a else "") or ""
            m = re.search(r"goodscode=(\d+)", href)
            pid = m.group(1) if m else None
            is_ad = it.select_one(".box__advertisement-container") is not None
            name_el = it.select_one(".text__item") or it.select_one(".text__item-title")
            price_el = it.select_one(".box__item-price .text__value") or it.select_one(".text__value")
            out.append({
                "product_id": pid,
                "product_url": f"https://item.gmarket.co.kr/Item?goodscode={pid}" if pid else None,
                "name_raw": name_el.get_text(" ", strip=True) if name_el else None,
                "price_raw": price_el.get_text(" ", strip=True) if price_el else None,
                "is_ad": is_ad,
                "is_catalog": False,  # 검색결과엔 가격비교 카탈로그 없음
            })
        return out

    # ---------------- 상세 ----------------
    def parse_detail(self, page, product_url):
        page.goto(product_url, wait_until="domcontentloaded", timeout=40000)
        polite_sleep()
        for _ in range(4):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(1000)
        m = re.search(r"goodscode=(\d+)", page.url)
        pid = m.group(1) if m else None
        opts = self.collect_option_names(page)
        return {
            "final_url": page.url,
            "option_count": len(opts),
            "is_bundle": self.is_bundle(opts),
            "product_image_urls": self._product_images(page),
            "description_image_urls": self._description_images(page),
            "seller_name": self._text(page, ".text__seller-name, .link__shop, span.text__seller"),
            "regular_price": self._price(page, ".box__price-original, span.price_original, del"),
            "price": self._price(page, "strong.price_real, .box__price-seller"),
        }

    @staticmethod
    def _text(page, sel):
        el = page.query_selector(sel)
        if el:
            t = el.inner_text().strip()
            return t if t and len(t) <= 40 else (t[:40] if t else None)
        return None

    @staticmethod
    def _price(page, sel):
        """요소 텍스트에서 'N,NNN원' 첫 매칭만 깔끔히 추출(할인률 등 노이즈 제거)."""
        el = page.query_selector(sel)
        if not el:
            return None
        m = re.search(r"[\d,]{2,}\s*원", el.inner_text())
        return m.group(0).replace(" ", "") if m else None

    @staticmethod
    def _og_image(page):
        """뷰어를 못 찾을 때의 폴백. og:image 는 대표이미지를 가리킨다."""
        try:
            og = page.evaluate(
                "() => { const m = document.querySelector('meta[property=\"og:image\"]');"
                " return m ? m.content : null; }")
        except Exception:
            return []
        if not og:
            return []
        return ["https:" + og if og.startswith("//") else og]

    @staticmethod
    def _imgs_from(scope):
        found = []
        for img in scope.query_selector_all("img"):
            src = (img.get_attribute("src") or img.get_attribute("data-src")
                   or img.get_attribute("data-original"))
            if src:
                if src.startswith("//"):
                    src = "https:" + src
                if src.startswith("http"):
                    found.append(src)
        return list(dict.fromkeys(found))

    def _description_images(self, page):
        """상세정보 iframe(ItemDetailV2) 내부 이미지 = OCR 대상."""
        frame = next((f for f in page.frames if f.url and re.search(r"ItemDetail|/Detail", f.url)), None)
        if frame:
            try:
                frame.wait_for_selector("img", timeout=5000)
            except Exception:
                pass
            urls = self._imgs_from(frame)
            if urls:
                return urls
        cont = page.query_selector("div[class*='detail'], #vip-tab_detail")
        return self._imgs_from(cont) if cont else []

    def _product_images(self, page):
        # 상단 이미지 뷰어(ul.viewer)가 실제 대표 상품컷이다.
        # 이전 셀렉터(.box__viewer-image 등)는 DOM 과 맞지 않아 항상 빈 배열이었다.
        for sel in ["ul.viewer li img", ".viewer img", ".box__thumbnail img"]:
            els = page.query_selector_all(sel)
            if els:
                urls = []
                for img in els:
                    src = img.get_attribute("src") or img.get_attribute("data-src")
                    if src:
                        if src.startswith("//"):
                            src = "https:" + src
                        urls.append(src)
                if urls:
                    return list(dict.fromkeys(urls))
        return self._og_image(page)
