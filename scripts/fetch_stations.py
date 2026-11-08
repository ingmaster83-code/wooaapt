#!/usr/bin/env python3
"""
fetch_stations.py - 전국 지하철·도시철도·광역철도 역 좌표를 카카오 로컬 API(카테고리 SW8)로 수집해 _rawdata/stations.json 에 저장.

- 아파트 좌표(../wooahakgun/data/geo_cache.json 'K:단지코드')가 있는 격자 셀마다 반경 검색(최대 45건: 15건 x 3페이지).
- 45건에 도달한 셀은 로그로 남겨 반경/격자 조정 근거로 쓴다.
- 결과: [{name(역 이름, 호선 제거), lines[], lat, lon, addr}]  (같은 역의 호선별 항목은 합침)
- 키: 환경변수 KAKAO_REST_KEY (없으면 ../hosppass/.env, 로컬 전용).
"""
import json, os, re, sys, time, math, pathlib, concurrent.futures
import requests
sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parent.parent
GEO = ROOT.parent / "wooahakgun" / "data" / "geo_cache.json"
OUT = ROOT / "_rawdata" / "stations.json"
URL = "https://dapi.kakao.com/v2/local/search/category.json"
DLAT, DLON, RADIUS = 0.04, 0.05, 3300

def key():
    k = os.environ.get("KAKAO_REST_KEY")
    if k: return k
    for line in (ROOT.parent / "hosppass" / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("KAKAO_REST_KEY="): return line.split("=", 1)[1].strip()
    sys.exit("KAKAO_REST_KEY 필요")
S = requests.Session(); S.headers["Authorization"] = "KakaoAK " + key()

def cell_query(c):
    lat, lon = c
    got = []
    for page in (1, 2, 3):
        for a in range(3):
            try:
                r = S.get(URL, params={"category_group_code": "SW8", "x": lon, "y": lat, "radius": RADIUS, "page": page, "size": 15, "sort": "distance"}, timeout=30)
                if r.status_code == 429: time.sleep(2); continue
                r.raise_for_status(); j = r.json(); break
            except Exception as e:
                if a == 2: raise
                time.sleep(1.5)
        got += j["documents"]
        if j["meta"]["is_end"]: break
    return c, got

def main():
    geo = json.loads(GEO.read_text(encoding="utf-8"))
    cells = set()
    for k, v in geo.items():
        if v and k.startswith("K:"):
            cells.add((round((math.floor(v[0] / DLAT) + .5) * DLAT, 4), round((math.floor(v[1] / DLON) + .5) * DLON, 4)))
    cells = sorted(cells); print("셀", len(cells), flush=True)
    raw = {}; full = 0; t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(6) as ex:
        for n, (c, docs) in enumerate(ex.map(cell_query, cells), 1):
            if len(docs) >= 45: full += 1
            for d in docs: raw[d["id"]] = d
            if n % 200 == 0: print("  %d/%d 역항목 %d 포화셀 %d (%.0f초)" % (n, len(cells), len(raw), full, time.time() - t0), flush=True)
    print("원시 항목", len(raw), "포화셀", full)
    st = {}
    for d in raw.values():
        nm = d["place_name"]
        m = re.match(r"^(.+?역)\s*(.*)$", nm)
        if not m or d.get("category_name", "").find("지하철") < 0 and d.get("category_name", "").find("철도") < 0: continue
        base, line = m.group(1), m.group(2).strip()
        base = re.sub(r"\s+", "", base)
        # 같은 이름이라도 서로 먼 역(예: 서로 다른 도시의 '시청역')은 분리: 이름+500m 이내 병합
        lat, lon = float(d["y"]), float(d["x"])
        hit = None
        for s in st.setdefault(base, []):
            if abs(s["lat"] - lat) < 0.006 and abs(s["lon"] - lon) < 0.007: hit = s; break
        if hit is None:
            hit = {"name": base, "lines": [], "lat": lat, "lon": lon, "addr": d.get("road_address_name") or d.get("address_name") or ""}
            st[base].append(hit)
        if line and line not in hit["lines"]: hit["lines"].append(line)
    out = [s for v in st.values() for s in v]
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("역", len(out), "저장", OUT, "(%.0f초)" % (time.time() - t0))

if __name__ == "__main__":
    main()
