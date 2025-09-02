#!/usr/bin/env python3
"""
MyGlodon Asset Management MCP Server

This MCP server provides access to MyGlodon asset management functionality
through the OpenAssetManageController API endpoints.
"""

import asyncio
import json
import logging
from typing import Any, Dict
import aiohttp
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.models import InitializationOptions
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    Tool,
    TextContent,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global constants
BASE_URL = "https://me-test.glodon.com"

# Create server instance
server = Server("myglodon-asset-management")


@server.list_tools()
async def list_tools() -> ListToolsResult:
    """List available tools for MyGlodon asset management."""
    tools = [
        Tool(
            name="query_assets_by_status",
            description="查询资产状态 - 根据状态查询企业资产信息，支持分页",
            inputSchema={
                "type": "object",
                "properties": {
                    "userToken": {
                        "type": "string",
                        "description": "用户认证令牌"
                    },
                    "clientToken": {
                        "type": "string",
                        "description": "客户端认证令牌"
                    },
                    "pageNum": {
                        "type": "integer",
                        "description": "页码，默认为1",
                        "default": 1
                    },
                    "pageSize": {
                        "type": "integer",
                        "description": "每页大小，默认为20",
                        "default": 20
                    },
                    "searchType": {
                        "type": "string",
                        "description": "搜索类型",
                        "enum": ["productUri", "productName", "assetNum", "memberAccount"]
                    },
                    "searchCondition": {
                        "type": "string",
                        "description": "搜索条件"
                    },
                    "assetStatus": {
                        "type": "string",
                        "description": "资产状态",
                        "enum": ["VALID", "EXPIRED", "UNASSIGNED", "ASSIGNED", "BORROWED", "ONLINED", "LOCKED"]
                    }
                },
                "required": ["userToken", "clientToken", "searchType", "searchCondition", "assetStatus"]
            }
        ),
        Tool(
            name="allocate_asset_privileges",
            description="分配/取消分配资产权限 - 为指定资产分配或取消分配权限给成员，返回操作状态。状态包括：NONE(无权限)、SUCCESS(分配成功)、FAILED(分配失败)、OCCUPIED(已分配给其他用户)、NOT_REQUIRED(无需分配)、BORROWED(已被借出)",
            inputSchema={
                "type": "object",
                "properties": {
                    "userToken": {
                        "type": "string",
                        "description": "用户认证令牌"
                    },
                    "clientToken": {
                        "type": "string",
                        "description": "客户端认证令牌"
                    },
                    "assignType": {
                        "type": "string",
                        "description": "分配类型",
                        "enum": ["assign", "unassign"]
                    },
                    "assetPrivileges": {
                        "type": "array",
                        "description": "资产权限列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "assetNum": {
                                    "type": "string",
                                    "description": "资产编号"
                                },
                                "assetId": {
                                    "type": "string",
                                    "description": "资产ID"
                                },
                                "memberId": {
                                    "type": "string",
                                    "description": "成员ID"
                                }
                            },
                            "required": ["assetNum", "assetId", "memberId"]
                        }
                    }
                },
                "required": ["userToken", "clientToken", "assignType", "assetPrivileges"]
            }
        ),
        Tool(
            name="query_online_products",
            description="查询在线产品 - 查询指定资产的在线云锁产品信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "userToken": {
                        "type": "string",
                        "description": "用户认证令牌"
                    },
                    "clientToken": {
                        "type": "string",
                        "description": "客户端认证令牌"
                    },
                    "assetId": {
                        "type": "string",
                        "description": "资产ID"
                    }
                },
                "required": ["userToken", "clientToken", "assetId"]
            }
        ),
        Tool(
            name="query_enterprise_members",
            description="查询企业成员 - 获取企业下的成员列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "userToken": {
                        "type": "string",
                        "description": "用户认证令牌"
                    },
                    "clientToken": {
                        "type": "string",
                        "description": "客户端认证令牌"
                    }
                },
                "required": ["userToken", "clientToken"]
            }
        ),
        Tool(
            name="query_asset_privilege_status",
            description="查询资产权限状态 - 获取资产的权限分配状态信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "userToken": {
                        "type": "string",
                        "description": "用户认证令牌"
                    },
                    "clientToken": {
                        "type": "string",
                        "description": "客户端认证令牌"
                    },
                    "assetId": {
                        "type": "string",
                        "description": "资产Id"
                    }
                },
                "required": ["userToken", "clientToken", "assetId"]
            }
        ),
    ]
    return ListToolsResult(tools=tools)


