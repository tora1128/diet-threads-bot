#!/usr/bin/env python3
"""投稿せずに1週間分の投稿文を確認するスクリプト"""

import argparse
import datetime
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))
from horoscope import generate_horoscope_posts
from love_messages import generate_love_message

DEFAULT_CATEGORIES = ["恋愛運"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="1週間分の投稿文をプレビューする")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="プレビューする日数（デフォルト: 7）",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=["金運", "恋愛運", "総合運"],
        default=DEFAULT_CATEGORIES,
        help="夕方ランキングの対象カテゴリ（デフォルト: 恋愛運）",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="開始日 YYYY-MM-DD（省略時: 今日）",
    )
    parser.add_argument(
        "--output",
        default="weekly_preview.txt",
        help="保存先ファイル（デフォルト: weekly_preview.txt）",
    )
    return parser.parse_args()


def resolve_start_date(value: Optional[str]) -> datetime.date:
    if not value:
        return datetime.date.today()
    return datetime.date.fromisoformat(value)


def build_preview(start_date: datetime.date, days: int, categories: list[str]) -> str:
    sections: list[str] = []

    for offset in range(days):
        today = start_date + datetime.timedelta(days=offset)
        for post_type in ("morning_message", "noon_message"):
            text = generate_love_message(today, post_type)
            label = "朝の恋愛ひとこと" if post_type == "morning_message" else "昼の恋愛ひとこと"
            sections.append(
                "\n".join(
                    [
                        "=" * 40,
                        f"{today.isoformat()} [{label}] ({len(text)}文字)",
                        "-" * 40,
                        text,
                    ]
                )
            )

        for category in categories:
            display_date = today + datetime.timedelta(days=1)
            posts = generate_horoscope_posts(display_date, category, rank_date=today)
            for index, text in enumerate(posts, 1):
                sections.append(
                    "\n".join(
                        [
                            "=" * 40,
                            f"{today.isoformat()} [夕方: 明日の{category}] 投稿{index} ({len(text)}文字)",
                            "-" * 40,
                            text,
                        ]
                    )
                )

    return "\n\n".join(sections) + "\n"


def main() -> None:
    args = parse_args()
    start_date = resolve_start_date(args.start_date)
    preview = build_preview(start_date, args.days, args.categories)

    print(preview)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(preview)
    print(f"保存しました: {args.output}")


if __name__ == "__main__":
    main()
