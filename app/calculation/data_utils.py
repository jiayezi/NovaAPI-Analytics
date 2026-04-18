# -*- coding: utf-8 -*-
import pandas as pd
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

class CalculationDataUtils:
    """计算辅助工具类，封装对数据仓库（DuckDB/DW）层数据的读取逻辑"""
    
    @staticmethod
    def read_api_facts(engine: "Engine", start_date: str, end_date: str) -> pd.DataFrame:
        """从事实表读取 API 调用明细数据 (DWD 层)"""
        # 此时读取的是已经过 ETL 清洗、关联过 SK 的事实表，性能更高且数据更准确
        query = """
            SELECT * FROM fct_api_requests 
            WHERE request_time BETWEEN %s AND %s
        """
        return pd.read_sql(query, con=engine, params=(start_date, end_date))

    @staticmethod
    def read_dim_accounts(engine: "Engine") -> pd.DataFrame:
        """读取账户维度表"""
        return pd.read_sql("SELECT * FROM dim_account", con=engine)

    @staticmethod
    def read_financial_facts(engine: "Engine", start_date: str, end_date: str) -> pd.DataFrame:
        """读取资金交易明细数据"""
        query = "SELECT * FROM fct_account_transactions WHERE created_at BETWEEN %s AND %s"
        return pd.read_sql(query, con=engine, params=(start_date, end_date))
