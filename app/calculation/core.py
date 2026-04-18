# -*- coding: utf-8 -*-
"""
NovaAPI Metrics Engine Core
"""
import pandas as pd
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Type, Any, Optional, Tuple, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

# 1. 计算阶段定义：按依赖顺序排列
class CalculationStage(Enum):
    USER = "user"          # 用户维度：注册、留存、消费金额、API 调用频次
    MODEL = "model"        # 模型维度：调用次数、Token、P99 延迟、成功率、单位利润
    PLATFORM = "platform"  # 平台维度：MAU、总利润、环比增长、预测结果

# 2. 计算上下文 (容器)
@dataclass
class CalculationContext:
    engine: "Engine"
    start_date: datetime    # 计算开始日期
    end_date: datetime      # 计算结束日期
    user_ids: Optional[List[int]] = None    # 可选：指定特定用户范围
    model_ids: Optional[List[str]] = None   # 可选：指定特定模型范围
    data_cache: dict = field(default_factory=dict) # 用于跨指标共享中间计算结果 (Cache)
    metadata: dict = field(default_factory=dict)   # 用于透传其他参数

# 3. 指标计算器注册表 (用于插件化解耦)
class MetricRegistry:
    _calculators: Dict[CalculationStage, List[Type['BaseMetricCalculator']]] = {}

    @classmethod
    def register(cls, stage: CalculationStage):
        """装饰器：将计算器注册到指定阶段"""
        def decorator(calculator_class: Type['BaseMetricCalculator']):
            if stage not in cls._calculators:
                cls._calculators[stage] = []
            if calculator_class not in cls._calculators[stage]:
                cls._calculators[stage].append(calculator_class)
            return calculator_class
        return decorator

    @classmethod
    def get_by_stage(cls, stage: CalculationStage, time_grain: Optional[str] = None) -> List['BaseMetricCalculator']:
        """获取指定阶段的所有计算器实例，并按优先级和时间粒度排序/过滤"""
        classes = cls._calculators.get(stage, [])
        instances = [c() for c in classes]
        
        # 按时间粒度进行过滤 (daily/monthly/weekly)
        if time_grain:
            instances = [c for c in instances if getattr(c, 'time_grain', 'daily') == time_grain]
            
        return sorted(instances, key=lambda x: getattr(x, "priority", 0))

# 4. 指标计算器基类 (所有具体指标必须继承此基类)
class BaseMetricCalculator(ABC):
    metric_code: str = ""        # 指标唯一标识 (如 'mau', 'retention_rate')
    entity_type: str = ""        # 实体类型 (user, model, platform)
    storage_table: str = ""      # 目标存储表 (ADS 层)
    description: str = "指标计算"  # 用于进度显示的名称
    time_grain: str = "daily"    # 时间粒度 (daily, monthly, weekly, yearly)，用于声明自己“多久计算一次”
    is_sql_mode: bool = False    # 是否开启 SQL 快速结算模式 (直接在 DB 执行 INSERT SELECT)
    priority: int = 0            # 执行优先级 (越小越先执行)

    def calculate(self, ctx: CalculationContext) -> pd.DataFrame:
        """
        [模式 A] Python+Pandas 计算逻辑
        返回的 DataFrame 必须包含: metric_code, entity_id, time_id, metric_value 等字段。
        """
        return pd.DataFrame()

    def calculate_sql(self, ctx: CalculationContext) -> str:
        """
        [模式 B] SQL 快速结算模式
        返回一个完整的 INSERT INTO ... SELECT ... 语句。
        系统会自动处理幂等性删除。
        """
        raise NotImplementedError("SQL 模式计算器必须实现 calculate_sql 方法")

    def get_delete_sql(self, ctx: CalculationContext) -> Tuple[str, tuple]:
        """
        生成幂等性删除 SQL。
        默认实现：根据 metric_code 和时间范围清理数据。
        """
        if not self.metric_code or not self.storage_table:
            return "", ()
        
        # 默认基于日期范围和指标编码清理数据 (Delete-Before-Insert 模式)
        sql = f"DELETE FROM {self.storage_table} WHERE metric_code = ? AND time_id BETWEEN ? AND ?"
        params = (self.metric_code, ctx.start_date.strftime('%Y-%m-%d'), ctx.end_date.strftime('%Y-%m-%d'))
        
        # 如果是用户或模型维度，可以进一步缩小删除范围
        if self.entity_type == 'user' and ctx.user_ids:
            sql += f" AND entity_id IN ({','.join(['?']*len(ctx.user_ids))})"
            params += tuple(ctx.user_ids)
        elif self.entity_type == 'model' and ctx.model_ids:
            sql += f" AND entity_id IN ({','.join(['?']*len(ctx.model_ids))})"
            params += tuple(ctx.model_ids)

        return sql, params

    @staticmethod
    def validate_result(df: pd.DataFrame) -> bool:
        """验证计算结果是否包含必要列"""
        if df is None or df.empty: return True
        required_cols = {"metric_code", "entity_id", "metric_value"}
        return required_cols.issubset(set(df.columns))
