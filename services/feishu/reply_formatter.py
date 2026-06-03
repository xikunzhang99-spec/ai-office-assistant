"""
reply_formatter.py — 飞书回复统一格式化模块。
所有飞书回复文本必须通过此模块生成，确保风格一致、简洁、适合手机阅读。
"""
import re
from config.settings import (
    FEISHU_REPLY_STYLE,
    FEISHU_REPLY_MAX_ITEMS,
    FEISHU_REPLY_MAX_SUMMARY_LENGTH,
    FEISHU_ENABLE_EMOJI,
    FEISHU_SHOW_DEBUG,
)

# ── Emoji Map ──
_EMOJI = {
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "task": "📌",
    "project": "📁",
    "client": "👤",
    "file": "📄",
    "time": "⏰",
    "tag": "🏷️",
    "search": "🔍",
    "brain": "🧠",
    "next": "➡️",
    "pending": "📝",
    "summary": "📝",
    "key_point": "🔑",
    "source": "📚",
    "priority_high": "🔴",
    "priority_medium": "🟡",
    "priority_low": "🟢",
    "risk": "🚨",
    "reminder": "🔔",
}


def _e(key: str) -> str:
    """返回 emoji 或空字符串（取决于配置）。"""
    if not FEISHU_ENABLE_EMOJI:
        return ""
    return _EMOJI.get(key, "")


def _s(text: str) -> str:
    """截断摘要文本。"""
    if not text:
        return ""
    text = str(text)
    if len(text) <= FEISHU_REPLY_MAX_SUMMARY_LENGTH:
        return text
    return text[:FEISHU_REPLY_MAX_SUMMARY_LENGTH] + "..."


def _n(items: list, max_n: int = None) -> list:
    """限制列表项数量。"""
    if max_n is None:
        max_n = FEISHU_REPLY_MAX_ITEMS
    return items[:max_n]


def _sanitize_error(error) -> str:
    """清理错误信息，移除 traceback、JSON、内部 ID 等调试信息。"""
    msg = str(error)

    # 移除 Python traceback
    msg = re.sub(r'Traceback\s*\(most recent call last\):.*', '', msg, flags=re.DOTALL)
    msg = re.sub(r'File\s*".*?",\s*line\s*\d+.*?\n', '', msg)
    msg = re.sub(r'\w+Error:\s*', '', msg)

    # 移除 JSON 块
    msg = re.sub(r'\{[^{}]*"(?:workflow_type|run_id|step_id|source_type|source_id|traceback)"[^{}]*\}', '', msg)
    msg = re.sub(r'\[AI调用失败\]\s*', '', msg)

    # 移除 URL
    msg = re.sub(r'https?://\S+', '', msg)

    msg = msg.strip()

    if not msg:
        return "系统暂时处理失败"

    # 截断
    if len(msg) > 200:
        msg = msg[:200] + "..."

    return msg


def _build(lines: list) -> str:
    """将行列表组装成最终回复文本。"""
    # 过滤空行和 None
    cleaned = []
    for line in lines:
        if line is None:
            continue
        line = str(line).strip()
        if line:
            cleaned.append(line)

    text = "\n".join(cleaned)

    # 全局长度限制（飞书文本消息建议不超过 2000 字符）
    if len(text) > 1800:
        text = text[:1800] + "\n...(内容已精简)"

    return text


# ── Public Formatting Functions ──

def format_task_created(result: dict) -> str:
    """格式化任务创建成功回复。"""
    lines = [
        f"{_e('success')} 已创建任务",
        "",
        f"{_e('task')} {result.get('title', '')}",
    ]
    if result.get("due_date"):
        lines.append(f"{_e('time')} 截止时间：{result['due_date']}")
    if result.get("priority"):
        p_key = f"priority_{result['priority']}" if result['priority'] in ("high", "medium", "low") else ""
        p_emoji = _e(p_key) if p_key else ""
        lines.append(f"{p_emoji} 优先级：{result['priority']}")
    if result.get("project_name"):
        lines.append(f"{_e('project')} 关联项目：{result['project_name']}")
    if result.get("client_name"):
        lines.append(f"{_e('client')} 关联客户：{result['client_name']}")
    return _build(lines)


