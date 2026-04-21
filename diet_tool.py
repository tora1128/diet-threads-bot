#!/usr/bin/env python3
"""ダイエット情報収集ツール — Web & note.com & X.com から情報を集めて表示する"""

import argparse
import re
import sys
import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from rich.text import Text

console = Console()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _parse_buzz_score(text: str) -> int:
    """スニペットからエンゲージメント数を推定する（いいね・RT・万単位に対応）"""
    score = 0
    # 「〇万いいね」「〇万RT」形式
    for m in re.finditer(
        r"([\d,]+(?:\.\d+)?)\s*万\s*(いいね|RT|リツイート|like|retweet)",
        text,
        re.IGNORECASE,
    ):
        val = int(float(m.group(1).replace(",", "")) * 10_000)
        score = max(score, val)
    # 通常の数字 + いいね・RT
    for m in re.finditer(
        r"([\d,]+)\s*(いいね|RT|リツイート|like|retweet)",
        text,
        re.IGNORECASE,
    ):
        val = int(m.group(1).replace(",", ""))
        score = max(score, val)
    return score


# ─────────────────────────────────────────────
# note.com 検索
# ─────────────────────────────────────────────

def search_note(
    query: str,
    limit: int = 10,
    buzz: bool = True,
    min_likes: int = 0,
) -> list[dict]:
    url = "https://note.com/api/v3/searches"
    # バズモード: note API の sort パラメータで人気順を要求
    params = {
        "context": "note",
        "q": query,
        "size": limit * 3 if buzz else limit,
        **({"sort": "like"} if buzz else {}),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        notes = data.get("data", {}).get("notes", {}).get("contents", [])
        results = []
        for n in notes:
            user_urlname = n.get("user", {}).get("urlname", "")
            key = n.get("key", "")
            highlight = n.get("highlight", "") or ""
            highlight_clean = highlight.replace("<em>", "").replace("</em>", "")
            likes = n.get("like_count", 0) or 0
            if likes < min_likes:
                continue
            results.append({
                "source": "note.com",
                "title": n.get("name", "(タイトルなし)"),
                "url": f"https://note.com/{user_urlname}/n/{key}",
                "summary": highlight_clean[:120].replace("\n", " "),
                "likes": likes,
                "buzz_score": likes,
            })
        if buzz:
            results.sort(key=lambda r: r["buzz_score"], reverse=True)
        return results[:limit]
    except Exception as e:
        console.print(f"[yellow]note.com 取得エラー: {e}[/yellow]")
        return []


# ─────────────────────────────────────────────
# DuckDuckGo 検索（HTML スクレイピング）
# ─────────────────────────────────────────────

def search_web(query: str, limit: int = 10, buzz: bool = True) -> list[dict]:
    url = "https://html.duckduckgo.com/html/"
    # バズモード: 話題性を示すキーワードをクエリに追加
    search_query = f"{query} (話題 OR バズ OR トレンド OR 人気)" if buzz else query
    try:
        resp = requests.post(
            url,
            data={"q": search_query},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for div in soup.select(".result__body")[:limit]:
            a = div.find("a", class_="result__a")
            snippet = div.find("a", class_="result__snippet")
            if not a:
                continue
            raw_url = a.get("href", "")
            if "uddg=" in raw_url:
                from urllib.parse import urlparse, parse_qs, unquote
                parsed = urlparse(raw_url)
                uddg = parse_qs(parsed.query).get("uddg", [""])
                raw_url = unquote(uddg[0]) if uddg[0] else raw_url
            snippet_text = snippet.get_text(strip=True) if snippet else ""
            results.append({
                "source": "Web",
                "title": a.get_text(strip=True),
                "url": raw_url,
                "summary": snippet_text,
                "likes": None,
                "buzz_score": _parse_buzz_score(snippet_text),
            })
        if buzz:
            results.sort(key=lambda r: r["buzz_score"], reverse=True)
        return results
    except Exception as e:
        console.print(f"[yellow]Web 検索エラー: {e}[/yellow]")
        return []


# ─────────────────────────────────────────────
# X.com 検索（DuckDuckGo 経由、APIキー不要）
# ─────────────────────────────────────────────

def search_x(query: str, limit: int = 10, buzz: bool = True) -> list[dict]:
    """X.com の投稿を DuckDuckGo で検索する（APIキー不要）"""
    url = "https://html.duckduckgo.com/html/"
    # バズモード: いいね・RT数が高い投稿が引っかかりやすいキーワードを追加
    x_query = f"site:x.com {query}" + (" いいね RT バズ" if buzz else "")
    try:
        resp = requests.post(
            url,
            data={"q": x_query},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for div in soup.select(".result__body")[:limit * 2]:
            a = div.find("a", class_="result__a")
            snippet = div.find("a", class_="result__snippet")
            if not a:
                continue
            raw_url = a.get("href", "")
            if "uddg=" in raw_url:
                from urllib.parse import urlparse, parse_qs, unquote
                parsed = urlparse(raw_url)
                uddg = parse_qs(parsed.query).get("uddg", [""])
                raw_url = unquote(uddg[0]) if uddg[0] else raw_url
            if "x.com" not in raw_url and "twitter.com" not in raw_url:
                continue
            snippet_text = snippet.get_text(strip=True) if snippet else ""
            buzz_score = _parse_buzz_score(snippet_text)
            results.append({
                "source": "X.com",
                "title": a.get_text(strip=True),
                "url": raw_url,
                "summary": snippet_text,
                "likes": None,
                "buzz_score": buzz_score,
            })
            if len(results) >= limit * 2:
                break
        if buzz:
            results.sort(key=lambda r: r["buzz_score"], reverse=True)
        return results[:limit]
    except Exception as e:
        console.print(f"[yellow]X.com 検索エラー: {e}[/yellow]")
        return []


# ─────────────────────────────────────────────
# 表示
# ─────────────────────────────────────────────

def render_results(results: list[dict], source_label: str) -> None:
    if not results:
        console.print(f"[dim]{source_label}: 結果が見つかりませんでした[/dim]")
        return

    has_likes = any(r.get("likes") is not None for r in results)
    has_buzz = any(r.get("buzz_score", 0) > 0 for r in results)

    table = Table(
        box=box.ROUNDED,
        show_lines=True,
        title=f"[bold cyan]{source_label}[/bold cyan]",
        title_style="bold",
        expand=True,
    )
    table.add_column("#", style="dim", width=3, no_wrap=True)
    table.add_column("タイトル", style="bold white", min_width=24)
    table.add_column("概要", style="white")
    table.add_column("URL", style="blue underline", no_wrap=False, min_width=20)
    if has_likes:
        table.add_column("♥ いいね", style="magenta", width=8, no_wrap=True)
    if has_buzz and not has_likes:
        table.add_column("🔥 バズ推定", style="yellow", width=10, no_wrap=True)

    for i, r in enumerate(results, 1):
        row = [
            str(i),
            r["title"],
            r["summary"] or "-",
            r["url"],
        ]
        if has_likes:
            row.append(str(r["likes"]) if r.get("likes") is not None else "-")
        if has_buzz and not has_likes:
            score = r.get("buzz_score", 0)
            row.append(f"{score:,}" if score > 0 else "-")
        table.add_row(*row)

    console.print(table)


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ダイエット情報収集ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python diet_tool.py
  python diet_tool.py -q "糖質制限 レシピ"
  python diet_tool.py -q "intermittent fasting" -n 5
  python diet_tool.py --source web
  python diet_tool.py --source note --min-likes 100
  python diet_tool.py --no-buzz          # バズ優先を無効化
        """,
    )
    parser.add_argument(
        "-q", "--query",
        default="ダイエット",
        help="検索キーワード (デフォルト: ダイエット)",
    )
    parser.add_argument(
        "-n", "--num",
        type=int,
        default=10,
        help="各ソースから取得する件数 (デフォルト: 10)",
    )
    parser.add_argument(
        "--source",
        choices=["all", "web", "note", "x"],
        default="all",
        help="情報源の選択 (デフォルト: all)",
    )
    parser.add_argument(
        "--buzz",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="バズってる投稿を優先表示 (デフォルト: 有効)",
    )
    parser.add_argument(
        "--min-likes",
        type=int,
        default=0,
        metavar="N",
        help="note.com: 最低いいね数フィルタ (デフォルト: 0)",
    )
    args = parser.parse_args()

    buzz_label = "[bold yellow]🔥 バズ優先[/bold yellow]" if args.buzz else "[dim]通常順[/dim]"
    console.print(
        Panel.fit(
            f"[bold green]ダイエット情報収集ツール[/bold green]\n"
            f"[dim]キーワード: [bold]{args.query}[/bold]  |  "
            f"件数: {args.num}  |  ソース: {args.source}[/dim]  |  {buzz_label}",
            border_style="green",
        )
    )

    if args.source in ("all", "web"):
        console.print("\n[bold]Web (DuckDuckGo) を検索中...[/bold]")
        web_results = search_web(args.query, args.num, buzz=args.buzz)
        render_results(web_results, "Web 検索結果")

    if args.source in ("all", "note"):
        console.print("\n[bold]note.com を検索中...[/bold]")
        note_results = search_note(args.query, args.num, buzz=args.buzz, min_likes=args.min_likes)
        render_results(note_results, "note.com 記事")

    if args.source in ("all", "x"):
        console.print("\n[bold]X.com を検索中...[/bold]")
        x_results = search_x(args.query, args.num, buzz=args.buzz)
        render_results(x_results, "X.com 投稿")

    console.print("\n[dim]検索完了[/dim]")


if __name__ == "__main__":
    main()
