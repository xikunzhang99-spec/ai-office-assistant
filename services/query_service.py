import json
import re
from datetime import date, timedelta
from services.ai_service import _chat
from services.timeline_service import search_events, add_event, EVENT_TYPE_LABELS
from services.project_service import get_all_projects, search_projects
from services.client_service import get_all_clients, search_clients
from services.task_service import search_tasks
from services.summary_service import search_notes
from services.search_service import global_search, build_context, search_files, search_summaries
from services.relation_service import expand_search_results
from utils.date_utils import today_str, now_str


def answer_question(question: str) -> dict:
    projects = get_all_projects()
    clients = get_all_clients()
    today = date.today()
    dates = _compute_reference_dates(today)

    parsed = _parse_question(question, projects, clients, dates)

    query_type = parsed.get("query_type", "general")
    results = _route_query(query_type, parsed, projects, clients)

    has_results = any(v for v in results.values())

    if not has_results:
        results = global_search(keyword=parsed.get("keyword", ""), limit=50)
        has_results = any(v for v in results.values())

    results_before_expand = {k: list(v) for k, v in results.items()}

    if has_results:
        results = expand_search_results(results)
        answer = _generate_answer(question, results, projects, clients, dates, query_type)
    else:
        answer = "没有找到相关数据，无法基于当前系统内容回答。请尝试调整查询范围或换个说法。"

    add_event("ai_query", question, answer[:200], event_date=today_str())

    return {
        "question": question,
        "answer": answer,
        "results": results,
        "results_before_expand": results_before_expand,
        "parsed_params": parsed,
    }


def _route_query(query_type: str, parsed: dict, projects: list, clients: list) -> dict:
    keyword = parsed.get("keyword")
    start_date = parsed.get("start_date")
    end_date = parsed.get("end_date")
    project_id = parsed.get("project_id")
    client_id = parsed.get("client_id")
    status = parsed.get("status")
    priority = parsed.get("priority")

    results = {
        "clients": [],
        "projects": [],
        "tasks": [],
        "files": [],
        "events": [],
        "notes": [],
        "summaries": [],
    }

    if query_type in ("client", "general"):
        results["clients"] = search_clients(keyword=keyword)

    if query_type in ("project", "general"):
        results["projects"] = search_projects(keyword=keyword, status=status)

    if query_type in ("task", "general"):
        results["tasks"] = search_tasks(
            keyword=keyword, status=status, project_id=project_id,
            client_id=client_id, priority=priority,
            start_date=start_date, end_date=end_date,
        )

    if query_type in ("file", "general"):
        results["files"] = search_files(
            keyword=keyword, project_id=project_id, client_id=client_id,
        )

    if query_type in ("event", "timeline", "summary", "general"):
        results["events"] = search_events(
            start_date=start_date, end_date=end_date,
            event_type=parsed.get("event_type"),
            project_id=project_id, client_id=client_id,
            keyword=keyword,
        )

    if query_type in ("note", "general"):
        results["notes"] = search_notes(
            keyword=keyword, start_date=start_date, end_date=end_date,
        )

    if query_type in ("summary", "general"):
        results["summaries"] = search_summaries(
            keyword=keyword, start_date=start_date, end_date=end_date,
        )

    return results


def _compute_reference_dates(today: date) -> dict:
    weekday = today.weekday()
    this_week_start = today - timedelta(days=weekday)
    this_week_end = this_week_start + timedelta(days=6)
    last_week_start = this_week_start - timedelta(days=7)
    last_week_end = this_week_start - timedelta(days=1)
    this_month_start = today.replace(day=1)
    last_month_end = this_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    return {
        "today": today.isoformat(),
        "yesterday": (today - timedelta(days=1)).isoformat(),
        "this_week_start": this_week_start.isoformat(),
        "this_week_end": this_week_end.isoformat(),
        "last_week_start": last_week_start.isoformat(),
        "last_week_end": last_week_end.isoformat(),
        "this_month_start": this_month_start.isoformat(),
        "this_month_end": today.isoformat(),
        "last_month_start": last_month_start.isoformat(),
        "last_month_end": last_month_end.isoformat(),
        "recent_7d": (today - timedelta(days=7)).isoformat(),
        "recent_30d": (today - timedelta(days=30)).isoformat(),
    }


