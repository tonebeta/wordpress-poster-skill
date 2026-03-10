#!/usr/bin/env python3
"""
WordPress 批量發文工具 — wordpress-poster skill
從 JSON 或 CSV 檔案批量匯入文章，支援乾跑模式、錯誤續傳。

Requires: httpx, python-dotenv
Optional: Pillow (for --webp flag)

Usage:
    uv run scripts/wp_batch.py import posts.json
    uv run scripts/wp_batch.py import posts.csv
    uv run scripts/wp_batch.py import posts.json --status publish
    uv run scripts/wp_batch.py import posts.json --dry-run
    uv run scripts/wp_batch.py import posts.json --webp --delay 1.0
    uv run scripts/wp_batch.py template --format json
    uv run scripts/wp_batch.py template --format csv

JSON 格式（每個物件一篇文章）:
[
  {
    "title": "文章標題",
    "content": "<p>HTML 內文</p>",
    "status": "draft",          // 選填，預設 draft
    "excerpt": "摘要",           // 選填
    "slug": "my-post-slug",     // 選填
    "categories": [1, 2],       // 選填，分類 ID 陣列
    "tags": [3, 4],             // 選填，標籤 ID 陣列
    "image_path": "/path/to/cover.jpg"  // 選填，自動上傳為特色圖片
  }
]

CSV 格式（第一列為欄位名稱）:
title,content,status,excerpt,slug,categories,tags,image_path
文章標題,<p>內文</p>,draft,摘要,my-slug,"1,2","3,4",/path/cover.jpg
"""
import csv
import json
import os
import sys
import time
from pathlib import Path

import httpx
from wp_client import WP_URL, auth_headers, media_headers, check_env


def _upload_image(
    file_path: str,
    convert_webp: bool = False,
    webp_quality: int = 85,
) -> int:
    """Upload image, optionally convert to WebP. Returns media ID."""
    import mimetypes
    import io

    if convert_webp:
        try:
            from PIL import Image
        except ImportError:
            print("  ⚠️  Pillow 未安裝，跳過 WebP 轉換。執行: uv add Pillow")
            convert_webp = False

    if convert_webp:
        from PIL import Image
        stem     = Path(file_path).stem
        filename = f"{stem}.webp"
        with Image.open(file_path) as img:
            img = img.convert("RGBA") if img.mode in ("RGBA","LA","PA") else img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="WEBP", quality=webp_quality)
        file_bytes = buf.getvalue()
        mime_type  = "image/webp"
        orig_size  = os.path.getsize(file_path)
        print(f"    WebP: {Path(file_path).name} → {filename} "
              f"({orig_size:,}→{len(file_bytes):,}B, "
              f"節省{(1-len(file_bytes)/orig_size)*100:.0f}%)")
    else:
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        filename  = Path(file_path).name
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "application/octet-stream"

    headers = media_headers(filename, mime_type)
    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/media",
        content=file_bytes, headers=headers, timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _create_post(payload: dict) -> dict:
    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        json=payload, headers=auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_id_list(val: str | list | None) -> list[int]:
    """Parse "1,2,3" or [1,2,3] or None → [1,2,3]."""
    if not val:
        return []
    if isinstance(val, list):
        return [int(x) for x in val if x]
    return [int(x.strip()) for x in str(val).split(",") if x.strip()]


def load_file(path: str) -> list[dict]:
    """Load posts from .json or .csv file."""
    ext = Path(path).suffix.lower()
    if ext == ".json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
    elif ext == ".csv":
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    else:
        raise ValueError(f"不支援的格式：{ext}（僅支援 .json / .csv）")


