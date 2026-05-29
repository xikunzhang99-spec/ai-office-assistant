"""
飞书会话状态管理服务 — 持久化多轮对话上下文。
Session 30 分钟自动过期。user_key 优先使用 open_id。
"""
import json
from datetime import datetime, timedelta
from database.db import fetch_one, insert, execute
from services.workflow_log_service import add_workflow_log

SESSION_TIMEOUT_MINUTES = 30


def _now_str() -> str:
    return datetime.now().isoformat()


def _expires_at() -> str:
    return (datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)).isoformat()


def get_or_create_session(user_key: str, chat_id: str = None, open_id: str = None) -> dict:
    """获取或创建用户的活跃会话。已过期 session 自动失效后重新创建。

    Returns:
        session dict with keys: id, user_key, chat_id, open_id, current_mode,
        last_file_id, last_analysis_json, pending_actions_json, last_question,
        last_answer, status, expires_at, created_at, updated_at
    """
    existing = fetch_one(
        "SELECT * FROM feishu_sessions WHERE user_key = ?",
        (user_key,),
    )
    if existing:
        if existing.get("status") == "active" and not is_session_expired(existing):
            # 刷新过期时间
            new_expiry = _expires_at()
            execute(
                "UPDATE feishu_sessions SET expires_at = ?, updated_at = ? WHERE id = ?",
                (new_expiry, _now_str(), existing["id"]),
            )
            existing["expires_at"] = new_expiry
            return existing
        else:
            # 旧的已过期或非 active → 标记过期，稍后创建新的
            if existing.get("status") == "active":
                execute(
                    "UPDATE feishu_sessions SET status = 'expired' WHERE id = ?",
                    (existing["id"],),
                )
                add_workflow_log("feishu_session_expired", "feishu", existing["id"], "success",
                                 f"Session expired for user_key={user_key}")

    # 创建新 session（使用 INSERT OR REPLACE 处理可能存在的 UNIQUE 冲突）
    now = _now_str()
    exp = _expires_at()
    session_id = insert(
        """INSERT OR REPLACE INTO feishu_sessions
           (user_key, chat_id, open_id, current_mode, status, expires_at, created_at, updated_at)
           VALUES (?, ?, ?, 'idle', 'active', ?, ?, ?)""",
        (user_key, chat_id, open_id, exp, now, now),
    )
    add_workflow_log("feishu_session_created", "feishu", session_id, "success",
                     f"Session created for user_key={user_key}")

    return fetch_one("SELECT * FROM feishu_sessions WHERE id = ?", (session_id,))


def update_session(user_key: str, **kwargs) -> bool:
    """更新会话字段。自动刷新 expires_at 和 updated_at。

    Supported kwargs: current_mode, last_file_id, last_analysis_json,
    pending_actions_json, last_question, last_answer, status
    """
    allowed = {"current_mode", "last_file_id", "last_analysis_json",
               "pending_actions_json", "last_question", "last_answer", "status"}
    updates = {}
    for k, v in kwargs.items():
        if k in allowed:
            updates[k] = v

    if not updates:
        return False

    updates["expires_at"] = _expires_at()
    updates["updated_at"] = _now_str()

    set_clauses = [f"{k} = ?" for k in updates.keys()]
    values = list(updates.values()) + [user_key]

    execute(
        f"UPDATE feishu_sessions SET {', '.join(set_clauses)} WHERE user_key = ?",
        tuple(values),
    )
    add_workflow_log("feishu_session_updated", "feishu", None, "success",
                     f"Session updated for user_key={user_key}: {list(updates.keys())}")
    return True


def get_active_session(user_key: str) -> dict | None:
    """获取用户活跃且未过期的会话。过期返回 None。"""
    session = fetch_one(
        "SELECT * FROM feishu_sessions WHERE user_key = ? AND status = 'active'",
        (user_key,),
    )
    if not session:
        return None
    if is_session_expired(session):
        execute(
            "UPDATE feishu_sessions SET status = 'expired' WHERE id = ?",
            (session["id"],),
        )
        return None
    return session


def clear_session(user_key: str) -> bool:
    """清空会话上下文，保留 session 记录但重置状态。"""
    execute(
        """UPDATE feishu_sessions SET
           current_mode = 'idle',
           last_file_id = NULL,
           last_analysis_json = NULL,
           pending_actions_json = NULL,
           last_question = NULL,
           last_answer = NULL,
           expires_at = ?,
           updated_at = ?
           WHERE user_key = ?""",
        (_expires_at(), _now_str(), user_key),
    )
    add_workflow_log("feishu_session_cleared", "feishu", None, "success",
                     f"Session cleared for user_key={user_key}")
    return True


def is_session_expired(session: dict) -> bool:
    """检查会话是否已过期。"""
    if not session or not session.get("expires_at"):
        return True
    try:
        expires = datetime.fromisoformat(session["expires_at"])
        return datetime.now() > expires
    except (ValueError, TypeError):
        return True


def save_pending_actions(user_key: str, actions: list) -> bool:
    """保存待执行的建议动作到会话。"""
    json_str = json.dumps(actions, ensure_ascii=False)
    result = update_session(user_key, pending_actions_json=json_str, current_mode="pending_actions")
    add_workflow_log("feishu_pending_action_saved", "feishu", None, "success",
                     f"Saved {len(actions)} pending actions for user_key={user_key}")
    return result


def get_pending_actions(user_key: str) -> list:
    """从会话读取待执行动作。"""
    session = get_active_session(user_key)
    if not session or not session.get("pending_actions_json"):
        return []
    try:
        return json.loads(session["pending_actions_json"])
    except (json.JSONDecodeError, TypeError):
        return []


def save_last_file_analysis(user_key: str, file_id: int, analysis_result: dict) -> bool:
    """保存最近一次文件分析结果到会话。"""
    json_str = json.dumps(analysis_result, ensure_ascii=False)
    return update_session(
        user_key,
        last_file_id=file_id,
        last_analysis_json=json_str,
        current_mode="file_analysis",
    )


def get_last_file_analysis(user_key: str) -> dict | None:
    """从会话获取最近一次文件分析结果。"""
    session = get_active_session(user_key)
    if not session or not session.get("last_analysis_json") or not session.get("last_file_id"):
        return None
    try:
        analysis = json.loads(session["last_analysis_json"])
        return {
            "file_id": session["last_file_id"],
            "analysis": analysis,
        }
    except (json.JSONDecodeError, TypeError):
        return None
