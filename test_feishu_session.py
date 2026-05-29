"""
飞书多轮上下文 + Session 状态管理 + 确认式执行 测试
======================================================
覆盖 11 个测试场景。
运行方式: python test_feishu_session.py
"""
import os
import sys
import json
import time
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 确保数据库已初始化
from database.init_db import init_database
init_database()

from database.db import fetch_one, fetch_all, execute, insert
from services.workflow_log_service import add_workflow_log, get_all_workflow_logs
from utils.date_utils import now_str

TEST_USER_KEY = "test_user_session_001"
TEST_OPEN_ID = "ou_test_001"
TEST_CHAT_ID = "oc_test_001"


def _cleanup():
    """清理测试数据。"""
    execute("DELETE FROM feishu_sessions WHERE user_key LIKE ?", (f"{TEST_USER_KEY}%",))
    execute("DELETE FROM workflow_logs WHERE message LIKE ?", ("%test%",))
    execute("DELETE FROM processed_feishu_events WHERE event_id LIKE ?", ("test_%",))
    # 清理测试创建的任务/项目/客户
    execute("DELETE FROM tasks WHERE title LIKE ?", ("TEST_%",))
    execute("DELETE FROM projects WHERE name LIKE ?", ("TEST_%",))
    execute("DELETE FROM clients WHERE name LIKE ?", ("TEST_%",))
    # 清理 section 命令创建的任务（标题为段落名称）
    execute("DELETE FROM tasks WHERE title IN (?, ?)", ("任务分解", "风险分析"))
    execute("DELETE FROM tasks WHERE description LIKE ?", ("%来自文档第%",))


