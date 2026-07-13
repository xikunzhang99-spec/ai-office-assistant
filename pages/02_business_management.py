import streamlit as st
import pandas as pd
from datetime import date

from services.task_service import (
    create_task, search_tasks, update_task, delete_task, get_all_tasks,
    mark_task_on_calendar, unmark_task_from_calendar,
    add_task_note, get_task_notes,
)
from services.project_service import (
    create_project, get_all_projects, update_project, delete_project,
)
from services.client_service import (
    create_client, get_all_clients, update_client, delete_client,
)
from services.timeline_service import add_event, search_events
from services.relation_service import (
    get_relation_network, get_entity_graph,
    find_risk_relations, find_follow_up_relations,
    RELATION_TYPE_LABELS,
)
from utils.display_utils import (
    status_badge, priority_badge,
    format_task_status, format_task_priority, format_project_status,
    format_event_type, format_file_type,
    EMPTY_MESSAGES,
)
from utils.date_utils import today_str, now_str


def render():
    st.title("业务管理")

    tabs = st.tabs(["任务管理", "项目管理", "客户管理", "关系查看"])

    with tabs[0]:
        _render_tasks()

    with tabs[1]:
        _render_projects()

    with tabs[2]:
        _render_clients()

    with tabs[3]:
        _render_relations()


# ═══════════════════════════════════════════════════════════════════════
# Tab 1: 任务管理
# ═══════════════════════════════════════════════════════════════════════

