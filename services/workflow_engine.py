"""
工作流引擎 — 项目阶段管理、模板管理、阶段推断、进度追踪。
"""
import json
from database.db import insert, fetch_all, fetch_one, execute
from utils.date_utils import now_str, today_str

DEFAULT_TEMPLATES = {
    "software_project": {
        "stages": [
            {"name": "需求分析", "order": 1},
            {"name": "原型设计", "order": 2},
            {"name": "开发", "order": 3},
            {"name": "测试", "order": 4},
            {"name": "上线", "order": 5},
        ],
        "default_tasks": [
            {"title": "需求调研", "priority": "high", "stage": 1},
            {"title": "需求文档编写", "priority": "high", "stage": 1},
            {"title": "低保真原型", "priority": "medium", "stage": 2},
            {"title": "高保真原型", "priority": "medium", "stage": 2},
            {"title": "接口开发", "priority": "high", "stage": 3},
            {"title": "前端开发", "priority": "high", "stage": 3},
            {"title": "数据库设计", "priority": "high", "stage": 3},
            {"title": "单元测试", "priority": "medium", "stage": 4},
            {"title": "集成测试", "priority": "high", "stage": 4},
            {"title": "上线部署", "priority": "high", "stage": 5},
        ],
    },
    "client_followup": {
        "stages": [
            {"name": "首次接触", "order": 1},
            {"name": "需求沟通", "order": 2},
            {"name": "方案发送", "order": 3},
            {"name": "报价", "order": 4},
            {"name": "签约", "order": 5},
            {"name": "交付", "order": 6},
        ],
        "default_tasks": [
            {"title": "初次电话/拜访", "priority": "high", "stage": 1},
            {"title": "客户信息记录", "priority": "medium", "stage": 1},
            {"title": "需求记录与确认", "priority": "high", "stage": 2},
            {"title": "方案文档编写", "priority": "medium", "stage": 3},
            {"title": "报价单制作", "priority": "high", "stage": 4},
            {"title": "合同起草", "priority": "high", "stage": 5},
            {"title": "合同签署", "priority": "high", "stage": 5},
            {"title": "交付物准备", "priority": "high", "stage": 6},
        ],
    },
    "research_project": {
        "stages": [
            {"name": "选题", "order": 1},
            {"name": "文献调研", "order": 2},
            {"name": "研究/实验", "order": 3},
            {"name": "论文撰写", "order": 4},
            {"name": "提交", "order": 5},
        ],
        "default_tasks": [
            {"title": "确定研究方向", "priority": "high", "stage": 1},
            {"title": "导师沟通确认", "priority": "high", "stage": 1},
            {"title": "文献检索与阅读", "priority": "high", "stage": 2},
            {"title": "实验设计", "priority": "high", "stage": 3},
            {"title": "数据收集", "priority": "high", "stage": 3},
            {"title": "论文初稿", "priority": "medium", "stage": 4},
            {"title": "修改完善", "priority": "medium", "stage": 4},
            {"title": "论文提交", "priority": "high", "stage": 5},
        ],
    },
    "marketing_campaign": {
        "stages": [
            {"name": "策划", "order": 1},
            {"name": "素材准备", "order": 2},
            {"name": "执行中", "order": 3},
            {"name": "效果分析", "order": 4},
            {"name": "复盘", "order": 5},
        ],
        "default_tasks": [
            {"title": "活动方案策划", "priority": "high", "stage": 1},
            {"title": "预算审批", "priority": "high", "stage": 1},
            {"title": "文案/图片准备", "priority": "medium", "stage": 2},
            {"title": "渠道对接", "priority": "high", "stage": 2},
            {"title": "渠道投放", "priority": "high", "stage": 3},
            {"title": "实时监控", "priority": "medium", "stage": 3},
            {"title": "数据收集与分析", "priority": "medium", "stage": 4},
            {"title": "效果报告", "priority": "medium", "stage": 4},
            {"title": "复盘报告", "priority": "medium", "stage": 5},
        ],
    },
}


def get_default_template(template_type: str) -> dict:
    """返回默认模板，DB 查不到时回退。"""
    return DEFAULT_TEMPLATES.get(template_type, DEFAULT_TEMPLATES["software_project"])


def _get_template_from_db(template_type: str) -> dict | None:
    row = fetch_one(
        "SELECT * FROM workflow_templates WHERE template_type = ? LIMIT 1",
        (template_type,),
    )
    if row:
        try:
            return json.loads(row["template_json"])
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _get_template(template_type: str) -> dict:
    """获取模板，优先 DB，回退到硬编码。"""
    tmpl = _get_template_from_db(template_type)
    if tmpl:
        return tmpl
    return get_default_template(template_type)


