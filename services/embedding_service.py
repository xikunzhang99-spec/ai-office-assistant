"""
Embedding 服务 — 基于 OpenAI-compatible API 的文本向量化。
Phase 11：numpy 批量 cosine_similarity + faiss 预留 + rebuild 进度 + 孤儿清理。
"""
import json
import math
from database.db import fetch_one, fetch_all, insert, execute
from config.settings import AI_API_KEY, AI_BASE_URL, EMBEDDING_MODEL
from utils.date_utils import now_str

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    np = None
    _HAS_NUMPY = False

# 使用 numpy 批量计算的最低行数阈值（少量数据时纯 Python 更快）
_NUMPY_THRESHOLD = 20


def _get_embedding_client():
    from openai import OpenAI
    return OpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL)


def get_embedding(text: str) -> list:
    """调用 Embedding API 获取文本向量。"""
    if not AI_API_KEY:
        return []
    if not text or not text.strip():
        return []
    try:
        client = _get_embedding_client()
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text[:8000],
        )
        return response.data[0].embedding
    except Exception:
        return []


def upsert_embedding(knowledge_item_id: int, text: str = None) -> bool:
    """为一条 knowledge_item 生成并存储 embedding（幂等）。"""
    if text is None:
        from services.knowledge_service import search_knowledge
        rows = fetch_all(
            "SELECT title, content FROM knowledge_items WHERE id = ?",
            (knowledge_item_id,),
        )
        if not rows:
            return False
        text = f"{rows[0]['title']}\n{rows[0].get('content', '')}"

    vec = get_embedding(text)
    if not vec:
        return False

    existing = fetch_one(
        "SELECT id FROM knowledge_embeddings WHERE knowledge_item_id = ?",
        (knowledge_item_id,),
    )
    embedding_json = json.dumps(vec)
    if existing:
        execute(
            """UPDATE knowledge_embeddings
               SET embedding = ?, embedding_model = ?, updated_at = ?
               WHERE knowledge_item_id = ?""",
            (embedding_json, EMBEDDING_MODEL, now_str(), knowledge_item_id),
        )
    else:
        insert(
            """INSERT INTO knowledge_embeddings
               (knowledge_item_id, embedding_model, embedding, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (knowledge_item_id, EMBEDDING_MODEL, embedding_json, now_str(), now_str()),
        )
    return True


def rebuild_embeddings(progress_callback=None) -> int:
    """为所有 knowledge_items 重建 embedding。

    Args:
        progress_callback: 可选回调函数，签名 callback(current_index, total_count)

    Returns:
        成功生成的数量。
    """
    items = fetch_all("SELECT id, title, content FROM knowledge_items")
    total = len(items)
    count = 0
    for i, item in enumerate(items):
        text = f"{item['title']}\n{item.get('content', '')}"
        if upsert_embedding(item["id"], text):
            count += 1
        if progress_callback and callable(progress_callback):
            progress_callback(i + 1, total)

    # 记录工作流日志
    try:
        from services.workflow_log_service import add_workflow_log
        add_workflow_log(
            "rebuild_embeddings",
            status="success" if count > 0 else "error",
            message=f"成功 {count}/{total} 条 embedding",
            details=json.dumps({"success": count, "total": total}, ensure_ascii=False),
        )
    except Exception:
        pass

    return count


def cosine_similarity(vec1: list, vec2: list) -> float:
    """纯 Python 计算两个向量的余弦相似度。"""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def _semantic_search_numpy(q_vec: list, emb_rows: list, limit: int) -> list:
    """使用 numpy 批量计算余弦相似度。"""
    if not emb_rows:
        return []

    valid_rows = []
    vectors = []
    for row in emb_rows:
        try:
            vec = json.loads(row["embedding"])
        except (json.JSONDecodeError, TypeError):
            continue
        valid_rows.append(row)
        vectors.append(vec)

    if not valid_rows:
        return []

    q = np.array(q_vec, dtype=np.float64)
    m = np.array(vectors, dtype=np.float64)  # shape [N, dim]

    # 批量余弦相似度: dot(q, m[i]) / (||q|| * ||m[i]||)
    q_norm = np.linalg.norm(q)
    m_norms = np.linalg.norm(m, axis=1)

    if q_norm == 0 or np.all(m_norms == 0):
        return []

    dot_products = np.dot(m, q)
    similarities = dot_products / (m_norms * q_norm)

    results = []
    for i, row in enumerate(valid_rows):
        sim = float(similarities[i])
        if sim > 0:
            results.append({
                "knowledge_item_id": row["knowledge_item_id"],
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "title": row["title"],
                "content": row["content"],
                "tags": row["tags"],
                "client_id": row["client_id"],
                "project_id": row["project_id"],
                "task_id": row["task_id"],
                "semantic_score": round(sim, 4),
            })

    results.sort(key=lambda x: x["semantic_score"], reverse=True)
    return results[:limit]


def semantic_search(question: str, limit: int = 10) -> list:
    """语义搜索：生成 question embedding，与所有 knowledge_embeddings 计算余弦相似度。

    返回结果按相似度降序排列，包含 knowledge_item 的字段 + semantic_score。
    当 numpy 可用且数据量较大时，自动使用批量矩阵运算加速。
    """
    q_vec = get_embedding(question)
    if not q_vec:
        return []

    emb_rows = fetch_all(
        "SELECT ke.knowledge_item_id, ke.embedding, ki.source_type, ki.source_id, "
        "ki.title, ki.content, ki.tags, ki.client_id, ki.project_id, ki.task_id "
        "FROM knowledge_embeddings ke "
        "JOIN knowledge_items ki ON ke.knowledge_item_id = ki.id"
    )
    if not emb_rows:
        return []

    # 数据量较大且有 numpy 时使用批量计算
    if _HAS_NUMPY and len(emb_rows) >= _NUMPY_THRESHOLD:
        return _semantic_search_numpy(q_vec, emb_rows, limit)

    # 纯 Python fallback
    results = []
    for row in emb_rows:
        try:
            vec = json.loads(row["embedding"])
        except (json.JSONDecodeError, TypeError):
            continue
        sim = cosine_similarity(q_vec, vec)
        if sim > 0:
            results.append({
                "knowledge_item_id": row["knowledge_item_id"],
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "title": row["title"],
                "content": row["content"],
                "tags": row["tags"],
                "client_id": row["client_id"],
                "project_id": row["project_id"],
                "task_id": row["task_id"],
                "semantic_score": round(sim, 4),
            })

    results.sort(key=lambda x: x["semantic_score"], reverse=True)
    return results[:limit]


def faiss_search(question: str, limit: int = 10) -> list:
    """FAISS 加速语义搜索（预留接口，暂未实现）。

    TODO: 实现 FAISS IVF/HNSW 索引以支持大规模 embedding 的亚线性检索。
        1. 构建或加载 FAISS 索引（从 knowledge_embeddings 表）
        2. 使用 IndexIDMap 映射 FAISS 内部 ID 到 knowledge_item_id
        3. 查询时：encode question → index.search → 返回 top-k
        4. 索引持久化到磁盘（与数据库同目录）

    当前 fallback 到 semantic_search()。
    """
    return semantic_search(question, limit)


def has_embeddings() -> bool:
    """检查是否有已生成的 embedding。"""
    row = fetch_one("SELECT COUNT(*) as cnt FROM knowledge_embeddings")
    return (row["cnt"] if row else 0) > 0


def count_orphan_embeddings() -> int:
    """统计 knowledge_item_id 已不存在的孤儿 embedding 数量。"""
    row = fetch_one("""
        SELECT COUNT(*) as cnt FROM knowledge_embeddings ke
        WHERE ke.knowledge_item_id NOT IN (SELECT id FROM knowledge_items)
    """)
    return row["cnt"] if row else 0


def cleanup_orphan_embeddings() -> int:
    """删除 knowledge_item_id 已不存在的孤儿 embedding。

    Returns:
        删除的数量。
    """
    before = count_orphan_embeddings()
    if before > 0:
        execute("""
            DELETE FROM knowledge_embeddings
            WHERE knowledge_item_id NOT IN (SELECT id FROM knowledge_items)
        """)
    return before


# ── Chunk-level embedding (Phase 4: RAG + Semantic Search) ──

def embed_and_store_chunk(chunk_id: int, text: str) -> bool:
    """为单个 knowledge_chunk 生成并存储 embedding。"""
    vec = get_embedding(text)
    if not vec:
        return False
    execute(
        "UPDATE knowledge_chunks SET embedding = ?, updated_at = ? WHERE id = ?",
        (json.dumps(vec), now_str(), chunk_id),
    )
    return True


def embed_and_store_batch(chunks: list[dict], source_type: str = "",
                          source_title: str = "", source_id: int = 0) -> int:
    """批量为 chunks 生成 embedding 并存储。

    Args:
        chunks: [{"chunk_id": int, "content": str, "metadata": dict}, ...]
        source_type, source_title, source_id: 未使用，保留兼容

    Returns:
        成功生成的数量
    """
    count = 0
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        content = chunk.get("content", "")
        if chunk_id and content:
            if embed_and_store_chunk(chunk_id, content):
                count += 1
    return count


def search_chunks_numpy(query_embedding: list, top_k: int = 5) -> list:
    """使用 numpy 在 knowledge_chunks 中进行语义搜索。

    Args:
        query_embedding: 查询文本的 embedding 向量
        top_k: 返回结果数量

    Returns:
        [{chunk_id, source_type, source_id, source_title, content, score, metadata_json}, ...]
    """
    rows = fetch_all(
        """SELECT id, source_type, source_id, source_title, content,
                  metadata_json, embedding
           FROM knowledge_chunks WHERE embedding IS NOT NULL"""
    )
    if not rows:
        return []

    if _HAS_NUMPY and len(rows) >= _NUMPY_THRESHOLD:
        return _search_chunks_numpy_impl(query_embedding, rows, top_k)
    return _search_chunks_python_impl(query_embedding, rows, top_k)


def _search_chunks_numpy_impl(q_vec: list, rows: list, top_k: int) -> list:
    """numpy 批量余弦相似度搜索。"""
    valid_rows = []
    vectors = []
    for row in rows:
        try:
            vec = json.loads(row["embedding"])
        except (json.JSONDecodeError, TypeError):
            continue
        valid_rows.append(row)
        vectors.append(vec)

    if not valid_rows:
        return []

    q = np.array(q_vec, dtype=np.float64)
    m = np.array(vectors, dtype=np.float64)

    q_norm = np.linalg.norm(q)
    m_norms = np.linalg.norm(m, axis=1)
    if q_norm == 0 or np.all(m_norms == 0):
        return []

    dot_products = np.dot(m, q)
    similarities = dot_products / (m_norms * q_norm)

    results = []
    for i, row in enumerate(valid_rows):
        sim = float(similarities[i])
        if sim > 0:
            metadata = {}
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                pass
            results.append({
                "chunk_id": row["id"],
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "source_title": row["source_title"],
                "content": row["content"],
                "score": round(sim, 4),
                "metadata": metadata,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def _search_chunks_python_impl(q_vec: list, rows: list, top_k: int) -> list:
    """纯 Python 余弦相似度搜索（少量数据时使用）。"""
    results = []
    for row in rows:
        try:
            vec = json.loads(row["embedding"])
        except (json.JSONDecodeError, TypeError):
            continue
        sim = cosine_similarity(q_vec, vec)
        if sim > 0:
            metadata = {}
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                pass
            results.append({
                "chunk_id": row["id"],
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "source_title": row["source_title"],
                "content": row["content"],
                "score": round(sim, 4),
                "metadata": metadata,
            })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def delete_chunk_embeddings(source_type: str, source_id: int):
    """删除指定来源的 chunk embeddings（清空 embedding 列）。"""
    execute(
        "UPDATE knowledge_chunks SET embedding = NULL WHERE source_type = ? AND source_id = ?",
        (source_type, source_id),
    )


def clear_chunk_embeddings():
    """清空所有 chunk embeddings。"""
    execute("UPDATE knowledge_chunks SET embedding = NULL")


def count_chunk_embeddings() -> int:
    """统计已生成 embedding 的 chunk 数量。"""
    row = fetch_one("SELECT COUNT(*) as cnt FROM knowledge_chunks WHERE embedding IS NOT NULL")
    return row["cnt"] if row else 0
