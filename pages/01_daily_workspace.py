import streamlit as st
import os
import json
from datetime import date, datetime, timedelta

from services.task_service import (
    get_today_tasks, get_overdue_tasks, get_tasks_by_date_range,
    update_task, create_task, search_tasks,
    mark_task_on_calendar, unmark_task_from_calendar,
    get_calendar_tasks,
)
from services.summary_service import (
    create_daily_note, get_today_notes, generate_summary,
    get_summary_by_date, get_notes_by_date,
)
from services.timeline_service import get_events_by_date, get_events_by_week, add_event
from services.project_service import get_all_projects
from services.client_service import get_all_clients
from services.file_service import save_file_record, get_all_files
from services.file_parser import parse_file
from services.ai_service import summarize_file
from config.settings import UPLOAD_DIR
from utils.date_utils import (
    today_str, week_start_date, week_end_date, now_str, format_date,
)
from utils.display_utils import (
    status_badge, priority_badge, format_event_type,
    format_task_status, format_task_priority, format_project_status,
    EMPTY_MESSAGES,
)

# ── display limits to keep sections compact ──
MAX_VISIBLE_TODO = 6
MAX_VISIBLE_DOING = 2
MAX_VISIBLE_NOTES = 4
MAX_VISIBLE_EVENTS = 5
MAX_VISIBLE_PROJECTS = 5
MAX_VISIBLE_CLIENTS = 5
MAX_VISIBLE_FILES = 3


def render():
    today = date.today()
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    st.title("每日工作台")
    st.caption(
        f"{today.year}年{today.month}月{today.day}日 "
        f"星期{weekdays[today.weekday()]}"
    )

    # ── 1. 统计栏 + 快速操作 ──
    _render_stats_bar()

    st.divider()

    # ── 2. 双列主体：今日任务 | 随手记 + 周视图 ──
    col_left, col_right = st.columns([6, 4])
    with col_left:
        _render_today_tasks_v2()
    with col_right:
        _render_notes_and_week()

    st.divider()

    # ── 3. 业务概览（三卡片）──
    _render_business_overview()

    st.divider()

    # ── 4. 每日总结 ──
    _render_daily_summary()


# ═══════════════════════════════════════════════════════════════════════════
# 1. 统计栏 + 快速操作
# ═══════════════════════════════════════════════════════════════════════════

def _render_stats_bar():
    tasks = get_today_tasks()
    todo = sum(1 for t in tasks if t["status"] == "todo")
    doing = sum(1 for t in tasks if t["status"] == "doing")
    done = sum(1 for t in tasks if t["status"] == "done")
    overdue_tasks = get_overdue_tasks()
    overdue_count = len(overdue_tasks)

    # 第一行：指标 + 快速按钮
    c_stats = st.columns([1, 1, 1, 1, 2.5])
    with c_stats[0]:
        st.markdown(
            f"<div style='text-align:center'><small>待办</small><br><b style='font-size:1.3em'>{todo}</b></div>",
            unsafe_allow_html=True,
        )
    with c_stats[1]:
        st.markdown(
            f"<div style='text-align:center'><small>进行中</small><br><b style='font-size:1.3em'>{doing}</b></div>",
            unsafe_allow_html=True,
        )
    with c_stats[2]:
        st.markdown(
            f"<div style='text-align:center'><small>已完成</small><br><b style='font-size:1.3em'>{done}</b></div>",
            unsafe_allow_html=True,
        )
    with c_stats[3]:
        color = "#e74c3c" if overdue_count > 0 else "#666"
        st.markdown(
            f"<div style='text-align:center'><small>逾期</small><br>"
            f"<b style='font-size:1.3em;color:{color}'>{overdue_count}</b></div>",
            unsafe_allow_html=True,
        )
    with c_stats[4]:
        st.write("")  # spacer
        btn_cols = st.columns(3)
        with btn_cols[0]:
            if st.button("＋ 新任务", use_container_width=True, key="qh_new_task"):
                st.session_state._show_quick_task = True
        with btn_cols[1]:
            if st.button("＋ 随手记", use_container_width=True, key="qh_new_note"):
                st.session_state._scroll_to_notes = True
        with btn_cols[2]:
            if st.button("📤 传文件", use_container_width=True, key="qh_upload"):
                st.session_state._show_file_upload = True

    # 快速新建任务弹出
    if st.session_state.get("_show_quick_task"):
        with st.expander("新建任务", expanded=True):
            _quick_task_form()

    # 逾期高亮条
    if overdue_tasks:
        high_overdue = [t for t in overdue_tasks if t["priority"] == "high"]
        if high_overdue:
            names = "、".join(t["title"][:20] for t in high_overdue[:3])
            st.error(f"⚠️ 逾期高优先级: {names}")


