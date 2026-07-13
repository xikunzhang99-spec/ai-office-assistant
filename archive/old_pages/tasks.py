import streamlit as st
import pandas as pd
from services.task_service import create_task, search_tasks, update_task, delete_task
from services.project_service import get_all_projects
from services.client_service import get_all_clients
from services.detail_service import get_task_detail, summarize_entity_detail
from config.settings import AI_API_KEY
from utils.display_utils import (
    status_badge, priority_badge, format_task_status, format_task_priority,
    format_project_status, format_event_type, format_file_type, format_date as fmt_date, EMPTY_MESSAGES,
)


def render():
    st.title("任务管理")

    tab1, tab2 = st.tabs(["任务列表", "新建任务"])

    with tab1:
        _render_task_list()

    with tab2:
        _render_task_form()


def _render_task_list():
    projects = get_all_projects()
    project_map = {p["id"]: p["name"] for p in projects}
    clients = get_all_clients()
    client_map = {c["id"]: c["name"] for c in clients}

    col_s, col_p, col_pr, col_c = st.columns(4)
    with col_s:
        status_filter = st.selectbox(
            "状态", ["全部", "todo", "doing", "done", "cancelled"],
            format_func=lambda x: "全部" if x == "全部" else format_task_status(x),
            key="task_status_filter",
        )
    with col_p:
        priority_filter = st.selectbox(
            "优先级", ["全部", "high", "medium", "low"],
            format_func=lambda x: "全部" if x == "全部" else format_task_priority(x),
            key="task_priority_filter",
        )
    with col_pr:
        project_options_list = ["全部"] + [p["name"] for p in projects]
        project_filter_name = st.selectbox("项目", project_options_list, key="task_project_filter")
    with col_c:
        client_options_list = ["全部"] + [c["name"] for c in clients]
        client_filter_name = st.selectbox("客户", client_options_list, key="task_client_filter")

    s = status_filter if status_filter != "全部" else None
    p = priority_filter if priority_filter != "全部" else None
    pr_id = None
    if project_filter_name != "全部":
        for proj in projects:
            if proj["name"] == project_filter_name:
                pr_id = proj["id"]
                break
    c_id = None
    if client_filter_name != "全部":
        for cli in clients:
            if cli["name"] == client_filter_name:
                c_id = cli["id"]
                break

    tasks = search_tasks(status=s, priority=p, project_id=pr_id, client_id=c_id)

    if not tasks:
        st.info(EMPTY_MESSAGES["tasks"])
        return

    st.write(f"共 {len(tasks)} 个任务")

    for task in tasks:
        s_badge = status_badge(task["status"])
        p_badge = priority_badge(task["priority"])
        expander_title = f"{s_badge} {p_badge} {task['title']}"

        with st.expander(expander_title, expanded=False):
            col1, col2 = st.columns([3, 2])

            with col1:
                if task["description"]:
                    st.info(task["description"])
                st.caption(f"标签: {task['tags'] or '无'}")
                st.caption(f"截止日期: {task['due_date'] or '无'}")
                st.caption(f"创建时间: {task['created_at']}")

                pid = task.get("project_id")
                cid = task.get("client_id")
                meta_parts = []
                if pid:
                    meta_parts.append(f"项目: {project_map.get(pid, '未知')}")
                if cid:
                    meta_parts.append(f"客户: {client_map.get(cid, '未知')}")
                if meta_parts:
                    st.caption(" | ".join(meta_parts))

            with col2:
                if st.button("查看详情", key=f"detail_task_{task['id']}"):
                    st.session_state["detail_task_id"] = task["id"]
                    st.rerun()

                new_status = st.selectbox(
                    "状态",
                    ["todo", "doing", "done", "cancelled"],
                    index=["todo", "doing", "done", "cancelled"].index(task["status"]),
                    format_func=format_task_status,
                    key=f"status_{task['id']}",
                )
                if new_status != task["status"]:
                    update_task(task["id"], status=new_status)
                    st.rerun()

                new_priority = st.selectbox(
                    "优先级",
                    ["high", "medium", "low"],
                    index=["high", "medium", "low"].index(task["priority"]),
                    format_func=format_task_priority,
                    key=f"pri_{task['id']}",
                )
                if new_priority != task["priority"]:
                    update_task(task["id"], priority=new_priority)
                    st.rerun()

                project_options = {"无": 0}
                for p_item in projects:
                    project_options[p_item["name"]] = p_item["id"]
                current_project_name = "无"
                current_project_id = task.get("project_id") or 0
                for name, pid_val in project_options.items():
                    if pid_val == current_project_id:
                        current_project_name = name
                        break
                new_project_name = st.selectbox(
                    "项目",
                    list(project_options.keys()),
                    index=list(project_options.keys()).index(current_project_name),
                    key=f"proj_{task['id']}",
                )
                new_project_id = project_options[new_project_name]
                if new_project_id != (task.get("project_id") or 0):
                    update_task(task["id"], project_id=new_project_id if new_project_id else None)
                    st.rerun()

                client_options = {"无": 0}
                for c_item in clients:
                    client_options[c_item["name"]] = c_item["id"]
                current_client_name = "无"
                current_client_id = task.get("client_id") or 0
                for name, cid_val in client_options.items():
                    if cid_val == current_client_id:
                        current_client_name = name
                        break
                new_client_name = st.selectbox(
                    "客户",
                    list(client_options.keys()),
                    index=list(client_options.keys()).index(current_client_name),
                    key=f"client_{task['id']}",
                )
                new_client_id = client_options[new_client_name]
                if new_client_id != (task.get("client_id") or 0):
                    update_task(task["id"], client_id=new_client_id if new_client_id else None)
                    st.rerun()

                if st.button("删除", key=f"del_{task['id']}", type="secondary"):
                    delete_task(task["id"])
                    st.success("已删除")
                    st.rerun()

    # 任务详情弹层
    detail_task_id = st.session_state.get("detail_task_id")
    if detail_task_id:
        _render_task_detail(detail_task_id)