def format_project_updated(result: dict) -> str:
    """格式化项目更新成功回复。"""
    lines = [
        f"{_e('success')} 已更新项目进展",
        "",
        f"{_e('project')} 项目：{result.get('project_name', result.get('title', ''))}",
    ]
    if result.get("summary"):
        lines.append(f"{_e('summary')} 进展：{_s(result['summary'])}")
    if result.get("next_step"):
        lines.append(f"{_e('next')} 下一步：{result['next_step']}")
    return _build(lines)


def format_client_updated(result: dict) -> str:
    """格式化客户跟进成功回复。"""
    lines = [
        f"{_e('success')} 已记录客户跟进",
        "",
        f"{_e('client')} 客户：{result.get('client_name', result.get('title', ''))}",
    ]
    if result.get("summary"):
        lines.append(f"{_e('summary')} 重点：{_s(result['summary'])}")
    if result.get("next_task"):
        lines.append(f"{_e('next')} 后续任务：{result['next_task']}")
    return _build(lines)


def format_file_processed(result: dict) -> str:
    """格式化文件处理完成回复。"""
    lines = [
        f"{_e('success')} 文件已处理",
        "",
        f"{_e('file')} 文件：{result.get('filename', '')}",
    ]
    if result.get("summary"):
        lines.append(f"{_e('summary')} 摘要：{_s(result['summary'])}")

    tags = result.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    if tags:
        lines.append(f"{_e('tag')} 标签：{', '.join(_n(tags, 5))}")

    matched = result.get("matched", {})
    if matched:
        if matched.get("client_name"):
            lines.append(f"{_e('client')} 关联客户：{matched['client_name']}")
        if matched.get("project_name"):
            lines.append(f"{_e('project')} 关联项目：{matched['project_name']}")

    # 文档动作建议（限 3 条）
    doc_actions = result.get("doc_actions", [])
    if doc_actions:
        lines.append("")
        lines.append(f"{_e('next')} 建议操作：")
        for a in _n(doc_actions, 3):
            atype = a.get("action_type", "")
            atype_cn = {
                "create_task": "创建任务", "create_project": "创建项目",
                "create_client": "创建客户", "create_timeline_event": "写入时间轴",
                "risk_alert": "风险提醒", "link_relation": "建立关联",
            }.get(atype, atype)
            lines.append(f"  - {atype_cn}：{a.get('title', '')}")

    return _build(lines)


def format_rag_answer(result: dict) -> str:
    """格式化 RAG 问答回复。"""
    item_count = result.get("item_count", len(result.get("sources", [])))

    if item_count == 0:
        return _build([
            f"{_e('warning')} 资料不足",
            "",
            "知识库中没有找到相关信息。",
            "建议：尝试其他关键词，或先在「数据管理」中执行知识入库。",
        ])

    lines = [
        f"{_e('search')} 查询结果",
        "",
        _s(result.get("answer", "无法回答")),
    ]

    sources = result.get("sources", [])
    if sources:
        lines.append("")
        lines.append(f"{_e('source')} 来源：")
        for src in _n(sources, 3):
            title = src.get("source_title", src.get("title", "未知"))
            stype = src.get("source_type", "")
            type_label = {
                "project": "项目", "project_timeline": "时间轴",
                "daily_summary": "总结", "daily_note": "笔记",
                "obsidian_note": "笔记", "client": "客户",
                "task": "任务", "file": "文件",
            }.get(stype, stype)
            lines.append(f"  - [{type_label}] {title}")

    return _build(lines)


def format_pending_confirmation(result: dict) -> str:
    """格式化等待确认回复。"""
    lines = [
        f"{_e('pending')} 已生成预览，等待确认",
        "",
        f"{_e('summary')} 内容：{_s(result.get('summary', ''))}",
    ]

    tags = result.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    if tags:
        lines.append(f"{_e('tag')} 标签：{', '.join(_n(tags, 5))}")

    lines.append(f"{_e('next')} 请到系统后台确认写入")
    return _build(lines)


