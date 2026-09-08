#!/usr/bin/env python3
"""
process_data.py - 원본 단지 목록(+ 점진적으로 쌓이는 상세정보)을 Jekyll 페이지용 JSON으로 가공

입력:
  _rawdata/apt_list_raw.json   - 전국 22,297개 단지 목록 (kaptCode/kaptName/주소)
  _rawdata/apt_detail.json     - {kaptCode: {상세정보...}} 점진적으로 채워지는 캐시 (없으면 빈 dict로 시작)
출력:
  _rawdata/apts_{시도}.json    - 시도별 분할 (시군구 그룹핑 포함)
  search_index.json            - 검색용 경량 인덱스 (전체 22,297개)
  _rawdata/stats.json          - 진행 통계 (전체/상세정보 채워진 개수 등)
"""
import json, re, hashlib, sys, io
from pathlib import Path
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
RAW_LIST = ROOT / "_rawdata" / "apt_list_raw.json"
RAW_DETAIL = ROOT / "_rawdata" / "apt_detail.json"
RAW_ENERGY = ROOT / "_rawdata" / "apt_energy.json"
RAWDATA_DIR = ROOT / "_rawdata"
SEARCH_INDEX_OUT = ROOT / "search_index.json"
STATS_OUT = ROOT / "_rawdata" / "stats.json"

DO_MAP = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
    "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
    "강원특별자치도": "강원", "강원도": "강원",
    "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "제주도": "제주",
}

# 관리비 API 등에서 참고할 코드성 필드는 없고, 기본정보 API 응답의 코드명 필드(codeHeatNm 등)는
# 이미 사람이 읽을 수 있는 한글 명칭으로 내려오므로 별도 매핑 불필요.


def guess_sido(raw, sggu):
    text = (raw or "").strip()
    sggu = (sggu or "").strip()
    if text == "전남광주통합특별시":
        return "광주" if sggu.endswith("구") else "전남"
    if text in DO_MAP:
        return DO_MAP[text]
    if text in DO_MAP.values():
        return text
    return ""


def slugify(text: str, extra: str) -> str:
    slug = re.sub(r"[^\w가-힣\s-]", "", text).strip()
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    h = hashlib.md5((text + "|" + extra).encode("utf-8")).hexdigest()[:6]
    return f"{slug}-{h}" if slug else h


def _won(v):
    """원 단위 금액을 "12,345원" 형태로. 0/None은 빈 문자열(해당 항목 없음으로 처리)."""
    if not v:
        return ""
    return f"{int(v):,}원"


def _fmt_date(req_date):
    """YYYYMM -> "2026년 7월"."""
    if not req_date or len(req_date) != 6:
        return ""
    return f"{req_date[:4]}년 {int(req_date[4:6])}월"


def energy_fields(e):
    """apt_energy.json의 단지 1건(dict 또는 None)을 페이지 표시용 필드로 변환."""
    if not e:
        return {"hasEnergy": False}
    return {
        "hasEnergy": True,
        "energyMonth": _fmt_date(e.get("reqDate")),
        "heatAmt": _won(e.get("heat")),
        "waterHotAmt": _won(e.get("waterHot")),
        "gasAmt": _won(e.get("gas")),
        "electAmt": _won(e.get("elect")),
        "waterCoolAmt": _won(e.get("waterCool")),
    }


