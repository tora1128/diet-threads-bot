#!/usr/bin/env python3
"""毎日の星座ランキングを Threads へ自動投稿するスケジューラー"""

import argparse
import datetime
import logging
import os
import random
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


# ─────────────────────────────────────────────
# スケジュール生成
# ─────────────────────────────────────────────

def daily_schedule(n: int = 4, start_h: int = 7, end_h: int = 22) -> list[datetime.time]:
    """
    1日を n 等分したスロットからランダムに時刻を1つずつ選ぶ。
    同じ時間帯に偏らないよう均等分散させる。
    """
    total_min = (end_h - start_h) * 60
    slot = total_min // n
    result = []
    for i in range(n):
        lo = start_h * 60 + i * slot
        hi = lo + slot - 1
        m = random.randint(lo, hi)
        result.append(datetime.time(m // 60, m % 60))
    return sorted(result)


# ─────────────────────────────────────────────
# 星座ランキング生成
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# 1回分の投稿処理
# ─────────────────────────────────────────────

def run_once(user_id: str, token: str, dry_run: bool = False) -> None:
    """星座ランキング生成（3投稿）→ Threads に順次投稿"""
    today = datetime.date.today()
    log.info(f"星座ランキング生成中 ({today})")

    try:
        posts = generate_horoscope_posts(today)
    except Exception as e:
        log.error(f"Claude API エラー: {e}")
        return

    if not posts:
        log.warning("投稿文章を生成できませんでした。スキップします。")
        return

    for i, text in enumerate(posts, 1):
        log.info(f"投稿 {i}/{len(posts)} ({len(text)}文字):\n{text}")

        if dry_run:
            continue

        try:
            thread_id = threads_post(text, user_id, token)
            log.info(f"投稿完了 {i}/{len(posts)} thread_id={thread_id}")
        except Exception as e:
            log.error(f"投稿失敗 {i}/{len(posts)}: {e}")
            continue

        if i < len(posts):
            time.sleep(10)

    if dry_run:
        log.info("[DRY RUN] 投稿はスキップしました。")


# ─────────────────────────────────────────────
# メインループ
# ─────────────────────────────────────────────

def run_scheduler(
    posts_per_day: int = 4,
    start_h: int = 7,
    end_h: int = 22,
    dry_run: bool = False,
) -> None:
    user_id = os.environ.get("THREADS_USER_ID", "")
    token   = os.environ.get("THREADS_ACCESS_TOKEN", "")

    if not dry_run and (not user_id or not token):
        log.error(
            "環境変数が設定されていません。\n"
            "  export THREADS_USER_ID='ユーザーID'\n"
            "  export THREADS_ACCESS_TOKEN='アクセストークン'"
        )
        sys.exit(1)

    log.info(
        f"スケジューラー起動 | 1日{posts_per_day}回 | "
        f"{start_h:02d}:00〜{end_h:02d}:00 | dry_run={dry_run}"
    )

    while True:
        today = datetime.date.today()
        schedule = daily_schedule(posts_per_day, start_h, end_h)
        log.info(
            f"【{today}】本日のスケジュール: "
            + ", ".join(t.strftime("%H:%M") for t in schedule)
        )

        now = datetime.datetime.now()

        for t in schedule:
            target = datetime.datetime.combine(today, t)

            if target <= now:
                log.info(f"{t.strftime('%H:%M')} は既に過去のためスキップ")
                continue

            wait_sec = (target - now).total_seconds()
            log.info(
                f"{t.strftime('%H:%M')} まで "
                f"{int(wait_sec // 3600)}時間{int((wait_sec % 3600) // 60)}分待機"
            )
            time.sleep(wait_sec)

            log.info(f"===== 投稿開始 {datetime.datetime.now().strftime('%H:%M')} =====")
            run_once(user_id, token, dry_run)
            now = datetime.datetime.now()

        # 翌日 00:00 まで待機
        tomorrow = datetime.datetime.combine(
            today + datetime.timedelta(days=1), datetime.time(0, 0)
        )
        wait_sec = (tomorrow - datetime.datetime.now()).total_seconds()
        log.info(f"翌日まで {int(wait_sec // 60)} 分待機")
        time.sleep(max(wait_sec, 1))


# ─────────────────────────────────────────────
# エントリーポイント
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="毎日の星座ランキングを Claude API で生成して Threads に定期投稿",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # 本番実行（バックグラウンド）
  nohup python3 scheduler.py &

  # 動作確認（実際には投稿しない）
  python3 scheduler.py --dry-run

  # 1日6回、8〜21時の範囲で投稿
  python3 scheduler.py --posts 6 --start 8 --end 21

ログ確認:
  tail -f ~/diet-tool/scheduler.log

停止:
  pkill -f scheduler.py
        """,
    )
    parser.add_argument(
        "--posts", type=int, default=4,
        help="1日の投稿回数 (デフォルト: 4)",
    )
    parser.add_argument(
        "--start", type=int, default=7,
        help="投稿開始時刻（時） (デフォルト: 7)",
    )
    parser.add_argument(
        "--end", type=int, default=22,
        help="投稿終了時刻（時） (デフォルト: 22)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="投稿せずに動作確認だけ行う",
    )
    args = parser.parse_args()

    try:
        run_scheduler(
            posts_per_day=args.posts,
            start_h=args.start,
            end_h=args.end,
            dry_run=args.dry_run,
        )
    except KeyboardInterrupt:
        log.info("スケジューラーを停止しました。")


if __name__ == "__main__":
    main()
