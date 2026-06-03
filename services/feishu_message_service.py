"""
飞书消息处理服务 — 命令解析、AI 问答、数据创建、AI 建议执行、多轮上下文。
feishu_api.py 只负责接收事件，业务逻辑全部在此模块。
"""
import re
import json
from services.workflow_log_service import add_workflow_log
from utils.date_utils import today_str

MAX_REPLY_LENGTH = 1000
MAX_SOURCES = 3


def _fe(reason, suggestion=""):
    """快捷格式化错误回复。"""
    from services.feishu.reply_formatter import format_error
    return format_error(reason, suggestion)


def _fs(result):
    """快捷格式化成功回复。"""
    from services.feishu.reply_formatter import format_success
    return format_success(result)

# AI 建议暂存（open_id → actions list）— 内存 fallback
PENDING_ACTIONS = {}

# 文档分析上下文暂存（open_id → {file_id, analysis, created_at}）— 内存 fallback
FEISHU_DOCUMENT_CONTEXTS = {}


# ── Session 读取辅助 ──

def _get_actions_from_session(sender_id: str) -> list:
    """从 DB session 读取 pending actions，fallback 到内存。"""
    try:
        from services.feishu_session_service import get_pending_actions
        actions = get_pending_actions(sender_id)
        if actions:
            return actions
    except Exception:
        pass
    return PENDING_ACTIONS.get(sender_id, [])


def _save_actions_to_session(sender_id: str, actions: list):
    """双写：DB session + 内存 fallback。"""
    try:
        from services.feishu_session_service import save_pending_actions
        save_pending_actions(sender_id, actions)
    except Exception:
        pass
    if actions:
        PENDING_ACTIONS[sender_id] = actions
    else:
        PENDING_ACTIONS.pop(sender_id, None)


def _get_doc_context_from_session(sender_id: str) -> dict | None:
    """从 DB session 读取文档分析上下文，fallback 到内存。"""
    try:
        from services.feishu_session_service import get_last_file_analysis
        fa = get_last_file_analysis(sender_id)
        if fa:
            return {"file_id": fa["file_id"], "analysis": fa["analysis"]}
    except Exception:
        pass
    return FEISHU_DOCUMENT_CONTEXTS.get(sender_id)

COMMANDS_HELP = None  # 由 _cmd_help 通过 format_help() 生成


def handle_feishu_text_message(user_text: str, message_id: str = None, sender_id: str = None) -> dict:
    """处理飞书文本消息。支持多轮上下文。

    Args:
        user_text: 用户发送的文本
        message_id: 飞书消息 ID
        sender_id: 发送者 open_id（用作 user_key）
    """
    text = (user_text or "").strip()
    sid = sender_id or "default"

    # ── 启动工作流追踪 ──
    try:
        from services.workflow_service import WorkflowService
        wf_run = WorkflowService.start_run("feishu_message", "feishu", None,
            {"text": text[:200], "sender_id": sid})
        wf_run_id = wf_run["id"]
    except Exception:
        wf_run_id = None

    def _wf_complete_step(step_name, output=""):
        if wf_run_id:
            try:
                WorkflowService.complete_step(wf_run_id, step_name, output)
            except Exception:
                pass

    def _wf_complete_run(result=None):
        if wf_run_id:
            try:
                WorkflowService.complete_run(wf_run_id, result)
            except Exception:
                pass

    # 空消息
    if not text:
        _wf_complete_step("detect_intent", "empty message")
        _wf_complete_run({"action": "empty"})
        return {"reply_text": "请输入问题，或发送 /帮助 查看命令。", "action": "empty", "success": True}

    # ── 确保 session 存在 ──
    try:
        from services.feishu_session_service import get_or_create_session
        get_or_create_session(sid)
    except Exception:
        pass

    # ── 会话上下文意图检测（优先于具体命令）──
    intent_result = _detect_session_intent(text, sid)
    if intent_result:
        _wf_complete_step("detect_intent", f"session_intent: {intent_result.get('action', 'unknown')}")
        _wf_complete_step("route_command", "session_intent")
        _wf_complete_step("execute_action", str(intent_result.get('success', False)))
        _wf_complete_step("build_reply", str(intent_result.get('reply_text', ''))[:80])
        _wf_complete_run({"action": intent_result.get("action")})
        return intent_result

    # ── 意图检测（内容类型识别）──
    intent_type = "unknown"
    try:
        from services.ai_service import detect_content_intent
        intent_result = detect_content_intent(text)
        intent_type = intent_result.get("intent_type", "unknown")
    except Exception:
        pass
    _wf_complete_step("detect_intent", f"content_type={intent_type}")

    # ── 执行全部建议动作 ──
    if re.match(r'^执行全部$', text):
        _wf_complete_step("route_command", "execute_all")
        result = _cmd_execute_all(sid)
        _wf_complete_step("execute_action", str(result.get('success', False)))
        _wf_complete_step("build_reply", str(result.get('reply_text', ''))[:80])
        _wf_complete_run({"action": result.get("action")})
        return result

    # ── 执行建议动作（单条）──
    exec_match = re.match(r'^执行\s*(\d+)$', text)
    if exec_match:
        _wf_complete_step("route_command", "execute_single")
        idx = int(exec_match.group(1)) - 1
        result = _cmd_execute_action(sid, idx)
        _wf_complete_step("execute_action", str(result.get('success', False)))
        _wf_complete_step("build_reply", str(result.get('reply_text', ''))[:80])
        _wf_complete_run({"action": result.get("action")})
        return result

    # ── 文档选段命令（优先匹配更具体的模式）──
    section_match = re.match(r'^把第?\s*(\d+)\s*部分?创建成(项目|任务|时间轴)', text)
    section_all_match = re.match(r'^把(.+?)全部创建成(任务)', text)
    section_kw_match = re.match(r'^把(.+?)部分?(?:写入|创建成)(时间轴|项目|任务)?', text)
    if section_match:
        _wf_complete_step("route_command", "document_section")
        idx = int(section_match.group(1)) - 1
        target = section_match.group(2)
        result = _handle_document_section_command(sid, section_index=idx, target_type=target)
        _wf_complete_step("execute_action", str(result.get('success', False)))
        _wf_complete_step("build_reply", str(result.get('reply_text', ''))[:80])
        _wf_complete_run({"action": result.get("action")})
        return result
    elif section_all_match:
        _wf_complete_step("route_command", "document_section_all")
        kw = section_all_match.group(1).strip()
        result = _handle_document_section_command(sid, keyword=kw, create_all_tasks=True)
        _wf_complete_step("execute_action", str(result.get('success', False)))
        _wf_complete_step("build_reply", str(result.get('reply_text', ''))[:80])
        _wf_complete_run({"action": result.get("action")})
        return result
    elif section_kw_match:
        _wf_complete_step("route_command", "document_section_kw")
        kw = section_kw_match.group(1).strip()
        target = section_kw_match.group(2) or "时间轴"
        result = _handle_document_section_command(sid, keyword=kw, target_type=target)
        _wf_complete_step("execute_action", str(result.get('success', False)))
        _wf_complete_step("build_reply", str(result.get('reply_text', ''))[:80])
        _wf_complete_run({"action": result.get("action")})
        return result

    # ── 上下文指代（它/这个/刚才/上面的）──
    context_result = _handle_context_reference(text, sid)
    if context_result:
        _wf_complete_step("route_command", "context_reference")
        _wf_complete_step("execute_action", str(context_result.get('success', False)))
        _wf_complete_step("build_reply", str(context_result.get('reply_text', ''))[:80])
        _wf_complete_run({"action": context_result.get("action")})
        return context_result

    # ── 命令路由 ──
    if text.startswith("/"):
        _wf_complete_step("route_command", f"command: {text.split()[0] if text.split() else text}")
        result = _handle_command(text, message_id, sid)
        _wf_complete_step("execute_action", str(result.get('success', False)))
        _wf_complete_step("build_reply", str(result.get('reply_text', ''))[:80])
        _wf_complete_run({"action": result.get("action")})
        return result

    # ── 默认：AI 问答 ──
    _wf_complete_step("route_command", "ai_qa")
    result = _handle_ai_qa(text, message_id, sid)
    _wf_complete_step("ai_qa", str(result.get('success', False)))
    _wf_complete_step("build_reply", str(result.get('reply_text', ''))[:80])
    _wf_complete_run({"action": result.get("action")})
    return result


