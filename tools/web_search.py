#!/usr/bin/env python3
"""中文搜索辅助脚本：搜狗(主) + 360(备) + Bing(备)。
用法: python3 web_search.py "关键词" [结果数] [--engine sogou|360|bing]
输出: 标题 | URL | 摘要
"""
import html as htmlmod
import re
import subprocess
import sys
import urllib.parse

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def _fetch(url: str) -> str:
    return subprocess.run(["curl", "-s", "-m", "20", url, "-A", UA],
                          capture_output=True, text=True).stdout


def _clean(s: str) -> str:
    return htmlmod.unescape(re.sub("<[^>]+>", "", s)).strip()


def _resolve_sogou(link: str) -> str:
    """搜狗 /link?url= 是跳转链接，解析出真实 URL。"""
    if not link.startswith("/link"):
        return link
    out = _fetch("https://www.sogou.com" + link)
    m = re.search(r'window\.location\.replace\("([^"]+)"\)', out)
    return m.group(1) if m else link


def search_sogou(query: str, count: int = 10) -> list:
    url = f"https://www.sogou.com/web?query={urllib.parse.quote_plus(query)}"
    h = _fetch(url)
    results = []
    for block in re.findall(r"<h3[^>]*>(.*?)</h3>", h, re.S):
        m = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if m:
            results.append((_clean(m.group(2)), _resolve_sogou(m.group(1)), ""))
        if len(results) >= count:
            break
    return results


def search_360(query: str, count: int = 10) -> list:
    url = f"https://www.so.com/s?q={urllib.parse.quote_plus(query)}"
    h = _fetch(url)
    results = []
    for block in re.findall(r'<li class="res-list.*?(?=<li class="res-list|</ul>)', h, re.S):
        m = re.search(r'<h3[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if m:
            snip = re.search(r'<p[^>]*class="res-desc[^"]*"[^>]*>(.*?)</p>', block, re.S)
            results.append((_clean(m.group(2)), m.group(1), _clean(snip.group(1)) if snip else ""))
        if len(results) >= count:
            break
    return results


def search_bing(query: str, count: int = 10) -> list:
    q = urllib.parse.quote_plus(f'"{query.split()[0]}" ' + " ".join(query.split()[1:])) if " " in query else query
    url = f"https://cn.bing.com/search?q={q}&ensearch=0"
    h = _fetch(url)
    results = []
    for block in re.findall(r'<li class="b_algo".*?(?=<li class="b_|</ol>)', h, re.S):
        m = re.search(r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if m:
            snip = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
            results.append((_clean(m.group(2)), m.group(1), _clean(snip.group(1)) if snip else ""))
        if len(results) >= count:
            break
    return results


ENGINES = {"sogou": search_sogou, "360": search_360, "bing": search_bing}


def search(query: str, count: int = 10, engine: str = "sogou") -> list:
    for name in [engine] + [e for e in ENGINES if e != engine]:
        try:
            r = ENGINES[name](query, count)
            if r:
                return [(t, u, s, name) for t, u, s in r]
        except Exception:
            continue
    return []


if __name__ == "__main__":
    q = sys.argv[1]
    n = next((int(a) for a in sys.argv[2:] if a.isdigit()), 10)
    eng = next((a.split("=")[1] for a in sys.argv if a.startswith("--engine=")), "sogou")
    for t, u, s, e in search(q, n, eng):
        print(f"[{e}] {t}\n  {u}\n  {s}\n")
