import json
from database.db import insert, fetch_one, fetch_all, execute
from services.timeline_service import add_event
from services.relation_service import add_relation, delete_relations_for
from utils.date_utils import now_str, today_str


def create_task(title: str, description: str = "", priority: str = "medium", due_date: str = "",
                project_id: int = None, client_id: int = None, tags: str = "") -> int:
    task_id = insert(
        """INSERT INTO tasks (title, description, status, priority, due_date, project_id, client_id, tags, created_at, updated_at)
           VALUES (?, ?, 'todo', ?, ?, ?, ?, ?, ?, ?)""",
        (title, description, priority, due_date, project_id, client_id, tags, now_str(), now_str()),
    )
    pid = project_id if project_id else None
    cid = client_id if client_id else None
    add_event("task_created", f"创建任务: {title}", description,
              "task", task_id, project_id=pid, client_id=cid, tags=tags)
    if pid:
        add_relation("task", task_id, "project", project_id, "belongs_to",
                     f"任务「{title}」属于该项目")
    if cid:
        add_relation("task", task_id, "client", client_id, "belongs_to",
                     f"任务「{title}」属于该客户")
    from services.knowledge_service import sync_task_to_knowledge
    sync_task_to_knowledge(task_id)
    return task_id


def get_or_create_task(title: str, description: str = "", priority: str = "medium",
                        due_date: str = "", project_id: int = None, client_id: int = None,
                        tags: str = "") -> dict:
    """幂等创建任务 — 按 title + project_id + client_id + due_date 判断重复。

    Returns:
        {task_id: int, created: bool, message: str}
    """
    # 查询同名、同项目、同客户、同截止日期的未删除任务
    existing = fetch_one(
        """SELECT * FROM tasks
           WHERE title = ? AND due_date = ?
           AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))
           AND (client_id = ? OR (client_id IS NULL AND ? IS NULL))
           LIMIT 1""",
        (title, due_date or "", project_id, project_id, client_id, client_id),
    )
    if existing:
        # 补充可能缺失的关系
        if project_id:
            add_relation("task", existing["id"], "project", project_id, "belongs_to",
                         f"任务「{title}」属于该项目")
        if client_id:
            add_relation("task", existing["id"], "client", client_id, "belongs_to",
                         f"任务「{title}」属于该客户")
        return {"task_id": existing["id"], "created": False, "message": f"任务「{title}」已存在"}

    task_id = create_task(title, description, priority, due_date, project_id, client_id, tags)
    return {"task_id": task_id, "created": True, "message": f"已创建任务「{title}」"}


def update_task(task_id: int, **kwargs) -> bool:
    old_task = get_task(task_id)
    allowed = ["title", "description", "status", "priority", "due_date", "project_id", "client_id", "tags", "show_on_calendar", "calendar_date"]
    updates = []
    values = []
    for k in allowed:
        if k in kwargs:
            updates.append(f"{k} = ?")
            values.append(kwargs[k])
    if not updates:
        return False
    updates.append("updated_at = ?")
    values.append(now_str())
    if kwargs.get("status") == "done":
        updates.append("completed_at = ?")
        values.append(now_str())
    values.append(task_id)
    execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", tuple(values))

    task = get_task(task_id)
    if not task:
        return True

    pid = task["project_id"] if task["project_id"] else None
    cid = task["client_id"] if task["client_id"] else None

    # Create relations when project_id or client_id is newly set
    if "project_id" in kwargs and pid:
        add_relation("task", task_id, "project", pid, "belongs_to",
                     f"任务「{task['title']}」属于该项目")
    if "client_id" in kwargs and cid:
        add_relation("task", task_id, "client", cid, "belongs_to",
                     f"任务「{task['title']}」属于该客户")

    from services.knowledge_service import sync_task_to_knowledge
    sync_task_to_knowledge(task_id)

    if "status" in kwargs:
        new_status = kwargs["status"]
        if new_status == "done":
            add_event("task_completed", f"完成任务: {task['title']}", "",
                      "task", task_id, project_id=pid, client_id=cid)
        else:
            old_status = old_task["status"] if old_task else "?"
            meta = json.dumps({"old_status": old_status, "new_status": new_status}, ensure_ascii=False)
            add_event("task_status_changed", f"任务状态变更: {task['title']}",
                      f"{old_status} → {new_status}",
                      "task", task_id, project_id=pid, client_id=cid, metadata=meta)
    else:
        changes = {}
        for k in kwargs:
            if k in allowed and old_task and old_task[k] != kwargs[k]:
                changes[k] = {"old": old_task[k], "new": kwargs[k]}
        if changes:
            meta = json.dumps(changes, ensure_ascii=False)
            add_event("task_updated", f"修改任务: {task['title']}",
                      str(changes), "task", task_id,
                      project_id=pid, client_id=cid, metadata=meta)
    return True


