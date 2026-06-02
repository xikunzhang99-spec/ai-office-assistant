from openai import OpenAI
from config.settings import AI_PROVIDER, AI_API_KEY, AI_BASE_URL, AI_MODEL


def _get_client():
    return OpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL)


def _chat(prompt: str, system_prompt: str = "You are a helpful AI office assistant.",
          temperature: float = 0.7, max_tokens: int = 2000) -> str:
    if not AI_API_KEY:
        return "[AI未配置] 请在 .env 中设置 AI_API_KEY"
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[AI调用失败] {str(e)}"


def summarize_file(content: str, filename: str) -> dict:
    prompt = f"""请分析以下文件内容，并按格式输出：

文件名：{filename}

文件内容：
{content}

请输出：
1. 摘要（200字以内）
2. 关键点（3-5条）
3. 标签（3-8个，用逗号分隔）
4. 后续任务建议（如有）"""

    result = _chat(prompt)
    return _parse_file_summary(result)


def _parse_file_summary(text: str) -> dict:
    summary = ""
    key_points = []
    tags = []
    suggestions = []
    current_section = None

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("1.") or line.startswith("摘要"):
            current_section = "summary"
            continue
        elif line.startswith("2.") or line.startswith("关键点"):
            current_section = "key_points"
            continue
        elif line.startswith("3.") or line.startswith("标签"):
            current_section = "tags"
            continue
        elif line.startswith("4.") or line.startswith("后续任务"):
            current_section = "suggestions"
            continue

        if current_section == "summary":
            summary += line
        elif current_section == "key_points":
            key_points.append(line.lstrip("-•* "))
        elif current_section == "tags":
            tags.extend([t.strip() for t in line.replace("，", ",").split(",") if t.strip()])
        elif current_section == "suggestions":
            suggestions.append(line.lstrip("-•* "))

    return {
        "summary": summary or text[:200],
        "key_points": key_points,
        "tags": tags[:8],
        "suggestions": suggestions,
    }


def extract_tags(content: str) -> list[str]:
    prompt = f"""请从以下内容中提取 3-8 个标签，用逗号分隔。只输出标签，不要其他内容。

内容：
{content}"""

    result = _chat(prompt)
    tags = [t.strip() for t in result.replace("，", ",").split(",")]
    return [t for t in tags if t][:8]


def generate_daily_summary(
    date_str: str,
    completed_tasks: list,
    new_tasks: list,
    files_list: list,
    notes: list,
    timeline_events: list,
) -> str:
    completed_text = "\n".join([f"- {t}" for t in completed_tasks]) or "无"
    new_text = "\n".join([f"- {t}" for t in new_tasks]) or "无"
    files_text = "\n".join([f"- {t}" for t in files_list]) or "无"
    notes_text = "\n".join([f"- {t}" for t in notes]) or "无"
    events_text = "\n".join([f"- {t}" for t in timeline_events]) or "无"

    prompt = f"""请根据以下数据生成 {date_str} 的工作总结：

## 今日完成任务
{completed_text}

## 今日新增任务
{new_text}

## 今日处理文件
{files_text}

## 今日随手记
{notes_text}

## 今日活动
{events_text}

请用Markdown格式输出，包含：
## 今日完成
## 今日重点
## 存在问题
## 明日建议"""

    return _chat(prompt)


def detect_content_intent(content: str) -> dict:
    """Detect the intent/type of content for workflow routing.

    Returns: {'intent_type': str, 'confidence': float, 'reasoning': str}
    intent_type: task, note, project_update, meeting, file_summary, daily_record, unknown
    """
    prompt = f"""Analyze the following content and classify it into EXACTLY ONE of these types:
- task: a specific action item, to-do, or assignment
- note: a general note, observation, or piece of information
- project_update: a project status update or progress report
- meeting: meeting notes, minutes, or discussion summary
- file_summary: a summary or analysis of a document/file
- daily_record: a daily journal or work log entry
- unknown: cannot confidently classify

Respond ONLY with a single line in this exact format:
TYPE|CONFIDENCE|BRIEF_REASON

Content:
{content[:2000]}"""

    result = _chat(prompt, "You are a content classifier. Respond with only the classification.",
                   temperature=0.2, max_tokens=100)
    try:
        parts = result.strip().split("|", 2)
        intent_type = parts[0].strip()
        confidence = float(parts[1].strip()) if len(parts) > 1 else 0.5
        reasoning = parts[2].strip() if len(parts) > 2 else ""
        valid_types = {"task", "note", "project_update", "meeting", "file_summary", "daily_record", "unknown"}
        if intent_type not in valid_types:
            intent_type = "unknown"
            confidence = 0.0
        return {"intent_type": intent_type, "confidence": confidence, "reasoning": reasoning}
    except Exception:
        return {"intent_type": "unknown", "confidence": 0.0, "reasoning": "Parse error"}
