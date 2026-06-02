# PROJECT_STATE.md — AI办公助理 项目交接文档

> 最后更新: 2026-05-29
> 当前阶段: Phase 16 Workflow Agent（工作流引擎）第一版 — 已完成
> 项目状态: 10 个页面，17 张表，36 个服务文件，Obsidian 双向同步，飞书多轮上下文 + 确认式执行，长期记忆 + 关系图谱 + 主动建议 + 工作流引擎

---

## 1. 项目目标

**AI办公助理** 是一个本地优先（local-first）的 AI 驱动个人办公助理系统。核心定位：

- 帮助个人用户管理每日任务、随手记、文件、项目、客户
- 通过 AI 自动生成文件摘要、每日工作总结
- 所有系统活动自动记录到时间轴（event sourcing 模式）
- 将 AI 生成的 Markdown 内容自动写入 Obsidian Vault
- 全部数据存储在本地 SQLite，无需网络即可运行核心功能
- 飞书机器人支持多轮上下文对话、确认式执行、主动建议

**非目标（明确不做）**：
- React / Next.js 前端（暂保持 Streamlit）
- 复杂 RAG / 向量数据库（Phase 3+ 已实现基础版）

---

## 2. 已实现功能

### 2.1 10 个功能页面

| 页面 | 文件 | 功能描述 |
|------|------|----------|
| **每日工作台** | `pages/dashboard.py` | 日/周/月视图；今日任务指标；任务快速操作；逾期提醒；随手记；时间轴；AI 主动建议（高风险项目、待跟进客户、未执行建议、长期记忆）；快速统计卡片 |
| **任务管理** | `pages/tasks.py` | 任务 CRUD；4 列多筛；内联编辑；删除；查看详情 |
| **日历视图** | `pages/calendar_view.py` | 月历网格；任务计数；逾期标记；点击日期查看详情 |
| **时间轴** | `pages/timeline.py` | 日/周/月/全部视图；4 列筛选；事件类型20+ |
| **AI问答** | `pages/ai_query.py` | 关键词/语义/混合搜索；Hybrid RAG；AI行动建议+执行；知识库维护 |
| **文件上传** | `pages/files.py` | 上传+AI解析+摘要；自动工作流；任务建议；文档动作分析+执行；长期记忆提取 |
| **每日总结** | `pages/daily_summary.py` | AI 生成总结；历史列表 |
| **项目管理** | `pages/projects.py` | 项目CRUD；进度条；查看详情（长期记忆+风险+下一步建议） |
| **客户管理** | `pages/clients.py` | 客户CRUD；查看详情（长期记忆+跟进建议+风险） |
| **数据管理** | `pages/data_management.py` | 数据库统计；知识库维护；数据导出；批量清理；Obsidian同步；飞书通知设置 |

### 2.2 时间轴事件系统

20+ 种事件类型被自动记录，包含 project_id、client_id、tags、metadata。

### 2.3 AI 集成

- 统一 OpenAI-compatible API 客户端（`services/ai_service.py`）
- `_chat()` 参数化 temperature、max_tokens
- 文件摘要、每日总结、AI 问答、AI 行动建议、AI 任务建议
- 长期记忆 AI 提取（temperature=0.2）

### 2.4 Obsidian 集成

- 客户/项目/任务/文件/每日总结 → Obsidian Vault 双向同步
- content_hash 去重，自动归档（Active ↔ Archive/Completed）

### 2.5 统一搜索 + 关系网络 + RAG

- **search_service.py** — 跨 7 表统一搜索 + build_context
- **relation_service.py** — 9 种语义关系类型，关系图谱，风险/跟进查询
- **knowledge_service.py** — 知识条目同步 + 多关键词加权搜索
- **embedding_service.py** — Embedding 生成 + 语义搜索（numpy + 纯 Python fallback）
- **hybrid_search_service.py** — 关键词+语义合并去重归一化
- **rag_service.py** — 三层 RAG（关键词/语义/混合）+ 内存缓存 + memory_items 上下文增强
- **action_suggestion_service.py** — AI 行动建议（6 种动作类型）
- **action_executor_service.py** — 一键执行建议动作

### 2.6 飞书深度集成（Phase 13-15）

#### 消息处理
- **feishu_api.py** — FastAPI webhook 端点，只负责接收事件+回复消息，不写业务逻辑
- **feishu_message_service.py** (1189行) — 命令路由、AI问答、多轮上下文、确认式执行
- **feishu_file_service.py** — 文件下载→解析→AI分析→去重→知识库→Embedding→Obsidian→长期记忆
- **feishu_session_service.py** — 会话状态管理（30分钟过期，DB持久化）
- **feishu_command_parser.py** — 自然语言命令解析（/新客户 /新项目 /新任务）

