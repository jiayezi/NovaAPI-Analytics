-- NovaAPI-Analytics OLTP 业务库 DDL (MySQL)
-- 遵循 3NF 范式设计，减少冗余，保证写入性能

CREATE DATABASE IF NOT EXISTS nova_api_oltp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE nova_api_oltp;

-- 1. 用户表 (Users)
CREATE TABLE IF NOT EXISTS `users` (
    `user_id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '用户唯一标识',
    `email` VARCHAR(100) NOT NULL UNIQUE COMMENT '注册邮箱',
    `password_hash` VARCHAR(255) NOT NULL COMMENT '哈希后的密码',
    `registration_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
    `subscription_plan` ENUM('free', 'pro', 'enterprise') NOT NULL DEFAULT 'free' COMMENT '订阅方案',
    `account_balance` DECIMAL(18, 4) NOT NULL DEFAULT 0.0000 COMMENT '当前账户余额 (USD)',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 1正常, 0禁用',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB COMMENT='用户基础信息表';

-- 1.5 用户订阅计划变更流水表 (User Plan Changes Log) - 用于 CDC 或 SCD2 练习
CREATE TABLE IF NOT EXISTS `user_plan_changes` (
    `change_id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `old_plan` VARCHAR(20) NOT NULL COMMENT '变更前的订阅级别',
    `new_plan` VARCHAR(20) NOT NULL COMMENT '变更后的订阅级别',
    `change_date` DATETIME NOT NULL COMMENT '变更时间',
    `change_reason` VARCHAR(100) DEFAULT 'user_upgrade' COMMENT '变更原因',
    FOREIGN KEY (`user_id`) REFERENCES `users`(`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='用户订阅级别变更轨迹表';

-- 2. API 密钥表 (API Keys)
CREATE TABLE IF NOT EXISTS `api_keys` (
    `key_id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '密钥主键',
    `user_id` INT NOT NULL COMMENT '关联用户ID',
    `key_name` VARCHAR(50) DEFAULT 'Default Key' COMMENT '密钥别名',
    `api_key` VARCHAR(64) NOT NULL UNIQUE COMMENT 'API Key 字符串(通常为哈希或混淆串)',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `last_used_at` DATETIME DEFAULT NULL,
    `is_active` BOOLEAN NOT NULL DEFAULT TRUE COMMENT '是否启用',
    FOREIGN KEY (`user_id`) REFERENCES `users`(`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='用户 API 密钥配置表';

-- 3. AI 模型档案表 (AI Models)
CREATE TABLE IF NOT EXISTS `ai_models` (
    `model_id` VARCHAR(50) PRIMARY KEY COMMENT '模型唯一名称/ID (如 gpt-4, claude-3)',
    `provider` VARCHAR(50) NOT NULL COMMENT '提供商 (OpenAI, Anthropic, etc.)',
    `input_price_per_1M` DECIMAL(10, 6) NOT NULL COMMENT '每 1M 输入 Token 价格 (USD)',
    `output_price_per_1M` DECIMAL(10, 6) NOT NULL COMMENT '每 1M 输出 Token 价格 (USD)',
    `max_context` INT NOT NULL COMMENT '最大上下文长度',
    `is_available` BOOLEAN NOT NULL DEFAULT TRUE COMMENT '模型当前是否可用'
) ENGINE=InnoDB COMMENT='AI 模型配置及价格表';

-- 4. 原始请求日志表 (Raw Request Logs)
-- 该表在生产环境中写入极其频繁，通常只存 ID 和原始度量
CREATE TABLE IF NOT EXISTS `request_logs_raw` (
    `request_id` BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '请求流水号',
    `key_id` INT NOT NULL COMMENT '关联密钥ID',
    `model_id` VARCHAR(50) NOT NULL COMMENT '调用模型ID',
    `prompt_token_count` INT NOT NULL DEFAULT 0 COMMENT '输入 Token 消耗',
    `completion_token_count` INT NOT NULL DEFAULT 0 COMMENT '输出 Token 消耗',
    `latency_ms` INT NOT NULL COMMENT '端到端响应延迟 (毫秒)',
    `http_status` INT NOT NULL COMMENT 'HTTP 状态码 (200, 429, 500等)',
    `error_code` VARCHAR(50) DEFAULT NULL COMMENT '内部错误分类代码',
    `request_time` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '请求发生时间(精确到毫秒)',
    INDEX `idx_request_time` (`request_time`),
    INDEX `idx_key_id` (`key_id`),
    FOREIGN KEY (`key_id`) REFERENCES `api_keys`(`key_id`),
    FOREIGN KEY (`model_id`) REFERENCES `ai_models`(`model_id`)
) ENGINE=InnoDB COMMENT='API 原始调用流水表';

-- 5. 账单与充值记录表 (Financial Transactions)
CREATE TABLE IF NOT EXISTS `billing_orders` (
    `order_id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `amount` DECIMAL(18, 4) NOT NULL COMMENT '金额 (正数为充值, 负数为扣费或退款)',
    `order_type` ENUM('recharge', 'subscription_fee', 'usage_settlement', 'refund') NOT NULL,
    `payment_method` VARCHAR(50) DEFAULT 'credit_card',
    `transaction_status` ENUM('pending', 'completed', 'failed') NOT NULL DEFAULT 'completed',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`user_id`)
) ENGINE=InnoDB COMMENT='财务流水与账单记录表';
