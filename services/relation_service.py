"""
关系网络服务 — 管理实体之间的 belongs_to / related_to / mentioned_in 等关系。
"""
from database.db import insert, fetch_all, fetch_one, execute
from utils.date_utils import now_str


def add_relation(source_type, source_id, target_type, target_id,
                 relation_type="related_to", description=None):
    """创建关系（幂等 — 相同关系不重复创建）。"""
    existing = fetch_one(
        """SELECT id FROM relations
           WHERE source_type=? AND source_id=? AND target_type=? AND target_id=? AND relation_type=?""",
        (source_type, source_id, target_type, target_id, relation_type),
    )
    if existing:
        return existing["id"]

    return insert(
        """INSERT INTO relations (source_type, source_id, target_type, target_id, relation_type, description, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (source_type, source_id, target_type, target_id, relation_type, description, now_str()),
    )


def get_relations(entity_type, entity_id):
    """获取实体的所有关系（出向 + 入向）。"""
    return fetch_all(
        """SELECT * FROM relations
           WHERE (source_type=? AND source_id=?)
              OR (target_type=? AND target_id=?)
           ORDER BY created_at DESC""",
        (entity_type, entity_id, entity_type, entity_id),
    )


def delete_relation(relation_id):
    """删除关系。"""
    execute("DELETE FROM relations WHERE id = ?", (relation_id,))


def delete_relations_for(entity_type, entity_id):
    """删除实体的所有关系（删除实体时调用）。"""
    execute(
        "DELETE FROM relations WHERE (source_type=? AND source_id=?) OR (target_type=? AND target_id=?)",
        (entity_type, entity_id, entity_type, entity_id),
    )


def get_related_entities(entity_type, entity_id):
    """获取与某个实体关联的所有其他实体数据。

    返回按类型分组的字典:
    {"clients": [...], "projects": [...], "tasks": [...], "files": [...], "events": [...]}
    """
    relations = get_relations(entity_type, entity_id)
    if not relations:
        return {"clients": [], "projects": [], "tasks": [], "files": [], "events": []}

    # 按目标类型收集ID
    type_ids = {}
    for r in relations:
        # 确定"对方"的类型和ID
        if r["source_type"] == entity_type and r["source_id"] == entity_id:
            other_type = r["target_type"]
            other_id = r["target_id"]
        else:
            other_type = r["source_type"]
            other_id = r["source_id"]

        if other_type not in type_ids:
            type_ids[other_type] = set()
        type_ids[other_type].add(other_id)

    return _fetch_entities(type_ids)


def get_relation_network(entity_type, entity_id):
    """构建实体的完整关系网络视图。

    返回:
    {
        "entity": {...},           # 实体自身数据
        "clients": [...],          # 关联的客户
        "projects": [...],         # 关联的项目
        "tasks": [...],            # 关联的任务
        "files": [...],            # 关联的文件
        "events": [...],           # 关联的时间轴事件
        "relations": [...],        # 原始关系记录（含 relation_type 和 description）
    }
    """
    entity = _fetch_entity(entity_type, entity_id)
    relations = get_relations(entity_type, entity_id)

    type_ids = {}
    for r in relations:
        if r["source_type"] == entity_type and r["source_id"] == entity_id:
            other_type = r["target_type"]
            other_id = r["target_id"]
        else:
            other_type = r["source_type"]
            other_id = r["source_id"]

        if other_type not in type_ids:
            type_ids[other_type] = set()
        type_ids[other_type].add(other_id)

    result = {
        "entity": entity,
        "clients": [],
        "projects": [],
        "tasks": [],
        "files": [],
        "events": [],
        "relations": relations,
    }

    entities = _fetch_entities(type_ids)
    result.update(entities)

    return result


_PLURAL_TO_SINGULAR = {
    "clients": "client",
    "projects": "project",
    "tasks": "task",
    "files": "file",
    "events": "event",
}


def expand_search_results(results):
    """对 global_search 的结果进行关系扩展。

    为每个找到的实体查找其关联实体，合并到结果中。
    返回扩展后的 results 字典。
    """
    expanded = {
        "clients": list(results.get("clients", [])),
        "projects": list(results.get("projects", [])),
        "tasks": list(results.get("tasks", [])),
        "files": list(results.get("files", [])),
        "events": list(results.get("events", [])),
        "notes": list(results.get("notes", [])),
        "summaries": list(results.get("summaries", [])),
    }

    seen = _build_seen_index(expanded)

    for entity_type, items in results.items():
        if entity_type in ("notes", "summaries"):
            continue
        singular_type = _PLURAL_TO_SINGULAR.get(entity_type, entity_type)
        for item in items:
            item_id = item.get("id")
            if not item_id:
                continue
            related = get_related_entities(singular_type, item_id)
            for rtype, ritems in related.items():
                for ri in ritems:
                    key = f"{rtype}_{ri.get('id')}"
                    if key not in seen[rtype]:
                        seen[rtype].add(key)
                        expanded[rtype].append(ri)

    return expanded


def _build_seen_index(results):
    seen = {}
    for etype in ("clients", "projects", "tasks", "files", "events", "notes", "summaries"):
        seen[etype] = set()
        for item in results.get(etype, []):
            item_id = item.get("id")
            if item_id:
                seen[etype].add(f"{etype}_{item_id}")
    return seen


def _fetch_entity(entity_type, entity_id):
    """获取单个实体数据。"""
    table_map = {
        "client": "clients",
        "project": "projects",
        "task": "tasks",
        "file": "files",
        "event": "timeline_events",
    }
    table = table_map.get(entity_type)
    if not table:
        return None
    return fetch_one(f"SELECT * FROM {table} WHERE id = ?", (entity_id,))


def _fetch_entities(type_ids):
    """批量获取各类型实体数据。"""
    table_map = {
        "client": ("clients", "clients"),
        "project": ("projects", "projects"),
        "task": ("tasks", "tasks"),
        "file": ("files", "files"),
        "event": ("events", "timeline_events"),
    }

    result = {"clients": [], "projects": [], "tasks": [], "files": [], "events": []}

    for type_key, (result_key, table) in table_map.items():
        ids = type_ids.get(type_key, set())
        if not ids:
            continue
        placeholders = ",".join(["?" for _ in ids])
        rows = fetch_all(
            f"SELECT * FROM {table} WHERE id IN ({placeholders})",
            tuple(ids),
        )
        for row in rows:
            row["_type"] = type_key
        result[result_key] = rows

    return result


def count_orphan_relations() -> int:
    """统计 source 或 target 实体已不存在的孤儿 relation 数量。"""
    row = fetch_one("""
        SELECT COUNT(*) as cnt FROM relations r
        WHERE NOT (
            (r.source_type = 'client' AND r.source_id IN (SELECT id FROM clients))
            OR (r.source_type = 'project' AND r.source_id IN (SELECT id FROM projects))
            OR (r.source_type = 'task' AND r.source_id IN (SELECT id FROM tasks))
            OR (r.source_type = 'file' AND r.source_id IN (SELECT id FROM files))
            OR (r.source_type = 'event' AND r.source_id IN (SELECT id FROM timeline_events))
        )
        OR NOT (
            (r.target_type = 'client' AND r.target_id IN (SELECT id FROM clients))
            OR (r.target_type = 'project' AND r.target_id IN (SELECT id FROM projects))
            OR (r.target_type = 'task' AND r.target_id IN (SELECT id FROM tasks))
            OR (r.target_type = 'file' AND r.target_id IN (SELECT id FROM files))
            OR (r.target_type = 'event' AND r.target_id IN (SELECT id FROM timeline_events))
        )
    """)
    return row["cnt"] if row else 0


def cleanup_orphan_relations() -> int:
    """删除 source 或 target 实体已不存在的孤儿 relations。

    Returns:
        删除的 relations 数量。
    """
    before = count_orphan_relations()
    if before > 0:
        execute("""
            DELETE FROM relations WHERE id IN (
                SELECT r.id FROM relations r
                WHERE NOT (
                    (r.source_type = 'client' AND r.source_id IN (SELECT id FROM clients))
                    OR (r.source_type = 'project' AND r.source_id IN (SELECT id FROM projects))
                    OR (r.source_type = 'task' AND r.source_id IN (SELECT id FROM tasks))
                    OR (r.source_type = 'file' AND r.source_id IN (SELECT id FROM files))
                    OR (r.source_type = 'event' AND r.source_id IN (SELECT id FROM timeline_events))
                )
                OR NOT (
                    (r.target_type = 'client' AND r.target_id IN (SELECT id FROM clients))
                    OR (r.target_type = 'project' AND r.target_id IN (SELECT id FROM projects))
                    OR (r.target_type = 'task' AND r.target_id IN (SELECT id FROM tasks))
                    OR (r.target_type = 'file' AND r.target_id IN (SELECT id FROM files))
                    OR (r.target_type = 'event' AND r.target_id IN (SELECT id FROM timeline_events))
                )
            )
        """)
    return before


# ── 关系图谱增强 ──

VALID_RELATION_TYPES = {
    "belongs_to", "related_to", "depends_on", "blocks", "caused_by",
    "mentioned_in", "created_from", "follow_up_required", "risk_related",
}

RELATION_TYPE_LABELS = {
    "belongs_to": "归属",
    "related_to": "关联",
    "depends_on": "依赖",
    "blocks": "阻塞",
    "caused_by": "由...引起",
    "mentioned_in": "提及于",
    "created_from": "创建自",
    "follow_up_required": "需跟进",
    "risk_related": "风险相关",
}


def add_semantic_relation(source_type: str, source_id: int,
                          target_type: str, target_id: int,
                          relation_type: str = "related_to",
                          description: str = None) -> int:
    """创建语义关系。relation_type 必须是预定义类型之一。"""
    if relation_type not in VALID_RELATION_TYPES:
        relation_type = "related_to"
    return add_relation(source_type, source_id, target_type, target_id,
                       relation_type, description)


def get_entity_graph(entity_type: str, entity_id: int) -> dict:
    """获取实体的完整关系图谱，包含关系语义标签。

    Returns:
        {
            "entity": {...},
            "nodes": [{type, id, name, ...}],
            "edges": [{source_type, source_id, target_type, target_id, relation_type, label}],
            "risks": [...],
            "follow_ups": [...],
        }
    """
    relations = get_relations(entity_type, entity_id)
    nodes = {}
    edges = []
    risks = []
    follow_ups = []

    # 收集节点
    entity = _fetch_entity(entity_type, entity_id)
    if entity:
        entity["_type"] = entity_type
        nodes[f"{entity_type}_{entity_id}"] = {
            "type": entity_type, "id": entity_id,
            "name": _get_entity_name(entity),
        }

    for r in relations:
        rel_type = r["relation_type"]
        label = RELATION_TYPE_LABELS.get(rel_type, rel_type)

        src_key = f"{r['source_type']}_{r['source_id']}"
        tgt_key = f"{r['target_type']}_{r['target_id']}"

        # 添加节点
        if src_key not in nodes:
            node = _fetch_entity(r["source_type"], r["source_id"])
            if node:
                node["_type"] = r["source_type"]
                nodes[src_key] = {
                    "type": r["source_type"], "id": r["source_id"],
                    "name": _get_entity_name(node),
                }

        if tgt_key not in nodes:
            node = _fetch_entity(r["target_type"], r["target_id"])
            if node:
                node["_type"] = r["target_type"]
                nodes[tgt_key] = {
                    "type": r["target_type"], "id": r["target_id"],
                    "name": _get_entity_name(node),
                }

        edge = {
            "source_type": r["source_type"], "source_id": r["source_id"],
            "target_type": r["target_type"], "target_id": r["target_id"],
            "relation_type": rel_type, "label": label,
            "description": r.get("description", ""),
        }
        edges.append(edge)

        if rel_type == "risk_related":
            risks.append(edge)
        if rel_type == "follow_up_required":
            follow_ups.append(edge)

    return {
        "entity": entity,
        "nodes": list(nodes.values()),
        "edges": edges,
        "risks": risks,
        "follow_ups": follow_ups,
    }


def get_client_graph(client_id: int) -> dict:
    """获取客户的完整关系图谱，向下遍历项目/任务/文件。"""
    graph = get_entity_graph("client", client_id)

    # 扩展：找到关联项目，再找项目的任务和风险
    related = get_related_entities("client", client_id)
    all_risks = list(graph.get("risks", []))
    all_follow_ups = list(graph.get("follow_ups", []))

    for p in related.get("projects", []):
        p_graph = get_entity_graph("project", p["id"])
        all_risks.extend(p_graph.get("risks", []))
        all_follow_ups.extend(p_graph.get("follow_ups", []))
        # 合并节点
        for node in p_graph.get("nodes", []):
            key = f"{node['type']}_{node['id']}"
            if key not in {f"{n['type']}_{n['id']}" for n in graph["nodes"]}:
                graph["nodes"].append(node)
        for edge in p_graph.get("edges", []):
            if edge not in graph["edges"]:
                graph["edges"].append(edge)

    graph["risks"] = all_risks
    graph["follow_ups"] = all_follow_ups

    # 添加客户长期记忆
    try:
        from services.memory_service import get_memory_by_client
        memories = get_memory_by_client(client_id, limit=20)
        graph["memories"] = memories
        # 风险记忆
        risk_memories = [m for m in memories if m["memory_type"] in ("project_risk", "task_blocker")]
        graph["risk_memories"] = risk_memories
    except Exception:
        graph["memories"] = []
        graph["risk_memories"] = []

    return graph


def get_project_graph(project_id: int) -> dict:
    """获取项目的完整关系图谱，包含风险关系和跟进关系。"""
    graph = get_entity_graph("project", project_id)

    try:
        from services.memory_service import get_memory_by_project
        memories = get_memory_by_project(project_id, limit=20)
        graph["memories"] = memories
        risk_memories = [m for m in memories if m["memory_type"] in ("project_risk", "task_blocker")]
        graph["risk_memories"] = risk_memories
    except Exception:
        graph["memories"] = []
        graph["risk_memories"] = []

    return graph


def find_risk_relations() -> list:
    """查找所有风险相关的关系。"""
    return fetch_all(
        """SELECT r.*,
                  COALESCE(
                    (SELECT name FROM projects WHERE id = r.source_id AND r.source_type = 'project'),
                    (SELECT name FROM projects WHERE id = r.target_id AND r.target_type = 'project'),
                    (SELECT title FROM tasks WHERE id = r.source_id AND r.source_type = 'task'),
                    (SELECT title FROM tasks WHERE id = r.target_id AND r.target_type = 'task'),
                    ''
                  ) as entity_name
           FROM relations r
           WHERE r.relation_type = 'risk_related'
           ORDER BY r.created_at DESC"""
    )


def find_follow_up_relations() -> list:
    """查找所有需跟进的关系。"""
    return fetch_all(
        """SELECT r.*,
                  COALESCE(
                    (SELECT name FROM clients WHERE id = r.target_id AND r.target_type = 'client'),
                    (SELECT name FROM projects WHERE id = r.target_id AND r.target_type = 'project'),
                    (SELECT title FROM tasks WHERE id = r.target_id AND r.target_type = 'task'),
                    ''
                  ) as entity_name
           FROM relations r
           WHERE r.relation_type = 'follow_up_required'
           ORDER BY r.created_at DESC"""
    )


def find_entity_risks(entity_type: str, entity_id: int) -> list:
    """查找某实体的所有风险关系。"""
    return fetch_all(
        """SELECT * FROM relations
           WHERE relation_type = 'risk_related'
           AND ((source_type = ? AND source_id = ?) OR (target_type = ? AND target_id = ?))
           ORDER BY created_at DESC""",
        (entity_type, entity_id, entity_type, entity_id),
    )


def find_entity_follow_ups(entity_type: str, entity_id: int) -> list:
    """查找某实体的所有跟进关系。"""
    return fetch_all(
        """SELECT * FROM relations
           WHERE relation_type = 'follow_up_required'
           AND ((source_type = ? AND source_id = ?) OR (target_type = ? AND target_id = ?))
           ORDER BY created_at DESC""",
        (entity_type, entity_id, entity_type, entity_id),
    )


def _get_entity_name(entity: dict) -> str:
    """从实体 dict 中提取名称/标题。"""
    return (entity.get("name") or entity.get("title") or
            entity.get("filename") or str(entity.get("id", "")))
