"""
飞书文件处理服务 — 下载、解析、AI 分析、去重、知识库同步、Embedding、Obsidian 同步。
"""
import os
import re
import hashlib
import json
from config.settings import UPLOAD_DIR, BASE_DIR

FEISHU_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "feishu")
SUPPORTED_TYPES = {".docx", ".pdf", ".txt", ".xlsx", ".md", ".csv"}
MAX_FILE_SIZE = 20 * 1024 * 1024


def _get_tenant_token() -> str:
    from services.feishu_service import get_tenant_access_token
    result = get_tenant_access_token()
    return result["token"] if result.get("success") else ""


def _is_supported(file_type: str) -> bool:
    return file_type.lower() in SUPPORTED_TYPES


def _compute_file_hash(file_bytes: bytes) -> str:
    return hashlib.md5(file_bytes).hexdigest()


def get_file_by_hash(file_hash: str) -> dict | None:
    """按 file_hash 查询已有文件记录。"""
    from database.db import fetch_one
    return fetch_one("SELECT * FROM files WHERE file_hash = ?", (file_hash,))


def _is_duplicate_file(file_hash: str) -> bool:
    return get_file_by_hash(file_hash) is not None


# ── 文件信息提取 ──

def get_file_info(message_event: dict) -> dict:
    message = message_event.get("message", {})
    content_str = message.get("content", "{}")
    try:
        content = json.loads(content_str)
    except Exception:
        content = {}

    file_key = content.get("file_key", "")
    file_name = content.get("file_name", "unknown")
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', file_name)
    ext = os.path.splitext(safe_name)[1].lower()

    return {
        "file_key": file_key,
        "file_name": safe_name,
        "file_type": ext,
        "size": content.get("size", 0),
        "message_id": message.get("message_id", ""),
    }


# ── 文件下载 ──

def download_feishu_file(message_id: str, file_key: str, filename: str) -> dict:
    token = _get_tenant_token()
    if not token:
        return {"success": False, "content": None,
                "error": "无法获取 tenant_access_token"}

    try:
        import requests
    except ImportError:
        return {"success": False, "content": None, "error": "requests 库未安装"}

    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}"
    params = {"type": "file"}
    headers = {"Authorization": f"Bearer {token}"}

    print(f"[飞书文件下载] message_id={message_id} file_key={file_key} file={filename}")

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        ct = resp.headers.get("Content-Type", "")
        print(f"[飞书文件下载] HTTP {resp.status_code}, Content-Type={ct}, body_len={len(resp.content)}")

        if resp.status_code != 200:
            err = resp.text[:500]
            return {"success": False, "content": None, "error": f"HTTP {resp.status_code}: {err[:300]}"}

        if "application/json" in ct:
            try:
                data = resp.json()
                code = data.get("code", -1)
                msg = data.get("msg", "unknown")
                return {"success": False, "content": None,
                        "error": f"飞书API错误: code={code} msg={msg}"}
            except Exception:
                pass

        print(f"[飞书文件下载] 成功: {len(resp.content)} bytes")
        return {"success": True, "content": resp.content, "error": ""}

    except Exception as e:
        return {"success": False, "content": None, "error": f"下载异常: {str(e)}"}


# ── 本地保存 ──

def save_feishu_file_to_uploads(file_bytes: bytes, filename: str) -> str:
    os.makedirs(FEISHU_UPLOAD_DIR, exist_ok=True)
    base, ext = os.path.splitext(filename)
    file_path = os.path.join(FEISHU_UPLOAD_DIR, filename)
    counter = 1
    while os.path.exists(file_path):
        file_path = os.path.join(FEISHU_UPLOAD_DIR, f"{base}_{counter}{ext}")
        counter += 1
    with open(file_path, "wb") as f:
        f.write(file_bytes)
    return file_path


# ── 客户/项目匹配 ──

