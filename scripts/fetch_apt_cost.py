#!/usr/bin/env python3
"""
fetch_apt_cost.py - 단지별 공용관리비 항목(17종) + 장기수선충당금(월부과·적립잔액)을 K-apt API(V3)로
                    하루 할당량만큼 점진 수집한다. (국토교통부_공동주택 관리비 정보, data.go.kr 15057937 / 15059160)

서비스: apis.data.go.kr/1613000/AptCmnuseManageCostServiceV3/getHsmp*InfoV3  (공용관리비 17개 항목)
        apis.data.go.kr/1613000/AptRepairsCostServiceV3/getHsmpMonthFeeInfoV3 (장기수선충당금 월 부과액)
        apis.data.go.kr/1613000/AptRepairsCostServiceV3/getHsmpReserveBalanceInfoV3 (장기수선충당금 적립잔액)
파라미터: kaptCode, searchDate(YYYYMM), _type=json. 응답 item 1개, 항목별로 필드 구성이 다름.

수집 전략
- 단지마다 최신 보고월이 달라서 인건비(Labor) 하나로 후보월을 캐스케이드해 "값이 있는 달"을 찾고,
  그 달에 나머지 항목을 모두 받는다 (단지당 약 1~4 + 18콜).
- 개발계정 일 5,000콜이 서비스(API)별 한도라 하루 처리량은 --limit 단지수로 제한. 세대수 큰 단지부터.
- 키는 환경변수 DATA_GO_KR_API_KEY (없으면 ../hosppass/.env 의 API_KEY: 로컬 개발용). 코드에 넣지 않는다.

사용법:
  python scripts/fetch_apt_cost.py --limit 200
  python scripts/fetch_apt_cost.py --probe A10020067
"""
import json, os, sys, time, argparse, pathlib, re, concurrent.futures
from datetime import date
import requests

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "_rawdata"
CACHE = RAW / "apt_cost.json"

def _key():
    k = os.environ.get("DATA_GO_KR_API_KEY")
    if k: return k.strip()
    p = ROOT.parent / "hosppass" / ".env"
    if p.exists():
        m = re.search(r"^API_KEY\s*=\s*(\S+)", p.read_text(encoding="utf-8"), re.M)
        if m: return m.group(1).strip("\"'")
    sys.exit("환경변수 DATA_GO_KR_API_KEY 가 필요합니다.")
KEY = _key()
BASE = "https://apis.data.go.kr/1613000/"
CM = "AptCmnuseManageCostServiceV3/getHsmp%sInfoV3"
RP = "AptRepairsCostServiceV3/getHsmp%sInfoV3"

# 그룹키 -> (엔드포인트, 합산 대상 필드 or None=숫자 필드 전부)
GROUPS = {
    "lab": (CM % "LaborCost", None),          # 인건비
    "ofc": (CM % "OfcrkCost", None),          # 제사무비
    "tax": (CM % "Taxdue", None),             # 제세공과금
    "clo": (CM % "ClothingCost", None),       # 피복비
    "cln": (CM % "CleaningCost", None),       # 청소비
    "grd": (CM % "GuardCost", None),          # 경비비
    "dis": (CM % "DisinfectionCost", None),   # 소독비
    "elv": (CM % "ElevatorMntncCost", None),  # 승강기유지비
    "hnw": (CM % "HomeNetworkMntncCost", None),  # 지능형홈네트워크 유지비
    "rep": (CM % "RepairsCost", None),        # 수선비
    "fac": (CM % "FacilityMntncCost", None),  # 시설유지비
    "saf": (CM % "SafetyCheckUpCost", None),  # 안전점검비
    "dst": (CM % "DisasterPreventionCost", None),  # 재해예방비
    "veh": (CM % "VhcleMntncCost", None),     # 차량유지비
    "edu": (CM % "EduTraingCost", None),      # 교육훈련비
    "con": (CM % "ConsignManageFee", None),   # 위탁관리수수료
    "etc": (CM % "EtcCost", None),            # 그 밖의 부대비용
}
REPAIR = {"levy": (RP % "MonthFee", "sLevy"), "resv": (RP % "ReserveBalance", "sTot")}
SKIP_FIELDS = {"kaptCode", "kaptName"}

