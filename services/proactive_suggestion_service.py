"""
主动工作流建议服务 — 基于系统状态主动生成工作建议。
提供每日建议、项目/客户级建议、逾期检测、风险检测。
"""
from database.db import fetch_all, fetch_one
from services.workflow_log_service import add_workflow_log
from utils.date_utils import today_str, now_str


def generate_daily_suggestions() -> dict:
    """生成今日主动建议。

    Returns:
        {
            "date": str,
            "priority_tasks": [...],
            "overdue_items": [...],
            "clients_to_follow": [...],
            "project_risks": [...],
            "pending_document_actions": [...],
            "recent_memories": [...],
            "summary": str,
        }
    """
    suggestions = {
        "date": today_str(),
        "priority_tasks": [],
        "overdue_items": [],
        "clients_to_follow": [],
        "project_risks": [],
        "pending_document_actions": [],
        "recent_memories": [],
        "summary": "",
    }

    # 1. 今日高优先级任务
    suggestions["priority_tasks"] = fetch_all(
        """SELECT * FROM tasks
           WHERE status IN ('todo', 'doing') AND priority = 'high'
           ORDER BY
             CASE WHEN due_date <= ? THEN 0 ELSE 1 END,
             due_date ASC
           LIMIT 10""",
        (today_str(),),
    )

    # 2. 逾期任务
    suggestions["overdue_items"] = fetch_all(
        """SELECT * FROM tasks
           WHERE status IN ('todo', 'doing') AND due_date < ? AND due_date != ''
           ORDER BY due_date ASC LIMIT 10""",
        (today_str(),),
    )

    # 3. 需跟进的客户（最近30天无活动但有活跃项目）
    suggestions["clients_to_follow"] = fetch_all(
        """SELECT c.*,
                (SELECT COUNT(*) FROM projects WHERE client_id = c.id AND status = 'active') as active_projects
           FROM clients c
           WHERE c.id IN (
               SELECT DISTINCT client_id FROM projects WHERE status = 'active'
           )
           AND (
               c.id NOT IN (
                   SELECT DISTINCT client_id FROM timeline_events
                   WHERE event_date > date('now', '-30 days') AND client_id IS NOT NULL
               )
               OR c.id IN (
                   SELECT DISTINCT client_id FROM tasks
                   WHERE status IN ('todo', 'doing') AND due_date < date('now') AND due_date != ''
               )
           )
           ORDER BY active_projects DESC
           LIMIT 10"""
    )

    # 4. 项目风险
    suggestions["project_risks"] = _detect_project_risks()

    # 5. 未执行的文件建议
    suggestions["pending_document_actions"] = fetch_all(
        """SELECT f.*, da.analysis_date
           FROM files f
           LEFT JOIN (
               SELECT source_id, MAX(created_at) as analysis_date
               FROM workflow_logs
               WHERE workflow_type = 'document_action_analysis'
               GROUP BY source_id
           ) da ON f.id = da.source_id
           WHERE f.suggestions IS NOT NULL AND f.suggestions != ''
           ORDER BY da.analysis_date DESC NULLS LAST
           LIMIT 10"""
    )

    # 6. 最近重要记忆
    try:
        from services.memory_service import get_high_importance_memories
        suggestions["recent_memories"] = get_high_importance_memories(limit=10)
    except Exception:
        pass

    # 7. AI 总结
    suggestions["summary"] = _generate_suggestion_summary(suggestions)

    add_workflow_log("proactive_daily_suggestions", "proactive", None, "success",
                     f"每日建议: {len(suggestions['priority_tasks'])} 任务, "
                     f"{len(suggestions['overdue_items'])} 逾期, "
                     f"{len(suggestions['project_risks'])} 风险")
    return suggestions


