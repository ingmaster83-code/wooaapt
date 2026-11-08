# -*- coding: utf-8 -*-
"""우아아파트 역세권 허브 생성 -> station/ 아래 index.html (Jekyll front matter 페이지, 커밋 대상) + _data/apt_stations.json (단지 페이지 '근처 역' 블록용).
 /station/                 전국 역 목록(시도별)
 /station/{역이름}/         역 반경 1km(직선) 안 단지 목록 — 500m 이내(초역세권)·1km 이내, 거리순
 데이터: _rawdata/stations.json (scripts/fetch_stations.py, 카카오 지하철역 카테고리) + 단지 좌표(../wooahakgun/data/geo_cache.json 'K:단지코드') + _rawdata/apts_*.json
사용: python scripts/build_station_pages.py"""
import bisect, collections, glob, html, json, math, pathlib, re, shutil, sys
sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parent.parent
GEO = ROOT.parent / "wooahakgun" / "data" / "geo_cache.json"
OUT = ROOT / "station"
MIN_APTS = 3            # 반경 1km 안 단지가 이 수 미만이면 페이지 생략
NEAR = 500; FAR = 1000  # m
CAP = 80
esc = html.escape
def clean(t): return t.replace("{{", "{ {").replace("{%", "{ %")

def hav(a, b, c, d):
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742000 * math.asin(math.sqrt(x))

def walk_min(m): return max(1, round(m * 1.3 / 80))     # 직선거리 x 1.3(우회) / 분속 80m

def load_apts():
    geo = json.loads(GEO.read_text(encoding="utf-8"))
    rows = []
    for p in sorted(glob.glob(str(ROOT / "_rawdata" / "apts_*.json"))):
        for r in json.loads(pathlib.Path(p).read_text(encoding="utf-8")):
            g = geo.get("K:" + r.get("code", ""))
            if not g or not r.get("slug"): continue
            u = str(r.get("usedate") or "")
            r["lat"], r["lon"] = g
            r["year"] = int(u[:4]) if len(u) >= 4 and u[:4].isdigit() and 1950 <= int(u[:4]) <= 2100 else None
            r["ho"] = int(r["hoCnt"]) if str(r.get("hoCnt") or "").isdigit() else 0
            rows.append(r)
    return rows

def card(a, dist):
    stats = ["<span>🚶 도보 약 %d분 · 직선 %sm</span>" % (walk_min(dist), "{:,}".format(int(round(dist, -1))))]
    if a["ho"]: stats.append("<span>🏠 %s세대</span>" % "{:,}".format(a["ho"]))
    if a["year"]: stats.append("<span>🗓️ %d년 준공</span>" % a["year"])
    return ('<a class="apt-card" data-name="%s" href="/apt/%s/"><div class="apt-card-name">%s</div><div class="apt-card-loc">%s %s %s</div><div class="apt-card-stats">%s</div></a>'
            % (esc(a["aptName"]), a["slug"], esc(a["aptName"]), esc(a["doShort"]), esc(a["sigungu"]), esc(a["dong"] or ""), "".join(stats)))

def write_page(path, title, desc, h1, sub, crumbs, lead_html, body_html, faq):
    d = ROOT / path.strip("/"); d.mkdir(parents=True, exist_ok=True)
    cr = " › ".join(('<a href="%s">%s</a>' % (u, esc(n))) if i < len(crumbs) - 1 else "<span>%s</span>" % esc(n) for i, (n, u) in enumerate(crumbs))
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
    faq_html = "".join('<details style="margin-bottom:10px;"><summary style="cursor:pointer;font-weight:600;padding:6px 0;">%s</summary><p style="color:var(--text-muted);">%s</p></details>' % (esc(q), esc(a)) for q, a in faq)
    out = f"""---
layout: default
title: "{clean(title).replace('"', "'")}"
description: "{clean(desc).replace('"', "'")}"
---
<div class="hero" style="padding:40px 20px 32px;">
  <h1 style="font-size:1.6rem;">{esc(h1)}<br><span class="accent">{esc(sub)}</span></h1>
</div>

<div class="breadcrumb">{cr}</div>

<div class="page-with-sidebar" style="margin-top:20px;">
<div class="side-main">
<div class="section">
  <div class="info-panel" style="margin-bottom:18px;"><p>{clean(lead_html)}</p></div>
  <div class="ad-slot" style="margin:0 0 20px;text-align:center;">{{% include ad.html %}}</div>
  {clean(body_html)}
  <div style="margin-top:28px;">
    <h2 style="font-size:1.1rem;margin-bottom:10px;">자주 묻는 질문</h2>
    {faq_html}
  </div>
  <script type="application/ld+json">{json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")}</script>
</div>
</div>
<aside class="tool-sidebar"></aside>
</div>
"""
    (d / "index.html").write_text(out, encoding="utf-8")

