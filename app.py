#!/usr/bin/env python3
"""
产业链研究工作台 — Flask Web 应用（多项目版）
启动: python3 app.py
访问: http://localhost:5000
"""

import yaml
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request, redirect, url_for, session
import json
import secrets as _secrets
import rowstore
import auth

BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"

app = Flask(__name__)

# 会话密钥：首次生成后持久化，重启不丢登录态
_secret_file = CONFIG_DIR / ".secret_key"
if _secret_file.exists():
    app.secret_key = _secret_file.read_text(encoding="utf-8").strip()
else:
    app.secret_key = _secrets.token_hex(24)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _secret_file.write_text(app.secret_key, encoding="utf-8")

app.config["PERMANENT_SESSION_LIFETIME"] = 7 * 24 * 3600  # 登录态保持 7 天

auth.ensure_admin()


# === 账号与登录 ===

def session_user():
    return auth.find_user(session.get("username", ""))


def session_author():
    u = session_user()
    if not u:
        return "匿名"
    return u.get("display_name") or u.get("username")


def session_username():
    u = session_user()
    return u.get("username") if u else ""


def can_manage_entry(row):
    """判断当前登录用户能否编辑/删除某条目：本人，或管理员。"""
    u = session_user()
    if not u:
        return False
    if u.get("role") == "admin":
        return True
    if row.get("author_username"):
        return row.get("author_username") == u.get("username")
    # 旧数据没有 author_username，按显示名回退匹配
    return (row.get("author") or "").strip() == (u.get("display_name") or "").strip()


@app.context_processor
def inject_current_user():
    u = session_user()
    return {"current_user": auth.public_user(u) if u else None}


@app.before_request
def require_login():
    path = request.path
    if path == "/login" or path.startswith("/static/") or path == "/favicon.ico" \
            or path.startswith("/api/login") or path.startswith("/api/logout") \
            or path.startswith("/api/register"):
        return None
    if not session.get("username"):
        if path.startswith("/api/"):
            return jsonify({"error": "未登录", "code": "no_auth"}), 401
        nxt = request.full_path.split("?", 1)[0] if request.full_path else "/"
        if not nxt.startswith("/"):
            nxt = "/"
        return redirect(url_for("login_page", next=nxt))


@app.route("/login")
def login_page():
    nxt = request.args.get("next", "/")
    if not nxt.startswith("/"):
        nxt = "/"
    return render_template("login.html", next=nxt)


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    u = auth.verify(username, password)
    if not u:
        return jsonify({"error": "账号或密码错误，或账号已被停用"}), 401
    session["username"] = u.get("username")
    session.permanent = True
    return jsonify({"ok": True, "user": auth.public_user(u)})


@app.route("/api/register", methods=["POST"])
def api_register():
    import re
    data = request.get_json() or {}
    username = str(data.get("username", "")).strip()
    display_name = str(data.get("display_name", "")).strip()
    password = str(data.get("password", ""))
    password2 = str(data.get("password2", ""))
    if not re.fullmatch(r"[A-Za-z0-9_]{2,32}", username):
        return jsonify({"error": "账号需为 2-32 位字母、数字或下划线"}), 400
    if not display_name:
        return jsonify({"error": "请填写显示姓名（填写信息时记录的名字）"}), 400
    if len(password) < 6:
        return jsonify({"error": "密码至少 6 位"}), 400
    if password != password2:
        return jsonify({"error": "两次输入的密码不一致"}), 400
    try:
        u = auth.create_user(username, display_name, password, "member")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    session["username"] = u.get("username")
    session.permanent = True
    return jsonify({"ok": True, "user": auth.public_user(u)})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/me")
def api_me():
    u = session_user()
    if not u:
        return jsonify({"error": "未登录"}), 401
    return jsonify(auth.public_user(u))


@app.route("/api/me/password", methods=["POST"])
def api_me_password():
    u = session_user()
    if not u:
        return jsonify({"error": "未登录"}), 401
    data = request.get_json() or {}
    old_pw = str(data.get("old_password", ""))
    new_pw = str(data.get("new_password", "")).strip()
    if not auth.verify(u.get("username"), old_pw):
        return jsonify({"error": "原密码不正确"}), 403
    if len(new_pw) < 6:
        return jsonify({"error": "新密码至少 6 位"}), 400
    auth.set_password(u.get("username"), new_pw)
    return jsonify({"ok": True})


