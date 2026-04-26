#!/usr/bin/env python3
"""収集した占い記事から 100〜500 文字の文章を生成し、Threads に投稿するツール"""

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
    r"|各社|Click|https?://\S+|www\.\S+|[|｜].*"
    r"|[①②③④⑤⑥⑦⑧⑨⑩]|[※★☆◆◇▶▷→←＊・•]|\d+[\.．、](?=\s))",
    re.IGNORECASE | re.MULTILINE,
)
_SPACES = re.compile(r"[\s\u3000\n\r\t]+")

# 占い・スピリチュアル関連キーワード（関連性チェック用）
_DIET_WORDS = re.compile(
    r"(占い|運勢|星座|タロット|風水|霊感|恋愛|仕事運|金運|運命|予言|カード"
    r"|星|月|宿命|縁|開運|スピリチュアル|相性|未来|幸運|吉|凶|運気|直感"
    r"|守護|天使|龍神|パワースポット|数秘術|オラクル|チャクラ)"
)


def clean(text: str) -> str:
    text = _NOISE.sub("", text)
    text = _SPACES.sub("", text)          # 改行・空白をすべて除去
    return text.strip()


def is_relevant(text: str) -> bool:
    """占い・スピリチュアルに関連する文章か判定"""
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
    "「{title}」を読んで、自分の運気の流れがちょっとわかった気がした。毎日の行動や選択が、星の動きと連動してるって聞いてから、占いを見る目が変わった。直感を信じることが、意外と大事なんだと思う。",
    "「{title}」に出会ってから、毎朝の過ごし方が変わった。今日の運勢を意識するだけで、なんとなく前向きな気持ちで一日を始められる。小さな心がけが、運気を引き寄せるきっかけになるのかもしれない。",
    "「{title}」って最初は半信半疑だったけど、当たってることが多くて驚いた。星座や生まれた日で、こんなにも傾向が違うんだと知ってから、人との関わり方も少し変わった気がする。",
    "「{title}」を気にするようになってから、恋愛も仕事もなんとなく流れが良くなった。運命って自分の行動次第で変えられると思うけど、占いはその背中をそっと押してくれる感じがする。",
    "「{title}」を知ってから、自分の強みと弱みを客観的に見られるようになった。占いって当たる当たらないだけじゃなくて、自分を深く知るためのヒントになるんだと思う。",
]

_KEYWORD_TEMPLATES = [
    "「{kw}」って、なんとなく気になって調べてみたら思ってたより深かった。毎日の運気の流れを知るだけで、気持ちの持ち方が変わる。自分を信じて、流れに乗ることが大事なんだと思う。",
    "「{kw}」を意識するようになってから、物事の見方がちょっと変わった。偶然と必然の境目って、意外とあいまいで、それを楽しめるようになったら毎日が面白くなった。",
    "「{kw}」で今の自分の状況を見てみたら、なんとなく腑に落ちた。占いって答えを教えてくれるものじゃなくて、自分の心に問いかけるきっかけをくれるものだと思う。",
    "「{kw}」が気になって調べてみたら、自分の運気の周期みたいなものが見えてきた。いい流れのときに思いきって動いて、停滞期はじっくり準備する。それだけで、なんか変わる気がした。",
    "「{kw}」ってスピリチュアルな話だけじゃなくて、自分の内面を見つめ直すヒントがいっぱいある。毎日の小さな選択の積み重ねが、気づいたら運命を変えていたりするんだと思う。",
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
    kw = query.split()[0] if query else "占い"
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


def threads_post(text: str, user_id: str, token: str, reply_to_id: Optional[str] = None) -> Optional[str]:
    """1件の文章を Threads に投稿し、スレッド ID を返す。reply_to_id を指定するとリプライになる"""
    # Step 1: メディアコンテナ作成
    params = {
        "media_type": "TEXT",
        "text": text,
        "access_token": token,
    }
    if reply_to_id:
        params["reply_to_id"] = reply_to_id
    resp = _requests.post(
        f"{THREADS_API}/{user_id}/threads",
        params=params,
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
        description="占い情報収集 → 100〜500 文字の文章を生成し Threads に投稿",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python generate_sentences.py
  python generate_sentences.py -q "星座占い"
  python generate_sentences.py -q "今日の運勢" -n 3 --post
  python generate_sentences.py --source note -n 5 --post

Threads 投稿に必要な環境変数:
  export THREADS_USER_ID="あなたの Threads ユーザーID"
  export THREADS_ACCESS_TOKEN="アクセストークン"
        """,
    )
    parser.add_argument(
        "-q", "--query", default="占い",
        help="検索キーワード (デフォルト: 占い)",
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
            f"[bold green]占い情報収集 → 文章生成ツール[/bold green]\n"
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
