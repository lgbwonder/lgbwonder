# MyGlodon Asset Management MCP Server

这是一个基于Python的MCP（Model Context Protocol）服务器，使用FastAPI和FastMCP构建，提供广联达（MyGlodon）资产管理功能的访问接口。

## 架构特性

### 技术栈
- **FastAPI**: 现代、快速的Web框架，提供自动API文档
- **FastMCP**: 专为MCP协议优化的FastAPI集成库
- **Uvicorn**: 高性能ASGI服务器
- **aiohttp**: 异步HTTP客户端

### 通信模式
- **HTTP API**: 标准的RESTful API接口
- **MCP协议**: 通过FastMCP提供完整的MCP协议支持
- **自动文档**: 访问 `/docs` 查看交互式API文档
- **健康检查**: 访问 `/health` 检查服务状态

### 可用工具

该MCP服务器提供以下5个工具：

1. **query_assets_by_status** - 查询资产状态
   - 根据状态查询企业资产信息，支持分页
   - 支持多种搜索类型：产品URI、产品名称、资产编号、成员账号
   - 支持多种资产状态：有效、过期、未分配、已分配、已借出、在线、锁定

2. **allocate_asset_privileges** - 分配/取消分配资产权限
   - 为指定资产分配或取消分配权限给成员
   - 支持分配和取消分配两种操作
   - 返回详细的操作状态信息

3. **query_online_products** - 查询在线产品
   - 查询指定资产的在线云锁产品信息

4. **query_enterprise_members** - 查询企业成员
   - 获取企业下的成员列表

5. **query_asset_privilege_status** - 查询资产权限状态
   - 获取资产的权限分配状态信息

## 安装和运行

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 启动服务器
```bash
python asset_manage_mcp_server.py
```

服务器将在 `http://0.0.0.0:8080` 上启动，提供以下端点：

- **主页面**: `http://localhost:8080/`
- **MCP端点**: `http://localhost:8080/mcp`
- **API文档**: `http://localhost:8080/docs`
- **健康检查**: `http://localhost:8080/health`

## 使用方法

### HTTP API模式

#### 1. 直接HTTP调用
```bash
# 查询服务器信息
curl http://localhost:8080/

# 健康检查
curl http://localhost:8080/health

# 查询可用工具
curl -X POST http://localhost:8080/mcp/tools/list

# 调用工具
curl -X POST http://localhost:8080/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "query_assets_by_status",
    "arguments": {
      "userToken": "your_user_token",
      "clientToken": "your_client_token",
      "searchType": "assetNum",
      "searchCondition": "ABC123",
      "assetStatus": "VALID"
    }
  }'
```

#### 2. Python客户端示例
```python
import requests

# 查询服务器信息
response = requests.get("http://localhost:8080/")
server_info = response.json()
print(f"Server: {server_info['service']}")

# 查询工具列表
response = requests.post("http://localhost:8080/mcp/tools/list")
tools = response.json()

# 调用工具
response = requests.post("http://localhost:8080/mcp/tools/call", json={
    "name": "query_assets_by_status",
    "arguments": {
        "userToken": "your_user_token",
        "clientToken": "your_client_token",
        "searchType": "assetNum",
        "searchCondition": "ABC123",
        "assetStatus": "VALID"
    }
})
result = response.json()
```

#### 3. 使用FastAPI客户端
```python
from fastapi.testclient import TestClient
from asset_manage_mcp_server import app

client = TestClient(app)

# 查询工具列表
response = client.post("/mcp/tools/list")
tools = response.json()

# 调用工具
response = client.post("/mcp/tools/call", json={
    "name": "query_assets_by_status",
    "arguments": {
        "userToken": "your_user_token",
        "clientToken": "your_client_token",
        "searchType": "assetNum",
        "searchCondition": "ABC123",
        "assetStatus": "VALID"
    }
})
result = response.json()
```

### MCP客户端集成

#### Claude Desktop
1. 打开Claude Desktop设置
2. 在MCP部分添加新服务器
3. 选择"HTTP"连接方式
4. 设置URL为 `http://localhost:8080/mcp`
5. 重启Claude Desktop

#### 其他MCP客户端
- 使用HTTP连接方式
- 服务器地址：`http://localhost:8080/mcp`
- 支持标准MCP协议

### 开发调试

