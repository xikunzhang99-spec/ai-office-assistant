# PROJECT_STATE.md — AI办公助理 项目交接文档

> 最后更新: 2026-06-11
> 当前阶段: 重构 V2 — 页面优化 + 日历 + 时间轴
> 项目状态: 5 个页面，21 张表（空数据），13 个核心服务，本地个人长期使用

---

## 1. 项目目标

**AI办公助理** 是一个本地优先（local-first）的 AI 驱动个人办公助理系统。

- 帮助个人用户管理每日任务、随手记、文件、项目、客户
- 通过 AI 自动生成文件摘要、每日工作总结
- 所有系统活动自动记录到时间轴
- 日历视图显示被标记任务的截止日期
- 全部数据存储在本地 SQLite，无需网络即可运行核心功能

**当前不做**：
- 飞书集成（相关代码保留在 services/ 中但未启用）
- React / Next.js 前端
- 云端部署
- 多人协作
- Chroma 向量数据库（使用 numpy embedding 方案）

---

## 2. 5 个功能页面

| 页面 | 文件 | 功能描述 |
|------|------|----------|
| **每日工作台** | `pages/01_daily_workspace.py` | 今日随手记（左输入+右总览）、今日任务（含日历标记按钮）、日历视图（月份切换+任务高亮）、本周概览、最近项目、最近客户、文件上传+AI解析、每日总结生成 |
| **时间轴** | `pages/05_timeline.py` | 日期筛选、事件类型分组筛选（全部/手动/随手记/任务/文件/项目/客户/总结/AI问答）、关键词搜索、手动记录、事件列表 |
| **业务管理** | `pages/02_business_management.py` | 4 Tab：任务管理（CRUD+筛选+日历标记）、项目管理（CRUD+阶段+任务进度）、客户管理（CRUD+关联项目）、关系查看（按客户/项目/全局风险+跟进） |
| **AI问答** | `pages/03_ai_assistant.py` | 自动选择搜索策略（SQL→关键词→语义→AI通用），高级模式可手动切换，来源引用，无本地数据不编造 |
| **数据管理** | `pages/04_data_management.py` | 6 Tab：数据统计（18表）、数据库备份、清空业务数据（RESET确认+自动备份）、重建索引/Embedding、清理孤儿数据、导出CSV/DB |

---

## 3. 核心技术栈

| 层级 | 技术 |
|------|------|
| **UI** | Streamlit 1.56+ (st.navigation 多页面路由) |
| **数据库** | SQLite（WAL模式） |
| **向量搜索** | numpy（批量余弦相似度） |
| **AI SDK** | `openai` (OpenAI-compatible) |
| **配置管理** | `python-dotenv` |
| **文件解析** | `python-docx`, `python-pptx`, `openpyxl`, `PyPDF2` |

**数据库细节**:
- 文件: `data/app.db`
- 日志模式: **WAL**
- 外键: 开启
- 行工厂: `sqlite3.Row`（fetch_one/fetch_all 自动转 dict）
- **返回类型**: `fetch_one` → `dict | None`, `fetch_all` → `list[dict]`

---

## 4. 项目目录结构

```text
ai-office-assistant/
├── app.py                         # Streamlit入口（st.navigation 路由，5个中文页面）
├── PROJECT_STATE.md               # 本文档
├── README.md
├── requirements.txt
├── .env                           # 环境变量
│
├── config/
│   └── settings.py                # 配置管理
│
├── database/
│   ├── db.py                      # 数据库连接（SQLite WAL）
│   ├── init_db.py                 # 建表 + 幂等迁移（含日历字段迁移）
│   └── schema.sql                 # 完整DDL（21张表）
│
├── pages/                         # 5 个页面（纯UI，零原始SQL）
│   ├── 01_daily_workspace.py      # 每日工作台
│   ├── 02_business_management.py  # 业务管理
│   ├── 03_ai_assistant.py         # AI问答
│   ├── 04_data_management.py      # 数据管理
│   └── 05_timeline.py             # 时间轴（新增）
│
├── services/                      # 业务逻辑层
│   ├── task_service.py            # 任务 CRUD + 搜索 + 日历标记
│   ├── project_service.py         # 项目 CRUD
│   ├── client_service.py          # 客户 CRUD
│   ├── timeline_service.py        # 时间轴事件
│   ├── file_service.py            # 文件记录管理
│   ├── summary_service.py         # 随手记 + 每日总结
│   ├── ai_service.py              # AI 统一调用（OpenAI-compatible）
│   ├── rag_service.py             # RAG（关键词/语义/混合/知识块）
│   ├── search_service.py          # 统一搜索（7表 + 语义chunks）
│   ├── unified_qa_service.py      # 统一问答（4层自动策略）
│   ├── data_management_service.py # 数据管理（统计/备份/清空/导出）
│   ├── backup_service.py          # 数据库备份
│   ├── relation_service.py        # 关系网络（9种语义类型）
│   ├── knowledge_service.py       # 知识条目管理
│   ├── embedding_service.py       # numpy embedding + 语义搜索
│   ├── memory_service.py          # 长期记忆
│   ├── workflow_engine.py         # 项目阶段管理
│   ├── ...（其余服务文件保留备用）
│   └── business_brain/            # 业务大脑模块（保留备用）
│       ├── brain_service.py
│       ├── classifier.py
│       ├── extractor.py
│       ├── entity_matcher.py
│       ├── action_planner.py
│       └── prompts.py
│
├── utils/
│   ├── date_utils.py              # 日期工具
│   ├── display_utils.py           # 统一显示格式化
│   └── text_utils.py
│
├── scripts/
│   └── reset_business_data.py     # 命令行清空数据脚本
│
├── archive/
│   └── old_pages/                  # 13 个旧页面归档
│
├── backup/                        # 数据库备份
│   ├── app_before_refactor_20260611_163928.db
│   └── app_before_reset_20260611_165155.db
│
└── data/
    ├── app.db                     # SQLite数据库（已清空业务数据）
    ├── backups/
    └── uploads/
```