def init_project_stages(project_id: int, template_type: str = "software_project") -> list:
    """为项目初始化阶段。幂等：已有阶段则直接返回。"""
    existing = fetch_all(
        "SELECT * FROM project_stages WHERE project_id = ? ORDER BY stage_order",
        (project_id,),
    )
    if existing:
        return existing

    template = _get_template(template_type)
    stages = template.get("stages", [])
    now = now_str()

    result = []
    for i, s in enumerate(stages):
        status = "active" if i == 0 else "active"
        started = now if i == 0 else None
        sid = insert(
            """INSERT INTO project_stages (project_id, stage_name, stage_order, status, started_at, completed_at)
               VALUES (?, ?, ?, ?, ?, NULL)""",
            (project_id, s["name"], s["order"], status, started),
        )
        result.append({
            "id": sid, "project_id": project_id, "stage_name": s["name"],
            "stage_order": s["order"], "status": status,
            "started_at": started, "completed_at": None,
        })

    from services.timeline_service import add_event
    from services.workflow_log_service import add_workflow_log

    add_event("stage_initialized", f"项目阶段初始化（{template_type}）",
              f"创建了 {len(stages)} 个阶段", "project", project_id,
              project_id=project_id)
    add_workflow_log("stage_initialized", "project", project_id, "success",
                     f"初始化 {len(stages)} 个阶段，模板: {template_type}")

    # 记录后续阶段的状态更新
    for i in range(1, len(stages)):
        execute(
            "UPDATE project_stages SET status = 'pending' WHERE id = ?",
            (result[i]["id"],),
        )
        result[i]["status"] = "pending"

    return result


def generate_tasks_from_template(project_id: int, template_type: str = "software_project") -> list:
    """从模板为项目创建任务。跳过已存在的同名任务。返回创建的任务 ID 列表。"""
    template = _get_template(template_type)
    default_tasks = template.get("default_tasks", [])
    created_ids = []

    # 获取项目信息
    project = fetch_one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not project:
        return created_ids

    from services.task_service import get_or_create_task

    for dt in default_tasks:
        result = get_or_create_task(
            title=dt["title"],
            description=dt.get("description", ""),
            priority=dt.get("priority", "medium"),
            project_id=project_id,
        )
        if result["created"]:
            created_ids.append(result["task_id"])

    from services.workflow_log_service import add_workflow_log
    add_workflow_log("tasks_from_template", "project", project_id, "success",
                     f"从模板 {template_type} 创建了 {len(created_ids)} 个任务")

    return created_ids


def get_project_stages(project_id: int) -> list:
    return fetch_all(
        "SELECT * FROM project_stages WHERE project_id = ? ORDER BY stage_order",
        (project_id,),
    )


def get_project_stage(stage_id: int) -> dict | None:
    return fetch_one("SELECT * FROM project_stages WHERE id = ?", (stage_id,))


def get_current_stage(project_id: int) -> dict | None:
    return fetch_one(
        """SELECT * FROM project_stages
           WHERE project_id = ? AND status = 'active'
           ORDER BY stage_order LIMIT 1""",
        (project_id,),
    )


def advance_stage(project_id: int, stage_id: int) -> dict:
    """推进阶段：将指定阶段标记为 completed，激活下一个阶段。"""
    stage = get_project_stage(stage_id)
    if not stage or stage["project_id"] != project_id:
        return {"success": False, "error": "阶段不存在或不属于该项目"}

    now = now_str()
    execute(
        "UPDATE project_stages SET status = 'completed', completed_at = ? WHERE id = ?",
        (now, stage_id),
    )

    next_stage = fetch_one(
        """SELECT * FROM project_stages
           WHERE project_id = ? AND stage_order > ? AND status != 'skipped'
           ORDER BY stage_order LIMIT 1""",
        (project_id, stage["stage_order"]),
    )

    if next_stage:
        execute(
            "UPDATE project_stages SET status = 'active', started_at = ? WHERE id = ?",
            (now, next_stage["id"]),
        )

    from services.timeline_service import add_event
    from services.workflow_log_service import add_workflow_log

    add_event("stage_advanced",
              f"阶段推进：{stage['stage_name']} → {next_stage['stage_name'] if next_stage else '结束'}",
              f"项目 {project_id} 完成阶段「{stage['stage_name']}」",
              "project", project_id, project_id=project_id)
    add_workflow_log("stage_advanced", "project", project_id, "success",
                     f"阶段「{stage['stage_name']}」完成，下一阶段: {next_stage['stage_name'] if next_stage else '无'}")

    return {
        "success": True,
        "completed_stage": stage,
        "next_stage": next_stage,
    }


def skip_stage(stage_id: int) -> bool:
    """跳过阶段（标记为 skipped），不自动激活下一个。"""
    stage = get_project_stage(stage_id)
    if not stage:
        return False

    execute(
        "UPDATE project_stages SET status = 'skipped', completed_at = ? WHERE id = ?",
        (now_str(), stage_id),
    )

    from services.timeline_service import add_event
    from services.workflow_log_service import add_workflow_log

    add_event("stage_skipped", f"阶段跳过：{stage['stage_name']}",
              f"项目 {stage['project_id']} 跳过了阶段「{stage['stage_name']}」",
              "project", stage["project_id"], project_id=stage["project_id"])
    add_workflow_log("stage_skipped", "project", stage["project_id"], "success",
                     f"跳过了阶段「{stage['stage_name']}」")

    return True


