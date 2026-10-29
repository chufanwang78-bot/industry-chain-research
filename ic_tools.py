#!/usr/bin/env python3
"""
产业链拆解工作流 — 辅助工具
用法: python3 ic_tools.py <command> [options]

命令:
  init                          初始化/重置节点台账
  status [industry]             查看全局研究进度
  show <节点编号>               查看节点详情
  new <父编号> <名称> [类型]    创建新节点
  update <编号> [--status S]    更新节点状态
  next [--all]                  查看下一个待研究节点
  tree [--depth N]              显示产业链树状结构
  report [-o file]              生成进度报告
  check                         运行质量检查
  log <message>                 添加工作流日志
"""

import sys
import os
import yaml
import argparse
from datetime import datetime
from pathlib import Path

# === 路径配置 ===
BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"
NODES_DIR = BASE_DIR / "nodes"
SOURCES_DIR = BASE_DIR / "sources"
OUTPUTS_DIR = BASE_DIR / "outputs"
LOGS_DIR = BASE_DIR / "logs"
TEMPLATES_DIR = BASE_DIR / "templates"

WORKFLOW_CONFIG = CONFIG_DIR / "workflow.yaml"
NODES_REGISTRY = CONFIG_DIR / "nodes-registry.yaml"
SOURCE_INDEX = SOURCES_DIR / "source-index.yaml"
WORKFLOW_LOG = LOGS_DIR / "workflow-log.md"


# === 工具函数 ===

def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def load_registry() -> dict:
    return load_yaml(NODES_REGISTRY)


def save_registry(data: dict):
    save_yaml(NODES_REGISTRY, data)


def load_workflow() -> dict:
    return load_yaml(WORKFLOW_CONFIG)


def fmt_status(s: str) -> str:
    icons = {"TODO": "⬜", "WIP": "🔵", "DONE": "✅", "GAP": "⚠️", "HOLD": "⏸️"}
    return f"{icons.get(s, '❓')} {s}"


def fmt_relation(r: str) -> str:
    m = {"TAX": "分类", "PROC": "工艺", "SUPP": "供应"}
    return m.get(r, r)


# === 命令实现 ===

def cmd_init(args):
    """从 workflow.yaml 的初始分类创建节点台账"""
    wf = load_workflow()
    if not wf:
        print("错误: config/workflow.yaml 不存在或为空")
        return

    industry = wf.get("research", {}).get("current_industry", "芯片")
    industries = wf.get("industries", {})

    if industry not in industries:
        print(f"错误: workflow.yaml 中未定义产业 '{industry}'")
        return

    tree = industries[industry]
    top_cats = tree.get("top_categories", [])

    registry = load_registry()
    if registry.get("nodes") and not args.force:
        print("节点台账已存在。使用 --force 重置（将丢失所有研究状态）。")
        print(f"当前已有 {len(registry.get('nodes', {}))} 个节点。")
        return

    nodes = {}
    count = 0

    def add_node(nid, name, ntype, parent, description=""):
        nonlocal count
        nodes[nid] = {
            "id": nid,
            "name": name,
            "relation_type": ntype,
            "parent": parent,
            "status": "TODO",
            "priority": "medium",
            "description": description,
            "children": [],
            "research_file": "",
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
        }
        count += 1

    def process_cat(cat, parent_id=None):
        cid = cat["id"]
        add_node(cid, cat["name"], cat.get("relation_type", "TAX"), parent_id,
                 cat.get("description", ""))
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"].append(cid)
        for sub in cat.get("subcategories", []):
            process_cat(sub, cid)

    for cat in top_cats:
        process_cat(cat)

    registry = {
        "industry": industry,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "nodes": nodes,
    }
    save_registry(registry)

    # 创建节点目录
    ic_dir = NODES_DIR / industry.replace(" ", "-")
    ic_dir.mkdir(parents=True, exist_ok=True)

    # 初始化来源台账
    if not SOURCE_INDEX.exists():
        save_yaml(SOURCE_INDEX, {"sources": [], "next_id": 1})

    # 初始化日志
    if not WORKFLOW_LOG.exists():
        WORKFLOW_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(WORKFLOW_LOG, "w", encoding="utf-8") as f:
            f.write(f"# 工作流运行日志\n\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — 初始化\n\n"
                    f"产业: {industry}\n初始节点数: {count}\n")

    print(f"✅ 初始化完成: {industry}产业")
    print(f"   节点数: {count}")
    print(f"   台账: {NODES_REGISTRY}")
    print(f"   节点目录: {ic_dir}")


