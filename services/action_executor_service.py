"""
AI 行动执行服务 — 执行 AI 建议的动作。
支持 create_task / create_project / create_client / create_timeline_event /
link_relation / risk_alert / generate_summary / tag_item / no_action
"""
import json
from services.workflow_log_service import add_workflow_log


def _resolve_client_id(client_name: str = None, description: str = "") -> int | None:
    """通过客户名称查找 client_id。找不到则返回 None。"""
    if not client_name:
        return None
    try:
        from services.client_service import search_clients
        matches = search_clients(keyword=client_name, limit=1)
        return matches[0]["id"] if matches else None
    except Exception:
        return None


def _resolve_project_id(project_name: str = None) -> int | None:
    """通过项目名称查找 project_id。找不到则返回 None。"""
    if not project_name:
        return None
    try:
        from services.project_service import search_projects
        matches = search_projects(keyword=project_name, limit=1)
        return matches[0]["id"] if matches else None
    except Exception:
        return None


def execute_action(action: dict, context_sources: list = None) -> dict:
    """执行一条 AI 建议的动作。

    Args:
        action: action dict，包含:
            - action_type: str
            - title: str
            - description: str
            - related_client_id: int | None
            - related_project_id: int | None
            - client_name: str | None (自动查找 ID)
            - project_name: str | None (自动查找 ID)
            - confidence: float
        context_sources: 保留兼容，暂未使用

    Returns:
        {success: bool, message: str, result_id: int | None}
    """
    action_type = action.get("action_type", "no_action")
    title = action.get("title", "")
    description = action.get("description", "")

    # 自动解析 client_name / project_name → ID
    related_client_id = action.get("related_client_id")
    related_project_id = action.get("related_project_id")
    if not related_client_id and action.get("client_name"):
        related_client_id = _resolve_client_id(action["client_name"], description)
    if not related_project_id and action.get("project_name"):
        related_project_id = _resolve_project_id(action["project_name"])

    try:
        if action_type == "create_task":
            return _execute_create_task(title, description, related_client_id,
                                        related_project_id, action)
        elif action_type == "create_project":
            return _execute_create_project(title, description, related_client_id)
        elif action_type == "create_client":
            return _execute_create_client(title, description, action)
        elif action_type == "create_timeline_event":
            return _execute_create_timeline_event(title, description,
                                                  related_client_id, related_project_id)
        elif action_type == "risk_alert":
            return _execute_risk_alert(title, description,
                                       related_client_id, related_project_id)
        elif action_type == "link_relation":
            return _execute_link_relation(action, context_sources)
        elif action_type == "generate_summary":
            return _execute_generate_summary(title, description)
        elif action_type == "tag_item":
            return _execute_tag_item(action)
        elif action_type == "create_note":
            return _execute_create_note(title, description)
        elif action_type == "update_project":
            return _execute_update_project(title, description, related_project_id, action)
        elif action_type == "update_client":
            return _execute_update_client(title, description, related_client_id, action)
        elif action_type == "no_action":
            return {"success": True, "message": "无需操作", "result_id": None}
        else:
            msg = f"未知的动作类型: {action_type}"
            _log_action(action_type, None, "error", msg, action)
            return {"success": False, "message": msg, "result_id": None}
    except Exception as e:
        msg = f"执行失败: {str(e)}"
        _log_action(action_type, None, "error", msg, action)
        return {"success": False, "message": msg, "result_id": None}


def _execute_create_task(title, description, client_id, project_id, action=None):
    from services.task_service import get_or_create_task

    priority = (action or {}).get("priority", "medium")
    due_date = (action or {}).get("due_date", "")

    result = get_or_create_task(
        title=title, description=description, priority=priority,
        due_date=due_date or "", project_id=project_id, client_id=client_id,
    )
    task_id = result["task_id"]
    created = result["created"]

    # 同步 embedding
    from services.knowledge_service import search_knowledge
    from services.embedding_service import upsert_embedding
    try:
        items = search_knowledge(source_type="task", limit=1)
        for item in items:
            if item.get("source_id") == task_id:
                upsert_embedding(item["id"])
                break
    except Exception:
        pass

    verb = "已创建" if created else "已存在"
    msg = f"任务「{title}」{verb}"
    _log_action("create_task", task_id, "success", msg, {"title": title, "task_id": task_id, "created": created})
    return {"success": True, "message": msg, "result_id": task_id}


def _execute_create_project(title, description, client_id):
    from services.project_service import get_or_create_project

    result = get_or_create_project(name=title, description=description, client_id=client_id)
    project_id = result["project_id"]
    created = result["created"]

    # 同步 embedding
    try:
        from services.knowledge_service import search_knowledge
        from services.embedding_service import upsert_embedding
        items = search_knowledge(source_type="project", limit=1)
        for item in items:
            if item.get("source_id") == project_id:
                upsert_embedding(item["id"])
                break
    except Exception:
        pass

    verb = "已创建" if created else "已存在"
    msg = f"项目「{title}」{verb}"
    _log_action("create_project", project_id, "success", msg,
                {"title": title, "project_id": project_id, "created": created})
    return {"success": True, "message": msg, "result_id": project_id}


