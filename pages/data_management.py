import streamlit as st
import pandas as pd
import csv
import io
import os
import shutil
from database.db import fetch_all
from config.settings import DATABASE_PATH, UPLOAD_DIR, OBSIDIAN_VAULT_PATH
from utils.display_utils import WORKFLOW_STATUS_LABELS, OBSIDIAN_SYNC_STATUS

TABLE_NAMES_CN = {
    "clients": "客户",
    "projects": "项目",
    "tasks": "任务",
    "files": "文件",
    "timeline_events": "时间轴事件",
    "knowledge_items": "知识条目",
    "knowledge_embeddings": "知识向量",
    "workflow_logs": "工作流日志",
}


def render():
    st.title("数据管理")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "数据库统计", "知识库维护", "知识块入库", "数据导出", "批量清理", "工作流日志", "Obsidian 同步", "通知设置",
    ])

    with tab1:
        _render_stats()
    with tab2:
        _render_kb_maintenance()
    with tab3:
        _render_chunk_ingestion()
    with tab4:
        _render_export()
    with tab5:
        _render_cleanup()
    with tab6:
        _render_workflow_logs()
    with tab7:
        _render_obsidian_sync()
    with tab8:
        _render_notification_settings()


def _render_stats():
    st.subheader("数据库统计")

    from services.knowledge_service import get_database_stats
    stats = get_database_stats()

    cols = st.columns(4)
    table_order = [
        "clients", "projects", "tasks", "files",
        "timeline_events", "knowledge_items", "knowledge_embeddings", "workflow_logs",
    ]

    for i, table in enumerate(table_order):
        with cols[i % 4]:
            label = TABLE_NAMES_CN.get(table, table)
            count = stats.get(table, 0)
            st.metric(label, count)

    st.divider()
    # 知识条目按类型分布
    from services.knowledge_service import get_knowledge_stats
    kb_stats = get_knowledge_stats()
    by_type = kb_stats.get("by_type", {})
    if by_type:
        st.caption("知识条目按来源类型分布：")
        type_cols = st.columns(len(by_type) if len(by_type) <= 6 else 6)
        for j, (stype, cnt) in enumerate(sorted(by_type.items())):
            with type_cols[j % len(type_cols)]:
                st.metric(stype, cnt)


def _render_kb_maintenance():
    st.subheader("知识库维护")

    from services.knowledge_service import rebuild_knowledge_items, get_knowledge_stats

    kb_stats = get_knowledge_stats()
    st.write(f"知识条目总数: **{kb_stats['total']}**")
    by_type = kb_stats.get("by_type", {})
    if by_type:
        st.caption("按来源类型：")
        for stype, cnt in sorted(by_type.items()):
            st.write(f"- {stype}: {cnt}")

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("重建知识库", key="dm_rebuild_kb", use_container_width=True):
            with st.spinner("正在重建知识库..."):
                total = rebuild_knowledge_items()
            st.success(f"知识库已重建，共 {total} 条记录")
            st.rerun()

    with col2:
        if st.button("重建 Embedding", key="dm_rebuild_emb", use_container_width=True):
            from services.embedding_service import rebuild_embeddings

            progress_bar = st.progress(0, text="准备中...")
            status_text = st.empty()

            def progress_callback(current, total):
                progress = current / total if total > 0 else 0
                progress_bar.progress(progress, text=f"处理中: {current}/{total}")

            with st.spinner("正在生成 Embedding（可能需要几分钟）..."):
                count = rebuild_embeddings(progress_callback=progress_callback)

            progress_bar.progress(1.0, text="完成!")
            st.success(f"Embedding 已生成，成功 {count} 条")
            st.rerun()


