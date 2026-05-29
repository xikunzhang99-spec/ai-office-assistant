"""
详情查询服务 — 为客户/项目/任务提供完整关联信息视图。

- 优先通过 relations 表查询关联数据
- 若 relations 不完整，通过外键兜底查询
- 返回统一结构，供 pages/ 直接使用
"""
from services.client_service import get_client
from services.project_service import get_project
from services.task_service import get_task
from services.relation_service import get_related_entities, get_relation_network
from services.timeline_service import search_events, EVENT_TYPE_LABELS
from database.db import fetch_all


def get_client_detail(client_id: int) -> dict:
    """获取客户完整详情，包含关联项目、任务、文件、事件。"""
    basic = get_client(client_id)
    if not basic:
        return {
            "basic": None,
            "projects": [], "tasks": [], "files": [], "events": [],
            "notes": [], "summaries": [],
        }

    # 1. 通过 relations 获取关联实体
    related = get_related_entities("client", client_id)

    # 2. 兜底：通过 client_id 外键查询（补充 relations 中可能缺失的数据）
    fallback_projects = _fallback_projects_by_client(client_id)
    fallback_tasks = _fallback_tasks_by_client(client_id)
    fallback_files = _fallback_files_by_client(client_id)
    fallback_events = _fallback_events("client", client_id)

    # 3. 合并去重
    projects = _merge_by_id(related.get("projects", []), fallback_projects)
    tasks = _merge_by_id(related.get("tasks", []), fallback_tasks)
    files = _merge_by_id(related.get("files", []), fallback_files)
    events = _merge_by_id(related.get("events", []), fallback_events)

    # 4. 最近活动（按事件日期倒序取前10条）
    events.sort(key=lambda e: e.get("event_date", ""), reverse=True)

    return {
        "basic": basic,
        "projects": projects,
        "tasks": tasks,
        "files": files,
        "events": events,
    }


def get_project_detail(project_id: int) -> dict:
    """获取项目完整详情，包含所属客户、任务、文件、事件。"""
    basic = get_project(project_id)
    if not basic:
        return {
            "basic": None, "client": None,
            "tasks": [], "files": [], "events": [],
        }

    # 所属客户
    client = None
    if basic.get("client_id"):
        client = get_client(basic["client_id"])

    # 1. 通过 relations 获取关联实体
    related = get_related_entities("project", project_id)

    # 如果 relations 里没有客户，但 basic 有 client_id
    if client and not any(
        c["id"] == basic["client_id"] for c in related.get("clients", [])
    ):
        related.setdefault("clients", []).append(client)

    # 2. 兜底：通过 project_id 外键查询
    fallback_tasks = _fallback_tasks_by_project(project_id)
    fallback_files = _fallback_files_by_project(project_id)
    fallback_events = _fallback_events("project", project_id)

    # 3. 合并去重
    tasks = _merge_by_id(related.get("tasks", []), fallback_tasks)
    files = _merge_by_id(related.get("files", []), fallback_files)
    events = _merge_by_id(related.get("events", []), fallback_events)
    clients = related.get("clients", [])

    # 4. 任务统计
    done_count = sum(1 for t in tasks if t["status"] == "done")
    todo_count = sum(1 for t in tasks if t["status"] == "todo")
    doing_count = sum(1 for t in tasks if t["status"] == "doing")
    high_priority = [t for t in tasks if t["priority"] == "high" and t["status"] != "done"]
    uncompleted = [t for t in tasks if t["status"] not in ("done", "cancelled")]
    status_changes = [e for e in events if e.get("event_type") == "task_status_changed"]

    events.sort(key=lambda e: e.get("event_date", ""), reverse=True)

    return {
        "basic": basic,
        "client": clients[0] if clients else client,
        "tasks": tasks,
        "files": files,
        "events": events,
        "stats": {
            "total_tasks": len(tasks),
            "done": done_count,
            "doing": doing_count,
            "todo": todo_count,
            "progress": done_count / len(tasks) if tasks else 0,
        },
        "high_priority_tasks": high_priority,
        "uncompleted_tasks": uncompleted,
        "status_changes": status_changes,
    }


def get_task_detail(task_id: int) -> dict:
    """获取任务完整详情，包含所属项目/客户、相关文件、事件、状态变更记录。"""
    basic = get_task(task_id)
    if not basic:
        return {
            "basic": None, "project": None, "client": None,
            "files": [], "events": [],
        }

    # 所属项目/客户
    project = None
    client = None
    if basic.get("project_id"):
        project = get_project(basic["project_id"])
    if basic.get("client_id"):
        client = get_client(basic["client_id"])

    # 1. 通过 relations 获取关联实体
    related = get_related_entities("task", task_id)

    # 兜底：如果外键有值但 relations 没有
    if project and not any(
        p["id"] == basic["project_id"] for p in related.get("projects", [])
    ):
        related.setdefault("projects", []).append(project)
    if client and not any(
        c["id"] == basic["client_id"] for c in related.get("clients", [])
    ):
        related.setdefault("clients", []).append(client)

    # 2. 兜底：查询直接关联的事件
    fallback_events = _fallback_events("task", task_id)

    # 3. 合并去重
    files = related.get("files", [])
    events = _merge_by_id(related.get("events", []), fallback_events)

    # 状态变更记录（从事件中筛选）
    status_changes = [e for e in events if e.get("event_type") in (
        "task_status_changed", "task_completed"
    )]
    events.sort(key=lambda e: e.get("event_date", ""), reverse=True)

    projects = related.get("projects", [])
    clients = related.get("clients", [])

    return {
        "basic": basic,
        "project": projects[0] if projects else project,
        "client": clients[0] if clients else client,
        "files": files,
        "events": events,
        "status_changes": status_changes,
    }


