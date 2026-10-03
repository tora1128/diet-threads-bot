#!/usr/bin/env python3
"""Threads の自分の投稿についた新着コメントへ安全な定型返信を行う。"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import os
import re
import sys
from typing import Any, Iterable

import requests

from generate_sentences import THREADS_API, threads_post


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

REPLY_FIELDS = (
    "id,text,timestamp,username,is_reply,is_reply_owned_by_me,"
    "root_post,replied_to,hide_status"
)

GENERAL_REPLIES = (
    "コメントありがとうございます🌙 今日も心が少し軽くなる時間がありますように。",
    "受け取ってくださってありがとうございます。焦らず、ご自身の気持ちを大切にしてくださいね🌙",
    "コメント嬉しいです。今のあなたに必要な流れが、やさしく動きますように✨",
    "反応してくださってありがとうございます。今日が穏やかな一日になりますように🌿",
    "ご縁をありがとうございます。無理をせず、自分の心の声も大切にしてくださいね🌙",
    "コメントありがとうございます。あなたにとって良い方向へ流れが整いますように✨",
)

EMOJI_REPLIES = (
    "受け取ってくださってありがとうございます🌙 良い流れにつながりますように。",
    "反応ありがとうございます✨ 今日もあなたらしく過ごせますように。",
    "ご縁をありがとうございます🌿 心穏やかな時間が増えますように。",
    "届いて嬉しいです🌙 今の気持ちを大切にしてくださいね。",
)

THANKS_REPLIES = (
    "こちらこそ、読んでくださってありがとうございます🌙",
    "嬉しいお言葉をありがとうございます。励みになります✨",
    "コメントありがとうございます。少しでもお役に立てたなら嬉しいです🌿",
)

FREE_READING_REPLIES = (
    "詳しくはDMにてお送りしますので、フォローしてお待ちください。",
    "鑑定結果はDMへ順番にお届けします。フォローしてお待ちくださいね🌙",
    "詳しい内容はDMでお送りします。フォローのうえ、少しお待ちください✨",
    "鑑定内容はDMにてご案内しますので、フォローしてお待ちください。",
    "順番にDMで詳しくお伝えします。フォローしてお待ちくださいね🌿",
    "詳しい結果はDMへお送りします。フォロー後、そのままお待ちください🌙",
)

# 自動応答で扱うべきではない内容。人が確認できるよう、返信せずログだけ残す。
SENSITIVE_PATTERN = re.compile(
    r"(死にたい|消えたい|自殺|殺す|殺され|暴力|DV|ストーカー|虐待|"
    r"病気|病院|医師|医者|診断|治療|薬|妊娠|借金|詐欺|警察|弁護士|"
    r"住所|電話番号|メールアドレス|個人情報|本名|LINE\s*ID)",
    re.IGNORECASE,
)
HOSTILE_PATTERN = re.compile(
    r"(死ね|消えろ|うざい|ウザい|きもい|キモい|馬鹿|バカ|アホ|嘘つき)",
    re.IGNORECASE,
)
THANKS_PATTERN = re.compile(r"(ありがとう|感謝|参考にな|助かり|嬉しい|うれしい)")
FREE_READING_POST_PATTERN = re.compile(
    r"(無料\s*(鑑定|占い)|鑑定\s*(募集|希望)|無料で.{0,8}(鑑定|占))",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
LETTER_OR_NUMBER_PATTERN = re.compile(r"[A-Za-z0-9ぁ-んァ-ヶ一-龠]")


def _parse_timestamp(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _relation_id(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or "")
    return str(value or "")


def _get_all(url: str, token: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    next_url: str | None = url
    next_params: dict[str, Any] | None = {**params, "access_token": token}

    while next_url:
        response = requests.get(next_url, params=next_params, timeout=20)
        if not response.ok:
            raise RuntimeError(
                f"Threads API 読み込み失敗: {response.status_code} {response.text}"
            )
        payload = response.json()
        results.extend(payload.get("data") or [])
        next_url = (payload.get("paging") or {}).get("next")
        next_params = None
    return results


def list_recent_root_posts(
    user_id: str, token: str, lookback_days: int
) -> list[dict[str, Any]]:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=lookback_days)
    posts = _get_all(
        f"{THREADS_API}/{user_id}/threads",
        token,
        {
            "fields": "id,text,timestamp,has_replies,is_reply",
            "limit": 50,
        },
    )
    roots: list[dict[str, Any]] = []
    for post in posts:
        timestamp = _parse_timestamp(str(post.get("timestamp") or ""))
        if timestamp and timestamp < cutoff:
            continue
        if post.get("is_reply"):
            continue
        if not post.get("has_replies"):
            continue
        roots.append(post)
    return roots


def list_conversation(root_id: str, token: str) -> list[dict[str, Any]]:
    return _get_all(
        f"{THREADS_API}/{root_id}/conversation",
        token,
        {"fields": REPLY_FIELDS, "reverse": "false", "limit": 100},
    )


def should_skip_reply(text: str) -> str | None:
    compact = re.sub(r"\s+", " ", (text or "").strip())
    if not compact:
        return "本文なし"
    if len(compact) > 80:
        return "長文"
    if "?" in compact or "？" in compact:
        return "質問"
    if URL_PATTERN.search(compact):
        return "URLを含む"
    if SENSITIVE_PATTERN.search(compact):
        return "要手動確認の内容"
    if HOSTILE_PATTERN.search(compact):
        return "攻撃的な内容"
    return None


def is_free_reading_post(text: str) -> bool:
    compact = re.sub(r"\s+", " ", (text or "").strip())
    return bool(FREE_READING_POST_PATTERN.search(compact))


def select_reply_text(reply_id: str, text: str, root_text: str = "") -> str:
    if is_free_reading_post(root_text):
        digest = hashlib.sha256(reply_id.encode("utf-8")).digest()
        return FREE_READING_REPLIES[
            int.from_bytes(digest[:2], "big") % len(FREE_READING_REPLIES)
        ]

    compact = re.sub(r"\s+", " ", text.strip())
    if THANKS_PATTERN.search(compact):
        choices = THANKS_REPLIES
    elif len(compact) <= 12 and not LETTER_OR_NUMBER_PATTERN.search(compact):
        choices = EMOJI_REPLIES
    else:
        choices = GENERAL_REPLIES

    digest = hashlib.sha256(reply_id.encode("utf-8")).digest()
    return choices[int.from_bytes(digest[:2], "big") % len(choices)]


def unanswered_direct_replies(
    root_id: str,
    conversation: Iterable[dict[str, Any]],
    account_username: str,
    lookback_hours: int,
) -> list[dict[str, Any]]:
    entries = list(conversation)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=lookback_hours)
    answered_ids = {
        _relation_id(entry.get("replied_to"))
        for entry in entries
        if entry.get("is_reply_owned_by_me")
    }

    candidates: list[dict[str, Any]] = []
    for entry in entries:
        reply_id = str(entry.get("id") or "")
        if not reply_id or reply_id in answered_ids:
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

        timestamp = _parse_timestamp(str(entry.get("timestamp") or ""))
        if timestamp and timestamp < cutoff:
            continue
        candidates.append(entry)

    return sorted(candidates, key=lambda item: str(item.get("timestamp") or ""))


def run_auto_reply(
    user_id: str,
    token: str,
    username: str,
    *,
    max_replies: int = 5,
    root_lookback_days: int = 7,
    reply_lookback_hours: int = 48,
    dry_run: bool = False,
) -> int:
    posted = 0
    roots = list_recent_root_posts(user_id, token, root_lookback_days)
    log.info("返信のある最近の親投稿: %s件", len(roots))

    for root in roots:
        root_id = str(root.get("id") or "")
        if not root_id:
            continue
        conversation = list_conversation(root_id, token)
        replies = unanswered_direct_replies(
            root_id, conversation, username, reply_lookback_hours
        )

        for reply in replies:
            reply_id = str(reply.get("id") or "")
            text = str(reply.get("text") or "")
            skip_reason = should_skip_reply(text)
            if skip_reason:
                log.info(
                    "自動返信を見送り: id=%s user=@%s reason=%s",
                    reply_id,
                    reply.get("username") or "unknown",
                    skip_reason,
                )
                continue

            response_text = select_reply_text(
                reply_id,
                text,
                str(root.get("text") or ""),
            )
            log.info(
                "返信対象: id=%s user=@%s text=%r response=%r",
                reply_id,
                reply.get("username") or "unknown",
                text[:80],
                response_text,
            )
            if not dry_run:
                threads_post(response_text, user_id, token, reply_to_id=reply_id)
            posted += 1
            if posted >= max_replies:
                log.info("1回の上限 %s件に到達", max_replies)
                return posted

    log.info("自動返信完了: %s件", posted)
    return posted


def main() -> None:
    user_id = os.environ.get("THREADS_USER_ID", "")
    token = os.environ.get("THREADS_ACCESS_TOKEN", "")
    username = os.environ.get("THREADS_USERNAME", "mayonaka_letter")
    if not user_id or not token:
        raise SystemExit("THREADS_USER_ID / THREADS_ACCESS_TOKEN が未設定です")

    run_auto_reply(
        user_id,
        token,
        username,
        max_replies=int(os.environ.get("MAX_REPLIES_PER_RUN", "5")),
        root_lookback_days=int(os.environ.get("ROOT_POST_LOOKBACK_DAYS", "7")),
        reply_lookback_hours=int(os.environ.get("REPLY_LOOKBACK_HOURS", "48")),
        dry_run=os.environ.get("DRY_RUN", "false").lower() == "true",
    )


if __name__ == "__main__":
    main()
