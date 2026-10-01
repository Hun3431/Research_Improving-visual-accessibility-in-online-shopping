# -*- coding: utf-8 -*-
"""수집 결과에서 상세가 비어있는(상세이미지 0장) 레코드를 재방문해 상세를 재수집.
선택적으로 product_id 기준 교차중복(여러 leaf에 걸친 동일 상품)을 제거한다.

사용법:
  python -u -m pcrawler.recollect gmarket --file data/raw/gmarket/merged.json --dedupe
"""
import argparse
import json
from pathlib import Path

from .adapters import ADAPTERS, CDP_PLATFORMS
from .browser import cdp_session, browser_session, warmup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("platform")
    ap.add_argument("--file", required=True)
    ap.add_argument("--dedupe", action="store_true", help="product_id 교차중복 제거(첫 등장 유지)")
    args = ap.parse_args()

    adapter = ADAPTERS[args.platform]()
    path = Path(args.file)
    recs = json.loads(path.read_text(encoding="utf-8"))
    path.with_suffix(path.suffix + ".bak").write_text(
        json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")

    targets = [r for r in recs if len(r["detail"].get("description_image_urls", [])) == 0]
    print(f"재수집 대상(상세이미지0): {len(targets)}건")

    use_cdp = args.platform in CDP_PLATFORMS
    cm = cdp_session() if use_cdp else browser_session()
    recovered = 0
    with cm as page:
        if not use_cdp:
            warmup(page, adapter.home_url)
        for i, r in enumerate(targets):
            url = r["source"].get("product_url")
            print(f"[{i+1}/{len(targets)}] {(r['raw'].get('name_raw') or '')[:34]}", flush=True)
            if not url:
                continue
            try:
                det = adapter.parse_detail(page, url)
                r["detail"] = det
                if det.get("description_image_urls"):
                    recovered += 1
            except Exception as e:
                r["detail"]["error"] = str(e)
                print(f"   실패: {e}", flush=True)
    print(f"\n복구 성공(상세이미지 확보): {recovered}/{len(targets)}건")

    if args.dedupe:
        seen, out = set(), []
        for r in recs:
            pid = r["source"].get("product_id")
            if pid in seen:
                continue
            seen.add(pid)
            out.append(r)
        print(f"교차중복 제거: {len(recs)} → {len(out)}건")
        recs = out

    path.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {path} (원본 백업: {path}.bak)")


if __name__ == "__main__":
    main()
