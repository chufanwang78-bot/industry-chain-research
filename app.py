#!/usr/bin/env python3
"""
产业链研究工作台 — Flask Web 应用
启动: python3 app.py
访问: http://localhost:5000
"""

import os
import yaml
import json
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_from_directory

# === 路径 ===
BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"
NODES_DIR = BASE_DIR / "nodes"
SOURCES_DIR = BASE_DIR / "sources"
LOGS_DIR = BASE_DIR / "logs"

WORKFLOW_CONFIG = CONFIG_DIR / "workflow.yaml"
NODES_REGISTRY = CONFIG_DIR / "nodes-registry.yaml"
SOURCE_INDEX = SOURCES_DIR / "source-index.yaml"
WORKFLOW_LOG = LOGS_DIR / "workflow-log.md"

app = Flask(__name__)


# === 数据加载 ===

def load_yaml(path):
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def save_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

def get_registry():
    return load_yaml(NODES_REGISTRY)

def save_registry(data):
    save_yaml(NODES_REGISTRY, data)

def get_workflow():
    return load_yaml(WORKFLOW_CONFIG)

def get_sources():
    return load_yaml(SOURCE_INDEX)


# === 页面路由 ===

@app.route("/")
def dashboard():
    return render_template("dashboard.html")

@app.route("/chain-map")
def chain_map():
    return render_template("chain_map.html")

@app.route("/nodes")
def nodes_list():
    return render_template("nodes.html")

@app.route("/node/<node_id>")
def node_detail(node_id):
    return render_template("node_detail.html", node_id=node_id)

@app.route("/sources")
def sources_page():
    return render_template("sources.html")

@app.route("/workflow")
def workflow_page():
    return render_template("workflow.html")


# === API 路由 ===

@app.route("/api/status")
def api_status():
    reg = get_registry()
    nodes = reg.get("nodes", {})
    if not nodes:
        return jsonify({"error": "节点台账为空", "total": 0})

    status_count = {}
    for n in nodes.values():
        s = n.get("status", "TODO")
        status_count[s] = status_count.get(s, 0) + 1

    total = len(nodes)

    # 按一级分类统计
    categories = []
    top_ids = sorted([k for k in nodes if "." not in k],
                     key=lambda x: int(x) if x.isdigit() else x)
    for tid in top_ids:
        n = nodes[tid]
        children = n.get("children", [])
        if children:
            c_total = len(children)
            c_done = sum(1 for c in children if nodes.get(c, {}).get("status") == "DONE")
        else:
            c_total = 1
            c_done = 1 if n.get("status") == "DONE" else 0
        categories.append({
            "id": tid,
            "name": n["name"],
            "total": c_total,
            "done": c_done,
            "percent": round(c_done * 100 / max(c_total, 1), 1),
        })

    return jsonify({
        "industry": reg.get("industry", ""),
        "total": total,
        "done": status_count.get("DONE", 0),
        "wip": status_count.get("WIP", 0),
        "todo": status_count.get("TODO", 0),
        "gap": status_count.get("GAP", 0),
        "hold": status_count.get("HOLD", 0),
        "categories": categories,
    })


@app.route("/api/tree")
def api_tree():
    reg = get_registry()
    nodes = reg.get("nodes", {})
    return jsonify({"nodes": nodes})


@app.route("/api/graph")
def api_graph():
    """返回 ECharts graph 所需的 nodes + links 数据"""
    reg = get_registry()
    nodes = reg.get("nodes", {})

    status_color = {
        "DONE": "#22c55e",
        "WIP": "#3b82f6",
        "TODO": "#94a3b8",
        "GAP": "#eab308",
        "HOLD": "#a855f7",
    }

    graph_nodes = []
    graph_links = []

    for nid, n in nodes.items():
        depth = nid.count(".")
        graph_nodes.append({
            "id": nid,
            "name": n.get("name", nid),
            "category": depth,
            "symbolSize": max(10, 30 - depth * 6),
            "itemStyle": {"color": status_color.get(n.get("status", "TODO"), "#94a3b8")},
            "meta": {
                "status": n.get("status", "TODO"),
                "relation": n.get("relation_type", ""),
                "parent": n.get("parent", ""),
                "children": n.get("children", []),
            }
        })

        parent = n.get("parent")
        if parent and parent in nodes:
            graph_links.append({
                "source": parent,
                "target": nid,
                "lineStyle": {"color": "#cbd5e1", "width": 1.5},
            })

    categories = [{"name": f"层级{i}"} for i in range(4)]

    return jsonify({
        "nodes": graph_nodes,
        "links": graph_links,
        "categories": categories,
    })


