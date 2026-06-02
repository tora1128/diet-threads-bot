#!/usr/bin/env python3
"""GitHub Actions から呼び出す星座ランキング1回投稿スクリプト"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from scheduler import run_once

parser = argparse.ArgumentParser(description="指定カテゴリの星座ランキングを1回投稿する")
parser.add_argument(
    "--category",
    choices=["金運", "恋愛運", "総合運"],
    default=os.environ.get("CATEGORY", "総合運"),
    help="投稿カテゴリ（環境変数 CATEGORY でも指定可）",
)
parser.add_argument(
    "--date-offset",
    type=int,
    default=None,
    help="日付オフセット（省略時: 総合運は1、その他は0）",
)
args = parser.parse_args()

date_offset = args.date_offset
if date_offset is None:
    date_offset = 1 if args.category == "総合運" else 0

user_id = os.environ.get("THREADS_USER_ID", "")
token   = os.environ.get("THREADS_ACCESS_TOKEN", "")

if not user_id or not token:
    print("ERROR: THREADS_USER_ID / THREADS_ACCESS_TOKEN が未設定です")
    sys.exit(1)

run_once(user_id, token, args.category, date_offset, dry_run=False)
