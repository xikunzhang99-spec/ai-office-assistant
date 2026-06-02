import os
from database.db import get_connection


SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

MIGRATIONS = [
    "ALTER TABLE files ADD COLUMN key_points TEXT",
    "ALTER TABLE files ADD COLUMN suggestions TEXT",
    "ALTER TABLE timeline_events ADD COLUMN project_id INTEGER",
    "ALTER TABLE timeline_events ADD COLUMN client_id INTEGER",
    "ALTER TABLE timeline_events ADD COLUMN tags TEXT",
    "ALTER TABLE timeline_events ADD COLUMN metadata TEXT",
    "ALTER TABLE projects ADD COLUMN client_id INTEGER",
    """CREATE TABLE IF NOT EXISTS relations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type TEXT NOT NULL,
        source_id INTEGER NOT NULL,
        target_type TEXT NOT NULL,
        target_id INTEGER NOT NULL,
        relation_type TEXT NOT NULL DEFAULT 'related_to',
        description TEXT,
        created_at TEXT
    )""",
    "ALTER TABLE relations ADD COLUMN description TEXT",
    """CREATE TABLE IF NOT EXISTS knowledge_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type TEXT NOT NULL,
        source_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        content TEXT,
        tags TEXT,
        project_id INTEGER,
        client_id INTEGER,
        task_id INTEGER,
        created_at TEXT,
        updated_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS knowledge_embeddings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        knowledge_item_id INTEGER NOT NULL UNIQUE,
        embedding_model TEXT NOT NULL,
        embedding TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS workflow_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workflow_type TEXT NOT NULL,
        source_type TEXT,
        source_id INTEGER,
        status TEXT NOT NULL DEFAULT 'pending',
        message TEXT,
        details TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS obsidian_sync_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type TEXT NOT NULL,
        source_id INTEGER NOT NULL,
        obsidian_path TEXT NOT NULL,
        sync_status TEXT DEFAULT 'success',
        content_hash TEXT,
        last_synced_at TEXT DEFAULT CURRENT_TIMESTAMP,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(source_type, source_id)
    )""",
    """CREATE TABLE IF NOT EXISTS processed_feishu_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT UNIQUE,
        message_id TEXT,
        open_id TEXT,
        chat_id TEXT,
        message_text TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""",
    "ALTER TABLE files ADD COLUMN file_hash TEXT",
    """CREATE TABLE IF NOT EXISTS feishu_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_key TEXT NOT NULL UNIQUE,
        chat_id TEXT,
        open_id TEXT,
        current_mode TEXT DEFAULT 'idle',
        last_file_id INTEGER,
        last_analysis_json TEXT,
        pending_actions_json TEXT,
        last_question TEXT,
        last_answer TEXT,
        status TEXT DEFAULT 'active',
        expires_at TEXT,
        created_at TEXT,
        updated_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS memory_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_type TEXT NOT NULL,
        source_type TEXT,
        source_id INTEGER,
        title TEXT NOT NULL,
        content TEXT,
        importance TEXT DEFAULT 'medium',
        client_id INTEGER,
        project_id INTEGER,
        task_id INTEGER,
        created_at TEXT,
        updated_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS project_stages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        stage_name TEXT NOT NULL,
        stage_order INTEGER NOT NULL,
        status TEXT DEFAULT 'active',
        started_at TEXT,
        completed_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS workflow_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_name TEXT NOT NULL,
        template_type TEXT NOT NULL,
        description TEXT,
        template_json TEXT NOT NULL,
        created_at TEXT
    )""",
    # Workflow Agent v2: Run/Step tracking
    """CREATE TABLE IF NOT EXISTS workflow_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workflow_type TEXT NOT NULL,
        source_type TEXT,
        source_id INTEGER,
        status TEXT NOT NULL DEFAULT 'running',
        trigger_info TEXT,
        preview_json TEXT,
        final_result_json TEXT,
        error_step_name TEXT,
        error_message TEXT,
        started_at TEXT,
        completed_at TEXT,
        created_at TEXT,
        updated_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS workflow_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        step_name TEXT NOT NULL,
        step_order INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        input_summary TEXT,
        output_summary TEXT,
        error_message TEXT,
        started_at TEXT,
        completed_at TEXT,
        created_at TEXT,
        UNIQUE(run_id, step_name)
    )""",
    "ALTER TABLE workflow_logs ADD COLUMN run_id INTEGER",
    "ALTER TABLE workflow_logs ADD COLUMN step_id INTEGER",
    # Phase 4: RAG chunk-level knowledge
    "ALTER TABLE knowledge_chunks ADD COLUMN embedding TEXT",
    """CREATE TABLE IF NOT EXISTS knowledge_chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type TEXT NOT NULL,
        source_id INTEGER NOT NULL,
        source_title TEXT NOT NULL,
        content TEXT NOT NULL,
        chunk_index INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT,
        created_at TEXT,
        updated_at TEXT
    )""",
]


def init_database():
    conn = get_connection()
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)
        conn.commit()

        for sql in MIGRATIONS:
            try:
                conn.execute(sql)
                conn.commit()
            except Exception:
                pass
    finally:
        conn.close()
