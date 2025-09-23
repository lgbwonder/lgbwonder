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
            
            实例流程：
            1、查询张三已分配的资产详情
                第一步：确定用户是通过用户名查询已分配有效资产
                第二步：确认参数searchType=memberAccount，searchCondition=张三，assetStatus=[VALID,ASSIGNED]
                第三步：查询资产状态 query_assets_by_status_mcp 进行查询
            2、给张三分配一个包含计价产品的资产    
                第一步：查询用户名为张三的授权成员
                第二步：查询有效且未分配并且包含计价产品的资产
                第三步：给张三分配资产

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

            # 参数验证和智能补全
            validation_error = self._validate_tool_parameters(tool_name, args)
            if validation_error:
                logger.warning(f"参数验证失败: {validation_error}")
                return f"参数验证失败: {validation_error}"

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

    def _validate_tool_parameters(self, tool_name: str, args: Dict) -> Optional[str]:
        """验证工具参数，并进行智能补全和过滤"""
        # 定义每个工具的必需参数和可选参数
        tool_params = {
            "query_assets_by_status_mcp": {
                "required": ["userToken", "clientToken", "searchType", "searchCondition", "assetStatus"],
                "optional": ["pageNum", "pageSize"]
            },
            "allocate_asset_privileges_mcp": {
                "required": ["userToken", "clientToken", "assignType", "assetPrivileges"],
                "optional": []
            },
            "query_enterprise_members_mcp": {
                "required": ["userToken", "clientToken"],
                "optional": ["keyword"]
            },
            "generate_client_token_mcp": {
                "required": ["grantType"],
                "optional": []
            },
            "generate_user_token_mcp": {
                "required": ["grantType"],
                "optional": ["uid"]
            },
            "query_asset_products_mcp": {
                "required": ["userToken", "clientToken", "assetId"],
                "optional": []
            },
            "add_enterprise_member_mcp": {
                "required": ["userToken", "userName", "password", "name"],
                "optional": ["departmentId", "remark", "passwordMobile", "regionCode"]
            },
            "renew_asset_product_mcp": {
                "required": ["customerId", "licenseId", "limitEndTime"],
                "optional": ["limitStartTime"]
            }
        }
        
        if tool_name in tool_params:
            tool_config = tool_params[tool_name]
            required_params = tool_config["required"]
            allowed_params = tool_config["required"] + tool_config["optional"]
            
            # 过滤掉不需要的参数
            filtered_args = {}
            for key, value in args.items():
                if key in allowed_params:
                    filtered_args[key] = value
                else:
                    logger.debug(f"过滤掉不需要的参数: {key}")
            
            # 更新args为过滤后的参数
            args.clear()
            args.update(filtered_args)
            
            # 检查必需参数
            missing_params = []
            for param in required_params:
                if param not in args:
                    missing_params.append(param)
            
            if missing_params:
                return f"缺少必需参数: {', '.join(missing_params)}。请提供完整的参数。"
        
        # 特殊验证和修复
        if tool_name == "query_assets_by_status_mcp":
            valid_search_types = [
                "productUri", "productName", "assetNum", "memberAccount"
            ]
            if ("searchType" in args and 
                args["searchType"] not in valid_search_types):
                return f"searchType必须是: {', '.join(valid_search_types)} 中的一个"
            
            # 自动修复 assetStatus 格式
            if "assetStatus" in args:
                if isinstance(args["assetStatus"], str):
                    # 如果是字符串，尝试转换为列表
                    try:
                        args["assetStatus"] = [args["assetStatus"]]
                        logger.info(f"自动修复 assetStatus 格式: {args['assetStatus']}")
                    except:
                        return "assetStatus格式错误，应为状态字符串或状态列表"
                elif not isinstance(args["assetStatus"], list):
                    return "assetStatus必须是列表格式"
        
        # 分配资产权限工具的特殊验证
        if tool_name == "allocate_asset_privileges_mcp":
            valid_assign_types = ["assign", "unassign"]
            if ("assignType" in args and 
                args["assignType"] not in valid_assign_types):
                return f"assignType必须是: {', '.join(valid_assign_types)} 中的一个"
            
            # 验证 assetPrivileges 格式
            if "assetPrivileges" in args:
                if not isinstance(args["assetPrivileges"], list):
                    return "assetPrivileges必须是列表格式"
                
                for i, privilege in enumerate(args["assetPrivileges"]):
                    if not isinstance(privilege, dict):
                        return f"assetPrivileges[{i}]必须是字典格式"
                    
                    required_fields = ["assetNum", "assetId", "memberId"]
                    for field in required_fields:
                        if field not in privilege:
                            return f"assetPrivileges[{i}]缺少必需字段: {field}"
        
        # 添加企业成员工具的特殊验证
        if tool_name == "add_enterprise_member_mcp":
            # 验证用户名格式
            if "userName" in args:
                username = args["userName"]
                if not isinstance(username, str) or len(username) < 2 or len(username) > 30:
                    return "userName长度必须在2-30个字符之间"
                if not username.replace('_', '').isalnum():
                    return "userName只能包含字母、数字和下划线"
            
            # 验证密码格式
            if "password" in args:
                password = args["password"]
                if not isinstance(password, str) or len(password) < 8 or len(password) > 16:
                    return "password长度必须在8-16个字符之间"
                
                # 检查密码复杂度
                has_digit = any(c.isdigit() for c in password)
                has_alpha = any(c.isalpha() for c in password)
                has_symbol = any(not c.isalnum() for c in password)
                
                complexity_count = sum([has_digit, has_alpha, has_symbol])
                if complexity_count < 2:
                    return "password必须包含至少两种字符类型（数字、字母、符号）"
        
        # 令牌生成工具的验证
        if tool_name in ["generate_client_token_mcp", "generate_user_token_mcp"]:
            valid_grant_types = ["client_credentials", "uid"]
            if ("grantType" in args and 
                args["grantType"] not in valid_grant_types):
                return f"grantType必须是: {', '.join(valid_grant_types)} 中的一个"
        
        # 智能参数补全
        self._auto_complete_parameters(tool_name, args)
        
        return None

    def _auto_complete_parameters(self, tool_name: str, args: Dict) -> None:
        """智能参数补全"""
        
        # 为令牌生成工具设置默认值
        if tool_name == "generate_client_token_mcp":
            if "grantType" not in args:
                args["grantType"] = "client_credentials"
                logger.info("自动补全 grantType 为 'client_credentials'")
        
        if tool_name == "generate_user_token_mcp":
            if "grantType" not in args:
                args["grantType"] = "uid"
                logger.info("自动补全 grantType 为 'uid'")
        
        # 为查询资产工具设置默认分页参数
        if tool_name == "query_assets_by_status_mcp":
            if "pageNum" not in args:
                args["pageNum"] = 1
                logger.debug("自动补全 pageNum 为 1")
            if "pageSize" not in args:
                args["pageSize"] = 20
                logger.debug("自动补全 pageSize 为 20")
            
            # 智能推断搜索类型
            if "searchType" not in args and "searchCondition" in args:
                search_condition = str(args["searchCondition"]).lower()
                if search_condition.startswith("asset") or "资产" in search_condition:
                    args["searchType"] = "assetNum"
                    logger.info("根据搜索条件自动推断 searchType 为 'assetNum'")
                elif "@" in search_condition or "account" in search_condition:
                    args["searchType"] = "memberAccount"
                    logger.info("根据搜索条件自动推断 searchType 为 'memberAccount'")
                elif "product" in search_condition or "产品" in search_condition:
                    args["searchType"] = "productName"
                    logger.info("根据搜索条件自动推断 searchType 为 'productName'")
                else:
                    args["searchType"] = "assetNum"  # 默认值
                    logger.info("使用默认 searchType 'assetNum'")
            
            # 智能设置资产状态
            if "assetStatus" not in args:
                # 根据搜索条件推断状态
                search_condition = str(args.get("searchCondition", "")).lower()
                if "未分配" in search_condition or "unassigned" in search_condition:
                    args["assetStatus"] = ["UNASSIGNED", "VALID"]
                elif "已分配" in search_condition or "assigned" in search_condition:
                    args["assetStatus"] = ["ASSIGNED"]
                elif "过期" in search_condition or "expired" in search_condition:
                    args["assetStatus"] = ["EXPIRED"]
                else:
                    args["assetStatus"] = ["VALID"]  # 默认查询有效资产
                logger.info(f"自动推断 assetStatus 为 {args['assetStatus']}")
        
        # 为企业成员查询设置默认关键词
        if tool_name == "query_enterprise_members_mcp":
            if "keyword" not in args:
                args["keyword"] = ""
                logger.debug("自动补全 keyword 为空字符串")
        
        # 为资产续费工具设置默认开始时间
        if tool_name == "renew_asset_product_mcp":
            if "limitStartTime" not in args:
                # 使用当前时间戳（毫秒）
                import time
                args["limitStartTime"] = int(time.time() * 1000)
                logger.info(f"自动补全 limitStartTime 为当前时间: {args['limitStartTime']}")
        
        logger.debug(f"参数补全完成，最终参数: {args}")

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
            # 如果LLM优化失败，生成简化的思考步骤
            return self._generate_simple_thinking_steps(raw_steps)

    def _optimize_streaming_thinking_steps_with_llm(self, raw_steps) -> List[Dict[str, Any]]:
        """使用LLM优化流式思考步骤，生成更适合逐步展示的内容"""
        
        # 如果没有原始步骤，返回默认步骤
        if not raw_steps:
            return self._generate_default_thinking_steps()
        
        # 构建LLM提示
        steps_text = ""
        for i, step in enumerate(raw_steps, 1):
            steps_text += f"步骤{i}:\n"
            steps_text += f"思考: {step['thought'][:300]}...\n"
            steps_text += f"执行工具: {step['tool']}\n"
            steps_text += f"执行结果: {step['observation'][:400]}...\n\n"
        
        prompt = f"""
            请将以下AI助手的资产管理执行步骤转换为用户友好的实时展示内容。

            原始执行步骤:
            {steps_text}

            转换要求:
            1. 每个步骤描述具体的业务操作（如：获取认证、查询资产、分析数据、分配权限等）
            2. 用自然语言描述进度，让用户了解当前在做什么
            3. 结果要具体，包含实际的数据信息（如找到多少资产、成员等）
            4. 适合逐步实时展示，有明确的进度感
            5. 避免技术术语，专注于业务含义

            请严格按以下JSON格式返回:
            [
            {{
                "content": "正在获取访问权限和认证信息...",
                "result": "认证成功，已获得系统访问权限",
                "result_type": "success",
                "progress": "1/4"
            }},
            {{
                "content": "正在查询您的资产信息...",
                "result": "已找到8个资产记录，包含3个未分配资产",
                "result_type": "success", 
                "progress": "2/4"
            }},
            {{
                "content": "正在分析成员和权限分配策略...",
                "result": "已识别目标成员，准备执行权限分配",
                "result_type": "success",
                "progress": "3/4"
            }},
            {{
                "content": "正在执行资产权限分配操作...",
                "result": "权限分配完成，操作执行成功",
                "result_type": "success",
                "progress": "4/4"
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
            # 如果LLM优化失败，使用备用方案
            return self._generate_fallback_thinking_steps(raw_steps)

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


if __name__ == "__main__":
    # 这里可以添加直接测试Agent的代码
    agent = AssetManageAgent()
    print("AssetManageAgent初始化完成，可用工具:", agent.get_available_tools())
