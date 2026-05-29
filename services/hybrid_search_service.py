"""
混合搜索服务 — 合并关键词搜索和语义搜索结果，去重后按综合分数排序。
Phase 10：从 rag_service.py 提取为独立服务，提供形式化 API。
"""
from services.knowledge_service import search_knowledge_items
from services.embedding_service import semantic_search


def hybrid_search(question: str, limit: int = 10) -> dict:
    """混合搜索：合并关键词和语义结果。

    返回:
        {items: [...], mode: "hybrid", total: int}
    """
    kw_results = search_knowledge_items(question, limit=limit * 2)
    sem_results = semantic_search(question, limit=limit * 2)

    items = merge_search_results(kw_results, sem_results)
    items = items[:limit]

    # 为兼容性添加 id 字段（关键词搜索结果用 id，语义搜索结果用 knowledge_item_id）
    for item in items:
        if "knowledge_item_id" in item and "id" not in item:
            item["id"] = item["knowledge_item_id"]

    return {
        "items": items,
        "mode": "hybrid",
        "total": len(items),
    }


def merge_search_results(keyword_results: list, semantic_results: list) -> list:
    """合并关键词和语义搜索结果，去重后按 final_score 排序。

    同一 knowledge_item_id（关键词的 id = 语义的 knowledge_item_id）只保留一条。
    """
    merged = {}  # key: knowledge_item_id

    # 归一化关键词分数
    kw_max = max((r.get("score", 0) for r in keyword_results), default=1)
    for r in keyword_results:
        kid = r["id"]
        norm = r.get("score", 0) / kw_max if kw_max > 0 else 0
        merged[kid] = {
            **{k: r[k] for k in ["source_type", "source_id", "title", "content", "tags",
                                  "client_id", "project_id", "task_id"]},
            "id": kid,
            "keyword_score": round(r.get("score", 0), 4),
            "semantic_score": 0.0,
            "final_score": round(norm * 0.5, 4),
        }

    # 归一化语义分数并合并
    sem_max = max((r.get("semantic_score", 0) for r in semantic_results), default=1)
    for r in semantic_results:
        kid = r["knowledge_item_id"]
        norm = r.get("semantic_score", 0) / sem_max if sem_max > 0 else 0
        if kid in merged:
            merged[kid]["semantic_score"] = round(r.get("semantic_score", 0), 4)
            merged[kid]["final_score"] = round(
                merged[kid]["final_score"] + norm * 0.5, 4
            )
        else:
            merged[kid] = {
                "source_type": r["source_type"],
                "source_id": r["source_id"],
                "title": r["title"],
                "content": r.get("content", ""),
                "tags": r.get("tags", ""),
                "client_id": r.get("client_id"),
                "project_id": r.get("project_id"),
                "task_id": r.get("task_id"),
                "id": kid,
                "keyword_score": 0.0,
                "semantic_score": round(r.get("semantic_score", 0), 4),
                "final_score": round(norm * 0.5, 4),
            }

    results = deduplicate_results(list(merged.values()))
    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results


def normalize_score(score: float, score_type: str) -> float:
    """归一化分数（当前由 merge_search_results 内部处理，此为独立工具函数）。"""
    return round(score, 4)


def deduplicate_results(results: list) -> list:
    """按 source_type + source_id 去重，保留 final_score 最高的条目。"""
    seen = {}
    for r in results:
        key = (r.get("source_type", ""), r.get("source_id", 0))
        if key not in seen or r.get("final_score", 0) > seen[key].get("final_score", 0):
            seen[key] = r
    return list(seen.values())
