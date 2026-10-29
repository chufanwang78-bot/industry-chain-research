# -*- coding: utf-8 -*-
"""行级协作数据存储。

设计：
- 每个节点一个 JSON 文件 rows/<项目>/<节点id>.json，保存"补充企业"和"补充新闻"两列表。
- 追加式写入：每次加一行，服务端自动记填写人 author 与时间戳 timestamp。
- 并发保护：flock（POSIX）锁文件 + 临时文件原子替换 + 重试。
- 认领节点：把 owner 字段外科式写回 registry（不重排 YAML 其他内容，避免大 diff）。
- 变更日志：rows/<项目>/changelog.json，只追加。
"""
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

try:
    import fcntl  # POSIX（WSL / Render）
except ImportError:
    fcntl = None

BASE_DIR = Path(__file__).parent
ROWS_DIR = BASE_DIR / "rows"
VALID_TYPES = ("company", "news")


def _safe(s):
    return str(s).replace("/", "-").replace("\\", "-")


def rows_file(project, node_id):
    return ROWS_DIR / _safe(project) / f"{node_id}.json"


def changelog_file(project):
    return ROWS_DIR / _safe(project) / "changelog.json"


def _acquire(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lf = open(path.with_suffix(path.suffix + ".lock"), "a+")
    if fcntl:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
    return lf


def _release(lf):
    if fcntl:
        try:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
    lf.close()


def _atomic_write(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_rows(project, node_id):
    p = rows_file(project, node_id)
    if not p.exists():
        return {"companies": [], "news": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"companies": [], "news": []}
    data.setdefault("companies", [])
    data.setdefault("news", [])
    return data


def log(project, node_id, action, user, detail):
    p = changelog_file(project)
    lf = _acquire(p)
    try:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {"log": []}
        else:
            data = {"log": []}
        data.setdefault("log", []).append({
            "time": _now(),
            "user": user or "匿名",
            "action": action,
            "node": node_id,
            "detail": detail,
        })
        _atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2))
    finally:
        _release(lf)


def append_row(project, node_id, row_type, fields, author, author_username=None):
    if row_type not in VALID_TYPES:
        raise ValueError(f"未知行类型: {row_type}")
    row = dict(fields)
    row["entry_id"] = uuid.uuid4().hex[:12]
    row["author"] = (author or "").strip() or "匿名"
    if author_username:
        row["author_username"] = author_username
    row["timestamp"] = _now()
    row.setdefault("复核状态", "待复核")
    row.setdefault("纠错状态", "无")

    p = rows_file(project, node_id)
    lf = _acquire(p)
    try:
        for _ in range(5):
            data = load_rows(project, node_id)
            key = "companies" if row_type == "company" else "news"
            data[key].append(row)
            _atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2))
            log(project, node_id,
                "补充企业" if row_type == "company" else "补充新闻",
                row["author"], row)
            return row
        raise RuntimeError("并发写入失败，请重试")
    finally:
        _release(lf)


def registry_path_for(project):
    if project == "芯片":
        return BASE_DIR / "config" / "nodes-registry.yaml"
    return BASE_DIR / "config" / f"nodes-registry-{project}.yaml"


def set_owner(project, node_id, owner):
    """把负责人 owner 外科式写入 registry 对应节点块。"""
    owner = (owner or "").strip()
    if not owner:
        raise ValueError("负责人不能为空")
    p = registry_path_for(project)
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    block_start = None
    for i, line in enumerate(lines):
        m = re.match(r"^  (.+?):\s*$", line)
        if m and m.group(1).strip("'\"") == node_id:
            block_start = i
            break
    if block_start is None:
        raise ValueError(f"registry 中未找到节点 {node_id}")

    end = len(lines)
    for j in range(block_start + 1, len(lines)):
        if re.match(r"^  (.+?):\s*$", lines[j]):
            end = j
            break

    block = lines[block_start:end]
    new_block = []
    inserted = False
    for bl in block:
        if re.match(r"^    owner:", bl):
            new_block.append(f"    owner: '{owner}'\n")
            inserted = True
        elif bl.startswith("    last_updated:") and not inserted:
            new_block.append(bl)
            new_block.append(f"    owner: '{owner}'\n")
            inserted = True
        else:
            new_block.append(bl)
    if not inserted:
        new_block.append(f"    owner: '{owner}'\n")

    lines[block_start:end] = new_block
    p.write_text("".join(lines), encoding="utf-8")

