"""
run_all.py — Chạy tất cả scrapers rồi merge
Dùng:
  python run_all.py                  # chạy tất cả
  python run_all.py chuoichien       # chỉ chạy 1
  python run_all.py hoadao           # chỉ chạy HoaDaoTV
  python run_all.py --merge-only     # chỉ merge
"""

import sys, io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import asyncio
from datetime import datetime, timezone, timedelta

TZ_VN = timezone(timedelta(hours=7))

# Danh sách scraper — (keyword, module, func, is_async)
# THÊM MỚI: hoadaotv
SCRAPERS = [
    ("chuoichien", "scrapers.chuoichientv", "main", False),
    ("hoiquan",    "scrapers.hoiquan1",     "main", False),
    ("quechoa",    "scrapers.quechoa8",     "main", True),
    ("hoadao",     "scrapers.hoadaotv",     "main", False),  # ← MỚI
]


async def run_all(filter_kw=None):
    results = {}

    for keyword, module_path, func_name, is_async in SCRAPERS:
        if filter_kw and filter_kw.lower() not in keyword:
            continue

        print(f"\n{'#'*60}", flush=True)
        print(f"# Chay: {module_path}", flush=True)
        print(f"{'#'*60}", flush=True)

        try:
            import importlib
            mod  = importlib.import_module(module_path)
            func = getattr(mod, func_name)
            if is_async:
                channels = await func()
            else:
                channels = func()
            results[keyword] = len(channels) if channels else 0
        except Exception as e:
            print(f"[LOI] {module_path}: {e}", flush=True)
            import traceback; traceback.print_exc()
            results[keyword] = 0

    return results


async def main():
    args = sys.argv[1:]

    print("=" * 60, flush=True)
    print("  IPTV RUN ALL", flush=True)
    print(f"  {datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M ICT')}", flush=True)
    print("=" * 60, flush=True)

    if "--merge-only" not in args:
        filter_kw = next((a for a in args if not a.startswith("-")), None)
        results = await run_all(filter_kw)

        print(f"\n{'='*60}", flush=True)
        print("  TONG KET", flush=True)
        print(f"{'='*60}", flush=True)
        for site, count in results.items():
            print(f"  {site:<15}: {count} kenh", flush=True)

    print(f"\n{'='*60}", flush=True)
    print("  MERGE", flush=True)
    print(f"{'='*60}", flush=True)
    import subprocess
    result = subprocess.run(
        [sys.executable, "merge.py"],
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        print(f"[LOI] merge.py exit code {result.returncode}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