@app.route("/api/node/<node_id>")
def api_node(node_id):
    reg = get_registry()
    nodes = reg.get("nodes", {})
    if node_id not in nodes:
        return jsonify({"error": f"节点 {node_id} 不存在"}), 404

    n = nodes[node_id]

    # 读取研究文件
    content = ""
    rf = n.get("research_file", "")
    if rf:
        rf_path = BASE_DIR / rf
        if rf_path.exists():
            content = rf_path.read_text(encoding="utf-8")

    # 父节点信息
    parent_name = ""
    p = n.get("parent")
    if p and p in nodes:
        parent_name = nodes[p].get("name", "")

    # 子节点信息
    children_info = []
    for c in n.get("children", []):
        if c in nodes:
            children_info.append({
                "id": c,
                "name": nodes[c].get("name", ""),
                "status": nodes[c].get("status", "TODO"),
            })

    return jsonify({
        "node": n,
        "parent_name": parent_name,
        "children_info": children_info,
        "content": content,
    })


@app.route("/api/node/<node_id>", methods=["PUT"])
def api_node_update(node_id):
    reg = get_registry()
    nodes = reg.get("nodes", {})
    if node_id not in nodes:
        return jsonify({"error": "节点不存在"}), 404

    data = request.get_json()
    n = nodes[node_id]

    if "status" in data:
        n["status"] = data["status"]
    if "priority" in data:
        n["priority"] = data["priority"]
    if "description" in data:
        n["description"] = data["description"]

    n["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    save_registry(reg)
    return jsonify({"ok": True})


@app.route("/api/node/<node_id>/file", methods=["PUT"])
def api_node_file(node_id):
    """保存研究文件内容"""
    reg = get_registry()
    nodes = reg.get("nodes", {})
    if node_id not in nodes:
        return jsonify({"error": "节点不存在"}), 404

    data = request.get_json()
    content = data.get("content", "")
    rf = nodes[node_id].get("research_file", "")
    if not rf:
        # 自动生成文件路径
        n = nodes[node_id]
        parent_id = n.get("parent", "")
        if parent_id:
            parent = nodes.get(parent_id, {})
            parent_name = parent.get("name", "")
            folder = NODES_DIR / reg.get("industry", "未知") / f"{parent_id}-{parent_name}"
        else:
            folder = NODES_DIR / reg.get("industry", "未知")
        folder.mkdir(parents=True, exist_ok=True)
        rf = str(folder / f"{node_id}-{n['name']}.md").replace(str(BASE_DIR) + "/", "")
        nodes[node_id]["research_file"] = rf

    rf_path = BASE_DIR / rf
    rf_path.parent.mkdir(parents=True, exist_ok=True)
    rf_path.write_text(content, encoding="utf-8")
    nodes[node_id]["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    save_registry(reg)
    return jsonify({"ok": True, "file": rf})


@app.route("/api/sources")
def api_sources():
    src = get_sources()
    return jsonify(src)


@app.route("/api/check")
def api_check():
    reg = get_registry()
    nodes = reg.get("nodes", {})
    issues = []

    for nid, n in sorted(nodes.items()):
        status = n.get("status", "TODO")
        rf = n.get("research_file", "")

        if status == "DONE" and not rf:
            issues.append({"level": "warning", "msg": f"{nid} {n['name']}: 标记为DONE但没有研究文件"})
        if status == "DONE" and rf:
            rf_path = BASE_DIR / rf
            if not rf_path.exists():
                issues.append({"level": "error", "msg": f"{nid} {n['name']}: 研究文件不存在 ({rf})"})
        for c in n.get("children", []):
            if c not in nodes:
                issues.append({"level": "error", "msg": f"{nid}: 子节点 '{c}' 不存在"})
            elif nodes[c].get("parent") != nid:
                issues.append({"level": "error", "msg": f"{nid}: 子节点 '{c}' 父节点不一致"})
        parent = n.get("parent")
        if parent and parent in nodes:
            if nid not in nodes[parent].get("children", []):
                issues.append({"level": "error", "msg": f"{nid}: 不在父节点 '{parent}' 的子列表中"})

    return jsonify({"issues": issues, "count": len(issues)})


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify({"results": []})

    reg = get_registry()
    nodes = reg.get("nodes", {})
    results = []
    for nid, n in nodes.items():
        if q in nid.lower() or q in n.get("name", "").lower() or q in n.get("description", "").lower():
            results.append({
                "id": nid,
                "name": n.get("name", ""),
                "status": n.get("status", "TODO"),
                "parent": n.get("parent", ""),
            })
    return jsonify({"results": results[:20]})


# === 启动 ===

if __name__ == "__main__":
    print("=" * 50)
    print("  产业链研究工作台")
    print("  访问: http://localhost:5000")
    print("  按 Ctrl+C 停止")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
