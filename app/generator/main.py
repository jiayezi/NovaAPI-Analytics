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
    logger.info(f"正在生成 {num_users} 个基础用户和 API Keys (包含用户升级演变以支持 SCD2)...")
    users = []
    api_keys = []
    plan_changes = []
    
    # 用户订阅分布： 70% Free, 25% Pro, 5% Enterprise
    tiers = np.random.choice(['free', 'pro', 'enterprise'], size=num_users, p=[0.70, 0.25, 0.05])
    
    # 基准起始时间
    base_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=settings.generator.simulation_days)

    change_id_counter = 1

    for i, tier in enumerate(tiers):
        # 随机注册时间在基准起始时间到现在的范围内 (以便分析新增长用户趋势)
        time_span = (datetime.now() - base_start).total_seconds()
        reg_seconds = random.uniform(0, time_span)
        reg_date = base_start + timedelta(seconds=int(reg_seconds))
        user_id = i+1
        initial_plan = tier
        upgrade_date = None
        current_plan = tier
        balance = 0

        # 模拟 SCD2 升级：如果是 Pro 或 Enterprise，有0.4的概率是中途升级上来的，有0.6的概率是一开始就是该等级
        if tier in ['pro', 'enterprise'] and random.random() < 0.4:
            # 模拟 SCD2 升级：尝试在注册之后安排一个升级时间
            # 我们确保升级时间在注册日之后，且在当前时间之前
            time_window = (datetime.now() - reg_date).total_seconds()
            if time_window > 86400 * 3: # 如果注册时间到现在超过3天，才模拟中途升级
                initial_plan = 'free' if tier == 'pro' else random.choice(['free', 'pro'])
                # 升级发生在注册 1 天后到当前时间的 80% 处
                upgrade_delay = random.uniform(86400, time_window * 0.8)
                upgrade_date = reg_date + timedelta(seconds=int(upgrade_delay))
            
                plan_changes.append({
                    'change_id': change_id_counter,
                    'user_id': user_id,
                    'old_plan': initial_plan,
                    'new_plan': current_plan,
                    'change_date': upgrade_date,
                    'change_reason': 'user_upgrade'
                })
                change_id_counter += 1
        
        # 模拟不同级别的最终资金 (根据最终状态)
        if current_plan == 'enterprise':
            balance = np.random.uniform(100, 1000)
        elif current_plan == 'pro':
            balance = np.random.uniform(20, 100)
        else:
            balance = np.random.uniform(0, 10)
            
        users.append({
            'user_id': user_id,
            'email': fake.unique.email(),
            'password_hash': fake.sha256(),
            'registration_date': reg_date,
            'subscription_plan': current_plan,
            'account_balance': round(balance, 4),
            'status': 1,
            # 辅助内部字段
            '_initial_plan': initial_plan,
            '_upgrade_date': upgrade_date
        })
        
        # Keys 
        num_k = random.randint(1, max_keys)
        for j in range(num_k):
            api_keys.append({
                'key_id': len(api_keys) + 1,
                'user_id': user_id,
                'key_name': f"{tier.title()}-Key-{fake.word()}",
                'api_key': "sk-nova-" + str(uuid.uuid4()),
                # Key 创建时间在注册之后，但不晚于现在
                'created_at': min(reg_date + timedelta(hours=random.randint(1, 10)), datetime.now()),
                'is_active': True
            })
            
    df_users = pd.DataFrame(users)
    df_keys = pd.DataFrame(api_keys)
    df_plan_changes = pd.DataFrame(plan_changes)
    return df_users, df_keys, df_plan_changes


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
    cheap_models = df_models[df_models['output_price_per_1M'] <= 12.0]['model_id'].tolist()
    expensive_models = df_models[df_models['output_price_per_1M'] > 12.0]['model_id'].tolist()
    
    # 挑选出“黑客用户”和“延迟异常模型”用于后续植入 AI 诊断案例
    # 挑选出“黑客用户”和“延迟异常模型”用于后续植入 AI 诊断案例
    # 警告：由于注册时间已改为随机，必须挑选在异常触发日之前已注册的用户
    hacker_day = 20
    anomaly_day = 15
    anomaly_model_id = "gpt-5.4" 

    hacker_candidates = df_users[
        (df_users['subscription_plan'] == 'free') & 
        (df_users['registration_date'].dt.date <= (start_date + timedelta(days=hacker_day)).date())
    ]
    
    if not hacker_candidates.empty:
        # 挑选符合条件的第一个或随机一个免费用户
        hacker_user_id = hacker_candidates.iloc[0]['user_id']
        hacker_key_id = df_keys[df_keys['user_id'] == hacker_user_id].iloc[0]['key_id']
    else:
        hacker_key_id = None
        logger.warning(f"⚠️ 未找到在第 {hacker_day} 天前注册的免费用户，黑客注入将跳过。")

    request_id_counter = 1
    
    for d in range(days):
        current_day = start_date + timedelta(days=d)
        is_weekend = current_day.weekday() >= 5
        
        for index, key in df_keys.iterrows():
            user = df_users[df_users['user_id'] == key['user_id']].iloc[0]
            
            # 业务规则：API 调用时间不能早于密钥创建时间
            if current_day.date() < key['created_at'].date(): # 必须按日期比较，因为 current_day 的时间固定是 00:00:00，而 key['created_at'] 通常会有时分秒（比如 14:30:00）
                continue
                
            tier = user['subscription_plan']
            
            # 动态支持 SCD2：如果用户有升级记录但数据模拟器生成当前请求日志时还没到升级日期，就使用初始的 Plan（升级前和升级后的请求数量和模型偏好是不同的）
            if pd.notna(user.get('_upgrade_date')) and current_day < user['_upgrade_date']:
                tier = user.get('_initial_plan', tier)
                
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
                
            # 黑客异常埋点：在指定的异常天，指定的免费用户产生爆发式请求
            if hacker_key_id and key['key_id'] == hacker_key_id and d == hacker_day:
                base_reqs += 5000 # 爆发性增长
                logger.info(f"🚨 [异常注入]: 黑客 (User {key['user_id']}, Key {key['key_id']}) 在第 {d} 天发起海量刷单 ({base_reqs} 级请求).")

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
                # “AI API 聚合服务 SaaS”的流量通常来自企业级应用（如 AI 扣子、智能客服、文档分析器），因此 Prompt 略大于 Completion 是符合目前行业 API 账单特征的
                completion_tokens = int(np.random.lognormal(mean=4.5, sigma=1.0))
                
                # max(5, ...)：确保输入 Token 至少为 5。min(..., ...)：对单次输入的长度做硬性限制。减去 2000 是为了留出足够的空间让模型生成回复，防止 Prompt 占满最大上下文。
                prompt_tokens = min(df_models[df_models['model_id']==model_id]['max_context'].values[0] - 2000, max(5, prompt_tokens))
                # max(1, ...)：确保输出 Token 至少为 1。min(8192, ...)：对单次回复的长度做硬性限制。
                completion_tokens = max(1, min(8192, completion_tokens))

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
                
                # 业务规则：API 调用时间既不能早于创建时间（针对密钥创建当天的请求时间），也不能晚于当前时刻
                if req_time < key['created_at'] or req_time > datetime.now():
                    continue
                
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


