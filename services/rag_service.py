"""
RAG 服务 — 关键词 + 语义 + 混合 RAG 回答流程（基于 knowledge_items 检索）。
Phase 9：优化速度（缓存、截断、参数化）+ 语义搜索基础结构。
"""
from collections import OrderedDict
from services.ai_service import _chat
from services.knowledge_service import search_knowledge_items
from services.timeline_service import add_event
from utils.date_utils import today_str

TYPE_LABELS = {
    "client": "客户",
    "project": "项目",
    "task": "任务",
    "file": "文件",
    "event": "事件",
}

MAX_CONTEXT_CHARS = 7000
MAX_ITEM_CONTENT_CHARS = 600

# 内存缓存：{(question, frozenset(source_ids)): result}
_rag_cache = OrderedDict()
MAX_CACHE_SIZE = 50


def _get_cache_key(question: str, sources: list, mode: str = "") -> tuple:
    source_ids = frozenset(
        (s.get("source_type", ""), s.get("source_id", 0)) for s in sources
    )
    return (question, source_ids, mode)


def _cache_get(question: str, sources: list, mode: str = "") -> dict | None:
    key = _get_cache_key(question, sources, mode)
    return _rag_cache.get(key)


def _cache_set(question: str, sources: list, result: dict):
    global _rag_cache
    mode = result.get("mode", "")
    key = _get_cache_key(question, sources, mode)
    _rag_cache[key] = result
    _rag_cache.move_to_end(key)
    if len(_rag_cache) > MAX_CACHE_SIZE:
        _rag_cache.popitem(last=False)


def answer_with_rag(question: str, mode: str = "keyword") -> dict:
    """基于 knowledge_items 的 RAG 问答。

    mode: "keyword" / "semantic" / "hybrid"
    返回: {answer, sources, context, item_count, mode, cached}
    """
    # 检索
    items, search_mode = _retrieve(question, mode)

    if not items:
        answer = "没有找到相关数据，无法基于当前系统内容回答。请尝试换一种问法或使用更具体的关键词。"
        add_event("ai_query", question, answer[:200], event_date=today_str())
        return {
            "answer": answer,
            "sources": [],
            "context": "",
            "item_count": 0,
            "mode": search_mode,
            "cached": False,
        }

    # 检查缓存
    cached_result = _cache_get(question, items, search_mode)
    if cached_result:
        cached_result["cached"] = True
        return cached_result

    # 构建上下文并生成回答
    context = build_rag_context(items)
    answer = _generate_rag_answer(question, context, len(items))

    sources = []
    for item in items:
        src = {
            "source_type": item["source_type"],
            "source_id": item["source_id"],
            "title": item["title"],
        }
        if "score" in item:
            src["score"] = item["score"]
        if "keyword_score" in item:
            src["keyword_score"] = item["keyword_score"]
        if "semantic_score" in item:
            src["semantic_score"] = item["semantic_score"]
        if "final_score" in item:
            src["final_score"] = item["final_score"]
        sources.append(src)

    add_event("ai_query", question, answer[:200], event_date=today_str())

    result = {
        "answer": answer,
        "sources": sources,
        "context": context,
        "item_count": len(items),
        "mode": search_mode,
        "cached": False,
    }

    _cache_set(question, items, result)
    return result


def _retrieve(question: str, mode: str) -> tuple:
    """根据 mode 检索 knowledge_items。返回 (items, used_mode)。"""
    if mode == "semantic":
        try:
            from services.embedding_service import semantic_search, has_embeddings
            if has_embeddings():
                items = semantic_search(question, limit=10)
                if items:
                    return items, "semantic"
        except Exception:
            pass
        # 回退到关键词搜索
        items = search_knowledge_items(question, limit=10)
        return items, "keyword"

    elif mode == "hybrid":
        try:
            from services.embedding_service import has_embeddings
            if has_embeddings():
                from services.hybrid_search_service import hybrid_search as hs
                result = hs(question, limit=10)
                return result["items"], "hybrid"
        except Exception:
            pass
        items = search_knowledge_items(question, limit=10)
        return items, "keyword"

    else:
        items = search_knowledge_items(question, limit=10)
        return items, "keyword"


