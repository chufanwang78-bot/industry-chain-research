#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性迁移脚本：把 屏幕 项目 nodes/*.md 中的企业/新闻表格，
转成 rows 行级条目，作者统一为 zmjjkk，作为“第一个同事”填写的原始信息。
- 幂等：每个节点只迁移一次（rows JSON 里写 migrated 标记）。
- 去重：与已有行字段完全相同则跳过。
- 不修改原 md 文件。
"""
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

import yaml
import rowstore

PROJECT = "屏幕"
AUTHOR = "zmjjkk"
SOURCE_INTERNAL = "产研院内部记录（XMind图）"

PLACEHOLDER_WORDS = ("待研究", "暂无", "待核实", "待补充")


def is_placeholder(s):
    s = (s or "").strip()
    if not s or s == "-":
        return True
    return any(w in s for w in PLACEHOLDER_WORDS)


def split_cells(row):
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [c.strip() for c in row.split("|")]


def parse_tables(text):
    lines = text.splitlines()
    tables = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            tables.append(block)
        else:
            i += 1
    return tables


def is_separator(row):
    return bool(re.match(r"^[\s\-:|]+$", row.strip()))


def classify(header):
    joined = "".join(header)
    has_company = "企业" in joined and ("所在地" in joined or "产品" in joined or "产业化状态" in joined)
    has_news = "日期" in joined and ("事件" in joined or "企业" in joined)
    if has_company and has_news:
        return "news" if "事件" in joined else "company"
    if has_company:
        return "company"
    if has_news:
        return "news"
    return None


def pick(row, header, keys):
    for i, h in enumerate(header):
        hc = h.strip()
        for k in keys:
            if hc == k or hc.startswith(k) or (k in hc):
                if i < len(row):
                    return row[i].strip()
    return ""


LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^\s)]+)\)")


def extract_link(text):
    m = LINK_RE.search(text or "")
    if m:
        label = m.group(1).strip() or "原文链接"
        return label, m.group(2).strip()
    return (text or "").strip(), ""


def node_timestamp(n):
    lu = str(n.get("last_updated", "")).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", lu):
        return lu + " 00:00:00"
    return rowstore._now()


def map_company(header, row):
    company = pick(row, header, ["企业"])
    if is_placeholder(company):
        return None
    loc = pick(row, header, ["所在地"])
    prod = pick(row, header, ["产品"])
    stage = pick(row, header, ["产业化状态"])
    verify = pick(row, header, ["核实状态"])
    if not (loc or prod or stage or verify):
        return None
    entry = {"企业": company, "所在地": loc, "主要产品": prod,
             "产业化状态": stage, "来源": SOURCE_INTERNAL}
    if verify:
        entry["核实状态"] = verify
    return entry


def map_news(header, row):
    date = pick(row, header, ["日期"])
    company = pick(row, header, ["企业"])
    event = pick(row, header, ["事件"])
    if is_placeholder(company) and is_placeholder(event):
        return None
    raw_src = pick(row, header, ["来源"])
    src_label, src_url = extract_link(raw_src)
    status = pick(row, header, ["状态"])
    entry = {"日期": date, "企业": company, "事件": event,
             "来源": src_label, "来源链接": src_url}
    if status:
        entry["状态"] = status
    return entry


def main():
    reg_file = BASE_DIR / "config" / f"nodes-registry-{PROJECT}.yaml"
    reg = yaml.safe_load(reg_file.read_text(encoding="utf-8")) or {}
    nodes = reg.get("nodes", {})
    total_c = total_n = 0
    processed = 0
    skipped = 0
    for nid in sorted(nodes):
        n = nodes[nid]
        rf = n.get("research_file", "")
        if not rf:
            continue
        fp = BASE_DIR / rf
        if not fp.exists():
            continue
        existing = rowstore.load_rows(PROJECT, nid)
        if existing.get("migrated"):
            skipped += 1
            continue
        text = fp.read_text(encoding="utf-8")
        companies, news = [], []
        for block in parse_tables(text):
            if len(block) < 2:
                continue
            header = split_cells(block[0])
            if not header:
                continue
            kind = classify(header)
            if kind is None:
                continue
            for raw in block[1:]:
                if is_separator(raw):
                    continue
                row = split_cells(raw)
                if kind == "company":
                    e = map_company(header, row)
                    if e:
                        companies.append(e)
                else:
                    e = map_news(header, row)
                    if e:
                        news.append(e)
        ts = node_timestamp(n)
        c_added = n_added = 0
        if companies:
            c_added = rowstore.add_rows(PROJECT, nid, "company", companies, author=AUTHOR, timestamp=ts)
        if news:
            n_added = rowstore.add_rows(PROJECT, nid, "news", news, author=AUTHOR, timestamp=ts)
        if c_added or n_added:
            processed += 1
        total_c += c_added
        total_n += n_added
        print(f"{nid} {n.get('name','')}: 企业+{c_added} 新闻+{n_added}")

    print("=" * 40)
    print(f"处理节点: {processed}, 跳过(已迁移): {skipped}")
    print(f"新增企业条目: {total_c}, 新增新闻条目: {total_n}")


if __name__ == "__main__":
    main()