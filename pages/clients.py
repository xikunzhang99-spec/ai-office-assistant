import streamlit as st
import pandas as pd
from services.client_service import create_client, get_all_clients, delete_client, update_client
from services.relation_service import get_relation_network
from services.detail_service import get_client_detail, summarize_entity_detail
from config.settings import AI_API_KEY
from utils.display_utils import (
    format_event_type, format_task_status, format_project_status,
    format_file_type, EMPTY_MESSAGES,
)


def render():
    st.title("客户管理")

    with st.form("new_client_form"):
        name = st.text_input("客户名称 *")
        description = st.text_area("描述")
        contact_info = st.text_input("联系方式")
        submitted = st.form_submit_button("创建客户")
        if submitted and name.strip():
            create_client(name.strip(), description.strip(), contact_info.strip())
            st.success("客户已创建")
            st.rerun()

    st.divider()
    clients = get_all_clients()

    if not clients:
        st.info(EMPTY_MESSAGES["clients"])
        return

    st.write(f"共 {len(clients)} 个客户")

    for c in clients:
        network = get_relation_network("client", c["id"])
        projects = network.get("projects", [])
        project_count = len(projects)
        title = c["name"]
        if project_count > 0:
            title += f"  [{project_count}个项目]"

        with st.expander(title):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**描述**：{c['description'] or '无'}")
                st.write(f"**联系方式**：{c['contact_info'] or '无'}")
                st.write(f"**创建时间**：{c['created_at']}")

                if projects:
                    st.write("**关联项目**")
                    for p in projects:
                        s = format_project_status(p.get("status", ""))
                        st.write(f"- {p['name']}（{s}）")

            with col2:
                if st.button("查看详情", key=f"detail_client_{c['id']}"):
                    st.session_state["detail_client_id"] = c["id"]
                    st.rerun()

                if st.button("编辑", key=f"edit_client_{c['id']}"):
                    st.session_state[f"editing_client_{c['id']}"] = True

                if st.button("删除", key=f"del_client_{c['id']}", type="secondary"):
                    delete_client(c["id"])
                    st.success(f"已删除客户: {c['name']}")
                    st.rerun()

            if st.session_state.get(f"editing_client_{c['id']}"):
                st.divider()
                st.caption("编辑客户")
                new_name = st.text_input("名称", value=c["name"], key=f"edit_cname_{c['id']}")
                new_desc = st.text_area("描述", value=c["description"] or "", key=f"edit_cdesc_{c['id']}")
                new_contact = st.text_input("联系方式", value=c["contact_info"] or "", key=f"edit_ccontact_{c['id']}")

                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("保存", key=f"save_client_{c['id']}"):
                        update_client(c["id"], name=new_name, description=new_desc, contact_info=new_contact)
                        st.session_state[f"editing_client_{c['id']}"] = False
                        st.success("已更新")
                        st.rerun()
                with col_cancel:
                    if st.button("取消", key=f"cancel_client_{c['id']}"):
                        st.session_state[f"editing_client_{c['id']}"] = False
                        st.rerun()

            _render_network(network)

    # 客户详情弹层
    detail_id = st.session_state.get("detail_client_id")
    if detail_id:
        _render_client_detail(detail_id)


