import streamlit as st
import os
import json
from datetime import datetime
from services.file_parser import parse_file
from services.ai_service import summarize_file
from services.markdown_service import generate_file_markdown
from services.obsidian_service import write_file_summary, is_configured
from services.timeline_service import add_event
from services.client_service import get_all_clients
from services.project_service import get_all_projects
from services.relation_service import add_relation
from services.file_service import save_file_record, get_all_files, delete_file, generate_task_suggestions_from_file
from services.search_service import search_files
from services.task_service import create_task
from config.settings import UPLOAD_DIR
from utils.date_utils import now_str
from utils.display_utils import format_file_type, EMPTY_MESSAGES


def render():
    st.title("文件上传与AI总结")

    tab1, tab2 = st.tabs(["上传文件", "文件列表"])

    with tab1:
        _render_upload()

    with tab2:
        _render_file_list()


def _render_upload():
    uploaded_file = st.file_uploader(
        "选择文件",
        type=["docx", "pptx", "xlsx", "xls", "pdf", "md", "txt", "csv"],
        key="file_uploader",
    )

    if not uploaded_file:
        return

    st.write(f"已选择: **{uploaded_file.name}** ({uploaded_file.size} bytes)")

    if st.button("解析并总结", type="primary", key="btn_analyze"):
        with st.spinner("正在处理..."):
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
            st.session_state["analysis_filename"] = filename
            st.session_state["analysis_file_ext"] = file_ext
            st.session_state["analysis_saved_path"] = saved_path
            st.session_state["analysis_result"] = result
            st.session_state["analysis_content"] = content
            st.rerun()

    if "analysis_result" not in st.session_state:
        return

    result = st.session_state["analysis_result"]
    filename = st.session_state["analysis_filename"]
    file_ext = st.session_state["analysis_file_ext"]
    saved_path = st.session_state["analysis_saved_path"]

    st.divider()
    st.info(f"文件已保存至: {saved_path}")

    content = st.session_state.get("analysis_content", "")
    if content:
        with st.expander("解析内容预览"):
            st.text(content[:1000] + ("..." if len(content) > 1000 else ""))

    st.subheader("AI 摘要")
    st.write(result.get("summary", ""))

    if result.get("key_points"):
        st.subheader("关键点")
        for pt in result["key_points"]:
            st.write(f"- {pt}")

    st.subheader("标签")
    default_tags = ", ".join(result.get("tags", []))
    tags = st.text_input("标签（可修改）", value=default_tags, key="file_tags_input")

    col_proj, col_client = st.columns(2)
    with col_proj:
        projects = get_all_projects()
        project_options = {"无": 0}
        for p in projects:
            project_options[p["name"]] = p["id"]
        selected_project_name = st.selectbox("关联项目（可选）", list(project_options.keys()), key="file_project")
        selected_project_id = project_options[selected_project_name]

    with col_client:
        clients = get_all_clients()
        client_options = {"无": 0}
        for c in clients:
            client_options[c["name"]] = c["id"]
        selected_client_name = st.selectbox("关联客户（可选）", list(client_options.keys()), key="file_client")
        selected_client_id = client_options[selected_client_name]

    if result.get("suggestions"):
        st.subheader("后续任务建议")
        for s in result["suggestions"]:
            st.write(f"- {s}")

    if st.button("确认保存", type="primary", key="btn_save"):
        file_id = save_file_record(
            filename=filename,
            file_path=saved_path,
            file_type=file_ext,
            summary=result.get("summary", ""),
            key_points=result.get("key_points", []),
            suggestions=result.get("suggestions", []),
            tags=tags,
            project_id=selected_project_id or None,
            client_id=selected_client_id or None,
        )
        add_event("file_uploaded", f"上传文件: {filename}", "", "file", file_id,
                  project_id=selected_project_id or None,
                  client_id=selected_client_id or None)
        if selected_project_id:
            add_relation("file", file_id, "project", selected_project_id, "belongs_to",
                         f"文件「{filename}」属于该项目")
        if selected_client_id:
            add_relation("file", file_id, "client", selected_client_id, "belongs_to",
                         f"文件「{filename}」属于该客户")

        md_content = generate_file_markdown(
            filename, file_ext, now_str(), tags,
            result.get("summary", ""),
            result.get("key_points", []),
            result.get("suggestions", []),
        )
        add_event("file_markdown_created", f"生成Markdown: {filename}", "", "file", file_id)

        if is_configured():
            md_path = write_file_summary(filename, md_content)
            add_event("file_summarized", f"AI总结文件: {filename}", "", "file", file_id)
            add_event("file_written_to_obsidian", f"Markdown写入Obsidian: {filename}",
                      md_path, "file", file_id)
            st.success(f"已写入 Obsidian: {md_path}")
        else:
            st.warning("Obsidian 未配置，跳过写入")

        st.success("文件处理完成！")
        st.markdown(md_content)

        # 提取长期记忆
        try:
            from services.memory_service import auto_extract_and_save
            summary = result.get("summary", "")
            key_points = result.get("key_points", [])
            memory_text = f"文件: {filename}\n摘要: {summary}\n关键点: {', '.join(key_points) if key_points else ''}\n标签: {tags}"
            auto_extract_and_save(
                memory_text, source_type="file", source_id=file_id,
                project_id=selected_project_id or None,
                client_id=selected_client_id or None,
            )
        except Exception:
            pass

        # AI 任务建议
        st.divider()
        st.subheader("AI 任务建议")
        _render_task_suggestions(file_id)

        st.session_state.pop("analysis_result", None)
        st.session_state.pop("analysis_filename", None)
        st.session_state.pop("analysis_file_ext", None)
        st.session_state.pop("analysis_saved_path", None)
        st.session_state.pop("analysis_content", None)


