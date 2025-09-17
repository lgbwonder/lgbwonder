# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
Agent包初始化文件

提供智能资产分配Agent相关的类和功能。
"""

import logging

# 获取日志记录器
logger = logging.getLogger(__name__)

# 导出主要的Agent类
try:
    from .asset_manage_agent import AssetManageAgent
    __all__ = ["AssetManageAgent"]
    logger.info("成功导入AssetManageAgent")
except ImportError as e:
    logger.warning(f"导入AssetManageAgent失败: {e}")
    __all__ = []

# 版本信息
__version__ = "1.0.0"
__author__ = "Asset Management Team"
__description__ = "智能资产分配Agent - 基于LangGraph和MCP" 