def simulate_billing_orders(df_users, days=30):
    """
    生成财务流水：
    1. 用户注册时的初始充值 (recharge)。
    2. Pro/Enterprise 用户的订阅费扣款 (subscription_fee)。
    3. 模拟周期性的用量结算 (usage_settlement)。
    """
    logger.info("正在生成配套的财务账单流水数据...")
    orders = []
    order_id_counter = 1
    
    for index, user in df_users.iterrows():
        curr_plan = user['subscription_plan']
        init_plan = user.get('_initial_plan', curr_plan)
        upgrade_date = user.get('_upgrade_date')
        reg_date = user['registration_date']
        
        def get_init_amount(p):
            if p == 'enterprise': return np.random.uniform(500, 2000)
            elif p == 'pro': return np.random.uniform(100, 300)
            return np.random.uniform(5, 50)
        
        # 初始充值
        orders.append({
            'order_id': order_id_counter,
            'user_id': user['user_id'],
            'amount': round(get_init_amount(init_plan), 4),
            'order_type': 'recharge',
            'payment_method': random.choice(['credit_card', 'paypal', 'alipay']),
            'transaction_status': 'completed',
            'created_at': reg_date + timedelta(minutes=random.randint(1, 60))
        })
        order_id_counter += 1
        
        # --- 订阅费逻辑 (含周期性续费) ---
        def add_subscription_fees(plan, start_dt, end_dt):
            nonlocal order_id_counter
            if plan == 'free':
                return
            
            sub_fee = -50.0 if plan == 'pro' else -500.0
            billing_date = start_dt + timedelta(hours=random.randint(1, 12))
            
            while billing_date < end_dt and billing_date < datetime.now():
                orders.append({
                    'order_id': order_id_counter,
                    'user_id': user['user_id'],
                    'amount': round(sub_fee, 4),
                    'order_type': 'subscription_fee',
                    'payment_method': 'credit_card' if random.random() > 0.3 else 'balance',
                    'transaction_status': 'completed',
                    'created_at': billing_date
                })
                order_id_counter += 1
                billing_date += timedelta(days=30) # 每 30 天续费一次

        # 处理初始阶段到升级前 (或到现在) 的订阅费
        # 如果有中途升级记录，则账单生成到升级日期结束（下一步会处理升级后的账单）。如果没有中途升级记录，则账单生成到当前时间
        sub_end_limit = upgrade_date if pd.notna(upgrade_date) else datetime.now()
        add_subscription_fees(init_plan, reg_date, sub_end_limit)
            
        # 模拟 SCD2 中途升级导致的充值与扣费
        if pd.notna(upgrade_date):
            # 升级时的充值
            orders.append({
                'order_id': order_id_counter,
                'user_id': user['user_id'],
                'amount': round(get_init_amount(curr_plan), 4),
                'order_type': 'recharge',
                'payment_method': 'credit_card',
                'transaction_status': 'completed',
                'created_at': upgrade_date - timedelta(minutes=random.randint(5, 30))
            })
            order_id_counter += 1
            
            # 升级后的周期性订阅费（账单从升级日期开始，每 30 天续费一次）
            add_subscription_fees(curr_plan, upgrade_date, datetime.now())
            
        # 随机零星充值 (独立循环：模拟用户余额不足时的补齐行为)
        # 根据等级设定目标充值周期：Pro/Enterprise 约为 30 天，Free 为 7-15 天
        recharge_time = reg_date + timedelta(days=random.randint(2, 5))
        while recharge_time < datetime.now():
            acting_tier = init_plan
            if pd.notna(upgrade_date) and recharge_time >= upgrade_date:
                acting_tier = curr_plan

            if acting_tier == 'enterprise':
                recharge_range, interval = (500, 2000), 30
            elif acting_tier == 'pro':
                recharge_range, interval = (50, 200), 30
            else:
                recharge_range, interval = (10, 30), random.randint(7, 15)

            orders.append({
                'order_id': order_id_counter,
                'user_id': user['user_id'],
                'amount': round(np.random.uniform(*recharge_range), 4),
                'order_type': 'recharge',
                'payment_method': 'credit_card',
                'transaction_status': 'completed',
                'created_at': recharge_time
            })
            order_id_counter += 1
            # 步进：目标周期 + 随机抖动 (确保 ±2 天抖动有效)
            recharge_time += timedelta(days=max(1, interval + random.randint(-2, 2)))

        # 周期性用量结算扣费 (独立循环：模拟混合计费模式下的后期结算)
        # 结算通常是阈值驱动或高频小额，这里模拟为不固定的周期性结算 (4-10 天一次)
        settlement_time = reg_date + timedelta(days=random.randint(3, 7))
        while settlement_time < datetime.now():
            acting_tier = init_plan
            if pd.notna(upgrade_date) and settlement_time >= upgrade_date:
                acting_tier = curr_plan

            if acting_tier == 'enterprise':
                usage_range = (100, 500)
            elif acting_tier == 'pro':
                usage_range = (10, 50)
            else:
                usage_range = (0.5, 5)

            orders.append({
                'order_id': order_id_counter,
                'user_id': user['user_id'],
                'amount': -round(np.random.uniform(*usage_range), 4),
                'order_type': 'usage_settlement',
                'payment_method': 'balance',
                'transaction_status': 'completed',
                'created_at': settlement_time + timedelta(hours=random.randint(1, 12))
            })
            order_id_counter += 1
            # 步进：4-10 天模拟一次结算
            settlement_time += timedelta(days=random.randint(4, 10))
            
    df_orders = pd.DataFrame(orders)
    df_orders = df_orders.sort_values(by='created_at').reset_index(drop=True)
    df_orders['order_id'] = range(1, len(df_orders) + 1)
    
    return df_orders