class TestFeishuSessionService(unittest.TestCase):
    """测试 feishu_session_service.py"""

    @classmethod
    def setUpClass(cls):
        _cleanup()

    def setUp(self):
        """每个测试前清理 session。"""
        execute("DELETE FROM feishu_sessions WHERE user_key = ?", (TEST_USER_KEY,))

    # ── 测试 1: get_or_create_session ──
    def test_01_create_session(self):
        """创建新 session。"""
        from services.feishu_session_service import get_or_create_session

        session = get_or_create_session(TEST_USER_KEY, chat_id=TEST_CHAT_ID, open_id=TEST_OPEN_ID)
        self.assertIsNotNone(session)
        self.assertEqual(session["user_key"], TEST_USER_KEY)
        self.assertEqual(session["status"], "active")
        self.assertEqual(session["current_mode"], "idle")

        # 验证 workflow_log
        logs = get_all_workflow_logs(workflow_type="feishu_session_created", limit=5)
        self.assertTrue(any(TEST_USER_KEY in (l.get("message") or "") for l in logs),
                        "应有 feishu_session_created 日志")

    # ── 测试 2: 同 user_key 只保留一个 active session ──
    def test_02_single_active_session(self):
        """一个 user_key 只保留一个 active session。"""
        from services.feishu_session_service import get_or_create_session

        s1 = get_or_create_session(TEST_USER_KEY)
        s2 = get_or_create_session(TEST_USER_KEY)
        self.assertEqual(s1["id"], s2["id"], "应返回同一个 session")

        # 数据库中应只有一条 active 记录
        from database.db import fetch_all
        rows = fetch_all(
            "SELECT * FROM feishu_sessions WHERE user_key = ? AND status = 'active'",
            (TEST_USER_KEY,),
        )
        self.assertEqual(len(rows), 1)

    # ── 测试 3: update_session ──
    def test_03_update_session(self):
        """更新 session 字段。"""
        from services.feishu_session_service import get_or_create_session, update_session, get_active_session

        get_or_create_session(TEST_USER_KEY)
        result = update_session(TEST_USER_KEY, current_mode="qa",
                               last_question="什么是AI?", last_answer="AI是人工智能")
        self.assertTrue(result)

        session = get_active_session(TEST_USER_KEY)
        self.assertEqual(session["current_mode"], "qa")
        self.assertEqual(session["last_question"], "什么是AI?")

        # 验证 feishu_session_updated 日志
        logs = get_all_workflow_logs(workflow_type="feishu_session_updated", limit=5)
        self.assertTrue(any("current_mode" in (l.get("details") or "") or
                           TEST_USER_KEY in (l.get("message") or "")
                           for l in logs),
                        "应有 feishu_session_updated 日志")

    # ── 测试 4: save / get pending_actions ──
    def test_04_save_and_get_pending_actions(self):
        """保存和读取 pending actions。"""
        from services.feishu_session_service import (
            get_or_create_session, save_pending_actions, get_pending_actions)

        get_or_create_session(TEST_USER_KEY)
        actions = [
            {"action_type": "create_task", "title": "TEST_任务1", "description": "测试任务1"},
            {"action_type": "create_project", "title": "TEST_项目1", "description": "测试项目1"},
            {"action_type": "create_task", "title": "TEST_任务2", "description": "测试任务2"},
        ]
        save_pending_actions(TEST_USER_KEY, actions)

        loaded = get_pending_actions(TEST_USER_KEY)
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[0]["title"], "TEST_任务1")

        # 验证日志
        logs = get_all_workflow_logs(workflow_type="feishu_pending_action_saved", limit=5)
        self.assertTrue(any(TEST_USER_KEY in (l.get("message") or "") for l in logs))

    # ── 测试 5: save / get last_file_analysis ──
    def test_05_save_and_get_file_analysis(self):
        """保存和读取文件分析结果。"""
        from services.feishu_session_service import (
            get_or_create_session, save_last_file_analysis, get_last_file_analysis)

        get_or_create_session(TEST_USER_KEY)
        analysis = {
            "document_summary": "这是一个项目方案文档",
            "sections": [
                {"section_id": 1, "title": "项目概述", "content": "..."},
                {"section_id": 2, "title": "任务列表", "content": "任务1\n任务2\n任务3"},
            ],
            "suggested_actions": [
                {"action_type": "create_project", "title": "TEST_新项目"},
                {"action_type": "create_task", "title": "TEST_任务A"},
            ],
        }
        save_last_file_analysis(TEST_USER_KEY, 999, analysis)

        result = get_last_file_analysis(TEST_USER_KEY)
        self.assertIsNotNone(result)
        self.assertEqual(result["file_id"], 999)
        self.assertEqual(result["analysis"]["document_summary"], "这是一个项目方案文档")
        self.assertEqual(len(result["analysis"]["sections"]), 2)

    # ── 测试 6: session 过期 ──
    def test_06_session_expiry(self):
        """session 超过 30 分钟自动过期。"""
        from services.feishu_session_service import (
            get_or_create_session, get_active_session, is_session_expired)
        from database.db import execute

        session = get_or_create_session(TEST_USER_KEY)
        self.assertIsNotNone(session)

        # 手动设置过期时间为 31 分钟前
        expired_time = (datetime.now() - timedelta(minutes=31)).isoformat()
        execute(
            "UPDATE feishu_sessions SET expires_at = ? WHERE id = ?",
            (expired_time, session["id"]),
        )

        # is_session_expired 应返回 True
        updated = fetch_one("SELECT * FROM feishu_sessions WHERE id = ?", (session["id"],))
        self.assertTrue(is_session_expired(updated))

        # get_active_session 应返回 None
        active = get_active_session(TEST_USER_KEY)
        self.assertIsNone(active, "过期 session 应返回 None")

        # 验证 status 被标记为 expired
        db_session = fetch_one("SELECT * FROM feishu_sessions WHERE id = ?", (session["id"],))
        self.assertEqual(db_session["status"], "expired")

    # ── 测试 7: clear_session ──
    def test_07_clear_session(self):
        """清空 session 上下文。"""
        from services.feishu_session_service import (
            get_or_create_session, clear_session, get_active_session,
            save_pending_actions, get_pending_actions)

        get_or_create_session(TEST_USER_KEY)
        save_pending_actions(TEST_USER_KEY, [{"action_type": "create_task", "title": "TEST_X"}])

        clear_session(TEST_USER_KEY)

        session = get_active_session(TEST_USER_KEY)
        self.assertIsNone(session["last_file_id"])
        self.assertIsNone(session["pending_actions_json"])
        self.assertIsNone(session["last_question"])
        self.assertEqual(session["current_mode"], "idle")

        # pending actions 应为空
        actions = get_pending_actions(TEST_USER_KEY)
        self.assertEqual(len(actions), 0)

        # 验证日志
        logs = get_all_workflow_logs(workflow_type="feishu_session_cleared", limit=5)
        self.assertTrue(any(TEST_USER_KEY in (l.get("message") or "") for l in logs))


