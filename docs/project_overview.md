# NovaAPI-Analytics 项目概览 (Project Overview)

本文件汇总了“AI API 平台 SaaS”数据平台项目的核心背景、技术架构及开发规划，旨在为后续开发提供参考。

## 1. 项目愿景与目标
基于《数据仓库工具箱》（Kimball 理论）实践现代数据栈（Modern Data Stack）。
- **核心目标**：构建一个端到端的“数据模拟 -> 业务数据库 (OLTP) -> ETL/ELT -> 数据仓库 (OLAP) -> AI 增强分析 -> 可视化看板”的全链路系统。
- **业务场景**：**AI API 聚合服务 SaaS**（模拟类似 OpenAI API 中转平台的运行逻辑）。

## 2. 技术栈 (Tech Stack)
- **后端框架**: FastAPI (Python)
- **数据库**: 
  - **OLTP**: MySQL (符合 3NF 范式)
  - **OLAP**: DuckDB (轻量级/高性能)
  - **缓存**: Redis (提高指标查询性能)
- **分析与 AI**:
  - **统计学**: Scipy, Statsmodels (3σ 异常检测, 回归分析, 假设检验)
  - **机器学习**: Scikit-learn (聚类分析, 预测)
  - **大模型**: LLM API (用于数据诊断、归因分析及自动生成报告)
- **数据生成**: Python + Faker + 自定义分布规则
- **前端工具**: Streamlit (快速构建交互式数据看板)
- **部署**: Docker / Docker-compose

## 3. 核心架构设计

### 3.1 业务数据库 (OLTP - 3NF)
- **users**: 用户基础信息、订阅版本。
- **api_keys**: 用户密钥映射。
- **ai_models**: 模型信息及单价配置。
- **request_logs_raw**: 原始请求日志（高频写入）。
- **billing_orders**: 财务流水记录。

### 3.2 数据仓库 (OLAP - 星型模型)
- **事实表**:
  - `fct_api_requests` (事务事实表): 记录每一笔请求，关注 Latency, Tokens, Cost。
  - `fct_account_transactions` (事务事实表): 记录资金变动。
  - `fct_account_daily_snapshot` (周期快照事实表): 每日账户余额及用量汇总。
- **维度表**:
  - `dim_account`: 采用 **SCD2 (缓慢变化维)** 记录用户订阅等级变更。
  - `dim_model`: 配置模型属性及计费标准。
  - `dim_status_code`: 异常归因辅助维度。

## 4. AI 与统计学赋能 (核心亮点)
- **接口稳定性分析**: 利用 **3σ原则 (Three-sigma Rule)** 或正态分布漂移检测 API 延迟异常。
- **财务预测**: 通过**线性/多项式回归**分析账户余额衰减速度，预测告警时间点。
- **用户行为特征**: 使用 **K-Means 聚类** 对用户进行画像分组（如“重度用户”、“刷量黑客”）。
- **AI 智能解读报告**: LLM 结合统计分析结果，自动生成人类可读的《数据异动诊断报告》。

## 5. 开发建议与迭代路线 (Roadmap)

### 第一阶段：MVP 基础构建 (V0.1 - 已完成)
- [x] **基础设施**: 定义 MySQL (OLTP) 与 DuckDB (OLAP) 结构。
- [x] **数据工厂**: 开发 Faker 数据模拟器，注入业务逻辑偏置（如昼夜节律、异常波动）。
- [x] **数据管道**: 实现 ODS -> DWD 的 ETL 流程，包含数据质量 (DQ) 校验与清洗。

### 第二阶段：指标建模与状态感知 (V0.2 - 当前重点)
- [ ] **DWS 汇总层**: 编写指标计算器，生成账户/模型维度的日聚合快照。
- [ ] **核心指标库**: 实现财务（月利润、ARPU）、运营（DAU、MAU、Retention）、性能（P99 Latency、错误率周环比）。
- [ ] **高性能查询**: 引入 **Redis** 缓存热点指标，构建基于 **FastAPI** 的数据查询 API 接口。

### 第三阶段：统计诊断与预测分析 (V0.3)
- [ ] **接口稳定性诊断**: 实现 **3σ (Three-sigma)** 异常检测算法，自动标记请求延迟抖动。
- [ ] **财务健康预测**: 利用 **线性/多项式回归** 拟合资金消耗速率，预测账户余额告警周期（Burn-rate Analysis）。
- [ ] **用户画像聚类**: 使用 **K-Means 算法** 对 API 使用习惯进行聚类，识别潜在“刷单黑客”或“重度企业客户”。

### 第四阶段：AI 看板与智能报告 (V1.0)
- [ ] **可视化看板**: 使用 **Streamlit** 搭建交互式数据仪表盘，展示核心 KPI 与异常清单。
- [ ] **AI 灵魂注入**: 集成 **LLM (如 GPT-4 / DeepSeek)** 接口，实现“一键生成数据异动诊断报告”。
- [ ] **工程化发布**: 完成 Docker 容器化部署，完善项目 README 与开发文档。

## 目录结构
```
NovaAPI-Analytics/
├── app/
│   ├── config/
│   │   ├── config.py           # 配置读取逻辑 (Pydantic)
│   │   └── settings.yaml       # 模型、定价及生成器设置
│   ├── generator/              # 数据模拟器 (ODS 层)
│   │   └── main.py             # 仿真生成 90 天的用户、订单与调用日志
│   ├── etl/                    # ETL 批处理流水线 (DW 层)
│   │   └── main.py             # MySQL -> DuckDB 的数据清洗与事实表装载
│   └── calculation/            # 指标计算引擎 (ADS 层/指标中心)
│       ├── core.py             # 核心框架 (Registry, 基类, Context)
│       ├── orchestrator.py     # 任务编排器 (驱动多阶段计算)
│       ├── data_utils.py       # 跨模型数据读取工具
│       └── calculators/        # 插件化指标检测器 (按需扩展指标)
├── docs/                       # 系统设计与分析指南
│   ├── project_overview.md
│   ├── analytics_metrics_guide.md  # 指标定义指南
│   └── 数据计算模块系统设计.md
├── sql/                        # 数据库 DDL 脚本
│   ├── schema_oltp.sql         # 业务库结构 (MySQL)
│   └── schema_dw.sql           # 数据仓库结构 (DuckDB)
├── data/                       # 存放 DuckDB 本地数据库文件
├── requirements.txt            # 项目依赖
└── .env                        # 敏感环境变量 (Local Only)
```

---
> [!NOTE]
> **开发警示**：
> - 避免在前端开发（Vue/React）上耗费过多精力，应专注于数据模型、ETL 逻辑及 AI 分析模块。
> - 保证模拟数据的“语义性”，确保 AI “读懂”的数据具有合理的业务逻辑偏移，否则分析结果将失去意义。
