#!/usr/bin/env python3
"""
WordPress Pages management — wordpress-poster skill
Requires: httpx, python-dotenv
Usage:
    uv run scripts/wp_pages.py list
    uv run scripts/wp_pages.py get <id>
    uv run scripts/wp_pages.py create '標題' '內容 HTML'
    uv run scripts/wp_pages.py update <id> --title '新標題'
    uv run scripts/wp_pages.py delete <id>
    uv run scripts/wp_pages.py tree
"""
import base64
import os
import sys
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

WP_URL       = os.getenv("WP_URL", "").rstrip("/")
USERNAME     = os.getenv("WP_USERNAME", "")
APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")


def _auth_headers() -> dict:
    token = base64.b64encode(f"{USERNAME}:{APP_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


# ── Pages CRUD ────────────────────────────────────────────────

def list_pages(
    per_page: int = 100,
    page: int = 1,
    status: str = "any",
    parent: int = 0,
    order_by: str = "menu_order",
    order: str = "asc",
) -> list[dict]:
    """List pages. parent=0 means all pages; parent=N means children of page N."""
    params: dict = {
        "per_page": per_page,
        "page": page,
        "status": status,
        "orderby": order_by,
        "order": order,
    }
    if parent:
        params["parent"] = parent
    resp = httpx.get(
        f"{WP_URL}/wp-json/wp/v2/pages",
        params=params, headers=_auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_page(page_id: int) -> dict:
    """Fetch a single page by ID."""
    resp = httpx.get(
        f"{WP_URL}/wp-json/wp/v2/pages/{page_id}",
        headers=_auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def create_page(
    title: str,
    content: str,
    status: str = "draft",           # draft | publish | private
    slug: str = "",
    parent: int = 0,                 # parent page ID (0 = top-level)
    menu_order: int = 0,
    excerpt: str = "",
    featured_media: int = 0,
    template: str = "",              # page template filename, e.g. "full-width.php"
) -> dict:
    """Create a new page."""
    payload: dict = {
        "title":      title,
        "content":    content,
        "status":     status,
        "menu_order": menu_order,
        "excerpt":    excerpt,
    }
    if slug:            payload["slug"] = slug
    if parent:          payload["parent"] = parent
    if featured_media:  payload["featured_media"] = featured_media
    if template:        payload["template"] = template

    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/pages",
        json=payload, headers=_auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def update_page(page_id: int, **fields) -> dict:
    """
    Update a page by ID.
    Any field accepted by the Pages endpoint can be passed as a kwarg.
    Common fields: title, content, status, slug, parent, menu_order, template
    """
    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/pages/{page_id}",
        json=fields, headers=_auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def delete_page(page_id: int, force: bool = False) -> dict:
    """Move page to trash (force=True for permanent deletion)."""
    resp = httpx.delete(
        f"{WP_URL}/wp-json/wp/v2/pages/{page_id}",
        params={"force": str(force).lower()},
        headers=_auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def page_tree() -> list[dict]:
    """
    Return all pages as a nested tree structure.
    Each page dict gains a 'children' key with sub-pages.
    """
    all_pages = list_pages(per_page=100, status="any")
    by_id = {p["id"]: {**p, "children": []} for p in all_pages}
    roots = []
    for p in by_id.values():
        parent_id = p.get("parent", 0)
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(p)
        else:
            roots.append(p)
    return roots


def _print_tree(pages: list[dict], indent: int = 0) -> None:
    for p in pages:
        prefix = "  " * indent + ("└─ " if indent else "")
        status = p.get("status", "?")
        title  = p["title"]["rendered"]
        print(f"{prefix}[{p['id']}] ({status}) {title}")
        if p.get("children"):
            _print_tree(p["children"], indent + 1)


# ── CLI ───────────────────────────────────────────────────────
if __name__ == "__main__":
    if not all([WP_URL, USERNAME, APP_PASSWORD]):
        print("❌ 請先設定 .env：WP_URL, WP_USERNAME, WP_APP_PASSWORD")
        sys.exit(1)

    action = sys.argv[1] if len(sys.argv) > 1 else "list"

    if action == "list":
        pages = list_pages()
        for p in pages:
            print(f"[{p['id']}] ({p['status']:8s}) order={p['menu_order']:3d}  {p['title']['rendered']}")

    elif action == "tree":
        tree = page_tree()
        _print_tree(tree)

    elif action == "get":
        pid = int(sys.argv[2])
        p = get_page(pid)
        print(json.dumps({
            "id": p["id"], "title": p["title"]["rendered"],
            "status": p["status"], "slug": p["slug"],
            "parent": p.get("parent"), "link": p["link"],
        }, ensure_ascii=False, indent=2))

    elif action == "create":
        title   = sys.argv[2] if len(sys.argv) > 2 else "新頁面"
        content = sys.argv[3] if len(sys.argv) > 3 else "<p>頁面內容</p>"
        result = create_page(title=title, content=content, status="draft")
        print(f"✅ 頁面草稿已建立 ID={result['id']}  連結={result['link']}")

    elif action == "update":
        # uv run wp_pages.py update <id> --title '新標題' --status publish
        pid  = int(sys.argv[2])
        args = sys.argv[3:]
        fields: dict = {}
        i = 0
        while i < len(args):
            if args[i] == "--title":   fields["title"]   = args[i+1]; i += 2
            elif args[i] == "--status": fields["status"]  = args[i+1]; i += 2
            elif args[i] == "--slug":   fields["slug"]    = args[i+1]; i += 2
            elif args[i] == "--order":  fields["menu_order"] = int(args[i+1]); i += 2
            else: i += 1
        result = update_page(pid, **fields)
        print(f"✅ 頁面已更新 ID={result['id']}  狀態={result['status']}")

    elif action == "delete":
        pid = int(sys.argv[2])
        force = "--force" in sys.argv
        result = delete_page(pid, force=force)
        print(f"✅ 頁面已{'永久刪除' if force else '移至垃圾桶'} ID={pid}")

    else:
        print(__doc__)