class TestFeishuMessageServiceMultiTurn(unittest.TestCase):
    """测试 feishu_message_service.py 多轮上下文"""

    @classmethod
    def setUpClass(cls):
        _cleanup()
        # 预创建一个 session 和 pending actions
        from services.feishu_session_service import (
            get_or_create_session, save_pending_actions, save_last_file_analysis)
        get_or_create_session(TEST_USER_KEY, open_id=TEST_OPEN_ID)
        cls.test_actions = [
            {"action_type": "create_task", "title": "TEST_任务A_多轮",
             "description": "第一个测试任务", "priority": "high"},
            {"action_type": "create_project", "title": "TEST_项目B_多轮",
             "description": "测试项目", "client_name": "测试客户"},
            {"action_type": "create_task", "title": "TEST_任务C_多轮",
             "description": "第三个测试任务", "priority": "low"},
        ]
        save_pending_actions(TEST_USER_KEY, cls.test_actions)

        cls.test_analysis = {
            "document_summary": "多轮测试方案文档",
            "sections": [
                {"section_id": 1, "title": "背景介绍", "content": "项目背景内容..."},
                {"section_id": 2, "title": "任务分解", "content": "任务A\n任务B\n任务C"},
                {"section_id": 3, "title": "风险分析", "content": "风险1: 资源不足\n风险2: 时间紧张"},
            ],
            "suggested_actions": [
                {"action_type": "create_project", "title": "TEST_文档项目"},
                {"action_type": "create_task", "title": "TEST_文档任务1"},
            ],
        }
        save_last_file_analysis(TEST_USER_KEY, 888, cls.test_analysis)

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def setUp(self):
        """每个测试前恢复 pending actions 和文件分析。"""
        from services.feishu_session_service import (
            get_or_create_session, save_pending_actions, save_last_file_analysis)
        get_or_create_session(TEST_USER_KEY, open_id=TEST_OPEN_ID)
        save_pending_actions(TEST_USER_KEY, self.test_actions)
        save_last_file_analysis(TEST_USER_KEY, 888, self.test_analysis)

    # ── 测试 8: "执行1" 执行第一条建议 ──
    def test_08_execute_one(self):
        """回复"执行1"能执行第一条建议。"""
        from services.feishu_message_service import handle_feishu_text_message

        result = handle_feishu_text_message("执行1", sender_id=TEST_USER_KEY)
        self.assertTrue(result["success"])
        self.assertIn("已创建", result.get("reply_text", ""))
        self.assertIn("TEST_任务A_多轮", result.get("reply_text", ""))

        # 验证 pending actions 减少了一条
        from services.feishu_session_service import get_pending_actions
        remaining = get_pending_actions(TEST_USER_KEY)
        self.assertEqual(len(remaining), 2, "执行后应剩余 2 条")

        # 验证 workflow_log
        logs = get_all_workflow_logs(workflow_type="feishu_action_confirmed", limit=5)
        self.assertTrue(any("TEST_任务A_多轮" in (l.get("message") or "") for l in logs),
                        "应有 feishu_action_confirmed 日志")

    # ── 测试 9: "执行全部" 批量执行 ──
    def test_09_execute_all(self):
        """回复"执行全部"能批量执行建议。"""
        from services.feishu_message_service import handle_feishu_text_message
        from services.feishu_session_service import get_pending_actions

        # 验证有 3 条
        actions = get_pending_actions(TEST_USER_KEY)
        self.assertEqual(len(actions), 3)

        result = handle_feishu_text_message("执行全部", sender_id=TEST_USER_KEY)
        self.assertTrue(result["success"])
        reply = result.get("reply_text", "")
        self.assertIn("批量执行结果", reply)

        # 验证 pending actions 已清空
        remaining = get_pending_actions(TEST_USER_KEY)
        self.assertEqual(len(remaining), 0)

    # ── 测试 10: "取消" 清空 session ──
    def test_10_cancel_actions(self):
        """回复"取消"能清空 pending actions。"""
        from services.feishu_message_service import handle_feishu_text_message
        from services.feishu_session_service import get_pending_actions

        result = handle_feishu_text_message("取消", sender_id=TEST_USER_KEY)
        self.assertTrue(result["success"])
        self.assertIn("取消", result.get("reply_text", ""))

        actions = get_pending_actions(TEST_USER_KEY)
        self.assertEqual(len(actions), 0)

        # 验证日志
        logs = get_all_workflow_logs(workflow_type="feishu_action_cancelled", limit=5)
        self.assertTrue(any(TEST_USER_KEY in (l.get("message") or "") for l in logs))

    # ── 测试 11: "清空" / "重新开始" ──
    def test_11_clear_and_restart(self):
        """回复"重新开始"清空整个 session。"""
        from services.feishu_message_service import handle_feishu_text_message
        from services.feishu_session_service import get_active_session

        result = handle_feishu_text_message("重新开始", sender_id=TEST_USER_KEY)
        self.assertTrue(result["success"])
        self.assertIn("清空", result.get("reply_text", ""))

        session = get_active_session(TEST_USER_KEY)
        if session:
            self.assertIsNone(session.get("pending_actions_json"))
            self.assertEqual(session.get("current_mode"), "idle")

    # ── 测试 12: "修改1 名字改成 xxx" ──
    def test_12_modify_action(self):
        """回复"修改1 名字改成 xxx"能修改建议。"""
        from services.feishu_message_service import handle_feishu_text_message
        from services.feishu_session_service import get_pending_actions

        result = handle_feishu_text_message("修改1 名字改成 TEST_修改后的任务", sender_id=TEST_USER_KEY)
        self.assertTrue(result["success"])
        self.assertIn("已修改", result.get("reply_text", ""))
        self.assertIn("TEST_修改后的任务", result.get("reply_text", ""))

        # 验证修改持久化
        actions = get_pending_actions(TEST_USER_KEY)
        self.assertEqual(actions[0]["title"], "TEST_修改后的任务")

        # 验证日志
        logs = get_all_workflow_logs(workflow_type="feishu_action_modified", limit=5)
        self.assertTrue(any("修改" in (l.get("message") or "") for l in logs))

    # ── 测试 13: 修改后再执行，执行的是修改后的内容 ──
    def test_13_modify_then_execute(self):
        """修改后再回复"执行1"，执行的是修改后的内容。"""
        from services.feishu_message_service import handle_feishu_text_message
        from services.feishu_session_service import get_pending_actions

        # 先修改
        handle_feishu_text_message("修改1 标题改成 TEST_最终版任务", sender_id=TEST_USER_KEY)

        # 再执行
        result = handle_feishu_text_message("执行1", sender_id=TEST_USER_KEY)
        self.assertTrue(result["success"])
        self.assertIn("TEST_最终版任务", result.get("reply_text", ""))

        # 验证已从 pending 移除
        actions = get_pending_actions(TEST_USER_KEY)
        titles = [a["title"] for a in actions]
        self.assertNotIn("TEST_最终版任务", titles)

    # ── 测试 14: "把第2部分创建成任务" ──
    def test_14_section_to_task(self):
        """回复"把第2部分创建成任务"能基于上次文件分析生成任务。"""
        from services.feishu_message_service import handle_feishu_text_message

        result = handle_feishu_text_message("把第2部分创建成任务", sender_id=TEST_USER_KEY)
        self.assertTrue(result["success"])
        reply = result.get("reply_text", "")
        self.assertTrue("已创建" in reply or "已存在" in reply,
                       f"应创建或已存在任务，实际: {reply[:100]}")

        # 验证来源是第2部分
        logs = get_all_workflow_logs(workflow_type="document_section_action", limit=5)
        self.assertTrue(any("选段" in (l.get("message") or "") for l in logs))

    # ── 测试 15: "把风险部分写入时间轴" ──
    def test_15_section_keyword_to_timeline(self):
        """回复"把风险部分写入时间轴"能基于关键词匹配段落。"""
        from services.feishu_message_service import handle_feishu_text_message

        result = handle_feishu_text_message("把风险部分写入时间轴", sender_id=TEST_USER_KEY)
        self.assertTrue(result["success"])

    # ── 测试 16: "确认" 触发执行全部 ──
    def test_16_confirm_executes_all(self):
        """回复"确认"触发执行全部 pending actions。"""
        from services.feishu_message_service import handle_feishu_text_message
        from services.feishu_session_service import get_pending_actions

        # 确保有 pending actions
        actions_before = get_pending_actions(TEST_USER_KEY)
        self.assertGreater(len(actions_before), 0, "测试需要 pending actions")

        result = handle_feishu_text_message("确认", sender_id=TEST_USER_KEY)
        self.assertTrue(result["success"])

        # pending 应已清空
        actions_after = get_pending_actions(TEST_USER_KEY)
        self.assertEqual(len(actions_after), 0, "确认后 pending 应清空")

    # ── 测试 17: 上下文指代无匹配时返回提示 ──
    def test_17_context_missing(self):
        """上下文缺失时返回明确提示。"""
        from services.feishu_message_service import handle_feishu_text_message

        # 用一个没有 session 的用户
        result = handle_feishu_text_message("把它创建成项目", sender_id="no_context_user")
        self.assertTrue(result["success"])
        self.assertIn("没有找到最近的文件或建议", result.get("reply_text", ""))

        # 验证 feishu_context_missing 日志
        logs = get_all_workflow_logs(workflow_type="feishu_context_missing", limit=5)
        self.assertTrue(len(logs) > 0, "应有 feishu_context_missing 日志")

    # ── 测试 18: "上面的" / "这个" 上下文指代 ──
    def test_18_shangmian_context(self):
        """回复"上面的文件"能获取上下文。"""
        from services.feishu_message_service import handle_feishu_text_message

        result = handle_feishu_text_message("上面的文件", sender_id=TEST_USER_KEY)
        self.assertTrue(result["success"])
        reply = result.get("reply_text", "")
        # 应有文件信息或建议提示
        self.assertTrue(
            "文件" in reply or "建议" in reply or "问答" in reply or "帮助" in reply,
            f"应返回有用信息，实际: {reply[:100]}"
        )