def _handle_command(text: str, message_id: str = None, sender_id: str = None) -> dict:
    """命令分发。"""
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    try:
        if cmd in ("/帮助", "/help"):
            return _cmd_help()

        if cmd == "/任务":
            return _cmd_tasks(arg)

        if cmd == "/总结":
            return _cmd_summary(arg)

        if cmd == "/问":
            if not arg.strip():
                return {"reply_text": "请在 /问 后输入问题。", "action": "ai_query_empty", "success": True}
            return _handle_ai_qa(arg, message_id, sender_id)

        if cmd == "/新任务":
            return _cmd_create_task(arg)

        if cmd == "/新项目":
            return _cmd_create_project(arg)

        if cmd == "/新客户":
            return _cmd_create_client(arg)

        if cmd == "/今日建议":
            return _cmd_daily_suggestions()

        if cmd == "/客户建议":
            return _cmd_client_suggestions(arg)

        if cmd == "/项目建议":
            return _cmd_project_suggestions(arg)

        if cmd == "/项目状态":
            return _cmd_project_status(arg)

        if cmd == "/客户状态":
            return _cmd_client_status(arg)

        if cmd == "/项目风险":
            return _cmd_project_risk(arg)

        return {"reply_text": f"未知命令「{cmd}」。发送 /帮助 查看可用命令。",
                "action": "unknown_command", "success": True}

    except Exception as e:
        add_workflow_log("feishu_command_error", "feishu", None, "error",
                         f"命令: {text[:100]} | {str(e)}")
        return {"reply_text": "系统暂时处理失败，请稍后再试。",
                "action": "command_error", "success": False}


# ── 查询命令 ──

def _cmd_help() -> dict:
    from services.feishu.reply_formatter import format_help
    return {"reply_text": format_help(), "action": "help", "success": True}


def _cmd_tasks(arg: str) -> dict:
    from services.reminder_service import get_today_tasks, get_overdue_tasks, get_due_tasks
    sub = arg.strip()

    if sub == "今天":
        tasks = get_today_tasks()
        if not tasks:
            return {"reply_text": "✅ 今日无到期任务。", "action": "tasks_today", "success": True}
        lines = ["📅 今日任务", ""]
        for t in tasks:
            emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t["priority"], "")
            status = {"todo": "⭕", "doing": "🔵"}.get(t["status"], "")
            lines.append(f"{status} {emoji} {t['title']}")
        return {"reply_text": "\n".join(lines), "action": "tasks_today", "success": True}

    elif sub == "逾期":
        tasks = get_overdue_tasks()
        if not tasks:
            return {"reply_text": "✅ 无逾期任务。", "action": "tasks_overdue", "success": True}
        lines = [f"⚠️ 逾期任务 ({len(tasks)})", ""]
        for t in tasks:
            lines.append(f"🔴 {t['title']} — {t.get('due_date', '')}")
        return {"reply_text": "\n".join(lines), "action": "tasks_overdue", "success": True}

    elif sub in ("未来3天", "即将到期"):
        tasks = get_due_tasks(3)
        if not tasks:
            return {"reply_text": "✅ 未来3天无到期任务。", "action": "tasks_upcoming", "success": True}
        lines = [f"🔜 未来3天 ({len(tasks)})", ""]
        for t in tasks:
            lines.append(f"- [{t['priority']}] {t['title']} — {t.get('due_date', '')}")
        return {"reply_text": "\n".join(lines), "action": "tasks_upcoming", "success": True}

    else:
        return {"reply_text": "用法：\n/任务 今天\n/任务 逾期\n/任务 未来3天",
                "action": "tasks_help", "success": True}


def _cmd_summary(arg: str) -> dict:
    if arg.strip() == "今天":
        try:
            from services.reminder_service import generate_today_briefing
            briefing = generate_today_briefing()
            return {"reply_text": _truncate(briefing), "action": "summary_today", "success": True}
        except Exception as e:
            return {"reply_text": f"生成简报失败: {str(e)[:200]}", "action": "summary_error", "success": False}
    else:
        return {"reply_text": "用法：/总结 今天", "action": "summary_help", "success": True}


# ── 创建命令 ──

def _cmd_create_client(arg: str) -> dict:
    from services.feishu_command_parser import parse_create_client_command
    from services.client_service import get_or_create_client

    parsed = parse_create_client_command(f"/新客户 {arg}")
    name = parsed["name"]
    if not name:
        return {"reply_text": "请指定客户名称。\n示例：/新客户 张三公司 联系人:张总 电话:138xxxx",
                "action": "create_client_help", "success": True}

    try:
        result = get_or_create_client(name, description=parsed.get("description", ""),
                                      contact_info=parsed.get("contact_info", ""))
        client_id = result["client_id"]
        created = result["created"]

        status = "created" if created else "existing"
        add_workflow_log("feishu_create_client", "client", client_id, "success",
                         f"飞书创建客户: {name} | 状态: {status}")

        if created:
            reply = f"✅ 已创建客户：{name}"
        else:
            reply = f"ℹ️ 客户「{name}」已存在，无需重复创建"
        if parsed.get("contact_info"):
            reply += f"\n联系信息：{parsed['contact_info']}"
        return {"reply_text": reply, "action": "create_client", "success": True}

    except Exception as e:
        add_workflow_log("feishu_create_client", "client", None, "error", str(e))
        return {"reply_text": _fe("创建客户失败"), "action": "create_client_error", "success": False}


