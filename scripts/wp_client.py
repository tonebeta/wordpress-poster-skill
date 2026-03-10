"""
WordPress REST API 共用模組 — wordpress-poster skill

提供認證 headers、共用 httpx client，所有腳本 import 此模組，
避免重複實作 _auth_headers()。

Usage (in other scripts):
    from wp_client import WP_URL, auth_headers, wp_get, wp_post, wp_delete
"""
import base64
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

WP_URL       = os.getenv("WP_URL", "").rstrip("/")
USERNAME     = os.getenv("WP_USERNAME", "")
APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")


def auth_headers() -> dict:
    """Build Basic Auth + JSON content-type headers."""
    token = base64.b64encode(f"{USERNAME}:{APP_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def media_headers(filename: str, mime_type: str) -> dict:
    """Build headers for media upload (no Content-Type: application/json)."""
    token = base64.b64encode(f"{USERNAME}:{APP_PASSWORD}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": mime_type,
    }


def check_env() -> None:
    """Raise EnvironmentError if required env vars are missing."""
    missing = [k for k, v in {
        "WP_URL": WP_URL,
        "WP_USERNAME": USERNAME,
        "WP_APP_PASSWORD": APP_PASSWORD,
    }.items() if not v]
    if missing:
        raise EnvironmentError(
            f"❌ 缺少環境變數：{', '.join(missing)}\n"
            "請確認 .env 檔案存在且已設定正確。"
        )


# ── Convenience wrappers ──────────────────────────────────────

def wp_get(path: str, **kwargs) -> httpx.Response:
    resp = httpx.get(
        f"{WP_URL}/wp-json/wp/v2/{path}",
        headers=auth_headers(), timeout=30, **kwargs,
    )
    resp.raise_for_status()
    return resp


def wp_post(path: str, json: dict, timeout: int = 30) -> httpx.Response:
    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/{path}",
        json=json, headers=auth_headers(), timeout=timeout,
    )
    resp.raise_for_status()
    return resp


def wp_delete(path: str, **kwargs) -> httpx.Response:
    resp = httpx.delete(
        f"{WP_URL}/wp-json/wp/v2/{path}",
        headers=auth_headers(), timeout=30, **kwargs,
    )
    resp.raise_for_status()
    return resp
