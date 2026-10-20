#!/usr/bin/env python3
"""抓取网页正文。支持搜狗 /link 跳转解析。
用法: python3 fetch_page.py <url> [max_chars]
"""
import html as htmlmod
import re
import subprocess
import sys

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def curl(url: str) -> str:
    return subprocess.run(["curl", "-s", "-m", "25", url, "-A", UA],
                          capture_output=True, text=True).stdout


def resolve(url: str) -> str:
    if url.startswith("/link"):
        body = curl("https://www.sogou.com" + url)
        m = re.search(r'window\.location\.replace\("([^"]+)"\)', body)
        if m:
            return m.group(1)
        m = re.search(r"URL='([^']+)'", body)
        if m:
            return m.group(1)
    return url


def fetch_text(url: str, max_chars: int = 7000) -> str:
    url = resolve(url)
    h = curl(url)
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", h, flags=re.S)
    text = re.sub(r"<[^>]+>", "\n", h)
    text = htmlmod.unescape(text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return "URL: " + url + "\n" + "\n".join(lines)[:max_chars]


if __name__ == "__main__":
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 7000
    print(fetch_text(sys.argv[1], n))
