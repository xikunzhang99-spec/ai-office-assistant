"""
RAG 问答 — 基于知识块的语义检索问答页面。
支持 Chunks / Keyword / Semantic / Hybrid 四种检索模式。
"""
import streamlit as st


MODE_LABELS = {
    "chunks": "知识块（推荐）",
    "keyword": "关键词",
    "semantic": "语义",
    "hybrid": "混合",
}

MODE_DESCRIPTIONS = {
    "chunks": "基于分块向量搜索，检索最相关的知识片段，回答更精确。",
    "keyword": "基于关键词匹配，速度快，适合精确查找。",
    "semantic": "基于语义向量搜索，理解问题含义，适合模糊查询。",
    "hybrid": "结合关键词和语义搜索，覆盖面最广。",
}

SOURCE_TYPE_LABELS = {
    "obsidian_note": "Obsidian笔记",
    "project": "项目",
    "project_timeline": "项目时间轴",
    "daily_summary": "每日总结",
    "daily_note": "随手记",
    "client": "客户",
    "task": "任务",
    "file": "文件",
    "event": "事件",
}

EXAMPLES = [
    "Workflow Agent 第二版主要完成了什么？",
    "Business Brain 第一版实现了哪些能力？",
    "AI办公助理项目的下一步计划是什么？",
    "最近有哪些项目有风险？",
    "张三公司最近的动态是什么？",
]


def render():
    st.title("RAG 问答")
    st.markdown("基于知识库的智能问答。系统从已入库的知识块中检索相关信息，由 AI 基于检索结果生成回答。")

    # Stats
    from services.knowledge_ingestion import get_chunk_stats
    from services.embedding_service import count_chunk_embeddings
    try:
        stats = get_chunk_stats()
        emb_count = count_chunk_embeddings()
        st.caption(f"知识块: {stats['total']} 个 | 已向量化: {emb_count} 个")
    except Exception:
        st.caption("知识库尚未初始化，请先在「数据管理」页面执行入库。")

    # Example buttons
    _render_examples()

    st.divider()

    # Mode selector
    mode = st.radio(
        "检索模式",
        list(MODE_LABELS.keys()),
        format_func=lambda m: MODE_LABELS[m],
        horizontal=True,
        key="rag_mode",
    )
    st.caption(MODE_DESCRIPTIONS.get(mode, ""))

    # Input area
    col_input, col_btn = st.columns([5, 1])
    with col_input:
        question = st.text_area(
            "输入问题",
            placeholder="例如：Workflow Agent 第二版主要完成了什么？",
            height=100,
            key="rag_question",
            label_visibility="collapsed",
        )
    with col_btn:
        st.write("")
        ask_clicked = st.button("提问", type="primary", use_container_width=True, key="btn_ask")

    if st.session_state.get("rag_auto_submit"):
        st.session_state["rag_auto_submit"] = False
        ask_clicked = True

    if ask_clicked and question.strip():
        _do_query(question.strip(), mode)
    elif ask_clicked:
        st.warning("请输入问题")

    # Show results
    if "rag_result" in st.session_state:
        st.divider()
        _render_result(st.session_state["rag_result"])


def _render_examples():
    st.caption("快速提问：")
    cols = st.columns(3)
    for i, q in enumerate(EXAMPLES):
        with cols[i % 3]:
            if st.button(q[:30] + ("..." if len(q) > 30 else ""), key=f"rag_ex_{i}", use_container_width=True):
                st.session_state["rag_question"] = q
                st.session_state["rag_auto_submit"] = True
                st.rerun()


def _do_query(question: str, mode: str):
    with st.spinner("检索中..."):
        try:
            if mode == "chunks":
                from services.rag_service import answer_with_chunks
                result = answer_with_chunks(question)
            elif mode == "keyword":
                from services.rag_service import answer_with_rag
                result = answer_with_rag(question, mode="keyword")
            elif mode == "semantic":
                from services.rag_service import answer_with_semantic_rag
                result = answer_with_semantic_rag(question)
            elif mode == "hybrid":
                from services.rag_service import answer_with_hybrid_rag
                result = answer_with_hybrid_rag(question)
            else:
                st.error(f"未知模式: {mode}")
                return

            result["query_mode"] = mode
            st.session_state["rag_result"] = result
        except Exception as e:
            st.error(f"查询失败: {str(e)}")


def _render_result(result: dict):
    mode = result.get("query_mode", result.get("mode", "unknown"))

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.markdown(f"**检索模式**: {MODE_LABELS.get(mode, mode)}")
    with col2:
        st.metric("检索结果", result.get("item_count", 0))
    with col3:
        cached = "是" if result.get("cached") else "否"
        st.caption(f"缓存命中: {cached}")

    st.divider()

    # Answer
    st.markdown("### 回答")
    st.markdown(result.get("answer", "无回答"))

    # Sources
    sources = result.get("sources", [])
    if sources:
        with st.expander("参考来源", expanded=True):
            for i, src in enumerate(sources):
                source_type = src.get("source_type", "")
                type_label = SOURCE_TYPE_LABELS.get(source_type, source_type)
                title = src.get("source_title", src.get("title", "未知"))

                meta_parts = [f"[{type_label}] {title}"]
                if src.get("score"):
                    meta_parts.append(f"相关度: {src['score']:.2f}")
                if src.get("date"):
                    meta_parts.append(f"日期: {src['date']}")
                if src.get("chunk_id"):
                    meta_parts.append(f"Chunk #{src['chunk_id']}")
                st.caption(f"{i+1}. " + " | ".join(meta_parts))

    # Context
    context = result.get("context", "")
    if context:
        with st.expander("检索上下文（供调试）", expanded=False):
            st.text(context[:3000])
