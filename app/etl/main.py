import os
import sys
import logging
import pandas as pd
import duckdb
from sqlalchemy import create_engine
from urllib.parse import quote_plus

# 添加项目根目录到 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.config.config import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_mysql_engine():
    db = settings.database.mysql
    encoded_password = quote_plus(db.password)
    db_url = f"mysql+pymysql://{db.user}:{encoded_password}@{db.host}:{db.port}/{db.database}"
    return create_engine(db_url)

def get_duckdb_conn():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), settings.database.duckdb.path)
    # 确保 data 目录存在
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return duckdb.connect(db_path)

def init_dw_schema(conn):
    schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'sql', 'schema_dw.sql')
    with open(schema_path, 'r', encoding='utf-8') as f:
        sql = f.read()
    conn.execute(sql)
    logger.info("✅ 数据仓库 DDL (schema_dw.sql) 执行完毕，表结构已就绪.")

def extract_from_mysql(engine):
    """从 MySQL 提取所有需要的数据 (ODS 层概念)"""
    logger.info("正在从 MySQL 业务库中抽取全量数据...")
    df_users = pd.read_sql("SELECT * FROM users", engine)
    df_models = pd.read_sql("SELECT * FROM ai_models", engine)
    df_api_keys = pd.read_sql("SELECT key_id, user_id, key_name, is_active FROM api_keys", engine)
    # 对于实际大数据量项目，这里会使用增量抽取。由于我们目前记录不多(10~20万)，全量抽取秒回
    df_logs = pd.read_sql("SELECT * FROM request_logs_raw", engine)
    df_billing = pd.read_sql("SELECT * FROM billing_orders", engine)
    return df_users, df_models, df_api_keys, df_logs, df_billing

def validate_and_clean(df_logs, df_billing):
    """
    Data Quality (DQ) 环节：对原始数据进行清洗和约束校验
    """
    dq_stats = {"original_logs": len(df_logs), "original_billing": len(df_billing)}
    
    # 1. 日志去重 (防止重试导致的重复记录)
    df_logs = df_logs.drop_duplicates(subset=['request_id'], keep='first')
    dq_stats["deduplicated_logs"] = dq_stats["original_logs"] - len(df_logs)

    # 2. 负值纠正：Token 和 Latency 不能为负
    # 将负值重置为 0 或剔除，这里我们选择剔除明显异常的脏数据
    valid_mask = (df_logs['prompt_token_count'] >= 0) & \
                 (df_logs['completion_token_count'] >= 0) & \
                 (df_logs['latency_ms'] > 0)
    df_logs = df_logs[valid_mask]
    dq_stats["invalid_numeric_logs"] = dq_stats["original_logs"] - dq_stats["deduplicated_logs"] - len(df_logs)

    # 3. 空值填充：将 error_code 为空的统一标记为 'NONE'
    df_logs['error_code'] = df_logs['error_code'].fillna('NONE')

    # 4. 财务流水校验：Amount 不能为空
    df_billing = df_billing.dropna(subset=['amount'])
    dq_stats["invalid_billing"] = dq_stats["original_billing"] - len(df_billing)

    logger.info(f"🛡️ Data Quality 检查完成: "
                f"去重 {dq_stats['deduplicated_logs']} 条, "
                f"过滤异常值 {dq_stats['invalid_numeric_logs']} 条.")
    
    return df_logs, df_billing