def _cmd_create_project(arg: str) -> dict:
    from services.feishu_command_parser import parse_create_project_command
    from services.project_service import get_or_create_project
    from services.client_service import search_clients

    parsed = parse_create_project_command(f"/新项目 {arg}")
    name = parsed["name"]
    if not name:
        return {"reply_text": "请指定项目名称。\n示例：/新项目 AI办公助理 客户:张三公司",
                "action": "create_project_help", "success": True}

    # 尝试匹配客户
    client_id = None
    client_name = parsed.get("client_name", "")
    match_hint = ""
    if client_name:
        matches = search_clients(keyword=client_name, limit=5)
        if matches:
            client_id = matches[0]["id"]
            if len(matches) > 1:
                match_hint = f"\n匹配到 {len(matches)} 个客户，已关联「{matches[0]['name']}」"
        else:
            match_hint = "\n⚠️ 未找到匹配客户，已创建为未关联项目"

    try:
        result = get_or_create_project(name=name, client_id=client_id)
        project_id = result["project_id"]
        created = result["created"]

        status = "created" if created else "existing"
        add_workflow_log("feishu_create_project", "project", project_id, "success",
                         f"飞书创建项目: {name} | 状态: {status} | 客户: {client_name}")

        if created:
            reply = f"✅ 已创建项目：{name}"
        else:
            reply = f"ℹ️ 项目「{name}」已存在，无需重复创建"
        if client_name:
            reply += f"\n关联客户：{client_name}"
        if match_hint and created:
            reply += match_hint
        return {"reply_text": reply, "action": "create_project", "success": True}

    except Exception as e:
        add_workflow_log("feishu_create_project", "project", None, "error", str(e))
        return {"reply_text": _fe("创建项目失败"), "action": "create_project_error", "success": False}


def _cmd_create_task(arg: str) -> dict:
    from services.feishu_command_parser import parse_create_task_command
    from services.task_service import get_or_create_task
    from services.project_service import search_projects
    from services.client_service import search_clients

    parsed = parse_create_task_command(f"/新任务 {arg}")
    title = parsed["title"]
    if not title:
        return {"reply_text": "请指定任务标题。\n示例：/新任务 跟进合同 项目:AI办公助理 客户:张三公司 截止:明天 优先级:高",
                "action": "create_task_help", "success": True}

    # 匹配项目
    project_id = None
    project_name = parsed.get("project_name", "")
    project_hint = ""
    if project_name:
        matches = search_projects(keyword=project_name, limit=5)
        if matches:
            project_id = matches[0]["id"]
            if len(matches) > 1:
                project_hint = f"\n匹配到 {len(matches)} 个项目，已关联「{matches[0]['name']}」"
        else:
            project_hint = "\n⚠️ 未找到匹配项目，已创建为未关联任务"

    # 匹配客户
    client_id = None
    client_name = parsed.get("client_name", "")
    client_hint = ""
    if client_name:
        matches = search_clients(keyword=client_name, limit=5)
        if matches:
            client_id = matches[0]["id"]
            if len(matches) > 1:
                client_hint = f"\n匹配到 {len(matches)} 个客户，已关联「{matches[0]['name']}」"
        else:
            client_hint = "\n⚠️ 未找到匹配客户，已创建为未关联任务"

    try:
        result = get_or_create_task(
            title=title,
            priority=parsed.get("priority") or "medium",
            due_date=parsed.get("due_date", ""),
            project_id=project_id,
            client_id=client_id,
        )
        task_id = result["task_id"]
        created = result["created"]

        status = "created" if created else "existing"
        add_workflow_log("feishu_create_task", "task", task_id, "success",
                         f"飞书创建任务: {title} | 状态: {status} | 项目: {project_name} | 客户: {client_name}")

        if created:
            reply = f"✅ 已创建任务：{title}"
        else:
            reply = f"ℹ️ 任务「{title}」已存在，无需重复创建"

        if parsed.get("priority"):
            p_cn = {"high": "🔴 高", "medium": "🟡 中", "low": "🟢 低"}.get(parsed["priority"], parsed["priority"])
            reply += f"\n优先级：{p_cn}"
        if parsed.get("due_date"):
            reply += f"\n截止日期：{parsed['due_date']}"
        if project_name:
            reply += f"\n关联项目：{project_name}"
        if client_name:
            reply += f"\n关联客户：{client_name}"
        if created and project_hint:
            reply += project_hint
        if created and client_hint:
            reply += client_hint
        return {"reply_text": reply, "action": "create_task", "success": True}

    except Exception as e:
        add_workflow_log("feishu_create_task", "task", None, "error", str(e))
        return {"reply_text": _fe("创建任务失败"), "action": "create_task_error", "success": False}


# ── AI 建议执行 ──

def _cmd_execute_action(sender_id: str, idx: int) -> dict:
    """执行暂存的 AI 建议动作（从 session 读取）。"""
    actions = _get_actions_from_session(sender_id)
    if not actions:
        return {"reply_text": "没有找到可执行建议，请先上传文件或发起 AI 问答。",
                "action": "execute_no_pending", "success": True}

    if idx < 0 or idx >= len(actions):
        return {"reply_text": f"无效的动作编号。当前有 {len(actions)} 条建议，请输入 执行1 到 执行{len(actions)}。",
                "action": "execute_invalid_index", "success": True}

    try:
        from services.action_executor_service import execute_action

        action = actions[idx]
        result = execute_action(action)

        if result["success"]:
            add_workflow_log("feishu_action_confirmed", "ai_suggestion", result.get("result_id"), "success",
                             f"执行建议 #{idx+1}: {action.get('title', '')} | {result['message']}")
            reply = f"✅ {result['message']}\n\n已执行建议 #{idx+1}"
            # 清除已执行的建议
            del actions[idx]
            _save_actions_to_session(sender_id, actions)
            return {"reply_text": reply, "action": "execute_action", "success": True}
        else:
            add_workflow_log("feishu_execute_action", "ai_suggestion", None, "error",
                             f"执行建议 #{idx+1} 失败: {result['message']}")
            return {"reply_text": _fe("执行失败"), "action": "execute_action_error", "success": False}

    except Exception as e:
        add_workflow_log("feishu_execute_action", "ai_suggestion", None, "error", str(e))
        return {"reply_text": _fe("执行异常"), "action": "execute_action_error", "success": False}


# ── 执行全部 ──

def _cmd_execute_all(sender_id: str) -> dict:
    """遍历所有 pending actions 并逐个执行（从 session 读取）。"""
    actions = _get_actions_from_session(sender_id)
    if not actions:
        return {"reply_text": "没有找到可执行建议。请先上传文件或发起 AI 问答。",
                "action": "execute_all_no_pending", "success": True}

    from services.action_executor_service import execute_action

    success_count = 0
    fail_count = 0
    lines = ["📋 批量执行结果：", ""]

    for i, action in enumerate(actions):
        try:
            result = execute_action(action)
            if result["success"]:
                success_count += 1
                lines.append(f"✅ #{i+1} {result['message']}")
            else:
                fail_count += 1
                lines.append(f"❌ #{i+1} {result['message']}")
        except Exception as e:
            fail_count += 1
            lines.append(f"❌ #{i+1} 执行异常: {str(e)[:100]}")

    # 清除已执行的建议
    _save_actions_to_session(sender_id, [])

    add_workflow_log("document_action_execute_all", "ai_suggestion", None, "success",
                     f"批量执行: {success_count} 成功, {fail_count} 失败")

    lines.append("")
    lines.append(f"完成：{success_count} 条成功，{fail_count} 条失败")
    return {"reply_text": "\n".join(lines), "action": "execute_all", "success": True}


