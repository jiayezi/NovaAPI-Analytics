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
1. **MVP 阶段 (V0.1)**: 定义 DDL，开发数据模拟生成器（模拟偏态分布的 Latency 数据），跑通 ODS -> DWD 的基本 ETL 流程。
2. **可视化与指标化 (V0.2)**: 引入 FastAPI + Redis，使用 Streamlit 搭建基础指标看板（DAU, Latency, Token Usage）。
3. **AI 灵魂注入 (V0.3)**: 实现 3σ 检测脚本，集成 LLM 接口完成“一键智能分析”功能。
4. **工程化与开源 (V1.0)**: 容器化部署，完善 README 文档。

## 目录结构
```
NovaAPI-Analytics/
├── app/
│   ├── config/
│   │   ├── config.py       # 读取逻辑
│   │   └── settings.yaml   # 配置文件
│   ├── generator/          # 数据模拟器模块
│   ├── etl/                # ETL/ELT 逻辑 (MySQL -> DuckDB)
│   └── analytics/          # 统计学分析与 AI 诊断逻辑
├── sql/
│   ├── schema_oltp.sql     # MySQL DDL
│   └── schema_dw.sql       # DuckDB DDL
├── data/                   # 存放 DuckDB 数据库文件
└── requirements.txt
```

---
> [!NOTE]
> **开发警示**：
> - 避免在前端开发（Vue/React）上耗费过多精力，应专注于数据模型、ETL 逻辑及 AI 分析模块。
> - 保证模拟数据的“语义性”，确保 AI “读懂”的数据具有合理的业务逻辑偏移，否则分析结果将失去意义。
