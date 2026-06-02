"""
knowledge_ingestion.py — 知识入库服务。
从不同来源读取内容，切分成 chunks，保存到 knowledge_chunks 表 + Chroma 向量库。
"""
import os
import json
import re
from database.db import insert, execute, fetch_all
from utils.date_utils import now_str


def split_text_into_chunks(text: str, chunk_size: int = 600,
                           overlap: int = 120) -> list[str]:
    """将文本切分成有重叠的 chunks。

    切分规则：
    1. 先按段落边界（\\n\\n）切分
    2. 再按句子边界（。！？）切分
    3. 最后按字符数切分
    4. 相邻 chunk 保留 overlap 字符重叠
    """
    if not text or not text.strip():
        return []

    # Step 1: 按段落切分
    paragraphs = text.split("\n\n")
    raw_segments = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # 尝试按句子切分
        sentences = re.split(r'(?<=[。！？])\s*', para)
        current = ""
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if len(current) + len(sent) <= chunk_size:
                current += sent
            else:
                if current:
                    raw_segments.append(current)
                # 如果单个句子超过 chunk_size，按字符数强制切分
                if len(sent) > chunk_size:
                    for i in range(0, len(sent), chunk_size - overlap):
                        raw_segments.append(sent[i:i + chunk_size])
                else:
                    current = sent
        if current:
            raw_segments.append(current)

    # Step 2: 合并短段落，添加重叠
    chunks = []
    i = 0
    while i < len(raw_segments):
        chunk = raw_segments[i]
        # 如果当前 chunk 太短，尝试合并下一个
        while len(chunk) < chunk_size // 2 and i + 1 < len(raw_segments):
            i += 1
            chunk += raw_segments[i]

        # 添加前一个 chunk 的尾部作为重叠
        if chunks and overlap > 0:
            prev = chunks[-1]
            if len(prev) > overlap:
                overlap_text = prev[-overlap:]
                # 尝试在句子边界处开始重叠
                boundary = max(overlap_text.find("。"), overlap_text.find("！"), overlap_text.find("？"))
                if boundary > 0:
                    chunk = overlap_text[boundary + 1:] + chunk

        chunks.append(chunk)
        i += 1

    return chunks


# ── Ingestion Functions ──

def _clear_source_chunks(source_type: str, source_id: int):
    """删除某个来源的已有 chunks（SQLite + Chroma）。"""
    execute("DELETE FROM knowledge_chunks WHERE source_type = ? AND source_id = ?",
            (source_type, source_id))
    try:
        from services.embedding_service import delete_chroma_chunks
        delete_chroma_chunks(source_type, source_id)
    except Exception:
        pass