def generate_project_suggestions(project_id: int) -> dict:
    """生成项目级主动建议。

    Returns:
        {
            "project": {...},
            "risks": [...],
            "blocked_tasks": [...],
            "overdue_tasks": [...],
            "memories": [...],
            "next_steps": str,
        }
    """
    from services.project_service import get_project
    from services.relation_service import find_entity_risks, find_entity_follow_ups

    project = get_project(project_id)
    if not project:
        return {"project": None, "risks": [], "blocked_tasks": [],
                "overdue_tasks": [], "memories": [], "next_steps": ""}

    # 风险关系
    risks = find_entity_risks("project", project_id)

    # 阻塞任务
    blocked_tasks = fetch_all(
        """SELECT t.* FROM tasks t
           INNER JOIN relations r ON (
               (r.source_type = 'task' AND r.source_id = t.id AND r.target_type = 'task' AND r.target_id = t.id)
               OR (r.target_type = 'task' AND r.target_id = t.id)
           )
           WHERE r.relation_type = 'blocks' AND t.status IN ('todo', 'doing')
           AND (r.source_id = ? OR r.target_id = ?)
           LIMIT 10""",
        (project_id, project_id),
    )
    if not blocked_tasks:
        blocked_tasks = fetch_all(
            """SELECT * FROM tasks
               WHERE project_id = ? AND status IN ('todo', 'doing')
               AND (title LIKE '%阻塞%' OR title LIKE '%block%'
                    OR description LIKE '%阻塞%' OR description LIKE '%block%')
               LIMIT 10""",
            (project_id,),
        )

    # 逾期任务
    overdue_tasks = fetch_all(
        """SELECT * FROM tasks
           WHERE project_id = ? AND status IN ('todo', 'doing')
           AND due_date < ? AND due_date != ''
           ORDER BY due_date ASC""",
        (project_id, today_str()),
    )

    # 长期记忆
    try:
        from services.memory_service import get_memory_by_project
        memories = get_memory_by_project(project_id, limit=20)
    except Exception:
        memories = []

    # 未完成任务
    uncompleted = fetch_all(
        """SELECT * FROM tasks
           WHERE project_id = ? AND status IN ('todo', 'doing')
           ORDER BY priority DESC, due_date ASC
           LIMIT 20""",
        (project_id,),
    )

    follow_ups = find_entity_follow_ups("project", project_id)

    # AI 下一步建议
    next_steps = _generate_project_next_steps(project, uncompleted, overdue_tasks,
                                              risks, memories)

    add_workflow_log("proactive_project_suggestions", "project", project_id, "success",
                     f"项目建议: {len(risks)} 风险, {len(overdue_tasks)} 逾期")

    return {
        "project": project,
        "risks": risks,
        "blocked_tasks": blocked_tasks,
        "overdue_tasks": overdue_tasks,
        "uncompleted_tasks": uncompleted,
        "memories": memories,
        "follow_ups": follow_ups,
        "next_steps": next_steps,
    }


def generate_client_suggestions(client_id: int) -> dict:
    """生成客户级主动建议。

    Returns:
        {
            "client": {...},
            "risks": [...],
            "follow_ups": [...],
            "memories": [...],
            "recent_activity": [...],
            "suggestions": str,
        }
    """
    from services.client_service import get_client
    from services.relation_service import find_entity_risks, find_entity_follow_ups, get_client_graph

    client = get_client(client_id)
    if not client:
        return {"client": None, "risks": [], "follow_ups": [],
                "memories": [], "recent_activity": [], "suggestions": ""}

    graph = get_client_graph(client_id)
    risks = graph.get("risks", [])
    follow_ups = graph.get("follow_ups", [])
    memories = graph.get("memories", [])

    # 最近活动
    recent_activity = fetch_all(
        """SELECT * FROM timeline_events
           WHERE (client_id = ? OR related_type = 'client' AND related_id = ?)
           ORDER BY event_date DESC LIMIT 20""",
        (client_id, client_id),
    )

    # 项目状态
    projects = fetch_all(
        "SELECT * FROM projects WHERE client_id = ? ORDER BY status, created_at DESC",
        (client_id,),
    )

    suggestions = _generate_client_suggestions_text(client, projects, risks,
                                                     follow_ups, memories,
                                                     recent_activity)

    add_workflow_log("proactive_client_suggestions", "client", client_id, "success",
                     f"客户建议: {len(risks)} 风险, {len(follow_ups)} 跟进")

    return {
        "client": client,
        "projects": projects,
        "risks": risks,
        "follow_ups": follow_ups,
        "memories": memories,
        "recent_activity": recent_activity,
        "suggestions": suggestions,
    }


def detect_overdue_followups() -> list:
    """检测所有逾期的跟进事项。"""
    # 有 follow_up_required 关系且关联的任务逾期
    results = fetch_all(
        """SELECT r.*, t.title as task_title, t.due_date, t.status as task_status,
                c.name as client_name, p.name as project_name
           FROM relations r
           LEFT JOIN tasks t ON (
               (r.source_type = 'task' AND r.source_id = t.id)
               OR (r.target_type = 'task' AND r.target_id = t.id)
           )
           LEFT JOIN clients c ON (
               (r.source_type = 'client' AND r.source_id = c.id)
               OR (r.target_type = 'client' AND r.target_id = c.id)
           )
           LEFT JOIN projects p ON (
               (r.source_type = 'project' AND r.source_id = p.id)
               OR (r.target_type = 'project' AND r.target_id = p.id)
           )
           WHERE r.relation_type = 'follow_up_required'
           ORDER BY t.due_date ASC
           LIMIT 30"""
    )
    return results


