"""
scrapers/hoiquan1.py
Chạy độc lập: python scrapers/hoiquan1.py

Mỗi trận có thể có nhiều stream: FULLHF / HD / SD
→ Mỗi stream = 1 dòng riêng trong file M3U

API:
  BASE : https://sv.hoiquantv.xyz/api/v1/external
  ├─ /fixtures/unfinished      → danh sách trận
  ├─ /fixtures/{id}/sources    → danh sách stream (thử trước)
  ├─ /fixtures/{id}/streams    → danh sách stream (thử tiếp)
  └─ /fixtures/{id}            → chi tiết trận
"""

import sys
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__file__), '..'))

import os, json, re, io, time
from datetime import datetime, timezone, timedelta
from config import BASE_THUMB_URL, BG_IMAGE_URL, OUTPUT_ROOT, THUMBS_DIR, DOCS_DIR

# ──────────────────────────────────────────────────────────────
# CẤU HÌNH
# ──────────────────────────────────────────────────────────────
SITE_NAME = "HoiQuan1"
SITE_URL  = "https://sv2.hoiquan1.live/"
API_BASE  = "https://sv.hoiquantv.xyz/api/v1/external"

API_FIXTURES = f"{API_BASE}/fixtures/unfinished"

OUTPUT_DIR = os.path.join(OUTPUT_ROOT, SITE_NAME)
OUT_M3U    = os.path.join(OUTPUT_DIR, f"{SITE_NAME}.m3u")
OUT_JSON   = os.path.join(OUTPUT_DIR, f"{SITE_NAME}.json")
TZ_VN      = timezone(timedelta(hours=7))
DELAY      = 0.4

for d in [OUTPUT_DIR, THUMBS_DIR, DOCS_DIR]:
    os.makedirs(d, exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent":      UA,
    "Accept":          "application/json, */*",
    "Accept-Language": "vi-VN,vi;q=0.9",
    "Referer":         SITE_URL,
    "Origin":          SITE_URL.rstrip("/"),
}

TEAM_SHORT = {
    "Manchester United":"Man Utd","Manchester City":"Man City",
    "Barcelona":"Barca","Real Madrid":"Real","Atletico Madrid":"Atletico",
    "Inter Milan":"Inter","AC Milan":"Milan","Juventus":"Juve",
    "Bayern Munich":"Bayern","Borussia Dortmund":"Dortmund",
    "Paris Saint-Germain":"PSG","Tottenham Hotspur":"Spurs",
    "Villarreal":"Villarr",
}
def shorten(name):
    name = str(name).strip()
    for f, s in TEAM_SHORT.items():
        if f.lower() in name.lower(): return s
    return name[:12] + ".." if len(name) > 13 else name


# ══════════════════════════════════════════════════════════════
# HTTP helper
# ══════════════════════════════════════════════════════════════
def get_json(url, extra=None):
    h = {**HEADERS, **(extra or {})}
    print(f"  [API] {url[:90]}", flush=True)
    try:
        from curl_cffi import requests as cr
        r = cr.get(url, headers=h, impersonate="chrome110", timeout=20)
    except ImportError:
        import requests
        r = requests.get(url, headers=h, timeout=20)

    print(f"        HTTP {r.status_code}", flush=True)
    if r.status_code == 200:
        try:
            return r.json()
        except Exception:
            return None
    return None


# ══════════════════════════════════════════════════════════════
# BƯỚC 1: Lấy danh sách trận
# ══════════════════════════════════════════════════════════════
def fetch_fixtures():
    print(f"\n[1/4] Lay danh sach tran: {API_FIXTURES}", flush=True)
    data = get_json(API_FIXTURES)
    if not data:
        return []

    if isinstance(data, dict):
        print(f"      Keys: {list(data.keys())}", flush=True)

    items = extract_list(data)
    if items:
        print(f"      {len(items)} tran tim duoc", flush=True)
        print(f"\n--- CAU TRUC ITEM DAU TIEN ---", flush=True)
        print(json.dumps(items[0], ensure_ascii=False, indent=2)[:800], flush=True)
        print("---\n", flush=True)
    return items


def extract_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ["data","fixtures","matches","events","items",
                  "results","list","response","unfinished"]:
            v = data.get(k)
            if isinstance(v, list):
                print(f"      Key '{k}': {len(v)} items", flush=True)
                return v
        best = []
        for v in data.values():
            if isinstance(v, list) and len(v) > len(best):
                best = v
        if best:
            return best
    return []


