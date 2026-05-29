import streamlit as st
from services.rag_service import answer_with_rag, answer_with_hybrid_rag, answer_with_semantic_rag
from services.knowledge_service import rebuild_knowledge_items, get_knowledge_stats

EXAMPLES = [
    "今天做了什么？",
    "本周完成了哪些任务？",
    "有哪些高优先级任务？",
    "最近有什么文件上传？",
    "客户相关的最新动态",
    "项目有哪些？",
]

TYPE_LABELS_CN = {
    "client": "客户",
    "project": "项目",
    "task": "任务",
    "file": "文件",
    "event": "事件",
}

MODE_OPTIONS = {
    "keyword": "关键词搜索",
    "semantic": "语义搜索",
    "hybrid": "混合搜索",
}


def render():
    st.title("AI 问答")

    st.markdown(
        "用自然语言查询你的工作数据，AI 会基于统一知识库检索相关内容并生成回答。"
        "例如：*\"有哪些未完成任务？\"*、*\"项目A这周做了什么？\"*"
    )

    _render_examples()

    st.divider()

    col1, col2 = st.columns([5, 1])
    with col1:
        question = st.text_area(
            "输入问题",
            placeholder="例如：本周完成了哪些任务？有哪些高优先级待办？项目A最近有什么进展？",
            key="ai_query_input",
            label_visibility="collapsed",
        )
    with col2:
        st.write("")
        search_clicked = st.button("查询", key="ai_query_btn", use_container_width=True)

    st.session_state.setdefault("ai_query_mode", "hybrid")
    mode = st.radio(
        "搜索模式",
        options=list(MODE_OPTIONS.keys()),
        format_func=lambda m: MODE_OPTIONS[m],
        horizontal=True,
        key="ai_query_mode",
    )

    if st.session_state.get("ai_query_auto_submit") and st.session_state.get("ai_query_input", "").strip():
        st.session_state["ai_query_auto_submit"] = False
        _do_query(st.session_state["ai_query_input"].strip(), mode)

    if search_clicked and question.strip():
        _do_query(question.strip(), mode)
    elif search_clicked and not question.strip():
        st.warning("请输入问题")

    st.divider()
    _render_kb_maintenance()


def _render_examples():
    st.caption("试试这些问题（点击自动查询）：")
    cols = st.columns(len(EXAMPLES))
    for i, example in enumerate(EXAMPLES):
        with cols[i]:
            if st.button(example, key=f"ex_{i}", use_container_width=True):
                st.session_state["ai_query_input"] = example
                st.session_state["ai_query_auto_submit"] = True
                st.rerun()


def _do_query(question: str, mode: str = "keyword"):
    from config.settings import AI_API_KEY

    if not AI_API_KEY:
        st.error("AI 未配置，请在 .env 中设置 AI_API_KEY")
        return

    # 语义/混合模式：检查 embedding 是否可用
    if mode in ("semantic", "hybrid"):
        try:
            from services.embedding_service import has_embeddings
            if not has_embeddings():
                st.warning("尚未生成 Embedding，将回退到关键词搜索。请在下方点击「重建 Embedding」。")
        except Exception:
            pass

    with st.spinner("AI 正在搜索知识库..."):
        if mode == "hybrid":
            result = answer_with_hybrid_rag(question)
        elif mode == "semantic":
            result = answer_with_semantic_rag(question)
        else:
            result = answer_with_rag(question, mode="keyword")

    st.divider()

    # 回答标题行：模式标签 + 缓存标签
    mode_label = MODE_OPTIONS.get(result.get("mode", mode), result.get("mode", mode))
    title_parts = [f"回答（{mode_label}）"]
    if result.get("cached"):
        title_parts.append("⚡缓存命中")
    st.subheader(" ".join(title_parts))

    st.markdown(result["answer"])

    item_count = result.get("item_count", 0)
    sources = result.get("sources", [])

    if item_count > 0:
        st.divider()
        st.subheader("参考来源")
        st.caption(f"知识库命中 {item_count} 条记录，以下为 AI 回答的参考依据：")
        _render_rag_sources(sources)

        # AI 行动建议
        st.divider()
        _render_action_suggestions(question, result["answer"], sources)
    else:
        st.warning("知识库中没有找到相关内容，无法基于当前系统内容回答。")

    with st.expander("检索上下文（调试）", expanded=False):
        context = result.get("context", "")
        if context:
            st.caption(f"上下文长度: {len(context)} 字符")
            st.text_area("传给 AI 的上下文", context, height=250)
        else:
            st.caption("无上下文（未命中任何知识条目）")
        st.caption(f"命中条目数: {item_count} | 缓存: {result.get('cached', False)}")
        if sources:
            st.json(sources)


