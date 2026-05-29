"""统一显示格式化工具 — 所有页面显示数据前必须经过此模块格式化"""

import re

# ── 状态 / 优先级 中英文映射 ──

TASK_STATUS_CN = {"todo": "待办", "doing": "进行中", "done": "已完成", "cancelled": "已取消"}
TASK_PRIORITY_CN = {"high": "高", "medium": "中", "low": "低"}
PROJECT_STATUS_CN = {"active": "进行中", "archived": "已归档", "completed": "已完成"}
STAGE_STATUS_CN = {"active": "进行中", "completed": "已完成", "skipped": "已跳过"}
STAGE_STATUS_EMOJI = {"active": "🔵", "completed": "✅", "skipped": "⏭️"}

STATUS_EMOJI = {"todo": "⭕", "doing": "🔵", "done": "✅", "cancelled": "❌"}
PRIORITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}

EVENT_TYPE_CN = {
    "task_created": "新建任务",
    "task_updated": "修改任务",
    "task_status_changed": "任务状态变更",
    "task_completed": "完成任务",
    "task_deleted": "删除任务",
    "file_uploaded": "上传文件",
    "file_summarized": "AI总结文件",
    "file_markdown_created": "生成Markdown",
    "file_written_to_obsidian": "写入Obsidian",
    "file_deleted": "删除文件",
    "file_updated": "修改文件",
    "daily_note": "随手记",
    "daily_summary": "每日总结",
    "daily_summary_written_to_obsidian": "总结写入Obsidian",
    "daily_summary_deleted": "删除总结",
    "daily_note_deleted": "删除随手记",
    "project_created": "新建项目",
    "project_updated": "修改项目",
    "project_deleted": "删除项目",
    "client_created": "新建客户",
    "client_updated": "修改客户",
    "client_deleted": "删除客户",
    "ai_query": "AI问答",
    "manual": "手动记录",
    "obsidian_synced": "Obsidian同步",
    "stage_initialized": "阶段初始化",
    "stage_advanced": "阶段推进",
    "stage_skipped": "阶段跳过",
    "project_stage_inferred": "阶段推断",
}

RELATED_TYPE_CN = {
    "client": "客户",
    "project": "项目",
    "task": "任务",
    "file": "文件",
    "event": "事件",
    "daily_note": "随手记",
    "daily_summary": "每日总结",
}

FILE_TYPE_CN = {
    ".docx": "Word文档", ".doc": "Word文档",
    ".pptx": "PPT演示", ".ppt": "PPT演示",
    ".xlsx": "Excel表格", ".xls": "Excel表格",
    ".pdf": "PDF文档",
    ".md": "Markdown",
    ".txt": "文本文件",
    ".csv": "CSV数据",
}

WORKFLOW_STATUS_LABELS = {"success": "成功", "error": "失败", "pending": "待处理"}
OBSIDIAN_SYNC_STATUS = {"success": "成功", "error": "失败", "skipped": "已跳过"}

# ── 格式化函数 ──

def format_event_type(event_type: str) -> str:
    """将内部 event_type 转为中文标签"""
    return EVENT_TYPE_CN.get(event_type, event_type)


def format_task_status(status: str) -> str:
    return TASK_STATUS_CN.get(status, status)


def format_task_priority(priority: str) -> str:
    return TASK_PRIORITY_CN.get(priority, priority)


def format_project_status(status: str) -> str:
    return PROJECT_STATUS_CN.get(status, status)


def format_stage_status(status: str) -> str:
    return STAGE_STATUS_CN.get(status, status)


def format_related_type(related_type: str) -> str:
    return RELATED_TYPE_CN.get(related_type, related_type)


def format_file_type(file_type: str) -> str:
    return FILE_TYPE_CN.get(file_type, file_type)


def format_date(date_str: str) -> str:
    """返回干净的日期字符串"""
    if not date_str:
        return ""
    return str(date_str)[:10]


def format_datetime(dt_str: str) -> str:
    """返回干净的日期时间字符串"""
    if not dt_str:
        return ""
    return str(dt_str)[:19]


def clean_html(text: str) -> str:
    """去除 HTML 标签，只保留纯文本"""
    if not text:
        return ""
    return re.sub(r'<[^>]+>', '', text)


# ── 徽章渲染 ──

def status_badge(status: str) -> str:
    """返回纯文本状态徽章，如 [待办]"""
    label = format_task_status(status)
    emoji = STATUS_EMOJI.get(status, "")
    return f"{emoji} [{label}]"


def priority_badge(priority: str) -> str:
    """返回纯文本优先级徽章，如 🔴 [高]"""
    label = format_task_priority(priority)
    emoji = PRIORITY_EMOJI.get(priority, "")
    return f"{emoji} [{label}]"


def task_title_display(task: dict) -> str:
    """格式化任务标题，包含状态和优先级标识"""
    s_badge = status_badge(task.get("status", ""))
    p_badge = priority_badge(task.get("priority", ""))
    return f"{s_badge} {p_badge} {task['title']}"


def event_display(event: dict) -> str:
    """格式化单条时间轴事件为一行纯文本"""
    label = format_event_type(event.get("event_type", ""))
    title = event.get("title", "")
    date_str = format_date(event.get("event_date", ""))
    return f"[{date_str}] {label}: {title}"


# ── 空数据提示 ──

EMPTY_MESSAGES = {
    "tasks": "暂无任务",
    "projects": "暂无项目",
    "clients": "暂无客户",
    "files": "暂无文件",
    "events": "暂无活动记录",
    "notes": "暂无随手记",
    "summaries": "暂无每日总结",
    "general": "暂无数据",
}