# === 账号管理（仅管理员） ===

def require_admin():
    u = session_user()
    if not u or u.get("role") != "admin":
        return None
    return u


@app.route("/users")
def users_page():
    if not require_admin():
        return redirect("/")
    projects = get_projects().get("projects", [])
    proj = projects[0]["id"] if projects else "屏幕"
    return render_template("users.html", project=proj)


@app.route("/api/users")
def api_users():
    if not require_admin():
        return jsonify({"error": "仅管理员可操作"}), 403
    return jsonify({"users": [auth.public_user(u) for u in auth.load_users()]})


@app.route("/api/users", methods=["POST"])
def api_users_create():
    if not require_admin():
        return jsonify({"error": "仅管理员可操作"}), 403
    data = request.get_json() or {}
    username = str(data.get("username", "")).strip()
    display_name = str(data.get("display_name", "")).strip()
    password = str(data.get("password", ""))
    role = str(data.get("role", "member"))
    try:
        u = auth.create_user(username, display_name, password, role)
        return jsonify({"ok": True, "user": auth.public_user(u)})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/users/<username>", methods=["POST"])
def api_users_update(username):
    if not require_admin():
        return jsonify({"error": "仅管理员可操作"}), 403
    if not auth.find_user(username):
        return jsonify({"error": "用户不存在"}), 404
    data = request.get_json() or {}
    if "display_name" in data:
        auth.set_display_name(username, str(data.get("display_name", "")).strip())
    if "enabled" in data:
        auth.set_enabled(username, bool(data.get("enabled")))
    return jsonify({"ok": True, "user": auth.public_user(auth.find_user(username))})


@app.route("/api/users/<username>/password", methods=["POST"])
def api_users_password(username):
    if not require_admin():
        return jsonify({"error": "仅管理员可操作"}), 403
    if not auth.find_user(username):
        return jsonify({"error": "用户不存在"}), 404
    data = request.get_json() or {}
    new_pw = str(data.get("password", "")).strip()
    if len(new_pw) < 6:
        return jsonify({"error": "新密码至少 6 位"}), 400
    auth.set_password(username, new_pw)
    return jsonify({"ok": True})


@app.route("/api/users/<username>", methods=["DELETE"])
def api_users_delete(username):
    u = require_admin()
    if not u:
        return jsonify({"error": "仅管理员可操作"}), 403
    if username == u.get("username"):
        return jsonify({"error": "不能删除当前登录的管理员账号"}), 400
    if auth.delete_user(username):
        return jsonify({"ok": True})
    return jsonify({"error": "用户不存在"}), 404


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
    owner = request.args.get("owner", "").strip()
    contributor = request.args.get("contributor", "").strip()
    reg = get_registry(project)
    nodes = reg.get("nodes", {})
    results = []
    for nid, n in nodes.items():
        if owner and n.get("owner", "") != owner:
            continue
        if contributor:
            rows = rowstore.load_rows(project, nid)
            authors = [r.get("author", "") for r in (rows.get("companies", []) + rows.get("news", []))]
            if contributor not in authors:
                continue
        hit = False
        if not q:
            if owner or contributor:
                hit = True
        else:
            if q in nid.lower() or q in n.get("name", "").lower() or q in str(n.get("description", "")).lower():
                hit = True
            else:
                rf = n.get("research_file", "")
                if rf:
                    fp = BASE_DIR / rf
                    if fp.exists():
                        try:
                            if q in fp.read_text(encoding="utf-8").lower():
                                hit = True
                        except OSError:
                            pass
                if not hit:
                    rows = rowstore.load_rows(project, nid)
                    if q in json.dumps(rows, ensure_ascii=False).lower():
                        hit = True
        if hit:
            pname = n.get("parent", "")
            results.append({
                "id": nid,
                "name": n.get("name", ""),
                "status": n.get("status", "TODO"),
                "parent": pname,
                "parent_name": nodes.get(pname, {}).get("name", "") if pname else "",
                "owner": n.get("owner", ""),
            })
    return jsonify({"results": results[:50]})


@app.route("/api/<project>/node/<node_id>/rows")
def api_node_rows(project, node_id):
    reg = get_registry(project)
    if node_id not in reg.get("nodes", {}):
        return jsonify({"error": "节点不存在"}), 404
    rows = rowstore.load_rows(project, node_id)
    owner = reg["nodes"][node_id].get("owner", "")
    return jsonify({"companies": rows.get("companies", []), "news": rows.get("news", []), "owner": owner})


