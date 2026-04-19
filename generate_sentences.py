#!/usr/bin/env python3
"""収集したダイエット記事から 100〜500 文字の文章を生成し、Threads に投稿するツール"""

import argparse
import re
import sys
import os
import time
from typing import Optional

import requests as _requests

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

sys.path.insert(0, os.path.dirname(__file__))
from diet_tool import search_note, search_web

console = Console()

# ─────────────────────────────────────────────
# テキスト処理ユーティリティ
# ─────────────────────────────────────────────

# 広告・ノイズ除去パターン
_NOISE = re.compile(
    r"(^POINT\s*|Contents|目次|\d+\s*\.|【[^】]*】|＜[^＞]*＞|<[^>]*>"
    r"|累計.*?突破|初回.*?引|レンジで.*?だけ|常温|仕出し|冷凍弁当|三ツ星"
    r"|お試し|申込|購入|注文|資料|送料無料|キャンペーン|簡単検索|お近く"
    r"|各社|Click|https?://\S+|www\.\S+|[|｜].*)",
    re.IGNORECASE | re.MULTILINE,
)
_SPACES = re.compile(r"[\s\u3000\n\r\t]+")

# ダイエット・健康関連キーワード（関連性チェック用）
_DIET_WORDS = re.compile(
    r"(ダイエット|食事|栄養|カロリー|体重|痩せ|健康|食生活|運動|脂肪"
    r"|糖質|タンパク質|食べ|レシピ|制限|改善|体型|習慣|バランス|筋肉"
    r"|代謝|食品|摂取|減量|リバウンド|継続|実践)"
)


def clean(text: str) -> str:
    text = _NOISE.sub("", text)
    text = _SPACES.sub("", text)          # 改行・空白をすべて除去
    return text.strip()


def is_relevant(text: str) -> bool:
    """ダイエット・健康に関連する文章か判定"""
    return bool(_DIET_WORDS.search(text))


def split_sentences(text: str) -> list[str]:
    """。！？ で文を分割し、空白行も区切りとする"""
    parts = re.split(r"[。！？\n]", text)
    return [p.strip() for p in parts if p.strip()]


def trim_to_range(text: str, lo: int = 100, hi: int = 500) -> Optional[str]:
    """テキストをlo〜hi文字に収める。無理なら None"""
    text = text.strip()
    if len(text) < lo:
        return None
    if len(text) <= hi:
        return text
    # 句読点で自然に切る
    for i in range(hi, lo - 1, -1):
        if text[i] in "。！？":
            return text[: i + 1]
    # 句読点がなければ強制カット
    return text[:hi]


# ─────────────────────────────────────────────
# 文章候補の抽出
# ─────────────────────────────────────────────

# タイトルを文体に変換するテンプレート（100〜500文字対応）
_TITLE_TEMPLATES = [
    "{title}を試してみたら、思ったより効果があった。食事を見直して運動を加えたら、体が少しずつ変わってきたのがわかった。無理せず続けられる方法を選んだのが、よかったんだと思う。",
    "{title}って最初は半信半疑だったけど、やってみたら全然違った。リバウンドしにくい体になってきたのは、正しいやり方を知れたからだと思う。自分に合ったペースで続けるのが一番だった。",
    "{title}を意識しながら食事を変えたら、カロリーだけじゃなく栄養バランスも気になり始めた。無理な制限はやっぱりストレスになるから、楽しみながらできる方法を探したのは正解だったな。",
    "{title}をちゃんと学んでから取り組んだら、体重管理がぐっと楽になった。短期間で結果を出そうとしてた頃は全然うまくいかなかったけど、生活習慣として続けたら変わってきた。",
    "{title}を知ってから、自分なりのダイエット計画を立てやすくなった。食事・運動・睡眠をバランスよく整えたら、体だけじゃなく気持ちも楽になってきた気がする。",
]

_KEYWORD_TEMPLATES = [
    "{kw}を始めてから、毎日の食事への意識が変わった。少し見直すだけでカロリーが自然と抑えられて、気づいたら体が軽くなってたのには驚いた。継続が一番大事だとつくづく感じた。",
    "{kw}を意識してから、食事の質が変わってきた。栄養バランスを考えて運動も加えたら、健康的に体重が落ちていった。焦らずコツコツ続けたのがよかったんだと思う。",
    "{kw}の基本を押さえてから、ダイエットがぐっとうまくいくようになった。食事制限だけに頼らず、日常で体を動かすようにしたら小さな変化が積み重なっていった。",
    "{kw}はちゃんとやれば健康的に痩せられるとわかった。無理は禁物で、自分の体質に合ったやり方を選んだら、長く続けられるようになった。",
    "{kw}について正しく知ってから、流行に振り回されなくなった。科学的な根拠のある方法を実践したら、安全に体が変わっていくのが実感できた。",
]