def infer_project_stage(project_id: int) -> dict:
    """根据任务完成率、文件上传、时间轴事件推断当前阶段。

    返回: {"inferred_stage": dict|None, "confidence": str, "reasoning": str,
           "task_completion_by_stage": dict}
    """
    stages = get_project_stages(project_id)
    if not stages:
        return {
            "inferred_stage": None,
            "confidence": "low",
            "reasoning": "项目尚未初始化阶段",
            "task_completion_by_stage": {},
        }

    tasks = fetch_all(
        "SELECT * FROM tasks WHERE project_id = ?",
        (project_id,),
    )

    # 按阶段名匹配任务（通过 stage_name 关键词匹配 task title）
    stage_completion = {}
    for s in stages:
        stage_completion[s["id"]] = {"stage_name": s["stage_name"], "total": 0, "done": 0, "rate": 0.0}

    # 简单的关键词匹配：任务标题包含阶段名关键词
    for task in tasks:
        matched_stage = None
        for s in stages:
            if s["stage_name"] in task["title"]:
                matched_stage = s["id"]
                break
        if matched_stage:
            stage_completion[matched_stage]["total"] += 1
            if task["status"] == "done":
                stage_completion[matched_stage]["done"] += 1

    for sid in stage_completion:
        sc = stage_completion[sid]
        if sc["total"] > 0:
            sc["rate"] = sc["done"] / sc["total"]

    # 推断逻辑：找到第一个 rate < 1.0 的阶段 = 当前阶段
    current = get_current_stage(project_id)
    inferred = current
    confidence = "medium"
    reasoning_parts = []

    # 检查当前活跃阶段
    if current:
        cur_data = stage_completion.get(current["id"], {})
        cur_rate = cur_data.get("rate", 0)
        if cur_rate >= 1.0 and cur_data.get("total", 0) > 0:
            reasoning_parts.append(f"当前阶段「{current['stage_name']}」所有任务已完成")
            confidence = "high"
        elif cur_rate >= 0.5:
            reasoning_parts.append(f"当前阶段「{current['stage_name']}」大部分任务已完成 ({cur_rate:.0%})")
            confidence = "medium"
        else:
            reasoning_parts.append(f"当前阶段「{current['stage_name']}」任务完成率 {cur_rate:.0%}")
            confidence = "medium"
    else:
        reasoning_parts.append("无活跃阶段")
        confidence = "low"

    return {
        "inferred_stage": {"stage_name": inferred["stage_name"], "stage_order": inferred["stage_order"]} if inferred else None,
        "confidence": confidence,
        "reasoning": "；".join(reasoning_parts) if reasoning_parts else "无法推断",
        "task_completion_by_stage": stage_completion,
    }


def get_project_progress(project_id: int) -> dict:
    """返回项目进度摘要。"""
    stages = get_project_stages(project_id)
    current = get_current_stage(project_id)
    tasks = fetch_all(
        "SELECT * FROM tasks WHERE project_id = ?",
        (project_id,),
    )

    total_stages = len(stages)
    completed_stages = sum(1 for s in stages if s["status"] == "completed")
    skipped_stages = sum(1 for s in stages if s["status"] == "skipped")
    completion_pct = (completed_stages / total_stages * 100) if total_stages > 0 else 0

    total_tasks = len(tasks)
    done_tasks = sum(1 for t in tasks if t["status"] == "done")
    task_pct = (done_tasks / total_tasks * 100) if total_tasks > 0 else 0

    remaining_tasks = sum(1 for t in tasks if t["status"] in ("todo", "doing"))

    stage_breakdown = []
    for s in stages:
        stage_tasks = [t for t in tasks if s["stage_name"] in t["title"]]
        s_total = len(stage_tasks)
        s_done = sum(1 for t in stage_tasks if t["status"] == "done")
        stage_breakdown.append({
            "stage_id": s["id"],
            "stage_name": s["stage_name"],
            "stage_order": s["stage_order"],
            "status": s["status"],
            "total_tasks": s_total,
            "done_tasks": s_done,
            "task_completion": s_done / s_total if s_total > 0 else 1.0,
            "started_at": s["started_at"],
            "completed_at": s["completed_at"],
        })

    return {
        "project_id": project_id,
        "total_stages": total_stages,
        "completed_stages": completed_stages,
        "skipped_stages": skipped_stages,
        "active_stage": current,
        "stage_completion_pct": round(completion_pct, 1),
        "task_completion_pct": round(task_pct, 1),
        "total_tasks": total_tasks,
        "done_tasks": done_tasks,
        "remaining_tasks": remaining_tasks,
        "all_stages": stages,
        "stage_breakdown": stage_breakdown,
    }