def add_rows(project, node_id, row_type, rows, author=None, timestamp=None):
    """批量追加行（迁移/导入用）：带去重、作者与时间戳，并写入 migrated 标记。"""
    if row_type not in VALID_TYPES:
        raise ValueError('未知行类型: ' + str(row_type))
    p = rows_file(project, node_id)
    lf = _acquire(p)
    try:
        data = load_rows(project, node_id)
        key = 'companies' if row_type == 'company' else 'news'
        existing = data[key]
        added = 0
        for fields in rows:
            f = {k: str(v).strip() for k, v in fields.items() if v is not None}
            dup = False
            for e in existing:
                if all(str(e.get(k, '')).strip() == f.get(k, '') for k in f if f.get(k, '')):
                    dup = True
                    break
            if dup:
                continue
            row = dict(f)
            row['entry_id'] = uuid.uuid4().hex[:12]
            row['author'] = (author or '').strip() or '匿名'
            row['timestamp'] = timestamp or _now()
            row.setdefault('复核状态', '待复核')
            row.setdefault('纠错状态', '无')
            existing.append(row)
            added += 1
        data[key] = existing
        data['migrated'] = True
        _atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2))
        if added:
            log(project, node_id, '迁移导入', author or '匿名', {'type': row_type, 'added': added})
        return added
    finally:
        _release(lf)


def load_all_rows(project):
    """聚合整个项目的全部行级条目，用于动态流与统计。
    返回 [{node_id, type, row}]，按 timestamp 倒序。"""
    base = ROWS_DIR / _safe(project)
    out = []
    if not base.exists():
        return out
    for f in base.glob('*.json'):
        if f.name in ('changelog.json', 'followups.json', 'trash.json'):
            continue
        node_id = f.stem
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            continue
        for row in data.get('companies', []):
            out.append({'node_id': node_id, 'type': 'company', 'row': row})
        for row in data.get('news', []):
            out.append({'node_id': node_id, 'type': 'news', 'row': row})
    out.sort(key=lambda x: str(x['row'].get('timestamp', '')), reverse=True)
    return out

def followups_file(project):
    return ROWS_DIR / _safe(project) / "followups.json"


def load_followups(project, entry_id):
    """读取某个条目的跟进记录（时间正序）。"""
    p = followups_file(project)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data.get(entry_id, [])


def add_followup(project, entry_id, fields, author, author_username=None):
    """往条目下追加一条跟进记录。类型为“纠错”时会把条目标记为“有纠错”。"""
    row = {k: str(v).strip() for k, v in fields.items() if str(v).strip()}
    row["fid"] = uuid.uuid4().hex[:12]
    row["author"] = (author or "").strip() or "匿名"
    if author_username:
        row["author_username"] = author_username
    row["timestamp"] = _now()
    row.setdefault("状态", "待处理")
    p = followups_file(project)
    lf = _acquire(p)
    try:
        data = {}
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
        data.setdefault(entry_id, []).append(row)
        _atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2))
        log(project, entry_id, "添加跟进", row["author"], row)
    finally:
        _release(lf)

    if row.get("类型") == "纠错":
        set_entry_field(project, entry_id, "纠错状态", "有纠错")
    return row


def resolve_followup(project, entry_id, fid, resolver):
    """把某条纠错跟进标记为已处理；若全部纠错都已处理，条目标记回“无纠错”。"""
    p = followups_file(project)
    if not p.exists():
        return None
    lf = _acquire(p)
    updated = None
    try:
        data = {}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        for row in data.get(entry_id, []):
            if row.get("fid") == fid:
                row["状态"] = "已处理"
                row["处理人"] = (resolver or "").strip() or "匿名"
                row["处理时间"] = _now()
                updated = row
                break
        if updated:
            _atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2))
            log(project, entry_id, "纠错已处理", resolver or "匿名", {"fid": fid})
    finally:
        _release(lf)

    if updated:
        remaining = [r for r in load_followups(project, entry_id)
                     if r.get("类型") == "纠错" and r.get("状态") != "已处理"]
        if not remaining:
            set_entry_field(project, entry_id, "纠错状态", "无")
    return updated


def _norm(s):
    """归一化：去空白、标点、统一小写，用于相似比对。"""
    return re.sub(r"[\s\W_]+", "", str(s or "")).lower()


