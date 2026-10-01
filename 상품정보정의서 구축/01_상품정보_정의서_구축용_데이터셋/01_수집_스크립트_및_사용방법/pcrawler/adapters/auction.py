# -*- coding: utf-8 -*-
"""옥션 어댑터 (CDP-진짜크롬 세션 전제). 이베이코리아라 G마켓과 구조 유사.

목록: /n/search (.section--itemcard, 광고=.section--advertisement)
상세: itempage3.auction.co.kr/DetailView.aspx?itemno=...
"""
import re
import urllib.parse

from bs4 import BeautifulSoup

from .base import BaseAdapter
from ..browser import polite_sleep

SEARCH_URL = "https://www.auction.co.kr/n/search?keyword={q}"


class AuctionAdapter(BaseAdapter):
    platform = "auction"
    home_url = "https://www.auction.co.kr/"

    def canonical_url(self, product_id):
        return f"https://itempage3.auction.co.kr/DetailView.aspx?itemno={product_id}"

    def browse_search(self, page, query, limit, max_pages=4):
        cards, seen = [], set()
        for pnum in range(1, max_pages + 1):
            url = SEARCH_URL.format(q=urllib.parse.quote(query))
            if pnum > 1:
                url += f"&page={pnum}"
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

    def browse_category(self, page, leaf_query, limit):
        return self.browse_search(page, leaf_query, limit)

    @staticmethod
    def _parse_listing(html):
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for it in soup.select(".section--itemcard"):
            a = it.select_one("a.link--itemcard[href*='itemno'], a[href*='itemno']")
            href = (a.get("href") if a else "") or ""
            m = re.search(r"itemno=([A-Za-z0-9]+)", href)
            pid = m.group(1) if m else None
            is_ad = it.select_one(".section--advertisement") is not None
            name_el = it.select_one(".text--title") or it.select_one(".text--itemcard_title")
            price_el = it.select_one(".text--price_seller")
            out.append({
                "product_id": pid,
                "product_url": f"https://itempage3.auction.co.kr/DetailView.aspx?itemno={pid}" if pid else None,
                "name_raw": name_el.get_text(" ", strip=True) if name_el else None,
                "price_raw": price_el.get_text(" ", strip=True) if price_el else None,
                "is_ad": is_ad,
                "is_catalog": False,
            })
        return out

    def parse_detail(self, page, product_url):
        page.goto(product_url, wait_until="domcontentloaded", timeout=40000)
        polite_sleep()
        for _ in range(4):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(1000)
        opts = self.collect_option_names(page)
        return {
            "final_url": page.url,
            "option_count": len(opts),
            "is_bundle": self.is_bundle(opts),
            "product_image_urls": self._product_images(page),
            "description_image_urls": self._description_images(page),
            "seller_name": self._text(page, ".text__seller, .link--shop, [class*='seller-name']"),
            "regular_price": self._price(page, "[class*='price-original'], del"),
            "price": self._price(page, "[class*='price_seller'], strong[class*='price'], [class*='item-price']"),
        }

    @staticmethod
    def _text(page, sel):
        el = page.query_selector(sel)
        if el:
            t = el.inner_text().strip()
            return t[:40] if t else None
        return None

    @staticmethod
    def _price(page, sel):
        el = page.query_selector(sel)
        if not el:
            return None
        m = re.search(r"[\d,]{2,}\s*원", el.inner_text())
        return m.group(0).replace(" ", "") if m else None

    def _product_images(self, page):
        """상단 이미지 뷰어의 대표 상품컷. 실패 시 og:image 폴백.
        (초기 구현에서 누락돼 옥션 상품은 대표이미지가 전부 비어 있었다)"""
        for sel in ["ul.viewer li img", ".viewer img"]:
            urls = []
            for img in page.query_selector_all(sel):
                src = img.get_attribute("src") or img.get_attribute("data-src")
                if src:
                    urls.append("https:" + src if src.startswith("//") else src)
            if urls:
                return list(dict.fromkeys(urls))
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
        """상세설명 iframe(ExplainView) 내부 이미지 = OCR 대상.
        메인 DetailView 프레임을 잡으면 사이트 UI 이미지까지 섞이므로 ExplainView만 타겟."""
        frame = next((f for f in page.frames if f.url and "ExplainView" in f.url), None)
        if frame:
            try:
                frame.wait_for_selector("img", timeout=6000)
            except Exception:
                pass
            urls = self._imgs_from(frame)
            if urls:
                return urls
        cont = page.query_selector("#vip-tab_detail")
        return self._imgs_from(cont) if cont else []
