"""
action_planner.py — 建议动作生成。
将提取结果中的实体信息转换为可执行的建议动作列表。
"""

# 动作类型 → 工作流类型映射
ACTION_TO_WORKFLOW = {
    "create_task": "task_creation",
    "create_note": "note_creation",
    "update_project": "project_update",
    "update_client": "client_update",
    "create_timeline": "timeline_record",
    "create_summary": "summary_creation",
    # send_reminder, ask_confirmation, ignore 没有对应工作流
}

ACTION_LABELS = {
    "create_task": "创建任务",
    "create_note": "创建笔记",
    "update_project": "更新项目",
    "update_client": "更新客户",
    "create_timeline": "写入时间轴",
    "create_summary": "生成总结",
    "send_reminder": "发送提醒",
    "ask_confirmation": "人工确认",
    "ignore": "无需操作",
}


def workflow_type_for_action(action_type: str) -> str | None:
    """获取动作类型对应的工作流类型。"""
    return ACTION_TO_WORKFLOW.get(action_type)


def plan_actions(extracted: dict) -> list:
    """基于提取结果生成建议动作列表。

    Args:
        extracted: 已匹配实体的分析结果

    Returns:
        [{"action_type": str, "title": str, "description": str,
          "related_client_id": int|None, "related_project_id": int|None,
          "confidence": float, "priority": str, "params": dict,
          "workflow_type": str|None}, ...]
    """
    actions = extracted.get("suggested_actions", [])
    if not actions:
        return _generate_default_actions(extracted)

    enriched = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = action.get("action_type", "ignore")

        # 补充关联 ID
        client_id = _resolve_client_id(action, extracted)
        project_id = _resolve_project_id(action, extracted)

        enriched.append({
            "action_type": action_type,
            "title": action.get("title", ""),
            "description": action.get("description", ""),
            "priority": action.get("priority", "medium"),
            "confidence": float(action.get("confidence", 0.5) or 0.5),
            "params": action.get("params", {}) or {},
            "related_client_id": client_id,
            "related_project_id": project_id,
            "workflow_type": workflow_type_for_action(action_type),
        })

    return enriched


def _resolve_client_id(action: dict, extracted: dict) -> int | None:
    """解析动作中的客户 ID。"""
    # 从 action 的 params 中查找
    params = action.get("params", {}) or {}
    if params.get("client_id"):
        return params["client_id"]

    # 从已匹配的 entities 中查找
    entities = extracted.get("entities", {})
    clients = entities.get("clients", [])
    for c in clients:
        if c.get("matched_id"):
            return c["matched_id"]

    return None


def _resolve_project_id(action: dict, extracted: dict) -> int | None:
    """解析动作中的项目 ID。"""
    params = action.get("params", {}) or {}
    if params.get("project_id"):
        return params["project_id"]

    entities = extracted.get("entities", {})
    projects = entities.get("projects", [])
    for p in projects:
        if p.get("matched_id"):
            return p["matched_id"]

    return None


def _generate_default_actions(extracted: dict) -> list:
    """当 AI 没有生成建议动作时，根据内容类型生成默认动作。"""
    content_type = extracted.get("content_type", "unknown")
    entities = extracted.get("entities", {})

    client_id = None
    project_id = None
    for c in entities.get("clients", []):
        if c.get("matched_id"):
            client_id = c["matched_id"]
            break
    for p in entities.get("projects", []):
        if p.get("matched_id"):
            project_id = p["matched_id"]
            break

    default_map = {
        "task": [{"action_type": "create_task", "title": extracted.get("title", "新任务"),
                  "description": extracted.get("summary", ""), "priority": "medium"}],
        "note": [{"action_type": "create_note", "title": extracted.get("title", "新笔记"),
                  "description": extracted.get("summary", "")}],
        "project_update": [{"action_type": "update_project", "title": extracted.get("title", "项目更新"),
                            "description": extracted.get("summary", "")},
                           {"action_type": "create_timeline", "title": extracted.get("title", "时间轴记录"),
                            "description": extracted.get("summary", "")}],
        "client_update": [{"action_type": "update_client", "title": extracted.get("title", "客户更新"),
                           "description": extracted.get("summary", "")},
                          {"action_type": "create_timeline", "title": extracted.get("title", "跟进记录"),
                           "description": extracted.get("summary", "")}],
        "meeting_note": [{"action_type": "create_note", "title": extracted.get("title", "会议记录"),
                          "description": extracted.get("summary", "")},
                         {"action_type": "create_timeline", "title": extracted.get("title", "会议记录"),
                          "description": extracted.get("summary", "")}],
        "daily_record": [{"action_type": "create_note", "title": extracted.get("title", "日常记录"),
                          "description": extracted.get("summary", "")}],
        "idea": [{"action_type": "create_note", "title": extracted.get("title", "想法记录"),
                  "description": extracted.get("summary", "")}],
        "file_summary": [{"action_type": "create_note", "title": extracted.get("title", "文件摘要"),
                          "description": extracted.get("summary", "")}],
    }

    defaults = default_map.get(content_type, [{"action_type": "ignore", "title": "无需操作",
                                                "description": "无法识别内容类型"}])
    result = []
    for d in defaults:
        result.append({
            "action_type": d.get("action_type", "ignore"),
            "title": d.get("title", ""),
            "description": d.get("description", ""),
            "priority": d.get("priority", "medium"),
            "confidence": 0.5,
            "params": {},
            "related_client_id": client_id,
            "related_project_id": project_id,
            "workflow_type": workflow_type_for_action(d.get("action_type", "")),
        })
    return result
