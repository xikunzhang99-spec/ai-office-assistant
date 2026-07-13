import streamlit as st
import pandas as pd
import json
from datetime import date
from services.timeline_service import (
    get_events_by_date, get_events_by_week, get_events_by_month, get_all_events,
    search_events,
    EVENT_TYPE_LABELS,
)
from services.project_service import get_all_projects
from services.client_service import get_all_clients
from utils.date_utils import week_start_date, week_end_date, month_start_date, month_end_date, format_date
from utils.display_utils import (
    format_event_type, format_date as fmt_date, format_related_type,
    EMPTY_MESSAGES,
)


def render():
    st.title("时间轴")

    view_mode = st.radio("视图", ["日", "周", "月", "全部"], horizontal=True, key="timeline_view")

    _render_filters()

    if view_mode == "日":
        _render_day_timeline()
    elif view_mode == "周":
        _render_week_timeline()
    elif view_mode == "月":
        _render_month_timeline()
    else:
        _render_all_timeline()


def _render_filters():
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        types = list(EVENT_TYPE_LABELS.keys())
        st.session_state["tl_type_filter"] = st.multiselect(
            "事件类型", types,
            default=st.session_state.get("tl_type_filter", []),
            format_func=lambda t: EVENT_TYPE_LABELS.get(t, t),
            key="tl_type_select",
        )

    with col2:
        projects = get_all_projects()
        project_map = {0: "全部"}
        project_map.update({p["id"]: p["name"] for p in projects})
        selected = st.selectbox(
            "项目筛选",
            list(project_map.keys()),
            format_func=lambda pid: project_map[pid],
            key="tl_project_filter",
        )
        st.session_state["tl_project_id"] = selected if selected != 0 else None

    with col3:
        clients = get_all_clients()
        client_map = {0: "全部"}
        client_map.update({c["id"]: c["name"] for c in clients})
        selected = st.selectbox(
            "客户筛选",
            list(client_map.keys()),
            format_func=lambda cid: client_map[cid],
            key="tl_client_filter",
        )
        st.session_state["tl_client_id"] = selected if selected != 0 else None

    with col4:
        st.session_state["tl_keyword"] = st.text_input("关键词搜索", key="tl_keyword_input")


def _get_filtered_events(events, use_search: bool = True, limit: int = 200, **kwargs):
    if use_search:
        type_filter = None
        types = st.session_state.get("tl_type_filter", [])
        if types and len(types) == 1:
            type_filter = types[0]

        return search_events(
            event_type=type_filter,
            project_id=st.session_state.get("tl_project_id"),
            client_id=st.session_state.get("tl_client_id"),
            keyword=st.session_state.get("tl_keyword") or None,
            limit=limit,
            **kwargs,
        )

    events = events or []
    types = st.session_state.get("tl_type_filter", [])
    if types:
        events = [e for e in events if e["event_type"] in types]
    pid = st.session_state.get("tl_project_id")
    if pid:
        events = [e for e in events if e["project_id"] == pid]
    cid = st.session_state.get("tl_client_id")
    if cid:
        events = [e for e in events if e["client_id"] == cid]
    kw = st.session_state.get("tl_keyword")
    if kw:
        kw_lower = kw.lower()
        events = [e for e in events if
                  (e["title"] and kw_lower in e["title"].lower()) or
                  (e["description"] and kw_lower in e["description"].lower())]
    return events


def _render_day_timeline():
    d = st.date_input("选择日期", date.today(), key="tl_day")
    date_str = d.isoformat()
    events = _get_filtered_events(None, start_date=date_str, end_date=date_str)
    _render_events(events, f"{date_str} 活动")


def _render_week_timeline():
    ws = week_start_date()
    we = week_end_date()
    events = _get_filtered_events(None, start_date=ws.isoformat(), end_date=we.isoformat(), limit=500)
    _render_events(events, f"本周活动 ({format_date(ws)} ~ {format_date(we)})")


def _render_month_timeline():
    today = date.today()
    year = st.selectbox("年", list(range(today.year - 1, today.year + 3)), index=1, key="tl_year")
    month = st.selectbox("月", list(range(1, 13)), index=today.month - 1, key="tl_month")
    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year}-12-31"
    else:
        end = f"{year}-{month+1:02d}-01"
    events = _get_filtered_events(None, start_date=start, end_date=end, limit=1000)
    _render_events(events, f"{year}年{month}月活动")


def _render_all_timeline():
    events = _get_filtered_events(None, limit=500)
    _render_events(events, "全部活动")


def _render_events(events, title: str):
    st.subheader(title)

    if not events:
        st.info(EMPTY_MESSAGES["events"])
        return

    st.caption(f"共 {len(events)} 条记录")

    # Resolve project/client names
    projects = get_all_projects()
    project_map = {p["id"]: p["name"] for p in projects}
    clients = get_all_clients()
    client_map = {c["id"]: c["name"] for c in clients}

    data = []
    for e in events:
        project_name = project_map.get(e["project_id"], "") if e["project_id"] else ""
        client_name = client_map.get(e["client_id"], "") if e["client_id"] else ""

        data.append({
            "日期": fmt_date(e["event_date"]),
            "类型": format_event_type(e["event_type"]),
            "标题": e["title"],
            "描述": (e["description"] or "")[:60],
            "项目": project_name,
            "客户": client_name,
            "时间": (e["created_at"] or "")[:19],
        })

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("时间线详情")

    for event in events:
        label = format_event_type(event["event_type"])
        date_str = fmt_date(event["event_date"])

        st.markdown(f"**{date_str}** {label}: {event['title']}")

        extras = []
        if event["description"]:
            extras.append(f"描述: {event['description'][:120]}")
        if event["tags"]:
            extras.append(f"标签: {event['tags']}")
        if event["related_type"] and event["related_id"]:
            rt_label = format_related_type(event["related_type"])
            extras.append(f"关联: {rt_label}#{event['related_id']}")
        if event["metadata"]:
            try:
                meta = json.loads(event["metadata"])
                extras.append(f"变更: {json.dumps(meta, ensure_ascii=False)[:80]}")
            except Exception:
                pass

        if extras:
            st.caption(" | ".join(extras))