def transform_and_load(conn, df_users, df_models, df_api_keys, df_logs, df_billing):
    """在 DuckDB 内存中进行 Transform，并 Load 到星型架构事实表和维度表中"""
    logger.info("注册 DataFrame 到 DuckDB 进行内存级联算...")
    conn.register("src_users", df_users)
    conn.register("src_models", df_models)
    conn.register("src_api_keys", df_api_keys)
    conn.register("src_logs", df_logs)
    conn.register("src_billing", df_billing)

    # 1. 挂载和装配维度表: dim_model
    conn.execute("TRUNCATE TABLE dim_model")
    conn.execute("""
        INSERT INTO dim_model (model_id, provider, input_price_per_1M, output_price_per_1M)
        SELECT model_id, provider, input_price_per_1M, output_price_per_1M FROM src_models
    """)
    logger.info("🔧 维度表 [dim_model] 装载完成.")

    # 2. 挂载和装配维度表: dim_account
    # (简化的 SCD Type 2：目前只装入 as is 状态，如果真有缓慢变化维此处可延伸)
    conn.execute("TRUNCATE TABLE dim_account")
    conn.execute("""
        INSERT INTO dim_account (user_id, email, subscription_plan, valid_from, valid_to, is_current)
        SELECT user_id, email, subscription_plan, registration_date, NULL, TRUE
        FROM src_users
    """)
    logger.info("🔧 维度表 [dim_account] 装载完成.")

    # 3. 挂载和装配辅助维度表: dim_status_code
    conn.execute("TRUNCATE TABLE dim_status_code")
    conn.execute("""
        INSERT INTO dim_status_code (http_status, error_code, is_error)
        SELECT DISTINCT http_status, error_code, 
               CASE WHEN http_status >= 400 THEN TRUE ELSE FALSE END AS is_error
        FROM src_logs
    """)
    logger.info("🔧 维度表 [dim_status_code] 装载完成.")

    # 4. 挂载和装配维度表: dim_api_key
    conn.execute("TRUNCATE TABLE dim_api_key")
    conn.execute("""
        INSERT INTO dim_api_key (key_id, key_name, is_active)
        SELECT key_id, key_name, is_active FROM src_api_keys
    """)
    logger.info("🔧 维度表 [dim_api_key] 装载完成.")

    # 5. 装载核心事务事实表: fct_api_requests
    # 这里我们利用 DuckDB 极速的 SQL 能力完成大表的维表转换关联和复杂业务计算 (计算价格)
    logger.info("⚙️ 正在转换和挂载业务指标事实表 [fct_api_requests]...")
    conn.execute("TRUNCATE TABLE fct_api_requests")
    conn.execute("""
        INSERT INTO fct_api_requests (
            request_id, account_sk, model_sk, status_sk, key_sk,
            request_time, latency_ms, 
            prompt_tokens, completion_tokens, cost_usd
        )
        SELECT 
            l.request_id,
            a.account_sk,
            m.model_sk,
            s.status_sk,
            k_dim.key_sk,
            l.request_time,
            l.latency_ms,
            l.prompt_token_count,
            l.completion_token_count,
            -- 计算调用成本公式: tokens * price / 1_000_000
            (l.prompt_token_count * m.input_price_per_1M / 1000000.0) + 
            (l.completion_token_count * m.output_price_per_1M / 1000000.0) AS cost_usd
        FROM src_logs l
        -- 关联获得 user_id 及 Key 信息
        JOIN src_api_keys k_src ON l.key_id = k_src.key_id
        -- 找到代理键 (Surrogate Keys)
        JOIN dim_account a ON k_src.user_id = a.user_id AND a.is_current = TRUE
        JOIN dim_api_key k_dim ON l.key_id = k_dim.key_id
        JOIN dim_model m ON l.model_id = m.model_id
        JOIN dim_status_code s 
          ON l.http_status = s.http_status 
         AND (l.error_code = s.error_code OR (l.error_code IS NULL AND s.error_code IS NULL))
    """)
    inserted_facts = conn.execute("SELECT COUNT(*) FROM fct_api_requests").fetchone()[0]
    logger.info(f"📈 事务事实表 [fct_api_requests] 装载完成: 共 {inserted_facts} 行记录!")

    # 5. 装载资金交易事实表: fct_account_transactions
    logger.info("⚙️ 正在转换和挂载资金交易事实表 [fct_account_transactions]...")
    conn.execute("TRUNCATE TABLE fct_account_transactions")
    conn.execute("""
        INSERT INTO fct_account_transactions (
            transaction_id, account_sk, amount, order_type, 
            payment_method, transaction_status, created_at
        )
        SELECT 
            b.order_id,
            a.account_sk,
            b.amount,
            b.order_type,
            b.payment_method,
            b.transaction_status,
            b.created_at
        FROM src_billing b
        JOIN dim_account a ON b.user_id = a.user_id AND a.is_current = TRUE
    """)
    inserted_trans = conn.execute("SELECT COUNT(*) FROM fct_account_transactions").fetchone()[0]
    logger.info(f"📈 交易事实表 [fct_account_transactions] 装载完成: 共 {inserted_trans} 行记录!")

    # 6. 生成聚合快照事实表: fct_account_daily_snapshot
    logger.info("⚙️ 正在降维聚合生成每日快照事实表 [fct_account_daily_snapshot]...")
    conn.execute("TRUNCATE TABLE fct_account_daily_snapshot")
    conn.execute("""
        INSERT INTO fct_account_daily_snapshot (
            snapshot_date, account_sk, daily_requests, daily_tokens, daily_cost_usd
        )
        SELECT 
            CAST(request_time AS DATE) AS snapshot_date,
            account_sk,
            COUNT(*) AS daily_requests,
            SUM(prompt_tokens + completion_tokens) AS daily_tokens,
            SUM(cost_usd) AS daily_cost_usd
        FROM fct_api_requests
        GROUP BY 1, 2
    """)
    inserted_snapshots = conn.execute("SELECT COUNT(*) FROM fct_account_daily_snapshot").fetchone()[0]
    logger.info(f"📈 快照事实表 [fct_account_daily_snapshot] 装载完成: 共 {inserted_snapshots} 行记录.")

def run_etl():
    logger.info("=== 🚀 开始执行 ETL 批处理流水线 ===")
    
    try:
        mysql_engine = get_mysql_engine()
        duckdb_conn = get_duckdb_conn()
        
        # ODS/DWD 初始化
        init_dw_schema(duckdb_conn)
        
        # 抽取 (Extract)
        df_users, df_models, df_api_keys, df_logs_raw, df_billing_raw = extract_from_mysql(mysql_engine)
        
        # 清洗与校验 (Validate & Clean)
        df_logs, df_billing = validate_and_clean(df_logs_raw, df_billing_raw)

        # 转换并装载 (Transform & Load)
        transform_and_load(duckdb_conn, df_users, df_models, df_api_keys, df_logs, df_billing)
        
        duckdb_conn.close()
        logger.info("=== 🎉 ETL 流水线执行成功 (Data Warehouse 已就绪) ===")
        
    except Exception as e:
        logger.error(f"❌ ETL 运行失败: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    run_etl()
