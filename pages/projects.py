import streamlit as st
import pandas as pd
from services.project_service import create_project, get_all_projects, update_project, delete_project
from services.client_service import get_all_clients
from services.task_service import search_tasks
from services.relation_service import get_relation_network
from services.detail_service import get_project_detail, summarize_entity_detail
from config.settings import AI_API_KEY
from utils.display_utils import (
    format_project_status, format_task_status, format_task_priority,
    format_event_type, format_file_type, format_stage_status, EMPTY_MESSAGES,
)


def render():
    st.title("项目管理")

    clients = get_all_clients()
    client_map = {c["id"]: c for c in clients}

    with st.form("new_project_form"):
        name = st.text_input("项目名称 *")
        description = st.text_area("描述")
        client_options = {"无": 0}
        for c_item in clients:
            client_options[c_item["name"]] = c_item["id"]
        selected_client_name = st.selectbox("关联客户（可选）", list(client_options.keys()))
        submitted = st.form_submit_button("创建项目")
        if submitted and name.strip():
            cid = client_options[selected_client_name] or None
            pid = create_project(name.strip(), description.strip(), client_id=cid)
            st.success("项目已创建")
            # 自动初始化阶段
            try:
                from services.workflow_engine import init_project_stages
                init_project_stages(pid)
            except Exception:
                pass
            st.rerun()

    st.divider()
    projects = get_all_projects()

    if not projects:
        st.info(EMPTY_MESSAGES["projects"])
        return

    st.write(f"共 {len(projects)} 个项目")

    for p in projects:
        status_label = format_project_status(p["status"])
        client_name = ""
        if p.get("client_id"):
            c = client_map.get(p["client_id"])
            if c:
                client_name = c["name"]

        expander_title = p["name"]
        if client_name:
            expander_title = f"[{client_name}] {expander_title}"
        expander_title += f" [{status_label}]"

        with st.expander(expander_title):
            tasks = search_tasks(project_id=p["id"])
            done_count = sum(1 for t in tasks if t["status"] == "done")
            doing_count = sum(1 for t in tasks if t["status"] == "doing")
            todo_count = sum(1 for t in tasks if t["status"] == "todo")
            total_tasks = len(tasks)

            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"**描述**：{p['description'] or '无'}")
                st.write(f"**关联客户**：{client_name or '无'}")
                st.write(f"**创建时间**：{p['created_at']}")

                if total_tasks > 0:
                    progress = done_count / total_tasks
                    st.progress(progress, text=f"进度 {progress:.0%}（{done_count}/{total_tasks}）")
                    st.caption(f"待办 {todo_count} | 进行中 {doing_count} | 已完成 {done_count}")

            # 阶段进度
            try:
                from services.workflow_engine import (
                    get_project_progress, get_project_stages,
                    advance_stage, skip_stage, init_project_stages,
                )
                progress = get_project_progress(p["id"])
                if progress["total_stages"] > 0:
                    st.divider()
                    st.caption(f"📊 阶段进度 ({progress['completed_stages']}/{progress['total_stages']})")
                    stage_data = []
                    for sb in progress["stage_breakdown"]:
                        emoji = {"active": "🔵", "completed": "✅", "skipped": "⏭️", "pending": "⚪"}.get(sb["status"], "")
                        stage_data.append(f"{emoji} {sb['stage_name']}")
                    st.caption(" → ".join(stage_data))
                    st.progress(
                        progress["stage_completion_pct"] / 100,
                        text=f"阶段 {progress['stage_completion_pct']:.0f}% | 任务 {progress['task_completion_pct']:.0f}%"
                    )

                    # 阶段操作按钮
                    current_stage = progress.get("active_stage")
                    if current_stage:
                        col_adv, col_skip = st.columns(2)
                        with col_adv:
                            if st.button(f"✅ 完成「{current_stage['stage_name']}」→ 下一阶段", key=f"adv_{p['id']}"):
                                result = advance_stage(p["id"], current_stage["id"])
                                if result["success"]:
                                    st.success(f"已推进到下一阶段")
                                else:
                                    st.error(result.get("error", "失败"))
                                st.rerun()
                        with col_skip:
                            if st.button(f"⏭️ 跳过「{current_stage['stage_name']}」", key=f"skip_{p['id']}"):
                                skip_stage(current_stage["id"])
                                st.success("已跳过该阶段")
                                st.rerun()
                else:
                    if st.button("⚙️ 初始化阶段", key=f"init_stages_{p['id']}"):
                        init_project_stages(p["id"])
                        st.success("阶段已初始化")
                        st.rerun()
            except Exception:
                pass

            with col_b:
                if st.button("查看详情", key=f"detail_proj_{p['id']}"):
                    st.session_state["detail_project_id"] = p["id"]
                    st.rerun()

                if st.button("编辑", key=f"edit_proj_{p['id']}"):
                    st.session_state[f"editing_project_{p['id']}"] = True

                if st.button("删除", key=f"del_proj_{p['id']}", type="secondary"):
                    delete_project(p["id"])
                    st.success(f"已删除项目: {p['name']}")
                    st.rerun()

            if st.session_state.get(f"editing_project_{p['id']}"):
                st.divider()
                st.caption("编辑项目")
                new_name = st.text_input("名称", value=p["name"], key=f"edit_pname_{p['id']}")
                new_desc = st.text_area("描述", value=p["description"] or "", key=f"edit_pdesc_{p['id']}")
                new_status = st.selectbox(
                    "状态", ["active", "archived", "completed"],
                    index=["active", "archived", "completed"].index(p["status"]) if p["status"] in ["active", "archived", "completed"] else 0,
                    format_func=format_project_status,
                    key=f"edit_pstatus_{p['id']}",
                )
                client_options_edit = {"无": 0}
                for c_item in clients:
                    client_options_edit[c_item["name"]] = c_item["id"]
                cur_cname = "无"
                cur_cid = p.get("client_id") or 0
                for name, cid_v in client_options_edit.items():
                    if cid_v == cur_cid:
                        cur_cname = name
                        break
                new_cname = st.selectbox("客户", list(client_options_edit.keys()),
                                         index=list(client_options_edit.keys()).index(cur_cname),
                                         key=f"edit_pclient_{p['id']}")
                new_cid = client_options_edit[new_cname] or None

                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("保存", key=f"save_proj_{p['id']}"):
                        update_project(p["id"], name=new_name, description=new_desc,
                                      status=new_status, client_id=new_cid)
                        st.session_state[f"editing_project_{p['id']}"] = False
                        st.success("已更新")
                        st.rerun()
                with col_cancel:
                    if st.button("取消", key=f"cancel_proj_{p['id']}"):
                        st.session_state[f"editing_project_{p['id']}"] = False
                        st.rerun()

            if tasks:
                st.divider()
                st.caption(f"项目任务 ({total_tasks})")
                for t in tasks:
                    s_label = format_task_status(t["status"])
                    p_label = format_task_priority(t["priority"])
                    done_mark = "~~" if t["status"] == "done" else ""
                    st.write(f"- [{p_label}] [{s_label}] {done_mark}{t['title']}{done_mark}")
                    if t.get("due_date"):
                        st.caption(f"  截止: {t['due_date']}")

            network = get_relation_network("project", p["id"])
            _render_network(network)

    # 项目详情弹层
    detail_proj_id = st.session_state.get("detail_project_id")
    if detail_proj_id:
        _render_project_detail(detail_proj_id)


