#!/usr/bin/env python3
"""生成した文章を note.com に自動投稿するツール（Playwright + API使用）"""

import argparse
import json
import os
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))
from diet_tool import search_note, search_web
from generate_sentences import candidates_from_results, select_sentences

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


NOTE_EMAIL    = os.environ.get("NOTE_EMAIL", "")
NOTE_PASSWORD = os.environ.get("NOTE_PASSWORD", "")

# セッション保存ファイル（ログイン状態を保持し、繰り返しログインを回避）
SESSION_FILE  = os.path.join(os.path.dirname(__file__), ".note_session.json")


# ─────────────────────────────────────────────
# note.com 投稿
# ─────────────────────────────────────────────

def _launch_ctx(p, headless: bool):
    """ステルスモードでブラウザコンテキストを起動する"""
    browser = p.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    storage = None
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE) as f:
                storage = json.load(f)
            print("保存済みセッションを読み込みました")
        except Exception:
            storage = None

    ctx = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        storage_state=storage,
    )
    ctx.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return browser, ctx


def _login(page, ctx) -> bool:
    """ログインページでサインインし、セッションを保存する"""
    page.goto("https://note.com/login", wait_until="networkidle")
    time.sleep(2)

    if "note.com/login" not in page.url:
        print("すでにログイン済み")
        return True

    page.fill("input#email", NOTE_EMAIL)
    page.fill("input#password", NOTE_PASSWORD)
    page.click('button:has-text("ログイン")')

    try:
        page.wait_for_url(lambda url: "login" not in url, timeout=25000)
    except PlaywrightTimeout:
        shot = os.path.join(os.path.dirname(__file__), "debug_login.png")
        page.screenshot(path=shot)
        raise RuntimeError(
            f"ログインに失敗しました。スクリーンショット: {shot}\n"
            "ヒント: note.comが一時的にブロックしている可能性があります。"
            "15〜30分後に再試行してください。"
        )

    time.sleep(2)
    # セッションを保存
    storage = ctx.storage_state()
    with open(SESSION_FILE, "w") as f:
        json.dump(storage, f)
    print("ログイン完了・セッション保存")
    return True


def _api_fetch(page, method: str, path: str, body: Optional[dict] = None) -> dict:
    """ブラウザのfetchを使って note.com API を呼び出す（クッキー自動送信）"""
    script = """
        async ({method, path, body}) => {
            const opts = {
                method,
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                credentials: 'include',
            };
            if (body !== null) opts.body = JSON.stringify(body);
            const r = await fetch(`https://note.com${path}`, opts);
            let data;
            try { data = await r.json(); } catch { data = {}; }
            return {status: r.status, data};
        }
    """
    return page.evaluate(script, {"method": method, "path": path, "body": body})


def _create_draft(page, title: str, body_html: str) -> dict:
    """下書きを作成し、ノートデータを返す"""
    result = _api_fetch(
        page,
        "POST",
        "/api/v1/text_notes",
        {"name": title, "body": body_html, "status": "draft"},
    )
    if result["status"] not in (200, 201):
        raise RuntimeError(f"下書き作成失敗: {result}")
    data = result["data"]
    if "data" not in data:
        raise RuntimeError(f"APIエラー: {data}")
    return data["data"]


