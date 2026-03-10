#!/usr/bin/env python3
"""
WordPress SEO 管理工具 — wordpress-poster skill
支援 Yoast SEO 與 Rank Math，自動偵測已安裝的外掛。

Requires: httpx, python-dotenv

Usage:
    uv run scripts/wp_seo.py detect
    uv run scripts/wp_seo.py get <post_id> [--page]
    uv run scripts/wp_seo.py update <post_id> --title "SEO 標題" --desc "描述" --keyword "關鍵字"
    uv run scripts/wp_seo.py update <post_id> --canonical "https://..." --noindex
    uv run scripts/wp_seo.py batch-update seo_data.json

SEO JSON 格式（batch-update 用）：
[
  {
    "post_id": 42,
    "seo_title": "SEO 標題",
    "meta_description": "搜尋引擎顯示的描述，建議 120–155 字",
    "focus_keyword": "主要關鍵字",
    "canonical_url": "https://...",
    "og_title": "社群分享標題（選填）",
    "og_description": "社群分享描述（選填）"
  }
]
"""
import json
import re
import sys
from typing import TypedDict

import httpx
from wp_client import WP_URL, auth_headers, check_env


# ── SEO field TypedDict ───────────────────────────────────────

class SEOFields(TypedDict, total=False):
    seo_title:        str
    meta_description: str
    focus_keyword:    str
    canonical_url:    str
    og_title:         str
    og_description:   str
    no_index:         bool


# ── Plugin field mappings ─────────────────────────────────────

YOAST_FIELDS: dict[str, str] = {
    "seo_title":        "_yoast_wpseo_title",
    "meta_description": "_yoast_wpseo_metadesc",
    "focus_keyword":    "_yoast_wpseo_focuskw",
    "canonical_url":    "_yoast_wpseo_canonical",
    "og_title":         "_yoast_wpseo_opengraph-title",
    "og_description":   "_yoast_wpseo_opengraph-description",
    "no_index":         "_yoast_wpseo_meta-robots-noindex",
}

RANKMATH_FIELDS: dict[str, str] = {
    "seo_title":        "rank_math_title",
    "meta_description": "rank_math_description",
    "focus_keyword":    "rank_math_focus_keyword",
    "canonical_url":    "rank_math_canonical_url",
    "og_title":         "rank_math_facebook_title",
    "og_description":   "rank_math_facebook_description",
}

_detected_plugin: str | None = None  # module-level cache


# ── Plugin Detection ──────────────────────────────────────────

def reset_plugin_cache() -> None:
    """Clear cached detection result. Useful for testing or runtime env changes."""
    global _detected_plugin
    _detected_plugin = None


