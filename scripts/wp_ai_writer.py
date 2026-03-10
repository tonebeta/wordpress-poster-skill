#!/usr/bin/env python3
"""
WordPress AI 自動寫文工具 — wordpress-poster skill
整合 Claude API，自動生成文章並發布至 WordPress。

Requires: httpx, python-dotenv, anthropic

Usage:
    # 單篇：給主題，自動生成並存為草稿
    uv run scripts/wp_ai_writer.py write "CAR-T 細胞療法的最新進展"

    # 指定語言、字數、發布狀態
    uv run scripts/wp_ai_writer.py write "Flow cytometry basics" --lang en --words 800 --status publish

    # 批量：從 topics.txt（每行一個主題）批量生成
    uv run scripts/wp_ai_writer.py batch topics.txt
    uv run scripts/wp_ai_writer.py batch topics.txt --status draft --delay 3

    # 互動模式：先預覽再決定是否發布
    uv run scripts/wp_ai_writer.py interactive "文章主題"

.env 需新增:
    ANTHROPIC_API_KEY=sk-ant-...
    WP_AI_DEFAULT_CATEGORY=1        # 選填，預設分類 ID
    WP_AI_DEFAULT_STATUS=draft      # 選填，預設發布狀態
"""
import base64
import json
import os
import sys
import time
import httpx
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

