import streamlit as st
import pandas as pd
from datetime import date
from services.task_service import get_today_tasks, get_overdue_tasks, get_tasks_by_date_range, update_task, get_tasks_by_date
from services.summary_service import create_daily_note, get_today_notes, generate_summary, get_summary_by_date
from services.timeline_service import get_events_by_date, get_events_by_week, get_events_by_month
from services.project_service import get_all_projects
from services.client_service import get_all_clients
from services.file_service import get_all_files
from services.ai_service import _chat
from config.settings import AI_API_KEY
from utils.date_utils import today_str, week_start_date, week_end_date, month_start_date, month_end_date, format_date
from utils.display_utils import (
    status_badge, priority_badge, format_event_type, format_date as fmt_date,
    format_task_status, format_task_priority, format_project_status,
    EMPTY_MESSAGES,
)

MEMORY_TYPE_LABELS = {
    "client_preference": "客户偏好", "project_risk": "项目风险",
    "task_blocker": "任务阻塞", "decision": "决策",
    "meeting_conclusion": "会议结论", "follow_up": "跟进",
    "important_fact": "重要事实",
}

IMPORTANCE_COLORS = {
    "critical": "#dc3545", "high": "#fd7e14", "medium": "#ffc107", "low": "#6c757d",
}

IMPORTANCE_EMOJI = {
    "critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢",
}


def render():
    st.title("每日工作台")

    view_mode = st.radio("视图切换", ["日", "周", "月"], horizontal=True, key="dashboard_view")

    if view_mode == "日":
        _render_day_view()
    elif view_mode == "周":
        _render_week_view()
    else:
        _render_month_view()