def _render_project_detail(project_id: int):
    st.divider()
    detail = get_project_detail(project_id)
    if not detail["basic"]:
        st.error("项目不存在")
        if st.button("关闭详情", key="close_project_detail"):
            del st.session_state["detail_project_id"]
            st.rerun()
        return

    p = detail["basic"]

    col_title, col_close = st.columns([5, 1])
    with col_title:
        st.subheader(f"项目详情: {p['name']}")
    with col_close:
        if st.button("关闭", key="close_project_detail", type="secondary"):
            del st.session_state["detail_project_id"]
            st.rerun()

    # 基础信息 + 所属客户
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**名称**\n\n{p['name']}")
    with col2:
        st.markdown(f"**状态**\n\n{format_project_status(p.get('status', ''))}")
    with col3:
        client = detail.get("client")
        st.markdown(f"**所属客户**\n\n{client['name'] if client else '无'}")

    if p.get("description"):
        st.info(p["description"])

    # 任务统计
    stats = detail.get("stats", {})
    st.divider()
    st.subheader("任务进度")
    col_a, col_b, col_c, col_d, col_e = st.columns(5)
    with col_a:
        st.metric("总数", stats.get("total_tasks", 0))
    with col_b:
        st.metric("已完成", stats.get("done", 0))
    with col_c:
        st.metric("进行中", stats.get("doing", 0))
    with col_d:
        st.metric("待办", stats.get("todo", 0))
    with col_e:
        progress = stats.get("progress", 0)
        st.metric("完成率", f"{progress:.0%}")

    if stats.get("total_tasks", 0) > 0:
        st.progress(stats["progress"],
                    text=f"进度 {stats['progress']:.0%}（{stats['done']}/{stats['total_tasks']}）")

    # 阶段可视化（详情视图）
    try:
        from services.workflow_engine import get_project_progress, advance_stage, skip_stage
        progress = get_project_progress(project_id)
        if progress["total_stages"] > 0:
            st.divider()
            st.subheader(f"📊 项目阶段 ({progress['completed_stages']}/{progress['total_stages']})")
            st.progress(
                progress["stage_completion_pct"] / 100,
                text=f"阶段进度 {progress['stage_completion_pct']:.0f}%"
            )

            cols = st.columns(min(len(progress["stage_breakdown"]), 5))
            for i, sb in enumerate(progress["stage_breakdown"]):
                with cols[i % 5]:
                    emoji = {"active": "🔵", "completed": "✅", "skipped": "⏭️", "pending": "⚪"}.get(sb["status"], "")
                    status_text = format_stage_status(sb["status"])
                    st.caption(f"{emoji} **{sb['stage_name']}**")
                    st.caption(f"_{status_text}_")
                    if sb["total_tasks"] > 0:
                        st.caption(f"{sb['done_tasks']}/{sb['total_tasks']} 任务")
                    elif sb["status"] == "active":
                        st.caption("无关联任务")

            # 阶段操作
            current = progress.get("active_stage")
            if current:
                col_adv, col_skip = st.columns(2)
                with col_adv:
                    if st.button(f"✅ 完成「{current['stage_name']}」", key=f"detail_adv_{project_id}"):
                        result = advance_stage(project_id, current["id"])
                        if result["success"]:
                            st.success("阶段已推进")
                        else:
                            st.error(result.get("error", "推进失败"))
                        st.rerun()
                with col_skip:
                    if st.button(f"⏭️ 跳过「{current['stage_name']}」", key=f"detail_skip_{project_id}"):
                        skip_stage(current["id"])
                        st.success("阶段已跳过")
                        st.rerun()
    except Exception:
        pass

    # 高优先级未完成任务
    high_tasks = detail.get("high_priority_tasks", [])
    if high_tasks:
        st.subheader("高优先级未完成任务")
        for t in high_tasks:
            p_label = format_task_priority(t.get("priority", ""))
            due = f" — 截止: {t['due_date']}" if t.get("due_date") else ""
            st.warning(f"{p_label} **{t['title']}**{due}")

    # 未完成任务
    uncompleted = detail.get("uncompleted_tasks", [])
    if uncompleted:
        st.subheader(f"未完成任务 ({len(uncompleted)})")
        data = [{"标题": t["title"],
                 "状态": format_task_status(t.get("status", "")),
                 "优先级": format_task_priority(t.get("priority", "")),
                 "截止日期": t.get("due_date") or "-"}
                for t in uncompleted]
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

    # 状态变更记录
    status_changes = detail.get("status_changes", [])
    if status_changes:
        st.subheader("任务状态变更")
        for sc in status_changes[:10]:
            label = format_event_type(sc.get("event_type", ""))
            date_str = sc.get("event_date", "")[:10] if sc.get("event_date") else ""
            st.write(f"- [{date_str}] {label}: {sc.get('title', '')}")
            if sc.get("description"):
                st.caption(f"  {sc['description']}")

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

    # ── 项目长期记忆 ──
    try:
        from services.memory_service import get_memory_by_project
        memories = get_memory_by_project(project_id, limit=20)
        if memories:
            st.divider()
            st.subheader(f"🧠 项目长期记忆 ({len(memories)})")
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

    # ── 项目风险 ──
    try:
        from services.relation_service import find_entity_risks
        risks = find_entity_risks("project", project_id)
        if risks:
            st.divider()
            st.subheader(f"🚨 项目风险关系 ({len(risks)})")
            for r in risks[:5]:
                st.warning(f"**{r.get('relation_type', '')}**: {r.get('description', '无详情')}")
    except Exception:
        pass

    # ── 下一步建议 ──
    try:
        from services.proactive_suggestion_service import generate_project_suggestions
        st.divider()
        st.subheader("💡 下一步建议")
        if st.button("生成建议", key=f"gen_project_suggestions_{project_id}"):
            with st.spinner("AI 分析中..."):
                s = generate_project_suggestions(project_id)
                if s.get("next_steps"):
                    st.markdown(s["next_steps"])
                if s.get("blocked_tasks"):
                    st.markdown("**阻塞任务**")
                    for t in s["blocked_tasks"][:5]:
                        st.warning(f"🚫 {t.get('title', '')}")
    except Exception:
        pass

    # AI 总结
    st.divider()
    if AI_API_KEY:
        if st.button("AI 生成项目总结", key=f"ai_summary_project_{project_id}"):
            with st.spinner("AI 分析中..."):
                summary = summarize_entity_detail("project", detail)
                st.markdown("### AI 总结")
                st.markdown(summary)
    else:
        st.caption("AI 未配置，设置 AI_API_KEY 后可使用 AI 总结")


def _render_network(network):
    clients = network.get("clients", [])
    tasks_from_net = network.get("tasks", [])
    files = network.get("files", [])
    events = network.get("events", [])

    has_relations = any([clients, tasks_from_net, files, events])
    if not has_relations:
        return

    st.divider()
    st.caption("关联数据")

    if clients:
        st.write("**关联客户**")
        for c_item in clients:
            st.write(f"- {c_item['name']}")

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
