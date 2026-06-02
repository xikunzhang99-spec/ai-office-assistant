"""
工作流日志服务 — 记录自动工作流执行过程。
Phase 10：用于追踪文件上传分析、知识同步等工作流状态。
"""
from database.db import insert, fetch_one, fetch_all, execute
from utils.date_utils import now_str


def add_workflow_log(
    workflow_type: str,
    source_type: str = None,
    source_id: int = None,
    status: str = "success",
    message: str = "",
    details: str = "",
    run_id: int = None,
    step_id: int = None,
) -> int:
    """记录一条工作流执行日志。"""
    return insert(
        """INSERT INTO workflow_logs
           (workflow_type, source_type, source_id, run_id, step_id, status, message, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (workflow_type, source_type, source_id, run_id, step_id, status, message, details, now_str()),
    )


def get_workflow_logs(
    source_type: str = None,
    source_id: int = None,
    limit: int = 50,
) -> list:
    """查询工作流日志。"""
    conditions = []
    params = []
    if source_type is not None:
        conditions.append("source_type = ?")
        params.append(source_type)
    if source_id is not None:
        conditions.append("source_id = ?")
        params.append(source_id)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM workflow_logs {where} ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return fetch_all(sql, tuple(params))


def get_workflow_log(log_id: int) -> dict | None:
    """获取单条工作流日志。"""
    return fetch_one("SELECT * FROM workflow_logs WHERE id = ?", (log_id,))


def get_all_workflow_logs(
    workflow_type: str = None,
    source_type: str = None,
    status: str = None,
    limit: int = 200,
) -> list:
    """获取工作流日志，支持可选筛选。"""
    conditions = []
    params = []
    if workflow_type:
        conditions.append("workflow_type = ?")
        params.append(workflow_type)
    if source_type:
        conditions.append("source_type = ?")
        params.append(source_type)
    if status:
        conditions.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM workflow_logs {where} ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return fetch_all(sql, tuple(params))


def get_distinct_workflow_types() -> list:
    """获取所有不重复的 workflow_type。"""
    rows = fetch_all("SELECT DISTINCT workflow_type FROM workflow_logs ORDER BY workflow_type")
    return [r["workflow_type"] for r in rows]


def get_distinct_source_types() -> list:
    """获取所有不重复的 source_type。"""
    rows = fetch_all("SELECT DISTINCT source_type FROM workflow_logs WHERE source_type IS NOT NULL ORDER BY source_type")
    return [r["source_type"] for r in rows]


def clear_workflow_logs() -> int:
    """清空 workflow_logs 表。返回删除的数量。"""
    row = fetch_one("SELECT COUNT(*) as cnt FROM workflow_logs")
    count = row["cnt"] if row else 0
    if count > 0:
        execute("DELETE FROM workflow_logs")
    return count
