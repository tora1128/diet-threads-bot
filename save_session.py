#!/usr/bin/env python3
"""
note.com セッション保存ツール

使い方:
  python3 save_session.py

ブラウザが開くので、note.comにログインしてください。
ログイン後にEnterキーを押すとセッションが保存されます。
"""

import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

SESSION_FILE = os.path.join(os.path.dirname(__file__), ".note_session.json")


def main():
    print("=" * 50)
    print("note.com セッション保存ツール")
    print("=" * 50)
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = ctx.new_page()

        print("ブラウザを開いています...")
        page.goto("https://note.com/login", wait_until="domcontentloaded")

        print()
        print(">>> ブラウザでnote.comにログインしてください <<<")
        print(">>> ログイン後、このスクリプトが自動的に検出します <<<")
        print()

        # ログインを自動検出（最大5分間ポーリング）
        print("ログイン待機中... (最大5分)")
        deadline = time.time() + 300
        logged_in = False
        while time.time() < deadline:
            try:
                result = page.evaluate("""
                    async () => {
                        const r = await fetch('https://note.com/api/v2/current_user', {
                            credentials: 'include'
                        });
                        const d = await r.json();
                        return {status: r.status, urlname: d?.data?.urlname || ''};
                    }
                """)
                if result["status"] == 200 and result["urlname"]:
                    logged_in = True
                    break
                print(f"  未ログイン (status={result['status']}) ... 5秒後に再確認")
            except Exception:
                print("  確認中...")
            time.sleep(5)

        if not logged_in:
            print("✗ タイムアウト: 5分以内にログインしてください")
            browser.close()
            sys.exit(1)

        # ログイン確認
        print("ログイン状態を確認中...")
        try:
            result = page.evaluate("""
                async () => {
                    const r = await fetch('https://note.com/api/v2/current_user', {
                        credentials: 'include'
                    });
                    const d = await r.json();
                    return {status: r.status, urlname: d?.data?.urlname || ''};
                }
            """)

            if result["status"] == 200 and result["urlname"]:
                print(f"✓ ログイン確認: ユーザー = {result['urlname']}")

                # セッション保存
                storage = ctx.storage_state()
                with open(SESSION_FILE, "w") as f:
                    json.dump(storage, f)
                print(f"✓ セッション保存完了: {SESSION_FILE}")
                print()
                print("これで自動投稿スクリプトが使えます:")
                print("  python3 post_to_note.py -q 'ダイエット'")
            else:
                print(f"✗ ログインが確認できませんでした (status={result['status']})")
                print("  note.comにログインしてから再実行してください")
                sys.exit(1)

        except Exception as e:
            print(f"エラー: {e}")
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
