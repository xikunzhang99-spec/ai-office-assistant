"""
Obsidian 同步服务 — 将实体数据导出为带 frontmatter 的 Markdown 文件。
Phase 12：完整重写，支持 clients/projects/tasks/files/daily_summaries 同步。
"""
import os
import re
import hashlib
from config.settings import OBSIDIAN_VAULT_PATH
from utils.date_utils import now_str, today_str

BASE_FOLDER = "AI办公助理"


# ── 基础工具函数 ──

def is_configured() -> bool:
    """检查 Obsidian Vault 路径是否已配置且存在。"""
    return bool(OBSIDIAN_VAULT_PATH) and os.path.isdir(OBSIDIAN_VAULT_PATH)


def get_obsidian_base_path() -> str | None:
    """获取 Obsidian Vault 路径。未配置或不存在时返回 None。"""
    if not OBSIDIAN_VAULT_PATH:
        return None
    if not os.path.isdir(OBSIDIAN_VAULT_PATH):
        return None
    return OBSIDIAN_VAULT_PATH


def sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符。"""
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = name.strip(' .')
    if len(name) > 120:
        name = name[:120]
    return name


def build_frontmatter(data: dict) -> str:
    """生成 YAML frontmatter 字符串。"""
    lines = ["---"]
    lines.append(f"source_type: {data.get('source_type', '')}")
    lines.append(f"source_id: {data.get('source_id', '')}")
    tags = data.get("tags", [])
    if tags:
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        if tags:
            lines.append("tags:")
            for t in tags:
                lines.append(f"  - {t}")
    lines.append(f"updated_at: {data.get('updated_at', now_str())}")
    lines.append("---")
    return "\n".join(lines)


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _write_markdown_internal(relative_path: str, content: str) -> str:
    """底层写入：创建目录 + utf-8 写入。返回完整文件路径。"""
    full_path = os.path.join(OBSIDIAN_VAULT_PATH, relative_path)
    _ensure_dir(os.path.dirname(full_path))
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    return full_path


def _compute_hash(content: str) -> str:
    """计算内容的 MD5 哈希。"""
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def _should_sync(source_type: str, source_id: int, content: str) -> bool:
    """检查内容是否变化，决定是否需要同步。"""
    from services.obsidian_log_service import get_sync_log
    existing = get_sync_log(source_type, source_id)
    if not existing:
        return True
    new_hash = _compute_hash(content)
    return existing.get("content_hash") != new_hash


# ── 向后兼容的函数 ──

def write_daily_note(date_str: str, content: str) -> str:
    """写入每日总结到 Obsidian（向后兼容）。"""
    folder = os.path.join(OBSIDIAN_VAULT_PATH, BASE_FOLDER, "Daily")
    _ensure_dir(folder)
    filepath = os.path.join(folder, f"{date_str}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


def write_file_summary(filename: str, content: str) -> str:
    """写入文件摘要到 Obsidian（向后兼容）。"""
    from utils.text_utils import safe_filename
    folder = os.path.join(OBSIDIAN_VAULT_PATH, BASE_FOLDER, "Files")
    _ensure_dir(folder)
    safe_name = safe_filename(filename)
    filepath = os.path.join(folder, f"{safe_name}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


# ── 实体同步函数 ──

def sync_client_to_obsidian(client_id: int) -> dict:
    """同步单个客户到 Obsidian。"""
    if not is_configured():
        return {"success": False, "path": "", "message": "Obsidian Vault 未配置或路径不存在", "skipped": False}

    from services.client_service import get_client
    from services.relation_service import get_relation_network
    from services.timeline_service import search_events

    client = get_client(client_id)
    if not client:
        return {"success": False, "path": "", "message": f"客户 {client_id} 不存在", "skipped": False}

    name = client["name"]
    safe_name = sanitize_filename(name)

    network = get_relation_network("client", client_id)
    projects = network.get("projects", [])
    tasks = network.get("tasks", [])
    events = search_events(client_id=client_id, limit=30)

    lines = []
    lines.append(build_frontmatter({
        "source_type": "client",
        "source_id": client_id,
        "tags": ["client", "ai-office"],
        "updated_at": client.get("updated_at", now_str()),
    }))
    lines.append("")
    lines.append(f"# {name}")
    lines.append("")
    lines.append("## 基础信息")
    lines.append("")
    if client.get("description"):
        lines.append(f"- 描述: {client['description']}")
    if client.get("contact_info"):
        lines.append(f"- 联系方式: {client['contact_info']}")
    lines.append(f"- 创建时间: {client.get('created_at', '')}")
    lines.append(f"- 更新时间: {client.get('updated_at', '')}")
    lines.append("")

    if projects:
        lines.append("## 关联项目")
        lines.append("")
        for p in projects:
            s_map = {"active": "进行中", "archived": "已归档", "completed": "已完成"}
            s = s_map.get(p.get("status", ""), p.get("status", ""))
            lines.append(f"- [{s}] {p['name']}")
            if p.get("description"):
                lines.append(f"  - {p['description'][:100]}")
        lines.append("")

    if tasks:
        lines.append("## 关联任务")
        lines.append("")
        for t in tasks[:20]:
            s_map = {"todo": "待办", "doing": "进行中", "done": "已完成", "cancelled": "已取消"}
            s = s_map.get(t.get("status", ""), t.get("status", ""))
            p_map = {"high": "高", "medium": "中", "low": "低"}
            p_label = p_map.get(t.get("priority", ""), t.get("priority", ""))
            lines.append(f"- [{s}] [{p_label}] {t['title']}")
            if t.get("due_date"):
                lines.append(f"  - 截止: {t['due_date']}")
        lines.append("")

    if events:
        lines.append("## 最近动态")
        lines.append("")
        for e in events[:10]:
            from services.timeline_service import EVENT_TYPE_LABELS
            label = EVENT_TYPE_LABELS.get(e.get("event_type", ""), e.get("event_type", ""))
            date_str = e.get("event_date", "")[:10] if e.get("event_date") else ""
            lines.append(f"- [{date_str}] {label}: {e.get('title', '')}")
        lines.append("")

    content = "\n".join(lines)
    content_hash = _compute_hash(content)

    if not _should_sync("client", client_id, content):
        return {"success": True, "path": "", "message": f"客户「{name}」内容无变化，已跳过", "skipped": True}

    relative_path = os.path.join(BASE_FOLDER, "Clients", f"{safe_name}.md")
    try:
        full_path = _write_markdown_internal(relative_path, content)
        from services.obsidian_log_service import upsert_sync_log
        upsert_sync_log("client", client_id, relative_path, content_hash, "success")
        _log_workflow("sync_client", client_id, "success", f"同步客户: {name}")
        return {"success": True, "path": full_path, "message": f"客户「{name}」已同步", "skipped": False}
    except Exception as e:
        from services.obsidian_log_service import upsert_sync_log
        upsert_sync_log("client", client_id, relative_path, content_hash, "error")
        _log_workflow("sync_client", client_id, "error", str(e))
        return {"success": False, "path": "", "message": f"写入失败: {e}", "skipped": False}


def sync_project_to_obsidian(project_id: int) -> dict:
    """同步单个项目到 Obsidian。"""
    if not is_configured():
        return {"success": False, "path": "", "message": "Obsidian Vault 未配置或路径不存在", "skipped": False}

    from services.project_service import get_project
    from services.relation_service import get_relation_network
    from services.timeline_service import search_events
    from services.task_service import search_tasks

    project = get_project(project_id)
    if not project:
        return {"success": False, "path": "", "message": f"项目 {project_id} 不存在", "skipped": False}

    name = project["name"]
    safe_name = sanitize_filename(name)
    status = project.get("status", "active")

    network = get_relation_network("project", project_id)
    clients = network.get("clients", [])
    tasks = search_tasks(project_id=project_id, limit=100)
    events = search_events(project_id=project_id, limit=30)

    total = len(tasks)
    done = sum(1 for t in tasks if t["status"] == "done")
    doing = sum(1 for t in tasks if t["status"] == "doing")
    todo = sum(1 for t in tasks if t["status"] == "todo")

    s_map = {"active": "进行中", "archived": "已归档", "completed": "已完成"}

    lines = []
    lines.append(build_frontmatter({
        "source_type": "project",
        "source_id": project_id,
        "tags": ["project", "ai-office"],
        "updated_at": project.get("updated_at", now_str()),
    }))
    lines.append("")
    lines.append(f"# {name}")
    lines.append("")
    lines.append("## 基础信息")
    lines.append("")
    lines.append(f"- 状态: {s_map.get(status, status)}")
    if project.get("description"):
        lines.append(f"- 描述: {project['description']}")
    lines.append(f"- 创建时间: {project.get('created_at', '')}")
    lines.append(f"- 更新时间: {project.get('updated_at', '')}")
    lines.append("")

    if clients:
        lines.append("## 所属客户")
        lines.append("")
        for c in clients:
            lines.append(f"- {c['name']}")
        lines.append("")

    lines.append("## 任务进度")
    lines.append("")
    progress = done / total if total > 0 else 0
    lines.append(f"- 总任务: {total} | 已完成: {done} | 进行中: {doing} | 待办: {todo}")
    lines.append(f"- 完成率: {progress:.0%}")
    lines.append("")

    uncompleted = [t for t in tasks if t["status"] not in ("done", "cancelled")]
    if uncompleted:
        lines.append("### 未完成任务")
        lines.append("")
        p_map = {"high": "高", "medium": "中", "low": "低"}
        for t in uncompleted:
            p_label = p_map.get(t.get("priority", ""), t.get("priority", ""))
            lines.append(f"- [{p_label}] {t['title']}")
            if t.get("due_date"):
                lines.append(f"  - 截止: {t['due_date']}")
        lines.append("")

    if events:
        lines.append("## 最近动态")
        lines.append("")
        for e in events[:10]:
            from services.timeline_service import EVENT_TYPE_LABELS
            label = EVENT_TYPE_LABELS.get(e.get("event_type", ""), e.get("event_type", ""))
            date_str = e.get("event_date", "")[:10] if e.get("event_date") else ""
            lines.append(f"- [{date_str}] {label}: {e.get('title', '')}")
        lines.append("")

    content = "\n".join(lines)
    content_hash = _compute_hash(content)

    if not _should_sync("project", project_id, content):
        return {"success": True, "path": "", "message": f"项目「{name}」内容无变化，已跳过", "skipped": True}

    subfolder = "Archive" if status in ("archived", "completed") else "Active"
    relative_path = os.path.join(BASE_FOLDER, "Projects", subfolder, f"{safe_name}.md")

    try:
        full_path = _write_markdown_internal(relative_path, content)

        # 状态变化导致路径迁移时，删除旧文件
        other_subfolder = "Active" if subfolder == "Archive" else "Archive"
        old_path = os.path.join(BASE_FOLDER, "Projects", other_subfolder, f"{safe_name}.md")
        old_full = os.path.join(OBSIDIAN_VAULT_PATH, old_path)
        if os.path.exists(old_full) and old_path != relative_path:
            try:
                os.remove(old_full)
            except Exception:
                pass

        from services.obsidian_log_service import upsert_sync_log
        upsert_sync_log("project", project_id, relative_path, content_hash, "success")
        _log_workflow("sync_project", project_id, "success", f"同步项目: {name}")
        return {"success": True, "path": full_path, "message": f"项目「{name}」已同步", "skipped": False}
    except Exception as e:
        from services.obsidian_log_service import upsert_sync_log
        upsert_sync_log("project", project_id, relative_path, content_hash, "error")
        _log_workflow("sync_project", project_id, "error", str(e))
        return {"success": False, "path": "", "message": f"写入失败: {e}", "skipped": False}


def sync_task_to_obsidian(task_id: int) -> dict:
    """同步单个任务到 Obsidian。"""
    if not is_configured():
        return {"success": False, "path": "", "message": "Obsidian Vault 未配置或路径不存在", "skipped": False}

    from services.task_service import get_task

    task = get_task(task_id)
    if not task:
        return {"success": False, "path": "", "message": f"任务 {task_id} 不存在", "skipped": False}

    title = task["title"]
    safe_title = sanitize_filename(title)
    task_status = task.get("status", "todo")

    s_map = {"todo": "待办", "doing": "进行中", "done": "已完成", "cancelled": "已取消"}
    p_map = {"high": "高", "medium": "中", "low": "低"}

    project_name = ""
    client_name = ""
    if task.get("project_id"):
        from services.project_service import get_project
        p = get_project(task["project_id"])
        if p:
            project_name = p["name"]
    if task.get("client_id"):
        from services.client_service import get_client
        c = get_client(task["client_id"])
        if c:
            client_name = c["name"]

    related_events = _fetch_related_events("task", task_id, 20)

    tags = ["task", "ai-office"]
    if task.get("tags"):
        for t in task["tags"].split(","):
            t = t.strip()
            if t and t not in tags:
                tags.append(t)

    lines = []
    lines.append(build_frontmatter({
        "source_type": "task",
        "source_id": task_id,
        "tags": tags,
        "updated_at": task.get("updated_at", now_str()),
    }))
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## 基础信息")
    lines.append("")
    lines.append(f"- 状态: {s_map.get(task_status, task_status)}")
    lines.append(f"- 优先级: {p_map.get(task.get('priority', ''), task.get('priority', ''))}")
    if task.get("due_date"):
        lines.append(f"- 截止日期: {task['due_date']}")
    if task.get("description"):
        lines.append(f"- 描述: {task['description']}")
    if project_name:
        lines.append(f"- 所属项目: {project_name}")
    if client_name:
        lines.append(f"- 所属客户: {client_name}")
    lines.append(f"- 创建时间: {task.get('created_at', '')}")
    lines.append(f"- 更新时间: {task.get('updated_at', '')}")
    lines.append("")

    if related_events:
        lines.append("## 时间轴记录")
        lines.append("")
        for e in related_events[:10]:
            from services.timeline_service import EVENT_TYPE_LABELS
            label = EVENT_TYPE_LABELS.get(e.get("event_type", ""), e.get("event_type", ""))
            date_str = e.get("event_date", "")[:10] if e.get("event_date") else ""
            lines.append(f"- [{date_str}] {label}: {e.get('title', '')}")
            if e.get("description"):
                lines.append(f"  - {e['description'][:200]}")
        lines.append("")

    content = "\n".join(lines)
    content_hash = _compute_hash(content)

    if not _should_sync("task", task_id, content):
        return {"success": True, "path": "", "message": f"任务「{title}」内容无变化，已跳过", "skipped": True}

    subfolder = "Completed" if task_status in ("done", "cancelled") else "Active"
    relative_path = os.path.join(BASE_FOLDER, "Tasks", subfolder, f"{safe_title}.md")

    try:
        full_path = _write_markdown_internal(relative_path, content)

        other_subfolder = "Active" if subfolder == "Completed" else "Completed"
        old_path = os.path.join(BASE_FOLDER, "Tasks", other_subfolder, f"{safe_title}.md")
        old_full = os.path.join(OBSIDIAN_VAULT_PATH, old_path)
        if os.path.exists(old_full) and old_path != relative_path:
            try:
                os.remove(old_full)
            except Exception:
                pass

        from services.obsidian_log_service import upsert_sync_log
        upsert_sync_log("task", task_id, relative_path, content_hash, "success")
        _log_workflow("sync_task", task_id, "success", f"同步任务: {title}")
        return {"success": True, "path": full_path, "message": f"任务「{title}」已同步", "skipped": False}
    except Exception as e:
        from services.obsidian_log_service import upsert_sync_log
        upsert_sync_log("task", task_id, relative_path, content_hash, "error")
        _log_workflow("sync_task", task_id, "error", str(e))
        return {"success": False, "path": "", "message": f"写入失败: {e}", "skipped": False}


def sync_file_to_obsidian(file_id: int) -> dict:
    """同步单个文件摘要到 Obsidian。"""
    if not is_configured():
        return {"success": False, "path": "", "message": "Obsidian Vault 未配置或路径不存在", "skipped": False}

    from services.file_service import get_file
    import json as _json

    f = get_file(file_id)
    if not f:
        return {"success": False, "path": "", "message": f"文件 {file_id} 不存在", "skipped": False}

    filename = f["filename"]
    safe_name = sanitize_filename(filename)

    project_name = ""
    client_name = ""
    if f.get("project_id"):
        from services.project_service import get_project
        p = get_project(f["project_id"])
        if p:
            project_name = p["name"]
    if f.get("client_id"):
        from services.client_service import get_client
        c = get_client(f["client_id"])
        if c:
            client_name = c["name"]

    tags = ["file", "ai-office"]
    if f.get("tags"):
        for t in f["tags"].split(","):
            t = t.strip()
            if t and t not in tags:
                tags.append(t)

    lines = []
    lines.append(build_frontmatter({
        "source_type": "file",
        "source_id": file_id,
        "tags": tags,
        "updated_at": f.get("updated_at", now_str()),
    }))
    lines.append("")
    lines.append(f"# {filename}")
    lines.append("")
    lines.append("## 基础信息")
    lines.append("")
    lines.append(f"- 文件类型: {f.get('file_type', '')}")
    if project_name:
        lines.append(f"- 关联项目: {project_name}")
    if client_name:
        lines.append(f"- 关联客户: {client_name}")
    lines.append(f"- 上传时间: {f.get('created_at', '')}")
    lines.append("")

    if f.get("summary"):
        lines.append("## AI 摘要")
        lines.append("")
        lines.append(f["summary"])
        lines.append("")

    if f.get("key_points"):
        try:
            key_points = _json.loads(f["key_points"]) if isinstance(f["key_points"], str) else f["key_points"]
            if key_points:
                lines.append("## 关键点")
                lines.append("")
                for pt in key_points:
                    lines.append(f"- {pt}")
                lines.append("")
        except Exception:
            pass

    if f.get("tags"):
        lines.append("## 标签")
        lines.append("")
        lines.append(f["tags"])
        lines.append("")

    content = "\n".join(lines)
    content_hash = _compute_hash(content)

    if not _should_sync("file", file_id, content):
        return {"success": True, "path": "", "message": f"文件「{filename}」内容无变化，已跳过", "skipped": True}

    relative_path = os.path.join(BASE_FOLDER, "Files", f"{safe_name}.md")

    try:
        full_path = _write_markdown_internal(relative_path, content)
        from services.obsidian_log_service import upsert_sync_log
        upsert_sync_log("file", file_id, relative_path, content_hash, "success")
        _log_workflow("sync_file", file_id, "success", f"同步文件: {filename}")
        return {"success": True, "path": full_path, "message": f"文件「{filename}」已同步", "skipped": False}
    except Exception as e:
        from services.obsidian_log_service import upsert_sync_log
        upsert_sync_log("file", file_id, relative_path, content_hash, "error")
        _log_workflow("sync_file", file_id, "error", str(e))
        return {"success": False, "path": "", "message": f"写入失败: {e}", "skipped": False}


def sync_daily_summary_to_obsidian(date_str: str) -> dict:
    """同步某天的每日总结到 Obsidian。"""
    if not is_configured():
        return {"success": False, "path": "", "message": "Obsidian Vault 未配置或路径不存在", "skipped": False}

    from services.summary_service import get_summary_by_date
    from services.task_service import get_tasks_by_date
    from services.timeline_service import get_events_by_date
    from services.file_service import get_files_by_date

    summary = get_summary_by_date(date_str)
    tasks = get_tasks_by_date(date_str)
    events = get_events_by_date(date_str)
    files = get_files_by_date(date_str)

    lines = []
    lines.append(build_frontmatter({
        "source_type": "daily_summary",
        "source_id": 0,
        "tags": ["daily", "ai-office", date_str],
        "updated_at": now_str(),
    }))
    lines.append("")
    lines.append(f"# {date_str} 工作日报")
    lines.append("")

    if tasks:
        lines.append("## 今日任务")
        lines.append("")
        s_map = {"todo": "待办", "doing": "进行中", "done": "已完成", "cancelled": "已取消"}
        p_map = {"high": "高", "medium": "中", "low": "低"}
        for t in tasks:
            s = s_map.get(t.get("status", ""), t.get("status", ""))
            p_label = p_map.get(t.get("priority", ""), t.get("priority", ""))
            lines.append(f"- [{s}] [{p_label}] {t['title']}")
        lines.append("")

    if events:
        lines.append("## 今日事件")
        lines.append("")
        for e in events[:30]:
            from services.timeline_service import EVENT_TYPE_LABELS
            label = EVENT_TYPE_LABELS.get(e.get("event_type", ""), e.get("event_type", ""))
            lines.append(f"- [{label}] {e.get('title', '')}")
            if e.get("description"):
                lines.append(f"  - {e['description'][:200]}")
        lines.append("")

    if files:
        lines.append("## 今日文件")
        lines.append("")
        for f in files:
            lines.append(f"- {f['filename']}")
            if f.get("summary"):
                lines.append(f"  - {f['summary'][:200]}")
        lines.append("")

    if summary:
        lines.append("## AI 每日总结")
        lines.append("")
        lines.append(summary.get("content", ""))
        lines.append("")

    content = "\n".join(lines)
    content_hash = _compute_hash(content)

    source_id = summary["id"] if summary else abs(hash(date_str)) % 100000
    if not _should_sync("daily_summary", source_id, content):
        return {"success": True, "path": "", "message": f"每日总结 {date_str} 内容无变化，已跳过", "skipped": True}

    relative_path = os.path.join(BASE_FOLDER, "Daily", f"{date_str}.md")

    try:
        full_path = _write_markdown_internal(relative_path, content)
        from services.obsidian_log_service import upsert_sync_log
        upsert_sync_log("daily_summary", source_id, relative_path, content_hash, "success")
        _log_workflow("sync_daily_summary", source_id, "success", f"同步每日总结: {date_str}")
        return {"success": True, "path": full_path, "message": f"每日总结 {date_str} 已同步", "skipped": False}
    except Exception as e:
        from services.obsidian_log_service import upsert_sync_log
        upsert_sync_log("daily_summary", source_id, relative_path, content_hash, "error")
        _log_workflow("sync_daily_summary", source_id, "error", str(e))
        return {"success": False, "path": "", "message": f"写入失败: {e}", "skipped": False}


def sync_all_to_obsidian() -> dict:
    """批量同步所有实体到 Obsidian。"""
    from services.client_service import get_all_clients
    from services.project_service import get_all_projects
    from services.task_service import get_all_tasks
    from services.file_service import get_all_files
    from services.summary_service import get_all_summaries

    details = []
    success_count = 0
    fail_count = 0
    skip_count = 0

    for c in get_all_clients():
        r = sync_client_to_obsidian(c["id"])
        details.append({"type": "client", "id": c["id"], "name": c["name"], **r})
        if r["skipped"]: skip_count += 1
        elif r["success"]: success_count += 1
        else: fail_count += 1

    for p in get_all_projects():
        r = sync_project_to_obsidian(p["id"])
        details.append({"type": "project", "id": p["id"], "name": p["name"], **r})
        if r["skipped"]: skip_count += 1
        elif r["success"]: success_count += 1
        else: fail_count += 1

    for t in get_all_tasks(limit=1000):
        r = sync_task_to_obsidian(t["id"])
        details.append({"type": "task", "id": t["id"], "name": t["title"], **r})
        if r["skipped"]: skip_count += 1
        elif r["success"]: success_count += 1
        else: fail_count += 1

    for f in get_all_files(limit=1000):
        r = sync_file_to_obsidian(f["id"])
        details.append({"type": "file", "id": f["id"], "name": f["filename"], **r})
        if r["skipped"]: skip_count += 1
        elif r["success"]: success_count += 1
        else: fail_count += 1

    for s in get_all_summaries(limit=90):
        date_str = s.get("summary_date", "")
        if date_str:
            r = sync_daily_summary_to_obsidian(date_str)
            details.append({"type": "daily_summary", "id": s["id"], "name": date_str, **r})
            if r["skipped"]: skip_count += 1
            elif r["success"]: success_count += 1
            else: fail_count += 1

    _log_workflow("sync_all", 0, "success",
                  f"同步完成: 成功 {success_count} / 失败 {fail_count} / 跳过 {skip_count}")

    return {
        "success_count": success_count,
        "fail_count": fail_count,
        "skip_count": skip_count,
        "details": details,
    }


# ── 内部工具 ──

def _fetch_related_events(related_type: str, related_id: int, limit: int = 20) -> list:
    """查询与指定实体关联的时间轴事件。"""
    from database.db import fetch_all
    return fetch_all(
        """SELECT * FROM timeline_events
           WHERE related_type = ? AND related_id = ?
           ORDER BY event_date DESC, created_at DESC LIMIT ?""",
        (related_type, related_id, limit),
    )


def _log_workflow(workflow_type: str, source_id: int, status: str, message: str):
    """记录工作流日志。"""
    try:
        from services.workflow_log_service import add_workflow_log
        add_workflow_log(workflow_type, "obsidian", source_id, status, message, "")
    except Exception:
        pass