# ══════════════════════════════════════════════════════════════
# BƯỚC 2: Lấy TẤT CẢ stream cho từng trận
# ══════════════════════════════════════════════════════════════
def fetch_streams_for_fixture(fixture_id):
    """
    Thử nhiều endpoint, lấy TẤT CẢ stream (FULLHF/HD/SD).
    Trả về list [{"name": "FULLHF", "url": "..."}, {"name": "HD", ...}, ...]
    """
    candidates = [
        f"{API_BASE}/fixtures/{fixture_id}/sources",
        f"{API_BASE}/fixtures/{fixture_id}/streams",
        f"{API_BASE}/fixtures/{fixture_id}",
        f"{API_BASE}/streams?fixture_id={fixture_id}",
        f"{API_BASE}/sources?fixture_id={fixture_id}",
        f"{API_BASE}/fixtures/{fixture_id}/links",
        f"{API_BASE}/fixtures/{fixture_id}/players",
    ]

    for url in candidates:
        data = get_json(url)
        if not data:
            continue
        streams = parse_streams_from_data(data, fixture_id)
        if streams:
            ep = url.replace(API_BASE, "")
            print(f"      -> {len(streams)} stream tu endpoint: {ep}", flush=True)
            return streams

    return []


def parse_streams_from_data(data, fixture_id=""):
    """
    Trích xuất TẤT CẢ stream URLs từ response.
    Nhận diện tên chất lượng: FULLHF / HD / SD / FHD / ...
    """
    streams = []

    # Nhãn chất lượng phổ biến
    QUALITY_LABELS = ["fullhf","fhd","full hd","1080","hd","720","sd","480","360","low","high","medium"]

    def guess_quality(obj):
        """Đoán tên chất lượng từ các field trong obj."""
        for field in ["name","label","quality","type","title","resolution"]:
            v = str(obj.get(field, "")).strip()
            if v:
                return v
        return "HD"

    def scan(obj, depth=0):
        if depth > 6:
            return
        if isinstance(obj, dict):
            # Tìm URL stream trong obj này
            stream_url = None
            for f in ["url","src","hls","stream_url","streamUrl",
                      "m3u8","link","source","play_url","cdn_url",
                      "stream","path","file"]:
                v = obj.get(f, "")
                if v and isinstance(v, str) and v.startswith("http"):
                    stream_url = v
                    break

            if stream_url:
                name = guess_quality(obj)
                streams.append({"name": name, "url": stream_url})
            else:
                # Chưa thấy URL → đi sâu vào các field con
                for v in obj.values():
                    scan(v, depth + 1)

        elif isinstance(obj, list):
            for item in obj:
                scan(item, depth + 1)

    scan(data)

    # Fallback regex nếu scan không tìm được gì
    if not streams:
        raw = json.dumps(data) if not isinstance(data, str) else data
        found = re.findall(r'https?://[^\s"\'\\]+(?:\.m3u8|\.flv|/live/)[^\s"\'\\]*', raw)
        for i, u in enumerate(found):
            streams.append({"name": f"Stream {i+1}", "url": u})

    # Dedup theo URL
    seen, unique = set(), []
    for s in streams:
        if s["url"] not in seen:
            seen.add(s["url"])
            unique.append(s)

    return unique


def normalize_stream_name(raw_name, index, total):
    """
    Chuẩn hóa tên stream: ưu tiên nhận ra FULLHF/HD/SD.
    Nếu chỉ có 1 stream → không thêm label.
    """
    if total == 1:
        return ""   # Trả về rỗng → không thêm [label] vào tên kênh

    name_up = str(raw_name).upper().strip()

    # Nhận diện theo keyword
    if any(x in name_up for x in ["FULLHF","FULL HF","FHD","FULL HD","1080"]):
        return "FULLHF"
    if any(x in name_up for x in ["HD","720","HIGH"]):
        return "HD"
    if any(x in name_up for x in ["SD","480","360","LOW","MEDIUM"]):
        return "SD"

    # Fallback: dùng tên gốc hoặc đánh số
    return raw_name if raw_name else f"Link {index+1}"