def _render_file_list():
    keyword = st.text_input("搜索文件", placeholder="按文件名、摘要或标签搜索...", key="file_search")
    col_type, _ = st.columns([1, 3])
    with col_type:
        file_type_filter = st.selectbox(
            "文件类型", ["全部", ".docx", ".pdf", ".md", ".txt", ".xlsx", ".xls", ".csv", ".pptx"],
            format_func=lambda x: format_file_type(x) if x != "全部" else "全部",
            key="file_type_filter",
        )

    if keyword or file_type_filter != "全部":
        files = search_files(keyword=keyword or None)
        if file_type_filter != "全部":
            files = [f for f in files if f.get("file_type", "") == file_type_filter]
    else:
        files = get_all_files()

    if not files:
        st.info(EMPTY_MESSAGES["files"])
        return

    st.write(f"共 {len(files)} 个文件")

    for f_item in files:
        ftype = f_item.get("file_type", "")
        ftype_cn = format_file_type(ftype)
        title = f"[{ftype_cn}] {f_item['filename']}"
        if f_item.get("tags"):
            title += f"  [{f_item['tags']}]"

        with st.expander(title, expanded=False):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**类型**：{ftype_cn}")
                st.write(f"**上传时间**：{f_item['created_at']}")

                st.divider()
                st.subheader("AI 摘要")
                st.write(f_item.get("summary") or "无摘要")

            with col2:
                if f_item.get("file_path") and os.path.exists(f_item["file_path"]):
                    st.caption(f"原始文件: {os.path.basename(f_item['file_path'])}")
                else:
                    st.caption("原始文件已删除")
                if st.button("删除", key=f"del_file_{f_item['id']}", type="secondary"):
                    delete_file(f_item["id"])
                    st.success(f"已删除文件: {f_item['filename']}")
                    st.rerun()

            if f_item.get("key_points"):
                try:
                    key_points = json.loads(f_item["key_points"])
                    if key_points:
                        st.divider()
                        st.subheader("关键点")
                        for pt in key_points:
                            st.write(f"- {pt}")
                except Exception:
                    pass

            if f_item.get("suggestions"):
                try:
                    suggestions = json.loads(f_item["suggestions"])
                    if suggestions:
                        st.divider()
                        st.subheader("后续任务建议")
                        for s in suggestions:
                            st.write(f"- {s}")
                except Exception:
                    pass

            # ── 文档动作分析 ──
            st.divider()
            _render_document_actions(f_item)


