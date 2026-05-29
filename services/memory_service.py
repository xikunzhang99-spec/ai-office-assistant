"""
长期记忆服务 — 从对话、文件、AI问答中提取和存储重要业务记忆。
只保存对未来有用的信息，支持按客户/项目/任务关联。
"""
import json
import re
from database.db import insert, fetch_one, fetch_all, execute
from services.workflow_log_service import add_workflow_log
from services.ai_service import _chat
from utils.date_utils import now_str

MEMORY_TYPES = [
    "client_preference",
    "project_risk",
    "task_blocker",
    "decision",
    "meeting_conclusion",
    "follow_up",
    "important_fact",
]

IMPORTANCE_LEVELS = ["low", "medium", "high", "critical"]

MEMORY_EXTRACTION_PROMPT = """从以下文本中提取值得长期记忆的重要信息。只保存对未来有用的信息。

记忆类型（memory_type）：
- client_preference: 客户偏好、需求、特殊要求
- project_risk: 项目风险、延期可能、资源问题
- task_blocker: 任务阻塞、依赖链、阻碍因素
- decision: 重要决策、方向选择、取舍
- meeting_conclusion: 会议结论、纪要、共识
- follow_up: 需要跟进的事项、待办
- important_fact: 重要事实、数据、里程碑

重要性（importance）：low / medium / high / critical

输出 JSON 数组，每个元素：
{"memory_type": "xxx", "title": "简洁标题", "content": "详细内容", "importance": "medium",
 "client_id": null, "project_id": null, "task_id": null}

规则：
- 不是什么都提取，只提取对未来有参考价值的信息
- 1-5条即可，没有重要的就返回空数组 []
- 如果能推断关联的客户/项目/任务，填对应id（填null表示无法推断）
- 只输出 JSON 数组，不要其他文字"""


def extract_memory_from_text(text: str, source_type: str = None, source_id: int = None,
                             client_id: int = None, project_id: int = None,
                             task_id: int = None) -> list:
    """从文本中提取长期记忆项。调用 AI 进行结构化提取。

    Returns:
        提取到的 memory dict 列表（未入库，调用方决定是否保存）
    """
    if not text or len(text) < 20:
        return []

    text_sample = text[:4000]

    # 构建上下文字段提示
    hint_parts = []
    if client_id:
        hint_parts.append(f"关联客户ID: {client_id}")
    if project_id:
        hint_parts.append(f"关联项目ID: {project_id}")
    if task_id:
        hint_parts.append(f"关联任务ID: {task_id}")

    hint_text = "\n".join(hint_parts) if hint_parts else "无已知关联"

    prompt = f"{MEMORY_EXTRACTION_PROMPT}\n\n已知关联：{hint_text}\n\n文本内容：\n{text_sample}"

    try:
        result = _chat(prompt, "你是一个信息提取器。只输出 JSON 数组。",
                      temperature=0.2, max_tokens=1500)
    except Exception as e:
        add_workflow_log("memory_extraction_error", source_type or "unknown", source_id,
                        "error", f"AI提取失败: {str(e)[:200]}")
        return []

    items = _parse_memory_json(result)

    # 如果 AI 没填关联ID，用传入的补上
    for item in items:
        if client_id and not item.get("client_id"):
            item["client_id"] = client_id
        if project_id and not item.get("project_id"):
            item["project_id"] = project_id
        if task_id and not item.get("task_id"):
            item["task_id"] = task_id

    add_workflow_log("memory_extraction", source_type or "unknown", source_id,
                    "success", f"提取 {len(items)} 条记忆")
    return items


