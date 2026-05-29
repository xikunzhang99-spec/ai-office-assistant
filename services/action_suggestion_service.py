"""
AI 行动建议服务 — 根据 AI 问答结果生成下一步建议动作。
Phase 10 第一版：只生成建议，不自动执行。
"""
import json
import re
from services.ai_service import _chat


ACTION_TYPES = [
    "create_task",
    "create_timeline_event",
    "link_relation",
    "generate_summary",
    "tag_item",
    "no_action",
]

ACTION_LABELS = {
    "create_task": "创建任务",
    "create_timeline_event": "写入时间轴",
    "link_relation": "建立关系",
    "generate_summary": "生成总结",
    "tag_item": "添加标签",
    "no_action": "无需操作",
}


def suggest_actions(question: str, answer: str, sources: list) -> list:
    """根据问答结果生成 AI 行动建议。

    sources: RAG 返回的 sources 列表，每项含 source_type, source_id, title 等。
    返回: [{action_type, title, description, related_client_id, related_project_id, confidence}]
    """
    if not sources:
        return []

    # 构建来源摘要
    sources_text = _format_sources_for_prompt(sources)

    prompt = f"""根据以下 AI 问答结果，生成 1-3 条下一步建议动作。只输出 JSON 数组，不要其他文字。

## 用户问题
{question}

## AI 回答
{answer[:500]}

## 参考来源
{sources_text}

## 可选动作类型
- create_task: 建议创建一个新任务
- create_timeline_event: 建议写入时间轴记录
- link_relation: 建议建立关系（如关联项目到客户）
- generate_summary: 建议生成一份总结
- tag_item: 建议添加标签
- no_action: 当前无需任何操作

## 输出 JSON 格式
[
  {{
    "action_type": "create_task",
    "title": "建议动作标题（简洁）",
    "description": "为什么建议这个动作",
    "related_client_id": null,
    "related_project_id": null,
    "confidence": 0.8
  }}
]

## 规则
- related_client_id 和 related_project_id 从参考来源中提取实际存在的 id，没有则填 null
- confidence 取值 0-1，表示建议的置信度
- 如果当前信息充足无需操作，返回 [{{"action_type": "no_action", ...}}]
- 只输出 JSON 数组"""

    result = _chat(prompt, "你是一个办公助理行动建议分析器。只输出 JSON 数组。", temperature=0.2, max_tokens=600)
    return _parse_actions_json(result)


def _format_sources_for_prompt(sources: list) -> str:
    """将 sources 格式化为 prompt 可读文本。"""
    lines = []
    for s in sources[:10]:
        stype = s.get("source_type", "")
        sid = s.get("source_id", "")
        title = s.get("title", "")
        lines.append(f"- [{stype}] id={sid} {title}")
    return "\n".join(lines) if lines else "（无）"


def _parse_actions_json(text: str) -> list:
    """解析 AI 返回的 JSON 数组。"""
    text = text.strip()
    arr_match = re.search(r'\[.*\]', text, re.DOTALL)
    if arr_match:
        text = arr_match.group(0)
    try:
        actions = json.loads(text)
        if isinstance(actions, list):
            return actions
    except json.JSONDecodeError:
        pass
    return []
