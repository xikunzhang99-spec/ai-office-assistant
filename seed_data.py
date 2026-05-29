"""
测试数据生成器 — AI办公助理

生成真实感的办公场景测试数据，包含客户、项目、任务、时间轴事件、
随手记、每日总结。数据之间有关联关系，时间分布在近30天内。

用法:
    python seed_data.py          # 生成数据
    python seed_data.py --dry    # 仅打印计划，不写入
"""

import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db import get_connection, execute, insert, fetch_all


TODAY = date.today()  # 2026-05-21

# ── 日期工具 ──────────────────────────────────────────────
def d(offset: int) -> str:
    """返回相对今天的日期字符串，offset 为负数表示过去"""
    return (TODAY + timedelta(days=offset)).isoformat()

def dt(offset: int, hour: int = 9, minute: int = 0) -> str:
    """返回相对今天的日期时间字符串"""
    d = TODAY + timedelta(days=offset)
    return f"{d.isoformat()}T{hour:02d}:{minute:02d}:00"


# ── 数据定义 ──────────────────────────────────────────────

# 5 个客户
CLIENTS = [
    {"id": 1, "name": "招商银行-企业信贷部", "description": "负责企业信贷审批流程的数字化转型，需要构建智能风控和自动化审批系统", "contact_info": "张行长 / zhanghang@cmbchina.com / 010-8888-1001", "created": d(-30)},
    {"id": 2, "name": "字节跳动-AI平台部", "description": "AI基础设施团队，负责内部模型训练平台和数据标注工具的研发", "contact_info": "王总监 / wangjian@bytedance.com / 010-6666-2002", "created": d(-28)},
    {"id": 3, "name": "华润集团-数字化转型办", "description": "集团层面推动ERP系统升级和数字化改造，涉及财务、人力、供应链多个模块", "contact_info": "李主任 / lihua@crc.com.cn / 0755-9999-3003", "created": d(-25)},
    {"id": 4, "name": "小米科技-供应链管理部", "description": "供应链数据可视化和智能预测需求，需要整合多个数据源进行实时监控", "contact_info": "陈经理 / chenwei@xiaomi.com / 010-7777-4004", "created": d(-20)},
    {"id": 5, "name": "万科地产-物业管理部", "description": "物业管理系统的现代化重构，包括业主服务、报修管理、费用核算等功能", "contact_info": "赵总 / zhaoming@vanke.com / 0755-5555-5005", "created": d(-15)},
]

# 8 个项目，关联客户
PROJECTS = [
    {"id": 1, "name": "企业信贷审批系统 v2", "description": "重构现有信贷审批流程，支持多级审批、自动化信用评估、审批进度实时追踪", "status": "active", "client_id": 1, "created": d(-28)},
    {"id": 2, "name": "智能风控模型开发", "description": "基于机器学习的风险控制模型，包括数据清洗、特征工程、模型训练和上线部署", "status": "active", "client_id": 1, "created": d(-25)},
    {"id": 3, "name": "AI模型训练平台搭建", "description": "搭建内部GPU集群管理平台，支持训练任务调度、资源监控、模型版本管理", "status": "active", "client_id": 2, "created": d(-26)},
    {"id": 4, "name": "数据标注工具开发", "description": "开发内部数据标注平台，支持文本、图像、音频多模态标注和审核流程", "status": "active", "client_id": 2, "created": d(-20)},
    {"id": 5, "name": "ERP系统升级改造", "description": "将旧版ERP系统升级至SAP S/4HANA，包括财务、人力、采购、库存四大模块", "status": "active", "client_id": 3, "created": d(-22)},
    {"id": 6, "name": "供应链可视化大屏", "description": "实时供应链数据监控大屏，展示采购、生产、物流、库存全链路数据", "status": "active", "client_id": 4, "created": d(-18)},
    {"id": 7, "name": "物业管理系统重构", "description": "将旧物业系统用微服务架构重构，包括业主APP、管理后台、数据中台", "status": "active", "client_id": 5, "created": d(-14)},
    {"id": 8, "name": "内部研发效能平台", "description": "公司内部使用的研发效能工具集，包括代码审查、自动化测试、CI/CD流水线", "status": "active", "client_id": None, "created": d(-30)},
]

