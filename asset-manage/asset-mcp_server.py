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
ASSET_URL = os.getenv("ASSET_URL")
MEMBER_URL = os.getenv("MEMBER_URL")
MEMBER_BASIC_HEADER = os.getenv("MEMBER_BASIC_HEADER")

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
        成功时返回API响应数据，失败时返回错误信息
    """
    try:
        url = f"{BASE_URL}/v1/assets/manage/asset/status"
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
    """分配/取消分配资产权限 - 为指定资产分配或取消分配权限给成员

    参数说明：
        userToken: 用户认证令牌
        clientToken: 客户端认证令牌
        assignType: 分配类型，可选值：assign(分配权限), unassign(取消分配权限)
        assetPrivileges: 资产权限列表，每个项目包含：assetNum(资产编号), assetId(资产ID), memberId(成员ID)

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
def query_online_products_mcp(userToken: str, clientToken: str, assetId: str) -> dict:
    """查询在线产品 - 查询指定资产的在线云锁产品信息

    参数说明：
        userToken: 用户认证令牌
        clientToken: 客户端认证令牌
        assetId: 资产ID

    返回格式：
        成功时返回API响应数据，失败时返回错误信息
    """
    try:
        url = f"{ASSET_URL}/v1/assets/manage/{assetId}/products/online"
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
def query_enterprise_members_mcp(userToken: str, clientToken: str) -> dict:
    """查询企业成员 - 获取企业下的成员列表

    参数说明：
        userToken: 用户认证令牌
        clientToken: 客户端认证令牌

    返回格式：
        成功时返回API响应数据，失败时返回错误信息
    """
    try:
        url = f"{ASSET_URL}/v1/assets/manage/members"
        headers = {"userToken": userToken, "clientToken": clientToken}

        logger.info("查询企业成员")

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
def query_asset_privilege_status_mcp(userToken: str, clientToken: str, assetId: str) -> dict:
    """查询资产权限状态 - 获取资产的权限分配状态信息

    参数说明：
        userToken: 用户认证令牌
        clientToken: 客户端认证令牌
        assetId: 资产ID

    返回格式：
        成功时返回API响应数据，失败时返回错误信息
    """
    try:
        url = f"{ASSET_URL}/v1/assets/manage/asset/{assetId}/privilege/status"
        headers = {"userToken": userToken, "clientToken": clientToken}

        logger.info(f"查询资产权限状态 - 资产ID:{assetId}")

        # 发送请求
        resp = requests.get(url, headers=headers, timeout=30)

        # 检查响应状态
        if resp.status_code == 200:
            result = resp.json()
            logger.info(f"查询成功 - 状态码:{resp.status_code}")
            return {"success": True, "data": result, "message": "查询资产权限状态成功"}
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
def generate_client_token_mcp(authHeader: str = None, grantType: str = "client_credentials") -> dict:
    """生成客户端令牌 - 通过OAuth2客户端凭据流程获取访问令牌"""
    try:
        if authHeader is None:
            authHeader = MEMBER_BASIC_HEADER

        headers = {
            "Authorization": f"Basic {authHeader}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        data = {"grant_type": grantType}

        logger.info(f"生成客户端令牌 - 授权类型: {grantType}")

        resp = requests.post(MEMBER_URL, headers=headers, data=data, timeout=30)

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
def generate_user_token_mcp(uid: str, authHeader: str = None, grantType: str = "uid") -> dict:
    """生成用户令牌 - 通过OAuth2 UID流程获取用户访问令牌

    参数说明：
        uid: 用户ID
        authHeader: 授权头，Base64编码的客户端ID和密钥，格式为 "client_id:client_secret" 的Base64编码
        grantType: 授权类型，默认为 "uid"

    返回格式：
        成功时返回包含访问令牌的响应数据，失败时返回错误信息
    """
    try:
        # 使用传入的授权头或默认值
        if authHeader is None:
            authHeader = MEMBER_BASIC_HEADER

        headers = {
            "Authorization": f"Basic {authHeader}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        data = {
            "grant_type": grantType,
            "uid": uid
        }

        logger.info(f"生成用户令牌 - UID: {uid}, 授权类型: {grantType}")

        # 发送请求到OAuth端点
        resp = requests.post(MEMBER_URL, headers=headers, data=data, timeout=30)

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


if __name__ == "__main__":
    print("🚀 MyGlodon Asset & Member Management MCP Server")
    print("=" * 50)
    print("可用工具:")
    print("  • query_assets_by_status_mcp - 查询资产状态")
    print("  • allocate_asset_privileges_mcp - 分配/取消分配资产权限")
    print("  • query_online_products_mcp - 查询在线产品")
    print("  • query_enterprise_members_mcp - 查询企业成员")
    print("  • query_asset_privilege_status_mcp - 查询资产权限状态")
    print("  • generate_client_token_mcp - 生成客户端令牌")
    print("  • generate_user_token_mcp - 生成用户令牌")
    print("=" * 50)
    print()

    # Run the server using FastMCP
    mcp.run(transport="streamable-http", host=os.getenv("ASSET_SERVER_HOST"), port=int(os.getenv("ASSET_SERVER_PORT")))