def delete_task(task_id: int) -> bool:
    task = get_task(task_id)
    if task:
        pid = task["project_id"] if task["project_id"] else None
        cid = task["client_id"] if task["client_id"] else None
        add_event("task_deleted", f"删除任务: {task['title']}", "", "task", task_id,
                  project_id=pid, client_id=cid)
    delete_relations_for("task", task_id)
    execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    from services.knowledge_service import delete_knowledge_item
    delete_knowledge_item("task", task_id)
    return True


def get_task(task_id: int):
    return fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,))


def get_tasks_by_date(date_str: str) -> list:
    return fetch_all(
        "SELECT * FROM tasks WHERE due_date = ? OR date(created_at) = ? ORDER BY priority DESC, created_at DESC",
        (date_str, date_str),
    )


def get_tasks_by_status(status: str) -> list:
    return fetch_all("SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC", (status,))


def get_tasks_by_date_range(start_date: str, end_date: str) -> list:
    return fetch_all(
        "SELECT * FROM tasks WHERE due_date >= ? AND due_date <= ? ORDER BY due_date ASC, priority DESC",
        (start_date, end_date),
    )


def get_all_tasks(limit: int = 200) -> list:
    return fetch_all("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,))


def get_today_tasks() -> list:
    return get_tasks_by_date(today_str())


def get_overdue_tasks() -> list:
    return fetch_all(
        "SELECT * FROM tasks WHERE status != 'done' AND status != 'cancelled' AND due_date < ? AND due_date != '' ORDER BY due_date ASC",
        (today_str(),),
    )


def mark_task_on_calendar(task_id: int, calendar_date: str = None) -> bool:
    """标记任务显示到日历。calendar_date 为空则使用 due_date。"""
    task = get_task(task_id)
    if not task:
        return False
    cal_date = calendar_date or task.get("due_date") or ""
    execute(
        "UPDATE tasks SET show_on_calendar = 1, calendar_date = ?, updated_at = ? WHERE id = ?",
        (cal_date, now_str(), task_id),
    )
    return True


def unmark_task_from_calendar(task_id: int) -> bool:
    """取消任务的日历标记。"""
    execute(
        "UPDATE tasks SET show_on_calendar = 0, calendar_date = NULL, updated_at = ? WHERE id = ?",
        (now_str(), task_id),
    )
    return True


def get_calendar_tasks(year: int, month: int) -> list:
    """获取指定月份被标记到日历的任务。"""
    import calendar as cal_mod
    start_date = f"{year}-{month:02d}-01"
    last_day = cal_mod.monthrange(year, month)[1]
    end_date = f"{year}-{month:02d}-{last_day:02d}"

    return fetch_all(
        """SELECT * FROM tasks
           WHERE show_on_calendar = 1
             AND date(COALESCE(calendar_date, due_date)) BETWEEN date(?) AND date(?)
           ORDER BY COALESCE(calendar_date, due_date) ASC""",
        (start_date, end_date),
    )


def add_task_note(task_id: int, content: str) -> int:
    """为任务添加备注，返回备注ID。"""
    return insert(
        "INSERT INTO task_notes (task_id, content, created_at) VALUES (?, ?, ?)",
        (task_id, content, now_str()),
    )


def get_task_notes(task_id: int) -> list:
    """获取任务的所有备注，按时间倒序。"""
    return fetch_all(
        "SELECT * FROM task_notes WHERE task_id = ? ORDER BY created_at DESC",
        (task_id,),
    )


def search_tasks(keyword: str = None, status: str = None, project_id: int = None,
                 client_id: int = None, priority: str = None,
                 start_date: str = None, end_date: str = None, limit: int = 200) -> list:
    conditions = []
    params = []
    if keyword:
        conditions.append("(title LIKE ? OR description LIKE ? OR tags LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw])
    if status:
        conditions.append("status = ?")
        params.append(status)
    if project_id is not None:
        conditions.append("project_id = ?")
        params.append(project_id)
    if client_id is not None:
        conditions.append("client_id = ?")
        params.append(client_id)
    if priority:
        conditions.append("priority = ?")
        params.append(priority)
    if start_date:
        conditions.append("(due_date >= ? OR created_at >= ?)")
        params.extend([start_date, start_date])
    if end_date:
        conditions.append("(due_date <= ? OR created_at <= ?)")
        params.extend([end_date, end_date])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM tasks {where} ORDER BY priority DESC, created_at DESC LIMIT ?"
    params.append(limit)
    return fetch_all(sql, tuple(params))
