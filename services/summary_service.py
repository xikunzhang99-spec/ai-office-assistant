from database.db import insert, fetch_one, fetch_all, execute
from services.timeline_service import add_event, get_events_by_date
from services.task_service import get_tasks_by_date
from services.file_service import get_files_by_date
from services.ai_service import generate_daily_summary as ai_summary
from services.markdown_service import generate_daily_summary_markdown
from services.obsidian_service import write_daily_note, is_configured
from utils.date_utils import now_str, today_str


def create_daily_note(content: str, note_date: str = None) -> int:
    date_str = note_date or today_str()
    note_id = insert(
        "INSERT INTO daily_notes (content, note_date, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (content, date_str, now_str(), now_str()),
    )
    add_event("daily_note", f"随手记: {content[:50]}...", content, "daily_note", note_id, date_str)
    return note_id


def get_notes_by_date(date_str: str) -> list:
    return fetch_all("SELECT * FROM daily_notes WHERE note_date = ? ORDER BY created_at DESC", (date_str,))


def get_today_notes() -> list:
    return get_notes_by_date(today_str())


def generate_summary(date_str: str = None) -> dict:
    date_str = date_str or today_str()
    tasks = get_tasks_by_date(date_str)
    completed = [t["title"] for t in tasks if t["status"] == "done"]
    new_tasks = [t["title"] for t in tasks if t["status"] != "done"]
    notes = [n["content"] for n in get_notes_by_date(date_str)]

    files = get_files_by_date(date_str)
    files_list = [f["filename"] for f in files]

    events = get_events_by_date(date_str)
    events_list = [f"[{e['event_type']}] {e['title']}" for e in events]

    summary_content = ai_summary(date_str, completed, new_tasks, files_list, notes, events_list)

    existing = fetch_one("SELECT * FROM daily_summaries WHERE summary_date = ?", (date_str,))
    if existing:
        execute(
            "UPDATE daily_summaries SET content = ?, updated_at = ? WHERE summary_date = ?",
            (summary_content, now_str(), date_str),
        )
        summary_id = existing["id"]
    else:
        summary_id = insert(
            "INSERT INTO daily_summaries (summary_date, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (date_str, summary_content, now_str(), now_str()),
        )

    markdown = generate_daily_summary_markdown(date_str, summary_content)
    markdown_path = ""
    if is_configured():
        markdown_path = write_daily_note(date_str, markdown)
        execute("UPDATE daily_summaries SET markdown_path = ? WHERE id = ?", (markdown_path, summary_id))
        add_event("daily_summary_written_to_obsidian", f"总结写入Obsidian: {date_str}",
                  markdown_path, "daily_summary", summary_id, event_date=date_str)

    add_event("daily_summary", f"生成每日总结: {date_str}", "", "daily_summary", summary_id, date_str)
    return {"id": summary_id, "content": summary_content, "markdown_path": markdown_path}


def get_summary_by_date(date_str: str):
    return fetch_one("SELECT * FROM daily_summaries WHERE summary_date = ?", (date_str,))


def get_all_summaries(limit: int = 30) -> list:
    return fetch_all("SELECT * FROM daily_summaries ORDER BY summary_date DESC LIMIT ?", (limit,))


def get_summary(summary_id: int):
    return fetch_one("SELECT * FROM daily_summaries WHERE id = ?", (summary_id,))


def delete_summary(summary_id: int) -> bool:
    summary = get_summary(summary_id)
    if summary:
        add_event("daily_summary_deleted", f"删除总结: {summary['summary_date']}", "", "daily_summary", summary_id)
    execute("DELETE FROM daily_summaries WHERE id = ?", (summary_id,))
    return True


def delete_note(note_id: int) -> bool:
    note = fetch_one("SELECT * FROM daily_notes WHERE id = ?", (note_id,))
    if note:
        add_event("daily_note_deleted", f"删除随手记: {note['content'][:50]}...", "", "daily_note", note_id)
    execute("DELETE FROM daily_notes WHERE id = ?", (note_id,))
    return True


def search_notes(keyword: str = None, start_date: str = None, end_date: str = None, limit: int = 100) -> list:
    conditions = []
    params = []
    if keyword:
        conditions.append("content LIKE ?")
        params.append(f"%{keyword}%")
    if start_date:
        conditions.append("note_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("note_date <= ?")
        params.append(end_date)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM daily_notes {where} ORDER BY note_date DESC, created_at DESC LIMIT ?"
    params.append(limit)
    return fetch_all(sql, tuple(params))
