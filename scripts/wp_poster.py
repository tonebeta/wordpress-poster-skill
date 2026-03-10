#!/usr/bin/env python3
"""
WordPress REST API helper — loaded from the wordpress-poster skill.
Usage: uv run wp_poster.py
Requires: httpx, python-dotenv
"""
import json
import os
import sys

import httpx
from wp_client import WP_URL, USERNAME, APP_PASSWORD, auth_headers, media_headers, check_env


def create_post(
    title: str,
    content: str,
    status: str = "draft",
    categories: list[int] | None = None,
    tags: list[int] | None = None,
    excerpt: str = "",
    slug: str = "",
    featured_media: int = 0,
) -> dict:
    payload: dict = {
        "title":   title,
        "content": content,
        "status":  status,
        "excerpt": excerpt,
    }
    if slug:            payload["slug"] = slug
    if categories:      payload["categories"] = categories
    if tags:            payload["tags"] = tags
    if featured_media:  payload["featured_media"] = featured_media

    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        json=payload, headers=auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def update_post(post_id: int, **fields) -> dict:
    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
        json=fields, headers=auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_post(post_id: int) -> dict:
    resp = httpx.get(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
        headers=auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def list_posts(per_page: int = 10, page: int = 1, status: str = "any") -> list[dict]:
    resp = httpx.get(
        f"{WP_URL}/wp-json/wp/v2/posts",
        params={"per_page": per_page, "page": page, "status": status},
        headers=auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def delete_post(post_id: int, force: bool = False) -> dict:
    resp = httpx.delete(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
        params={"force": str(force).lower()},
        headers=auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def list_categories() -> list[dict]:
    resp = httpx.get(
        f"{WP_URL}/wp-json/wp/v2/categories",
        params={"per_page": 100},
        headers=auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def create_category(name: str, slug: str = "", parent: int = 0) -> dict:
    payload: dict = {"name": name}
    if slug:   payload["slug"] = slug
    if parent: payload["parent"] = parent
    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/categories",
        json=payload, headers=auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _convert_to_webp(
    file_path: str,
    quality: int = 85,
    lossless: bool = False,
) -> tuple[bytes, str]:
    """
    Convert an image to WebP format in-memory.
    Returns (webp_bytes, new_filename).
    Requires: Pillow (`uv add Pillow`)
    """
    try:
        from PIL import Image
        import io
    except ImportError:
        raise ImportError(
            "Pillow is required for WebP conversion. "
            "Run: uv add Pillow"
        )

    stem = os.path.splitext(os.path.basename(file_path))[0]
    new_filename = f"{stem}.webp"

    with Image.open(file_path) as img:
        # Preserve transparency (RGBA) or convert to RGB
        if img.mode in ("RGBA", "LA", "PA"):
            img = img.convert("RGBA")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=quality, lossless=lossless)
        return buf.getvalue(), new_filename


def upload_media(
    file_path: str,
    title: str = "",
    convert_webp: bool = False,
    webp_quality: int = 85,
    webp_lossless: bool = False,
) -> dict:
    """
    Upload an image or file as WordPress media.

    Args:
        file_path:      Local path to the file.
        title:          Optional media title shown in WordPress.
        convert_webp:   If True, convert image to WebP before uploading.
        webp_quality:   WebP lossy quality 1-100 (default 85). Ignored when lossless=True.
        webp_lossless:  If True, use lossless WebP encoding (larger file, perfect quality).

    Returns:
        WordPress media object dict (includes 'id', 'source_url', etc.)
    """
    import mimetypes

    if convert_webp:
        file_bytes, filename = _convert_to_webp(file_path, webp_quality, webp_lossless)
        mime_type = "image/webp"
        original_size = os.path.getsize(file_path)
        print(
            f"  WebP 轉換完成: {os.path.basename(file_path)} → {filename} "
            f"({original_size:,} → {len(file_bytes):,} bytes, "
            f"節省 {(1 - len(file_bytes)/original_size)*100:.1f}%)"
        )
    else:
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        filename = os.path.basename(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "application/octet-stream"

    headers = media_headers(filename, mime_type)
    if title:
        headers["X-WP-Media-Title"] = title

    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/media",
        content=file_bytes, headers=headers, timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


# ── CLI ───────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        check_env()
    except EnvironmentError as e:
        print(e)
        sys.exit(1)

    action = sys.argv[1] if len(sys.argv) > 1 else "list"

    if action == "list":
        posts = list_posts(per_page=5, status="any")
        for p in posts:
            print(f"[{p['id']}] {p['status']:8s} {p['title']['rendered']}")

    elif action == "create":
        result = create_post(
            title=sys.argv[2] if len(sys.argv) > 2 else "測試文章",
            content="<p>透過 <strong>WordPress Poster Skill</strong> 建立的文章。</p>",
            status="draft",
        )
        print(f"✅ 草稿已建立 ID={result['id']}  連結={result['link']}")

    elif action == "upload":
        # Usage:
        #   uv run scripts/wp_poster.py upload photo.jpg
        #   uv run scripts/wp_poster.py upload photo.jpg --webp
        #   uv run scripts/wp_poster.py upload photo.jpg --webp --quality 90
        #   uv run scripts/wp_poster.py upload photo.jpg --webp --lossless
        if len(sys.argv) < 3:
            print("用法: uv run scripts/wp_poster.py upload <file> [--webp] [--quality N] [--lossless]")
            sys.exit(1)

        file_arg   = sys.argv[2]
        args       = sys.argv[3:]
        do_webp    = "--webp" in args
        lossless   = "--lossless" in args
        quality    = 85
        if "--quality" in args:
            idx = args.index("--quality")
            quality = int(args[idx + 1])

        result = upload_media(
            file_path=file_arg,
            convert_webp=do_webp,
            webp_quality=quality,
            webp_lossless=lossless,
        )
        print(f"✅ 媒體已上傳 ID={result['id']}")
        print(f"   URL: {result['source_url']}")

    else:
        print("用法:")
        print("  uv run scripts/wp_poster.py list")
        print("  uv run scripts/wp_poster.py create '標題'")
        print("  uv run scripts/wp_poster.py upload <file>")
        print("  uv run scripts/wp_poster.py upload <file> --webp")
        print("  uv run scripts/wp_poster.py upload <file> --webp --quality 90")
        print("  uv run scripts/wp_poster.py upload <file> --webp --lossless")
