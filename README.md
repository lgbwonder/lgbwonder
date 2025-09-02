# MyGlodon Asset Management MCP Server

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/Protocol-MCP-orange.svg)](https://modelcontextprotocol.io/)

一个基于Python的MCP（Model Context Protocol）服务器，使用FastMCP框架构建，提供广联达（MyGlodon）资产管理功能的访问接口。该服务器完全兼容MCP协议规范，支持多种MCP客户端集成。

## 🚀 特性

- **完全兼容MCP协议**: 支持所有标准MCP客户端
- **FastMCP框架**: 基于高性能的FastMCP库，自动处理工具注册和路由
- **企业级资产管理**: 提供完整的广联达资产管理功能
- **RESTful API**: 支持HTTP API调用，便于集成
- **完整的错误处理**: 标准化的错误响应和日志记录
- **异步支持**: 支持高并发请求处理

## 📋 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [API文档](#api文档)
- [配置说明](#配置说明)
- [使用示例](#使用示例)
- [故障排除](#故障排除)
- [开发指南](#开发指南)

## 🛠️ 安装

### 系统要求

- Python 3.8+
- Windows 10/11, macOS 10.14+, Ubuntu 18.04+
- 网络访问权限（用于调用广联达API）

### 1. 克隆项目

```bash
git clone <repository-url>
cd myglodon
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 环境配置

创建 `.env` 文件并配置以下环境变量：

```bash
# 服务器配置
SERVER_NAME=myglodon-asset-management
SERVER_HOST=127.0.0.1
SERVER_PORT=8000

# 广联达API配置
MYGLODON_URL=https://me-test.glodon.com

# 可选：日志级别
LOG_LEVEL=INFO
```

## 🚀 快速开始

### 启动服务器

```bash
python asset_manage_mcp_server.py
```

服务器启动后，您将看到类似输出：

```
Starting MyGlodon Asset Management MCP Server
Server is running in FastMCP mode
Available tools:
  - query_assets_by_status_mcp: 查询资产状态
  - allocate_asset_privileges_mcp: 分配/取消分配资产权限
  - query_online_products_mcp: 查询在线产品
  - query_enterprise_members_mcp: 查询企业成员
  - query_asset_privileges_status_mcp: 查询资产权限状态
```

### 测试连接

```bash
# 测试服务器是否正常运行
curl http://127.0.0.1:8000/health

# 查看可用工具列表
curl http://127.0.0.1:8000/tools/list
```

## 📚 API文档

### 核心工具

#### 1. 查询资产状态 (`query_assets_by_status_mcp`)

根据状态查询企业资产信息，支持分页和多种搜索条件。

**参数:**
- `userToken` (string, 必需): 用户认证令牌
- `clientToken` (string, 必需): 客户端认证令牌
- `searchType` (string, 必需): 搜索类型
  - `productUri`: 产品URI
  - `productName`: 产品名称
  - `assetNum`: 资产编号
  - `memberAccount`: 成员账号
- `searchCondition` (string, 必需): 搜索条件
- `assetStatus` (array, 必需): 资产状态列表
  - 支持值: `["VALID", "EXPIRED", "UNASSIGNED", "ASSIGNED", "BORROWED", "ONLINED", "LOCKED"]`
- `pageNum` (integer, 可选): 页码，默认1
- `pageSize` (integer, 可选): 每页大小，默认20

**示例:**
```python
result = query_assets_by_status_mcp(
    userToken="your_user_token",
    clientToken="your_client_token",
    searchType="assetNum",
    searchCondition="ABC123",
    assetStatus=["VALID", "ASSIGNED"],
    pageNum=1,
    pageSize=20
)
```

#### 2. 分配/取消分配资产权限 (`allocate_asset_privileges_mcp`)

为指定资产分配或取消分配权限给成员。

**参数:**
- `userToken` (string, 必需): 用户认证令牌
- `clientToken` (string, 必需): 客户端认证令牌
- `assignType` (string, 必需): 分配类型
  - `assign`: 分配权限
  - `unassign`: 取消分配权限
- `assetPrivileges` (array, 必需): 资产权限列表
  - 每个项目包含: `assetNum`, `assetId`, `memberId`

**示例:**
```python
result = allocate_asset_privileges_mcp(
    userToken="your_user_token",
    clientToken="your_client_token",
    assignType="assign",
    assetPrivileges=[
        {
            "assetNum": "ABC123",
            "assetId": "asset_001",
            "memberId": "member_001"
        }
    ]
)
```

#### 3. 查询在线产品 (`query_online_products_mcp`)

查询指定资产的在线云锁产品信息。

**参数:**
- `userToken` (string, 必需): 用户认证令牌
- `clientToken` (string, 必需): 客户端认证令牌
- `assetId` (string, 必需): 资产ID

#### 4. 查询企业成员 (`query_enterprise_members_mcp`)

获取企业下的成员列表。

**参数:**
- `userToken` (string, 必需): 用户认证令牌
- `clientToken` (string, 必需): 客户端认证令牌

#### 5. 查询资产权限状态 (`query_asset_privilege_status_mcp`)

获取资产的权限分配状态信息。

**参数:**
- `userToken` (string, 必需): 用户认证令牌
- `clientToken` (string, 必需): 客户端认证令牌
- `assetId` (string, 必需): 资产ID

## ⚙️ 配置说明

### 服务器配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `SERVER_NAME` | `myglodon-asset-management` | 服务器名称 |
| `SERVER_HOST` | `127.0.0.1` | 监听地址 |
| `SERVER_PORT` | `8000` | 监听端口 |
| `MYGLODON_URL` | `https://me-test.glodon.com` | 广联达API基础地址 |

### 环境变量

```bash
# Windows
set SERVER_HOST=0.0.0.0
set SERVER_PORT=9000

# Linux/macOS
export SERVER_HOST=0.0.0.0
export SERVER_PORT=9000
```

## 💻 使用示例

### Python客户端

```python
import requests

# 配置基础URL
BASE_URL = "http://127.0.0.1:8000"

# 查询可用工具
response = requests.get(f"{BASE_URL}/tools/list")
tools = response.json()
print("可用工具:", tools)

# 调用查询资产状态工具
response = requests.post(f"{BASE_URL}/tools/call", json={
    "name": "query_assets_by_status_mcp",
    "arguments": {
        "userToken": "your_user_token",
        "clientToken": "your_client_token",
        "searchType": "assetNum",
        "searchCondition": "ABC123",
        "assetStatus": ["VALID", "ASSIGNED"]
    }
})
result = response.json()
print("查询结果:", result)
```

### MCP客户端集成

#### Claude Desktop

1. 打开Claude Desktop设置
2. 在MCP部分添加新服务器
3. 选择"HTTP"连接方式
4. 设置URL为 `http://localhost:8000`
5. 重启Claude Desktop

#### Cursor

在 `~/.cursor/settings.json` 中添加：

```json
{
  "mcpServers": {
    "myglodon-asset-management": {
      "command": "http://127.0.0.1:8000",
      "transport": "streamable-http"
    }
  }
}
```

#### 其他MCP客户端

- 使用HTTP连接方式
- 服务器地址：`http://127.0.0.1:8000`
- 支持标准MCP协议

### cURL示例

```bash
# 查询工具列表
curl -X GET http://127.0.0.1:8000/tools/list

# 调用工具
curl -X POST http://127.0.0.1:8000/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "query_enterprise_members_mcp",
    "arguments": {
      "userToken": "your_user_token",
      "clientToken": "your_client_token"
    }
  }'
```

## 🔧 故障排除

### 常见问题

#### 1. 端口被占用

```bash
# 查看端口占用情况
netstat -ano | findstr :8000

# 使用其他端口
set SERVER_PORT=9000
python asset_manage_mcp_server.py
```

#### 2. 依赖安装失败

```bash
# 升级pip
python -m pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt --force-reinstall
```

#### 3. 认证失败

- 确认 `userToken` 和 `clientToken` 的有效性
- 检查网络连接是否正常
- 验证广联达API地址是否正确

#### 4. 网络连接问题

```bash
# 测试网络连接
ping me-test.glodon.com

# 检查防火墙设置
# Windows: 检查Windows Defender防火墙
# Linux: 检查iptables规则
```

### 调试技巧

1. **查看详细日志**: 设置 `LOG_LEVEL=DEBUG`
2. **测试网络连接**: 使用ping或telnet测试连接
3. **检查环境变量**: 确认所有必需的环境变量都已设置
4. **查看控制台输出**: 服务器启动时会显示详细的启动信息

## 🛠️ 开发指南

### 项目结构

```
myglodon/
├── asset_manage_mcp_server.py    # 主服务器文件
├── requirements.txt              # Python依赖
├── README.md                     # 项目文档
├── .env                         # 环境配置
└── logs/                        # 日志目录
```

### 添加新工具

1. 使用 `@mcp.tool()` 装饰器定义新工具
2. 实现对应的函数逻辑
3. 添加适当的错误处理
4. 工具会自动注册到MCP服务器

```python
@mcp.tool()
def new_tool_mcp(param1: str, param2: int) -> dict:
    """新工具的描述
    
    参数说明：
        param1: 参数1说明
        param2: 参数2说明
    
    返回格式：
        成功时返回API响应数据，失败时返回错误信息
    """
    try:
        # 实现工具逻辑
        result = do_something(param1, param2)
        return {
            "success": True,
            "data": result,
            "message": "操作成功"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "type": "unknown_error"
        }
```

### 代码规范

- 使用Python 3.8+语法
- 遵循PEP 8代码风格
- 添加完整的类型注解
- 包含详细的文档字符串
- 实现完整的错误处理

### 测试

```bash
# 运行单元测试
python -m pytest tests/

# 运行代码检查
flake8 asset_manage_mcp_server.py
black asset_manage_mcp_server.py
```

## 📊 性能优化

### 当前特性

- **同步处理**: 使用requests库进行同步HTTP请求
- **超时设置**: 所有API调用都设置了30秒超时
- **连接池**: 自动管理HTTP连接池
- **错误重试**: 内置错误重试机制

### 优化建议

1. **异步处理**: 对于高并发场景，考虑使用aiohttp
2. **缓存机制**: 添加Redis缓存减少API调用
3. **连接池优化**: 调整连接池大小和超时设置
4. **监控指标**: 添加性能监控和指标收集

## 🔒 安全考虑

- 所有API调用都通过HTTPS进行
- 支持Token认证机制
- 输入参数验证和清理
- 错误信息不暴露敏感数据

## 📄 许可证

本项目遵循MIT许可证。详见 [LICENSE](LICENSE) 文件。

## 🤝 贡献

欢迎提交Issue和Pull Request！

### 贡献指南

1. Fork项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开Pull Request

## 📞 支持

如果您遇到问题或有建议，请：

1. 查看 [Issues](../../issues) 页面
2. 创建新的Issue
3. 联系项目维护者

## 🔄 更新日志

### v1.0.0 (2024-01-01)
- 初始版本发布
- 支持5个核心资产管理工具
- 完整的MCP协议支持
- FastMCP框架集成

---

**注意**: 本项目仅供学习和研究使用，请遵守相关法律法规和广联达的使用条款。