def _execute_create_client(title, description, action=None):
    from services.client_service import get_or_create_client

    contact_info = (action or {}).get("contact_info", "")
    result = get_or_create_client(name=title, description=description, contact_info=contact_info)
    client_id = result["client_id"]
    created = result["created"]

    verb = "已创建" if created else "已存在"
    msg = f"客户「{title}」{verb}"
    _log_action("create_client", client_id, "success", msg,
                {"title": title, "client_id": client_id, "created": created})
    return {"success": True, "message": msg, "result_id": client_id}


def _execute_risk_alert(title, description, client_id, project_id):
    from services.timeline_service import add_event

    event_id = add_event(
        event_type="risk_alert",
        title=title,
        description=description,
        project_id=project_id,
        client_id=client_id,
        tags="风险提醒",
    )

    msg = f"风险提醒「{title}」已记录"
    _log_action("risk_alert", event_id, "success", msg,
                {"title": title, "event_id": event_id})
    return {"success": True, "message": msg, "result_id": event_id}


def _execute_create_timeline_event(title, description, client_id, project_id):
    from services.timeline_service import add_event

    event_id = add_event(
        event_type="manual",
        title=title,
        description=description,
        project_id=project_id,
        client_id=client_id,
    )

    msg = f"时间轴事件「{title}」已创建"
    _log_action("create_timeline_event", event_id, "success", msg, {"title": title, "event_id": event_id})
    return {"success": True, "message": msg, "result_id": event_id}


def _execute_link_relation(action, context_sources):
    source_type = action.get("source_type")
    source_id = action.get("source_id")
    target_type = action.get("target_type")
    target_id = action.get("target_id")
    description = action.get("description", "")

    # 尝试从 action 已有的字段推断
    if not source_type and not target_type:
        # 如果同时有 client_id 和 project_id，链接 project 到 client
        cid = action.get("related_client_id")
        pid = action.get("related_project_id")
        if cid and pid:
            source_type = "project"
            source_id = pid
            target_type = "client"
            target_id = cid

    if not source_type or not source_id or not target_type or not target_id:
        msg = "无法确定关联的实体，请手动建立关系"
        _log_action("link_relation", None, "error", msg, action)
        return {"success": False, "message": msg, "result_id": None}

    from services.relation_service import add_relation
    rel_id = add_relation(source_type, source_id, target_type, target_id,
                          relation_type="related_to", description=description)

    msg = f"已建立 {source_type}→{target_type} 的关联"
    _log_action("link_relation", rel_id, "success", msg, {
        "source_type": source_type, "source_id": source_id,
        "target_type": target_type, "target_id": target_id,
    })
    return {"success": True, "message": msg, "result_id": rel_id}


def _execute_generate_summary(title, description):
    from services.summary_service import create_daily_note

    content = f"AI 建议总结: {title}\n\n{description}"
    note_id = create_daily_note(content)

    msg = f"总结「{title}」已保存为随手记"
    _log_action("generate_summary", note_id, "success", msg, {"title": title, "note_id": note_id})
    return {"success": True, "message": msg, "result_id": note_id}


def _execute_tag_item(action):
    msg = "标签功能暂不支持自动执行"
    _log_action("tag_item", None, "error", msg, action)
    return {"success": False, "message": msg, "result_id": None}


def _execute_create_note(title, description):
    """创建随手记/笔记。"""
    from services.summary_service import create_daily_note
    content = f"{title}\n\n{description}" if description else title
    note_id = create_daily_note(content)
    msg = f"笔记「{title}」已保存"
    _log_action("create_note", note_id, "success", msg, {"title": title, "note_id": note_id})
    return {"success": True, "message": msg, "result_id": note_id}


def _execute_update_project(title, description, project_id, action=None):
    """更新项目状态并记录时间轴事件。"""
    from services.timeline_service import add_event

    event_id = None
    if project_id:
        try:
            from services.project_service import update_project
            status = (action or {}).get("params", {}).get("status", "")
            if status:
                update_project(project_id, status=status)
        except Exception:
            pass

        event_id = add_event(
            event_type="project_update",
            title=title,
            description=description,
            project_id=project_id,
        )

    msg = f"项目更新「{title}」已记录"
    _log_action("update_project", event_id, "success", msg,
                {"title": title, "project_id": project_id, "event_id": event_id})
    return {"success": True, "message": msg, "result_id": event_id}


def _execute_update_client(title, description, client_id, action=None):
    """更新客户跟进记录，写入时间轴。"""
    from services.timeline_service import add_event

    event_id = add_event(
        event_type="client_followup",
        title=title,
        description=description,
        client_id=client_id,
    )

    msg = f"客户跟进「{title}」已记录"
    _log_action("update_client", event_id, "success", msg,
                {"title": title, "client_id": client_id, "event_id": event_id})
    return {"success": True, "message": msg, "result_id": event_id}


def _log_action(action_type, result_id, status, message, action):
    try:
        add_workflow_log(
            workflow_type=f"action_{action_type}",
            source_type="ai_suggestion",
            source_id=result_id,
            status=status,
            message=message,
            details=json.dumps(action, ensure_ascii=False, default=str),
        )
    except Exception:
        pass
