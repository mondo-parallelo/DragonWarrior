# ╔══════════════════════════════════════════════════════════╗
# ║   config.py — CHỈ CẦN SỬA FILE NÀY DUY NHẤT            ║
# ╚══════════════════════════════════════════════════════════╝

GITHUB_USER   = "mondo-parallelo"
GITHUB_REPO   = "DragonWarrior"
GITHUB_BRANCH = "main"

# Tự động tính từ 3 dòng trên — không cần sửa
GITHUB_RAW     = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}"
BASE_THUMB_URL = f"{GITHUB_RAW}/thumbs/"

# Thư mục output
OUTPUT_ROOT = "output_m3u"
DOCS_DIR    = "docs"
THUMBS_DIR  = "thumbs"

# Bearer token ChuoiChienTV
# Khi hết hạn (API trả 401): F12 → Network → request api.chuoichientv.com → copy Authorization header
CHUOICHIEN_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJndWVzdElkIjoiZTM0Zjk3ZmQtNWMxMC00MGEzLWE1OGYtZDE3MmQwMmIxNDZjIiwidHlwZSI6Imd1ZXN0IiwiaXAiOiIxNjIuMTU5Ljk4LjIyMCIsInVzZXJBZ2VudCI6Ik1vemlsbGEvNS4wIChXaW5kb3dzIE5UIDEwLjA7IFdpbjY0OyB4NjQpIEFwcGxlV2ViS2l0LzUzNy4zNiAoS0hUTUwsIGxpa2UgR2Vja28pIENocm9tZS8xMzEuMC4wLjAgU2FmYXJpLzUzNy4zNiIsIm5hbWUiOiJCw7puIMSQ4buPIDQ1MyIsInRpbWVzdGFtcCI6MTc3MjI5MTc4NzEwNCwiaWF0IjoxNzcyMjkxNzg3LCJleHAiOjE4MDM4Mjc3ODd9"
    ".iHhwdQaDRcrjyRfCVGCbSZb6dFj-EuzJblTD1wmttV0"
)

# Ảnh nền thumbnail
BG_IMAGE_URL = "https://raw.githubusercontent.com/nghehoang007-wq/HFB321/main/HFB/Thump/nguonphat5.png"