WP_URL        = os.getenv("WP_URL", "").rstrip("/")
USERNAME      = os.getenv("WP_USERNAME", "")
APP_PASSWORD  = os.getenv("WP_APP_PASSWORD", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEFAULT_CAT   = int(os.getenv("WP_AI_DEFAULT_CATEGORY", "0") or "0")
DEFAULT_STATUS = os.getenv("WP_AI_DEFAULT_STATUS", "draft")

CLAUDE_MODEL  = "claude-sonnet-4-20250514"
API_URL       = "https://api.anthropic.com/v1/messages"


def _wp_headers() -> dict:
    token = base64.b64encode(f"{USERNAME}:{APP_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def _claude_headers() -> dict:
    return {
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


# ── AI Generation ─────────────────────────────────────────────

def generate_post(
    topic: str,
    language: str = "zh-TW",
    word_count: int = 600,
    tone: str = "professional",       # professional | casual | educational
    extra_instructions: str = "",
) -> dict:
    """
    Call Claude API to generate a complete WordPress post.

    Returns dict with keys: title, content (HTML), excerpt, tags_suggested
    """
    lang_instruction = {
        "zh-TW": "以繁體中文撰寫",
        "zh-CN": "以简体中文撰写",
        "en":    "Write in English",
        "ja":    "日本語で書いてください",
    }.get(language, f"Write in {language}")

    tone_instruction = {
        "professional":  "語氣專業、嚴謹，適合產業讀者",
        "casual":        "語氣親切、易懂，適合一般大眾",
        "educational":   "語氣清晰、有條理，像教學文章",
    }.get(tone, tone)

    system_prompt = (
        "你是一位專業的部落格內容寫手，擅長撰寫 WordPress 文章。"
        "你必須只回傳 JSON 物件，不要有任何其他文字或 markdown 格式。"
    )

    user_prompt = f"""請為以下主題撰寫一篇完整的 WordPress 部落格文章：

主題：{topic}
語言：{lang_instruction}
字數：約 {word_count} 字
語氣：{tone_instruction}
{f'額外要求：{extra_instructions}' if extra_instructions else ''}

請嚴格回傳以下 JSON 格式（不要包含任何其他文字）：
{{
  "title": "吸引人的文章標題",
  "content": "完整的文章 HTML 內容（使用 <h2>, <h3>, <p>, <ul>, <strong> 等標籤）",
  "excerpt": "文章摘要，100字以內",
  "tags_suggested": ["建議標籤1", "建議標籤2", "建議標籤3"],
  "meta_description": "SEO 描述，120字以內"
}}"""

    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    resp = httpx.post(
        API_URL,
        json=payload,
        headers=_claude_headers(),
        timeout=60,
    )
    resp.raise_for_status()
    raw_text = resp.json()["content"][0]["text"].strip()

    # Strip accidental markdown fences
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
    raw_text = raw_text.strip()

    return json.loads(raw_text)


def _create_wp_post(
    generated: dict,
    status: str = "draft",
    categories: list[int] | None = None,
) -> dict:
    """Push a generated post dict to WordPress."""
    payload: dict = {
        "title":   generated["title"],
        "content": generated["content"],
        "excerpt": generated.get("excerpt", ""),
        "status":  status,
    }
    if categories:
        payload["categories"] = categories
    elif DEFAULT_CAT:
        payload["categories"] = [DEFAULT_CAT]

    resp = httpx.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        json=payload, headers=_wp_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ── High-level Actions ────────────────────────────────────────

def write_post(
    topic: str,
    language: str = "zh-TW",
    word_count: int = 600,
    tone: str = "professional",
    status: str = DEFAULT_STATUS,
    categories: list[int] | None = None,
    extra_instructions: str = "",
    preview: bool = False,
) -> dict:
    """
    Generate a post with Claude and publish to WordPress.

    Args:
        topic:       Article topic or title hint.
        language:    Output language code (zh-TW / zh-CN / en / ja).
        word_count:  Target word/character count.
        tone:        Writing tone (professional / casual / educational).
        status:      WordPress post status (draft / publish / pending).
        categories:  List of category IDs.
        extra_instructions: Extra prompt instructions for Claude.
        preview:     If True, print content but don't post to WordPress.

    Returns:
        dict with 'generated' (Claude output) and 'post' (WP response) keys.
    """
    print(f"🤖 Claude 生成中：「{topic}」…")
    generated = generate_post(
        topic=topic,
        language=language,
        word_count=word_count,
        tone=tone,
        extra_instructions=extra_instructions,
    )

    print(f"   標題：{generated['title']}")
    print(f"   摘要：{generated.get('excerpt','')[:60]}…")
    print(f"   建議標籤：{', '.join(generated.get('tags_suggested', []))}")

    if preview:
        print("\n── 內容預覽 ──────────────────────────")
        # Print first 400 chars of HTML content
        print(generated["content"][:400] + "…")
        return {"generated": generated, "post": None}

    print(f"   發布至 WordPress（status={status}）…")
    post = _create_wp_post(generated, status=status, categories=categories)
    print(f"✅  完成！ID={post['id']}  連結={post['link']}")
    return {"generated": generated, "post": post}


def batch_write(
    topics_file: str,
    language: str = "zh-TW",
    word_count: int = 600,
    tone: str = "professional",
    status: str = DEFAULT_STATUS,
    delay: float = 3.0,
) -> list[dict]:
    """
    Read topics from a text file (one per line) and generate + publish each.
    Skips blank lines and lines starting with #.
    """
    topics = [
        line.strip()
        for line in Path(topics_file).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    print(f"批量寫文：共 {len(topics)} 個主題\n")
    results = []
    for i, topic in enumerate(topics, 1):
        print(f"[{i}/{len(topics)}] 主題：{topic}")
        try:
            result = write_post(topic, language=language, word_count=word_count,
                                tone=tone, status=status)
            results.append({"topic": topic, "status": "ok",
                             "id": result["post"]["id"], "link": result["post"]["link"]})
        except Exception as e:
            print(f"   ❌ 失敗：{e}")
            results.append({"topic": topic, "status": "error", "error": str(e)})
        if delay and i < len(topics):
            print(f"   等待 {delay}s…\n")
            time.sleep(delay)
    return results


def interactive_write(topic: str) -> None:
    """Generate post, show preview, ask for confirmation before publishing."""
    result = write_post(topic, preview=True)
    generated = result["generated"]

    print(f"\n標題：{generated['title']}")
    print(f"摘要：{generated.get('excerpt','')}")
    print("\n選擇操作:")
    print("  1) 存為草稿")
    print("  2) 直接發布")
    print("  3) 取消")
    choice = input("請輸入 1/2/3：").strip()

    if choice == "1":
        post = _create_wp_post(generated, status="draft")
        print(f"✅ 草稿已儲存 ID={post['id']}  {post['link']}")
    elif choice == "2":
        post = _create_wp_post(generated, status="publish")
        print(f"✅ 已發布 ID={post['id']}  {post['link']}")
    else:
        print("已取消。")


# ── CLI ───────────────────────────────────────────────────────
if __name__ == "__main__":
    missing = []
    if not all([WP_URL, USERNAME, APP_PASSWORD]):
        missing.append("WP_URL / WP_USERNAME / WP_APP_PASSWORD")
    if not ANTHROPIC_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if missing:
        print(f"❌ .env 缺少設定：{', '.join(missing)}")
        sys.exit(1)

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    action = sys.argv[1]
    args   = sys.argv[3:]

    def _arg(flag: str, default: str = "") -> str:
        return args[args.index(flag)+1] if flag in args else default

    if action == "write":
        topic = sys.argv[2]
        write_post(
            topic=topic,
            language=_arg("--lang", "zh-TW"),
            word_count=int(_arg("--words", "600")),
            tone=_arg("--tone", "professional"),
            status=_arg("--status", DEFAULT_STATUS),
        )

    elif action == "interactive":
        topic = sys.argv[2]
        interactive_write(topic)

    elif action == "batch":
        topics_file = sys.argv[2]
        results = batch_write(
            topics_file=topics_file,
            language=_arg("--lang", "zh-TW"),
            word_count=int(_arg("--words", "600")),
            status=_arg("--status", DEFAULT_STATUS),
            delay=float(_arg("--delay", "3")),
        )
        log_path = Path(topics_file).stem + "_ai_log.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        ok = sum(1 for r in results if r["status"] == "ok")
        print(f"\n完成：{ok}/{len(results)} 成功，結果存至 {log_path}")

    else:
        print(__doc__)
