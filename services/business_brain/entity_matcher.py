"""
entity_matcher.py — 实体关联匹配。
将 AI 提取的实体名称与数据库中已有记录进行匹配。
"""
import re


def match_entities(extracted: dict, db_context: dict) -> dict:
    """将提取结果中的实体名称匹配到已有数据库记录。

    对 extracted dict 进行原地修改并返回。

    Args:
        extracted: extractor.extract_entities() 的输出
        db_context: {"clients": [...], "projects": [...], "tags": [...]}

    Returns:
        添加了 matched_* 字段的 enriched dict
    """
    db_clients = db_context.get("clients", [])
    db_projects = db_context.get("projects", [])
    db_tags = db_context.get("tags", [])

    entities = extracted.get("entities", {})

    # 匹配提取出的客户
    for client_ref in entities.get("clients", []):
        client_name = client_ref.get("name", "")
        if client_name:
            matched = _find_best_match(client_name, db_clients, "name")
            if matched:
                client_ref["matched_id"] = matched["id"]
                client_ref["matched_name"] = matched["name"]

    # 匹配提取出的项目
    for project_ref in entities.get("projects", []):
        project_name = project_ref.get("name", "")
        if project_name:
            matched = _find_best_match(project_name, db_projects, "name")
            if matched:
                project_ref["matched_id"] = matched["id"]
                project_ref["matched_name"] = matched["name"]
                # 如果项目关联了客户，也添加到 entities.clients
                if matched.get("client_id") and matched.get("client_name"):
                    project_ref["client_id"] = matched["client_id"]
                    existing_client_ids = {
                        c.get("matched_id") for c in entities.get("clients", [])
                    }
                    if matched["client_id"] not in existing_client_ids:
                        entities.setdefault("clients", []).append({
                            "name": matched["client_name"],
                            "matched_id": matched["client_id"],
                            "matched_name": matched["client_name"],
                        })

    # 匹配标签
    matched_tags = []
    new_tags = []
    for tag in extracted.get("tags", []):
        if _tag_exists(tag, db_tags):
            matched_tags.append(tag)
        else:
            new_tags.append(tag)

    extracted["matched_tags"] = matched_tags
    extracted["new_tags"] = new_tags

    return extracted


def _find_best_match(name: str, records: list, key: str = "name") -> dict | None:
    """查找最佳匹配记录。使用包含匹配（不区分大小写）。"""
    if not name or not records:
        return None

    name_lower = name.strip().lower()

    # 精确匹配（不区分大小写）
    for r in records:
        if (r.get(key, "") or "").strip().lower() == name_lower:
            return dict(r)

    # 包含匹配：record name 包含 search name（较短名称）
    for r in records:
        r_name = (r.get(key, "") or "").strip().lower()
        if name_lower in r_name or r_name in name_lower:
            return dict(r)

    return None


def _tag_exists(tag: str, db_tags: list) -> bool:
    """检查标签是否已存在于数据库中。"""
    tag_lower = tag.strip().lower()
    for t in db_tags:
        if (t.strip().lower() if isinstance(t, str) else "").lower() == tag_lower:
            return True
    return False
