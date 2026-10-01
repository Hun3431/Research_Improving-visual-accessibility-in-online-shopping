# -*- coding: utf-8 -*-
"""11번가 어댑터.

카테고리 목록: DisplayCategory.tmall (구형 서버렌더 템플릿 .total_listitem, 페이지당 ~52개)
상세: /products/{id} — 상세이미지/가격 로직은 11st_crawler_v3(v8)에서 검증된 것을 포팅.
카탈로그(가격비교) 및 광고 식별 마커 포함.
"""
import copy
import json
import re
import urllib.parse

from bs4 import BeautifulSoup

from .base import BaseAdapter
from ..browser import polite_sleep

# leaf(세분류) 카테고리 목록 URL. method 파라미터가 있어야 홈으로 리다이렉트되지 않음.
LEAF_URL = ("https://www.11st.co.kr/category/DisplayCategory.tmall"
            "?method=getDisplayCategory2Depth&dispCtgrNo={leaf_id}")
SEARCH_URL = "https://search.11st.co.kr/pc/total-search?kwd={q}"


def _text_no_sr(el):
    """라벨 요소를 제외한 실제 값 텍스트 추출.

    11번가 카드는 <div class="c-card-item__name"><dt>상품명</dt><dd>실제이름</dd></div>
    처럼 <dt> 라벨을 두고, 가격/판매자엔 .sr-only 라벨을 쓴다. 이를 제거하지 않으면
    상품명이 '상품명 실제이름' 형태로 오염된다(기존 수집 데이터의 그 버그).
    """
    if el is None:
        return None
    el = copy.copy(el)
    for junk in el.select(".sr-only, dt"):
        junk.decompose()
    t = el.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", t).strip() or None