def _quick_task_form():
    with st.form("quick_task_form_v2", clear_on_submit=True):
        c1, c2 = st.columns([2, 1])
        with c1:
            title = st.text_input("任务标题", key="qt_title")
        with c2:
            priority = st.selectbox("优先级", ["medium", "high", "low"],
                                    format_func=format_task_priority, key="qt_pri")
        c3, c4 = st.columns([1, 1])
        with c3:
            due = st.date_input("截止日期", value=None, key="qt_due")
        with c4:
            st.write("")
            st.write("")
            submitted = st.form_submit_button("创建", use_container_width=True)
        if submitted and title.strip():
            due_str = due.isoformat() if due else today_str()
            create_task(title=title.strip(), priority=priority, due_date=due_str)
            st.success(f"任务「{title}」已创建")
            st.session_state._show_quick_task = False
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# 2. 今日任务（紧凑版）
# ═══════════════════════════════════════════════════════════════════════════

def _render_today_tasks_v2():
    st.subheader("⏰ 今日任务")

    tasks = get_today_tasks()
    todo = [t for t in tasks if t["status"] == "todo"]
    doing = [t for t in tasks if t["status"] == "doing"]
    done = [t for t in tasks if t["status"] == "done"]
    overdue = get_overdue_tasks()

    # ── 逾期提醒（紧凑）──
    if overdue:
        st.caption(f"⚠️ 逾期/即将到期 {len(overdue)} 项")
        for task in overdue[:3]:
            p_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task["priority"], "⚪")
            due_info = f"截止: {task['due_date']}" if task.get("due_date") else ""
            st.caption(f"{p_emoji} {task['title'][:30]} — {due_info}")

    # ── 待办 ──
    if todo:
        st.caption(f"📋 待办 ({len(todo)})")
        visible = todo[:MAX_VISIBLE_TODO]
        for task in visible:
            _render_compact_task_row(task)
        if len(todo) > MAX_VISIBLE_TODO:
            with st.expander(f"+ 更多待办 ({len(todo) - MAX_VISIBLE_TODO} 项)", expanded=False):
                for task in todo[MAX_VISIBLE_TODO:]:
                    _render_compact_task_row(task)
    elif not overdue and not doing:
        st.info(EMPTY_MESSAGES["tasks"])

    # ── 进行中 ──
    if doing:
        st.caption(f"🔄 进行中 ({len(doing)})")
        visible = doing[:MAX_VISIBLE_DOING]
        for task in visible:
            _render_compact_task_row(task)
        if len(doing) > MAX_VISIBLE_DOING:
            with st.expander(f"+ 更多进行中 ({len(doing) - MAX_VISIBLE_DOING} 项)", expanded=False):
                for task in doing[MAX_VISIBLE_DOING:]:
                    _render_compact_task_row(task)

    # ── 已完成（折叠）──
    if done:
        with st.expander(f"✅ 已完成 ({len(done)})", expanded=False):
            for task in done[:20]:
                st.caption(f"~~{task['title'][:40]}~~")


