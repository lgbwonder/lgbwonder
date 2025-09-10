#!/usr/bin/env python3
"""
MyGlodon Asset & Member Management MCP Server

This MCP server provides access to MyGlodon asset management functionality
through the OpenAssetManageController API endpoints.
This MCP server provides access to MyGlodon asset management and member management functionality
"""

import json
import logging
import os
from pathlib import Path
import requests
from fastmcp import FastMCP
from dotenv import load_dotenv
import datetime
import random
import string

# Load Environment Variables
env_path = (Path(__file__).parent / "../system/.env").resolve()
load_dotenv(dotenv_path=env_path, verbose=False)


def setup_logging(log_level=None, log_file=None, log_format=None):
    """Setup logging configuration"""

    # Default values
    if log_level is None:
        log_level = os.getenv("ASSET_LOG_LEVEL", "INFO")

    if log_format is None:
        log_format = os.getenv("ASSET_LOG_FORMAT", "simple")

    # Convert string to logging level
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }

    log_level_num = level_map.get(log_level.upper(), logging.INFO)

    # Log formats
    formats = {
        "simple": "%(asctime)s [%(levelname)s] %(message)s",
        "detailed": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
        "minimal": "%(levelname)s: %(message)s",
        "json": '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
    }

    log_format_str = formats.get(log_format, formats["simple"])

    # Create logs directory if it doesn't exist
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=log_level_num,
        format=log_format_str,
        datefmt='%H:%M:%S',
        handlers=[]
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level_num)
    console_formatter = logging.Formatter(log_format_str, datefmt='%H:%M:%S')
    console_handler.setFormatter(console_formatter)

    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(log_level_num)
        file_formatter = logging.Formatter(log_format_str, datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(file_formatter)
        logging.getLogger().addHandler(file_handler)

    # Add console handler
    logging.getLogger().addHandler(console_handler)

    # Set specific logger levels
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return logging.getLogger(__name__)


# Setup logging
logger = setup_logging(
    log_level=os.getenv("ASSET_LOG_LEVEL", "INFO"),
    log_file=os.getenv("ASSET_LOG_FILE", "logs/server.log"),
    log_format=os.getenv("ASSET_LOG_FORMAT", "simple")
)

# Global constants
ORDER_URL = os.getenv("ORDER_URL")
ORDER_APPKEY = os.getenv("ORDER_APPKEY")

ASSET_URL = os.getenv("ASSET_URL")
MEMBER_CLIENT_TOKEN_URL = os.getenv("MEMBER_CLIENT_TOKEN_URL")
MEMBER_USER_TOKEN_URL = os.getenv("MEMBER_USER_TOKEN_URL")
MEMBER_CLIENT_TOKEN_HEADER = os.getenv("MEMBER_CLIENT_TOKEN_HEADER")
MEMBER_USER_TOKEN_HEADER = os.getenv("MEMBER_USER_TOKEN_HEADER")
MEMBER_ADD_URL = os.getenv("MEMBER_ADD_URL")

# Create FastMCP server
mcp = FastMCP(os.getenv("ASSET_SERVER_NAME"))


@mcp.tool()
def query_assets_by_status_mcp(userToken: str, clientToken: str, searchType: str, searchCondition: str,
                               assetStatus: list, pageNum: int = 1, pageSize: int = 20) -> dict:
    """查询资产状态 - 根据状态查询企业资产信息，支持分页

    参数说明：
        userToken: 用户认证令牌
        clientToken: 客户端认证令牌
        pageNum: 页码，默认为1
        pageSize: 每页大小，默认为20
        searchType: 搜索类型，可选值：productUri, productName, assetNum, memberAccount
        searchCondition: 搜索条件
        assetStatus: 资产状态列表，可选值：["VALID", "EXPIRED", "UNASSIGNED", "ASSIGNED", "BORROWED", "ONLINED", "LOCKED"]

    返回格式：
        成功时返回结构化的资产列表数据，包含以下字段：
        {
            "success": true,
            "data": {
                "summary": {
                    "totalAssets": 总资产数,
                    "currentPage": 当前页码,
                    "pageSize": 每页大小,
                    "totalPages": 总页数,
                    "searchType": 搜索类型,
                    "searchCondition": 搜索条件,
                    "assetStatus": 查询的资产状态列表,
                    "statusCounts": {
                        "VALID": 有效资产数,
                        "EXPIRED": 过期资产数,
                        "UNASSIGNED": 未分配资产数,
                        "ASSIGNED": 已分配资产数,
                        "BORROWED": 借出资产数,
                        "ONLINED": 在线资产数,
                        "LOCKED": 锁定资产数
                    }
                },
                "assets": [
                    {
                        "assetId": "资产ID",
                        "assetNum": "资产编号",
                        "productName": "产品名称",
                        "productUri": "产品URI",
                        "status": "资产状态",
                        "memberName": "分配成员姓名",
                        "memberAccount": "分配成员账号",
                        "memberId": "分配成员ID",
                        "assignTime": "分配时间",
                        "expireTime": "过期时间",
                        "createTime": "创建时间",
                        "updateTime": "更新时间",
                        "onlineStatus": "在线状态",
                        "borrowStatus": "借出状态",
                        "lockStatus": "锁定状态"
                    }
                ],
                "pagination": {
                    "pageNum": 当前页码,
                    "pageSize": 每页大小,
                    "total": 总记录数,
                    "pages": 总页数,
                    "hasNextPage": 是否有下一页,
                    "hasPrevPage": 是否有上一页
                },
                "rawData": 原始API响应数据
            },
            "message": "查询资产状态成功，共找到 X 个资产"
        }
        
        失败时返回错误信息：
        {
            "success": false,
            "error": "错误描述",
            "status_code": HTTP状态码,
            "type": "错误类型"
        }
    """
    try:
        url = f"{ASSET_URL}/v1/assets/manage/asset/status"
        params = {"pageNum": pageNum, "pageSize": pageSize}
        data = {"searchType": searchType, "searchCondition": searchCondition, "assetStatus": assetStatus}
        headers = {"userToken": userToken, "clientToken": clientToken, "Content-Type": "application/json"}

        logger.info(f"查询资产状态 - 类型:{searchType}, 状态:{assetStatus}, 页码:{pageNum}")

        # 发送请求
        resp = requests.post(url, params=params, json=data, headers=headers, timeout=30)

        # 检查响应状态
        if resp.status_code == 200:
            result = resp.json()
            
            # 解析API响应数据
            api_data = result.get('data', {}) if isinstance(result, dict) else result
            assets_list = api_data.get('list', []) if isinstance(api_data, dict) else []
            pagination_info = api_data.get('pagination', {}) if isinstance(api_data, dict) else {}
            
            # 统计信息
            total_assets = len(assets_list) if isinstance(assets_list, list) else 0
            status_counts = {}
            
            # 处理资产数据，提取关键信息
            processed_assets = []
            if isinstance(assets_list, list):
                for asset in assets_list:
                    # 统计各状态数量
                    status = asset.get('status', 'UNKNOWN')
                    status_counts[status] = status_counts.get(status, 0) + 1
                    
                    # 构建简化的资产信息
                    asset_info = {
                        "assetId": asset.get('assetId'),
                        "assetNum": asset.get('assetNum'),
                        "productName": asset.get('productName'),
                        "productUri": asset.get('productUri'),
                        "status": status,
                        "memberName": asset.get('memberName'),
                        "memberAccount": asset.get('memberAccount'),
                        "memberId": asset.get('memberId'),
                        "assignTime": asset.get('assignTime'),
                        "expireTime": asset.get('expireTime'),
                        "createTime": asset.get('createTime'),
                        "updateTime": asset.get('updateTime'),
                        "onlineStatus": asset.get('onlineStatus'),
                        "borrowStatus": asset.get('borrowStatus'),
                        "lockStatus": asset.get('lockStatus')
                    }
                    processed_assets.append(asset_info)
            
            # 计算分页信息
            total_pages = pagination_info.get('pages', 1)
            has_next_page = pageNum < total_pages
            has_prev_page = pageNum > 1
            
            # 构建优化的返回格式
            response_data = {
                "summary": {
                    "totalAssets": total_assets,
                    "currentPage": pageNum,
                    "pageSize": pageSize,
                    "totalPages": total_pages,
                    "searchType": searchType,
                    "searchCondition": searchCondition,
                    "assetStatus": assetStatus,
                    "statusCounts": status_counts
                },
                "assets": processed_assets,
                "pagination": {
                    "pageNum": pageNum,
                    "pageSize": pageSize,
                    "total": pagination_info.get('total', total_assets),
                    "pages": total_pages,
                    "hasNextPage": has_next_page,
                    "hasPrevPage": has_prev_page
                },
                "rawData": api_data  # 保留原始数据以备需要
            }
            
            logger.info(f"查询成功 - 总资产数:{total_assets}, 当前页:{pageNum}, 总页数:{total_pages}")
            return {
                "success": True, 
                "data": response_data, 
                "message": f"查询资产状态成功，共找到 {total_assets} 个资产"
            }
        else:
            error_msg = f"接口调用失败，状态码: {resp.status_code}"
            try:
                error_detail = resp.json()
                error_msg += f"，错误详情: {error_detail}"
            except:
                error_msg += f"，响应内容: {resp.text}"

            logger.error(f"查询失败 - {error_msg}")
            return {"success": False, "error": error_msg, "status_code": resp.status_code}

    except requests.exceptions.RequestException as e:
        error_msg = f"网络请求异常: {str(e)}"
        logger.error(f"网络异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "network_error"}
    except json.JSONDecodeError as e:
        error_msg = f"响应解析异常: {str(e)}"
        logger.error(f"解析异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "parse_error"}
    except Exception as e:
        error_msg = f"未知异常: {str(e)}"
        logger.error(f"未知异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "unknown_error"}


@mcp.tool()
def allocate_asset_privileges_mcp(userToken: str, clientToken: str, assignType: str, assetPrivileges: list) -> dict:
    """分配/取消分配资产权限 - 为指定资产分配或取消分配权限给成员

    参数说明：
        userToken: 用户认证令牌
            - 类型: 字符串
            - 必填: 是
            - 说明: 用于身份验证的用户访问令牌，从 generate_user_token_mcp 获取
        
        clientToken: 客户端认证令牌
            - 类型: 字符串
            - 必填: 是
            - 说明: 用于客户端身份验证的令牌，从 generate_client_token_mcp 获取
        
        assignType: 分配类型
            - 类型: 字符串
            - 必填: 是
            - 可选值: 
                * "assign" - 分配权限给成员
                * "unassign" - 取消分配权限（从成员处收回权限）
            - 说明: 指定是分配还是取消分配资产权限
        
        assetPrivileges: 资产权限列表
            - 类型: 列表
            - 必填: 是
            - 说明: 包含要操作的资产权限信息列表，每个元素为字典格式
            - 列表元素结构:
                {
                    "assetNum": "资产编号",      # 必填，字符串，资产的唯一编号
                    "assetId": "资产ID",        # 必填，字符串，资产的唯一标识ID
                    "memberId": "成员ID"        # 必填，字符串，目标成员的唯一标识ID
                }
            - 示例:
                [
                    {
                        "assetNum": "ASSET001",
                        "assetId": "12345",
                        "memberId": "member_001"
                    },
                    {
                        "assetNum": "ASSET002", 
                        "assetId": "12346",
                        "memberId": "member_002"
                    }
                ]
            - 注意事项:
                * 可以同时操作多个资产权限
                * 每个资产权限操作都是独立的
                * 资产编号和资产ID必须对应同一个资产
                * 成员ID必须是有效的企业成员

    返回格式：
        成功时返回API响应数据，失败时返回错误信息
    """
    try:
        url = f"{ASSET_URL}/v1/assets/manage/asset/{assignType}/privileges"
        headers = {"userToken": userToken, "clientToken": clientToken, "Content-Type": "application/json"}

        logger.info(f"资产权限操作 - 类型:{assignType}, 数量:{len(assetPrivileges)}")

        # 发送请求
        resp = requests.post(url, json=assetPrivileges, headers=headers, timeout=30)

        # 检查响应状态
        if resp.status_code == 200:
            result = resp.json()
            logger.info(f"权限操作成功 - 状态码:{resp.status_code}")
            return {"success": True, "data": result, "message": f"资产权限{assignType}操作成功"}
        else:
            error_msg = f"接口调用失败，状态码: {resp.status_code}"
            try:
                error_detail = resp.json()
                error_msg += f"，错误详情: {error_detail}"
            except:
                error_msg += f"，响应内容: {resp.text}"

            logger.error(f"权限操作失败 - {error_msg}")
            return {"success": False, "error": error_msg, "status_code": resp.status_code}

    except requests.exceptions.RequestException as e:
        error_msg = f"网络请求异常: {str(e)}"
        logger.error(f"网络异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "network_error"}
    except json.JSONDecodeError as e:
        error_msg = f"响应解析异常: {str(e)}"
        logger.error(f"解析异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "parse_error"}
    except Exception as e:
        error_msg = f"未知异常: {str(e)}"
        logger.error(f"未知异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "unknown_error"}


@mcp.tool()
def query_asset_products_mcp(userToken: str, clientToken: str, assetId: str) -> dict:
    """查询资产产品详情 - 查询指定资产的云锁产品详情信息

    参数说明：
        userToken: 用户认证令牌
        clientToken: 客户端认证令牌
        assetId: 资产ID

    返回格式：
        成功时返回API响应数据，失败时返回错误信息
    """
    try:
        url = f"{ASSET_URL}/v1/assets/manage/{assetId}/products"
        headers = {"userToken": userToken, "clientToken": clientToken}

        logger.info(f"查询在线产品 - 资产ID:{assetId}")

        # 发送请求
        resp = requests.get(url, headers=headers, timeout=30)

        # 检查响应状态
        if resp.status_code == 200:
            result = resp.json()
            logger.info(f"查询成功 - 状态码:{resp.status_code}")
            return {"success": True, "data": result, "message": "查询在线产品成功"}
        else:
            error_msg = f"接口调用失败，状态码: {resp.status_code}"
            try:
                error_detail = resp.json()
                error_msg += f"，错误详情: {error_detail}"
            except:
                error_msg += f"，响应内容: {resp.text}"

            logger.error(f"查询失败 - {error_msg}")
            return {"success": False, "error": error_msg, "status_code": resp.status_code}

    except requests.exceptions.RequestException as e:
        error_msg = f"网络请求异常: {str(e)}"
        logger.error(f"网络异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "network_error"}
    except json.JSONDecodeError as e:
        error_msg = f"响应解析异常: {str(e)}"
        logger.error(f"解析异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "parse_error"}
    except Exception as e:
        error_msg = f"未知异常: {str(e)}"
        logger.error(f"未知异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "unknown_error"}


@mcp.tool()
def query_enterprise_members_mcp(userToken: str, clientToken: str, keyword: str = '') -> dict:
    """查询企业成员 - 获取企业下的成员列表

    参数说明：
        userToken: 用户认证令牌
        clientToken: 客户端认证令牌
        keyword: 搜索关键词，支持按账号模糊搜索（可选）

    返回格式：
        成功时返回结构化的成员列表数据，包含以下字段：
        {
            "success": true,
            "data": {
                "summary": {
                    "totalMembers": 总成员数,
                    "onlineMembers": 在线成员数,
                    "offlineMembers": 离线成员数,
                    "membersWithAssets": 有资产分配的成员数,
                    "searchKeyword": 搜索关键词
                },
                "members": [
                    {
                        "id": "成员ID",
                        "userName": "用户名",
                        "name": "姓名",
                        "globalId": "全局ID",
                        "departmentName": "部门名称",
                        "onlineFlag": true/false,
                        "assetCount": 分配的资产数量,
                        "assetNums": ["资产编号1", "资产编号2", ...],
                        "hasMoreAssets": true/false,
                        "borrowNum": "借出锁编号",
                        "createTime": "创建时间",
                        "updateTime": "更新时间"
                    }
                ],
                "rawData": 原始API响应数据
            },
            "message": "查询企业成员成功，共找到 X 名成员"
        }
        
        失败时返回错误信息：
        {
            "success": false,
            "error": "错误描述",
            "status_code": HTTP状态码,
            "type": "错误类型"
        }
    """
    try:
        url = f"{ASSET_URL}/v1/assets/manage/members"
        if keyword:
            url += f"?keyword={keyword}"
        
        headers = {"userToken": userToken, "clientToken": clientToken}

        logger.info(f"查询企业成员 - 关键词: {keyword if keyword else '无'}")

        # 发送请求
        resp = requests.get(url, headers=headers, timeout=30)

        # 检查响应状态
        if resp.status_code == 200:
            result = resp.json()
            
            # 解析API响应数据
            members_data = result.get('data', []) if isinstance(result, dict) else result
            
            # 统计信息
            total_count = len(members_data) if isinstance(members_data, list) else 0
            online_count = 0
            offline_count = 0
            assigned_assets_count = 0
            
            # 处理成员数据，提取关键信息
            processed_members = []
            if isinstance(members_data, list):
                for member in members_data:
                    # 统计在线状态
                    if member.get('onlineFlag'):
                        online_count += 1
                    else:
                        offline_count += 1
                    
                    # 统计分配资产数量
                    asset_nums = member.get('assetNums', [])
                    if asset_nums and len(asset_nums) > 0:
                        assigned_assets_count += 1
                    
                    # 构建简化的成员信息
                    member_info = {
                        "id": member.get('id'),
                        "userName": member.get('userName'),
                        "name": member.get('name'),
                        "globalId": member.get('globalId'),
                        "departmentName": member.get('departmentName'),
                        "onlineFlag": member.get('onlineFlag', False),
                        "assetCount": len(asset_nums) if asset_nums else 0,
                        "assetNums": asset_nums[:5] if asset_nums else [],  # 只显示前5个资产编号
                        "hasMoreAssets": len(asset_nums) > 5 if asset_nums else False,
                        "borrowNum": member.get('borrowNum'),
                        "createTime": member.get('createTime'),
                        "updateTime": member.get('updateTime')
                    }
                    processed_members.append(member_info)
            
            # 构建优化的返回格式
            response_data = {
                "summary": {
                    "totalMembers": total_count,
                    "onlineMembers": online_count,
                    "offlineMembers": offline_count,
                    "membersWithAssets": assigned_assets_count,
                    "searchKeyword": keyword if keyword else None
                },
                "members": processed_members,
                "rawData": members_data  # 保留原始数据以备需要
            }
            
            logger.info(f"查询成功 - 总成员数:{total_count}, 在线:{online_count}, 离线:{offline_count}")
            return {
                "success": True, 
                "data": response_data, 
                "message": f"查询企业成员成功，共找到 {total_count} 名成员"
            }
        else:
            error_msg = f"接口调用失败，状态码: {resp.status_code}"
            try:
                error_detail = resp.json()
                error_msg += f"，错误详情: {error_detail}"
            except:
                error_msg += f"，响应内容: {resp.text}"

            logger.error(f"查询失败 - {error_msg}")
            return {"success": False, "error": error_msg, "status_code": resp.status_code}

    except requests.exceptions.RequestException as e:
        error_msg = f"网络请求异常: {str(e)}"
        logger.error(f"网络异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "network_error"}
    except json.JSONDecodeError as e:
        error_msg = f"响应解析异常: {str(e)}"
        logger.error(f"解析异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "parse_error"}
    except Exception as e:
        error_msg = f"未知异常: {str(e)}"
        logger.error(f"未知异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "unknown_error"}

@mcp.tool()
def add_enterprise_member_mcp(userToken: str, userName: str, password: str, name: str,
                              departmentId: int = None, remark: str = None,
                              passwordMobile: str = None, regionCode: str = None) -> dict:
    """添加企业成员 - 为企业添加新成员

    参数说明：
        userToken: 用户认证令牌
        userName: 账号名称，只能包含字母和数字，长度2-30个字符
        password: 初始密码，8-16个字符，必须包含至少两种字符类型（数字、字母、符号）
        name: 用户全名，最多30个字符
        departmentId: 部门ID（可选）
        remark: 备注信息，最多200个字符（可选）
        passwordMobile: 安全手机号，用于密码找回（可选）
        regionCode: 安全手机号的区域代码，仅国际站点有效（可选）

    返回格式：
        成功时返回API响应数据，失败时返回错误信息
    """
    try:
        headers = {
            "Authorization": f"Bearer {userToken}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        # 构建表单数据
        data = {
            "userName": userName,
            "password": password,
            "name": name
        }

        # 添加可选参数
        if departmentId is not None:
            data["departmentId"] = departmentId
        if remark is not None:
            data["remark"] = remark
        if passwordMobile is not None:
            data["passwordMobile"] = passwordMobile
        if regionCode is not None:
            data["regionCode"] = regionCode

        logger.info(f"添加企业成员 - 用户名:{userName}, 姓名:{name}")

        # 发送请求
        resp = requests.post(MEMBER_ADD_URL, data=data, headers=headers, timeout=30)

        # 检查响应状态
        if resp.status_code == 200:
            result = resp.json()
            logger.info(f"添加成员成功 - 状态码:{resp.status_code}")
            return {"success": True, "data": result, "message": "添加企业成员成功"}
        else:
            error_msg = f"接口调用失败，状态码: {resp.status_code}"
            try:
                error_detail = resp.json()
                error_msg += f"，错误详情: {error_detail}"
            except:
                error_msg += f"，响应内容: {resp.text}"

            logger.error(f"添加成员失败 - {error_msg}")
            return {"success": False, "error": error_msg, "status_code": resp.status_code}

    except requests.exceptions.RequestException as e:
        error_msg = f"网络请求异常: {str(e)}"
        logger.error(f"网络异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "network_error"}
    except json.JSONDecodeError as e:
        error_msg = f"响应解析异常: {str(e)}"
        logger.error(f"解析异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "parse_error"}
    except Exception as e:
        error_msg = f"未知异常: {str(e)}"
        logger.error(f"未知异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "unknown_error"}

@mcp.tool()
def generate_client_token_mcp(grantType: str = "client_credentials") -> dict:
    """生成客户端令牌 - 通过OAuth2客户端凭据流程获取访问令牌"""
    try:
        headers = {
            "Authorization": f"Basic {MEMBER_CLIENT_TOKEN_HEADER}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        data = {"grant_type": grantType}

        logger.info(f"生成客户端令牌 - 授权类型: {grantType}")

        resp = requests.post(MEMBER_CLIENT_TOKEN_URL, headers=headers, data=data, timeout=30)

        if resp.status_code == 200:
            result = resp.json()
            logger.info(f"令牌生成成功 - 状态码: {resp.status_code}")
            return {
                "success": True,
                "data": result,
                "message": "客户端令牌生成成功",
                "access_token": result.get("access_token"),
                "token_type": result.get("token_type"),
                "expires_in": result.get("expires_in")
            }
        else:
            error_msg = f"接口调用失败，状态码: {resp.status_code}"
            try:
                error_detail = resp.json()
                error_msg += f"，错误详情: {error_detail}"
            except:
                error_msg += f"，响应内容: {resp.text}"

            logger.error(f"令牌生成失败 - {error_msg}")
            return {"success": False, "error": error_msg, "status_code": resp.status_code}

    except requests.exceptions.RequestException as e:
        error_msg = f"网络请求异常: {str(e)}"
        logger.error(f"网络异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "network_error"}
    except json.JSONDecodeError as e:
        error_msg = f"响应解析异常: {str(e)}"
        logger.error(f"解析异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "parse_error"}
    except Exception as e:
        error_msg = f"未知异常: {str(e)}"
        logger.error(f"未知异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "unknown_error"}


@mcp.tool()
def generate_user_token_mcp(uid: str = None, grantType: str = "uid") -> dict:
    """生成用户令牌 - 通过OAuth2 UID流程获取用户访问令牌

    参数说明：
        uid: 用户ID
        grantType: 授权类型，默认为 "uid"

    返回格式：
        成功时返回包含访问令牌的响应数据，失败时返回错误信息
    """
    try:
        headers = {
            "Authorization": f"Basic {MEMBER_USER_TOKEN_HEADER}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        data = {
            "grant_type": grantType,
            "uid": uid
        }

        logger.info(f"生成用户令牌 - UID: {uid}, 授权类型: {grantType}")

        # 发送请求到OAuth端点
        resp = requests.post(MEMBER_USER_TOKEN_URL, headers=headers, data=data, timeout=30)

        # 检查响应状态
        if resp.status_code == 200:
            result = resp.json()
            logger.info(f"用户令牌生成成功 - 状态码: {resp.status_code}")
            return {
                "success": True,
                "data": result,
                "message": "用户令牌生成成功",
                "access_token": result.get("access_token"),
                "token_type": result.get("token_type"),
                "expires_in": result.get("expires_in"),
                "uid": uid
            }
        else:
            error_msg = f"接口调用失败，状态码: {resp.status_code}"
            try:
                error_detail = resp.json()
                error_msg += f"，错误详情: {error_detail}"
            except:
                error_msg += f"，响应内容: {resp.text}"

            logger.error(f"用户令牌生成失败 - {error_msg}")
            return {"success": False, "error": error_msg, "status_code": resp.status_code}

    except requests.exceptions.RequestException as e:
        error_msg = f"网络请求异常: {str(e)}"
        logger.error(f"网络异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "network_error"}
    except json.JSONDecodeError as e:
        error_msg = f"响应解析异常: {str(e)}"
        logger.error(f"解析异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "parse_error"}
    except Exception as e:
        error_msg = f"未知异常: {str(e)}"
        logger.error(f"未知异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "unknown_error"}

@mcp.tool()
def renew_asset_product_mcp(customerId: str, licenseId: str, 
                           limitEndTime: int, limitStartTime: int = None) -> dict:
    """资产下产品续费 - 为指定资产下的产品进行续费操作

    参数说明：
        customerId: 客户ID
        licenseId: 许可证ID
        limitEndTime: 结束时间戳（毫秒）
        limitStartTime: 开始时间戳（毫秒），不指定时取当前时间

    返回格式：
        成功时返回API响应数据，失败时返回错误信息
    """
    try:
        # 生成随机的channelOrderId（8位随机字符串 + 当前时间戳）
        random_str = ''.join(random.choices(string.digits + string.ascii_lowercase, k=8))
        current_timestamp = str(int(datetime.datetime.now().timestamp() * 1000))
        channel_order_id = f"{current_timestamp}{random_str}"
        
        # 如果未指定开始时间，使用当前时间
        if limitStartTime is None:
            limitStartTime = int(datetime.datetime.now().timestamp() * 1000)
        
        # 构建请求数据，参考图片中的JSON结构
        data = {
            "channelOrderId": channel_order_id,
            "syncMode": "async",
            "orderList": [
                {
                    "sequence": "0",
                    "customerId": customerId,
                    "licenseType": "cloud_customer",
                    "orderType": "renew_license",
                    "assets": [
                        {
                            "products": [
                                {
                                    "licenseId": licenseId,
                                    "limitEndDate": limitEndTime,
                                    "limitStartDate": limitStartTime
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        url = f"{ORDER_URL}/api/order/v1/licenseOrder/batchOrder?appKey={ORDER_APPKEY}"
        headers = {"Content-Type": "application/json"}

        logger.info(f"产品续费 - 客户ID:{customerId}, 许可证ID:{licenseId}, 订单ID:{channel_order_id}")

        # 发送请求
        resp = requests.post(url, json=data, headers=headers, timeout=30)

        # 检查响应状态
        if resp.status_code == 200:
            result = resp.json()
            logger.info(f"续费成功 - 状态码:{resp.status_code}, 订单ID:{channel_order_id}")
            return {
                "success": True, 
                "data": result, 
                "message": "产品续费成功",
                "channelOrderId": channel_order_id,
                "customerId": customerId,
                "licenseId": licenseId
            }
        else:
            error_msg = f"接口调用失败，状态码: {resp.status_code}"
            try:
                error_detail = resp.json()
                error_msg += f"，错误详情: {error_detail}"
            except:
                error_msg += f"，响应内容: {resp.text}"

            logger.error(f"续费失败 - {error_msg}")
            return {"success": False, "error": error_msg, "status_code": resp.status_code}

    except requests.exceptions.RequestException as e:
        error_msg = f"网络请求异常: {str(e)}"
        logger.error(f"网络异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "network_error"}
    except json.JSONDecodeError as e:
        error_msg = f"响应解析异常: {str(e)}"
        logger.error(f"解析异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "parse_error"}
    except Exception as e:
        error_msg = f"未知异常: {str(e)}"
        logger.error(f"未知异常 - {error_msg}")
        return {"success": False, "error": error_msg, "type": "unknown_error"}


if __name__ == "__main__":
    print("🚀 MyGlodon Asset & Member Management MCP Server")
    print("=" * 50)
    print("可用工具:")
    print("  • query_assets_by_status_mcp - 查询资产状态")
    print("  • allocate_asset_privileges_mcp - 分配/取消分配资产权限")
    print("  • query_asset_products_mcp - 查询资产下产品详情")
    print("  • query_enterprise_members_mcp - 查询企业成员")
    print("  • add_enterprise_member_mcp - 添加企业成员")
    print("  • generate_client_token_mcp - 生成客户端令牌")
    print("  • generate_user_token_mcp - 生成用户令牌")
    print("  • renew_asset_product_mcp - 资产下产品续费")
    print("=" * 50)
    print()

    # Run the server using FastMCP
    mcp.run(transport="sse", host=os.getenv("ASSET_SERVER_HOST"), port=int(os.getenv("ASSET_SERVER_PORT")))