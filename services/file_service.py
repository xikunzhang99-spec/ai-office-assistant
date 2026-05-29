import os
import json
from database.db import insert, fetch_one, execute
from services.timeline_service import add_event
from services.relation_service import delete_relations_for
from utils.date_utils import now_str


def save_file_record(filename: str, file_path: str, file_type: str,
                     summary: str = "", key_points: list = None,
                     suggestions: list = None, tags: str = "",
                     project_id: int = None, client_id: int = None,
                     file_hash: str = "") -> int:
    file_id = insert(
        """INSERT INTO files (filename, file_path, file_type, file_hash, summary, key_points, suggestions, tags,
                              project_id, client_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (filename, file_path, file_type, file_hash,
         summary,
         json.dumps(key_points or [], ensure_ascii=False),
         json.dumps(suggestions or [], ensure_ascii=False),
         tags,
         project_id,
         client_id,
         now_str(), now_str()),
    )
    from services.knowledge_service import sync_file_to_knowledge
    knowledge_id = sync_file_to_knowledge(file_id)

    # 同步 embedding（如果已有 embedding 数据）
    try:
        from services.embedding_service import upsert_embedding, has_embeddings
        if has_embeddings() and knowledge_id:
            upsert_embedding(knowledge_id, f"{filename}\n{summary or ''}")
    except Exception:
        pass

    # 记录工作流日志
    try:
        from services.workflow_log_service import add_workflow_log
        add_workflow_log("file_upload_analysis", "file", file_id, "success",
                         f"文件「{filename}」已保存、摘要、知识库同步", "")
    except Exception:
        pass

    return file_id


def generate_task_suggestions_from_file(file_id: int) -> list:
    """根据文件内容生成任务建议。只返回建议，不插入数据库。

    返回: [{title, description, priority, due_date, related_project_id, related_client_id}]
    """
    import json as _json
    from services.ai_service import _chat

    f = get_file(file_id)
    if not f:
        return []

    # 构建文件信息摘要
    info = f"文件名: {f['filename']}\n文件类型: {f.get('file_type', '')}\n"
    if f.get("summary"):
        info += f"摘要: {f['summary']}\n"
    if f.get("key_points"):
        try:
            kp = _json.loads(f["key_points"]) if isinstance(f["key_points"], str) else f["key_points"]
            info += f"关键点: {', '.join(kp)}\n"
        except Exception:
            pass
    if f.get("tags"):
        info += f"标签: {f['tags']}\n"

    prompt = f"""根据以下文件信息，建议1-3个需要跟进的待办任务。只输出JSON数组，不要其他文字。

## 文件信息
{info[:1500]}

## 输出JSON格式
[
  {{
    "title": "任务标题（简洁）",
    "description": "任务描述",
    "priority": "high/medium/low",
    "due_date": null,
    "related_project_id": {f.get('project_id') or 'null'},
    "related_client_id": {f.get('client_id') or 'null'}
  }}
]

## 规则
- priority 根据紧急程度选择 high/medium/low
- due_date 如果用文件信息推断不出具体日期填 null
- related_project_id 和 related_client_id 使用上面提供的值
- 只输出 JSON 数组"""

    import re
    text = _chat(prompt, "你是一个办公任务建议分析器。只输出 JSON 数组。", temperature=0.2, max_tokens=500)

    # 解析 JSON
    text = text.strip()
    arr_match = re.search(r'\[.*\]', text, re.DOTALL)
    if arr_match:
        text = arr_match.group(0)
    try:
        return _json.loads(text)
    except Exception:
        return []


def get_file(file_id: int):
    return fetch_one("SELECT * FROM files WHERE id = ?", (file_id,))


def get_all_files(limit: int = 50) -> list:
    from database.db import fetch_all
    return fetch_all("SELECT * FROM files ORDER BY created_at DESC LIMIT ?", (limit,))


def update_file(file_id: int, filename: str = None, tags: str = None,
               summary: str = None, project_id: int = None, client_id: int = None) -> bool:
    f = get_file(file_id)
    if not f:
        return False
    updates = []
    values = []
    if filename is not None:
        updates.append("filename = ?")
        values.append(filename)
    if tags is not None:
        updates.append("tags = ?")
        values.append(tags)
    if summary is not None:
        updates.append("summary = ?")
        values.append(summary)
    if project_id is not None:
        updates.append("project_id = ?")
        values.append(project_id)
    if client_id is not None:
        updates.append("client_id = ?")
        values.append(client_id)
    if not updates:
        return False
    updates.append("updated_at = ?")
    values.append(now_str())
    values.append(file_id)
    execute(f"UPDATE files SET {', '.join(updates)} WHERE id = ?", tuple(values))
    changed = [k for k in ["filename", "tags", "summary", "project_id", "client_id"]
               if locals().get(k) is not None]
    add_event("file_updated", f"更新文件: {filename or f['filename']}",
              f"更新字段: {', '.join(changed)}", "file", file_id)
    if project_id is not None:
        from services.relation_service import add_relation
        add_relation("file", file_id, "project", project_id, "belongs_to",
                     f"文件「{filename or f['filename']}」属于该项目")
    if client_id is not None:
        from services.relation_service import add_relation
        add_relation("file", file_id, "client", client_id, "belongs_to",
                     f"文件「{filename or f['filename']}」属于该客户")
    from services.knowledge_service import sync_file_to_knowledge
    sync_file_to_knowledge(file_id)
    return True


def get_files_by_date(date_str: str) -> list:
    from database.db import fetch_all
    return fetch_all("SELECT * FROM files WHERE date(created_at) = ?", (date_str,))


def delete_file(file_id: int) -> bool:
    f = get_file(file_id)
    if not f:
        return False

    # 1. Delete physical file on disk
    if f["file_path"] and os.path.exists(f["file_path"]):
        try:
            os.remove(f["file_path"])
        except Exception:
            pass

    # 2. Delete relations for this file
    delete_relations_for("file", file_id)

    # 3. Delete database record
    execute("DELETE FROM files WHERE id = ?", (file_id,))

    # 3.5 Clean up knowledge_items
    from services.knowledge_service import delete_knowledge_item
    delete_knowledge_item("file", file_id)

    # 4. Write timeline event
    pid = f["project_id"] if f["project_id"] else None
    cid = f["client_id"] if f["client_id"] else None
    add_event("file_deleted", f"删除文件: {f['filename']}", "", "file", file_id,
              project_id=pid, client_id=cid)

    return True
