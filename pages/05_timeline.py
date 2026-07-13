import streamlit as st
from datetime import date, timedelta
from collections import defaultdict

from services.timeline_service import (
    search_events, get_all_events,
    EVENT_TYPE_LABELS, EVENT_TYPE_ICONS,
)
from services.summary_service import create_daily_note
from utils.date_utils import today_str, now_str
from utils.display_utils import format_event_type


EVENT_TYPE_GROUPS = {
    "全部": None,
    "手动记录": "manual",
    "随手记": "daily_note",
    "任务相关": ["task_created", "task_updated", "task_status_changed", "task_completed", "task_deleted"],
    "文件相关": ["file_uploaded", "file_summarized", "file_markdown_created", "file_written_to_obsidian", "file_updated", "file_deleted"],
    "项目相关": ["project_created", "project_updated", "project_deleted"],
    "客户相关": ["client_created", "client_updated", "client_deleted"],
    "每日总结": "daily_summary",
    "AI问答": "ai_query",
}


def render():
    st.title("时间轴")

    # ── 筛选区 ──
    _render_filter_bar()

    st.divider()

    # ── 手动记录 ──
    with st.expander("+ 手动记录", expanded=False):
        manual_text = st.text_area("记录内容", placeholder="输入要记录的内容…", height=80, key="ts_manual")
        if st.button("保存记录", key="ts_save_manual"):
            if manual_text.strip():
                create_daily_note(manual_text.strip())
                st.success("已保存到时间轴")
                st.rerun()
            else:
                st.warning("请输入内容")

    st.divider()

    # ── 事件列表（按日期分组）──
    _render_grouped_events()


def _render_filter_bar():
    """筛选栏"""
    col_date1, col_date2, col_type, col_keyword = st.columns([1, 1, 1.2, 1.2])

    with col_date1:
        st.date_input("开始日期", value=None, key="ts_start")
    with col_date2:
        st.date_input("结束日期", value=None, key="ts_end")
    with col_type:
        st.selectbox("事件类型", list(EVENT_TYPE_GROUPS.keys()), key="ts_type")
    with col_keyword:
        st.text_input("关键词", placeholder="搜索标题或内容…",
                      key="ts_keyword", label_visibility="collapsed")


def _fetch_events():
    """根据当前筛选条件获取事件列表"""
    start_date = st.session_state.get("ts_start")
    end_date = st.session_state.get("ts_end")
    event_group = st.session_state.get("ts_type", "全部")
    keyword = st.session_state.get("ts_keyword")

    start_str = start_date.isoformat() if start_date else None
    end_str = end_date.isoformat() if end_date else None

    event_types = EVENT_TYPE_GROUPS.get(event_group)
    if isinstance(event_types, list):
        all_events = []
        for et in event_types:
            events = search_events(
                start_date=start_str, end_date=end_str,
                event_type=et, keyword=keyword or None, limit=100
            )
            all_events.extend(events)
        all_events.sort(key=lambda e: (e.get("event_date") or "", e.get("created_at") or ""), reverse=True)
        return all_events[:300]
    else:
        return search_events(
            start_date=start_str, end_date=end_str,
            event_type=event_types, keyword=keyword or None, limit=300
        )


def _group_events_by_date(events):
    """将事件按 event_date 分组"""
    groups = defaultdict(list)
    for e in events:
        date_key = (e.get("event_date") or "")[:10] or "(无日期)"
        groups[date_key].append(e)
    # 按日期倒序排列
    sorted_groups = sorted(groups.items(), key=lambda x: x[0], reverse=True)
    return sorted_groups


def _render_grouped_events():
    """按日期分组渲染事件"""
    events = _fetch_events()
    st.caption(f"共 {len(events)} 条记录")

    if not events:
        st.info("暂无匹配的时间轴记录")
        return

    grouped = _group_events_by_date(events)

    for date_label, day_events in grouped:
        # 日期头部
        _render_date_header(date_label, day_events)

        # 当日事件列表
        for event in day_events:
            _render_event_row(event)


