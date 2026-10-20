#!/usr/bin/env python3
"""
产业链研究工作台 — Flask Web 应用（多项目版）
启动: python3 app.py
访问: http://localhost:5000
"""

import yaml
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request, redirect, url_for

BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"

app = Flask(__name__)


# === 数据层 ===

def load_yaml(path):
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def save_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

def get_projects():
    return load_yaml(CONFIG_DIR / "projects.yaml")

def get_registry(project):
    """Per-project node registry. Falls back to shared file for chip project."""
    project_file = CONFIG_DIR / f"nodes-registry-{project}.yaml"
    if project_file.exists():
        return load_yaml(project_file)
    # Fallback: chip project uses the original file
    if project == "芯片":
        return load_yaml(CONFIG_DIR / "nodes-registry.yaml")
    return {"industry": project, "nodes": {}}

def save_registry(project, data):
    if project == "芯片":
        save_yaml(CONFIG_DIR / "nodes-registry.yaml", data)
    else:
        save_yaml(CONFIG_DIR / f"nodes-registry-{project}.yaml", data)

def get_workflow(project):
    return load_yaml(CONFIG_DIR / "workflow.yaml")

def get_sources(project):
    return load_yaml(BASE_DIR / "sources" / "source-index.yaml")


# === 项目首页 ===

@app.route("/")
def project_home():
    return render_template("project_home.html")

@app.route("/api/projects")
def api_projects():
    data = get_projects()
    # 更新每个项目的实时进度
    for p in data.get("projects", []):
        reg = get_registry(p["id"])
        nodes = reg.get("nodes", {})
        p["total_nodes"] = len(nodes)
        p["done_nodes"] = sum(1 for n in nodes.values() if n.get("status") == "DONE")
    return jsonify(data)


@app.route("/api/projects", methods=["POST"])
def api_create_project():
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "项目名称不能为空"}), 400

    projects = get_projects()
    existing_ids = [p["id"] for p in projects.get("projects", [])]
    if name in existing_ids:
        return jsonify({"error": f"项目 '{name}' 已存在"}), 400

    projects.setdefault("projects", []).append({
        "id": name,
        "name": data.get("display_name", name),
        "code": data.get("code", ""),
        "status": "进行中",
        "description": data.get("description", ""),
        "start_date": datetime.now().strftime("%Y-%m-%d"),
        "total_nodes": 0,
        "done_nodes": 0,
        "icon": data.get("icon", "📊"),
    })
    save_yaml(CONFIG_DIR / "projects.yaml", projects)
    return jsonify({"ok": True, "id": name})


# === 项目内页面路由 ===

@app.route("/<project>/")
def dashboard(project):
    return render_template("dashboard.html", project=project)

@app.route("/<project>/chain-map")
def chain_map(project):
    return render_template("chain_map.html", project=project)

@app.route("/<project>/nodes")
def nodes_list(project):
    return render_template("nodes.html", project=project)

@app.route("/<project>/node/<node_id>")
def node_detail(project, node_id):
    return render_template("node_detail.html", project=project, node_id=node_id)

@app.route("/<project>/sources")
def sources_page(project):
    return render_template("sources.html", project=project)

@app.route("/<project>/workflow")
def workflow_page(project):
    return render_template("workflow.html", project=project)


# === API 路由 ===

@app.route("/api/<project>/status")
def api_status(project):
    reg = get_registry(project)
    nodes = reg.get("nodes", {})
    if not nodes:
        return jsonify({"error": "节点台账为空", "total": 0, "project": project})

    status_count = {}
    for n in nodes.values():
        s = n.get("status", "TODO")
        status_count[s] = status_count.get(s, 0) + 1

    total = len(nodes)
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
        "project": project,
        "industry": reg.get("industry", project),
        "total": total,
        "done": status_count.get("DONE", 0),
        "wip": status_count.get("WIP", 0),
        "todo": status_count.get("TODO", 0),
        "gap": status_count.get("GAP", 0),
        "hold": status_count.get("HOLD", 0),
        "categories": categories,
    })


@app.route("/api/<project>/tree")
def api_tree(project):
    reg = get_registry(project)
    return jsonify({"nodes": reg.get("nodes", {})})


