# -*- coding: utf-8 -*-
import pandas as pd
from typing import Optional
from sqlalchemy.engine import Engine

class CalculationDataUtils:
    """计算辅助工具类，封装常用的 ODS 数据读取逻辑"""
    
    @staticmethod
    def read_request_logs(engine: Engine, start_date: str, end_date: str) -> pd.DataFrame:
        """读取指定日期范围内的 API 原始日志"""
        query = """
            SELECT * FROM request_logs_raw 
            WHERE request_time BETWEEN %s AND %s
        """
        return pd.read_sql(query, con=engine, params=(start_date, end_date))

    @staticmethod
    def read_users(engine: Engine) -> pd.DataFrame:
        """读取所有用户信息及其最新订阅状态"""
        return pd.read_sql("SELECT * FROM users", con=engine)

    @staticmethod
    def read_billing_orders(engine: Engine, start_date: str, end_date: str) -> pd.DataFrame:
        """读取账单流水"""
        query = "SELECT * FROM billing_orders WHERE created_at BETWEEN %s AND %s"
        return pd.read_sql(query, con=engine, params=(start_date, end_date))