def build_rag_context(items: list) -> str:
    """将 knowledge_items 检索结果整理成 AI 可读文本，按 source_type 分组。
    同时纳入 memory_items 和风险关系。

    每条 content 截取 {MAX_ITEM_CONTENT_CHARS} 字，总上下文限制 {MAX_CONTEXT_CHARS} 字。
    """
    grouped = {}
    for item in items:
        stype = item["source_type"]
        if stype not in grouped:
            grouped[stype] = []
        grouped[stype].append(item)

    sections = []
    total_chars = 0
    type_order = ["client", "project", "task", "file", "event"]
    for stype in type_order:
        if stype not in grouped:
            continue
        label = TYPE_LABELS.get(stype, stype)
        lines = [f"【{label}】"]
        for item in grouped[stype]:
            if total_chars >= MAX_CONTEXT_CHARS:
                break
            title = item.get("title") or "(无标题)"
            content = item.get("content") or ""

            # 截断每条 content
            if len(content) > MAX_ITEM_CONTENT_CHARS:
                content = content[:MAX_ITEM_CONTENT_CHARS] + "..."

            lines.append(f"- 标题：{title}")
            if content:
                for content_line in content.split("\n"):
                    content_line = content_line.strip()
                    if content_line:
                        lines.append(f"  内容：{content_line}")

            # 显示相关度分数
            score = item.get("final_score") or item.get("semantic_score") or item.get("score")
            if score:
                lines.append(f"  相关度：{score}")

            section_text = "\n".join(lines)
            total_chars = sum(len(s.get("title", "")) + len(s.get("content", "")) for s in grouped[stype][:grouped[stype].index(item) + 1])
            # 用实际字符计数
            total_chars = sum(len(line) for section in sections for line in section.split("\n"))
            total_chars += len("\n".join(lines))

        if total_chars < MAX_CONTEXT_CHARS:
            sections.append("\n".join(lines))
        else:
            break

    # ── 纳入 memory_items ──
    if total_chars < MAX_CONTEXT_CHARS:
        try:
            memory_section = _build_memory_context(items)
            if memory_section:
                sections.append(memory_section)
        except Exception:
            pass

    if not sections:
        return "没有找到相关数据。"

    return "\n\n".join(sections)


def _build_memory_context(knowledge_items: list) -> str:
    """基于 knowledge_items 中涉及的实体，搜索相关长期记忆。"""
    client_ids = set()
    project_ids = set()
    task_ids = set()

    for item in knowledge_items:
        cid = item.get("client_id")
        pid = item.get("project_id")
        tid = item.get("task_id") or (item.get("source_id") if item.get("source_type") == "task" else None)
        if cid:
            client_ids.add(cid)
        if pid:
            project_ids.add(pid)
        if tid:
            task_ids.add(tid)

    if not client_ids and not project_ids and not task_ids:
        return ""

    from services.memory_service import search_memory, get_memory_by_client, get_memory_by_project
    from services.relation_service import find_entity_risks

    memories = []
    seen_ids = set()

    for cid in client_ids:
        for m in get_memory_by_client(cid, limit=5):
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                memories.append(m)

    for pid in project_ids:
        for m in get_memory_by_project(pid, limit=5):
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                memories.append(m)

    if not memories:
        return ""

    lines = ["【长期记忆】"]
    for m in memories[:10]:
        imp_label = {"critical": "严重", "high": "重要", "medium": "一般", "low": "提示"}.get(
            m.get("importance", ""), "")
        type_label = {
            "client_preference": "客户偏好", "project_risk": "项目风险",
            "task_blocker": "任务阻塞", "decision": "决策",
            "meeting_conclusion": "会议结论", "follow_up": "跟进",
            "important_fact": "重要事实",
        }.get(m.get("memory_type", ""), m.get("memory_type", ""))
        lines.append(f"- [{imp_label}][{type_label}] {m.get('title', '')}")
        if m.get("content"):
            content_short = m["content"][:200]
            lines.append(f"  {content_short}")

    # 添加风险关系
    try:
        risk_lines = []
        for pid in project_ids:
            risks = find_entity_risks("project", pid)
            for r in risks[:3]:
                risk_lines.append(f"- 风险: {r.get('description', r.get('relation_type', ''))}")
        if risk_lines:
            lines.append("")
            lines.append("【项目风险】")
            lines.extend(risk_lines)
    except Exception:
        pass

    return "\n".join(lines)


