"""
清空所有业务数据，保留数据库表结构。

用法: python scripts/reset_business_data.py

执行流程:
1. 检查 data/app.db 是否存在
2. 自动备份到 backup/
3. 逐表清空业务数据
4. 重置自增 ID
5. 输出清空结果
"""

import os
import sys
import shutil
import sqlite3
from datetime import datetime

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

# 业务数据表（按依赖顺序清空）
BUSINESS_TABLES = [
    "knowledge_embeddings",
    "knowledge_chunks",
    "knowledge_items",
    "memory_items",
    "relations",
    "project_stages",
    "workflow_steps",
    "workflow_runs",
    "workflow_logs",
    "workflow_templates",
    "timeline_events",
    "daily_notes",
    "daily_summaries",
    "files",
    "tasks",
    "projects",
    "clients",
    "tags",
    "obsidian_sync_logs",
    "processed_feishu_events",
    "feishu_sessions",
]


def main():
    print("=" * 50)
    print("清空业务数据脚本")
    print("=" * 50)

    # 1. 检查数据库文件
    if not os.path.exists(DATABASE_PATH):
        print(f"数据库文件不存在: {DATABASE_PATH}")
        print("无需清空。")
        return

    db_size_before = os.path.getsize(DATABASE_PATH)

    # 2. 自动备份
    backup_dir = os.path.join(PROJECT_ROOT, "backup")
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"app_before_reset_{timestamp}.db")
    shutil.copy2(DATABASE_PATH, backup_path)
    print(f"已备份: {backup_path}")

    # 3. 连接数据库
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")
    cursor = conn.cursor()

    # 4. 清空业务表
    print("\n开始清空业务数据...")
    deleted = {}
    skipped = {}

    for table in BUSINESS_TABLES:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            if count > 0:
                cursor.execute(f"DELETE FROM {table}")
                deleted[table] = count
            else:
                skipped[table] = 0
        except sqlite3.OperationalError:
            # 表不存在，跳过
            skipped[table] = None

    conn.commit()

    # 5. 重置自增 ID
    existing_tables = [t for t in BUSINESS_TABLES if t in deleted or t in skipped]
    if existing_tables:
        placeholders = ", ".join(["?" for _ in existing_tables])
        cursor.execute(
            f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})",
            existing_tables,
        )
        conn.commit()
        print("自增 ID 已重置。")

    # 6. 输出结果
    print("\n清空结果:")
    total_deleted = 0
    for table in BUSINESS_TABLES:
        count = deleted.get(table)
        if count is not None:
            print(f"  {table}: 已清空 {count} 条")
            total_deleted += count
        else:
            status = "不存在" if skipped.get(table) is None else "无数据"
            print(f"  {table}: {status}")

    print(f"\n共清空 {total_deleted} 条记录 ({len(deleted)} 张表)")

    # 7. 验证
    conn.close()

    # 重新初始化数据库结构
    print("\n重新初始化数据库结构...")
    from database.init_db import init_database
    init_database()
    print("数据库结构已确认。")

    if os.path.exists(DATABASE_PATH):
        db_size_after = os.path.getsize(DATABASE_PATH)
        print(f"\n数据库大小: {db_size_before/1024/1024:.1f}MB → {db_size_after/1024/1024:.1f}MB")
        print(f"备份文件: {backup_path}")

    print("\n清空完成。可以重新录入数据了。")


if __name__ == "__main__":
    main()
