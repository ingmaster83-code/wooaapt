# -*- coding: utf-8 -*-
"""우아아파트 조건별 단지 허브 생성 -> hall/ heating/ year/ large/ old/ builder/ filters/ 아래 index.html (Jekyll front matter 페이지, 커밋 대상).
 /hall/{계단식|복도식|혼합식}/..   /heating/{지역난방|개별난방|중앙난방}/..   /old/..(재건축 연한 30년 이상)   /year/{연대}/..   /builder/{시공사}/..   /large/..(1,000세대+)
 각각 전국 → 시도 → 시군구(조건 만족 단지 MIN개 이상일 때). 데이터: _rawdata/apts_*.json (22,297단지).
사용: python scripts/build_filter_pages.py   (매년 1월 재건축 연한 기준 연도가 바뀌므로 재실행)"""
import collections, datetime, glob, html, json, pathlib, re, shutil, sys
sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT                                # 페이지는 저장소 루트의 hall/ heating/ year/ large/ old/ builder/ filters/ 아래에 생성
GEN_DIRS = ["hall", "heating", "year", "large", "old", "builder", "filters"]
YEAR = datetime.date.today().year
OLD_YEAR = YEAR - 30                      # 사용승인 연도가 이 값 이하면 재건축 연한(30년) 경과
MIN_SGG = 5                               # 시군구 페이지 최소 단지 수
CAP = 100                                 # 한 페이지 카드 수 상한
esc = html.escape

def load():
    rows = []
    for p in sorted(glob.glob(str(ROOT / "_rawdata" / "apts_*.json"))):
        rows += json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    out = []
    for r in rows:
        if not r.get("slug") or not r.get("doShort") or not r.get("sigungu"): continue
        u = str(r.get("usedate") or "")
        r["year"] = int(u[:4]) if len(u) >= 4 and u[:4].isdigit() and 1950 <= int(u[:4]) <= YEAR else None
        r["ho"] = int(r["hoCnt"]) if str(r.get("hoCnt") or "").isdigit() else 0
        r["hall"] = (r.get("hallType") or "").strip()
        r["heat"] = (r.get("heatType") or "").strip()
        r["brand"] = brand(r.get("bcompany"))
        out.append(r)
    return out

ALIAS = [("현대산업개발", "HDC현대산업개발"), ("HDC", "HDC현대산업개발"), ("현대엔지니어링", "현대엔지니어링"), ("현대건설", "현대건설"), ("대우건설", "대우건설"), ("대우", "대우건설"), ("GS건설", "GS건설"), ("LG건설", "GS건설"), ("럭키", "GS건설"),
         ("삼성물산", "삼성물산"), ("삼성건설", "삼성물산"), ("롯데건설", "롯데건설"), ("대림산업", "DL이앤씨"), ("DL", "DL이앤씨"), ("대림", "DL이앤씨"), ("포스코", "포스코이앤씨"), ("SK", "SK에코플랜트"), ("한화", "한화건설"),
         ("쌍용", "쌍용건설"), ("두산", "두산건설"), ("금호", "금호건설"), ("태영", "태영건설"), ("동부", "동부건설"), ("코오롱", "코오롱글로벌"), ("한신공영", "한신공영"), ("계룡", "계룡건설"), ("우미", "우미건설"), ("호반", "호반건설"),
         ("중흥", "중흥건설"), ("대방", "대방건설"), ("반도", "반도건설"), ("이수", "이수건설"), ("삼부", "삼부토건"), ("신동아", "신동아건설"), ("벽산", "벽산건설"), ("동아건설", "동아건설"), ("극동", "극동건설"), ("한양", "한양"),
         ("풍림", "풍림산업"), ("진흥", "진흥기업"), ("경남기업", "경남기업"), ("대한주택공사", "한국토지주택공사(LH)"), ("한국토지주택공사", "한국토지주택공사(LH)"), ("주택공사", "한국토지주택공사(LH)"), ("LH", "한국토지주택공사(LH)"),
         ("한국주택", "한국토지주택공사(LH)"), ("SH", "SH공사"), ("서울주택도시", "SH공사"), ("부영", "부영주택"), ("우성건설", "우성건설"), ("제일건설", "제일건설"), ("서희", "서희건설"), ("우방", "우방"), ("한라", "한라건설"),
         ("양우", "양우건설"), ("남양건설", "남양건설"), ("성원", "성원건설"), ("건영", "건영"), ("동원개발", "동원개발"), ("동문", "동문건설")]