# 20 个任务，关联项目
TASKS = [
    # ── 项目1: 信贷审批系统 (5个) ──
    {"id": 1, "title": "完成需求文档评审", "description": "与招商银行信贷部进行需求评审，确认审批流程节点、角色权限和合规要求", "status": "done", "priority": "high", "project_id": 1, "client_id": 1, "due_date": d(-22), "created": d(-28), "completed": d(-24)},
    {"id": 2, "title": "搭建审批流程引擎", "description": "基于Camunda搭建可配置的审批流程引擎，支持串行/并行/条件分支", "status": "done", "priority": "high", "project_id": 1, "client_id": 1, "due_date": d(-15), "created": d(-24), "completed": d(-16)},
    {"id": 3, "title": "对接银行核心系统接口", "description": "对接招商银行核心交易系统的授信查询和放款接口（HTTP/SOAP协议）", "status": "doing", "priority": "high", "project_id": 1, "client_id": 1, "due_date": d(3), "created": d(-10)},
    {"id": 4, "title": "开发客户信用评估模块", "description": "接入央行征信数据和行内黑名单，实现自动信用评分和风险等级分类", "status": "todo", "priority": "high", "project_id": 1, "client_id": 1, "due_date": d(7), "created": d(-5)},
    {"id": 5, "title": "编写接口文档与联调指南", "description": "为银行IT团队编写接口对接文档，包含签名算法、报文格式、错误码说明", "status": "todo", "priority": "medium", "project_id": 1, "client_id": 1, "due_date": d(10), "created": d(-3)},

    # ── 项目2: 智能风控 (4个) ──
    {"id": 6, "title": "数据清洗与特征工程", "description": "清洗2年的历史信贷数据，提取200+维度的特征变量用于模型训练", "status": "done", "priority": "high", "project_id": 2, "client_id": 1, "due_date": d(-18), "created": d(-22), "completed": d(-19)},
    {"id": 7, "title": "风控模型训练与调参", "description": "使用XGBoost和LightGBM训练违约预测模型，AUC目标>0.85", "status": "doing", "priority": "high", "project_id": 2, "client_id": 1, "due_date": d(1), "created": d(-15)},
    {"id": 8, "title": "模型A/B测试方案设计", "description": "设计新老模型并行运行的A/B测试方案，评估线上实际效果差异", "status": "todo", "priority": "medium", "project_id": 2, "client_id": 1, "due_date": d(5), "created": d(-5)},
    {"id": 9, "title": "编写模型部署文档", "description": "包含模型格式转换、推理服务部署、性能基准测试和回滚方案", "status": "todo", "priority": "low", "project_id": 2, "client_id": 1, "due_date": d(12), "created": d(-2)},

    # ── 项目3: AI训练平台 (3个) ──
    {"id": 10, "title": "需求调研与技术选型", "description": "调研Kubeflow、Ray、Determined AI等训练平台方案，输出技术选型报告", "status": "done", "priority": "high", "project_id": 3, "client_id": 2, "due_date": d(-20), "created": d(-24), "completed": d(-21)},
    {"id": 11, "title": "搭建GPU集群管理环境", "description": "部署Kubernetes + NVIDIA GPU Operator，配置资源配额和调度策略", "status": "doing", "priority": "high", "project_id": 3, "client_id": 2, "due_date": d(2), "created": d(-12)},
    {"id": 12, "title": "开发训练任务调度系统", "description": "实现训练任务的提交、排队、调度、监控功能，支持优先级抢占", "status": "todo", "priority": "high", "project_id": 3, "client_id": 2, "due_date": d(8), "created": d(-3)},

    # ── 项目4: 数据标注工具 (2个) ──
    {"id": 13, "title": "标注工具UI设计", "description": "完成标注工具前端界面设计，包括标注工作台、审核面板、数据统计页", "status": "done", "priority": "high", "project_id": 4, "client_id": 2, "due_date": d(-10), "created": d(-16), "completed": d(-11)},
    {"id": 14, "title": "标注审核流程开发", "description": "实现标注-初审-复审-终审四级审核流程，支持驳回和打回重标", "status": "doing", "priority": "medium", "project_id": 4, "client_id": 2, "due_date": d(4), "created": d(-7)},

    # ── 项目5: ERP升级 (2个) ──
    {"id": 15, "title": "旧系统数据迁移", "description": "将旧ERP系统的10年历史数据清洗、转换后迁移至SAP S/4HANA", "status": "done", "priority": "high", "project_id": 5, "client_id": 3, "due_date": d(-12), "created": d(-18), "completed": d(-13)},
    {"id": 16, "title": "财务模块UAT测试", "description": "组织华润财务团队进行用户验收测试，覆盖总账、应收、应付、资产四大流程", "status": "doing", "priority": "high", "project_id": 5, "client_id": 3, "due_date": d(3), "created": d(-6)},

    # ── 项目6: 供应链大屏 (2个) ──
    {"id": 17, "title": "多数据源接入与清洗", "description": "接入ERP、WMS、TMS三个系统的数据源，进行ETL管道开发", "status": "done", "priority": "high", "project_id": 6, "client_id": 4, "due_date": d(-6), "created": d(-14), "completed": d(-7)},
    {"id": 18, "title": "大屏前端可视化开发", "description": "使用ECharts + Three.js开发供应链全链路可视化大屏，含地图、流向图、仪表盘", "status": "doing", "priority": "high", "project_id": 6, "client_id": 4, "due_date": d(2), "created": d(-5)},

    # ── 项目7: 物业管理 (1个) ──
    {"id": 19, "title": "微服务架构设计与数据库建模", "description": "按业主、报修、缴费、公告四个领域拆分微服务，设计对应的数据库Schema", "status": "doing", "priority": "high", "project_id": 7, "client_id": 5, "due_date": d(1), "created": d(-4)},

    # ── 项目8: 内部效能 (1个) ──
    {"id": 20, "title": "代码审查机器人集成", "description": "将SonarQube和AI Code Review集成到GitLab CI流程，自动化代码质量检查", "status": "done", "priority": "medium", "project_id": 8, "client_id": None, "due_date": d(-20), "created": d(-26), "completed": d(-21)},
]

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 10 条随手记
DAILY_NOTES = [
    {"content": "早上和招商银行张行长通了电话，确认了信贷审批系统的需求变更——需要在审批流程中加入合规审查节点", "note_date": d(-3)},
    {"content": "下午3点字节跳动王总监来公司做技术交流，讨论了GPU集群的网络拓扑方案，建议用InfiniBand而不是以太网", "note_date": d(-5)},
    {"content": "发现风控模型的AUC只有0.78，怀疑是训练数据中的负样本不够——需要找银行要更多违约案例数据", "note_date": d(-8)},
    {"content": "小米的陈经理反馈供应链大屏的实时数据延迟太大（5秒以上），要求优化到1秒以内，这是个性能优化的高优事项", "note_date": d(-2)},
    {"content": "今天整理了一下近两周的工作内容，准备写周报。信贷审批系统和风控模型都在稳步推进中", "note_date": d(-1)},
    {"content": "华润ERP数据迁移中发现旧系统字符编码问题——大量中文数据是GBK编码，转UTF-8时出现乱码，得写个专门的转换脚本", "note_date": d(-12)},
    {"content": "物业管理系统重构的第一次迭代计划定下来了，优先做报修流程和缴费查询两个核心功能", "note_date": d(-9)},
    {"content": "内部效能平台的自动化测试流水线覆盖率达到了85%，这周重点攻克剩下的集成测试部分", "note_date": d(-15)},
    {"content": "和团队讨论了AI问答模块的重构方案——当前只查timeline_events，需要扩展到查所有业务表。这是本周的高优事项", "note_date": d(-4)},
    {"content": "今天和万科赵总确认了下一阶段的合作计划，物业管理系统预计分三期交付，第一期聚焦业主端APP", "note_date": d(-6)},
]