#### 1. 查看API文档
访问 `http://localhost:8080/docs` 查看交互式API文档，可以：
- 查看所有可用的端点
- 测试API调用
- 查看请求/响应模型

#### 2. 查看服务器状态
```bash
# 健康检查
curl http://localhost:8080/health

# 服务器信息
curl http://localhost:8080/
```

#### 3. 日志查看
服务器启动时会显示详细的连接信息，包括：
- 服务器启动状态
- 监听地址和端口
- 可用的端点

## 配置说明

### 服务器配置
- **HOST**: `0.0.0.0` (监听所有网络接口)
- **PORT**: `8080` (HTTP端口)
- **BASE_URL**: `https://me-test.glodon.com` (广联达API基础地址)
- **框架**: FastAPI + FastMCP
- **服务器**: Uvicorn ASGI服务器

### 认证要求
所有查询接口都需要提供：
- `userToken`: 用户认证令牌
- `clientToken`: 客户端认证令牌

## 工具参数说明

### query_assets_by_status
- `userToken` (必需): 用户认证令牌
- `clientToken` (必需): 客户端认证令牌
- `pageNum` (可选): 页码，默认1
- `pageSize` (可选): 每页大小，默认20
- `searchType` (必需): 搜索类型
  - `productUri`: 产品URI
  - `productName`: 产品名称
  - `assetNum`: 资产编号
  - `memberAccount`: 成员账号
- `searchCondition` (必需): 搜索条件
- `assetStatus` (必需): 资产状态
  - `VALID`: 有效
  - `EXPIRED`: 过期
  - `UNASSIGNED`: 未分配
  - `ASSIGNED`: 已分配
  - `BORROWED`: 已借出
  - `ONLINED`: 在线
  - `LOCKED`: 锁定

### allocate_asset_privileges
- `userToken` (必需): 用户认证令牌
- `clientToken` (必需): 客户端认证令牌
- `assignType` (必需): 分配类型
  - `assign`: 分配权限
  - `unassign`: 取消分配权限
- `assetPrivileges` (必需): 资产权限列表
  - `assetNum`: 资产编号
  - `assetId`: 资产ID
  - `memberId`: 成员ID

### query_online_products
- `userToken` (必需): 用户认证令牌
- `clientToken` (必需): 客户端认证令牌
- `assetId` (必需): 资产ID

### query_enterprise_members
- `userToken` (必需): 用户认证令牌
- `clientToken` (必需): 客户端认证令牌

### query_asset_privilege_status
- `userToken` (必需): 用户认证令牌
- `clientToken` (必需): 客户端认证令牌
- `assetId` (必需): 资产ID

## 错误处理

服务器会返回标准的HTTP状态码和MCP响应格式，包含：
- 成功响应：包含工具执行结果
- 错误响应：包含错误信息和描述
- 验证错误：自动参数验证和错误提示

## 开发说明

### 代码结构
- 使用FastAPI框架提供Web服务
- 使用FastMCP集成MCP协议
- 装饰器方式声明MCP工具
- 异步HTTP客户端处理API调用
- 完整的错误处理和日志记录

### 扩展新工具
1. 在工具列表中添加新的Tool定义
2. 实现对应的异步函数
3. 在call_tool函数中添加路由逻辑
4. 工具会自动出现在API文档中

### 添加新的HTTP端点
```python
@app.get("/custom")
async def custom_endpoint():
    return {"message": "Custom endpoint"}
```

## 故障排除

### 常见问题
1. **端口被占用**: 修改PORT常量或停止占用端口的进程
2. **网络访问限制**: 检查防火墙设置
3. **认证失败**: 确认userToken和clientToken的有效性
4. **依赖安装失败**: 确保Python版本兼容性

### 调试技巧
1. **查看API文档**: 访问 `/docs` 了解所有可用端点
2. **检查日志**: 服务器启动和运行时的详细日志
3. **健康检查**: 使用 `/health` 端点检查服务状态
4. **测试工具**: 使用API文档页面测试工具调用

## 性能优化

### 异步处理
- 所有工具函数都是异步的
- 使用aiohttp进行异步HTTP请求
- 支持并发处理多个请求

### 缓存策略
- 可以考虑添加Redis缓存
- 实现请求结果缓存
- 减少重复API调用

## 许可证

本项目遵循相应的开源许可证。