def match_related_client_project(filename: str, content: str) -> dict:
    """从文件名和内容中自动匹配客户和项目，按匹配质量排序。

    Returns:
        {client_id, client_name, project_id, project_name}
    """
    result = {"client_id": None, "client_name": "", "project_id": None, "project_name": ""}

    try:
        from services.client_service import get_all_clients
        from services.project_service import get_all_projects
        all_text = filename + " " + (content or "")[:2000]

        # 客户匹配：按名称长度降序（长名称先匹配，避免短名称误匹配）
        clients = sorted(get_all_clients(), key=lambda c: len(c.get("name", "")), reverse=True)
        for c in clients:
            if c.get("name") and c["name"] in all_text:
                result["client_id"] = c["id"]
                result["client_name"] = c["name"]
                break

        # 项目匹配
        projects = sorted(get_all_projects(), key=lambda p: len(p.get("name", "")), reverse=True)
        for p in projects:
            if p.get("name") and p["name"] in all_text:
                result["project_id"] = p["id"]
                result["project_name"] = p["name"]
                break

    except Exception:
        pass

    return result


# ── 主处理流程 ──

def handle_feishu_file_message(message_event: dict, message_id: str = None,
                               open_id: str = None) -> dict:
    """处理飞书文件消息：下载 → 去重 → 解析 → AI分析 → 保存 → 知识库 → Embedding → Obsidian。

    Returns:
        {reply_text, action, success}
    """
    from services.workflow_log_service import add_workflow_log
    from services.workflow_service import WorkflowService

    # Start workflow run
    run = WorkflowService.start_run("file_processing", "feishu", None,
        {"filename": "unknown", "source": "feishu"})
    run_id = run["id"]

    # ── 调试 ──
    msg = message_event.get("message", {})
    content_str = msg.get("content", "{}")
    try:
        content_json = json.loads(content_str)
    except Exception:
        content_json = {}
    print("=" * 60)
    print(f"[飞书文件消息] message_id={message_id} type={msg.get('message_type')}")
    print(f"[飞书文件消息] content={json.dumps(content_json, ensure_ascii=False, indent=2)}")
    print(f"[飞书文件消息] file_key={content_json.get('file_key', 'N/A')} file_name={content_json.get('file_name', 'N/A')}")
    print("=" * 60)

    # ── Step 1: 获取文件信息 ──
    info = get_file_info(message_event)
    file_key = info["file_key"]
    file_name = info["file_name"]
    file_type = info["file_type"]
    msg_id = message_id or info.get("message_id", "")

    # Update run trigger_info with actual filename
    from database.db import execute
    import json as _json
    execute(
        "UPDATE workflow_runs SET trigger_info = ? WHERE id = ?",
        (_json.dumps({"filename": file_name, "file_type": file_type, "source": "feishu"},
                     ensure_ascii=False), run_id),
    )

    if not file_key:
        add_workflow_log("feishu_file_error", "feishu", None, "error", "缺少 file_key", run_id=run_id)
        WorkflowService.fail_step(run_id, "extract_file_info", "缺少 file_key")
        return {"reply_text": "文件信息不完整，无法处理。", "action": "file_error", "success": False}

    if not _is_supported(file_type):
        add_workflow_log("feishu_file_error", "feishu", None, "error", f"不支持格式: {file_type}", run_id=run_id)
        WorkflowService.fail_step(run_id, "check_supported", f"不支持格式: {file_type}")
        return {"reply_text": f"暂不支持 {file_type} 格式。\n支持: {', '.join(sorted(SUPPORTED_TYPES))}",
                "action": "file_unsupported", "success": True}
    WorkflowService.complete_step(run_id, "extract_file_info", f"file_key={file_key[:20]}...")
    WorkflowService.complete_step(run_id, "check_supported", f"格式: {file_type}")

    # ── Step 2: 下载 ──
    dl_result = download_feishu_file(msg_id, file_key, file_name)
    if not dl_result["success"]:
        add_workflow_log("file_download_failed", "feishu", None, "error",
                         f"{file_name}: {dl_result['error']}", run_id=run_id)
        WorkflowService.fail_step(run_id, "download_file", dl_result["error"])
        return {"reply_text": f"文件下载失败\n\n{dl_result['error']}",
                "action": "file_download_error", "success": False}
    file_bytes = dl_result["content"]
    add_workflow_log("file_download_success", "feishu", None, "success",
                     f"{file_name} ({len(file_bytes)} bytes)", run_id=run_id)
    WorkflowService.complete_step(run_id, "download_file", f"{len(file_bytes)} bytes")

    # ── Step 3: 去重 ──
    file_hash = _compute_file_hash(file_bytes)
    existing = get_file_by_hash(file_hash)
    if existing:
        add_workflow_log("file_dedup_skipped", "file", existing["id"], "success",
                         f"重复文件: {file_name} hash={file_hash[:16]}", run_id=run_id)
        WorkflowService.complete_step(run_id, "check_duplicate", "重复文件，已跳过")
        WorkflowService.complete_run(run_id, {"action": "file_duplicate", "existing_file_id": existing["id"]})

        from services.file_service import generate_task_suggestions_from_file
        dup_suggestions = generate_task_suggestions_from_file(existing["id"])
        dup_pending = []
        for s in dup_suggestions[:5]:
            dup_pending.append({
                "action_type": "create_task",
                "title": s.get("title", "") if isinstance(s, dict) else str(s),
                "description": s.get("description", "") if isinstance(s, dict) else "",
                "related_project_id": existing.get("project_id"),
                "related_client_id": existing.get("client_id"),
            })
        if dup_pending and open_id:
            from services.feishu_message_service import PENDING_ACTIONS
            PENDING_ACTIONS[open_id] = dup_pending

        reply = (f"该文件已存在，已为你找到原记录。\n\n"
                 f"📄 文件：{existing['filename']}\n"
                 f"📝 摘要：{(existing.get('summary') or '无')[:150]}\n"
                 f"🏷️ 标签：{existing.get('tags', '无')}")
        if dup_pending:
            reply += "\n\n💡 建议任务："
            for i, a in enumerate(dup_pending[:3]):
                reply += f"\n  {i+1}. {a['title']}"
            reply += "\n\n回复「执行N」即可创建对应任务"
        return {"reply_text": reply, "action": "file_duplicate", "success": True}
    WorkflowService.complete_step(run_id, "check_duplicate", "新文件，继续处理")

    # ── Step 4: 保存到本地 ──
    base, ext = os.path.splitext(file_name)
    unique_name = f"{base}_{file_hash[:8]}{ext}"
    file_path = save_feishu_file_to_uploads(file_bytes, unique_name)
    WorkflowService.complete_step(run_id, "save_local", file_path)

    # ── Step 5: 解析文本 ──
    try:
        from services.file_parser import parse_file
        text_content = parse_file(file_path)
    except Exception as e:
        add_workflow_log("file_parse_failed", "feishu", None, "error",
                         f"{file_name}: {str(e)}", run_id=run_id)
        WorkflowService.fail_step(run_id, "parse_text", str(e))
        return {"reply_text": f"文件「{file_name}」解析失败：{str(e)[:200]}",
                "action": "file_parse_error", "success": False}
    add_workflow_log("file_parse_success", "feishu", None, "success",
                     f"{file_name} ({len(text_content)} chars)", run_id=run_id)
    WorkflowService.complete_step(run_id, "parse_text", f"{len(text_content)} chars")

    # ── Step 6: AI 分析 ──
    try:
        from services.ai_service import summarize_file
        analysis = summarize_file(text_content[:6000], file_name)
    except Exception as e:
        add_workflow_log("file_summary_failed", "feishu", None, "error",
                         f"{file_name}: {str(e)}", run_id=run_id)
        WorkflowService.fail_step(run_id, "ai_summarize", str(e))
        return {"reply_text": f"AI 分析失败：{str(e)[:200]}",
                "action": "file_analysis_error", "success": False}

    summary = analysis.get("summary", "")[:500]
    key_points = analysis.get("key_points", [])[:5]
    tags = analysis.get("tags", [])[:8]
    tags_str = ", ".join(tags) if tags else ""
    suggestions = analysis.get("suggestions", [])[:5]
    add_workflow_log("file_summary_success", "feishu", None, "success",
                     f"{file_name} summary={summary[:80]} tags={tags_str[:60]}", run_id=run_id)
    WorkflowService.complete_step(run_id, "ai_summarize", f"summary={summary[:80]}")
    WorkflowService.complete_step(run_id, "ai_classify", f"tags={tags_str[:60]}")

    # ── Step 7: 匹配客户/项目 ──
    matched = match_related_client_project(file_name, text_content)
    WorkflowService.complete_step(run_id, "match_relations",
        f"client={matched.get('client_name', 'None')} project={matched.get('project_name', 'None')}")

    # ── Step 8: 保存 files 记录 ──
    from services.file_service import save_file_record
    file_id = save_file_record(
        filename=file_name, file_path=file_path, file_type=file_type,
        summary=summary, key_points=key_points, suggestions=suggestions,
        tags=tags_str,
        project_id=matched["project_id"], client_id=matched["client_id"],
        file_hash=file_hash,
    )
    WorkflowService.complete_step(run_id, "save_file_record", f"file_id={file_id}")
    # Update run source_id
    execute("UPDATE workflow_runs SET source_id = ? WHERE id = ?", (file_id, run_id))
    WorkflowService.complete_step(run_id, "generate_preview", f"file_id={file_id}")

    # ── Step 9: timeline_event + relations ──
    try:
        from services.timeline_service import add_event
        add_event("file_uploaded", f"飞书上传文件: {file_name}",
                  f"文件通过飞书上传并自动分析 | 摘要: {summary[:100]}",
                  "file", file_id,
                  project_id=matched["project_id"],
                  client_id=matched["client_id"],
                  tags=tags_str)
    except Exception:
        pass

    # ── Step 10: knowledge_items ──
    try:
        from services.knowledge_service import sync_file_to_knowledge
        ki_id = sync_file_to_knowledge(file_id)
        add_workflow_log("file_sync_knowledge_success", "file", file_id, "success",
                         f"KI id={ki_id}", run_id=run_id)
        WorkflowService.complete_step(run_id, "sync_knowledge", f"KI id={ki_id}")
    except Exception as e:
        add_workflow_log("file_sync_knowledge_failed", "file", file_id, "error", str(e), run_id=run_id)
        WorkflowService.complete_step(run_id, "sync_knowledge", f"Error: {str(e)[:80]}")

    # ── Step 11: Embedding ──
    try:
        from services.embedding_service import upsert_embedding, has_embeddings
        from services.knowledge_service import search_knowledge
        if has_embeddings():
            items = search_knowledge(source_type="file", limit=1)
            for item in items:
                if item.get("source_id") == file_id:
                    upsert_embedding(item["id"])
                    add_workflow_log("file_embedding_success", "file", file_id, "success", "", run_id=run_id)
                    break
        WorkflowService.complete_step(run_id, "sync_embedding", "done")
    except Exception as e:
        add_workflow_log("file_embedding_failed", "file", file_id, "error", str(e), run_id=run_id)
        WorkflowService.complete_step(run_id, "sync_embedding", f"Error: {str(e)[:80]}")

    # ── Step 12: Obsidian 同步 ──
    try:
        from config.settings import OBSIDIAN_VAULT_PATH
        from services.obsidian_service import is_configured, sync_file_to_obsidian
        if OBSIDIAN_VAULT_PATH and is_configured():
            try:
                sync_file_to_obsidian(file_id)
                add_workflow_log("obsidian_sync_success", "file", file_id, "success",
                                 f"飞书文件 Obsidian 同步: {file_name}", run_id=run_id)
                WorkflowService.complete_step(run_id, "write_obsidian", f"synced: {file_name}")
            except Exception:
                add_workflow_log("obsidian_sync_failed", "file", file_id, "error",
                                 f"飞书文件 Obsidian 同步失败: {file_name}", run_id=run_id)
                WorkflowService.complete_step(run_id, "write_obsidian", "sync failed")
        else:
            add_workflow_log("obsidian_sync_skipped", "file", file_id, "success",
                             "Obsidian 未配置", run_id=run_id)
            WorkflowService.complete_step(run_id, "write_obsidian", "skipped: Obsidian not configured")
    except Exception:
        add_workflow_log("obsidian_sync_skipped", "file", file_id, "success",
                         "Obsidian 未配置", run_id=run_id)
        WorkflowService.complete_step(run_id, "write_obsidian", "skipped")

    # ── Step 13: 任务建议 ──
    pending_actions = []
    if suggestions:
        for s in suggestions:
            pending_actions.append({
                "action_type": "create_task",
                "title": s if isinstance(s, str) else s.get("title", str(s)),
                "description": s if isinstance(s, str) else s.get("description",
                               f"由飞书文件「{file_name}」分析生成"),
                "related_project_id": matched["project_id"],
                "related_client_id": matched["client_id"],
            })

    if pending_actions and open_id:
        from services.feishu_message_service import PENDING_ACTIONS, FEISHU_DOCUMENT_CONTEXTS
        PENDING_ACTIONS[open_id] = pending_actions

    # ── Step 14: 文档动作分析 ──
    doc_actions = []
    doc_analysis = None
    try:
        from services.document_action_service import analyze_document_actions
        from utils.date_utils import now_str
        doc_analysis = analyze_document_actions(file_id)
        doc_actions = doc_analysis.get("suggested_actions", [])
        if doc_actions and open_id:
            doc_pending = []
            for a in doc_actions[:5]:
                doc_pending.append({
                    "action_type": a.get("action_type", "create_task"),
                    "title": a.get("title", ""),
                    "description": a.get("description", ""),
                    "related_project_id": matched["project_id"],
                    "related_client_id": matched["client_id"],
                    "project_name": a.get("project_name"),
                    "client_name": a.get("client_name"),
                    "priority": a.get("priority", "medium"),
                    "confidence": a.get("confidence", 0.7),
                    "due_date": a.get("due_date"),
                })
            # 内存 fallback
            PENDING_ACTIONS[open_id] = doc_pending
            FEISHU_DOCUMENT_CONTEXTS[open_id] = {
                "file_id": file_id,
                "analysis": doc_analysis,
                "created_at": now_str(),
            }
            # 持久化到 DB session
            try:
                from services.feishu_session_service import (
                    save_pending_actions, save_last_file_analysis)
                save_pending_actions(open_id, doc_pending)
                save_last_file_analysis(open_id, file_id, doc_analysis)
            except Exception:
                pass
        add_workflow_log("document_action_analysis", "file", file_id, "success",
                         f"文档动作建议: {len(doc_actions)} 条", run_id=run_id)
    except Exception as e:
        add_workflow_log("document_action_analysis", "file", file_id, "error",
                         f"文档动作分析失败: {str(e)[:200]}", run_id=run_id)

    # ── Step 15: 提取长期记忆 ──
    try:
        from services.memory_service import auto_extract_and_save
        memory_text = f"文件: {file_name}\n摘要: {summary}\n关键点: {', '.join(key_points) if key_points else ''}\n标签: {tags_str}"
        mem_count = auto_extract_and_save(
            memory_text, source_type="file", source_id=file_id,
            project_id=matched["project_id"], client_id=matched["client_id"],
        )
        if mem_count > 0:
            add_workflow_log("file_memory_extraction", "file", file_id, "success",
                           f"从文件提取 {mem_count} 条长期记忆", run_id=run_id)
        WorkflowService.complete_step(run_id, "extract_memory", f"{mem_count} memories extracted")
    except Exception as e:
        add_workflow_log("file_memory_extraction", "file", file_id, "error",
                       f"记忆提取失败: {str(e)[:200]}", run_id=run_id)
        WorkflowService.complete_step(run_id, "extract_memory", f"Error: {str(e)[:80]}")

    # ── Step 16: 构建回复 ──
    reply = _build_file_reply(file_name, file_type, summary, key_points, tags,
                              matched, pending_actions, doc_actions)
    WorkflowService.complete_step(run_id, "build_reply", f"reply length: {len(reply)}")

    # ── 完成日志 ──
    add_workflow_log("feishu_file_processed", "file", file_id, "success",
                     f"飞书文件处理完成: {file_name} | summary={summary[:80]} "
                     f"| project={matched['project_name']} | client={matched['client_name']} "
                     f"| tags={tags_str[:60]}", run_id=run_id)
    WorkflowService.complete_run(run_id, {
        "file_id": file_id, "filename": file_name,
        "summary": summary[:100], "tags": tags_str,
        "project": matched["project_name"], "client": matched["client_name"],
    })

    return {"reply_text": reply, "action": "file_processed", "success": True}


