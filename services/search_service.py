"""
统一搜索层 — 同时检索 clients / projects / tasks / files / daily_notes / daily_summaries / timeline_events。
"""
from database.db import fetch_all
from services.client_service import search_clients
from services.project_service import search_projects
from services.task_service import search_tasks
from services.timeline_service import search_events, EVENT_TYPE_LABELS
from services.summary_service import search_notes


def search_files(keyword=None, project_id=None, client_id=None, limit=100):
    conditions = []
    params = []
    if keyword:
        conditions.append("(filename LIKE ? OR summary LIKE ? OR tags LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw])
    if project_id is not None:
        conditions.append("project_id = ?")
        params.append(project_id)
    if client_id is not None:
        conditions.append("client_id = ?")
        params.append(client_id)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM files {where} ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return fetch_all(sql, tuple(params))


def search_summaries(keyword=None, start_date=None, end_date=None, limit=50):
    conditions = []
    params = []
    if keyword:
        conditions.append("content LIKE ?")
        params.append(f"%{keyword}%")
    if start_date:
        conditions.append("summary_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("summary_date <= ?")
        params.append(end_date)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM daily_summaries {where} ORDER BY summary_date DESC LIMIT ?"
    params.append(limit)
    return fetch_all(sql, tuple(params))


def global_search(keyword="", limit=10):
    """同时搜索所有7个数据表，返回统一结构。"""
    return {
        "clients": _normalize(search_clients(keyword=keyword, limit=limit), "client"),
        "projects": _normalize(search_projects(keyword=keyword, limit=limit), "project"),
        "tasks": _normalize(search_tasks(keyword=keyword, limit=limit), "task"),
        "files": _normalize(search_files(keyword=keyword, limit=limit), "file"),
        "notes": _normalize(search_notes(keyword=keyword, limit=limit), "note"),
        "summaries": _normalize(search_summaries(keyword=keyword, limit=limit), "summary"),
        "events": _normalize(search_events(keyword=keyword, limit=limit), "event"),
    }


def _normalize(items, item_type):
    """为每条结果添加 _type 标记。"""
    for item in items:
        item["_type"] = item_type
    return items


def build_context(results, project_map=None, client_map=None):
    """将搜索结果整理成 AI 可读的中文文本。"""
    if project_map is None:
        project_map = {}
    if client_map is None:
        client_map = {}

    sections = []

    if results.get("clients"):
        lines = ["【客户】"]
        for c in results["clients"]:
            lines.append(f"- {c['name']}")
            if c.get("description"):
                lines.append(f"  描述: {c['description'][:100]}")
            if c.get("contact_info"):
                lines.append(f"  联系方式: {c['contact_info']}")
        sections.append("\n".join(lines))

    if results.get("projects"):
        status_map = {"active": "进行中", "archived": "已归档", "completed": "已完成"}
        lines = ["【项目】"]
        for p in results["projects"]:
            s = status_map.get(p.get("status", ""), p.get("status", ""))
            client_name = ""
            if p.get("client_id") and p["client_id"] in client_map:
                client_name = f"，所属客户: {client_map[p['client_id']]}"
            lines.append(f"- {p['name']}（{s}{client_name}）")
            if p.get("description"):
                lines.append(f"  描述: {p['description'][:100]}")
        sections.append("\n".join(lines))

    if results.get("tasks"):
        status_map = {"todo": "待办", "doing": "进行中", "done": "已完成", "cancelled": "已取消"}
        priority_map = {"high": "高", "medium": "中", "low": "低"}
        lines = ["【任务】"]
        for t in results["tasks"]:
            s = status_map.get(t.get("status", ""), t.get("status", ""))
            p = priority_map.get(t.get("priority", ""), "")
            extra = []
            if t.get("due_date"):
                extra.append(f"截止: {t['due_date']}")
            if t.get("project_id") and t["project_id"] in project_map:
                extra.append(f"项目: {project_map[t['project_id']]}")
            if t.get("client_id") and t["client_id"] in client_map:
                extra.append(f"客户: {client_map[t['client_id']]}")
            context = f"（{', '.join(extra)}）" if extra else ""
            lines.append(f"- [{p}优先级] [{s}] {t['title']}{context}")
            if t.get("description"):
                lines.append(f"  {t['description'][:120]}")
        sections.append("\n".join(lines))

    if results.get("files"):
        lines = ["【文件】"]
        for f in results["files"]:
            tags_str = f" [标签: {f['tags']}]" if f.get("tags") else ""
            lines.append(f"- {f['filename']}{tags_str}")
            if f.get("summary"):
                lines.append(f"  摘要: {f['summary'][:150]}")
        sections.append("\n".join(lines))

    if results.get("events"):
        lines = ["【时间轴】"]
        current_date = None
        for e in results["events"]:
            if e.get("event_date") != current_date:
                current_date = e.get("event_date")
                lines.append(f"\n  {current_date}:")
            label = EVENT_TYPE_LABELS.get(e.get("event_type", ""), e.get("event_type", ""))
            line = f"  - [{label}] {e.get('title', '')}"
            if e.get("project_id") and e["project_id"] in project_map:
                line += f"（项目: {project_map[e['project_id']]}）"
            if e.get("client_id") and e["client_id"] in client_map:
                line += f"（客户: {client_map[e['client_id']]}）"
            if e.get("description"):
                desc = e["description"][:80]
                if desc:
                    line += f" — {desc}"
            lines.append(line)
        sections.append("\n".join(lines))

    if results.get("notes"):
        lines = ["【随手记】"]
        for n in results["notes"]:
            date_str = f"{n.get('note_date', '')}: " if n.get("note_date") else ""
            lines.append(f"- {date_str}{n['content'][:150]}")
        sections.append("\n".join(lines))

    if results.get("summaries"):
        lines = ["【每日总结】"]
        for s in results["summaries"]:
            content = s.get("content", "") or ""
            lines.append(f"- {s.get('summary_date', '')}: {content[:200]}")
        sections.append("\n".join(lines))

    if not sections:
        return "没有找到相关数据。"

    return "\n\n".join(sections)
