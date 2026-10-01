# -*- coding: utf-8 -*-
"""Playwright 세션 공통화 + 봇탐지 회피. 3개 스크립트에 중복돼 있던 세팅을 단일화한다."""
import os
import random
import time
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# 쿠팡 스크립트의 강화판 init script를 표준으로 채택
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR', 'ko']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
"""


@contextmanager
def cdp_session(endpoint="http://127.0.0.1:9222"):  # localhost가 IPv6(::1)로 잡히는 문제 회피
    """사용자가 --remote-debugging-port로 띄운 '진짜 크롬'에 CDP로 연결.
    Cloudflare 등 자동화 탐지가 강한 사이트(G마켓·옥션)용. 크롬 창은 유지된다.

    사전: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \\
              --remote-debugging-port=9222 --user-data-dir="/tmp/pcrawler_cdp_profile"
    """
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(endpoint)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        # 사용자 탭(pages[0])을 재사용하면 사용자가 그 탭을 닫는 순간 수집이 전부 실패한다.
        # (실제로 'Target page, context or browser has been closed' 로 대량 실패했음)
        # → 크롤러 전용 탭을 새로 만들어 사용한다.
        page = ctx.new_page()
        try:
            yield page
        finally:
            try:
                if not page.is_closed():
                    page.close()
            except Exception:
                pass
            browser.close()  # CDP 연결만 끊음(크롬 창 유지)


@contextmanager
def browser_session(headless=False):
    """크롬(실제) 우선, 실패 시 번들 크로미움 폴백. page 하나를 yield한다."""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=headless,
                channel="chrome",
                args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
            )
        except Exception:
            browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1440, "height": 1000},
            user_agent=UA,
            extra_http_headers={"Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"},
        )
        context.add_init_script(STEALTH_JS)
        page = context.new_page()
        try:
            yield page
        finally:
            browser.close()


def warmup(page, home_url):
    """홈페이지부터 사람처럼 진입 (탐지 회피)."""
    page.goto(home_url, wait_until="domcontentloaded")
    time.sleep(random.uniform(2.0, 3.5))
    try:
        page.mouse.move(300, 400)
        time.sleep(random.uniform(0.8, 1.6))
        page.mouse.wheel(0, 600)
        time.sleep(random.uniform(1.0, 2.0))
    except Exception:
        pass


def polite_sleep(lo=1.5, hi=3.5):
    """요청 간 대기. 환경변수 PCRAWLER_SLEEP_SCALE 로 배율 조정 가능.

    11번가처럼 요청이 몰리면 빈 결과를 반환하며 막는 사이트는 배율을 올려
    (예: 2.5) 천천히 수집한다.
    """
    try:
        scale = float(os.environ.get("PCRAWLER_SLEEP_SCALE", "1"))
    except ValueError:
        scale = 1.0
    time.sleep(random.uniform(lo, hi) * scale)
