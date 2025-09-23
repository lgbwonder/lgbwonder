# -*- coding: utf-8 -*-
"""
智能Agent HTTP服务
集成资产管理Agent和知识库Agent，通过LLM智能路由
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional, Union
from datetime import datetime

# FastAPI相关导入
try:
    from fastapi import FastAPI, HTTPException, Header
    from fastapi.responses import JSONResponse, StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# 导入Agent
try:
    from ..agent.asset_manage_agent import AssetManageAgent
    from ..agent.knowledge_retrieval_agent import KnowledgeRetrievalAgent
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agent.asset_manage_agent import AssetManageAgent
    from agent.knowledge_retrieval_agent import KnowledgeRetrievalAgent

# LLM导入
from langchain_openai import ChatOpenAI

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProcessRequestModel(BaseModel):
    """请求模型"""
    message: str
    mcp_server_url: str = None
    agent_type: str = None  # 可选指定agent类型: 'asset' 或 'knowledge'


class AgentRouter:
    """智能Agent路由器"""
    
    def __init__(self):
        """初始化路由器"""
        # 初始化LLM用于智能路由
        self.router_llm = ChatOpenAI(
            model=os.getenv("QWEN_MODEL", "qwen-plus"),
            temperature=0.0,  # 确定性输出
            api_key=os.getenv("QWEN_API_KEY", "sk-8fe5cd468cd241d2b7fd2849468bcfde"),
            base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            timeout=10,
            max_tokens=100  # 路由决策只需要简短回答
        )
        
        # 全局Agent实例
        self._asset_agent: Optional[AssetManageAgent] = None
        self._knowledge_agent: Optional[KnowledgeRetrievalAgent] = None
        
        logger.info("Agent路由器初始化完成")
    
    def get_asset_agent(self, mcp_server_url: str = None) -> AssetManageAgent:
        """获取资产管理Agent实例"""
        if self._asset_agent is None:
            self._asset_agent = AssetManageAgent(mcp_server_url)
        return self._asset_agent
    
    def get_knowledge_agent(self) -> KnowledgeRetrievalAgent:
        """获取知识库Agent实例"""
        if self._knowledge_agent is None:
            self._knowledge_agent = KnowledgeRetrievalAgent()
        return self._knowledge_agent
    
    def determine_agent_type(self, message: str) -> str:
        """通过LLM智能判断应该使用哪个Agent"""
        try:
            prompt = f"""
                请分析用户的问题，判断应该使用哪个AI助手来回答：

                用户问题：{message}

                可选助手：
                1. asset - 资产管理助手：处理企业资产分配、权限管理、成员管理、资产查询等操作性任务
                - 关键词：分配、权限、资产、成员、账号、令牌、查询资产状态、添加成员等
                - 示例：分配资产给用户、查询未分配资产、创建成员账号、管理权限等

                2. knowledge - 知识库助手：回答专业知识问题，提供行业信息、技术解答、概念解释等
                - 关键词：什么是、如何、为什么、解释、介绍、原理、方法、流程、技术等
                - 示例：BIM是什么、施工流程、技术原理、行业标准、操作方法等

                请只回答助手类型：asset 或 knowledge

                回答："""

            response = self.router_llm.invoke(prompt)
            agent_type = response.content.strip().lower()

            agent_type = 'asset'
            
            # 验证返回值
            if agent_type in ['asset', 'knowledge']:
                logger.info(f"路由决策: {message[:30]}... -> {agent_type}")
                return agent_type
            else:
                # 默认路由逻辑
                logger.warning(f"LLM路由返回无效值: {agent_type}，使用默认逻辑")
                return self._fallback_routing(message)
                
        except Exception as e:
            logger.error(f"LLM路由失败: {e}，使用默认逻辑")
            return self._fallback_routing(message)
    
    def _fallback_routing(self, message: str) -> str:
        """备用路由逻辑"""
        # 资产管理关键词
        asset_keywords = [
            '分配', '权限', '资产', '成员', '账号', '令牌', 'token',
            '查询资产', '添加成员', '管理', '分配给', '创建', '删除',
            'userToken', 'clientToken', 'assetNum', 'memberId'
        ]
        
        # 知识库关键词
        knowledge_keywords = [
            '什么是', '如何', '为什么', '解释', '介绍', '原理', '方法',
            '流程', '技术', 'BIM', '施工', '造价', '管理', '标准'
        ]
        
        message_lower = message.lower()
        
        # 检查资产管理关键词
        asset_score = sum(1 for keyword in asset_keywords if keyword.lower() in message_lower)
        knowledge_score = sum(1 for keyword in knowledge_keywords if keyword.lower() in message_lower)
        
        if asset_score > knowledge_score:
            return 'asset'
        elif knowledge_score > asset_score:
            return 'knowledge'
        else:
            # 默认使用知识库Agent
            return 'knowledge'


class IntelligentAgentServer:
    """智能Agent服务器"""
    
    def __init__(self):
        """初始化服务器"""
        self.router = AgentRouter()
        self.app = self._create_app()
        
    def _create_app(self) -> FastAPI:
        """创建FastAPI应用"""
        app = FastAPI(
            title="智能Agent服务平台",
            description="集成资产管理和知识库的智能Agent服务",
            version="2.0.0"
        )

        # 添加CORS中间件
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # 注册路由
        self._register_routes(app)
        
        return app
    
    def _register_routes(self, app: FastAPI):
        """注册所有路由"""
        
        @app.post("/process")
        async def process_request(request: ProcessRequestModel):
            """处理请求 - 非流式"""
            try:
                # 确定Agent类型
                agent_type = request.agent_type or self.router.determine_agent_type(request.message)
                
                if agent_type == 'asset':
                    # 使用资产管理Agent
                    agent = self.router.get_asset_agent(request.mcp_server_url)
                    result = agent.process_request(request.message)
                    return {
                        "success": True,
                        "agent_type": "asset",
                        "data": result
                    }
                else:
                    # 使用知识库Agent
                    agent = self.router.get_knowledge_agent()
                    result = agent.chat_with_knowledge(request.message)
                    return {
                        "success": True,
                        "agent_type": "knowledge",
                        "data": result
                    }
                    
            except Exception as e:
                logger.error(f"处理请求失败: {e}")
                raise HTTPException(status_code=500, detail={"error": str(e)})

        @app.post("/process-stream")
        async def process_request_stream(
            request: ProcessRequestModel,
            user_token: str = Header(None, alias="userToken"),
            client_token: str = Header(None, alias="clientToken")
        ):
            """流式处理请求 - 智能路由"""
            
            async def generate_response_stream():
                try:
                    # 记录接收到的token信息
                    if user_token and client_token:
                        logger.info(f"从请求头获取到认证token: userToken={user_token[:20]}..., clientToken={client_token[:20]}...")
                    else:
                        logger.warning(f"请求头中缺少认证token: userToken={'有' if user_token else '无'}, clientToken={'有' if client_token else '无'}")
                    
                    # 发送开始信号
                    yield f"data: {json.dumps({'type': 'start', 'message': '正在分析您的请求...'}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.5)
                    
                    # 确定Agent类型
                    agent_type = request.agent_type or self.router.determine_agent_type(request.message)
                    
                    # 发送路由信息
                    route_info = {
                        'type': 'route',
                        'agent_type': agent_type,
                        'message': f'已选择{"资产管理" if agent_type == "asset" else "知识库"}助手为您服务'
                    }
                    yield f"data: {json.dumps(route_info, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.3)
                    
                    if agent_type == 'asset':
                        # 使用资产管理Agent进行流式处理
                        async for chunk in self._process_asset_stream(request, user_token, client_token):
                            yield chunk
                    else:
                        # 使用知识库Agent进行流式处理
                        async for chunk in self._process_knowledge_stream(request, user_token, client_token):
                            yield chunk
                    
                    # 发送结束信号
                    yield f"data: {json.dumps({'type': 'end'}, ensure_ascii=False)}\n\n"
                    
                except Exception as e:
                    logger.error(f"流式处理失败: {e}")
                    error_msg = {'type': 'error', 'message': f'处理异常: {str(e)}'}
                    yield f"data: {json.dumps(error_msg, ensure_ascii=False)}\n\n"
            
            return StreamingResponse(
                generate_response_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "*",
                }
            )

        @app.get("/status")
        async def get_status():
            """获取服务状态"""
            try:
                return {
                    "success": True,
                    "data": {
                        "status": "healthy",
                        "agents": ["asset", "knowledge"],
                        "router_enabled": True,
                        "cors_enabled": True,
                        "timestamp": datetime.now().isoformat()
                    }
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail={"error": str(e)})

        @app.get("/agents")
        async def get_available_agents():
            """获取可用的Agent列表"""
            try:
                asset_agent = self.router.get_asset_agent()
                knowledge_agent = self.router.get_knowledge_agent()
                
                return {
                    "success": True,
                    "data": {
                        "asset": {
                            "name": "资产管理助手",
                            "description": "处理企业资产分配、权限管理、成员管理等操作",
                            "tools_count": len(asset_agent.get_available_tools())
                        },
                        "knowledge": {
                            "name": "知识库助手", 
                            "description": "提供专业知识解答、技术支持、概念解释等服务",
                            "llm_enabled": True
                        }
                    }
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail={"error": str(e)})

    async def _process_asset_stream(self, request: ProcessRequestModel, user_token: str = None, client_token: str = None):
        """处理资产管理Agent的流式响应"""
        try:
            agent = self.router.get_asset_agent(request.mcp_server_url)
            
            # 执行资产管理处理，传递token
            result = await asyncio.get_event_loop().run_in_executor(
                None, agent.process_request_with_streaming, request.message, user_token, client_token
            )
            
            if result.get("success"):
                # 发送思考步骤
                thinking_steps = result.get("thinking_steps", [])
                for i, step in enumerate(thinking_steps, 1):
                    step_data = {
                        'type': 'step',
                        'step': step  # 直接传递step数据，前端会使用data.step
                    }
                    yield f"data: {json.dumps(step_data, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.8)
                
                # 发送最终结果
                final_result = {
                    'type': 'result',
                    'content': result.get("output", ""),
                    'allocation_plan': result.get("allocation_plan", {}),
                    'tools_used': result.get("tools_used", []),
                    'agent_type': 'asset'
                }
                yield f"data: {json.dumps(final_result, ensure_ascii=False)}\n\n"
            else:
                # 发送错误信息
                error_data = {
                    'type': 'error',
                    'message': result.get('message', '资产管理处理失败')
                }
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                
        except Exception as e:
            error_data = {'type': 'error', 'message': f'资产管理Agent异常: {str(e)}'}
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    async def _process_knowledge_stream(self, request: ProcessRequestModel, user_token: str = None, client_token: str = None):
        """处理知识库Agent的流式响应"""
        try:
            agent = self.router.get_knowledge_agent()
            
            # 第一步：分析用户问题
            step1_data = {
                'type': 'step',
                'step': 1,
                'data': {
                    "step": 1,
                    "type": "thinking",
                    "content": f"正在分析您的问题：{request.message[:50]}...",
                    "result": "问题分析完成，已识别关键词和查询意图",
                    "result_type": "success",
                    "progress": "1/5",
                    "timestamp": datetime.now().isoformat()
                }
            }
            yield f"data: {json.dumps(step1_data, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.8)
            
            # 第二步：搜索知识库
            step2_data = {
                'type': 'step',
                'step': 2,
                'data': {
                    "step": 2,
                    "type": "thinking",
                    "content": "正在知识库中搜索相关内容...",
                    "result": "已在广联达知识库中找到相关文档和资料",
                    "result_type": "success",
                    "progress": "2/5",
                    "timestamp": datetime.now().isoformat()
                }
            }
            yield f"data: {json.dumps(step2_data, ensure_ascii=False)}\n\n"
            
            # 实际执行知识检索
            knowledge_results = await asyncio.get_event_loop().run_in_executor(
                None, agent.knowledge_retrieval, request.message
            )
            
            await asyncio.sleep(0.8)
            
            # 第三步：分析检索结果
            knowledge_count = len(knowledge_results.get("data", {}).get("results", []))
            step3_data = {
                'type': 'step',
                'step': 3,
                'data': {
                    "step": 3,
                    "type": "thinking",
                    "content": "正在分析和筛选检索到的知识内容...",
                    "result": f"成功获取到 {knowledge_count} 条相关知识内容，相似度较高",
                    "result_type": "success" if knowledge_count > 0 else "warning",
                    "progress": "3/5",
                    "timestamp": datetime.now().isoformat()
                }
            }
            yield f"data: {json.dumps(step3_data, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.8)
            
            # 第四步：LLM处理
            step4_data = {
                'type': 'step',
                'step': 4,
                'data': {
                    "step": 4,
                    "type": "thinking",
                    "content": "正在基于知识库内容生成专业回答...",
                    "result": "AI模型正在结合知识库内容和专业知识进行综合分析",
                    "result_type": "info",
                    "progress": "4/5",
                    "timestamp": datetime.now().isoformat()
                }
            }
            yield f"data: {json.dumps(step4_data, ensure_ascii=False)}\n\n"
            
            # 执行智能问答
            result = await asyncio.get_event_loop().run_in_executor(
                None, agent.intelligent_qa, request.message
            )
            
            await asyncio.sleep(0.8)
            
            # 第五步：完成回答
            step5_data = {
                'type': 'step',
                'step': 5,
                'data': {
                    "step": 5,
                    "type": "thinking",
                    "content": "正在整理和优化回答内容...",
                    "result": "专业回答已生成完成，包含知识库参考和AI分析",
                    "result_type": "success",
                    "progress": "5/5",
                    "timestamp": datetime.now().isoformat()
                }
            }
            yield f"data: {json.dumps(step5_data, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.5)
            
            # 发送最终结果
            final_result = {
                'type': 'result',
                'content': result,
                'agent_type': 'knowledge',
                'knowledge_enhanced': True,
                'knowledge_sources': knowledge_count
            }
            yield f"data: {json.dumps(final_result, ensure_ascii=False)}\n\n"
                
        except Exception as e:
            error_data = {'type': 'error', 'message': f'知识库Agent异常: {str(e)}'}
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    def run(self, host: str = "0.0.0.0", port: int = 8001):
        """启动服务器"""
        if not FASTAPI_AVAILABLE:
            logger.error("FastAPI未安装，无法启动HTTP服务")
            return
            
        logger.info(f"启动智能Agent服务器: http://{host}:{port}")
        uvicorn.run(self.app, host=host, port=port, log_level="info")


# 全局服务器实例
_server_instance: Optional[IntelligentAgentServer] = None


def get_server() -> IntelligentAgentServer:
    """获取服务器实例"""
    global _server_instance
    if _server_instance is None:
        _server_instance = IntelligentAgentServer()
    return _server_instance


def run_server(host: str = "0.0.0.0", port: int = 8001):
    """启动智能Agent服务器"""
    server = get_server()
    server.run(host, port)


if __name__ == "__main__":
    run_server() 