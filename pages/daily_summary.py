import streamlit as st
from datetime import date
from services.summary_service import generate_summary, get_summary_by_date, get_all_summaries, delete_summary
from services.task_service import get_tasks_by_date
from services.summary_service import get_notes_by_date
from services.timeline_service import get_events_by_date
from utils.date_utils import today_str


def render():
    st.title("每日总结")

    tab1, tab2 = st.tabs(["生成总结", "历史总结"])

    with tab1:
        _render_generate()

    with tab2:
        _render_history()


def _render_generate():
    selected_date = st.date_input("选择日期", date.today(), key="summary_date")
    date_str = selected_date.isoformat()

    st.subheader(f"{date_str} 工作数据")

    col1, col2, col3 = st.columns(3)
    with col1:
        tasks = get_tasks_by_date(date_str)
        done = sum(1 for t in tasks if t["status"] == "done")
        st.metric("任务", len(tasks))
        st.metric("完成", done)
    with col2:
        notes = get_notes_by_date(date_str)
        st.metric("随手记", len(notes))
    with col3:
        events = get_events_by_date(date_str)
        st.metric("活动", len(events))

    if st.button("生成工作总结", type="primary", key="gen_summary"):
        with st.spinner("AI正在生成总结..."):
            result = generate_summary(date_str)
            st.success("总结已生成")
            st.markdown(result["content"])
            if result.get("markdown_path"):
                st.info(f"已写入Obsidian: {result['markdown_path']}")

    existing = get_summary_by_date(date_str)
    if existing and existing["content"]:
        st.divider()
        st.subheader("已有总结")
        st.markdown(existing["content"])


def _render_history():
    summaries = get_all_summaries()
    if not summaries:
        st.info("暂无历史总结")
        return

    st.write(f"共 {len(summaries)} 条总结")

    for s in summaries:
        with st.expander(f"{s['summary_date']} 工作总结"):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(s["content"] or "无内容")
                if s["markdown_path"]:
                    st.caption(f"Obsidian: {s['markdown_path']}")
                st.caption(f"创建时间: {s['created_at']}")
            with col2:
                if st.button("删除", key=f"del_summary_{s['id']}", type="secondary"):
                    delete_summary(s["id"])
                    st.success(f"已删除总结: {s['summary_date']}")
                    st.rerun()