def candidates_from_results(results: list[dict], query: str) -> list[str]:
    """記事リストから 100〜500 文字の候補文を抽出・生成"""
    seen: set[str] = set()
    candidates: list[str] = []

    def add(text: str) -> None:
        s = trim_to_range(clean(text))
        if s and s not in seen and len(s) >= 100 and is_relevant(s):
            seen.add(s)
            candidates.append(s)

    # ① サマリー全体を優先的に使う（長文向け）
    for r in results:
        summary = r.get("summary", "")
        add(summary)

    # ② 複数文を結合して100文字以上にする
    for r in results:
        summary = r.get("summary", "")
        sents = split_sentences(summary)
        combined = ""
        for sent in sents:
            combined += sent + "。"
            if len(clean(combined)) >= 100:
                add(combined)
                break

    # ③ タイトルをテンプレートで長文に変換
    import itertools
    for r, tmpl in zip(results, itertools.cycle(_TITLE_TEMPLATES)):
        title = clean(r.get("title", ""))
        if title and len(title) <= 40:
            add(tmpl.format(title=title))

    # ④ キーワードテンプレート（補充）
    kw = query.split()[0] if query else "ダイエット"
    for tmpl in _KEYWORD_TEMPLATES:
        add(tmpl.format(kw=kw))

    return candidates


# ─────────────────────────────────────────────
# 候補の選定
# ─────────────────────────────────────────────

def score(sentence: str) -> float:
    """文章の品質スコア（高いほど良い）"""
    s = 0.0
    ln = len(sentence)
    # 文字数が 150〜400 に近いほど高得点
    s += 2.0 - abs(ln - 275) / 225
    # 。で終わる文は自然
    if sentence.endswith("。"):
        s += 1.0
    # 複数の文が含まれる（内容が充実）
    s += min(sentence.count("。"), 4) * 0.3
    # 動詞・助詞が含まれる（日本語らしさ）
    if re.search(r"[はがをにでもの]", sentence):
        s += 0.5
    # 英数字が多すぎる文は減点
    en_ratio = len(re.findall(r"[a-zA-Z0-9]", sentence)) / max(ln, 1)
    s -= en_ratio * 2
    return s


def select_sentences(candidates: list[str], num: int) -> list[str]:
    """スコアで並べ、内容が重複しないよう上位 num 件を選ぶ"""
    ranked = sorted(candidates, key=score, reverse=True)
    selected: list[str] = []
    for s in ranked:
        # 既選択との先頭 15 文字が被ったら除外（重複防止）
        head = s[:15]
        if any(head in prev or prev[:15] in s for prev in selected):
            continue
        selected.append(s)
        if len(selected) >= num:
            break
    return selected


# ─────────────────────────────────────────────
# Threads 投稿
# ─────────────────────────────────────────────

THREADS_API = "https://graph.threads.net/v1.0"


def threads_post(text: str, user_id: str, token: str) -> Optional[str]:
    """1件の文章を Threads に投稿し、スレッド ID を返す"""
    # Step 1: メディアコンテナ作成
    resp = _requests.post(
        f"{THREADS_API}/{user_id}/threads",
        params={
            "media_type": "TEXT",
            "text": text,
            "access_token": token,
        },
        timeout=15,
    )
    if not resp.ok:
        raise RuntimeError(f"コンテナ作成失敗: {resp.status_code} {resp.text}")
    creation_id = resp.json().get("id")
    if not creation_id:
        raise RuntimeError(f"creation_id が取得できません: {resp.text}")

    # Step 2: 少し待ってから公開（Threads API の推奨）
    time.sleep(5)

    # Step 3: 公開
    resp2 = _requests.post(
        f"{THREADS_API}/{user_id}/threads_publish",
        params={
            "creation_id": creation_id,
            "access_token": token,
        },
        timeout=15,
    )
    if not resp2.ok:
        raise RuntimeError(f"公開失敗: {resp2.status_code} {resp2.text}")
    return resp2.json().get("id")