def save_memory_item(memory_type: str, title: str, content: str = "",
                     source_type: str = None, source_id: int = None,
                     importance: str = "medium",
                     client_id: int = None, project_id: int = None,
                     task_id: int = None) -> int:
    """幂等保存一条长期记忆。同一 source_type + source_id + memory_type + title 去重。

    Returns:
        memory_item id
    """
    if memory_type not in MEMORY_TYPES:
        memory_type = "important_fact"
    if importance not in IMPORTANCE_LEVELS:
        importance = "medium"

    # 幂等检查
    existing = fetch_one(
        """SELECT id FROM memory_items
           WHERE memory_type = ? AND source_type = ? AND source_id = ?
           AND title = ?""",
        (memory_type, source_type or "", source_id, title),
    )
    if existing:
        execute(
            """UPDATE memory_items
               SET content = ?, importance = ?,
                   client_id = ?, project_id = ?, task_id = ?,
                   updated_at = ?
               WHERE id = ?""",
            (content, importance, client_id, project_id, task_id, now_str(), existing["id"]),
        )
        add_workflow_log("memory_item_updated", source_type or "memory", source_id,
                        "success", f"更新记忆: {title}")
        return existing["id"]

    mem_id = insert(
        """INSERT INTO memory_items
           (memory_type, source_type, source_id, title, content, importance,
            client_id, project_id, task_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (memory_type, source_type, source_id, title, content, importance,
         client_id, project_id, task_id, now_str(), now_str()),
    )
    add_workflow_log("memory_item_created", source_type or "memory", source_id,
                    "success", f"新增记忆: {title}")
    return mem_id


def get_memory_by_client(client_id: int, limit: int = 50) -> list:
    """获取客户相关的长期记忆。"""
    return fetch_all(
        """SELECT * FROM memory_items
           WHERE client_id = ?
           ORDER BY
             CASE importance
               WHEN 'critical' THEN 0 WHEN 'high' THEN 1
               WHEN 'medium' THEN 2 WHEN 'low' THEN 3
             END,
             created_at DESC
           LIMIT ?""",
        (client_id, limit),
    )


def get_memory_by_project(project_id: int, limit: int = 50) -> list:
    """获取项目相关的长期记忆。"""
    return fetch_all(
        """SELECT * FROM memory_items
           WHERE project_id = ?
           ORDER BY
             CASE importance
               WHEN 'critical' THEN 0 WHEN 'high' THEN 1
               WHEN 'medium' THEN 2 WHEN 'low' THEN 3
             END,
             created_at DESC
           LIMIT ?""",
        (project_id, limit),
    )


def get_memory_by_task(task_id: int, limit: int = 50) -> list:
    """获取任务相关的长期记忆。"""
    return fetch_all(
        """SELECT * FROM memory_items
           WHERE task_id = ?
           ORDER BY created_at DESC
           LIMIT ?""",
        (task_id, limit),
    )


def search_memory(question: str, limit: int = 10) -> list:
    """搜索长期记忆。优先匹配 memory_type，然后关键词。"""
    keywords = _extract_memory_keywords(question)
    if not keywords:
        return fetch_all(
            "SELECT * FROM memory_items ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )

    score_parts = []
    score_params = []
    for kw in keywords:
        kw_param = f"%{kw}%"
        score_parts.append(
            f"(CASE WHEN title LIKE ? THEN 3 ELSE 0 END) + "
            f"(CASE WHEN memory_type LIKE ? THEN 2 ELSE 0 END) + "
            f"(CASE WHEN content LIKE ? THEN 1 ELSE 0 END)"
        )
        score_params.extend([kw_param, kw_param, kw_param])

    score_expr = " + ".join(score_parts) if score_parts else "0"
    sql = f"""SELECT *, ({score_expr}) AS score
              FROM memory_items
              WHERE ({score_expr}) > 0
              ORDER BY score DESC
              LIMIT ?"""
    all_params = list(score_params) + list(score_params) + [limit]
    return fetch_all(sql, tuple(all_params))


def get_recent_memories(limit: int = 20) -> list:
    """获取最近的长期记忆。"""
    return fetch_all(
        """SELECT * FROM memory_items
           ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    )


