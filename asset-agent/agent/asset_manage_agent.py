# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
基于ReActAgent的智能资产管理Agent (优化版：支持并发安全)
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, TypedDict
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.tools import Tool
from langchain_core.prompts import PromptTemplate

# 导入MCP客户端
try:
    from ..utils.mcp_client import MCPClient
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.mcp_client import MCPClient

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)


class AssetAllocationState(TypedDict):
    """资产分配状态"""
    messages: List[Any]
    user_token: Optional[str]
    client_token: Optional[str]
    available_assets: List[Dict[str, Any]]
    available_members: List[Dict[str, Any]]
    allocation_plan: Dict[str, Any]
    current_step: str
    error_message: Optional[str]
    mcp_tools: List[Dict[str, Any]]


class AssetManageAgent:
    """智能资产管理Agent - 基于ReAct模式（优化并发安全）"""

    def __init__(self, mcp_server_url: str = None):
        if mcp_server_url is None:
            mcp_server_url = os.getenv("MCP_SERVER_URL")

        self.mcp_client = MCPClient(mcp_server_url)

        # 配置LLM
        model = os.getenv("QWEN_MODEL", "qwen-plus")
        temperature = float(os.getenv("QWEN_TEMPERATURE", "0"))
        api_key = os.getenv("QWEN_API_KEY", "sk-8fe5cd468cd241d2b7fd2849468bcfde")
        base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

        if not api_key:
            logger.warning("QWEN_API_KEY 环境变量未设置，LLM功能可能无法正常工作")

        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=api_key,
            base_url=base_url,
            timeout=30,
            max_retries=3,         # 提高重试次数，避免一次失败就终止
            request_timeout=30,
            max_tokens=2000        # 增大输出限制，支持长结果
        )

        # 缓存工具
        self.tools: List[Tool] = []
        self._load_mcp_tools()

        # 缓存Agent提示模板
        self._prompt = self._build_prompt()

        logger.debug(f"Agent初始化完成，MCP服务器: {mcp_server_url}")

    def _build_prompt(self) -> PromptTemplate:
        """构建提示模板"""
        return PromptTemplate.from_template("""
            你是资产管理助手。能够理解自然语言并完成完整的多步骤任务流程。

            可用工具: {tools}

            任务流程:
            1. 获取认证令牌 (generate_client_token_mcp, generate_user_token_mcp)
            2. 创建或查询成员 (add_enterprise_member_mcp, query_enterprise_members_mcp)
            3. 查询资产状态 (query_assets_by_status_mcp)
            4. 分配资产权限 (allocate_asset_privileges_mcp)

            自然语言理解指南:
            - "创建账号XXX" → userName="XXX", name="XXX"
            - "密码为XXX" → password="XXX"
            - "密保手机为XXX" → passwordMobile="XXX"
            - "查询未分配资产" → assetStatus=["UNASSIGNED", "VALID"]

            格式:
            Question: {input}
            Thought: 分析用户需求，提取关键信息，规划下一步行动
            Action: [{tool_names}] 中的工具名
            Action Input: 完整JSON参数
            Observation: 工具执行结果
            ... (继续执行直到完成所有必要步骤)
            Final Answer: 任务完成总结

            重要规则:
            - Action Input必须是有效JSON，数组用[]，字符串用""
            - 示例: {{"userToken": "令牌", "assetStatus": ["UNASSIGNED", "VALID"]}}
            - 必须完成完整流程，不要在中途停止
            - 每个步骤都要检查结果是否成功
            - 从用户自然语言中智能提取参数信息
            - mcp工具调用时参数类型、参数个数严格按照接口描述进行传递
            - 新成员的 globalId 不为 memberId
            {agent_scratchpad}
        """)

    def _load_mcp_tools(self):
        """从MCP服务器加载工具"""
        try:
            tools_result = self.mcp_client.get_tools()

            if not tools_result.get("success"):
                logger.error(f"获取MCP工具失败: {tools_result.get('error')}")
                return

            mcp_tools = tools_result.get("data", [])
            self.tools = []

            for tool_info in mcp_tools:
                tool_name = tool_info.get("name")
                tool_description = tool_info.get("description", "")

                if not tool_name:
                    continue

                langchain_tool = Tool(
                    name=tool_name,
                    description=tool_description,
                    func=lambda args, name=tool_name: self._call_mcp_tool(name, args)
                )
                self.tools.append(langchain_tool)

            logger.info(f"加载了 {len(self.tools)} 个MCP工具")

        except Exception as e:
            logger.error(f"加载MCP工具失败: {str(e)}")
            raise e

    def _call_mcp_tool(self, tool_name: str, args):
        """调用MCP工具的包装函数"""
        try:
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    return f"参数格式错误: {args}"

            if not isinstance(args, dict):
                return f"参数类型错误: {type(args)}。请使用JSON格式的参数。"

            logger.info(f"调用MCP工具: {tool_name}")
            result = self.mcp_client.call_tool(tool_name, args)

            if result.get("success"):
                data = result.get("data", {})
                return json.dumps(data, ensure_ascii=False)
            else:
                return f"工具调用失败: {result.get('error', '未知错误')}"

        except Exception as e:
            logger.error(f"调用MCP工具异常: {str(e)}")
            return f"工具调用异常: {str(e)}"

    def _create_agent_executor(self) -> AgentExecutor:
        """每次请求动态创建新的AgentExecutor，保证并发安全"""
        agent = create_react_agent(self.llm, self.tools, self._prompt)
        return AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=False,
            max_iterations=8,
            max_execution_time=120,
            return_intermediate_steps=True,
            handle_parsing_errors=True,
            early_stopping_method="force"
        )

    def process_request(self, user_message: str) -> Dict[str, Any]:
        """处理用户请求（并发安全）"""
        try:
            logger.info(f"处理请求: {user_message[:50]}...")

            agent_executor = self._create_agent_executor()
            result = agent_executor.invoke({"input": user_message})

            output = result.get("output", "")
            intermediate_steps = result.get("intermediate_steps", [])
            tools_used = [step[0].tool for step in intermediate_steps if len(step) >= 2]

            return {
                "success": True,
                "message": "请求处理完成",
                "output": output,
                "tools_used": tools_used,
                "allocation_plan": self._extract_allocation_info(output),
                "current_step": "completed"
            }

        except Exception as e:
            logger.error(f"处理请求失败: {str(e)}")
            return {
                "success": False,
                "message": f"处理请求失败: {str(e)}",
                "allocation_plan": {},
                "current_step": "error",
                "mcp_tools_used": []
            }

    def _extract_allocation_info(self, output: str) -> Dict[str, Any]:
        """从输出中提取分配信息"""
        return {
            "summary": output,
            "timestamp": datetime.now().isoformat(),
            "status": "completed" if "成功" in output or "完成" in output else "failed"
        }

    def get_available_tools(self) -> List[str]:
        return [tool.name for tool in self.tools]

    def reload_tools(self):
        logger.info("重新加载MCP工具...")
        self._load_mcp_tools()


# ---------------- HTTP 服务部分 ----------------
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


class ProcessRequestModel(BaseModel):
    message: str
    mcp_server_url: str = None


_global_agent: Optional[AssetManageAgent] = None


def get_agent(mcp_server_url: str = None) -> AssetManageAgent:
    global _global_agent
    if _global_agent is None:
        _global_agent = AssetManageAgent(mcp_server_url)
    return _global_agent


def create_app() -> FastAPI:
    app = FastAPI(title="智能资产管理Agent API", version="1.0.0")

    @app.post("/process")
    async def process_request(request: ProcessRequestModel):
        try:
            agent = get_agent(request.mcp_server_url)
            return {"success": True, "data": agent.process_request(request.message)}
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": str(e)})

    @app.get("/tools")
    async def get_available_tools():
        try:
            agent = get_agent()
            return {"success": True, "data": agent.get_available_tools()}
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": str(e)})

    return app


def run_http_server(host="0.0.0.0", port=8001):
    if not FASTAPI_AVAILABLE:
        logger.error("FastAPI未安装，无法启动HTTP服务")
        return
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_http_server()