def batch_import(
    file_path: str,
    default_status: str = "draft",
    dry_run: bool = False,
    convert_webp: bool = False,
    webp_quality: int = 85,
    delay: float = 0.5,
) -> dict:
    """
    Import posts from a JSON or CSV file.

    Args:
        file_path:      Path to .json or .csv file.
        default_status: Fallback status if not set per-row (draft/publish/pending).
        dry_run:        Print what would happen without actually posting.
        convert_webp:   Convert image_path images to WebP before uploading.
        webp_quality:   WebP quality 1-100 (default 85).
        delay:          Seconds between each API call (avoids rate limiting).

    Returns:
        Summary dict: {total, success, failed, skipped, results}
    """
    records = load_file(file_path)
    total   = len(records)
    results = []
    success = failed = skipped = 0

    print(f"{'[DRY RUN] ' if dry_run else ''}匯入來源: {file_path}  共 {total} 筆\n")

    for i, row in enumerate(records, 1):
        title   = str(row.get("title", "")).strip()
        content = str(row.get("content", "")).strip()

        if not title:
            print(f"  [{i}/{total}] ⚠️  跳過（無標題）")
            skipped += 1
            results.append({"index": i, "status": "skipped", "reason": "no title"})
            continue

        status = str(row.get("status", default_status)).strip() or default_status

        payload: dict = {
            "title":   title,
            "content": content,
            "status":  status,
        }
        if row.get("excerpt"):  payload["excerpt"]    = str(row["excerpt"])
        if row.get("slug"):     payload["slug"]       = str(row["slug"])
        cats = _parse_id_list(row.get("categories"))
        tags = _parse_id_list(row.get("tags"))
        if cats: payload["categories"] = cats
        if tags: payload["tags"]       = tags

        if dry_run:
            print(f"  [{i}/{total}] 🔍 [DRY RUN] '{title}' → status={status}"
                  + (f"  image={row.get('image_path')}" if row.get("image_path") else ""))
            success += 1
            results.append({"index": i, "status": "dry_run", "title": title})
            continue

        # Upload featured image if provided
        image_path = str(row.get("image_path", "")).strip()
        if image_path:
            if not os.path.exists(image_path):
                print(f"  [{i}/{total}] ⚠️  圖片不存在，跳過上傳: {image_path}")
            else:
                try:
                    media_id = _upload_image(image_path, convert_webp, webp_quality)
                    payload["featured_media"] = media_id
                except Exception as e:
                    print(f"  [{i}/{total}] ⚠️  圖片上傳失敗: {e}")

        try:
            result = _create_post(payload)
            print(f"  [{i}/{total}] ✅  '{title}' → ID={result['id']}  {result['link']}")
            success += 1
            results.append({"index": i, "status": "ok", "id": result["id"],
                             "title": title, "link": result["link"]})
        except httpx.HTTPStatusError as e:
            msg = e.response.text[:120]
            print(f"  [{i}/{total}] ❌  '{title}' 失敗: {e.response.status_code} {msg}")
            failed += 1
            results.append({"index": i, "status": "error", "title": title,
                             "error": str(e.response.status_code)})

        if delay and i < total:
            time.sleep(delay)

    print(f"\n完成 ─ 成功:{success}  失敗:{failed}  跳過:{skipped}  共:{total}")
    return {"total": total, "success": success, "failed": failed,
            "skipped": skipped, "results": results}


def print_template(fmt: str = "json") -> None:
    """Print a starter template to stdout."""
    if fmt == "json":
        template = [
            {
                "title": "文章標題一",
                "content": "<h2>小標</h2><p>內文段落，支援完整 HTML。</p>",
                "status": "draft",
                "excerpt": "文章摘要（選填）",
                "slug": "article-slug-one",
                "categories": [1],
                "tags": [2, 3],
                "image_path": "/path/to/cover.jpg"
            },
            {
                "title": "文章標題二",
                "content": "<p>第二篇文章</p>",
                "status": "publish"
            }
        ]
        print(json.dumps(template, ensure_ascii=False, indent=2))
    else:
        print("title,content,status,excerpt,slug,categories,tags,image_path")
        print('文章標題一,"<h2>小標</h2><p>內文</p>",draft,摘要,my-slug,"1,2","3,4",/path/cover.jpg')
        print('文章標題二,<p>內文</p>,publish,,,,, ')


# ── CLI ───────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    action = sys.argv[1]

    if action == "template":
        fmt = "csv" if "--format" in sys.argv and sys.argv[sys.argv.index("--format")+1] == "csv" else "json"
        print_template(fmt)

    elif action == "import":
        if len(sys.argv) < 3:
            print("用法: uv run scripts/wp_batch.py import <file.json|file.csv> [options]")
            sys.exit(1)

        try:
            check_env()
        except EnvironmentError as e:
            print(e)
            sys.exit(1)

        args = sys.argv[3:]
        status    = args[args.index("--status")+1] if "--status" in args else "draft"
        dry_run   = "--dry-run" in args
        do_webp   = "--webp" in args
        quality   = int(args[args.index("--quality")+1]) if "--quality" in args else 85
        delay     = float(args[args.index("--delay")+1]) if "--delay" in args else 0.5

        summary = batch_import(
            file_path=sys.argv[2],
            default_status=status,
            dry_run=dry_run,
            convert_webp=do_webp,
            webp_quality=quality,
            delay=delay,
        )

        # Save results log
        log_path = Path(sys.argv[2]).stem + "_import_log.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"結果已存至: {log_path}")

    else:
        print(__doc__)
