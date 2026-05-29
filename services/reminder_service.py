"""
提醒服务 — 任务截止日期提醒、每日摘要生成。
"""
from datetime import date, timedelta
from database.db import fetch_all, fetch_one
from utils.date_utils import today_str


def get_today_tasks() -> list:
    """获取今日到期且未完成的任务。"""
    return fetch_all(
        "SELECT * FROM tasks WHERE due_date = ? AND status != 'done' AND status != 'cancelled' "
        "ORDER BY priority DESC",
        (today_str(),),
    )


def get_overdue_tasks() -> list:
    """获取逾期未完成的任务。"""
    return fetch_all(
        "SELECT * FROM tasks WHERE status != 'done' AND status != 'cancelled' "
        "AND due_date < ? AND due_date != '' ORDER BY due_date ASC",
        (today_str(),),
    )


def get_due_tasks(days: int = 3) -> list:
    """获取未来 N 天内到期的任务（不含今天和逾期）。"""
    end = (date.today() + timedelta(days=days)).isoformat()
    return fetch_all(
        "SELECT * FROM tasks WHERE status != 'done' AND status != 'cancelled' "
        "AND due_date > ? AND due_date <= ? ORDER BY due_date ASC, priority DESC",
        (today_str(), end),
    )


def get_high_priority_undone() -> list:
    """获取所有高优先级未完成的任务。"""
    return fetch_all(
        "SELECT * FROM tasks WHERE priority = 'high' AND status != 'done' AND status != 'cancelled' "
        "ORDER BY due_date ASC",
    )


def build_reminder_message() -> str:
    """构建提醒消息文本。"""
    today = get_today_tasks()
    overdue = get_overdue_tasks()
    upcoming = get_due_tasks(3)
    high_priority = get_high_priority_undone()

    lines = ["📋 **AI 办公助理 — 任务提醒**", ""]

    if overdue:
        lines.append(f"### ⚠️ 逾期任务 ({len(overdue)})")
        for t in overdue:
            due = t["due_date"] or "无截止日期"
            lines.append(f"- [{t['priority']}] {t['title']} — 截止: {due}")
        lines.append("")

    if today:
        lines.append(f"### 📅 今日任务 ({len(today)})")
        for t in today:
            p_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t["priority"], "")
            lines.append(f"- {p_emoji} {t['title']}")
        lines.append("")

    if upcoming:
        lines.append(f"### 🔜 未来3天 ({len(upcoming)})")
        for t in upcoming:
            due = t["due_date"] or ""
            lines.append(f"- [{t['priority']}] {t['title']} — {due}")
        lines.append("")

    if high_priority:
        lines.append(f"### 🔴 高优先级未完成 ({len(high_priority)})")
        for t in high_priority:
            lines.append(f"- {t['title']}")
        lines.append("")

    if not any([overdue, today, upcoming, high_priority]):
        lines.append("✅ 暂无待处理任务，一切顺利！")

    return "\n".join(lines)


def mark_reminder_sent(task_id: int):
    """标记任务提醒已发送（记录 workflow_log）。"""
    from services.workflow_log_service import add_workflow_log
    add_workflow_log("reminder_sent", "task", task_id, "success",
                     f"任务 #{task_id} 提醒已发送")


def generate_today_briefing() -> str:
    """生成今日工作简报。"""
    today = today_str()
    lines = [f"# 📋 工作简报 — {today}", ""]

    # 今日任务
    today_tasks = get_today_tasks()
    lines.append("## 今日任务")
    if today_tasks:
        for t in today_tasks:
            s_map = {"todo": "⭕", "doing": "🔵", "done": "✅", "cancelled": "❌"}
            lines.append(f"- {s_map.get(t['status'], '')} {t['title']}")
    else:
        lines.append("无今日到期任务")
    lines.append("")

    # 逾期任务
    overdue = get_overdue_tasks()
    if overdue:
        lines.append(f"## ⚠️ 逾期任务 ({len(overdue)})")
        for t in overdue:
            lines.append(f"- {t['title']} — 截止: {t['due_date']}")
        lines.append("")

    # 最近项目动态
    lines.append("## 最近项目动态")
    projects = fetch_all(
        "SELECT * FROM projects WHERE status = 'active' ORDER BY updated_at DESC LIMIT 5"
    )
    if projects:
        for p in projects:
            lines.append(f"- **{p['name']}** (进行中)")
    else:
        lines.append("无活跃项目")
    lines.append("")

    # 今日文件处理
    lines.append("## 今日文件处理")
    today_files = fetch_all(
        "SELECT * FROM files WHERE date(created_at) = ? ORDER BY created_at DESC", (today,)
    )
    if today_files:
        for f in today_files:
            lines.append(f"- {f['filename']} ({f.get('file_type', '')})")
    else:
        lines.append("今日无新文件")
    lines.append("")

    # 今日时间轴
    lines.append("## 今日动态")
    today_events = fetch_all(
        "SELECT * FROM timeline_events WHERE event_date = ? ORDER BY created_at DESC LIMIT 20",
        (today,),
    )
    if today_events:
        from utils.display_utils import format_event_type
        for e in today_events:
            label = format_event_type(e["event_type"])
            lines.append(f"- [{label}] {e['title']}")
    else:
        lines.append("今日暂无活动记录")

    return "\n".join(lines)


def send_today_briefing(receive_id: str = "") -> dict:
    """生成并发送今日简报。

    Args:
        receive_id: 接收者 open_id（为空时退回 log 模式）
    """
    try:
        briefing = generate_today_briefing()
        from services.feishu_service import send_feishu_message
        if not receive_id:
            from services.workflow_log_service import add_workflow_log
            add_workflow_log("daily_briefing_sent", "daily_summary", None, "error",
                             "未提供 receive_id，简报未发送")
            return {"success": False, "message": "未提供 receive_id"}
        result = send_feishu_message(receive_id, briefing)

        from services.workflow_log_service import add_workflow_log
        if result.get("success"):
            add_workflow_log("daily_briefing_sent", "daily_summary", None, "success",
                             "今日简报已发送")
        else:
            add_workflow_log("daily_briefing_sent", "daily_summary", None, "error",
                             f"发送失败: {result.get('message', '')}")
        return result
    except Exception as e:
        from services.workflow_log_service import add_workflow_log
        add_workflow_log("daily_briefing_sent", "daily_summary", None, "error", str(e))
        return {"success": False, "message": str(e)}
