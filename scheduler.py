#!/usr/bin/env python3
"""ダイエット情報を1日4回ランダムな時間に Threads へ自動投稿するスケジューラー"""

import argparse
import datetime
import logging
import os
import random
import sys
import time

import re

# diet-tool の関数を再利用
sys.path.insert(0, os.path.dirname(__file__))
from diet_tool import search_note, search_web, search_x
from generate_sentences import candidates_from_results, select_sentences
from generate_sentences import threads_post

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
# 1回分の投稿処理
# ─────────────────────────────────────────────

QUERIES = [
    "ダイエット 食事",
    "糖質制限",
    "食生活 改善",
    "有酸素運動 ダイエット",
    "ダイエット 継続",
    "カロリー 管理",
    "筋トレ ダイエット",
    "ダイエット レシピ",
]


_STYLE_RULES = [
    # ですます → 語り口調
    (r'できます。',     'できた。'),
    (r'します。',       'した。'),
    (r'なります。',     'なった。'),
    (r'思います。',     'と思う。'),
    (r'大切です。',     '大切だと感じた。'),
    (r'重要です。',     '重要だと気づいた。'),
    (r'ましょう。',     'といいと思う。'),
    (r'でしょう。',     'だと思う。'),
    (r'ください。',     'といいよ。'),
    (r'あります。',     'あった。'),
    (r'います。',       'いた。'),
    (r'わかります。',   'わかった。'),
    (r'つながります。', 'つながっていった。'),
    (r'変わります。',   '変わっていった。'),
    (r'続けます。',     '続けた。'),
    (r'できません。',   'できなかった。'),
    (r'しません。',     'しなかった。'),
    (r'ありません。',   'なかった。'),
]


def polish_text(text: str) -> str:
    """ルールベースで文章を整える（APIなし）"""

    # 1. 外部サイト名・URL・出典を除去
    text = re.sub(r'https?://\S+', '', text)                        # URL
    text = re.sub(r'(出典|参考|引用|via|by|from)[：:]\s*\S+', '', text)  # 出典表記
    text = re.sub(r'【[^】]*】', '', text)                            # 【サイト名】
    text = re.sub(r'「[^」]{1,30}(サイト|メディア|ブログ|note|web|Web)[^」]*」', '', text)

    # 2. ですます調 → 語り口調に変換
    for pattern, replacement in _STYLE_RULES:
        text = re.sub(pattern, replacement, text)

    # 3. 連続する句読点・スペースを整理
    text = re.sub(r'。{2,}', '。', text)
    text = re.sub(r'、{2,}', '、', text)
    text = re.sub(r'[\u3000]+', '', text)
    text = re.sub(r' +', '', text)

    # 4. 文末が句読点で終わっていない場合は「。」を追加
    if text and text[-1] not in '。！？':
        text += '。'

    # 5. 文を分割（1文ずつ改行するため）
    sentences = re.split(r'(?<=[。！？])', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    # 6. 短すぎる文（5文字未満）は除去
    sentences = [s for s in sentences if len(s) >= 5]

    # 7. 1文ずつ改行で結合・500文字以内に収める
    result_lines = []
    total = 0
    for s in sentences:
        if total + len(s) + 1 <= 500:   # +1 は改行文字分
            result_lines.append(s)
            total += len(s) + 1
        else:
            break
    result = '\n'.join(result_lines)

    # 8. 100文字未満なら元のテキストを返す
    if len(result.replace('\n', '')) < 100:
        return text[:500]

    log.info(f"文章整形完了 ({len(text)}→{len(result)}文字)")
    return result


def run_once(user_id: str, token: str, dry_run: bool = False) -> None:
    """記事収集 → 文章生成 → Threads 投稿を1回実行"""
    query = random.choice(QUERIES)
    log.info(f"検索キーワード: {query}")

    # 情報収集
    results = []
    try:
        results += search_web(query, limit=10)
        results += search_note(query, limit=10)
        results += search_x(query, limit=10)
    except Exception as e:
        log.warning(f"検索エラー: {e}")

    if not results:
        log.warning("記事が取得できませんでした。スキップします。")
        return

    # 文章生成
    candidates = candidates_from_results(results, query)
    sentences = select_sentences(candidates, num=1)

    if not sentences:
        log.warning("文章を生成できませんでした。スキップします。")
        return

    text = sentences[0]
    log.info(f"生成文章 ({len(text)}文字): {text}")

    # ルールで文章を整える
    text = polish_text(text)
    log.info(f"投稿文章 ({len(text)}文字): {text}")

    if dry_run:
        log.info("[DRY RUN] 投稿はスキップしました。")
        return

    # Threads 投稿
    try:
        thread_id = threads_post(text, user_id, token)
        log.info(f"投稿完了 thread_id={thread_id}")
    except Exception as e:
        log.error(f"投稿失敗: {e}")


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
        description="ダイエット情報を自動収集して Threads に定期投稿",
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