# ══════════════════════════════════════════════════════════════
# BƯỚC 3: Parse thông tin trận đấu
# ══════════════════════════════════════════════════════════════
def parse_fixture(item):
    if not isinstance(item, dict):
        return None

    uid = (item.get("_id") or item.get("id") or
           item.get("fixture_id") or item.get("fixtureId") or
           item.get("event_id") or "")

    home = away = home_logo = away_logo = ""

    if "home" in item and isinstance(item["home"], dict):
        home      = item["home"].get("name", "")
        home_logo = item["home"].get("logo", "") or item["home"].get("image", "")
    if "away" in item and isinstance(item["away"], dict):
        away      = item["away"].get("name", "")
        away_logo = item["away"].get("logo", "") or item["away"].get("image", "")

    if not home and "teams" in item and isinstance(item["teams"], dict):
        h = item["teams"].get("home", {}) or {}
        a = item["teams"].get("away", {}) or {}
        home = h.get("name", ""); home_logo = h.get("logo", "")
        away = a.get("name", ""); away_logo = a.get("logo", "")

    if not home:
        home      = item.get("home_team","") or item.get("homeTeam","") or item.get("homeName","")
        away      = item.get("away_team","") or item.get("awayTeam","") or item.get("awayName","")
        home_logo = item.get("home_logo","") or item.get("homeLogo","")
        away_logo = item.get("away_logo","") or item.get("awayLogo","")

    name = f"{home} vs {away}" if home and away else (
        item.get("name") or item.get("title") or item.get("match_name") or str(uid) or "Unknown"
    )

    raw_time = (item.get("date") or item.get("matchTime") or
                item.get("start_time") or item.get("startTime") or
                item.get("time") or item.get("kickoff") or "")
    time_str = "00h00"
    if raw_time:
        try:
            from dateutil import parser as dp
            dt = dp.parse(str(raw_time)).astimezone(TZ_VN)
            time_str = dt.strftime("%Hh%M")
        except Exception:
            t = re.search(r'(\d{1,2}:\d{2})', str(raw_time))
            if t: time_str = t.group(1).replace(":", "h")

    league = ""
    for path in [
        lambda x: x.get("league",{}).get("name") if isinstance(x.get("league"),dict) else x.get("league"),
        lambda x: x.get("tournament",{}).get("name") if isinstance(x.get("tournament"),dict) else x.get("tournament"),
        lambda x: x.get("competition",""),
        lambda x: x.get("league_name",""),
        lambda x: x.get("category",""),
    ]:
        try:
            v = path(item)
            if v and isinstance(v, str): league = v; break
        except Exception:
            pass
    league = league or "Hoi Quan 1"

    thumb = (item.get("thumbnail") or item.get("logo") or
             item.get("image") or item.get("poster") or home_logo or "")

    return {
        "id":         str(uid),
        "name":       f"[{time_str}] {name}",
        "name_clean": name,
        "group":      league,
        "logo":       thumb,
        "home_logo":  home_logo,
        "away_logo":  away_logo,
        "home":       home,
        "away":       away,
        "time":       time_str,
    }


# ══════════════════════════════════════════════════════════════
# BƯỚC 4: Thumbnail
# ══════════════════════════════════════════════════════════════
_bg = None

def load_bg():
    global _bg
    if _bg: return _bg
    try:
        from PIL import Image
        try:
            from curl_cffi import requests as cr
            res = cr.get(BG_IMAGE_URL, timeout=10, impersonate="chrome110")
        except Exception:
            import requests
            res = requests.get(BG_IMAGE_URL, timeout=10)
        _bg = Image.open(io.BytesIO(res.content)).convert("RGBA").resize((640, 360))
        print("  [OK] Anh nen 640x360", flush=True)
    except Exception as e:
        from PIL import Image
        print(f"  [!] Dung nen den: {e}", flush=True)
        _bg = Image.new("RGBA", (640, 360), (20, 20, 40, 255))
    return _bg


def make_thumb(mid, home_url, away_url):
    try:
        from PIL import Image
        try:
            from curl_cffi import requests as cr
            def gi(u): return Image.open(io.BytesIO(cr.get(u, timeout=5, impersonate="chrome110").content)).convert("RGBA")
        except Exception:
            import requests
            def gi(u): return Image.open(io.BytesIO(requests.get(u, timeout=5).content)).convert("RGBA")

        bg = load_bg().copy()
        ok = False
        if home_url:
            try: img = gi(home_url).resize((120,120)); bg.paste(img,(100,100),img); ok=True
            except Exception: pass
        if away_url:
            try: img = gi(away_url).resize((120,120)); bg.paste(img,(420,100),img); ok=True
            except Exception: pass
        if ok:
            p = f"{THUMBS_DIR}/{mid}.png"
            bg.save(p, "PNG")
            return f"{BASE_THUMB_URL}{mid}.png"
    except Exception as e:
        print(f"    [!] Thumb loi: {e}", flush=True)
    return BG_IMAGE_URL


