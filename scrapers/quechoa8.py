"""
scrapers/quechoa8.py
Chạy độc lập: python scrapers/quechoa8.py
"""

import sys
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__file__), '..'))

import os, json, re, asyncio
from datetime import datetime, timezone, timedelta
from config import BASE_THUMB_URL, OUTPUT_ROOT, THUMBS_DIR, DOCS_DIR

# ──────────────────────────────────────────────────────────────
SITE_NAME  = "QueChoaTV"
SITE_URL   = "https://quechoa8.live"
HOME_PAGES = [
    "https://quechoa8.live/",
    "https://quechoa8.live/truc-tiep/",
]
PLAYWRIGHT_TIMEOUT = 15

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


def find_streams_in_html(html):
    streams = []
    for pat in [
        r'(https?://[^\s\'"<>{}\\,\]]+?\.m3u8[^\s\'"<>{}\\,\]]*)',
        r'(https?://[^\s\'"<>{}\\,\]]+?\.flv[^\s\'"<>{}\\,\]]*)',
        r'(rtmp://[^\s\'"<>{}\\,\]]+)',
        r'"(?:url|src|source|hls|stream|file)"\s*:\s*"(https?://[^\s"]+)"',
        r"(?:url|src|hls|file)\s*[=:]\s*['\"]?(https?://[^\s'\"]+?\.m3u8[^\s'\"]*)",
    ]:
        streams.extend(re.findall(pat, html, re.IGNORECASE))

    iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)

    seen, unique = set(), []
    for s in streams:
        s = s.strip().strip("'\"")
        if s and s.startswith("http") and s not in seen:
            seen.add(s); unique.append(s)
    return unique, iframes


def get_match_links_from_html():
    links = set()
    for url in HOME_PAGES:
        html = fetch_html(url)
        if not html:
            continue
        found = re.findall(
            r'href=["\']([^"\']*?/truc-tiep/[^"\']+)["\']',
            html, re.IGNORECASE
        )
        for href in found:
            full = href if href.startswith("http") else SITE_URL + href
            full = full.split("?")[0].split("#")[0].rstrip("/")
            if full.count("/") >= 4:
                links.add(full)
    return sorted(links)


async def find_links_playwright():
    links = set()
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await (await browser.new_context(user_agent=UA)).new_page()
            for url in HOME_PAGES:
                print(f"  [PW] {url}", flush=True)
                try:
                    await asyncio.wait_for(
                        page.goto(url, wait_until="domcontentloaded"), timeout=20
                    )
                    await asyncio.sleep(3)
                    hrefs = await page.eval_on_selector_all(
                        "a[href*='/truc-tiep/']",
                        "els => els.map(e => e.href)"
                    )
                    for h in hrefs:
                        if h.count("/") >= 4:
                            links.add(h.split("?")[0])
                    print(f"       {len(hrefs)} link", flush=True)
                except Exception as e:
                    print(f"  [!] {e}", flush=True)
            await browser.close()
    except Exception as e:
        print(f"  [PW] Loi: {e}", flush=True)
    return sorted(links)


async def find_streams_playwright(url):
    print(f"    [PW] Mo (timeout {PLAYWRIGHT_TIMEOUT}s)...", flush=True)
    captured = []
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx  = await browser.new_context(user_agent=UA, locale="vi-VN")
            page = await ctx.new_page()

            async def on_req(req):
                u = req.url
                if any(x in u for x in [".m3u8", ".flv", "/hls/", "/live/"]):
                    if u not in captured:
                        captured.append(u)
                        print(f"    [PW🔴] {u[:80]}", flush=True)

            page.on("request", on_req)
            try:
                await asyncio.wait_for(
                    page.goto(url, wait_until="domcontentloaded"),
                    timeout=PLAYWRIGHT_TIMEOUT
                )
            except Exception:
                pass
            await asyncio.sleep(8)
            try:
                content = await page.content()
                s, _ = find_streams_in_html(content)
                for x in s:
                    if x not in captured: captured.append(x)
            except Exception:
                pass
            await browser.close()
    except Exception as e:
        print(f"    [PW] Loi: {e}", flush=True)
    return captured


def parse_slug(url):
    slug = url.rstrip("/").split("/")[-1]
    dm = re.search(r'(\d{2}-\d{2}-\d{4})$', slug)
    date_str = dm.group(1) if dm else ""
    base = slug[:dm.start()].rstrip("-") if dm else slug
    lm = re.search(r'-([A-Z]{2,8})-?$', base)
    league = lm.group(1) if lm else "Que Choa"
    base = base[:lm.start()] if lm else base
    name = base.replace("-", " ").title()
    label = f"[{date_str}] {name}" if date_str else name
    return {"name": label, "league": league, "slug": slug}


def write_m3u(channels):
    with open(OUT_M3U, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        f.write(f"# Source  : {SITE_URL}\n")
        f.write(f"# Updated : {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")
        f.write(f"# Total   : {len(channels)} kenh\n\n")
        for ch in channels:
            f.write(f'#EXTINF:-1 tvg-logo="" group-title="{ch["league"]}",{ch["name"]}\n')
            f.write(f'#EXTVLCOPT:http-referrer={ch["page_url"]}\n')
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
async def main():
    print("=" * 60, flush=True)
    print(f"  {SITE_NAME}", flush=True)
    print(f"  {datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M ICT')}", flush=True)
    print("=" * 60, flush=True)

    # 1. Tìm link
    print("\n[1/2] Tim link /truc-tiep/...", flush=True)
    match_links = get_match_links_from_html()

    if not match_links:
        print("  HTML khong co link, thu Playwright...", flush=True)
        match_links = await find_links_playwright()

    if not match_links:
        print("  [!] Khong co link nao!", flush=True)
        return []

    print(f"  {len(match_links)} link:", flush=True)
    for l in match_links:
        print(f"    {l}", flush=True)

    # 2. Scrape từng trận
    print(f"\n[2/2] Scrape {len(match_links)} tran...", flush=True)
    channels = []

    for i, url in enumerate(match_links):
        info = parse_slug(url)
        print(f"\n  [{i+1:02d}/{len(match_links)}] {info['name']}", flush=True)

        # Tầng 1: HTML
        html = fetch_html(url, timeout=10)
        streams, iframes = find_streams_in_html(html) if html else ([], [])

        # Tầng 2: iframe
        if not streams and iframes:
            print(f"    {len(iframes)} iframe tim thay, thu fetch...", flush=True)
            for src in iframes[:3]:
                if not src.startswith("http"):
                    continue
                print(f"    [iframe] {src[:70]}", flush=True)
                ifr = fetch_html(src, timeout=8)
                if ifr:
                    s, _ = find_streams_in_html(ifr)
                    if s:
                        streams.extend(s)
                        print(f"    -> {len(s)} stream tu iframe!", flush=True)
                        break

        # Tầng 3: Playwright
        if not streams:
            streams = await find_streams_playwright(url)

        if not streams:
            print(f"    -> SKIP", flush=True)
            continue

        # Dedup
        seen, unique = set(), []
        for s in streams:
            if s not in seen: seen.add(s); unique.append(s)

        print(f"    -> {len(unique)} stream: {unique[0][:60]}", flush=True)

        channels.append({
            "name":       info["name"],
            "league":     info["league"],
            "stream_url": unique[0],
            "streams":    unique,
            "page_url":   url,
        })

    print(f"\n  Ket qua: {len(channels)} kenh", flush=True)
    if channels:
        write_m3u(channels)
        write_json(channels)

    return channels


if __name__ == "__main__":
    asyncio.run(main())
