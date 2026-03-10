#!/usr/bin/env python3
"""
WordPress AI 寫文工具 — wordpress-poster skill（Claude skill 模式）

此腳本只負責「把內容發布到 WordPress」，並可同時寫入 SEO meta。
文章生成由 Claude（對話環境）負責，不需要 ANTHROPIC_API_KEY。

工作流程：
    1. 你在對話中告訴 Claude 主題與要求
    2. Claude 生成 title / content / excerpt / seo_* 欄位
    3. 此腳本發布文章並寫入 SEO meta（需搭配 functions.php snippet）

Requires: httpx, python-dotenv

Usage:
    uv run scripts/wp_ai_writer.py publish '{"title":"...","content":"...","seo_title":"...","meta_description":"..."}'
    uv run scripts/wp_ai_writer.py publish-file generated.json
    uv run scripts/wp_ai_writer.py interactive

JSON 格式：
{
  "title":            "文章標題",
  "content":          "<h2>小標</h2><p>HTML 內文...</p>",
  "excerpt":          "文章摘要（選填）",
  "status":           "draft",
  "categories":       [1, 2],
  "tags":             [3, 4],
  "seo_title":        "SEO 專用標題（選填，建議 ≤60 字）",
  "meta_description": "搜尋結果描述（選填，建議 120–155 字）",
  "focus_keyword":    "主要關鍵字（選填）",
  "og_title":         "社群分享標題（選填）",
  "og_description":   "社群分享描述（選填）"
}
"""
import base64
import json
import os
import sys
import httpx
from dotenv import load_dotenv

load_dotenv()

WP_URL         = os.getenv("WP_URL", "").rstrip("/")
USERNAME       = os.getenv("WP_USERNAME", "")
APP_PASSWORD   = os.getenv("WP_APP_PASSWORD", "")
DEFAULT_STATUS = os.getenv("WP_AI_DEFAULT_STATUS", "draft")
DEFAULT_CAT    = int(os.getenv("WP_AI_DEFAULT_CATEGORY", "0") or "0")

# Lazy-import seo module (same package)
_seo = None

def _get_seo():
    global _seo
    if _seo is None:
        import importlib.util, pathlib
        spec = importlib.util.spec_from_file_location(
            "wp_seo",
            pathlib.Path(__file__).parent / "wp_seo.py",
        )
        _seo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_seo)
    return _seo


def _auth_headers() -> dict:
    token = base64.b64encode(f"{USERNAME}:{APP_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def publish_generated(
    title: str,
    content: str,
    excerpt: str = "",
    status: str = DEFAULT_STATUS,
    categories: list[int] | None = None,
    tags: list[int] | None = None,
    # SEO fields (Yoast / Rank Math)
    seo_title: str = "",
    meta_description: str = "",
    focus_keyword: str = "",
    og_title: str = "",
    og_description: str = "",
    auto_seo: bool = True,
) -> dict:
    """
    Publish Claude-generated content to WordPress, with optional SEO meta.

    Args:
        title:            Article title.
        content:          Full HTML content.
        excerpt:          Short summary (optional).
        status:           draft | publish | pending | private.
        categories:       List of category IDs.
        tags:             List of tag IDs.
        seo_title:        SEO title tag (≤60 chars recommended).
        meta_description: Meta description for search results (120–155 chars).
        focus_keyword:    Primary keyword for SEO scoring.
        og_title:         Open Graph title for social sharing.
        og_description:   Open Graph description for social sharing.
        auto_seo:         If True and no seo_title/meta_description provided,
                          auto-generate them from title + content.

    Returns:
        WordPress post object (includes 'id', 'link', 'status').
    """
    # Auto-generate SEO fields if not provided
    if auto_seo and not seo_title and not meta_description:
        seo = _get_seo()
        suggested = seo.generate_seo_fields(title, content, focus_keyword)
        seo_title        = seo_title        or suggested["seo_title"]
        meta_description = meta_description or suggested["meta_description"]
        og_title         = og_title         or suggested["og_title"]
        og_description   = og_description   or suggested["og_description"]

    payload: dict = {
        "title":   title,
        "content": content,
        "status":  status,
    }
    if excerpt:
        payload["excerpt"] = excerpt

    cats = categories or ([DEFAULT_CAT] if DEFAULT_CAT else [])
    if cats:   payload["categories"] = cats
    if tags:   payload["tags"] = tags

    # Step 1: create the post
    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        json=payload, headers=_auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    post = resp.json()
    post_id = post["id"]

    # Step 2: write SEO meta (best-effort — skip if plugin not detected)
    if any([seo_title, meta_description, focus_keyword, og_title, og_description]):
        try:
            seo = _get_seo()
            seo.WP_URL       = WP_URL
            seo.USERNAME     = USERNAME
            seo.APP_PASSWORD = APP_PASSWORD
            seo.update_seo(
                post_id=post_id,
                seo_title=seo_title,
                meta_description=meta_description,
                focus_keyword=focus_keyword,
                og_title=og_title,
                og_description=og_description,
            )
            print(f"   SEO meta 已寫入（外掛：{seo.get_plugin()}）")
        except RuntimeError as e:
            print(f"   ⚠️  SEO meta 跳過：{e}")
        except Exception as e:
            print(f"   ⚠️  SEO meta 寫入失敗：{e}")

    return post


