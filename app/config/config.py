import yaml
import os
from pathlib import Path
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class MySQLConfig(BaseModel):
    host: str = "localhost"
    port: int = 3306
    user: str
    password: str
    database: str

class DuckDBConfig(BaseModel):
    path: str = "data/nova_analytics.db"

class DatabaseConfig(BaseModel):
    mysql: MySQLConfig
    duckdb: DuckDBConfig

class AIModelConfig(BaseModel):
    model_id: str
    provider: str
    input_price_per_1M: float
    output_price_per_1M: float
    max_context: int

class GeneratorConfig(BaseModel):
    initial_users: int = 50
    max_keys_per_user: int = 3
    simulation_days: int = 30

class Settings(BaseSettings):
    """全局配置模型 (Pydantic 风格)"""
    database: DatabaseConfig
    ai_models: List[AIModelConfig]
    generator: GeneratorConfig

    # 支持从环境变量读取，优先级最高
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore"
    )

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Settings":
        """从 YAML 文件加载并合并环境变量"""
        if config_path is None:
            # 默认指向 app/config/settings.yaml
            config_path = Path(__file__).parent / "settings.yaml"

        config_data = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}
        
        return cls(**config_data)

# 初始化单例
settings = Settings.load(os.getenv("CONFIG_PATH"))

if __name__ == "__main__":
    # 测试代码
    print(f"MySQL Host: {settings.database.mysql.host}")
    print(f"First Model: {settings.ai_models[0].model_id}")
