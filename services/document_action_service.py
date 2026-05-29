"""
文档动作分析服务 — 基于文件内容生成结构化动作建议。
AI 只生成建议，不自动执行。用户确认后由 action_executor_service 执行。
"""
import json
import re
from services.workflow_log_service import add_workflow_log

# 内存缓存：file_id → 分析结果
_DOCUMENT_ANALYSIS_CACHE = {}

# 段落切分正则：匹配中英文标题
_SECTION_PATTERNS = [
    re.compile(r'^#{1,3}\s+(.+?)(?:\s*#{0,3})$', re.MULTILINE),          # Markdown headings
    re.compile(r'^[（(]?\s*(\d+)\s*[)）.、]\s*(.+)$', re.MULTILINE),     # 1. / (1) / 1、
    re.compile(r'^[一二三四五六七八九十]+[、.]\s*(.+)$', re.MULTILINE),    # 一、二、
    re.compile(r'^(第[一二三四五六七八九十\d]+[章节部分])\s*[：:]?\s*(.*)$', re.MULTILINE),  # 第X章
]


def split_document_sections(content: str) -> list:
    """将文档内容按标题切分为段落。

    Returns:
        [{section_id: int, title: str, content: str}]
    """
    if not content or not content.strip():
        return [{"section_id": 1, "title": "全文", "content": content or ""}]

    lines = content.split("\n")
    sections = []
    current_title = "概述"
    current_lines = []
    has_heading = False

    for line in lines:
        stripped = line.strip()
        matched = False
        for pattern in _SECTION_PATTERNS:
            m = pattern.match(stripped)
            if m:
                # 保存上一段落
                if has_heading:
                    sections.append({
                        "section_id": len(sections) + 1,
                        "title": current_title,
                        "content": "\n".join(current_lines).strip(),
                    })
                has_heading = True

                # 提取标题
                groups = m.groups()
                if len(groups) == 1:
                    current_title = groups[0]
                elif len(groups) == 2:
                    current_title = f"{groups[0]} {groups[1]}".strip()
                else:
                    current_title = stripped
                current_lines = []
                matched = True
                break
        if not matched:
            current_lines.append(line)

    # 保存最后一段
    sections.append({
        "section_id": len(sections) + 1,
        "title": current_title,
        "content": "\n".join(current_lines).strip(),
    })

    # 如果一个段落都没切出来，返回全文作为一段
    if not sections:
        sections.append({"section_id": 1, "title": "全文", "content": content})

    return sections


def get_cached_analysis(file_id: int) -> dict | None:
    """从内存缓存获取文件分析结果。"""
    return _DOCUMENT_ANALYSIS_CACHE.get(file_id)


def analyze_document_actions(file_id: int) -> dict:
    """分析文件内容，生成结构化动作建议。

    Args:
        file_id: files 表主键

    Returns:
        {document_summary, sections: [{section_id, title, content}],
         suggested_actions: [{action_type, title, description, ...}]}
    """
    # 检查缓存
    cached = get_cached_analysis(file_id)
    if cached:
        return cached

    from services.file_service import get_file
    from services.file_parser import parse_file
    from services.ai_service import _chat
    from services.client_service import get_all_clients
    from services.project_service import get_all_projects

    f = get_file(file_id)
    if not f:
        result = {"document_summary": "", "sections": [], "suggested_actions": []}
        add_workflow_log("document_action_analysis", "file", file_id, "error",
                         "文件不存在")
        return result

    # 读取文件内容
    content = ""
    if f.get("file_path") and f["file_path"]:
        try:
            content = parse_file(f["file_path"])
        except Exception:
            pass
    if not content and f.get("summary"):
        content = f["summary"]

    if not content:
        result = {"document_summary": f.get("summary", ""), "sections": [], "suggested_actions": []}
        add_workflow_log("document_action_analysis", "file", file_id, "error",
                         "无法读取文件内容")
        return result

    content = content[:8000]

    # 切分段落
    sections = split_document_sections(content)

    # 获取已有客户和项目供 AI 匹配
    try:
        clients = get_all_clients()
        client_names = [c["name"] for c in (clients or [])]
    except Exception:
        client_names = []

    try:
        projects = get_all_projects()
        project_names = [p["name"] for p in (projects or [])]
    except Exception:
        project_names = []

    # 调用 AI
    prompt = _build_analysis_prompt(content, f["filename"], sections, client_names, project_names)
    system = "你是一个办公文档分析助手。你只输出结构化 JSON，不输出其他内容。"
    try:
        ai_text = _chat(prompt, system, temperature=0.2, max_tokens=2000)
    except Exception as e:
        result = {"document_summary": f.get("summary", ""), "sections": sections,
                  "suggested_actions": []}
        add_workflow_log("document_action_analysis", "file", file_id, "error",
                         f"AI 调用失败: {str(e)[:200]}")
        return result

    result = _parse_analysis_json(ai_text)
    result["sections"] = sections  # override with actual sections

    # 缓存
    _DOCUMENT_ANALYSIS_CACHE[file_id] = result

    # 日志
    action_count = len(result.get("suggested_actions", []))
    add_workflow_log("document_action_analysis", "file", file_id, "success",
                     f"文档动作分析完成: {f['filename']} | {action_count} 条建议 "
                     f"| {len(sections)} 个段落")

    return result


