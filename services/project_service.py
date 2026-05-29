import json
from database.db import insert, fetch_all, fetch_one, execute
from services.timeline_service import add_event
from services.relation_service import add_relation, delete_relations_for
from utils.date_utils import now_str


def create_project(name: str, description: str = "", client_id: int = None) -> int:
    project_id = insert(
        "INSERT INTO projects (name, description, status, client_id, created_at, updated_at) VALUES (?, ?, 'active', ?, ?, ?)",
        (name, description, client_id, now_str(), now_str()),
    )
    add_event("project_created", f"创建项目: {name}", description, "project", project_id, client_id=client_id)
    if client_id:
        add_relation("project", project_id, "client", client_id, "belongs_to",
                     f"项目「{name}」属于该客户")
    from services.knowledge_service import sync_project_to_knowledge
    sync_project_to_knowledge(project_id)
    return project_id


def get_or_create_project(name: str, description: str = "", client_id: int = None) -> dict:
    """幂等创建项目 — 同名项目已存在时返回已有记录。

    Returns:
        {project_id: int, created: bool, message: str}
    """
    existing = fetch_one("SELECT * FROM projects WHERE name = ?", (name,))
    if existing:
        # 补充缺失的客户关系
        if client_id:
            add_relation("project", existing["id"], "client", client_id, "belongs_to",
                         f"项目「{name}」属于该客户")
        return {"project_id": existing["id"], "created": False, "message": f"项目「{name}」已存在"}

    project_id = create_project(name, description, client_id)
    return {"project_id": project_id, "created": True, "message": f"已创建项目「{name}」"}


def get_all_projects() -> list:
    return fetch_all("SELECT * FROM projects ORDER BY created_at DESC")


def get_project(project_id: int):
    return fetch_one("SELECT * FROM projects WHERE id = ?", (project_id,))


def delete_project(project_id: int) -> bool:
    project = get_project(project_id)
    if project:
        add_event("project_deleted", f"删除项目: {project['name']}", "", "project", project_id)
    delete_relations_for("project", project_id)
    execute("DELETE FROM projects WHERE id = ?", (project_id,))
    from services.knowledge_service import delete_knowledge_item
    delete_knowledge_item("project", project_id)
    return True


def update_project(project_id: int, name: str = None, description: str = None,
                   status: str = None, client_id: int = None) -> bool:
    project = get_project(project_id)
    if not project:
        return False
    updates = []
    values = []
    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if description is not None:
        updates.append("description = ?")
        values.append(description)
    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if client_id is not None:
        updates.append("client_id = ?")
        values.append(client_id)
    if not updates:
        return False
    updates.append("updated_at = ?")
    values.append(now_str())
    values.append(project_id)
    execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", tuple(values))

    changed = []
    if name is not None and name != project["name"]:
        changed.append("name")
    if description is not None and description != (project["description"] or ""):
        changed.append("description")
    if status is not None and status != project["status"]:
        changed.append("status")
    if client_id is not None and client_id != project.get("client_id"):
        changed.append("client_id")

    meta = json.dumps({"changed": changed}, ensure_ascii=False)
    display_name = name if name is not None else project["name"]
    add_event("project_updated", f"更新项目: {display_name}",
              f"更新字段: {', '.join(changed)}" if changed else "",
              "project", project_id, metadata=meta)

    if client_id is not None:
        add_relation("project", project_id, "client", client_id, "belongs_to",
                     f"项目「{display_name}」属于该客户")
    from services.knowledge_service import sync_project_to_knowledge
    sync_project_to_knowledge(project_id)
    return True


def update_project_status(project_id: int, status: str) -> None:
    update_project(project_id, status=status)


def search_projects(keyword: str = None, status: str = None, client_id: int = None, limit: int = 100) -> list:
    conditions = []
    params = []
    if keyword:
        conditions.append("(name LIKE ? OR description LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw])
    if status:
        conditions.append("status = ?")
        params.append(status)
    if client_id is not None:
        conditions.append("client_id = ?")
        params.append(client_id)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM projects {where} ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return fetch_all(sql, tuple(params))