def cmd_status(args):
    """显示全局研究进度"""
    reg = load_registry()
    if not reg.get("nodes"):
        print("节点台账为空。请先运行: python3 ic_tools.py init")
        return

    nodes = reg["nodes"]
    industry = reg.get("industry", "未知")

    # 统计
    status_count = {}
    for n in nodes.values():
        s = n.get("status", "TODO")
        status_count[s] = status_count.get(s, 0) + 1

    total = len(nodes)
    done = status_count.get("DONE", 0)
    wip = status_count.get("WIP", 0)
    todo = status_count.get("TODO", 0)
    gap = status_count.get("GAP", 0)
    hold = status_count.get("HOLD", 0)

    print(f"\n{'='*50}")
    print(f"  产业链研究进度 — {industry}")
    print(f"{'='*50}")
    print(f"  总节点数: {total}")
    print(f"  ✅ 已完成: {done}  ({done*100//max(total,1)}%)")
    print(f"  🔵 研究中: {wip}")
    print(f"  ⬜ 未开始: {todo}")
    print(f"  ⚠️  待补充: {gap}")
    print(f"  ⏸️  暂  缓: {hold}")
    print(f"{'='*50}")

    # 按一级分类展示
    top_nodes = {k: v for k, v in nodes.items()
                 if v.get("parent") is None or "." not in k}

    for nid in sorted(top_nodes.keys()):
        n = top_nodes[nid]
        children = n.get("children", [])
        child_done = sum(1 for c in children if nodes.get(c, {}).get("status") == "DONE")
        child_total = len(children)
        bar_len = 20
        filled = int(bar_len * child_done / max(child_total, 1))
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  {nid} {n['name']:12s} [{bar}] {child_done}/{child_total} 子节点完成")

    print()


def cmd_show(args):
    """显示节点详情"""
    reg = load_registry()
    nodes = reg.get("nodes", {})
    nid = args.node_id

    if nid not in nodes:
        print(f"错误: 节点 '{nid}' 不存在")
        # 尝试模糊匹配
        matches = [k for k in nodes if nid in k or nodes[k].get("name", "") == nid]
        if matches:
            print(f"  是否想查找: {', '.join(matches[:5])}")
        return

    n = nodes[nid]
    print(f"\n{'='*50}")
    print(f"  节点 {nid}: {n['name']}")
    print(f"{'='*50}")
    print(f"  关系类型: {fmt_relation(n.get('relation_type', ''))}")
    print(f"  上级节点: {n.get('parent', '无（顶级节点）')}")
    print(f"  研究状态: {fmt_status(n.get('status', 'TODO'))}")
    print(f"  优先级:   {n.get('priority', 'medium')}")
    print(f"  说明:     {n.get('description', '')}")
    print(f"  子节点:   {', '.join(n.get('children', [])) or '无'}")
    print(f"  更新日期: {n.get('last_updated', '')}")

    # 检查研究文件
    rf = n.get("research_file", "")
    if rf:
        rf_path = BASE_DIR / rf
        if rf_path.exists():
            size = rf_path.stat().st_size
            print(f"  研究文件: {rf} ({size} bytes)")
        else:
            print(f"  研究文件: {rf} (文件缺失!)")
    else:
        print(f"  研究文件: 未创建")

    print()