#### 飞书命令
| 命令 | 说明 |
|------|------|
| `/帮助` | 命令列表 |
| `/任务 今天/逾期/未来3天` | 任务查询 |
| `/总结 今天` | 今日简报 |
| `/问 xxx` | AI 查询 |
| `/新客户` `/新项目` `/新任务` | 数据创建 |
| `/今日建议` | 主动建议（重点任务+逾期+风险+跟进+记忆） |
| `/客户建议 客户名` | 客户级建议（风险+跟进+记忆） |
| `/项目建议 项目名` | 项目级建议（风险+阻塞+下一步） |

#### 多轮上下文 + 确认式执行
- 连续对话不丢失上下文
- AI 只生成建议，用户回复"执行1/执行全部/确认"后才执行
- 支持修改建议（"修改1 名字改成 xxx"）
- 支持范围执行（"只创建前3个"）
- 支持文档选段（"把第2部分创建成任务"）
- 上下文指代（"它/这个/上面的文件"）
- 双重存储（DB session + 内存 fallback）

### 2.7 长期记忆系统（Phase 15）

- **memory_items** 表 — 7 种记忆类型
- **memory_service.py** — AI 提取 + 幂等保存 + 按客户/项目/任务查询 + 搜索 + 重建
- 从文件上传、AI问答、飞书对话中自动提取
- Dashboard/客户详情/项目详情 展示长期记忆
- RAG 回答自动引用相关记忆和风险关系

### 2.8 关系图谱增强（Phase 15）

- 9 种语义关系类型：belongs_to, related_to, depends_on, blocks, caused_by, mentioned_in, created_from, follow_up_required, risk_related
- **get_entity_graph()** — 实体完整关系图谱（节点+边+风险+跟进）
- **get_client_graph()** — 客户图谱（向下遍历项目/任务/文件 + 记忆 + 风险）
- **get_project_graph()** — 项目图谱（含记忆 + 风险）
- **find_risk_relations() / find_follow_up_relations()** — 全局风险/跟进查询

### 2.9 主动工作流建议（Phase 15）

- **proactive_suggestion_service.py** — 每日/项目/客户级主动建议
- 逾期检测、项目风险检测（多维度：标记风险+高优逾期+阻塞任务）
- 需跟进客户检测（30天无活动但有活跃项目）
- AI 生成总结建议

### 2.10 工作流引擎（Phase 16）🆕

#### 项目阶段管理
- **project_stages** 表 — 项目阶段追踪（active/completed/skipped/pending）
- **workflow_templates** 表 — 4 套默认模板（software_project / client_followup / research_project / marketing_campaign），模板 JSON 含 stages + default_tasks
- **workflow_engine.py** — 阶段初始化（幂等）、推进、跳过、推断、进度摘要、自动任务生成
- 阶段流转：`advance_stage()` 完成当前阶段并激活下一个，`skip_stage()` 跳过但不自动激活

#### 风险检测
- **risk_detection_service.py** — 专用风险检测：项目（6维度：阶段缺失/逾期高优/停滞14天/阻塞/阶段卡住30天/标记风险）、客户（4维度：30天无跟进/所有项目停滞/逾期交付物/僵尸客户）、任务（3维度：逾期/阻塞/依赖风险）
- 风险等级：high (逾期高优/停滞/阻塞/依赖逾期)、medium (阶段缺失/阶段卡住/无跟进)、low

#### 统一编排
- **workflow_agent_service.py** — `analyze_business_state()` 编排 risk_detection + proactive_suggestion + relation_service，返回综合健康度评分 + 风险汇总 + 项目/客户摘要 + AI 总览

#### 页面增强
- **Dashboard** — AI 建议区新增项目阶段分布进度条
- **Project 详情页** — 阶段进度条 + 推进/跳过按钮 + 阶段卡片；新建项目自动初始化阶段

#### 飞书新命令
| 命令 | 说明 |
|------|------|
| `/项目状态 项目名` | 当前阶段、阶段流、进度%、剩余任务、风险 |
| `/客户状态 客户名` | 客户概况、活跃项目阶段 |
| `/项目风险 项目名` | 详细风险分析（高/中/低 + 建议） |

---

## 3. 核心技术栈

