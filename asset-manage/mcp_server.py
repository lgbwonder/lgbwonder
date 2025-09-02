#!/usr/bin/env python3
"""
MyGlodon Asset Management MCP Server

This MCP server provides access to MyGlodon asset management functionality
through the OpenAssetManageController API endpoints.
"""

import json
import logging
import os
from pathlib import Path
import requests
from fastmcp import FastMCP
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load Environment Variables
env_path = (Path(__file__).parent / "../system/.env").resolve()
load_dotenv(dotenv_path=env_path, verbose=True)

# Global constants
BASE_URL = os.getenv("MYGLODON_URL")

# Create FastMCP server
mcp = FastMCP(os.getenv("SERVER_NAME"))


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
        params = {
            "pageNum": pageNum,
            "pageSize": pageSize
        }

        data = {
            "searchType": searchType,
            "searchCondition": searchCondition,
            "assetStatus": assetStatus
        }

        headers = {
            "userToken": userToken,
            "clientToken": clientToken,
            "Content-Type": "application/json"
        }

        print(f"开始调用查询资产状态接口: {url}")
        print(f"请求参数: {params}")
        print(f"请求数据: {data}")

        # 发送请求
        resp = requests.post(url, params=params, json=data, headers=headers, timeout=30)

        # 检查响应状态
        if resp.status_code == 200:
            result = resp.json()
            print(f"接口调用成功: {result}")
            return {
                "success": True,
                "data": result,
                "message": "查询资产状态成功"
            }
        else:
            error_msg = f"接口调用失败，状态码: {resp.status_code}"
            try:
                error_detail = resp.json()
                error_msg += f"，错误详情: {error_detail}"
            except:
                error_msg += f"，响应内容: {resp.text}"

            print(f"接口调用失败: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "status_code": resp.status_code
            }

    except requests.exceptions.RequestException as e:
        error_msg = f"网络请求异常: {str(e)}"
        print(f"网络请求异常: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "type": "network_error"
        }
    except json.JSONDecodeError as e:
        error_msg = f"响应解析异常: {str(e)}"
        print(f"响应解析异常: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "type": "parse_error"
        }
    except Exception as e:
        error_msg = f"未知异常: {str(e)}"
        print(f"未知异常: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "type": "unknown_error"
        }


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
        url = f"{BASE_URL}/v1/assets/manage/asset/{assignType}/privileges"
        headers = {
            "userToken": userToken,
            "clientToken": clientToken,
            "Content-Type": "application/json"
        }

        print(f"开始调用分配资产权限接口: {url}")
        print(f"分配类型: {assignType}")
        print(f"资产权限列表: {assetPrivileges}")

        # 发送请求
        resp = requests.post(url, json=assetPrivileges, headers=headers, timeout=30)

        # 检查响应状态
        if resp.status_code == 200:
            result = resp.json()
            print(f"接口调用成功: {result}")
            return {
                "success": True,
                "data": result,
                "message": f"资产权限{assignType}操作成功"
            }
        else:
            error_msg = f"接口调用失败，状态码: {resp.status_code}"
            try:
                error_detail = resp.json()
                error_msg += f"，错误详情: {error_detail}"
            except:
                error_msg += f"，响应内容: {resp.text}"

            print(f"接口调用失败: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "status_code": resp.status_code
            }

    except requests.exceptions.RequestException as e:
        error_msg = f"网络请求异常: {str(e)}"
        print(f"网络请求异常: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "type": "network_error"
        }
    except json.JSONDecodeError as e:
        error_msg = f"响应解析异常: {str(e)}"
        print(f"响应解析异常: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "type": "parse_error"
        }
    except Exception as e:
        error_msg = f"未知异常: {str(e)}"
        print(f"未知异常: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "type": "unknown_error"
        }


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
        url = f"{BASE_URL}/v1/assets/manage/{assetId}/products/online"
        headers = {
            "userToken": userToken,
            "clientToken": clientToken
        }

        print(f"开始调用查询在线产品接口: {url}")
        print(f"资产ID: {assetId}")

        # 发送请求
        resp = requests.get(url, headers=headers, timeout=30)

        # 检查响应状态
        if resp.status_code == 200:
            result = resp.json()
            print(f"接口调用成功: {result}")
            return {
                "success": True,
                "data": result,
                "message": "查询在线产品成功"
            }
        else:
            error_msg = f"接口调用失败，状态码: {resp.status_code}"
            try:
                error_detail = resp.json()
                error_msg += f"，错误详情: {error_detail}"
            except:
                error_msg += f"，响应内容: {resp.text}"

            print(f"接口调用失败: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "status_code": resp.status_code
            }

    except requests.exceptions.RequestException as e:
        error_msg = f"网络请求异常: {str(e)}"
        print(f"网络请求异常: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "type": "network_error"
        }
    except json.JSONDecodeError as e:
        error_msg = f"响应解析异常: {str(e)}"
        print(f"响应解析异常: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "type": "parse_error"
        }
    except Exception as e:
        error_msg = f"未知异常: {str(e)}"
        print(f"未知异常: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "type": "unknown_error"
        }


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
        url = f"{BASE_URL}/v1/assets/manage/members"
        headers = {
            "userToken": userToken,
            "clientToken": clientToken
        }

        print(f"开始调用查询企业成员接口: {url}")

        # 发送请求
        resp = requests.get(url, headers=headers, timeout=30)

        # 检查响应状态
        if resp.status_code == 200:
            result = resp.json()
            print(f"接口调用成功: {result}")
            return {
                "success": True,
                "data": result,
                "message": "查询企业成员成功"
            }
        else:
            error_msg = f"接口调用失败，状态码: {resp.status_code}"
            try:
                error_detail = resp.json()
                error_msg += f"，错误详情: {error_detail}"
            except:
                error_msg += f"，响应内容: {resp.text}"

            print(f"接口调用失败: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "status_code": resp.status_code
            }

    except requests.exceptions.RequestException as e:
        error_msg = f"网络请求异常: {str(e)}"
        print(f"网络请求异常: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "type": "network_error"
        }
    except json.JSONDecodeError as e:
        error_msg = f"响应解析异常: {str(e)}"
        print(f"响应解析异常: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "type": "parse_error"
        }
    except Exception as e:
        error_msg = f"未知异常: {str(e)}"
        print(f"未知异常: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "type": "unknown_error"
        }


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
        url = f"{BASE_URL}/v1/assets/manage/asset/{assetId}/privilege/status"
        headers = {
            "userToken": userToken,
            "clientToken": clientToken
        }

        print(f"开始调用查询资产权限状态接口: {url}")
        print(f"资产ID: {assetId}")

        # 发送请求
        resp = requests.get(url, headers=headers, timeout=30)

        # 检查响应状态
        if resp.status_code == 200:
            result = resp.json()
            print(f"接口调用成功: {result}")
            return {
                "success": True,
                "data": result,
                "message": "查询资产权限状态成功"
            }
        else:
            error_msg = f"接口调用失败，状态码: {resp.status_code}"
            try:
                error_detail = resp.json()
                error_msg += f"，错误详情: {error_detail}"
            except:
                error_msg += f"，响应内容: {resp.text}"

            print(f"接口调用失败: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "status_code": resp.status_code
            }

    except requests.exceptions.RequestException as e:
        error_msg = f"网络请求异常: {str(e)}"
        print(f"网络请求异常: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "type": "network_error"
        }
    except json.JSONDecodeError as e:
        error_msg = f"响应解析异常: {str(e)}"
        print(f"响应解析异常: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "type": "parse_error"
        }
    except Exception as e:
        error_msg = f"未知异常: {str(e)}"
        print(f"未知异常: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "type": "unknown_error"
        }


if __name__ == "__main__":
    print("Starting MyGlodon Asset Management MCP Server")
    print("Server is running in FastMCP mode")
    print("Available tools:")
    print("  - query_assets_by_status_mcp: 查询资产状态")
    print("  - allocate_asset_privileges_mcp: 分配/取消分配资产权限")
    print("  - query_online_products_mcp: 查询在线产品")
    print("  - query_enterprise_members_mcp: 查询企业成员")
    print("  - query_asset_privilege_status_mcp: 查询资产权限状态")

    # Run the server using FastMCP
    mcp.run(transport="streamable-http", host=os.getenv("SERVER_HOST"), port=int(os.getenv("SERVER_PORT")))