# ── 主动建议命令 ──

def _cmd_daily_suggestions() -> dict:
    """生成今日主动建议。"""
    try:
        from services.proactive_suggestion_service import generate_daily_suggestions
        s = generate_daily_suggestions()

        lines = ["📋 今日工作建议", ""]

        # AI 总结
        if s.get("summary"):
            lines.append(f"💡 {s['summary']}")
            lines.append("")

        # 逾期事项
        if s["overdue_items"]:
            lines.append(f"⚠️ 逾期事项 ({len(s['overdue_items'])})")
            for t in s["overdue_items"][:5]:
                p_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t["priority"], "")
                lines.append(f"  {p_emoji} {t['title']} — {t.get('due_date', '')}")
            lines.append("")

        # 今日重点
        if s["priority_tasks"]:
            lines.append(f"🔴 今日高优先级任务 ({len(s['priority_tasks'])})")
            for t in s["priority_tasks"][:5]:
                lines.append(f"  - {t['title']}")
            lines.append("")

        # 需跟进客户
        if s["clients_to_follow"]:
            lines.append(f"📞 需跟进客户 ({len(s['clients_to_follow'])})")
            for c in s["clients_to_follow"][:3]:
                proj_count = c.get("active_projects", 0)
                lines.append(f"  - {c['name']}（{proj_count} 个活跃项目）")
            lines.append("")

        # 项目风险
        if s["project_risks"]:
            lines.append(f"🚨 项目风险 ({len(s['project_risks'])})")
            for r in s["project_risks"][:3]:
                client_info = f"[{r.get('client_name', '')}] " if r.get("client_name") else ""
                lines.append(f"  - {client_info}{r['name']}: {r.get('description', '')}")
            lines.append("")

        # 未执行建议
        if s["pending_document_actions"]:
            lines.append(f"📄 未执行文件建议 ({len(s['pending_document_actions'])})")
            lines.append("  回复「上传文件」查看详情")

        if not any([s["priority_tasks"], s["overdue_items"], s["clients_to_follow"],
                    s["project_risks"]]):
            lines.append("✅ 今日一切正常，无特别关注事项。")

        add_workflow_log("feishu_daily_suggestions", "feishu", None, "success",
                         f"每日建议: {len(s.get('priority_tasks', []))} 任务")
        return {"reply_text": "\n".join(lines), "action": "daily_suggestions", "success": True}

    except Exception as e:
        add_workflow_log("feishu_daily_suggestions", "feishu", None, "error", str(e))
        return {"reply_text": _fe("生成建议失败"),
                "action": "daily_suggestions_error", "success": False}


def _cmd_client_suggestions(arg: str) -> dict:
    """生成客户级主动建议。"""
    client_name = arg.strip()
    if not client_name:
        return {"reply_text": "请指定客户名称。\n示例：/客户建议 张三公司",
                "action": "client_suggestions_help", "success": True}

    try:
        from services.client_service import search_clients
        clients = search_clients(keyword=client_name, limit=1)
        if not clients:
            return {"reply_text": f"未找到客户「{client_name}」",
                    "action": "client_suggestions_not_found", "success": True}

        from services.proactive_suggestion_service import generate_client_suggestions
        s = generate_client_suggestions(clients[0]["id"])

        c = s["client"]
        lines = [f"📋 {c['name']} — 跟进建议", ""]

        if s.get("suggestions"):
            lines.append(f"💡 {s['suggestions']}")
            lines.append("")

        if s["risks"]:
            lines.append("🚨 风险")
            for r in s["risks"][:3]:
                lines.append(f"  - {r.get('description', r.get('relation_type', ''))}")
            lines.append("")

        if s["follow_ups"]:
            lines.append("📌 需跟进")
            for f in s["follow_ups"][:3]:
                lines.append(f"  - {f.get('description', f.get('relation_type', ''))}")
            lines.append("")

        if s["memories"]:
            lines.append("🧠 长期记忆")
            for m in s["memories"][:5]:
                imp = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                    m.get("importance", ""), "")
                lines.append(f"  {imp} [{m.get('memory_type', '')}] {m.get('title', '')}")
            lines.append("")

        if s["projects"]:
            active = [p for p in s["projects"] if p.get("status") == "active"]
            if active:
                lines.append(f"📁 活跃项目 ({len(active)})")
                for p in active[:5]:
                    lines.append(f"  - {p['name']}")

        add_workflow_log("feishu_client_suggestions", "client", clients[0]["id"], "success",
                         f"客户建议: {c['name']}")
        return {"reply_text": "\n".join(lines), "action": "client_suggestions", "success": True}

    except Exception as e:
        add_workflow_log("feishu_client_suggestions", "client", None, "error", str(e))
        return {"reply_text": _fe("生成建议失败"),
                "action": "client_suggestions_error", "success": False}


def _cmd_project_suggestions(arg: str) -> dict:
    """生成项目级主动建议。"""
    project_name = arg.strip()
    if not project_name:
        return {"reply_text": "请指定项目名称。\n示例：/项目建议 AI办公助理",
                "action": "project_suggestions_help", "success": True}

    try:
        from services.project_service import search_projects
        projects = search_projects(keyword=project_name, limit=1)
        if not projects:
            return {"reply_text": f"未找到项目「{project_name}」",
                    "action": "project_suggestions_not_found", "success": True}

        from services.proactive_suggestion_service import generate_project_suggestions
        s = generate_project_suggestions(projects[0]["id"])

        p = s["project"]
        lines = [f"📋 {p['name']} — 项目建议", ""]

        if s.get("next_steps"):
            lines.append(f"💡 {s['next_steps']}")
            lines.append("")

        if s["overdue_tasks"]:
            lines.append(f"⚠️ 逾期任务 ({len(s['overdue_tasks'])})")
            for t in s["overdue_tasks"][:5]:
                lines.append(f"  - {t['title']} — {t.get('due_date', '')}")
            lines.append("")

        if s["blocked_tasks"]:
            lines.append(f"🚫 阻塞任务 ({len(s['blocked_tasks'])})")
            for t in s["blocked_tasks"][:5]:
                lines.append(f"  - {t.get('title', '')}")
            lines.append("")

        if s["risks"]:
            lines.append("🚨 项目风险")
            for r in s["risks"][:3]:
                lines.append(f"  - {r.get('description', r.get('relation_type', ''))}")
            lines.append("")

        if s["memories"]:
            lines.append("🧠 长期记忆")
            for m in s["memories"][:5]:
                imp = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                    m.get("importance", ""), "")
                lines.append(f"  {imp} [{m.get('memory_type', '')}] {m.get('title', '')}")

        if s["uncompleted_tasks"]:
            lines.append("")
            lines.append(f"📝 未完成任务: {len(s['uncompleted_tasks'])} 个")

        add_workflow_log("feishu_project_suggestions", "project", projects[0]["id"], "success",
                         f"项目建议: {p['name']}")
        return {"reply_text": "\n".join(lines), "action": "project_suggestions", "success": True}

    except Exception as e:
        add_workflow_log("feishu_project_suggestions", "project", None, "error", str(e))
        return {"reply_text": _fe("生成建议失败"),
                "action": "project_suggestions_error", "success": False}