| 层级 | 技术 | 版本要求 |
|------|------|----------|
| **UI** | Streamlit | >=1.28.0 |
| **飞书API** | FastAPI + uvicorn | — |
| **数据库** | SQLite（WAL模式） | 系统自带 |
| **AI SDK** | `openai` (OpenAI-compatible) | >=1.0.0 |
| **配置管理** | `python-dotenv` | >=1.0.0 |
| **文件解析** | `python-docx`, `python-pptx`, `openpyxl`, `PyPDF2` | 见 requirements.txt |
| **数据处理** | `pandas` | >=2.0.0 |
| **运行环境** | Python 3.x（macOS / Linux） | — |

**数据库细节**:
- 文件: `data/app.db`
- 日志模式: **WAL** (Write-Ahead Logging)
- 同步级别: NORMAL
- 外键: 开启
- 繁忙超时: 5000ms
- 行工厂: `sqlite3.Row`（fetch_one/fetch_all 自动转 dict）
- **返回类型**: `fetch_one` → `dict | None`, `fetch_all` → `list[dict]`

---

## 4. 项目目录结构

```text
ai-office-assistant/
├── .env                          # 环境变量（AI密钥、飞书APP_ID/SECRET、路径）
├── README.md
├── PROJECT_STATE.md              # 本文档
├── requirements.txt
├── app.py                        # Streamlit入口 + 导航路由
├── feishu_api.py                 # FastAPI 飞书 webhook（只负责接收+回复）
├── seed_data.py                  # 测试数据生成器
│
├── config/
│   ├── __init__.py
│   └── settings.py               # 读取.env，导出所有配置常量
│
├── database/
│   ├── __init__.py
│   ├── db.py                     # 数据库连接层
│   ├── init_db.py                # 建表 + 幂等迁移脚本
│   └── schema.sql                # 完整DDL（15张表）
│
├── pages/                        # Streamlit页面（纯UI）
│   ├── __init__.py
│   ├── dashboard.py              # 每日工作台（含AI主动建议+记忆统计）
│   ├── tasks.py
│   ├── calendar_view.py
│   ├── timeline.py
│   ├── ai_query.py               # AI问答（3种RAG + 行动建议执行）
│   ├── files.py                  # 文件上传（自动工作流+文档动作+记忆提取）
│   ├── daily_summary.py
│   ├── projects.py               # 项目管理（含长期记忆+风险+下一步建议）
│   ├── clients.py                # 客户管理（含长期记忆+跟进建议+风险）
│   └── data_management.py        # 数据管理（统计+知识库+导出+清理+Obsidian+飞书）
│
├── services/                     # 业务逻辑层（36个文件）
│   ├── __init__.py
│   ├── ai_service.py             # AI统一调用
│   ├── backup_service.py         # 数据库备份
│   ├── client_service.py         # 客户CRUD
│   ├── detail_service.py         # 详情查询
│   ├── file_parser.py            # 文件解析路由
│   ├── file_service.py           # 文件CRUD
│   ├── knowledge_service.py      # 知识条目服务
│   ├── markdown_service.py       # Markdown生成
│   ├── obsidian_service.py       # Obsidian Vault写入+同步日志
│   ├── obsidian_log_service.py   # Obsidian同步状态
│   ├── project_service.py        # 项目CRUD
│   ├── query_service.py          # AI自然语言查询
│   ├── relation_service.py       # 关系网络（9种语义类型+图谱+风险/跟进）
│   ├── search_service.py         # 统一搜索层
│   ├── summary_service.py        # 每日总结+随手记
│   ├── task_service.py           # 任务CRUD
│   ├── timeline_service.py       # 时间轴事件
│   ├── rag_service.py            # RAG回答（关键词/语义/混合+memory上下文）
│   ├── embedding_service.py      # Embedding服务
│   ├── hybrid_search_service.py  # 混合搜索
│   ├── action_suggestion_service.py  # AI行动建议
│   ├── action_executor_service.py    # 建议执行引擎
│   ├── workflow_log_service.py   # 工作流日志
│   ├── reminder_service.py       # 提醒服务
│   │
│   ├── feishu_service.py         # 飞书API（token+消息发送）
│   ├── feishu_message_service.py # 飞书消息处理（命令+多轮上下文+确认式执行）
│   ├── feishu_session_service.py # 飞书会话状态管理（30min过期）
│   ├── feishu_file_service.py    # 飞书文件处理（下载→分析→记忆提取）
│   ├── feishu_command_parser.py  # 飞书命令解析
│   │
│   ├── memory_service.py         # 长期记忆（AI提取+幂等+搜索+重建）
│   ├── proactive_suggestion_service.py  # 主动工作流建议
│   ├── document_action_service.py       # 文档动作分析
│   ├── relation_service.py       # 关系图谱增强
│   │
│   ├── workflow_engine.py        # 工作流引擎（阶段管理+模板+自动任务）🆕
│   ├── risk_detection_service.py # 风险检测（项目/客户/任务多维度）🆕
│   └── workflow_agent_service.py # 统一编排入口（综合业务状态分析）🆕
│
├── utils/
│   ├── __init__.py
│   ├── date_utils.py
│   ├── display_utils.py          # 统一显示格式化（20+函数+常量）
│   └── text_utils.py
│
├── data/
│   ├── app.db                    # SQLite数据库
│   └── uploads/                  # 上传文件目录
│       └── feishu/               # 飞书文件子目录
│
├── test_feishu_session.py        # 22个测试（Session+多轮上下文+确认式执行+事件去重）
└── test_feishu_memory.py         # 16个测试（记忆+关系+主动建议+飞书命令）
```

