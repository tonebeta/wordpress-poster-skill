#!/usr/bin/env python3
"""
WordPress REST API helper — loaded from the wordpress-poster skill.
Usage: uv run wp_poster.py
Requires: httpx, python-dotenv
"""
import httpx
import base64
import os
import json
import sys
from dotenv import load_dotenv

load_dotenv()

WP_URL       = os.getenv("WP_URL", "").rstrip("/")
USERNAME     = os.getenv("WP_USERNAME", "")
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
        json=payload, headers=_auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def update_post(post_id: int, **fields) -> dict:
    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
        json=fields, headers=_auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_post(post_id: int) -> dict:
    resp = httpx.get(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
        headers=_auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def list_posts(per_page: int = 10, page: int = 1, status: str = "any") -> list[dict]:
    resp = httpx.get(
        f"{WP_URL}/wp-json/wp/v2/posts",
        params={"per_page": per_page, "page": page, "status": status},
        headers=_auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def delete_post(post_id: int, force: bool = False) -> dict:
    resp = httpx.delete(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
        params={"force": str(force).lower()},
        headers=_auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def list_categories() -> list[dict]:
    resp = httpx.get(
        f"{WP_URL}/wp-json/wp/v2/categories",
        params={"per_page": 100},
        headers=_auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def create_category(name: str, slug: str = "", parent: int = 0) -> dict:
    payload: dict = {"name": name}
    if slug:   payload["slug"] = slug
    if parent: payload["parent"] = parent
    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/categories",
        json=payload, headers=_auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def upload_media(file_path: str, title: str = "") -> dict:
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
            content=f.read(), headers=headers, timeout=60,
        )
    resp.raise_for_status()
    return resp.json()


# ── CLI quick-test ────────────────────────────────────────────
if __name__ == "__main__":
    if not all([WP_URL, USERNAME, APP_PASSWORD]):
        print("❌ 請先設定 .env：WP_URL, WP_USERNAME, WP_APP_PASSWORD")
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

    else:
        print(f"用法: uv run scripts/wp_poster.py [list|create '標題']")
