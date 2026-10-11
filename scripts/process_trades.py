#!/usr/bin/env python3
"""
process_trades.py - data/trade_cache/ 의 아파트 실거래(매매·전월세) 원자료를 단지(aptSeq)별로 집계해
_rawdata/trades_{시도}.json 을 만든다. K-apt 단지(kaptCode)와는 (시군구코드, 법정동, 지번) → 단지명 유사도 순으로 연결한다.

출력 레코드(단지 1건):
  seq, code(K-apt 코드 또는 ""), slug(K-apt 페이지 slug 또는 ""), name, doShort, sigungu, dong, jibun, by(준공연도),
  n36(최근 36개월 매매), n12(최근 12개월 매매), nr12(최근 12개월 전월세), last(마지막 매매일),
  tg: 평형(전용 정수㎡)별 매매 요약 [{a, py, n12, avg12, min12, max3, max3d, max3f, last:[ymd,floor,amt]}]
  rg: 평형별 전월세 요약 [{a, nj, avgj, nw, avgwd, avgwm}]
  t: 최근 매매 [[ymd, 전용, 층, 금액(만원)]], r: 최근 전월세 [[ymd, 전용, 층, 보증금, 월세]],
  yr: 가장 거래가 많은 평형의 연도별 [[year, n, avg]], hi: 최근 30일 신고가 [{a, d, amt, prev, f}]
"""
import gzip, json, re, sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).parent.parent
CACHE = ROOT / "data" / "trade_cache"
RAW = ROOT / "_rawdata"
TODAY = date.today()


def ymd_of(d):
    return d.year * 10000 + d.month * 100 + d.day


Y12 = ymd_of(TODAY - timedelta(days=365))
Y36 = ymd_of(TODAY - timedelta(days=365 * 3))
Y30D = ymd_of(TODAY - timedelta(days=30))
MIN_TOTAL = 20000       # 이보다 적으면 수집 실패로 보고 중단(빌드·배포 차단)
MIN_TRADES_PAGE = 3     # K-apt 에 없는 단지는 36개월 매매가 이 이상일 때만 별도 페이지


def norm_name(s):
    s = re.sub(r"\([^)]*\)", "", s or "")
    s = re.sub(r"아파트|APT|apt|\s+|[-·.,]", "", s)
    return s


def dedupe(rows, idx):
    seen, out = set(), []
    for r in rows:
        k = tuple(r[i] for i in idx)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


JUNK_NAME = re.compile(r"^[\(\)\d\-\s,.]*$")


def py_label(a):
    """전용면적(㎡) → 공급 평형 근사(전용×1.32÷3.3058)."""
    return int(round(a * 1.32 / 3.3058))


def load_kapt():
    detail = json.loads((RAW / "apt_detail.json").read_text(encoding="utf-8"))
    apts = {}
    for f in RAW.glob("apts_*.json"):
        for a in json.loads(f.read_text(encoding="utf-8")):
            apts[a["code"]] = a
    sgg_map = defaultdict(Counter)
    idx_j = defaultdict(list)      # (sgg, dong, jibun) -> [code]
    idx_d = defaultdict(list)      # (sgg, dong) -> [code]
    for code, d in detail.items():
        a = apts.get(code)
        if not a or not d.get("bjdCode"):
            continue
        sgg = d["bjdCode"][:5]
        sgg_map[sgg][(a["doShort"], a["sigungu"])] += 1
        m = re.search(r"\s(\S+?(?:동|읍|면|가))\s+(\d+(?:-\d+)?)-?\s", (d.get("kaptAddr") or "") + " ")
        dong = a.get("dong") or (m.group(1) if m else "")
        jibun = m.group(2) if m else ""
        if jibun:
            idx_j[(sgg, dong, jibun)].append(code)
        idx_d[(sgg, dong)].append(code)
    return apts, {k: v.most_common(1)[0][0] for k, v in sgg_map.items()}, idx_j, idx_d


SEQ_REQ = {}   # aptSeq -> 요청에 쓴 시군구코드(K-apt bjdCode 앞 5자리와 같은 체계; aptSeq 접두는 옛 코드일 수 있음)


def load_rows(kind):
    out = defaultdict(list)       # aptSeq -> rows
    # 1) 확정 월 이력(_rawdata/trade_hist/{kind}_{ym}.json.gz)  2) 최근 월 캐시(data/trade_cache/{kind}/{ym}/{sgg}.json)
    hist_months = set()
    for f in sorted((RAW / "trade_hist").glob(f"{kind}_*.json.gz")):
        hist_months.add(f.name[:-8].split("_")[1])
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for req, rows in json.load(fh).items():
                for r in rows:
                    if r[0]:
                        out[r[0]].append(r)
                        SEQ_REQ.setdefault(r[0], req)
    base = CACHE / kind
    if base.exists():
        for mdir in sorted(base.iterdir()):
            if mdir.name in hist_months:
                continue            # 이력에 있는 월은 이력을 우선
            for f in mdir.glob("*.json"):
                req = f.stem
                for r in json.loads(f.read_text(encoding="utf-8")):
                    if r[0]:
                        out[r[0]].append(r)
                        SEQ_REQ.setdefault(r[0], req)
    return out


