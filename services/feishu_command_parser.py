"""
飞书命令解析器 — 第一版规则解析，解析 /新任务 /新项目 /新客户 命令。
"""
import re
from datetime import date, timedelta


# ── 时间词映射 ──
DATE_WORDS = {
    "今天": date.today().isoformat(),
    "明天": (date.today() + timedelta(days=1)).isoformat(),
    "后天": (date.today() + timedelta(days=2)).isoformat(),
    "本周": date.today().isoformat(),
    "下周": (date.today() + timedelta(weeks=1)).isoformat(),
}

PRIORITY_MAP = {
    "高": "high", "高优先级": "high", "high": "high",
    "中": "medium", "中优先级": "medium", "medium": "medium",
    "低": "low", "低优先级": "low", "low": "low",
}


def _extract_date(text: str) -> str:
    """从文本中提取日期。"""
    # 关键词
    for word, val in DATE_WORDS.items():
        if word in text:
            return val

    # YYYY-MM-DD 格式
    m = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    if m:
        return m.group(1)

    # MM-DD 格式（补全年份）
    m = re.search(r'(\d{2})-(\d{2})', text)
    if m:
        return f"{date.today().year}-{m.group(1)}-{m.group(2)}"

    return ""


def _extract_kv(text: str, key: str) -> str:
    """从文本中提取 关键词:值 格式。"""
    # 匹配 关键词:值 或 关键词：值（全角冒号）
    m = re.search(rf'{key}[:：]\s*([^\s]+)', text)
    if m:
        val = m.group(1)
        # 去除尾部标点
        val = re.sub(r'[，,。；;]$', '', val)
        return val
    return ""


def _remove_prefix_cmd(text: str) -> str:
    """去掉命令前缀 /新任务 /新项目 /新客户。"""
    text = re.sub(r'^/\S+\s*', '', text).strip()
    return text


def parse_create_task_command(text: str) -> dict:
    """解析 /新任务 命令。

    格式:
      /新任务 跟进客户合同延期
      /新任务 跟进客户合同延期 明天 高优先级
      /新任务 跟进客户合同延期 项目:AI办公助理 客户:张三公司 截止:2026-05-30 优先级:高

    Returns:
      {title, project_name, client_name, due_date, priority}
    """
    cleaned = _remove_prefix_cmd(text)
    if not cleaned:
        return {"title": "", "project_name": "", "client_name": "", "due_date": "", "priority": ""}

    # 提取关键词
    project_name = _extract_kv(cleaned, "项目")
    client_name = _extract_kv(cleaned, "客户")
    due_date_str = _extract_kv(cleaned, "截止")
    priority_str = _extract_kv(cleaned, "优先级")

    # 从 cleaned 中移除已匹配的 KV 对，剩余部分作为 title 基础
    title_base = cleaned
    for key in ["项目", "客户", "截止", "优先级"]:
        title_base = re.sub(rf'{key}[:：]\s*\S+', '', title_base).strip()

    # 如果没通过 KV 提取到日期和优先级，尝试从 title_base 末尾提取
    if not due_date_str:
        # 检查末尾的时间词
        for word in DATE_WORDS:
            if title_base.endswith(word):
                due_date_str = word
                title_base = title_base[:-len(word)].strip()
                break

    if not priority_str:
        # 检查末尾的优先级词
        for label in ["高优先级", "高", "中优先级", "中", "低优先级", "低"]:
            if title_base.endswith(label):
                priority_str = label
                title_base = title_base[:-len(label)].strip()
                break

    # 清理剩余的标点
    title = title_base.rstrip("，,。；; ")

    # 解析日期
    due_date = _extract_date(due_date_str) if due_date_str else ""

    # 解析优先级
    priority = PRIORITY_MAP.get(priority_str, "")

    return {
        "title": title,
        "project_name": project_name,
        "client_name": client_name,
        "due_date": due_date,
        "priority": priority,
    }


def parse_create_project_command(text: str) -> dict:
    """解析 /新项目 命令。

    格式:
      /新项目 AI办公助理二期
      /新项目 AI办公助理二期 客户:张三公司 状态:进行中

    Returns:
      {name, client_name, status}
    """
    cleaned = _remove_prefix_cmd(text)
    if not cleaned:
        return {"name": "", "client_name": "", "status": ""}

    client_name = _extract_kv(cleaned, "客户")
    status_str = _extract_kv(cleaned, "状态")

    # 提取项目名称（去掉 KV 对后的剩余部分）
    name_base = cleaned
    for key in ["客户", "状态"]:
        name_base = re.sub(rf'{key}[:：]\s*\S+', '', name_base).strip()

    name = name_base.rstrip("，,。；; ")

    # 状态映射
    status_map = {"进行中": "active", "active": "active", "已完成": "completed",
                  "completed": "completed", "已归档": "archived", "archived": "archived"}
    status = status_map.get(status_str, "active")

    return {
        "name": name,
        "client_name": client_name,
        "status": status,
    }


def parse_create_client_command(text: str) -> dict:
    """解析 /新客户 命令。

    格式:
      /新客户 张三公司
      /新客户 张三公司 联系人:张总 电话:138xxxx 备注:重点客户

    Returns:
      {name, contact_person, phone, notes}
    """
    cleaned = _remove_prefix_cmd(text)
    if not cleaned:
        return {"name": "", "contact_person": "", "phone": "", "notes": ""}

    contact_person = _extract_kv(cleaned, "联系人")
    phone = _extract_kv(cleaned, "电话")
    notes = _extract_kv(cleaned, "备注")

    # 提取客户名称
    name_base = cleaned
    for key in ["联系人", "电话", "备注"]:
        name_base = re.sub(rf'{key}[:：]\s*\S+', '', name_base).strip()

    name = name_base.rstrip("，,。；; ")

    # 构建 contact_info
    info_parts = []
    if contact_person:
        info_parts.append(f"联系人: {contact_person}")
    if phone:
        info_parts.append(f"电话: {phone}")
    if notes:
        info_parts.append(f"备注: {notes}")

    return {
        "name": name,
        "contact_info": "; ".join(info_parts) if info_parts else "",
        "description": notes or "",
    }