def detect_project_risks() -> list:
    """检测所有项目风险。"""
    return _detect_project_risks()


def get_project_stage_summary(project_id: int) -> dict:
    """获取项目阶段化摘要，供 dashboard/project detail 使用。

    Returns:
        {
            "project": {...},
            "stages": [...],
            "current_stage": {...} or None,
            "progress": float,
            "risks": [...],
            "next_milestone": str,
        }
    """
    from services.workflow_engine import get_project_progress, get_current_stage, get_project_stages
    from services.risk_detection_service import detect_project_risks as detect_all_project_risks

    project = fetch_one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not project:
        return {"project": None, "stages": [], "current_stage": None,
                "progress": 0, "risks": [], "next_milestone": ""}

    progress = get_project_progress(project_id)
    current_stage = get_current_stage(project_id)
    stages = get_project_stages(project_id)

    all_risks = detect_all_project_risks()
    project_risks = [r for r in all_risks if r.get("project_id") == project_id]

    next_milestone = ""
    if current_stage:
        next_milestone = f"完成阶段「{current_stage['stage_name']}」"
    elif stages:
        pending = [s for s in stages if s["status"] == "pending"]
        if pending:
            next_milestone = f"推进到阶段「{pending[0]['stage_name']}」"

    return {
        "project": project,
        "stages": progress.get("stage_breakdown", []),
        "current_stage": current_stage,
        "progress": progress.get("stage_completion_pct", 0),
        "task_progress": progress.get("task_completion_pct", 0),
        "remaining_tasks": progress.get("remaining_tasks", 0),
        "risks": project_risks,
        "next_milestone": next_milestone,
    }


def _detect_project_risks() -> list:
    """内部：检测项目风险。从多个维度综合判断（含阶段感知）。"""
    risks = []

    # 1. 有关风险关系的项目
    risk_relations = fetch_all(
        """SELECT p.id, p.name, p.status, r.description, r.created_at,
                c.name as client_name
           FROM relations r
           JOIN projects p ON (
               (r.source_type = 'project' AND r.source_id = p.id)
               OR (r.target_type = 'project' AND r.target_id = p.id)
           )
           LEFT JOIN clients c ON p.client_id = c.id
           WHERE r.relation_type = 'risk_related' AND p.status = 'active'
           ORDER BY r.created_at DESC"""
    )
    for rr in risk_relations:
        rr["risk_source"] = "marked_risk"
        risks.append(rr)

    # 2. 有高优先级逾期任务的项目
    overdue_projects = fetch_all(
        """SELECT DISTINCT p.id, p.name, p.status, c.name as client_name,
                COUNT(t.id) as overdue_count
           FROM projects p
           JOIN tasks t ON t.project_id = p.id
           LEFT JOIN clients c ON p.client_id = c.id
           WHERE t.priority = 'high' AND t.status IN ('todo', 'doing')
           AND t.due_date < ? AND t.due_date != ''
           AND p.status = 'active'
           GROUP BY p.id
           ORDER BY overdue_count DESC""",
        (today_str(),),
    )
    for op in overdue_projects:
        op["risk_source"] = "overdue_high_priority"
        op["description"] = f"{op['overdue_count']} 个高优先级任务逾期"
        risks.append(op)

    # 3. 有阻塞任务的项目
    blocked_projects = fetch_all(
        """SELECT DISTINCT p.id, p.name, p.status, c.name as client_name,
                COUNT(t.id) as blocked_count
           FROM projects p
           JOIN tasks t ON t.project_id = p.id
           LEFT JOIN clients c ON p.client_id = c.id
           WHERE t.status IN ('todo', 'doing')
           AND (t.title LIKE '%阻塞%' OR t.title LIKE '%卡住%'
                OR t.description LIKE '%阻塞%' OR t.description LIKE '%卡住%'
                OR t.tags LIKE '%阻塞%')
           AND p.status = 'active'
           GROUP BY p.id
           ORDER BY blocked_count DESC""",
    )
    for bp in blocked_projects:
        bp["risk_source"] = "blocked_tasks"
        bp["description"] = f"{bp['blocked_count']} 个阻塞任务"
        risks.append(bp)

    # 4. (NEW) 阶段缺失 — 活跃项目但未初始化阶段
    missing_stages = fetch_all(
        """SELECT p.id, p.name, p.status,
                c.name as client_name
           FROM projects p
           LEFT JOIN clients c ON p.client_id = c.id
           WHERE p.status = 'active'
             AND NOT EXISTS (SELECT 1 FROM project_stages ps WHERE ps.project_id = p.id)"""
    )
    for ms in missing_stages:
        ms["risk_source"] = "missing_stages"
        ms["description"] = "项目尚未初始化阶段"
        risks.append(ms)

    # 5. (NEW) 阶段卡住 — 活跃阶段超过30天未推进
    stuck_stages = fetch_all(
        """SELECT DISTINCT p.id, p.name, p.status,
                c.name as client_name,
                ps.stage_name, ps.started_at
           FROM project_stages ps
           JOIN projects p ON ps.project_id = p.id
           LEFT JOIN clients c ON p.client_id = c.id
           WHERE ps.status = 'active'
             AND ps.started_at IS NOT NULL
             AND ps.started_at < date('now', '-30 days')
             AND p.status = 'active'"""
    )
    for ss in stuck_stages:
        ss["risk_source"] = "stage_stuck"
        ss["description"] = f"阶段「{ss['stage_name']}」已超过30天未推进"
        risks.append(ss)

    # 合并去重
    seen_ids = set()
    unique_risks = []
    for r in risks:
        pid = r.get("id")
        risk_key = (pid, r.get("risk_source"))
        if pid and risk_key not in seen_ids:
            seen_ids.add(risk_key)
            unique_risks.append(r)

    return unique_risks


