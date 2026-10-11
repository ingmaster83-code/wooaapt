#!/usr/bin/env python3
"""
fetch_trades.py - 국토교통부 아파트 실거래(매매·전월세) API를 시군구(243개)×월 단위로 수집해 data/trade_cache/ 에 캐시한다.

- 매매: RTMSDataSvcAptTradeDev(상세) 최근 36개월 / 전월세: RTMSDataSvcAptRent 최근 24개월
- 이미 받은 (종류, 월, 시군구)는 건너뛴다(최근 2개월은 신고 지연·해제 때문에 항상 다시 받음).
- 일일 호출 한도에 걸리면 정상 종료하고, 다음 실행에서 이어서 받는다.
사용: python scripts/fetch_trades.py [--kind trade|rent|both] [--months-trade 36] [--months-rent 24] [--refresh-recent]
키: 환경변수 DATA_GO_KR_API_KEY (없으면 ../hosppass/.env 의 API_KEY — 로컬 전용)
"""
import argparse, gzip, json, os, re, sys, time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).parent.parent
CACHE = ROOT / "data" / "trade_cache"
HIST = ROOT / "_rawdata" / "trade_hist"   # 확정된(4개월 이상 지난) 월 데이터: git 에 보관
RECENT_N = 2                              # 빌드마다 다시 받는 최근 개월 수(신고 지연 30일 → 2개월이면 충분, 일일 호출 한도 절약)
SGG = json.loads((ROOT / "scripts" / "sgg_codes.json").read_text(encoding="utf-8"))

URLS = {
    "trade": "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
    "rent": "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
}
ROWS = 1000


def get_key():
    k = os.environ.get("DATA_GO_KR_API_KEY")
    if k:
        return k
    env = ROOT.parent / "hosppass" / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("API_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("DATA_GO_KR_API_KEY 가 없습니다.")


KEY = get_key()
sess = requests.Session()


HTTP = [0]   # 실제 HTTP 호출 수(페이지 포함)


class QuotaExceeded(Exception):
    pass


def txt(it, tag):
    e = it.find(tag)
    return (e.text or "").strip() if e is not None and e.text else ""


def num(s, f=float):
    try:
        return f(str(s).replace(",", "").strip())
    except ValueError:
        return 0


def parse_items(root, kind):
    rows = []
    for it in root.iter("item"):
        ymd = num(txt(it, "dealYear"), int) * 10000 + num(txt(it, "dealMonth"), int) * 100 + num(txt(it, "dealDay"), int)
        base = [txt(it, "aptSeq"), txt(it, "aptNm"), txt(it, "umdNm"), txt(it, "jibun"), ymd, num(txt(it, "excluUseAr")), num(txt(it, "floor"), int)]
        if kind == "trade":
            cancelled = 1 if txt(it, "cdealType") == "O" or txt(it, "cdealDay") else 0
            gbn = txt(it, "dealingGbn")[:2]
            base += [num(txt(it, "dealAmount"), int), num(txt(it, "buildYear"), int), cancelled, gbn]
        else:
            base += [num(txt(it, "deposit"), int), num(txt(it, "monthlyRent"), int), txt(it, "contractType")[:2], num(txt(it, "buildYear"), int)]
        rows.append(base)
    return rows


def fetch_one(kind, sgg, ym):
    rows, page = [], 1
    while True:
        for attempt in range(5):
            try:
                HTTP[0] += 1
                r = sess.get(URLS[kind], params={"serviceKey": KEY, "LAWD_CD": sgg, "DEAL_YMD": ym, "numOfRows": ROWS, "pageNo": page}, timeout=40)
                if r.status_code == 429 or "LIMITED_NUMBER_OF_SERVICE_REQUESTS" in r.text:
                    raise QuotaExceeded()
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}")
                root = ET.fromstring(r.text)
                code = (root.findtext(".//resultCode") or "").strip()
                if code not in ("000", "00"):
                    msg = root.findtext(".//resultMsg") or r.text[:100]
                    if "LIMIT" in msg.upper():
                        raise QuotaExceeded()
                    raise RuntimeError(f"resultCode {code}: {msg}")
                break
            except QuotaExceeded:
                raise
            except Exception as e:
                if attempt == 4:
                    raise
                time.sleep(2 * (attempt + 1))
        batch = parse_items(root, kind)
        rows.extend(batch)
        total = num(root.findtext(".//totalCount") or "0", int)
        if len(rows) >= total or not batch:
            return rows
        page += 1
        time.sleep(0.1)