def export_or_insert_to_db(df_users, df_keys, df_plan_changes, df_models, df_logs, df_billing):
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
            conn.execute(text("TRUNCATE TABLE user_plan_changes;"))
            conn.execute(text("TRUNCATE TABLE users;"))
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
            
        df_users.to_sql('users', con=engine, if_exists='append', index=False)
        logger.info(f"✅ Users 导入成功: {len(df_users)} 行")
        
        if not df_plan_changes.empty:
            df_plan_changes.to_sql('user_plan_changes', con=engine, if_exists='append', index=False)
            logger.info(f"✅ User Plan Changes 导入成功: {len(df_plan_changes)} 行")
        
        df_keys.to_sql('api_keys', con=engine, if_exists='append', index=False)
        logger.info(f"✅ API Keys 导入成功: {len(df_keys)} 行")
        
        df_models.to_sql('ai_models', con=engine, if_exists='append', index=False)
        logger.info(f"✅ AI Models 导入成功: {len(df_models)} 行")

        df_billing.to_sql('billing_orders', con=engine, if_exists='append', index=False)
        logger.info(f"✅ Billing Orders 导入成功: {len(df_billing)} 行")

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
        if not df_plan_changes.empty:
            df_plan_changes.to_csv(os.path.join(data_dir, "user_plan_changes.csv"), index=False)
        df_keys.to_csv(os.path.join(data_dir, "api_keys.csv"), index=False)
        df_models.to_csv(os.path.join(data_dir, "ai_models.csv"), index=False)
        df_billing.to_csv(os.path.join(data_dir, "billing_orders.csv"), index=False)
        df_logs.to_csv(os.path.join(data_dir, "request_logs_raw.csv"), index=False)
        logger.info(f"📁 CSV 备份完毕在 {data_dir}!")


def main():
    logger.info("=== 🚀 开始生成具有统计学与业务分析特征的模拟数据 ===")
    
    num_users = settings.generator.initial_users
    max_keys = settings.generator.max_keys_per_user
    days = settings.generator.simulation_days
    
    df_models = generate_reference_data()
    df_users, df_keys, df_plan_changes = generate_users_and_keys(num_users=num_users, max_keys=max_keys)
    df_billing = simulate_billing_orders(df_users, days=days)
    df_logs = simulate_request_logs(df_keys, df_users, df_models, days=days)
    
    # 清理内部辅助字段
    df_users_clean = df_users.drop(columns=['_initial_plan', '_upgrade_date'])
    
    logger.info(f"🏁 测算完成！共计 {len(df_logs)} 条调用请求流日志.")
    
    # 导进数据库或生成CSV
    export_or_insert_to_db(df_users_clean, df_keys, df_plan_changes, df_models, df_logs, df_billing)
    logger.info("=== 全部流程生成结束 ===")

if __name__ == "__main__":
    main()