def _parse_question(question: str, projects: list, clients: list, dates: dict) -> dict:
    project_list = "\n".join(
        [f"- id={p['id']}, 名称=\"{p['name']}\", 状态={p['status']}" for p in projects]
    ) or "（无项目）"
    client_list = "\n".join(
        [f"- id={c['id']}, 名称=\"{c['name']}\"" for c in clients]
    ) or "（无客户）"
    event_types = "\n".join([f"- {k}: {v}" for k, v in EVENT_TYPE_LABELS.items()])

    prompt = f"""根据用户的自然语言问题，提取查询参数并返回JSON。

## 参考日期
- 今天: {dates['today']}
- 昨天: {dates['yesterday']}
- 本周: {dates['this_week_start']} ~ {dates['this_week_end']}
- 上周: {dates['last_week_start']} ~ {dates['last_week_end']}
- 本月(至今): {dates['this_month_start']} ~ {dates['this_month_end']}
- 上月: {dates['last_month_start']} ~ {dates['last_month_end']}
- 最近7天: {dates['recent_7d']} ~ {dates['today']}
- 最近30天: {dates['recent_30d']} ~ {dates['today']}

## 可用项目
{project_list}

## 可用客户
{client_list}

## 可用事件类型
{event_types}

## 用户问题
{question}

## 输出JSON格式
{{{{
    "query_type": "问题类型",
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "event_type": "事件类型",
    "project_id": 数字,
    "client_id": 数字,
    "keyword": "关键词",
    "status": "状态",
    "priority": "优先级",
    "limit": 200
}}}}

## query_type 取值规则（重要！）
- "client": 问客户信息、客户列表、某客户相关的内容
- "project": 问项目信息、项目列表、某项目相关的内容
- "task": 问任务、待办、完成了什么、任务状态、优先级
- "file": 问文件、上传了什么、文档
- "summary": 问每日总结、某天的工作总结
- "event" 或 "timeline": 问最近活动、时间轴记录、操作日志
- "general": 问题涉及多个方面，或不确定类型

## 规则
- 日期用上面参考日期的实际值，不要写"上周一"这种描述
- 项目/客户id从可用列表中精确匹配，匹配不到的字段用null
- keyword用来匹配标题、描述、文件名、标签中的关键词
- status可选值: todo, doing, done, cancelled（仅task类型）
- priority可选值: high, medium, low（仅task类型）
- 只输出JSON，不要其他文字"""

    result = _chat(prompt, "你是一个查询解析器。只输出JSON，不要输出任何其他内容。")
    return _parse_json_response(result)


def _parse_json_response(text: str) -> dict:
    text = text.strip()

    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        text = json_match.group(1).strip()
    else:
        brace_start = text.find('{')
        brace_end = text.rfind('}')
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            text = text[brace_start:brace_end + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _generate_answer(question: str, results: dict, projects: list, clients: list,
                     dates: dict, query_type: str) -> str:
    project_map = {p["id"]: p["name"] for p in projects}
    client_map = {c["id"]: c["name"] for c in clients}

    context = build_context(results, project_map, client_map)

    if context == "没有找到相关数据。":
        return "没有找到相关数据，无法基于当前系统内容回答。"

    prompt = f"""根据以下查询结果回答用户的问题。用中文回答，简洁清晰，用Markdown格式。

## 用户问题
{question}

## 问题类型
{query_type}

## 查询结果
{context}

## 严格要求
- 先给出一句总结，概括找到多少条相关信息
- 列出关键的客户/项目/任务/文件/事件
- 如果涉及项目或客户，明确提及名称
- **如果查询结果中没有相关信息，请明确说"未找到相关数据"，绝对不要猜测、编造或假设任何信息**
- **不要编造不存在的客户、项目、任务、文件或数据，只能引用查询结果中实际存在的数据**
- 不超过800字"""

    return _chat(prompt, "You are a helpful office assistant. Answer questions based on the provided data.")