async def query_assets_by_status(arguments: Dict[str, Any]) -> CallToolResult:
    """查询资产状态"""
    user_token = arguments.get("userToken")
    client_token = arguments.get("clientToken")

    if not user_token:
        return CallToolResult(
            content=[TextContent(type="text", text="Error: userToken is required")]
        )
    if not client_token:
        return CallToolResult(
            content=[TextContent(type="text", text="Error: clientToken is required")]
        )

    url = f"{BASE_URL}/v1/assets/manage/asset/status"
    params = {
        "pageNum": arguments.get("pageNum", 1),
        "pageSize": arguments.get("pageSize", 20)
    }

    data = {
        "searchType": arguments["searchType"],
        "searchCondition": arguments["searchCondition"],
        "assetStatus": arguments["assetStatus"]
    }

    headers = {"userToken": user_token, "clientToken": client_token, "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, params=params, json=data, headers=headers) as response:
                result = await response.json()
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
                )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )


async def allocate_asset_privileges(arguments: Dict[str, Any]) -> CallToolResult:
    """分配资产权限"""
    user_token = arguments.get("userToken")
    client_token = arguments.get("clientToken")

    if not user_token:
        return CallToolResult(
            content=[TextContent(type="text", text="Error: userToken is required")]
        )
    if not client_token:
        return CallToolResult(
            content=[TextContent(type="text", text="Error: clientToken is required")]
        )

    assign_type = arguments["assignType"]
    asset_privileges = arguments["assetPrivileges"]

    url = f"{BASE_URL}/v1/assets/manage/asset/{assign_type}/privileges"
    headers = {"userToken": user_token, "clientToken": client_token, "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=asset_privileges, headers=headers) as response:
                result = await response.json()
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
                )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )


async def query_online_products(arguments: Dict[str, Any]) -> CallToolResult:
    """查询在线产品"""
    user_token = arguments.get("userToken")
    client_token = arguments.get("clientToken")

    if not user_token:
        return CallToolResult(
            content=[TextContent(type="text", text="Error: userToken is required")]
        )
    if not client_token:
        return CallToolResult(
            content=[TextContent(type="text", text="Error: clientToken is required")]
        )

    asset_id = arguments["assetId"]
    url = f"{BASE_URL}/v1/assets/manage/{asset_id}/products/online"
    headers = {"userToken": user_token, "clientToken": client_token}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                result = await response.json()
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
                )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )


async def query_enterprise_members(arguments: Dict[str, Any]) -> CallToolResult:
    """查询企业成员"""
    user_token = arguments.get("userToken")
    client_token = arguments.get("clientToken")

    if not user_token:
        return CallToolResult(
            content=[TextContent(type="text", text="Error: userToken is required")]
        )
    if not client_token:
        return CallToolResult(
            content=[TextContent(type="text", text="Error: clientToken is required")]
        )

    url = f"{BASE_URL}/v1/assets/manage/members"
    headers = {"userToken": user_token, "clientToken": client_token}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                result = await response.json()
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
                )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )


async def query_asset_privilege_status(arguments: Dict[str, Any]) -> CallToolResult:
    """查询资产权限状态"""
    user_token = arguments.get("userToken")
    client_token = arguments.get("clientToken")

    if not user_token:
        return CallToolResult(
            content=[TextContent(type="text", text="Error: userToken is required")]
        )
    if not client_token:
        return CallToolResult(
            content=[TextContent(type="text", text="Error: clientToken is required")]
        )

    asset_id = arguments["assetId"]
    url = f"{BASE_URL}/v1/assets/manage/asset/{asset_id}/privilege/status"
    headers = {"userToken": user_token, "clientToken": client_token}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                result = await response.json()
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
                )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )


async def main():
    """Main entry point for the MCP server."""
    print("Starting MyGlodon Asset Management MCP Server")
    print("Server is running in stdio mode - suitable for MCP client integration")
    print("To use HTTP API, you can integrate with MCP clients like Claude Desktop")

    # Run the server using stdio (standard MCP mode)
    async with stdio_server() as (read_stream, write_stream):
        print("Server started successfully in stdio mode")
        # Create capabilities manually to avoid None issues
        capabilities = {
            "tools": {
                "listChanged": False,  # 工具列表是否可变
                "maxTools": 100  # 最大工具数量
            },
            "notifications": {
                "supported": False  # 是否支持通知
            },
            "resources": {
                "supported": False  # 是否支持资源管理
            },
            "logging": {
                "supported": False  # 是否支持日志
            }
        }

        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="myglodon-asset-management",
                server_version="1.0.0",
                capabilities=capabilities,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())