def _render_compact_task_row(task):
    """紧凑单行任务：优先级 · 标题 · 截止日期 + 操作按钮"""
    task_id = task["id"]
    p_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task["priority"], "⚪")
    on_calendar = task.get("show_on_calendar") == 1
    title = task["title"]
    if len(title) > 30:
        title = title[:28] + "…"

    c1, c2, c3, c4, c5 = st.columns([0.4, 3.5, 1.8, 1.2, 1.2])

    with c1:
        st.markdown(f"<span style='font-size:1.1em'>{p_emoji}</span>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"**{title}**")
    with c3:
        due = task.get("due_date", "")
        if due:
            st.caption(f"截止:{due}")
        else:
            st.caption("无截止")
    with c4:
        if task["status"] == "todo":
            st.button("▶ 开始", key=f"start_{task_id}", use_container_width=True,
                       on_click=_do_start_task, args=(task_id,))
        elif task["status"] == "doing":
            st.button("✓ 完成", key=f"done_{task_id}", use_container_width=True,
                       on_click=_do_complete_task, args=(task_id,))
        else:
            st.write("")
    with c5:
        if not on_calendar:
            st.button("📅", key=f"calin_{task_id}", use_container_width=True,
                       help="标记到日历",
                       on_click=_do_mark_calendar, args=(task_id, task.get("due_date")))
        else:
            st.button("📅", key=f"calout_{task_id}", use_container_width=True,
                       help="取消日历标记",
                       on_click=_do_unmark_calendar, args=(task_id,))


def _do_start_task(task_id):
    update_task(task_id, status="doing")
    st.rerun()


def _do_complete_task(task_id):
    update_task(task_id, status="done")
    st.rerun()


def _do_mark_calendar(task_id, due_date):
    cal_date = due_date or date.today().isoformat()
    mark_task_on_calendar(task_id, cal_date)
    st.rerun()


def _do_unmark_calendar(task_id):
    unmark_task_from_calendar(task_id)
    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# 3. 随手记 + 周视图（右列）
# ═══════════════════════════════════════════════════════════════════════════

def _render_notes_and_week():
    # ── 随手记输入 ──
    st.subheader("📝 随手记")
    note_content = st.text_area(
        "写一条随手记",
        placeholder="记录今天的工作内容…",
        height=80,
        label_visibility="collapsed",
        key="daily_note_input_v2",
    )
    c_save, c_fill = st.columns([1, 2])
    with c_save:
        if st.button("保存", use_container_width=True, key="save_note_v2"):
            if note_content.strip():
                create_daily_note(note_content.strip())
                st.success("已保存")
                st.rerun()
            else:
                st.warning("请输入内容")

    # ── 今日记录 ──
    st.caption("── 📌 今日记录 ──")
    notes = get_today_notes()
    if notes:
        for note in notes[:MAX_VISIBLE_NOTES]:
            content = note["content"]
            if len(content) > 40:
                content = content[:38] + "…"
            ts = (note.get("created_at") or "")[11:16] if note.get("created_at") else ""
            st.caption(f"• {content}  {ts}")
        if len(notes) > MAX_VISIBLE_NOTES:
            with st.expander(f"查看全部 ({len(notes)} 条)", expanded=False):
                for note in notes[MAX_VISIBLE_NOTES:]:
                    st.caption(f"• {note['content'][:50]}")
    else:
        st.caption("今天还没有随手记")

    st.write("")

    # ── 本周速览条 ──
    st.caption("── 📅 本周速览 ──")
    _render_week_strip()

    # ── 最近活动 ──
    st.caption("── 📜 最近活动 ──")
    ws = week_start_date()
    we = week_end_date()
    events = get_events_by_week(ws.isoformat(), we.isoformat())
    if events:
        for e in events[:MAX_VISIBLE_EVENTS]:
            label = format_event_type(e["event_type"])
            date_str = (e.get("event_date") or "")[5:10] if e.get("event_date") else ""
            st.caption(f"[{date_str}] {label}: {e['title'][:30]}")
    else:
        st.caption(EMPTY_MESSAGES.get("events", "暂无活动"))

    # 完整日历入口
    with st.expander("📅 完整月日历", expanded=False):
        _render_compact_calendar()


def _render_week_strip():
    """紧凑本周条：7天，标任务数"""
    ws = week_start_date()
    today = today_str()
    we = ws + timedelta(days=6)
    week_tasks = get_tasks_by_date_range(ws.isoformat(), we.isoformat())

    tasks_by_day = {}
    for t in week_tasks:
        due = t.get("due_date", "")
        if due:
            tasks_by_day.setdefault(due, []).append(t)

    week_labels = ["一", "二", "三", "四", "五", "六", "日"]
    cols = st.columns(7)

    for i in range(7):
        day_date = ws + timedelta(days=i)
        day_str = day_date.isoformat()
        day_tasks = tasks_by_day.get(day_str, [])
        count = len(day_tasks)
        is_today = day_str == today

        with cols[i]:
            if is_today:
                st.markdown(f"<div style='text-align:center'><b>{week_labels[i]}</b></div>",
                            unsafe_allow_html=True)
                st.markdown(f"<div style='text-align:center;color:#1f77b4;font-weight:bold'>{day_date.day}</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='text-align:center'>{week_labels[i]}</div>",
                            unsafe_allow_html=True)
                st.markdown(f"<div style='text-align:center'>{day_date.day}</div>",
                            unsafe_allow_html=True)

            if count:
                st.markdown(f"<div style='text-align:center;font-size:0.85em;color:#e74c3c'>{count}项</div>",
                            unsafe_allow_html=True)
            elif is_today:
                st.markdown(f"<div style='text-align:center;font-size:0.85em;color:#1f77b4'>今天</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='text-align:center;font-size:0.85em;color:#ccc'>—</div>",
                            unsafe_allow_html=True)

    # 本周统计
    todo_count = sum(1 for t in week_tasks if t["status"] in ("todo", "doing"))
    done_count = sum(1 for t in week_tasks if t["status"] == "done")
    st.caption(f"⚡ 本周待完成 {todo_count} / 已完成 {done_count}")


def _render_compact_calendar():
    """折叠的完整月日历"""
    import calendar as cal_mod
    today = date.today()

    if "cal_year_v2" not in st.session_state:
        st.session_state.cal_year_v2 = today.year
    if "cal_month_v2" not in st.session_state:
        st.session_state.cal_month_v2 = today.month

    year = st.session_state.cal_year_v2
    month = st.session_state.cal_month_v2

    cp, ct, cn = st.columns([1, 3, 1])
    with cp:
        if st.button("◀", key="cal_p2", use_container_width=True):
            if month == 1:
                st.session_state.cal_month_v2 = 12
                st.session_state.cal_year_v2 -= 1
            else:
                st.session_state.cal_month_v2 -= 1
            st.rerun()
    with ct:
        st.markdown(f"**{year}年{month}月**")
    with cn:
        if st.button("▶", key="cal_n2", use_container_width=True):
            if month == 12:
                st.session_state.cal_month_v2 = 1
                st.session_state.cal_year_v2 += 1
            else:
                st.session_state.cal_month_v2 += 1
            st.rerun()

    cal_tasks = get_calendar_tasks(year, month)
    tasks_by_date = {}
    for t in cal_tasks:
        task_date = t.get("calendar_date") or t.get("due_date") or ""
        if task_date:
            tasks_by_date.setdefault(task_date, []).append(t)

    month_cal = cal_mod.monthcalendar(year, month)
    week_headers = ["一", "二", "三", "四", "五", "六", "日"]

    hcols = st.columns(7)
    for i, h in enumerate(week_headers):
        hcols[i].markdown(f"**{h}**")

    for week in month_cal:
        dcols = st.columns(7)
        for i, day in enumerate(week):
            with dcols[i]:
                if day == 0:
                    st.write("")
                else:
                    date_str = f"{year}-{month:02d}-{day:02d}"
                    day_tasks = tasks_by_date.get(date_str, [])
                    is_today = (date_str == today.isoformat())
                    if is_today:
                        st.markdown(f"**{day}** 🔵")
                    elif day_tasks:
                        st.markdown(f"**{day}**")
                        st.caption(f"{len(day_tasks)}项")
                    else:
                        st.markdown(f"**{day}**")


# ═══════════════════════════════════════════════════════════════════════════
# 4. 业务概览（三卡片）
# ═══════════════════════════════════════════════════════════════════════════

def _render_business_overview():
    st.subheader("🗂️ 业务概览")

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        st.markdown("##### 📁 活跃项目")
        _render_projects_card()

    with col_b:
        st.markdown("##### 👥 客户动态")
        _render_clients_card()

    with col_c:
        st.markdown("##### 📄 最近文件")
        _render_files_card()


def _render_projects_card():
    projects = get_all_projects()
    clients = get_all_clients()
    client_map = {c["id"]: c["name"] for c in clients}

    active = [p for p in projects if p["status"] == "active"]
    other = [p for p in projects if p["status"] != "active"]

    visible = (active + other)[:MAX_VISIBLE_PROJECTS]

    if not visible:
        st.info(EMPTY_MESSAGES.get("projects", "暂无项目"))
        return

    for p in visible:
        s_emoji = {"active": "🟢", "pending": "🟡", "completed": "✅", "on_hold": "⏸️"}.get(p["status"], "⚪")
        client_name = client_map.get(p.get("client_id"), "") if p.get("client_id") else ""
        prefix = f"[{client_name}] " if client_name else ""
        name = p["name"]
        if len(name) > 18:
            name = name[:16] + "…"
        st.caption(f"{s_emoji} {prefix}{name}")

    if len(projects) > MAX_VISIBLE_PROJECTS:
        st.caption(f"… 共 {len(projects)} 个项目")


def _render_clients_card():
    clients = get_all_clients()
    projects = get_all_projects()

    if not clients:
        st.info(EMPTY_MESSAGES.get("clients", "暂无客户"))
        return

    for c in clients[:MAX_VISIBLE_CLIENTS]:
        active_count = sum(1 for p in projects
                           if p.get("client_id") == c["id"] and p["status"] == "active")
        name = c["name"]
        if len(name) > 18:
            name = name[:16] + "…"
        st.caption(f"• {name} ({active_count}活跃)")

    if len(clients) > MAX_VISIBLE_CLIENTS:
        st.caption(f"… 共 {len(clients)} 个客户")


def _render_files_card():
    files = get_all_files(limit=MAX_VISIBLE_FILES)

    if files:
        for f_item in files:
            ftype = f_item.get("file_type", "")
            fname = f_item["filename"]
            if len(fname) > 22:
                fname = fname[:20] + "…"
            st.caption(f"📄 {fname} ({ftype})")
    else:
        st.caption(EMPTY_MESSAGES.get("files", "暂无文件"))

    if st.button("＋ 上传并分析", use_container_width=True, key="card_upload_btn"):
        st.session_state._show_file_upload = True

    if st.session_state.get("_show_file_upload"):
        with st.expander("上传文件", expanded=True):
            _render_file_upload_inline()


def _render_file_upload_inline():
    """内联文件上传（完整流程）"""
    uploaded_file = st.file_uploader(
        "选择文件",
        type=["docx", "pptx", "xlsx", "xls", "pdf", "md", "txt", "csv"],
        key="workspace_file_uploader_v2",
        label_visibility="collapsed",
    )

    if not uploaded_file:
        return

    st.write(f"已选择: **{uploaded_file.name}** ({uploaded_file.size} bytes)")

    if st.button("解析并保存", type="primary", key="btn_ws_analyze_v2"):
        with st.spinner("正在处理文件…"):
            filename = uploaded_file.name
            file_ext = os.path.splitext(filename)[1].lower()

            saved_path = os.path.join(UPLOAD_DIR, f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}")
            with open(saved_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            content = parse_file(saved_path)
            if content.startswith("[文件解析失败]"):
                st.error(content)
                return

            result = summarize_file(content, filename)
            st.success("文件解析完成")

            st.subheader("AI 摘要")
            st.write(result.get("summary", ""))

            if result.get("key_points"):
                st.subheader("关键点")
                for pt in result["key_points"]:
                    st.write(f"- {pt}")

            default_tags = ", ".join(result.get("tags", []))
            tags = st.text_input("标签（可修改）", value=default_tags, key="ws_file_tags_v2")

            col_p, col_c = st.columns(2)
            with col_p:
                projects = get_all_projects()
                proj_opts = {"无": None}
                for p_item in projects:
                    proj_opts[p_item["name"]] = p_item["id"]
                sel_proj = st.selectbox("关联项目", list(proj_opts.keys()), key="ws_file_proj_v2")
                sel_proj_id = proj_opts[sel_proj]
            with col_c:
                clients = get_all_clients()
                cli_opts = {"无": None}
                for c_item in clients:
                    cli_opts[c_item["name"]] = c_item["id"]
                sel_cli = st.selectbox("关联客户", list(cli_opts.keys()), key="ws_file_cli_v2")
                sel_cli_id = cli_opts[sel_cli]

            if st.button("确认保存", key="btn_ws_save_file_v2"):
                file_id = save_file_record(
                    filename=filename, file_path=saved_path,
                    file_type=file_ext,
                    summary=result.get("summary", ""),
                    key_points=result.get("key_points", []),
                    suggestions=result.get("suggestions", []),
                    tags=tags,
                    project_id=sel_proj_id,
                    client_id=sel_cli_id,
                )
                add_event("file_uploaded", f"上传文件: {filename}",
                          project_id=sel_proj_id, client_id=sel_cli_id)
                st.success(f"文件「{filename}」已保存")
                st.session_state._show_file_upload = False
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# 5. 每日总结
# ═══════════════════════════════════════════════════════════════════════════

def _render_daily_summary():
    st.subheader("🤖 今日AI总结")
    today = today_str()

    col_gen, col_view = st.columns([1, 1])

    with col_gen:
        st.caption("基于今日数据生成工作总结")
        c_btn1, c_btn2 = st.columns([1, 1])
        with c_btn1:
            if st.button("✨ 生成今日总结", type="primary", use_container_width=True,
                         key="gen_ws_summary_v2"):
                with st.spinner("AI正在生成总结…"):
                    try:
                        result = generate_summary(today)
                        st.success("总结已生成")
                    except Exception as e:
                        st.error(f"生成失败: {str(e)[:200]}")
        with c_btn2:
            existing = get_summary_by_date(today)
            has_history = existing and existing.get("content")
            if st.button("📋 查看历史", use_container_width=True, key="view_history_v2",
                         disabled=not has_history):
                st.session_state._show_history_summary = True

    with col_view:
        existing = get_summary_by_date(today)
        if existing and existing.get("content"):
            with st.expander("查看今日总结", expanded=True):
                st.markdown(existing["content"])
        else:
            st.info("今日暂无总结，点击左侧按钮生成")


render()