def months_back(n):
    t = date.today()
    y, m = t.year, t.month
    out = []
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def hist_path(kind, ym):
    return HIST / f"{kind}_{ym}.json.gz"


def write_hist(kind, ym, by_sgg):
    HIST.mkdir(parents=True, exist_ok=True)
    with gzip.open(hist_path(kind, ym), "wt", encoding="utf-8") as f:
        json.dump(by_sgg, f, ensure_ascii=False, separators=(",", ":"))


def windows(args):
    return {"trade": args.months_trade, "rent": args.months_rent}


def prune_hist(args):
    keep = {k: set(months_back(n)) for k, n in windows(args).items()}
    for f in HIST.glob("*.json.gz"):
        kind, ym = f.name[:-8].split("_")
        if ym not in keep.get(kind, set()):
            f.unlink()
            print("오래된 이력 삭제:", f.name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="full", choices=["full", "recent", "fill-hist", "pack-cache"])
    ap.add_argument("--kind", default="both")
    ap.add_argument("--months-trade", type=int, default=36)
    ap.add_argument("--months-rent", type=int, default=24)
    ap.add_argument("--max-calls", type=int, default=9000)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    kinds = ["trade", "rent"] if args.kind == "both" else [args.kind]
    done = skipped = 0

    if args.mode == "pack-cache":      # 로컬 부트스트랩: 캐시의 확정 월을 이력 파일로 묶는다
        for kind in kinds:
            for ym in months_back(windows(args)[kind])[RECENT_N:]:
                d = CACHE / kind / ym
                if hist_path(kind, ym).exists() or not d.exists():
                    continue
                write_hist(kind, ym, {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in d.glob("*.json")})
                done += 1
        prune_hist(args)
        print(f"이력 파일 {done}개 생성")
        return

    for kind in kinds:
        all_months = months_back(windows(args)[kind])
        if args.mode == "recent":
            months, to_hist = all_months[:RECENT_N], False
        elif args.mode == "fill-hist":
            months, to_hist = [m for m in all_months[RECENT_N:] if not hist_path(kind, m).exists()], True
        else:
            months, to_hist = all_months, False
        recent = set(all_months[:RECENT_N])
        for ym in months:
            d = CACHE / kind / ym
            if not to_hist:
                d.mkdir(parents=True, exist_ok=True)
            todo = [g for g in SGG if to_hist or ym in recent or not (d / f"{g}.json").exists()]
            skipped += len(SGG) - len(todo)
            if not todo:
                continue
            if HTTP[0] >= args.max_calls:
                print(f"호출 {HTTP[0]}회 도달 — 중단(다음 실행에서 이어서). 받음 {done}, 건너뜀 {skipped}")
                sys.exit(2 if args.mode == "recent" else 0)   # 최근 월은 일부만 받으면 안 되므로 실패 처리
            try:
                with ThreadPoolExecutor(max_workers=args.workers) as ex:
                    results = list(ex.map(lambda g: (g, fetch_one(kind, g, ym)), todo))
            except QuotaExceeded:
                print(f"일일 호출 한도 도달(HTTP {HTTP[0]}회) — 중단(다음 실행에서 이어서). 받음 {done}, 건너뜀 {skipped}")
                sys.exit(2 if args.mode == "recent" else 0)
            done += len(results)
            if to_hist:
                write_hist(kind, ym, {g: rows for g, rows in results})
                print(f"이력 저장: {kind} {ym}", flush=True)
            else:
                for g, rows in results:
                    (d / f"{g}.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                print(f"[{kind}] {ym} {len(results)}개 시군구 (HTTP {HTTP[0]})", flush=True)
    if args.mode == "fill-hist":
        prune_hist(args)
    print(f"완료: 받음 {done}, 건너뜀 {skipped}")


if __name__ == "__main__":
    main()
