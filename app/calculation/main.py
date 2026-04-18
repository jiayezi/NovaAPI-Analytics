# -*- coding: utf-8 -*-
"""
NovaAPI 指标计算入口程序
负责初始化环境并启动 AnalyticsOrchestrator 执行计算任务。
"""
import os
import sys
import logging
from datetime import datetime, timedelta
from sqlalchemy import create_engine

# 添加项目根目录到 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.config.config import settings
from app.calculation.orchestrator import AnalyticsOrchestrator
from app.calculation.calculators import import_all_calculators

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("calculation_main")

def get_duckdb_engine():
    """获取 DuckDB SQLAlchemy 引擎"""
    db_path = os.path.abspath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
        settings.database.duckdb.path
    ))
    # DuckDB 的 SQLAlchemy 连接字符串格式为 duckdb:///path/to/db
    engine = create_engine(f"duckdb:///{db_path}")
    return engine

def run_calculation_task():
    # 1. 自动发现并加载所有计算器 (确保 @register 装饰器被执行)
    logger.info("🔍 正在扫描并加载指标计算器...")
    import_all_calculators()

    # 2. 初始化引擎
    engine = get_duckdb_engine()

    # 3. 设定计算范围
    # 默认：计算过去 90 天到今天的数据，并进行边界闭合处理 (00:00:00 - 23:59:59)
    days_to_calc = settings.generator.simulation_days
    now = datetime.now()
    
    start_date = (now - timedelta(days=days_to_calc)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    logger.info(f"📅 计算周期设定: {start_date} 至 {end_date}")

    # 4. 初始化并在不同频率下执行
    orchestrator = AnalyticsOrchestrator(
        engine=engine,
        start_date=start_date,
        end_date=end_date
    )

    # 第一波：执行每日指标
    logger.info("🚀 启动 [Daily] 频率指标计算...")
    orchestrator.run_all(time_grain="daily")

    # 第二波：执行每月指标 (如果有)
    logger.info("🚀 启动 [Monthly] 频率指标计算...")
    orchestrator.run_all(time_grain="monthly")

    logger.info("🎉 所有阶段的频率计算已完成。")

if __name__ == "__main__":
    run_calculation_task()