def _months(n=5):
    y, m = date.today().year, date.today().month - 2     # 2개월 전부터 (최근 달은 미보고가 흔함)
    out = []
    for _ in range(n):
        if m <= 0: m += 12; y -= 1
        out.append("%d%02d" % (y, m)); m -= 1
    return out

_sess = requests.Session()
def call(ep, code, ym, tries=4):
    for a in range(tries):
        try:
            r = _sess.get(BASE + ep, params={"serviceKey": KEY, "kaptCode": code, "searchDate": ym, "_type": "json"}, timeout=60)
            if r.status_code != 200: raise RuntimeError("HTTP %d" % r.status_code)
            j = r.json()
            if "response" not in j:
                h = (j.get("OpenAPI_ServiceResponse") or {}).get("cmmMsgHeader") or {}
                raise RuntimeError("API %s %s" % (h.get("returnReasonCode"), h.get("errMsg")))
            b = j["response"]["body"]
            it = b.get("item")
            if isinstance(it, list): it = it[0] if it else None
            return it if isinstance(it, dict) else None
        except Exception as e:
            if a == tries - 1: raise
            # 게이트웨이 04(HTTP_ERROR)는 짧은 시간에 많이 호출하면 발생(2026-11-08 약 1,300콜 뒤 반복) → 길게 쉬었다 재시도
            time.sleep(40 if "API 04" in str(e) else 3)

def num(d, fields=None):
    if not d: return 0
    s = 0
    for k, v in d.items():
        if k in SKIP_FIELDS or (fields and k not in fields): continue
        try: s += float(v or 0)
        except (TypeError, ValueError): pass
    return int(round(s))

def fetch_one(code):
    ym_hit = None; lab = None
    for ym in _months():
        it = call(GROUPS["lab"][0], code, ym)
        if it and num(it) > 0: ym_hit, lab = ym, it; break
    if not ym_hit: return None
    out = {"m": ym_hit, "lab": num(lab)}
    for g, (ep, _) in GROUPS.items():
        if g == "lab": continue
        out[g] = num(call(ep, code, ym_hit))
    for g, (ep, f) in REPAIR.items():
        it = call(ep, code, ym_hit)
        out[g] = num(it, {f})
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--probe", metavar="CODE")
    a = ap.parse_args()
    if a.probe:
        print(json.dumps(fetch_one(a.probe), ensure_ascii=False)); return
    lst = json.loads((RAW / "apt_list_raw.json").read_text(encoding="utf-8"))
    det = json.loads((RAW / "apt_detail.json").read_text(encoding="utf-8")) if (RAW / "apt_detail.json").exists() else {}
    def hh(d):
        x = det.get(d["kaptCode"]) or {}
        try: return int(x.get("hoCnt") or d.get("hoCnt") or 0)
        except (TypeError, ValueError): return 0
    codes = [d["kaptCode"] for d in sorted(lst, key=hh, reverse=True) if d.get("kaptCode")]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    todo = [c for c in codes if c not in cache][: a.limit]
    print("전체 %d / 확보 %d / 이번 %d" % (len(codes), len(cache), len(todo)), flush=True)
    ok = empty = fail = 0; t0 = time.time()
    def one(c):
        try: return c, fetch_one(c), None
        except Exception as e: return c, None, e
    with concurrent.futures.ThreadPoolExecutor(a.threads) as ex:
        for n, (c, r, err) in enumerate(ex.map(one, todo), 1):
            if err is not None:
                fail += 1
                if fail > 15: print("연속 오류로 중단:", err); break
                continue
            cache[c] = r or {"m": ""}
            if r: ok += 1
            else: empty += 1
            if n % 50 == 0:
                print("  %d/%d  ok %d empty %d fail %d (%.0f초)" % (n, len(todo), ok, empty, fail, time.time() - t0), flush=True)
                CACHE.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("완료 ok %d empty %d fail %d (%.0f초) 누적 %d" % (ok, empty, fail, time.time() - t0, len(cache)))

if __name__ == "__main__":
    main()
