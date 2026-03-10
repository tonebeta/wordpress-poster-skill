---
name: wordpress-poster
description: >
  Publish, manage, and interact with WordPress content via the WordPress REST API.
  Use this skill whenever the user wants to create, update, read, or delete WordPress
  posts, pages, categories, or tags — including drafting content, uploading media,
  batch importing from JSON/CSV, or using Claude AI to auto-generate and publish posts.
  Trigger when the user mentions WordPress, publishing a blog post, updating a page,
  batch importing articles, scheduling posts, uploading images to WordPress, or
  auto-generating blog content with AI. Also trigger for "post this to my blog",
  "add a draft to WordPress", "bulk import articles", or "write and publish a post".
  Always uses .env for credentials and uv for Python.
---

# WordPress Poster Skill

Automates WordPress content management via the **WordPress REST API (v2)**.  
Credentials are always loaded from a `.env` file — never hardcoded.

---

## Scripts Overview

| 腳本 | 功能 |
|------|------|
| `scripts/wp_poster.py` | Posts CRUD、媒體上傳（含 WebP 轉換）、Categories |
| `scripts/wp_pages.py`  | Pages 完整 CRUD、層級樹狀結構 |
| `scripts/wp_batch.py`  | 批量匯入文章（JSON / CSV）、乾跑模式 |
| `scripts/wp_ai_writer.py` | Claude AI 自動生成文章並發布至 WordPress |

---

## Environment Setup

```dotenv
# .env
WP_URL=https://your-site.com
WP_USERNAME=your_wp_username
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx

# Claude API（wp_ai_writer.py 需要）
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx

# AI 寫文預設值（選填）
WP_AI_DEFAULT_CATEGORY=1
WP_AI_DEFAULT_STATUS=draft
```

**Application Password 取得方式：**  
WordPress Admin → Users → Profile → Application Passwords → Add New

---

## Quick Start

```bash
uv init my-wp-project && cd my-wp-project
uv add httpx python-dotenv          # 基本功能
uv add Pillow                       # WebP 轉換（選填）
uv add anthropic                    # AI 寫文（選填）
```

---

## 1. Posts 管理（wp_poster.py）

### 建立文章

```python
from scripts.wp_poster import create_post, update_post, list_posts

# 草稿
result = create_post(
    title="我的新文章",
    content="<h2>副標</h2><p>內文...</p>",
    status="draft",
    categories=[3],
    tags=[7, 12],
)
print(f"ID={result['id']}  連結={result['link']}")
```

### 更新 / 發布

```python
update_post(42, title="新標題", status="publish")
```

### 媒體上傳（含 WebP）

```python
from scripts.wp_poster import upload_media

# 直接上傳
media = upload_media("/path/to/photo.jpg")

# 自動轉 WebP（需 Pillow）
media = upload_media("/path/to/photo.png", convert_webp=True, webp_quality=85)
media = upload_media("/path/to/icon.png",  convert_webp=True, webp_lossless=True)
```

**CLI：**
```bash
uv run scripts/wp_poster.py list
uv run scripts/wp_poster.py create "標題"
uv run scripts/wp_poster.py upload photo.jpg --webp --quality 90
```

---

## 2. Pages 管理（wp_pages.py）

### CRUD

```python
from scripts.wp_pages import create_page, update_page, list_pages, page_tree

# 建立頁面（頂層）
page = create_page(title="關於我們", content="<p>...</p>", status="publish")

# 建立子頁面
sub = create_page(title="團隊介紹", content="<p>...</p>", parent=page["id"])

# 更新頁面順序
update_page(page["id"], menu_order=2)

# 取得所有頁面（樹狀）
tree = page_tree()
```

**CLI：**
```bash
uv run scripts/wp_pages.py list
uv run scripts/wp_pages.py tree                         # 顯示層級結構
uv run scripts/wp_pages.py create "關於我們" "<p>內文</p>"
uv run scripts/wp_pages.py update 12 --title "新標題" --status publish
uv run scripts/wp_pages.py delete 12                   # 移至垃圾桶
uv run scripts/wp_pages.py delete 12 --force           # 永久刪除
```

---