def _open_editor(page, note_key: str, timeout: int = 60) -> bool:
    """エディタページを開き、「公開に進む」ボタンが表示されるまで待つ"""
    edit_url = f"https://editor.note.com/notes/{note_key}/edit"
    page.goto(edit_url, wait_until="domcontentloaded")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            btn = page.query_selector('button:has-text("公開に進む")')
            if btn:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def post_to_note(title: str, body: str, headless: bool = True) -> str:
    """note.com にテキスト記事を投稿し、公開URLを返す"""

    with sync_playwright() as p:
        browser, ctx = _launch_ctx(p, headless)
        page = ctx.new_page()

        try:
            # ── ログイン確認 ──
            _login(page, ctx)

            check = _api_fetch(page, "GET", "/api/v2/current_user")
            if check["status"] != 200:
                print("セッション切れ。再ログイン中...")
                if os.path.exists(SESSION_FILE):
                    os.remove(SESSION_FILE)
                browser.close()
                browser, ctx = _launch_ctx(p, headless)
                page = ctx.new_page()
                _login(page, ctx)
                check = _api_fetch(page, "GET", "/api/v2/current_user")

            user_data = check["data"].get("data", {})
            urlname = user_data.get("urlname", "")
            print(f"ユーザー: {urlname}")

            # ── 下書き作成（タイトルのみAPIで）──
            print("下書きを作成中...")
            note = _create_draft(page, title, "")
            note_key = note["key"]
            print(f"下書き作成完了: key={note_key}")

            # ── エディタを開く ──
            print("エディタを開いています...")
            if not _open_editor(page, note_key, timeout=50):
                raise RuntimeError("エディタが読み込めませんでした")

            print("エディタ読み込み完了")
            time.sleep(1)

            # ── 本文をエディタに入力 ──
            print("本文を入力中...")
            # ProseMirrorエディタの本文エリアをクリックして入力
            body_area = page.query_selector('.ProseMirror, [contenteditable="true"]')
            if body_area:
                body_area.click()
                time.sleep(0.5)
                page.keyboard.type(body)
                time.sleep(1)
                print(f"本文入力完了 ({len(body)}文字)")
            else:
                print("本文エリアが見つかりません（タイトルのみで公開します）")

            # ── 「公開に進む」ボタンをクリック ──
            print("「公開に進む」をクリック中...")
            page.click('button:has-text("公開に進む")')
            time.sleep(3)

            # ── 公開確認ダイアログで「公開する」をクリック ──
            shot = os.path.join(os.path.dirname(__file__), "debug_publish.png")
            page.screenshot(path=shot)
            print(f"公開設定画面のスクリーンショット: {shot}")

            try:
                # 公開設定画面の「投稿する」ボタン
                page.wait_for_selector(
                    'button:has-text("投稿する"), button:has-text("公開する"), button:has-text("今すぐ公開")',
                    timeout=10000,
                )
                page.click('button:has-text("投稿する"), button:has-text("公開する"), button:has-text("今すぐ公開")')
                time.sleep(3)
            except PlaywrightTimeout:
                page.screenshot(path=shot)
                raise RuntimeError(
                    f"「投稿する」ボタンが見つかりませんでした\nスクリーンショット: {shot}"
                )

            # ── 公開後URL取得 ──
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeout:
                pass
            time.sleep(2)

            pub_url = page.url
            # エディタURLのままなら note.com の公開URLに変換
            if "editor.note.com" in pub_url:
                pub_url = f"https://note.com/{urlname}/{note_key}"

            print(f"公開完了: {pub_url}")
            return pub_url

        except Exception as e:
            shot = os.path.join(os.path.dirname(__file__), "debug.png")
            try:
                page.screenshot(path=shot)
            except Exception:
                pass
            raise RuntimeError(f"エラー: {e}\nスクリーンショット: {shot}")
        finally:
            browser.close()


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ダイエット情報を収集して note.com に投稿",
        epilog="""
必要な環境変数:
  export NOTE_EMAIL='your@email.com'
  export NOTE_PASSWORD='yourpassword'

例:
  python post_to_note.py
  python post_to_note.py -q "糖質制限" --show  # ブラウザ表示あり
        """,
    )
    parser.add_argument("-q", "--query", default="ダイエット",
                        help="検索キーワード (デフォルト: ダイエット)")
    parser.add_argument("--fetch", type=int, default=10,
                        help="取得記事数 (デフォルト: 10)")
    parser.add_argument("--show", action="store_true",
                        help="ブラウザを表示して実行（デバッグ用）")
    args = parser.parse_args()

    if not NOTE_EMAIL or not NOTE_PASSWORD:
        print("エラー: 環境変数を設定してください")
        print("  export NOTE_EMAIL='your@email.com'")
        print("  export NOTE_PASSWORD='yourpassword'")
        sys.exit(1)

    # 文章生成
    print(f"「{args.query}」で記事を収集中...")
    results = search_web(args.query, args.fetch) + search_note(args.query, args.fetch)

    if not results:
        print("記事が見つかりませんでした")
        sys.exit(1)

    candidates = candidates_from_results(results, args.query)
    sentences  = select_sentences(candidates, num=1)

    if not sentences:
        print("文章を生成できませんでした")
        sys.exit(1)

    text = sentences[0]
    title = f"{args.query}について"
    print(f"タイトル: {title}")
    print(f"本文({len(text)}文字): {text}")

    # 投稿
    url = post_to_note(title, text, headless=not args.show)
    print(f"\n公開URL: {url}")


if __name__ == "__main__":
    main()