def _generate_rag_answer(question: str, context: str, item_count: int) -> str:
    """调用 AI 基于 context 生成回答。使用低 temperature 提高稳定性和速度。"""
    prompt = f"""根据以下知识库检索结果回答用户的问题。用中文回答，简洁清晰，用Markdown格式。

## 用户问题
{question}

## 知识库检索结果（共 {item_count} 条）
{context}

## 严格要求
- 先给出一句总结，概括从知识库中找到多少相关信息
- 列出关键信息，涉及客户/项目/任务/文件时明确提及名称
- 如果检索结果中包含「长期记忆」部分，要结合这些记忆来回答（这些是过去积累的重要业务信息）
- 如果检索结果中包含「项目风险」部分，要在回答中重点提及相关风险信息
- **只能基于上述检索结果回答，绝对不要编造不存在的信息**
- **如果检索结果不足以回答问题的某个部分，请明确说明"当前资料不足"**
- **不要猜测或假设知识库中没有的数据**
- 不超过500字"""

    return _chat(
        prompt,
        "You are a helpful office assistant. Answer questions based ONLY on the provided knowledge base data. "
        "Never fabricate or assume information not present in the data.",
        temperature=0.3,
        max_tokens=1000,
    )


def answer_with_hybrid_rag(question: str) -> dict:
    """使用混合搜索（关键词+语义）的 RAG 问答。"""
    from services.hybrid_search_service import hybrid_search as hs

    result = hs(question, limit=10)
    items = result["items"]

    if not items:
        answer = "没有找到相关数据，无法基于当前系统内容回答。请尝试换一种问法或使用更具体的关键词。"
        add_event("ai_query", question, answer[:200], event_date=today_str())
        return {
            "answer": answer,
            "sources": [],
            "context": "",
            "item_count": 0,
            "mode": "hybrid",
            "cached": False,
        }

    cached_result = _cache_get(question, items, "hybrid")
    if cached_result:
        cached_result["cached"] = True
        return cached_result

    context = build_rag_context(items)
    answer = _generate_rag_answer(question, context, len(items))

    sources = []
    for item in items:
        src = {"source_type": item["source_type"], "source_id": item["source_id"], "title": item["title"]}
        if "keyword_score" in item:
            src["keyword_score"] = item["keyword_score"]
        if "semantic_score" in item:
            src["semantic_score"] = item["semantic_score"]
        if "final_score" in item:
            src["final_score"] = item["final_score"]
        if "score" in item:
            src["score"] = item["score"]
        sources.append(src)

    add_event("ai_query", question, answer[:200], event_date=today_str())

    result = {
        "answer": answer,
        "sources": sources,
        "context": context,
        "item_count": len(items),
        "mode": "hybrid",
        "cached": False,
    }
    _cache_set(question, items, result)
    return result


def answer_with_semantic_rag(question: str) -> dict:
    """使用语义搜索的 RAG 问答。"""
    try:
        from services.embedding_service import semantic_search, has_embeddings
        if has_embeddings():
            items = semantic_search(question, limit=10)
            if items:
                context = build_rag_context(items)
                answer = _generate_rag_answer(question, context, len(items))
                sources = [{"source_type": i["source_type"], "source_id": i["source_id"],
                            "title": i["title"], "semantic_score": i.get("semantic_score", 0)}
                           for i in items]
                add_event("ai_query", question, answer[:200], event_date=today_str())
                return {"answer": answer, "sources": sources, "context": context,
                        "item_count": len(items), "mode": "semantic", "cached": False}
    except Exception:
        pass
    # 回退到关键词
    return answer_with_rag(question, mode="keyword")