def detect_seo_plugin() -> str | None:
    """
    Auto-detect active SEO plugin via REST API probing.
    Result is cached; call reset_plugin_cache() to force re-detection.

    Returns: 'yoast' | 'rankmath' | None
    """
    global _detected_plugin

    # Yoast adds 'yoast_head' to post responses
    try:
        resp = httpx.get(
            f"{WP_URL}/wp-json/wp/v2/posts",
            params={"per_page": 1, "status": "any"},
            headers=auth_headers(), timeout=10,
        )
        if resp.status_code == 200:
            posts = resp.json()
            if posts and "yoast_head" in posts[0]:
                _detected_plugin = "yoast"
                return "yoast"
    except httpx.RequestError as e:
        print(f"⚠️  偵測 Yoast 時發生網路錯誤: {e}")
    except httpx.HTTPStatusError as e:
        print(f"⚠️  偵測 Yoast 時 HTTP 錯誤 {e.response.status_code}")

    # Rank Math registers its own REST namespace
    try:
        resp = httpx.get(
            f"{WP_URL}/wp-json/rankmath/v1/getHead",
            headers=auth_headers(), timeout=10,
        )
        # 400 = endpoint exists but missing required params → plugin active
        if resp.status_code in (200, 400):
            _detected_plugin = "rankmath"
            return "rankmath"
    except httpx.RequestError as e:
        print(f"⚠️  偵測 Rank Math 時發生網路錯誤: {e}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:  # 404 = namespace absent = not installed
            print(f"⚠️  偵測 Rank Math 時 HTTP 錯誤 {e.response.status_code}")

    _detected_plugin = None
    return None


def get_plugin(force_plugin: str | None = None) -> str | None:
    """Return forced, cached, or freshly detected plugin name."""
    if force_plugin:
        return force_plugin
    global _detected_plugin
    if _detected_plugin is None:
        detect_seo_plugin()
    return _detected_plugin


def _build_meta_payload(fields: SEOFields, plugin: str) -> dict:
    """Map friendly SEOFields keys → plugin-specific WordPress meta keys."""
    field_map = YOAST_FIELDS if plugin == "yoast" else RANKMATH_FIELDS
    meta: dict = {}
    for key, value in fields.items():
        if value and key in field_map:
            meta[field_map[key]] = "1" if (key == "no_index" and value is True) else value
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
    post_type: str = "posts",
) -> dict:
    """
    Update SEO meta fields for a post or page.

    Args:
        post_id:          WordPress post/page ID.
        seo_title:        SEO title tag. ≤60 chars recommended.
        meta_description: Meta description for search results. 120–155 chars recommended.
        focus_keyword:    Primary keyword for SEO plugin scoring.
        canonical_url:    Canonical URL to prevent duplicate content.
        og_title:         Open Graph title for social sharing.
        og_description:   Open Graph description for social sharing.
        no_index:         True = add noindex (hide from search engines).
        plugin:           Force 'yoast' or 'rankmath'; auto-detect if None.
        post_type:        'posts' or 'pages'.

    Raises:
        RuntimeError: No SEO plugin detected.
        ValueError:   No SEO fields provided.
        httpx.HTTPStatusError: API request failed.
    """
    active_plugin = get_plugin(plugin)
    if not active_plugin:
        raise RuntimeError(
            "無法偵測 SEO 外掛。請確認 Yoast SEO 或 Rank Math 已啟用，"
            "或使用 plugin='yoast'/'rankmath' 手動指定。\n"
            "另請確認 references/functions-php-snippet.md 中的設定已加入 functions.php。"
        )

    fields: SEOFields = {  # type: ignore[assignment]
        k: v for k, v in {
            "seo_title":        seo_title,
            "meta_description": meta_description,
            "focus_keyword":    focus_keyword,
            "canonical_url":    canonical_url,
            "og_title":         og_title,
            "og_description":   og_description,
            "no_index":         no_index,
        }.items() if v
    }

    meta = _build_meta_payload(fields, active_plugin)
    if not meta:
        raise ValueError("至少需要提供一個 SEO 欄位（seo_title / meta_description / ...）")

    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/{post_type}/{post_id}",
        json={"meta": meta},
        headers=auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_seo(post_id: int, post_type: str = "posts") -> dict:
    """
    Read current SEO fields for a post or page.
    Returns friendly keys (seo_title, meta_description, ...) plus raw plugin info.
    """
    resp = httpx.get(
        f"{WP_URL}/wp-json/wp/v2/{post_type}/{post_id}",
        params={"context": "edit"},  # 'edit' exposes meta fields
        headers=auth_headers(), timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    meta = data.get("meta", {})

    active_plugin = get_plugin()
    field_map = YOAST_FIELDS if active_plugin == "yoast" else RANKMATH_FIELDS
    reverse_map = {v: k for k, v in field_map.items()}

    parsed: dict = {
        "post_id":    post_id,
        "post_title": data["title"]["rendered"],
        "plugin":     active_plugin,
        "yoast_head": data.get("yoast_head_json"),
    }
    for meta_key, value in meta.items():
        if meta_key in reverse_map:
            parsed[reverse_map[meta_key]] = value

    return parsed


def batch_update_seo(
    records: list[dict],
    plugin: str | None = None,
) -> list[dict]:
    """
    Bulk-update SEO fields for multiple posts.
    Input records are NOT mutated.

    Each record must contain 'post_id' plus any seo_* fields.
    """
    results = []
    for i, record in enumerate(records, 1):
        # Use .get() — never .pop() — to avoid mutating caller's data
        post_id   = record.get("post_id")
        post_type = record.get("post_type", "posts")
        fields    = {k: v for k, v in record.items() if k not in ("post_id", "post_type")}

        if post_id is None:
            print(f"  [{i}/{len(records)}] ⚠️  跳過（缺少 post_id）")
            results.append({"index": i, "status": "skipped", "reason": "missing post_id"})
            continue

        try:
            update_seo(post_id=int(post_id), plugin=plugin, post_type=post_type, **fields)
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
) -> SEOFields:
    """
    Generate basic SEO field suggestions from article title and HTML content.
    Used as auto_seo fallback in wp_ai_writer.publish_generated().

    Returns a SEOFields dict ready to unpack into update_seo().
    """
    seo_title = title[:60] if len(title) > 60 else title

    plain = re.sub(r"<[^>]+>", "", content).strip()
    meta_description = (plain[:155].rsplit(" ", 1)[0] + "…") if len(plain) > 155 else plain

    return SEOFields(
        seo_title=seo_title,
        meta_description=meta_description,
        focus_keyword=focus_keyword,
        og_title=seo_title,
        og_description=meta_description[:120],
    )


# ── CLI ───────────────────────────────────────────────────────
if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "help"

    if action == "detect":
        if not WP_URL:
            print("❌ WP_URL 未設定")
            sys.exit(1)
        plugin = detect_seo_plugin()
        if plugin:
            print(f"✅ 偵測到 SEO 外掛：{plugin}")
        else:
            print("⚠️  未偵測到 Yoast SEO 或 Rank Math，請確認外掛已安裝並啟用")
    else:
        try:
            check_env()
        except EnvironmentError as e:
            print(e)
            sys.exit(1)

        if action == "get":
            post_id   = int(sys.argv[2])
            post_type = "pages" if "--page" in sys.argv else "posts"
            result = get_seo(post_id, post_type=post_type)
            print(json.dumps(result, ensure_ascii=False, indent=2))

        elif action == "update":
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
            print(f"✅ SEO meta 已更新（外掛：{get_plugin()}）")
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