def _render_task_suggestions(file_id: int):
    """根据文件内容生成并显示 AI 任务建议。"""
    from config.settings import AI_API_KEY

    if not AI_API_KEY:
        st.caption("AI 未配置，跳过任务建议生成")
        return

    with st.spinner("AI 正在生成任务建议..."):
        try:
            suggestions = generate_task_suggestions_from_file(file_id)
        except Exception:
            st.caption("任务建议生成失败")
            return

    if not suggestions:
        st.caption("根据文件内容，暂无需要跟进的任务建议")
        return

    st.caption(f"根据该文件，AI 建议创建以下 {len(suggestions)} 个任务：")
    for i, s in enumerate(suggestions):
        title = s.get("title", "未命名任务")
        desc = s.get("description", "")
        priority = s.get("priority", "medium")
        due_date = s.get("due_date") or ""
        proj_id = s.get("related_project_id")
        client_id = s.get("related_client_id")

        priority_label = {"high": "高", "medium": "中", "low": "低"}.get(priority, priority)

        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"{i+1}. **{title}** [{priority_label}优先级]")
            if desc:
                st.caption(desc)
            if due_date:
                st.caption(f"建议截止: {due_date}")
        with col2:
            btn_key = f"create_task_btn_{file_id}_{i}"
            if st.button("创建任务", key=btn_key, use_container_width=True):
                task_id = create_task(
                    title=title,
                    description=desc,
                    priority=priority,
                    due_date=due_date,
                    project_id=proj_id,
                    client_id=client_id,
                )
                st.success(f"任务「{title}」已创建")
                # 记录工作流日志
                try:
                    from services.workflow_log_service import add_workflow_log
                    add_workflow_log("task_created_from_file", "task", task_id, "success",
                                     f"从文件分析建议创建任务: {title}", "")
                except Exception:
                    pass


def _render_document_actions(f_item: dict):
    """在文件详情中展示「分析可执行动作」按钮和结果。"""
    from config.settings import AI_API_KEY

    if not AI_API_KEY:
        st.caption("AI 未配置，无法分析文档动作")
        return

    file_id = f_item["id"]
    cache_key = f"doc_action_{file_id}"

    # 初始化或加载缓存
    if cache_key not in st.session_state:
        st.session_state[cache_key] = None

    col_btn, _ = st.columns([1, 3])
    with col_btn:
        if st.button("🔍 分析可执行动作", key=f"doc_action_btn_{file_id}"):
            with st.spinner("AI 正在分析文档..."):
                try:
                    from services.document_action_service import analyze_document_actions
                    result = analyze_document_actions(file_id)
                    st.session_state[cache_key] = result
                except Exception as e:
                    st.error(f"分析失败: {str(e)[:200]}")
                    st.session_state[cache_key] = None

    analysis = st.session_state.get(cache_key)
    if not analysis:
        return

    # 显示分析结果
    doc_summary = analysis.get("document_summary", "")
    sections = analysis.get("sections", [])
    suggested_actions = analysis.get("suggested_actions", [])

    if doc_summary:
        st.caption("📝 文档摘要")
        st.info(doc_summary[:300])

    if sections:
        with st.expander(f"📄 文档分段（{len(sections)} 段）", expanded=False):
            for s in sections:
                st.markdown(f"**第{s['section_id']}部分: {s.get('title', '')}**")
                st.caption(s.get("content", "")[:300])
                if len(s.get("content", "")) > 300:
                    st.caption("...")

    if suggested_actions:
        st.caption(f"📋 建议动作（{len(suggested_actions)} 条）")
        type_emoji = {"create_project": "🆕", "create_task": "📝", "create_client": "👤",
                      "risk_alert": "⚠️", "create_timeline_event": "📅",
                      "link_relation": "🔗"}
        type_labels = {"create_project": "创建项目", "create_task": "创建任务",
                       "create_client": "创建客户", "risk_alert": "风险提醒",
                       "create_timeline_event": "写入时间轴",
                       "link_relation": "建立关联"}

        for i, a in enumerate(suggested_actions):
            a_type = a.get("action_type", "")
            emoji = type_emoji.get(a_type, "📌")
            label = type_labels.get(a_type, a_type)
            conf = a.get("confidence", 0)
            conf_str = f" {int(conf * 100)}%" if conf else ""

            col_info, col_exec = st.columns([4, 1])
            with col_info:
                st.markdown(f"{i+1}. {emoji} **{label}**：{a.get('title', '')}`{conf_str}`")
                if a.get("description"):
                    st.caption(a["description"][:150])
            with col_exec:
                exec_key = f"doc_exec_{file_id}_{i}"
                if st.button("执行", key=exec_key, use_container_width=True):
                    from services.action_executor_service import execute_action
                    action = {
                        "action_type": a_type,
                        "title": a.get("title", ""),
                        "description": a.get("description", ""),
                        "project_name": a.get("project_name"),
                        "client_name": a.get("client_name"),
                        "priority": a.get("priority", "medium"),
                        "due_date": a.get("due_date"),
                        "confidence": a.get("confidence", 0.7),
                    }
                    result = execute_action(action)
                    if result["success"]:
                        st.success(result["message"])
                    else:
                        st.error(result["message"])
    else:
        st.caption("未识别到可执行动作建议")
