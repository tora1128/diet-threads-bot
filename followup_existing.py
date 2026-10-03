#!/usr/bin/env python3
"""指定したThreads投稿の既存コメントへ、重複を避けて追加案内を返信する。"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Iterable

from auto_reply import _get_all, _relation_id, list_conversation
from generate_sentences import THREADS_API, threads_post


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

FOLLOWUP_REPLY = (
    "ご案内が重なってしまった方は失礼しました。"
    "鑑定についてのやり取りはプロフィールのサイトで行っています。"
    "まだフォローがお済みでない方は、フォロー後にプロフィールのサイトより"
    "追加をお願いします🌙"
)
FOLLOWUP_MARKER = "ご案内が重なってしまった方は失礼しました"


def find_root_post(user_id: str, token: str, shortcode: str) -> dict[str, Any]:
    posts = _get_all(
        f"{THREADS_API}/{user_id}/threads",
        token,
        {
            "fields": "id,text,timestamp,shortcode,permalink,is_reply",
            "limit": 100,
        },
    )
    for post in posts:
        if str(post.get("shortcode") or "").lower() == shortcode.lower():
            if post.get("is_reply"):
                break
            return post
    raise RuntimeError(f"対象投稿が見つかりません: {shortcode}")


def pending_followups(
    root_id: str,
    conversation: Iterable[dict[str, Any]],
    account_username: str,
) -> list[dict[str, Any]]:
    entries = list(conversation)
    completed_ids = {
        _relation_id(entry.get("replied_to"))
        for entry in entries
        if entry.get("is_reply_owned_by_me")
        and FOLLOWUP_MARKER in str(entry.get("text") or "")
    }

    candidates: list[dict[str, Any]] = []
    for entry in entries:
        reply_id = str(entry.get("id") or "")
        if not reply_id or reply_id in completed_ids:
            continue
        if entry.get("is_reply_owned_by_me"):
            continue
        if str(entry.get("username") or "").lower() == account_username.lower():
            continue
        if str(entry.get("hide_status") or "").lower() in {"hidden", "true"}:
            continue

        parent_id = _relation_id(entry.get("replied_to"))
        if parent_id and parent_id != root_id:
            continue
        candidates.append(entry)

    return sorted(candidates, key=lambda item: str(item.get("timestamp") or ""))


def run_followups(
    user_id: str,
    token: str,
    username: str,
    shortcode: str,
    *,
    max_replies: int = 50,
    dry_run: bool = False,
) -> int:
    root = find_root_post(user_id, token, shortcode)
    root_id = str(root.get("id") or "")
    if not root_id:
        raise RuntimeError("対象投稿のIDを取得できません")

    candidates = pending_followups(
        root_id,
        list_conversation(root_id, token),
        username,
    )
    log.info("追加返信の対象: %s件", len(candidates))

    posted = 0
    for reply in candidates:
        reply_id = str(reply.get("id") or "")
        log.info(
            "追加返信: id=%s user=@%s text=%r",
            reply_id,
            reply.get("username") or "unknown",
            str(reply.get("text") or "")[:80],
        )
        if not dry_run:
            threads_post(FOLLOWUP_REPLY, user_id, token, reply_to_id=reply_id)
        posted += 1
        if posted >= max_replies:
            log.info("1回の上限 %s件に到達", max_replies)
            break

    log.info("追加返信完了: %s件", posted)
    return posted


def main() -> None:
    user_id = os.environ.get("THREADS_USER_ID", "")
    token = os.environ.get("THREADS_ACCESS_TOKEN", "")
    username = os.environ.get("THREADS_USERNAME", "mayonaka_letter")
    shortcode = os.environ.get("THREADS_POST_SHORTCODE", "")
    if not user_id or not token or not shortcode:
        raise SystemExit(
            "THREADS_USER_ID / THREADS_ACCESS_TOKEN / THREADS_POST_SHORTCODE が未設定です"
        )

    run_followups(
        user_id,
        token,
        username,
        shortcode,
        max_replies=int(os.environ.get("MAX_FOLLOWUPS_PER_RUN", "50")),
        dry_run=os.environ.get("DRY_RUN", "false").lower() == "true",
    )


if __name__ == "__main__":
    main()