def cmd_new(args):
    """创建新节点"""
    reg = load_registry()
    nodes = reg.setdefault("nodes", {})
    parent_id = args.parent_id
    name = args.name
    ntype = args.node_type or "TAX"

    if parent_id not in nodes and parent_id != "root":
        print(f"错误: 父节点 '{parent_id}' 不存在")
        return

    # 生成子节点编号
    if parent_id == "root":
        existing_top = [k for k in nodes if "." not in k]
        next_num = max([int(k) for k in existing_top if k.isdigit()], default=0) + 1
        nid = f"{next_num:02d}"
    else:
        parent = nodes[parent_id]
        existing_children = parent.get("children", [])
        if existing_children:
            last = existing_children[-1]
            last_num = int(last.split(".")[-1])
        else:
            last_num = 0
        next_num = last_num + 1
        nid = f"{parent_id}.{next_num:02d}"

    if nid in nodes:
        print(f"错误: 节点编号 '{nid}' 已存在")
        return

    nodes[nid] = {
        "id": nid,
        "name": name,
        "relation_type": ntype,
        "parent": parent_id if parent_id != "root" else None,
        "status": "TODO",
        "priority": args.priority or "medium",
        "description": "",
        "children": [],
        "research_file": "",
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
    }

    if parent_id != "root":
        nodes[parent_id]["children"].append(nid)

    save_registry(reg)
    print(f"✅ 创建节点: {nid} {name}")
    print(f"   类型: {fmt_relation(ntype)}")
    print(f"   父节点: {parent_id}")


def cmd_update(args):
    """更新节点状态"""
    reg = load_registry()
    nodes = reg.get("nodes", {})
    nid = args.node_id

    if nid not in nodes:
        print(f"错误: 节点 '{nid}' 不存在")
        return

    n = nodes[nid]
    changed = []

    if args.status:
        old = n.get("status", "TODO")
        n["status"] = args.status
        changed.append(f"状态: {old} → {args.status}")

    if args.priority:
        old = n.get("priority", "medium")
        n["priority"] = args.priority
        changed.append(f"优先级: {old} → {args.priority}")

    if args.file:
        n["research_file"] = args.file
        changed.append(f"研究文件: {args.file}")

    n["last_updated"] = datetime.now().strftime("%Y-%m-%d")

    save_registry(reg)
    print(f"✅ 更新节点 {nid} ({n['name']})")
    for c in changed:
        print(f"   {c}")


def cmd_next(args):
    """显示待研究节点"""
    reg = load_registry()
    nodes = reg.get("nodes", {})

    # 优先级排序
    priority_order = {"high": 0, "medium": 1, "low": 2}

    if args.all:
        targets = [n for n in nodes.values() if n.get("status") in ("TODO", "GAP")]
    else:
        targets = [n for n in nodes.values() if n.get("status") == "TODO"]

    targets.sort(key=lambda x: (
        priority_order.get(x.get("priority", "medium"), 1),
        x.get("id", "")
    ))

    if not targets:
        print("没有待研究的节点！")
        return

    print(f"\n待研究节点 ({len(targets)} 个):")
    print(f"{'编号':8s} {'名称':25s} {'类型':6s} {'优先级':6s} {'父节点':10s}")
    print("-" * 65)
    for n in targets[:20]:
        print(f"{n['id']:8s} {n['name']:25s} "
              f"{fmt_relation(n.get('relation_type', '')):6s} "
              f"{n.get('priority', ''):6s} {str(n.get('parent', '')):10s}")

    if len(targets) > 20:
        print(f"... 还有 {len(targets)-20} 个节点")


