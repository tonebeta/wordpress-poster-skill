---
name: wordpress-poster
description: >
  Publish, manage, and interact with WordPress content via the WordPress REST API.
  Use this skill whenever the user wants to create, update, read, or delete WordPress posts,
  pages, categories, or tags — including drafting content, uploading media, or managing
  post metadata. Trigger when the user mentions WordPress, wp-json, publishing a blog post,
  updating a page, or any workflow involving a WordPress site. Also trigger when the user
  says "post this to my blog", "add a draft to WordPress", or "schedule a WordPress article".
  Always uses .env for credentials and uv for Python.
---

# WordPress Poster Skill

Automates WordPress content management via the **WordPress REST API (v2)**.
Credentials are always loaded from a `.env` file — never hardcoded.

---

## Environment Setup

Before running any script, ensure a `.env` file exists with:

```dotenv
# .env
WP_URL=https://your-site.com          # No trailing slash
WP_USERNAME=your_wp_username
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx   # Application Password (with spaces OK)
```

**How to generate an Application Password:**
1. WordPress Admin → Users → Your Profile
2. Scroll to **Application Passwords**
3. Enter a name (e.g., "Claude API") → Click **Add New Application Password**
4. Copy the generated password (spaces included are fine)

---

## Quick Start

```bash
# Initialize project with uv
uv init wp-project
cd wp-project
uv add httpx python-dotenv
```

---

## Core Script: `wp_poster.py`

Use this as the base for all WordPress operations:

```python
# wp_poster.py
import httpx
import base64
import os
from dotenv import load_dotenv

load_dotenv()

WP_URL      = os.getenv("WP_URL", "").rstrip("/")
USERNAME    = os.getenv("WP_USERNAME", "")
APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")

def _auth_headers() -> dict:
    token = base64.b64encode(f"{USERNAME}:{APP_PASSWORD}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }

def create_post(
    title: str,
    content: str,
    status: str = "draft",          # draft | publish | pending | private
    categories: list[int] | None = None,
    tags: list[int] | None = None,
    excerpt: str = "",
    slug: str = "",
) -> dict:
    """Create a new WordPress post."""
    payload: dict = {
        "title":   title,
        "content": content,
        "status":  status,
        "excerpt": excerpt,
    }
    if slug:
        payload["slug"] = slug
    if categories:
        payload["categories"] = categories
    if tags:
        payload["tags"] = tags

    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        json=payload,
        headers=_auth_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def update_post(post_id: int, **fields) -> dict:
    """Update an existing post by ID."""
    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
        json=fields,
        headers=_auth_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_post(post_id: int) -> dict:
    """Fetch a single post by ID."""
    resp = httpx.get(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
        headers=_auth_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def list_posts(per_page: int = 10, page: int = 1, status: str = "any") -> list[dict]:
    """List posts with pagination."""
    resp = httpx.get(
        f"{WP_URL}/wp-json/wp/v2/posts",
        params={"per_page": per_page, "page": page, "status": status},
        headers=_auth_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def delete_post(post_id: int, force: bool = False) -> dict:
    """Delete (trash) a post. Use force=True to permanently delete."""
    resp = httpx.delete(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
        params={"force": str(force).lower()},
        headers=_auth_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def list_categories() -> list[dict]:
    """List all categories."""
    resp = httpx.get(
        f"{WP_URL}/wp-json/wp/v2/categories",
        params={"per_page": 100},
        headers=_auth_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def create_category(name: str, slug: str = "", parent: int = 0) -> dict:
    """Create a new category."""
    payload: dict = {"name": name}
    if slug:
        payload["slug"] = slug
    if parent:
        payload["parent"] = parent
    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/categories",
        json=payload,
        headers=_auth_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def upload_media(file_path: str, title: str = "") -> dict:
    """Upload an image or file as WordPress media."""
    import mimetypes
    mime_type, _ = mimetypes.guess_type(file_path)
    filename = os.path.basename(file_path)
    token = base64.b64encode(f"{USERNAME}:{APP_PASSWORD}".encode()).decode()
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": mime_type or "application/octet-stream",
    }
    if title:
        headers["X-WP-Media-Title"] = title

    with open(file_path, "rb") as f:
        resp = httpx.post(
            f"{WP_URL}/wp-json/wp/v2/media",
            content=f.read(),
            headers=headers,
            timeout=60,
        )
    resp.raise_for_status()
    return resp.json()
```

