# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
Utils包初始化文件 - 配置日志系统

提供统一的日志配置和工具类导入。
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

# 加载.env文件
def load_env_config():
    """加载config目录下的.env文件"""
    try:
        from dotenv import load_dotenv
        
        # 获取config目录路径
        config_dir = Path(__file__).parent.parent / "config"
        env_file = config_dir / ".env"
        
        if env_file.exists():
            result = load_dotenv(env_file)
            return True
        else:
            return False
                
    except ImportError:
        return False
    except Exception as e:
        return False

# 自动加载环境变量
_env_loaded = load_env_config()

def setup_logging(
    level: str = "INFO",
    log_file: str = None,
    format_string: str = None,
    include_timestamp: bool = True
):
    """
    设置日志配置
    
    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径，如果为None则只输出到控制台
        format_string: 自定义日志格式字符串
        include_timestamp: 是否在日志中包含时间戳
    """
    # 设置日志级别
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # 默认日志格式
    if format_string is None:
        if include_timestamp:
            format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        else:
            format_string = "%(name)s - %(levelname)s - %(message)s"
    
    # 创建格式化器
    formatter = logging.Formatter(format_string)
    
    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # 清除现有的处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 添加控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 如果指定了日志文件，添加文件处理器
    if log_file:
        # 确保日志目录存在
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的日志记录器
    
    Args:
        name: 日志记录器名称
        
    Returns:
        logging.Logger: 日志记录器实例
    """
    return logging.getLogger(name)

# 默认日志配置
def init_default_logging():
    """初始化默认日志配置"""
    import os
    
    # 创建logs目录
    logs_dir = Path(__file__).parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    # 生成日志文件名（包含日期）
    today = datetime.now().strftime("%Y%m%d")
    log_file = logs_dir / f"asset_agent_{today}.log"
    
    # 从环境变量获取日志级别
    log_level = os.getenv("LOG_LEVEL", "INFO")
    
    # 设置日志配置
    setup_logging(
        level=log_level,
        log_file=str(log_file),
        include_timestamp=True
    )

# 自动初始化日志（可以通过环境变量控制）
import os
if os.getenv("ASSET_AGENT_AUTO_LOG", "true").lower() == "true":
    init_default_logging()

# 导出主要的工具类
try:
    from .mcp_client import MCPClient
    __all__ = ["MCPClient", "setup_logging", "get_logger", "init_default_logging", "load_env_config"]
except ImportError as e:
    logging.warning(f"导入MCPClient失败: {e}")
    __all__ = ["setup_logging", "get_logger", "init_default_logging", "load_env_config"] 