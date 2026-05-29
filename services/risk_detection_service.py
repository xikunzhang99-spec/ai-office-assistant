"""
风险检测服务 — 多维度检测项目、客户、任务风险。
与 proactive_suggestion_service 互补：本服务专注结构化规则检测（确定性、可测试）。
"""
from database.db import fetch_all, fetch_one
from utils.date_utils import today_str, now_str
from services.workflow_log_service import add_workflow_log


def detect_project_risks() -> list:
    """多维度检测所有活跃项目风险。

    维度:
    1. stage_missing: 活跃项目但未初始化阶段
    2. overdue_high_priority: 高优先级逾期任务
    3. stalled: 14天内无任务完成、无文件上传、无timeline_event
    4. blocked_tasks: 有阻塞标记的任务
    5. stage_stuck: 当前阶段存在超过30天未推进
    6. marked_risk: 已有 risk_related 关系标记
    """
    risks = []
    today = today_str()

    # 1. 阶段缺失 — 活跃项目但没有 project_stages 记录
    missing_stages = fetch_all(
        """SELECT p.id, p.name, p.client_id,
                COALESCE((SELECT c.name FROM clients c WHERE c.id = p.client_id), '') as client_name
           FROM projects p
           WHERE p.status = 'active'
             AND NOT EXISTS (SELECT 1 FROM project_stages ps WHERE ps.project_id = p.id)"""
    )
    for p in missing_stages:
        risks.append({
            "project_id": p["id"], "project_name": p["name"],
            "client_id": p["client_id"], "client_name": p["client_name"],
            "risk_type": "stage_missing",
            "risk_level": "medium",
            "description": f"项目「{p['name']}」尚未初始化阶段",
            "suggestion": "建议为项目设置工作流阶段模板",
            "detected_at": today,
        })

    # 2. 逾期高优先级任务
    overdue = fetch_all(
        """SELECT t.id as task_id, t.title, t.project_id, t.client_id,
                   p.name as project_name,
                   COALESCE((SELECT c.name FROM clients c WHERE c.id = t.client_id), '') as client_name
           FROM tasks t
           LEFT JOIN projects p ON t.project_id = p.id
           WHERE t.status IN ('todo', 'doing')
             AND t.priority = 'high'
             AND t.due_date IS NOT NULL
             AND t.due_date < ?""",
        (today,),
    )
    for t in overdue:
        risks.append({
            "project_id": t["project_id"], "project_name": t["project_name"] or "",
            "client_id": t["client_id"], "client_name": t["client_name"],
            "task_id": t["task_id"],
            "risk_type": "overdue_high_priority",
            "risk_level": "high",
            "description": f"高优先级任务「{t['title']}」已逾期（截止日期: {t.get('due_date', '')}）",
            "suggestion": "建议尽快处理或调整截止日期",
            "detected_at": today,
        })

    # 3. 项目停滞 — 14天内无活动
    fourteen_days_ago = fetch_one(
        "SELECT date('now', '-14 days') as d", ()
    )["d"]
    stalled = fetch_all(
        """SELECT p.id, p.name, p.client_id,
                   COALESCE((SELECT c.name FROM clients c WHERE c.id = p.client_id), '') as client_name
           FROM projects p
           WHERE p.status = 'active'
             AND NOT EXISTS (
                 SELECT 1 FROM tasks t
                 WHERE t.project_id = p.id
                   AND t.status = 'done'
                   AND t.updated_at >= ?
             )
             AND NOT EXISTS (
                 SELECT 1 FROM timeline_events te
                 WHERE te.project_id = p.id
                   AND te.created_at >= ?
             )
             AND NOT EXISTS (
                 SELECT 1 FROM files f
                 WHERE f.project_id = p.id
                   AND f.created_at >= ?
             )""",
        (fourteen_days_ago, fourteen_days_ago, fourteen_days_ago),
    )

    # 区分停滞程度：查最后一次活动日期
    for p in stalled:
        last_activity = _get_project_last_activity(p["id"])
        days_since = None
        if last_activity:
            from datetime import datetime
            try:
                last_dt = datetime.strptime(last_activity[:10], "%Y-%m-%d")
                today_dt = datetime.strptime(today, "%Y-%m-%d")
                days_since = (today_dt - last_dt).days
            except (ValueError, TypeError):
                pass

        level = "high" if (days_since and days_since >= 30) else "medium"
        desc = f"项目「{p['name']}」已停滞 {days_since} 天" if days_since else f"项目「{p['name']}」近期无活动"
        risks.append({
            "project_id": p["id"], "project_name": p["name"],
            "client_id": p["client_id"], "client_name": p["client_name"],
            "risk_type": "stalled",
            "risk_level": level,
            "description": desc,
            "suggestion": "建议检查项目进度，更新任务状态或推进阶段",
            "detected_at": today,
        })

    # 4. 阻塞任务
    blocked = fetch_all(
        """SELECT t.id as task_id, t.title, t.project_id,
                   p.name as project_name
           FROM tasks t
           JOIN relations r ON (
               (r.source_type = 'task' AND r.source_id = t.id)
               OR (r.target_type = 'task' AND r.target_id = t.id)
           )
           LEFT JOIN projects p ON t.project_id = p.id
           WHERE t.status IN ('todo', 'doing')
             AND r.relation_type = 'blocks'"""
    )
    for t in blocked:
        risks.append({
            "project_id": t["project_id"], "project_name": t["project_name"] or "",
            "task_id": t["task_id"],
            "risk_type": "blocked_tasks",
            "risk_level": "high",
            "description": f"任务「{t['title']}」存在阻塞依赖",
            "suggestion": "检查并解决阻塞原因后再推进",
            "detected_at": today,
        })

    # 5. 阶段卡住 — 当前活跃阶段超过30天未推进
    thirty_days_ago = fetch_one(
        "SELECT date('now', '-30 days') as d", ()
    )["d"]
    stuck_stages = fetch_all(
        """SELECT ps.id as stage_id, ps.stage_name, ps.project_id,
                   p.name as project_name, ps.started_at,
                   COALESCE((SELECT c.name FROM clients c WHERE c.id = p.client_id), '') as client_name
           FROM project_stages ps
           JOIN projects p ON ps.project_id = p.id
           WHERE ps.status = 'active'
             AND ps.started_at IS NOT NULL
             AND ps.started_at < ?
             AND p.status = 'active'""",
        (thirty_days_ago,),
    )
    for s in stuck_stages:
        risks.append({
            "project_id": s["project_id"], "project_name": s["project_name"],
            "client_name": s["client_name"],
            "stage_id": s["stage_id"],
            "risk_type": "stage_stuck",
            "risk_level": "medium",
            "description": f"项目「{s['project_name']}」的阶段「{s['stage_name']}」已超过30天未推进",
            "suggestion": "检查阶段卡住原因，考虑推进或跳过该阶段",
            "detected_at": today,
        })

    # 6. 已标记的风险关系
    marked = fetch_all(
        """SELECT r.id as relation_id, r.source_type, r.source_id, r.target_type, r.target_id,
                   r.description,
                   COALESCE(p.id, p2.id) as project_id,
                   COALESCE(p.name, p2.name) as project_name,
                   COALESCE(
                       (SELECT c.name FROM clients c WHERE c.id = COALESCE(p.client_id, p2.client_id)),
                       ''
                   ) as client_name
           FROM relations r
           LEFT JOIN projects p ON (r.source_type = 'project' AND r.source_id = p.id)
           LEFT JOIN projects p2 ON (r.target_type = 'project' AND r.target_id = p2.id)
           WHERE r.relation_type = 'risk_related'
             AND (p.status = 'active' OR p2.status = 'active')"""
    )
    for m in marked:
        risks.append({
            "project_id": m["project_id"], "project_name": m["project_name"] or "",
            "client_name": m["client_name"],
            "risk_type": "marked_risk",
            "risk_level": "medium",
            "description": m.get("description", "") or "该项目存在已标记的风险关系",
            "suggestion": "查看风险详情并制定应对方案",
            "detected_at": today,
        })

    # 按 project_id 去重合并相同类型的风险
    seen = set()
    deduped = []
    for r in risks:
        key = (r.get("project_id"), r["risk_type"], r.get("task_id"), r.get("stage_id"))
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    add_workflow_log("risk_detection_project", None, None, "success",
                     f"检测到 {sum(1 for r in deduped if r['risk_level'] == 'high')} 个高风险、"
                     f"{sum(1 for r in deduped if r['risk_level'] == 'medium')} 个中风险、"
                     f"{sum(1 for r in deduped if r['risk_level'] == 'low')} 个低风险项目")
    return deduped