def _render_day_view():
    selected_date = st.date_input("选择日期", date.today(), key="day_picker")
    date_str = selected_date.isoformat()

    col1, col2, col3 = st.columns(3)
    tasks = get_tasks_by_date(date_str)
    todo_tasks = [t for t in tasks if t["status"] == "todo"]
    doing_tasks = [t for t in tasks if t["status"] == "doing"]
    done_tasks = [t for t in tasks if t["status"] == "done"]

    with col1:
        st.metric("待办", len(todo_tasks))
    with col2:
        st.metric("进行中", len(doing_tasks))
    with col3:
        st.metric("已完成", len(done_tasks))

    st.divider()

    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader("今日待办任务")
        if todo_tasks:
            for task in todo_tasks:
                _render_task_card(task)
        else:
            st.info(EMPTY_MESSAGES["tasks"])

        if doing_tasks:
            st.subheader("进行中")
            for task in doing_tasks:
                _render_task_card(task)

        st.subheader("今日已完成")
        if done_tasks:
            for task in done_tasks[:10]:
                st.write(f"- ~~{task['title']}~~")
        else:
            st.info("暂无已完成任务")

        overdue = get_overdue_tasks()
        if overdue:
            st.subheader("逾期/即将到期")
            for task in overdue[:10]:
                p_badge = priority_badge(task["priority"])
                if task["priority"] == "high":
                    st.error(f"{p_badge} **{task['title']}** — 截止: {task['due_date']}")
                elif task["priority"] == "medium":
                    st.warning(f"{p_badge} {task['title']} — 截止: {task['due_date']}")
                else:
                    st.info(f"{p_badge} {task['title']} — 截止: {task['due_date']}")

    with col_right:
        st.subheader("今日随手记")
        note_text = st.text_area("记录想法", placeholder="输入今天的想法...", key="daily_note_input")
        if st.button("保存随手记", key="save_note"):
            if note_text.strip():
                create_daily_note(note_text.strip())
                st.success("已保存")
                st.rerun()

        notes = get_today_notes() if date_str == today_str() else []
        if notes:
            for note in notes[:5]:
                with st.expander(note["content"][:40] + "..." if len(note["content"]) > 40 else note["content"]):
                    st.write(note["content"])
                    st.caption(note["created_at"])

        st.divider()
        st.subheader("今日时间轴")
        events = get_events_by_date(date_str)
        if events:
            for event in events[:10]:
                label = format_event_type(event["event_type"])
                st.caption(f"[{label}] {event['title']}")
        else:
            st.info(EMPTY_MESSAGES["events"])

    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        with st.expander("最近项目", expanded=False):
            projects = get_all_projects()
            clients = get_all_clients()
            client_map = {c["id"]: c["name"] for c in clients}
            for p in projects[:5]:
                s_label = format_project_status(p["status"])
                client_name = client_map.get(p.get("client_id"), "") if p.get("client_id") else ""
                prefix = f"[{client_name}] " if client_name else ""
                st.write(f"- {prefix}**{p['name']}** [{s_label}]")

    with col_b:
        with st.expander("最近文件", expanded=False):
            files = get_all_files(limit=5)
            if files:
                for f_item in files:
                    st.write(f"- {f_item['filename']} ({f_item.get('file_type', '')})")
            else:
                st.caption(EMPTY_MESSAGES["files"])

    # ── AI 主动建议 ──
    with st.expander("🤖 AI 主动建议", expanded=True):
        if st.button("🔄 生成今日建议", key="gen_proactive_suggestions"):
            with st.spinner("AI 正在分析系统状态..."):
                try:
                    from services.proactive_suggestion_service import generate_daily_suggestions
                    suggestions = generate_daily_suggestions()

                    if suggestions.get("summary"):
                        st.markdown(f"### 💡 今日概要\n{suggestions['summary']}")

                    # 逾期事项
                    overdue_items = suggestions.get("overdue_items", [])
                    if overdue_items:
                        st.markdown("### ⚠️ 逾期事项")
                        for t in overdue_items[:5]:
                            p_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t.get("priority", ""), "")
                            st.error(f"{p_emoji} **{t['title']}** — 截止: {t.get('due_date', '')}")

                    # 高风险项目
                    risks = suggestions.get("project_risks", [])
                    if risks:
                        st.markdown("### 🚨 项目风险")
                        for r in risks[:5]:
                            c_name = f"[{r.get('client_name', '')}] " if r.get("client_name") else ""
                            st.warning(f"**{c_name}{r.get('name', '')}**: {r.get('description', r.get('risk_source', ''))}")

                    # 需跟进客户
                    clients_follow = suggestions.get("clients_to_follow", [])
                    if clients_follow:
                        st.markdown("### 📞 需跟进客户")
                        for c in clients_follow[:5]:
                            st.info(f"**{c['name']}** — {c.get('active_projects', 0)} 个活跃项目，建议联系")

                    # 未执行文件建议
                    pending = suggestions.get("pending_document_actions", [])
                    if pending:
                        st.markdown(f"### 📄 未执行文件建议 ({len(pending)})")
                        for f_item in pending[:5]:
                            st.caption(f"📄 {f_item['filename']} — 有未执行的建议动作")

                    # 最近重要记忆
                    memories = suggestions.get("recent_memories", [])
                    if memories:
                        st.markdown("### 🧠 最近重要记忆")
                        for m in memories[:5]:
                            imp = IMPORTANCE_EMOJI.get(m.get("importance", ""), "")
                            mtype = MEMORY_TYPE_LABELS.get(m.get("memory_type", ""), m.get("memory_type", ""))
                            with st.container(border=True):
                                st.caption(f"{imp} [{mtype}] **{m.get('title', '')}**")
                                if m.get("content"):
                                    st.caption(m["content"][:150])

                    if not any([overdue_items, risks, clients_follow, pending, memories]):
                        st.success("✅ 今日一切正常，无特别需要关注的事项。")

                except Exception as e:
                    st.error(f"生成建议失败: {str(e)[:200]}")

        # 快速状态统计（静态）
        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        with col_r1:
            try:
                from services.memory_service import get_memory_stats
                m_stats = get_memory_stats()
                st.metric("长期记忆", m_stats.get("total", 0))
            except Exception:
                st.metric("长期记忆", "—")
        with col_r2:
            try:
                from services.relation_service import find_risk_relations
                risks_all = find_risk_relations()
                st.metric("风险关系", len(risks_all))
            except Exception:
                st.metric("风险关系", "—")
        with col_r3:
            try:
                from services.relation_service import find_follow_up_relations
                fus = find_follow_up_relations()
                st.metric("跟进事项", len(fus))
            except Exception:
                st.metric("跟进事项", "—")
        with col_r4:
            try:
                from services.proactive_suggestion_service import detect_overdue_followups
                od_fus = detect_overdue_followups()
                st.metric("逾期跟进", len(od_fus))
            except Exception:
                st.metric("逾期跟进", "—")

        # 项目阶段分布
        try:
            from services.workflow_engine import get_project_progress
            st.divider()
            st.caption("📊 项目阶段分布")
            projects = get_all_projects()
            active_projects = [p for p in projects if p["status"] == "active"]
            if active_projects:
                for p in active_projects[:8]:
                    try:
                        progress = get_project_progress(p["id"])
                        current = progress.get("active_stage", {})
                        stage_name = current.get("stage_name", "未设置") if current else "未设置"
                        pct = progress.get("stage_completion_pct", 0)
                        client_label = f"[{client_map.get(p.get('client_id'), '')}] " if p.get("client_id") and client_map.get(p.get("client_id")) else ""
                        st.progress(
                            pct / 100,
                            text=f"{client_label}{p['name']} — {stage_name} ({progress['completed_stages']}/{progress['total_stages']})"
                        )
                    except Exception:
                        st.caption(f"📁 {p['name']} — 尚未初始化阶段")
            else:
                st.caption("暂无活跃项目")
        except Exception:
            pass

    st.divider()
    st.subheader("生成工作总结")
    if st.button("生成今日总结", type="primary"):
        with st.spinner("AI正在生成总结..."):
            result = generate_summary(date_str)
            st.success("总结已生成")
            st.markdown(result["content"])
            if result.get("markdown_path"):
                st.info(f"已写入Obsidian: {result['markdown_path']}")

    existing_summary = get_summary_by_date(date_str)
    if existing_summary:
        with st.expander("查看历史总结"):
            st.markdown(existing_summary["content"])