def group_stats_trade(rows):
    by = defaultdict(list)
    for r in rows:
        by[int(r[5])].append(r)
    groups = []
    for a, lst in by.items():
        lst.sort(key=lambda x: (x[4], x[6]))
        l12 = [x for x in lst if x[4] >= Y12]
        if not l12:
            continue
        mx = max(lst, key=lambda x: (x[7], x[4]))
        last = lst[-1]
        groups.append({"a": a, "py": py_label(a), "n12": len(l12), "avg12": int(sum(x[7] for x in l12) / len(l12)), "min12": min(x[7] for x in l12),
                       "max3": mx[7], "max3d": mx[4], "max3f": mx[6], "last": [last[4], last[6], last[7]], "n3": len(lst)})
    groups.sort(key=lambda g: (-g["n12"], g["a"]))
    return groups[:6]


def new_highs(rows):
    by = defaultdict(list)
    for r in rows:
        by[int(r[5])].append(r)
    out = []
    for a, lst in by.items():
        lst.sort(key=lambda x: (x[4], x[6]))
        recent = [x for x in lst if x[4] >= Y30D]
        older = [x for x in lst if x[4] < Y30D]
        if not recent or len(older) < 3:
            continue
        top = max(recent, key=lambda x: x[7])
        pm = max(x[7] for x in older)
        if top[7] > pm:
            out.append({"a": a, "d": top[4], "amt": top[7], "prev": pm, "f": top[6]})
    return out