def find_duplicates(project, row_type, fields):
    """在项目内查找疑似重复条目，返回候选列表（最多 6 条），每条带 reason。

    企业条目：企业名相同即视为疑似重复。
    新闻条目：来源链接相同，或 企业名相同且事件相同/高度相似（或未填事件）。
    """
    import difflib
    cands = []
    base = ROWS_DIR / _safe(project)
    if not base.exists():
        return cands
    target_name = _norm(fields.get("企业", ""))
    target_event = _norm(fields.get("事件", ""))
    target_link = str(fields.get("来源链接", "")).strip()
    if not target_name and not target_link:
        return cands
    for f in sorted(base.glob("*.json")):
        if f.name in ("changelog.json", "followups.json", "trash.json"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        key = "companies" if row_type == "company" else "news"
        for row in data.get(key, []):
            name_match = bool(target_name) and _norm(row.get("企业", "")) == target_name
            link_match = False
            if target_link:
                link = str(row.get("来源链接", "")).strip()
                if link and link == target_link:
                    link_match = True
            dup = False
            reason = ""
            if row_type == "company":
                if name_match:
                    dup = True
                    reason = "企业名相同"
            else:
                ev = _norm(row.get("事件", ""))
                event_match = False
                if target_event and ev:
                    if target_event == ev:
                        event_match = True
                    elif len(target_event) >= 6 and len(ev) >= 6:
                        event_match = difflib.SequenceMatcher(None, target_event, ev).ratio() >= 0.75
                if link_match:
                    dup = True
                    reason = "来源链接相同"
                elif name_match and event_match:
                    dup = True
                    reason = "企业相同且事件高度相似"
                elif name_match and not target_event:
                    dup = True
                    reason = "企业相同（未填事件，请确认）"
            if dup:
                cands.append({
                    "entry_id": row.get("entry_id", ""),
                    "node_id": f.stem,
                    "reason": reason,
                    "row": row,
                })
                if len(cands) >= 6:
                    return cands
    return cands


def find_entry(project, entry_id):
    """按 entry_id 查找条目，返回 (node_id, rtype, row)；未找到返回 (None, None, None)。"""
    base = ROWS_DIR / _safe(project)
    if not base.exists():
        return None, None, None
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
                    return f.stem, rtype, row
    return None, None, None


def update_row(project, entry_id, updates, editor=None):
    """按 entry_id 更新行内字段；传入 editor 时记录最后编辑人与时间。
    返回 (node_id, list_key) 或 (None, None)。"""
    base = ROWS_DIR / _safe(project)
    if not base.exists():
        return None, None
    for f in sorted(base.glob("*.json")):
        if f.name in ("changelog.json", "followups.json", "trash.json"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for key in ("companies", "news"):
            for row in data.get(key, []):
                if row.get("entry_id") == entry_id:
                    lf = _acquire(f)
                    try:
                        row.update(updates)
                        if editor:
                            row["最后编辑人"] = (editor or "").strip() or "匿名"
                            row["最后编辑时间"] = _now()
                        _atomic_write(f, json.dumps(data, ensure_ascii=False, indent=2))
                        if editor:
                            log(project, f.stem, "编辑条目", row.get("最后编辑人"),
                                {"entry_id": entry_id, "updates": updates})
                    finally:
                        _release(lf)
                    return f.stem, key
    return None, None


def _trash(project, row, operator, node_id):
    """把被删除的条目追加进 trash.json，误删可恢复。"""
    p = ROWS_DIR / _safe(project) / "trash.json"
    lf = _acquire(p)
    try:
        data = {}
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
        data.setdefault("items", []).append({
            "deleted_at": _now(),
            "deleted_by": (operator or "").strip() or "匿名",
            "original_node": node_id,
            "row": row,
        })
        _atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2))
    finally:
        _release(lf)


def delete_row(project, entry_id, operator):
    """删除条目：先存进 trash.json（可恢复），再从原文件移除。返回被删的 row。"""
    base = ROWS_DIR / _safe(project)
    if not base.exists():
        return None
    for f in sorted(base.glob("*.json")):
        if f.name in ("changelog.json", "followups.json", "trash.json"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for key in ("companies", "news"):
            for row in data.get(key, []):
                if row.get("entry_id") == entry_id:
                    lf = _acquire(f)
                    try:
                        data[key] = [r for r in data[key] if r.get("entry_id") != entry_id]
                        _atomic_write(f, json.dumps(data, ensure_ascii=False, indent=2))
                        _trash(project, row, operator, f.stem)
                        log(project, f.stem, "删除条目", (operator or "").strip() or "匿名",
                            {"entry_id": entry_id, "deleted": row})
                    finally:
                        _release(lf)
                    return row
    return None


def set_entry_field(project, entry_id, field, value):
    """给某个条目写入一个状态字段（如 纠错状态），不记录编辑人。"""
    node_id, key = update_row(project, entry_id, {field: value})
    return node_id is not None

def set_review_status(project, entry_id, status, reviewer):
    """把某条目的复核状态写回（待复核 / 已复核），并记录复核人与时间。"""
    base = ROWS_DIR / _safe(project)
    if not base.exists():
        return None
    for f in sorted(base.glob("*.json")):
        if f.name in ("changelog.json", "followups.json", "trash.json"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for key in ("companies", "news"):
            for row in data.get(key, []):
                if row.get("entry_id") == entry_id:
                    lf = _acquire(f)
                    try:
                        row["复核状态"] = status
                        row["复核人"] = (reviewer or "").strip() or "匿名"
                        row["复核时间"] = _now()
                        _atomic_write(f, json.dumps(data, ensure_ascii=False, indent=2))
                        log(project, f.stem, "标记复核", row.get("author", ""),
                            {"entry_id": entry_id, "status": status, "reviewer": row["复核人"]})
                    finally:
                        _release(lf)
                    return row
    return None