def main():
    stations = json.loads((ROOT / "_rawdata" / "stations.json").read_text(encoding="utf-8"))
    apts = load_apts(); print("좌표 있는 단지", len(apts), "역", len(stations))
    KNOWN = {(a["doShort"], a["sigungu"]) for a in apts}
    apts.sort(key=lambda a: a["lat"]); lats = [a["lat"] for a in apts]
    dlat = FAR / 111000 * 1.02; dlon = FAR / 88000 * 1.05
    near = {}                       # station idx -> [(dist, apt)]
    for i, s in enumerate(stations):
        lo = bisect.bisect_left(lats, s["lat"] - dlat); hi = bisect.bisect_right(lats, s["lat"] + dlat)
        res = []
        for a in apts[lo:hi]:
            if abs(a["lon"] - s["lon"]) > dlon: continue
            d = hav(s["lat"], s["lon"], a["lat"], a["lon"])
            if d <= FAR: res.append((d, a))
        res.sort(key=lambda t: t[0]); near[i] = res
    keep = [i for i in near if len(near[i]) >= MIN_APTS]
    print("페이지 대상 역", len(keep), "/", len(stations))
    # 슬러그: 동명 역은 시군구 덧붙임
    cnt = collections.Counter(stations[i]["name"] for i in keep)
    slugs = {}
    for i in keep:
        s = stations[i]; sg = near[i][0][1]["sigungu"]; do = near[i][0][1]["doShort"]
        tk = (s.get("addr") or "").split()          # 역 주소("서울 강남구 ...")로 시도·시군구를 정하되, 단지 데이터에 있는 조합일 때만 채택
        if len(tk) >= 3:
            for cand in (tk[1] + tk[2], tk[1].rstrip("시") + tk[2], tk[1] + " " + tk[2], tk[1]):
                if (tk[0], cand) in KNOWN: do, sg = tk[0], cand; break
        slugs[i] = s["name"] if cnt[s["name"]] == 1 else "%s-%s" % (s["name"], sg)
        s["do"], s["sg"] = do, sg
    seen = collections.Counter()
    for i in keep:
        seen[slugs[i]] += 1
        if seen[slugs[i]] > 1: slugs[i] = "%s-%d" % (slugs[i], seen[slugs[i]])
    if len(set(slugs.values())) != len(slugs): sys.exit("슬러그 중복")
    if OUT.exists(): shutil.rmtree(OUT)
    by_do = collections.defaultdict(list)
    apt_st = collections.defaultdict(list)      # apt slug -> [(dist, station idx)]
    for i in keep:
        s = stations[i]; res = near[i]; slug = slugs[i]
        n_near = sum(1 for d, a in res if d <= NEAR); ho_all = sum(a["ho"] for d, a in res)
        ys = [a["year"] for d, a in res if a["year"]]
        by_do[s["do"]].append((s["name"], slug, len(res), s["lines"]))
        for d, a in res:
            if d <= 1200: apt_st[a["slug"]].append((d, i))
        lines = " · ".join(s["lines"]) if s["lines"] else "도시철도"
        ctx = "%s %s" % (s["do"], s["sg"])
        big = max(res, key=lambda t: t[1]["ho"])[1]
        lead = ("%s(%s, %s) 반경 1km(직선거리 기준) 안에는 아파트 %d개 단지, 총 %s세대가 있습니다. 그중 500m 이내 초역세권 단지는 %d개이며, 가장 가까운 단지는 %s(약 %s m)입니다. %s"
                % (s["name"], lines, ctx, len(res), "{:,}".format(ho_all), n_near, res[0][1]["aptName"], "{:,}".format(int(round(res[0][0], -1))),
                   ("평균 준공 연도는 %d년이고 가장 큰 단지는 %s(%s세대)입니다." % (round(sum(ys) / len(ys)), big["aptName"], "{:,}".format(big["ho"]))) if ys and big["ho"] else ""))
        body = ""
        g1 = [(d, a) for d, a in res if d <= NEAR]; g2 = [(d, a) for d, a in res if d > NEAR]
        shown = 0
        for ttl, grp in ((("500m 이내 · 초역세권 (도보 약 10분 이내)"), g1), (("500m~1km (도보 약 10~16분)"), g2)):
            if not grp: continue
            grp = grp[:max(0, CAP - shown)]; shown += len(grp)
            if not grp: continue
            body += '<h2 style="font-size:1.05rem;margin:18px 0 10px;">%s · %d개 단지</h2><div class="apt-grid">%s</div>' % (ttl, len(grp), "".join(card(a, d) for d, a in grp))
        body += '<p style="color:var(--text-muted);font-size:.82rem;margin-top:14px;">※ 거리는 역 위치와 단지 위치 사이의 직선거리이며, 도보 시간은 직선거리 × 1.3(우회 보정)을 분속 80m로 환산한 추정치입니다. 실제 경로·출구 위치·언덕 등에 따라 다릅니다. 역 위치는 카카오맵, 단지 정보는 국토교통부 K-apt 기준입니다.</p>'
        body += '<div class="chip-row" style="margin-top:14px;"><a class="chip" href="/region/%s/%s/">%s %s 아파트 전체</a><a class="chip" href="/station/">전국 역세권 아파트</a></div>' % (s["do"], s["sg"], esc(s["do"]), esc(s["sg"]))
        faq = [("%s 초역세권 아파트는 어디인가요?" % s["name"], "%s에서 직선거리 500m 이내(도보 약 10분)에는 %d개 단지가 있습니다.%s 세대수·준공 연도는 각 단지 페이지에서 확인할 수 있습니다." % (s["name"], n_near, (" 가장 가까운 곳은 %s입니다." % res[0][1]["aptName"]) if res else "")),
               ("%s 근처 아파트는 모두 몇 개 단지인가요?" % s["name"], "반경 1km 안 %d개 단지, %s세대입니다(K-apt 등록 공동주택 기준)." % (len(res), "{:,}".format(ho_all))),
               ("도보 시간은 어떻게 계산했나요?", "역과 단지 사이의 직선거리에 우회 보정 1.3을 곱하고 분속 80m로 나눈 추정치입니다. 실제 보행 경로와는 차이가 있을 수 있습니다.")]
        write_page("/station/%s/" % slug, "%s 근처 아파트 %d개 단지 — %s 역세권 (%s)" % (s["name"], len(res), ctx, lines), "%s 반경 1km 아파트 %d개 단지·%s세대. 500m 이내 초역세권 %d개 단지, 거리순 목록과 세대수·준공연도·도보시간." % (s["name"], len(res), "{:,}".format(ho_all), n_near),
                   "%s 근처 아파트" % s["name"], "%s · %s" % (ctx, lines), [("우아아파트", "/"), ("역세권 아파트", "/station/"), (s["name"], "/station/%s/" % slug)], lead, body, faq)
    # 인덱스
    secs = ""; order = ["서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종"]
    for do in sorted(by_do, key=lambda k: (order.index(k) if k in order else 99, k)):
        lst = sorted(by_do[do], key=lambda t: -t[2])
        secs += '<h2 style="font-size:1.05rem;margin:20px 0 10px;">%s · 역 %d곳</h2><div class="chip-row">%s</div>' % (esc(do), len(lst), "".join('<a class="chip" href="/station/%s/">%s <em>%d</em></a>' % (sl, esc(nm), c) for nm, sl, c, ln in lst))
    lead = "전국 지하철·도시철도·광역철도 역 %d곳 반경 1km 안의 아파트 단지를 거리순으로 모았습니다. 역 이름 옆 숫자는 반경 1km 안 단지 수입니다." % len(keep)
    write_page("/station/", "역세권 아파트 — 전국 지하철역 %d곳 근처 아파트 단지 목록" % len(keep), "전국 지하철역 %d곳별로 반경 1km 안 아파트 단지를 거리순으로 정리했습니다. 초역세권(500m 이내) 단지·세대수·준공 연도 비교." % len(keep),
               "역세권 아파트", "지하철역 근처 아파트 단지 모아보기", [("우아아파트", "/"), ("역세권 아파트", "/station/")], lead, secs,
               [("역세권 아파트는 역에서 몇 m 이내를 말하나요?", "법적 기준은 없고, 보통 도보 10분(약 500~800m) 이내를 역세권, 500m 이내를 초역세권이라 부릅니다. 이 사이트는 직선거리 500m·1km를 기준으로 나눴습니다."),
                ("거리는 어떻게 계산했나요?", "역 좌표와 단지 좌표 사이의 직선거리입니다. 실제 걷는 거리는 길 모양에 따라 더 길 수 있습니다.")])
    # 단지 페이지용 데이터
    D = ROOT / "_data"; D.mkdir(exist_ok=True)
    out = {}
    for slug, lst in apt_st.items():
        lst.sort(key=lambda t: t[0])
        rows = [[stations[i]["name"], slugs[i], int(round(d, -1)), walk_min(d), "·".join(stations[i]["lines"][:3])] for d, i in lst[:3] if i in slugs]
        if rows: out[slug] = rows
    (D / "apt_stations.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("역 페이지", len(keep), "+ 인덱스 1, 근처 역 있는 단지", len(out), "/", len(apts))

if __name__ == "__main__":
    main()