def publish_from_dict(data: dict) -> dict:
    """Convenience wrapper: publish from Claude's JSON output dict."""
    return publish_generated(
        title=data["title"],
        content=data["content"],
        excerpt=data.get("excerpt", ""),
        status=data.get("status", DEFAULT_STATUS),
        categories=data.get("categories"),
        tags=data.get("tags"),
        seo_title=data.get("seo_title", ""),
        meta_description=data.get("meta_description", ""),
        focus_keyword=data.get("focus_keyword", ""),
        og_title=data.get("og_title", ""),
        og_description=data.get("og_description", ""),
        auto_seo=data.get("auto_seo", True),
    )


# ── CLI ───────────────────────────────────────────────────────
if __name__ == "__main__":
    if not all([WP_URL, USERNAME, APP_PASSWORD]):
        print("❌ 請先設定 .env：WP_URL, WP_USERNAME, WP_APP_PASSWORD")
        sys.exit(1)

    action = sys.argv[1] if len(sys.argv) > 1 else "help"

    if action == "publish":
        data = json.loads(sys.argv[2])
        post = publish_from_dict(data)
        print(f"✅ 已發布 ID={post['id']}  狀態={post['status']}")
        print(f"   連結: {post['link']}")

    elif action == "publish-file":
        with open(sys.argv[2], encoding="utf-8") as f:
            data = json.load(f)
        records = data if isinstance(data, list) else [data]
        for i, record in enumerate(records, 1):
            post = publish_from_dict(record)
            print(f"[{i}/{len(records)}] ✅ ID={post['id']}  {post['link']}")

    elif action == "interactive":
        print("請貼上 Claude 生成的 JSON 內容（貼完後按 Enter 兩次）：")
        lines = []
        while True:
            line = input()
            if line == "" and lines:
                break
            lines.append(line)
        data = json.loads("\n".join(lines))
        records = data if isinstance(data, list) else [data]
        print(f"\n準備發布 {len(records)} 篇文章：")
        for r in records:
            print(f"  - {r['title']}  (status={r.get('status', DEFAULT_STATUS)})")
        confirm = input("\n確認發布？[y/N] ").strip().lower()
        if confirm == "y":
            for i, record in enumerate(records, 1):
                post = publish_from_dict(record)
                print(f"[{i}] ✅ ID={post['id']}  {post['link']}")
        else:
            print("已取消。")

    else:
        print(__doc__)