def _render_tasks():
    st.subheader("任务管理")

    # 创建任务表单
    with st.expander("+ 新建任务", expanded=False):
        _render_task_form()

    # 筛选器
    projects = get_all_projects()
    clients = get_all_clients()

    col_s, col_p, col_pr, col_c = st.columns(4)
    with col_s:
        status = st.selectbox("状态", ["全部", "todo", "doing", "done", "cancelled"],
                              format_func=lambda x: "全部" if x == "全部" else format_task_status(x),
                              key="bm_task_status")
    with col_p:
        priority = st.selectbox("优先级", ["全部", "high", "medium", "low"],
                                format_func=lambda x: "全部" if x == "全部" else format_task_priority(x),
                                key="bm_task_priority")
    with col_pr:
        proj_names = ["全部"] + [p["name"] for p in projects]
        sel_proj = st.selectbox("项目", proj_names, key="bm_task_project")
    with col_c:
        cli_names = ["全部"] + [c["name"] for c in clients]
        sel_cli = st.selectbox("客户", cli_names, key="bm_task_client")

    # 解析筛选参数
    s_val = status if status != "全部" else None
    p_val = priority if priority != "全部" else None
    pr_id = None
    if sel_proj != "全部":
        for p in projects:
            if p["name"] == sel_proj:
                pr_id = p["id"]
                break
    c_id = None
    if sel_cli != "全部":
        for cl in clients:
            if cl["name"] == sel_cli:
                c_id = cl["id"]
                break

    tasks = search_tasks(status=s_val, priority=p_val, project_id=pr_id, client_id=c_id)

    if not tasks:
        st.info(EMPTY_MESSAGES["tasks"])
        return

    st.write(f"共 {len(tasks)} 个任务")

    # 任务列表
    for task in tasks:
        s_badge = status_badge(task["status"])
        p_badge = priority_badge(task["priority"])

        with st.expander(f"{s_badge} {p_badge} {task['title']}", expanded=False):
            col1, col2 = st.columns([3, 1])

            with col1:
                if task.get("description"):
                    st.info(task["description"])
                st.caption(f"标签: {task.get('tags') or '无'}")
                st.caption(f"截止: {task.get('due_date') or '无'}")
                st.caption(f"创建: {(task.get('created_at') or '')[:10]}")

                # 关联信息
                meta = []
                if task.get("project_id"):
                    proj = next((p for p in projects if p["id"] == task["project_id"]), None)
                    if proj:
                        meta.append(f"项目: {proj['name']}")
                if task.get("client_id"):
                    cli = next((c for c in clients if c["id"] == task["client_id"]), None)
                    if cli:
                        meta.append(f"客户: {cli['name']}")
                if meta:
                    st.caption(" | ".join(meta))

            with col2:
                # 状态变更
                new_status = st.selectbox("状态", ["todo", "doing", "done", "cancelled"],
                                          index=["todo", "doing", "done", "cancelled"].index(task["status"]),
                                          format_func=format_task_status,
                                          key=f"bm_ts_{task['id']}")
                if new_status != task["status"]:
                    update_task(task["id"], status=new_status)
                    st.rerun()

                # 优先级变更
                new_pri = st.selectbox("优先级", ["high", "medium", "low"],
                                       index=["high", "medium", "low"].index(task["priority"]),
                                       format_func=format_task_priority,
                                       key=f"bm_tp_{task['id']}")
                if new_pri != task["priority"]:
                    update_task(task["id"], priority=new_pri)
                    st.rerun()

                # 关联项目
                proj_opts = {"无": None}
                for p in projects:
                    proj_opts[p["name"]] = p["id"]
                cur_proj_name = "无"
                for name, pid_v in proj_opts.items():
                    if pid_v == task.get("project_id"):
                        cur_proj_name = name
                        break
                new_proj_name = st.selectbox("关联项目", list(proj_opts.keys()),
                                             index=list(proj_opts.keys()).index(cur_proj_name),
                                             key=f"bm_tproj_{task['id']}")
                if proj_opts[new_proj_name] != task.get("project_id"):
                    update_task(task["id"], project_id=proj_opts[new_proj_name])
                    st.rerun()

                # 关联客户
                cli_opts = {"无": None}
                for c in clients:
                    cli_opts[c["name"]] = c["id"]
                cur_cli_name = "无"
                for name, cid_v in cli_opts.items():
                    if cid_v == task.get("client_id"):
                        cur_cli_name = name
                        break
                new_cli_name = st.selectbox("关联客户", list(cli_opts.keys()),
                                            index=list(cli_opts.keys()).index(cur_cli_name),
                                            key=f"bm_tcli_{task['id']}")
                if cli_opts[new_cli_name] != task.get("client_id"):
                    update_task(task["id"], client_id=cli_opts[new_cli_name])
                    st.rerun()

                if st.button("删除", key=f"bm_del_task_{task['id']}", type="secondary"):
                    delete_task(task["id"])
                    st.success("已删除")
                    st.rerun()

                # 日历标记
                st.divider()
                on_cal = task.get("show_on_calendar") == 1
                if on_cal:
                    st.caption(f"日历日: {task.get('calendar_date') or task.get('due_date')}")
                    if st.button("取消标记", key=f"bm_cal_unmark_{task['id']}"):
                        unmark_task_from_calendar(task["id"])
                        st.rerun()
                else:
                    cal_date = st.date_input("日历日期", value=None, key=f"bm_cal_date_{task['id']}")
                    if st.button("标记到日历", key=f"bm_cal_mark_{task['id']}"):
                        mark_task_on_calendar(task["id"], cal_date.isoformat() if cal_date else None)
                        st.success("已标记")
                        st.rerun()

                # 备注
                st.divider()
                notes = get_task_notes(task["id"])
                st.caption(f"备注 ({len(notes)})")

                for note in notes:
                    note_date = (note.get("created_at") or "")[:16]
                    st.info(f"{note['content']}\n\n*{note_date}*")

                with st.form(f"bm_note_form_{task['id']}", clear_on_submit=True):
                    note_content = st.text_area("添加备注", key=f"bm_note_input_{task['id']}",
                                               placeholder="输入后期的想法或备注...")
                    if st.form_submit_button("添加备注", type="primary"):
                        if note_content.strip():
                            add_task_note(task["id"], note_content.strip())
                            st.success("备注已添加")
                            st.rerun()


def _render_task_form():
    projects = get_all_projects()
    clients = get_all_clients()

    with st.form("bm_new_task_form", clear_on_submit=True):
        title = st.text_input("任务标题 *")
        description = st.text_area("描述")
        priority = st.selectbox("优先级", ["medium", "high", "low"],
                                format_func=format_task_priority)
        due_date = st.date_input("截止日期", value=None)

        col_p, col_c = st.columns(2)
        with col_p:
            proj_opts = {"无": None}
            for p in projects:
                proj_opts[p["name"]] = p["id"]
            sel_p = st.selectbox("关联项目", list(proj_opts.keys()))
        with col_c:
            cli_opts = {"无": None}
            for c in clients:
                cli_opts[c["name"]] = c["id"]
            sel_c = st.selectbox("关联客户", list(cli_opts.keys()))

        submitted = st.form_submit_button("创建任务", type="primary")
        if submitted and title.strip():
            due_str = due_date.isoformat() if due_date else ""
            create_task(
                title=title.strip(),
                description=description.strip(),
                priority=priority,
                due_date=due_str,
                project_id=proj_opts[sel_p],
                client_id=cli_opts[sel_c],
            )
            st.success(f"任务「{title}」已创建")
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# Tab 2: 项目管理
# ═══════════════════════════════════════════════════════════════════════