# ══════════════════════════════════════════════════════════════
# BƯỚC 5: Xuất file M3U — mỗi stream = 1 dòng riêng
# ══════════════════════════════════════════════════════════════
def write_m3u(rows):
    """
    rows = list of {
        "name":    "[21h00] MU vs Arsenal",
        "group":   "Premier League",
        "thumb":   "https://...",
        "streams": [{"name":"FULLHF","url":"..."},
                    {"name":"HD","url":"..."},
                    {"name":"SD","url":"..."}]
    }
    Mỗi stream → 1 entry riêng trong M3U.
    """
    total_entries = sum(len(r["streams"]) for r in rows)

    with open(OUT_M3U, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        f.write(f"# Source  : {SITE_URL}\n")
        f.write(f"# Updated : {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")
        f.write(f"# Matches : {len(rows)} tran\n")
        f.write(f"# Streams : {total_entries} kenh\n\n")

        for r in rows:
            streams = r["streams"]
            total   = len(streams)

            for i, s in enumerate(streams):
                # Tên kênh: [21h00] MU vs Arsenal [FULLHF]
                label = normalize_stream_name(s["name"], i, total)
                if label:
                    channel_name = f"{r['name']} [{label}]"
                else:
                    channel_name = r["name"]

                # group-title giữ nguyên tên giải
                f.write(
                    f'#EXTINF:-1 '
                    f'tvg-logo="{r["thumb"]}" '
                    f'group-title="{r["group"]}"'
                    f',{channel_name}\n'
                )
                f.write(f'#EXTVLCOPT:http-referrer={SITE_URL}\n')
                f.write(f'#EXTVLCOPT:http-user-agent={UA}\n')
                f.write(f'{s["url"]}\n\n')

    print(f"  [OK] {OUT_M3U}", flush=True)
    print(f"       {len(rows)} tran × streams = {total_entries} kenh tong", flush=True)


def write_json(rows):
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "site":     SITE_NAME,
            "source":   SITE_URL,
            "updated":  datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "matches":  len(rows),
            "total_streams": sum(len(r["streams"]) for r in rows),
            "data":     rows,
        }, f, ensure_ascii=False, indent=2)
    print(f"  [OK] {OUT_JSON}", flush=True)


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
def main():
    print("=" * 60, flush=True)
    print(f"  {SITE_NAME}", flush=True)
    print(f"  {datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M ICT')}", flush=True)
    print("=" * 60, flush=True)

    # 1. Danh sách trận
    fixtures = fetch_fixtures()
    if not fixtures:
        print("[LOI] Khong lay duoc fixtures!", flush=True)
        return []

    # 2. Stream từng trận
    print(f"\n[2/4] Lay stream cho {len(fixtures)} tran...\n", flush=True)
    rows          = []   # Dữ liệu đầy đủ để ghi file
    no_stream_ids = []

    for i, fix in enumerate(fixtures):
        ch = parse_fixture(fix)
        if not ch:
            continue

        uid = ch["id"] or f"hq_{i}"
        print(f"  [{i+1:03d}/{len(fixtures)}] {ch['name'][:55]}", flush=True)

        # Thử inline trước
        streams = parse_streams_from_data(fix)
        if streams:
            print(f"      -> Stream inline: {len(streams)} link", flush=True)

        # Gọi endpoint riêng nếu chưa có
        if not streams and uid:
            streams = fetch_streams_for_fixture(uid)
            time.sleep(DELAY)

        if not streams:
            no_stream_ids.append(uid)
            print(f"      -> SKIP (khong co stream)", flush=True)
            continue

        # In tất cả stream tìm được
        for j, s in enumerate(streams):
            label = normalize_stream_name(s["name"], j, len(streams))
            tag   = f" [{label}]" if label else ""
            print(f"      [{j+1}]{tag} {s['url'][:65]}", flush=True)

        thumb = make_thumb(uid, ch["home_logo"], ch["away_logo"])

        rows.append({
            "name":    ch["name"],
            "group":   ch["group"],
            "thumb":   thumb,
            "streams": streams,   # ← TOÀN BỘ stream, không chỉ streams[0]
            "home":    ch["home"],
            "away":    ch["away"],
            "time":    ch["time"],
            "id":      uid,
        })

    # 3. Debug nếu thiếu stream
    if no_stream_ids:
        print(f"\n[!] {len(no_stream_ids)} tran khong co stream.", flush=True)
        print(f"    IDs: {no_stream_ids[:5]}", flush=True)
        print(f"\n--- DEBUG ---", flush=True)
        test_id = no_stream_ids[0]
        for ep in [f"/fixtures/{test_id}/sources",
                   f"/fixtures/{test_id}/streams",
                   f"/fixtures/{test_id}"]:
            data = get_json(API_BASE + ep)
            if data:
                print(f"  Response ({ep}):", flush=True)
                print(f"  {json.dumps(data, ensure_ascii=False)[:500]}", flush=True)
                break

    # 4. Xuất file
    total_streams = sum(len(r["streams"]) for r in rows)
    print(f"\n[3/4] Ket qua: {len(rows)} tran / {total_streams} stream tong", flush=True)
    print(f"\n[4/4] Xuat file...", flush=True)

    if rows:
        write_m3u(rows)
        write_json(rows)

    print(f"\n{'='*60}", flush=True)
    print(f"  XONG! {len(rows)} tran | {total_streams} kenh trong M3U", flush=True)
    print(f"{'='*60}", flush=True)

    return rows


if __name__ == "__main__":
    main()
