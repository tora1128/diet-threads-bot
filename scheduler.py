#!/usr/bin/env python3
"""毎日の星座ランキングを Threads へ自動投稿するスケジューラー"""

import argparse
import datetime
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from generate_sentences import threads_post
from horoscope import generate_horoscope_posts
from love_messages import generate_love_message

LOG_FILE = os.path.join(os.path.dirname(__file__), "scheduler.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# (投稿時刻JST, 投稿タイプ, カテゴリ, 日付オフセット)
# 日付オフセット1 = 翌日の日付を表示
SCHEDULE = [
    (datetime.time(8, 0), "morning_message", "恋愛運", 0),
    (datetime.time(12, 0), "noon_message", "恋愛運", 0),
    (datetime.time(18, 0), "ranking", "恋愛運", 1),
]


def next_scheduled(now: datetime.datetime) -> tuple:
    """次に実行すべき (実行日時, 投稿タイプ, カテゴリ, 日付オフセット) を返す"""
    today = now.date()
    candidates = []
    for t, post_type, cat, date_offset in SCHEDULE:
        dt = datetime.datetime.combine(today, t)
        if dt <= now:
            dt += datetime.timedelta(days=1)
        candidates.append((dt, post_type, cat, date_offset))
    return min(candidates, key=lambda x: x[0])


def run_once(
    user_id: str,
    token: str,
    category: str,
    date_offset: int = 0,
    dry_run: bool = False,
    post_type: str = "ranking",
) -> None:
    """投稿文生成（ランキングまたは短文）→ Threads に投稿"""
    today = datetime.date.today()
    target_date = today + datetime.timedelta(days=date_offset)
    log.info(f"投稿文生成中 [{post_type}] [{category}] 日付:{target_date}")

    try:
        if post_type == "ranking":
            posts = generate_horoscope_posts(target_date, category, rank_date=today)
        elif post_type in ("morning_message", "noon_message"):
            posts = [generate_love_message(today, post_type)]
        else:
            raise ValueError(f"未対応の投稿タイプ: {post_type}")
    except Exception as e:
        log.error(f"生成エラー: {e}")
        return

    if not posts:
        log.warning("投稿文章を生成できませんでした。スキップします。")
        return

    for i, text in enumerate(posts, 1):
        log.info(f"投稿 {i}/{len(posts)} ({len(text)}文字):\n{text}")

    if dry_run:
        log.info("[DRY RUN] 投稿はスキップしました。")
        return

    parent_id = None
    for i, text in enumerate(posts, 1):
        try:
            thread_id = threads_post(text, user_id, token, reply_to_id=parent_id)
            log.info(f"投稿完了 {i}/{len(posts)} thread_id={thread_id}")
            if i == 1:
                parent_id = thread_id
        except Exception as e:
            log.error(f"投稿失敗 {i}/{len(posts)}: {e}")
            continue

        if i < len(posts):
            time.sleep(10)


def run_scheduler(dry_run: bool = False) -> None:
    user_id = os.environ.get("THREADS_USER_ID", "")
    token   = os.environ.get("THREADS_ACCESS_TOKEN", "")

    if not dry_run and (not user_id or not token):
        log.error(
            "環境変数が設定されていません。\n"
            "  export THREADS_USER_ID='ユーザーID'\n"
            "  export THREADS_ACCESS_TOKEN='アクセストークン'"
        )
        sys.exit(1)

    schedule_str = " / ".join(f"{t.strftime('%H:%M')}[{post_type}:{cat}]" for t, post_type, cat, _ in SCHEDULE)
    log.info(f"スケジューラー起動 | {schedule_str} | dry_run={dry_run}")

    while True:
        now = datetime.datetime.now()
        target_dt, post_type, category, date_offset = next_scheduled(now)

        wait_sec = (target_dt - now).total_seconds()
        log.info(
            f"次回投稿: {target_dt.strftime('%Y-%m-%d %H:%M')} [{post_type}/{category}] まで "
            f"{int(wait_sec // 3600)}時間{int((wait_sec % 3600) // 60)}分待機"
        )
        time.sleep(wait_sec)

        log.info(f"===== 投稿開始 [{post_type}/{category}] {datetime.datetime.now().strftime('%H:%M')} =====")
        run_once(user_id, token, category, date_offset, dry_run, post_type)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="恋愛系の朝昼メッセージと夕方ランキングを Threads に投稿",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # 本番実行（バックグラウンド）
  nohup python3 scheduler.py &

  # 動作確認（実際には投稿しない）
  python3 scheduler.py --dry-run

ログ確認:
  tail -f scheduler.log

停止:
  pkill -f scheduler.py
        """,
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="投稿せずに動作確認だけ行う",
    )
    args = parser.parse_args()

    try:
        run_scheduler(dry_run=args.dry_run)
    except KeyboardInterrupt:
        log.info("スケジューラーを停止しました。")


if __name__ == "__main__":
    main()
