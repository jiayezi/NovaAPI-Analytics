# -*- coding: utf-8 -*-
"""
此文件用于自动导入 calculators 目录下所有的指标实现类，
确保在 MetricRegistry 中自动完成注册。
"""
import os
import importlib

def import_all_calculators():
    curr_dir = os.path.dirname(__file__)
    for file in os.listdir(curr_dir):
        if file.endswith(".py") and file != "__init__.py":
            module_name = f"app.calculation.calculators.{file[:-3]}"
            importlib.import_module(module_name)

# 执行自动发现
import_all_calculators()