class TestFeishuEventDedup(unittest.TestCase):
    """测试飞书事件去重"""

    @classmethod
    def setUpClass(cls):
        _cleanup()

    def test_19_duplicate_event_skipped(self):
        """同一个飞书事件重复推送不会重复执行。"""
        from database.db import insert

        event_id = "test_event_dedup_001"
        msg_id = "om_test_msg_001"

        # 插入第一条事件记录
        insert(
            """INSERT INTO processed_feishu_events
               (event_id, message_id, open_id, chat_id, message_text, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_id, msg_id, TEST_OPEN_ID, TEST_CHAT_ID, "测试消息", "success", now_str()),
        )

        # 尝试再次插入（应失败或静默跳过）
        try:
            insert(
                """INSERT INTO processed_feishu_events
                   (event_id, message_id, open_id, chat_id, message_text, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (event_id, msg_id, TEST_OPEN_ID, TEST_CHAT_ID, "测试消息", "pending", now_str()),
            )
        except Exception:
            pass  # 预期 UNIQUE constraint violation

        # 验证只有一条记录
        from database.db import fetch_all
        rows = fetch_all(
            "SELECT * FROM processed_feishu_events WHERE event_id = ?",
            (event_id,),
        )
        self.assertEqual(len(rows), 1)

        # 验证去重日志
        logs = get_all_workflow_logs(workflow_type="feishu_duplicate_skipped", limit=5)
        # 可能没有触发 webhook，这里只验证表结构工作正常


class TestWorkflowLogs(unittest.TestCase):
    """测试 workflow_logs 完整性"""

    @classmethod
    def setUpClass(cls):
        _cleanup()

    def test_20_all_log_types(self):
        """验证所有 workflow_type 都有日志记录。"""
        expected_types = [
            "feishu_session_created",
            "feishu_session_updated",
            "feishu_session_cleared",
            "feishu_pending_action_saved",
            "feishu_action_confirmed",
            "feishu_action_cancelled",
            "feishu_action_modified",
            "feishu_context_missing",
        ]

        # 触发所有类型的日志
        from services.feishu_session_service import (
            get_or_create_session, update_session, clear_session,
            save_pending_actions, save_last_file_analysis)
        from services.workflow_log_service import add_workflow_log

        get_or_create_session(TEST_USER_KEY + "_logtest")
        update_session(TEST_USER_KEY + "_logtest", current_mode="qa")
        save_pending_actions(TEST_USER_KEY + "_logtest",
                           [{"action_type": "create_task", "title": "T"}])
        clear_session(TEST_USER_KEY + "_logtest")

        add_workflow_log("feishu_action_confirmed", "test", None, "success", "test confirm")
        add_workflow_log("feishu_action_cancelled", "test", None, "success", "test cancel")
        add_workflow_log("feishu_action_modified", "test", None, "success", "test modify")
        add_workflow_log("feishu_context_missing", "test", None, "success", "test missing")

        # 检查每种类型都有记录
        for wf_type in expected_types:
            logs = get_all_workflow_logs(workflow_type=wf_type, limit=5)
            self.assertTrue(len(logs) > 0,
                          f"缺少 workflow_type={wf_type} 的日志记录")

    def test_21_log_structure(self):
        """验证日志记录结构完整。"""
        log_id = add_workflow_log("feishu_session_created", "feishu", 1, "success",
                                  "test message", '{"key": "value"}')
        self.assertIsNotNone(log_id)
        self.assertGreater(log_id, 0)

        from services.workflow_log_service import get_workflow_log
        log = get_workflow_log(log_id)
        self.assertIsNotNone(log)
        self.assertEqual(log["workflow_type"], "feishu_session_created")
        self.assertEqual(log["source_type"], "feishu")
        self.assertEqual(log["status"], "success")
        self.assertEqual(log["message"], "test message")


class TestFeishuApiCleanliness(unittest.TestCase):
    """测试 feishu_api.py 只负责接收事件和回复消息"""

    def test_22_api_no_business_logic(self):
        """验证 feishu_api.py 不写复杂业务逻辑。"""
        import inspect
        import feishu_api

        # 获取 feishu_api.py 中定义的所有函数
        funcs = [name for name, obj in inspect.getmembers(feishu_api, inspect.isfunction)
                 if not name.startswith("_")]

        # 预期只有 webhook 端点、token 获取、消息回复、事件记录等基础设施函数
        allowed_business_keywords = [
            "handle_feishu_text_message",  # 不应直接出现在 feishu_api.py
        ]

        source = inspect.getsource(feishu_api)
        for keyword in allowed_business_keywords:
            # feishu_api.py 应该只 import 业务函数，不应内联实现
            # 检查是否有 def handle_feishu_text_message 在 feishu_api.py 中
            self.assertNotIn(f"def {keyword}", source,
                           f"feishu_api.py 不应包含 {keyword} 的业务实现")

        # 验证路由处理函数只做 routing + reply
        webhook_source = inspect.getsource(feishu_api.feishu_webhook)
        # 应该 import 业务模块而不是内联实现
        self.assertIn("from services.feishu_message_service import", source,
                     "feishu_api.py 应导入 feishu_message_service")
        self.assertIn("from services.feishu_file_service import", source,
                     "feishu_api.py 应导入 feishu_file_service")


if __name__ == "__main__":
    # 先初始化数据库
    print("初始化数据库...")
    init_database()
    print("数据库就绪。\n")

    # 运行测试
    unittest.main(verbosity=2)
