# Asset Agent - 智能资产分配系统

基于LangGraph和MCP的企业资产管理智能Agent，能够实时获取MCP服务器工具并执行智能资产分配决策。

## 🚀 功能特性

- **智能分配决策**: 使用LLM分析用户需求，制定最优资产分配方案
- **实时工具获取**: 动态从MCP服务器获取可用工具，无需本地硬编码
- **工作流管理**: 基于LangGraph的状态机工作流，确保分配流程的可靠性
- **完整日志系统**: 统一的日志配置和管理，支持文件和控制台输出
- **模块化设计**: 清晰的包结构，便于维护和扩展

## 📁 项目结构

```
asset-agent/
├── __init__.py              # 主包入口文件
├── README.md               # 项目文档
├── agent/                  # Agent核心模块
│   ├── __init__.py         # Agent包初始化
│   └── asset_agent.py      # 主Agent实现
├── utils/                  # 工具模块
│   ├── __init__.py         # 工具包初始化（含日志配置）
│   └── mcp_client.py       # MCP客户端实现
├── examples/               # 示例代码
│   └── demo.py            # 演示脚本
├── config/                 # 配置文件目录
└── logs/                  # 日志文件目录
```

## 🛠️ 安装和配置

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖：
- `langchain>=0.1.0` - LangChain框架
- `langgraph>=0.3.25` - LangGraph工作流
- `langchain-mcp-adapters>=0.1.0` - MCP适配器
- `langchain-openai>=0.1.0` - OpenAI集成
- `fastmcp>=0.1.0` - FastMCP框架
- `python-dotenv>=1.0.0` - 环境变量管理

### 2. 配置环境变量

```bash
# 复制配置模板
cp config/env.example config/.env

# 编辑配置文件
nano config/.env  # 或使用其他编辑器
```

### 3. 验证配置

```bash
# 检查配置是否正确
python config/check_config.py
```

## 🔧 配置说明

### 环境变量配置

系统支持两种环境变量配置方式：

#### 方式1：使用.env文件（推荐）

1. 复制配置模板：
```bash
cp config/env.example config/.env
```

2. 编辑 `config/.env` 文件：
```bash
# OpenAI API配置
OPENAI_API_KEY=your-openai-api-key-here

# MCP服务器配置
MCP_SERVER_URL=http://192.168.0.239:8000/sse

# 日志配置
ASSET_AGENT_AUTO_LOG=true
LOG_LEVEL=INFO
```

#### 方式2：系统环境变量

```bash
# OpenAI API密钥
export OPENAI_API_KEY="your-openai-api-key"

# MCP服务器地址（可选，默认为http://192.168.0.239:8000/sse）
export MCP_SERVER_URL="http://192.168.0.239:8000/sse"

# 日志配置
export ASSET_AGENT_AUTO_LOG="true"
export LOG_LEVEL="INFO"
```

### MCP服务器配置

默认MCP服务器地址：`http://192.168.0.239:8000/sse`

可通过以下方式配置MCP服务器地址：

1. **环境变量方式（推荐）**：
```bash
export MCP_SERVER_URL="http://your-mcp-server:8000/sse"
```

2. **代码中指定**：
```python
from agent import RealTimeMCPAgent

agent = RealTimeMCPAgent("http://your-mcp-server:8000/sse")
```

## 📖 使用方法

### HTTP服务模式

启动HTTP服务：
```bash
# 方式1: 使用启动脚本（推荐）
python start_server.py

# 方式2: 直接运行Agent
python agent/asset_manage_agent.py

# 方式3: 使用环境变量配置
export AGENT_SERVER_HOST=0.0.0.0
export AGENT_SERVER_PORT=8001
python start_server.py
```

服务启动后，可以通过以下方式访问：

- **API文档**: http://localhost:8001/docs
- **健康检查**: http://localhost:8001/health
- **服务状态**: http://localhost:8001/status

