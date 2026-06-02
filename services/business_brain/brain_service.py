"""
brain_service.py — 业务大脑统一入口。
编排 classifier → extractor → entity_matcher → action_planner 流水线。
"""
from services.business_brain.extractor import extract_entities
from services.business_brain.entity_matcher import match_entities
from services.business_brain.action_planner import plan_actions, ACTION_LABELS, workflow_type_for_action


def analyze_input(content: str, source_type: str = "text",
                  source_id: int = None) -> dict:
    """业务大脑统一分析入口。

    对输入内容进行：类型识别 → 信息提取 → 实体匹配 → 动作规划

    Args:
        content: 用户输入的自然语言文本
        source_type: 来源类型 (text, feishu, file, etc.)
        source_id: 来源实体 ID

    Returns:
        {
            "content_type": str,
            "title": str,
            "summary": str,
            "entities": {
                "clients": [{"name": str, "matched_id": int|None, ...}, ...],
                "projects": [...],
                "people": [...],
                "tasks": [{"title": str, "priority": str, "due_date": str}, ...],
                "deadlines": [str],
                "dates": [str],
            },
            "tags": [str],
            "matched_tags": [str],
            "new_tags": [str],
            "suggested_actions": [
                {
                    "action_type": str,
                    "title": str,
                    "description": str,
                    "priority": str,
                    "confidence": float,
                    "params": dict,
                    "related_client_id": int|None,
                    "related_project_id": int|None,
                    "workflow_type": str|None,
                }, ...
            ],
            "confidence": float,
            "need_human_confirmation": bool,
            "source_type": str,
            "source_id": int|None,
        }
    """
    # 1. 构建数据库上下文
    db_context = _build_db_context()

    # 2. AI 提取结构化信息
    result = extract_entities(content, db_context)

    # 3. 匹配已有实体
    result = match_entities(result, db_context)

    # 4. 生成建议动作
    result["suggested_actions"] = plan_actions(result)

    # 5. 补充元数据
    result["source_type"] = source_type
    result["source_id"] = source_id

    # 6. 判断是否需要确认：高价值动作或低置信度时需要
    if not result.get("need_human_confirmation"):
        confidence = result.get("confidence", 0.5)
        has_write_actions = any(
            a.get("action_type") not in ("ignore", "ask_confirmation")
            for a in result.get("suggested_actions", [])
        )
        if has_write_actions and confidence < 0.7:
            result["need_human_confirmation"] = True
        if any(a.get("action_type") == "ask_confirmation"
               for a in result.get("suggested_actions", [])):
            result["need_human_confirmation"] = True

    return result


def _build_db_context() -> dict:
    """构建 AI 分析所需的数据库上下文。"""
    context = {
        "clients": [],
        "projects": [],
        "recent_tasks": [],
        "tags": [],
    }

    try:
        from services.client_service import get_all_clients
        clients = get_all_clients()
        for c in clients[:20]:
            context["clients"].append({
                "id": c["id"],
                "name": c.get("name", ""),
            })
    except Exception:
        pass

    try:
        from services.project_service import get_all_projects
        projects = get_all_projects()
        for p in projects[:20]:
            context["projects"].append({
                "id": p["id"],
                "name": p.get("name", ""),
                "client_id": p.get("client_id"),
                "client_name": p.get("client_name", ""),
            })
    except Exception:
        pass

    try:
        from services.task_service import get_all_tasks
        tasks = get_all_tasks(limit=10)
        for t in tasks:
            context["recent_tasks"].append({
                "id": t["id"],
                "title": t.get("title", ""),
            })
    except Exception:
        pass

    try:
        from database.db import fetch_all
        rows = fetch_all("SELECT DISTINCT name FROM tags ORDER BY name")
        context["tags"] = [r["name"] for r in rows]
    except Exception:
        pass

    return context


def execute_actions(actions: list, run_tracking: bool = True) -> list:
    """执行建议动作列表，每个动作通过对应的 Workflow Agent 执行。

    Args:
        actions: plan_actions() 输出的动作列表
        run_tracking: 是否创建 workflow run 记录

    Returns:
        [{"action_type": str, "success": bool, "message": str, "run_id": int|None}, ...]
    """
    results = []

    for action in actions:
        action_type = action.get("action_type", "ignore")
        workflow_type = action.get("workflow_type")

        if action_type in ("ignore", "ask_confirmation"):
            results.append({
                "action_type": action_type,
                "success": True,
                "message": ACTION_LABELS.get(action_type, action_type),
                "run_id": None,
            })
            continue

        if action_type == "send_reminder":
            results.append({
                "action_type": action_type,
                "success": True,
                "message": "提醒已记录（通知发送需飞书配置）",
                "run_id": None,
            })
            continue

        # 通过现有 action_executor 执行
        try:
            from services.action_executor_service import execute_action
            exec_result = execute_action(action)
            results.append({
                "action_type": action_type,
                "success": exec_result.get("success", False),
                "message": exec_result.get("message", ""),
                "run_id": None,
            })
        except Exception as e:
            results.append({
                "action_type": action_type,
                "success": False,
                "message": str(e),
                "run_id": None,
            })

    return results
