from fastapi import FastAPI, Request
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# =========================
# 飞书配置
# =========================

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")


# =========================
# 获取 tenant_access_token
# =========================

def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
    response = requests.post(url, json=payload)
    result = response.json()
    if result.get("code") != 0:
        print(f"获取 tenant_access_token 失败: code={result.get('code')} msg={result.get('msg')}")
        return None
    return result.get("tenant_access_token")


# =========================
# 回复消息
# =========================

def reply_message(message_id: str, text: str):
    tenant_access_token = get_tenant_access_token()
    if not tenant_access_token:
        print("获取 tenant_access_token 失败")
        return
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"
    headers = {
        "Authorization": f"Bearer {tenant_access_token}",
        "Content-Type": "application/json",
    }
    data = {
        "content": json.dumps({"text": text}),
        "msg_type": "text",
    }
    response = requests.post(url, headers=headers, json=data)
    print("回复消息结果：", response.json())
    return response.json()


# =========================
# 事件去重
# =========================

def _is_duplicate_event(event_id: str, message_id: str) -> bool:
    """检查飞书事件是否已经处理过。用 event_id 优先，否则用 message_id。"""
    from database.db import fetch_one
    dedup_key = event_id or message_id
    if not dedup_key:
        return False

    existing = fetch_one(
        "SELECT id FROM processed_feishu_events WHERE event_id = ? OR (message_id = ? AND event_id IS NULL)",
        (dedup_key, message_id),
    )
    return existing is not None


def _record_event(event_id: str, message_id: str, open_id: str, chat_id: str,
                  message_text: str, status: str = "pending"):
    """记录飞书事件处理状态。"""
    from database.db import insert, execute
    from utils.date_utils import now_str

    # 用 event_id 作为唯一键，无 event_id 时用 message_id
    dedup_key = event_id or f"msg:{message_id}" if message_id else None
    if not dedup_key:
        return None

    try:
        return insert(
            """INSERT INTO processed_feishu_events
               (event_id, message_id, open_id, chat_id, message_text, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_id or dedup_key, message_id, open_id, chat_id, message_text, status, now_str()),
        )
    except Exception:
        # UNIQUE constraint violation → already exists, silently skip
        return None


def _update_event_status(event_id: str, message_id: str, status: str):
    """更新事件处理状态。"""
    from database.db import execute
    dedup_key = event_id or f"msg:{message_id}" if message_id else None
    if not dedup_key:
        return
    try:
        execute(
            "UPDATE processed_feishu_events SET status = ? WHERE event_id = ?",
            (status, dedup_key),
        )
    except Exception:
        pass


# =========================
# 飞书 webhook
# =========================

@app.post("/webhook/feishu")
async def feishu_webhook(request: Request):
    data = await request.json()

    print("收到飞书消息：")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    # 飞书 challenge 校验
    if "challenge" in data:
        return {"challenge": data["challenge"]}

    # 提取字段
    event = data.get("event", {})
    message = event.get("message", {})
    sender = event.get("sender", {})
    header = data.get("header", {})

    event_id = header.get("event_id", "")
    message_id = message.get("message_id")

    sender_info = sender.get("sender_id", {})
    open_id = sender_info.get("open_id", "") if isinstance(sender_info, dict) else ""
    chat_id = message.get("chat_id", "")

    msg_type = message.get("message_type", "text")
    content_str = message.get("content", "{}")
    try:
        content_json = json.loads(content_str)
        user_text = content_json.get("text", "")
    except Exception:
        user_text = ""

    print(f"消息类型: {msg_type} | 用户消息: {user_text}")

    # ── 去重检查 ──
    if _is_duplicate_event(event_id, message_id):
        print(f"重复事件，跳过: event_id={event_id} message_id={message_id}")
        from services.workflow_log_service import add_workflow_log
        add_workflow_log("feishu_duplicate_skipped", "feishu", None, "success",
                         f"重复事件已跳过: event_id={event_id} message_id={message_id}")
        return {"code": 0}

    # 记录事件（pending）
    display_text = user_text or f"[{msg_type}]"
    _record_event(event_id, message_id, open_id, chat_id, display_text, "pending")

    # ── 按消息类型路由 ──
    if msg_type == "file":
        from services.feishu_file_service import handle_feishu_file_message
        result = handle_feishu_file_message(event, message_id, open_id)
    elif msg_type == "image":
        result = {"reply_text": "暂不支持图片消息，请发送文本或文件。",
                  "action": "image_unsupported", "success": True}
    else:
        from services.feishu_message_service import handle_feishu_text_message
        result = handle_feishu_text_message(user_text, message_id, open_id)

    # ── 统一回复（只在此处调用一次 reply_message）──
    if result.get("reply_text"):
        reply_message(message_id, result["reply_text"])

    # 更新事件状态
    status = "success" if result["success"] else "failed"
    _update_event_status(event_id, message_id, status)

    return {"code": 0}
