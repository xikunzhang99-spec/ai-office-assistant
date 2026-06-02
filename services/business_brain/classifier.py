"""
classifier.py — 内容类型识别。
轻量级分类包装器，可独立调用或作为完整分析的一部分。
"""
from services.ai_service import _chat
from services.business_brain.prompts import BRAIN_ANALYSIS_SYSTEM

CLASSIFY_PROMPT = """分析以下内容，判断它属于哪种类型。

类型选项：task, note, project_update, client_update, meeting_note, file_summary, daily_record, idea, unknown

只输出一行，格式为：TYPE|CONFIDENCE

内容：
{content}"""

VALID_TYPES = {"task", "note", "project_update", "client_update", "meeting_note",
               "file_summary", "daily_record", "idea", "unknown"}


def classify_content(content: str) -> dict:
    """快速识别内容类型，不提取详细信息。

    Returns:
        {"content_type": str, "confidence": float}
    """
    prompt = CLASSIFY_PROMPT.format(content=content[:2000])
    result = _chat(prompt, BRAIN_ANALYSIS_SYSTEM, temperature=0.2, max_tokens=50)

    try:
        parts = result.strip().split("|", 1)
        content_type = parts[0].strip()
        confidence = float(parts[1].strip()) if len(parts) > 1 else 0.5
        if content_type not in VALID_TYPES:
            content_type = "unknown"
            confidence = 0.0
        return {"content_type": content_type, "confidence": confidence}
    except Exception:
        return {"content_type": "unknown", "confidence": 0.0}
