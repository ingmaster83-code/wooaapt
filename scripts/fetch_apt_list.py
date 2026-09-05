#!/usr/bin/env python3
"""
fetch_apt_list.py - 국토교통부 공동주택 단지 목록제공 서비스(AptListService4)에서
전국 모든 단지(kaptCode/kaptName/주소) 목록을 전량 수집한다.
페이지네이션만 있으면 되는 API라 트래픽 제한과 무관하게 한 번에 전체 수집 가능.

사용법: python scripts/fetch_apt_list.py
출력: _rawdata/apt_list_raw.json
"""
import json, os, sys, time
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_rawdata", "apt_list_raw.json")

SERVICE_KEY = os.environ.get("DATA_GO_KR_API_KEY") or "9490b1d34e92aa9e25b32a4cff1438fc7b9c71e5d332413916a391e867f61e86"
BASE = "https://apis.data.go.kr/1613000/AptListService4/getTotalAptList4"
NUM_OF_ROWS = 1000


def fetch_page(page_no, attempt=1):
    params = {
        "serviceKey": SERVICE_KEY,
        "_type": "json",
        "numOfRows": NUM_OF_ROWS,
        "pageNo": page_no,
    }
    try:
        r = requests.get(BASE, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        if attempt >= 5:
            raise
        print(f"  [재시도 {attempt}] page {page_no}: {e}")
        time.sleep(3)
        return fetch_page(page_no, attempt + 1)


def main():
    all_items = []
    page = 1
    total_count = None
    while True:
        data = fetch_page(page)
        body = data.get("response", {}).get("body", {})
        items = body.get("items") or []
        if total_count is None:
            total_count = int(body.get("totalCount", 0))
            print(f"전체 단지 수: {total_count}")
        if not items:
            break
        all_items.extend(items)
        print(f"  page {page}: 누적 {len(all_items)} / {total_count}")
        if len(all_items) >= total_count:
            break
        page += 1
        if page > 100:
            print("안전장치: 100페이지 초과, 중단")
            break

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False)
    print(f"\n총 {len(all_items)}건 저장 -> {OUT}")


if __name__ == "__main__":
    main()