---

## 5. 数据库表（21张）

| 表名 | 说明 |
|------|------|
| `tasks` | 任务（含 show_on_calendar / calendar_date 日历字段） |
| `projects` | 项目 |
| `clients` | 客户 |
| `files` | 文件 |
| `daily_notes` | 随手记 |
| `daily_summaries` | 每日总结 |
| `timeline_events` | 时间轴事件 |
| `tags` | 标签 |
| `relations` | 关系网络 |
| `knowledge_items` | 知识条目 |
| `knowledge_embeddings` | 向量存储（numpy） |
| `knowledge_chunks` | 知识块 |
| `workflow_logs` | 工作流日志 |
| `workflow_runs` | 工作流运行 |
| `workflow_steps` | 工作流步骤 |
| `workflow_templates` | 工作流模板 |
| `memory_items` | 长期记忆 |
| `project_stages` | 项目阶段 |
| `obsidian_sync_logs` | Obsidian同步日志 |
| `processed_feishu_events` | 飞书事件去重（保留备用） |
| `feishu_sessions` | 飞书会话（保留备用） |

---

## 6. 新增功能（重构 V2）

### 6.1 随手记保存修复
- **Bug**: 保存按钮调用 `add_event()` 只写入 `timeline_events`，`get_today_notes()` 读取 `daily_notes` 表
- **修复**: 改为调用 `create_daily_note()`，同时写入 `daily_notes` 和 `timeline_events`

### 6.2 左侧菜单中文化
- `app.py` 使用 `st.navigation()` 统一路由，5个页面均为中文标题
- 不再显示 "app" 入口和英文页面名
- 子页面移除 `st.set_page_config()`（由导航统一管理）

### 6.3 时间轴页面
- 新增 `pages/05_timeline.py`
- 支持日期范围筛选、事件类型分组筛选、关键词搜索、手动记录

### 6.4 日历视图
- 每日工作台新增日历视图模块
- 支持月份切换（上/下月）
- 被标记任务日期红色高亮，今日蓝色标记
- 显示每日任务数量和标题

### 6.5 任务日历标记
- `tasks` 表新增 `show_on_calendar` (INTEGER DEFAULT 0) 和 `calendar_date` (TEXT)
- 每日工作台任务行：标记/取消按钮
- 业务管理任务详情：日历日期选择 + 标记/取消按钮
- 新增服务函数: `mark_task_on_calendar()`, `unmark_task_from_calendar()`, `get_calendar_tasks()`
- 日历日期优先级: `calendar_date` > `due_date`

### 6.6 页面布局优化
- 今日随手记改为左输入 + 右总览的左右布局
- 输入框高度 120px，总览显示最近 5 条

---

## 7. 当前数据状态

所有业务表已清空，表结构完整保留：

```
tasks: 0 | projects: 0 | clients: 0 | files: 0
daily_summaries: 0 | timeline_events: 0
knowledge_items: 0 | knowledge_embeddings: 0
relations: 0 | memory_items: 0
...
总记录数: 0
```

---

## 8. 启动方式

```bash
cd /Users/zxk/Desktop/AI_Project/obs_phase1/ai-office-assistant

# 安装依赖（首次）
pip install -r requirements.txt

# 配置 .env（AI密钥 + Obsidian路径等）

# 启动
streamlit run app.py
# → http://localhost:8501

# 清空数据（需要时）
python scripts/reset_business_data.py
```

---

## 9. 环境变量

```env
# AI Provider
AI_PROVIDER=qwen
AI_API_KEY=sk-xxx
AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AI_MODEL=qwen3.6-plus
EMBEDDING_MODEL=text-embedding-v1

# Obsidian（可选）
OBSIDIAN_VAULT_PATH=/Users/zxk/Documents/Obsidian_Vault

# Database & Storage
DATABASE_PATH=./data/app.db
UPLOAD_DIR=./data/uploads
```

---

## 10. 架构约束

1. **pages/ 只放 UI 代码**，所有 DB 操作和业务逻辑在 services/
2. **数据库查询结果是 `dict`**，fetch_one/fetch_all 内部已转
3. **app.py 使用 `st.navigation()` 统一路由**，子页面不再调用 `st.set_page_config()`
4. **页面末尾必须调用 `render()`**，Streamlit 不会自动调用
5. **AI 问答不编造本地数据**，无匹配时明确说明
6. **清空数据前必须自动备份**
7. **当前不依赖 Chroma**，使用 numpy embedding 方案
8. **当前不做飞书集成**
9. **随手记保存使用 `create_daily_note()`**，自动同步写入 daily_notes 和 timeline_events
10. **日历日期优先级**: calendar_date > due_date

---

## 11. 下一阶段建议

1. **录入真实数据** — 从每日工作台开始手动录入任务、项目、客户
2. **快速输入 AI 解析** — 自然语言输入自动识别客户/项目/任务/日期
3. **向量检索升级** — numpy → FAISS（FAISS 已安装，接口已预留）
4. **标签系统完善** — 标签管理、按标签筛选
5. **UI 改进** — 数据可视化图表
6. **日历增强** — 点击日期查看当天任务详情、拖拽修改日期