def post_all(sentences: list[str], user_id: str, token: str, interval: int = 30) -> None:
    """複数の文章を順番に Threads へ投稿する"""
    console.print(f"\n[bold cyan]Threads に {len(sentences)} 件投稿します[/bold cyan]")
    for i, s in enumerate(sentences, 1):
        console.print(f"\n[dim]{i}/{len(sentences)}[/dim] 投稿中: {s[:40]}…")
        try:
            thread_id = threads_post(s, user_id, token)
            console.print(f"  [green]✓ 投稿完了[/green] ID: {thread_id}")
        except RuntimeError as e:
            console.print(f"  [red]✗ 投稿失敗: {e}[/red]")
        # 最後の1件以外はウェイト（連投制限対策）
        if i < len(sentences):
            console.print(f"  [dim]{interval} 秒待機中...[/dim]")
            time.sleep(interval)
    console.print("\n[bold]投稿完了[/bold]")


# ─────────────────────────────────────────────
# 表示
# ─────────────────────────────────────────────

def render_sentences(sentences: list[str], query: str) -> None:
    console.print()
    console.print(Rule(f"[bold green]生成文章 — {query}[/bold green]"))
    console.print()
    for i, s in enumerate(sentences, 1):
        length = len(s)
        color = "green" if 100 <= length <= 500 else "yellow"
        console.print(
            f"[dim]{i:2}.[/dim] {s}  [{color}]({length}文字)[/{color}]"
        )
    console.print()


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ダイエット情報収集 → 100〜500 文字の文章を生成し Threads に投稿",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python generate_sentences.py
  python generate_sentences.py -q "糖質制限"
  python generate_sentences.py -q "食生活" -n 3 --post
  python generate_sentences.py --source note -n 5 --post

Threads 投稿に必要な環境変数:
  export THREADS_USER_ID="あなたの Threads ユーザーID"
  export THREADS_ACCESS_TOKEN="アクセストークン"
        """,
    )
    parser.add_argument(
        "-q", "--query", default="ダイエット",
        help="検索キーワード (デフォルト: ダイエット)",
    )
    parser.add_argument(
        "-n", "--num", type=int, default=5,
        help="生成する文章の本数 (デフォルト: 5)",
    )
    parser.add_argument(
        "--fetch", type=int, default=10,
        help="各ソースから取得する記事数 (デフォルト: 10)",
    )
    parser.add_argument(
        "--source", choices=["all", "web", "note"], default="all",
        help="情報源 (デフォルト: all)",
    )
    parser.add_argument(
        "--post", action="store_true",
        help="生成した文章を Threads に投稿する",
    )
    parser.add_argument(
        "--interval", type=int, default=30,
        help="投稿間隔（秒）。連投制限対策 (デフォルト: 30)",
    )
    args = parser.parse_args()

    console.print(
        Panel.fit(
            f"[bold green]ダイエット情報収集 → 文章生成ツール[/bold green]\n"
            f"[dim]キーワード: [bold]{args.query}[/bold]  |  "
            f"生成本数: {args.num}  |  ソース: {args.source}[/dim]",
            border_style="green",
        )
    )

    # ── 情報収集 ──
    all_results: list[dict] = []

    if args.source in ("all", "web"):
        console.print("\n[bold]Web を検索中...[/bold]", end=" ")
        web = search_web(args.query, args.fetch)
        all_results.extend(web)
        console.print(f"[dim]{len(web)} 件取得[/dim]")

    if args.source in ("all", "note"):
        console.print("[bold]note.com を検索中...[/bold]", end=" ")
        note = search_note(args.query, args.fetch)
        all_results.extend(note)
        console.print(f"[dim]{len(note)} 件取得[/dim]")

    if not all_results:
        console.print("[yellow]記事が見つかりませんでした。[/yellow]")
        sys.exit(0)

    # ── 文章生成（ルールベース） ──
    console.print(f"\n[bold]文章を生成中...[/bold]")
    candidates = candidates_from_results(all_results, args.query)
    sentences = select_sentences(candidates, args.num)

    if not sentences:
        console.print("[yellow]適切な文章が生成できませんでした。--fetch を増やしてみてください。[/yellow]")
        sys.exit(0)

    render_sentences(sentences, args.query)
    console.print(f"[dim]完了（{len(sentences)} 本生成）[/dim]")

    # ── Threads 投稿 ──
    if args.post:
        user_id = os.environ.get("THREADS_USER_ID", "")
        token   = os.environ.get("THREADS_ACCESS_TOKEN", "")
        if not user_id or not token:
            console.print(
                "\n[red]Threads 投稿には環境変数が必要です:[/red]\n"
                "  export THREADS_USER_ID='あなたのユーザーID'\n"
                "  export THREADS_ACCESS_TOKEN='アクセストークン'\n\n"
                "[dim]取得方法: https://developers.facebook.com/ でアプリを作成し、\n"
                "Threads API を追加して長期トークンを発行してください。[/dim]"
            )
            sys.exit(1)
        post_all(sentences, user_id, token, args.interval)


if __name__ == "__main__":
    main()