# 5 条每日总结（最近5天）
DAILY_SUMMARIES = [
    {
        "summary_date": d(-4),
        "content": """## 今日完成\n- 完成物业管理系统微服务架构设计初稿\n- 与团队讨论AI问答模块重构方案，确定扩展查询范围至全部业务表\n- 修复数据标注工具审核流程中的一个状态流转Bug\n\n## 今日重点\n- AI问答重构方案已获团队共识，明天开始编码\n- 微服务拆分方案需要进一步细化数据库分库策略\n\n## 存在问题\n- 风控模型AUC仍然偏低，需要更多违约样本\n\n## 明日计划\n- 开始AI问答模块重构编码\n- 安排与招商银行的技术对接会议""",
    },
    {
        "summary_date": d(-3),
        "previous_day_plan": "开始AI问答模块重构编码，安排与招商银行技术对接会议",
        "content": """## 今日完成\n- 启动AI问答模块重构，新增search_clients/search_projects/search_tasks等函数\n- 与招商银行确认接口对接协议从SOAP迁移到REST\n- 完成供应链大屏实时推送方案的技术评审\n\n## 今日重点\n- 接口协议变更影响面较大，需要更新审批流程引擎的对接代码\n- 大屏延迟优化方案确定使用WebSocket + 增量推送\n\n## 存在问题\n- REST接口的签名算法与现有SOAP方案不兼容，需要重写签名模块\n\n## 明日计划\n- 继续AI问答重构的query_service.py重写\n- 对接银行核心系统接口开发""",
    },
    {
        "summary_date": d(-2),
        "previous_day_plan": "继续AI问答重构，对接银行核心系统接口开发",
        "content": """## 今日完成\n- query_service.py核心逻辑重写完成，实现多表查询路由和全局搜索\n- 银行核心系统接口完成授信查询部分的编码\n- 标注工具审核流程Bug修复已部署到测试环境\n\n## 今日重点\n- AI问答现在可以查询客户、项目、任务、文件等多个业务表\n- 银行接口开发进度正常，预计明天完成放款接口\n\n## 存在问题\n- 小米供应链大屏的WebSocket方案需要额外的中间件支持\n\n## 明日计划\n- 生成测试数据开始完整功能验证\n- 完成银行接口的放款查询部分\n- 安排ERP财务模块第二轮UAT测试""",
    },
    {
        "summary_date": d(-1),
        "previous_day_plan": "完成测试数据生成和银行放款接口开发",
        "content": """## 今日完成\n- 编写seed_data.py生成完整测试数据（5客户/8项目/20任务）\n- 银行放款接口编码完成，进入自测阶段\n- 华润ERP财务模块第二轮UAT测试通过率92%\n\n## 今日重点\n- 测试数据覆盖了全模块，AI问答可以验证各种查询场景\n- 银行两个核心接口（授信+放款）都已编码完成\n\n## 存在问题\n- UAT中固定资产模块有3个用例未通过，涉及折旧计算逻辑\n\n## 明日计划\n- 修复ERP固定资产折旧计算问题\n- 银行接口联调测试\n- 周报整理""",
    },
    {
        "summary_date": d(0),
        "previous_day_plan": "修复ERP折旧计算，银行接口联调，整理周报",
        "content": """## 今日完成\n- 完成银行核心系统接口联调测试，授信和放款接口均通过\n- ERP固定资产折旧计算逻辑修复，UAT回归测试通过\n- 整理本周工作周报\n\n## 今日重点\n- 信贷审批系统对接银行接口部分基本完成，下一步是信用评估模块\n- ERP系统UAT全部通过，可以准备上线\n\n## 存在问题\n- 风控模型AUC仍然不达标，需要下周重点攻克\n\n## 下周计划\n- 风控模型优化\n- 信用评估模块开发启动\n- 供应链大屏性能优化\n- 物业管理系统第一期开发启动""",
    },
]

