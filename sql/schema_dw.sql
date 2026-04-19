-- NovaAPI-Analytics OLAP 数据仓库 DDL (DuckDB)
-- 采用 Kimball 维度建模理论设计的星型架构 (Star Schema)

-- ==========================================
-- 1. 维度表 (Dimension Tables)
-- ==========================================

CREATE SEQUENCE IF NOT EXISTS seq_account_sk START 1;
CREATE TABLE IF NOT EXISTS dim_account (
    account_sk INTEGER PRIMARY KEY DEFAULT nextval('seq_account_sk'),
    user_id INTEGER,
    email VARCHAR,
    subscription_plan VARCHAR,
    registration_date TIMESTAMP,
    valid_from TIMESTAMP,
    valid_to TIMESTAMP,
    is_current BOOLEAN
);

CREATE SEQUENCE IF NOT EXISTS seq_model_sk START 1;
CREATE TABLE IF NOT EXISTS dim_model (
    model_sk INTEGER PRIMARY KEY DEFAULT nextval('seq_model_sk'),
    model_id VARCHAR,
    provider VARCHAR,
    input_price_per_1M DOUBLE,
    output_price_per_1M DOUBLE,
    input_cost_per_1M DOUBLE,
    output_cost_per_1M DOUBLE
);

CREATE SEQUENCE IF NOT EXISTS seq_status_sk START 1;
CREATE TABLE IF NOT EXISTS dim_status_code (
    status_sk INTEGER PRIMARY KEY DEFAULT nextval('seq_status_sk'),
    http_status INTEGER,
    error_code VARCHAR,
    is_error BOOLEAN
);

CREATE SEQUENCE IF NOT EXISTS seq_key_sk START 1;
CREATE TABLE IF NOT EXISTS dim_api_key (
    key_sk INTEGER PRIMARY KEY DEFAULT nextval('seq_key_sk'),
    key_id INTEGER,
    key_name VARCHAR,
    is_active BOOLEAN
);


-- ==========================================
-- 2. 事实表 (Fact Tables)
-- ==========================================

-- 2.1 API 调用事务事实表 (Transaction Fact)
CREATE TABLE IF NOT EXISTS fct_api_requests (
    request_id BIGINT PRIMARY KEY,
    account_sk INTEGER,
    model_sk INTEGER,
    status_sk INTEGER,
    key_sk INTEGER,
    request_time TIMESTAMP,
    latency_ms INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    revenue_usd DOUBLE,
    cost_usd DOUBLE
);

-- 2.2 资金交易事实表 (Financial Transaction Fact)
CREATE TABLE IF NOT EXISTS fct_account_transactions (
    transaction_id BIGINT PRIMARY KEY,
    account_sk INTEGER,
    amount DOUBLE,
    order_type VARCHAR,
    payment_method VARCHAR,
    transaction_status VARCHAR,
    created_at TIMESTAMP
);

-- 2.3 账户账单周期快照事实表 (Periodic Snapshot Fact)
CREATE TABLE IF NOT EXISTS fct_account_daily_snapshot (
    snapshot_date DATE,
    account_sk INTEGER,
    daily_requests INTEGER,
    sum_prompt_tokens BIGINT,
    sum_completion_tokens BIGINT,
    daily_revenue_usd DOUBLE,
    daily_cost_usd DOUBLE,
    PRIMARY KEY (snapshot_date, account_sk)
);

-- 2.4 模型服务质量每日快照事实表
CREATE TABLE IF NOT EXISTS fct_model_daily_snapshot (
    snapshot_date DATE,
    model_sk INTEGER,
    daily_requests INTEGER,
    sum_prompt_tokens BIGINT,
    sum_completion_tokens BIGINT,
    daily_revenue_usd DOUBLE,
    daily_cost_usd DOUBLE,
    sum_latency_ms BIGINT,       -- 总延迟，用于计算平均响应时间
    error_requests INTEGER,      -- 错误请求数 (HTTP >= 400)
    PRIMARY KEY (snapshot_date, model_sk)
);

-- ==========================================
-- 3. 汇总层 (DWS - 指标中心化模型)
-- 核心原则：新增指标 = 新行，而不是新表或新列
-- ==========================================

-- 3.1 指标元数据注册表 (所有指标的口径定义)
CREATE TABLE IF NOT EXISTS meta_metric (
    metric_code VARCHAR PRIMARY KEY,  -- 'account.monthly.cost', 'model.daily.latency_p99'
    metric_name VARCHAR,              -- 中文名：'账户月度 API 成本'
    description VARCHAR,              -- 业务含义说明
    formula VARCHAR,                  -- 计算口径：'SUM(cost_usd) GROUP BY account, month'
    entity_type VARCHAR,              -- 主体类型：'account' / 'model' / 'platform'
    time_type VARCHAR,                -- 时间粒度：'day' / 'month' / 'year'
    status VARCHAR DEFAULT 'online'   -- 'draft' / 'online' / 'deprecated'
);

-- 3.2 通用指标数值表 (统一存储所有数值型汇总指标)
CREATE TABLE IF NOT EXISTS dws_metric_value (
    metric_code VARCHAR,    -- 关联 meta_metric
    entity_type VARCHAR,    -- 'account' / 'model' / 'platform'
    entity_id VARCHAR,      -- 主体 ID (account_sk 或 model_sk 的字符串形式)
    time_type VARCHAR,      -- 'day' / 'month' / 'year'
    time_id VARCHAR,        -- 时间标识：'2026-04', '2026-04-15', '2026'
    metric_value DOUBLE,
    created_at TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (metric_code, entity_type, entity_id, time_type, time_id)
);

-- 3.3 指标结构化结果表 (存储无法用单一数值表达的复合结果)
CREATE TABLE IF NOT EXISTS dws_metric_struct (
    metric_code VARCHAR,
    entity_type VARCHAR,
    entity_id VARCHAR,
    time_type VARCHAR,
    time_id VARCHAR,
    struct_type VARCHAR,    -- 'rank' / 'distribution' / 'segment' / 'forecast'
    struct_json VARCHAR,    -- JSON 结构化结果
    created_at TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (metric_code, entity_type, entity_id, time_type, time_id)
);

-- ==========================================
-- 4. 应用层 (ADS - AI 分析结果标签池)
-- ==========================================

-- 4.1 通用账户标签池 (存储 AI 模型输出的用户级标签)
CREATE TABLE IF NOT EXISTS ads_account_tags (
    account_sk INTEGER,
    tag_key VARCHAR,    -- 'segment_label', 'burn_rate', 'exhaust_date', 'churn_risk'
    tag_value VARCHAR,
    confidence DOUBLE,
    updated_at TIMESTAMP,
    PRIMARY KEY (account_sk, tag_key)
);

-- 4.2 通用模型标签池 (存储 AI 诊断的模型级标签)
CREATE TABLE IF NOT EXISTS ads_model_tags (
    model_sk INTEGER,
    tag_key VARCHAR,    -- 'stability_rank', 'anomaly_score'
    tag_value VARCHAR,
    updated_at TIMESTAMP,
    PRIMARY KEY (model_sk, tag_key)
);

