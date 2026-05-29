from database.db import insert, fetch_all, fetch_one, execute
from services.timeline_service import add_event
from services.relation_service import delete_relations_for
from utils.date_utils import now_str


def create_client(name: str, description: str = "", contact_info: str = "") -> int:
    client_id = insert(
        "INSERT INTO clients (name, description, contact_info, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (name, description, contact_info, now_str(), now_str()),
    )
    add_event("client_created", f"创建客户: {name}", description, "client", client_id)
    from services.knowledge_service import sync_client_to_knowledge
    sync_client_to_knowledge(client_id)
    return client_id


def get_or_create_client(name: str, description: str = "", contact_info: str = "") -> dict:
    """幂等创建客户 — 同名客户已存在时返回已有记录。

    Returns:
        {client_id: int, created: bool, message: str}
    """
    existing = fetch_one("SELECT * FROM clients WHERE name = ?", (name,))
    if existing:
        return {"client_id": existing["id"], "created": False, "message": f"客户「{name}」已存在"}

    client_id = create_client(name, description, contact_info)
    return {"client_id": client_id, "created": True, "message": f"已创建客户「{name}」"}


def get_all_clients() -> list:
    return fetch_all("SELECT * FROM clients ORDER BY created_at DESC")


def get_client(client_id: int):
    return fetch_one("SELECT * FROM clients WHERE id = ?", (client_id,))


def delete_client(client_id: int) -> bool:
    client = get_client(client_id)
    if client:
        add_event("client_deleted", f"删除客户: {client['name']}", "", "client", client_id)
    delete_relations_for("client", client_id)
    execute("DELETE FROM clients WHERE id = ?", (client_id,))
    from services.knowledge_service import delete_knowledge_item
    delete_knowledge_item("client", client_id)
    return True


def update_client(client_id: int, name: str = None, description: str = None,
                  contact_info: str = None) -> bool:
    client = get_client(client_id)
    if not client:
        return False
    updates = []
    values = []
    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if description is not None:
        updates.append("description = ?")
        values.append(description)
    if contact_info is not None:
        updates.append("contact_info = ?")
        values.append(contact_info)
    if not updates:
        return False
    updates.append("updated_at = ?")
    values.append(now_str())
    values.append(client_id)
    execute(f"UPDATE clients SET {', '.join(updates)} WHERE id = ?", tuple(values))
    changed = [k for k in ["name", "description", "contact_info"] if k in
               {k: v for k, v in zip(["name", "description", "contact_info"],
                [name, description, contact_info]) if v is not None}]
    meta = f"更新字段: {', '.join(changed)}"
    add_event("client_updated", f"更新客户: {name or client['name']}", meta, "client", client_id)
    from services.knowledge_service import sync_client_to_knowledge
    sync_client_to_knowledge(client_id)
    return True


def search_clients(keyword: str = None, limit: int = 100) -> list:
    conditions = []
    params = []
    if keyword:
        conditions.append("(name LIKE ? OR description LIKE ? OR contact_info LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM clients {where} ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return fetch_all(sql, tuple(params))
