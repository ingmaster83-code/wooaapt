#!/usr/bin/env python3
"""
fetch_apt_energy.py - 단지별 에너지 사용량/사용금액 정보(K-apt, 국토교통부)를
                       하루 할당량만큼 점진적으로 수집한다.

API: 국토교통부_공동주택 에너지 사용 정보 (data.go.kr id 15012964)
Base URL: apis.data.go.kr/1613000/ApHusEnergyUseInfoOfferServiceV2
Operation: getHsmpApHusUsgQtyInfoSearchV2 (단지 공동주택 에너지 사용량 정보조회)

단지코드 1개당 API 1콜. fetch_apt_detail.py와 동일한 점진 수집 패턴을 따른다.

사용법:
  python scripts/fetch_apt_energy.py --probe A10021295   # 필드명 확인용 1건 원본 출력
  python scripts/fetch_apt_energy.py [--limit N]          # 점진 수집
"""
import json, os, sys, time, argparse
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_LIST = os.path.join(ROOT, "_rawdata", "apt_list_raw.json")
ENERGY_CACHE = os.path.join(ROOT, "_rawdata", "apt_energy.json")

SERVICE_KEY = os.environ.get("DATA_GO_KR_API_KEY") or "9490b1d34e92aa9e25b32a4cff1438fc7b9c71e5d332413916a391e867f61e86"
BASE = "https://apis.data.go.kr/1613000/ApHusEnergyUseInfoOfferServiceV2/getHsmpApHusUsgQtyInfoSearchV2"

DEFAULT_DAILY_LIMIT = 900


def fetch_one(kapt_code, attempt=1):
    params = {"serviceKey": SERVICE_KEY, "_type": "json", "kaptCode": kapt_code, "numOfRows": 12}
    try:
        r = requests.get(BASE, params=params, timeout=90)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        if attempt >= 3:
            print(f"  실패 {kapt_code}: {e}")
            return None
        time.sleep(2)
        return fetch_one(kapt_code, attempt + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DEFAULT_DAILY_LIMIT)
    ap.add_argument("--probe", metavar="KAPT_CODE", help="필드명 확인용: 단지 1개 원본 응답만 출력하고 종료")
    args = ap.parse_args()

    if args.probe:
        raw = fetch_one(args.probe)
        print(json.dumps(raw, ensure_ascii=False, indent=2))
        return

    apt_list = json.load(open(RAW_LIST, encoding="utf-8"))
    codes = [d["kaptCode"] for d in apt_list if d.get("kaptCode")]
    print(f"전체 단지: {len(codes)}개")

    cache = {}
    if os.path.exists(ENERGY_CACHE):
        cache = json.load(open(ENERGY_CACHE, encoding="utf-8"))

    remaining = [c for c in codes if c not in cache]
    print(f"확보 {len(cache)}개 / 남음 {len(remaining)}개")
    if not remaining:
        print("완료!")
        return

    todo = remaining[: args.limit]
    print(f"이번 실행에서 {len(todo)}개 처리...")

    ok, empty, fail = 0, 0, 0
    for i, code in enumerate(todo, 1):
        raw = fetch_one(code)
        if raw is None:
            fail += 1
        else:
            body = raw.get("response", {}).get("body", {})
            items = body.get("items")
            if isinstance(items, dict):
                items = items.get("item")
            if not items:
                cache[code] = []
                empty += 1
            else:
                if isinstance(items, dict):
                    items = [items]
                cache[code] = items
                ok += 1
        if i % 300 == 0:
            print(f"  진행 {i}/{len(todo)} (성공 {ok}, 데이터없음 {empty}, 실패 {fail})")
            with open(ENERGY_CACHE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
        time.sleep(0.05)

    with open(ENERGY_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    print(f"\n완료: 성공 {ok} / 데이터없음 {empty} / 실패 {fail}")
    print(f"누적 확보: {len(cache)} / {len(codes)} ({len(cache)*100//len(codes)}%)")


if __name__ == "__main__":
    main()
