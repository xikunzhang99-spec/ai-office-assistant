"""
Business Brain — 业务大脑预览页面。
输入自然语言内容，AI 分析后展示结构化结果，确认后交由 Workflow Agent 执行。
"""
import streamlit as st
from services.business_brain import analyze_input
from services.business_brain.brain_service import execute_actions
from services.business_brain.action_planner import ACTION_LABELS


EXAMPLES = [
    ("任务", "周五前完成AI办公助理的测试报告，优先级高，关联AI办公助理项目"),
    ("项目进展", "AI办公助理项目开发阶段已完成，今天开始进入测试阶段，预计下周三完成"),
    ("客户跟进", "今天跟张三公司的张总通了电话，他们对二期合作很感兴趣，下周发方案给他们"),
    ("会议纪要", "下午2点和开发团队开了周会，讨论了三个问题：1) 性能优化需要两周 2) 飞书集成下周上线 3) 需要招一个测试"),
    ("想法灵感", "想到一个好主意：在每日工作台加入AI主动提醒功能，根据逾期任务和客户跟进状态自动推送建议"),
    ("日常记录", "今天主要处理了三个事情：完成了API文档，修复了文件上传bug，跟李四讨论了新需求"),
]

CONTENT_TYPE_LABELS = {
    "task": "任务",
    "note": "笔记",
    "project_update": "项目进展",
    "client_update": "客户跟进",
    "meeting_note": "会议纪要",
    "file_summary": "文件摘要",
    "daily_record": "日常记录",
    "idea": "想法灵感",
    "unknown": "未知",
}

CONTENT_TYPE_COLORS = {
    "task": "orange",
    "note": "grey",
    "project_update": "blue",
    "client_update": "green",
    "meeting_note": "purple",
    "file_summary": "brown",
    "daily_record": "teal",
    "idea": "gold",
    "unknown": "red",
}


def render():
    st.title("业务大脑")

    st.markdown("输入自然语言内容，AI 将自动识别内容类型、提取关键信息、关联已有实体，并生成建议动作。")

    # Example buttons
    _render_examples()

    st.divider()

    # Input area
    col_input, col_btn = st.columns([5, 1])
    with col_input:
        user_input = st.text_area(
            "输入内容",
            placeholder="例如：周五前完成AI办公助理的测试报告，优先级高，关联AI办公助理项目",
            height=120,
            key="brain_input",
            label_visibility="collapsed",
        )
    with col_btn:
        st.write("")
        analyze_clicked = st.button("分析", type="primary", use_container_width=True, key="btn_analyze")

    # Handle example auto-submit
    if st.session_state.get("brain_auto_submit"):
        st.session_state["brain_auto_submit"] = False
        analyze_clicked = True

    if analyze_clicked and user_input.strip():
        _do_analysis(user_input.strip())
    elif analyze_clicked:
        st.warning("请输入内容")

    # Show results if available
    if "brain_result" in st.session_state:
        st.divider()
        _render_result(st.session_state["brain_result"])

    st.divider()
    st.caption("Business Brain V1 — 业务理解层，分析结果仅供确认，真正执行由 Workflow Agent 负责。")


def _render_examples():
    """Render example buttons for quick testing."""
    st.caption("快速示例：")
    cols = st.columns(3)
    for i, (label, text) in enumerate(EXAMPLES):
        with cols[i % 3]:
            if st.button(f"{label}", key=f"brain_example_{i}", use_container_width=True):
                st.session_state["brain_input"] = text
                st.session_state["brain_auto_submit"] = True
                st.rerun()


def _do_analysis(content: str):
    """Run business brain analysis and store result."""
    with st.spinner("AI 分析中..."):
        try:
            result = analyze_input(content)
            st.session_state["brain_result"] = result
            st.session_state["brain_show_modify"] = False
        except Exception as e:
            st.error(f"分析失败: {str(e)}")


