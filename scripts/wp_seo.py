#!/usr/bin/env python3
"""
WordPress SEO 管理工具 — wordpress-poster skill
支援 Yoast SEO 與 Rank Math，自動偵測已安裝的外掛。

Requires: httpx, python-dotenv

Usage:
    # 偵測目前安裝的 SEO 外掛
    uv run scripts/wp_seo.py detect

    # 更新單篇文章的 SEO meta
    uv run scripts/wp_seo.py update <post_id> \\
        --title "SEO 標題" \\
        --desc "Meta description，120字以內" \\
        --keyword "主要關鍵字" \\
        --canonical "https://example.com/canonical-url"

    # 讀取單篇文章的 SEO 狀態
    uv run scripts/wp_seo.py get <post_id>

    # 批量更新（從 JSON 檔案）
    uv run scripts/wp_seo.py batch-update seo_data.json

SEO JSON 格式（batch-update 用）：
[
  {
    "post_id": 42,
    "seo_title": "SEO 標題（與文章標題可不同）",
    "meta_description": "搜尋引擎顯示的描述，建議 120–155 字",
    "focus_keyword": "主要關鍵字",
    "canonical_url": "https://...",
    "og_title": "社群分享標題（選填）",
    "og_description": "社群分享描述（選填）"
  }
]
"""
import base64
import json
import os
import sys
import httpx
from dotenv import load_dotenv

load_dotenv()

WP_URL       = os.getenv("WP_URL", "").rstrip("/")
USERNAME     = os.getenv("WP_USERNAME", "")
APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")

# SEO plugin field mappings
YOAST_FIELDS = {
    "seo_title":        "_yoast_wpseo_title",
    "meta_description": "_yoast_wpseo_metadesc",
    "focus_keyword":    "_yoast_wpseo_focuskw",
    "canonical_url":    "_yoast_wpseo_canonical",
    "og_title":         "_yoast_wpseo_opengraph-title",
    "og_description":   "_yoast_wpseo_opengraph-description",
    "no_index":         "_yoast_wpseo_meta-robots-noindex",
}

RANKMATH_FIELDS = {
    "seo_title":        "rank_math_title",
    "meta_description": "rank_math_description",
    "focus_keyword":    "rank_math_focus_keyword",
    "canonical_url":    "rank_math_canonical_url",
    "og_title":         "rank_math_facebook_title",
    "og_description":   "rank_math_facebook_description",
}

# None = no plugin detected
_detected_plugin: str | None = None