def get_high_importance_memories(limit: int = 20) -> list:
    """获取高重要性的记忆（high/critical）。"""
    return fetch_all(
        """SELECT * FROM memory_items
           WHERE importance IN ('high', 'critical')
           ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    )


def rebuild_memory_items() -> int:
    """重建所有长期记忆：清空并从现有数据（文件摘要、AI问答、时间轴）重新提取。

    Returns:
        重建的记忆条数
    """
    from services.workflow_log_service import add_workflow_log

    execute("DELETE FROM memory_items")
    count = 0

    # 从文件摘要和关键点提取
    files = fetch_all(
        "SELECT id, filename, summary, key_points, suggestions, project_id, client_id FROM files"
    )
    for f in files:
        text_parts = []
        if f.get("filename"):
            text_parts.append(f"文件名: {f['filename']}")
        if f.get("summary"):
            text_parts.append(f"摘要: {f['summary']}")
        if f.get("key_points"):
            text_parts.append(f"关键点: {f['key_points']}")
        if f.get("suggestions"):
            text_parts.append(f"建议: {f['suggestions']}")
        text = "\n".join(text_parts)
        if len(text) > 30:
            items = extract_memory_from_text(
                text, source_type="file", source_id=f["id"],
                project_id=f.get("project_id"), client_id=f.get("client_id"),
            )
            for item in items:
                save_memory_item(
                    memory_type=item.get("memory_type", "important_fact"),
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    source_type="file", source_id=f["id"],
                    importance=item.get("importance", "medium"),
                    client_id=item.get("client_id"),
                    project_id=item.get("project_id"),
                    task_id=item.get("task_id"),
                )
                count += 1

    # 从时间轴事件提取
    events = fetch_all(
        """SELECT * FROM timeline_events
           WHERE event_type NOT IN ('ai_query', 'daily_summary')
           ORDER BY created_at DESC LIMIT 100"""
    )
    for e in events:
        text_parts = []
        if e.get("title"):
            text_parts.append(f"事件: {e['title']}")
        if e.get("description"):
            text_parts.append(f"描述: {e['description']}")
        text = "\n".join(text_parts)
        if len(text) > 30:
            items = extract_memory_from_text(
                text, source_type="event", source_id=e["id"],
                project_id=e.get("project_id"), client_id=e.get("client_id"),
            )
            for item in items:
                save_memory_item(
                    memory_type=item.get("memory_type", "important_fact"),
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    source_type="event", source_id=e["id"],
                    importance=item.get("importance", "medium"),
                    client_id=item.get("client_id"),
                    project_id=item.get("project_id"),
                )
                count += 1

    add_workflow_log("memory_rebuild", "memory", None, "success",
                     f"重建 {count} 条长期记忆")
    return count


def auto_extract_and_save(text: str, source_type: str, source_id: int,
                          client_id: int = None, project_id: int = None,
                          task_id: int = None) -> int:
    """便捷函数：从文本提取记忆并自动保存。

    Returns:
        保存的记忆条数
    """
    items = extract_memory_from_text(
        text, source_type=source_type, source_id=source_id,
        client_id=client_id, project_id=project_id, task_id=task_id,
    )
    count = 0
    for item in items:
        save_memory_item(
            memory_type=item.get("memory_type", "important_fact"),
            title=item.get("title", ""),
            content=item.get("content", ""),
            source_type=source_type, source_id=source_id,
            importance=item.get("importance", "medium"),
            client_id=item.get("client_id"),
            project_id=item.get("project_id"),
            task_id=item.get("task_id"),
        )
        count += 1
    return count


def get_memory_stats() -> dict:
    """获取 memory_items 统计信息。"""
    total = fetch_one("SELECT COUNT(*) as cnt FROM memory_items")
    by_type = fetch_all(
        "SELECT memory_type, COUNT(*) as cnt FROM memory_items GROUP BY memory_type"
    )
    by_importance = fetch_all(
        "SELECT importance, COUNT(*) as cnt FROM memory_items GROUP BY importance"
    )
    return {
        "total": total["cnt"] if total else 0,
        "by_type": {r["memory_type"]: r["cnt"] for r in by_type},
        "by_importance": {r["importance"]: r["cnt"] for r in by_importance},
    }


def _parse_memory_json(text: str) -> list:
    """解析 AI 返回的 JSON 数组。"""
    text = text.strip()
    arr_match = re.search(r'\[.*\]', text, re.DOTALL)
    if arr_match:
        text = arr_match.group(0)
    try:
        items = json.loads(text)
        if isinstance(items, list):
            return items
    except json.JSONDecodeError:
        pass
    return []


def _extract_memory_keywords(question: str) -> list:
    """从问题中提取搜索关键词。"""
    keywords = []
    english_words = re.findall(r'[a-zA-Z]{2,}', question)
    keywords.extend(w.lower() for w in english_words)
    numbers = re.findall(r'\d+', question)
    keywords.extend(numbers)
    cleaned = re.sub(r'[a-zA-Z0-9]+', ' ', question)
    chinese_chars = re.findall(r'[一-鿿]', cleaned)
    chinese_str = ''.join(chinese_chars)
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
    seen = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique
