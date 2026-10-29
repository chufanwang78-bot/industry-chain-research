# -*- coding: utf-8 -*-
"""账号身份体系：本地用户库（JSON）+ 密码哈希 + 管理员管理。

- 用户存在 config/users.json。
- 密码用 werkzeug 哈希保存，不存明文。
- 首次启动自动创建管理员：admin / admin123（显示名 zmjjkk）。
"""
import json
from datetime import datetime
from pathlib import Path

from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).parent
USERS_FILE = BASE_DIR / "config" / "users.json"


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_users():
    if not USERS_FILE.exists():
        return []
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data.get("users", [])


def save_users(users):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = USERS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"users": users}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(USERS_FILE)


def find_user(username):
    username = (username or "").strip()
    for u in load_users():
        if u.get("username") == username:
            return u
    return None


def public_user(u):
    return {
        "username": u.get("username"),
        "display_name": u.get("display_name") or u.get("username"),
        "role": u.get("role", "member"),
        "enabled": bool(u.get("enabled", True)),
        "created_at": u.get("created_at", ""),
    }


def verify(username, password):
    u = find_user(username)
    if not u:
        return None
    if not u.get("enabled", True):
        return None
    if check_password_hash(u.get("password_hash", ""), password or ""):
        return u
    return None


def ensure_admin():
    """首次启动时创建默认管理员。"""
    users = load_users()
    if any(u.get("role") == "admin" for u in users):
        return
    users.append({
        "username": "admin",
        "display_name": "zmjjkk",
        "role": "admin",
        "password_hash": generate_password_hash("admin123"),
        "enabled": True,
        "created_at": _now(),
    })
    save_users(users)


def create_user(username, display_name, password, role="member"):
    username = (username or "").strip()
    if not username or not password:
        raise ValueError("用户名和密码不能为空")
    if find_user(username):
        raise ValueError(f"用户名 {username} 已存在")
    users = load_users()
    users.append({
        "username": username,
        "display_name": (display_name or "").strip() or username,
        "role": role if role in ("admin", "member") else "member",
        "password_hash": generate_password_hash(password),
        "enabled": True,
        "created_at": _now(),
    })
    save_users(users)
    return find_user(username)


def set_password(username, new_password):
    users = load_users()
    for u in users:
        if u.get("username") == username:
            u["password_hash"] = generate_password_hash(new_password)
            save_users(users)
            return True
    return False


def set_display_name(username, display_name):
    users = load_users()
    for u in users:
        if u.get("username") == username:
            u["display_name"] = (display_name or "").strip() or username
            save_users(users)
            return True
    return False


def set_enabled(username, enabled):
    users = load_users()
    for u in users:
        if u.get("username") == username:
            u["enabled"] = bool(enabled)
            save_users(users)
            return True
    return False


def delete_user(username):
    users = load_users()
    out = [u for u in users if u.get("username") != username]
    if len(out) != len(users):
        save_users(out)
        return True
    return False