#### API接口

1. **处理请求** - `POST /process`
```bash
curl -X POST "http://localhost:8001/process" \
     -H "Content-Type: application/json" \
     -d '{"message": "请为张三分配一个广联达云锁产品"}'
```

2. **获取工具列表** - `GET /tools`
```bash
curl "http://localhost:8001/tools"
```

3. **检查服务状态** - `GET /status`
```bash
curl "http://localhost:8001/status"
```

### Python代码调用

```python
from asset_agent import create_agent

# 创建Agent实例
agent = create_agent()

# 处理资产分配请求
result = agent.process_request("请为张三分配一个广联达云锁产品")

# 查看结果
if result["success"]:
    print(f"分配成功: {result['message']}")
    print(f"分配计划: {result['allocation_plan']}")
else:
    print(f"分配失败: {result['message']}")
```

### MCP客户端单独使用

```python
from asset_agent.utils import MCPClient

# 创建MCP客户端
client = MCPClient()

# 获取可用工具
tools_result = client.get_tools()
if tools_result["success"]:
    tools = tools_result["data"]
    for tool in tools:
        print(f"工具: {tool['name']} - {tool['description']}")

# 调用工具
result = client.call_tool("generate_client_token_mcp", {
    "grantType": "client_credentials"
})
```

### 自定义日志配置

```python
from asset_agent.utils import setup_logging

# 设置日志级别和输出文件
setup_logging(
    level="DEBUG",
    log_file="custom_log.log",
    include_timestamp=True
)
```

## 🎯 工作流程

Agent的资产分配工作流包含以下步骤：

1. **获取MCP工具** - 从MCP服务器获取可用工具列表
2. **身份认证** - 生成客户端和用户令牌
3. **请求分析** - 使用LLM分析用户需求
4. **查询资产** - 获取可用资产信息
5. **查询成员** - 获取企业成员信息
6. **制定计划** - 基于资产和成员信息制定分配计划
7. **执行分配** - 调用MCP工具执行资产分配
8. **验证结果** - 验证分配是否成功

## 🧪 运行演示

```bash
cd asset-agent
python examples/demo.py
```

演示程序将展示：
- 系统版本信息
- MCP客户端功能
- 日志系统功能
- Agent工作流演示

## 📊 日志系统

### 自动日志配置

系统会自动创建日志文件：`logs/asset_agent_YYYYMMDD.log`

### 日志级别

- `DEBUG` - 详细调试信息
- `INFO` - 一般信息（默认）
- `WARNING` - 警告信息
- `ERROR` - 错误信息
- `CRITICAL` - 严重错误

### 日志格式

```
2024-01-01 10:00:00,000 - asset_agent.utils.mcp_client - INFO - MCP客户端配置创建成功
```

## 🔍 故障排除

### 常见问题

1. **MCP服务器连接失败**
   ```
   错误: unhandled errors in a TaskGroup (1 sub-exception)
   ```
   - 检查MCP服务器是否运行
   - 验证服务器地址和端口
   - 确认网络连接

2. **工具获取失败**
   ```
   错误: 获取工具列表失败
   ```
   - 检查MCP服务器状态
   - 验证服务器API端点
   - 查看服务器日志

3. **OpenAI API调用失败**
   ```
   错误: Invalid API key
   ```
   - 检查OPENAI_API_KEY环境变量
   - 验证API密钥有效性
   - 确认网络访问权限

### 调试模式

启用详细日志输出：

```python
from asset_agent.utils import setup_logging
setup_logging(level="DEBUG")
```

## 🤝 贡献指南

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 创建Pull Request

## 📄 许可证

本项目采用MIT许可证 - 详见LICENSE文件

## 📞 支持

如有问题或建议，请：
1. 查看故障排除部分
2. 检查日志文件
3. 提交Issue到项目仓库

---

**Asset Agent Team** - 让资产管理更智能 🚀 