def _save_chunks(source_type: str, source_id: int, source_title: str,
                 chunks: list[str], metadata: dict = None) -> int:
    """保存 chunks 到 SQLite + Chroma。"""
    if not chunks:
        return 0

    # 先清除旧数据
    _clear_source_chunks(source_type, source_id)

    now = now_str()
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)
    total = 0

    # 准备批量数据
    chunk_records = []
    for idx, content in enumerate(chunks):
        chunk_id = insert(
            """INSERT INTO knowledge_chunks
               (source_type, source_id, source_title, content, chunk_index,
                metadata_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (source_type, source_id, source_title, content, idx,
             meta_json, now, now),
        )
        chunk_records.append({
            "chunk_id": chunk_id,
            "content": content,
            "metadata": dict(metadata or {}),
        })
        total += 1

    # 批量写入 Chroma
    try:
        from services.embedding_service import embed_and_store_batch
        embed_and_store_batch(chunk_records, source_type, source_title, source_id)
    except Exception as e:
        print(f"[knowledge_ingestion] Chroma batch store warning: {e}")

    return total


def ingest_single(source_type: str, source_id: int, title: str,
                  content: str, metadata: dict = None) -> int:
    """入库单条内容。"""
    if not content or not content.strip():
        return 0
    chunks = split_text_into_chunks(content)
    full_meta = dict(metadata or {})
    full_meta.update({
        "source_type": source_type,
        "source_title": title,
        "source_id": source_id,
    })
    return _save_chunks(source_type, source_id, title, chunks, full_meta)


def ingest_obsidian_notes() -> int:
    """从 Obsidian Vault 读取 Markdown 笔记并入库。"""
    from config.settings import OBSIDIAN_VAULT_PATH
    if not OBSIDIAN_VAULT_PATH or not os.path.isdir(OBSIDIAN_VAULT_PATH):
        print("[knowledge_ingestion] Obsidian vault not configured or not found")
        return 0

    total = 0
    for root, dirs, files in os.walk(OBSIDIAN_VAULT_PATH):
        # 跳过隐藏目录
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue

            if not content.strip():
                continue

            title = os.path.splitext(fname)[0]
            rel_path = os.path.relpath(fpath, OBSIDIAN_VAULT_PATH)

            # 使用文件路径作为 source_id 的哈希
            source_id = abs(hash(rel_path)) % (10 ** 9)

            metadata = {
                "obsidian_path": rel_path,
                "date": "",
                "tags": _extract_obsidian_tags(content),
            }

            count = ingest_single("obsidian_note", source_id, title, content, metadata)
            total += count

    print(f"[knowledge_ingestion] Obsidian: {total} chunks ingested")
    return total


def _extract_obsidian_tags(content: str) -> list[str]:
    """提取 Obsidian 笔记中的标签（#tag 或 frontmatter tags）。"""
    tags = []
    # frontmatter tags
    fm_match = re.search(r'^tags:\s*\[(.*?)\]', content, re.MULTILINE)
    if fm_match:
        tags.extend([t.strip().strip('"\'') for t in fm_match.group(1).split(",")])
    # inline #tags
    for m in re.finditer(r'(?<!\w)#([\w一-鿿-]+)', content):
        tags.append(m.group(1))
    return list(set(tags))[:20]


def ingest_projects_and_timeline() -> int:
    """从项目和时间轴记录入库。"""
    total = 0

    try:
        from services.project_service import get_all_projects
        projects = get_all_projects()
    except Exception:
        projects = []

    for proj in projects:
        proj_id = proj["id"]
        proj_name = proj.get("name", "")
        proj_desc = proj.get("description", "") or ""

        # 项目基本信息
        proj_content = f"项目名称: {proj_name}\n状态: {proj.get('status', '')}\n描述: {proj_desc}"
        metadata = {
            "project_id": proj_id,
            "project_name": proj_name,
            "date": proj.get("created_at", ""),
            "tags": [],
        }
        count = ingest_single("project", proj_id, proj_name, proj_desc or proj_name, metadata)
        total += count

        # 项目的时间轴事件
        try:
            from database.db import fetch_all
            events = fetch_all(
                """SELECT * FROM timeline_events WHERE project_id = ?
                   ORDER BY event_date DESC LIMIT 50""",
                (proj_id,),
            )
            events_text = ""
            for ev in events:
                ev_date = ev.get("event_date", "") or ev.get("created_at", "")
                events_text += f"[{ev_date[:10]}] {ev.get('event_type', '')}: {ev.get('title', '')}"
                if ev.get("description"):
                    events_text += f" — {ev['description'][:200]}"
                events_text += "\n"

            if events_text.strip():
                ev_metadata = {
                    "project_id": proj_id,
                    "project_name": proj_name,
                    "date": proj.get("created_at", ""),
                    "tags": [],
                }
                count = ingest_single("project_timeline", proj_id,
                                      f"{proj_name} - 时间轴", events_text, ev_metadata)
                total += count
        except Exception:
            pass

    print(f"[knowledge_ingestion] Projects+Timeline: {total} chunks ingested")
    return total


def ingest_daily_summaries() -> int:
    """从每日总结入库。"""
    total = 0
    try:
        from database.db import fetch_all
        summaries = fetch_all(
            "SELECT * FROM daily_summaries ORDER BY summary_date DESC LIMIT 100"
        )
    except Exception:
        summaries = []

    for s in summaries:
        content = s.get("content", "")
        if not content or not content.strip():
            continue
        date_str = s.get("summary_date", "")
        title = f"每日总结 - {date_str}"
        metadata = {
            "date": date_str,
            "tags": ["每日总结"],
        }
        count = ingest_single("daily_summary", s["id"], title, content, metadata)
        total += count

    # 也入库随手记
    try:
        from database.db import fetch_all
        notes = fetch_all("SELECT * FROM daily_notes ORDER BY note_date DESC LIMIT 200")
        for n in notes:
            content = n.get("content", "")
            if not content or not content.strip():
                continue
            date_str = n.get("note_date", "")
            title = f"随手记 - {date_str}"
            metadata = {"date": date_str, "tags": ["随手记"]}
            count = ingest_single("daily_note", n["id"], title, content, metadata)
            total += count
    except Exception:
        pass

    print(f"[knowledge_ingestion] Summaries+Notes: {total} chunks ingested")
    return total


def ingest_all() -> dict:
    """全量入库所有来源。

    Returns:
        {"obsidian": int, "projects": int, "summaries": int, "total": int}
    """
    results = {
        "obsidian": ingest_obsidian_notes(),
        "projects": ingest_projects_and_timeline(),
        "summaries": ingest_daily_summaries(),
    }
    results["total"] = sum(results.values())
    print(f"[knowledge_ingestion] All done: {results}")
    return results


def clear_all_chunks() -> int:
    """清空所有 knowledge_chunks。"""
    row = execute("SELECT COUNT(*) as cnt FROM knowledge_chunks")
    from database.db import fetch_one
    result = fetch_one("SELECT COUNT(*) as cnt FROM knowledge_chunks")
    count = result["cnt"] if result else 0
    execute("DELETE FROM knowledge_chunks")
    try:
        from services.embedding_service import clear_chroma_collection
        clear_chroma_collection()
    except Exception:
        pass
    return count


def get_chunk_stats() -> dict:
    """获取知识块统计信息。"""
    from database.db import fetch_all
    rows = fetch_all(
        """SELECT source_type, COUNT(*) as cnt
           FROM knowledge_chunks GROUP BY source_type ORDER BY cnt DESC"""
    )
    by_type = {r["source_type"]: r["cnt"] for r in rows}
    total_row = fetch_all("SELECT COUNT(*) as cnt FROM knowledge_chunks")
    total = total_row[0]["cnt"] if total_row else 0
    return {"total": total, "by_type": by_type}
