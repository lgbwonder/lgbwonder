# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
基于ReActAgent的智能资产管理Agent (优化版：支持并发安全)
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, TypedDict

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
            
            # 解析简化的思考步骤
            thinking_steps = self._parse_simple_thinking_steps(intermediate_steps)

            return {
                "success": True,
                "message": "请求处理完成",
                "output": output,
                "tools_used": tools_used,
                "thinking_steps": thinking_steps,
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
                "thinking_steps": [],
                "mcp_tools_used": []
            }

    def _parse_simple_thinking_steps(self, intermediate_steps) -> List[Dict[str, Any]]:
        """解析简化的思考步骤 - 通过LLM优化展示"""
        if not intermediate_steps:
            return []
        
        # 收集原始的思考和执行信息
        raw_steps = []
        for step in intermediate_steps:
            if len(step) >= 2:
                action = step[0]
                observation = step[1]
                
                thought = getattr(action, 'log', '') or str(action)
                tool_name = getattr(action, 'tool', 'unknown')
                
                raw_steps.append({
                    'thought': thought,
                    'tool': tool_name,
                    'observation': str(observation)
                })
        
        if not raw_steps:
            return []
        
        # 使用LLM总结和优化思考步骤
        try:
            optimized_steps = self._optimize_thinking_steps_with_llm(raw_steps)
            return optimized_steps
        except Exception as e:
            logger.error(f"LLM优化思考步骤失败: {str(e)}")
            # 如果LLM优化失败，返回空列表
            return []

    def process_request_with_streaming(self, user_message: str) -> Dict[str, Any]:
        """处理用户请求，支持流式思考步骤（同步版本，用于线程池执行）"""
        try:
            logger.info(f"流式处理请求: {user_message[:50]}...")

            # 检查消息是否包含必要的token信息
            if "userToken:" not in user_message or "clientToken:" not in user_message:
                logger.warning("请求缺少必要的token信息")
                return {
                    "success": False,
                    "message": "请求缺少必要的认证信息",
                    "output": "请确保包含用户令牌和客户端令牌信息",
                    "allocation_plan": {},
                    "current_step": "error",
                    "thinking_steps": [],
                    "tools_used": []
                }

            agent_executor = self._create_agent_executor()
            result = agent_executor.invoke({"input": user_message})

            output = result.get("output", "")
            intermediate_steps = result.get("intermediate_steps", [])
            tools_used = [step[0].tool for step in intermediate_steps if len(step) >= 2]
            
            # 解析简化的思考步骤（用于流式传输）
            thinking_steps = self._parse_streaming_thinking_steps(intermediate_steps)

            logger.info(f"流式请求处理完成，使用了 {len(tools_used)} 个工具，{len(thinking_steps)} 个思考步骤")

            return {
                "success": True,
                "message": "请求处理完成",
                "output": output,
                "tools_used": tools_used,
                "thinking_steps": thinking_steps,
                "allocation_plan": self._extract_allocation_info(output),
                "current_step": "completed"
            }

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"流式处理请求失败: {str(e)}")
            logger.error(f"错误详情: {error_details}")
            
            return {
                "success": False,
                "message": f"处理请求失败: {str(e)}",
                "output": "系统处理请求时发生错误，请稍后重试",
                "allocation_plan": {},
                "current_step": "error",
                "thinking_steps": [],
                "tools_used": []
            }

    def _parse_streaming_thinking_steps(self, intermediate_steps) -> List[Dict[str, Any]]:
        """解析用于流式传输的思考步骤"""
        if not intermediate_steps:
            return []
        
        # 收集原始的思考和执行信息
        raw_steps = []
        for step in intermediate_steps:
            if len(step) >= 2:
                action = step[0]
                observation = step[1]
                
                thought = getattr(action, 'log', '') or str(action)
                tool_name = getattr(action, 'tool', 'unknown')
                
                raw_steps.append({
                    'thought': thought,
                    'tool': tool_name,
                    'observation': str(observation)
                })
        
        if not raw_steps:
            return []
        
        # 使用LLM优化思考步骤（适合流式传输）
        try:
            optimized_steps = self._optimize_streaming_thinking_steps_with_llm(raw_steps)
            return optimized_steps
        except Exception as e:
            logger.error(f"LLM优化流式思考步骤失败: {str(e)}")
            # 如果LLM优化失败，返回空列表
            return []

    def _optimize_streaming_thinking_steps_with_llm(self, raw_steps) -> List[Dict[str, Any]]:
        """使用LLM优化流式思考步骤，生成更适合逐步展示的内容"""
        
        # 构建LLM提示
        steps_text = ""
        for i, step in enumerate(raw_steps, 1):
            steps_text += f"步骤{i}:\n"
            steps_text += f"思考: {step['thought']}\n"
            steps_text += f"执行: {step['tool']}\n"
            steps_text += f"结果: {step['observation'][:200]}...\n\n"
        
        prompt = f"""
            请将以下AI助手的技术执行步骤转换为适合逐步展示的用户友好描述。

            原始步骤:
            {steps_text}

            要求:
            1. 每个步骤要有清晰的"正在做什么"和"处理结果"
            2. 用自然、友好的语言，避免技术术语
            3. 适合实时展示，让用户感受到处理进度
            4. 每个步骤包含: 当前操作 + 处理状态 + 结果反馈
            5. 保持简洁但信息完整

            请按以下JSON格式返回:
            [
            {{
                "content": "正在查询您的资产信息...",
                "status": "processing",
                "result": "已找到8个资产记录",
                "result_type": "success",
                "progress": "1/3"
            }},
            {{
                "content": "分析资产分配状态...", 
                "status": "processing",
                "result": "识别出3个未分配资产",
                "result_type": "success",
                "progress": "2/3"
            }}
            ]
            """

        try:
            # 创建一个简化的LLM实例用于优化
            optimizer_llm = ChatOpenAI(
                model=self.llm.model_name,
                api_key=self.llm.openai_api_key,
                base_url=self.llm.openai_api_base,
                temperature=0.2,  # 更低温度保证一致性
                max_tokens=1000,
                timeout=20  # 稍长超时用于流式处理
            )
            
            response = optimizer_llm.invoke(prompt)
            
            # 解析LLM返回的JSON
            import re
            json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
            if json_match:
                steps_data = json.loads(json_match.group())
                
                # 转换为标准格式
                optimized_steps = []
                for i, step_data in enumerate(steps_data, 1):
                    step_info = {
                        "step": i,
                        "type": "thinking",
                        "content": step_data.get("content", "处理中..."),
                        "status": step_data.get("status", "processing"),
                        "result": step_data.get("result", "完成"),
                        "result_type": step_data.get("result_type", "success"),
                        "progress": step_data.get("progress", f"{i}/{len(steps_data)}"),
                        "timestamp": datetime.now().isoformat()
                    }
                    optimized_steps.append(step_info)
                
                logger.debug(f"LLM优化生成了 {len(optimized_steps)} 个流式步骤")
                return optimized_steps
            else:
                logger.warning("LLM返回格式不正确，无法解析JSON")
                raise ValueError("LLM返回格式错误")
                
        except Exception as e:
            logger.error(f"LLM优化流式思考步骤失败: {str(e)}")
            raise e

    def _optimize_thinking_steps_with_llm(self, raw_steps) -> List[Dict[str, Any]]:
        """使用LLM优化思考步骤，生成用户友好的描述"""
        
        # 构建LLM提示
        steps_text = ""
        for i, step in enumerate(raw_steps, 1):
            steps_text += f"步骤{i}:\n"
            steps_text += f"思考: {step['thought']}\n"
            steps_text += f"执行: {step['tool']}\n"
            steps_text += f"结果: {step['observation'][:200]}...\n\n"
        
        prompt = f"""
            请将以下AI助手的技术执行步骤转换为用户友好的自然语言描述。
            
            原始步骤:
            {steps_text}
            
            要求:
            1. 用自然、友好的语言描述每个步骤在做什么
            2. 不要提及具体的工具名称、API调用等技术细节
            3. 专注于用户能理解的业务逻辑
            4. 每个步骤包含: 在做什么 + 结果如何
            5. 保持简洁明了，避免冗余
            
            请按以下JSON格式返回:
            [
              {{
                "content": "正在查询您的资产信息",
                "result": "找到了5个相关资产",
                "result_type": "success"
              }},
              {{
                "content": "分析资产状态和分配情况", 
                "result": "识别出3个未分配的资产",
                "result_type": "success"
              }}
            ]
            """

        try:
            # 创建一个简化的LLM实例用于优化
            optimizer_llm = ChatOpenAI(
                model=self.llm.model_name,
                api_key=self.llm.openai_api_key,
                base_url=self.llm.openai_api_base,
                temperature=0.3,  # 较低温度保证稳定输出
                max_tokens=800,
                timeout=15  # 较短超时避免影响主流程
            )
            
            response = optimizer_llm.invoke(prompt)
            
            # 解析LLM返回的JSON
            import re
            json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
            if json_match:
                steps_data = json.loads(json_match.group())
                
                # 转换为标准格式
                optimized_steps = []
                for i, step_data in enumerate(steps_data, 1):
                    step_info = {
                        "step": i,
                        "type": "thinking",
                        "content": step_data.get("content", "处理中..."),
                        "result": step_data.get("result", "完成"),
                        "result_type": step_data.get("result_type", "success"),
                        "timestamp": datetime.now().isoformat()
                    }
                    optimized_steps.append(step_info)
                
                logger.debug(f"LLM优化生成了 {len(optimized_steps)} 个友好步骤")
                return optimized_steps
            else:
                logger.warning("LLM返回格式不正确，无法解析JSON")
                raise ValueError("LLM返回格式错误")
                
        except Exception as e:
            logger.error(f"LLM优化思考步骤失败: {str(e)}")
            raise e



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
    from fastapi.middleware.cors import CORSMiddleware
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

    # 添加CORS中间件支持跨域访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 允许所有源，生产环境建议指定具体域名
        allow_credentials=True,
        allow_methods=["*"],  # 允许所有HTTP方法
        allow_headers=["*"],  # 允许所有请求头
    )

    @app.post("/process")
    async def process_request(request: ProcessRequestModel):
        try:
            agent = get_agent(request.mcp_server_url)
            return {"success": True, "data": agent.process_request(request.message)}
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": str(e)})
    
    @app.post("/process-stream")
    async def process_request_stream(request: ProcessRequestModel):
        """流式处理请求，实时返回思考步骤"""
        from fastapi.responses import StreamingResponse
        import asyncio
        import json
        
        async def generate_thinking_stream():
            try:
                agent = get_agent(request.mcp_server_url)
                
                # 发送开始信号
                yield f"data: {json.dumps({'type': 'start', 'message': '开始分析您的请求...'})}\n\n"
                await asyncio.sleep(0.5)
                
                # 执行Agent处理
                result = await asyncio.get_event_loop().run_in_executor(
                    None, agent.process_request_with_streaming, request.message
                )
                
                if result.get("success"):
                    # 逐步发送思考步骤
                    thinking_steps = result.get("thinking_steps", [])
                    for i, step in enumerate(thinking_steps, 1):
                        # 发送思考步骤
                        yield f"data: {json.dumps({'type': 'thinking_step', 'step': i, 'data': step})}\n\n"
                        await asyncio.sleep(0.8)  # 模拟处理时间
                    
                    # 发送最终结果
                    final_result = {
                        'type': 'final_result',
                        'output': result.get("output", ""),
                        'allocation_plan': result.get("allocation_plan", {}),
                        'tools_used': result.get("tools_used", [])
                    }
                    yield f"data: {json.dumps(final_result)}\n\n"
                else:
                    # 发送错误信息
                    yield f"data: {json.dumps({'type': 'error', 'message': result.get('message', '处理失败')})}\n\n"
                
                # 发送结束信号
                yield f"data: {json.dumps({'type': 'end'})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'处理异常: {str(e)}'})}\n\n"
        
        return StreamingResponse(
            generate_thinking_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
            }
        )

    @app.get("/tools")
    async def get_available_tools():
        try:
            agent = get_agent()
            return {"success": True, "data": agent.get_available_tools()}
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": str(e)})

    @app.get("/status")
    async def get_status():
        """获取Agent状态"""
        try:
            agent = get_agent()
            return {
                "success": True, 
                "data": {
                    "status": "running",
                    "mcp_server_url": agent.mcp_client.server_url,
                    "tools_count": len(agent.get_available_tools()),
                    "cors_enabled": True
                }
            }
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