def _build_analysis_prompt(content: str, filename: str, sections: list,
                            client_names: list, project_names: list) -> str:
    """构建 AI 分析 prompt。"""
    sections_text = ""
    for s in sections:
        sections_text += f"\n--- 第{s['section_id']}部分: {s['title']} ---\n{s['content'][:500]}\n"

    clients_text = ", ".join(client_names) if client_names else "（无已有客户）"
    projects_text = ", ".join(project_names) if project_names else "（无已有项目）"

    return f"""请分析以下文件内容，生成结构化动作建议。只输出 JSON，不要其他文字。

## 文件名
{filename}

## 已有客户（优先匹配，避免重复创建）
{clients_text}

## 已有项目（优先匹配，避免重复创建）
{projects_text}

## 文件内容概要
{content[:2000]}

## 文档分段
{sections_text[:3000]}

## 输出 JSON 格式
{{
  "document_summary": "文档整体摘要（200字以内）",
  "suggested_actions": [
    {{
      "action_type": "create_project | create_task | create_client | link_relation | create_timeline_event | risk_alert",
      "title": "动作标题（简洁）",
      "description": "为什么建议这个动作，来自文档哪部分",
      "priority": "high | medium | low",
      "confidence": 0.85,
      "source_section_id": 1,
      "client_name": null,
      "project_name": null,
      "due_date": null
    }}
  ]
}}

## 动作类型说明
- create_project: 文档描述了一个新项目 → 优先在已有项目中匹配 project_name，匹配不到再新建
- create_task: 文档中有明确待办事项/任务 → 关联到已有 project_name
- create_client: 文档涉及一个新客户/合作方 → 优先在已有客户中匹配 client_name
- link_relation: 需要建立项目与客户、文件与项目的关联
- create_timeline_event: 文档中有重要时间节点/里程碑/决策记录
- risk_alert: 文档中有风险点、延期可能、资源不足等信息

## 规则
1. client_name 和 project_name 优先从已有列表匹配，匹配不上才建议新建
2. confidence 取值 0-1，低于 0.6 的建议可以不放
3. 1-5 条建议即可，不要过多
4. source_section_id 用实际段落编号
5. 只输出 JSON"""


def _parse_analysis_json(text: str) -> dict:
    """解析 AI 返回的 JSON，容错处理。"""
    default = {"document_summary": "", "sections": [], "suggested_actions": []}

    text = text.strip()
    # 尝试提取 JSON 对象
    obj_match = re.search(r'\{.*\}', text, re.DOTALL)
    if obj_match:
        text = obj_match.group(0)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return default

    if not isinstance(data, dict):
        return default

    return {
        "document_summary": data.get("document_summary", ""),
        "sections": data.get("sections", []),
        "suggested_actions": data.get("suggested_actions", []),
    }
