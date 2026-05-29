"""
知识条目服务 — 将各业务实体同步为统一的 knowledge_items，为后续语义搜索/RAG做准备。
"""
from database.db import insert, fetch_one, fetch_all, execute
from utils.date_utils import now_str


def _upsert_knowledge(source_type: str, source_id: int, title: str, content: str,
                      tags: str = "", project_id: int = None, client_id: int = None,
                      task_id: int = None) -> int:
    """幂等 upsert：同一 source_type+source_id 只保留一条记录。"""
    existing = fetch_one(
        "SELECT id FROM knowledge_items WHERE source_type = ? AND source_id = ?",
        (source_type, source_id),
    )
    if existing:
        execute(
            """UPDATE knowledge_items
               SET title = ?, content = ?, tags = ?,
                   project_id = ?, client_id = ?, task_id = ?,
                   updated_at = ?
               WHERE id = ?""",
            (title, content, tags, project_id, client_id, task_id, now_str(), existing["id"]),
        )
        return existing["id"]
    else:
        return insert(
            """INSERT INTO knowledge_items
               (source_type, source_id, title, content, tags,
                project_id, client_id, task_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (source_type, source_id, title, content, tags,
             project_id, client_id, task_id, now_str(), now_str()),
        )


def sync_client_to_knowledge(client_id: int) -> int:
    from services.client_service import get_client

    c = get_client(client_id)
    if not c:
        return 0

    parts = [f"客户: {c['name']}"]
    if c.get("description"):
        parts.append(f"描述: {c['description']}")
    if c.get("contact_info"):
        parts.append(f"联系方式: {c['contact_info']}")

    return _upsert_knowledge(
        source_type="client",
        source_id=client_id,
        title=c["name"],
        content="\n".join(parts),
        tags="客户",
        client_id=client_id,
    )


def sync_project_to_knowledge(project_id: int) -> int:
    from services.project_service import get_project

    p = get_project(project_id)
    if not p:
        return 0

    status_map = {"active": "进行中", "archived": "已归档", "completed": "已完成"}
    parts = [f"项目: {p['name']}"]
    parts.append(f"状态: {status_map.get(p.get('status', ''), p.get('status', ''))}")
    if p.get("description"):
        parts.append(f"描述: {p['description']}")

    return _upsert_knowledge(
        source_type="project",
        source_id=project_id,
        title=p["name"],
        content="\n".join(parts),
        tags="项目",
        project_id=project_id,
        client_id=p.get("client_id"),
    )


def sync_task_to_knowledge(task_id: int) -> int:
    from services.task_service import get_task

    t = get_task(task_id)
    if not t:
        return 0

    status_map = {"todo": "待办", "doing": "进行中", "done": "已完成", "cancelled": "已取消"}
    priority_map = {"high": "高", "medium": "中", "low": "低"}
    parts = [f"任务: {t['title']}"]
    parts.append(f"状态: {status_map.get(t.get('status', ''), t.get('status', ''))}")
    parts.append(f"优先级: {priority_map.get(t.get('priority', ''), t.get('priority', ''))}")
    if t.get("description"):
        parts.append(f"描述: {t['description']}")
    if t.get("due_date"):
        parts.append(f"截止日期: {t['due_date']}")
    if t.get("tags"):
        parts.append(f"标签: {t['tags']}")

    tag_list = "任务"
    if t.get("tags"):
        tag_list += f",{t['tags']}"

    return _upsert_knowledge(
        source_type="task",
        source_id=task_id,
        title=t["title"],
        content="\n".join(parts),
        tags=tag_list,
        project_id=t.get("project_id"),
        client_id=t.get("client_id"),
        task_id=task_id,
    )


def sync_file_to_knowledge(file_id: int) -> int:
    from services.file_service import get_file

    f = get_file(file_id)
    if not f:
        return 0

    parts = [f"文件: {f['filename']}"]
    if f.get("summary"):
        parts.append(f"摘要: {f['summary']}")
    if f.get("tags"):
        parts.append(f"标签: {f['tags']}")

    tag_list = "文件"
    if f.get("tags"):
        tag_list += f",{f['tags']}"

    return _upsert_knowledge(
        source_type="file",
        source_id=file_id,
        title=f["filename"],
        content="\n".join(parts),
        tags=tag_list,
        project_id=f.get("project_id"),
        client_id=f.get("client_id"),
    )


def sync_event_to_knowledge(event_id: int) -> int:
    from database.db import fetch_one as db_fetch_one

    e = db_fetch_one("SELECT * FROM timeline_events WHERE id = ?", (event_id,))
    if not e:
        return 0

    if e.get("event_type") == "ai_query":
        return 0

    from services.timeline_service import EVENT_TYPE_LABELS
    label = EVENT_TYPE_LABELS.get(e.get("event_type", ""), e.get("event_type", ""))

    parts = [f"事件: {label}"]
    if e.get("title"):
        parts.append(f"标题: {e['title']}")
    if e.get("description"):
        parts.append(f"描述: {e['description']}")
    if e.get("event_date"):
        parts.append(f"日期: {e['event_date']}")

    return _upsert_knowledge(
        source_type="event",
        source_id=event_id,
        title=e.get("title", "")[:120],
        content="\n".join(parts),
        tags=f"事件,{label}",
        project_id=e.get("project_id"),
        client_id=e.get("client_id"),
    )


def rebuild_knowledge_items():
    """重建所有知识条目：清空现有记录，从所有业务表中重新生成。"""
    execute("DELETE FROM knowledge_items")

    from services.client_service import get_all_clients
    from services.project_service import get_all_projects
    from services.task_service import get_all_tasks
    from services.file_service import get_all_files

    count = 0
    for c in get_all_clients():
        sync_client_to_knowledge(c["id"])
        count += 1
    for p in get_all_projects():
        sync_project_to_knowledge(p["id"])
        count += 1
    for t in get_all_tasks(limit=1000):
        sync_task_to_knowledge(t["id"])
        count += 1
    for f in get_all_files(limit=1000):
        sync_file_to_knowledge(f["id"])
        count += 1

    # timeline_events: sync last 200
    events = fetch_all("SELECT id FROM timeline_events ORDER BY created_at DESC LIMIT 200")
    for e in events:
        sync_event_to_knowledge(e["id"])
        count += 1

    return count


def search_knowledge(keyword: str = None, source_type: str = None,
                     project_id: int = None, client_id: int = None,
                     limit: int = 50) -> list:
    """搜索知识条目。"""
    conditions = []
    params = []
    if keyword:
        conditions.append("(title LIKE ? OR content LIKE ? OR tags LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw])
    if source_type:
        conditions.append("source_type = ?")
        params.append(source_type)
    if project_id is not None:
        conditions.append("project_id = ?")
        params.append(project_id)
    if client_id is not None:
        conditions.append("client_id = ?")
        params.append(client_id)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM knowledge_items {where} ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    return fetch_all(sql, tuple(params))


def delete_knowledge_item(source_type: str, source_id: int):
    """删除指定来源的知识条目。"""
    execute(
        "DELETE FROM knowledge_items WHERE source_type = ? AND source_id = ?",
        (source_type, source_id),
    )


def search_knowledge_items(question: str, limit: int = 10) -> list:
    """关键词版 RAG 检索：从问题中提取关键词，在 knowledge_items 中加权搜索。

    title 命中权重 3，tags 命中权重 2，content 命中权重 1。
    多个关键词命中同一知识条目时分数累加，按总分降序返回。
    """
    keywords = _extract_keywords(question)
    if not keywords:
        return []

    # 构建加权评分 SQL：每个关键词在 title/tags/content 中 LIKE 匹配，累加得分
    # 使用 CTE 避免 score_expr 中 ? 占位符在 SELECT 和 WHERE 中重复
    score_parts = []
    score_params = []
    for kw in keywords:
        kw_param = f"%{kw}%"
        score_parts.append(
            f"(CASE WHEN title LIKE ? THEN 3 ELSE 0 END) + "
            f"(CASE WHEN tags LIKE ? THEN 2 ELSE 0 END) + "
            f"(CASE WHEN content LIKE ? THEN 1 ELSE 0 END)"
        )
        score_params.extend([kw_param, kw_param, kw_param])

    score_expr = " + ".join(score_parts)
    sql = f"""SELECT id, source_type, source_id, title, content, tags,
                     client_id, project_id, task_id, score
              FROM (
                  SELECT *, ({score_expr}) AS score
                  FROM knowledge_items
              )
              WHERE score > 0
              ORDER BY score DESC
              LIMIT ?"""
    score_params.append(limit)
    return fetch_all(sql, tuple(score_params))


def _extract_keywords(question: str) -> list:
    """从问题中提取搜索关键词。"""
    import re

    keywords = []

    # 提取英文单词（>=2 字符）
    english_words = re.findall(r'[a-zA-Z]{2,}', question)
    keywords.extend(w.lower() for w in english_words)

    # 提取数字
    numbers = re.findall(r'\d+', question)
    keywords.extend(numbers)

    # 移除英文和数字后，提取中文词组（2-4 字滑动窗口）
    cleaned = re.sub(r'[a-zA-Z0-9]+', ' ', question)
    chinese_chars = re.findall(r'[一-鿿]', cleaned)
    chinese_str = ''.join(chinese_chars)

    # 常见停用词
    stop_words = {
        '什么', '怎么', '哪些', '哪个', '如何', '为什么', '有没有', '是否',
        '一个', '一下', '一些', '所有', '全部', '这个', '那个', '可以',
        '的', '了', '是', '在', '有', '和', '与', '或', '吗', '呢', '吧',
        '请', '帮我', '我想', '我要', '查询', '搜索', '查找', '显示', '列出',
    }

    for length in [4, 3, 2]:
        for i in range(len(chinese_str) - length + 1):
            phrase = chinese_str[i:i + length]
            if phrase not in stop_words:
                keywords.append(phrase)

    # 去重并保持顺序
    seen = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)

    return unique


def get_knowledge_stats() -> dict:
    """获取 knowledge_items 统计信息。"""
    total = fetch_one("SELECT COUNT(*) as cnt FROM knowledge_items")
    by_type_rows = fetch_all(
        "SELECT source_type, COUNT(*) as cnt FROM knowledge_items GROUP BY source_type"
    )
    by_type = {row["source_type"]: row["cnt"] for row in by_type_rows}
    return {
        "total": total["cnt"] if total else 0,
        "by_type": by_type,
    }


def get_database_stats() -> dict:
    """获取所有主要数据表的行数统计。"""
    tables = [
        "clients", "projects", "tasks", "files",
        "timeline_events", "knowledge_items", "knowledge_embeddings", "workflow_logs",
    ]
    stats = {}
    for table in tables:
        row = fetch_one(f"SELECT COUNT(*) as cnt FROM {table}")
        stats[table] = row["cnt"] if row else 0
    return stats


def count_orphan_knowledge_items() -> int:
    """统计 source 实体已不存在的孤儿 knowledge_items 数量。"""
    row = fetch_one("""
        SELECT COUNT(*) as cnt FROM knowledge_items ki
        WHERE NOT (
            (ki.source_type = 'client' AND ki.source_id IN (SELECT id FROM clients))
            OR (ki.source_type = 'project' AND ki.source_id IN (SELECT id FROM projects))
            OR (ki.source_type = 'task' AND ki.source_id IN (SELECT id FROM tasks))
            OR (ki.source_type = 'file' AND ki.source_id IN (SELECT id FROM files))
            OR (ki.source_type = 'event' AND ki.source_id IN (SELECT id FROM timeline_events))
        )
    """)
    return row["cnt"] if row else 0


def cleanup_orphan_knowledge_items() -> int:
    """删除 source 实体已不存在的孤儿 knowledge_items（及其关联的 embeddings）。

    Returns:
        删除的 knowledge_items 数量。
    """
    before = count_orphan_knowledge_items()
    if before > 0:
        # 先删除孤儿 knowledge_items 对应的 embeddings
        execute("""
            DELETE FROM knowledge_embeddings
            WHERE knowledge_item_id IN (
                SELECT ki.id FROM knowledge_items ki
                WHERE NOT (
                    (ki.source_type = 'client' AND ki.source_id IN (SELECT id FROM clients))
                    OR (ki.source_type = 'project' AND ki.source_id IN (SELECT id FROM projects))
                    OR (ki.source_type = 'task' AND ki.source_id IN (SELECT id FROM tasks))
                    OR (ki.source_type = 'file' AND ki.source_id IN (SELECT id FROM files))
                    OR (ki.source_type = 'event' AND ki.source_id IN (SELECT id FROM timeline_events))
                )
            )
        """)
        # 再删除孤儿 knowledge_items
        execute("""
            DELETE FROM knowledge_items
            WHERE NOT (
                (source_type = 'client' AND source_id IN (SELECT id FROM clients))
                OR (source_type = 'project' AND source_id IN (SELECT id FROM projects))
                OR (source_type = 'task' AND source_id IN (SELECT id FROM tasks))
                OR (source_type = 'file' AND source_id IN (SELECT id FROM files))
                OR (source_type = 'event' AND source_id IN (SELECT id FROM timeline_events))
            )
        """)
    return before
