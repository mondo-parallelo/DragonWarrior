"""
merge.py — Gộp tất cả M3U trong output_m3u/ → docs/all.m3u
Chạy: python merge.py

THAY ĐỔI SO VỚI GỐC:
  • all.m3u được chia 4 group theo SITE_NAME:
      QUECHOATV / HOADAOTV / CHUOICHIENTV / HOIQUANTV
  • Nếu channel đã có group-title riêng thì giữ nguyên (sub-group),
    còn group header trong #EXTINF vẫn được đặt theo SITE_NAME để
    các IPTV player (TiviMate, IPTV Smarters…) nhóm đúng.
  • Vẫn copy file riêng từng site vào docs/ như gốc.
"""

import sys, io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os, glob, shutil, re
from datetime import datetime
from config import OUTPUT_ROOT, DOCS_DIR

os.makedirs(DOCS_DIR, exist_ok=True)
OUT_ALL = os.path.join(DOCS_DIR, "all.m3u")

# Mapping tên thư mục site → SITE_NAME hiển thị trong group-title
SITE_GROUP = {
    "QueChoaTV":   "QUECHOATV",
    "HoaDaoTV":    "HOADAOTV",
    "ChuoiChienTV":"CHUOICHIENTV",
    "HoiQuan1":    "HOIQUANTV",
}

# Thứ tự group trong file all.m3u
GROUP_ORDER = ["QUECHOATV", "HOADAOTV", "CHUOICHIENTV", "HOIQUANTV"]


# ══════════════════════════════════════════════════════════════
# Parse M3U
# ══════════════════════════════════════════════════════════════
def parse_m3u(filepath):
    """Trả về list channel dict — GIỐNG HỆT GỐC."""
    channels = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  [!] {filepath}: {e}", flush=True)
        return []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            extinf = line
            extras = []
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("#"):
                extras.append(lines[j].strip())
                j += 1
            url = lines[j].strip() if j < len(lines) else ""
            if url and not url.startswith("#"):
                channels.append({"extinf": extinf, "extras": extras, "url": url})
                i = j + 1
            else:
                i += 1
        else:
            i += 1
    return channels


def set_group_title(extinf_line, new_group):
    """
    Thay thế hoặc thêm group-title trong dòng #EXTINF.
    Giữ nguyên các attribute khác (tvg-logo, tvg-name…).
    """
    if 'group-title=' in extinf_line:
        return re.sub(r'group-title="[^"]*"', f'group-title="{new_group}"', extinf_line)
    # Chèn trước dấu phẩy cuối
    comma_idx = extinf_line.rfind(",")
    if comma_idx != -1:
        return extinf_line[:comma_idx] + f' group-title="{new_group}"' + extinf_line[comma_idx:]
    return extinf_line + f' group-title="{new_group}"'


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════
def main():
    print("=" * 60, flush=True)
    print("  MERGE", flush=True)
    print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", flush=True)
    print("=" * 60, flush=True)

    m3u_files = sorted(glob.glob(os.path.join(OUTPUT_ROOT, "*", "*.m3u")))
    if not m3u_files:
        print(f"\n[!] Khong co file M3U nao trong {OUTPUT_ROOT}/", flush=True)
        return

    # Đọc và phân nhóm theo SITE_NAME
    grouped = {g: [] for g in GROUP_ORDER}
    stats   = {}

    for filepath in m3u_files:
        # Tên thư mục site (vd: "HoaDaoTV", "QueChoaTV"…)
        folder_name = filepath.replace("\\", "/").split("/")[-2]
        site_group  = SITE_GROUP.get(folder_name, folder_name.upper())

        chs = parse_m3u(filepath)
        stats[folder_name] = len(chs)

        for ch in chs:
            # Gán group-title = SITE_NAME (override)
            ch["extinf"] = set_group_title(ch["extinf"], site_group)
            ch["site_group"] = site_group

        if site_group in grouped:
            grouped[site_group].extend(chs)
        else:
            # Site không trong danh sách → nhóm vào group cuối có slot
            print(f"  [!] {folder_name} -> group '{site_group}' chua trong GROUP_ORDER, them vao HOIQUANTV", flush=True)
            grouped["HOIQUANTV"].extend(chs)

        print(f"  {folder_name:<20}: {len(chs)} kenh  [{site_group}]", flush=True)

        # Copy file riêng vào docs/ — GỐC
        dest = os.path.join(DOCS_DIR, f"{folder_name}.m3u")
        shutil.copy2(filepath, dest)
        print(f"               -> {dest}", flush=True)

    # Ghi all.m3u — theo thứ tự GROUP_ORDER
    total = sum(len(v) for v in grouped.values())
    with open(OUT_ALL, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        f.write(f"# Updated : {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")
        f.write(f"# Total   : {total} kenh\n")
        # Stats header
        for folder, count in stats.items():
            grp = SITE_GROUP.get(folder, folder.upper())
            f.write(f"# {grp:<20}: {count} kenh\n")
        f.write("\n")

        for group_name in GROUP_ORDER:
            channels = grouped[group_name]
            if not channels:
                continue

            f.write(f"\n# ══ {group_name} ({len(channels)} kenh) ══\n\n")

            for ch in channels:
                f.write(f"{ch['extinf']}\n")
                for ex in ch["extras"]:
                    f.write(f"{ex}\n")
                f.write(f"{ch['url']}\n\n")

    print(f"\n[OK] {OUT_ALL}  ({total} kenh tong cong)", flush=True)
    print(f"\n  Phan bo theo group:", flush=True)
    for g in GROUP_ORDER:
        print(f"    {g:<20}: {len(grouped[g])} kenh", flush=True)


if __name__ == "__main__":
    main()
