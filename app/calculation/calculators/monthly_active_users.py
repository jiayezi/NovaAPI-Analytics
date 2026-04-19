# -*- coding: utf-8 -*-
from typing import Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from app.calculation.core import CalculationContext

from app.calculation.core import MetricRegistry, CalculationStage, BaseMetricCalculator

@MetricRegistry.register(CalculationStage.PLATFORM)
class MonthlyActiveUsers(BaseMetricCalculator):
    """
    MAU (月活跃用户) 计算器
    基于 fct_account_daily_snapshot 预聚合表进行计算，效率极高。
    定义：每月至少有一次成功 API 调用请求的用户总数。
    """
    metric_code = "platform.monthly.mau"
    entity_type = "platform"
    storage_table = "dws_metric_value"
    description = "计算全平台月活跃用户数 (MAU)"
    time_grain = "monthly" # 声明为月度指标
    is_sql_mode = True

    def get_delete_sql(self, ctx: "CalculationContext") -> Tuple[str, tuple]:
        """
        生成幂等性删除 SQL。
        """
        # 基于日期范围和指标编码清理数据
        sql = f"DELETE FROM {self.storage_table} WHERE metric_code = ? AND entity_type = ? AND entity_id = ? AND time_type = ? AND time_id BETWEEN ? AND ?"
        params = (self.metric_code, self.entity_type, 'all', 'month', ctx.start_date.strftime('%Y-%m'), ctx.end_date.strftime('%Y-%m'))

        return sql, params
        
    def calculate_sql(self, ctx):
        """
        利用 DuckDB 的 strftime 函数将日期转换为月份标识 ('YYYY-MM')。
        """
        sql = f"""
            INSERT INTO {self.storage_table} (
                metric_code, entity_type, entity_id, time_type, time_id, metric_value
            )
            SELECT 
                '{self.metric_code}',
                '{self.entity_type}',
                'all',
                'month',
                strftime(snapshot_date, '%Y-%m'),
                CAST(COUNT(DISTINCT account_sk) AS DOUBLE)
            FROM fct_account_daily_snapshot
            WHERE snapshot_date BETWEEN '{ctx.start_date}' AND '{ctx.end_date}'
            GROUP BY 1, 2, 3, 4, 5
        """

        return sql