def format_error(error, suggestion: str = "") -> str:
    """格式化错误回复。用户只看到简短原因和建议。"""
    reason = _sanitize_error(error)
    lines = [
        f"{_e('error')} 处理失败",
        "",
        f"原因：{reason[:150]}",
    ]
    if suggestion:
        lines.append(f"建议：{suggestion}")
    else:
        lines.append("建议：请稍后重试，或联系管理员。")
    return _build(lines)


def format_unknown_input() -> str:
    """格式化无法识别的输入回复。"""
    return _build([
        f"{_e('warning')} 我还不确定要怎么处理这段内容",
        "",
        "你可以补充说明：",
        "  - 这是任务",
        "  - 这是项目进展",
        "  - 这是客户记录",
        "  - 这是普通笔记",
    ])


def format_success(result: dict) -> str:
    """格式化通用成功回复。"""
    message = result.get("message", result.get("title", "操作完成"))
    lines = [
        f"{_e('success')} {message}",
    ]
    if result.get("detail"):
        lines.append(_s(str(result["detail"])))
    return _build(lines)


def format_help() -> str:
    """格式化帮助信息。"""
    return _build([
        f"{_e('info')} AI 办公助理",
        "",
        "查询：",
        "  /任务 今天 / 逾期 / 未来3天",
        "  /总结 今天",
        "  /问 xxx",
        "",
        "创建：",
        "  /新任务 / 新项目 / 新客户",
        "",
        "建议：",
        "  /今日建议 / 项目建议 / 客户建议",
        "",
        "状态：",
        "  /项目状态 / 客户状态 / 项目风险",
        "",
        "发送 /帮助 查看此信息",
    ])


def format_task_list(tasks: list, list_type: str = "today") -> str:
    """格式化任务列表回复。"""
    type_labels = {
        "today": f"{_e('time')} 今日任务",
        "overdue": f"{_e('warning')} 逾期任务",
        "upcoming": f"{_e('time')} 即将到期",
    }
    header = type_labels.get(list_type, "任务列表")

    if not tasks:
        return _build([f"{_e('success')} {header}：无"])

    lines = [header]
    for t in _n(tasks):
        title = t.get("title", "")
        due = t.get("due_date", "")
        line = f"  {_e('task')} {title}"
        if due:
            line += f" — {due[:10]}"
        lines.append(line)

    return _build(lines)


def format_status(result: dict) -> str:
    """格式化项目/客户状态回复。"""
    lines = []

    if result.get("project_name"):
        lines.append(f"{_e('project')} 项目：{result['project_name']}")

    if result.get("client_name"):
        lines.append(f"{_e('client')} 客户：{result['client_name']}")

    if result.get("current_stage"):
        lines.append(f"当前阶段：{result['current_stage']}")

    if result.get("progress"):
        lines.append(f"进度：{result['progress']}")

    tasks = result.get("remaining_tasks", [])
    if tasks:
        lines.append(f"剩余任务：{len(tasks)} 项")

    risks = result.get("risks", [])
    if risks:
        lines.append("")
        lines.append(f"{_e('risk')} 风险：")
        for r in _n(risks, 3):
            lines.append(f"  - {r.get('description', str(r))}")

    return _build(lines)


def format_suggestions(result: dict) -> str:
    """格式化建议列表回复。"""
    lines = [f"{_e('info')} 建议"]

    summary = result.get("summary", result.get("ai_summary", ""))
    if summary:
        lines.append(_s(str(summary)))

    items = result.get("items", result.get("suggestions", []))
    if items:
        lines.append("")
        for i, item in enumerate(_n(items)):
            title = item.get("title", str(item)) if isinstance(item, dict) else str(item)
            lines.append(f"  {i+1}. {title}")

    return _build(lines)


def format_confirmation(result: dict) -> str:
    """格式化确认/执行结果回复。"""
    success_count = result.get("success_count", 0)
    fail_count = result.get("fail_count", 0)
    total = success_count + fail_count

    if fail_count == 0:
        lines = [f"{_e('success')} 全部完成（{total} 项）"]
    else:
        lines = [f"{_e('warning')} 完成 {success_count}/{total} 项"]

    items = result.get("items", [])
    for item in _n(items):
        icon = _e("success") if item.get("success") else _e("error")
        msg = item.get("message", "")[:60]
        lines.append(f"  {icon} {msg}")

    return _build(lines)