---

## 5. 数据库表（17张）

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `tasks` | 任务 | title, status, priority, due_date, project_id, client_id |
| `projects` | 项目 | name, status, client_id |
| `clients` | 客户 | name, contact_info |
| `files` | 文件 | filename, file_hash, summary, key_points, tags, project_id, client_id |
| `daily_notes` | 随手记 | content, note_date |
| `daily_summaries` | 每日总结 | summary_date, content |
| `timeline_events` | 时间轴 | event_type, title, project_id, client_id, tags, metadata |
| `tags` | 标签 | name (UNIQUE), type |
| `relations` | 关系网络 | source_type, source_id, target_type, target_id, relation_type, description |
| `knowledge_items` | 知识条目 | source_type, source_id, title, content, tags |
| `knowledge_embeddings` | 向量存储 | knowledge_item_id (UNIQUE), embedding_model, embedding (JSON) |
| `workflow_logs` | 工作流日志 | workflow_type, source_type, source_id, status, message, details |
| `processed_feishu_events` | 飞书事件去重 | event_id (UNIQUE), message_id, status |
| `obsidian_sync_logs` | Obsidian同步 | source_type+source_id (UNIQUE), content_hash, obsidian_path |
| `memory_items` | 长期记忆 | memory_type, title, content, importance, client_id, project_id, task_id |
| `feishu_sessions` | 飞书会话 | user_key (UNIQUE), current_mode, pending_actions_json, last_analysis_json, expires_at |
| `project_stages` 🆕 | 项目阶段 | project_id, stage_name, stage_order, status, started_at, completed_at |
| `workflow_templates` 🆕 | 工作流模板 | template_name, template_type, template_json |

---

## 6. 已完成里程碑

### Phase 1-12: MVP核心 + 时间轴 + 搜索 + 关系 + RAG + 数据管理 + Obsidian同步 ✅
详见历史记录，已稳定运行。

### Phase 13: 日历同步 + 提醒通知 + 飞书通知第一版 ✅
- 提醒服务 + 飞书 Webhook 通知 + 日历增强
- 每日简报 + 飞书卡片消息
- 通知设置页面

### Phase 14: 飞书多轮上下文 + Session 状态管理 + 确认式执行 ✅
- `feishu_sessions` 表（30分钟过期，DB持久化）
- `feishu_session_service.py`（9个函数）
- `feishu_message_service.py` 多轮上下文改造
- 确认式执行：AI只建议不执行，用户回复确认后执行
- 修改建议再执行（"修改1 名字改成 xxx"）
- 文档选段命令（"把第2部分创建成任务"）
- 上下文指代（"它/这个/上面的文件"）
- 飞书事件去重
- 22 个测试用例全部通过

### Phase 15: 长期记忆 + 关系图谱增强 + 主动工作流第一版 ✅
- `memory_items` 表（7种记忆类型，幂等）
- `memory_service.py`（AI提取+保存+搜索+重建）
- 关系图谱增强（9种语义类型，实体图谱/客户图谱/项目图谱）
- 主动工作流建议（每日/项目/客户级）
- Dashboard 增强（AI建议+记忆统计+风险+跟进）
- 客户/项目详情页增强（长期记忆+风险+建议）
- RAG 上下文增强（纳入 memory_items + 风险关系）
- 飞书命令 `/今日建议` `/客户建议` `/项目建议`
- 文件上传自动提取长期记忆
- 17 个 DB 层测试 + 16 个集成测试全部通过

