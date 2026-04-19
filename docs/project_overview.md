# NovaAPI-Analytics 项目概览 (Project Overview)

本文件汇总了“AI API 平台 SaaS”数据平台项目的核心背景、技术架构及开发规划，旨在为后续开发提供参考。

## 1. 项目愿景与目标
基于《数据仓库工具箱》（Kimball 理论）实践现代数据栈（Modern Data Stack）。
- **核心目标**：构建一个端到端的“数据模拟 -> 业务数据库 (OLTP) -> ETL/ELT -> 数据仓库 (OLAP) -> AI 增强分析 -> 可视化看板”的全链路系统。
- **业务场景**：**AI API 聚合服务 SaaS**（模拟类似 OpenAI API 中转平台的运行逻辑）。

## 2. 技术栈 (Tech Stack)
- **后端语言**: Python 3.12+
- **数据库**: 
  - **OLTP**: MySQL (符合 3NF 范式，TB 级写入潜力)
  - **OLAP**: DuckDB (单机嵌入式高性能列存)
- **分析与 AI**:
  - **统计学**: Scipy, Statsmodels (3σ 异常检测, 回归分析)
  - **机器学习**: Scikit-learn (K-Means 聚类分析)
  - **大模型**: LLM API (用于数据诊断、归因分析及自动生成报告)
- **数据生成**: Python + Faker + 自定义分布规则
- **前端工具**: Streamlit (快速构建交互式数据看板)

## 3. 核心架构设计

### 3.1 业务数据库 (OLTP - 3NF)
- **users**: 用户基础信息、订阅版本。
- **api_keys**: 用户密钥映射。
- **ai_models**: 模型信息及单价配置。
- **request_logs_raw**: 原始请求日志（高频写入）。
- **billing_orders**: 财务流水记录。

### 3.2 数据仓库 (OLAP - 星型模型)
- **DWD 层 (事实表)**:
  - `fct_api_requests`: 事务事实表，记录单笔请求的消耗与成本。
- **DWM 层 (聚合快照)**:
  - `fct_account_daily_snapshot`: 账户维度日聚合（Token 拆分为 Prompt/Completion）。
  - `fct_model_daily_snapshot`: 模型维度日聚合（含 Latency Sum 与 Error Count）。
- **DWS/ADS 层 (指标与标签)**:
  - `dws_metric_value`: 数值型指标存储（EAV 模型）。
  - `dws_metric_struct`: 结构化指标存储（如留存矩阵 JSON）。
  - `ads_account_tags`: 用户画像标签池。
- **维度表**:
  - `dim_account`: 采用 **SCD2 (缓慢变化维)** 记录用户订阅等级变更。
  - `dim_model`: 配置模型属性及计费标准。
  - `dim_status_code`: 异常归因辅助维度。

## 4. AI 与统计学赋能 (项目灵魂)
- **接口稳定性分析**: 利用 **3σ原则 (Three-sigma Rule)** 或正态分布漂移检测 API 延迟异常，自动标记性能抖动。
- **财务健康预测**: 通过**线性/多项式回归**分析账户余额衰减速度（Burn-rate），预测余额耗尽的时间点并提前告警。
- **用户行为特征**: 使用 **K-Means 聚类** 对用户进行画像分组（如“科研重度用户”、“刷量黑客”、“长尾开发者”）。
- **AI 智能解读报告**: 集成 **LLM (GPT-4/DeepSeek)**，结合上述统计分析结果，自动生成人类可读的《月度数据异动诊断与优化建议报告》。

## 5. 指标计算引擎 (Calculation Engine)

### 5.1 核心组件
- **`BaseMetricCalculator`**: 抽象基类。包含 `metric_code`, `time_grain` (daily/monthly/weekly), `is_sql_mode` 等属性。
- **`MetricRegistry`**: 插件化注册表。使用装饰器 `@MetricRegistry.register(stage)` 实现自动发现。
- **`AnalyticsOrchestrator`**: 编排器。负责任务调度、环境上下文 (`CalculationContext`) 传递及数据幂等性清理（Delete-Before-Insert）。

