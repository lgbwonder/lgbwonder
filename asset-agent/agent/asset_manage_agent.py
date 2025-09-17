# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
基于ReActAgent的智能资产管理Agent

该Agent能够实时获取MCP服务器的工具并动态调用，实现智能的资产分配决策和操作。
"""

import os
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional, TypedDict
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.tools import Tool
from langchain_core.prompts import PromptTemplate

# 导入MCP客户端
try:
    from ..utils.mcp_client import MCPClient
except ImportError:
    # 支持直接运行脚本
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
    """智能资产管理Agent - 基于ReAct模式"""
    
    def __init__(self, mcp_server_url: str = None):
        # 从环境变量获取MCP服务器地址，如果没有则使用默认值
        if mcp_server_url is None:
            mcp_server_url = os.getenv("MCP_SERVER_URL")
        
        self.mcp_client = MCPClient(mcp_server_url)
        
        # 配置LLM，添加超时和错误处理
        model = os.getenv("QWEN_MODEL", "qwen-plus")
        temperature = float(os.getenv("QWEN_TEMPERATURE", "0.1"))
        api_key = os.getenv("QWEN_API_KEY", "sk-8fe5cd468cd241d2b7fd2849468bcfde")
        base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        
        if not api_key:
            logger.warning("QWEN_API_KEY 环境变量未设置，LLM功能可能无法正常工作")
        
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=api_key,
            base_url=base_url,
            timeout=30,                             # 减少到30秒超时
            max_retries=1,                          # 减少重试次数
            request_timeout=30,                     # 请求超时30秒
            max_tokens=1000                         # 限制最大输出长度
        )
        
        # 初始化工具和代理
        self.tools = []
        self.agent_executor = None
        self._initialize_agent()
        
        logger.debug(f"Agent初始化完成，MCP服务器: {mcp_server_url}")
    
    def _initialize_agent(self):
        """初始化ReAct Agent"""
        try:
            # 从MCP服务器加载工具
            self._load_mcp_tools()
            
                        # 创建简化的ReAct Agent提示模板
            prompt = PromptTemplate.from_template("""
                资产管理助手。用JSON格式调用工具。

                可用工具: {tools}

                格式:
                Question: {input}
                Thought: 下一步行动
                Action: [{tool_names}] 中的工具名
                Action Input: JSON参数
                Observation: 结果
                Final Answer: 答案

                规则: 用完整JSON，包含所有必需参数
                流程: 获取令牌→查询→分配

                {agent_scratchpad}
                """)
            
            # 创建ReAct Agent
            agent = create_react_agent(self.llm, self.tools, prompt)
            
            # 创建Agent执行器
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=self.tools,
                verbose=False,                      # 关闭详细输出以提高性能
                max_iterations=4,                   # 减少迭代次数以提高速度
                max_execution_time=60,              # 减少到1分钟
                return_intermediate_steps=True,
                handle_parsing_errors=True
            )
            
            logger.info(f"ReAct Agent初始化完成，加载了 {len(self.tools)} 个工具")
            
        except Exception as e:
            logger.error(f"初始化Agent失败: {str(e)}")
            raise e
    
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
                
                # 创建LangChain Tool对象，增强描述信息
                enhanced_description = self._enhance_tool_description(
                    tool_name, tool_description, tool_info
                )
                langchain_tool = Tool(
                    name=tool_name,
                    description=enhanced_description,
                    func=lambda args, name=tool_name: self._call_mcp_tool(name, args)
                )
                
                self.tools.append(langchain_tool)
            
            logger.debug(f"加载了 {len(self.tools)} 个MCP工具")
            
        except Exception as e:
            logger.error(f"加载MCP工具失败: {str(e)}")
            raise e
    
    def _enhance_tool_description(
        self, tool_name: str, description: str, tool_info: Dict
    ) -> str:
        """增强工具描述，简化参数信息以提高速度"""
        # 只保留核心描述，简化参数示例
        tool_descriptions = {
            "query_assets_by_status_mcp": 
                "查询资产状态。参数: userToken, clientToken, searchType(productName), searchCondition, assetStatus([UNASSIGNED])",
            "allocate_asset_privileges_mcp": 
                "分配资产权限。参数: userToken, clientToken, assignType(assign), assetPrivileges",
            "query_enterprise_members_mcp": 
                "查询企业成员。参数: userToken, clientToken, keyword",
            "generate_client_token_mcp": 
                "生成客户端令牌。参数: grantType(client_credentials)",
            "generate_user_token_mcp": 
                "生成用户令牌。参数: uid, grantType(uid)"
        }
        
        return tool_descriptions.get(tool_name, description[:100])
    
    def _validate_tool_parameters(
        self, tool_name: str, args: Dict
    ) -> Optional[str]:
        """验证工具参数"""
        required_params = {
            "query_assets_by_status_mcp": [
                "userToken", "clientToken", "searchType", 
                "searchCondition", "assetStatus"
            ],
            "allocate_asset_privileges_mcp": [
                "userToken", "clientToken", "assignType", "assetPrivileges"
            ],
            "query_enterprise_members_mcp": [
                "userToken", "clientToken"
            ],
            "generate_client_token_mcp": [
                "grantType"
            ],
            "generate_user_token_mcp": [
                "grantType"
            ],
            "query_asset_products_mcp": [
                "userToken", "clientToken", "assetId"
            ],
            "add_enterprise_member_mcp": [
                "userToken", "userName", "password", "name"
            ],
            "renew_asset_product_mcp": [
                "customerId", "licenseId", "limitEndTime"
            ]
        }
        
        if tool_name in required_params:
            missing_params = []
            for param in required_params[tool_name]:
                if param not in args:
                    missing_params.append(param)
            
            if missing_params:
                return f"缺少必需参数: {', '.join(missing_params)}。请提供完整的参数。"
        
        # 特殊验证
        if tool_name == "query_assets_by_status_mcp":
            valid_search_types = [
                "productUri", "productName", "assetNum", "memberAccount"
            ]
            if ("searchType" in args and 
                args["searchType"] not in valid_search_types):
                return f"searchType必须是: {', '.join(valid_search_types)} 中的一个"
            
            if "assetStatus" in args and not isinstance(args["assetStatus"], list):
                return "assetStatus必须是列表格式"
        
        return None
    
    def _call_mcp_tool(self, tool_name: str, args):
        """调用MCP工具的包装函数"""
        try:
            # 如果args是字符串，尝试解析为JSON
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    logger.warning(f"无法解析参数为JSON: {args}")
                    return f"参数格式错误: {args}"
            
            # 确保args是字典
            if not isinstance(args, dict):
                logger.warning(
                    f"参数类型错误，期望dict但得到{type(args)}: {args}"
                )
                return f"参数类型错误: {type(args)}。请使用JSON格式的参数。"
            
            # 验证特定工具的必需参数
            validation_error = self._validate_tool_parameters(tool_name, args)
            if validation_error:
                logger.warning(f"参数验证失败: {validation_error}")
                return f"参数验证失败: {validation_error}"
            
            logger.info(f"调用MCP工具: {tool_name}")
            logger.debug(f"参数: {args}")
            
            result = self.mcp_client.call_tool(tool_name, args)
            
            if result.get("success"):
                data = result.get("data", {})
                # 返回更简洁的结果，避免过长的JSON字符串
                if isinstance(data, dict):
                    # 对于复杂的数据结构，返回摘要信息
                    if len(str(data)) > 1000:
                        summary = {
                            "status": "success",
                            "tool": tool_name,
                            "message": "操作成功完成"
                        }
                        # 保留关键信息
                        if "message" in data:
                            summary["result"] = data["message"]
                        elif "access_token" in data:
                            summary["result"] = "令牌获取成功"
                        return json.dumps(summary, ensure_ascii=False)
                    else:
                        return json.dumps(data, ensure_ascii=False)
                else:
                    return str(data)
            else:
                error_msg = result.get("error", "未知错误")
                logger.error(f"MCP工具调用失败: {error_msg}")
                return f"工具调用失败: {error_msg}"
                
        except Exception as e:
            logger.error(f"调用MCP工具异常: {str(e)}")
            return f"工具调用异常: {str(e)}"
    
    def reload_tools(self):
        """重新加载MCP工具"""
        try:
            logger.info("重新加载MCP工具...")
            self._load_mcp_tools()
            
            if self.agent_executor:
                # 重新初始化Agent
                self._initialize_agent()
                logger.info("Agent工具已重新加载")
            
        except Exception as e:
            logger.error(f"重新加载工具失败: {str(e)}")
            raise e
    
    def get_available_tools(self) -> List[str]:
        """获取可用工具列表"""
        return [tool.name for tool in self.tools]
    
    def quick_invoke(self, message: str) -> str:
        """快速调用agent.invoke的便捷方法"""
        try:
            result = self.process_request(message)
            if result.get("success"):
                return result.get("output", "处理完成")
            else:
                return f"处理失败: {result.get('message')}"
        except Exception as e:
            return f"调用失败: {str(e)}"
    
    def process_request(self, user_message: str) -> Dict[str, Any]:
        """处理用户请求"""
        try:
            logger.info(f"处理请求: {user_message[:50]}{'...' if len(user_message) > 50 else ''}")
            
            if not self.agent_executor:
                logger.error("Agent执行器未初始化")
                return {
                    "success": False,
                    "message": "Agent执行器未初始化",
                    "allocation_plan": {},
                    "current_step": "error",
                    "mcp_tools_used": []
                }
            
            # 使用ReAct Agent处理请求
            try:
                result = self.agent_executor.invoke({
                    "input": user_message
                })
                
                # 提取结果
                output = result.get("output", "")
                intermediate_steps = result.get("intermediate_steps", [])
                
                # 分析中间步骤，提取使用的工具
                tools_used = []
                for step in intermediate_steps:
                    if len(step) >= 2:
                        action = step[0]
                        if hasattr(action, 'tool'):
                            tools_used.append(action.tool)
                
                logger.info(f"ReAct Agent处理完成，使用了 {len(tools_used)} 个工具")
                
                return {
                    "success": True,
                    "message": "请求处理完成",
                    "output": output,
                    "intermediate_steps": intermediate_steps,
                    "tools_used": tools_used,
                    "allocation_plan": self._extract_allocation_info(output),
                    "current_step": "completed"
                }
                
            except Exception as agent_error:
                logger.error(f"Agent执行失败: {str(agent_error)}")
                return {
                    "success": False,
                    "message": f"Agent执行失败: {str(agent_error)}",
                    "allocation_plan": {},
                    "current_step": "error",
                    "mcp_tools_used": []
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
        try:
            # 尝试从输出中提取结构化的分配信息
            # 这里可以根据实际输出格式进行调整
            allocation_plan = {
                "summary": output,
                "timestamp": datetime.now().isoformat(),
                "status": "completed" if "成功" in output or "完成" in output else "failed"
            }
            
            return allocation_plan
            
        except Exception as e:
            logger.debug(f"提取分配信息失败: {str(e)}")
            return {"summary": output}

# HTTP 服务相关导入
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# 请求模型
class ProcessRequestModel(BaseModel):
    """处理请求的数据模型"""
    message: str
    mcp_server_url: str = None

class AgentStatusModel(BaseModel):
    """Agent状态模型"""
    pass

# 全局Agent实例
_global_agent = None

def get_agent(mcp_server_url: str = None) -> AssetManageAgent:
    """获取或创建Agent实例"""
    global _global_agent
    if _global_agent is None:
        _global_agent = AssetManageAgent(mcp_server_url)
    return _global_agent

def create_app() -> FastAPI:
    """创建FastAPI应用"""
    app = FastAPI(
        title="智能资产管理Agent API",
        description="基于ReAct Agent和MCP的智能资产管理Agent HTTP服务",
        version="1.0.0"
    )
    
    @app.get("/")
    async def root():
        """根路径"""
        return {
            "message": "智能资产管理Agent HTTP服务",
            "version": "1.0.0",
            "status": "running",
            "agent_type": "ReAct Agent"
        }
    
    @app.get("/health")
    async def health_check():
        """健康检查"""
        try:
            agent = get_agent()
            # 简单检查MCP客户端是否可用
            tools_result = agent.mcp_client.get_tools()
            mcp_status = "connected" if tools_result.get("success") else "disconnected"
            
            return {
                "status": "healthy",
                "mcp_status": mcp_status,
                "tools_count": len(tools_result.get("data", [])) if tools_result.get("success") else 0,
                "agent_type": "ReAct Agent"
            }
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "unhealthy",
                    "error": str(e)
                }
            )
    
    @app.post("/process")
    async def process_request(request: ProcessRequestModel):
        """处理用户请求"""
        try:
            agent = get_agent(request.mcp_server_url)
            result = agent.process_request(request.message)
            
            return {
                "success": True,
                "data": result,
                "message": "请求处理完成"
            }
        except Exception as e:
            logger.error(f"处理请求失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail={
                    "success": False,
                    "error": str(e),
                    "message": "请求处理失败"
                }
            )
    
    @app.get("/tools")
    async def get_available_tools():
        """获取可用工具列表"""
        try:
            agent = get_agent()
            tools_result = agent.mcp_client.get_tools()
            
            return {
                "success": True,
                "data": tools_result.get("data", []),
                "count": len(tools_result.get("data", [])),
                "message": "获取工具列表成功"
            }
        except Exception as e:
            logger.error(f"获取工具列表失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail={
                    "success": False,
                    "error": str(e),
                    "message": "获取工具列表失败"
                }
            )
    
    @app.post("/reload-tools")
    async def reload_tools():
        """重新加载MCP工具"""
        try:
            agent = get_agent()
            agent.reload_tools()
            
            return {
                "success": True,
                "message": "工具重新加载成功",
                "tools_count": len(agent.get_available_tools())
            }
        except Exception as e:
            logger.error(f"重新加载工具失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail={
                    "success": False,
                    "error": str(e),
                    "message": "重新加载工具失败"
                }
            )
    
    @app.get("/status")
    async def get_agent_status():
        """获取Agent状态"""
        try:
            agent = get_agent()
            
            # 获取MCP工具状态
            tools_result = agent.mcp_client.get_tools()
            
            return {
                "agent_initialized": agent is not None,
                "agent_type": "ReAct Agent",
                "mcp_server_url": agent.mcp_client.server_url if agent else None,
                "mcp_connected": tools_result.get("success", False),
                "available_tools": len(tools_result.get("data", [])),
                "llm_model": getattr(agent.llm, 'model_name', 'unknown') if agent else None,
                "tools_list": agent.get_available_tools() if agent else []
            }
        except Exception as e:
            logger.error(f"获取Agent状态失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail={
                    "success": False,
                    "error": str(e),
                    "message": "获取Agent状态失败"
                }
            )
    
    return app

def run_http_server(host: str = "0.0.0.0", port: int = 8001):
    """运行HTTP服务器"""
    if not FASTAPI_AVAILABLE:
        logger.error("FastAPI未安装，无法启动HTTP服务。请运行: pip install fastapi uvicorn")
        return
    
    print("🚀 智能资产管理Agent HTTP服务 (ReAct Agent)")
    print("=" * 50)
    print(f"服务地址: http://{host}:{port}")
    print(f"API文档: http://{host}:{port}/docs")
    print("=" * 50)
    
    app = create_app()
    
    # 启动服务器
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )

def main():
    """主函数 - 只支持HTTP服务器模式"""
    # 设置日志
    try:
        from ..utils import setup_logging
        setup_logging(level="INFO")
    except ImportError:
        try:
            from utils import setup_logging
            setup_logging(level="INFO")
        except ImportError:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
    
    # 只支持HTTP服务器模式
    host = os.getenv("AGENT_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("AGENT_SERVER_PORT", "8001"))
    
    print("🚀 智能资产管理Agent (ReAct模式)")
    print("=" * 40)
    print(f"启动服务: {host}:{port}")
    print("=" * 40)
    
    run_http_server(host, port)

if __name__ == "__main__":
    main() 