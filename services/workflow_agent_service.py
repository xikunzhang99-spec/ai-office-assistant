"""
工作流代理服务 — 统一入口，编排调用各子服务，生成综合业务状态分析。
"""
from utils.date_utils import today_str
from services.workflow_log_service import add_workflow_log


def analyze_business_state() -> dict:
    """综合业务状态分析 — 一次性获取全局业务视图。

    Returns: {
        "analyzed_at": str,
        "overall_health": "good" | "warning" | "critical",
        "summary": str,
        "risks": {"total": int, "high": int, "medium": int, "low": int,
                  "project_risks": [...], "client_risks": [...], "task_risks": [...]},
        "suggestions": {"priority_tasks": [...], "clients_to_follow": [...],
                        "overdue_items": [...]},
        "relations": {"risk_relations": [...], "follow_up_relations": [...]},
        "projects_summary": [{"project_id": int, "project_name": str, ...}, ...],
        "clients_summary": [{"client_id": int, "client_name": str, ...}, ...],
    }
    """
    from services.risk_detection_service import (
        detect_project_risks as risk_project,
        detect_client_risks as risk_client,
        detect_task_risks as risk_task,
    )
    from services.proactive_suggestion_service import generate_daily_suggestions
    from services.relation_service import find_risk_relations, find_follow_up_relations
    from database.db import fetch_all

    result = {
        "analyzed_at": today_str(),
        "overall_health": "good",
        "summary": "",
        "risks": {
            "total": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "project_risks": [],
            "client_risks": [],
            "task_risks": [],
        },
        "suggestions": {},
        "relations": {},
        "projects_summary": [],
        "clients_summary": [],
    }

    # 1. 风险检测
    project_risks = risk_project()
    client_risks = risk_client()
    task_risks = risk_task()

    result["risks"]["project_risks"] = project_risks
    result["risks"]["client_risks"] = client_risks
    result["risks"]["task_risks"] = task_risks

    all_risk_items = project_risks + client_risks + task_risks
    result["risks"]["total"] = len(all_risk_items)
    for r in all_risk_items:
        level = r.get("risk_level", "low")
        result["risks"][level] = result["risks"].get(level, 0) + 1

    # 2. 主动建议
    suggestions = generate_daily_suggestions()
    result["suggestions"] = {
        "priority_tasks": suggestions.get("priority_tasks", []),
        "clients_to_follow": suggestions.get("clients_to_follow", []),
        "overdue_items": suggestions.get("overdue_items", []),
        "project_risks": suggestions.get("project_risks", []),
        "pending_document_actions": suggestions.get("pending_document_actions", []),
    }

    # 3. 关系
    result["relations"]["risk_relations"] = find_risk_relations()
    result["relations"]["follow_up_relations"] = find_follow_up_relations()

    # 4. 项目摘要
    projects = fetch_all("SELECT * FROM projects ORDER BY status, created_at DESC")
    for p in projects:
        p_risks = [r for r in project_risks if r.get("project_id") == p["id"]]
        p_tasks = fetch_all(
            "SELECT COUNT(*) as cnt FROM tasks WHERE project_id = ? AND status IN ('todo', 'doing')",
            (p["id"],),
        )
        pending_tasks = p_tasks[0]["cnt"] if p_tasks else 0

        # 尝试获取阶段进度
        try:
            from services.workflow_engine import get_project_progress, get_current_stage
            progress = get_project_progress(p["id"])
            stage_name = progress.get("active_stage", {}).get("stage_name") or None
            progress_pct = progress.get("stage_completion_pct", 0)
        except Exception:
            stage_name = None
            progress_pct = 0

        result["projects_summary"].append({
            "project_id": p["id"],
            "project_name": p["name"],
            "status": p["status"],
            "client_id": p.get("client_id"),
            "progress_pct": progress_pct,
            "current_stage": stage_name,
            "risk_count": len(p_risks),
            "overdue_task_count": pending_tasks,
        })

    # 5. 客户摘要
    clients = fetch_all("SELECT * FROM clients ORDER BY name")
    for c in clients:
        c_risks = [r for r in client_risks if r.get("client_id") == c["id"]]
        c_projects = fetch_all(
            "SELECT COUNT(*) as cnt FROM projects WHERE client_id = ? AND status = 'active'",
            (c["id"],),
        )
        active_count = c_projects[0]["cnt"] if c_projects else 0

        result["clients_summary"].append({
            "client_id": c["id"],
            "client_name": c["name"],
            "active_project_count": active_count,
            "risk_count": len(c_risks),
            "follow_up_count": sum(
                1 for r in result["relations"]["follow_up_relations"]
                if r.get("source_id") == c["id"] or r.get("target_id") == c["id"]
            ),
        })

    # 6. 总体健康度
    high_risks = result["risks"]["high"]
    if high_risks >= 5:
        result["overall_health"] = "critical"
    elif high_risks >= 2:
        result["overall_health"] = "warning"
    else:
        result["overall_health"] = "good"

    # 7. AI 总结
    result["summary"] = _generate_state_summary(result)

    add_workflow_log("business_state_analysis", "system", None, "success",
                     f"健康度: {result['overall_health']}, "
                     f"风险: {result['risks']['total']} (H:{result['risks']['high']} "
                     f"M:{result['risks']['medium']} L:{result['risks']['low']}), "
                     f"项目: {len(result['projects_summary'])}, "
                     f"客户: {len(result['clients_summary'])}")

    return result


def _generate_state_summary(state: dict) -> str:
    """AI 生成综合状态总结。"""
    try:
        from services.ai_service import _chat

        high = state["risks"]["high"]
        medium = state["risks"]["medium"]
        overall = state["overall_health"]
        active_projects = sum(1 for p in state["projects_summary"] if p["status"] == "active")
        at_risk_projects = sum(1 for p in state["projects_summary"] if p["risk_count"] > 0)
        clients_to_follow = len(state["suggestions"].get("clients_to_follow", []))

        prompt = f"""综合业务状态总览（中文，2-3句话）：
系统健康度: {overall}
活跃项目: {active_projects}个，其中 {at_risk_projects} 个有风险
高风险项: {high}个，中风险项: {medium}个
需跟进客户: {clients_to_follow}个

请给出简洁的总览建议。"""
        return _chat(prompt, "你是一个业务分析助手。给出简洁直接的建议。",
                    temperature=0.4, max_tokens=300)
    except Exception:
        if state["overall_health"] == "critical":
            return "系统存在较多高风险事项，建议立即处理逾期任务和高风险项目。"
        elif state["overall_health"] == "warning":
            return "系统存在一些需要关注的风险项，建议优先处理高风险事项。"
        else:
            return "系统运行状况良好，暂无紧急事项。"