class ElevenstAdapter(BaseAdapter):
    platform = "11st"
    home_url = "https://www.11st.co.kr/"

    def canonical_url(self, product_id):
        return f"https://www.11st.co.kr/products/{product_id}"

    @staticmethod
    def _goto(page, url, timeout=30000, retries=2):
        """간헐적 타임아웃 대비 재시도."""
        last = None
        for attempt in range(retries + 1):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                return True
            except Exception as e:
                last = e
                page.wait_for_timeout(1500)
        raise last

    def browse_category(self, page, target, limit):
        """파이프라인 진입점. target 이 검색어(문자열)면 검색, 숫자면 카테고리 ID."""
        if isinstance(target, str) and not str(target).isdigit():
            return self.browse_search(page, target, limit)
        return self.browse_category_ids(page, target, limit)

    # ---------------- 목록: 검색 기반 ----------------
    def browse_search(self, page, query, limit, max_pages=6):
        """검색 결과에서 수집. 카테고리 목록은 동일/유사 상품이 몰려 나오는 경향이 있어
        검색이 상품 다양성이 더 좋다. 카드 메타는 anchor의 data-log-body(JSON)에서 파싱."""
        cards, seen = [], set()
        for pnum in range(1, max_pages + 1):
            url = SEARCH_URL.format(q=urllib.parse.quote(query))
            if pnum > 1:
                url += f"&pageNum={pnum}"
            try:
                self._goto(page, url, timeout=45000)
            except Exception:
                break
            polite_sleep(1.5, 3.0)
            for _ in range(3):
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(900)
            new = 0
            for c in self._parse_search(page.content()):
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

    @staticmethod
    def _parse_search(html):
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for it in soup.select("li.c-search-list__item"):
            a = it.select_one("a.c-card-item__anchor")
            if not a:
                continue
            meta = {}
            try:
                meta = json.loads(a.get("data-log-body") or "{}")
            except Exception:
                pass
            pid = meta.get("content_no")
            coll = str((meta.get("collection_object") or {}).get("name", ""))
            is_ad = meta.get("ad_yn") == "Y" or "ad" in coll.lower()
            txt = it.get_text(" ", strip=True)
            is_catalog = "가격비교" in txt
            name_el = (it.select_one(".c-card-item__name") or it.select_one("[class*='card-item__name']"))
            price_el = it.select_one(".c-card-item__price .value") or it.select_one(".c-card-item__price")
            seller_el = it.select_one(".c-seller__name")
            out.append({
                "product_id": pid,
                "product_url": f"https://www.11st.co.kr/products/{pid}" if pid else None,
                "name_raw": _text_no_sr(name_el),
                "price_raw": _text_no_sr(price_el),
                "seller_raw": _text_no_sr(seller_el),
                "is_ad": is_ad,
                "is_catalog": is_catalog,
            })
        return out

    # ---------------- 목록: 카테고리 기반(레거시) ----------------
    def browse_category_ids(self, page, leaf_id, limit, max_pages=8):
        """leaf 카테고리를 페이지네이션하며 ListCard(dict) 리스트 반환(필터 전 원본).

        11번가 카테고리(구형 total_listitem 템플릿)는 URL 페이지 파라미터가 없고
        JS 함수 smartFilter.goPageNum(N) 으로 목록을 교체 렌더링한다. 매 페이지 파싱 후
        product_id 기준으로 누적 dedupe 한다."""
        self._goto(page, LEAF_URL.format(leaf_id=leaf_id), timeout=35000)
        polite_sleep(1.5, 3.0)
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(1000)

        cards = []
        seen = set()

        def harvest():
            for c in self._parse_listing(page.content()):
                key = c["product_id"] or ("AD:" + (c["name_raw"] or ""))
                if key in seen:
                    continue
                seen.add(key)
                cards.append(c)

        def clean_count():
            return sum(1 for c in cards if c["product_id"] and not c["is_ad"] and not c["is_catalog"])

        harvest()
        for n in range(2, max_pages + 1):
            if clean_count() >= limit:
                break
            try:
                page.evaluate(f"smartFilter.goPageNum({n})")
            except Exception:
                break  # 페이지네이션 함수 없음(끝)
            page.wait_for_timeout(2200)
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(1000)
            before = len(cards)
            harvest()
            if len(cards) == before:
                break  # 새 상품 없음 → 마지막 페이지
            polite_sleep(1.0, 2.0)
        return cards

    @staticmethod
    def _parse_listing(html):
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for it in soup.select(".total_listitem"):
            prod_a = it.select_one("a[href*='/products/']")
            ad_a = it.select_one("a[href*='adoffice']")
            href = (prod_a.get("href") if prod_a else "") or ""
            m = re.search(r"/products/(\d+)", href)
            pid = m.group(1) if m else None
            is_ad = bool(ad_a) and not pid
            # 카탈로그(가격비교): 항목 내 '가격비교' 버튼 존재 = 하위 여러 판매자 링크
            is_catalog = any("가격비교" in (a.get_text() or "") for a in it.select("a"))
            name_el = it.select_one(".info_tit") or it.select_one(".list_info")
            price_el = it.select_one(".sale_price") or it.select_one(".price_detail")
            out.append({
                "product_id": pid,
                "product_url": f"https://www.11st.co.kr/products/{pid}" if pid else None,
                "name_raw": name_el.get_text(" ", strip=True) if name_el else None,
                "price_raw": price_el.get_text(" ", strip=True) if price_el else None,
                "is_ad": is_ad,
                "is_catalog": is_catalog,
            })
        return out

    # ---------------- 상세 (11st_crawler_v3 포팅) ----------------
    def parse_detail(self, page, product_url):
        self._goto(page, product_url, timeout=35000)
        polite_sleep()
        final_url = page.url
        m = re.search(r"/products/(\d+)", final_url)
        product_id = m.group(1) if m else None

        opts = self.collect_option_names(page)
        result = {
            "final_url": f"https://www.11st.co.kr/products/{product_id}" if product_id else final_url,
            "product_image_urls": [],
            "description_image_urls": self._collect_description_images(page),
            "seller_name": self._collect_seller(page),
            "option_count": len(opts),
            "is_bundle": self.is_bundle(opts),
        }
        result.update(self._collect_price(page))
        if product_id:
            result["product_image_urls"] = self._collect_product_images(page, product_id)
        return result

    @staticmethod
    def _extract_imgs(scope):
        found = []
        for img in scope.query_selector_all("img"):
            src = img.get_attribute("src") or img.get_attribute("data-src")
            if src:
                if src.startswith("//"):
                    src = "https:" + src
                found.append(src)
        return found

    def _collect_description_images(self, page):
        """상세설명 iframe의 img 수집.

        11번가는 상세 프레임 URL 표기가 템플릿마다 다르다: 'view-desc'(하이픈)와
        'viewDesc'(카멜케이스) 두 가지가 존재하므로 대소문자·하이픈 무시하고 매칭한다.
        (하이픈만 찾으면 viewDesc 템플릿 상품이 전부 이미지 0장으로 누락됨)
        """
        try:
            page.wait_for_selector("iframe[src*='iewDesc'], iframe[src*='view-desc'], iframe[src*='/desc']",
                                   timeout=6000)
        except Exception:
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.4)")
                page.wait_for_timeout(1500)
            except Exception:
                pass
        # 상세 프레임 후보: view-desc / viewDesc (notice·review 프레임은 제외)
        cands = [f for f in page.frames
                 if f.url and re.search(r"view-?desc", f.url, re.I)
                 and "/desc/notice" not in f.url and "review" not in f.url]
        urls = []
        for frame in cands:
            try:
                frame.wait_for_selector("img", timeout=5000)
            except Exception:
                pass
            urls = self._extract_imgs(frame)
            if urls:
                break
        if not urls:
            try:
                page.wait_for_selector("div.ifrm_prdc_detail", timeout=4000)
            except Exception:
                pass
            cont = page.query_selector("div.ifrm_prdc_detail")
            if cont:
                urls = self._extract_imgs(cont)
        return list(dict.fromkeys(urls))

    def _collect_product_images(self, page, product_id):
        raw = []
        for img in page.query_selector_all("img"):
            src = img.get_attribute("src") or img.get_attribute("data-src")
            if not src:
                continue
            if src.startswith("//"):
                src = "https:" + src
            if src.startswith("http"):
                raw.append(src)
        relevant = [u for u in raw if f"/product/{product_id}/" in u or re.search(rf"/{product_id}_", u)]
        best = {}
        for u in relevant:
            sm = re.search(r"/resize/(\d+)", u)
            size = int(sm.group(1)) if sm else 0
            km = re.search(r"/11src/(.+)$", u)
            key = km.group(1) if km else u
            if key not in best or size > best[key][0]:
                best[key] = (size, u)
        deduped = [v[1] for v in best.values()]
        option_imgs = sorted([u for u in deduped if f"/product/{product_id}/" in u])
        main_cands = [u for u in deduped if u not in option_imgs]
        main = None
        if main_cands:
            main = max(main_cands, key=lambda u: int(re.search(r"/resize/(\d+)", u).group(1))
                       if re.search(r"/resize/(\d+)", u) else 0)
        return ([main] if main else []) + option_imgs

    @staticmethod
    def _collect_price(page):
        result = {"regular_price": None, "price": None}
        reg = page.query_selector("dd.price_regular del")
        if reg:
            result["regular_price"] = reg.inner_text().strip()
        final = page.query_selector("#finalDscPrcArea dd.price .value")
        if final:
            result["price"] = final.inner_text().strip() + "원"
        return result

    @staticmethod
    def _collect_seller(page):
        """판매자 store 이름. 11번가 상세 구조상 안정적 셀렉터가 없어 정밀 셀렉터만 사용,
        확신이 없으면 None(추천상품 이름 등 오탐 방지). TODO: 셀러 영역 셀렉터 정교화."""
        for sel in ["a.c-product-seller__name", ".c-product-seller__name",
                    ".c-seller-store__name", "a[href*='minishop'] .name"]:
            el = page.query_selector(sel)
            if el:
                t = el.inner_text().strip()
                if t and len(t) <= 30:
                    return t
        return None
