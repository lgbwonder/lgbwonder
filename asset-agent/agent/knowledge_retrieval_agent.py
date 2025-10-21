"""
知识检索代理
用于调用广联达知识库API进行知识检索，并结合LLM进行智能回答
"""

import requests
import logging
from typing import Dict, Any, List, Optional
import json
from datetime import datetime

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CustomLLM:
    """自定义LLM类，用于调用广联达AI接口"""
    
    def __init__(self, api_url: str, api_key: str, model_name: str, temperature: float = 0.0, max_tokens: int = 4000):
        self.api_url = api_url
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        
    def invoke(self, prompt: str) -> str:
        """调用LLM生成回答"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens
            }
            
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            # 提取回答内容
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            else:
                return "抱歉，无法生成回答。"
                
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return f"LLM调用失败: {str(e)}"


class KnowledgeRetrievalAgent:
    """知识检索代理类"""
    
    def __init__(self, temperature: float = 0.0, max_tokens: int = 4000):
        """初始化知识检索代理"""
        # 知识库检索配置
        self.api_url = "https://copilot.glodon.com/api/cvforce/chat/v1/knowledge/retrieval"
        self.headers = {
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NTg2ODAwMTcsInJvIjoidXNlciIsInRlbiI6Inl3cHRicHRqY2Z3YiIsInVpZCI6IjEwMDE1MjEifQ.zmPgu4gDgkGvaK2-e5swfEkXdx9ICzTC-XY7V_0B92U",
            "Content-Type": "application/json",
        }
        self.default_knowledge_id = "9d91ce0f-bf09-434e-b29c-cb09f17ca533"
        
        # LLM配置
        self.llm = CustomLLM(
            api_url="https://copilot.glodon.com/api/cvforce/aishop/v1/chat/completions",
            api_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NTc4NDI3NTcsInJvIjoidXNlciIsInRlbiI6Inl3cHRicHRqY2Z3YiIsInVpZCI6IjEwMDE1MjEifQ.zx_ofGhbiS-2zYCCBg0y0MkSoLPsHOTijCpaeWMR-iQ",
            model_name="A26lwykwnz2pq",
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        logger.info("=== ReAPI 知识库工具配置 ===")
        logger.info("知识检索代理初始化完成")
        logger.info(f"LLM配置 - 模型: A26lwykwnz2pq, 温度: {temperature}, 最大令牌: {max_tokens}")

    def knowledge_retrieval(self, content: str, **kwargs) -> Dict[str, Any]:
        """
        调用广联达知识检索API，根据用户输入内容检索知识库
        
        Args:
            content (str): 用户输入的查询内容
            **kwargs: 其他可选参数
                - knowledges (List[str]): 知识库ID列表，默认使用内置知识库
                - top_k (int): 返回结果数量，默认3
                - score (float): 相似度阈值，默认0.3
                - rerank_mode (int): 重排模式，默认0
                - return_source_data (int): 是否返回源数据，默认0
                - mode (int): 检索模式，默认0
        
        Returns:
            Dict[str, Any]: API响应结果
        """
        logger.info("正在加载 ReAPI 知识库工具...")
        
        try:
            # 构建请求参数
            payload = {
                "knowledges": kwargs.get("knowledges", [self.default_knowledge_id]),
                "content": content,
                "top_k": kwargs.get("top_k", 3),
                "score": kwargs.get("score", 0.3),
                "rerank_mode": kwargs.get("rerank_mode", 0),
                "return_source_data": kwargs.get("return_source_data", 0),
                "mode": kwargs.get("mode", 0)
            }
            
            logger.info(f"发起知识检索请求，查询内容: {content}")
            logger.info(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")
            
            # 发送请求
            response = requests.post(
                self.api_url, 
                headers=self.headers, 
                json=payload,
                timeout=30
            )
            
            # 检查响应状态
            response.raise_for_status()
            
            result = response.json()
            
            # 根据实际返回格式处理数据
            if result.get('code') == 200 and result.get('data'):
                data_list = result.get('data', [])
                total_results = 0
                
                # 统计所有知识库的结果数量
                for knowledge_data in data_list:
                    if isinstance(knowledge_data, dict) and 'results' in knowledge_data:
                        total_results += len(knowledge_data.get('results', []))
                
                logger.info(f"知识检索成功，返回结果数量: {total_results}")
                return result
            else:
                error_msg = f"知识检索失败: {result.get('message', '未知错误')}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "data": []
                }
            
        except requests.exceptions.RequestException as e:
            error_msg = f"网络请求失败: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "data": []
            }
        except Exception as e:
            error_msg = f"ReAPI 知识库工具调用失败: {str(e)}"
            logger.error(error_msg)
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": error_msg,
                "data": []
            }

    def format_knowledge_results(self, raw_results: Dict[str, Any]) -> str:
        """
        格式化知识检索结果为用户友好的文本
        
        Args:
            raw_results: API原始返回结果
            
        Returns:
            str: 格式化后的文本结果
        """
        try:
            # 检查API调用是否成功
            if raw_results.get("code") != 200:
                return f"知识检索失败: {raw_results.get('message', '未知错误')}"
            
            # 解析新的数据格式
            data_list = raw_results.get("data", [])
            all_results = []
            
            # 从所有知识库中收集结果
            for knowledge_data in data_list:
                if isinstance(knowledge_data, dict) and 'results' in knowledge_data:
                    results = knowledge_data.get('results', [])
                    all_results.extend(results)
            
            if not all_results:
                return "抱歉，没有找到相关的知识内容。"
            
            formatted_text = "📚 **相关知识内容：**\n\n"
            
            for i, result in enumerate(all_results[:3], 1):  # 最多显示3个结果
                content = result.get("content", "").strip()
                score = result.get("score", 0)
                source = result.get("source", "")
                
                if content:
                    formatted_text += f"**{i}. 相关内容 (相似度: {score:.2f})**\n"
                    formatted_text += f"{content}\n"
                    if source:
                        formatted_text += f"*来源: {source}*\n"
                    formatted_text += "\n"
            
            return formatted_text.strip()
            
        except Exception as e:
            logger.error(f"格式化知识结果失败: {e}")
            return f"结果格式化失败: {str(e)}"

    def search_knowledge(self, query: str, format_result: bool = True) -> str:
        """
        搜索知识库并返回格式化结果
        
        Args:
            query (str): 搜索查询
            format_result (bool): 是否格式化结果
            
        Returns:
            str: 搜索结果文本
        """
        raw_results = self.knowledge_retrieval(query)
        
        if format_result:
            return self.format_knowledge_results(raw_results)
        else:
            return json.dumps(raw_results, ensure_ascii=False, indent=2)
    
    def intelligent_qa(self, question: str, use_knowledge: bool = True) -> str:
        """
        智能问答：结合知识库检索和LLM生成回答
        
        Args:
            question (str): 用户问题
            use_knowledge (bool): 是否使用知识库检索
            
        Returns:
            str: 智能回答
        """
        try:
            if use_knowledge:
                # 先检索相关知识
                knowledge_results = self.knowledge_retrieval(question)
                knowledge_content = ""
                
                # 检查知识检索是否成功（新格式）
                if knowledge_results.get("code") == 200:
                    data_list = knowledge_results.get("data", [])
                    all_results = []
                    
                    # 从所有知识库中收集结果
                    for knowledge_data in data_list:
                        if isinstance(knowledge_data, dict) and 'results' in knowledge_data:
                            results = knowledge_data.get('results', [])
                            all_results.extend(results)
                    
                    if all_results:
                        knowledge_content = "\n".join([
                            f"知识片段{i+1}: {result.get('text', '').strip()}"
                            for i, result in enumerate(all_results[:3])
                            if result.get('text', '').strip()
                        ])
                
                # 构建增强提示词
                if knowledge_content:
                    prompt = f"""作为一个专业的智能助手，请基于以下知识库内容回答用户问题。

