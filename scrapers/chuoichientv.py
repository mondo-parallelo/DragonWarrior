"""
scrapers/chuoichientv.py
Chạy độc lập: python scrapers/chuoichientv.py
"""

import sys
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__file__), '..'))

import os, json, re, time
from datetime import datetime, timezone, timedelta
from config import (
    CHUOICHIEN_TOKEN, BASE_THUMB_URL, BG_IMAGE_URL,
    OUTPUT_ROOT, THUMBS_DIR, DOCS_DIR
)

# ──────────────────────────────────────────────────────────────
SITE_NAME = "ChuoiChienTV"
SITE_URL  = "https://live18.chuoichientv.com"
API_URL   = "https://api.chuoichientv.com/v1/matches?page=1&limit=100&sport=&type=blv"

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
    "User-Agent":    UA,
    "Accept":        "application/json, */*",
    "Authorization": f"Bearer {CHUOICHIEN_TOKEN}",
    "Origin":        SITE_URL,
    "Referer":       SITE_URL + "/",
}

TEAM_SHORT = {
    "Manchester United":"Man Utd","Manchester City":"Man City",
    "Barcelona":"Barca","Real Madrid":"Real","Atletico Madrid":"Atletico",
    "Inter Milan":"Inter","AC Milan":"Milan","Juventus":"Juve",
    "Bayern Munich":"Bayern","Borussia Dortmund":"Dortmund",
    "Paris Saint-Germain":"PSG","Tottenham Hotspur":"Spurs",
}
def shorten(name):
    for f, s in TEAM_SHORT.items():
        if f.lower() in str(name).lower(): return s
    return str(name)[:13]


# ══════════════════════════════════════════════════════════════
def fetch_matches():
    print(f"  [API] {API_URL}", flush=True)
    try:
        from curl_cffi import requests as cr
        r = cr.get(API_URL, headers=HEADERS, impersonate="chrome110", timeout=20)
    except ImportError:
        import requests
        r = requests.get(API_URL, headers=HEADERS, timeout=20)

    print(f"        HTTP {r.status_code}", flush=True)
    if r.status_code == 401:
        print("  [401] Token het han! Cap nhat CHUOICHIEN_TOKEN trong config.py", flush=True)
        return []
    if r.status_code == 200:
        return r.json().get("matches", [])
    return []


def parse_match(match):
    teams    = match.get("teams", {})
    home     = teams.get("home", {})
    away     = teams.get("away", {})
    team1    = home.get("name", "Home")
    team2    = away.get("name", "Away")
    logo     = home.get("logo", "")
    league   = (match.get("tournament") or {}).get("name", "Chuoi Chien TV")

    # Giờ thi đấu
    raw_t = match.get("matchTime", "")
    time_str = "00h00"
    if raw_t:
        try:
            from dateutil import parser as dp
            dt = dp.parse(raw_t).astimezone(TZ_VN)
            time_str = dt.strftime("%Hh%M")
        except Exception:
            pass

    # Stream URLs từ blvs
    streams = []
    for blv in match.get("blvs", []):
        for s in blv.get("streams", []):
            u = s.get("url", "")
            if u:
                streams.append(u)

    if not streams:
        return None

    return {
        "name":       f"[{time_str}] {team1} vs {team2}",
        "group":      league,
        "logo":       logo,
        "stream_url": streams[0],
        "streams":    streams,
        "page_url":   SITE_URL + "/",
    }


def write_m3u(channels):
    with open(OUT_M3U, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        f.write(f"# Source  : {SITE_URL}\n")
        f.write(f"# Updated : {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")
        f.write(f"# Total   : {len(channels)} kenh\n\n")
        for ch in channels:
            f.write(f'#EXTINF:-1 tvg-logo="{ch["logo"]}" group-title="{ch["group"]}",{ch["name"]}\n')
            f.write(f'#EXTVLCOPT:http-referrer={SITE_URL}/\n')
            f.write(f'#EXTVLCOPT:http-user-agent={UA}\n')
            f.write(f'{ch["stream_url"]}\n\n')
    print(f"  [OK] {OUT_M3U}  ({len(channels)} kenh)", flush=True)


def write_json(channels):
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "site": SITE_NAME, "source": SITE_URL,
            "updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "total": len(channels), "channels": channels
        }, f, ensure_ascii=False, indent=2)
    print(f"  [OK] {OUT_JSON}", flush=True)


# ══════════════════════════════════════════════════════════════
def main():
    print("=" * 60, flush=True)
    print(f"  {SITE_NAME}", flush=True)
    print(f"  {datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M ICT')}", flush=True)
    print("=" * 60, flush=True)

    matches = fetch_matches()
    print(f"  {len(matches)} tran tu API", flush=True)

    channels = []
    for i, match in enumerate(matches):
        ch = parse_match(match)
        if ch:
            channels.append(ch)
            print(f"  [{i+1:03d}] {ch['name'][:55]} -> OK", flush=True)
        else:
            print(f"  [{i+1:03d}] SKIP", flush=True)
        time.sleep(0.2)

    print(f"\n  Ket qua: {len(channels)} kenh", flush=True)
    if channels:
        write_m3u(channels)
        write_json(channels)

    return channels


if __name__ == "__main__":
    main()
