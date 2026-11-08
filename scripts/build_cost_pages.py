# -*- coding: utf-8 -*-
"""우아아파트 관리비 순위 페이지 생성 -> cost/ 아래 index.html (Jekyll front matter 페이지, 커밋 대상) + _data/cost_sgg.json.
 /cost/                      전국 세대당 공용관리비 높은/낮은 TOP 30 + 순위 페이지가 있는 시군구
 /cost/{시도}/{시군구}/        수집된 단지 MIN_N개 이상인 시군구의 세대당 공용관리비 순위표
데이터: _rawdata/apts_*.json 의 hasCost/costPerHoNum 등 (scripts/process_data.py 가 apt_cost.json 으로 채움). 수집은 세대수 큰 단지부터 진행되므로
페이지에는 '수집된 단지 기준'임을 밝힌다. 수집이 늘면 이 스크립트를 다시 실행하면 순위 페이지가 자동으로 늘어난다.
사용: python scripts/build_cost_pages.py"""
import collections, glob, html, json, pathlib, shutil, statistics, sys
sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "cost"
MIN_N = 8
esc = html.escape
def clean(t): return t.replace("{{", "{ {").replace("{%", "{ %")
def w(n): return "{:,}".format(int(n))

def load():
    rows = []
    for p in sorted(glob.glob(str(ROOT / "_rawdata" / "apts_*.json"))):
        for r in json.loads(pathlib.Path(p).read_text(encoding="utf-8")):
            if r.get("hasCost") and r.get("slug") and r.get("costPerHoNum"): rows.append(r)
    return rows

def levy_num(r):
    try: return int(str(r.get("levyPerHo") or "0").replace(",", "").replace("원", ""))
    except ValueError: return 0

def tbl(rows, start=1):
    body = "".join('<tr><td>%d</td><td><a href="/apt/%s/">%s</a><br><small>%s %s</small></td><td>%s</td><td>%s</td><td><b>%s</b></td><td>%s</td></tr>'
                   % (i, r["slug"], esc(r["aptName"]), esc(r["sigungu"]), esc(r["dong"] or ""), ("%s세대" % w(r["hoCnt"])) if r.get("hoCnt") else "-",
                      ("%s년" % str(r.get("usedate"))[:4]) if r.get("usedate") else "-", r["costPerHo"], r["costTotal"]) for i, r in enumerate(rows, start))
    return '<div class="tbl-wrap"><table class="trade-tbl" style="min-width:560px;"><thead><tr><th>순위</th><th>단지</th><th>세대수</th><th>준공</th><th>세대당 공용관리비</th><th>월 합계</th></tr></thead><tbody>%s</tbody></table></div>' % body

def write_page(path, title, desc, h1, sub, crumbs, lead, body, faq):
    d = ROOT / path.strip("/"); d.mkdir(parents=True, exist_ok=True)
    cr = " › ".join(('<a href="%s">%s</a>' % (u, esc(n))) if i < len(crumbs) - 1 else "<span>%s</span>" % esc(n) for i, (n, u) in enumerate(crumbs))
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
    fh = "".join('<details style="margin-bottom:10px;"><summary style="cursor:pointer;font-weight:600;padding:6px 0;">%s</summary><p style="color:var(--text-muted);">%s</p></details>' % (esc(q), esc(a)) for q, a in faq)
    (d / "index.html").write_text(f"""---
layout: default
title: "{clean(title).replace('"', "'")}"
description: "{clean(desc).replace('"', "'")}"
---
<div class="hero" style="padding:40px 20px 32px;"><h1 style="font-size:1.6rem;">{esc(h1)}<br><span class="accent">{esc(sub)}</span></h1></div>
<div class="breadcrumb">{cr}</div>
<div class="page-with-sidebar" style="margin-top:20px;">
<div class="side-main"><div class="section">
  <div class="info-panel" style="margin-bottom:18px;"><p>{clean(lead)}</p></div>
  <div class="ad-slot" style="margin:0 0 20px;text-align:center;">{{% include ad.html %}}</div>
  {clean(body)}
  <div style="margin-top:28px;"><h2 style="font-size:1.1rem;margin-bottom:10px;">자주 묻는 질문</h2>{fh}</div>
  <script type="application/ld+json">{json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")}</script>
</div></div>
<aside class="tool-sidebar"></aside>
</div>
""", encoding="utf-8")

NOTE = ("※ 세대당 공용관리비는 K-apt에 공개된 공용관리비 17개 항목(인건비·청소비·경비비 등)의 월 합계를 세대수로 나눈 단순 평균입니다. 전기·수도·난방 같은 개별 사용료와 장기수선충당금은 포함하지 않으며, "
        "단지 규모·연식·경비 방식·보고월에 따라 크게 달라지므로 우열이 아니라 참고용 비교입니다. 이 순위는 현재까지 수집된 단지만 대상으로 하며(세대수 큰 단지부터 매일 늘려가는 중), 전체 단지의 순위가 아닙니다.")

