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

    Args:
        userToken (str): 用户认证令牌
        clientToken (str): 客户端认证令牌
        searchType (str): 搜索类型，可选值：productUri, productName, assetNum, memberAccount
        searchCondition (str): 搜索条件，不指定具体搜索条件时，需要传递 ""
        assetStatus (list): 资产状态列表，可选值：["VALID", "EXPIRED", "UNASSIGNED", "ASSIGNED", "BORROWED", "ONLINED", "LOCKED"]
        pageNum (int, optional): 页码，默认为1
        pageSize (int, optional): 每页大小，默认为20

    Returns:
        dict: API原始响应数据，包含以下完整结构：
        
        成功时返回：
        {
            "success": true,
            "message": "success",
            "data": {
                "assetSize": 总资产数量,
                "assetDetails": [
                    {
                        "asset": {
                            "assetNum": "资产编号",
                            "assetId": "资产ID", 
                            "assetStatus": ["资产状态列表"],
                            "limitStartDate": 开始时间戳,
                            "limitEndDate": 结束时间戳,
                            "borrowAsset": "借出资产信息"
                        },
                        "member": {
                            "memberName": "成员姓名",
                            "memberId": "成员ID",
                            "memberAccount": "成员账号", 
                            "globalId": "全局ID",
                            "memberPhone": "成员手机号"
                        },
                        "customerId": "客户ID"
                    }
                ]
            }
        }
        
        失败时返回：
        {
            "success": false,
            "message": "错误描述", 
            "data": null
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
            logger.info(f"查询成功 - 状态码:{resp.status_code}")
            return {"success": True, "data": result, "message": "查询资产状态成功"}
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
    """分配/取消分配资产权限 - 为指定资产分配或取消分配权限给成员，支持批量操作

    Args:
        userToken (str): 用户认证令牌，从 generate_user_token_mcp 获取
        clientToken (str): 客户端认证令牌，从 generate_client_token_mcp 获取
        assignType (str): 分配类型，可选值："assign"(分配权限)或"unassign"(取消分配权限)
        assetPrivileges (list): 资产权限列表，每个元素为包含以下字段的字典：
            - assetNum (str): 资产编号，必填
            - assetId (str): 资产ID，必填  
            - memberId (str): 授权成员ID，必填

    Returns:
        dict: API原始响应数据
        
        成功时返回：
        {
            "success": true,
            "data": API响应结果,
            "message": "资产权限{assignType}操作成功"
        }
        
        失败时返回：
        {
            "success": false,
            "error": "错误描述",
            "status_code": HTTP状态码
        }
        
    Example:
        assetPrivileges = [
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
        
    Note:
        - 可以同时操作多个资产权限
        - 每个资产权限操作都是独立的
        - 资产编号和资产ID必须对应同一个资产
        - 成员ID必须是有效的企业成员
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

    Args:
        userToken (str): 用户认证令牌
        clientToken (str): 客户端认证令牌
        assetId (str): 资产ID

    Returns:
        dict: API原始响应数据，包含以下完整结构：
        
        成功时返回：
        {
            "success": true,
            "message": "success",
            "data": {
                "productInstanceList": [
                    {
                        "id": "产品实例ID",
                        "licenseId": "许可证ID",
                        "licenseType": "许可证类型",
                        "customerId": "客户ID",
                        "assetId": "资产ID",
                        "assetInsId": "资产实例ID", 
                        "merchandiseInsId": "商品实例ID",
                        "assetNum": "资产编号",
                        "productUri": "产品URI",
                        "gmsPid": "GMS产品ID",
                        "appKey": "应用密钥",
                        "productName": "产品名称",
                        "channelCode": "渠道代码",
                        "licenseOrderId": "许可证订单ID",
                        "channelOrderId": "渠道订单ID",
                        "limitStartTime": "限制开始时间",
                        "limitEndTime": "限制结束时间",
                        "limitAmount": "限制数量",
                        "limitConcurrent": "限制并发数",
                        "limitTimeDuration": "限制时间持续时间",
                        "trial": "试用标识",
                        "trialEndDate": "试用结束日期",
                        "limitType": "限制类型",
                        "prodDefExtend": "产品默认扩展",
                        "timeDurationExpression": "时间持续时间表达式",
                        "srcLicenseOrderId": "原订单号",
                        "createTime": "创建时间",
                        "updateTime": "更新时间",
                        "activateFlag": "激活标识",
                        "crmProductId": "CRM产品ID",
                        "parentProductUri": "父产品URI（可能为空）",
                        "parentProductName": "父产品名称（可能为空）",
                        "productExtendInstanceList": [
                            {
                                "id": "产品扩展实例ID",
                                "productInsId": "产品实例ID",
                                "customerId": "客户ID",
                                "limitType": "限制类型",
                                "limitCode": "限制代码",
                                "limitValue": "限制值",
                                "limitValueUsed": "已使用限制值",
                                "limitValueType": "限制值类型",
                                "trial": "试用标识",
                                "trialEndDate": "试用结束日期",
                                "createTime": "创建时间", 
                                "updateTime": "更新时间",
                                "limitName": "限制名称"
                            }
                        ]
                    }
                ]
            }
        }
        
        失败时返回：
        {
            "success": false,
            "message": "错误描述",
            "data": null
        }
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

    Args:
        userToken (str): 用户认证令牌
        clientToken (str): 客户端认证令牌
        keyword (str, optional): 搜索关键词，支持按账号模糊搜索，默认为空

    Returns:
        dict: API原始响应数据，包含以下完整结构：
        
        成功时返回：
        {
            "success": true,
            "message": "success",
            "data": [
                {
                    "id": "授权成员ID",
                    "userId": "用户中心userId，默认赋值为globalId",
                    "globalId": "用户中心gid",
                    "enterpriseId": "用户中心企业id，赋值为授权客户关联的企业主账号id",
                    "departmentId": "所属部门id（可能为空）",
                    "departmentName": "所属部门名称（可能为空）",
                    "userName": "用户名，授权成员的cloudAccountIdentity",
                    "password": "密码（为空）",
                    "passwordMobile": "密保手机（可能为空）",
                    "name": "姓名，授权成员的memberName",
                    "assetNums": ["分配的资产编号列表"],
                    "borrowNum": "借出锁编号（可能为空）",
                    "onlineFlag": true/false,
                    "remark": "备注（可能为空）",
                    "deleted": true/false,
                    "updateTime": "更新时间",
                    "createTime": "创建时间"
                }
            ]
        }
        
        失败时返回：
        {
            "success": false,
            "message": "错误描述",
            "data": null
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
            logger.info(f"查询成功 - 状态码:{resp.status_code}")
            return {"success": True, "data": result, "message": "查询企业成员成功"}
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
def add_enterprise_member_mcp(userToken: str, userName: str, password: str, name: str) -> dict:
    """添加用户中心成员 - 成功时返回的ID并非授权成员ID

    Args:
        userToken (str): 用户认证令牌
        userName (str): 账号名称，只能包含字母和数字，长度2-30个字符
        password (str): 初始密码，8-16个字符，必须包含至少两种字符类型（数字、字母、符号）
        name (str): 用户全名，最多30个字符

    Returns:
        dict: API原始响应数据
        
        成功时返回：
        {
         "code": 0,
         "message": "OK",
         "data": {
                 "id": 1260628957136352,//用户中心成员id
                 "userId": 6357051057240272929,//用户中心用户id
                 "globalId": "6357051057240272929",//用户中心globalId
                 "enterpriseId": 6339382805877858516,//企业id
                 "departmentId": null,//部门id
                 "departmentName": null,//部门名称
                 "userName": "测试账号@liuyjTest",//用户中心成员账号
                 "name": "测试姓名",//用户姓名
                 "remark": null,//备注
                 "deleted": false,//是否删除
                 "passwordMobile": "11010001000",//密保手机
                 "updateTime": 1515639113000,
                 "createTime": 1515639113000
            }
        }
        
        失败时返回：
        {
            "success": false,
            "error": "错误描述",
            "status_code": HTTP状态码
        }
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
            "name": name,
        }

        logger.info(f"添加企业成员 - 用户名:{userName}, 姓名:{name}")

        # 发送请求
        resp = requests.post(MEMBER_ADD_URL, data=data, headers=headers, timeout=30)

        logger.error(resp.json())

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
    """生成客户端令牌 - 通过OAuth2客户端凭据流程获取访问令牌

    Args:
        grantType (str, optional): 授权类型，固定为"client_credentials"，默认已设置

    Returns:
        dict: API原始响应数据，包含访问令牌信息
        
        成功时返回：
        {
            "success": true,
            "data": API响应结果,
            "message": "客户端令牌生成成功",
            "access_token": "访问令牌",
            "token_type": "令牌类型",
            "expires_in": 过期时间秒数
        }
        
        失败时返回：
        {
            "success": false,
            "error": "错误描述",
            "status_code": HTTP状态码
        }
    """
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

    Args:
        uid (str, optional): 用户ID，可选
        grantType (str, optional): 授权类型，固定为"uid"，默认已设置

    Returns:
        dict: API原始响应数据，包含用户访问令牌信息
        
        成功时返回：
        {
            "success": true,
            "data": API响应结果,
            "message": "用户令牌生成成功",
            "access_token": "访问令牌",
            "token_type": "令牌类型",
            "expires_in": 过期时间秒数,
            "uid": "用户ID"
        }
        
        失败时返回：
        {
            "success": false,
            "error": "错误描述",
            "status_code": HTTP状态码
        }
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

    Args:
        customerId (str): 客户ID
        licenseId (str): 许可证ID
        limitEndTime (int): 结束时间戳（毫秒）
        limitStartTime (int, optional): 开始时间戳（毫秒），不指定时取当前时间

    Returns:
        dict: API原始响应数据
        
        成功时返回：
        {
            "success": true,
            "data": API响应结果,
            "message": "产品续费成功",
            "channelOrderId": "渠道订单ID",
            "customerId": "客户ID",
            "licenseId": "许可证ID"
        }
        
        失败时返回：
        {
            "success": false,
            "error": "错误描述",
            "status_code": HTTP状态码
        }
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
    mcp.run(transport="streamable-http", host=os.getenv("ASSET_SERVER_HOST"), port=int(os.getenv("ASSET_SERVER_PORT")))