def cmd_tree(args):
    """显示产业链树状结构"""
    reg = load_registry()
    nodes = reg.get("nodes", {})
    max_depth = args.depth or 3

    status_icons = {"TODO": "⬜", "WIP": "🔵", "DONE": "✅", "GAP": "⚠️", "HOLD": "⏸️"}

    top_nodes = sorted([k for k in nodes if "." not in k],
                       key=lambda x: int(x) if x.isdigit() else x)

    def print_node(nid, depth=0):
        if depth > max_depth:
            return
        n = nodes.get(nid)
        if not n:
            return
        indent = "  " * depth
        icon = status_icons.get(n.get("status", "TODO"), "❓")
        rel = fmt_relation(n.get("relation_type", ""))
        print(f"{indent}{icon} {nid} {n['name']} [{rel}]")
        for c in sorted(n.get("children", [])):
            print_node(c, depth + 1)

    for nid in top_nodes:
        print_node(nid)


def cmd_report(args):
    """生成进度报告"""
    reg = load_registry()
    nodes = reg.get("nodes", {})
    industry = reg.get("industry", "未知")

    if not nodes:
        print("节点台账为空。")
        return

    status_count = {}
    for n in nodes.values():
        s = n.get("status", "TODO")
        status_count[s] = status_count.get(s, 0) + 1

    total = len(nodes)
    done = status_count.get("DONE", 0)

    lines = [
        f"# 产业链研究进度报告 — {industry}",
        f"\n> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"\n## 总体进度",
        f"\n| 指标 | 数值 |",
        f"|------|------|",
        f"| 总节点数 | {total} |",
        f"| 已完成 | {done} ({done*100//max(total,1)}%) |",
        f"| 研究中 | {status_count.get('WIP', 0)} |",
        f"| 未开始 | {status_count.get('TODO', 0)} |",
        f"| 待补充 | {status_count.get('GAP', 0)} |",
        f"| 暂缓 | {status_count.get('HOLD', 0)} |",
    ]

    # 按一级分类
    lines.append(f"\n## 各环节进度\n")
    lines.append(f"| 环节 | 总节点 | 已完成 | 完成率 | 状态 |")
    lines.append(f"|------|--------|--------|--------|------|")

    top_nodes = sorted([k for k in nodes if "." not in k],
                       key=lambda x: int(x) if x.isdigit() else x)
    for nid in top_nodes:
        n = nodes[nid]
        children = n.get("children", [])
        if children:
            c_total = len(children)
            c_done = sum(1 for c in children if nodes.get(c, {}).get("status") == "DONE")
            pct = c_done * 100 // max(c_total, 1)
        else:
            c_total = 1
            c_done = 1 if n.get("status") == "DONE" else 0
            pct = c_done * 100
        lines.append(f"| {n['name']} | {c_total} | {c_done} | {pct}% | {fmt_status(n.get('status','TODO'))} |")

    # 已完成节点列表
    done_nodes = [n for n in nodes.values() if n.get("status") == "DONE"]
    if done_nodes:
        lines.append(f"\n## 已完成节点\n")
        for n in sorted(done_nodes, key=lambda x: x.get("id", "")):
            lines.append(f"- **{n['id']}** {n['name']} ({n.get('last_updated', '')})")

    # WIP节点
    wip_nodes = [n for n in nodes.values() if n.get("status") == "WIP"]
    if wip_nodes:
        lines.append(f"\n## 研究中节点\n")
        for n in sorted(wip_nodes, key=lambda x: x.get("id", "")):
            lines.append(f"- **{n['id']}** {n['name']}")

    report_text = "\n".join(lines) + "\n"

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = OUTPUTS_DIR / "reports" / f"progress-{datetime.now().strftime('%Y%m%d')}.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(report_text)
    print(f"\n📄 报告已保存: {out_path}")


