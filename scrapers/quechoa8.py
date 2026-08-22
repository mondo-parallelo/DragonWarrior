"""
scrapers/quechoa8.py
Chạy độc lập: python scrapers/quechoa8.py

CÁCH HOẠT ĐỘNG:
  1. Fetch trang chủ quechoa8.live
  2. Parse dữ liệu RSC (React Server Components) nhúng trong HTML
     → Lấy danh sách trận đấu + metadata (đội, logo, giải, BLV, giờ)
  3. Fetch trang chi tiết từng trận → lấy stream URL (FHD/HD/SD) của mỗi BLV
  4. Xuất file .m3u và .json

OUTPUT M3U FORMAT:
  [18:30 | 09.05] Liverpool - Chelsea [Premier League] | BLV: PUMA [FHD]
"""

import sys
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__file__), '..'))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import os, json, re, time
from datetime import datetime, timezone, timedelta
from config import BASE_THUMB_URL, OUTPUT_ROOT, THUMBS_DIR, DOCS_DIR

# ──────────────────────────────────────────────────────────────
SITE_NAME  = "QueChoaTV"
SITE_URL   = "https://quechoa11.live"
HOME_URL   = "https://quechoa11.live/"
DELAY      = 0.3

OUTPUT_DIR = os.path.join(OUTPUT_ROOT, SITE_NAME)
OUT_M3U    = os.path.join(OUTPUT_DIR, f"{SITE_NAME}.m3u")
OUT_JSON   = os.path.join(OUTPUT_DIR, f"{SITE_NAME}.json")
TZ_VN      = timezone(timedelta(hours=7))

for d in [OUTPUT_DIR, THUMBS_DIR, DOCS_DIR]:
    os.makedirs(d, exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent":      UA,
    "Accept":          "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Referer":         SITE_URL + "/",
}


# ══════════════════════════════════════════════════════════════
# HTTP
# ══════════════════════════════════════════════════════════════
def fetch_html(url, timeout=15):
    print(f"  [GET] {url}", flush=True)
    try:
        from curl_cffi import requests as cr
        r = cr.get(url, headers=HEADERS, impersonate="chrome110", timeout=timeout)
        print(f"        HTTP {r.status_code} | {len(r.text)} bytes", flush=True)
        if r.status_code == 200:
            return r.text
    except Exception as e:
        print(f"        curl_cffi: {e}", flush=True)
    try:
        import requests
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.text
    except Exception as e:
        print(f"        requests: {e}", flush=True)
    return ""


# ══════════════════════════════════════════════════════════════
# RSC PARSING — Parse React Server Components payload
# ══════════════════════════════════════════════════════════════
def extract_rsc_data(html):
    """
    Trích xuất và ghép nối tất cả RSC chunks từ HTML page.
    Trả về chuỗi unescaped JSON-like data.
    """
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
    full_rsc = "".join(chunks)
    # Unescape JSON strings
    full_rsc = full_rsc.replace('\\"', '"').replace('\\\\', '\\').replace('\\n', '\n')
    return full_rsc


def parse_matches_from_rsc(rsc):
    """
    Parse danh sách trận đấu từ RSC data trang chủ.
    Mỗi trận đấu là một component card $L34 với cấu trúc:
      {"slug":"...", "startTime":"$DXXX", "league":"...",
       "teamA":{name,logo,score}, "teamB":{name,logo,score},
       "allCommentators":[{id,name,avatar,isPrimary},...]}
    """
    matches = []
    seen_slugs = set()

    # Pattern: Tìm match card JSON objects trong RSC
    # Mỗi card bắt đầu bằng {"slug":"XXX-vs-YYY-...",
    # và chứa teamA, teamB, allCommentators
    pattern = re.compile(
        r'\{"slug":"([^"]+)",'
        r'"isLive":(true|false),'
        r'"isHot":(true|false),'
        r'"status":"([^"]*)",'
        r'"startTime":"\$D([^"]+)",'
        r'"league":"([^"]*)",'
        r'"leagueIcon":"([^"]*)",'
        r'"cardBgUrl":"?([^",]*)"?,'
        r'"teamA":\{"name":"([^"]*)","logo":"([^"]*)","score":(\d+)\},'
        r'"teamB":\{"name":"([^"]*)","logo":"([^"]*)","score":(\d+)\},'
        r'"commentator":\{[^}]*\},'
        r'"additionalCommentators":\d+,'
        r'"allCommentators":\[(.*?)\],'
        r'"matchInfo":',
        re.S
    )

    for m in pattern.finditer(rsc):
        slug = m.group(1)

        # Bỏ qua "full-match-" (video xem lại)
        if slug.startswith("full-match-"):
            continue

        # Bỏ qua trùng lặp (cùng trận hiện ở nhiều section)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        is_live     = m.group(2) == "true"
        is_hot      = m.group(3) == "true"
        status      = m.group(4)
        start_time  = m.group(5)
        league      = m.group(6)
        league_icon = m.group(7)
        team_a_name = m.group(9)
        team_a_logo = m.group(10)
        team_a_score = int(m.group(11))
        team_b_name = m.group(12)
        team_b_logo = m.group(13)
        team_b_score = int(m.group(14))
        comms_raw   = m.group(15)

        # Parse commentators
        commentators = []
        for cm in re.finditer(
            r'\{"id":"([^"]+)","name":"([^"]+)",'
            r'"customCommentatorLabel":([^,]+),'
            r'"avatar":"([^"]+)",'
            r'"isPrimary":(true|false)\}',
            comms_raw
        ):
            commentators.append({
                "id":        cm.group(1),
                "name":      cm.group(2),
                "avatar":    cm.group(4),
                "isPrimary": cm.group(5) == "true",
            })

        # Parse start_time → giờ Việt Nam (UTC+7)
        try:
            dt_utc = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            dt_vn  = dt_utc.astimezone(TZ_VN)
            time_label = dt_vn.strftime("%H:%M")
            date_label = dt_vn.strftime("%d.%m")
        except Exception:
            time_label = ""
            date_label = ""

        matches.append({
            "slug":          slug,
            "is_live":       is_live,
            "is_hot":        is_hot,
            "status":        status,
            "start_time_utc": start_time,
            "time_label":    time_label,
            "date_label":    date_label,
            "league":        league,
            "league_icon":   league_icon,
            "team_a":        {"name": team_a_name, "logo": team_a_logo, "score": team_a_score},
            "team_b":        {"name": team_b_name, "logo": team_b_logo, "score": team_b_score},
            "commentators":  commentators,
            "page_url":      f"{SITE_URL}/truc-tiep/{slug}",
        })

    return matches