# ── 回复格式化 ──

def _build_file_reply(file_name: str, file_type: str, summary: str,
                      key_points: list, tags: list, matched: dict,
                      pending_actions: list, doc_actions: list = None) -> str:
    lines = ["✅ 文件已处理完成", ""]
    lines.append(f"📄 文件：{file_name}（{file_type}）")

    if summary:
        lines.append(f"📝 摘要：{summary[:200]}{'…' if len(summary) > 200 else ''}")

    if key_points:
        lines.append("🔑 关键点：")
        for kp in key_points[:3]:
            lines.append(f"  - {kp}")

    if tags:
        lines.append(f"🏷️ 标签：{', '.join(tags[:5])}")

    if matched["client_name"]:
        lines.append(f"👤 关联客户：{matched['client_name']}")
    if matched["project_name"]:
        lines.append(f"📁 关联项目：{matched['project_name']}")

    if not matched["client_name"] and not matched["project_name"]:
        lines.append("⚠️ 未识别到关联客户/项目，可后续手动关联")

    # 文档动作建议（优先展示）
    if doc_actions:
        lines.append("")
        lines.append("📋 **文档动作建议：**")
        type_emoji = {"create_project": "🆕", "create_task": "📝", "create_client": "👤",
                      "risk_alert": "⚠️", "create_timeline_event": "📅",
                      "link_relation": "🔗"}
        for i, a in enumerate(doc_actions[:5]):
            emoji = type_emoji.get(a.get("action_type", ""), "📌")
            type_cn = {"create_project": "创建项目", "create_task": "创建任务",
                       "create_client": "创建客户", "risk_alert": "风险提醒",
                       "create_timeline_event": "写入时间轴",
                       "link_relation": "建立关联"}.get(a.get("action_type", ""), a.get("action_type", ""))
            conf = a.get("confidence", 0)
            conf_str = f" [{int(conf*100)}%]" if conf else ""
            lines.append(f"  {i+1}. {emoji} {type_cn}：{a.get('title', '')}{conf_str}")
        lines.append("")
        lines.append("回复「执行N」执行对应建议，或「执行全部」批量执行")
        lines.append("也可「把第N部分创建成项目/任务」按段落执行")

    elif pending_actions:
        lines.append("")
        lines.append("💡 建议任务：")
        for i, a in enumerate(pending_actions[:5]):
            lines.append(f"  {i+1}. {a['title']}")
        lines.append("")
        lines.append("回复「执行N」即可创建对应任务")

    return "\n".join(lines)