def cmd_check(args):
    """运行质量检查"""
    reg = load_registry()
    nodes = reg.get("nodes", {})
    issues = []

    for nid, n in sorted(nodes.items()):
        # 检查状态
        status = n.get("status", "TODO")
        rf = n.get("research_file", "")

        if status == "DONE" and not rf:
            issues.append(f"⚠️  {nid} {n['name']}: 标记为DONE但没有研究文件")

        if status == "DONE" and rf:
            rf_path = BASE_DIR / rf
            if not rf_path.exists():
                issues.append(f"⚠️  {nid} {n['name']}: 研究文件不存在 ({rf})")

        # 检查子节点一致性
        for c in n.get("children", []):
            if c not in nodes:
                issues.append(f"❌ {nid}: 子节点 '{c}' 在台账中不存在")
            elif nodes[c].get("parent") != nid:
                issues.append(f"❌ {nid}: 子节点 '{c}' 的父节点指向 '{nodes[c].get('parent')}' 而不是 '{nid}'")

        # 检查父节点一致性
        parent = n.get("parent")
        if parent and parent in nodes:
            if nid not in nodes[parent].get("children", []):
                issues.append(f"❌ {nid}: 不在父节点 '{parent}' 的子节点列表中")

    # 检查来源
    src = load_yaml(SOURCE_INDEX)
    sources = src.get("sources", [])
    if not sources:
        issues.append("ℹ️  来源台账为空（初始阶段正常）")

    if issues:
        print(f"\n质量检查结果 ({len(issues)} 个问题):")
        print("=" * 50)
        for i in issues:
            print(f"  {i}")
    else:
        print("\n✅ 质量检查通过，未发现问题。")
    print()


def cmd_log(args):
    """添加日志"""
    WORKFLOW_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not WORKFLOW_LOG.exists():
        with open(WORKFLOW_LOG, "w", encoding="utf-8") as f:
            f.write("# 工作流运行日志\n")

    with open(WORKFLOW_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n## {timestamp}\n{args.message}\n")

    print(f"✅ 日志已记录: {WORKFLOW_LOG}")


# === 主入口 ===

def main():
    parser = argparse.ArgumentParser(description="产业链拆解工作流辅助工具")
    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="初始化节点台账")
    p_init.add_argument("--force", action="store_true", help="强制重置")

    # status
    p_status = sub.add_parser("status", help="查看全局进度")
    p_status.add_argument("industry", nargs="?", help="产业名称")

    # show
    p_show = sub.add_parser("show", help="查看节点详情")
    p_show.add_argument("node_id", help="节点编号")

    # new
    p_new = sub.add_parser("new", help="创建新节点")
    p_new.add_argument("parent_id", help="父节点编号 (或 'root')")
    p_new.add_argument("name", help="节点名称")
    p_new.add_argument("--type", dest="node_type", choices=["TAX", "PROC", "SUPP"],
                       default="TAX", help="关系类型")
    p_new.add_argument("--priority", choices=["high", "medium", "low"], default="medium")

    # update
    p_upd = sub.add_parser("update", help="更新节点状态")
    p_upd.add_argument("node_id", help="节点编号")
    p_upd.add_argument("--status", choices=["TODO", "WIP", "DONE", "GAP", "HOLD"])
    p_upd.add_argument("--priority", choices=["high", "medium", "low"])
    p_upd.add_argument("--file", help="研究文件路径")

    # next
    p_next = sub.add_parser("next", help="查看待研究节点")
    p_next.add_argument("--all", action="store_true", help="包含GAP状态")

    # tree
    p_tree = sub.add_parser("tree", help="显示产业链树")
    p_tree.add_argument("--depth", type=int, default=3, help="显示深度")

    # report
    p_rep = sub.add_parser("report", help="生成进度报告")
    p_rep.add_argument("-o", "--output", help="输出文件路径")

    # check
    sub.add_parser("check", help="运行质量检查")

    # log
    p_log = sub.add_parser("log", help="添加工作流日志")
    p_log.add_argument("message", help="日志内容")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "init": cmd_init,
        "status": cmd_status,
        "show": cmd_show,
        "new": cmd_new,
        "update": cmd_update,
        "next": cmd_next,
        "tree": cmd_tree,
        "report": cmd_report,
        "check": cmd_check,
        "log": cmd_log,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
