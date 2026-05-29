"""
Obsidian 同步日志服务 — 追踪每个实体的同步状态和内容哈希。
"""
from database.db import insert, fetch_one, fetch_all, execute
from utils.date_utils import now_str


def upsert_sync_log(source_type: str, source_id: int, obsidian_path: str,
                    content_hash: str = "", sync_status: str = "success") -> int:
    """记录或更新一条同步日志（幂等 — source_type+source_id 唯一）。

    Returns:
        日志记录 ID
    """
    existing = fetch_one(
        "SELECT id FROM obsidian_sync_logs WHERE source_type = ? AND source_id = ?",
        (source_type, source_id),
    )
    if existing:
        execute(
            """UPDATE obsidian_sync_logs
               SET obsidian_path = ?, sync_status = ?, content_hash = ?, last_synced_at = ?
               WHERE id = ?""",
            (obsidian_path, sync_status, content_hash, now_str(), existing["id"]),
        )
        return existing["id"]
    else:
        return insert(
            """INSERT INTO obsidian_sync_logs
               (source_type, source_id, obsidian_path, sync_status, content_hash, last_synced_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (source_type, source_id, obsidian_path, sync_status, content_hash, now_str(), now_str()),
        )


def get_sync_log(source_type: str, source_id: int) -> dict | None:
    """获取指定实体的同步日志。"""
    return fetch_one(
        "SELECT * FROM obsidian_sync_logs WHERE source_type = ? AND source_id = ?",
        (source_type, source_id),
    )


def get_all_sync_logs(limit: int = 100) -> list:
    """获取所有同步日志，按最近同步时间降序。"""
    return fetch_all(
        "SELECT * FROM obsidian_sync_logs ORDER BY last_synced_at DESC LIMIT ?",
        (limit,),
    )


def count_sync_logs() -> int:
    """获取同步日志总数。"""
    row = fetch_one("SELECT COUNT(*) as cnt FROM obsidian_sync_logs")
    return row["cnt"] if row else 0


def delete_sync_log(source_type: str, source_id: int):
    """删除指定实体的同步日志。"""
    execute(
        "DELETE FROM obsidian_sync_logs WHERE source_type = ? AND source_id = ?",
        (source_type, source_id),
    )