@app.route("/api/<project>/node/<node_id>/rows", methods=["POST"])
def api_node_rows_add(project, node_id):
    reg = get_registry(project)
    if node_id not in reg.get("nodes", {}):
        return jsonify({"error": "节点不存在"}), 404
    data = request.get_json() or {}
    row_type = data.get("type", "")
    if row_type not in ("company", "news"):
        return jsonify({"error": "type 必须是 company 或 news"}), 400
    author = session_author()
    author_username = session_username()
    fields = data.get("fields") or {}
    required = ("企业",)
    missing = [k for k in required if not str(fields.get(k, "")).strip()]
    if not missing and not str(fields.get("来源链接", "")).strip() and not str(fields.get("来源", "")).strip():
        missing = ["来源链接或来源"]
    if missing:
        return jsonify({"error": "；".join(missing) + " 不能为空"}), 400
    allowed = {
        "company": ["企业", "所在地", "主要产品", "产业化状态", "来源链接", "来源", "核实状态", "提炼观点"],
        "news": ["日期", "企业", "事件", "来源链接", "来源", "状态", "提炼观点"],
    }[row_type]
    clean = {k: str(fields[k]).strip() for k in allowed if k in fields and str(fields[k]).strip()}
    if data.get("require_insight") and not clean.get("提炼观点"):
        return jsonify({"error": "请填写“提炼观点”（一句话写清你的判断）"}), 400

    # 防重复：先查重，疑似重复时返回候选，由前端提示用户确认
    force = bool(data.get("force"))
    if not force:
        dups = rowstore.find_duplicates(project, row_type, clean)
        if dups:
            nodes = reg.get("nodes", {})
            for d in dups:
                n = nodes.get(d["node_id"], {})
                d["node_name"] = n.get("name", d["node_id"])
                parent = n.get("parent", "")
                d["parent_name"] = nodes.get(parent, {}).get("name", "") if parent else ""
                d["type"] = row_type
            return jsonify({"ok": False, "conflict": True, "duplicates": dups}), 409

    try:
        row = rowstore.append_row(project, node_id, row_type, clean, author, author_username=author_username)
        return jsonify({"ok": True, "row": row})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/<project>/node/<node_id>/claim", methods=["POST"])
def api_node_claim(project, node_id):
    reg = get_registry(project)
    if node_id not in reg.get("nodes", {}):
        return jsonify({"error": "节点不存在"}), 404
    owner = session_author()
    if not owner or owner == "匿名":
        return jsonify({"error": "未登录"}), 401
    try:
        rowstore.set_owner(project, node_id, owner)
        rowstore.log(project, node_id, "认领节点", session_username(), {"owner": owner})
        return jsonify({"ok": True, "owner": owner})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/<project>/activity")
def activity_page(project):
    return render_template("activity.html", project=project)


@app.route("/api/<project>/activity")
def api_activity(project):
    reg = get_registry(project)
    nodes = reg.get("nodes", {})
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        limit = 50
    rows = rowstore.load_all_rows(project)
    feed = []
    contributors = {}
    for item in rows:
        nid = item["node_id"]
        row = item["row"]
        author = str(row.get("author", "匿名"))
        contributors[author] = contributors.get(author, 0) + 1
        if nid not in nodes:
            continue
        n = nodes[nid]
        parent = n.get("parent", "")
        feed.append({
            "node_id": nid,
            "node_name": n.get("name", nid),
            "parent_name": nodes.get(parent, {}).get("name", "") if parent else "",
            "type": item["type"],
            "row": row,
        })
    top = sorted(contributors.items(), key=lambda kv: kv[1], reverse=True)
    return jsonify({
        "feed": feed[:limit],
        "total_entries": len(feed),
        "contributors": [{"name": k, "count": v} for k, v in top],
    })
@app.route("/<project>/entry/<entry_id>")
def entry_page(project, entry_id):
    return render_template("entry_detail.html", project=project)