知识库内容：
{knowledge_content}

用户问题：{question}

请根据知识库内容提供准确、详细的回答。如果知识库内容不足以完全回答问题，请明确说明，并基于你的专业知识提供补充信息。

回答要求：
1. 内容准确，逻辑清晰
2. 结构化组织，便于理解
3. 如果涉及具体操作或流程，请分步骤说明
4. 保持专业性和实用性"""
                else:
                    prompt = f"""作为一个专业的智能助手，请回答以下问题：

{question}

请提供准确、详细、有帮助的回答。"""
            else:
                # 直接使用LLM回答
                prompt = f"""作为一个专业的智能助手，请回答以下问题：

{question}

请提供准确、详细、有帮助的回答。"""
            
            # 调用LLM生成回答
            answer = self.llm.invoke(prompt)
            return answer
            
        except Exception as e:
            logger.error(f"智能问答失败: {e}")
            return f"抱歉，处理您的问题时出现错误：{str(e)}"
    
    def chat_with_knowledge(self, message: str) -> Dict[str, Any]:
        """
        带知识库的聊天接口
        
        Args:
            message (str): 用户消息
            
        Returns:
            Dict[str, Any]: 包含回答和相关信息的响应
        """
        try:
            # 检索相关知识
            knowledge_results = self.knowledge_retrieval(message)
            
            # 生成智能回答
            answer = self.intelligent_qa(message, use_knowledge=True)
            
            # 构建响应
            # 计算知识结果数量（新格式）
            knowledge_count = 0
            if knowledge_results.get("code") == 200:
                data_list = knowledge_results.get("data", [])
                for knowledge_data in data_list:
                    if isinstance(knowledge_data, dict) and 'results' in knowledge_data:
                        knowledge_count += len(knowledge_data.get('results', []))
            
            response = {
                "success": True,
                "answer": answer,
                "knowledge_used": knowledge_results.get("code") == 200,
                "knowledge_count": knowledge_count,
                "timestamp": datetime.now().isoformat()
            }
            
            return response
            
        except Exception as e:
            logger.error(f"聊天处理失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "answer": "抱歉，处理您的消息时出现了错误。"
            }


# 创建全局实例
knowledge_agent = KnowledgeRetrievalAgent()


def knowledge_retrieval(content: str) -> dict:
    """
    知识检索工具函数（兼容原有接口）
    
    Args:
        content (str): 用户输入内容
        
    Returns:
        dict: 检索结果
    """
    return knowledge_agent.knowledge_retrieval(content)


def search_knowledge_base(query: str) -> str:
    """
    搜索知识库工具函数
    
    Args:
        query (str): 搜索查询
        
    Returns:
        str: 格式化的搜索结果
    """
    return knowledge_agent.search_knowledge(query)


def intelligent_answer(question: str) -> str:
    """
    智能问答工具函数
    
    Args:
        question (str): 用户问题
        
    Returns:
        str: 智能回答
    """
    return knowledge_agent.intelligent_qa(question)


def chat_with_knowledge(message: str) -> dict:
    """
    带知识库的聊天工具函数
    
    Args:
        message (str): 用户消息
        
    Returns:
        dict: 聊天响应
    """
    return knowledge_agent.chat_with_knowledge(message)


if __name__ == "__main__":
    # 测试知识检索功能
    test_agent = KnowledgeRetrievalAgent()
    
    test_queries = [
        "什么是BIM？",
        "施工管理流程",
        "工程造价控制方法"
    ]
    
    for query in test_queries:
        print(f"\n{'='*50}")
        print(f"测试查询: {query}")
        print(f"{'='*50}")
        
        result = test_agent.search_knowledge(query)
        print(result)