### 5.2 计算模式
1.  **SQL 快速结算模式 (is_sql_mode=True)**: 直接在 DuckDB 内部执行 `INSERT INTO ... SELECT ...`。适用于简单的 COUNT/SUM/DISTINCT 聚合，效率最高。
2.  **Python+Pandas 模式 (is_sql_mode=False)**: 将数据读取到 DataFrame 中处理。适用于机器学习、留存矩阵构建、异常检测等复杂逻辑。

## 6. 指标计算器开发指南 (Development Guide)

### 6.1 新增指标流程
1.  在 `app/calculation/calculators/` 下创建 `.py` 文件并添加类。
2.  继承 `BaseMetricCalculator`。
3.  使用 `@MetricRegistry.register(CalculationStage.USER)` 等装饰器标记所属阶段。
4.  实现 `get_delete_sql`：定义如何根据日期范围清理旧数据，保证幂等。
5.  实现 `calculate_sql` 或 `calculate`。

### 6.2 开发最佳实践
- **SQL 优先**: 简单的聚合优先使用 `is_sql_mode=True`。
- **时间闭合**: 任务时间锁定为 `00:00:00` 至 `23:59:59`。
- **幂等性**: 每个计算器必须实现 `get_delete_sql`。

## 7. 开发迭代路线 (Roadmap)

### 第一阶段：MVP 基础构建 (已完成)
- [x] **基础设施**: 定义 MySQL 与 DuckDB 结构。
- [x] **数据工厂**: 开发 Faker 数据模拟器，注入业务偏置逻辑（如昼夜节律、异常波动）。
- [x] **数据管道**: 实现 ODS -> DWD/DWM 的 ETL 流程，包含数据质量校验。

### 第二阶段：指标建模与状态感知 (当前重点)
- [x] **DWS 汇总层**: 建立指标计算框架，实现全发现机制。
- [x] **核心指标库**: 实现 MAU、留存率 (Cohort Matrix)、每日全平台用量统计。
- [ ] **模型利润分析**: 实现各模型维度的 Revenue vs Cost 精准对比指标。

### 第三阶段：统计诊断与预测分析
- [ ] **接口稳定性诊断**: 实现 **3σ (Three-sigma)** 异常检测算法，自动标记请求延迟抖动。
- [ ] **财务健康预测**: 利用 **回归分析** 拟合资金消耗速率，预测告警周期。
- [ ] **用户画像聚类**: 使用 **K-Means 算法** 对 API 使用习惯进行聚类，识别潜在异常用户或高价值客户。

### 第四阶段：AI 看板与智能报告
- [ ] **可视化看板**: 使用 **Streamlit** 搭建仪表盘。
- [ ] **AI 灵魂注入**: 集成 **LLM**，实现“一键生成数据异动诊断报告”。

---
> [!NOTE]
> **开发警示**：
> - 避免在前端开发（Vue/React）上耗费过多精力，应专注于数据模型、ETL 逻辑及 AI 分析模块。
> - 保证模拟数据的“语义性”，确保 AI “读懂”的数据具有合理的业务逻辑偏移，否则分析结果将失去意义。
> - 写 SQL 时，要考虑 DuckDB 的语法特性（如占位符 `?`）。

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
│       ├── main.py             # 指标计算引擎入口
│       ├── core.py             # 核心框架 (Registry, 基类, Context)
│       ├── orchestrator.py     # 任务编排器 (驱动多阶段计算)
│       ├── data_utils.py       # 跨模型数据读取工具
│       └── calculators/        # 插件化指标检测器 (按需扩展指标)
├── docs/                       # 系统设计与分析指南
│   ├── project_overview.md
│   └── analytics_metrics_guide.md  # 指标定义指南
├── sql/                        # 数据库 DDL 脚本
│   ├── schema_oltp.sql         # 业务库结构 (MySQL)
│   └── schema_dw.sql           # 数据仓库结构 (DuckDB)
├── data/                       # 存放 DuckDB 本地数据库文件
└── requirements.txt            # 项目依赖
```