def _render_action_suggestions(question: str, answer: str, sources: list):
    """显示 AI 行动建议，支持一键执行。"""
    try:
        from services.action_suggestion_service import suggest_actions, ACTION_LABELS
        actions = suggest_actions(question, answer, sources)
    except Exception:
        return

    if not actions:
        return

    st.subheader("AI 建议动作")

    # 初始化执行状态追踪
    st.session_state.setdefault("action_executed", {})
    st.session_state.setdefault("action_ignored", {})
    st.session_state.setdefault("action_results", {})

    import hashlib
    q_hash = hashlib.md5(question.encode()).hexdigest()[:8]

    for i, a in enumerate(actions):
        action_type = a.get("action_type", "")
        if action_type == "no_action":
            continue

        action_key = f"{q_hash}_{i}"
        label = ACTION_LABELS.get(action_type, action_type)
        title = a.get("title", "")
        desc = a.get("description", "")
        confidence = a.get("confidence", 0)

        st.markdown(f"{i+1}. **[{label}]** {title}（置信度: {confidence:.0%}）")
        if desc:
            st.caption(desc)

        # 检查是否已执行或已忽略
        is_executed = st.session_state["action_executed"].get(action_key, False)
        is_ignored = st.session_state["action_ignored"].get(action_key, False)

        if is_executed:
            result = st.session_state["action_results"].get(action_key, {})
            if result.get("success"):
                st.success(f"✅ {result.get('message', '已执行')}")
            else:
                st.error(f"❌ {result.get('message', '执行失败')}")
        elif is_ignored:
            st.caption("已忽略")
        else:
            col1, col2, col3 = st.columns([1, 1, 4])
            with col1:
                if st.button("执行此建议", key=f"exec_{action_key}", use_container_width=True):
                    from services.action_executor_service import execute_action
                    result = execute_action(a, sources)
                    st.session_state["action_executed"][action_key] = True
                    st.session_state["action_results"][action_key] = result
                    st.rerun()
            with col2:
                if st.button("忽略", key=f"ignore_{action_key}", use_container_width=True):
                    st.session_state["action_ignored"][action_key] = True
                    st.rerun()


def _render_rag_sources(sources: list):
    """显示 RAG 命中的知识条目来源。"""
    for i, src in enumerate(sources, 1):
        stype = src.get("source_type", "")
        label = TYPE_LABELS_CN.get(stype, stype)
        title = src.get("title", "(无标题)")
        # 根据模式显示不同分数
        if "final_score" in src:
            score_str = f"综合: {src['final_score']}（关键词: {src.get('keyword_score', '-')} / 语义: {src.get('semantic_score', '-')}）"
        elif "semantic_score" in src:
            score_str = f"语义: {src['semantic_score']}"
        else:
            score_str = f"相关度: {src.get('score', 1)}"
        st.markdown(f"{i}. **[{label}]** {title}（{score_str}）")


def _render_kb_maintenance():
    """知识库维护区域。"""
    stats = get_knowledge_stats()

    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
    with col1:
        st.metric("知识条目总数", stats["total"])
    with col2:
        by_type = stats.get("by_type", {})
        type_summary = " | ".join(
            f"{TYPE_LABELS_CN.get(k, k)}: {v}"
            for k, v in sorted(by_type.items())
        )
        st.caption(f"各类型数量: {type_summary}" if type_summary else "暂无数据")
    with col3:
        if st.button("重建知识库", key="rebuild_kb_btn", use_container_width=True):
            with st.spinner("正在重建知识库..."):
                total = rebuild_knowledge_items()
            st.success(f"知识库已重建，共 {total} 条记录")
            st.rerun()
    with col4:
        if st.button("重建 Embedding", key="rebuild_emb_btn", use_container_width=True):
            from services.embedding_service import rebuild_embeddings, has_embeddings
            with st.spinner("正在生成 Embedding（可能需要几分钟）..."):
                emb_count = rebuild_embeddings()
            st.success(f"Embedding 已生成，共 {emb_count} 条")
            st.rerun()

    # 显示 Embedding 状态
    try:
        from services.embedding_service import has_embeddings
        if has_embeddings():
            emb_row = fetch_emb_count()
            if emb_row:
                st.caption(f"Embedding 已就绪: {emb_row} 条（语义/混合搜索可用）")
        else:
            st.caption("Embedding 尚未生成，语义/混合搜索将回退到关键词搜索")
    except Exception:
        pass


def fetch_emb_count():
    from database.db import fetch_one
    row = fetch_one("SELECT COUNT(*) as cnt FROM knowledge_embeddings")
    return row["cnt"] if row else 0