def detect_client_risks() -> list:
    """检测所有客户风险。

    维度:
    1. no_recent_followup: 30天无跟进活动但有活跃项目
    2. all_projects_stalled: 所有关联项目都停滞
    3. overdue_deliverables: 关联高优任务逾期
    4. stale_client: 无活跃项目但有历史项目未关闭
    """
    risks = []
    today = today_str()
    thirty_days_ago = fetch_one("SELECT date('now', '-30 days') as d", ())["d"]

    # 1. 30天无跟进但有活跃项目
    no_followup = fetch_all(
        """SELECT c.id, c.name,
                   COUNT(DISTINCT p.id) as active_project_count
           FROM clients c
           JOIN projects p ON c.id = p.client_id AND p.status = 'active'
           WHERE NOT EXISTS (
               SELECT 1 FROM timeline_events te
               WHERE te.client_id = c.id
                 AND te.created_at >= ?
           )
           GROUP BY c.id""",
        (thirty_days_ago,),
    )
    for c in no_followup:
        risks.append({
            "client_id": c["id"], "client_name": c["name"],
            "risk_type": "no_recent_followup",
            "risk_level": "medium",
            "description": f"客户「{c['name']}」30天内无跟进活动，但有 {c['active_project_count']} 个活跃项目",
            "suggestion": "建议安排跟进联系",
            "detected_at": today,
        })

    # 2. 所有项目停滞（需要所有项目都在 stalled 状态）
    # 这里简化：查活跃项目中哪些有阶段卡住的
    stalled_clients = fetch_all(
        """SELECT c.id, c.name,
                   COUNT(p.id) as total_active,
                   SUM(CASE WHEN EXISTS (
                       SELECT 1 FROM project_stages ps
                       WHERE ps.project_id = p.id AND ps.status = 'active'
                         AND ps.started_at < ?
                   ) THEN 1 ELSE 0 END) as stuck_count
           FROM clients c
           JOIN projects p ON c.id = p.client_id AND p.status = 'active'
           GROUP BY c.id
           HAVING stuck_count >= total_active AND total_active > 0""",
        (thirty_days_ago,),
    )
    for c in stalled_clients:
        risks.append({
            "client_id": c["id"], "client_name": c["name"],
            "risk_type": "all_projects_stalled",
            "risk_level": "high",
            "description": f"客户「{c['name']}」的所有 {c['total_active']} 个活跃项目均处于停滞状态",
            "suggestion": "评估客户关系，主动联系了解情况",
            "detected_at": today,
        })

    # 3. 逾期交付物
    overdue_clients = fetch_all(
        """SELECT c.id, c.name,
                   COUNT(t.id) as overdue_count
           FROM clients c
           JOIN tasks t ON c.id = t.client_id
           WHERE t.status IN ('todo', 'doing')
             AND t.priority = 'high'
             AND t.due_date IS NOT NULL
             AND t.due_date < ?
           GROUP BY c.id""",
        (today,),
    )
    for c in overdue_clients:
        risks.append({
            "client_id": c["id"], "client_name": c["name"],
            "risk_type": "overdue_deliverables",
            "risk_level": "high",
            "description": f"客户「{c['name']}」有 {c['overdue_count']} 个高优先级逾期任务",
            "suggestion": "优先处理逾期交付物，及时与客户沟通",
            "detected_at": today,
        })

    # 4. 僵尸客户 — 有历史项目但不活跃
    stale = fetch_all(
        """SELECT c.id, c.name
           FROM clients c
           WHERE EXISTS (SELECT 1 FROM projects p WHERE p.client_id = c.id)
             AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.client_id = c.id AND p.status = 'active')
             AND NOT EXISTS (
                 SELECT 1 FROM timeline_events te
                 WHERE te.client_id = c.id AND te.created_at >= ?
             )""",
        (thirty_days_ago,),
    )
    for c in stale:
        risks.append({
            "client_id": c["id"], "client_name": c["name"],
            "risk_type": "stale_client",
            "risk_level": "low",
            "description": f"客户「{c['name']}」无活跃项目且30天无活动",
            "suggestion": "考虑是否需要重新激活或归档该客户",
            "detected_at": today,
        })

    add_workflow_log("risk_detection_client", None, None, "success",
                     f"检测到 {len(risks)} 个客户风险项")
    return risks