def _render_projects():
    st.subheader("项目管理")

    clients = get_all_clients()
    client_map = {c["id"]: c for c in clients}

    # 创建项目
    with st.expander("+ 新建项目", expanded=False):
        with st.form("bm_new_project_form", clear_on_submit=True):
            name = st.text_input("项目名称 *")
            desc = st.text_area("描述")
            cli_opts = {"无": None}
            for c in clients:
                cli_opts[c["name"]] = c["id"]
            sel_c = st.selectbox("关联客户", list(cli_opts.keys()))
            submitted = st.form_submit_button("创建项目", type="primary")
            if submitted and name.strip():
                pid = create_project(name.strip(), desc.strip(), client_id=cli_opts[sel_c])
                try:
                    from services.workflow_engine import init_project_stages
                    init_project_stages(pid)
                except Exception:
                    pass
                st.success(f"项目「{name}」已创建")
                st.rerun()

    projects = get_all_projects()
    if not projects:
        st.info(EMPTY_MESSAGES["projects"])
        return

    st.write(f"共 {len(projects)} 个项目")

    for p in projects:
        s_label = format_project_status(p["status"])
        c_name = client_map[p["client_id"]]["name"] if p.get("client_id") and p["client_id"] in client_map else ""
        title = f"[{c_name}] {p['name']}" if c_name else p["name"]

        with st.expander(f"{title} [{s_label}]", expanded=False):
            col_a, col_b = st.columns([3, 1])

            with col_a:
                st.write(f"**描述**: {p.get('description') or '无'}")
                st.write(f"**创建**: {(p.get('created_at') or '')[:10]}")
                st.write(f"**更新**: {(p.get('updated_at') or '')[:10]}")

                # 关联任务统计
                tasks = search_tasks(project_id=p["id"])
                done = sum(1 for t in tasks if t["status"] == "done")
                total = len(tasks)
                if total > 0:
                    st.progress(done / total, text=f"任务进度 {done}/{total} ({done/total*100:.0f}%)")

            with col_b:
                if st.button("编辑", key=f"bm_edit_proj_{p['id']}"):
                    st.session_state[f"bm_editing_proj_{p['id']}"] = True
                if st.button("删除", key=f"bm_del_proj_{p['id']}", type="secondary"):
                    delete_project(p["id"])
                    st.success(f"已删除项目: {p['name']}")
                    st.rerun()

            # 编辑模式
            if st.session_state.get(f"bm_editing_proj_{p['id']}"):
                st.divider()
                st.caption("编辑项目")
                new_name = st.text_input("名称", value=p["name"], key=f"bm_epn_{p['id']}")
                new_desc = st.text_area("描述", value=p.get("description") or "", key=f"bm_epd_{p['id']}")
                new_status = st.selectbox("状态", ["active", "archived", "completed"],
                                          index=["active", "archived", "completed"].index(p["status"]) if p["status"] in ["active", "archived", "completed"] else 0,
                                          format_func=format_project_status, key=f"bm_eps_{p['id']}")
                cli_opts2 = {"无": None}
                for c in clients:
                    cli_opts2[c["name"]] = c["id"]
                cur_cname = "无"
                for name, cid_v in cli_opts2.items():
                    if cid_v == p.get("client_id"):
                        cur_cname = name
                        break
                new_cname = st.selectbox("客户", list(cli_opts2.keys()),
                                         index=list(cli_opts2.keys()).index(cur_cname),
                                         key=f"bm_epc_{p['id']}")
                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("保存", key=f"bm_save_proj_{p['id']}"):
                        update_project(p["id"], name=new_name, description=new_desc,
                                       status=new_status, client_id=cli_opts2[new_cname])
                        st.session_state[f"bm_editing_proj_{p['id']}"] = False
                        st.success("已更新")
                        st.rerun()
                with col_cancel:
                    if st.button("取消", key=f"bm_cancel_proj_{p['id']}"):
                        st.session_state[f"bm_editing_proj_{p['id']}"] = False
                        st.rerun()

            # 关联任务列表
            if tasks:
                st.divider()
                st.caption(f"关联任务 ({total})")
                for t in tasks:
                    s_b = format_task_status(t["status"])
                    p_b = format_task_priority(t["priority"])
                    done_m = "~~" if t["status"] == "done" else ""
                    st.write(f"- [{p_b}] [{s_b}] {done_m}{t['title']}{done_m}")
                    if t.get("due_date"):
                        st.caption(f"  截止: {t['due_date']}")

            # 阶段进度
            try:
                from services.workflow_engine import get_project_progress, advance_stage, skip_stage, init_project_stages
                progress = get_project_progress(p["id"])
                if progress["total_stages"] > 0:
                    st.divider()
                    st.caption(f"阶段进度 ({progress['completed_stages']}/{progress['total_stages']})")
                    stage_data = []
                    for sb in progress["stage_breakdown"]:
                        emoji = {"active": "🔵", "completed": "✅", "skipped": "⏭️", "pending": "⚪"}.get(sb["status"], "")
                        stage_data.append(f"{emoji}{sb['stage_name']}")
                    st.caption(" → ".join(stage_data))

                    current = progress.get("active_stage")
                    if current:
                        col_adv, col_skip = st.columns(2)
                        with col_adv:
                            if st.button(f"完成「{current['stage_name']}」", key=f"bm_adv_{p['id']}"):
                                advance_stage(p["id"], current["id"])
                                st.success("已推进")
                                st.rerun()
                        with col_skip:
                            if st.button(f"跳过「{current['stage_name']}」", key=f"bm_skip_{p['id']}"):
                                skip_stage(current["id"])
                                st.success("已跳过")
                                st.rerun()
                else:
                    if st.button("初始化阶段", key=f"bm_init_stages_{p['id']}"):
                        init_project_stages(p["id"])
                        st.success("阶段已初始化")
                        st.rerun()
            except Exception:
                pass

            # 关系网络
            network = get_relation_network("project", p["id"])
            clients_from_net = network.get("clients", [])
            files_from_net = network.get("files", [])
            events_from_net = network.get("events", [])
            has_rel = any([clients_from_net, files_from_net, events_from_net])
            if has_rel:
                st.divider()
                st.caption("关联数据")
                if clients_from_net:
                    for cl in clients_from_net:
                        st.write(f"- 客户: {cl['name']}")
                if files_from_net:
                    for f in files_from_net:
                        st.write(f"- 文件: {f['filename']}")
                if events_from_net:
                    for e in events_from_net[:5]:
                        st.write(f"- {format_event_type(e.get('event_type', ''))}: {e.get('title', '')}")