def _auth_headers() -> dict:
    token = base64.b64encode(f"{USERNAME}:{APP_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


# ── Plugin Detection ──────────────────────────────────────────

def detect_seo_plugin() -> str | None:
    """
    Auto-detect which SEO plugin is active by probing known REST API endpoints.

    Returns: 'yoast' | 'rankmath' | None
    """
    global _detected_plugin

    # Check Yoast: it adds yoast_head to post responses when active
    try:
        resp = httpx.get(
            f"{WP_URL}/wp-json/wp/v2/posts",
            params={"per_page": 1, "status": "any"},
            headers=_auth_headers(), timeout=10,
        )
        if resp.status_code == 200:
            posts = resp.json()
            if posts and "yoast_head" in posts[0]:
                _detected_plugin = "yoast"
                return "yoast"
    except Exception:
        pass

    # Check Rank Math: it registers its own namespace
    try:
        resp = httpx.get(
            f"{WP_URL}/wp-json/rankmath/v1/getHead",
            headers=_auth_headers(), timeout=10,
        )
        # 400 = endpoint exists but missing params → plugin is active
        if resp.status_code in (200, 400):
            _detected_plugin = "rankmath"
            return "rankmath"
    except Exception:
        pass

    _detected_plugin = None
    return None


def get_plugin(force_plugin: str | None = None) -> str | None:
    """Return cached or freshly detected plugin name."""
    if force_plugin:
        return force_plugin
    global _detected_plugin
    if _detected_plugin is None:
        detect_seo_plugin()
    return _detected_plugin


def _build_meta_payload(
    seo_fields: dict,
    plugin: str,
) -> dict:
    """Map friendly field names → plugin-specific meta keys."""
    field_map = YOAST_FIELDS if plugin == "yoast" else RANKMATH_FIELDS
    meta: dict = {}
    for friendly_key, value in seo_fields.items():
        if value and friendly_key in field_map:
            meta[field_map[friendly_key]] = value
    return meta


# ── Core SEO Operations ───────────────────────────────────────

def update_seo(
    post_id: int,
    seo_title: str = "",
    meta_description: str = "",
    focus_keyword: str = "",
    canonical_url: str = "",
    og_title: str = "",
    og_description: str = "",
    no_index: bool = False,
    plugin: str | None = None,
    post_type: str = "posts",         # posts | pages
) -> dict:
    """
    Update SEO meta fields for a post or page.
    Auto-detects Yoast or Rank Math if plugin not specified.

    Args:
        post_id:          WordPress post/page ID.
        seo_title:        SEO title tag (can differ from post title).
        meta_description: Meta description shown in search results (120–155 chars recommended).
        focus_keyword:    Primary keyword for SEO scoring.
        canonical_url:    Canonical URL to prevent duplicate content.
        og_title:         Open Graph title for social sharing.
        og_description:   Open Graph description for social sharing.
        no_index:         Set to True to tell search engines not to index this page.
        plugin:           Force 'yoast' or 'rankmath' (auto-detect if None).
        post_type:        'posts' or 'pages'.

    Returns:
        Updated WordPress post/page object.
    """
    active_plugin = get_plugin(plugin)
    if not active_plugin:
        raise RuntimeError(
            "無法偵測 SEO 外掛。請確認 Yoast SEO 或 Rank Math 已啟用，"
            "或使用 plugin='yoast'/'rankmath' 手動指定。"
        )

    seo_fields = {
        "seo_title":        seo_title,
        "meta_description": meta_description,
        "focus_keyword":    focus_keyword,
        "canonical_url":    canonical_url,
        "og_title":         og_title,
        "og_description":   og_description,
    }
    if no_index:
        seo_fields["no_index"] = "1"

    meta = _build_meta_payload(seo_fields, active_plugin)
    if not meta:
        raise ValueError("至少需要提供一個 SEO 欄位（seo_title / meta_description / ...）")

    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/{post_type}/{post_id}",
        json={"meta": meta},
        headers=_auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_seo(post_id: int, post_type: str = "posts") -> dict:
    """
    Read current SEO fields for a post.
    Returns a dict with both raw meta and parsed seo_* friendly keys.
    """
    resp = httpx.get(
        f"{WP_URL}/wp-json/wp/v2/{post_type}/{post_id}",
        params={"context": "edit"},   # 'edit' context exposes meta fields
        headers=_auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    meta = data.get("meta", {})

    active_plugin = get_plugin()
    field_map = YOAST_FIELDS if active_plugin == "yoast" else RANKMATH_FIELDS

    parsed: dict = {
        "post_id":    post_id,
        "post_title": data["title"]["rendered"],
        "plugin":     active_plugin,
        "yoast_head": data.get("yoast_head_json"),  # None if Rank Math
    }
    # Reverse-map meta keys → friendly names
    reverse_map = {v: k for k, v in field_map.items()}
    for meta_key, value in meta.items():
        if meta_key in reverse_map:
            parsed[reverse_map[meta_key]] = value

    return parsed


def batch_update_seo(
    records: list[dict],
    plugin: str | None = None,
) -> list[dict]:
    """
    Bulk-update SEO fields for multiple posts from a list of dicts.
    Each dict must have 'post_id' plus any seo_* fields.

    Example record:
        {
            "post_id": 42,
            "seo_title": "Better Title for Google",
            "meta_description": "Compelling description...",
            "focus_keyword": "flow cytometry"
        }
    """
    results = []
    for i, record in enumerate(records, 1):
        post_id = record.pop("post_id")
        post_type = record.pop("post_type", "posts")
        try:
            update_seo(post_id=post_id, plugin=plugin, post_type=post_type, **record)
            print(f"  [{i}/{len(records)}] ✅ post_id={post_id}")
            results.append({"post_id": post_id, "status": "ok"})
        except Exception as e:
            print(f"  [{i}/{len(records)}] ❌ post_id={post_id}  {e}")
            results.append({"post_id": post_id, "status": "error", "error": str(e)})
    return results


def generate_seo_fields(
    title: str,
    content: str,
    focus_keyword: str = "",
) -> dict:
    """
    Helper: generate SEO-optimised field suggestions from article content.
    Call this from Claude's conversation to get recommended values before
    calling update_seo().

    Returns a dict ready to unpack into update_seo():
        seo_title, meta_description, focus_keyword, og_title, og_description
    """
    # Trim title to 60 chars (Google truncates at ~60)
    seo_title = title[:60] if len(title) > 60 else title

    # Strip HTML tags for description generation
    import re
    plain = re.sub(r"<[^>]+>", "", content).strip()
    # First ~155 chars of plain text as meta description
    meta_description = plain[:155].rsplit(" ", 1)[0] + "…" if len(plain) > 155 else plain

    return {
        "seo_title":        seo_title,
        "meta_description": meta_description,
        "focus_keyword":    focus_keyword,
        "og_title":         seo_title,
        "og_description":   meta_description[:120],
    }


# ── CLI ───────────────────────────────────────────────────────
if __name__ == "__main__":
    if not all([WP_URL, USERNAME, APP_PASSWORD]):
        print("❌ 請先設定 .env：WP_URL, WP_USERNAME, WP_APP_PASSWORD")
        sys.exit(1)

    action = sys.argv[1] if len(sys.argv) > 1 else "help"

    if action == "detect":
        plugin = detect_seo_plugin()
        if plugin:
            print(f"✅ 偵測到 SEO 外掛：{plugin}")
        else:
            print("⚠️  未偵測到 Yoast SEO 或 Rank Math，請確認外掛已安裝並啟用")

    elif action == "get":
        post_id   = int(sys.argv[2])
        post_type = "pages" if "--page" in sys.argv else "posts"
        result = get_seo(post_id, post_type=post_type)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif action == "update":
        # uv run scripts/wp_seo.py update <id> --title "..." --desc "..." --keyword "..."
        post_id = int(sys.argv[2])
        args = sys.argv[3:]
        def _arg(flag: str, default: str = "") -> str:
            return args[args.index(flag) + 1] if flag in args else default

        post_type = "pages" if "--page" in args else "posts"
        result = update_seo(
            post_id=post_id,
            seo_title=_arg("--title"),
            meta_description=_arg("--desc"),
            focus_keyword=_arg("--keyword"),
            canonical_url=_arg("--canonical"),
            og_title=_arg("--og-title"),
            og_description=_arg("--og-desc"),
            no_index="--noindex" in args,
            post_type=post_type,
        )
        plugin = get_plugin()
        print(f"✅ SEO meta 已更新（外掛：{plugin}）")
        print(f"   post_id={post_id}  title={result['title']['rendered']}")

    elif action == "batch-update":
        path = sys.argv[2]
        with open(path, encoding="utf-8") as f:
            records = json.load(f)
        records = records if isinstance(records, list) else [records]
        print(f"批量更新 SEO：共 {len(records)} 筆")
        results = batch_update_seo(records)
        ok = sum(1 for r in results if r["status"] == "ok")
        print(f"\n完成：{ok}/{len(results)} 成功")

    else:
        print(__doc__)
