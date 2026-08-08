"""
scrapers/hoadaotv.py
Chạy độc lập: python scrapers/hoadaotv.py

CẤU TRÚC HTML TRANG CHỦ (xác nhận thực tế):
  Mỗi card trong "Các Trận Hot" có cấu trúc:

    <div card>
      ...
      Wellington Phoenix       ← team name text
      09:00 |  14/03           ← text node RIÊNG (giờ + ngày), ngay trên link
      [Đặt Cược] [Xem → /slug] ← 2 link cuối card
    </div>

  → Với mỗi <a href="/slug">, lấy text node ngay TRƯỚC nó trong cùng card
    = giờ thi đấu chính xác của trận đó.

TRANG DETAIL: parse <a href="?mode=xxx"> để lấy tất cả mode có sẵn,
  fetch từng mode → stream URL riêng.
"""

import sys
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__file__), '..'))

import os, json, re, time
from datetime import datetime, timezone, timedelta
from config import OUTPUT_ROOT, THUMBS_DIR, DOCS_DIR

# ──────────────────────────────────────────────────────────────
SITE_NAME = "HoaDaoTV"
SITE_URL  = "https://hoadaotv.info"

OUTPUT_DIR = os.path.join(OUTPUT_ROOT, SITE_NAME)
OUT_M3U    = os.path.join(OUTPUT_DIR, f"{SITE_NAME}.m3u")
OUT_JSON   = os.path.join(OUTPUT_DIR, f"{SITE_NAME}.json")
TZ_VN      = timezone(timedelta(hours=7))
DELAY      = 0.4

MODE_LABEL = {
    "sd":       "SD",
    "hd":       "HD",
    "fullhd":   "FullHD",
    "flv":      "SD Nhanh",
    "flv2":     "HD Nhanh",
    "ndsd":     "Nhà đài SD",
    "ndhd":     "Nhà đài HD",
    "emulator": "Mô Phỏng",
}

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
    "Origin":          SITE_URL,
}

STREAM_PATTERNS = [
    re.compile(r'(https?://[^\s\'"<>{}\\,\]]+?\.m3u8[^\s\'"<>{}\\,\]]*)'),
    re.compile(r'"(?:url|src|source|hls|stream|file|link)"\s*:\s*"(https?://[^\s"]+)"'),
    re.compile(r"(?:url|src|hls|file)\s*[=:]\s*['\"]?(https?://[^\s'\"]+?\.m3u8[^\s'\"]*)"),
    re.compile(r'<source[^>]+src=["\']([^"\']+\.m3u8[^"\']*)["\']', re.I),
]

# Pattern giờ trên trang chủ: "09:00 |  14/03" hoặc "09:00- 14/03"
_TIME_RE = re.compile(r'(\d{1,2}:\d{2})\s*[\|\-]\s*(\d{1,2}/\d{1,2})')


