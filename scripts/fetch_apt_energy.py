#!/usr/bin/env python3
"""
fetch_apt_energy.py - 단지별 에너지 사용량/사용금액(K-apt, 국토교통부)을 하루 할당량만큼
                       점진적으로 수집한다. 관리비 정보 대신 채택한 대체 지표(§ 인벤토리 메모 참고
                       — 항목별 관리비 원본은 오픈API가 아니라 k-apt.go.kr 게시판 XLSX로만 존재해서
                       API로 자동화 불가능함을 확인, 대신 이 에너지 사용량/금액 API로 대체).

API: 국토교통부_공동주택 에너지 사용 정보 (data.go.kr id 15012964)
Base URL: apis.data.go.kr/1613000/ApHusEnergyUseInfoOfferServiceV2
Operation: getHsmpApHusUsgQtyInfoSearchV2 (단지 공동주택 에너지 사용량 정보조회)
필수 파라미터: kaptCode(단지코드), reqDate(발생년월, YYYYMM) — reqDate 누락 시 전부 0으로
채워진 응답이 와서 마치 데이터가 없는 것처럼 보이므로 반드시 지정해야 함(실측 확인).

단지마다 최신 보고월이 달라서(관리사무소가 최근 몇 달 미보고인 경우가 흔함), 최근 몇 개
후보월을 순서대로 시도해 데이터가 실제로 채워진(0이 아닌) 첫 응답을 채택하는 캐스케이드 방식을
쓴다 — 단지당 최대 CANDIDATE_MONTHS개 콜이 들 수 있어 하루 처리량을 그만큼 낮게 잡는다.

사용법:
  python scripts/fetch_apt_energy.py --probe A10021295   # 필드명/응답 확인용 원본 출력
  python scripts/fetch_apt_energy.py [--limit N]          # 점진 수집
"""
import json, os, sys, time, argparse
from datetime import date
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_LIST = os.path.join(ROOT, "_rawdata", "apt_list_raw.json")
ENERGY_CACHE = os.path.join(ROOT, "_rawdata", "apt_energy.json")

SERVICE_KEY = os.environ.get("DATA_GO_KR_API_KEY") or "9490b1d34e92aa9e25b32a4cff1438fc7b9c71e5d332413916a391e867f61e86"
BASE = "https://apis.data.go.kr/1613000/ApHusEnergyUseInfoOfferServiceV2/getHsmpApHusUsgQtyInfoSearchV2"

DEFAULT_DAILY_LIMIT = 200  # 단지당 최대 4콜(월 캐스케이드)까지 들 수 있어 900보다 낮게 잡음

AMOUNT_FIELDS = ["heat", "waterHot", "gas", "elect", "waterCool"]
USAGE_FIELDS = ["hheat", "hwaterHot", "hgas", "helect", "hwaterCool"]


def _candidate_months(n=4):
    """최근 완료됐을 법한 달부터 역순으로 n개 후보(YYYYMM 문자열) 생성.
    당월/전월은 보고가 안 됐을 가능성이 높아 2개월 전부터 시작."""
    y, m = date.today().year, date.today().month
    out = []
    m -= 2  # 2개월 전부터
    for _ in range(n):
        if m <= 0:
            m += 12
            y -= 1
        out.append(f"{y}{m:02d}")
        m -= 1
    return out


def fetch_one_month(kapt_code, req_date, attempt=1):
    params = {"serviceKey": SERVICE_KEY, "_type": "json", "kaptCode": kapt_code, "reqDate": req_date}
    try:
        r = requests.get(BASE, params=params, timeout=90)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        if attempt >= 3:
            print(f"  실패 {kapt_code}/{req_date}: {e}")
            return None
        time.sleep(2)
        return fetch_one_month(kapt_code, req_date, attempt + 1)


def fetch_one(kapt_code):
    """후보월을 순서대로 시도해 0이 아닌(=실제 보고된) 첫 응답을 채택. 전부 0/실패면 None(데이터없음)."""
    for req_date in _candidate_months():
        raw = fetch_one_month(kapt_code, req_date)
        if raw is None:
            continue
        item = raw.get("response", {}).get("body", {}).get("item")
        if not item or not isinstance(item, dict):
            continue
        has_any = any((item.get(f) or 0) not in (0, None) for f in AMOUNT_FIELDS + USAGE_FIELDS)
        if has_any:
            item["reqDate"] = req_date
            return item
        time.sleep(0.05)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DEFAULT_DAILY_LIMIT)
    ap.add_argument("--probe", metavar="KAPT_CODE", help="필드명/응답 확인용: 단지 1개 원본 출력하고 종료")
    args = ap.parse_args()

    if args.probe:
        for req_date in _candidate_months():
            raw = fetch_one_month(args.probe, req_date)
            print(f"--- reqDate={req_date} ---")
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

    ok, empty = 0, 0
    for i, code in enumerate(todo, 1):
        item = fetch_one(code)
        if item:
            cache[code] = item
            ok += 1
        else:
            cache[code] = None
            empty += 1
        if i % 50 == 0:
            print(f"  진행 {i}/{len(todo)} (데이터있음 {ok}, 데이터없음 {empty})")
            with open(ENERGY_CACHE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
        time.sleep(0.05)

    with open(ENERGY_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    print(f"\n완료: 데이터있음 {ok} / 데이터없음 {empty}")
    print(f"누적 확보: {len(cache)} / {len(codes)} ({len(cache)*100//len(codes)}%)")


if __name__ == "__main__":
    main()