def main():
    raw = json.loads(RAW_LIST.read_text(encoding="utf-8"))
    detail_map = {}
    if RAW_DETAIL.exists():
        detail_map = json.loads(RAW_DETAIL.read_text(encoding="utf-8"))
    print(f"목록 {len(raw)}건, 상세정보 확보 {len(detail_map)}건 ({len(detail_map)*100//max(len(raw),1)}%)")

    energy_map = {}
    if RAW_ENERGY.exists():
        raw_energy = json.loads(RAW_ENERGY.read_text(encoding="utf-8"))
        energy_map = {k: v for k, v in raw_energy.items() if v}  # None(데이터없음) 항목 제외
    print(f"에너지정보 확보 {len(energy_map)}건 ({len(energy_map)*100//max(len(raw),1)}%)")

    apts = []
    seen_slugs = Counter()
    skipped = 0
    for d in raw:
        code = d.get("kaptCode")
        name = (d.get("kaptName") or "").strip()
        do_short = guess_sido(d.get("as1"), d.get("as2"))
        sigungu = (d.get("as2") or "").strip() or "기타"
        dong = (d.get("as3") or "").strip() or "기타"
        if not code or not name or not do_short:
            skipped += 1
            continue

        slug = slugify(name, code)
        seen_slugs[slug] += 1
        if seen_slugs[slug] > 1:
            slug = f"{slug}-{seen_slugs[slug]}"

        detail = detail_map.get(code) or {}
        apts.append({
            "code": code,
            "aptName": name,
            "doShort": do_short,
            "sigungu": sigungu,
            "dong": dong,
            "slug": slug,
            "addr": detail.get("kaptAddr") or "",
            "doroAddr": detail.get("doroJuso") or "",
            "hasDetail": bool(detail),
            "hoCnt": detail.get("hoCnt"),
            "dongCnt": detail.get("kaptDongCnt"),
            "saleType": detail.get("codeSaleNm"),
            "heatType": detail.get("codeHeatNm"),
            "mgrType": detail.get("codeMgrNm"),
            "hallType": detail.get("codeHallNm"),
            "aptType": detail.get("codeAptNm"),
            "usedate": detail.get("kaptUsedate"),
            "bcompany": detail.get("kaptBcompany"),
            "acompany": detail.get("kaptAcompany"),
            "tarea": detail.get("kaptTarea"),
            "marea": detail.get("kaptMarea"),
            "topFloor": detail.get("kaptTopFloor"),
            "tel": detail.get("kaptTel"),
            "fax": detail.get("kaptFax"),
            "homepageUrl": detail.get("kaptUrl"),
            **energy_fields(energy_map.get(code)),
        })

    print(f"제외: {skipped}건 (코드/이름/지역 누락)")

    by_do = defaultdict(list)
    for a in apts:
        by_do[a["doShort"]].append(a)

    RAWDATA_DIR.mkdir(parents=True, exist_ok=True)
    for do, group in by_do.items():
        out = RAWDATA_DIR / f"apts_{do}.json"
        out.write_text(json.dumps(group, ensure_ascii=False), encoding="utf-8")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {do}: {len(group)}개 단지 -> {out.name} ({size_mb:.1f}MB)")

    print(f"\n총 {len(apts)}개 단지 저장 (시도 {len(by_do)}개 파일)")

    do_counts = Counter(a["doShort"] for a in apts)
    print("\n지역별 단지 수:")
    for do, cnt in sorted(do_counts.items(), key=lambda x: -x[1]):
        print(f"  {do}: {cnt}개")

    # 검색 인덱스: 전체 22,297개, 경량 필드만
    index = [
        {"n": a["aptName"], "do": a["doShort"], "sg": a["sigungu"], "s": a["slug"], "d": bool(a["hasDetail"])}
        for a in apts
    ]
    SEARCH_INDEX_OUT.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size_mb = SEARCH_INDEX_OUT.stat().st_size / 1024 / 1024
    print(f"\n검색 인덱스 {len(index)}개 저장 -> {SEARCH_INDEX_OUT} ({size_mb:.1f}MB)")

    filled = sum(1 for a in apts if a["hasDetail"])
    stats = {"total": len(apts), "detailFilled": filled, "detailPct": round(filled * 100 / max(len(apts), 1), 1)}
    STATS_OUT.write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")
    print(f"\n상세정보 진행률: {filled}/{len(apts)} ({stats['detailPct']}%)")


if __name__ == "__main__":
    main()