# ── 兜底查询（通过外键） ──

def _fallback_projects_by_client(client_id: int) -> list:
    return fetch_all(
        "SELECT * FROM projects WHERE client_id = ? ORDER BY created_at DESC",
        (client_id,),
    )


def _fallback_tasks_by_client(client_id: int) -> list:
    return fetch_all(
        "SELECT * FROM tasks WHERE client_id = ? ORDER BY created_at DESC",
        (client_id,),
    )


def _fallback_tasks_by_project(project_id: int) -> list:
    return fetch_all(
        "SELECT * FROM tasks WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    )


def _fallback_files_by_client(client_id: int) -> list:
    return fetch_all(
        "SELECT * FROM files WHERE client_id = ? ORDER BY created_at DESC",
        (client_id,),
    )


def _fallback_files_by_project(project_id: int) -> list:
    return fetch_all(
        "SELECT * FROM files WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    )


def _fallback_events(related_type: str, related_id: int) -> list:
    if related_type == "project":
        return search_events(project_id=related_id, limit=100)
    elif related_type == "client":
        return search_events(client_id=related_id, limit=100)
    else:
        return fetch_all(
            """SELECT * FROM timeline_events
               WHERE related_type = ? AND related_id = ?
               ORDER BY event_date DESC LIMIT 100""",
            (related_type, related_id),
        )


def summarize_entity_detail(entity_type: str, detail: dict) -> str:
    """根据详情数据，调用 AI 生成简洁的中文总结。"""
    from services.ai_service import _chat

    if not detail or not detail.get("basic"):
        return "数据不足，无法生成总结。"

    basic = detail["basic"]
    prompt_parts = []

    if entity_type == "client":
        prompt_parts.append(f"客户名称: {basic.get('name', '')}")
        prompt_parts.append(f"描述: {basic.get('description', '无')}")
        prompt_parts.append(f"联系方式: {basic.get('contact_info', '无')}")
        prompt_parts.append(f"关联项目数: {len(detail.get('projects', []))}")
        prompt_parts.append(f"关联任务数: {len(detail.get('tasks', []))}")
        prompt_parts.append(f"关联文件数: {len(detail.get('files', []))}")
        prompt_parts.append(f"关联事件数: {len(detail.get('events', []))}")
        for p in detail.get("projects", [])[:5]:
            s = {"active": "进行中", "archived": "已归档", "completed": "已完成"}.get(p.get("status", ""), "")
            prompt_parts.append(f"- 项目: {p['name']}（{s}）")
        for t in detail.get("tasks", [])[:5]:
            prompt_parts.append(f"- 任务: {t['title']}（{t.get('status', '')}）")

    elif entity_type == "project":
        prompt_parts.append(f"项目名称: {basic.get('name', '')}")
        prompt_parts.append(f"描述: {basic.get('description', '无')}")
        prompt_parts.append(f"状态: {basic.get('status', '')}")
        c = detail.get("client")
        if c:
            prompt_parts.append(f"所属客户: {c['name']}")
        stats = detail.get("stats", {})
        prompt_parts.append(f"总任务: {stats.get('total_tasks', 0)}，完成: {stats.get('done', 0)}，进行中: {stats.get('doing', 0)}，待办: {stats.get('todo', 0)}")
        prompt_parts.append(f"高优先级未完成: {len(detail.get('high_priority_tasks', []))}")
        for t in detail.get("tasks", [])[:5]:
            prompt_parts.append(f"- 任务: {t['title']}（{t.get('status', '')}）")

    elif entity_type == "task":
        prompt_parts.append(f"任务标题: {basic.get('title', '')}")
        prompt_parts.append(f"描述: {basic.get('description', '无')}")
        prompt_parts.append(f"状态: {basic.get('status', '')}，优先级: {basic.get('priority', '')}")
        if basic.get("due_date"):
            prompt_parts.append(f"截止日期: {basic['due_date']}")
        p = detail.get("project")
        if p:
            prompt_parts.append(f"所属项目: {p['name']}")
        c = detail.get("client")
        if c:
            prompt_parts.append(f"所属客户: {c['name']}")
        prompt_parts.append(f"关联文件: {len(detail.get('files', []))}")
        prompt_parts.append(f"状态变更次数: {len(detail.get('status_changes', []))}")

    prompt = (
        f"根据以下数据，用3-5句话总结{entity_type}的当前情况。用中文，简洁直接，Markdown格式。\n\n"
        + "\n".join(prompt_parts)
    )
    return _chat(prompt)


def _merge_by_id(*lists) -> list:
    """合并多个列表，按 id 去重，保留首次出现的记录。"""
    seen = {}
    for lst in lists:
        for item in lst:
            item_id = item.get("id")
            if item_id is not None and item_id not in seen:
                seen[item_id] = item
    return list(seen.values())
