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

# ─────────────────────────────────────────────
# ログ設定
# ─────────────────────────────────────────────

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


POST_TIME = datetime.time(18, 0)  # 毎日 18:00 JST に固定（UTC 9:00）


# ─────────────────────────────────────────────
# 星座ランキング生成
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# 1回分の投稿処理
# ─────────────────────────────────────────────

def run_once(user_id: str, token: str, dry_run: bool = False) -> None:
    """星座ランキング生成（3投稿）→ Threads に順次投稿"""
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    log.info(f"星座ランキング生成中 ({tomorrow})")

    try:
        posts = generate_horoscope_posts(tomorrow)
    except Exception as e:
        log.error(f"Claude API エラー: {e}")
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
                parent_id = thread_id  # 2・3投稿目は1投稿目のコメント欄へ
        except Exception as e:
            log.error(f"投稿失敗 {i}/{len(posts)}: {e}")
            continue

        if i < len(posts):
            time.sleep(10)


# ─────────────────────────────────────────────
# メインループ
# ─────────────────────────────────────────────

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

    log.info(f"スケジューラー起動 | 毎日 18:00 JST | dry_run={dry_run}")

    while True:
        now = datetime.datetime.now()
        target = datetime.datetime.combine(now.date(), POST_TIME)
        if target <= now:
            target = datetime.datetime.combine(
                now.date() + datetime.timedelta(days=1), POST_TIME
            )

        wait_sec = (target - now).total_seconds()
        log.info(
            f"次回投稿: {target.strftime('%Y-%m-%d %H:%M')} まで "
            f"{int(wait_sec // 3600)}時間{int((wait_sec % 3600) // 60)}分待機"
        )
        time.sleep(wait_sec)

        log.info(f"===== 投稿開始 {datetime.datetime.now().strftime('%H:%M')} =====")
        run_once(user_id, token, dry_run)


# ─────────────────────────────────────────────
# エントリーポイント
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="毎日 18:00 JST に星座ランキングを Threads に投稿",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # 本番実行（バックグラウンド）
  nohup python3 scheduler.py &

  # 動作確認（実際には投稿しない）
  python3 scheduler.py --dry-run

ログ確認:
  tail -f ~/diet-tool/scheduler.log

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
