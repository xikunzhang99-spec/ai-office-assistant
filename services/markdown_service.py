def generate_file_markdown(filename: str, file_type: str, upload_time: str, tags: str, summary: str, key_points: list, suggestions: list) -> str:
    key_points_md = "\n".join([f"- {p}" for p in key_points]) if key_points else "-"
    suggestions_md = "\n".join([f"- {s}" for s in suggestions]) if suggestions else "-"

    return f"""# {filename}

## 基本信息
- 文件名：{filename}
- 文件类型：{file_type}
- 上传时间：{upload_time}
- 标签：{tags}

## AI摘要
{summary}

## 关键内容
{key_points_md}

## 后续任务建议
{suggestions_md}
"""


def generate_daily_summary_markdown(date_str: str, content: str) -> str:
    return f"""# {date_str} 工作总结

{content}
"""


def generate_task_markdown(title: str, description: str, status: str, priority: str, due_date: str, tags: str) -> str:
    return f"""# {title}

- 状态：{status}
- 优先级：{priority}
- 截止日期：{due_date}
- 标签：{tags}

## 描述
{description or "无"}
"""