# ── 工作流状态命令 ──

def _cmd_project_status(project_name: str) -> dict:
    """/项目状态 项目名 — 展示当前阶段、进度%、剩余任务、风险。"""
    if not project_name.strip():
        return {"reply_text": "请指定项目名称。\n示例：/项目状态 AI办公助理",
                "action": "project_status_help", "success": True}

    try:
        from services.project_service import search_projects
        from services.workflow_engine import get_project_progress, get_current_stage
        from services.risk_detection_service import detect_project_risks

        projects = search_projects(keyword=project_name, limit=1)
        if not projects:
            return {"reply_text": f"未找到项目「{project_name}」",
                    "action": "project_status_not_found", "success": True}

        p = projects[0]
        pid = p["id"]
        progress = get_project_progress(pid)
        current = get_current_stage(pid)

        lines = [f"📊 {p['name']} — 项目状态", ""]

        # 阶段信息
        if progress["total_stages"] > 0:
            current_name = current["stage_name"] if current else "未设置"
            lines.append(f"📌 当前阶段：{current_name}")
            lines.append(f"📈 阶段进度：{progress['completed_stages']}/{progress['total_stages']} ({progress['stage_completion_pct']:.0f}%)")
            lines.append(f"✅ 任务完成率：{progress['done_tasks']}/{progress['total_tasks']} ({progress['task_completion_pct']:.0f}%)")

            # 各阶段状态
            stage_line = " → ".join([
                f"{'✅' if s['status'] == 'completed' else '⏭️' if s['status'] == 'skipped' else '🔵' if s['status'] == 'active' else '⚪'}{s['stage_name']}"
                for s in progress.get("stage_breakdown", [])
            ])
            lines.append(f"🔄 阶段流：{stage_line}")
        else:
            lines.append("📌 阶段：未初始化（发送 /项目建议 查看详情）")

        lines.append("")

        # 风险
        all_risks = detect_project_risks()
        p_risks = [r for r in all_risks if r.get("project_id") == pid]
        if p_risks:
            lines.append(f"🚨 风险 ({len(p_risks)})")
            for r in p_risks[:3]:
                level_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(r.get("risk_level", ""), "")
                lines.append(f"  {level_emoji} [{r.get('risk_type', '')}] {r.get('description', '')}")

        # 剩余任务
        if progress["remaining_tasks"] > 0:
            lines.append(f"📝 剩余任务：{progress['remaining_tasks']} 个")

        lines.append(f"📋 项目状态：{p.get('status', '—')}")

        add_workflow_log("feishu_project_status", "project", pid, "success",
                         f"项目状态: {p['name']}")
        return {"reply_text": "\n".join(lines), "action": "project_status", "success": True}

    except Exception as e:
        add_workflow_log("feishu_project_status", "project", None, "error", str(e))
        return {"reply_text": _fe("查询失败"),
                "action": "project_status_error", "success": False}


def _cmd_client_status(client_name: str) -> dict:
    """/客户状态 客户名 — 展示客户概况、活跃项目阶段。"""
    if not client_name.strip():
        return {"reply_text": "请指定客户名称。\n示例：/客户状态 张三公司",
                "action": "client_status_help", "success": True}

    try:
        from services.client_service import search_clients
        from services.workflow_engine import get_project_progress

        clients = search_clients(keyword=client_name, limit=1)
        if not clients:
            return {"reply_text": f"未找到客户「{client_name}」",
                    "action": "client_status_not_found", "success": True}

        c = clients[0]
        cid = c["id"]

        from database.db import fetch_all
        projects = fetch_all(
            "SELECT * FROM projects WHERE client_id = ? ORDER BY status, created_at DESC",
            (cid,),
        )

        lines = [f"👤 {c['name']} — 客户状态", ""]

        active_count = sum(1 for p in projects if p["status"] == "active")
        lines.append(f"📊 活跃项目: {active_count} | 总项目: {len(projects)}")

        if c.get("contact_info"):
            lines.append(f"📞 联系方式: {c['contact_info']}")

        lines.append("")

        if active_count > 0:
            lines.append("活跃项目阶段：")
            for p in projects:
                if p["status"] != "active":
                    continue
                try:
                    progr = get_project_progress(p["id"])
                    if progr["total_stages"] > 0:
                        current = progr.get("active_stage", {})
                        stage_name = current.get("stage_name", "—") if current else "—"
                        lines.append(f"  📁 {p['name']}: {stage_name} "
                                    f"({progr['completed_stages']}/{progr['total_stages']}, "
                                    f"任务 {progr['task_completion_pct']:.0f}%)")
                    else:
                        lines.append(f"  📁 {p['name']}: 未初始化阶段")
                except Exception:
                    lines.append(f"  📁 {p['name']}: 查询失败")
        else:
            lines.append("暂无活跃项目。")

        # 最近活动
        from services.relation_service import find_entity_follow_ups
        follow_ups = find_entity_follow_ups("client", cid)
        if follow_ups:
            lines.append(f"\n📌 跟进事项: {len(follow_ups)} 个")

        add_workflow_log("feishu_client_status", "client", cid, "success",
                         f"客户状态: {c['name']}")
        return {"reply_text": "\n".join(lines), "action": "client_status", "success": True}

    except Exception as e:
        add_workflow_log("feishu_client_status", "client", None, "error", str(e))
        return {"reply_text": _fe("查询失败"),
                "action": "client_status_error", "success": False}


def _cmd_project_risk(project_name: str) -> dict:
    """/项目风险 项目名 — 展示详细项目风险分析。"""
    if not project_name.strip():
        return {"reply_text": "请指定项目名称。\n示例：/项目风险 AI办公助理",
                "action": "project_risk_help", "success": True}

    try:
        from services.project_service import search_projects
        from services.risk_detection_service import detect_project_risks
        from services.relation_service import find_entity_risks

        projects = search_projects(keyword=project_name, limit=1)
        if not projects:
            return {"reply_text": f"未找到项目「{project_name}」",
                    "action": "project_risk_not_found", "success": True}

        p = projects[0]
        pid = p["id"]

        lines = [f"🚨 {p['name']} — 项目风险", ""]

        # 结构化风险
        all_risks = detect_project_risks()
        p_risks = [r for r in all_risks if r.get("project_id") == pid]

        if p_risks:
            high_risks = [r for r in p_risks if r.get("risk_level") == "high"]
            med_risks = [r for r in p_risks if r.get("risk_level") == "medium"]
            low_risks = [r for r in p_risks if r.get("risk_level") == "low"]

            if high_risks:
                lines.append(f"🔴 高风险 ({len(high_risks)})")
                for r in high_risks:
                    lines.append(f"  - [{r.get('risk_type', '')}] {r.get('description', '')}")
                    if r.get("suggestion"):
                        lines.append(f"    💡 {r['suggestion']}")
                lines.append("")

            if med_risks:
                lines.append(f"🟡 中风险 ({len(med_risks)})")
                for r in med_risks[:5]:
                    lines.append(f"  - [{r.get('risk_type', '')}] {r.get('description', '')}")
                lines.append("")

            if low_risks:
                lines.append(f"🟢 低风险 ({len(low_risks)})")
                for r in low_risks[:3]:
                    lines.append(f"  - [{r.get('risk_type', '')}] {r.get('description', '')}")
        else:
            lines.append("✅ 未检测到风险。")

        # 风险关系
        rel_risks = find_entity_risks("project", pid)
        if rel_risks:
            lines.append(f"\n🔗 风险关系 ({len(rel_risks)})")
            for r in rel_risks[:3]:
                lines.append(f"  - {r.get('description', r.get('relation_type', ''))}")

        add_workflow_log("feishu_project_risk", "project", pid, "success",
                         f"项目风险: {p['name']}")
        return {"reply_text": "\n".join(lines), "action": "project_risk", "success": True}

    except Exception as e:
        add_workflow_log("feishu_project_risk", "project", None, "error", str(e))
        return {"reply_text": _fe("风险查询失败"),
                "action": "project_risk_error", "success": False}