def _render_week_view():
    ws = week_start_date()
    we = week_end_date()
    st.subheader(f"本周 ({format_date(ws)} ~ {format_date(we)})")

    tasks = get_tasks_by_date_range(ws.isoformat(), we.isoformat())
    done = [t for t in tasks if t["status"] == "done"]

    col1, col2 = st.columns(2)
    with col1:
        st.metric("本周任务", len(tasks))
    with col2:
        st.metric("本周完成", len(done))

    st.subheader("本周活动")
    events = get_events_by_week(ws.isoformat(), we.isoformat())
    if events:
        df = pd.DataFrame([{
            "日期": fmt_date(e["event_date"]),
            "类型": format_event_type(e["event_type"]),
            "描述": e["title"],
        } for e in events])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info(EMPTY_MESSAGES["events"])


def _render_month_view():
    ms = month_start_date()
    me = month_end_date()
    st.subheader(f"本月 ({format_date(ms)} ~ {format_date(me)})")

    tasks = get_tasks_by_date_range(ms.isoformat(), me.isoformat())
    done = [t for t in tasks if t["status"] == "done"]
    total = len(tasks)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("本月任务", total)
    with col2:
        st.metric("本月完成", len(done))
    with col3:
        st.metric("完成率", f"{len(done)/total*100:.0f}%" if total > 0 else "0%")

    st.subheader("本月活动")
    events = get_events_by_month(ms.year, ms.month)
    if events:
        df = pd.DataFrame([{
            "日期": fmt_date(e["event_date"]),
            "类型": format_event_type(e["event_type"]),
            "描述": e["title"],
        } for e in events])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info(EMPTY_MESSAGES["events"])


def _render_task_card(task):
    cols = st.columns([4, 1, 1])
    s_badge = status_badge(task["status"])
    p_badge = priority_badge(task["priority"])

    with cols[0]:
        st.write(f"{s_badge} {p_badge} **{task['title']}**")
        if task["due_date"]:
            st.caption(f"截止: {task['due_date']}")
    with cols[1]:
        if task["status"] != "done" and st.button("完成", key=f"done_{task['id']}"):
            update_task(task["id"], status="done")
            st.rerun()
    with cols[2]:
        if task["status"] == "todo" and st.button("开始", key=f"doing_{task['id']}"):
            update_task(task["id"], status="doing")
            st.rerun()
