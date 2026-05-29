from database.db import insert, fetch_all
from services.relation_service import add_relation
from utils.date_utils import now_str, today_str

# 事件类型中文标签
EVENT_TYPE_LABELS = {
    "task_created": "创建任务",
    "task_updated": "修改任务",
    "task_status_changed": "任务状态变更",
    "task_completed": "完成任务",
    "task_deleted": "删除任务",
    "file_uploaded": "上传文件",
    "file_summarized": "AI总结文件",
    "file_markdown_created": "生成Markdown",
    "file_written_to_obsidian": "写入Obsidian",
    "daily_note": "随手记",
    "daily_summary": "每日总结",
    "daily_summary_written_to_obsidian": "总结写入Obsidian",
    "project_created": "创建项目",
    "project_updated": "修改项目",
    "client_created": "创建客户",
    "client_updated": "修改客户",
    "client_deleted": "删除客户",
    "project_deleted": "删除项目",
    "daily_summary_deleted": "删除总结",
    "daily_note_deleted": "删除随手记",
    "file_deleted": "删除文件",
    "ai_query": "AI问答",
    "manual": "手动记录",
    "file_updated": "修改文件",
    "obsidian_synced": "Obsidian同步",
    "stage_initialized": "阶段初始化",
    "stage_advanced": "阶段推进",
    "stage_skipped": "阶段跳过",
    "project_stage_inferred": "阶段推断",
}

# 事件类型图标
EVENT_TYPE_ICONS = {
    "task_created": "+",
    "task_updated": "~",
    "task_status_changed": ">",
    "task_completed": "DONE",
    "task_deleted": "DEL",
    "file_uploaded": "UP",
    "file_summarized": "AI",
    "file_markdown_created": "MD",
    "file_written_to_obsidian": "OBS",
    "daily_note": "NOTE",
    "daily_summary": "SUM",
    "daily_summary_written_to_obsidian": "OBS",
    "project_created": "+P",
    "project_updated": "~P",
    "client_created": "+C",
    "client_updated": "~C",
    "client_deleted": "DEL",
    "project_deleted": "DEL",
    "daily_summary_deleted": "DEL",
    "daily_note_deleted": "DEL",
    "file_deleted": "DEL",
    "ai_query": "AI?",
    "manual": "📝",
    "file_updated": "~F",
    "obsidian_synced": "OBS",
    "stage_initialized": "+S",
    "stage_advanced": ">>S",
    "stage_skipped": "xS",
    "project_stage_inferred": "?S",
}

# 任务状态标签
TASK_STATUS_LABELS = {"todo": "待办", "doing": "进行中", "done": "已完成", "cancelled": "已取消"}

# 任务优先级标签
TASK_PRIORITY_LABELS = {"high": "高", "medium": "中", "low": "低"}


def add_event(event_type: str, title: str, description: str = "",
              related_type: str = "", related_id: int = 0,
              project_id: int = None, client_id: int = None,
              tags: str = "", metadata: str = "",
              event_date: str = None):
    event_id = insert(
        """INSERT INTO timeline_events
           (event_type, title, description, related_type, related_id,
            project_id, client_id, tags, metadata, event_date, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (event_type, title, description, related_type, related_id,
         project_id, client_id, tags, metadata,
         event_date or today_str(), now_str()),
    )
    if project_id:
        add_relation("event", event_id, "project", project_id, "related_to",
                     f"事件「{title}」关联该项目")
    if client_id:
        add_relation("event", event_id, "client", client_id, "related_to",
                     f"事件「{title}」关联该客户")
    if related_type and related_id:
        add_relation("event", event_id, related_type, related_id, "related_to",
                     f"事件「{title}」关联该{related_type}")

    from services.knowledge_service import sync_event_to_knowledge
    sync_event_to_knowledge(event_id)

    return event_id


def search_events(start_date: str = None, end_date: str = None,
                  event_type: str = None, project_id: int = None,
                  client_id: int = None, keyword: str = None,
                  limit: int = 200) -> list:
    conditions = []
    params = []

    if start_date:
        conditions.append("event_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("event_date <= ?")
        params.append(end_date)
    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)
    if project_id is not None:
        conditions.append("project_id = ?")
        params.append(project_id)
    if client_id is not None:
        conditions.append("client_id = ?")
        params.append(client_id)
    if keyword:
        conditions.append("(title LIKE ? OR description LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM timeline_events {where} ORDER BY event_date DESC, created_at DESC LIMIT ?"
    params.append(limit)

    return fetch_all(sql, tuple(params))


def get_events_by_date(date_str: str) -> list:
    return search_events(start_date=date_str, end_date=date_str)


def get_events_by_week(start_date: str, end_date: str) -> list:
    return search_events(start_date=start_date, end_date=end_date, limit=500)


def get_events_by_month(year: int, month: int) -> list:
    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year}-12-31"
    else:
        end = f"{year}-{month+1:02d}-01"
    return search_events(start_date=start, end_date=end, limit=1000)


def get_events_by_type(event_type: str, limit: int = 50) -> list:
    return search_events(event_type=event_type, limit=limit)


def get_events_by_project(project_id: int, limit: int = 100) -> list:
    return search_events(project_id=project_id, limit=limit)


def get_events_by_client(client_id: int, limit: int = 100) -> list:
    return search_events(client_id=client_id, limit=limit)


def get_all_events(limit: int = 100) -> list:
    return search_events(limit=limit)