def _render_chunk_ingestion():
    """知识块入库 — 从各数据源生成 knowledge_chunks 并向量化。"""
    st.subheader("知识块入库")

    from services.knowledge_ingestion import (
        ingest_all, ingest_obsidian_notes, ingest_projects_and_timeline,
        ingest_daily_summaries, clear_all_chunks, get_chunk_stats,
    )
    from services.embedding_service import count_chunk_embeddings

    # 当前状态
    stats = get_chunk_stats()
    emb_count = count_chunk_embeddings()
    col1, col2 = st.columns(2)
    with col1:
        st.metric("知识块总数", stats["total"])
    with col2:
        st.metric("已向量化", emb_count)

    if stats["by_type"]:
        st.caption("按类型分布: " + ", ".join(
            f"{k}: {v}" for k, v in stats["by_type"].items()
        ))

    st.divider()

    # 入库按钮
    st.write("**按来源入库**")

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        if st.button("从 Obsidian 入库", use_container_width=True, key="btn_ingest_obsidian"):
            with st.spinner("从 Obsidian Vault 读取并入库..."):
                n = ingest_obsidian_notes()
                if n > 0:
                    st.success(f"Obsidian: {n} 个知识块已入库")
                else:
                    st.info("未找到 Obsidian 笔记（请检查 OBSIDIAN_VAULT_PATH 配置）")
                st.rerun()

    with col_b:
        if st.button("从项目/时间轴入库", use_container_width=True, key="btn_ingest_projects"):
            with st.spinner("读取项目和时间轴记录..."):
                n = ingest_projects_and_timeline()
                st.success(f"项目/时间轴: {n} 个知识块已入库")
                st.rerun()

    with col_c:
        if st.button("从每日总结入库", use_container_width=True, key="btn_ingest_summaries"):
            with st.spinner("读取每日总结和随手记..."):
                n = ingest_daily_summaries()
                st.success(f"总结/笔记: {n} 个知识块已入库")
                st.rerun()

    st.divider()

    # 全量入库
    col_all, col_clear = st.columns(2)
    with col_all:
        if st.button("全量入库", type="primary", use_container_width=True, key="btn_ingest_all"):
            with st.spinner("全量入库中，请耐心等待..."):
                results = ingest_all()
                st.success(f"入库完成: {results}")
                st.rerun()

    with col_clear:
        clear_confirm = st.checkbox("确认清空", key="confirm_clear_chunks")
        if st.button("清空重建知识块", use_container_width=True,
                     key="btn_clear_chunks", disabled=not clear_confirm):
            deleted = clear_all_chunks()
            st.success(f"已清空 {deleted} 个知识块")
            st.rerun()

    st.divider()
    st.caption("入库后的知识块可在「RAG问答」页面进行语义检索和智能问答。")


