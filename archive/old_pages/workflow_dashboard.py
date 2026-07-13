"""
Workflow Dashboard — 工作流监控页面。
查看所有工作流运行状态：运行中、待确认、失败、已完成。
可查看每条工作流的详细信息，包括触发来源、执行步骤、AI输出、错误信息。
"""
import streamlit as st
from services.workflow_service import WorkflowService
from services.workflow_definitions import WORKFLOW_REGISTRY


def render():
    st.title("工作流监控")

    # Summary metrics
    try:
        running = WorkflowService.get_runs_by_status("running")
        waiting = WorkflowService.get_pending_confirmations()
        failed = WorkflowService.get_runs_by_status("failed")
        completed = WorkflowService.get_runs_by_status("completed")
    except Exception:
        st.warning("无法加载工作流数据，请确认数据库已初始化。")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("运行中", len(running))
    col2.metric("待确认", len(waiting))
    col3.metric("失败", len(failed))
    col4.metric("已完成", len(completed))

    st.divider()

    tab_waiting, tab_running, tab_failed, tab_completed, tab_all = st.tabs(
        ["待确认", "运行中", "失败", "已完成", "全部"]
    )

    with tab_waiting:
        _render_run_list(waiting, show_confirm_actions=True)

    with tab_running:
        _render_run_list(running)

    with tab_failed:
        _render_run_list(failed, show_retry=True)

    with tab_completed:
        _render_run_list(completed)

    with tab_all:
        all_runs = WorkflowService.get_all_runs(limit=200)
        _render_run_list(all_runs)


def _render_run_list(runs, show_confirm_actions=False, show_retry=False):
    if not runs:
        st.info("暂无数据")
        return

    definition_labels = {k: v.label for k, v in WORKFLOW_REGISTRY.items()}

    for run in runs:
        status_emoji = {
            "running": "🔄", "waiting_confirmation": "⏳",
            "confirmed": "✅", "completed": "✅",
            "failed": "❌", "cancelled": "🚫",
        }.get(run["status"], "❓")

        wf_label = definition_labels.get(run["workflow_type"], run["workflow_type"])
        title_parts = [f"{status_emoji} [{wf_label}]"]
        if run.get("source_type"):
            title_parts.append(f"{run['source_type']}#{run.get('source_id', '-')}")
        if run.get("error_message"):
            title_parts.append(f"— {run['error_message'][:60]}")
        title = " ".join(title_parts)

        expanded = run["status"] in ("waiting_confirmation", "running")
        with st.expander(title, expanded=expanded):
            col1, col2 = st.columns([3, 2])

            with col1:
                st.caption(f"Run ID: {run['id']} | 创建: {run.get('created_at', '-')[:19] if run.get('created_at') else '-'}")
                if run.get("completed_at"):
                    st.caption(f"完成: {run['completed_at'][:19] if run.get('completed_at') else '-'}")

                # Trigger info
                trigger = run.get("trigger_info", {})
                if isinstance(trigger, str):
                    import json
                    try:
                        trigger = json.loads(trigger)
                    except Exception:
                        trigger = {}
                if trigger:
                    st.caption(f"触发信息: {str(trigger)[:200]}")

                # Steps table
                steps = run.get("steps", [])
                if steps:
                    step_data = []
                    for s in steps:
                        step_status_icon = {
                            "pending": "⏳", "running": "🔄", "completed": "✅",
                            "failed": "❌", "skipped": "⏭️"
                        }.get(s["status"], "❓")
                        step_data.append({
                            "状态": step_status_icon,
                            "步骤": s["step_name"],
                            "开始": (s.get("started_at") or "-")[:19] if s.get("started_at") else "-",
                            "完成": (s.get("completed_at") or "-")[:19] if s.get("completed_at") else "-",
                            "输出": (s.get("output_summary") or "")[:80],
                            "错误": (s.get("error_message") or "")[:80],
                        })
                    st.dataframe(step_data, use_container_width=True, hide_index=True)

            with col2:
                # Error details for failed runs
                if run["status"] == "failed":
                    st.error(f"失败步骤: {run.get('error_step_name', 'unknown')}")
                    if run.get("error_message"):
                        st.caption(f"错误: {run['error_message']}")

                # Confirmation actions
                if show_confirm_actions and run["status"] == "waiting_confirmation":
                    preview = run.get("preview_json", {})
                    if isinstance(preview, str):
                        import json
                        try:
                            preview = json.loads(preview)
                        except Exception:
                            preview = {}
                    if preview:
                        st.markdown("**预览内容**")
                        st.markdown(f"**标题**: {preview.get('title', '-')}")
                        summary = preview.get('summary', '-')
                        st.markdown(f"**摘要**: {summary[:150] if summary else '-'}")
                        tags = preview.get('tags', [])
                        if tags:
                            st.markdown(f"**标签**: {', '.join(tags)}")
                        rp = preview.get('related_project')
                        if rp:
                            st.markdown(f"**关联项目**: {rp.get('name', rp) if isinstance(rp, dict) else rp}")
                        rc = preview.get('related_client')
                        if rc:
                            st.markdown(f"**关联客户**: {rc.get('name', rc) if isinstance(rc, dict) else rc}")
                        pending = preview.get('pending_actions', [])
                        if pending:
                            st.markdown("**待执行操作**:")
                            for pa in pending:
                                st.caption(f"  - {pa}")
                        tasks = preview.get('suggested_tasks', [])
                        if tasks:
                            st.markdown("**建议任务**:")
                            for t in tasks[:5]:
                                title_t = t.get('title', str(t)) if isinstance(t, dict) else str(t)
                                st.caption(f"  - {title_t}")

                    c_col1, c_col2 = st.columns(2)
                    with c_col1:
                        if st.button("✅ 确认执行", key=f"confirm_{run['id']}"):
                            WorkflowService.confirm_run(run["id"])
                            st.rerun()
                    with c_col2:
                        if st.button("❌ 取消", key=f"cancel_{run['id']}"):
                            WorkflowService.cancel_run(run["id"])
                            st.rerun()

                # Retry button for failed runs
                if show_retry and run["status"] == "failed":
                    if st.button("🔄 重新执行", key=f"retry_{run['id']}"):
                        WorkflowService.retry_run(run["id"])
                        st.success(f"Run #{run['id']} 已重置，将重新执行。")
                        st.rerun()

                # Source info
                source_type = run.get("source_type")
                source_id = run.get("source_id")
                if source_type and source_id:
                    st.caption(f"来源: {source_type} #{source_id}")

                # Final result
                final = run.get("final_result_json")
                if final and isinstance(final, dict):
                    st.markdown("**最终结果**")
                    for k, v in final.items():
                        st.caption(f"{k}: {str(v)[:100]}")