# ── 文档选段命令 ──

def _handle_document_section_command(sender_id: str, section_index: int = None,
                                      keyword: str = None, target_type: str = "task",
                                      create_all_tasks: bool = False) -> dict:
    """处理文档选段命令：把第N部分创建成项目/任务/时间轴。（从 session 读取）"""
    ctx = _get_doc_context_from_session(sender_id)
    if not ctx or not ctx.get("analysis"):
        return {"reply_text": "没有找到最近的文档分析结果。请先上传文件。",
                "action": "section_no_context", "success": True}

    analysis = ctx["analysis"]
    sections = analysis.get("sections", [])

    # 按索引或关键词查找段落
    matched_sections = []
    if section_index is not None:
        if 0 <= section_index < len(sections):
            matched_sections = [sections[section_index]]
    elif keyword:
        for s in sections:
            if keyword in s.get("title", ""):
                matched_sections.append(s)

    if not matched_sections:
        available = ", ".join([f"第{s['section_id']}部分「{s.get('title', '')}」" for s in sections])
        hint = f"可用段落：{available}" if available else "文档无分段"
        return {"reply_text": f"未找到匹配的段落。\n{hint}",
                "action": "section_not_found", "success": True}

    from services.action_executor_service import execute_action

    if create_all_tasks and matched_sections and target_type == "任务":
        # 把匹配段落的内容按行拆成多个 task
        lines_text = matched_sections[0].get("content", "")
        lines_list = [l.strip() for l in lines_text.split("\n") if l.strip() and len(l.strip()) > 5]
        results = []
        for line in lines_list[:10]:
            action = {
                "action_type": "create_task",
                "title": line[:100],
                "description": f"来自文档第{matched_sections[0]['section_id']}部分「{matched_sections[0].get('title', '')}」",
            }
            r = execute_action(action)
            results.append(r)
        success = sum(1 for r in results if r["success"])
        add_workflow_log("document_section_action", "file", ctx.get("file_id"), "success",
                         f"选段批量创建任务: {success}/{len(results)}")
        return {"reply_text": f"✅ 已将「{matched_sections[0].get('title', '')}」中的 {len(results)} 项创建为任务，{success} 条成功。",
                "action": "section_create_all_tasks", "success": True}

    # 单段落 → 创建实体
    section = matched_sections[0]
    type_map = {"项目": "create_project", "任务": "create_task", "时间轴": "create_timeline_event"}
    action_type = type_map.get(target_type, "create_task")

    action = {
        "action_type": action_type,
        "title": section.get("title", "")[:100],
        "description": f"来自文档第{section['section_id']}部分「{section.get('title', '')}」:\n{section.get('content', '')[:500]}",
    }

    result = execute_action(action)
    add_workflow_log("document_section_action", "file", ctx.get("file_id"),
                     "success" if result["success"] else "error",
                     f"选段执行: {action_type} | {result['message']}")

    if result["success"]:
        return {"reply_text": f"✅ {result['message']}\n\n来源：文档第{section['section_id']}部分「{section.get('title', '')}」",
                "action": "section_action", "success": True}
    else:
        return {"reply_text": _fe("执行失败"), "action": "section_action_error", "success": False}


# ── AI 问答 ──

def _handle_ai_qa(question: str, message_id: str = None, sender_id: str = None) -> dict:
    """调用 Hybrid RAG，生成 answer + 建议，暂存建议供后续执行。"""
    sid = sender_id or "default"

    try:
        from services.rag_service import answer_with_hybrid_rag
        from services.action_suggestion_service import suggest_actions

        result = answer_with_hybrid_rag(question)
        answer = result.get("answer", "系统中没有找到相关数据。")
        sources = result.get("sources", [])

        # 生成建议动作并暂存到 session
        actions = []
        suggestions_text = ""
        try:
            actions = suggest_actions(question, answer, sources)
            if actions:
                _save_actions_to_session(sid, actions)
                suggestions_text = _format_suggestions(actions)
        except Exception:
            pass

        # 保存 q/a 到 session
        try:
            from services.feishu_session_service import update_session
            update_session(sid, last_question=question, last_answer=answer[:500],
                          current_mode="qa")
        except Exception:
            pass

        # 自动提取长期记忆
        try:
            from services.memory_service import auto_extract_and_save
            memory_text = f"用户问: {question}\nAI回答: {answer[:500]}"
            auto_extract_and_save(memory_text, source_type="feishu_qa", source_id=0)
        except Exception:
            pass

        # 构建回复
        reply = _build_qa_reply(answer, sources, suggestions_text)

        # timeline_events
        try:
            from services.timeline_service import add_event
            add_event("ai_query", question, reply[:200], event_date=today_str())
        except Exception:
            pass

        # workflow_logs
        add_workflow_log("feishu_message", "feishu", None, "success",
                         f"Q: {question[:100]} | A: {reply[:100]}")

        return {"reply_text": reply, "action": "ai_qa", "success": True}

    except Exception as e:
        add_workflow_log("feishu_message", "feishu", None, "error",
                         f"AI问答异常: {question[:100]} | {str(e)}")
        return {"reply_text": "系统暂时处理失败，请稍后再试。",
                "action": "ai_qa_error", "success": False}


def _format_suggestions(actions: list) -> str:
    """格式化建议动作为文本。"""
    if not actions:
        return ""
    from services.feishu.reply_formatter import format_suggestions
    return format_suggestions({"items": actions})


# ── 会话意图检测 ──