# ══════════════════════════════════════════════════════════════
# HTTP
# ══════════════════════════════════════════════════════════════
def fetch_html(url, params=None, timeout=15):
    display = url + (f"?mode={params['mode']}" if params and 'mode' in params else "")
    print(f"  [GET] {display}", flush=True)
    try:
        from curl_cffi import requests as cr
        r = cr.get(url, params=params, headers=HEADERS, impersonate="chrome110", timeout=timeout)
        print(f"        HTTP {r.status_code} | {len(r.text)} bytes", flush=True)
        if r.status_code == 200:
            return r.text
    except Exception as e:
        print(f"        curl_cffi: {e}", flush=True)
    try:
        import requests as rq
        r = rq.get(url, params=params, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.text
    except Exception as e:
        print(f"        requests: {e}", flush=True)
    return ""


def extract_stream_url(html):
    for pat in STREAM_PATTERNS:
        m = pat.search(html)
        if m:
            url = m.group(1).strip().strip("'\"")
            if any(x in url for x in ["facebook","google","ads",".css",".js","jquery"]):
                continue
            if url.startswith("http"):
                return url
    return None


# ══════════════════════════════════════════════════════════════
# BƯỚC 1: Parse trang chủ → {url: match_info}
# ══════════════════════════════════════════════════════════════
def fetch_match_list():
    """
    Parse trang chủ HoaDaoTV.
    Với mỗi card trận, lấy:
      - URL trang detail
      - Tên đội (từ img alt)
      - Giờ thi đấu: text node ngay trước link [Xem] trong card
      - League, BLV, logo
    Trả về list[dict].
    """
    from bs4 import BeautifulSoup, NavigableString

    html = fetch_html(SITE_URL)
    if not html:
        print("  [!] Khong lay duoc trang chu!", flush=True)
        return []

    soup = BeautifulSoup(html, "html.parser")
    matches = []
    seen_urls = set()

    # Tìm tất cả link [Xem] / [Xem Ngay] trỏ đến trang trận đấu
    for a_xem in soup.find_all("a", href=True):
        href = a_xem.get("href", "").strip()

        # Lọc chỉ lấy link trang trận đấu
        if not href or "javascript:" in href:
            continue
        if any(s in href for s in [
            "bang-xep-hang", "ket-qua", "binh-luan", "tin-tuc",
            "xemlai", "fb88", "Account", "nhacai", "register",
            "debet", "sky88", "pub88", "telegram", "facebook",
        ]):
            continue
        if "vs" not in href and not re.search(r"-\d{6,}$", href):
            continue

        # Chuẩn hóa URL
        if not href.startswith("http"):
            href = SITE_URL.rstrip("/") + "/" + href.lstrip("/")
        href = href.split("?")[0]   # bỏ ?mode=xxx nếu có

        if href in seen_urls:
            continue
        seen_urls.add(href)

        # ── Tìm card cha chứa link này ────────────────────────
        card = a_xem.find_parent(["div", "li", "article"])
        if not card:
            continue

        # ── Lấy giờ ───────────────────────────────────────────
        # Giờ là text node trong card, dạng "09:00 |  14/03"
        # Nằm ngay trước <a>[Đặt Cược]</a> hoặc <a>[Xem]</a>
        time_str = ""
        date_str = ""

        # Lấy tất cả text nodes trong card, tìm cái khớp pattern giờ
        for node in card.descendants:
            if not isinstance(node, NavigableString):
                continue
            t = node.strip()
            if not t:
                continue
            m = _TIME_RE.search(t)
            if m:
                time_str = m.group(1)
                date_str = m.group(2)
                break   # lấy cái đầu tiên = giờ của trận này

        # ── Lấy tên đội ───────────────────────────────────────
        title = ""
        team_imgs = card.select("img[alt]")
        team_names = [
            img.get("alt", "").strip() for img in team_imgs
            if img.get("alt", "").strip() not in ("", "corner", "live", "LIVE")
            and not img.get("alt","").startswith("BLV")
            and "icon" not in img.get("src","").lower()
        ]
        if len(team_names) >= 2:
            title = f"{team_names[0]} vs {team_names[-1]}"

        # ── Lấy league ────────────────────────────────────────
        league = ""
        for el in card.select(".league, .tournament, [class*='league']"):
            t = el.get_text(strip=True)
            if t:
                league = t; break
        # Fallback: text ngắn trước team name
        if not league:
            texts = [n.strip() for n in card.strings if n.strip()]
            for t in texts:
                if len(t) > 3 and len(t) < 50 and t not in team_names:
                    if not _TIME_RE.search(t) and "/" not in t:
                        league = t; break

        # ── BLV ───────────────────────────────────────────────
        blv = ""
        blv_img = card.find("img", alt=re.compile(r"BLV", re.I))
        if blv_img:
            blv = blv_img.get("alt", "").strip()

        # ── Logo đội ──────────────────────────────────────────
        logo = ""
        logo_el = card.select_one("img[src*='rapid-api'], img[src*='flashscore']")
        if logo_el:
            logo = logo_el.get("src", "")

        if not title:
            slug  = href.rstrip("/").split("/")[-1]
            slug  = re.sub(r"-\d+$", "", slug)
            title = slug.replace("-", " ").title()

        matches.append({
            "title":    title,
            "url":      href,
            "league":   league or "HoaDaoTV",
            "logo":     logo,
            "blv":      blv,
            "time_str": time_str,   # "09:00"
            "date_str": date_str,   # "14/03"
        })

    print(f"  {len(matches)} tran tim duoc", flush=True)

    # Debug: in ra giờ của vài trận đầu để kiểm tra
    for m in matches[:5]:
        print(f"    {m['time_str']} {m['date_str']}  {m['title'][:40]}", flush=True)

    return matches


# ══════════════════════════════════════════════════════════════
# BƯỚC 2: Fetch trang detail → parse modes → fetch từng mode
# ══════════════════════════════════════════════════════════════
def parse_modes_from_detail(html, page_url):
    """
    Parse tất cả <a href="?mode=xxx"> trong trang detail.
    Trả về [(label, mode_val), ...]
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    modes = []
    seen  = set()
    for a in soup.select("a[href*='?mode=']"):
        href = a.get("href", "")
        m = re.search(r'\?mode=(\w+)', href)
        if not m:
            continue
        mode_val = m.group(1)
        if mode_val in seen or mode_val == "emulator":
            continue
        seen.add(mode_val)
        label = MODE_LABEL.get(mode_val, mode_val.upper())
        modes.append((label, mode_val))
    return modes


def scrape_match_streams(match):
    """
    Fetch trang detail → lấy modes → fetch từng mode → stream URL.
    """
    base_url = match["url"]
    title    = match["title"]
    league   = match.get("league", "HoaDaoTV")
    logo     = match.get("logo", "")
    blv      = match.get("blv", "")
    time_str = match.get("time_str", "")
    date_str = match.get("date_str", "")

    # Build dt_label: "[14/03 09:00]"
    if date_str and time_str:
        dt_label = f"[{date_str} {time_str}]"
    elif time_str:
        dt_label = f"[{time_str}]"
    else:
        dt_label = ""

    # Fetch trang detail (không params) để lấy danh sách modes
    html_base = fetch_html(base_url, timeout=12)
    if not html_base:
        return []

    modes = parse_modes_from_detail(html_base, base_url)
    if not modes:
        print(f"    [!] Khong tim thay mode nao", flush=True)
        return []

    print(f"    [MODES] {[l for l,v in modes]}", flush=True)

    channels = []
    seen_urls = set()

    for label, mode_val in modes:
        html_mode = fetch_html(base_url, params={"mode": mode_val}, timeout=12)
        if not html_mode:
            continue

        stream_url = extract_stream_url(html_mode)
        if not stream_url:
            print(f"    [!] {label}: no stream", flush=True)
            continue

        seen_urls.add(stream_url)

        # Tên kênh: "[14/03 09:00] [BLV TÁO] Wellington vs Perth [HD]"
        parts = []
        if dt_label:
            parts.append(dt_label)
        if blv:
            parts.append(f"[{blv}]")
        parts.append(title)
        parts.append(f"[{label}]")
        ch_name = " ".join(parts)

        channels.append({
            "name":       ch_name,
            "league":     league,
            "stream_url": stream_url,
            "streams":    [stream_url],
            "page_url":   base_url,
            "logo":       logo,
        })
        print(f"    [OK] {label}: {stream_url[:55]}", flush=True)
        time.sleep(DELAY)

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
            f.write(f'#EXTINF:-1 tvg-logo="{ch["logo"]}" group-title="{ch["league"]}",{ch["name"]}\n')
            f.write(f'#EXTVLCOPT:http-referrer={SITE_URL}/\n')
            f.write(f'#EXTVLCOPT:http-user-agent={UA}\n')
            f.write(f'{ch["stream_url"]}\n\n')
    print(f"  [OK] {OUT_M3U}  ({len(channels)} kenh)", flush=True)


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
    print(f"  {SITE_NAME}", flush=True)
    print(f"  {datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M ICT')}", flush=True)
    print("=" * 60, flush=True)

    print(f"\n[1/2] Lay danh sach tran + gio tu {SITE_URL}...", flush=True)
    matches = fetch_match_list()
    if not matches:
        print("[LOI] Khong lay duoc danh sach tran!", flush=True)
        return []

    print(f"\n[2/2] Fetch stream cho {len(matches)} tran...", flush=True)
    all_channels = []

    for i, match in enumerate(matches):
        t = f"  {match['time_str']} {match['date_str']}" if match.get("time_str") else ""
        print(f"\n  [{i+1:03d}/{len(matches)}] {match['title'][:45]}{t}", flush=True)

        streams = scrape_match_streams(match)
        if not streams:
            print(f"    -> SKIP", flush=True)
        else:
            print(f"    -> {len(streams)} kenh", flush=True)
            all_channels.extend(streams)
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