# ═══════════════════════════════════════════════════════════════════════
# Tab 3: 客户管理
# ═══════════════════════════════════════════════════════════════════════

def _render_clients():
    st.subheader("客户管理")

    # 创建客户
    with st.expander("+ 新建客户", expanded=False):
        with st.form("bm_new_client_form", clear_on_submit=True):
            name = st.text_input("客户名称 *")
            desc = st.text_area("描述")
            contact = st.text_input("联系方式")
            submitted = st.form_submit_button("创建客户", type="primary")
            if submitted and name.strip():
                create_client(name.strip(), desc.strip(), contact.strip())
                st.success(f"客户「{name}」已创建")
                st.rerun()

    clients = get_all_clients()
    if not clients:
        st.info(EMPTY_MESSAGES["clients"])
        return

    projects = get_all_projects()
    st.write(f"共 {len(clients)} 个客户")

    for c in clients:
        # 统计关联项目
        c_projects = [p for p in projects if p.get("client_id") == c["id"]]
        active_count = sum(1 for p in c_projects if p["status"] == "active")
        title = c["name"]
        if c_projects:
            title += f" [{len(c_projects)}个项目, {active_count}活跃]"

        with st.expander(title, expanded=False):
            col1, col2 = st.columns([3, 1])

            with col1:
                st.write(f"**描述**: {c.get('description') or '无'}")
                st.write(f"**联系方式**: {c.get('contact_info') or '无'}")
                st.write(f"**创建**: {(c.get('created_at') or '')[:10]}")

                if c_projects:
                    st.write("**关联项目**")
                    for p in c_projects:
                        s = format_project_status(p["status"])
                        st.write(f"- {p['name']} [{s}]")

            with col2:
                if st.button("编辑", key=f"bm_edit_client_{c['id']}"):
                    st.session_state[f"bm_editing_client_{c['id']}"] = True
                if st.button("删除", key=f"bm_del_client_{c['id']}", type="secondary"):
                    delete_client(c["id"])
                    st.success(f"已删除客户: {c['name']}")
                    st.rerun()

            # 编辑模式
            if st.session_state.get(f"bm_editing_client_{c['id']}"):
                st.divider()
                st.caption("编辑客户")
                new_name = st.text_input("名称", value=c["name"], key=f"bm_ecn_{c['id']}")
                new_desc = st.text_area("描述", value=c.get("description") or "", key=f"bm_ecd_{c['id']}")
                new_contact = st.text_input("联系方式", value=c.get("contact_info") or "", key=f"bm_ecc_{c['id']}")
                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("保存", key=f"bm_save_client_{c['id']}"):
                        update_client(c["id"], name=new_name, description=new_desc, contact_info=new_contact)
                        st.session_state[f"bm_editing_client_{c['id']}"] = False
                        st.success("已更新")
                        st.rerun()
                with col_cancel:
                    if st.button("取消", key=f"bm_cancel_client_{c['id']}"):
                        st.session_state[f"bm_editing_client_{c['id']}"] = False
                        st.rerun()

            # 关系网络
            network = get_relation_network("client", c["id"])
            tasks_from_net = network.get("tasks", [])
            files_from_net = network.get("files", [])
            events_from_net = network.get("events", [])
            has_rel = any([tasks_from_net, files_from_net, events_from_net])
            if has_rel:
                st.divider()
                st.caption("关联数据")
                if tasks_from_net:
                    for t in tasks_from_net:
                        s = format_task_status(t["status"])
                        st.write(f"- 任务 [{s}]: {t['title']}")
                if files_from_net:
                    for f in files_from_net:
                        st.write(f"- 文件: {f['filename']}")
                if events_from_net:
                    for e in events_from_net[:5]:
                        st.write(f"- {format_event_type(e.get('event_type', ''))}: {e.get('title', '')}")