def detect_task_risks() -> list:
    """检测所有任务风险。

    维度:
    1. overdue: 逾期任务
    2. blocked: 被 blocks 关系阻塞的任务
    3. dependency_at_risk: 依赖的关联任务逾期
    """
    risks = []
    today = today_str()

    # 1. 所有逾期任务（不限优先级）
    overdue = fetch_all(
        """SELECT t.id as task_id, t.title, t.priority, t.due_date,
                   t.project_id, t.client_id,
                   p.name as project_name,
                   COALESCE((SELECT c.name FROM clients c WHERE c.id = t.client_id), '') as client_name
           FROM tasks t
           LEFT JOIN projects p ON t.project_id = p.id
           WHERE t.status IN ('todo', 'doing')
             AND t.due_date IS NOT NULL
             AND t.due_date < ?
           ORDER BY t.priority = 'high' DESC, t.due_date""",
        (today,),
    )
    for t in overdue:
        level = "high" if t["priority"] == "high" else ("medium" if t["priority"] == "medium" else "low")
        risks.append({
            "task_id": t["task_id"], "task_title": t["title"],
            "project_id": t["project_id"], "project_name": t["project_name"] or "",
            "client_id": t["client_id"], "client_name": t["client_name"],
            "risk_type": "overdue",
            "risk_level": level,
            "description": f"任务「{t['title']}」已逾期（截止: {t['due_date']}）",
            "suggestion": "尽快处理或重新排期",
            "detected_at": today,
        })

    # 2. 阻塞任务
    blocked = fetch_all(
        """SELECT t.id as task_id, t.title, t.project_id,
                   p.name as project_name, t.client_id,
                   COALESCE((SELECT c.name FROM clients c WHERE c.id = t.client_id), '') as client_name
           FROM tasks t
           JOIN relations r ON (
               (r.target_type = 'task' AND r.target_id = t.id)
           )
           LEFT JOIN projects p ON t.project_id = p.id
           WHERE t.status IN ('todo', 'doing')
             AND r.relation_type = 'blocks'"""
    )
    for t in blocked:
        risks.append({
            "task_id": t["task_id"], "task_title": t["title"],
            "project_id": t["project_id"], "project_name": t["project_name"] or "",
            "client_id": t["client_id"], "client_name": t["client_name"],
            "risk_type": "blocked",
            "risk_level": "high",
            "description": f"任务「{t['title']}」被阻塞依赖阻挡",
            "suggestion": "先完成前置阻塞任务",
            "detected_at": today,
        })

    # 3. 依赖风险：当前任务所依赖的任务已逾期
    dep_risks = fetch_all(
        """SELECT t.id as task_id, t.title, t.project_id,
                   p.name as project_name,
                   dep.id as dep_task_id, dep.title as dep_title,
                   dep.due_date as dep_due_date
           FROM tasks t
           JOIN relations r ON r.source_type = 'task' AND r.source_id = t.id
                             AND r.relation_type = 'depends_on'
           JOIN tasks dep ON r.target_type = 'task' AND r.target_id = dep.id
           LEFT JOIN projects p ON t.project_id = p.id
           WHERE t.status IN ('todo', 'doing')
             AND dep.status != 'done'
             AND dep.due_date IS NOT NULL
             AND dep.due_date < ?""",
        (today,),
    )
    for t in dep_risks:
        risks.append({
            "task_id": t["task_id"], "task_title": t["title"],
            "project_id": t["project_id"], "project_name": t["project_name"] or "",
            "risk_type": "dependency_at_risk",
            "risk_level": "high",
            "description": f"任务「{t['title']}」的依赖任务「{t['dep_title']}」已逾期",
            "suggestion": f"优先处理依赖任务，或重新评估依赖关系",
            "detected_at": today,
        })

    add_workflow_log("risk_detection_task", None, None, "success",
                     f"检测到 {len(risks)} 个任务风险项")
    return risks


def _get_project_last_activity(project_id: int) -> str | None:
    """获取项目最后一次活动日期。"""
    row = fetch_one(
        """SELECT MAX(created_at) as last_activity FROM (
            SELECT created_at FROM tasks WHERE project_id = ? AND status = 'done'
            UNION ALL
            SELECT created_at FROM timeline_events WHERE project_id = ?
            UNION ALL
            SELECT created_at FROM files WHERE project_id = ?
        )""",
        (project_id, project_id, project_id),
    )
    if row:
        return row["last_activity"]
    return None