def _render_result(result: dict):
    """Render the structured analysis result."""
    content_type = result.get("content_type", "unknown")
    confidence = result.get("confidence", 0)
    ct_label = CONTENT_TYPE_LABELS.get(content_type, content_type)
    ct_color = CONTENT_TYPE_COLORS.get(content_type, "grey")

    # Header
    col_type, col_conf, col_confirm = st.columns([2, 1, 1])
    with col_type:
        st.markdown(f"**内容类型**: :{ct_color}[{ct_label}]")
    with col_conf:
        st.metric("置信度", f"{confidence:.0%}")
    with col_confirm:
        need = result.get("need_human_confirmation", False)
        st.markdown(f"**需确认**: {'是' if need else '否'}")

    # Title & Summary
    if result.get("title"):
        st.markdown(f"**标题**: {result['title']}")
    if result.get("summary"):
        st.markdown(f"**摘要**: {result['summary']}")

    # Entities
    entities = result.get("entities", {})
    if any(entities.get(k) for k in ("clients", "projects", "people", "tasks", "deadlines", "dates")):
        with st.expander("提取的实体", expanded=True):
            _render_entities(entities)

    # Tags
    tags = result.get("tags", [])
    matched_tags = result.get("matched_tags", [])
    new_tags = result.get("new_tags", [])
    if tags or matched_tags or new_tags:
        with st.expander("标签", expanded=False):
            if matched_tags:
                st.markdown("**已有标签**: " + ", ".join([f"`{t}`" for t in matched_tags]))
            if new_tags:
                st.markdown("**新标签**: " + ", ".join([f"`{t}`" for t in new_tags]))
            if not matched_tags and not new_tags and tags:
                st.markdown("**标签**: " + ", ".join([f"`{t}`" for t in tags]))

    # Suggested Actions
    actions = result.get("suggested_actions", [])
    if actions:
        st.divider()
        st.subheader("建议动作")
        for i, action in enumerate(actions):
            _render_action_card(i, action)

    # Action buttons
    st.divider()
    _render_action_buttons(result)


def _render_entities(entities: dict):
    """Render extracted entities in a structured way."""
    clients = entities.get("clients", [])
    projects = entities.get("projects", [])
    people = entities.get("people", [])
    tasks = entities.get("tasks", [])
    deadlines = entities.get("deadlines", [])
    dates = entities.get("dates", [])

    if clients:
        st.caption("**客户**:")
        for c in clients:
            matched = " (已匹配)" if c.get("matched_id") else ""
            st.caption(f"  - {c.get('name', '')}{matched}")

    if projects:
        st.caption("**项目**:")
        for p in projects:
            matched = " (已匹配)" if p.get("matched_id") else ""
            st.caption(f"  - {p.get('name', '')}{matched}")

    if people:
        st.caption("**人物**:")
        for p in people:
            role = f" ({p.get('role', '')})" if p.get('role') else ""
            st.caption(f"  - {p.get('name', '')}{role}")

    if tasks:
        st.caption("**任务**:")
        for t in tasks:
            priority = t.get("priority", "")
            due = f" 截止: {t.get('due_date', '')}" if t.get("due_date") else ""
            st.caption(f"  - {t.get('title', '')} [{priority}]{due}")

    if deadlines:
        st.caption(f"**截止日期**: {', '.join(deadlines)}")

    if dates:
        st.caption(f"**相关日期**: {', '.join(dates)}")