def _generate_suggestion_summary(suggestions: dict) -> str:
    """生成每日建议的 AI 总结。"""
    try:
        from services.ai_service import _chat

        priority_count = len(suggestions.get("priority_tasks", []))
        overdue_count = len(suggestions.get("overdue_items", []))
        follow_count = len(suggestions.get("clients_to_follow", []))
        risk_count = len(suggestions.get("project_risks", []))
        memory_count = len(suggestions.get("recent_memories", []))

        if priority_count + overdue_count + follow_count + risk_count == 0:
            return "今日一切正常，无特别需要关注的事项。继续保持！"

        prompt = f"""根据以下今日工作数据，用3-5句话给出简洁的工作建议。中文，直接实用。

高优先级任务: {priority_count}个
逾期事项: {overdue_count}个
需跟进客户: {follow_count}个
有风险项目: {risk_count}个
近期重要记忆: {memory_count}条

按优先级给出建议：先处理逾期，再关注高风险，最后跟进客户。"""
        return _chat(prompt, "你是一个工作建议助手。给出简洁实用的建议。",
                    temperature=0.5, max_tokens=500)
    except Exception:
        return "AI 建议生成失败，请稍后重试。"


def _generate_project_next_steps(project: dict, uncompleted: list,
                                  overdue: list, risks: list,
                                  memories: list) -> str:
    """生成项目下一步建议。"""
    try:
        from services.ai_service import _chat

        if not uncompleted and not overdue and not risks:
            return "项目当前状态良好，所有任务已完成。可以关注是否有新的需求或阶段性总结。"

        prompt = f"""项目「{project.get('name', '')}」当前状态分析：
未完成任务: {len(uncompleted)}个
逾期任务: {len(overdue)}个
风险关系: {len(risks)}个
长期记忆: {len(memories)}条

请给出3-5条下一步建议。优先处理逾期和阻塞任务，然后关注风险。中文，简洁。"""
        return _chat(prompt, "你是一个项目管理助手。给出实用建议。",
                    temperature=0.4, max_tokens=500)
    except Exception:
        return "建议生成失败。"


def _generate_client_suggestions_text(client: dict, projects: list,
                                       risks: list, follow_ups: list,
                                       memories: list,
                                       recent_activity: list) -> str:
    """生成客户跟进建议。"""
    try:
        from services.ai_service import _chat

        active_count = sum(1 for p in projects if p.get("status") == "active")
        prompt = f"""客户「{client.get('name', '')}」当前状态：
活跃项目: {active_count}个
风险关系: {len(risks)}个
跟进事项: {len(follow_ups)}个
长期记忆: {len(memories)}条
最近活动: {len(recent_activity)}条

请给出3-5条客户跟进建议。优先关注风险，然后是需要跟进的承诺，最后是长期关系维护。中文，简洁。"""
        return _chat(prompt, "你是一个客户管理助手。给出实用建议。",
                    temperature=0.4, max_tokens=500)
    except Exception:
        return "建议生成失败。"