def _render_client_detail(client_id: int):
    st.divider()
    detail = get_client_detail(client_id)
    if not detail["basic"]:
        st.error("客户不存在")
        if st.button("关闭详情", key="close_client_detail"):
            del st.session_state["detail_client_id"]
            st.rerun()
        return

    c = detail["basic"]

    col_title, col_close = st.columns([5, 1])
    with col_title:
        st.subheader(f"客户详情: {c['name']}")
    with col_close:
        if st.button("关闭", key="close_client_detail", type="secondary"):
            del st.session_state["detail_client_id"]
            st.rerun()

    # 基础信息卡片
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**名称**\n\n{c['name']}")
    with col2:
        st.markdown(f"**联系方式**\n\n{c.get('contact_info') or '无'}")
    with col3:
        st.markdown(f"**创建时间**\n\n{c.get('created_at', '')}")

    if c.get("description"):
        st.info(c["description"])

    # 统计概览
    st.divider()
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("关联项目", len(detail["projects"]))
    with col_b:
        st.metric("关联任务", len(detail["tasks"]))
    with col_c:
        st.metric("关联文件", len(detail["files"]))
    with col_d:
        st.metric("最近活动", len(detail["events"]))

    # 关联项目
    if detail["projects"]:
        st.subheader("关联项目")
        data = [{"名称": p["name"],
                 "状态": format_project_status(p.get("status", "")),
                 "描述": (p.get("description") or "")[:60]}
                for p in detail["projects"]]
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

    # 关联任务
    if detail["tasks"]:
        st.subheader("关联任务")
        data = [{"标题": t["title"],
                 "状态": format_task_status(t.get("status", "")),
                 "优先级": format_task_status(t.get("priority", "")),
                 "截止日期": t.get("due_date") or "-"}
                for t in detail["tasks"]]
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
    else:
        st.caption("暂无关联任务")

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

    # 最近活动（最近10条）
    if detail["events"]:
        st.subheader("最近活动")
        for e in detail["events"][:10]:
            label = format_event_type(e.get("event_type", ""))
            date_str = e.get("event_date", "")[:10] if e.get("event_date") else ""
            st.write(f"- [{date_str}] {label}: {e.get('title', '')}")
    else:
        st.caption("暂无活动记录")

    # ── 长期记忆 ──
    try:
        from services.memory_service import get_memory_by_client
        memories = get_memory_by_client(client_id, limit=20)
        if memories:
            st.divider()
            st.subheader(f"🧠 长期记忆 ({len(memories)})")
            risk_memories = [m for m in memories if m["memory_type"] in ("project_risk", "task_blocker")]
            other_memories = [m for m in memories if m not in risk_memories]

            if risk_memories:
                st.markdown("#### 🚨 风险/阻塞")
                for m in risk_memories[:5]:
                    imp_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                        m.get("importance", ""), "")
                    mtype = {
                        "client_preference": "客户偏好", "project_risk": "项目风险",
                        "task_blocker": "任务阻塞", "decision": "决策",
                        "meeting_conclusion": "会议结论", "follow_up": "跟进",
                        "important_fact": "重要事实",
                    }.get(m.get("memory_type", ""), m.get("memory_type", ""))
                    st.warning(f"{imp_emoji} [{mtype}] **{m.get('title', '')}**")
                    if m.get("content"):
                        st.caption(f"  {m['content'][:200]}")

            if other_memories:
                st.markdown("#### 📝 其他记忆")
                for m in other_memories[:10]:
                    imp_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                        m.get("importance", ""), "")
                    mtype = {
                        "client_preference": "客户偏好", "project_risk": "项目风险",
                        "task_blocker": "任务阻塞", "decision": "决策",
                        "meeting_conclusion": "会议结论", "follow_up": "跟进",
                        "important_fact": "重要事实",
                    }.get(m.get("memory_type", ""), m.get("memory_type", ""))
                    st.write(f"{imp_emoji} [{mtype}] **{m.get('title', '')}**")
                    if m.get("content"):
                        st.caption(f"  {m['content'][:200]}")
    except Exception:
        pass

    # ── 客户跟进建议 ──
    try:
        from services.proactive_suggestion_service import generate_client_suggestions
        st.divider()
        st.subheader("💡 客户跟进建议")
        if st.button("生成跟进建议", key=f"gen_client_suggestions_{client_id}"):
            with st.spinner("AI 分析中..."):
                s = generate_client_suggestions(client_id)
                if s.get("suggestions"):
                    st.markdown(s["suggestions"])
                if s.get("risks"):
                    st.markdown("**风险**")
                    for r in s["risks"][:3]:
                        st.warning(r.get("description", str(r)))
                if s.get("follow_ups"):
                    st.markdown("**需跟进**")
                    for f in s["follow_ups"][:3]:
                        st.info(f.get("description", str(f)))
    except Exception:
        pass

    # AI 总结按钮
    st.divider()
    if AI_API_KEY:
        if st.button("AI 生成客户总结", key=f"ai_summary_client_{client_id}"):
            with st.spinner("AI 分析中..."):
                summary = summarize_entity_detail("client", detail)
                st.markdown("### AI 总结")
                st.markdown(summary)
    else:
        st.caption("AI 未配置，设置 AI_API_KEY 后可使用 AI 总结")


def _render_network(network):
    projects = network.get("projects", [])
    tasks = network.get("tasks", [])
    files = network.get("files", [])
    events = network.get("events", [])

    has_relations = any([projects, tasks, files, events])
    if not has_relations:
        return

    st.divider()
    st.caption("更多关联数据")

    if tasks:
        st.write("**相关任务**")
        for t in tasks:
            s = format_task_status(t.get("status", ""))
            st.write(f"- [{s}] {t['title']}")
            if t.get("due_date"):
                st.write(f"  截止: {t['due_date']}")

    if files:
        st.write("**相关文件**")
        for f_item in files:
            tags_str = f" [{f_item['tags']}]" if f_item.get("tags") else ""
            st.write(f"- {f_item['filename']}{tags_str}")

    if events:
        st.write("**最近事件**（最近5条）")
        for e in events[:5]:
            label = format_event_type(e.get("event_type", ""))
            st.write(f"- [{label}] {e.get('title', '')}（{e.get('event_date', '')}）")
