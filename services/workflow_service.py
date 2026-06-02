"""
workflow_service.py — Core workflow execution engine for Workflow Agent v2.
Handles: run creation, step execution, status tracking, confirmation, retry.
"""
import json
from database.db import insert, execute, fetch_one, fetch_all
from utils.date_utils import now_str
from services.workflow_definitions import WORKFLOW_REGISTRY


class WorkflowService:
    """Core workflow engine. Each execution is a 'run' containing ordered 'steps'."""

    # ------------------------------------------------------------------
    # Run Lifecycle
    # ------------------------------------------------------------------

    @staticmethod
    def start_run(workflow_type: str, source_type: str = None,
                  source_id: int = None, trigger_info: dict = None) -> dict:
        """Create a new workflow_runs record and all its workflow_steps."""
        definition = WORKFLOW_REGISTRY.get(workflow_type)
        if not definition:
            raise ValueError(f"Unknown workflow_type: {workflow_type}")

        now = now_str()
        run_id = insert(
            """INSERT INTO workflow_runs
               (workflow_type, source_type, source_id, status, trigger_info,
                started_at, created_at, updated_at)
               VALUES (?, ?, ?, 'running', ?, ?, ?, ?)""",
            (workflow_type, source_type, source_id,
             json.dumps(trigger_info or {}, ensure_ascii=False),
             now, now, now),
        )

        for i, step_def in enumerate(definition.steps):
            insert(
                """INSERT INTO workflow_steps
                   (run_id, step_name, step_order, status, created_at)
                   VALUES (?, ?, ?, 'pending', ?)""",
                (run_id, step_def.name, i + 1, now),
            )

        WorkflowService._log(run_id, None, workflow_type, source_type, source_id,
                             "running", f"Workflow started: {definition.label}")
        return WorkflowService.get_run(run_id)

    @staticmethod
    def execute_step(run_id: int, step_name: str) -> dict:
        """Mark a step as 'running'."""
        now = now_str()
        execute(
            """UPDATE workflow_steps
               SET status = 'running', started_at = ?
               WHERE run_id = ? AND step_name = ?""",
            (now, run_id, step_name),
        )
        step = fetch_one(
            "SELECT * FROM workflow_steps WHERE run_id = ? AND step_name = ?",
            (run_id, step_name),
        )
        WorkflowService._log(run_id, step["id"] if step else None,
                             f"step_{step_name}", None, None, "running",
                             f"Step started: {step_name}")
        return step

    @staticmethod
    def complete_step(run_id: int, step_name: str,
                      output_summary: str = "") -> dict:
        """Mark a step as 'completed'."""
        now = now_str()
        execute(
            """UPDATE workflow_steps
               SET status = 'completed', completed_at = ?,
                   output_summary = ?
               WHERE run_id = ? AND step_name = ?""",
            (now, output_summary, run_id, step_name),
        )
        step = fetch_one(
            "SELECT * FROM workflow_steps WHERE run_id = ? AND step_name = ?",
            (run_id, step_name),
        )
        WorkflowService._log(run_id, step["id"] if step else None,
                             f"step_{step_name}", None, None, "success",
                             f"Step completed: {step_name}")
        return step

    @staticmethod
    def fail_step(run_id: int, step_name: str, error_message: str) -> dict:
        """Mark a step and its run as 'failed'."""
        now = now_str()
        execute(
            """UPDATE workflow_steps
               SET status = 'failed', completed_at = ?,
                   error_message = ?
               WHERE run_id = ? AND step_name = ?""",
            (now, error_message, run_id, step_name),
        )
        execute(
            """UPDATE workflow_runs
               SET status = 'failed', completed_at = ?,
                   error_step_name = ?, error_message = ?,
                   updated_at = ?
               WHERE id = ?""",
            (now, step_name, error_message, now, run_id),
        )
        step = fetch_one(
            "SELECT * FROM workflow_steps WHERE run_id = ? AND step_name = ?",
            (run_id, step_name),
        )
        WorkflowService._log(run_id, step["id"] if step else None,
                             f"step_{step_name}", None, None, "error",
                             f"Step FAILED: {step_name} | {error_message}")
        return step

    @staticmethod
    def complete_run(run_id: int, final_result: dict = None) -> dict:
        """Mark a run as 'completed'."""
        now = now_str()
        execute(
            """UPDATE workflow_runs
               SET status = 'completed', completed_at = ?,
                   final_result_json = ?, updated_at = ?
               WHERE id = ?""",
            (now, json.dumps(final_result or {}, ensure_ascii=False),
             now, run_id),
        )
        WorkflowService._log(run_id, None, "workflow_run", None, None, "success",
                             f"Workflow completed: run_id={run_id}")
        return WorkflowService.get_run(run_id)

    # ------------------------------------------------------------------
    # Confirmation
    # ------------------------------------------------------------------

    @staticmethod
    def set_waiting_confirmation(run_id: int, preview: dict) -> dict:
        """Set run status to 'waiting_confirmation' and store preview_json."""
        now = now_str()
        execute(
            """UPDATE workflow_runs
               SET status = 'waiting_confirmation',
                   preview_json = ?, updated_at = ?
               WHERE id = ?""",
            (json.dumps(preview, ensure_ascii=False), now, run_id),
        )
        WorkflowService._log(run_id, None, "workflow_run", None, None, "success",
                             "Waiting for user confirmation")
        return WorkflowService.get_run(run_id)

    @staticmethod
    def confirm_run(run_id: int) -> dict:
        """User confirms. Change status back to 'running'."""
        now = now_str()
        execute(
            """UPDATE workflow_runs
               SET status = 'running', updated_at = ?
               WHERE id = ?""",
            (now, run_id),
        )
        WorkflowService._log(run_id, None, "workflow_run", None, None, "success",
                             "User confirmed, continuing execution")
        return WorkflowService.get_run(run_id)

    @staticmethod
    def cancel_run(run_id: int) -> dict:
        """User cancels at confirmation stage."""
        now = now_str()
        execute(
            """UPDATE workflow_runs
               SET status = 'cancelled', completed_at = ?,
                   error_message = '用户取消', updated_at = ?
               WHERE id = ?""",
            (now, now, run_id),
        )
        return WorkflowService.get_run(run_id)

    # ------------------------------------------------------------------
    # Retry
    # ------------------------------------------------------------------

    @staticmethod
    def retry_run(run_id: int) -> dict:
        """Full workflow retry: reset all steps to pending."""
        now = now_str()
        execute(
            """UPDATE workflow_runs
               SET status = 'running', error_step_name = NULL,
                   error_message = NULL, updated_at = ?
               WHERE id = ?""",
            (now, run_id),
        )
        execute(
            """UPDATE workflow_steps
               SET status = 'pending', started_at = NULL,
                   completed_at = NULL, error_message = NULL,
                   input_summary = NULL, output_summary = NULL
               WHERE run_id = ?""",
            (run_id,),
        )
        WorkflowService._log(run_id, None, "workflow_run", None, None, "success",
                             f"Workflow retry initiated: run_id={run_id}")
        return WorkflowService.get_run(run_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @staticmethod
    def get_run(run_id: int) -> dict | None:
        """Return a run with its steps nested, JSON fields parsed."""
        run = fetch_one("SELECT * FROM workflow_runs WHERE id = ?", (run_id,))
        if not run:
            return None
        run["steps"] = fetch_all(
            "SELECT * FROM workflow_steps WHERE run_id = ? ORDER BY step_order",
            (run_id,),
        )
        for json_field in ("trigger_info", "preview_json", "final_result_json"):
            if run.get(json_field):
                try:
                    run[json_field] = json.loads(run[json_field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return run

    @staticmethod
    def get_runs_by_status(status: str, limit: int = 50) -> list[dict]:
        """Get all runs with a given status, with steps nested."""
        runs = fetch_all(
            "SELECT * FROM workflow_runs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        )
        for r in runs:
            r["steps"] = fetch_all(
                "SELECT * FROM workflow_steps WHERE run_id = ? ORDER BY step_order",
                (r["id"],),
            )
            for json_field in ("trigger_info", "preview_json", "final_result_json"):
                if r.get(json_field):
                    try:
                        r[json_field] = json.loads(r[json_field])
                    except (json.JSONDecodeError, TypeError):
                        pass
        return runs

    @staticmethod
    def get_all_runs(limit: int = 100) -> list[dict]:
        """Get all runs, most recent first, with steps nested."""
        runs = fetch_all(
            "SELECT * FROM workflow_runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        for r in runs:
            r["steps"] = fetch_all(
                "SELECT * FROM workflow_steps WHERE run_id = ? ORDER BY step_order",
                (r["id"],),
            )
            for json_field in ("trigger_info", "preview_json", "final_result_json"):
                if r.get(json_field):
                    try:
                        r[json_field] = json.loads(r[json_field])
                    except (json.JSONDecodeError, TypeError):
                        pass
        return runs

    @staticmethod
    def get_pending_confirmations() -> list[dict]:
        """Get all runs awaiting user confirmation."""
        return WorkflowService.get_runs_by_status("waiting_confirmation")

    # ------------------------------------------------------------------
    # Core Executor
    # ------------------------------------------------------------------

    @staticmethod
    def run_workflow(workflow_type: str, source_type: str = None,
                     source_id: int = None, trigger_info: dict = None,
                     step_handler: callable = None) -> dict:
        """Execute a full workflow from start to completion or until
        a confirmation point or failure.

        Args:
            workflow_type: key into WORKFLOW_REGISTRY
            source_type: 'file', 'feishu', 'task', etc.
            source_id: FK to the source entity
            trigger_info: context dict
            step_handler: callback(run_id, step_def, step_record) -> dict
                Returns {'success': bool, 'output': str, 'wait_confirmation': bool,
                         'preview': dict|None, 'error': str|None}

        Returns:
            {"success": bool, "run": dict, "error": str|None}
        """
        definition = WORKFLOW_REGISTRY.get(workflow_type)
        if not definition:
            return {"success": False, "run": None,
                    "error": f"Unknown workflow_type: {workflow_type}"}

        run = WorkflowService.start_run(workflow_type, source_type, source_id, trigger_info)

        for step_def in definition.steps:
            WorkflowService.execute_step(run["id"], step_def.name)

            if step_handler is None:
                WorkflowService.complete_step(run["id"], step_def.name, "No handler")
                continue

            try:
                result = step_handler(run["id"], step_def, {})
            except Exception as e:
                WorkflowService.fail_step(run["id"], step_def.name, str(e))
                return {"success": False, "run": WorkflowService.get_run(run["id"]),
                        "error": str(e)}

            if result.get("wait_confirmation"):
                WorkflowService.complete_step(run["id"], step_def.name,
                                              result.get("output", ""))
                WorkflowService.set_waiting_confirmation(run["id"], result.get("preview", {}))
                return {"success": True, "run": WorkflowService.get_run(run["id"]),
                        "wait_confirmation": True, "error": None}

            if not result.get("success"):
                err_msg = result.get("error", "Unknown error")
                WorkflowService.fail_step(run["id"], step_def.name, err_msg)
                if step_def.critical:
                    return {"success": False, "run": WorkflowService.get_run(run["id"]),
                            "error": err_msg}
                WorkflowService.complete_step(run["id"], step_def.name,
                                              f"Non-critical error: {err_msg}")
            else:
                WorkflowService.complete_step(run["id"], step_def.name,
                                              result.get("output", ""))

        final_run = WorkflowService.complete_run(run["id"])
        return {"success": True, "run": final_run, "error": None}

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    @staticmethod
    def _log(run_id: int, step_id: int, workflow_type: str,
             source_type: str, source_id: int, status: str,
             message: str, details: str = ""):
        """Write a row to workflow_logs with run_id and step_id."""
        try:
            insert(
                """INSERT INTO workflow_logs
                   (workflow_type, source_type, source_id, run_id, step_id,
                    status, message, details, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (workflow_type, source_type, source_id, run_id, step_id,
                 status, message, details, now_str()),
            )
        except Exception:
            pass
