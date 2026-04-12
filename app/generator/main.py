import os
import sys
import random
import logging
import uuid
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from faker import Faker
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

# 添加项目根目录到 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.config.config import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

fake = Faker()

def get_engine():
    db = settings.database.mysql
    encoded_password = quote_plus(db.password)
    db_url = f"mysql+pymysql://{db.user}:{encoded_password}@{db.host}:{db.port}/{db.database}"
    return create_engine(db_url)

def generate_reference_data():
    """生成 AI models 初始数据"""
    models = []
    for m in settings.ai_models:
        models.append({
            'model_id': m.model_id,
            'provider': m.provider,
            'input_price_per_1M': m.input_price_per_1M,
            'output_price_per_1M': m.output_price_per_1M,
            'max_context': m.max_context,
            'is_available': True
        })
    return pd.DataFrame(models)

def generate_users_and_keys(num_users, max_keys):
    """根据幂律分布和偏好生成用户极其具有代表性的属性"""
    logger.info(f"正在生成 {num_users} 个基础用户和 API Keys...")
    users = []
    api_keys = []
    
    # 用户订阅分布： 70% Free, 25% Pro, 5% Enterprise
    tiers = np.random.choice(['free', 'pro', 'enterprise'], size=num_users, p=[0.70, 0.25, 0.05])
    
    # 基准起始时间 (30天前的 0点)
    base_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=settings.generator.simulation_days)

    for i in range(1, num_users + 1):
        tier = tiers[i-1]
        
        # 模拟不同级别的初始资金
        if tier == 'enterprise':
            balance = np.random.uniform(100, 1000)
        elif tier == 'pro':
            balance = np.random.uniform(20, 100)
        else:
            balance = np.random.uniform(0, 10)
            
        reg_date = base_start - timedelta(days=random.randint(1, 30), hours=random.randint(0, 23))
            
        users.append({
            'user_id': i,
            'email': fake.unique.email(),
            'password_hash': fake.sha256(),
            'registration_date': reg_date,
            'subscription_plan': tier,
            'account_balance': round(balance, 4),
            'status': 1
        })
        
        # Keys 
        num_k = random.randint(1, max_keys)
        for _ in range(num_k):
            api_keys.append({
                'key_id': len(api_keys) + 1,
                'user_id': i,
                'key_name': f"{tier.title()}-Key-{fake.word()}",
                'api_key': "sk-nova-" + str(uuid.uuid4()).replace('-', ''),
                'created_at': reg_date + timedelta(hours=random.randint(1, 10)),
                'is_active': True
            })
            
    df_users = pd.DataFrame(users)
    df_keys = pd.DataFrame(api_keys)
    return df_users, df_keys