# ═══════════════════════════════════════════════════════════════════════
# Tab 4: 关系查看
# ═══════════════════════════════════════════════════════════════════════

def _render_relations():
    st.subheader("关系查看")

    # 选择查看维度
    view_type = st.radio("查看维度", ["按客户", "按项目", "全局风险/跟进"], horizontal=True)

    if view_type == "按客户":
        _render_relations_by_client()
    elif view_type == "按项目":
        _render_relations_by_project()
    else:
        _render_global_relations()


def _render_relations_by_client():
    clients = get_all_clients()
    if not clients:
        st.info("暂无客户")
        return

    sel_client = st.selectbox("选择客户", [c["name"] for c in clients], key="rel_client")
    client = next((c for c in clients if c["name"] == sel_client), None)
    if not client:
        return

    graph = get_entity_graph("client", client["id"])

    st.write(f"**{client['name']}** 的关系网络")

    # 节点
    nodes = graph.get("nodes", [])
    if nodes:
        st.caption(f"关联节点 ({len(nodes)})")
        for n in nodes:
            type_cn = {"client": "客户", "project": "项目", "task": "任务", "file": "文件", "event": "事件"}.get(n["type"], n["type"])
            st.write(f"- [{type_cn}] {n['name']}")

    # 边
    edges = graph.get("edges", [])
    if edges:
        st.caption(f"关系 ({len(edges)})")
        for e in edges:
            label = RELATION_TYPE_LABELS.get(e["relation_type"], e["relation_type"])
            st.write(f"- {label}: {e.get('description', '')}")

    if not nodes and not edges:
        st.info("暂无关系数据")


def _render_relations_by_project():
    projects = get_all_projects()
    if not projects:
        st.info("暂无项目")
        return

    sel_project = st.selectbox("选择项目", [p["name"] for p in projects], key="rel_project")
    project = next((p for p in projects if p["name"] == sel_project), None)
    if not project:
        return

    graph = get_entity_graph("project", project["id"])

    st.write(f"**{project['name']}** 的关系网络")

    nodes = graph.get("nodes", [])
    if nodes:
        st.caption(f"关联节点 ({len(nodes)})")
        for n in nodes:
            type_cn = {"client": "客户", "project": "项目", "task": "任务", "file": "文件", "event": "事件"}.get(n["type"], n["type"])
            st.write(f"- [{type_cn}] {n['name']}")

    edges = graph.get("edges", [])
    if edges:
        st.caption(f"关系 ({len(edges)})")
        for e in edges:
            label = RELATION_TYPE_LABELS.get(e["relation_type"], e["relation_type"])
            st.write(f"- {label}: {e.get('description', '')}")

    if not nodes and not edges:
        st.info("暂无关系数据")


def _render_global_relations():
    col_risk, col_follow = st.columns(2)

    with col_risk:
        st.caption("风险关系")
        risks = find_risk_relations()
        if risks:
            for r in risks[:15]:
                st.warning(f"**{r.get('entity_name', '')}**: {r.get('description', '无详情')}")
        else:
            st.info("暂无风险关系")

    with col_follow:
        st.caption("跟进关系")
        follows = find_follow_up_relations()
        if follows:
            for f in follows[:15]:
                st.info(f"**{f.get('entity_name', '')}**: {f.get('description', '无详情')}")
        else:
            st.info("暂无跟进关系")


render()
