"""
飞书通知服务 — 通过应用机器人 API 发送/回复消息。
"""
import time
import json
from config.settings import BASE_DIR
import os


# ── 内存级 token 缓存 ──
_token_cache = {"token": "", "expires_at": 0}


def _get_app_credentials() -> tuple[str, str]:
    """从 .env 读取飞书应用凭证。"""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    app_id = os.getenv("FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET", "")
    return app_id, app_secret


def is_configured() -> bool:
    """检查飞书应用机器人是否已配置。"""
    app_id, app_secret = _get_app_credentials()
    return bool(app_id and app_secret)


def get_tenant_access_token() -> dict:
    """获取 tenant_access_token，自动缓存。

    Returns:
        {success: bool, token: str, message: str}
    """
    global _token_cache

    # 缓存有效（提前 60s 过期避免边界问题）
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return {"success": True, "token": _token_cache["token"], "message": "使用缓存 token"}

    app_id, app_secret = _get_app_credentials()
    if not app_id or not app_secret:
        return {"success": False, "token": "", "message": "FEISHU_APP_ID 或 FEISHU_APP_SECRET 未配置"}

    try:
        import requests
    except ImportError:
        return {"success": False, "token": "", "message": "requests 库未安装"}

    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") == 0:
            token = data["tenant_access_token"]
            expire = data.get("expire", 7200)
            _token_cache = {"token": token, "expires_at": time.time() + expire}
            return {"success": True, "token": token, "message": "token 获取成功"}
        else:
            return {"success": False, "token": "", "message": f"获取 token 失败: code={data.get('code')} msg={data.get('msg')}"}
    except Exception as e:
        return {"success": False, "token": "", "message": f"请求异常: {str(e)}"}


def send_feishu_message(receive_id: str, text: str) -> dict:
    """通过应用机器人发送飞书消息。

    Args:
        receive_id: 接收者 open_id 或 chat_id
        text: 消息文本

    Returns:
        {success: bool, message: str}
    """
    token_result = get_tenant_access_token()
    if not token_result["success"]:
        return {"success": False, "message": token_result["message"]}

    try:
        import requests
    except ImportError:
        return {"success": False, "message": "requests 库未安装"}

    # 飞书 text 消息格式
    content = json.dumps({"text": text}, ensure_ascii=False)
    payload = {
        "receive_id": receive_id,
        "msg_type": "text",
        "content": content,
    }

    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            headers={
                "Authorization": f"Bearer {token_result['token']}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )
        data = resp.json()
        if data.get("code") == 0:
            msg_id = data.get("data", {}).get("message_id", "")
            return {"success": True, "message": "消息发送成功", "message_id": msg_id}
        else:
            return {"success": False, "message": f"飞书返回错误: code={data.get('code')} msg={data.get('msg')}"}
    except Exception as e:
        return {"success": False, "message": f"发送异常: {str(e)}"}


def reply_feishu_message(message_id: str, text: str) -> dict:
    """回复飞书消息。

    Args:
        message_id: 被回复的消息 ID
        text: 回复文本

    Returns:
        {success: bool, message: str}
    """
    token_result = get_tenant_access_token()
    if not token_result["success"]:
        return {"success": False, "message": token_result["message"]}

    try:
        import requests
    except ImportError:
        return {"success": False, "message": "requests 库未安装"}

    content = json.dumps({"text": text}, ensure_ascii=False)
    payload = {
        "content": content,
        "msg_type": "text",
    }

    try:
        resp = requests.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
            headers={
                "Authorization": f"Bearer {token_result['token']}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        data = resp.json()
        if data.get("code") == 0:
            return {"success": True, "message": "回复成功"}
        else:
            return {"success": False, "message": f"飞书返回错误: code={data.get('code')} msg={data.get('msg')}"}
    except Exception as e:
        return {"success": False, "message": f"回复异常: {str(e)}"}


def handle_feishu_message(message_id: str, user_text: str, receive_id: str) -> dict:
    """处理飞书用户消息 → AI 问答 → 回复。

    Args:
        message_id: 飞书消息 ID（用于回复）
        user_text: 用户发送的文本
        receive_id: 发送者 open_id（用于单发回复）

    Returns:
        {success: bool, message: str, answer: str}
    """
    from services.workflow_log_service import add_workflow_log

    # 1. 调用 AI 问答
    try:
        from services.rag_service import answer_with_hybrid_rag
        result = answer_with_hybrid_rag(user_text)
        answer = result.get("answer", "抱歉，无法处理您的问题。")
    except Exception as e:
        answer = f"AI 问答异常: {str(e)}"
        add_workflow_log("feishu_ai_qa", "feishu", None, "error",
                         f"问题: {user_text[:100]} | 错误: {str(e)}")
        return {"success": False, "message": str(e), "answer": ""}

    # 2. 回复消息
    reply_result = reply_feishu_message(message_id, answer)

    # 3. 如果回复失败，尝试直接发送给用户
    if not reply_result["success"]:
        send_result = send_feishu_message(receive_id, answer)
        reply_result = send_result

    # 4. 记录日志
    status = "success" if reply_result["success"] else "error"
    add_workflow_log("feishu_ai_qa", "feishu", None, status,
                     f"Q: {user_text[:100]} | A: {answer[:100]}")

    return {"success": reply_result["success"], "message": reply_result["message"], "answer": answer}


def send_daily_reminder(receive_id: str) -> dict:
    """发送每日任务提醒。

    Args:
        receive_id: 接收者 open_id
    """
    from services.reminder_service import build_reminder_message
    from services.workflow_log_service import add_workflow_log

    message = build_reminder_message()
    result = send_feishu_message(receive_id, message)

    status = "success" if result["success"] else "error"
    add_workflow_log("daily_reminder_sent", "reminder", None, status,
                     result.get("message", ""))
    return result


def send_task_reminder(task_id: int, receive_id: str) -> dict:
    """发送单个任务提醒。

    Args:
        task_id: 任务 ID
        receive_id: 接收者 open_id
    """
    from database.db import fetch_one
    from services.reminder_service import mark_reminder_sent
    from services.workflow_log_service import add_workflow_log

    task = fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not task:
        return {"success": False, "message": f"任务 #{task_id} 不存在"}

    p_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task["priority"], "")
    lines = [
        "📌 任务提醒",
        "",
        f"{p_emoji} {task['title']}",
    ]
    if task.get("description"):
        lines.append(f"描述: {task['description']}")
    if task.get("due_date"):
        lines.append(f"截止日期: {task['due_date']}")
    lines.append(f"优先级: {task['priority']}")

    result = send_feishu_message(receive_id, "\n".join(lines))

    if result["success"]:
        mark_reminder_sent(task_id)

    status = "success" if result["success"] else "error"
    add_workflow_log("task_reminder_sent", "task", task_id, status,
                     result.get("message", ""))
    return result


def test_feishu_connection(receive_id: str) -> dict:
    """测试飞书应用机器人连接。"""
    from services.workflow_log_service import add_workflow_log

    result = send_feishu_message(receive_id, "✅ 飞书应用机器人连接测试成功！\n\nAI 办公助理已就绪。")

    status = "success" if result["success"] else "error"
    add_workflow_log("feishu_test", "feishu", None, status,
                     result.get("message", ""))
    return result