def main():
    apts, sgg_map, idx_j, idx_d = load_kapt()
    trades = load_rows("trade")
    rents = load_rows("rent")
    print(f"K-apt {len(apts):,}단지, 실거래 단지 매매 {len(trades):,} / 전월세 {len(rents):,}")
    seqs = set(trades) | set(rents)

    # 단지 메타(최빈값)
    out_by_do = defaultdict(list)
    stat = Counter()
    used_codes = {}
    for seq in seqs:
        t_rows = dedupe([r for r in trades.get(seq, []) if not r[9] and r[7] > 0 and r[4] >= Y36], (4, 5, 6, 7))
        r_rows = dedupe([r for r in rents.get(seq, []) if r[4] >= Y12 - 10000 and (r[7] > 0 or r[8] > 0)], (4, 5, 6, 7, 8))
        if not t_rows and not r_rows:
            continue
        sgg = SEQ_REQ.get(seq) or seq.split("-")[0]
        if sgg not in sgg_map:
            stat["no_sgg"] += 1
            continue
        do, sg = sgg_map[sgg]
        src = (t_rows or r_rows)
        name = Counter(r[1] for r in src).most_common(1)[0][0]
        dong = Counter(r[2] for r in src).most_common(1)[0][0]
        jibun = Counter(r[3] for r in src).most_common(1)[0][0]
        by = [r[8] for r in t_rows if r[8]] or [r[-1] for r in r_rows if r[-1]]
        by = Counter(by).most_common(1)[0][0] if by else 0

        # K-apt 연결
        code = ""
        cands = idx_j.get((sgg, dong, jibun), [])
        nn = norm_name(name)
        if cands:
            best = max(cands, key=lambda c: SequenceMatcher(None, nn, norm_name(apts[c]["aptName"])).ratio())
            ratio = SequenceMatcher(None, nn, norm_name(apts[best]["aptName"])).ratio()
            ud = (apts[best].get("usedate") or "")[:4]
            year_ok = bool(by) and ud.isdigit() and abs(int(ud) - int(by)) <= 2
            weird = (not re.search(r"[가-힣]", name)) or JUNK_NAME.match(name) or name.startswith("(")   # 영문·번호뿐인 상호는 이름 비교가 무의미
            if ratio >= 0.5 or (ratio >= 0.2 and year_ok) or (weird and year_ok):
                code = best
        if not code:
            c2 = idx_d.get((sgg, dong), [])
            scored = [(SequenceMatcher(None, nn, norm_name(apts[c]["aptName"])).ratio(), c) for c in c2]
            scored = [x for x in scored if x[0] >= 0.8 or (len(nn) >= 4 and (nn in norm_name(apts[x[1]]["aptName"]) or norm_name(apts[x[1]]["aptName"]) in nn))]
            if scored:
                code = max(scored)[1]
        if code in used_codes and code:
            # 같은 K-apt 단지에 여러 실거래 단지가 매핑되면 거래가 더 많은 쪽만 연결
            prev = used_codes[code]
            if len(t_rows) <= prev[0]:
                code = ""
            else:
                for rec in list(out_by_do[prev[1]]):
                    if rec["seq"] == prev[2]:
                        rec["code"], rec["slug"] = "", ""
                        if rec["n36"] < MIN_TRADES_PAGE or JUNK_NAME.match(rec["name"]) or len(norm_name(rec["name"])) < 2:
                            out_by_do[prev[1]].remove(rec)     # 별도 페이지를 만들 만큼의 거래가 없으면 버린다
        t_sorted = sorted(t_rows, key=lambda x: (x[4], x[6]), reverse=True)
        r_sorted = sorted(r_rows, key=lambda x: (x[4], x[6]), reverse=True)
        tg = group_stats_trade(t_rows)
        # 전월세 평형별
        rgby = defaultdict(list)
        for r in r_rows:
            if r[4] >= Y12:
                rgby[int(r[5])].append(r)
        rg = []
        for a, lst in rgby.items():
            j = [x[7] for x in lst if x[8] == 0]
            w = [x for x in lst if x[8] > 0]
            rg.append({"a": a, "nj": len(j), "avgj": int(sum(j) / len(j)) if j else 0, "nw": len(w),
                       "avgwd": int(sum(x[7] for x in w) / len(w)) if w else 0, "avgwm": int(sum(x[8] for x in w) / len(w)) if w else 0})
        rg.sort(key=lambda g: (-(g["nj"] + g["nw"]), g["a"]))
        # 연도별(최다 거래 평형)
        yr = []
        if tg:
            ta = tg[0]["a"]
            ys = defaultdict(list)
            for r in t_rows:
                if int(r[5]) == ta:
                    ys[r[4] // 10000].append(r[7])
            yr = [[y, len(v), int(sum(v) / len(v))] for y, v in sorted(ys.items())]
        rec = {
            "seq": seq, "code": code, "slug": apts[code]["slug"] if code else "", "name": name, "doShort": do, "sigungu": sg, "dong": dong, "jibun": jibun, "by": by,
            "n36": len(t_rows), "n12": sum(1 for r in t_rows if r[4] >= Y12), "nr12": sum(1 for r in r_rows if r[4] >= Y12),
            "last": t_sorted[0][4] if t_sorted else 0,
            "tg": tg, "rg": rg[:5],
            "t": [[r[4], round(r[5], 1), r[6], r[7]] for r in t_sorted[:20]],
            "r": [[r[4], round(r[5], 1), r[6], r[7], r[8]] for r in r_sorted[:10]],
            "yr": yr, "hi": new_highs(t_rows),
        }
        if code:
            used_codes[code] = (len(t_rows), do, seq)
            stat["matched"] += 1
        else:
            if len(t_rows) < MIN_TRADES_PAGE:
                stat["skip_small"] += 1
                continue
            if JUNK_NAME.match(name) or len(norm_name(name)) < 2:
                stat["skip_junk"] += 1
                continue
            stat["trade_only"] += 1
        out_by_do[do].append(rec)

    for old in RAW.glob("trades_*.json"):
        old.unlink()
    total = 0
    for do, lst in out_by_do.items():
        lst.sort(key=lambda r: (r["sigungu"], r["dong"], r["name"]))
        (RAW / f"trades_{do}.json").write_text(json.dumps(lst, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        total += len(lst)
    latest = max((r["last"] for lst in out_by_do.values() for r in lst), default=0)
    (RAW / "trade_meta.json").write_text(json.dumps({"latest": latest, "built": ymd_of(TODAY)}), encoding="utf-8")
    if total < MIN_TOTAL:
        raise SystemExit(f"가공된 단지가 {total}건뿐입니다(최소 {MIN_TOTAL}). 수집 실패로 보여 중단합니다.")
    sz = sum(f.stat().st_size for f in RAW.glob("trades_*.json")) / 1e6
    print(f"단지 레코드 {total:,} (K-apt 연결 {stat['matched']:,}, 실거래 전용 {stat['trade_only']:,}, 제외(소규모) {stat['skip_small']:,}, 제외(이름없음) {stat['skip_junk']:,}, 지역 없음 {stat['no_sgg']:,}) / {sz:.1f}MB / 최근 거래일 {latest}")
    kapt_with = sum(1 for lst in out_by_do.values() for r in lst if r["code"])
    print(f"K-apt 단지 {len(apts):,} 중 실거래 연결 {kapt_with:,} ({kapt_with / max(1, len(apts)):.0%})")


if __name__ == "__main__":
    main()
