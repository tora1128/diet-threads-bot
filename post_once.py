#!/usr/bin/env python3
"""GitHub Actions から呼び出す1回投稿スクリプト"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from scheduler import QUERIES, run_once

user_id = os.environ.get("THREADS_USER_ID", "")
token   = os.environ.get("THREADS_ACCESS_TOKEN", "")

if not user_id or not token:
    print("ERROR: THREADS_USER_ID / THREADS_ACCESS_TOKEN が未設定です")
    sys.exit(1)

# ランダムなキーワードで1件投稿
query = random.choice(QUERIES)
print(f"キーワード: {query}")
run_once(user_id, token, dry_run=False)