def parse_stream_urls_from_rsc(rsc, match_commentator_ids):
    """
    Parse stream URLs từ RSC data trang chi tiết trận đấu.
    Mỗi BLV trong trang detail có cấu trúc:
      "account":{"id":"XXX","name":"YYY","username":"ZZZ",
       "image":"...", "streamUrls":[{"label":"FHD","url":"..."},...]
      }
    match_commentator_ids: set các commentator ID cần lấy stream.
    Trả về dict: { commentator_id: {"name":..., "streamUrls":[...]} }
    """
    result = {}

    for m in re.finditer(
        r'"account":\{"id":"([^"]+)","name":"([^"]+)","username":"([^"]+)",'
        r'"image":"([^"]+)",'
        r'"streamUrls":\[([^\]]*)\]',
        rsc, re.S
    ):
        comm_id   = m.group(1)
        comm_name = m.group(2)
        urls_raw  = m.group(5)

        # Chỉ lấy BLV thuộc trận này
        if comm_id not in match_commentator_ids:
            continue

        # Parse stream URLs
        stream_urls = []
        for su in re.finditer(r'\{"label":"([^"]+)","url":"([^"]+)"\}', urls_raw):
            stream_urls.append({"label": su.group(1), "url": su.group(2)})

        if stream_urls and comm_id not in result:
            result[comm_id] = {
                "name":       comm_name,
                "streamUrls": stream_urls,
            }

    return result


# ══════════════════════════════════════════════════════════════
# BƯỚC 1: Parse trang chủ → danh sách trận
# ══════════════════════════════════════════════════════════════
def fetch_match_list():
    html = fetch_html(HOME_URL)
    if not html:
        print("  [!] Khong lay duoc trang chu!", flush=True)
        return []

    rsc = extract_rsc_data(html)
    matches = parse_matches_from_rsc(rsc)

    print(f"  {len(matches)} tran tim duoc", flush=True)
    for m in matches:
        blvs = ", ".join(c["name"] for c in m["commentators"])
        print(f"    [{m['time_label']} | {m['date_label']}] "
              f"{m['team_a']['name']} vs {m['team_b']['name']} "
              f"[{m['league']}] BLV: {blvs}", flush=True)

    return matches