@app.route("/api/<project>/graph")
def api_graph(project):
    reg = get_registry(project)
    nodes = reg.get("nodes", {})

    status_color = {
        "DONE": "#22c55e", "WIP": "#3b82f6", "TODO": "#94a3b8",
        "GAP": "#eab308", "HOLD": "#a855f7",
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
    return jsonify({"nodes": graph_nodes, "links": graph_links, "categories": categories})


@app.route("/api/<project>/node/<node_id>")
def api_node(project, node_id):
    reg = get_registry(project)
    nodes = reg.get("nodes", {})
    if node_id not in nodes:
        return jsonify({"error": f"节点 {node_id} 不存在"}), 404

    n = nodes[node_id]
    content = ""
    rf = n.get("research_file", "")
    if rf:
        rf_path = BASE_DIR / rf
        if rf_path.exists():
            content = rf_path.read_text(encoding="utf-8")

    parent_name = ""
    p = n.get("parent")
    if p and p in nodes:
        parent_name = nodes[p].get("name", "")

    children_info = []
    for c in n.get("children", []):
        if c in nodes:
            children_info.append({
                "id": c, "name": nodes[c].get("name", ""),
                "status": nodes[c].get("status", "TODO"),
            })

    return jsonify({
        "node": n, "parent_name": parent_name,
        "children_info": children_info, "content": content,
    })


@app.route("/api/<project>/node/<node_id>", methods=["PUT"])
def api_node_update(project, node_id):
    reg = get_registry(project)
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
    save_registry(project, reg)
    return jsonify({"ok": True})


@app.route("/api/<project>/node/<node_id>/file", methods=["PUT"])
def api_node_file(project, node_id):
    reg = get_registry(project)
    nodes = reg.get("nodes", {})
    if node_id not in nodes:
        return jsonify({"error": "节点不存在"}), 404

    data = request.get_json()
    content = data.get("content", "")
    rf = nodes[node_id].get("research_file", "")
    if not rf:
        n = nodes[node_id]
        parent_id = n.get("parent", "")
        if parent_id:
            parent = nodes.get(parent_id, {})
            folder = BASE_DIR / "nodes" / project / f"{parent_id}-{parent.get('name','')}"
        else:
            folder = BASE_DIR / "nodes" / project
        folder.mkdir(parents=True, exist_ok=True)
        rf = str(folder / f"{node_id}-{n['name']}.md").replace(str(BASE_DIR) + "/", "")
        nodes[node_id]["research_file"] = rf

    rf_path = BASE_DIR / rf
    rf_path.parent.mkdir(parents=True, exist_ok=True)
    rf_path.write_text(content, encoding="utf-8")
    nodes[node_id]["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    save_registry(project, reg)
    return jsonify({"ok": True, "file": rf})


@app.route("/api/<project>/sources")
def api_sources(project):
    return jsonify(get_sources(project))


@app.route("/api/<project>/check")
def api_check(project):
    reg = get_registry(project)
    nodes = reg.get("nodes", {})
    issues = []
    for nid, n in sorted(nodes.items()):
        status = n.get("status", "TODO")
        rf = n.get("research_file", "")
        if status == "DONE" and not rf:
            issues.append({"level": "warning", "msg": f"{nid} {n['name']}: DONE但无研究文件"})
        if status == "DONE" and rf and not (BASE_DIR / rf).exists():
            issues.append({"level": "error", "msg": f"{nid} {n['name']}: 研究文件不存在"})
        for c in n.get("children", []):
            if c not in nodes:
                issues.append({"level": "error", "msg": f"{nid}: 子节点 '{c}' 不存在"})
            elif nodes[c].get("parent") != nid:
                issues.append({"level": "error", "msg": f"{nid}: 子节点 '{c}' 父节点不一致"})
        parent = n.get("parent")
        if parent and parent in nodes and nid not in nodes[parent].get("children", []):
            issues.append({"level": "error", "msg": f"{nid}: 不在父节点 '{parent}' 子列表中"})
    return jsonify({"issues": issues, "count": len(issues)})


@app.route("/api/<project>/search")
def api_search(project):
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify({"results": []})
    reg = get_registry(project)
    nodes = reg.get("nodes", {})
    results = []
    for nid, n in nodes.items():
        if q in nid.lower() or q in n.get("name", "").lower():
            results.append({
                "id": nid, "name": n.get("name", ""),
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