def _render_task_detail(task_id: int):
    st.divider()
    detail = get_task_detail(task_id)
    if not detail["basic"]:
        st.error("任务不存在")
        if st.button("关闭详情", key="close_task_detail"):
            del st.session_state["detail_task_id"]
            st.rerun()
        return

    t = detail["basic"]

    col_title, col_close = st.columns([5, 1])
    with col_title:
        s_badge = status_badge(t.get("status", ""))
        p_badge = priority_badge(t.get("priority", ""))
        st.subheader(f"任务详情: {s_badge} {p_badge} {t['title']}")
    with col_close:
        if st.button("关闭", key="close_task_detail", type="secondary"):
            del st.session_state["detail_task_id"]
            st.rerun()

    # 基础信息
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"**状态**\n\n{format_task_status(t.get('status', ''))}")
    with col2:
        st.markdown(f"**优先级**\n\n{format_task_priority(t.get('priority', ''))}")
    with col3:
        st.markdown(f"**截止日期**\n\n{t.get('due_date') or '无'}")
    with col4:
        st.markdown(f"**创建时间**\n\n{t.get('created_at', '')}")

    if t.get("description"):
        st.info(t["description"])

    if t.get("tags"):
        st.caption(f"标签: {t['tags']}")

    # 所属项目 / 客户
    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        project = detail.get("project")
        if project:
            st.write(f"**所属项目**: {project['name']} [{format_project_status(project.get('status', ''))}]")
        else:
            st.caption("未关联项目")
    with col_b:
        client = detail.get("client")
        if client:
            st.write(f"**所属客户**: {client['name']}")
        else:
            st.caption("未关联客户")

    # 状态变更记录
    status_changes = detail.get("status_changes", [])
    if status_changes:
        st.subheader("状态变更记录")
        for sc in status_changes:
            label = format_event_type(sc.get("event_type", ""))
            date_str = sc.get("event_date", "")[:10] if sc.get("event_date") else ""
            desc = sc.get("description", "")
            st.write(f"- [{date_str}] {label}: {desc}")
    else:
        st.caption("暂无状态变更记录")

    # 关联文件
    if detail["files"]:
        st.subheader("关联文件")
        for f in detail["files"]:
            ftype = format_file_type(f.get("file_type", ""))
            st.write(f"- [{ftype}] {f['filename']}")
            if f.get("summary"):
                st.caption(f"  {f['summary'][:100]}")
    else:
        st.caption("暂无关联文件")

    # 最近活动
    if detail["events"]:
        st.subheader("最近活动")
        for e in detail["events"][:10]:
            label = format_event_type(e.get("event_type", ""))
            date_str = e.get("event_date", "")[:10] if e.get("event_date") else ""
            st.write(f"- [{date_str}] {label}: {e.get('title', '')}")

    # AI 总结
    st.divider()
    if AI_API_KEY:
        if st.button("AI 生成任务总结", key=f"ai_summary_task_{task_id}"):
            with st.spinner("AI 分析中..."):
                summary = summarize_entity_detail("task", detail)
                st.markdown("### AI 总结")
                st.markdown(summary)
    else:
        st.caption("AI 未配置，设置 AI_API_KEY 后可使用 AI 总结")


def _render_task_form():
    projects = get_all_projects()
    clients = get_all_clients()

    with st.form("new_task_form"):
        title = st.text_input("任务标题 *")
        description = st.text_area("描述")
        priority = st.selectbox("优先级", ["medium", "high", "low"],
                               format_func=format_task_priority)
        due_date = st.date_input("截止日期", value=None, key="task_due_date")
        tags = st.text_input("标签（逗号分隔）")

        col_proj, col_client = st.columns(2)
        with col_proj:
            project_options = {"无": 0}
            for p in projects:
                project_options[p["name"]] = p["id"]
            selected_project_name = st.selectbox("关联项目（可选）", list(project_options.keys()), key="task_form_project")
            selected_project_id = project_options[selected_project_name]

        with col_client:
            client_options = {"无": 0}
            for c in clients:
                client_options[c["name"]] = c["id"]
            selected_client_name = st.selectbox("关联客户（可选）", list(client_options.keys()), key="task_form_client")
            selected_client_id = client_options[selected_client_name]

        submitted = st.form_submit_button("创建任务")
        if submitted:
            if not title.strip():
                st.error("请输入任务标题")
            else:
                due_str = due_date.isoformat() if due_date else ""
                create_task(
                    title=title.strip(),
                    description=description.strip(),
                    priority=priority,
                    due_date=due_str,
                    tags=tags.strip(),
                    project_id=selected_project_id or None,
                    client_id=selected_client_id or None,
                )
                st.success("任务已创建")
                st.rerun()