@app.route("/api/<project>/entry/<entry_id>")
def api_entry_detail(project, entry_id):
    reg = get_registry(project)
    nodes = reg.get("nodes", {})
    base = rowstore.ROWS_DIR / rowstore._safe(project)
    for f in sorted(base.glob("*.json")):
        if f.name in ("changelog.json", "followups.json", "trash.json"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for key, rtype in (("companies", "company"), ("news", "news")):
            for row in data.get(key, []):
                if row.get("entry_id") == entry_id:
                    nid = f.stem
                    n = nodes.get(nid, {})
                    parent = n.get("parent", "")
                    return jsonify({
                        "node_id": nid,
                        "node_name": n.get("name", nid),
                        "parent_name": nodes.get(parent, {}).get("name", "") if parent else "",
                        "type": rtype,
                        "row": row,
                    })
    return jsonify({"error": "条目不存在"}), 404


@app.route("/api/<project>/entry/<entry_id>/followups")
def api_entry_followups(project, entry_id):
    return jsonify({"followups": rowstore.load_followups(project, entry_id)})


@app.route("/api/<project>/entry/<entry_id>", methods=["PUT"])
def api_entry_update(project, entry_id):
    data = request.get_json() or {}
    fields = data.get("fields") or {}
    node_id, rtype, row = rowstore.find_entry(project, entry_id)
    if row is None:
        return jsonify({"error": "条目不存在"}), 404
    if not can_manage_entry(row):
        return jsonify({"error": "只有上传者本人或管理员才能编辑这条信息"}), 403
    allowed = {
        "company": ["企业", "所在地", "主要产品", "产业化状态", "来源链接", "来源", "核实状态", "提炼观点"],
        "news": ["日期", "企业", "事件", "来源链接", "来源", "状态", "提炼观点"],
    }[rtype]
    clean = {k: str(fields[k]).strip() for k in allowed if k in fields}
    if not clean:
        return jsonify({"error": "没有可更新的字段"}), 400
    nid, key = rowstore.update_row(project, entry_id, clean, editor=session_author())
    if nid is None:
        return jsonify({"error": "更新失败"}), 500
    _, _, newrow = rowstore.find_entry(project, entry_id)
    return jsonify({"ok": True, "row": newrow})


@app.route("/api/<project>/entry/<entry_id>", methods=["DELETE"])
def api_entry_delete(project, entry_id):
    node_id, rtype, row = rowstore.find_entry(project, entry_id)
    if row is None:
        return jsonify({"error": "条目不存在"}), 404
    if not can_manage_entry(row):
        return jsonify({"error": "只有上传者本人或管理员才能删除这条信息"}), 403
    deleted = rowstore.delete_row(project, entry_id, session_author())
    if deleted is None:
        return jsonify({"error": "删除失败"}), 500
    return jsonify({"ok": True, "node_id": node_id, "deleted": deleted})


@app.route("/api/<project>/entry/<entry_id>/review", methods=["POST"])
def api_entry_review(project, entry_id):
    data = request.get_json() or {}
    status = str(data.get("status", "")).strip()
    if status not in ("待复核", "已复核"):
        return jsonify({"error": "status 必须是 待复核 或 已复核"}), 400
    reviewer = session_author()
    row = rowstore.set_review_status(project, entry_id, status, reviewer)
    if row is None:
        return jsonify({"error": "条目不存在"}), 404
    return jsonify({"ok": True, "row": row})


@app.route("/api/<project>/entry/<entry_id>/followups/<fid>/resolve", methods=["POST"])
def api_entry_followup_resolve(project, entry_id, fid):
    data = request.get_json() or {}
    resolver = session_author() or "匿名"
    row = rowstore.resolve_followup(project, entry_id, fid, resolver)
    if row is None:
        return jsonify({"error": "跟进记录不存在"}), 404
    return jsonify({"ok": True, "row": row})


@app.route("/api/<project>/entry/<entry_id>/followups", methods=["POST"])
def api_entry_followups_add(project, entry_id):
    data = request.get_json() or {}
    author = session_author()
    author_username = session_username()
    fields = data.get("fields") or {}
    if not str(fields.get("内容", "")).strip():
        return jsonify({"error": "内容不能为空"}), 400
    allowed = ["类型", "日期", "内容", "来源链接"]
    clean = {k: str(fields[k]).strip() for k in allowed if k in fields and str(fields[k]).strip()}
    try:
        row = rowstore.add_followup(project, entry_id, clean, author, author_username=author_username)
        return jsonify({"ok": True, "row": row})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/demo")
def demo_page():
    return render_template("demo.html", project="屏幕")


# === 启动 ===

if __name__ == "__main__":
    print("=" * 50)
    print("  产业链研究工作台")
    print("  访问: http://localhost:5000")
    print("  按 Ctrl+C 停止")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
