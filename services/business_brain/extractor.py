"""
extractor.py — 关键信息提取。
通过单次 AI 调用，从自然语言内容中提取结构化信息。
"""
import json
import re
from services.ai_service import _chat
from services.business_brain.prompts import (
    BRAIN_ANALYSIS_SYSTEM, build_analysis_prompt
)

# 默认空结果
EMPTY_RESULT = {
    "content_type": "unknown",
    "title": "",
    "summary": "",
    "entities": {
        "clients": [],
        "projects": [],
        "people": [],
        "tasks": [],
        "deadlines": [],
        "dates": [],
    },
    "tags": [],
    "suggested_actions": [],
    "confidence": 0.0,
    "need_human_confirmation": False,
}


def extract_entities(content: str, db_context: dict) -> dict:
    """从内容中提取所有结构化信息。

    Args:
        content: 用户输入的自然语言文本
        db_context: {"clients": [...], "projects": [...], "tags": [...]}

    Returns:
        完整的结构化分析结果 dict
    """
    clients_context = _format_clients(db_context.get("clients", []))
    projects_context = _format_projects(db_context.get("projects", []))
    tags_context = _format_tags(db_context.get("tags", []))

    prompt = build_analysis_prompt(content, clients_context, projects_context, tags_context)
    result = _chat(prompt, BRAIN_ANALYSIS_SYSTEM, temperature=0.2, max_tokens=2000)

    return _parse_json_response(result)


def _format_clients(clients: list) -> str:
    if not clients:
        return "无"
    lines = []
    for c in clients[:20]:
        lines.append(f"- id={c['id']} {c['name']}")
    return "\n".join(lines)


def _format_projects(projects: list) -> str:
    if not projects:
        return "无"
    lines = []
    for p in projects[:20]:
        client_info = f" (客户: {p['client_name']})" if p.get("client_name") else ""
        lines.append(f"- id={p['id']} {p['name']}{client_info}")
    return "\n".join(lines)


def _format_tags(tags: list) -> str:
    if not tags:
        return "无"
    return ", ".join(tags[:50])


def _parse_json_response(text: str) -> dict:
    """从 AI 响应中解析 JSON，带容错回退。"""
    try:
        # 尝试直接解析
        return _validate_and_fix(json.loads(text))
    except json.JSONDecodeError:
        pass

    # 尝试提取 JSON 块
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        try:
            return _validate_and_fix(json.loads(json_match.group()))
        except json.JSONDecodeError:
            pass

    return EMPTY_RESULT


def _validate_and_fix(data: dict) -> dict:
    """确保返回结果包含所有必需字段。"""
    result = EMPTY_RESULT.copy()
    if not isinstance(data, dict):
        return result

    result["content_type"] = data.get("content_type", "unknown")
    result["title"] = data.get("title", "") or ""
    result["summary"] = data.get("summary", "") or ""
    result["confidence"] = float(data.get("confidence", 0.5) or 0.5)
    result["need_human_confirmation"] = bool(data.get("need_human_confirmation", False))
    result["tags"] = data.get("tags", []) or []
    result["suggested_actions"] = data.get("suggested_actions", []) or []

    entities = data.get("entities", {}) or {}
    if isinstance(entities, dict):
        result["entities"]["clients"] = entities.get("clients", []) or []
        result["entities"]["projects"] = entities.get("projects", []) or []
        result["entities"]["people"] = entities.get("people", []) or []
        result["entities"]["tasks"] = entities.get("tasks", []) or []
        result["entities"]["deadlines"] = entities.get("deadlines", []) or []
        result["entities"]["dates"] = entities.get("dates", []) or []

    return result
