#!/usr/bin/env python3
"""Bing 中文搜索辅助脚本（DDG 被限流时的备用方案）。
用法: python3 bing_search.py "关键词" [结果数] [--news]
输出: 标题 | URL | 摘要
"""
import html as htmlmod
import re
import subprocess
import sys
import urllib.parse


def _fetch(url: str) -> str:
    return subprocess.run(
        ["curl", "-s", "-m", "20", url,
         "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"],
        capture_output=True, text=True,
    ).stdout


def _clean(s: str) -> str:
    return htmlmod.unescape(re.sub("<[^>]+>", "", s)).strip()


def search(query: str, count: int = 10, news: bool = False) -> list:
    q = urllib.parse.quote_plus(query)
    if news:
        url = f"https://cn.bing.com/news/search?q={q}"
        out = _fetch(url)
        results = []
        for m in re.finditer(r'<a[^>]+class="title"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', out):
            results.append((_clean(m.group(2)), m.group(1), ""))
        return results[:count]
    url = f"https://cn.bing.com/search?q={q}&ensearch=0"
    out = _fetch(url)
    results = []
    # b_algo 块解析：链接在 <h2><a href=...>，摘要在 <p ...>
    for block in re.findall(r'<li class="b_algo".*?(?=<li class="b_|</ol>)', out, re.S):
        m = re.search(r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        snip = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
        results.append((_clean(m.group(2)), m.group(1), _clean(snip.group(1)) if snip else ""))
    return results[:count]


if __name__ == "__main__":
    q = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 10
    news_mode = "--news" in sys.argv
    for t, u, s in search(q, n, news_mode):
        print(f"{t}\n  {u}\n  {s}\n")