def simulate_request_logs(df_keys, df_users, df_models, days=30):
    """
    核心方法：生成具备统计学意义的仿真请求日志。
    注入特征：
    1. 昼夜节律 (Diurnal Cycles)：业务高峰通常在白天/工作日。
    2. 等级偏好：Enterprise 请求多，模型选用偏重旗舰版；Free 偏向便宜模型。
    3. 埋点异常1：“模型稳定性”异常。某一天特定模型的延迟(Latency)出现剧烈抖动(为 3-sigma 诊断做准备)。
    4. 埋点异常2：“黑客盗刷”异常。某个Free用户在特定时间点产生远超等级的极大并发。(为聚类/异常检测做准备)。
    """
    logger.info(f"正在进行 {days} 天的业务流量测算和日志模拟 (包含随机注入的数据异常)...")
    logs = []
    
    start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    
    # 将模型分类
    cheap_models = df_models[df_models['input_price_per_1M'] < 1.0]['model_id'].tolist()
    expensive_models = df_models[df_models['input_price_per_1M'] >= 1.0]['model_id'].tolist()
    
    # 挑选出“黑客用户”和“延迟异常模型”用于后续植入 AI 诊断案例
    hacker_key_id = df_keys[df_keys['user_id'].isin(df_users[df_users['subscription_plan'] == 'free']['user_id'])].iloc[0]['key_id']
    anomaly_model_id = "gpt-5.4" # 我们故意让 gpt-5.4 在第 15 天延迟翻倍
    anomaly_day = 15

    request_id_counter = 1
    
    for d in range(days):
        current_day = start_date + timedelta(days=d)
        is_weekend = current_day.weekday() >= 5
        
        for index, key in df_keys.iterrows():
            user = df_users[df_users['user_id'] == key['user_id']].iloc[0]
            tier = user['subscription_plan']
            
            # 用户一天发多少请求？根据等级决定
            if tier == 'enterprise':
                base_reqs = int(np.random.normal(500, 100)) # 企业用户日均 500 次
            elif tier == 'pro':
                base_reqs = int(np.random.normal(50, 15))   # Pro 50次
            else:
                base_reqs = int(np.random.lognormal(mean=1.0, sigma=1.0)) # Free长尾分布，大多很低
                
            # 周末流量打8折
            if is_weekend:
                base_reqs = int(base_reqs * 0.8)
                
            # 黑客异常埋点：在第20天，指定的免费用户盗刷十万级请求
            if key['key_id'] == hacker_key_id and d == 20:
                base_reqs += 5000 
                logger.info(f"🚨 [异常注入]: 黑客 (User {key['user_id']}, Key {key['key_id']}) 在第 {d} 天发起海量刷单 ({base_reqs} requests).")

            # 过滤无效负数请求
            base_reqs = max(0, base_reqs)
            
            # 生成该 Key 下当天的所有请求
            for _ in range(base_reqs):
                # 选模型：Free更爱便宜的，Enterprise更爱贵的
                if tier == 'free':
                    model_choices = cheap_models * 4 + expensive_models
                else:
                    model_choices = cheap_models + expensive_models * 3
                model_id = random.choice(model_choices)
                
                # Token 分布：服从对数正态分布 (多数短文本，少数长文本)
                prompt_tokens = int(np.random.lognormal(mean=5.5, sigma=1.2))
                completion_tokens = int(np.random.lognormal(mean=4.5, sigma=1.0))
                
                prompt_tokens = min(df_models[df_models['model_id']==model_id]['max_context'].values[0] - 2000, max(5, prompt_tokens))
                completion_tokens = max(1, min(8000, completion_tokens))

                # Latency 基础模拟: 与 Token 数正相关，外加基础延迟
                base_latency = 300 + completion_tokens * 15 # 每生成一个 Token 约需 15ms
                latency_ms = int(np.random.normal(base_latency, base_latency * 0.1))
                
                # Latency异常埋点：在第15天的 gpt-5.4 延迟全部膨胀3~6倍，伴随 429 和 500
                status_code = 200
                error_code = None
                
                if model_id == anomaly_model_id and d == anomaly_day:
                    latency_ms = int(latency_ms * np.random.uniform(3.0, 6.0))
                    # 30% 概率超时或宕机
                    err_rand = random.random()
                    if err_rand > 0.8:
                        status_code = 504
                        error_code = 'gateway_timeout'
                    elif err_rand > 0.7:
                        status_code = 429
                        error_code = 'rate_limit_exceeded'
                else:
                    # 正常情况也有极小概率错误
                    if random.random() > 0.99:
                        status_code = random.choice([400, 401, 403, 429, 500])
                        error_code = 'generic_error' if status_code >= 500 else 'client_error'

                # 时间生成：一天内的高斯分布（集中在白天核心时段）
                # 用均值在 14 点(下午2点)的正态分布构建
                hour = int(np.random.normal(loc=14, scale=4))
                hour = min(23, max(0, hour))
                minute = random.randint(0, 59)
                second = random.randint(0, 59)
                req_time = current_day.replace(hour=hour, minute=minute, second=second)
                
                logs.append({
                    'request_id': request_id_counter,
                    'key_id': key['key_id'],
                    'model_id': model_id,
                    'prompt_token_count': prompt_tokens,
                    'completion_token_count': completion_tokens,
                    'latency_ms': max(50, latency_ms),
                    'http_status': status_code,
                    'error_code': error_code,
                    'request_time': req_time
                })
                request_id_counter += 1
                
    if anomaly_day < days:
        logger.info(f"🚨 [异常注入]: {anomaly_model_id} 在第 {anomaly_day} 天经历了严重的请求堆积与高延迟异常.")
                
    df_logs = pd.DataFrame(logs)
    
    # 按时间排序以模拟真实写入顺序
    df_logs = df_logs.sort_values(by='request_time').reset_index(drop=True)
    df_logs['request_id'] = range(1, len(df_logs) + 1)
    
    return df_logs