# ── 时间轴事件（手动构造，保证丰富度）──
# 格式: (event_type, title, description, related_type, related_id, project_id, client_id, event_date)
TIMELINE_EVENTS = [
    # ── 客户创建 ──
    ("client_created", "创建客户: 招商银行-企业信贷部", "负责企业信贷审批流程的数字化转型", "client", 1, None, 1, d(-30)),
    ("client_created", "创建客户: 字节跳动-AI平台部", "AI基础设施团队", "client", 2, None, 2, d(-28)),
    ("client_created", "创建客户: 华润集团-数字化转型办", "集团层面推动ERP系统升级", "client", 3, None, 3, d(-25)),
    ("client_created", "创建客户: 小米科技-供应链管理部", "供应链数据可视化需求", "client", 4, None, 4, d(-20)),
    ("client_created", "创建客户: 万科地产-物业管理部", "物业管理系统现代化重构", "client", 5, None, 5, d(-15)),

    # ── 项目创建 ──
    ("project_created", "创建项目: 内部研发效能平台", "公司内部使用的研发效能工具集", "project", 8, 8, None, d(-30)),
    ("project_created", "创建项目: 企业信贷审批系统 v2", "重构现有信贷审批流程", "project", 1, 1, 1, d(-28)),
    ("project_created", "创建项目: AI模型训练平台搭建", "搭建内部GPU集群管理平台", "project", 3, 3, 2, d(-26)),
    ("project_created", "创建项目: 智能风控模型开发", "基于机器学习的风险控制模型", "project", 2, 2, 1, d(-25)),
    ("project_created", "创建项目: ERP系统升级改造", "ERP系统升级至SAP S/4HANA", "project", 5, 5, 3, d(-22)),
    ("project_created", "创建项目: 数据标注工具开发", "开发内部数据标注平台", "project", 4, 4, 2, d(-20)),
    ("project_created", "创建项目: 供应链可视化大屏", "实时供应链数据监控大屏", "project", 6, 6, 4, d(-18)),
    ("project_created", "创建项目: 物业管理系统重构", "微服务架构重构物业系统", "project", 7, 7, 5, d(-14)),

    # ── 任务创建 ──
    ("task_created", "创建任务: 代码审查机器人集成", "", "task", 20, 8, None, d(-26)),
    ("task_created", "创建任务: 完成需求文档评审", "", "task", 1, 1, 1, d(-28)),
    ("task_created", "创建任务: 需求调研与技术选型", "", "task", 10, 3, 2, d(-24)),
    ("task_created", "创建任务: 搭建审批流程引擎", "", "task", 2, 1, 1, d(-24)),
    ("task_created", "创建任务: 数据清洗与特征工程", "", "task", 6, 2, 1, d(-22)),
    ("task_created", "创建任务: 旧系统数据迁移", "", "task", 15, 5, 3, d(-18)),
    ("task_created", "创建任务: 标注工具UI设计", "", "task", 13, 4, 2, d(-16)),
    ("task_created", "创建任务: 风控模型训练与调参", "", "task", 7, 2, 1, d(-15)),
    ("task_created", "创建任务: 多数据源接入与清洗", "", "task", 17, 6, 4, d(-14)),
    ("task_created", "创建任务: 搭建GPU集群管理环境", "", "task", 11, 3, 2, d(-12)),
    ("task_created", "创建任务: 对接银行核心系统接口", "", "task", 3, 1, 1, d(-10)),

    # ── 任务完成 ──
    ("task_completed", "完成任务: 完成需求文档评审", "需求评审通过，进入开发阶段", "task", 1, 1, 1, d(-24)),
    ("task_completed", "完成任务: 代码审查机器人集成", "SonarQube+AI Review已集成到CI流程", "task", 20, 8, None, d(-21)),
    ("task_completed", "完成任务: 需求调研与技术选型", "确定使用Kubeflow作为训练平台底座", "task", 10, 3, 2, d(-21)),
    ("task_completed", "完成任务: 数据清洗与特征工程", "提取215维特征变量", "task", 6, 2, 1, d(-19)),
    ("task_completed", "完成任务: 搭建审批流程引擎", "流程引擎上线，支持10种审批模板", "task", 2, 1, 1, d(-16)),
    ("task_completed", "完成任务: 旧系统数据迁移", "10年历史数据迁移完成，数据一致性校验通过", "task", 15, 5, 3, d(-13)),
    ("task_completed", "完成任务: 标注工具UI设计", "设计稿通过评审，进入前端开发", "task", 13, 4, 2, d(-11)),
    ("task_completed", "完成任务: 多数据源接入与清洗", "ERP/WMS/TMS三系统数据接入完成", "task", 17, 6, 4, d(-7)),

    # ── 任务状态变更（进行中）──
    ("task_status_changed", "任务状态变更: 对接银行核心系统接口", "todo → doing", "task", 3, 1, 1, d(-8)),
    ("task_status_changed", "任务状态变更: 风控模型训练与调参", "todo → doing", "task", 7, 2, 1, d(-12)),
    ("task_status_changed", "任务状态变更: 搭建GPU集群管理环境", "todo → doing", "task", 11, 3, 2, d(-10)),
    ("task_status_changed", "任务状态变更: 财务模块UAT测试", "todo → doing", "task", 16, 5, 3, d(-4)),
    ("task_status_changed", "任务状态变更: 大屏前端可视化开发", "todo → doing", "task", 18, 6, 4, d(-3)),
    ("task_status_changed", "任务状态变更: 标注审核流程开发", "todo → doing", "task", 14, 4, 2, d(-4)),
    ("task_status_changed", "任务状态变更: 微服务架构设计与数据库建模", "todo → doing", "task", 19, 7, 5, d(-2)),

    # ── 文件相关 ──
    ("file_uploaded", "上传文件: 信贷审批需求文档v3.docx", "", "file", 1, 1, 1, d(-27)),
    ("file_summarized", "AI总结文件: 信贷审批需求文档v3.docx", "提取了15个关键需求和32个功能点", "file", 1, 1, 1, d(-27)),
    ("file_uploaded", "上传文件: AI训练平台技术选型报告.pdf", "", "file", 2, 3, 2, d(-23)),
    ("file_summarized", "AI总结文件: AI训练平台技术选型报告.pdf", "Kubeflow vs Ray vs Determined AI综合对比", "file", 2, 3, 2, d(-23)),
    ("file_uploaded", "上传文件: 华润ERP数据迁移方案.xlsx", "", "file", 3, 5, 3, d(-17)),
    ("file_uploaded", "上传文件: 供应链大屏PRD_v2.md", "", "file", 4, 6, 4, d(-13)),

    # ── 随手记 ──
    ("daily_note", "随手记: 早上和招商银行张行长通了电话...", "", "daily_note", 1, None, 1, d(-3)),
    ("daily_note", "随手记: 下午3点字节跳动王总监来公司做技术交流...", "", "daily_note", 2, None, 2, d(-5)),
    ("daily_note", "随手记: 发现风控模型的AUC只有0.78...", "", "daily_note", 3, None, 1, d(-8)),
    ("daily_note", "随手记: 小米的陈经理反馈供应链大屏的实时数据延迟太大...", "", "daily_note", 4, None, 4, d(-2)),
    ("daily_note", "随手记: 今天整理了一下近两周的工作内容，准备写周报...", "", "daily_note", 5, None, None, d(-1)),
    ("daily_note", "随手记: 华润ERP数据迁移中发现旧系统字符编码问题...", "", "daily_note", 6, None, 3, d(-12)),
    ("daily_note", "随手记: 物业管理系统重构的第一次迭代计划定下来了...", "", "daily_note", 7, None, 5, d(-9)),
    ("daily_note", "随手记: 内部效能平台的自动化测试流水线覆盖率达到了85%...", "", "daily_note", 8, None, None, d(-15)),
    ("daily_note", "随手记: 和团队讨论了AI问答模块的重构方案...", "", "daily_note", 9, None, None, d(-4)),
    ("daily_note", "随手记: 今天和万科赵总确认了下一阶段的合作计划...", "", "daily_note", 10, None, 5, d(-6)),

    # ── 每日总结 ──
    ("daily_summary", "生成每日总结: " + d(-4), "", "daily_summary", 1, None, None, d(-4)),
    ("daily_summary", "生成每日总结: " + d(-3), "", "daily_summary", 2, None, None, d(-3)),
    ("daily_summary", "生成每日总结: " + d(-2), "", "daily_summary", 3, None, None, d(-2)),
    ("daily_summary", "生成每日总结: " + d(-1), "", "daily_summary", 4, None, None, d(-1)),
    ("daily_summary", "生成每日总结: " + d(0), "", "daily_summary", 5, None, None, d(0)),

    # ── AI问答示例（模拟历史查询）──
    ("ai_query", "AI问答: 本周完成了哪些任务？", "本周完成了3个任务：标注工具UI设计、多数据源接入与清洗、AI问答模块重构...", "ai_query", 0, None, None, d(-1)),
    ("ai_query", "AI问答: 招商银行最近有什么进展？", "招商银行有2个项目在推进：信贷审批系统已对接核心接口，风控模型正在调参...", "ai_query", 0, 1, 1, d(-1)),
]


