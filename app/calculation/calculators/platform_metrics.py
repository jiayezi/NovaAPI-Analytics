# -*- coding: utf-8 -*-
from app.calculation.core import MetricRegistry, CalculationStage, BaseMetricCalculator

@MetricRegistry.register(CalculationStage.PLATFORM)
class DailyPlatformCalls(BaseMetricCalculator):
    """
    全平台每日调用总量指标
    直接统计事实表中的记录行数。
    """
    metric_code = "platform.daily.calls"
    entity_type = "platform"
    storage_table = "dws_metric_value"
    description = "计算全平台每日调用总量"
    time_grain = "daily"
    is_sql_mode = True # 使用 SQL 快速聚合模式

    def calculate_sql(self, ctx):
        """
        利用 SQL 直接从事实表聚合数据。
        """
        return f"""
            INSERT INTO {self.storage_table} (
                metric_code, entity_type, entity_id, time_type, time_id, metric_value
            )
            SELECT 
                '{self.metric_code}',
                '{self.entity_type}',
                'all',
                'day',
                strftime(request_time, '%Y-%m-%d'),
                CAST(COUNT(*) AS DOUBLE)
            FROM fct_api_requests
            WHERE request_time BETWEEN '{ctx.start_date}' AND '{ctx.end_date}'
            GROUP BY 1, 2, 3, 4, 5
        """
