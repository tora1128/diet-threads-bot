#!/usr/bin/env python3
"""ダイエット情報収集ツール — Web & note.com & X.com から情報を集めて表示する"""

import argparse
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


# ─────────────────────────────────────────────
# note.com 検索
# ─────────────────────────────────────────────

def search_note(query: str, limit: int = 10) -> list[dict]:
    url = "https://note.com/api/v3/searches"
    params = {"context": "note", "q": query, "size": limit}
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
            # highlight タグを除去
            highlight_clean = highlight.replace("<em>", "").replace("</em>", "")
            results.append({
                "source": "note.com",
                "title": n.get("name", "(タイトルなし)"),
                "url": f"https://note.com/{user_urlname}/n/{key}",
                "summary": highlight_clean[:120].replace("\n", " "),
                "likes": n.get("like_count", 0),
            })
        return results
    except Exception as e:
        console.print(f"[yellow]note.com 取得エラー: {e}[/yellow]")
        return []


# ─────────────────────────────────────────────
# DuckDuckGo 検索（HTML スクレイピング）
# ─────────────────────────────────────────────

def search_web(query: str, limit: int = 10) -> list[dict]:
    url = "https://html.duckduckgo.com/html/"
    try:
        resp = requests.post(
            url,
            data={"q": query},
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
            # DuckDuckGo がリダイレクト URL を返す場合があるので uddg= パラメータを取り出す
            if "uddg=" in raw_url:
                from urllib.parse import urlparse, parse_qs, unquote
                parsed = urlparse(raw_url)
                uddg = parse_qs(parsed.query).get("uddg", [""])
                raw_url = unquote(uddg[0]) if uddg[0] else raw_url
            results.append({
                "source": "Web",
                "title": a.get_text(strip=True),
                "url": raw_url,
                "summary": snippet.get_text(strip=True) if snippet else "",
                "likes": None,
            })
        return results
    except Exception as e:
        console.print(f"[yellow]Web 検索エラー: {e}[/yellow]")
        return []


# ─────────────────────────────────────────────
# X.com 検索（DuckDuckGo 経由、APIキー不要）
# ─────────────────────────────────────────────

def search_x(query: str, limit: int = 10) -> list[dict]:
    """X.com の投稿を DuckDuckGo で検索する（APIキー不要）"""
    url = "https://html.duckduckgo.com/html/"
    x_query = f"site:x.com {query}"
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
            # x.com / twitter.com のURLのみ残す
            if "x.com" not in raw_url and "twitter.com" not in raw_url:
                continue
            results.append({
                "source": "X.com",
                "title": a.get_text(strip=True),
                "url": raw_url,
                "summary": snippet.get_text(strip=True) if snippet else "",
                "likes": None,
            })
            if len(results) >= limit:
                break
        return results
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
    if any(r.get("likes") is not None for r in results):
        table.add_column("♥", style="magenta", width=6, no_wrap=True)

    for i, r in enumerate(results, 1):
        row = [
            str(i),
            r["title"],
            r["summary"] or "-",
            r["url"],
        ]
        if any(r2.get("likes") is not None for r2 in results):
            row.append(str(r["likes"]) if r.get("likes") is not None else "-")
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
  python diet_tool.py --source note
  python diet_tool.py --source x
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
    args = parser.parse_args()

    console.print(
        Panel.fit(
            f"[bold green]ダイエット情報収集ツール[/bold green]\n"
            f"[dim]キーワード: [bold]{args.query}[/bold]  |  "
            f"件数: {args.num}  |  ソース: {args.source}[/dim]",
            border_style="green",
        )
    )

    if args.source in ("all", "web"):
        console.print("\n[bold]Web (DuckDuckGo) を検索中...[/bold]")
        web_results = search_web(args.query, args.num)
        render_results(web_results, "Web 検索結果")

    if args.source in ("all", "note"):
        console.print("\n[bold]note.com を検索中...[/bold]")
        note_results = search_note(args.query, args.num)
        render_results(note_results, "note.com 記事")

    if args.source in ("all", "x"):
        console.print("\n[bold]X.com を検索中...[/bold]")
        x_results = search_x(args.query, args.num)
        render_results(x_results, "X.com 投稿")

    console.print("\n[dim]検索完了[/dim]")


if __name__ == "__main__":
    main()