# ── 清理和插入逻辑 ─────────────────────────────────────────

def clear_all():
    """清空所有表数据"""
    from database.init_db import init_database
    init_database()
    tables = ["relations", "tags", "timeline_events", "daily_summaries",
              "daily_notes", "files", "tasks", "projects", "clients"]
    for t in tables:
        execute(f"DELETE FROM {t}")
    print("已清空所有数据表")


def seed_clients():
    for c in CLIENTS:
        insert(
            """INSERT INTO clients (id, name, description, contact_info, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (c["id"], c["name"], c["description"], c["contact_info"], c["created"], c["created"]),
        )
    print(f"  ✓ 插入 {len(CLIENTS)} 个客户")


def seed_projects():
    for p in PROJECTS:
        cid = None if p["client_id"] is None else p["client_id"]
        insert(
            """INSERT INTO projects (id, name, description, status, client_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (p["id"], p["name"], p["description"], p["status"], cid, p["created"], p["created"]),
        )
    print(f"  ✓ 插入 {len(PROJECTS)} 个项目")


def seed_tasks():
    for t in TASKS:
        pid = None if t["project_id"] is None else t["project_id"]
        cid = None if t["client_id"] is None else t["client_id"]
        completed = t.get("completed")
        insert(
            """INSERT INTO tasks (id, title, description, status, priority, due_date,
               project_id, client_id, created_at, updated_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (t["id"], t["title"], t["description"], t["status"], t["priority"],
             t["due_date"], pid, cid, t["created"], t["created"], completed),
        )
    print(f"  ✓ 插入 {len(TASKS)} 个任务")


def seed_notes():
    for i, n in enumerate(DAILY_NOTES):
        insert(
            """INSERT INTO daily_notes (id, content, note_date, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (i + 1, n["content"], n["note_date"], n["note_date"], n["note_date"]),
        )
    print(f"  ✓ 插入 {len(DAILY_NOTES)} 条随手记")


def seed_summaries():
    for i, s in enumerate(DAILY_SUMMARIES):
        insert(
            """INSERT INTO daily_summaries (id, summary_date, content, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (i + 1, s["summary_date"], s["content"], s["summary_date"], s["summary_date"]),
        )
    print(f"  ✓ 插入 {len(DAILY_SUMMARIES)} 条每日总结")


def seed_files():
    files_data = [
        {"id": 1, "filename": "信贷审批需求文档v3.docx", "file_type": ".docx", "tags": "需求,银行,审批", "summary": "招商银行企业信贷审批系统需求文档第三版，包含15个关键需求和32个功能点，覆盖贷前、贷中、贷后全流程", "project_id": 1, "client_id": 1, "created": d(-27)},
        {"id": 2, "filename": "AI训练平台技术选型报告.pdf", "file_type": ".pdf", "tags": "AI,技术选型,Kubeflow", "summary": "综合对比Kubeflow、Ray、Determined AI三个训练平台方案，推荐使用Kubeflow作为底座", "project_id": 3, "client_id": 2, "created": d(-23)},
        {"id": 3, "filename": "华润ERP数据迁移方案.xlsx", "file_type": ".xlsx", "tags": "ERP,数据迁移,SAP", "summary": "详细的数据迁移方案，包含10年历史数据的清洗规则、转换映射表和校验方案", "project_id": 5, "client_id": 3, "created": d(-17)},
        {"id": 4, "filename": "供应链大屏PRD_v2.md", "file_type": ".md", "tags": "供应链,大屏,PRD", "summary": "供应链可视化大屏产品需求文档v2，定义了实时监控、预警、下钻分析三大功能模块", "project_id": 6, "client_id": 4, "created": d(-13)},
    ]
    for f in files_data:
        pid = None if f["project_id"] is None else f["project_id"]
        cid = None if f["client_id"] is None else f["client_id"]
        insert(
            """INSERT INTO files (id, filename, file_path, file_type, summary, tags,
               project_id, client_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (f["id"], f["filename"], f"/data/uploads/{f['filename']}", f["file_type"],
             f["summary"], f["tags"], pid, cid, f["created"], f["created"]),
        )
    print(f"  ✓ 插入 {len(files_data)} 个文件")


def seed_timeline_events():
    from utils.date_utils import now_str
    count = 0
    for evt in TIMELINE_EVENTS:
        event_type, title, desc, rel_type, rel_id, proj_id, client_id, event_date = evt
        insert(
            """INSERT INTO timeline_events
               (event_type, title, description, related_type, related_id,
                project_id, client_id, event_date, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_type, title, desc, rel_type, rel_id,
             proj_id, client_id, event_date, event_date),
        )
        count += 1
    print(f"  ✓ 插入 {count} 条时间轴事件")


def seed_relations():
    """为所有测试数据创建 relations 表关联记录"""
    from services.relation_service import add_relation

    count = 0
    # project → client
    for p in PROJECTS:
        if p.get("client_id"):
            add_relation("project", p["id"], "client", p["client_id"], "belongs_to",
                        f"项目「{p['name']}」属于该客户")
            count += 1

    # task → project + task → client
    for t in TASKS:
        if t.get("project_id"):
            add_relation("task", t["id"], "project", t["project_id"], "belongs_to",
                        f"任务「{t['title']}」属于该项目")
            count += 1
        if t.get("client_id"):
            add_relation("task", t["id"], "client", t["client_id"], "belongs_to",
                        f"任务「{t['title']}」属于该客户")
            count += 1

    # file → project + file → client
    files_data = [
        {"id": 1, "project_id": 1, "client_id": 1, "filename": "信贷审批需求文档v3.docx"},
        {"id": 2, "project_id": 3, "client_id": 2, "filename": "AI训练平台技术选型报告.pdf"},
        {"id": 3, "project_id": 5, "client_id": 3, "filename": "华润ERP数据迁移方案.xlsx"},
        {"id": 4, "project_id": 6, "client_id": 4, "filename": "供应链大屏PRD_v2.md"},
    ]
    for f in files_data:
        if f.get("project_id"):
            add_relation("file", f["id"], "project", f["project_id"], "belongs_to",
                        f"文件「{f['filename']}」属于该项目")
            count += 1
        if f.get("client_id"):
            add_relation("file", f["id"], "client", f["client_id"], "belongs_to",
                        f"文件「{f['filename']}」属于该客户")
            count += 1

    print(f"  ✓ 插入 {count} 条关系记录")


def seed():
    is_dry = "--dry" in sys.argv

    if is_dry:
        print("=" * 60)
        print("DRY RUN — 仅预览，不写入数据库")
        print("=" * 60)
        print()
        print(f"  客户:     {len(CLIENTS)} 个")
        for c in CLIENTS:
            print(f"    - {c['name']} ({c['created']})")
        print()
        print(f"  项目:     {len(PROJECTS)} 个")
        for p in PROJECTS:
            cname = next((c['name'] for c in CLIENTS if c['id'] == p['client_id']), "内部")
            print(f"    - {p['name']} [{p['status']}] → {cname} ({p['created']})")
        print()
        print(f"  任务:     {len(TASKS)} 个")
        status_count = {}
        for t in TASKS:
            s = t['status']
            status_count[s] = status_count.get(s, 0) + 1
        print(f"    状态分布: {status_count}")
        print()
        print(f"  随手记:   {len(DAILY_NOTES)} 条")
        print(f"  每日总结: {len(DAILY_SUMMARIES)} 条")
        print(f"  时间轴:   {len(TIMELINE_EVENTS)} 条")
        print(f"  文件:     4 个")
        print()
        print("运行 python seed_data.py 写入数据")
        return

    print("=" * 60)
    print("AI办公助理 — 测试数据生成器")
    print("=" * 60)
    print()

    clear_all()
    print()

    print("插入数据:")
    seed_clients()
    seed_projects()
    seed_tasks()
    seed_notes()
    seed_summaries()
    seed_files()
    seed_timeline_events()
    seed_relations()

    # 重置SQLite自增序列
    execute("DELETE FROM sqlite_sequence")
    for t in ["clients", "projects", "tasks", "files", "daily_notes",
              "daily_summaries", "timeline_events"]:
        max_id = fetch_all(f"SELECT MAX(id) as m FROM {t}")
        if max_id and max_id[0]["m"]:
            execute(f"INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)",
                    (t, max_id[0]["m"]))

    print()
    print("=" * 60)
    print("数据生成完成!")
    print("=" * 60)
    print(f"  客户:       {len(CLIENTS)} 个")
    print(f"  项目:       {len(PROJECTS)} 个")
    print(f"  任务:       {len(TASKS)} 个")
    print(f"  随手记:     {len(DAILY_NOTES)} 条")
    print(f"  每日总结:   {len(DAILY_SUMMARIES)} 条")
    print(f"  文件:       4 个")
    print(f"  时间轴事件: {len(TIMELINE_EVENTS)} 条")
    print()
    print("启动应用: streamlit run app.py")
    print("试试这些问题:")
    print('  "招商银行最近有什么进展？"')
    print('  "有哪些未完成的高优先级任务？"')
    print('  "本周完成了哪些任务？"')
    print('  "项目有哪些？"')
    print('  "字节跳动的项目情况如何？"')


if __name__ == "__main__":
    seed()