def _detect_session_intent(text: str, sender_id: str) -> dict | None:
    """检测会话上下文意图。返回 None 表示不匹配，由后续逻辑处理。"""
    actions = _get_actions_from_session(sender_id)

    # ── 取消类 ──
    if text in ("不要", "取消", "算了"):
        if actions:
            _save_actions_to_session(sender_id, [])
            add_workflow_log("feishu_action_cancelled", "feishu", None, "success",
                             f"用户取消 {len(actions)} 条建议: {sender_id}")
            return {"reply_text": "已取消所有建议。可重新上传文件或发送问题。",
                    "action": "session_cancel", "success": True}
        return {"reply_text": "当前没有待处理的建议。", "action": "session_cancel_empty", "success": True}

    if text in ("清空", "重新开始"):
        try:
            from services.feishu_session_service import clear_session
            clear_session(sender_id)
        except Exception:
            pass
        PENDING_ACTIONS.pop(sender_id, None)
        FEISHU_DOCUMENT_CONTEXTS.pop(sender_id, None)
        return {"reply_text": "已清空会话上下文，可以重新开始。",
                "action": "session_cleared", "success": True}

    # ── 确认类：直接执行全部 pending actions ──
    if text in ("是", "确认", "可以", "创建", "行", "好", "ok", "yes"):
        if actions:
            return _cmd_execute_all(sender_id)
        return None  # 无 pending 时继续走后续命令路由

    # ── "执行"（无编号）→ 执行第一条 ──
    if text == "执行":
        if actions:
            return _cmd_execute_action(sender_id, 0)

    # ── 修改类 ──
    mod_match = re.match(r'^修改\s*(\d+)\s*(.*)', text)
    if mod_match:
        idx = int(mod_match.group(1)) - 1
        mod_text = mod_match.group(2).strip()
        return _cmd_modify_action(sender_id, idx, mod_text)

    # 无编号修改（修改最近一条）
    mod_no_idx = re.match(r'^(名字|标题|描述|优先级|截止日期|项目|客户)\s*(?:改成?|为|是|：|:)\s*(.+)$', text)
    if mod_no_idx and actions:
        return _cmd_modify_action(sender_id, len(actions) - 1, text)

    # ── 范围执行 ──
    range_match = re.match(r'^只创建前\s*(\d+)\s*个$', text)
    if range_match:
        count = int(range_match.group(1))
        return _cmd_execute_range(sender_id, count)

    # ── 跳过 ──
    skip_match = re.match(r'^(?:不要|跳过|删除)\s*(?:创建)?第?\s*(\d+)\s*个?$', text)
    if skip_match:
        idx = int(skip_match.group(1)) - 1
        return _cmd_skip_action(sender_id, idx)

    return None


# ── 修改动作 ──

_FIELD_ALIASES = {
    "名字": "title", "标题": "title", "名称": "title",
    "描述": "description", "说明": "description",
    "优先级": "priority",
    "截止日期": "due_date", "截止": "due_date", "日期": "due_date",
    "项目": "project_name", "项目名": "project_name",
    "客户": "client_name", "客户名": "client_name",
}

_PRIORITY_MAP = {"高": "high", "中": "medium", "低": "low",
                 "high": "high", "medium": "medium", "low": "low"}


def _cmd_modify_action(sender_id: str, idx: int, mod_text: str) -> dict:
    """修改 pending action 的指定字段。"""
    actions = _get_actions_from_session(sender_id)
    if not actions:
        return {"reply_text": "没有找到可修改的建议。请先上传文件或发起 AI 问答。",
                "action": "modify_no_pending", "success": True}

    if idx < 0 or idx >= len(actions):
        return {"reply_text": f"无效的动作编号。当前有 {len(actions)} 条建议。",
                "action": "modify_invalid_index", "success": True}

    action = actions[idx]

    # 解析修改内容："名字改成 AI办公助理三期" / "优先级改成 高" / "截止日期改成 明天"
    for cn_field, en_field in _FIELD_ALIASES.items():
        pattern = rf'{cn_field}\s*(?:改成?|为|是|：|:)\s*(.+)$'
        m = re.search(pattern, mod_text)
        if m:
            new_value = m.group(1).strip()
            if en_field == "priority":
                new_value = _PRIORITY_MAP.get(new_value, new_value)
            elif en_field == "due_date":
                # 简单日期词映射
                date_map = {"今天": "today", "明天": "+1", "后天": "+2"}
                new_value = date_map.get(new_value, new_value)
            action[en_field] = new_value
            _save_actions_to_session(sender_id, actions)

            add_workflow_log("feishu_action_modified", "ai_suggestion", None, "success",
                             f"修改建议 #{idx+1}: {en_field} → {new_value}")

            # 展示修改后的建议
            lines = [f"✅ 已修改建议 #{idx+1} 的 {cn_field} 为「{new_value}」", ""]
            lines.append(f"📋 {idx+1}. {action.get('title', '')}")
            if action.get("description"):
                lines.append(f"   描述：{action['description'][:100]}")
            if action.get("priority"):
                lines.append(f"   优先级：{action['priority']}")
            if action.get("due_date"):
                lines.append(f"   截止：{action['due_date']}")
            if action.get("project_name"):
                lines.append(f"   项目：{action['project_name']}")
            lines.append("")
            lines.append("回复「执行N」执行修改后的建议")
            return {"reply_text": "\n".join(lines), "action": "modify_action", "success": True}

    return {"reply_text": f"未能识别修改内容。\n支持修改：名字/描述/优先级/截止日期/项目/客户\n示例：「修改{idx+1} 名字改成 AI办公助理三期」",
            "action": "modify_parse_error", "success": True}


# ── 范围执行 ──

def _cmd_execute_range(sender_id: str, count: int) -> dict:
    """只执行前 N 条建议。"""
    actions = _get_actions_from_session(sender_id)
    if not actions:
        return {"reply_text": "没有找到可执行建议。", "action": "range_no_pending", "success": True}

    count = min(count, len(actions))
    subset = actions[:count]
    remaining = actions[count:]

    from services.action_executor_service import execute_action

    success_count = 0
    lines = [f"📋 执行前 {count} 条：", ""]
    for i, action in enumerate(subset):
        try:
            result = execute_action(action)
            if result["success"]:
                success_count += 1
                lines.append(f"✅ #{i+1} {result['message']}")
            else:
                lines.append(f"❌ #{i+1} {result['message']}")
        except Exception as e:
            lines.append(f"❌ #{i+1} 异常: {str(e)[:100]}")

    _save_actions_to_session(sender_id, remaining)

    add_workflow_log("document_action_execute_all", "ai_suggestion", None, "success",
                     f"范围执行前{count}条: {success_count} 成功")

    lines.append("")
    lines.append(f"完成：{success_count}/{count} 条成功")
    if remaining:
        lines.append(f"剩余 {len(remaining)} 条未执行，可继续操作")
    return {"reply_text": "\n".join(lines), "action": "execute_range", "success": True}


# ── 跳过动作 ──

def _cmd_skip_action(sender_id: str, idx: int) -> dict:
    """跳过/删除第 N 条建议。"""
    actions = _get_actions_from_session(sender_id)
    if not actions:
        return {"reply_text": "没有找到可操作的建议。", "action": "skip_no_pending", "success": True}

    if idx < 0 or idx >= len(actions):
        return {"reply_text": f"无效的动作编号。当前有 {len(actions)} 条建议。",
                "action": "skip_invalid_index", "success": True}

    removed = actions.pop(idx)
    _save_actions_to_session(sender_id, actions)

    add_workflow_log("feishu_action_cancelled", "ai_suggestion", None, "success",
                     f"跳过建议 #{idx+1}: {removed.get('title', '')}")

    if actions:
        hints = ", ".join([f"执行{i+1}" for i in range(min(len(actions), 5))])
        return {"reply_text": f"✅ 已跳过建议 #{idx+1}「{removed.get('title', '')}」\n\n"
                             f"剩余 {len(actions)} 条建议。回复「{hints}」继续执行。",
                "action": "skip_action", "success": True}
    else:
        return {"reply_text": f"✅ 已跳过建议 #{idx+1}「{removed.get('title', '')}」\n\n"
                             f"所有建议已清空。可重新上传文件或发送问题。",
                "action": "skip_action_all_cleared", "success": True}


