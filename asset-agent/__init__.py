# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
Asset Agent包初始化文件

智能资产分配系统 - 基于LangGraph和MCP的企业资产管理解决方案
"""

import logging
from pathlib import Path

# 包信息
__version__ = "1.0.0"
__author__ = "Asset Management Team"
__description__ = "智能资产分配Agent - 基于LangGraph和MCP"

# 初始化日志系统
def init_logging():
    """初始化日志系统"""
    try:
        from .utils import init_default_logging
        init_default_logging()
        logging.info("Asset Agent包日志系统初始化完成")
    except ImportError as e:
        logging.warning(f"日志系统初始化失败: {e}")

# 自动初始化日志
init_logging()

# 获取日志记录器
logger = logging.getLogger(__name__)

# 导出主要组件
try:
    from .agent import AssetManageAgent
    from .utils import MCPClient, setup_logging, get_logger
    
    __all__ = [
        "AssetManageAgent",
        "MCPClient", 
        "setup_logging",
        "get_logger"
    ]
    
    logger.info("Asset Agent包组件导入成功")
    
except ImportError as e:
    logger.error(f"导入Asset Agent组件失败: {e}")
    __all__ = []

def create_agent(mcp_server_url: str = "http://localhost:8000/mcp") -> 'AssetManageAgent':
    """
    创建智能资产管理Agent实例
    
    Args:
        mcp_server_url: MCP服务器地址
        
    Returns:
        AssetManageAgent: Agent实例
    """
    try:
        agent = AssetManageAgent(mcp_server_url)
        logger.info(f"成功创建Asset Agent实例，MCP服务器: {mcp_server_url}")
        return agent
    except Exception as e:
        logger.error(f"创建Asset Agent实例失败: {e}")
        raise

def get_version_info() -> dict:
    """
    获取版本信息
    
    Returns:
        dict: 版本信息字典
    """
    return {
        "version": __version__,
        "author": __author__,
        "description": __description__,
        "components": __all__
    } 