def hybrid_search(question: str, limit: int = 10) -> list:
    """混合搜索（委托给 hybrid_search_service）。"""
    from services.hybrid_search_service import hybrid_search as hs
    result = hs(question, limit=limit)
    return result["items"]


# ── Chunk-based RAG (Phase 4: RAG + Semantic Search) ──

def answer_with_chunks(question: str, top_k: int = 5) -> dict:
    """基于 knowledge_chunks 的 RAG 问答。

    流程：
    1. 语义搜索相关 chunks
    2. 构建 chunk 上下文
    3. 调用 LLM 生成答案
    4. 返回答案 + 来源

    Returns:
        {answer, sources, context, item_count, mode: "chunks"}
    """
    from services.search_service import semantic_search_chunks

    chunks = semantic_search_chunks(question, top_k)

    if not chunks:
        answer = "资料不足，无法回答。知识库中没有找到相关信息，请先执行知识入库或尝试其他问法。"
        add_event("ai_query", question, answer[:200], event_date=today_str())
        return {
            "answer": answer,
            "sources": [],
            "context": "",
            "item_count": 0,
            "mode": "chunks",
            "cached": False,
        }

    context = _build_chunk_context(chunks)
    answer = _generate_chunk_answer(question, context, len(chunks))

    sources = []
    for c in chunks:
        meta = c.get("metadata", {})
        sources.append({
            "source_title": c.get("source_title", ""),
            "source_type": c.get("source_type", ""),
            "source_id": c.get("source_id", 0),
            "date": meta.get("date", ""),
            "chunk_id": c.get("chunk_id", 0),
            "score": c.get("score", 0),
        })

    add_event("ai_query", question, answer[:200], event_date=today_str())

    return {
        "answer": answer,
        "sources": sources,
        "context": context,
        "item_count": len(chunks),
        "mode": "chunks",
        "cached": False,
    }


def _build_chunk_context(chunks: list) -> str:
    """构建 chunk 上下文文本，供 LLM 使用。"""
    sections = []
    seen_sources = set()

    for i, c in enumerate(chunks):
        source_key = (c.get("source_type", ""), c.get("source_id", 0))
        source_title = c.get("source_title", "未知来源")
        source_type = c.get("source_type", "")

        type_label = TYPE_LABELS.get(source_type, source_type)
        score = c.get("score", 0)

        if source_key not in seen_sources:
            sections.append(f"\n### [{type_label}] {source_title}")
            seen_sources.add(source_key)

        content = c.get("content", "")[:600]
        sections.append(f"**[片段 {i+1}]** (相关度: {score:.2f})\n{content}")

    return "\n".join(sections)


def _generate_chunk_answer(question: str, context: str, item_count: int) -> str:
    """基于 chunk 上下文生成 AI 回答。"""
    prompt = f"""根据以下知识库检索结果回答用户的问题。用中文回答，简洁清晰，用Markdown格式。

## 用户问题
{question}

## 知识库检索结果（共 {item_count} 个相关片段）
{context}

## 严格要求
- 先给出一句总结，概括从知识库中找到多少相关信息
- 列出关键信息，引用来源时标明来源标题和类型（如"来自 [项目] XXX"）
- **只能基于上述检索结果回答，绝对不要编造不存在的信息**
- **如果检索结果不足以回答问题的某个部分，请明确说明"当前资料不足，无法回答这部分"**
- **不要猜测或假设知识库中没有的数据**
- 不超过500字"""

    return _chat(
        prompt,
        "You are a helpful office assistant. Answer questions based ONLY on the provided knowledge base context. "
        "Always cite your sources. Never fabricate or assume information not present in the data.",
        temperature=0.3,
        max_tokens=1000,
    )
