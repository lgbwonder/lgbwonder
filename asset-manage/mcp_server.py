#!/usr/bin/env python3
"""
MyGlodon Asset Management MCP Server

This MCP server provides access to MyGlodon asset management functionality
through the OpenAssetManageController API endpoints.
"""

import json
import logging
from typing import Any, Dict
import aiohttp
from fastapi import FastAPI
from mcp.server import Server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    ListToolsResult,
    Tool,
    TextContent,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global constants
BASE_URL = "https://me-test.glodon.com"
HOST = "127.0.0.1"  # Listen on localhost only
PORT = 18080  # HTTP port

# Create FastAPI app
app = FastAPI(title="MyGlodon Asset Management MCP Server", version="1.0.0")

# Create MCP server
mcp_server = Server("myglodon-asset-management")


# Define tools
def get_tools():
    """Get the list of available tools."""
    return [
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


# Set up MCP server handlers
async def handle_list_tools(request: ListToolsRequest) -> ListToolsResult:
    """Handle list tools request."""
    return ListToolsResult(tools=get_tools())


async def handle_call_tool(request: CallToolRequest) -> CallToolResult:
    """Handle tool call request."""
    try:
        if request.name == "query_assets_by_status":
            return await query_assets_by_status(request.arguments)
        elif request.name == "allocate_asset_privileges":
            return await allocate_asset_privileges(request.arguments)
        elif request.name == "query_online_products":
            return await query_online_products(request.arguments)
        elif request.name == "query_enterprise_members":
            return await query_enterprise_members(request.arguments)
        elif request.name == "query_asset_privilege_status":
            return await query_asset_privilege_status(request.arguments)
        else:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Unknown tool: {request.name}")]
            )
    except Exception as e:
        logger.error(f"Error executing tool {request.name}: {str(e)}")
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )


# Set up the server handlers
mcp_server.list_tools = handle_list_tools
mcp_server.call_tool = handle_call_tool


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


# Add MCP endpoints to FastAPI app
@app.post("/mcp/tools/list")
async def mcp_list_tools():
    """MCP tools list endpoint."""
    tools = get_tools()
    # Convert Tool objects to dictionaries
    tools_list = []
    for tool in tools:
        tool_dict = {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.inputSchema
        }
        tools_list.append(tool_dict)
    return {"tools": tools_list}


@app.post("/mcp/tools/call")
async def mcp_call_tool(request: dict):
    """MCP tool call endpoint."""
    tool_name = request.get("name")
    arguments = request.get("arguments", {})

    try:
        if tool_name == "query_assets_by_status":
            result = await query_assets_by_status(arguments)
        elif tool_name == "allocate_asset_privileges":
            result = await allocate_asset_privileges(arguments)
        elif tool_name == "query_online_products":
            result = await query_online_products(arguments)
        elif tool_name == "query_enterprise_members":
            result = await query_enterprise_members(arguments)
        elif tool_name == "query_asset_privilege_status":
            result = await query_asset_privilege_status(arguments)
        else:
            return {"error": f"Unknown tool: {tool_name}"}

        # Convert MCP result to simple dict
        return {
            "content": [
                {
                    "type": content.type,
                    "text": content.text
                } for content in result.content
            ]
        }
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {str(e)}")
        return {"error": str(e)}


# Add health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "MyGlodon Asset Management MCP Server"}


# Add root endpoint
@app.get("/")
async def root():
    """Root endpoint with server information."""
    return {
        "service": "MyGlodon Asset Management MCP Server",
        "version": "1.0.0",
        "mode": "FastAPI + FastMCP",
        "endpoints": {
            "mcp": "/mcp",
            "health": "/health",
            "docs": "/docs"
        }
    }


if __name__ == "__main__":
    import uvicorn

    print("Starting MyGlodon Asset Management MCP Server")
    print(f"Server is running in FastAPI + MCP mode on {HOST}:{PORT}")
    print("You can access the server at:")
    print(f"  - Main API: http://{HOST}:{PORT}")
    print(f"  - MCP Endpoint: http://{HOST}:{PORT}/mcp")
    print(f"  - API Documentation: http://{HOST}:{PORT}/docs")
    print(f"  - Health Check: http://{HOST}:{PORT}/health")

    # Run the server using uvicorn
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info"
    )