# ── 上下文指代 ──

def _handle_context_reference(text: str, sender_id: str) -> dict | None:
    """处理「它/这个/刚才/上面的」等上下文指代。"""
    ctx_result = _get_doc_context_from_session(sender_id)

    # 把它创建成项目 / 把这个做成任务
    ref_create_match = re.match(r'^把(?:它|这个|那个|上面的|文件|文档)创建成(项目|任务|客户)$', text)
    if ref_create_match:
        target = ref_create_match.group(1)
        if ctx_result and ctx_result.get("analysis"):
            analysis = ctx_result["analysis"]
            doc_summary = analysis.get("document_summary", "文档分析")
            from services.action_executor_service import execute_action

            if target == "项目":
                action = {"action_type": "create_project", "title": doc_summary[:100] or "新项目",
                         "description": "基于上传的文档创建"}
            elif target == "任务":
                action = {"action_type": "create_task", "title": doc_summary[:100] or "新任务",
                         "description": "基于上传的文档创建"}
            else:
                action = {"action_type": "create_client", "title": doc_summary[:100] or "新客户",
                         "description": "基于上传的文档创建"}

            result = execute_action(action)
            return {"reply_text": f"✅ {result['message']}",
                    "action": "context_create", "success": result["success"]}
        else:
            add_workflow_log("feishu_context_missing", "feishu", None, "success",
                             f"上下文缺失: {text[:80]}")
            return {"reply_text": "我没有找到最近的文件或建议，请重新上传文件或发送 /帮助。",
                    "action": "context_missing", "success": True}

    # "把这个做成任务" variant
    ref_alt_match = re.match(r'^把(?:它|这个|那个|上面的|文件|文档)做[成为](?:一个)?(项目|任务|客户)$', text)
    if ref_alt_match:
        target = ref_alt_match.group(1)
        if ctx_result and ctx_result.get("analysis"):
            analysis = ctx_result["analysis"]
            doc_summary = analysis.get("document_summary", "文档分析")
            from services.action_executor_service import execute_action
            type_map = {"项目": "create_project", "任务": "create_task", "客户": "create_client"}
            action = {"action_type": type_map.get(target, "create_task"),
                     "title": doc_summary[:100], "description": "基于上传的文档创建"}
            result = execute_action(action)
            return {"reply_text": f"✅ {result['message']}",
                    "action": "context_create", "success": result["success"]}
        else:
            add_workflow_log("feishu_context_missing", "feishu", None, "success",
                             f"上下文缺失: {text[:80]}")
            return {"reply_text": "我没有找到最近的文件或建议，请重新上传文件或发送 /帮助。",
                    "action": "context_missing", "success": True}

    # "执行刚才那个" / "执行刚才的建议"
    if text in ("执行刚才那个", "执行刚才的建议", "执行上一个"):
        actions = _get_actions_from_session(sender_id)
        if actions:
            from services.action_executor_service import execute_action
            result = execute_action(actions[0])
            del actions[0]
            _save_actions_to_session(sender_id, actions)
            return {"reply_text": f"✅ {result['message']}\n\n已执行刚才的建议",
                    "action": "context_execute", "success": result["success"]}
        else:
            add_workflow_log("feishu_context_missing", "feishu", None, "success",
                             f"上下文缺失: {text[:80]}")
            return {"reply_text": "我没有找到最近的文件或建议，请重新上传文件或发送 /帮助。",
                    "action": "context_missing", "success": True}

    # "刚才那个文件" / "刚才上传的" / "上面的文件"
    if re.match(r'^(?:刚才|刚刚|上次|上面)(?:那个|上传的?|面的?)?(?:文件|文档|分析)$', text):
        if ctx_result:
            ctx_fid = ctx_result.get("file_id")
            if ctx_fid:
                from services.file_service import get_file
                f = get_file(ctx_fid)
                if f:
                    return {"reply_text": f"📄 刚才的文件：{f['filename']}\n"
                                         f"📝 摘要：{(f.get('summary') or '无')[:200]}\n"
                                         f"🏷️ 标签：{f.get('tags', '无')}\n\n"
                                         f"可回复「把它创建成项目」来基于此文件创建。",
                            "action": "context_file_info", "success": True}
        add_workflow_log("feishu_context_missing", "feishu", None, "success",
                         f"上下文缺失: {text[:80]}")
        return {"reply_text": "我没有找到最近的文件或建议，请重新上传文件或发送 /帮助。",
                "action": "context_missing", "success": True}

    # 独立上下文指代词：它/这个/那个/上面的（不在其他模式中时）
    if text in ("它", "这个", "那个", "刚才那个", "上面的", "这个文件", "那个文件", "上面的文件"):
        # 优先级：pending actions > 文件分析 > AI 回答
        actions = _get_actions_from_session(sender_id)
        if actions:
            hints = ", ".join([f"执行{i+1}" for i in range(min(len(actions), 5))])
            return {"reply_text": f"当前有 {len(actions)} 条待执行建议，回复「{hints}」或「执行全部」来执行。",
                    "action": "context_pending_hint", "success": True}

        if ctx_result:
            ctx_fid = ctx_result.get("file_id")
            if ctx_fid:
                from services.file_service import get_file
                f = get_file(ctx_fid)
                if f:
                    return {"reply_text": f"📄 最近的文件：{f['filename']}\n"
                                         f"📝 摘要：{(f.get('summary') or '无')[:200]}\n"
                                         f"🏷️ 标签：{f.get('tags', '无')}\n\n"
                                         f"可回复「把它创建成项目」来基于此文件创建。",
                            "action": "context_file_info", "success": True}

        # 尝试从 session 获取 last_answer
        try:
            from services.feishu_session_service import get_active_session
            s = get_active_session(sender_id)
            if s and s.get("last_answer"):
                return {"reply_text": f"最近一次问答：\n{s['last_answer'][:300]}\n\n"
                                     f"可继续提问或上传文件。",
                        "action": "context_last_answer", "success": True}
        except Exception:
            pass

        add_workflow_log("feishu_context_missing", "feishu", None, "success",
                         f"上下文缺失: {text[:80]}")
        return {"reply_text": "我没有找到最近的文件或建议，请重新上传文件或发送 /帮助。",
                "action": "context_missing", "success": True}

    # No match
    return None


# ── 回复格式化 ──

def _build_qa_reply(answer: str, sources: list, suggestions_text: str = "") -> str:
    """构建 QA 回复：委托给 reply_formatter。"""
    from services.feishu.reply_formatter import format_rag_answer
    return format_rag_answer({
        "answer": answer,
        "sources": sources,
        "item_count": len(sources),
    })


def _truncate(text: str, max_len: int = MAX_REPLY_LENGTH) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 30] + "\n\n（内容较长，已简化）"
