from typing import Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from app.calculation.core import CalculationContext

from app.calculation.core import MetricRegistry, CalculationStage, BaseMetricCalculator

@MetricRegistry.register(CalculationStage.PLATFORM)
class MonthlyRetentionCalculator(BaseMetricCalculator):
    """
    月度留存率计算器 (Cohort Analysis)
    输出：每个注册批次在后续月份的活跃百分比。
    存储：dws_metric_struct (JSON 格式)
    """
    metric_code = "platform.monthly.retention"
    entity_type = "platform"
    storage_table = "dws_metric_struct" # 存储到结构化表
    description = "计算月度留存率矩阵 (Cohort Analysis)"
    time_grain = "monthly"
    is_sql_mode = True

    def get_delete_sql(self, ctx: "CalculationContext") -> Tuple[str, tuple]:
        """
        生成幂等性删除 SQL。
        """
        # 留存率比较特殊：我们每次计算都会刷新过去所有批次的留存情况
        # 因此删除范围应该是：从有数据开始，到当前任务结束月份
        sql = f"DELETE FROM {self.storage_table} WHERE metric_code = ? AND time_id <= ?"
        params = (self.metric_code, ctx.end_date.strftime('%Y-%m'))
        return sql, params

    def calculate_sql(self, ctx):
        """
        利用 DuckDB 的 CTE 嵌套计算留存矩阵并序列化为 JSON。
        """
        # 我们只计算到任务结束时间为止的留存情况
        end_date_str = ctx.end_date.strftime('%Y-%m-%d')
        sql = f"""
            INSERT INTO {self.storage_table} (
                metric_code, entity_type, entity_id, time_type, time_id, struct_type, struct_json
            )
            WITH user_cohorts AS (
                -- 1. 确定每个用户的身份和注册月份 (Cohort)
                SELECT 
                    user_id, 
                    account_sk,
                    strftime(registration_date, '%Y-%m') as cohort_month,
                    strftime(registration_date, '%Y') as cohort_year,
                    strftime(registration_date, '%m') as cohort_only_month
                FROM dim_account
                WHERE is_current = true
                -- 过去 24 个月的所有注册批次
                AND registration_date >= CAST('{end_date_str}' AS DATE) - INTERVAL 24 MONTH
            ),
            active_months AS (
                -- 2. 确定每个用户在哪些月份活跃过
                SELECT DISTINCT 
                    a.user_id, 
                    strftime(s.snapshot_date, '%Y-%m') as active_month,
                    strftime(s.snapshot_date, '%Y') as active_year,
                    strftime(s.snapshot_date, '%m') as active_only_month
                FROM fct_account_daily_snapshot s
                JOIN dim_account a ON s.account_sk = a.account_sk
                WHERE s.snapshot_date <= '{end_date_str}' -- 限制上限，不限制下限
            ),
            retention_base AS (
                -- 3. 计算月差 (Month N)
                SELECT 
                    c.cohort_month,
                    a.active_month,
                    -- 计算活跃月份与注册月份的差值：(Y2*12 + M2) - (Y1*12 + M1)
                    (CAST(a.active_year AS INT) * 12 + 
                     CAST(a.active_only_month AS INT)) -
                    (CAST(c.cohort_year AS INT) * 12 + 
                     CAST(c.cohort_only_month AS INT)) as month_diff,
                    -- 各注册月份的用户在各月份的活跃数量
                    COUNT(DISTINCT c.user_id) as active_user_count
                FROM user_cohorts c
                JOIN active_months a ON c.user_id = a.user_id
                GROUP BY 1, 2, 3
            ),
            cohort_size AS (
                -- 4. 以该月份“注册”的总人数作为分母
                SELECT cohort_month, COUNT(user_id) as total_users
                FROM user_cohorts
                GROUP BY 1
            ),
            retention_final AS (
                -- 5. 计算比例并按 Cohort 聚合为 JSON 对象
                SELECT 
                    r.cohort_month,
                    -- 生成 JSON 结构: |"month_0": 1.0, "month_1": 0.45, ... |
                    json_group_object(
                        'month_' || CAST(r.month_diff AS VARCHAR), 
                        ROUND(CAST(r.active_user_count AS DOUBLE) / s.total_users, 4)
                    ) as retention_json
                FROM retention_base r
                JOIN cohort_size s ON r.cohort_month = s.cohort_month
                GROUP BY 1
            )
            SELECT 
                '{self.metric_code}',
                'platform',
                'all',
                'month',
                cohort_month,
                'distribution',
                retention_json
            FROM retention_final
        """

        return sql
