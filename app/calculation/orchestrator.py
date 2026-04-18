# -*- coding: utf-8 -*-
import logging
from typing import List, Optional, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

from app.calculation.core import MetricRegistry, CalculationStage, CalculationContext

logger = logging.getLogger(__name__)

class AnalyticsOrchestrator:
    """
    指标计算编排器
    负责按阶段、按逻辑顺序驱动不同的指标计算器运行。
    """
    
    def __init__(
        self, 
        engine: "Engine", 
        start_date: datetime,
        end_date: datetime,
        user_ids: Optional[List[int]] = None,
        model_ids: Optional[List[str]] = None,
        metadata: dict = None
    ):
        self.engine = engine
        self.start_date = start_date
        self.end_date = end_date
        self.ctx = CalculationContext(
            engine=engine,
            start_date=start_date,
            end_date=end_date,
            user_ids=user_ids,
            model_ids=model_ids,
            metadata=metadata or {}
        )

    def run_all(self, time_grain: Optional[str] = None):
        """
        执行指标计算任务
        :param time_grain: 可选，按时间粒度过滤 (daily/monthly/weekly)，如果不传则执行全量。
        """
        logger.info(f"🚀 开始执行指标计算任务: {self.start_date.date()} -> {self.end_date.date()} (频率: {time_grain or 'ALL'})")
        
        # 按 CalculationStage 的定义顺序依次执行
        for stage in CalculationStage:
            self._run_stage(stage, time_grain=time_grain)
        
        logger.info("🏁 所有指标计算任务执行完毕。")

    def _run_stage(self, stage: CalculationStage, time_grain: Optional[str] = None):
        """运行特定阶段的所有计算器"""
        calculators = MetricRegistry.get_by_stage(stage, time_grain=time_grain)
        if not calculators:
            return

        logger.info(f"--- 正在执行阶段: {stage.value.upper()} ({len(calculators)} 个指标) ---")
        
        for calc in calculators:
            try:
                logger.info(f"开始计算指标 [{calc.metric_code}]: {calc.description}...")
                
                # 1. 幂等性清理 旧数据 (无论哪种模式，都先删后插)
                delete_sql, params = calc.get_delete_sql(self.ctx)
                if delete_sql:
                    with self.engine.begin() as conn:
                        conn.exec_driver_sql(delete_sql, params)
                
                # 2. 根据模式执行计算
                if calc.is_sql_mode:
                    # [模式 B] SQL 快速结算模式
                    insert_sql = calc.calculate_sql(self.ctx)
                    if insert_sql:
                        with self.engine.begin() as conn:
                            conn.exec_driver_sql(insert_sql)
                    logger.info(f"✅ 指标 [{calc.metric_code}] 已通过 SQL 引擎完成计算入库。")
                else:
                    # [模式 A] Python+Pandas 计算逻辑
                    df_result = calc.calculate(self.ctx)
                    
                    # 3. 结果入库 (DWS / ADS)
                    if df_result is not None and not df_result.empty:
                        if not calc.validate_result(df_result):
                            logger.error(f"严重错误: 指标 [{calc.metric_code}] 返回的数据格式不合法!")
                            continue
                        
                        df_result.to_sql(calc.storage_table, con=self.engine, if_exists='append', index=False)
                        logger.info(f"✅ 指标 [{calc.metric_code}] 写入完成，共 {len(df_result)} 行。")
                    else:
                        logger.warning(f"⚠️ 指标 [{calc.metric_code}] 计算结果为空。")
                    
            except Exception as e:
                logger.error(f"❌ 指标 [{calc.metric_code}] 计算失败: {str(e)}", exc_info=True)
                # 在生产环境下可以选择跳过或停止全部任务
                continue
            