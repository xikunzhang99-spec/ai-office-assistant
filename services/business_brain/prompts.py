"""
prompts.py — 业务大脑提示词模板。
统一管理所有 AI 分析提示词，方便调整和版本管理。
"""

BRAIN_ANALYSIS_SYSTEM = """你是一个智能办公助理的业务理解引擎。你的任务是根据用户输入，输出结构化的 JSON 分析结果。

你必须严格遵循以下规则：
1. 只输出 JSON，不要输出任何其他文字、解释或 markdown。
2. 所有字段必须填写，不允许省略。
3. 日期统一使用 YYYY-MM-DD 格式。
4. 如果无法确定某个字段，使用空字符串、空数组或 null。
5. 从提供的数据库上下文中匹配已有客户和项目，不要编造。
6. 生成的 suggested_actions 必须具体可执行。"""

BRAIN_ANALYSIS_PROMPT = """请分析以下用户输入，输出结构化 JSON。

## 内容类型（9选1）
task: 具体任务或待办事项
note: 普通笔记或观察
project_update: 项目状态更新或进展报告
client_update: 客户跟进记录或客户动态
meeting_note: 会议纪要或讨论记录
file_summary: 文件或文档摘要
daily_record: 日常工作记录
idea: 想法或灵感
unknown: 无法判断

## 数据库上下文（已有实体）
已有客户：
{clients_context}

已有项目：
{projects_context}

已有标签：
{tags_context}

## 可用的建议动作类型
- create_task: 创建任务
- create_note: 创建笔记/随手记
- update_project: 更新项目状态
- update_client: 更新客户信息/跟进记录
- create_timeline: 写入时间轴
- create_summary: 生成每日总结
- send_reminder: 发送提醒
- ask_confirmation: 需要人工确认
- ignore: 无需操作

## 用户输入
{content}

## 输出格式
严格按照以下 JSON 结构输出，不要省略任何字段：

```json
{{
  "content_type": "task|note|project_update|client_update|meeting_note|file_summary|daily_record|idea|unknown",
  "title": "简短标题（15字以内）",
  "summary": "一句话总结（50字以内）",
  "entities": {{
    "clients": [{{"name": "客户名"}}],
    "projects": [{{"name": "项目名"}}],
    "people": [{{"name": "人名", "role": "角色"}}],
    "tasks": [{{"title": "任务标题", "priority": "high|medium|low", "due_date": "YYYY-MM-DD或空"}}],
    "deadlines": ["YYYY-MM-DD"],
    "dates": ["YYYY-MM-DD"]
  }},
  "tags": ["标签1", "标签2"],
  "suggested_actions": [
    {{
      "action_type": "create_task|create_note|update_project|update_client|create_timeline|create_summary|send_reminder|ask_confirmation|ignore",
      "title": "动作标题",
      "description": "动作描述",
      "priority": "high|medium|low",
      "confidence": 0.85,
      "params": {{}}
    }}
  ],
  "confidence": 0.8,
  "need_human_confirmation": false
}}
```

请基于用户输入和数据库上下文，仔细分析并输出 JSON："""


def build_analysis_prompt(content: str, clients_context: str, projects_context: str,
                          tags_context: str) -> str:
    """构建完整的分析提示词。"""
    return BRAIN_ANALYSIS_PROMPT.format(
        content=content[:3000],
        clients_context=clients_context or "无",
        projects_context=projects_context or "无",
        tags_context=tags_context or "无",
    )
