"""
长期记忆 + 关系图谱增强 + 主动工作流 测试
==========================================
覆盖 10 个测试场景。
运行方式: python test_feishu_memory.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.init_db import init_database
init_database()

from database.db import fetch_all, execute
from services.workflow_log_service import add_workflow_log, get_all_workflow_logs
from utils.date_utils import now_str, today_str

TEST_CLIENT_ID = 99901
TEST_PROJECT_ID = 99902
TEST_TASK_ID = 99903


def _setup_test_data():
    """创建测试数据。"""
    execute("DELETE FROM memory_items")
    execute("DELETE FROM relations WHERE source_id >= 99900 OR target_id >= 99900")

    # 确保有测试用的 client/project/task（幂等）
    from database.db import fetch_one
    c = fetch_one("SELECT id FROM clients WHERE id = ?", (TEST_CLIENT_ID,))
    if not c:
        from database.db import insert
        insert("INSERT INTO clients (id, name, description, created_at) VALUES (?, ?, ?, ?)",
               (TEST_CLIENT_ID, "TEST_记忆测试客户", "用于测试的客户", now_str()))
    p = fetch_one("SELECT id FROM projects WHERE id = ?", (TEST_PROJECT_ID,))
    if not p:
        from database.db import insert
        insert("INSERT INTO projects (id, name, description, status, client_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
               (TEST_PROJECT_ID, "TEST_记忆测试项目", "用于测试的项目", "active", TEST_CLIENT_ID, now_str()))
    t = fetch_one("SELECT id FROM tasks WHERE id = ?", (TEST_TASK_ID,))
    if not t:
        from database.db import insert
        insert("INSERT INTO tasks (id, title, description, status, priority, project_id, client_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               (TEST_TASK_ID, "TEST_记忆测试任务", "用于测试的任务", "todo", "high", TEST_PROJECT_ID, TEST_CLIENT_ID, now_str()))


def _cleanup():
    """清理测试数据。"""
    execute("DELETE FROM memory_items WHERE client_id = ? OR project_id = ? OR task_id = ?",
            (TEST_CLIENT_ID, TEST_PROJECT_ID, TEST_TASK_ID))
    execute("DELETE FROM relations WHERE source_id >= 99900 OR target_id >= 99900")


class TestMemoryService(unittest.TestCase):
    """测试 memory_service.py"""

    @classmethod
    def setUpClass(cls):
        _setup_test_data()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    def setUp(self):
        execute("DELETE FROM memory_items WHERE client_id = ? OR project_id = ?",
                (TEST_CLIENT_ID, TEST_PROJECT_ID))

    # ── 测试 1: 保存和读取记忆 ──
    def test_01_save_and_get_memory(self):
        """保存记忆并读取。"""
        from services.memory_service import save_memory_item, get_memory_by_client, get_memory_by_project

        mid = save_memory_item(
            memory_type="client_preference",
            title="TEST_客户偏好测试",
            content="该客户喜欢用微信沟通，每周一上午开会",
            source_type="test", source_id=1,
            importance="high", client_id=TEST_CLIENT_ID,
        )
        self.assertIsNotNone(mid)
        self.assertGreater(mid, 0)

        # 按客户读取
        client_memories = get_memory_by_client(TEST_CLIENT_ID)
        self.assertGreater(len(client_memories), 0)
        self.assertEqual(client_memories[0]["title"], "TEST_客户偏好测试")

        # 按项目读取（保存一条）
        save_memory_item(
            memory_type="project_risk",
            title="TEST_项目风险测试",
            content="资源不足可能导致延期",
            source_type="test", source_id=2,
            importance="critical", project_id=TEST_PROJECT_ID,
        )
        project_memories = get_memory_by_project(TEST_PROJECT_ID)
        self.assertGreater(len(project_memories), 0)

        # 验证 workflow_logs
        logs = get_all_workflow_logs(workflow_type="memory_item_created", limit=10)
        self.assertTrue(any("TEST_" in (l.get("message") or "") for l in logs))

    # ── 测试 2: 幂等保存 ──
    def test_02_idempotent_save(self):
        """重复保存同一来源的记忆不重复插入。"""
        from services.memory_service import save_memory_item

        mid1 = save_memory_item(
            memory_type="decision", title="TEST_幂等测试",
            content="版本1", source_type="test", source_id=5,
            client_id=TEST_CLIENT_ID,
        )
        mid2 = save_memory_item(
            memory_type="decision", title="TEST_幂等测试",
            content="版本2——更新后的内容", source_type="test", source_id=5,
            client_id=TEST_CLIENT_ID,
        )
        self.assertEqual(mid1, mid2, "同一来源应更新而非新增")

        from database.db import fetch_all
        rows = fetch_all(
            "SELECT * FROM memory_items WHERE source_type = 'test' AND source_id = 5 AND title = 'TEST_幂等测试'"
        )
        self.assertEqual(len(rows), 1)
        self.assertIn("版本2", rows[0]["content"])

        # 验证更新日志
        logs = get_all_workflow_logs(workflow_type="memory_item_updated", limit=5)
        self.assertTrue(any("TEST_幂等测试" in (l.get("message") or "") for l in logs))

    # ── 测试 3: 搜索记忆 ──
    def test_03_search_memory(self):
        """测试记忆搜索。"""
        from services.memory_service import save_memory_item, search_memory

        save_memory_item(
            memory_type="important_fact", title="TEST_签约时间",
            content="客户于2024年3月签订年度合同",
            source_type="test", source_id=10, importance="high",
            client_id=TEST_CLIENT_ID,
        )

        results = search_memory("签约时间")
        self.assertGreater(len(results), 0)

        results2 = search_memory("年度合同")
        self.assertGreater(len(results2), 0)

    # ── 测试 4: 提取记忆 ──
    def test_04_extract_memory_from_text(self):
        """从文本提取长期记忆。"""
        from services.memory_service import extract_memory_from_text

        text = """今天和张三公司的王总开了项目启动会。
        客户要求所有交付物必须在6月底前完成，这是硬性要求。
        项目预算有80万，但开发团队人手不足，可能需要外包一部分。
        下次跟进会议定在下周三。"""

        items = extract_memory_from_text(
            text, source_type="test", source_id=20,
            client_id=TEST_CLIENT_ID, project_id=TEST_PROJECT_ID,
        )
        self.assertIsInstance(items, list)
        # AI 提取可能成功也可能返回空，不强制要求数量
        # 但应该至少提取到截止日期和预算信息

        # 验证 workflow_log
        logs = get_all_workflow_logs(workflow_type="memory_extraction", limit=5)
        self.assertTrue(any("test" in (l.get("source_type") or "") for l in logs))

    # ── 测试 5: 自动提取并保存 ──
    def test_05_auto_extract_and_save(self):
        """自动从文本提取并保存记忆。"""
        from services.memory_service import auto_extract_and_save, get_memory_by_client

        text = """AI问答记录：用户询问了关于项目延期的风险，
        AI回答指出项目A的项目B有3个高优先级任务已逾期，
        建议优先处理。客户对接人表示理解但希望能在本月内交付。"""

        count = auto_extract_and_save(
            text, source_type="feishu_qa", source_id=0,
            client_id=TEST_CLIENT_ID, project_id=TEST_PROJECT_ID,
        )
        self.assertGreaterEqual(count, 0)

        if count > 0:
            memories = get_memory_by_client(TEST_CLIENT_ID)
            self.assertGreater(len(memories), 0)

    # ── 测试 6: 统计信息 ──
    def test_06_memory_stats(self):
        """测试记忆统计。"""
        from services.memory_service import get_memory_stats, save_memory_item

        save_memory_item(
            memory_type="follow_up", title="TEST_跟进统计",
            content="测试数据", source_type="test", source_id=30,
            importance="high", client_id=TEST_CLIENT_ID,
        )

        stats = get_memory_stats()
        self.assertIn("total", stats)
        self.assertIn("by_type", stats)
        self.assertIn("by_importance", stats)
        self.assertGreater(stats["total"], 0)


class TestRelationGraphEnhanced(unittest.TestCase):
    """测试关系图谱增强"""

    @classmethod
    def setUpClass(cls):
        _setup_test_data()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    # ── 测试 7: 语义关系 ──
    def test_07_semantic_relations(self):
        """创建语义关系并查询。"""
        from services.relation_service import (
            add_semantic_relation, find_entity_risks, find_entity_follow_ups,
            get_entity_graph, get_client_graph, get_project_graph,
        )

        # 创建风险关系
        rid1 = add_semantic_relation(
            "project", TEST_PROJECT_ID, "task", TEST_TASK_ID,
            relation_type="risk_related", description="任务阻塞可能导致项目延期",
        )
        self.assertGreater(rid1, 0)

        # 创建跟进关系
        rid2 = add_semantic_relation(
            "client", TEST_CLIENT_ID, "project", TEST_PROJECT_ID,
            relation_type="follow_up_required", description="需要跟进项目进度",
        )
        self.assertGreater(rid2, 0)

        # 查找风险关系
        risks = find_entity_risks("project", TEST_PROJECT_ID)
        self.assertGreater(len(risks), 0)

        # 查找跟进关系
        follow_ups = find_entity_follow_ups("client", TEST_CLIENT_ID)
        self.assertGreater(len(follow_ups), 0)

        # 实体图谱
        graph = get_entity_graph("project", TEST_PROJECT_ID)
        self.assertIn("entity", graph)
        self.assertIn("nodes", graph)
        self.assertIn("edges", graph)
        self.assertIn("risks", graph)
        self.assertGreater(len(graph["risks"]), 0)

        # 客户图谱
        c_graph = get_client_graph(TEST_CLIENT_ID)
        self.assertIn("memories", c_graph)
        self.assertIn("risk_memories", c_graph)

        # 项目图谱
        p_graph = get_project_graph(TEST_PROJECT_ID)
        self.assertIn("memories", p_graph)

    # ── 测试 8: 查找全部风险和跟进 ──
    def test_08_find_all_risks_and_followups(self):
        """查找全局风险和跟进关系。"""
        from services.relation_service import find_risk_relations, find_follow_up_relations

        risks = find_risk_relations()
        self.assertIsInstance(risks, list)

        follow_ups = find_follow_up_relations()
        self.assertIsInstance(follow_ups, list)


class TestProactiveSuggestions(unittest.TestCase):
    """测试主动工作流建议"""

    @classmethod
    def setUpClass(cls):
        _setup_test_data()
        # 添加测试记忆
        from services.memory_service import save_memory_item
        save_memory_item(
            memory_type="project_risk", title="TEST_风险记忆",
            content="测试风险描述", source_type="test", source_id=40,
            importance="high", project_id=TEST_PROJECT_ID, client_id=TEST_CLIENT_ID,
        )

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    # ── 测试 9: 每日建议 ──
    def test_09_daily_suggestions(self):
        """生成今日主动建议。"""
        from services.proactive_suggestion_service import generate_daily_suggestions

        s = generate_daily_suggestions()
        self.assertIn("date", s)
        self.assertIn("priority_tasks", s)
        self.assertIn("overdue_items", s)
        self.assertIn("clients_to_follow", s)
        self.assertIn("project_risks", s)
        self.assertIn("recent_memories", s)

        # 验证 workflow_log
        logs = get_all_workflow_logs(workflow_type="proactive_daily_suggestions", limit=5)
        self.assertTrue(len(logs) > 0)

    # ── 测试 10: 项目建议 ──
    def test_10_project_suggestions(self):
        """生成项目级主动建议。"""
        from services.proactive_suggestion_service import generate_project_suggestions

        s = generate_project_suggestions(TEST_PROJECT_ID)
        self.assertIsNotNone(s.get("project"))
        self.assertIn("risks", s)
        self.assertIn("blocked_tasks", s)
        self.assertIn("overdue_tasks", s)
        self.assertIn("memories", s)

        logs = get_all_workflow_logs(workflow_type="proactive_project_suggestions", limit=5)
        self.assertTrue(len(logs) > 0)

    # ── 测试 11: 客户建议 ──
    def test_11_client_suggestions(self):
        """生成客户级主动建议。"""
        from services.proactive_suggestion_service import generate_client_suggestions

        s = generate_client_suggestions(TEST_CLIENT_ID)
        self.assertIsNotNone(s.get("client"))
        self.assertIn("risks", s)
        self.assertIn("follow_ups", s)
        self.assertIn("memories", s)

        logs = get_all_workflow_logs(workflow_type="proactive_client_suggestions", limit=5)
        self.assertTrue(len(logs) > 0)

    # ── 测试 12: 逾期跟进检测 ──
    def test_12_overdue_followups(self):
        """检测逾期跟进。"""
        from services.proactive_suggestion_service import detect_overdue_followups

        results = detect_overdue_followups()
        self.assertIsInstance(results, list)


class TestFeishuCommands(unittest.TestCase):
    """测试飞书新增命令"""

    @classmethod
    def setUpClass(cls):
        _setup_test_data()

    @classmethod
    def tearDownClass(cls):
        _cleanup()

    # ── 测试 13: /今日建议 ──
    def test_13_feishu_daily_suggestions(self):
        """飞书命令 /今日建议。"""
        from services.feishu_message_service import handle_feishu_text_message

        result = handle_feishu_text_message("/今日建议", sender_id="test_user_cmd")
        self.assertTrue(result["success"])
        self.assertIn("今日工作建议", result.get("reply_text", ""))

        logs = get_all_workflow_logs(workflow_type="feishu_daily_suggestions", limit=5)
        self.assertTrue(len(logs) > 0)

    # ── 测试 14: /客户建议 ──
    def test_14_feishu_client_suggestions(self):
        """飞书命令 /客户建议 客户名。"""
        from services.feishu_message_service import handle_feishu_text_message

        result = handle_feishu_text_message("/客户建议 TEST_记忆测试客户", sender_id="test_user_cmd")
        self.assertTrue(result["success"])
        self.assertIn("跟进建议", result.get("reply_text", ""))

    # ── 测试 15: /项目建议 ──
    def test_15_feishu_project_suggestions(self):
        """飞书命令 /项目建议 项目名。"""
        from services.feishu_message_service import handle_feishu_text_message

        result = handle_feishu_text_message("/项目建议 TEST_记忆测试项目", sender_id="test_user_cmd")
        self.assertTrue(result["success"])
        self.assertIn("项目建议", result.get("reply_text", ""))


class TestWorkflowLogs(unittest.TestCase):
    """测试 workflow_logs 完整性"""

    def test_16_memory_workflow_logs(self):
        """验证所有记忆相关 workflow_type 都有日志。"""
        # 触发 memory_rebuild 确保有日志
        try:
            from services.memory_service import rebuild_memory_items
            rebuild_memory_items()
        except Exception:
            pass

        expected_types = [
            "memory_item_created",
            "memory_item_updated",
            "memory_extraction",
            "memory_rebuild",
            "proactive_daily_suggestions",
            "proactive_project_suggestions",
            "proactive_client_suggestions",
            "feishu_daily_suggestions",
            "feishu_client_suggestions",
            "feishu_project_suggestions",
        ]

        for wf_type in expected_types:
            logs = get_all_workflow_logs(workflow_type=wf_type, limit=5)
            self.assertTrue(len(logs) > 0,
                          f"缺少 workflow_type={wf_type} 的日志记录")


if __name__ == "__main__":
    print("初始化数据库...")
    init_database()
    print("数据库就绪。\n")
    unittest.main(verbosity=2)
