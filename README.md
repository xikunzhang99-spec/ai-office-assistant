# AI办公助理 MVP

AI驱动的个人办公助理系统，帮助你管理每日任务、处理文件、生成总结、写入Obsidian。

## 功能

- **每日工作台** — 今日任务、随手记、时间轴、AI总结，支持日/周/月视图
- **任务管理** — 创建、编辑、完成任务，按状态/优先级筛选
- **日历视图** — 月历展示，点击日期查看当天详情
- **时间轴** — 记录所有系统活动，支持日/周/月视图
- **文件上传** — 上传 Word/PPT/Excel/PDF，AI自动总结
- **每日总结** — 基于当天数据，AI生成工作总结
- **项目管理** — 基础项目增删改查
- **客户管理** — 基础客户增删改查

## 启动方式

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env .env
```

编辑 `.env` 文件：

```env
# AI配置（必填）
AI_PROVIDER=deepseek
AI_API_KEY=your_api_key_here
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-chat

# Obsidian配置（可选，不配置则跳过Obsidian写入）
OBSIDIAN_VAULT_PATH=/Users/yourname/Documents/ObsidianVault

# 数据库和上传目录（可选，使用默认值即可）
DATABASE_PATH=./data/app.db
UPLOAD_DIR=./data/uploads
```

### 3. 启动

```bash
streamlit run app.py
```

浏览器访问 `http://localhost:8501`

## AI服务

第一版默认使用 DeepSeek API。如需切换模型：

- **OpenAI**: 修改 `AI_PROVIDER=openai`, `AI_BASE_URL=https://api.openai.com/v1`, `AI_MODEL=gpt-4o`
- **Kimi**: 修改 `AI_PROVIDER=kimi`, `AI_BASE_URL=https://api.moonshot.cn/v1`, `AI_MODEL=moonshot-v1-8k`
- **智谱**: 修改 `AI_PROVIDER=zhipu`, `AI_BASE_URL=https://open.bigmodel.cn/api/paas/v4`, `AI_MODEL=glm-4`

## 项目结构

```text
ai-office-assistant/
  app.py                 # Streamlit入口
  requirements.txt       # Python依赖
  .env.example           # 环境变量示例
  config/settings.py     # 配置管理
  database/
    db.py                # 数据库连接
    init_db.py           # 初始化脚本
    schema.sql           # 表结构
  pages/                 # Streamlit页面
    dashboard.py         # 每日工作台
    tasks.py             # 任务管理
    calendar_view.py     # 日历视图
    timeline.py          # 时间轴
    files.py             # 文件上传
    daily_summary.py     # 每日总结
    projects.py          # 项目管理
    clients.py           # 客户管理
  services/
    ai_service.py        # AI统一调用
    file_parser.py       # 文件解析
    markdown_service.py  # Markdown生成
    obsidian_service.py  # Obsidian写入
    timeline_service.py  # 时间轴服务
    task_service.py      # 任务服务
    summary_service.py   # 总结服务
  utils/
    date_utils.py        # 日期工具
    text_utils.py        # 文本工具
  data/
    uploads/             # 上传文件目录
    app.db               # SQLite数据库
```

## 后期扩展方向

- React / Next.js 前端
- FastAPI 后端
- PostgreSQL 数据库
- 向量数据库 + AI语义搜索
- 智能关系网络
- 飞书Bot + 通知
