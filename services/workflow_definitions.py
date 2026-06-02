"""
workflow_definitions.py — Workflow type and step definitions.
Each workflow type declares its ordered steps. Used by WorkflowService for orchestration.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WorkflowStep:
    """Definition of one step in a workflow."""
    name: str
    label: str
    critical: bool = True
    description: str = ""


@dataclass
class WorkflowDefinition:
    """Definition of a complete workflow type."""
    workflow_type: str
    label: str
    steps: list = field(default_factory=list)
    confirmation_step: Optional[str] = None


WORKFLOW_REGISTRY: dict[str, WorkflowDefinition] = {}


def register(definition: WorkflowDefinition):
    WORKFLOW_REGISTRY[definition.workflow_type] = definition


# -- Workflow Definitions --

FILE_PROCESSING_WORKFLOW = WorkflowDefinition(
    workflow_type="file_processing",
    label="文件处理工作流",
    confirmation_step="generate_preview",
    steps=[
        WorkflowStep("extract_file_info",   "提取文件信息"),
        WorkflowStep("check_supported",      "检查文件格式",   critical=False),
        WorkflowStep("download_file",        "下载文件"),
        WorkflowStep("check_duplicate",      "文件去重检查"),
        WorkflowStep("save_local",           "保存到本地"),
        WorkflowStep("parse_text",           "解析文本内容"),
        WorkflowStep("ai_summarize",         "AI摘要分析"),
        WorkflowStep("ai_classify",          "AI分类标签"),
        WorkflowStep("match_relations",      "匹配客户/项目"),
        WorkflowStep("save_file_record",     "保存文件记录"),
        WorkflowStep("generate_preview",     "生成确认预览"),
        WorkflowStep("write_obsidian",       "写入Obsidian",   critical=False),
        WorkflowStep("sync_knowledge",       "同步知识库",     critical=False),
        WorkflowStep("sync_embedding",       "同步Embedding",  critical=False),
        WorkflowStep("extract_memory",       "提取长期记忆",   critical=False),
        WorkflowStep("build_reply",          "构建回复"),
    ],
)

FEISHU_MESSAGE_WORKFLOW = WorkflowDefinition(
    workflow_type="feishu_message",
    label="飞书消息处理工作流",
    steps=[
        WorkflowStep("detect_intent",        "意图检测"),
        WorkflowStep("route_command",        "命令路由"),
        WorkflowStep("execute_action",       "执行动作"),
        WorkflowStep("ai_qa",                "AI问答",         critical=False),
        WorkflowStep("save_context",         "保存上下文",     critical=False),
        WorkflowStep("build_reply",          "构建回复"),
    ],
)

TASK_CREATION_WORKFLOW = WorkflowDefinition(
    workflow_type="task_creation",
    label="任务创建工作流",
    steps=[
        WorkflowStep("validate_input",       "验证输入"),
        WorkflowStep("resolve_relations",    "解析关联"),
        WorkflowStep("create_task",          "创建任务"),
        WorkflowStep("sync_knowledge",       "同步知识库",     critical=False),
        WorkflowStep("write_obsidian",       "同步Obsidian",   critical=False),
    ],
)

PROJECT_UPDATE_WORKFLOW = WorkflowDefinition(
    workflow_type="project_update",
    label="项目更新工作流",
    steps=[
        WorkflowStep("validate_input",       "验证输入"),
        WorkflowStep("update_project_record","更新项目记录"),
        WorkflowStep("create_timeline_event","创建时间轴事件"),
        WorkflowStep("build_summary",        "生成更新摘要"),
    ],
)

CLIENT_UPDATE_WORKFLOW = WorkflowDefinition(
    workflow_type="client_update",
    label="客户更新工作流",
    steps=[
        WorkflowStep("validate_input",       "验证输入"),
        WorkflowStep("update_client_record", "更新客户记录"),
        WorkflowStep("create_timeline_event","创建跟进记录"),
        WorkflowStep("build_summary",        "生成更新摘要"),
    ],
)

TIMELINE_RECORD_WORKFLOW = WorkflowDefinition(
    workflow_type="timeline_record",
    label="时间轴记录工作流",
    steps=[
        WorkflowStep("validate_input",       "验证输入"),
        WorkflowStep("create_timeline_event","创建时间轴事件"),
        WorkflowStep("link_relations",       "建立关联关系",   critical=False),
    ],
)

NOTE_CREATION_WORKFLOW = WorkflowDefinition(
    workflow_type="note_creation",
    label="笔记创建工作流",
    steps=[
        WorkflowStep("validate_input",       "验证输入"),
        WorkflowStep("save_note",            "保存笔记"),
        WorkflowStep("sync_knowledge",       "同步知识库",     critical=False),
        WorkflowStep("write_obsidian",       "写入Obsidian",   critical=False),
    ],
)

SUMMARY_CREATION_WORKFLOW = WorkflowDefinition(
    workflow_type="summary_creation",
    label="总结生成工作流",
    steps=[
        WorkflowStep("validate_input",       "验证输入"),
        WorkflowStep("generate_summary",     "生成总结内容"),
        WorkflowStep("save_summary",         "保存总结"),
        WorkflowStep("write_obsidian",       "写入Obsidian",   critical=False),
    ],
)

register(FILE_PROCESSING_WORKFLOW)
register(FEISHU_MESSAGE_WORKFLOW)
register(TASK_CREATION_WORKFLOW)
register(PROJECT_UPDATE_WORKFLOW)
register(CLIENT_UPDATE_WORKFLOW)
register(TIMELINE_RECORD_WORKFLOW)
register(NOTE_CREATION_WORKFLOW)
register(SUMMARY_CREATION_WORKFLOW)