---

## Usage Examples

### 建立草稿

```python
result = create_post(
    title="我的新文章",
    content="<p>這是文章內容，支援 HTML 格式。</p>",
    status="draft",
)
print(f"已建立草稿 ID={result['id']}，連結={result['link']}")
```

### 直接發布

```python
result = create_post(
    title="立即發布的文章",
    content="<h2>副標題</h2><p>內文...</p>",
    status="publish",
    categories=[3],   # category ID
    tags=[7, 12],     # tag IDs
)
```

### 更新文章

```python
result = update_post(42, title="新標題", status="publish")
```

### 列出最新 10 篇草稿

```python
posts = list_posts(per_page=10, status="draft")
for p in posts:
    print(p["id"], p["title"]["rendered"])
```

### 上傳圖片並設為特色圖片

```python
media = upload_media("/path/to/cover.jpg", title="封面圖")
update_post(post_id, featured_media=media["id"])
```

### 上傳圖片並自動轉換為 WebP

WebP 轉換需要 Pillow：`uv add Pillow`

```python
# 標準 lossy WebP（quality=85，推薦）
media = upload_media(
    "/path/to/photo.jpg",
    convert_webp=True,
)

# 指定品質 1–100
media = upload_media(
    "/path/to/photo.jpg",
    convert_webp=True,
    webp_quality=90,
)

# Lossless WebP（無損，適合 PNG 圖示、精確圖形）
media = upload_media(
    "/path/to/icon.png",
    convert_webp=True,
    webp_lossless=True,
)
```

上傳時會自動印出節省空間的資訊：
```
WebP 轉換完成: photo.jpg → photo.webp (320,000 → 98,000 bytes, 節省 69.4%)
```

**支援輸入格式：** JPEG、PNG、BMP、TIFF、GIF（靜態）  
**透明度：** RGBA / PNG 透明圖片自動保留 alpha 通道  
**CLI 用法：**
```bash
uv run scripts/wp_poster.py upload photo.jpg --webp
uv run scripts/wp_poster.py upload photo.jpg --webp --quality 90
uv run scripts/wp_poster.py upload icon.png  --webp --lossless
```

---

## Common Operations Reference

| 操作 | HTTP Method | Endpoint |
|------|------------|---------|
| 新增文章 | POST | `/wp-json/wp/v2/posts` |
| 更新文章 | POST | `/wp-json/wp/v2/posts/{id}` |
| 刪除文章 | DELETE | `/wp-json/wp/v2/posts/{id}` |
| 列出分類 | GET | `/wp-json/wp/v2/categories` |
| 上傳媒體 | POST | `/wp-json/wp/v2/media` |
| 新增頁面 | POST | `/wp-json/wp/v2/pages` |

---

## Error Handling Best Practices

```python
try:
    result = create_post(title="測試", content="內容", status="publish")
except httpx.HTTPStatusError as e:
    print(f"HTTP 錯誤 {e.response.status_code}: {e.response.text}")
except httpx.ConnectError:
    print("無法連線到 WordPress，請確認 WP_URL 是否正確")
```

**常見錯誤：**
- `401 Unauthorized` → 檢查 `.env` 中的 `WP_USERNAME` 與 `WP_APP_PASSWORD`
- `403 Forbidden` → 該使用者權限不足（需要 Editor 或 Administrator）
- `404 Not Found` → REST API 可能被停用，或網址設定錯誤

---

## Notes

- `content` 欄位支援 **HTML**，可直接傳入 HTML 字串
- `status` 可為：`draft`（草稿）、`publish`（發布）、`pending`（待審）、`private`（私密）
- Application Password 中的空格不影響認證，可保留或移除
- 若網站有 Cloudflare 或安全外掛，需確認 REST API 白名單已開放