def main():
    rows = load()
    if OUT.exists(): shutil.rmtree(OUT)
    if len(rows) < MIN_N:
        print("수집 단지가 너무 적어 생성 생략", len(rows)); (ROOT / "_data").mkdir(exist_ok=True); (ROOT / "_data" / "cost_sgg.json").write_text("[]", encoding="utf-8"); return
    by = collections.defaultdict(list)
    for r in rows: by[(r["doShort"], r["sigungu"])].append(r)
    keys = []
    for (do, sg), lst in sorted(by.items(), key=lambda t: -len(t[1])):
        if len(lst) < MIN_N: continue
        keys.append("%s|%s" % (do, sg))
        lst.sort(key=lambda r: r["costPerHoNum"])
        vals = [r["costPerHoNum"] for r in lst]
        med = int(statistics.median(vals)); lo, hi = lst[0], lst[-1]
        lead = ("%s %s에서 현재까지 공용관리비가 수집된 %d개 단지를 세대당 월 공용관리비가 낮은 순으로 정렬했습니다. 중앙값은 %s원, 가장 낮은 단지는 %s(%s원), 가장 높은 단지는 %s(%s원)입니다. 보고월은 단지마다 다르며 가장 최근 보고월 기준입니다."
                % (do, sg, len(lst), w(med), lo["aptName"], w(lo["costPerHoNum"]), hi["aptName"], w(hi["costPerHoNum"])))
        body = tbl(lst) + '<p style="color:var(--text-muted);font-size:.82rem;margin-top:12px;">%s</p>' % esc(NOTE)
        body += '<div class="chip-row" style="margin-top:14px;"><a class="chip" href="/region/%s/%s/">%s %s 아파트 전체</a><a class="chip" href="/cost/">전국 관리비 순위</a></div>' % (do, sg, esc(do), esc(sg))
        faq = [("%s %s 아파트 관리비는 평균 얼마인가요?" % (do, sg), "수집된 %d개 단지의 세대당 월 공용관리비 중앙값은 %s원입니다(개별 사용료 제외, 단순 평균 기준)." % (len(lst), w(med))),
               ("관리비가 낮은 단지가 더 좋은 단지인가요?", "아닙니다. 경비·청소 인력, 승강기 수, 단지 규모와 연식에 따라 관리비 구성이 달라 단순 비교로 우열을 가릴 수 없습니다."),
               ("이 순위에 내 단지가 없어요.", "공용관리비 정보는 세대수가 큰 단지부터 순차적으로 수집하고 있어 아직 포함되지 않았을 수 있습니다. 매일 조금씩 늘어납니다.")]
        write_page("/cost/%s/%s/" % (do, sg), "%s %s 아파트 관리비 순위 — 세대당 공용관리비 (%d개 단지)" % (do, sg, len(lst)), "%s %s 아파트 %d개 단지의 세대당 월 공용관리비 순위. 중앙값 %s원, 최저 %s원, 최고 %s원 (K-apt 공개 자료)." % (do, sg, len(lst), w(med), w(lo["costPerHoNum"]), w(hi["costPerHoNum"])),
                   "%s %s 아파트 관리비 순위" % (do, sg), "세대당 월 공용관리비 · 수집 %d개 단지" % len(lst), [("우아아파트", "/"), ("관리비 순위", "/cost/"), ("%s %s" % (do, sg), "/cost/%s/%s/" % (do, sg))], lead, body, faq)
    rows.sort(key=lambda r: r["costPerHoNum"])
    chips = "".join('<a class="chip" href="/cost/%s/%s/">%s %s <em>%d</em></a>' % (k.split("|")[0], k.split("|")[1], esc(k.split("|")[0]), esc(k.split("|")[1]), len(by[tuple(k.split("|"))])) for k in keys)
    body = ('<h2 style="font-size:1.05rem;margin:6px 0 10px;">세대당 공용관리비 낮은 TOP 30</h2>' + tbl(rows[:30]) +
            '<h2 style="font-size:1.05rem;margin:22px 0 10px;">세대당 공용관리비 높은 TOP 30</h2>' + tbl(rows[::-1][:30]) +
            ('<h2 style="font-size:1.05rem;margin:22px 0 10px;">지역별 순위</h2><div class="chip-row">%s</div>' % chips if keys else "") +
            '<p style="color:var(--text-muted);font-size:.82rem;margin-top:12px;">%s</p>' % esc(NOTE))
    med = int(statistics.median(r["costPerHoNum"] for r in rows))
    write_page("/cost/", "아파트 관리비 순위 — 세대당 공용관리비 높은·낮은 단지 TOP", "전국 아파트 %d개 단지의 세대당 월 공용관리비 순위. 중앙값 %s원. K-apt 공개 자료 기반, 시군구별 순위 제공." % (len(rows), w(med)),
               "아파트 관리비 순위", "세대당 공용관리비 · 수집 %s개 단지" % w(len(rows)), [("우아아파트", "/"), ("관리비 순위", "/cost/")],
               "K-apt에 공개된 공용관리비 17개 항목을 세대수로 나눈 세대당 월 평균을 비교합니다. 현재 %s개 단지가 수집됐고 전체 중앙값은 %s원입니다. 세대수 큰 단지부터 매일 늘려가는 중입니다." % (w(len(rows)), w(med)), body,
               [("아파트 관리비는 어떻게 비교했나요?", "공용관리비 17개 항목의 월 합계를 세대수로 나눈 단순 평균입니다. 전기·수도·난방 등 개별 사용료는 포함하지 않습니다."), ("전체 단지가 포함되나요?", "아니요. 세대수가 큰 단지부터 순차 수집 중이라 일부 단지만 포함됩니다.")])
    (ROOT / "_data").mkdir(exist_ok=True)
    (ROOT / "_data" / "cost_sgg.json").write_text(json.dumps(keys, ensure_ascii=False), encoding="utf-8")
    print("관리비 순위: 수집 단지", len(rows), "시군구 페이지", len(keys), "+ 인덱스")

if __name__ == "__main__":
    main()
