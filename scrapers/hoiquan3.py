"""
scrapers/hoiquan3.py
Chạy độc lập: python scrapers/hoiquan3.py

CÁCH HOẠT ĐỘNG:
  1. Fetch API fixtures/unfinished từ sv.hoiquantv.xyz
  2. Parse danh sách trận đấu và stream từ fixtureCommentators
  3. Xuất file .m3u và .json

OUTPUT M3U FORMAT:
  [12:00 | 09.05] Mito Hollyhock - Urawa [J1 League] | BLV: PHAN MÃ [FHD]
"""

import sys
import os
import json
import re
import time
from datetime import datetime, timezone, timedelta

# Cấu hình encoding cho Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import BASE_THUMB_URL, OUTPUT_ROOT, THUMBS_DIR, DOCS_DIR

# ──────────────────────────────────────────────────────────────
SITE_NAME = "HoiQuan3"
SITE_URL  = "https://sv2.hoiquan3.live/"
API_BASE  = "https://sv.hoiquantv.xyz/api/v1/external"
API_FIXTURES = f"{API_BASE}/fixtures/unfinished"

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
    "Accept":          "application/json, */*",
    "Accept-Language": "vi-VN,vi;q=0.9",
    "Referer":         SITE_URL,
    "Origin":          SITE_URL.rstrip("/"),
}

# ══════════════════════════════════════════════════════════════
# HTTP Helper
# ══════════════════════════════════════════════════════════════
def get_json(url):
    print(f"  [API] {url}", flush=True)
    try:
        from curl_cffi import requests as cr
        r = cr.get(url, headers=HEADERS, impersonate="chrome110", timeout=20)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"        curl_cffi error: {e}", flush=True)
    
    try:
        import requests
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"        requests error: {e}", flush=True)
    return None

# ══════════════════════════════════════════════════════════════
# BƯỚC 1: Parse dữ liệu từ API
# ══════════════════════════════════════════════════════════════
def fetch_matches():
    data = get_json(API_FIXTURES)
    if not data:
        return []
    
    items = data if isinstance(data, list) else data.get('data', data.get('fixtures', []))
    print(f"  Tim thay {len(items)} tran dau", flush=True)
    
    channels = []
    for item in items:
        # Metadata
        league = item.get('league', {}).get('name', 'Hội Quán')
        home_team = item.get('homeTeam', {}).get('name', 'Team A')
        away_team = item.get('awayTeam', {}).get('name', 'Team B')
        home_logo = item.get('homeTeam', {}).get('logoUrl', '')
        away_logo = item.get('awayTeam', {}).get('logoUrl', '')
        
        # Time
        start_time_raw = item.get('startTime', '')
        time_label = ""
        date_label = ""
        if start_time_raw:
            try:
                dt_utc = datetime.fromisoformat(start_time_raw.replace('Z', '+00:00'))
                dt_vn = dt_utc.astimezone(TZ_VN)
                time_label = dt_vn.strftime("%H:%M")
                date_label = dt_vn.strftime("%d.%m")
            except:
                pass
        
        # Commentators & Streams
        commentators = item.get('fixtureCommentators', [])
        for comm_wrapper in commentators:
            comm = comm_wrapper.get('commentator', {})
            blv_name = comm.get('nickname', comm.get('name', 'BLV'))
            streams = comm.get('streams', [])
            
            # Nếu không có stream trong comm, bỏ qua (hoặc xử lý fallback nếu cần)
            if not streams:
                continue
                
            # Lọc và khử trùng quality
            seen_urls = set()
            for s in streams:
                quality = s.get('name', 'HD').upper()
                url = s.get('sourceUrl', '').strip()
                
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                
                # Format tên kênh
                # [12:00 | 09.05] Mito Hollyhock - Urawa [J1 League] | BLV: PHAN MÃ [FHD]
                ch_name = f"[{time_label} | {date_label}] {home_team} - {away_team} [{league}] | BLV: {blv_name} [{quality}]"
                
                channels.append({
                    "name": ch_name,
                    "league": league,
                    "stream_url": url,
                    "logo": home_logo,
                    "home": home_team,
                    "away": away_team,
                    "time": f"{time_label} | {date_label}",
                    "blv": blv_name,
                    "quality": quality,
                    "page_url": SITE_URL # API không trả về page_url cụ thể dễ dàng
                })
                
    return channels

# ══════════════════════════════════════════════════════════════
# BƯỚC 2: Xuất file
# ══════════════════════════════════════════════════════════════
def write_m3u(channels):
    with open(OUT_M3U, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        f.write(f"# Source  : {SITE_URL}\n")
        f.write(f"# Updated : {datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M ICT')}\n")
        f.write(f"# Total   : {len(channels)} kenh\n\n")
        
        for ch in channels:
            f.write(f'#EXTINF:-1 tvg-logo="{ch["logo"]}" group-title="{ch["league"]}",{ch["name"]}\n')
            f.write(f'#EXTVLCOPT:http-referrer={SITE_URL}\n')
            f.write(f'#EXTVLCOPT:http-user-agent={UA}\n')
            f.write(f'{ch["stream_url"]}\n\n')
            
    print(f"  [OK] {OUT_M3U} ({len(channels)} kenh)", flush=True)
    
    # Copy to docs
    docs_path = os.path.join(DOCS_DIR, f"{SITE_NAME}.m3u")
    try:
        import shutil
        shutil.copy2(OUT_M3U, docs_path)
        print(f"  [OK] {docs_path}", flush=True)
    except Exception as e:
        print(f"  [!] Copy to docs failed: {e}", flush=True)

def write_json(channels):
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "site": SITE_NAME,
            "source": SITE_URL,
            "updated": datetime.now(TZ_VN).strftime("%Y-%m-%d %H:%M ICT"),
            "total": len(channels),
            "channels": channels
        }, f, ensure_ascii=False, indent=2)
    print(f"  [OK] {OUT_JSON}", flush=True)

# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
def main():
    print("=" * 60, flush=True)
    print(f"  {SITE_NAME} Scraper", flush=True)
    print(f"  {datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M ICT')}", flush=True)
    print("=" * 60, flush=True)
    
    channels = fetch_matches()
    
    if channels:
        write_m3u(channels)
        write_json(channels)
    else:
        print("  [!] Khong tim thay kenh nao.", flush=True)
        
    print(f"\n{'='*60}", flush=True)
    print(f"  XONG! {len(channels)} kenh", flush=True)
    print(f"{'='*60}", flush=True)

if __name__ == "__main__":
    main()
