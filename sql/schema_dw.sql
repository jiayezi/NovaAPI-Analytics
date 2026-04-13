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
    output_price_per_1M DOUBLE
);

CREATE SEQUENCE IF NOT EXISTS seq_status_sk START 1;
CREATE TABLE IF NOT EXISTS dim_status_code (
    status_sk INTEGER PRIMARY KEY DEFAULT nextval('seq_status_sk'),
    http_status INTEGER,
    error_code VARCHAR,
    is_error BOOLEAN
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
    request_time TIMESTAMP,
    latency_ms INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
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
    daily_tokens INTEGER,
    daily_cost_usd DOUBLE,
    PRIMARY KEY (snapshot_date, account_sk)
);
