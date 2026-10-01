from .elevenst import ElevenstAdapter
from .gmarket import GmarketAdapter
from .auction import AuctionAdapter

ADAPTERS = {
    "11st": ElevenstAdapter,
    "gmarket": GmarketAdapter,
    "auction": AuctionAdapter,
}

# CDP(사용자가 띄운 진짜 크롬)로 접속해야 하는 플랫폼.
# G마켓/옥션은 Cloudflare, 11번가는 Playwright 실행 크롬을 감지해 응답을 지연/차단하므로
# 세 곳 모두 CDP 세션을 사용한다.
CDP_PLATFORMS = {"gmarket", "auction", "11st"}

# 카테고리 ID 대신 검색어로 목록을 수집하는 플랫폼.
# (11번가는 카테고리 목록이 동일/유사 상품 위주라 검색이 다양성이 좋음)
SEARCH_PLATFORMS = {"gmarket", "auction", "11st"}