def _render_date_header(date_label, day_events):
    """渲染日期分组头部"""
    # 格式化日期显示
    try:
        d = date.fromisoformat(date_label)
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        display = f"{d.year}年{d.month}月{d.day}日 星期{weekdays[d.weekday()]}"
    except (ValueError, TypeError):
        display = date_label

    # 统计当日各类型数量
    type_counts = defaultdict(int)
    for e in day_events:
        etype = e.get("event_type", "unknown")
        cat = _event_category(etype)
        type_counts[cat] += 1

    summary_parts = []
    if type_counts.get("task"):
        summary_parts.append(f"任务 {type_counts['task']}")
    if type_counts.get("file"):
        summary_parts.append(f"文件 {type_counts['file']}")
    if type_counts.get("note"):
        summary_parts.append(f"记录 {type_counts['note']}")
    if type_counts.get("project"):
        summary_parts.append(f"项目 {type_counts['project']}")
    if type_counts.get("client"):
        summary_parts.append(f"客户 {type_counts['client']}")
    if type_counts.get("summary"):
        summary_parts.append("总结")
    if type_counts.get("other"):
        summary_parts.append(f"其他 {type_counts['other']}")

    summary = " | ".join(summary_parts) if summary_parts else ""

    st.markdown(f"### 📅 {display}  ({len(day_events)}条)")
    if summary:
        st.caption(f"  {summary}")
    st.markdown("<hr style='margin:0.2em 0 0.5em 0'>", unsafe_allow_html=True)


def _event_category(etype):
    """将事件类型归类"""
    if etype in ("task_created", "task_updated", "task_status_changed", "task_completed", "task_deleted"):
        return "task"
    if etype in ("file_uploaded", "file_summarized", "file_markdown_created",
                 "file_written_to_obsidian", "file_updated", "file_deleted"):
        return "file"
    if etype in ("daily_note", "manual", "daily_note_deleted"):
        return "note"
    if etype in ("project_created", "project_updated", "project_deleted",
                 "stage_initialized", "stage_advanced", "stage_skipped", "project_stage_inferred"):
        return "project"
    if etype in ("client_created", "client_updated", "client_deleted"):
        return "client"
    if etype in ("daily_summary", "daily_summary_written_to_obsidian", "daily_summary_deleted"):
        return "summary"
    return "other"


def _render_event_row(event):
    """渲染单条事件（紧凑行 + 可展开详情）"""
    event_id = event.get("id", id(event))
    etype = event.get("event_type", "")
    icon = EVENT_TYPE_ICONS.get(etype, "")
    label = EVENT_TYPE_LABELS.get(etype, etype)
    title = event.get("title", "") or "(无标题)"
    created_at = (event.get("created_at") or "")[11:16]  # 只取 HH:MM
    description = event.get("description", "")
    related_type = event.get("related_type", "")
    related_id = event.get("related_id", "")

    has_detail = bool(description or event.get("project_id")
                      or event.get("client_id") or related_type)
    is_active = st.session_state.get("_active_detail_id") == event_id

    # 紧凑行
    c1, c2, c3, c4 = st.columns([1.3, 4, 1.2, 0.8])

    with c1:
        st.caption(f"[{icon} {label}]")
    with c2:
        display_title = title if len(title) <= 50 else title[:48] + "…"
        st.markdown(f"**{display_title}**")
    with c3:
        st.caption(created_at)
    with c4:
        if has_detail:
            if is_active:
                if st.button("收起", key=f"cls_{event_id}", use_container_width=True):
                    st.session_state["_active_detail_id"] = None
                    st.rerun()
            else:
                if st.button("详情", key=f"det_{event_id}", use_container_width=True):
                    st.session_state["_active_detail_id"] = event_id
                    st.rerun()

    # 详情展开（互斥：同时只展开一条）
    if is_active and has_detail:
        with st.expander("事件详情", expanded=True):
            st.caption(f"事件类型: {label}")
            st.caption(f"创建时间: {event.get('created_at', '')}")
            st.caption(f"事件日期: {event.get('event_date', '')}")
            if description:
                st.write(description)
            if event.get("project_id"):
                st.caption(f"关联项目ID: {event['project_id']}")
            if event.get("client_id"):
                st.caption(f"关联客户ID: {event['client_id']}")
            if related_type and related_id:
                st.caption(f"关联: {related_type}#{related_id}")


render()