## 3. 批量發文（wp_batch.py）

### 準備匯入檔案

**JSON 格式（posts.json）：**
```json
[
  {
    "title": "文章一",
    "content": "<p>HTML 內文</p>",
    "status": "draft",
    "excerpt": "摘要",
    "slug": "article-one",
    "categories": [1],
    "tags": [2, 3],
    "image_path": "/path/to/cover.jpg"
  }
]
```

**CSV 格式（posts.csv）：**
```
title,content,status,categories,tags,image_path
文章一,<p>內文</p>,draft,"1,2","3,4",/path/cover.jpg
```

### 執行匯入

```python
from scripts.wp_batch import batch_import

summary = batch_import(
    file_path="posts.json",
    default_status="draft",
    dry_run=False,       # True = 只預覽不發文
    convert_webp=True,   # 自動轉 WebP
    delay=0.5,           # 每篇間隔秒數
)
```

**CLI：**
```bash
# 乾跑（先確認資料無誤）
uv run scripts/wp_batch.py import posts.json --dry-run

# 正式匯入
uv run scripts/wp_batch.py import posts.json
uv run scripts/wp_batch.py import posts.csv --status publish --webp

# 產生範本
uv run scripts/wp_batch.py template --format json > posts_template.json
uv run scripts/wp_batch.py template --format csv  > posts_template.csv
```

匯入完成後自動產生 `posts_import_log.json` 記錄每篇結果。

---

## 4. AI 自動生成文章（wp_ai_writer.py）

需要 `.env` 中設定 `ANTHROPIC_API_KEY`。

### 單篇生成

```python
from scripts.wp_ai_writer import write_post

result = write_post(
    topic="CAR-T 細胞療法的最新進展",
    language="zh-TW",       # zh-TW | zh-CN | en | ja
    word_count=800,
    tone="professional",    # professional | casual | educational
    status="draft",
)
# result["post"]["id"], result["post"]["link"]
```

### 批量生成（topics.txt，每行一個主題）

```
# topics.txt
Flow cytometry 基礎介紹
CAR-T 細胞療法原理
PBMC 分離技術
```

```python
from scripts.wp_ai_writer import batch_write

results = batch_write(
    topics_file="topics.txt",
    language="zh-TW",
    status="draft",
    delay=3.0,     # Claude API rate limit 緩衝
)
```

**CLI：**
```bash
# 單篇草稿
uv run scripts/wp_ai_writer.py write "CAR-T 細胞療法"

# 指定語言、字數、直接發布
uv run scripts/wp_ai_writer.py write "Flow cytometry" --lang en --words 800 --status publish

# 互動模式（預覽後再決定）
uv run scripts/wp_ai_writer.py interactive "文章主題"

# 批量生成
uv run scripts/wp_ai_writer.py batch topics.txt --delay 3
```

---

## Common Operations Reference

| 操作 | 腳本 | Endpoint |
|------|------|---------|
| Posts CRUD | wp_poster.py | `/wp-json/wp/v2/posts` |
| Pages CRUD | wp_pages.py | `/wp-json/wp/v2/pages` |
| 媒體上傳 | wp_poster.py | `/wp-json/wp/v2/media` |
| 分類管理 | wp_poster.py | `/wp-json/wp/v2/categories` |
| 批量匯入 | wp_batch.py | （多次呼叫 posts endpoint）|
| AI 生成 | wp_ai_writer.py | Claude API + WP posts |

---

## Error Handling

```python
try:
    result = create_post(...)
except httpx.HTTPStatusError as e:
    print(f"HTTP {e.response.status_code}: {e.response.text}")
```

**常見錯誤：**
- `401` → 檢查 WP_USERNAME / WP_APP_PASSWORD
- `403` → 使用者權限不足（需 Editor 以上）
- `404` → WP_URL 設定錯誤，或 REST API 被停用
- Claude API `429` → 觸發 rate limit，增加 batch_write 的 delay

---

## Dependencies

```bash
uv add httpx python-dotenv    # 必要
uv add Pillow                 # WebP 轉換（wp_poster / wp_batch）
uv add anthropic              # AI 生成（wp_ai_writer，選填，也可直接用 httpx）
```