def brand(n):
    c = re.sub(r"\(.*?\)|㈜|주식회사|\s", "", (n or "").strip())
    if not c or c in ("미기재", "-", "없음"): return None
    for kk, v in ALIAS:
        if kk in c: return v
    return None

def decade(y):
    if y is None: return None
    if y < 1980: return "1970년대이전"
    return "%d년대" % (y // 10 * 10)

def card(a):
    stats = ["<span>🏠 %s세대</span>" % "{:,}".format(a["ho"])] if a["ho"] else []
    if a["year"]: stats.append("<span>🗓️ %d년 준공</span>" % a["year"])
    if a["hall"]: stats.append("<span>%s</span>" % esc(a["hall"]))
    if a["heat"]: stats.append("<span>%s</span>" % esc(a["heat"]))
    return ('<a class="apt-card" data-name="%s" href="/apt/%s/"><div class="apt-card-name">%s</div><div class="apt-card-loc">%s %s %s</div><div class="apt-card-stats">%s</div></a>'
            % (esc(a["aptName"]), a["slug"], esc(a["aptName"]), esc(a["doShort"]), esc(a["sigungu"]), esc(a["dong"] or ""), "".join(stats)))

def stats_sentence(items):
    n = len(items); ho = sum(a["ho"] for a in items)
    ys = [a["year"] for a in items if a["year"]]
    s = "총 %s개 단지, %s세대" % ("{:,}".format(n), "{:,}".format(ho))
    if ys: s += "이며 평균 준공 연도는 %d년(가장 오래된 %d년~가장 최근 %d년)" % (round(sum(ys) / len(ys)), min(ys), max(ys))
    big = max(items, key=lambda a: a["ho"])
    if big["ho"]: s += ", 가장 큰 단지는 %s(%s세대)" % (big["aptName"], "{:,}".format(big["ho"]))
    return s + "입니다."

def clean(t): return t.replace("{{", "{ {").replace("{%", "{ %")

def write(path, title, desc, h1, sub, crumbs, lead, chips_html, items, order, faq, note=""):
    d = OUT / path.strip("/")
    d.mkdir(parents=True, exist_ok=True)
    items = sorted(items, key=order)
    shown = items[:CAP]
    cr = ' › '.join(('<a href="%s">%s</a>' % (u, esc(n))) if i < len(crumbs) - 1 else "<span>%s</span>" % esc(n) for i, (n, u) in enumerate(crumbs))
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
    faq_html = "".join('<details style="margin-bottom:10px;"><summary style="cursor:pointer;font-weight:600;padding:6px 0;">%s</summary><p style="color:var(--text-muted);">%s</p></details>' % (esc(q), esc(a)) for q, a in faq)
    more = ('<p class="note" style="color:var(--text-muted);font-size:.85rem;margin-top:10px;">전체 %s개 중 %d개만 표시했습니다. 더 좁혀 보려면 시군구 페이지를 이용하세요.</p>' % ("{:,}".format(len(items)), len(shown))) if len(items) > len(shown) else ""
    out = f"""---
layout: default
title: "{clean(title).replace('"', "'")}"
description: "{clean(desc).replace('"', "'")}"
---
<div class="hero" style="padding:40px 20px 32px;">
  <h1 style="font-size:1.6rem;">{esc(h1)}<br><span class="accent">{esc(sub)}</span></h1>
  <p>{esc(stats_sentence(items))}</p>
</div>

<div class="breadcrumb">{cr}</div>

<div class="page-with-sidebar" style="margin-top:20px;">
<div class="side-main">
<div class="section">
  <div class="info-panel" style="margin-bottom:18px;"><p>{clean(lead)}</p></div>
  <div class="ad-slot" style="margin:0 0 20px;text-align:center;">{{% include ad.html %}}</div>
  {chips_html}
  <div class="apt-grid">
    {''.join(clean(card(a)) for a in shown)}
  </div>
  {more}
  {note}
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

def chip_row(items):
    return '<div class="chip-row" style="margin-bottom:16px;">%s</div>' % "".join('<a class="chip" href="%s">%s <em>%s</em></a>' % (u, esc(t), c) for t, u, c in items)

def region_chips(prefix, bucket, level):
    """bucket: dict key->list. level 'do' => (do) chips, 'sgg' => sigungu chips"""
    return chip_row([(k if isinstance(k, str) else k[-1], "%s%s/" % (prefix, "/".join(k) if isinstance(k, tuple) else k), "{:,}".format(len(v))) for k, v in sorted(bucket.items(), key=lambda t: -len(t[1]))])

# 조건 패밀리 정의 ------------------------------------------------------------
FAMILIES = {}
def family(slug, title_noun, label_fn, pred, order, order_label, intro, faq_fn, values):
    FAMILIES[slug] = dict(noun=title_noun, label=label_fn, pred=pred, order=order, order_label=order_label, intro=intro, faq=faq_fn, values=values)

HALL_INTRO = {
    "계단식": "계단식 아파트는 한 층에 여러 세대가 엘리베이터·계단 홀을 공유하는 구조로, 복도식보다 세대 간 사생활이 보호되고 환기와 채광이 유리한 경우가 많습니다.",
    "복도식": "복도식 아파트는 긴 외부 복도를 따라 현관이 이어지는 구조로 한 층에 많은 세대를 배치하는 방식입니다. 건축 시기가 오래된 단지에 많고 세대 간 거리가 가깝다는 특징이 있습니다.",
    "혼합식": "혼합식 아파트는 계단식과 복도식이 한 단지 안에 함께 있거나 동마다 구조가 다른 단지입니다. 같은 단지라도 동에 따라 구조가 다를 수 있습니다.",
}
HEAT_INTRO = {
    "지역난방": "지역난방은 열병합발전소 등에서 만든 온수를 단지에 공급받는 방식으로 단지별 보일러가 필요 없고 안전하다는 특징이 있습니다. 난방비는 열요금 체계에 따라 부과됩니다.",
    "개별난방": "개별난방은 세대마다 보일러를 설치해 도시가스로 난방하는 방식으로 각 세대가 사용 시기와 온도를 직접 조절합니다.",
    "중앙난방": "중앙난방은 단지 내 보일러실에서 온수를 만들어 모든 세대에 공급하는 방식입니다. 관리사무소가 가동 시간을 정하는 경우가 많습니다.",
}

def build():
    apts = load()
    for g in GEN_DIRS:
        if (OUT / g).exists(): shutil.rmtree(OUT / g)
    total = 0
    def sg_url(a): return "/region/%s/%s/" % (a["doShort"], a["sigungu"])

    def make_family(slug, noun, values, keyfn, order, order_label, lead_fn, faq_fn, extra_note=""):
        nonlocal total
        for val in values:
            sel = [a for a in apts if keyfn(a) == val]
            if not sel: continue
            by_do = collections.defaultdict(list)
            for a in sel: by_do[a["doShort"]].append(a)
            base = "/%s/%s/" % (slug, val)
            label = noun(val)
            # 전국
            write(base, "%s 전국 단지 %s개 — 시도·시군구별" % (label, "{:,}".format(len(sel))), "%s %s개 단지를 시도·시군구별로 정리했습니다. %s" % (label, "{:,}".format(len(sel)), order_label), label, "전국 단지 목록",
                  [("홈", "/"), ("조건별 아파트", "/filters/"), (label, base)], lead_fn(label, sel, "전국"), region_chips(base, {k: v for k, v in by_do.items()}, "do"), sel, order, faq_fn(label, sel, "전국"), extra_note); total += 1
            for do, dl in by_do.items():
                by_sg = collections.defaultdict(list)
                for a in dl: by_sg[a["sigungu"]].append(a)
                pdo = "%s%s/" % (base, do)
                sg_ok = {k: v for k, v in by_sg.items() if len(v) >= MIN_SGG}
                chips = region_chips(pdo, sg_ok, "sgg") if sg_ok else ""
                write(pdo, "%s %s 단지 %s개" % (do, label, "{:,}".format(len(dl))), "%s의 %s %s개 단지. 시군구별 단지 수와 세대수 많은 단지를 확인하세요." % (do, label, "{:,}".format(len(dl))), "%s %s" % (do, label), "단지 목록",
                      [("홈", "/"), ("조건별 아파트", "/filters/"), (label, base), (do, pdo)], lead_fn(label, dl, do), chips, dl, order, faq_fn(label, dl, do)); total += 1
                for sg, sl in sg_ok.items():
                    psg = "%s%s/" % (pdo, sg)
                    write(psg, "%s %s %s 단지 %d개" % (do, sg, label, len(sl)), "%s %s의 %s %d개 단지 목록. 세대수·준공 연도·난방방식 정보와 단지별 실거래가·관리비 링크." % (do, sg, label, len(sl)), "%s %s %s" % (do, sg, label), "단지 목록",
                          [("홈", "/"), ("조건별 아파트", "/filters/"), (label, base), (do, pdo), (sg, psg)], lead_fn(label, sl, "%s %s" % (do, sg)),
                          chip_row([("%s %s 전체 단지 보기" % (do, sg), sg_url(sl[0]), "")]), sl, order, faq_fn(label, sl, "%s %s" % (do, sg))); total += 1

    # 계단식·복도식·혼합식
    make_family("hall", lambda v: "%s 아파트" % v, ["계단식", "복도식", "혼합식"], lambda a: a["hall"], lambda a: (-a["ho"], a["aptName"]), "세대수가 많은 단지 순으로 정렬했습니다.",
                lambda label, items, where_: "%s에 있는 <b>%s</b> %s개 단지입니다. %s 단지를 누르면 세대수·준공일·난방방식과 실거래가·전월세 시세를 볼 수 있습니다." % (esc(where_), esc(label), "{:,}".format(len(items)), HALL_INTRO.get(label.split()[0], "")),
                lambda label, items, where_: [("%s에는 %s 아파트가 몇 곳 있나요?" % (where_, label.split()[0]), "공공데이터 기준 %s개 단지입니다." % "{:,}".format(len(items))), ("%s와 다른 구조의 차이는?" % label.split()[0], HALL_INTRO.get(label.split()[0], ""))])
    # 난방방식
    make_family("heating", lambda v: "%s 아파트" % v, ["지역난방", "개별난방", "중앙난방"], lambda a: a["heat"], lambda a: (-a["ho"], a["aptName"]), "세대수가 많은 단지 순으로 정렬했습니다.",
                lambda label, items, where_: "%s의 <b>%s</b> %s개 단지입니다. %s" % (esc(where_), esc(label), "{:,}".format(len(items)), HEAT_INTRO.get(label.split()[0], "")),
                lambda label, items, where_: [("%s 아파트는 어떤 점이 다른가요?" % label.split()[0], HEAT_INTRO.get(label.split()[0], "")), ("%s에 몇 곳 있나요?" % where_, "공공데이터 기준 %s개 단지입니다." % "{:,}".format(len(items)))])
    # 준공 연대
    DECADES = ["2020년대", "2010년대", "2000년대", "1990년대", "1980년대", "1970년대이전"]
    make_family("year", lambda v: "%s 준공 아파트" % v.replace("이전", " 이전"), DECADES, lambda a: decade(a["year"]), lambda a: (a["year"] or 0, a["aptName"]), "준공 연도가 오래된 단지부터 정렬했습니다.",
                lambda label, items, where_: "%s에서 <b>%s</b> 단지는 %s개입니다. 사용승인일 기준이며 단지를 누르면 세대수·난방방식과 실거래가를 볼 수 있습니다." % (esc(where_), esc(label), "{:,}".format(len(items))),
                lambda label, items, where_: [("%s 아파트는 몇 곳인가요?" % label, "%s에 공공데이터 기준 %s개 단지가 있습니다." % (where_, "{:,}".format(len(items)))), ("준공 연도는 어떤 기준인가요?", "공동주택 관리정보의 사용승인일 연도를 기준으로 했습니다.")])
    # 대단지
    make_family("large", lambda v: "1,000세대 이상 대단지", ["1000"], lambda a: "1000" if a["ho"] >= 1000 else None, lambda a: (-a["ho"], a["aptName"]), "세대수가 많은 단지 순으로 정렬했습니다.",
                lambda label, items, where_: "%s의 1,000세대 이상 대단지는 <b>%s개</b>입니다. 대단지는 단지 내 상가·커뮤니티 시설이 크고 거래가 활발한 경우가 많습니다. 단지를 누르면 세대수·준공일·실거래가를 볼 수 있습니다." % (esc(where_), "{:,}".format(len(items))),
                lambda label, items, where_: [("%s 1,000세대 이상 아파트는 몇 곳인가요?" % where_, "공공데이터 기준 %s개 단지입니다." % "{:,}".format(len(items))), ("대단지의 장점은?", "공용 시설과 관리 규모가 크고 거래가 활발한 편이지만 관리비와 입주·이사 시기 혼잡 등은 단지별로 다릅니다.")])
    # 재건축 연한 (사용승인 OLD_YEAR 이하)
    old = [a for a in apts if a["year"] and a["year"] <= OLD_YEAR]
    if old:
        by_do = collections.defaultdict(list)
        for a in old: by_do[a["doShort"]].append(a)
        base = "/old/"
        lead = lambda where_, items: ("%s에서 사용승인 후 30년이 지난(%d년 이전 준공) 아파트는 <b>%s개 단지</b>입니다. 일반적으로 준공 후 30년이 지나면 재건축 안전진단을 신청할 수 있는 연한을 채우지만, 안전진단 결과·정비구역 지정·조합 설립 등 별도 요건을 통과해야 재건축이 가능합니다. "
                                     "이 목록은 사용승인일만 기준으로 한 참고 자료이며 재건축 추진 여부를 뜻하지 않습니다.") % (esc(where_), OLD_YEAR, "{:,}".format(len(items)))
        faq = lambda where_, items: [("재건축 연한 30년은 무엇인가요?", "공동주택이 준공 후 30년이 지나면 재건축 안전진단을 받을 수 있는 연한 요건을 충족한다는 뜻입니다. 안전진단 통과 등 다른 요건이 필요합니다."), ("%s에는 30년 넘은 아파트가 몇 곳인가요?" % where_, "%d년 이전 준공 기준 %s개 단지입니다." % (OLD_YEAR, "{:,}".format(len(items))))]
        write(base, "재건축 연한 30년 넘은 아파트 전국 %s개 단지 (%d년 이전 준공)" % ("{:,}".format(len(old)), OLD_YEAR), "준공 후 30년이 지난 아파트 %s개 단지를 시도·시군구별로 정리했습니다. 사용승인일 기준 참고 자료입니다." % "{:,}".format(len(old)), "재건축 연한 30년 넘은 아파트", "전국 단지 목록",
              [("홈", "/"), ("조건별 아파트", "/filters/"), ("재건축 연한 30년+", base)], lead("전국", old), region_chips(base, dict(by_do), "do"), old, lambda a: (a["year"], -a["ho"], a["aptName"]), faq("전국", old)); total += 1
        for do, dl in by_do.items():
            by_sg = collections.defaultdict(list)
            for a in dl: by_sg[a["sigungu"]].append(a)
            sg_ok = {k: v for k, v in by_sg.items() if len(v) >= 3}
            pdo = "%s%s/" % (base, do)
            write(pdo, "%s 재건축 연한 30년 넘은 아파트 %s개 단지" % (do, "{:,}".format(len(dl))), "%s의 준공 30년 이상 아파트 %s개 단지를 시군구별로 정리했습니다." % (do, "{:,}".format(len(dl))), "%s 재건축 연한 30년 넘은 아파트" % do, "단지 목록",
                  [("홈", "/"), ("조건별 아파트", "/filters/"), ("재건축 연한 30년+", base), (do, pdo)], lead(do, dl), region_chips(pdo, sg_ok, "sgg") if sg_ok else "", dl, lambda a: (a["year"], -a["ho"], a["aptName"]), faq(do, dl)); total += 1
            for sg, sl in sg_ok.items():
                psg = "%s%s/" % (pdo, sg)
                write(psg, "%s %s 재건축 연한 30년 넘은 아파트 %d개 단지" % (do, sg, len(sl)), "%s %s의 준공 30년 이상 아파트 %d개 단지 목록. 준공 연도 오래된 순, 세대수·난방방식과 실거래가 링크." % (do, sg, len(sl)), "%s %s 재건축 연한 30년 넘은 아파트" % (do, sg), "단지 목록",
                      [("홈", "/"), ("조건별 아파트", "/filters/"), ("재건축 연한 30년+", base), (do, pdo), (sg, psg)], lead("%s %s" % (do, sg), sl), chip_row([("%s %s 전체 단지 보기" % (do, sg), sg_url(sl[0]), "")]), sl, lambda a: (a["year"], -a["ho"], a["aptName"]), faq("%s %s" % (do, sg), sl)); total += 1
    # 시공사
    bl = [a for a in apts if a["brand"]]
    bc = collections.Counter(a["brand"] for a in bl)
    for br, cnt in bc.items():
        if cnt < 40: continue
        sel = [a for a in bl if a["brand"] == br]
        by_do = collections.defaultdict(list)
        for a in sel: by_do[a["doShort"]].append(a)
        base = "/builder/%s/" % br
        lead = lambda where_, items, br=br: "%s에서 <b>%s</b>이(가) 시공한 아파트는 <b>%s개 단지</b>입니다. 시공사는 공동주택 관리정보에 기재된 값을 정리한 것으로 합병·사명 변경 전 이름이 같은 회사로 묶여 있을 수 있습니다. 단지를 누르면 세대수·준공일과 실거래가를 볼 수 있습니다." % (esc(where_), esc(br), "{:,}".format(len(items)))
        faq = lambda where_, items, br=br: [("%s 시공 아파트는 몇 곳인가요?" % br, "%s에 공공데이터 기준 %s개 단지입니다." % (where_, "{:,}".format(len(items))))]
        do_ok = {k: v for k, v in by_do.items() if len(v) >= 3}
        write(base, "%s 시공 아파트 전국 %s개 단지 — 지역별" % (br, "{:,}".format(len(sel))), "%s이(가) 시공한 아파트 %s개 단지를 시도별로 정리했습니다." % (br, "{:,}".format(len(sel))), "%s 시공 아파트" % br, "전국 단지 목록",
              [("홈", "/"), ("조건별 아파트", "/filters/"), ("시공사별", "/builder/"), (br, base)], lead("전국", sel), region_chips(base, do_ok, "do") if do_ok else "", sel, lambda a: (-a["ho"], a["aptName"]), faq("전국", sel)); total += 1
        for do, dl in do_ok.items():
            pdo = "%s%s/" % (base, do)
            write(pdo, "%s %s 시공 아파트 %d개 단지" % (do, br, len(dl)), "%s에서 %s이(가) 시공한 아파트 %d개 단지 목록. 세대수·준공 연도와 실거래가 링크." % (do, br, len(dl)), "%s %s 시공 아파트" % (do, br), "단지 목록",
                  [("홈", "/"), ("조건별 아파트", "/filters/"), ("시공사별", "/builder/"), (br, base), (do, pdo)], lead(do, dl), "", dl, lambda a: (-a["ho"], a["aptName"]), faq(do, dl)); total += 1
    # 시공사 허브 + 전체 허브
    top = sorted([(b, c) for b, c in bc.items() if c >= 40], key=lambda t: -t[1])
    d = OUT / "builder"; d.mkdir(parents=True, exist_ok=True)
    chips = chip_row([(b, "/builder/%s/" % b, "{:,}".format(c)) for b, c in top])
    (d / "index.html").write_text(f"""---
layout: default
title: "시공사별 아파트 단지 — 현대건설·대우건설·GS건설 등 {len(top)}개 건설사"
description: "건설사별로 시공한 아파트 단지를 정리했습니다. 단지 수와 지역별 목록을 확인하세요."
---
<div class="hero" style="padding:40px 20px 32px;"><h1 style="font-size:1.6rem;">시공사별 아파트<br><span class="accent">건설사별 단지 목록</span></h1><p>공동주택 관리정보에 기재된 시공사 기준으로 {len(top)}개 건설사를 정리했습니다.</p></div>
<div class="breadcrumb"><a href="/">홈</a> › <a href="/filters/">조건별 아파트</a> › <span>시공사별</span></div>
<div class="page-with-sidebar" style="margin-top:20px;"><div class="side-main"><div class="section">
<div class="info-panel" style="margin-bottom:18px;"><p>건설사를 누르면 해당 건설사가 시공한 단지를 지역별로 볼 수 있습니다. 시공사가 기재되지 않은 단지는 제외했고, 이름이 바뀐 회사는 같은 회사로 묶었습니다(예: 대림산업→DL이앤씨).</p></div>
<div class="ad-slot" style="margin:0 0 20px;text-align:center;">{{% include ad.html %}}</div>
{chips}
</div></div><aside class="tool-sidebar"></aside></div>
""", encoding="utf-8"); total += 1
    # /filters/ 허브
    fam_chips = []
    for slug, label in (("hall", "계단식·복도식·혼합식"), ("heating", "난방방식(지역·개별·중앙)"), ("year", "준공 연대별"), ("large", "1,000세대 이상 대단지"), ("old", "재건축 연한 30년 넘은 아파트"), ("builder", "시공사별")):
        pass
    (OUT / "filters").mkdir(parents=True, exist_ok=True)
    blocks = [("🏢 구조", [("계단식 아파트", "/hall/계단식/"), ("복도식 아파트", "/hall/복도식/"), ("혼합식 아파트", "/hall/혼합식/")]),
              ("🔥 난방방식", [("지역난방", "/heating/지역난방/"), ("개별난방", "/heating/개별난방/"), ("중앙난방", "/heating/중앙난방/")]),
              ("🗓️ 준공 연대", [(x.replace("이전", " 이전") + " 준공", "/year/%s/" % x) for x in DECADES]),
              ("🏗️ 규모·연식", [("1,000세대 이상 대단지", "/large/1000/"), ("재건축 연한 30년 넘은 아파트", "/old/")]),
              ("🏭 시공사", [(b, "/builder/%s/" % b) for b, c in top[:14]] + [("시공사 전체 보기", "/builder/")])]
    secs = "".join('<h2 style="font-size:1.1rem;margin:18px 0 8px;">%s</h2>%s' % (h, '<div class="chip-row">%s</div>' % "".join('<a class="chip" href="%s">%s</a>' % (u, esc(t)) for t, u in items)) for h, items in blocks)
    (OUT / "filters" / "index.html").write_text(f"""---
layout: default
title: "조건별 아파트 찾기 — 계단식·복도식·재건축 연한·시공사·난방방식·대단지"
description: "계단식·복도식, 난방방식, 준공 연대, 대단지, 재건축 연한 30년, 시공사 조건으로 전국 아파트 단지를 찾아보세요."
---
<div class="hero" style="padding:40px 20px 32px;"><h1 style="font-size:1.6rem;">조건별 아파트 찾기<br><span class="accent">구조·난방·연식·시공사로 골라보기</span></h1><p>전국 22,297개 단지를 조건별로 정리했습니다.</p></div>
<div class="breadcrumb"><a href="/">홈</a> › <span>조건별 아파트</span></div>
<div class="page-with-sidebar" style="margin-top:20px;"><div class="side-main"><div class="section">
<div class="info-panel" style="margin-bottom:18px;"><p>원하는 조건을 고르면 전국·시도·시군구별로 해당 단지를 볼 수 있습니다. 각 단지 페이지에서 세대수, 준공일, 실거래가와 전월세 시세를 확인하세요.</p></div>
<div class="ad-slot" style="margin:0 0 20px;text-align:center;">{{% include ad.html %}}</div>
{secs}
</div></div><aside class="tool-sidebar"></aside></div>
""", encoding="utf-8"); total += 1
    print("filter pages", total, "| 재건축 연한 기준: %d년 이전 준공 (%d단지)" % (OLD_YEAR, len(old)))

if __name__ == "__main__":
    build()
