# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
MCP客户端工具类 - 支持MultiServerMCPClient

用于与MCP服务器通信，获取工具列表并调用工具。
"""

import os
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime

from langchain_mcp_adapters.client import MultiServerMCPClient

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)

class MCPClient:
    """MCP客户端类 - 支持MultiServerMCPClient"""
    
    def __init__(self, server_url: str = None):
        # 从环境变量获取MCP服务器地址，如果没有则使用默认值
        if server_url is None:
            server_url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
        
        self.server_url = server_url
        self._tools_cache = None
        self._cache_timestamp = None
        self._cache_ttl = 300  # 5分钟缓存
        
        # 初始化MCP客户端配置
        self.config = {
            "myglodon-asset-management": {
                "url": server_url,
                "transport": "streamable_http"
            }
        }
        logger.debug(f"MCP客户端配置创建: {server_url}")
    
    def _format_tool(self, tool) -> Optional[Dict[str, Any]]:
        """格式化工具信息，优先使用docstring解析参数"""
        try:
            if hasattr(tool, 'name') and hasattr(tool, 'description'):
                tool_name = tool.name
                tool_description = tool.description
                parameters = {}
                
                # 优先策略：从docstring解析参数（适用于FastMCP 2.0）
                if hasattr(tool, 'func') and hasattr(tool.func, '__doc__') and tool.func.__doc__:
                    # 使用docstring解析参数
                    doc_params = self._parse_docstring_parameters(tool.func.__doc__)
                    if doc_params and doc_params.get('properties'):
                        parameters = doc_params
                        logger.debug(f"工具 {tool_name} 使用docstring解析参数: {len(parameters.get('properties', {}))}")
                
                # 备用策略1：从函数签名生成参数结构
                if not parameters and hasattr(tool, 'func'):
                    sig_params = self._generate_parameters_from_signature(tool)
                    if sig_params and sig_params.get('properties'):
                        parameters = sig_params
                        logger.debug(f"工具 {tool_name} 使用函数签名生成参数: {len(parameters.get('properties', {}))}")
                
                # 备用策略2：从schema属性获取（但要过滤复杂schema）
                if not parameters:
                    schema_candidates = []
                    
                    # 检查各种可能的schema属性
                    if hasattr(tool, 'input_schema'):
                        schema_candidates.append(('input_schema', tool.input_schema))
                    if hasattr(tool, 'args_schema'):
                        schema_candidates.append(('args_schema', tool.args_schema))
                    if hasattr(tool, 'parameters'):
                        schema_candidates.append(('parameters', tool.parameters))
                    
                    for schema_name, schema in schema_candidates:
                        try:
                            if isinstance(schema, dict):
                                # 直接是字典，检查是否是简单的参数结构
                                if self._is_simple_parameters_schema(schema):
                                    parameters = schema
                                    logger.debug(f"工具 {tool_name} 使用 {schema_name} 直接获取参数")
                                    break
                            elif hasattr(schema, 'model_json_schema'):
                                schema_dict = schema.model_json_schema()
                                if self._is_simple_parameters_schema(schema_dict):
                                    parameters = schema_dict
                                    logger.debug(f"工具 {tool_name} 使用 {schema_name}.model_json_schema() 获取参数")
                                    break
                            elif hasattr(schema, 'schema'):
                                schema_dict = schema.schema()
                                if self._is_simple_parameters_schema(schema_dict):
                                    parameters = schema_dict
                                    logger.debug(f"工具 {tool_name} 使用 {schema_name}.schema() 获取参数")
                                    break
                        except Exception as schema_error:
                            logger.debug(f"解析 {schema_name} 失败: {schema_error}")
                            continue
                
                # 确保返回的参数结构是简洁的
                if parameters and not self._is_simple_parameters_schema(parameters):
                    logger.debug(f"工具 {tool_name} 的参数结构过于复杂，使用空参数")
                    parameters = {}
                
                return {
                    "name": tool_name,
                    "description": tool_description,
                    "parameters": parameters if parameters else {}
                }
            elif isinstance(tool, dict):
                # 处理字典格式的工具
                formatted = {
                    "name": tool.get("name", "unknown"),
                    "description": tool.get("description", "无描述"),
                    "parameters": tool.get("parameters", {})
                }
                # 确保参数结构简洁
                if formatted["parameters"] and not self._is_simple_parameters_schema(formatted["parameters"]):
                    formatted["parameters"] = {}
                return formatted
            else:
                # 未知格式的工具
                return {
                    "name": str(tool),
                    "description": "未知工具",
                    "parameters": {}
                }
        except Exception as e:
            logger.debug(f"格式化工具失败: {e}")
            return None
    
    def _is_simple_parameters_schema(self, schema: Dict[str, Any]) -> bool:
        """检查参数schema是否是简洁的结构（避免复杂的$defs等）"""
        try:
            if not isinstance(schema, dict):
                return False
            
            # 拒绝包含复杂schema定义的结构
            if '$defs' in schema or 'anyOf' in schema or '$ref' in schema:
                return False
            
            # 检查是否有基本的参数结构
            if 'type' not in schema:
                return False
                
            if schema.get('type') != 'object':
                return False
            
            # 检查properties是否存在且为字典
            properties = schema.get('properties', {})
            if not isinstance(properties, dict):
                return False
            
            # 检查每个属性是否是简单结构
            for prop_name, prop_info in properties.items():
                if not isinstance(prop_info, dict):
                    return False
                if '$ref' in prop_info or 'anyOf' in prop_info:
                    return False
            
            return True
            
        except Exception as e:
            logger.debug(f"检查schema结构失败: {e}")
            return False
    
    def _parse_docstring_parameters(self, docstring: str) -> Dict[str, Any]:
        """从docstring中解析参数信息，优先支持标准FastMCP 2.0格式（Google-style docstrings）"""
        try:
            import re
            
            # 优先匹配标准的Google-style Args格式
            args_pattern = r'Args:\s*\n(.*?)(?:\n\s*(?:Returns?|Example|Note|Raises):|$)'
            args_match = re.search(args_pattern, docstring, re.DOTALL | re.IGNORECASE)
            
            if not args_match:
                # 回退到旧格式支持
                args_pattern = r'参数说明[：:]\s*\n(.*?)(?:\n\s*(?:返回格式|Returns?|示例|Examples?):|$)'
                args_match = re.search(args_pattern, docstring, re.DOTALL | re.IGNORECASE)
            
            if not args_match:
                return {}
            
            args_text = args_match.group(1)
            parameters = {
                "type": "object",
                "properties": {},
                "required": []
            }
            
            # 标准Google-style格式: paramName (type, optional): description
            # 也支持: paramName (type): description
            param_pattern = r'^\s*(\w+)\s*\(([^)]+)\):\s*(.+?)(?=^\s*\w+\s*\([^)]+\):|^\s*$|$)'
            matches = list(re.finditer(param_pattern, args_text, re.MULTILINE | re.DOTALL))
            
            if matches:
                # 解析标准格式
                for match in matches:
                    param_name = match.group(1)
                    type_info = match.group(2).strip()
                    description = match.group(3).strip()
                    
                    # 清理描述文本，保留多行格式
                    description = re.sub(r'\n\s*-\s*', '\n- ', description)
                    description = re.sub(r'\n\s{2,}', ' ', description)
                    description = re.sub(r'\s+', ' ', description).strip()
                    
                    # 解析类型和可选性
                    is_required = True
                    param_type = "string"
                    default_value = None
                    
                    # 处理类型信息: "str", "str, optional", "list", "int, optional", etc.
                    type_parts = [part.strip() for part in type_info.split(',')]
                    
                    if type_parts:
                        param_type = type_parts[0].strip()
                        
                        # 检查是否是可选参数
                        if len(type_parts) > 1:
                            for part in type_parts[1:]:
                                if 'optional' in part.lower():
                                    is_required = False
                                # 查找默认值模式
                                default_match = re.search(r'默认.*?([^，,\s]+)', part)
                                if default_match:
                                    default_value = default_match.group(1)
                    
                    # 转换Python类型到JSON Schema类型
                    json_type = self._python_type_to_json(param_type)
                    
                    param_info = {
                        "type": json_type,
                        "description": description
                    }
                    
                    # 设置默认值
                    if default_value is not None:
                        try:
                            if json_type == "integer":
                                param_info["default"] = int(default_value)
                            elif json_type == "number":
                                param_info["default"] = float(default_value)
                            elif json_type == "boolean":
                                param_info["default"] = default_value.lower() in ['true', '1', 'yes']
                            else:
                                param_info["default"] = str(default_value).strip('"\'')
                        except:
                            param_info["default"] = str(default_value)
                    
                    # 从描述中提取更多信息
                    enum_values = self._extract_enum_values(description)
                    if enum_values:
                        param_info["enum"] = enum_values
                    
                    # 处理数组类型的items
                    if json_type == "array":
                        array_items = self._extract_array_items_schema(description)
                        if array_items:
                            param_info["items"] = array_items
                        elif '权限' in description and '列表' in description:
                            param_info["items"] = {
                                "type": "object",
                                "description": "资产权限对象"
                            }
                        elif 'assetPrivileges' in param_name:
                            # 特殊处理assetPrivileges参数
                            param_info["items"] = {
                                "type": "object",
                                "properties": {
                                    "assetNum": {"type": "string", "description": "资产编号"},
                                    "assetId": {"type": "string", "description": "资产ID"},
                                    "memberId": {"type": "string", "description": "成员ID"}
                                },
                                "required": ["assetNum", "assetId", "memberId"]
                            }
                    
                    parameters["properties"][param_name] = param_info
                    
                    if is_required:
                        parameters["required"].append(param_name)
            else:
                # 回退处理非标准格式（旧格式兼容）
                param_pattern_simple = r'^\s*(\w+):\s*(.+?)(?=^\s*\w+\s*:|^\s*$|$)'
                
                for match in re.finditer(param_pattern_simple, args_text, re.MULTILINE | re.DOTALL):
                    param_name = match.group(1)
                    param_desc = match.group(2).strip()
                    
                    # 清理描述文本
                    param_desc = re.sub(r'\n\s*-\s*', '\n- ', param_desc)
                    param_desc = re.sub(r'\n\s+', ' ', param_desc)
                    param_desc = re.sub(r'\s+', ' ', param_desc).strip()
                    
                    # 简单类型推断
                    json_type = "string"
                    is_required = True
                    
                    if '可选' in param_desc or 'optional' in param_desc.lower():
                        is_required = False
                    
                    if 'list' in param_desc.lower() or '列表' in param_desc or '数组' in param_desc:
                        json_type = "array"
                    elif '页码' in param_desc or '数量' in param_desc or '时间戳' in param_desc:
                        json_type = "integer"
                    
                    param_info = {
                        "type": json_type,
                        "description": param_desc
                    }
                    
                    enum_values = self._extract_enum_values(param_desc)
                    if enum_values:
                        param_info["enum"] = enum_values
                    
                    parameters["properties"][param_name] = param_info
                    
                    if is_required:
                        parameters["required"].append(param_name)
            
            return parameters
            
        except Exception as e:
            logger.debug(f"解析docstring失败: {e}")
            return {}
    
    def _extract_enum_values(self, description: str) -> List[str]:
        """从描述中提取枚举值，支持标准格式和中文格式"""
        try:
            import re
            
            # 多种枚举值匹配模式
            enum_patterns = [
                r'可选值[：:]\s*\[([^\]]+)\]',                    # 可选值：["A", "B", "C"]
                r'可选值[：:]\s*([^，。\n\r]+)',                 # 可选值：A, B, C
                r'values?[：:]\s*\[([^\]]+)\]',                 # values: ["A", "B"]
                r'可选值.*?["\'"]([^"\']+)["\'"].*?["\'"]([^"\']+)["\'"]',  # 描述中的引号值
                r'(?:包括|如|例如)[：:]?\s*["\'"]([^"\']+)["\'"](?:\s*[,，]\s*["\'"]([^"\']+)["\'"])*', # 如："value1", "value2"
            ]
            
            for pattern in enum_patterns:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    values_str = match.group(1) if match.group(1) else match.group(0)
                    
                    # 提取所有引号内的值和单词
                    values = re.findall(r'"([^"]+)"|\'([^\']+)\'|(\w+)', values_str)
                    enum_values = []
                    
                    for value_groups in values:
                        for value in value_groups:
                            if value and value not in ['或', 'or', 'and', '和']:
                                cleaned_value = value.strip().strip(',"\'')
                                if cleaned_value:
                                    enum_values.append(cleaned_value)
                    
                    # 去重并过滤掉太长的值（可能是描述文本）
                    unique_values = []
                    for val in enum_values:
                        if len(val) <= 30 and val not in unique_values:  # 枚举值通常不会太长
                            unique_values.append(val)
                    
                    if unique_values:
                        return unique_values
            
            # 特殊处理：从描述中查找常见的状态值模式
            status_patterns = [
                r'(?:状态|status).*?(?:包括|包含)[：:]?\s*(.+?)(?:\n|$)',
                r'\[([A-Z_,\s"\']+)\]',  # [VALID, EXPIRED, UNASSIGNED]
            ]
            
            for pattern in status_patterns:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    status_text = match.group(1)
                    # 提取大写状态值
                    status_values = re.findall(r'"([A-Z_]+)"|\'([A-Z_]+)\'|([A-Z_]+)', status_text)
                    enum_values = []
                    
                    for value_groups in status_values:
                        for value in value_groups:
                            if value and len(value) >= 3:  # 状态值通常至少3个字符
                                enum_values.append(value)
                    
                    if enum_values:
                        return list(set(enum_values))  # 去重
            
            return []
            
        except Exception as e:
            logger.debug(f"提取枚举值失败: {e}")
            return []
    
    def _extract_array_items_schema(self, description: str) -> Optional[Dict[str, Any]]:
        """从描述中提取数组项的schema"""
        try:
            import re
            
            # 查找数组项的详细描述
            if '每个元素为' in description or '包含以下字段' in description:
                # 这是一个复杂对象数组
                return {
                    "type": "object",
                    "description": "数组元素对象"
                }
            elif 'list' in description.lower() and 'string' in description.lower():
                return {"type": "string"}
            elif 'list' in description.lower() and 'int' in description.lower():
                return {"type": "integer"}
            
            return None
            
        except Exception as e:
            logger.debug(f"提取数组项schema失败: {e}")
            return None
    
    def _python_type_to_json(self, python_type: str) -> str:
        """将Python类型转换为JSON Schema类型"""
        type_mapping = {
            'str': 'string',
            'string': 'string',
            'int': 'integer',
            'integer': 'integer',
            'float': 'number',
            'number': 'number',
            'bool': 'boolean',
            'boolean': 'boolean',
            'list': 'array',
            'array': 'array',
            'dict': 'object',
            'object': 'object'
        }
        
        return type_mapping.get(python_type.lower(), 'string')
    
    def _generate_parameters_from_signature(self, tool) -> Dict[str, Any]:
        """从工具的函数签名生成基本参数结构"""
        try:
            import inspect
            
            # 尝试获取原始函数
            func = None
            if hasattr(tool, 'func'):
                func = tool.func
            elif hasattr(tool, '__call__'):
                func = tool
            
            if not func:
                return {}
            
            # 获取函数签名
            sig = inspect.signature(func)
            parameters = {
                "type": "object",
                "properties": {},
                "required": []
            }
            
            param_count = 0
            for param_name, param in sig.parameters.items():
                # 跳过self和cls参数
                if param_name in ['self', 'cls']:
                    continue
                
                param_count += 1
                
                # 从类型注解确定参数类型
                param_type = 'string'  # 默认类型
                if param.annotation != inspect.Parameter.empty:
                    annotation = param.annotation
                    
                    if annotation == str:
                        param_type = 'string'
                    elif annotation == int:
                        param_type = 'integer'
                    elif annotation == float:
                        param_type = 'number'
                    elif annotation == bool:
                        param_type = 'boolean'
                    elif annotation == list:
                        param_type = 'array'
                    elif annotation == dict:
                        param_type = 'object'
                    else:
                        # 处理类型字符串
                        type_str = str(annotation).lower()
                        if 'str' in type_str:
                            param_type = 'string'
                        elif 'int' in type_str:
                            param_type = 'integer'
                        elif 'float' in type_str:
                            param_type = 'number'
                        elif 'bool' in type_str:
                            param_type = 'boolean'
                        elif 'list' in type_str:
                            param_type = 'array'
                        elif 'dict' in type_str:
                            param_type = 'object'
                
                # 生成参数描述
                param_description = self._generate_param_description(param_name, param_type)
                
                param_info = {
                    "type": param_type,
                    "description": param_description
                }
                
                # 处理默认值
                if param.default != inspect.Parameter.empty:
                    param_info["default"] = param.default
                else:
                    # 必填参数
                    parameters["required"].append(param_name)
                
                # 为已知参数添加特殊信息
                self._enhance_param_info(param_name, param_info)
                
                parameters["properties"][param_name] = param_info
            
            # 只有在有实际参数时才返回参数结构
            if param_count == 0:
                return {}
            
            return parameters
            
        except Exception as e:
            logger.debug(f"从函数签名生成参数失败: {e}")
            return {}
    
    def _generate_param_description(self, param_name: str, param_type: str) -> str:
        """为参数生成合适的描述"""
        # 根据参数名称生成描述
        descriptions = {
            'userToken': '用户认证令牌',
            'clientToken': '客户端认证令牌',
            'assetId': '资产ID',
            'searchType': '搜索类型',
            'searchCondition': '搜索条件',
            'assetStatus': '资产状态列表',
            'pageNum': '页码',
            'pageSize': '每页大小',
            'assignType': '分配类型',
            'assetPrivileges': '资产权限列表',
            'userName': '用户名',
            'password': '密码',
            'name': '姓名',
            'uid': '用户ID',
            'customerId': '客户ID',
            'licenseId': '许可证ID',
            'limitEndTime': '结束时间戳（毫秒）',
            'limitStartTime': '开始时间戳（毫秒）',
            'keyword': '搜索关键词',
            'grantType': '授权类型',
            'departmentId': '部门ID',
            'remark': '备注信息',
            'passwordMobile': '安全手机号',
            'regionCode': '区域代码'
        }
        
        return descriptions.get(param_name, f"{param_name} ({param_type})")
    
    def _enhance_param_info(self, param_name: str, param_info: Dict[str, Any]) -> None:
        """为已知参数添加额外信息"""
        # 为特定参数添加枚举值或特殊属性
        if param_name == 'searchType':
            param_info["enum"] = ["productUri", "productName", "assetNum", "memberAccount"]
        elif param_name == 'assetStatus' and param_info["type"] == "array":
            param_info["items"] = {"type": "string"}
            param_info["enum"] = ["VALID", "EXPIRED", "UNASSIGNED", "ASSIGNED", "BORROWED", "ONLINED", "LOCKED"]
        elif param_name == 'assignType':
            param_info["enum"] = ["assign", "unassign"]
        elif param_name == 'assetPrivileges' and param_info["type"] == "array":
            param_info["items"] = {
                "type": "object",
                "properties": {
                    "assetNum": {"type": "string", "description": "资产编号"},
                    "assetId": {"type": "string", "description": "资产ID"},
                    "memberId": {"type": "string", "description": "成员ID"}
                },
                "required": ["assetNum", "assetId", "memberId"]
            }
    
    async def _async_get_tools(self):
        """异步获取工具列表"""
        try:
            # 创建客户端实例
            client = MultiServerMCPClient(self.config)
            tools = await client.get_tools()
            
            # 尝试关闭客户端
            if hasattr(client, 'close'):
                try:
                    await client.close()
                except:
                    pass
            
            return tools
        except Exception as e:
            logger.error(f"异步获取工具失败: {str(e)}")
            raise e
    
    async def _async_call_tool(self, tool_name: str, parameters: Dict[str, Any]):
        """异步调用工具"""
        try:
            # 创建客户端实例
            client = MultiServerMCPClient(self.config)
            tools = await client.get_tools()
            
            # 查找对应的工具
            target_tool = None
            for tool in tools:
                tool_name_attr = getattr(tool, 'name', None) or (tool.get('name') if isinstance(tool, dict) else str(tool))
                if tool_name_attr == tool_name:
                    target_tool = tool
                    break
            
            result = None
            if target_tool:
                # 尝试调用工具
                try:
                    if hasattr(target_tool, 'ainvoke'):
                        result = await target_tool.ainvoke(parameters)
                    elif hasattr(target_tool, 'invoke'):
                        result = target_tool.invoke(parameters)
                    elif hasattr(target_tool, 'arun'):
                        result = await target_tool.arun(parameters)
                    elif hasattr(target_tool, 'run'):
                        result = target_tool.run(parameters)
                    elif hasattr(target_tool, 'acall'):
                        result = await target_tool.acall(parameters)
                    elif hasattr(target_tool, 'call'):
                        result = target_tool.call(parameters)
                    else:
                        logger.warning(f"工具 {tool_name} 没有可调用的方法")
                        result = {
                            "error": f"工具 {tool_name} 没有可调用的方法",
                            "parameters": parameters
                        }
                except Exception as call_error:
                    logger.error(f"调用工具 {tool_name} 失败: {str(call_error)}")
                    result = {
                        "error": f"调用失败: {str(call_error)}",
                        "parameters": parameters
                    }
            
            # 尝试关闭客户端
            if hasattr(client, 'close'):
                try:
                    await client.close()
                except:
                    pass
            
            return result
            
        except Exception as e:
            logger.error(f"异步调用工具失败: {str(e)}")
            raise e
    
    def get_tools(self, force_refresh: bool = False) -> Dict[str, Any]:
        """获取MCP服务器可用工具列表"""
        try:
            # 检查缓存
            if not force_refresh and self._tools_cache and self._cache_timestamp:
                cache_age = datetime.now().timestamp() - self._cache_timestamp
                if cache_age < self._cache_ttl:
                    logger.debug("使用缓存的工具列表")
                    return {
                        "success": True,
                        "data": self._tools_cache
                    }
            
            logger.debug("获取MCP服务器工具列表...")
            
            # 检查是否已经在事件循环中
            try:
                loop = asyncio.get_running_loop()
                # 如果已经在事件循环中，创建任务
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self._async_get_tools())
                    tools = future.result(timeout=30)
            except RuntimeError:
                # 没有运行的事件循环，直接使用 asyncio.run
                tools = asyncio.run(self._async_get_tools())
            except Exception as e:
                logger.error(f"获取工具失败: {str(e)}")
                return {
                    "success": False,
                    "error": f"获取工具失败: {str(e)}",
                    "data": []
                }
            
            # 将工具转换为标准格式
            formatted_tools = []
            for tool in tools:
                try:
                    formatted_tool = self._format_tool(tool)
                    if formatted_tool:
                        formatted_tools.append(formatted_tool)
                except Exception as format_error:
                    logger.debug(f"格式化工具失败: {str(format_error)}")
                    continue
            
            self._tools_cache = formatted_tools
            self._cache_timestamp = datetime.now().timestamp()
            logger.debug(f"获取到 {len(formatted_tools)} 个工具")
            
            return {
                "success": True,
                "data": formatted_tools
            }
            
        except Exception as e:
            logger.error(f"获取工具列表失败: {str(e)}")
            return {
                "success": False,
                "error": f"获取工具列表失败: {str(e)}",
                "data": []
            }
    
    def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """调用MCP工具"""
        try:
            logger.debug(f"调用MCP工具: {tool_name}")
            
            try:
                # 检查是否已经在事件循环中
                try:
                    loop = asyncio.get_running_loop()
                    # 如果已经在事件循环中，创建任务
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, self._async_call_tool(tool_name, parameters))
                        result = future.result(timeout=30)
                except RuntimeError:
                    # 没有运行的事件循环，直接使用 asyncio.run
                    result = asyncio.run(self._async_call_tool(tool_name, parameters))
                
                if result is not None:
                    # 检查工具调用是否成功
                    if isinstance(result, dict) and "success" in result:
                        return result
                    elif isinstance(result, dict) and "error" in result:
                        return {
                            "success": False,
                            "error": result["error"]
                        }
                    else:
                        # 如果工具返回格式不同，包装成标准格式
                        return {
                            "success": True,
                            "data": result,
                            "message": "工具调用成功"
                        }
                else:
                    logger.warning(f"未找到工具 {tool_name}")
                    return {
                        "success": False,
                        "error": f"未找到工具 {tool_name}"
                    }
            except Exception as e:
                logger.error(f"MCP工具调用失败: {str(e)}")
                return {
                    "success": False,
                    "error": f"工具调用失败: {str(e)}"
                }
                
        except Exception as e:
            logger.error(f"调用工具异常: {str(e)}")
            return {
                "success": False,
                "error": f"调用工具失败: {str(e)}"
            }
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """获取特定工具的信息"""
        tools_result = self.get_tools()
        if not tools_result.get("success"):
            return None
        
        tools = tools_result.get("data", [])
        for tool in tools:
            if tool.get("name") == tool_name:
                return tool
        
        return None
    
    def list_available_tools(self) -> List[str]:
        """列出所有可用工具的名称"""
        tools_result = self.get_tools()
        if not tools_result.get("success"):
            return []
        
        tools = tools_result.get("data", [])
        return [tool.get("name") for tool in tools if tool.get("name")]
    
    async def async_get_tools(self, force_refresh: bool = False) -> Dict[str, Any]:
        """异步获取MCP服务器可用工具列表"""
        try:
            # 检查缓存
            if not force_refresh and self._tools_cache and self._cache_timestamp:
                cache_age = datetime.now().timestamp() - self._cache_timestamp
                if cache_age < self._cache_ttl:
                    logger.debug("使用缓存的工具列表")
                    return {
                        "success": True,
                        "data": self._tools_cache
                    }
            
            logger.debug("异步获取MCP服务器工具列表...")
            
            tools = await self._async_get_tools()
            
            # 将工具转换为标准格式
            formatted_tools = []
            for tool in tools:
                try:
                    formatted_tool = self._format_tool(tool)
                    if formatted_tool:
                        formatted_tools.append(formatted_tool)
                except Exception as format_error:
                    logger.debug(f"格式化工具失败: {str(format_error)}")
                    continue
            
            self._tools_cache = formatted_tools
            self._cache_timestamp = datetime.now().timestamp()
            logger.debug(f"获取到 {len(formatted_tools)} 个工具")
            
            return {
                "success": True,
                "data": formatted_tools
            }
            
        except Exception as e:
            logger.error(f"获取工具列表异常: {str(e)}")
            return {
                "success": False,
                "error": f"获取工具列表失败: {str(e)}",
                "data": []
            }
    
    async def async_call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """异步调用MCP工具"""
        try:
            logger.debug(f"异步调用MCP工具: {tool_name}")
            
            try:
                result = await self._async_call_tool(tool_name, parameters)
                
                if result is not None:
                    # 检查工具调用是否成功
                    if isinstance(result, dict) and "success" in result:
                        return result
                    elif isinstance(result, dict) and "error" in result:
                        return {
                            "success": False,
                            "error": result["error"]
                        }
                    else:
                        # 如果工具返回格式不同，包装成标准格式
                        return {
                            "success": True,
                            "data": result,
                            "message": "工具调用成功"
                        }
                else:
                    logger.warning(f"未找到工具 {tool_name}")
                    return {
                        "success": False,
                        "error": f"未找到工具 {tool_name}"
                    }
            except Exception as e:
                logger.error(f"MCP工具调用失败: {str(e)}")
                return {
                    "success": False,
                    "error": f"工具调用失败: {str(e)}"
                }
                
        except Exception as e:
            logger.error(f"调用工具异常: {str(e)}")
            return {
                "success": False,
                "error": f"调用工具失败: {str(e)}"
            }

def main():
    """测试MCP客户端"""
    # 导入日志配置
    try:
        from . import setup_logging
        setup_logging(level="INFO")
    except ImportError:
        # 如果作为独立脚本运行，使用基本日志配置
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )
    
    print("🔧 MCP客户端测试")
    print("=" * 40)
    
    # 显示使用的MCP服务器地址
    mcp_url = os.getenv("MCP_SERVER_URL", "未设置")
    print(f"MCP服务器: {mcp_url}")
    
    client = MCPClient()
    
    # 测试获取工具列表
    print("\n1. 获取工具列表...")
    tools_result = client.get_tools()
    if tools_result.get("success"):
        tools = tools_result.get("data", [])
        print(f"   ✅ 找到 {len(tools)} 个工具")
        for i, tool in enumerate(tools[:3], 1):  # 只显示前3个
            print(f"   {i}. {tool.get('name')}")
        if len(tools) > 3:
            print(f"   ... 还有 {len(tools) - 3} 个工具")
    else:
        print(f"   ❌ 失败: {tools_result.get('error')}")
    
    # 测试调用工具
    print("\n2. 测试工具调用...")
    result = client.call_tool("generate_client_token_mcp", {"grantType": "client_credentials"})
    if result.get("success"):
        print("   ✅ 工具调用成功")
    else:
        print(f"   ❌ 调用失败: {result.get('error')}")
    
    print("\n" + "=" * 40)
    print("🎉 测试完成")

if __name__ == "__main__":
    main() 