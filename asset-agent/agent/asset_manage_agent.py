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
            2、给张三分配一个包含计价产品的资产    
                第一步：查询用户名为张三的授权成员，使用工具query_enterprise_members_mcp
                第二步：查询有效且未分配并且包含计价产品的资产，使用工具query_assets_by_status_mcp
                第三步：给张三分配资产，使用工具allocate_asset_privileges_mcp

            自然语言理解指南:
            - "创建账号XXX" → userName="XXX", name="XXX"
            - "密码为XXX" → password="XXX"
            - "密保手机为XXX" → passwordMobile="XXX"
            - "查询未分配资产" → assetStatus=["UNASSIGNED", "VALID"]
            
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
            - 每个步骤都要检查结果是否成功
            - 从用户自然语言中智能提取参数信息
            - mcp工具调用时参数类型、参数个数严格按照接口描述进行传递
            - 新成员的 globalId 不为 memberId
            - 禁止调用: 如果用户输入中包含"系统提供的认证信息"，说明已有token，严禁调用generate_client_token_mcp和generate_user_token_mcp
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
        
        # 检查必需参数
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
        
        # 智能参数补全
        self._auto_complete_parameters(tool_name, args, properties)
        
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
        """从工具描述生成参数描述"""
        try:
            description = tool.get("description", "")
            if not description:
                return None
            
            # 解析工具描述中的参数信息
            import re
            
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
                # 解析参数类型
                type_mapping = {
                    'str': 'string',
                    'int': 'integer', 
                    'float': 'number',
                    'bool': 'boolean',
                    'list': 'array',
                    'dict': 'object'
                }
                
                # 提取基础类型
                base_type = param_type.split(',')[0].strip()
                if 'optional' in param_type.lower():
                    is_optional = True
                else:
                    is_optional = False
                    required.append(param_name)
                
                # 转换类型
                json_type = type_mapping.get(base_type, 'string')
                
                param_info = {
                    "type": json_type,
                    "description": param_desc.strip()
                }
                
                # 添加默认值（如果有）
                default_match = re.search(r'默认为(\d+|"[^"]*")', param_desc)
                if default_match:
                    default_val = default_match.group(1)
                    if default_val.startswith('"'):
                        param_info["default"] = default_val.strip('"')
                    elif default_val.isdigit():
                        param_info["default"] = int(default_val)
                
                # 添加枚举值（如果有）
                enum_match = re.search(r'可选值[：:]([^。\n]+)', param_desc)
                if enum_match:
                    enum_text = enum_match.group(1)
                    # 提取枚举值
                    enum_values = re.findall(r'["\']([^"\']+)["\']|(\w+)', enum_text)
                    if enum_values:
                        param_info["enum"] = [val[0] or val[1] for val in enum_values if val[0] or val[1]]
                
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

    def _auto_complete_parameters(self, tool_name: str, args: Dict, properties: Dict) -> None:
        """智能参数补全"""
        
        # 基于工具描述进行参数补全
        for param_name, param_info in properties.items():
            if param_name not in args:
                # 获取参数的默认值
                default_value = param_info.get("default")
                if default_value is not None:
                    args[param_name] = default_value
                    logger.info(f"从工具描述自动补全 {param_name} 为默认值: {default_value}")
                    continue
                
                # 基于参数类型和名称进行智能补全
                param_type = param_info.get("type", "")
                
                # 智能补全常见参数
                if param_name == "grantType":
                    if tool_name == "generate_client_token_mcp":
                        args[param_name] = "client_credentials"
                        logger.info("自动补全 grantType 为 'client_credentials'")
                    elif tool_name == "generate_user_token_mcp":
                        args[param_name] = "uid"
                        logger.info("自动补全 grantType 为 'uid'")
                
                elif param_name == "pageNum" and param_type == "integer":
                    args[param_name] = 1
                    logger.debug("自动补全 pageNum 为 1")
                
                elif param_name == "pageSize" and param_type == "integer":
                    args[param_name] = 20
                    logger.debug("自动补全 pageSize 为 20")
                
                elif param_name == "keyword" and param_type == "string":
                    args[param_name] = ""
                    logger.debug("自动补全 keyword 为空字符串")
        
        # 特殊的智能推断逻辑
        if tool_name == "query_assets_by_status_mcp":
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
        
        # 为资产续费工具设置默认开始时间
        if tool_name == "renew_asset_product_mcp" and "limitStartTime" not in args:
            import time
            args["limitStartTime"] = int(time.time() * 1000)
            logger.info(f"自动补全 limitStartTime 为当前时间: {args['limitStartTime']}")
        
        logger.debug(f"参数补全完成，最终参数: {args}")

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
        """应用业务逻辑验证规则"""
        
        # 基于参数名称的业务验证
        if param_name == "userName" and isinstance(param_value, str):
            # 用户名验证规则
            if len(param_value) < 2 or len(param_value) > 30:
                return f"用户名长度必须在2-30个字符之间，当前长度: {len(param_value)}"
            if not param_value.replace('_', '').replace('-', '').isalnum():
                return f"用户名只能包含字母、数字、下划线和连字符: {param_value}"
        
        elif param_name == "password" and isinstance(param_value, str):
            # 密码复杂度验证
            if len(param_value) < 8 or len(param_value) > 16:
                return f"密码长度必须在8-16个字符之间，当前长度: {len(param_value)}"
            
            # 检查密码复杂度
            has_digit = any(c.isdigit() for c in param_value)
            has_alpha = any(c.isalpha() for c in param_value)
            has_symbol = any(not c.isalnum() for c in param_value)
            
            complexity_count = sum([has_digit, has_alpha, has_symbol])
            if complexity_count < 2:
                return "密码必须包含至少两种字符类型（数字、字母、符号）"
        
        elif param_name == "email" and isinstance(param_value, str):
            # 邮箱格式验证
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, param_value):
                return f"邮箱格式不正确: {param_value}"
        
        elif param_name == "phone" and isinstance(param_value, str):
            # 手机号格式验证
            import re
            phone_pattern = r'^1[3-9]\d{9}$'
            if not re.match(phone_pattern, param_value):
                return f"手机号格式不正确: {param_value}"
        
        elif param_name.endswith("Time") and isinstance(param_value, (int, float)):
            # 时间戳验证
            if param_value < 0:
                return f"时间戳不能为负数: {param_value}"
            # 检查是否为合理的时间戳范围（1970-2100年）
            if param_value < 0 or param_value > 4102444800000:  # 2100年的毫秒时间戳
                return f"时间戳超出合理范围: {param_value}"
        
        return None

    def _apply_cross_parameter_validation(self, tool_name: str, args: Dict, properties: Dict) -> Optional[str]:
        """应用跨参数验证规则"""
        
        # 时间范围验证
        if "limitStartTime" in args and "limitEndTime" in args:
            start_time = args["limitStartTime"]
            end_time = args["limitEndTime"]
            if isinstance(start_time, (int, float)) and isinstance(end_time, (int, float)):
                if start_time >= end_time:
                    return f"开始时间必须小于结束时间: {start_time} >= {end_time}"
        
        # 分页参数验证
        if "pageNum" in args and "pageSize" in args:
            page_num = args["pageNum"]
            page_size = args["pageSize"]
            if isinstance(page_num, int) and isinstance(page_size, int):
                if page_num < 1:
                    return f"页码必须大于0: {page_num}"
                if page_size < 1 or page_size > 1000:
                    return f"页面大小必须在1-1000之间: {page_size}"
        
        # 数组元素验证
        for param_name, param_value in args.items():
            if isinstance(param_value, list) and param_name in properties:
                param_info = properties[param_name]
                items_info = param_info.get("items", {})
                
                # 验证数组元素
                for i, item in enumerate(param_value):
                    if items_info.get("type") == "object":
                        # 验证对象数组的必需字段
                        required_fields = items_info.get("required", [])
                        if isinstance(item, dict):
                            for field in required_fields:
                                if field not in item:
                                    return f"{param_name}[{i}] 缺少必需字段: {field}"
                        else:
                            return f"{param_name}[{i}] 必须是对象类型"
        
        return None

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

    def get_available_tools(self) -> List[str]:
        return [tool.name for tool in self.tools]

    def reload_tools(self):
        logger.info("重新加载MCP工具...")
        self._load_mcp_tools()


if __name__ == "__main__":
    # 这里可以添加直接测试Agent的代码
    agent = AssetManageAgent()
    print("AssetManageAgent初始化完成，可用工具:", agent.get_available_tools())
 