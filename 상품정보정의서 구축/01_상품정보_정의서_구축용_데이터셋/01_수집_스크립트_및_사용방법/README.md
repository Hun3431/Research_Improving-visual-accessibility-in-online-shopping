# 수집 스크립트 및 사용 방법

이 폴더를 터미널의 현재 위치로 설정한 뒤 실행한다. Python 파일을 하나씩 실행하지 않고 `python -m pcrawler.cli`를 시작점으로 사용한다. 현재 지원 플랫폼은 11번가·G마켓·옥션이고, 설정은 주방용품 10개 상품군이다.

## 1. 실행 환경 준비

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

수집에는 OCR/Gemini 인증키가 필요 없다. 패키지는 버전이 고정되지 않은 원본 환경을 반영하므로, 과거 실행 환경과 완전히 동일하다고 보장하지 않는다.

## 2. 별도 터미널에서 Chrome 실행

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir="/tmp/pcrawler_cdp_profile"
```

Chrome과 이 터미널을 켜 둔다. 수집 프로그램은 CDP로 이 브라우저에 연결하여 전용 탭을 연다.

## 3. 소량 테스트

첫 번째 터미널에서:

```bash
python -m pcrawler.cli 11st --test
```

앞의 두 상품군에서 총 최대 3건. `data/raw/11st/날짜_시간_test.json`의 상품명, 가격, 상세이미지 주소를 확인한다. 테스트 파일은 후속 표집에서 제외한다. 현재 사이트에서 실제 수집 성공 여부는 이 정리 작업에서 확인하지 않았다.

## 4. 본수집

다음 명령을 하나씩 실행하고 완료를 기다린다.

```bash
python -m pcrawler.cli 11st --limit 500 --per-leaf 50
python -m pcrawler.cli gmarket --limit 500 --per-leaf 50
python -m pcrawler.cli auction --limit 500 --per-leaf 50
```

플랫폼별 최대 500건, 상품군별 최대 50건이다. 실제 확보량은 부족할 수 있다. 실행 회차별 파일이 `data/raw/플랫폼/`에 생긴다. 기존 `collected_all.json`은 자동 갱신되지 않는다. 이 폴더의 `data/raw/`에는 과거 회차별 자료도 복사해 두었으므로, 위 기본 명령으로 새로 수집하면 이후 집계·표집은 과거 자료와 신규 자료를 함께 읽는다.

새 자료를 따로 보관하려면 다음처럼 출력 폴더를 지정한다. 이 별도 폴더는 기본 현황·표집 명령에서 자동으로 읽지 않는다.

```bash
python -m pcrawler.cli 11st --limit 20 --per-leaf 20 --leaves home.kitchen.pot --out data/new_collection/11st
```

## 5. 현황 확인과 부족분 보충

```bash
python -m pcrawler.status_report --target 50 --need 20
python -m pcrawler.collect_fill --platforms auction,11st --target 50 --rounds 8
```

현황 확인은 읽기 작업이다. 보충은 기존 `data/raw`를 다시 집계해 부족한 상품군을 수집한다. 과거 자료가 포함되어 있으면 이미 목표를 달성한 것으로 판단할 수 있다.

## 6. 균형표집

```bash
python -m pcrawler.balance_dataset --per-group 100 --out data/reproduced/kitchen_100each.json
```

회차별 원본에서 중복·빈 상세를 제외하고 상품군별 100건씩, 플랫폼 비율을 가능한 균등하게 선택한다. 결과는 별도 `data/reproduced/`에 저장된다. 제공된 확정 1,000건 파일을 덮어쓰지 않는다. 원본이 부족하면 100건 미만이 선택될 수 있다.

## 파일 역할

| 파일 | 역할 |
|---|---|
| cli.py | 수집 명령과 옵션 해석 |
| pipeline.py | 검색 → 필터 → 상세 방문 → 저장 순서 관리 |
| browser.py | 직접 띄운 Chrome 연결과 요청 간 대기 |
| adapters/ | 사이트별 목록·상세정보 추출 |
| filters.py | 광고·카탈로그·목록 내 중복 제외 |
| collect_fill.py | 기존 자료를 세어 부족분 보충 |
| collect_rotate.py | 플랫폼을 번갈아 수집하는 초기 방식; 이전 회차 중복을 피하는 데 한계가 있어 보충은 collect_fill 사용 |
| recollect.py | 상세이미지가 없는 상품 재방문; 입력 파일을 수정하고 .bak 생성 |
| status_report.py | 상품군·플랫폼별 확보량 확인 |
| balance_dataset.py | 상품군별·플랫폼별 균형표집 |
| configs/category_map.yaml | 상품군과 검색어 설정 |

목록 필터의 중복 제거 범위와 여러 회차를 합칠 때의 중복 제거는 다르다. 상세가 연속 8번 비면 중단하며, 앞서 저장한 회차 파일에는 빈 상세가 남을 수 있다. 사이트 구조가 바뀌면 어댑터 수정이 필요하다.