def export_or_insert_to_db(df_users, df_keys, df_models, df_logs):
    """将数据保存至 MySQL 数据库"""
    try:
        engine = get_engine()
        # 测试连接
        with engine.connect() as conn:
            pass
        
        logger.info("成功连接到 MySQL 数据库! 正在批量导入数据...")
        
        # 按照外键依赖顺序写入
        # 设置 if_exists='append'，要求必须先建好结构，这里为了防止冲突我们先清空表
        with engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
            conn.execute(text("TRUNCATE TABLE billing_orders;"))
            conn.execute(text("TRUNCATE TABLE request_logs_raw;"))
            conn.execute(text("TRUNCATE TABLE ai_models;"))
            conn.execute(text("TRUNCATE TABLE api_keys;"))
            conn.execute(text("TRUNCATE TABLE users;"))
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
            
        df_users.to_sql('users', con=engine, if_exists='append', index=False)
        logger.info(f"✅ Users 导入成功: {len(df_users)} 行")
        
        df_keys.to_sql('api_keys', con=engine, if_exists='append', index=False)
        logger.info(f"✅ API Keys 导入成功: {len(df_keys)} 行")
        
        df_models.to_sql('ai_models', con=engine, if_exists='append', index=False)
        logger.info(f"✅ AI Models 导入成功: {len(df_models)} 行")

        # 为了防止 request logs 太大，分块导入
        chunk_size = 5000
        for i in range(0, len(df_logs), chunk_size):
            chunk = df_logs.iloc[i:i+chunk_size]
            chunk.to_sql('request_logs_raw', con=engine, if_exists='append', index=False)
        logger.info(f"✅ Request Logs 导入成功: {len(df_logs)} 行")

    except Exception as e:
        logger.warning(f"❌ 数据库连接或写入失败! {str(e)}")
        logger.info("我们将把数据输出为 CSV 备份在 /data 目录，供您后续手动处理...")
        
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
        os.makedirs(data_dir, exist_ok=True)
        
        df_users.to_csv(os.path.join(data_dir, "users.csv"), index=False)
        df_keys.to_csv(os.path.join(data_dir, "api_keys.csv"), index=False)
        df_models.to_csv(os.path.join(data_dir, "ai_models.csv"), index=False)
        df_logs.to_csv(os.path.join(data_dir, "request_logs_raw.csv"), index=False)
        logger.info(f"📁 CSV 备份完毕在 {data_dir}!")


def main():
    logger.info("=== 🚀 开始生成具有统计学与业务分析特征的模拟数据 ===")
    
    num_users = settings.generator.initial_users
    max_keys = settings.generator.max_keys_per_user
    days = settings.generator.simulation_days
    
    df_models = generate_reference_data()
    df_users, df_keys = generate_users_and_keys(num_users=num_users, max_keys=max_keys)
    df_logs = simulate_request_logs(df_keys, df_users, df_models, days=days)
    
    logger.info(f"🏁 测算完成！共计 {len(df_logs)} 条调用请求流日志.")
    
    # 导进数据库或生成CSV
    export_or_insert_to_db(df_users, df_keys, df_models, df_logs)
    logger.info("=== 全部流程生成结束 ===")

if __name__ == "__main__":
    main()
