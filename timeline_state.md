# 时间轴模块 (Timeline Module)

## 概述

时间轴模块负责记录和展示系统中所有事件的时间线，支持按日期范围、事件类型、关键词筛选，事件按日期分组展示。

## 涉及文件

| 文件 | 说明 |
|------|------|
| `pages/05_timeline.py` | 时间轴页面 UI |
| `services/timeline_service.py` | 事件数据服务（增删改查） |

## 数据结构

`timeline_events` 表核心字段：

| 字段 | 说明 |
|------|------|
| `event_type` | 事件类型（task_created, file_uploaded, daily_note 等） |
| `title` | 事件标题 |
| `description` | 事件描述 |
| `event_date` | 事件日期 |
| `created_at` | 创建时间戳 |
| `project_id` / `client_id` | 关联项目/客户 |
| `related_type` / `related_id` | 关联实体类型和 ID |

## 事件类型分类

| 分类 | 包含类型 |
|------|----------|
| 任务相关 | task_created, task_updated, task_status_changed, task_completed, task_deleted |
| 文件相关 | file_uploaded, file_summarized, file_markdown_created, file_written_to_obsidian, file_updated, file_deleted |
| 项目相关 | project_created, project_updated, project_deleted, stage_* |
| 客户相关 | client_created, client_updated, client_deleted |
| 记录类 | daily_note, manual |
| 总结类 | daily_summary, daily_summary_written_to_obsidian |
| 其他 | ai_query, obsidian_synced |

---

## 修改记录

### V1.0 — 2026-07-12 按日期分组的紧凑布局

**修改前状态：**
- 每条事件渲染为一个独立 `st.expander`，200 条事件即 200 个折叠面板
- 事件平铺展示，无日期分组，难以按天浏览
- 代码中存在 `if condition or True` 恒真逻辑
- 每行展示格式：`[类型标签][日期][关联信息]`，信息密度低

**本次修改内容：**

1. **按日期分组合并** — 使用 `defaultdict` + `_group_events_by_date()` 将事件按 `event_date` 分组，同一天的事件归到同一个日期头部下展示
2. **日期头部** — 每个日期组显示 `年-月-日 星期X` + 事件总数 + 按类型的细分统计（任务x / 文件x / 记录x / 项目x / 客户x）
3. **紧凑单行渲染** — 每条事件改为一行四列布局：`[类型标签] | 标题 | HH:MM | 详情按钮`，标题超过 50 字自动截断
4. **详情互斥展开** — 点击"详情"展开事件详情 expander，同时只能展开一条，再次点击或点"收起"关闭
5. **筛选栏精简** — 移除无实际作用的"查询"按钮，Streamlit 原生响应式自动触发筛选
6. **代码重构** — 拆分为 `_render_filter_bar` / `_fetch_events` / `_group_events_by_date` / `_render_grouped_events` / `_render_date_header` / `_event_category` / `_render_event_row` 七个独立函数，职责清晰

**页面布局：**
```
┌─ 筛选栏 ────────────────────────────────────────┐
│ [开始日期] [结束日期] [事件类型 ▼] [关键词搜索]  │
├─────────────────────────────────────────────────┤
│ + 手动记录（折叠）                               │
├─────────────────────────────────────────────────┤
│ 共 N 条记录                                      │
│                                                  │
│ ### 📅 2026年7月11日 星期五 (12条)               │
│     任务 5 | 文件 2 | 记录 3 | 项目 2            │
│ ───────────────────────────────────────────────  │
│ [+ 创建任务] 新建"xxx"              10:30 [详情] │
│ [~ 修改任务] 更新任务状态            09:15 [详情] │
│ [NOTE 随手记] 开会讨论了...          08:00 [详情] │
│                                                  │
│ ### 📅 2026年7月10日 星期四 (8条)                │
│     任务 3 | 记录 4 | 总结 1                     │
│ ───────────────────────────────────────────────  │
│ ...                                              │
└──────────────────────────────────────────────────┘
```

---

### V0 — 2026-06 初始版本

- 首次提交于 `4b63e04`（AI Office Assistant Initial Version）
- 初始文件 `pages/timeline.py` + `services/timeline_service.py`
- 基础事件 CRUD，支持筛选、手动记录
- 后续在 `3a8a741`（update project files）中重命名为 `pages/05_timeline.py`