def _render_action_card(index: int, action: dict):
    """Render a single suggested action card."""
    action_type = action.get("action_type", "ignore")
    label = ACTION_LABELS.get(action_type, action_type)
    confidence = action.get("confidence", 0.5)
    workflow_type = action.get("workflow_type")

    col_icon, col_info = st.columns([0.5, 5.5])
    with col_icon:
        icon_map = {
            "create_task": "📝", "create_note": "📄", "update_project": "📁",
            "update_client": "👤", "create_timeline": "📅", "create_summary": "📊",
            "send_reminder": "🔔", "ask_confirmation": "❓", "ignore": "⏭️",
        }
        st.markdown(f"### {icon_map.get(action_type, '📌')}")
    with col_info:
        st.markdown(f"**{label}** — {action.get('title', '')}")
        if action.get("description"):
            st.caption(action["description"])
        meta_parts = [f"优先级: {action.get('priority', 'medium')}"]
        if confidence:
            meta_parts.append(f"置信度: {confidence:.0%}")
        if workflow_type:
            meta_parts.append(f"工作流: `{workflow_type}`")
        if action.get("related_client_id"):
            meta_parts.append(f"客户ID: {action['related_client_id']}")
        if action.get("related_project_id"):
            meta_parts.append(f"项目ID: {action['related_project_id']}")
        st.caption(" | ".join(meta_parts))


def _render_action_buttons(result: dict):
    """Render confirm / modify / re-analyze / cancel buttons."""
    col1, col2, col3, col4 = st.columns([1.5, 1.5, 1, 1])

    with col1:
        if st.button("确认执行全部", type="primary", use_container_width=True, key="btn_confirm_execute"):
            _do_execute(result)

    with col2:
        if st.button("修改后执行", use_container_width=True, key="btn_modify_execute"):
            st.session_state["brain_show_modify"] = True
            st.rerun()

    with col3:
        if st.button("重新识别", use_container_width=True, key="btn_reanalyze"):
            if "brain_result" in st.session_state:
                del st.session_state["brain_result"]
            st.rerun()

    with col4:
        if st.button("取消", use_container_width=True, key="btn_cancel"):
            if "brain_result" in st.session_state:
                del st.session_state["brain_result"]
            st.rerun()

    # Modify mode: show editable JSON
    if st.session_state.get("brain_show_modify"):
        with st.expander("修改分析结果", expanded=True):
            import json
            editable = {
                "content_type": result.get("content_type"),
                "title": result.get("title"),
                "summary": result.get("summary"),
                "tags": result.get("tags", []),
                "suggested_actions": result.get("suggested_actions", []),
            }
            json_str = st.text_area(
                "编辑 JSON（修改后点击下方按钮执行）",
                value=json.dumps(editable, ensure_ascii=False, indent=2),
                height=300,
                key="brain_modify_json",
            )
            if st.button("按修改内容执行", type="primary", key="btn_modify_confirm"):
                try:
                    modified = json.loads(json_str)
                    result["title"] = modified.get("title", result.get("title"))
                    result["summary"] = modified.get("summary", result.get("summary"))
                    result["tags"] = modified.get("tags", result.get("tags", []))
                    result["suggested_actions"] = modified.get("suggested_actions", result.get("suggested_actions", []))
                    st.session_state["brain_show_modify"] = False
                    _do_execute(result)
                except json.JSONDecodeError as e:
                    st.error(f"JSON 格式错误: {str(e)}")


def _do_execute(result: dict):
    """Execute suggested actions via Workflow Agent."""
    actions = result.get("suggested_actions", [])
    if not actions:
        st.warning("没有可执行的动作")
        return

    executable = [a for a in actions if a.get("action_type") not in ("ignore", "ask_confirmation")]
    if not executable:
        st.info("所有动作均为忽略或确认类型，无需执行。")
        return

    with st.spinner(f"正在执行 {len(executable)} 个动作..."):
        exec_results = execute_actions(actions)

    st.divider()
    st.subheader("执行结果")

    success_count = sum(1 for r in exec_results if r.get("success"))
    fail_count = len(exec_results) - success_count

    if fail_count == 0:
        st.success(f"全部 {len(exec_results)} 个动作执行成功")
    else:
        st.warning(f"{success_count} 成功, {fail_count} 失败")

    for r in exec_results:
        icon = "✅" if r.get("success") else "❌"
        st.caption(f"{icon} {ACTION_LABELS.get(r['action_type'], r['action_type'])}: {r.get('message', '')}")

    # Clear result after execution
    if "brain_result" in st.session_state:
        del st.session_state["brain_result"]
