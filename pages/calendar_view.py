import streamlit as st
import calendar
from datetime import date, datetime, timedelta
from services.task_service import get_tasks_by_date, get_tasks_by_date_range
from services.timeline_service import get_events_by_date, get_events_by_week
from services.summary_service import get_notes_by_date, get_summary_by_date
from services.project_service import get_all_projects
from services.reminder_service import get_today_tasks, get_overdue_tasks, get_due_tasks
from utils.date_utils import month_start_date, month_end_date, week_start_date, week_end_date, format_date, today_str
from utils.display_utils import format_event_type, EMPTY_MESSAGES, format_task_status, format_task_priority

PRIORITY_COLORS = {"high": "red", "medium": "orange", "low": "green"}
STATUS_COLORS = {"todo": "gray", "doing": "blue", "done": "green", "cancelled": "gray"}
PRIORITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}
STATUS_EMOJI = {"todo": "⭕", "doing": "🔵", "done": "✅", "cancelled": "❌"}


def render():
    st.title("日历视图")

    # ── 顶部任务概览卡片 ──
    _render_task_overview()

    st.divider()

    # ── 月历视图 ──
    today = date.today()
    year = st.selectbox("年", list(range(today.year - 2, today.year + 3)), index=2, key="cal_year")
    month = st.selectbox("月", list(range(1, 13)), index=today.month - 1, key="cal_month")

    _render_month_calendar(year, month)


def _render_task_overview():
    """顶部任务概览：今日 / 逾期 / 本周 / 高优先级"""
    col1, col2, col3, col4 = st.columns(4)

    today_tasks = get_today_tasks()
    overdue_tasks = get_overdue_tasks()
    upcoming_tasks = get_due_tasks(3)

    with col1:
        count = len(today_tasks)
        st.metric("📅 今日任务", count)
        if today_tasks:
            for t in today_tasks[:5]:
                emoji = PRIORITY_EMOJI.get(t["priority"], "")
                st.caption(f"{emoji} {t['title'][:20]}")

    with col2:
        count = len(overdue_tasks)
        st.metric("⚠️ 逾期任务", count, delta=f"{count} 项" if count > 0 else None)
        if overdue_tasks:
            for t in overdue_tasks[:5]:
                st.caption(f"🔴 {t['title'][:20]} ({t.get('due_date', '')[:10]})")

    with col3:
        ws = week_start_date().isoformat()
        we = week_end_date().isoformat()
        week_tasks = get_tasks_by_date_range(ws, we)
        st.metric("📆 本周任务", len(week_tasks))

    with col4:
        high_undone = [t for t in today_tasks + overdue_tasks if t["priority"] == "high"]
        st.metric("🔴 高优先级", len(high_undone))


def _render_month_calendar(year: int, month: int):
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdayscalendar(year, month)

    day_names = ["一", "二", "三", "四", "五", "六", "日"]
    cols = st.columns(7)
    for i, name in enumerate(day_names):
        cols[i].markdown(f"**{name}**")

    today = date.today()

    if "selected_cal_date" not in st.session_state:
        st.session_state.selected_cal_date = today.isoformat()

    # 预取本月所有任务，用于在日历格中显示颜色标记
    m_start = f"{year}-{month:02d}-01"
    m_end = month_end_date(date(year, month, 1)).isoformat()
    month_tasks = get_tasks_by_date_range(m_start, m_end)
    tasks_by_date = {}
    for t in month_tasks:
        d = t.get("due_date", "")[:10] or t.get("created_at", "")[:10]
        if d:
            tasks_by_date.setdefault(d, []).append(t)

    for week in month_days:
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                if day == 0:
                    st.write("")
                else:
                    d = date(year, month, day)
                    date_str = d.isoformat()
                    day_tasks = tasks_by_date.get(date_str, [])
                    done_count = sum(1 for t in day_tasks if t["status"] == "done")
                    total = len(day_tasks)

                    # 颜色标记：有逾期未完成 → red, 有今日任务 → orange, 有任务 → blue, 完成 → green
                    has_overdue = any(
                        t["status"] not in ("done", "cancelled") and t.get("due_date", "")[:10] < today.isoformat()
                        for t in day_tasks
                    )
                    has_today_due = any(
                        t["status"] not in ("done", "cancelled") for t in day_tasks
                    )

                    label = str(day)
                    if d == today:
                        label = f"**{day}**"

                    # 状态描述
                    task_info = ""
                    if total > 0:
                        task_info = f"({done_count}/{total})"
                        if has_overdue:
                            task_info += " ⚠️"

                    button_type = "primary" if date_str == st.session_state.selected_cal_date else "secondary"
                    if st.button(f"{label} {task_info}", key=f"cal_day_{date_str}",
                                 use_container_width=True):
                        st.session_state.selected_cal_date = date_str

    st.divider()
    selected = st.session_state.selected_cal_date
    st.subheader(f"{selected} 详情")

    _render_day_detail(selected)


def _render_day_detail(date_str: str):
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**任务**")
        tasks = get_tasks_by_date(date_str)
        if tasks:
            for task in tasks:
                s_emoji = STATUS_EMOJI.get(task["status"], "")
                p_emoji = PRIORITY_EMOJI.get(task.get("priority", ""), "")
                color = PRIORITY_COLORS.get(task.get("priority", ""), "gray")
                st.markdown(
                    f"{s_emoji} {p_emoji} :{color}[{task['title']}]"
                )
                if task.get("description"):
                    st.caption(task["description"][:60])
        else:
            st.info(EMPTY_MESSAGES.get("tasks", "无任务"))

        # 项目时间节点
        st.divider()
        st.markdown("**项目里程碑**")
        projects = get_all_projects()
        active_projects = [p for p in projects if p["status"] == "active"]
        if active_projects:
            for p in active_projects[:5]:
                # 获取项目相关任务数
                from services.task_service import search_tasks
                p_tasks = search_tasks(project_id=p["id"], limit=100)
                done = sum(1 for t in p_tasks if t["status"] == "done")
                st.caption(f"📁 {p['name']} — 任务 {done}/{len(p_tasks)}")
        else:
            st.caption("无活跃项目")

    with col2:
        st.markdown("**随手记**")
        notes = get_notes_by_date(date_str)
        if notes:
            for note in notes:
                st.caption(note["content"][:80])
        else:
            st.info(EMPTY_MESSAGES.get("notes", "无随手记"))

        st.divider()
        st.markdown("**时间轴**")
        events = get_events_by_date(date_str)
        if events:
            for event in events[:10]:
                label = format_event_type(event["event_type"])
                st.caption(f"[{label}] {event['title'][:50]}")
        else:
            st.info(EMPTY_MESSAGES.get("events", "无活动"))

    with col3:
        st.markdown("**每日总结**")
        summary = get_summary_by_date(date_str)
        if summary and summary["content"]:
            with st.expander("查看总结"):
                st.markdown(summary["content"])
        else:
            st.info(EMPTY_MESSAGES.get("summaries", "无总结"))

    # ── 本周时间轴 ──
    st.divider()
    st.subheader(f"本周时间轴 ({week_start_date().isoformat()} ~ {week_end_date().isoformat()})")

    ws = week_start_date(date.fromisoformat(date_str)).isoformat()
    we = week_end_date(date.fromisoformat(date_str)).isoformat()
    week_events = get_events_by_week(ws, we)
    if week_events:
        for event in week_events[:20]:
            label = format_event_type(event["event_type"])
            ev_date = event.get("event_date", "")[:10]
            st.caption(f"[{ev_date}] [{label}] {event['title'][:60]}")
    else:
        st.info("本周暂无活动")
