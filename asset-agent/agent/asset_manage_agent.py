# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
基于ReActAgent的智能资产管理Agent (优化版：支持并发安全)
"""

import os
import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, TypedDict, Tuple
from dataclasses import dataclass

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


# ==================== 常量定义 ====================
@dataclass
class LLMConfig:
    """LLM配置常量"""
    DEFAULT_MODEL: str = "qwen-plus"
    DEFAULT_TEMPERATURE: float = 0.0
    DEFAULT_TIMEOUT: int = 60
    DEFAULT_MAX_RETRIES: int = 5
    DEFAULT_MAX_TOKENS: int = 3000
    
    OPTIMIZER_TEMPERATURE: float = 0.2
    OPTIMIZER_TIMEOUT: int = 15
    OPTIMIZER_MAX_TOKENS: int = 800
    
    STREAMING_TEMPERATURE: float = 0.2
    STREAMING_TIMEOUT: int = 20
    STREAMING_MAX_TOKENS: int = 1000
    
    SIMPLIFY_TEMPERATURE: float = 0.2
    SIMPLIFY_TIMEOUT: int = 10
    SIMPLIFY_MAX_TOKENS: int = 300
    
    COMPLETION_TEMPERATURE: float = 0.1
    COMPLETION_TIMEOUT: int = 15
    COMPLETION_MAX_TOKENS: int = 500


@dataclass
class AgentConfig:
    """Agent配置常量"""
    MAX_ITERATIONS: int = 15
    MAX_EXECUTION_TIME: int = 300
    EARLY_STOPPING_METHOD: str = "generate"


@dataclass
class ValidationConfig:
    """参数验证配置常量"""
    USERNAME_MIN_LENGTH: int = 2
    USERNAME_MAX_LENGTH: int = 30
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_MAX_LENGTH: int = 16
    MAX_TIMESTAMP: int = 4102444800000  # 2100年的毫秒时间戳
    MAX_PAGE_SIZE: int = 1000
    DEFAULT_PAGE_NUM: int = 1
    DEFAULT_PAGE_SIZE: int = 20


# JSON类型映射
TYPE_MAPPING = {
    'str': 'string',
    'int': 'integer',
    'float': 'number',
    'bool': 'boolean',
    'list': 'array',
    'dict': 'object'
}

# 工具参数Schema字段名候选
SCHEMA_FIELD_NAMES = ["inputSchema", "parameters", "schema", "input_schema", "args_schema"]


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
        """初始化Agent
        
        Args:
            mcp_server_url: MCP服务器URL，如果为None则从环境变量读取
        """
        # 初始化MCP客户端
        self.mcp_client = MCPClient(mcp_server_url or os.getenv("MCP_SERVER_URL"))
        
        # 初始化配置
        self.llm_config = LLMConfig()
        self.agent_config = AgentConfig()
        self.validation_config = ValidationConfig()
        
        # 配置并初始化LLM
        self.llm = self._initialize_llm()
        
        # 缓存工具和提示模板
        self.tools: List[Tool] = []
        self._load_mcp_tools()
        self._prompt = self._build_prompt()
        
        logger.info(f"Agent初始化完成，加载了 {len(self.tools)} 个工具")

    def _initialize_llm(self) -> ChatOpenAI:
        """初始化主LLM实例
        
        Returns:
            配置好的ChatOpenAI实例
        """
        api_key = os.getenv("QWEN_API_KEY", "sk-8fe5cd468cd241d2b7fd2849468bcfde")
        if not api_key:
            logger.warning("QWEN_API_KEY 环境变量未设置，LLM功能可能无法正常工作")
        
        return ChatOpenAI(
            model=os.getenv("QWEN_MODEL", self.llm_config.DEFAULT_MODEL),
            temperature=float(os.getenv("QWEN_TEMPERATURE", str(self.llm_config.DEFAULT_TEMPERATURE))),
            api_key=api_key,
            base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            timeout=self.llm_config.DEFAULT_TIMEOUT,
            max_retries=self.llm_config.DEFAULT_MAX_RETRIES,
            request_timeout=self.llm_config.DEFAULT_TIMEOUT,
            max_tokens=self.llm_config.DEFAULT_MAX_TOKENS
        )
    
    def _create_llm_instance(self, temperature: float, max_tokens: int, timeout: int) -> ChatOpenAI:
        """创建LLM实例的工厂方法
        
        Args:
            temperature: 温度参数
            max_tokens: 最大token数
            timeout: 超时时间
            
        Returns:
            配置好的ChatOpenAI实例
        """
        return ChatOpenAI(
            model=self.llm.model_name,
            api_key=self.llm.openai_api_key,
            base_url=self.llm.openai_api_base,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )

    def _build_prompt(self) -> PromptTemplate:
        """构建提示模板"""
        return PromptTemplate.from_template("""
            你是资产管理助手。能够理解自然语言并完成完整的多步骤任务流程。

            可用工具: {tools}

            ⚠️ 重要提醒：
            - 如果用户输入中包含"系统提供的认证信息"或直接提供了userToken和clientToken，请直接使用这些令牌
            - 在这种情况下，绝对不要调用generate_client_token_mcp或generate_user_token_mcp工具
            - 直接从提供的信息中提取userToken和clientToken进行后续操作

            任务流程:
            1. 检查用户请求中是否已包含认证令牌（userToken和clientToken）
               - 如果已包含，直接使用这些令牌
               - 如果缺少，则调用 generate_client_token_mcp, generate_user_token_mcp 获取
            2. 创建或查询成员 (add_enterprise_member_mcp, query_enterprise_members_mcp)
            3. 查询资产状态 (query_assets_by_status_mcp)
            4. 分配资产权限 (allocate_asset_privileges_mcp)
            
            示例流程：
            1、查询张三已分配的资产详情
                第一步：确定用户是通过用户名查询已分配有效资产
                第二步：确认参数searchType=memberAccount，searchCondition=张三，assetStatus=[VALID,ASSIGNED]
                第三步：查询资产状态 query_assets_by_status_mcp 进行查询
            2、给张三001分配一个包含计价产品的资产    
                第一步：查询用户名为张三001的授权成员，使用工具query_enterprise_members_mcp,searchType=memberAccount，searchCondition=张三001
                第二步：查询有效且未分配并且包含计价产品的资产，使用工具query_assets_by_status_mcp
                第三步：给张三分配资产，使用工具allocate_asset_privileges_mcp
            3、创建账号并分配资产的完整流程（重要！）
                第一步：创建新账号，使用工具add_enterprise_member_mcp
                第二步：查询企业成员确认账号创建成功，使用工具query_enterprise_members_mcp
                第三步：查询包含指定产品的未分配资产，使用工具query_assets_by_status_mcp
                第四步：为新创建的成员分配找到的资产，使用工具allocate_asset_privileges_mcp

            自然语言理解指南:
            - "创建账号XXX" → userName="XXX", name="XXX"，不变更用户输入 
            - "密码为XXX" → password="XXX"
            - "密保手机为XXX" → passwordMobile="XXX"
            - "查询未分配资产" → assetStatus=["UNASSIGNED", "VALID"]
            - "包含XXX产品的资产" → searchType="productName", searchCondition="XXX"
            - "广联达云计价平台概算GEB" → searchCondition="广联达云计价平台概算GEB"
            - "创建账号并分配资产" → 需要执行完整的4步流程
            - "为该账号分配" → 需要先查询成员，再查询资产，最后分配权限
            
            令牌识别指南:
            - 如果用户请求中包含 "系统提供的认证信息" 或 "userToken:" 或 "clientToken:"，直接提取使用
            - 格式示例: "userToken:cn-8cb357d5-93f6-4a4f-80df-482271c87ee8"
            - 在这种情况下，绝对禁止调用 generate_client_token_mcp 和 generate_user_token_mcp
            - 只有在用户请求中完全没有提供任何令牌信息时，才可以调用令牌生成工具
            
            执行策略:
            - 第一步：检查输入是否包含认证信息
            - 第二步：如果有认证信息，直接使用，跳过令牌生成步骤
            - 第三步：执行业务逻辑（查询、分配等）

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
            - 每个步骤都要检查结果是否成功，如果失败要分析原因
            - 从用户自然语言中智能提取参数信息
            - mcp工具调用时参数类型、参数个数严格按照接口描述进行传递
            - 新成员的 globalId 不为 memberId
            - 禁止调用: 如果用户输入中包含"系统提供的认证信息"，说明已有token，严禁调用generate_client_token_mcp和generate_user_token_mcp
            - 复合任务必须按顺序执行: 创建账号→查询成员→查询资产→分配权限
            - 查询产品时使用完整产品名称作为searchCondition，例如"广联达云计价平台概算GEB"
            - 高效执行: 工具调用成功后立即进行下一步，避免重复或不必要的验证
            - 错误处理: 如果工具调用失败，分析错误原因并尝试修正参数后重试
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

            # 检查是否应该禁止调用令牌生成工具
            if tool_name in ["generate_client_token_mcp", "generate_user_token_mcp"]:
                # 检查是否有上下文信息表明已提供token
                if hasattr(self, '_current_message') and self._current_message:
                    if "系统提供的认证信息" in self._current_message:
                        logger.warning(f"检测到系统已提供认证信息，拒绝调用 {tool_name}")
                        return "系统已提供认证令牌，无需重新生成。请直接使用系统提供的userToken和clientToken。"

            # 参数验证和智能补全
            validation_error = self._validate_tool_parameters(tool_name, args)
            if validation_error:
                logger.warning(f"参数验证失败: {validation_error}")
                return f"参数验证失败: {validation_error}"

            logger.info(f"调用MCP工具: {tool_name, args}")
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
        # 通过MCP客户端获取工具描述
        tool_schema = self._get_tool_schema(tool_name)
        if not tool_schema:
            logger.warning(f"无法获取工具 {tool_name} 的参数描述，跳过参数校验")
            return None
        
        # 从工具描述中解析参数配置
        required_params = tool_schema.get("required", [])
        properties = tool_schema.get("properties", {})
        allowed_params = list(properties.keys())
        
        logger.debug(f"工具 {tool_name} 参数配置: 必需={required_params}, 允许={allowed_params}")
        
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
        
        # 智能参数补全（在必需参数检查之前执行）
        self._auto_complete_parameters(tool_name, args, properties)
        
        # 重新过滤参数（补全后可能增加了新参数）
        final_filtered_args = {}
        for key, value in args.items():
            if key in allowed_params:
                final_filtered_args[key] = value
            else:
                logger.debug(f"过滤掉补全后不需要的参数: {key}")
        
        # 更新args为最终过滤后的参数
        args.clear()
        args.update(final_filtered_args)
        
        # 检查必需参数（在智能补全之后检查）
        missing_params = []
        for param in required_params:
            if param not in args:
                missing_params.append(param)
        
        if missing_params:
            return f"缺少必需参数: {', '.join(missing_params)}。请提供完整的参数。"
        
        # 基于工具描述进行参数类型验证
        validation_error = self._validate_parameter_types(args, properties)
        if validation_error:
            return validation_error
        
        # 动态特殊验证和修复
        validation_error = self._apply_dynamic_validation_rules(tool_name, args, properties)
        if validation_error:
            return validation_error
        
        return None

    def _get_tool_schema(self, tool_name: str) -> Optional[Dict]:
        """获取工具的参数描述"""
        try:
            # 从MCP客户端获取工具列表
            tools_result = self.mcp_client.get_tools()
            if not tools_result.get("success"):
                logger.error(f"获取工具列表失败: {tools_result.get('error')}")
                return None
            
            tools = tools_result.get("data", [])
            logger.debug(f"获取到 {len(tools)} 个工具")
            
            # 查找指定工具的描述
            for tool in tools:
                if tool.get("name") == tool_name:
                    logger.debug(f"找到工具 {tool_name}，工具结构: {tool.keys()}")
                    
                    # 尝试不同的参数描述字段名
                    input_schema = None
                    
                    # 常见的参数描述字段名
                    schema_fields = ["inputSchema", "parameters", "schema", "input_schema", "args_schema"]
                    
                    for field in schema_fields:
                        if field in tool:
                            input_schema = tool[field]
                            logger.debug(f"在字段 {field} 中找到参数描述")
                            break
                    
                    if input_schema:
                        logger.debug(f"获取工具 {tool_name} 的参数描述: {input_schema}")
                        return input_schema
                    else:
                        # 如果没有找到参数描述，尝试从函数签名生成
                        logger.info(f"尝试从工具描述生成参数描述: {tool_name}")
                        generated_schema = self._generate_schema_from_description(tool)
                        if generated_schema:
                            logger.info(f"成功生成工具 {tool_name} 的参数描述")
                            return generated_schema
                        
                        # 记录工具的完整结构用于调试
                        logger.warning(f"工具 {tool_name} 没有参数描述，工具完整结构: {tool}")
                        return None
            
            logger.warning(f"未找到工具: {tool_name}，可用工具: {[t.get('name') for t in tools]}")
            return None
            
        except Exception as e:
            logger.error(f"获取工具参数描述失败: {str(e)}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return None

    def _generate_schema_from_description(self, tool: Dict) -> Optional[Dict]:
        """从工具描述生成参数描述
        
        Args:
            tool: 工具信息字典
            
        Returns:
            生成的参数schema，失败返回None
        """
        try:
            description = tool.get("description", "")
            if not description:
                return None
            
            # 查找Args部分
            args_match = re.search(r'Args:\s*(.*?)(?:\n\n|\nReturns:|\nNote:|\Z)', description, re.DOTALL)
            if not args_match:
                return None
            
            args_text = args_match.group(1)
            
            # 解析每个参数
            param_pattern = r'(\w+)\s*\(([^)]+)\):\s*([^\n]+)'
            matches = re.findall(param_pattern, args_text)
            
            if not matches:
                return None
            
            properties = {}
            required = []
            
            for param_name, param_type, param_desc in matches:
                param_info = self._parse_parameter_info(param_name, param_type, param_desc, required)
                properties[param_name] = param_info
            
            schema = {
                "type": "object",
                "properties": properties,
                "required": required
            }
            
            logger.debug(f"生成的参数描述: {schema}")
            return schema
            
        except Exception as e:
            logger.error(f"从描述生成参数描述失败: {str(e)}")
            return None
    
    def _parse_parameter_info(self, param_name: str, param_type: str, param_desc: str, required: List[str]) -> Dict:
        """解析单个参数的信息
        
        Args:
            param_name: 参数名
            param_type: 参数类型字符串
            param_desc: 参数描述
            required: 必需参数列表（会被修改）
            
        Returns:
            参数信息字典
        """
        # 提取基础类型
        base_type = param_type.split(',')[0].strip()
        if 'optional' not in param_type.lower():
            required.append(param_name)
        
        # 转换类型
        json_type = TYPE_MAPPING.get(base_type, 'string')
        
        param_info = {
            "type": json_type,
            "description": param_desc.strip()
        }
        
        # 添加默认值（如果有）
        default_match = re.search(r'默认为(\d+|"[^"]*")', param_desc)
        if default_match:
            default_val = default_match.group(1)
            param_info["default"] = (
                default_val.strip('"') if default_val.startswith('"') 
                else int(default_val) if default_val.isdigit() 
                else default_val
            )
        
        # 添加枚举值（如果有）
        enum_match = re.search(r'可选值[：:]([^。\n]+)', param_desc)
        if enum_match:
            enum_text = enum_match.group(1)
            enum_values = re.findall(r'["\']([^"\']+)["\']|(\w+)', enum_text)
            if enum_values:
                param_info["enum"] = [val[0] or val[1] for val in enum_values if val[0] or val[1]]
        
        return param_info

    def _auto_complete_parameters(self, tool_name: str, args: Dict, properties: Dict) -> None:
        """通过LLM智能补全缺失参数
        
        Args:
            tool_name: 工具名称
            args: 参数字典（会被修改）
            properties: 参数属性定义
        """
        # 首先尝试从当前消息中提取token（基于工具参数要求）
        self._extract_tokens_from_message(args, properties)
        
        # 基于工具描述进行基础参数补全
        self._apply_basic_parameter_completion(tool_name, args, properties)
        
        # 使用LLM智能补全复杂参数
        missing_params = [param for param in properties.keys() if param not in args]
        if missing_params and hasattr(self, '_current_message') and self._current_message:
            llm_completed_params = self._llm_complete_parameters(tool_name, args, missing_params, properties)
            if llm_completed_params:
                args.update(llm_completed_params)
        
        logger.debug(f"参数补全完成，最终参数: {args}")
    
    def _apply_basic_parameter_completion(self, tool_name: str, args: Dict, properties: Dict) -> None:
        """应用基础参数补全规则
        
        Args:
            tool_name: 工具名称
            args: 参数字典（会被修改）
            properties: 参数属性定义
        """
        for param_name, param_info in properties.items():
            if param_name in args:
                continue
            
            # 获取参数的默认值
            default_value = param_info.get("default")
            if default_value is not None:
                args[param_name] = default_value
                logger.info(f"从工具描述自动补全 {param_name} 为默认值: {default_value}")
                continue
            
            # 基础参数补全
            param_type = param_info.get("type", "")
            completed_value = self._get_default_param_value(tool_name, param_name, param_type)
            if completed_value is not None:
                args[param_name] = completed_value
                logger.info(f"基础参数补全 {param_name}: {completed_value}")
    
    def _get_default_param_value(self, tool_name: str, param_name: str, param_type: str) -> Any:
        """获取参数的默认值
        
        Args:
            tool_name: 工具名称
            param_name: 参数名称
            param_type: 参数类型
            
        Returns:
            默认值，如果没有返回None
        """
        if param_name == "grantType":
            if tool_name == "generate_client_token_mcp":
                return "client_credentials"
            elif tool_name == "generate_user_token_mcp":
                return "uid"
        elif param_name == "pageNum" and param_type == "integer":
            return self.validation_config.DEFAULT_PAGE_NUM
        elif param_name == "pageSize" and param_type == "integer":
            return self.validation_config.DEFAULT_PAGE_SIZE
        elif param_name == "keyword" and param_type == "string":
            return ""
        
        return None

    def _llm_complete_parameters(self, tool_name: str, existing_args: Dict, missing_params: List[str], properties: Dict) -> Dict:
        """使用LLM智能补全缺失的参数"""
        try:
            # 构建参数描述
            param_descriptions = []
            for param in missing_params:
                param_info = properties.get(param, {})
                param_type = param_info.get("type", "unknown")
                param_desc = param_info.get("description", "")
                enum_values = param_info.get("enum", [])
                
                desc_text = f"- {param} ({param_type}): {param_desc}"
                if enum_values:
                    desc_text += f" 可选值: {enum_values}"
                param_descriptions.append(desc_text)
            
            # 构建LLM提示
            prompt = f"""
                基于用户的原始请求，为工具 {tool_name} 智能补全缺失的参数。

                用户原始请求:
                {self._current_message}

                工具已有参数:
                {existing_args}

                需要补全的参数:
                {chr(10).join(param_descriptions)}

                请根据用户请求的语义理解，智能推断这些参数的值。

                参数补全规则:
                1. searchType参数推断:
                - 如果用户提到具体用户名/账号，使用 "memberAccount"
                - 如果用户提到产品名称/软件名称，使用 "productName" 
                - 如果用户提到资产编号，使用 "assetNum"
                - 如果用户提到产品URI，使用 "productUri"

                2. assetStatus参数推断:
                - 用户要分配资产时，查询 ["UNASSIGNED", "VALID"] (未分配的有效资产)
                - 用户查询已分配资产时，使用 ["ASSIGNED", "VALID"]
                - 没有明确指定时，默认使用 ["VALID"]

                3. searchCondition参数推断:
                - 提取用户请求中的具体关键词
                - 产品名称要使用完整名称，如"广联达云计价平台概算GEB"
                - 用户名要使用具体的用户名
                
                4、password参数推断: 
                - 初始密码，8-16个字符，必须包含至少两种字符类型（数字、字母、符号），不指定时随机生成
                
                5、可选入参字段，用户无明确说明时，不进行处理（严格执行）
                 
                示例：创建成员白玉亮003并为该成员分配一个包含云计价产品的资产
                {"name": "白玉亮003","userName":"白玉亮003","searchCondition":"白玉亮003"} 
                 
                请严格按照以下JSON格式返回，不要添加任何其他文字:
                {{
                "参数名": "参数值"
                }}

                如果无法确定某个参数的值，请省略该参数。
                """
            
            # 创建LLM实例进行参数补全
            completion_llm = self._create_llm_instance(
                temperature=self.llm_config.COMPLETION_TEMPERATURE,
                max_tokens=self.llm_config.COMPLETION_MAX_TOKENS,
                timeout=self.llm_config.COMPLETION_TIMEOUT
            )
            
            response = completion_llm.invoke(prompt)
            logger.debug(f"LLM参数补全返回: {response.content}")
            
            # 尝试提取JSON
            json_match = re.search(r'\{[^}]*\}', response.content, re.DOTALL)

            if json_match:
                completed_params = json.loads(json_match.group())
                
                # 验证参数类型
                validated_params = {}
                for param_name, param_value in completed_params.items():
                    if param_name in missing_params:
                        param_info = properties.get(param_name, {})
                        param_type = param_info.get("type", "")
                        
                        # 类型转换和验证
                        try:
                            if param_type == "array" and not isinstance(param_value, list):
                                if isinstance(param_value, str):
                                    validated_params[param_name] = [param_value]
                                else:
                                    validated_params[param_name] = param_value
                            elif param_type == "integer" and not isinstance(param_value, int):
                                validated_params[param_name] = int(param_value)
                            elif param_type == "string" and not isinstance(param_value, str):
                                validated_params[param_name] = str(param_value)
                            else:
                                validated_params[param_name] = param_value
                                
                            logger.info(f"LLM智能补全参数 {param_name}: {validated_params[param_name]}")
                        except (ValueError, TypeError) as e:
                            logger.warning(f"LLM补全参数 {param_name} 类型转换失败: {e}")
                            continue
                
                return validated_params
            else:
                logger.warning("LLM返回格式不正确，无法解析参数补全结果")
                return {}
                
        except Exception as e:
            logger.error(f"LLM参数补全失败: {str(e)}")
            return {}

    def _extract_tokens_from_message(self, args: Dict, properties: Dict) -> None:
        """从当前消息中提取token并补全到参数中（仅当工具需要时）"""
        if not hasattr(self, '_current_message') or not self._current_message:
            return
            
        import re
        
        # 只有当工具参数中定义了userToken时才提取
        if "userToken" in properties and "userToken" not in args:
            user_token_match = re.search(r'-\s*userToken:\s*([^\s\n]+)', self._current_message)
            if user_token_match:
                args["userToken"] = user_token_match.group(1)
                logger.info(f"从消息中提取并补全 userToken: {user_token_match.group(1)[:20]}...")
            else:
                logger.warning("工具需要userToken但未能从消息中提取")
        
        # 只有当工具参数中定义了clientToken时才提取
        if "clientToken" in properties and "clientToken" not in args:
            client_token_match = re.search(r'-\s*clientToken:\s*([^\s\n]+)', self._current_message)
            if client_token_match:
                args["clientToken"] = client_token_match.group(1)
                logger.info(f"从消息中提取并补全 clientToken: {client_token_match.group(1)[:20]}...")
            else:
                logger.warning("工具需要clientToken但未能从消息中提取")

    def _validate_parameter_types(self, args: Dict, properties: Dict) -> Optional[str]:
        """基于工具描述验证参数类型"""
        for param_name, param_value in args.items():
            if param_name not in properties:
                continue
            
            param_info = properties[param_name]
            expected_type = param_info.get("type", "")
            
            # 验证参数类型
            if expected_type == "string" and not isinstance(param_value, str):
                return f"参数 {param_name} 应该是字符串类型，当前类型: {type(param_value).__name__}"
            
            elif expected_type == "integer" and not isinstance(param_value, int):
                # 尝试转换为整数
                try:
                    args[param_name] = int(param_value)
                    logger.info(f"自动转换参数 {param_name} 为整数: {args[param_name]}")
                except (ValueError, TypeError):
                    return f"参数 {param_name} 应该是整数类型，无法转换: {param_value}"
            
            elif expected_type == "number" and not isinstance(param_value, (int, float)):
                # 尝试转换为数字
                try:
                    args[param_name] = float(param_value)
                    logger.info(f"自动转换参数 {param_name} 为数字: {args[param_name]}")
                except (ValueError, TypeError):
                    return f"参数 {param_name} 应该是数字类型，无法转换: {param_value}"
            
            elif expected_type == "boolean" and not isinstance(param_value, bool):
                # 尝试转换为布尔值
                if isinstance(param_value, str):
                    if param_value.lower() in ['true', '1', 'yes', 'on']:
                        args[param_name] = True
                        logger.info(f"自动转换参数 {param_name} 为布尔值: True")
                    elif param_value.lower() in ['false', '0', 'no', 'off']:
                        args[param_name] = False
                        logger.info(f"自动转换参数 {param_name} 为布尔值: False")
                    else:
                        return f"参数 {param_name} 应该是布尔类型，无法转换: {param_value}"
                else:
                    return f"参数 {param_name} 应该是布尔类型，当前类型: {type(param_value).__name__}"
            
            elif expected_type == "array" and not isinstance(param_value, list):
                # 尝试转换为数组
                if isinstance(param_value, str):
                    # 如果是字符串，尝试转换为单元素数组
                    args[param_name] = [param_value]
                    logger.info(f"自动转换参数 {param_name} 为数组: {args[param_name]}")
                else:
                    return f"参数 {param_name} 应该是数组类型，当前类型: {type(param_value).__name__}"
            
            # 验证枚举值
            enum_values = param_info.get("enum")
            if enum_values and param_value not in enum_values:
                return f"参数 {param_name} 的值必须是 {enum_values} 中的一个，当前值: {param_value}"
            
            # 验证字符串长度
            if expected_type == "string" and isinstance(param_value, str):
                min_length = param_info.get("minLength")
                max_length = param_info.get("maxLength")
                
                if min_length is not None and len(param_value) < min_length:
                    return f"参数 {param_name} 长度不能少于 {min_length} 个字符，当前长度: {len(param_value)}"
                
                if max_length is not None and len(param_value) > max_length:
                    return f"参数 {param_name} 长度不能超过 {max_length} 个字符，当前长度: {len(param_value)}"
            
            # 验证数字范围
            if expected_type in ["integer", "number"] and isinstance(param_value, (int, float)):
                minimum = param_info.get("minimum")
                maximum = param_info.get("maximum")
                
                if minimum is not None and param_value < minimum:
                    return f"参数 {param_name} 不能小于 {minimum}，当前值: {param_value}"
                
                if maximum is not None and param_value > maximum:
                    return f"参数 {param_name} 不能大于 {maximum}，当前值: {param_value}"
        
        return None

    def _apply_dynamic_validation_rules(self, tool_name: str, args: Dict, properties: Dict) -> Optional[str]:
        """动态应用验证和修复规则"""
        
        # 遍历所有参数，应用基于参数描述的验证规则
        for param_name, param_value in args.items():
            if param_name not in properties:
                continue
                
            param_info = properties[param_name]
            
            # 应用格式修复规则
            fix_error = self._apply_format_fixes(param_name, param_value, param_info, args)
            if fix_error:
                return fix_error
            
            # 应用业务逻辑验证规则
            business_error = self._apply_business_validation(tool_name, param_name, param_value, param_info)
            if business_error:
                return business_error
        
        # 应用跨参数验证规则
        cross_param_error = self._apply_cross_parameter_validation(tool_name, args, properties)
        if cross_param_error:
            return cross_param_error
        
        return None

    def _apply_format_fixes(self, param_name: str, param_value: Any, param_info: Dict, args: Dict) -> Optional[str]:
        """应用格式修复规则"""
        
        # 数组格式自动修复
        if param_info.get("type") == "array" and not isinstance(param_value, list):
            if isinstance(param_value, str):
                # 字符串转数组
                args[param_name] = [param_value]
                logger.info(f"自动修复 {param_name} 格式: 字符串 -> 数组")
            elif param_value is not None:
                # 其他类型转数组
                args[param_name] = [param_value]
                logger.info(f"自动修复 {param_name} 格式: {type(param_value).__name__} -> 数组")
        
        # 字符串格式修复
        elif param_info.get("type") == "string" and not isinstance(param_value, str):
            if param_value is not None:
                args[param_name] = str(param_value)
                logger.info(f"自动修复 {param_name} 格式: {type(param_value).__name__} -> 字符串")
        
        # 整数格式修复
        elif param_info.get("type") == "integer" and not isinstance(param_value, int):
            try:
                args[param_name] = int(param_value)
                logger.info(f"自动修复 {param_name} 格式: {type(param_value).__name__} -> 整数")
            except (ValueError, TypeError):
                return f"参数 {param_name} 无法转换为整数: {param_value}"
        
        return None

    def _apply_business_validation(self, tool_name: str, param_name: str, param_value: Any, param_info: Dict) -> Optional[str]:
        """应用业务逻辑验证规则
        
        Args:
            tool_name: 工具名称
            param_name: 参数名
            param_value: 参数值
            param_info: 参数信息
            
        Returns:
            错误信息，如果验证通过返回None
        """
        validators = {
            "userName": self._validate_username,
            "password": self._validate_password,
            "email": self._validate_email,
            "phone": self._validate_phone,
        }
        
        # 特定参数验证
        validator = validators.get(param_name)
        if validator and isinstance(param_value, str):
            return validator(param_value)
        
        # 时间戳验证
        if param_name.endswith("Time") and isinstance(param_value, (int, float)):
            return self._validate_timestamp(param_value)
        
        return None
    
    def _validate_username(self, username: str) -> Optional[str]:
        """验证用户名"""
        if not (self.validation_config.USERNAME_MIN_LENGTH <= len(username) <= self.validation_config.USERNAME_MAX_LENGTH):
            return f"用户名长度必须在{self.validation_config.USERNAME_MIN_LENGTH}-{self.validation_config.USERNAME_MAX_LENGTH}个字符之间，当前长度: {len(username)}"
        if not username.replace('_', '').replace('-', '').isalnum():
            return f"用户名只能包含字母、数字、下划线和连字符: {username}"
        return None
    
    def _validate_password(self, password: str) -> Optional[str]:
        """验证密码"""
        if not (self.validation_config.PASSWORD_MIN_LENGTH <= len(password) <= self.validation_config.PASSWORD_MAX_LENGTH):
            return f"密码长度必须在{self.validation_config.PASSWORD_MIN_LENGTH}-{self.validation_config.PASSWORD_MAX_LENGTH}个字符之间，当前长度: {len(password)}"
        
        # 检查密码复杂度
        has_digit = any(c.isdigit() for c in password)
        has_alpha = any(c.isalpha() for c in password)
        has_symbol = any(not c.isalnum() for c in password)
        
        if sum([has_digit, has_alpha, has_symbol]) < 2:
            return "密码必须包含至少两种字符类型（数字、字母、符号）"
        return None
    
    def _validate_email(self, email: str) -> Optional[str]:
        """验证邮箱格式"""
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return f"邮箱格式不正确: {email}"
        return None
    
    def _validate_phone(self, phone: str) -> Optional[str]:
        """验证手机号格式"""
        phone_pattern = r'^1[3-9]\d{9}$'
        if not re.match(phone_pattern, phone):
            return f"手机号格式不正确: {phone}"
        return None
    
    def _validate_timestamp(self, timestamp: float) -> Optional[str]:
        """验证时间戳"""
        if timestamp < 0:
            return f"时间戳不能为负数: {timestamp}"
        if timestamp > self.validation_config.MAX_TIMESTAMP:
            return f"时间戳超出合理范围: {timestamp}"
        return None

    def _apply_cross_parameter_validation(self, tool_name: str, args: Dict, properties: Dict) -> Optional[str]:
        """应用跨参数验证规则
        
        Args:
            tool_name: 工具名称
            args: 参数字典
            properties: 参数属性定义
            
        Returns:
            错误信息，如果验证通过返回None
        """
        # 时间范围验证
        time_error = self._validate_time_range(args)
        if time_error:
            return time_error
        
        # 分页参数验证
        page_error = self._validate_pagination(args)
        if page_error:
            return page_error
        
        # 数组元素验证
        array_error = self._validate_array_elements(args, properties)
        if array_error:
            return array_error
        
        return None
    
    def _validate_time_range(self, args: Dict) -> Optional[str]:
        """验证时间范围参数"""
        if "limitStartTime" in args and "limitEndTime" in args:
            start_time = args["limitStartTime"]
            end_time = args["limitEndTime"]
            if isinstance(start_time, (int, float)) and isinstance(end_time, (int, float)):
                if start_time >= end_time:
                    return f"开始时间必须小于结束时间: {start_time} >= {end_time}"
        return None
    
    def _validate_pagination(self, args: Dict) -> Optional[str]:
        """验证分页参数"""
        if "pageNum" in args and "pageSize" in args:
            page_num = args["pageNum"]
            page_size = args["pageSize"]
            if isinstance(page_num, int) and isinstance(page_size, int):
                if page_num < 1:
                    return f"页码必须大于0: {page_num}"
                if not (1 <= page_size <= self.validation_config.MAX_PAGE_SIZE):
                    return f"页面大小必须在1-{self.validation_config.MAX_PAGE_SIZE}之间: {page_size}"
        return None
    
    def _validate_array_elements(self, args: Dict, properties: Dict) -> Optional[str]:
        """验证数组元素"""
        for param_name, param_value in args.items():
            if not isinstance(param_value, list) or param_name not in properties:
                continue
            
            param_info = properties[param_name]
            items_info = param_info.get("items", {})
            
            # 验证对象数组的必需字段
            if items_info.get("type") == "object":
                required_fields = items_info.get("required", [])
                for i, item in enumerate(param_value):
                    if not isinstance(item, dict):
                        return f"{param_name}[{i}] 必须是对象类型"
                    for field in required_fields:
                        if field not in item:
                            return f"{param_name}[{i}] 缺少必需字段: {field}"
        
        return None

    def _create_agent_executor(self) -> AgentExecutor:
        """每次请求动态创建新的AgentExecutor，保证并发安全
        
        Returns:
            配置好的AgentExecutor实例
        """
        agent = create_react_agent(self.llm, self.tools, self._prompt)
        return AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=False,
            max_iterations=self.agent_config.MAX_ITERATIONS,
            max_execution_time=self.agent_config.MAX_EXECUTION_TIME,
            return_intermediate_steps=True,
            handle_parsing_errors=True,
            early_stopping_method=self.agent_config.EARLY_STOPPING_METHOD
        )

    def process_request(self, user_message: str, user_token: str = None, client_token: str = None) -> Dict[str, Any]:
        """处理用户请求（并发安全）"""
        try:
            logger.info(f"处理请求: {user_message[:50]}...")

            # 如果提供了token，增强消息内容
            if user_token and client_token:
                enhanced_message = f"{user_message}\n\n系统提供的认证信息:\n- userToken: {user_token}\n- clientToken: {client_token}\n\n请直接使用这些认证令牌，无需重新生成。"
                logger.info(f"使用header中的认证token: userToken={user_token[:20]}..., clientToken={client_token[:20]}...")
            else:
                enhanced_message = user_message

            # 设置当前消息供工具调用检查
            self._current_message = enhanced_message

            agent_executor = self._create_agent_executor()
            result = agent_executor.invoke({"input": enhanced_message})

            output = result.get("output", "")
            intermediate_steps = result.get("intermediate_steps", [])
            tools_used = [step[0].tool for step in intermediate_steps if len(step) >= 2]
            
            # 解析简化的思考步骤
            thinking_steps = self._parse_simple_thinking_steps(intermediate_steps)

            # 简化技术性输出为用户友好的消息
            simplified_output = self._simplify_success_message(output)

            return {
                "success": True,
                "message": "请求处理完成",
                "output": simplified_output,
                "original_output": output,  # 保留原始输出用于调试
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

    def process_request_with_streaming(self, user_message: str, user_token: str = None, client_token: str = None) -> Dict[str, Any]:
        """处理用户请求，支持流式思考步骤（同步版本，用于线程池执行）"""
        try:
            logger.info(f"流式处理请求: {user_message[:50]}...")

            # 检查是否提供了认证token
            if not user_token or not client_token:
                logger.warning("请求缺少必要的认证token")
                return {
                    "success": False,
                    "message": "请求缺少必要的认证信息",
                    "output": "请确保在请求头中包含userToken和clientToken",
                    "allocation_plan": {},
                    "current_step": "error",
                    "thinking_steps": [],
                    "tools_used": []
                }

            # 在用户消息中添加token信息，供Agent使用
            enhanced_message = f"{user_message}\n\n系统提供的认证信息:\n- userToken: {user_token}\n- clientToken: {client_token}\n\n请直接使用这些认证令牌，无需重新生成。"
            logger.info(f"使用header中的认证token: userToken={user_token[:20]}..., clientToken={client_token[:20]}...")

            # 设置当前消息供工具调用检查
            self._current_message = enhanced_message

            agent_executor = self._create_agent_executor()
            result = agent_executor.invoke({"input": enhanced_message})

            output = result.get("output", "")
            intermediate_steps = result.get("intermediate_steps", [])
            tools_used = [step[0].tool for step in intermediate_steps if len(step) >= 2]
            
            # 解析简化的思考步骤（用于流式传输）
            thinking_steps = self._parse_streaming_thinking_steps(intermediate_steps)

            # 简化技术性输出为用户友好的消息
            simplified_output = self._simplify_success_message(output)

            logger.info(f"流式请求处理完成，使用了 {len(tools_used)} 个工具，{len(thinking_steps)} 个思考步骤")

            return {
                "success": True,
                "message": "请求处理完成",
                "output": simplified_output,
                "original_output": output,  # 保留原始输出用于调试
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
            return self._generate_fallback_thinking_steps(raw_steps)

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

            请严格按照以下JSON格式返回，不要添加任何其他文字：
            [
              {{
                "content": "正在获取认证信息",
                "result": "认证成功",
                "result_type": "success",
                "status": "completed",
                "progress": "1/{len(raw_steps)}"
              }},
              {{
                "content": "正在查询资产信息",
                "result": "找到5个相关资产",
                "result_type": "success", 
                "status": "completed",
                "progress": "2/{len(raw_steps)}"
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

    def _generate_fallback_thinking_steps(self, raw_steps) -> List[Dict[str, Any]]:
        """生成备用的思考步骤（当LLM优化失败时使用）"""
        simple_steps = []
        
        for i, step in enumerate(raw_steps, 1):
            # 从工具名称推断操作类型
            tool_name = step['tool']
            thought = step['thought']
            observation = step['observation']
            
            # 根据工具类型生成用户友好的描述
            if 'generate_client_token' in tool_name:
                content = "正在获取客户端认证令牌..."
                result = "客户端认证成功，已获得访问权限"
            elif 'generate_user_token' in tool_name:
                content = "正在获取用户认证令牌..."
                result = "用户身份验证完成，已建立安全连接"
            elif 'query_assets_by_status' in tool_name:
                content = "正在查询资产信息和状态..."
                # 尝试从观察结果中提取数字信息
                import re
                numbers = re.findall(r'\d+', observation)
                if numbers:
                    result = f"已找到 {numbers[0]} 个相关资产记录"
                else:
                    result = "资产查询完成，正在分析数据"
            elif 'query_enterprise_members' in tool_name:
                content = "正在查询企业成员信息..."
                numbers = re.findall(r'\d+', observation)
                if numbers:
                    result = f"已获取 {numbers[0]} 个成员的详细信息"
                else:
                    result = "成员信息查询完成"
            elif 'allocate_asset_privileges' in tool_name:
                content = "正在执行资产权限分配操作..."
                if 'success' in observation.lower() or '成功' in observation:
                    result = "权限分配操作执行成功"
                else:
                    result = "权限分配操作已完成"
            elif 'add_enterprise_member' in tool_name:
                content = "正在创建新的企业成员账号..."
                if 'success' in observation.lower() or '成功' in observation:
                    result = "新成员账号创建成功"
                else:
                    result = "成员账号创建操作已完成"
            else:
                # 通用处理
                content = f"正在执行 {tool_name.replace('_mcp', '').replace('_', ' ')} 操作..."
                result = "操作执行完成"
            
            # 判断结果类型
            if 'error' in observation.lower() or 'failed' in observation.lower() or '失败' in observation:
                result_type = 'error'
                result = "操作执行失败，请检查参数"
            elif 'success' in observation.lower() or '成功' in observation or 'true' in observation.lower():
                result_type = 'success'
            else:
                result_type = 'info'
            
            step_info = {
                "step": i,
                "type": "thinking",
                "content": content,
                "result": result,
                "result_type": result_type,
                "progress": f"{i}/{len(raw_steps)}",
                "timestamp": datetime.now().isoformat()
            }
            simple_steps.append(step_info)
        
        return simple_steps

    def _generate_default_thinking_steps(self) -> List[Dict[str, Any]]:
        """生成默认的思考步骤（当没有原始步骤时使用）"""
        return [
            {
                "step": 1,
                "type": "thinking",
                "content": "正在分析您的请求...",
                "result": "请求分析完成，开始处理",
                "result_type": "success",
                "progress": "1/3",
                "timestamp": datetime.now().isoformat()
            },
            {
                "step": 2,
                "type": "thinking", 
                "content": "正在执行相关操作...",
                "result": "操作执行中，请稍候",
                "result_type": "info",
                "progress": "2/3",
                "timestamp": datetime.now().isoformat()
            },
            {
                "step": 3,
                "type": "thinking",
                "content": "正在整理结果...",
                "result": "处理完成，准备返回结果",
                "result_type": "success", 
                "progress": "3/3",
                "timestamp": datetime.now().isoformat()
            }
        ]

    def _extract_allocation_info(self, output: str) -> Dict[str, Any]:
        """从输出中提取分配信息"""
        return {
            "summary": output,
            "timestamp": datetime.now().isoformat(),
            "status": "completed" if "成功" in output or "完成" in output else "failed"
        }

    def _simplify_success_message(self, technical_output: str) -> str:
        """将技术性的成功消息转换为用户友好的信息"""
        try:
            # 使用LLM简化技术消息
            simplify_prompt = f"""
            请将以下技术性的操作结果转换为简洁、友好的用户消息。

            技术输出:
            {technical_output}

            转换要求:
            1. 去掉所有技术术语（如memberId、globalId、assetId等）
            2. 用简单易懂的语言描述操作结果
            3. 突出用户关心的核心信息（姓名、账号、资产等）
            4. 保持简洁，避免冗长的流程描述
            5. 使用友好的语气

            示例转换:
            技术输出: "成员ID（memberId）为：bf036025d2984c03b316d36a57e10caa，globalId 为 7376454108297884596"
            友好输出: "账号创建成功"

            技术输出: "选取第一个资产（编号：YSZZ8000155423，ID：ead32d1a60334d9cbefdd41a167ba858）"
            友好输出: "已为您分配资产 YSZZ8000155423"

            请直接返回简化后的友好消息，不要添加任何解释或格式标记：
            """

            # 创建LLM实例进行消息简化
            simplify_llm = ChatOpenAI(
                model=self.llm.model_name,
                api_key=self.llm.openai_api_key,
                base_url=self.llm.openai_api_base,
                temperature=0.2,  # 较低温度保证稳定输出
                max_tokens=300,
                timeout=10
            )

            response = simplify_llm.invoke(simplify_prompt)
            simplified_message = response.content.strip()

            # 如果简化后的消息太短或为空，返回默认消息
            if len(simplified_message) < 10:
                return "操作已成功完成！"

            return simplified_message

        except Exception as e:
            logger.error(f"简化成功消息失败: {str(e)}")
            # 如果LLM简化失败，返回默认友好消息
            if "成功" in technical_output or "完成" in technical_output:
                return "✅ 操作已成功完成！"
            else:
                return "操作已完成"

    def get_available_tools(self) -> List[str]:
        return [tool.name for tool in self.tools]

    def reload_tools(self):
        logger.info("重新加载MCP工具...")
        self._load_mcp_tools()


if __name__ == "__main__":
    # 这里可以添加直接测试Agent的代码
    agent = AssetManageAgent()
    print("AssetManageAgent初始化完成，可用工具:", agent.get_available_tools())
 