def _render_export():
    st.subheader("数据导出")

    # 表导出为 CSV
    st.write("**导出数据表为 CSV**")
    export_tables = ["clients", "projects", "tasks", "files", "timeline_events", "knowledge_items"]

    for table in export_tables:
        label = TABLE_NAMES_CN.get(table, table)
        rows = fetch_all(f"SELECT * FROM {table}")
        if not rows:
            st.caption(f"{label}: 无数据")
            continue

        csv_buffer = io.StringIO()
        writer = csv.DictWriter(csv_buffer, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

        st.download_button(
            label=f"导出 {label} ({len(rows)} 条)",
            data=csv_buffer.getvalue(),
            file_name=f"{table}.csv",
            mime="text/csv",
            key=f"export_{table}",
        )

    st.divider()
    st.write("**数据库完整备份**")

    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("生成数据库备份", key="dm_backup"):
            from services.backup_service import backup_database
            try:
                path = backup_database()
                st.success(f"备份已生成: {path}")

                # 提供下载
                with open(path, "rb") as f:
                    backup_data = f.read()
                st.download_button(
                    label="下载数据库备份",
                    data=backup_data,
                    file_name=os.path.basename(path),
                    mime="application/octet-stream",
                    key="download_backup",
                )
            except Exception as e:
                st.error(f"备份失败: {str(e)}")


def _render_cleanup():
    st.subheader("批量清理")

    # 1. 清理 workflow_logs
    st.write("**清理工作流日志**")
    from services.workflow_log_service import clear_workflow_logs

    wl_row = fetch_all("SELECT COUNT(*) as cnt FROM workflow_logs")
    wl_count = wl_row[0]["cnt"] if wl_row else 0
    st.caption(f"当前工作流日志: {wl_count} 条")

    wl_confirm = st.checkbox("我确认要删除所有工作流日志", key="confirm_clear_wl")
    if st.button("清理工作流日志", key="btn_clear_wl", disabled=not wl_confirm):
        deleted = clear_workflow_logs()
        st.success(f"已清理 {deleted} 条工作流日志")
        st.rerun()

    st.divider()

    # 2. 清理 orphan relations
    st.write("**清理孤儿关系**")
    from services.relation_service import count_orphan_relations, cleanup_orphan_relations

    or_count = count_orphan_relations()
    st.caption(f"当前孤儿关系: {or_count} 条（关系的源或目标实体已不存在）")

    or_confirm = st.checkbox("我确认要删除所有孤儿关系", key="confirm_clean_orphan_rel")
    if st.button("清理孤儿关系", key="btn_clean_orphan_rel", disabled=not or_confirm):
        deleted = cleanup_orphan_relations()
        st.success(f"已清理 {deleted} 条孤儿关系")
        st.rerun()

    st.divider()

    # 3. 清理 orphan knowledge_items
    st.write("**清理孤儿知识条目**")
    from services.knowledge_service import count_orphan_knowledge_items, cleanup_orphan_knowledge_items

    ok_count = count_orphan_knowledge_items()
    st.caption(f"当前孤儿知识条目: {ok_count} 条（来源实体已不存在）")

    ok_confirm = st.checkbox("我确认要删除所有孤儿知识条目（含关联的 Embedding）", key="confirm_clean_orphan_ki")
    if st.button("清理孤儿知识条目", key="btn_clean_orphan_ki", disabled=not ok_confirm):
        deleted = cleanup_orphan_knowledge_items()
        st.success(f"已清理 {deleted} 条孤儿知识条目")
        st.rerun()

    st.divider()

    # 4. 清理 orphan embeddings
    st.write("**清理孤儿 Embedding**")
    from services.embedding_service import count_orphan_embeddings, cleanup_orphan_embeddings

    oe_count = count_orphan_embeddings()
    st.caption(f"当前孤儿 Embedding: {oe_count} 条（knowledge_item_id 已不存在）")

    oe_confirm = st.checkbox("我确认要删除所有孤儿 Embedding", key="confirm_clean_orphan_emb")
    if st.button("清理孤儿 Embedding", key="btn_clean_orphan_emb", disabled=not oe_confirm):
        deleted = cleanup_orphan_embeddings()
        st.success(f"已清理 {deleted} 条孤儿 Embedding")
        st.rerun()


def _render_workflow_logs():
    st.subheader("工作流日志")

    from services.workflow_log_service import (
        get_all_workflow_logs,
        get_distinct_workflow_types,
        get_distinct_source_types,
    )

    # 筛选器
    col1, col2, col3 = st.columns(3)
    with col1:
        status_options = ["全部", "success", "error", "pending"]
        status_filter = st.selectbox(
            "状态",
            status_options,
            format_func=lambda x: WORKFLOW_STATUS_LABELS.get(x, x) if x != "全部" else "全部",
            key="wl_status_filter",
        )
    with col2:
        wf_types = ["全部"] + get_distinct_workflow_types()
        wf_type_filter = st.selectbox("工作流类型", wf_types, key="wl_type_filter")
    with col3:
        src_types = ["全部"] + get_distinct_source_types()
        src_type_filter = st.selectbox("来源类型", src_types, key="wl_src_filter")

    # 查询
    logs = get_all_workflow_logs(
        workflow_type=None if wf_type_filter == "全部" else wf_type_filter,
        source_type=None if src_type_filter == "全部" else src_type_filter,
        status=None if status_filter == "全部" else status_filter,
        limit=200,
    )

    if not logs:
        st.info("暂无工作流日志")
        return

    st.write(f"共 {len(logs)} 条记录")

    # 格式化显示
    rows = []
    for log in logs:
        status_label = WORKFLOW_STATUS_LABELS.get(log.get("status", ""), log.get("status", ""))
        rows.append({
            "ID": log["id"],
            "工作流类型": log.get("workflow_type", ""),
            "来源类型": log.get("source_type", "") or "-",
            "来源ID": log.get("source_id", "") or "-",
            "状态": status_label,
            "消息": log.get("message", "")[:80],
            "时间": log.get("created_at", "")[:19],
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # 展开查看详情
    with st.expander("查看详细日志"):
        log_id = st.number_input("日志 ID", min_value=1, step=1, key="wl_detail_id")
        if st.button("查看详情", key="btn_wl_detail"):
            from services.workflow_log_service import get_workflow_log
            detail = get_workflow_log(int(log_id))
            if detail:
                st.json(detail)
            else:
                st.warning("未找到该日志")


def _render_obsidian_sync():
    st.subheader("Obsidian 同步")

    # 显示 Vault 路径和状态
    from services.obsidian_service import is_configured, get_obsidian_base_path

    vault_path = get_obsidian_base_path()
    if not OBSIDIAN_VAULT_PATH:
        st.warning("Obsidian Vault 未配置。请在 .env 中设置 OBSIDIAN_VAULT_PATH")
    elif not vault_path:
        st.error(f"Obsidian Vault 路径不存在: {OBSIDIAN_VAULT_PATH}")
    else:
        st.success(f"Vault 路径: {vault_path}")

    if not vault_path:
        st.info("配置 OBSIDIAN_VAULT_PATH 后即可使用同步功能。\n\n示例: `OBSIDIAN_VAULT_PATH=/Users/xxx/Documents/ObsidianVault`")
        return

    st.divider()

    # 同步统计
    from services.obsidian_log_service import count_sync_logs, get_all_sync_logs

    sync_count = count_sync_logs()
    st.metric("已同步记录", sync_count)

    # 最近同步记录
    if sync_count > 0:
        recent_logs = get_all_sync_logs(limit=5)
        if recent_logs:
            st.caption("最近同步记录：")
            for log in recent_logs:
                status_label = OBSIDIAN_SYNC_STATUS.get(log.get("sync_status", ""), log.get("sync_status", ""))
                st.write(f"- [{status_label}] {log['source_type']}#{log['source_id']} → {log['obsidian_path']} ({log.get('last_synced_at', '')[:19]})")

    st.divider()

    # 同步按钮
    st.write("**同步操作**")

    if st.button("同步全部到 Obsidian", key="obsidian_sync_all", type="primary", use_container_width=True):
        with st.spinner("正在同步所有数据到 Obsidian..."):
            try:
                from services.obsidian_service import sync_all_to_obsidian
                result = sync_all_to_obsidian()
                st.success(f"同步完成: 成功 {result['success_count']} / 失败 {result['fail_count']} / 跳过 {result['skip_count']}")
                if result["fail_count"] > 0:
                    st.warning(f"有 {result['fail_count']} 条同步失败")
                st.rerun()
            except Exception as e:
                st.error(f"同步失败: {str(e)}")

    st.divider()

    # 分类同步按钮
    col1, col2 = st.columns(2)

    with col1:
        if st.button("同步客户", key="obsidian_sync_clients", use_container_width=True):
            from services.client_service import get_all_clients
            from services.obsidian_service import sync_client_to_obsidian

            clients = get_all_clients()
            success, fail, skip = 0, 0, 0
            progress = st.progress(0, text="同步客户中...")
            for i, c in enumerate(clients):
                r = sync_client_to_obsidian(c["id"])
                if r["skipped"]: skip += 1
                elif r["success"]: success += 1
                else: fail += 1
                progress.progress((i + 1) / len(clients), text=f"客户 {i+1}/{len(clients)}")
            st.success(f"客户同步: 成功 {success} / 失败 {fail} / 跳过 {skip}")

        if st.button("同步任务", key="obsidian_sync_tasks", use_container_width=True):
            from services.task_service import get_all_tasks
            from services.obsidian_service import sync_task_to_obsidian

            tasks = get_all_tasks(limit=1000)
            success, fail, skip = 0, 0, 0
            progress = st.progress(0, text="同步任务中...")
            for i, t in enumerate(tasks):
                r = sync_task_to_obsidian(t["id"])
                if r["skipped"]: skip += 1
                elif r["success"]: success += 1
                else: fail += 1
                if (i + 1) % 10 == 0:
                    progress.progress((i + 1) / len(tasks), text=f"任务 {i+1}/{len(tasks)}")
            progress.progress(1.0, text="完成")
            st.success(f"任务同步: 成功 {success} / 失败 {fail} / 跳过 {skip}")

    with col2:
        if st.button("同步项目", key="obsidian_sync_projects", use_container_width=True):
            from services.project_service import get_all_projects
            from services.obsidian_service import sync_project_to_obsidian

            projects = get_all_projects()
            success, fail, skip = 0, 0, 0
            for p in projects:
                r = sync_project_to_obsidian(p["id"])
                if r["skipped"]: skip += 1
                elif r["success"]: success += 1
                else: fail += 1
            st.success(f"项目同步: 成功 {success} / 失败 {fail} / 跳过 {skip}")

        if st.button("同步文件摘要", key="obsidian_sync_files", use_container_width=True):
            from services.file_service import get_all_files
            from services.obsidian_service import sync_file_to_obsidian

            files = get_all_files(limit=1000)
            success, fail, skip = 0, 0, 0
            for f in files:
                r = sync_file_to_obsidian(f["id"])
                if r["skipped"]: skip += 1
                elif r["success"]: success += 1
                else: fail += 1
            st.success(f"文件同步: 成功 {success} / 失败 {fail} / 跳过 {skip}")

    # 每日总结同步
    st.divider()
    st.write("**同步每日总结**")
    col_date, col_btn = st.columns([3, 1])
    with col_date:
        from datetime import date
        sync_date = st.date_input("选择日期", value=date.today(), key="obsidian_sync_date")
    with col_btn:
        if st.button("同步该日总结", key="obsidian_sync_daily_btn"):
            date_str = sync_date.strftime("%Y-%m-%d")
            from services.obsidian_service import sync_daily_summary_to_obsidian
            with st.spinner(f"同步 {date_str} 每日总结..."):
                r = sync_daily_summary_to_obsidian(date_str)
                if r["success"]:
                    st.success(r["message"])
                else:
                    st.error(r["message"])


def _render_notification_settings():
    st.subheader("通知设置")

    from services.feishu_service import is_configured as feishu_configured, test_feishu_connection, send_daily_reminder
    from services.reminder_service import build_reminder_message, generate_today_briefing, send_today_briefing
    from services.workflow_log_service import get_all_workflow_logs

    # 飞书应用机器人状态
    st.write("**飞书应用机器人**")
    col1, col2 = st.columns(2)
    with col1:
        if feishu_configured():
            st.success("飞书应用机器人已配置")
        else:
            st.warning("飞书应用机器人未配置")
            st.caption("在 .env 中设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET 即可启用")

    # 接收者 ID 输入
    receive_id = st.text_input(
        "接收者 open_id（或 chat_id）",
        placeholder="ou_xxxxx 或 oc_xxxxx",
        key="feishu_receive_id",
        help="从飞书开发者后台获取用户 open_id，或群聊 chat_id",
    )

    with col2:
        if st.button("测试飞书连接", key="btn_test_feishu",
                      disabled=not feishu_configured() or not receive_id):
            with st.spinner("发送测试消息..."):
                result = test_feishu_connection(receive_id)
                if result["success"]:
                    st.success(result["message"])
                else:
                    st.error(result["message"])

    st.divider()

    # 发送提醒
    st.write("**发送提醒**")
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        with st.expander("查看提醒内容"):
            msg = build_reminder_message()
            st.markdown(msg)

    with col_b:
        if st.button("发送每日提醒到飞书", key="btn_daily_reminder",
                      disabled=not feishu_configured() or not receive_id,
                      use_container_width=True):
            with st.spinner("发送中..."):
                r = send_daily_reminder(receive_id)
                if r["success"]:
                    st.success("提醒已发送")
                else:
                    st.error(r["message"])

    with col_c:
        if st.button("发送今日简报", key="btn_today_briefing",
                      disabled=not feishu_configured() or not receive_id,
                      use_container_width=True):
            with st.spinner("生成并发送简报..."):
                r = send_today_briefing(receive_id)
                if r["success"]:
                    st.success("简报已发送")
                else:
                    st.error(r["message"])

    st.divider()

    # 简报预览
    st.write("**今日简报预览**")
    with st.expander("查看简报内容"):
        briefing = generate_today_briefing()
        st.markdown(briefing)

    st.divider()

    # 最近通知日志
    st.write("**最近通知日志**")
    notification_logs = get_all_workflow_logs(
        limit=50,
    )
    # 筛选通知相关的日志
    notif_types = ["reminder_sent", "daily_reminder_sent", "task_reminder_sent",
                   "daily_briefing_sent", "feishu_test"]
    notif_logs = [l for l in notification_logs if l.get("workflow_type") in notif_types]

    if notif_logs:
        rows = []
        for log in notif_logs[:30]:
            rows.append({
                "ID": log["id"],
                "类型": log.get("workflow_type", ""),
                "状态": log.get("status", ""),
                "消息": log.get("message", "")[:80],
                "时间": log.get("created_at", "")[:19],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("暂无通知日志")
