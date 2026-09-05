#!/usr/bin/env python3
"""
fetch_apt_detail.py - 단지 기본정보(AptBasisInfoServiceV5)를 하루 할당량만큼 점진적으로 수집한다.

단지코드 1개당 API 1콜이 필요해서 전체(22,297개)를 한번에 못 가져온다.
이미 _rawdata/apt_detail.json에 있는 코드는 건너뛰고, 아직 없는 코드부터
DAILY_LIMIT개만 가져와 캐시에 이어붙인다. 매일 실행(cron)하면 며칠에 걸쳐
전체가 채워진다.

사용법: python scripts/fetch_apt_detail.py [--limit N]
"""
import json, os, sys, time, argparse
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_LIST = os.path.join(ROOT, "_rawdata", "apt_list_raw.json")
DETAIL_CACHE = os.path.join(ROOT, "_rawdata", "apt_detail.json")

SERVICE_KEY = os.environ.get("DATA_GO_KR_API_KEY") or "9490b1d34e92aa9e25b32a4cff1438fc7b9c71e5d332413916a391e867f61e86"
BASE = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV5/getAphusBassInfoV5"

DEFAULT_DAILY_LIMIT = 900  # 실제 한도(1,000/일)보다 여유를 둠


def fetch_one(kapt_code, attempt=1):
    params = {"serviceKey": SERVICE_KEY, "_type": "json", "kaptCode": kapt_code}
    try:
        r = requests.get(BASE, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        item = data.get("response", {}).get("body", {}).get("item")
        return item
    except Exception as e:
        if attempt >= 3:
            print(f"  실패 {kapt_code}: {e}")
            return None
        time.sleep(2)
        return fetch_one(kapt_code, attempt + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DEFAULT_DAILY_LIMIT)
    args = ap.parse_args()

    raw = json.loads(open(RAW_LIST, encoding="utf-8").read())
    all_codes = [d["kaptCode"] for d in raw if d.get("kaptCode")]

    detail_map = {}
    if os.path.exists(DETAIL_CACHE):
        detail_map = json.loads(open(DETAIL_CACHE, encoding="utf-8").read())

    remaining = [c for c in all_codes if c not in detail_map]
    print(f"전체 {len(all_codes)}개 / 확보 {len(detail_map)}개 / 남음 {len(remaining)}개")

    if not remaining:
        print("모든 단지 상세정보 수집 완료!")
        return

    todo = remaining[: args.limit]
    print(f"이번 실행에서 {len(todo)}개 수집 시도...")

    ok, fail = 0, 0
    for i, code in enumerate(todo, 1):
        item = fetch_one(code)
        if item:
            detail_map[code] = item
            ok += 1
        else:
            fail += 1
        if i % 100 == 0:
            print(f"  진행 {i}/{len(todo)} (성공 {ok}, 실패 {fail})")
            # 중간 저장 (중단되어도 진행분 보존)
            with open(DETAIL_CACHE, "w", encoding="utf-8") as f:
                json.dump(detail_map, f, ensure_ascii=False)
        time.sleep(0.05)

    with open(DETAIL_CACHE, "w", encoding="utf-8") as f:
        json.dump(detail_map, f, ensure_ascii=False)

    total_filled = len(detail_map)
    print(f"\n완료: 이번 회차 성공 {ok} / 실패 {fail}")
    print(f"누적 확보: {total_filled} / {len(all_codes)} ({total_filled*100//len(all_codes)}%)")


if __name__ == "__main__":
    main()