### Phase 16: Workflow Agent（工作流引擎）第一版 ✅ 🆕
- `project_stages` 表（阶段追踪：active/completed/skipped/pending）
- `workflow_templates` 表（4套默认模板：software/client/research/marketing）
- `workflow_engine.py`（阶段初始化/推进/跳过/推断/进度/自动任务生成）
- `risk_detection_service.py`（项目6维度/客户4维度/任务3维度风险检测）
- `workflow_agent_service.py`（统一编排 `analyze_business_state()`）
- `proactive_suggestion_service.py` 增强（阶段缺失/卡住维度 + get_project_stage_summary）
- Dashboard 项目阶段分布进度条
- Project 详情页阶段可视化 + 推进/跳过按钮
- 新建项目自动初始化阶段
- 飞书命令 `/项目状态` `/客户状态` `/项目风险`
- timeline_service 新增 4 个 event type（stage_*）
- 全部逻辑幂等，所有操作记录 workflow_log

---

## 7. 当前存在的问题和 Bug

| 问题 | 严重程度 | 说明 |
|------|----------|------|
| Streamlit session_state 依赖 | 低 | 浏览器刷新后 session_state 丢失（已防崩溃） |
| 语义搜索全量遍历 | 低 | 已用 numpy 批量优化，未来可引入 FAISS |
| AI API 调用超时 | 低 | 主动建议中的 AI 总结生成可能较慢 |
| Embedding 生成耗时 | 低 | 首次 rebuild 需逐条调用 API |

---

## 8. 下一阶段开发建议

### 8.1 工作流引擎增强
- 阶段自动推断：根据任务完成率和文件上传自动建议阶段推进
- 工作流模板管理页面（CRUD 自定义模板）
- 阶段 SLA 设置（预计完成时间 + 超时告警）

### 8.2 标签系统完善
- 标签管理页面
- `tag_item` 动作一键执行
- 按标签筛选实体

### 8.3 向量检索升级
- FAISS IVF/HNSW 索引（`faiss_search()` 接口已预留）

### 8.4 UI/UX 改进
- 暗色模式
- 到期任务通知弹窗
- 数据可视化图表（项目进度、任务趋势、时间热力图）

### 8.5 基础设施升级（谨慎）
- FastAPI 后端（替换 Streamlit 内置服务器）
- PostgreSQL 迁移（多用户场景）

---

## 9. 启动方式

```bash
# 1. 进入项目目录
cd /Users/zxk/Desktop/AI_Project/obs_phase1/ai-office-assistant

# 2. 安装依赖（首次）
pip install -r requirements.txt

# 3. 配置 .env（AI密钥+飞书凭证+Obsidian路径）

# 4. 生成测试数据（首次）
python3 seed_data.py

# 5. 启动 Streamlit
streamlit run app.py
# → http://localhost:8501

# 6. 启动飞书 webhook（可选）
uvicorn feishu_api:app --host 0.0.0.0 --port 8080

# 7. 运行测试
python test_feishu_session.py   # 22 tests
python test_feishu_memory.py    # 16 tests
```

---

## 10. 环境变量

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
DATABASE_PATH=/Users/zxk/Desktop/AI_Project/obs_phase1/ai-office-assistant/data/app.db
UPLOAD_DIR=/Users/zxk/Desktop/AI_Project/obs_phase1/ai-office-assistant/data/uploads

# 飞书应用机器人
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

---

## 11. 架构约束（开发注意事项）

1. **pages/ 只能放 UI 代码**，所有 DB 操作和业务逻辑在 services/
2. **数据库查询结果是 `dict`**，fetch_one/fetch_all 内部已转
3. **每次 DB 操作创建新连接**，无连接池
4. **`init_database()` 必须幂等**（CREATE TABLE IF NOT EXISTS + try/except 迁移）
5. **事件记录 + 关系创建是副作用**，add_event() 自动建立关系
6. **关系创建是幂等的**，add_relation() 先查后插
7. **知识条目同步是幂等的**，_upsert_knowledge() 通过 source_type+source_id UNIQUE 去重
8. **记忆保存是幂等的**，save_memory_item() 通过 source_type+source_id+memory_type+title 去重
9. **飞书事件去重**，processed_feishu_events 表 UNIQUE 约束 + 内存检查
10. **feishu_api.py 只负责路由**，不写复杂业务逻辑
11. **飞书消息回复只在 feishu_api.py 中调用一次** reply_message()
12. **feishu_session_service.py 双重存储**：DB session + 内存 fallback