# ══════════════════════════════════════════════════════════════
# BƯỚC 2: Fetch trang detail → lấy stream URLs cho mỗi BLV
# ══════════════════════════════════════════════════════════════
def scrape_match_streams(match):
    """
    Fetch trang chi tiết trận đấu → parse RSC data → lấy stream URLs.
    Trả về list[dict] — mỗi dict là 1 kênh IPTV (1 BLV × 1 quality).
    """
    page_url = match["page_url"]
    html = fetch_html(page_url, timeout=12)
    if not html:
        return []

    rsc = extract_rsc_data(html)

    # Lấy danh sách commentator IDs của trận này
    comm_ids = {c["id"] for c in match["commentators"]}
    blv_streams = parse_stream_urls_from_rsc(rsc, comm_ids)

    if not blv_streams:
        print(f"    [!] Khong tim thay stream URL trong detail page", flush=True)
        return []

    channels = []
    time_label = match["time_label"]
    date_label = match["date_label"]
    league     = match["league"]
    team_a     = match["team_a"]["name"]
    team_b     = match["team_b"]["name"]
    team_a_logo = match["team_a"]["logo"]
    team_b_logo = match["team_b"]["logo"]

    for comm in match["commentators"]:
        comm_id = comm["id"]
        if comm_id not in blv_streams:
            print(f"    [!] BLV {comm['name']}: khong co stream", flush=True)
            continue

        blv_info = blv_streams[comm_id]
        blv_name = blv_info["name"]

        # Lọc: chỉ lấy FHD và HD, bỏ SD
        wanted = [
            su for su in blv_info["streamUrls"]
            if su["label"].upper() in ("FHD", "HD")
        ]
        if not wanted:
            # Fallback: nếu không có FHD/HD, lấy cái đầu tiên
            wanted = blv_info["streamUrls"][:1]

        # Nếu FHD và HD cùng URL → gộp thành 1 entry [FHD]
        # Nếu khác URL → tạo riêng FHD và HD
        fhd = next((s for s in wanted if s["label"].upper() == "FHD"), None)
        hd  = next((s for s in wanted if s["label"].upper() == "HD"),  None)

        if fhd and hd and fhd["url"] == hd["url"]:
            # Trùng URL → 1 entry duy nhất
            output_streams = [{"label": "FHD", "url": fhd["url"]}]
        elif fhd and hd:
            # Khác URL → 2 entry riêng
            output_streams = [fhd, hd]
        else:
            # Chỉ có 1 trong 2 hoặc fallback
            output_streams = wanted

        for su in output_streams:
            ch_name = (
                f"[{time_label} | {date_label}] "
                f"{team_a} - {team_b} [{league}] "
                f"| BLV: {blv_name} [{su['label']}]"
            )
            channels.append({
                "name":       ch_name,
                "league":     league,
                "stream_url": su["url"],
                "streams":    [s["url"] for s in blv_info["streamUrls"]],
                "page_url":   page_url,
                "logo":       team_a_logo,
                "team_a_logo": team_a_logo,
                "team_b_logo": team_b_logo,
                "blv":        blv_name,
                "blv_avatar": comm.get("avatar", ""),
                "time":       f"{time_label} | {date_label}",
                "team_a":     team_a,
                "team_b":     team_b,
                "quality":    su["label"],
            })
            print(f"    [OK] BLV {blv_name} [{su['label']}]: {su['url'][:55]}", flush=True)

    return channels


# ══════════════════════════════════════════════════════════════
# Xuất file
# ══════════════════════════════════════════════════════════════
def write_m3u(channels):
    with open(OUT_M3U, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        f.write(f"# Source  : {SITE_URL}\n")
        f.write(f"# Updated : {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")
        f.write(f"# Total   : {len(channels)} kenh\n\n")
        for ch in channels:
            logo = ch.get("logo", "")
            f.write(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{ch["league"]}",{ch["name"]}\n')
            f.write(f'#EXTVLCOPT:http-referrer={ch["page_url"]}\n')
            f.write(f'#EXTVLCOPT:http-user-agent={UA}\n')
            f.write(f'{ch["stream_url"]}\n\n')
    print(f"  [OK] {OUT_M3U}  ({len(channels)} kenh)", flush=True)

    # Sao chép vào docs/
    docs_path = os.path.join(DOCS_DIR, f"{SITE_NAME}.m3u")
    try:
        import shutil
        shutil.copy2(OUT_M3U, docs_path)
        print(f"  [OK] {docs_path}", flush=True)
    except Exception as e:
        print(f"  [!] Copy to docs: {e}", flush=True)


def write_json(channels):
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "site":     SITE_NAME,
            "source":   SITE_URL,
            "updated":  datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "total":    len(channels),
            "channels": channels,
        }, f, ensure_ascii=False, indent=2)
    print(f"  [OK] {OUT_JSON}", flush=True)


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
def main():
    print("=" * 60, flush=True)
    print(f"  {SITE_NAME} — Scraper v2 (RSC Parser)", flush=True)
    print(f"  {datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M ICT')}", flush=True)
    print("=" * 60, flush=True)

    # Bước 1: Lấy danh sách trận
    print(f"\n[1/2] Lay danh sach tran tu {SITE_URL}...", flush=True)
    matches = fetch_match_list()
    if not matches:
        print("[!] Khong co tran nao!", flush=True)
        return []

    # Bước 2: Fetch stream cho từng trận
    print(f"\n[2/2] Fetch stream cho {len(matches)} tran...", flush=True)
    all_channels = []

    for i, match in enumerate(matches):
        blvs = ", ".join(c["name"] for c in match["commentators"])
        print(f"\n  [{i+1:02d}/{len(matches)}] "
              f"[{match['time_label']} | {match['date_label']}] "
              f"{match['team_a']['name']} vs {match['team_b']['name']} "
              f"[{match['league']}] BLV: {blvs}", flush=True)

        channels = scrape_match_streams(match)
        if channels:
            all_channels.extend(channels)
            print(f"    -> {len(channels)} kenh", flush=True)
        else:
            print(f"    -> SKIP", flush=True)

        time.sleep(DELAY)

    print(f"\n  Ket qua: {len(all_channels)} kenh (tu {len(matches)} tran)", flush=True)
    if all_channels:
        write_m3u(all_channels)
        write_json(all_channels)

    print(f"\n{'='*60}", flush=True)
    print(f"  XONG! {len(all_channels)} kenh", flush=True)
    print(f"{'='*60}", flush=True)
    return all_channels


if __name__ == "__main__":
    main()
