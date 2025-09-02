# MyGlodon Asset Management MCP Server

这是一个基于Python的MCP（Model Context Protocol）服务器，使用FastMCP库构建，提供广联达（MyGlodon）资产管理功能的访问接口。

## 架构特性

### 技术栈
- **FastMCP**: 专为MCP协议优化的Python库，提供简洁的API
- **requests**: 同步HTTP客户端库，用于调用广联达API
- **标准MCP协议**: 完全兼容MCP协议规范

### 通信模式
- **HTTP API**: 通过FastMCP提供的HTTP端点
- **MCP协议**: 完整的MCP协议支持
- **自动工具注册**: FastMCP自动处理工具注册和路由

### 可用工具

该MCP服务器提供以下5个工具：

1. **query_assets_by_status_mcp** - 查询资产状态
   - 根据状态查询企业资产信息，支持分页
   - 支持多种搜索类型：产品URI、产品名称、资产编号、成员账号
   - 支持多种资产状态：有效、过期、未分配、已分配、已借出、在线、锁定

2. **allocate_asset_privileges_mcp** - 分配/取消分配资产权限
   - 为指定资产分配或取消分配权限给成员
   - 支持分配和取消分配两种操作
   - 返回详细的操作状态信息

3. **query_online_products_mcp** - 查询在线产品
   - 查询指定资产的在线云锁产品信息

4. **query_enterprise_members_mcp** - 查询企业成员
   - 获取企业下的成员列表

5. **query_asset_privilege_status_mcp** - 查询资产权限状态
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

服务器将以FastMCP模式启动，自动提供HTTP端点。

## 使用方法

### FastMCP模式

服务器以FastMCP模式运行，这是最简洁的MCP实现方式：

#### 1. 直接调用工具
```python
from asset_manage_mcp_server import query_assets_by_status_mcp

# 调用查询资产状态工具
result = query_assets_by_status_mcp(
    userToken="your_user_token",
    clientToken="your_client_token",
    searchType="assetNum",
    searchCondition="ABC123",
    assetStatus=["VALID", "ASSIGNED"]
)

print(result)
```

#### 2. HTTP API调用
```bash
# 查询可用工具
curl -X POST http://localhost:8000/tools/list

# 调用工具
curl -X POST http://localhost:8000/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "query_assets_by_status_mcp",
    "arguments": {
      "userToken": "your_user_token",
      "clientToken": "your_client_token",
      "searchType": "assetNum",
      "searchCondition": "ABC123",
      "assetStatus": ["VALID", "ASSIGNED"]
    }
  }'
```

#### 3. Python客户端示例
```python
import requests

# 查询工具列表
response = requests.post("http://localhost:8000/tools/list")
tools = response.json()

# 调用工具
response = requests.post("http://localhost:8000/tools/call", json={
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
```

### MCP客户端集成

#### Claude Desktop
1. 打开Claude Desktop设置
2. 在MCP部分添加新服务器
3. 选择"HTTP"连接方式
4. 设置URL为 `http://localhost:8000`
5. 重启Claude Desktop

#### 其他MCP客户端
- 使用HTTP连接方式
- 服务器地址：`http://localhost:8000`
- 支持标准MCP协议

## 配置说明

### 服务器配置
- **BASE_URL**: `https://me-test.glodon.com` (广联达API基础地址)
- **框架**: FastMCP
- **默认端口**: 8000 (FastMCP默认端口)
- **传输方式**: streamable-http

### 认证要求
所有查询接口都需要提供：
- `userToken`: 用户认证令牌
- `clientToken`: 客户端认证令牌

## 工具参数说明

### query_assets_by_status_mcp
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
- `assetStatus` (必需): 资产状态列表
  - 支持多个状态组合，如：`["VALID", "ASSIGNED"]`
  - 可选值：`["VALID", "EXPIRED", "UNASSIGNED", "ASSIGNED", "BORROWED", "ONLINED", "LOCKED"]`

### allocate_asset_privileges_mcp
- `userToken` (必需): 用户认证令牌
- `clientToken` (必需): 客户端认证令牌
- `assignType` (必需): 分配类型
  - `assign`: 分配权限
  - `unassign`: 取消分配权限
- `assetPrivileges` (必需): 资产权限列表
  - `assetNum`: 资产编号
  - `assetId`: 资产ID
  - `memberId`: 成员ID

### query_online_products_mcp
- `userToken` (必需): 用户认证令牌
- `clientToken` (必需): 客户端认证令牌
- `assetId` (必需): 资产ID

### query_enterprise_members_mcp
- `userToken` (必需): 用户认证令牌
- `clientToken` (必需): 客户端认证令牌

### query_asset_privilege_status_mcp
- `userToken` (必需): 用户认证令牌
- `clientToken` (必需): 客户端认证令牌
- `assetId` (必需): 资产ID

## 错误处理

服务器会返回标准化的响应格式，包含：
- 成功响应：包含工具执行结果和成功消息
- 错误响应：包含错误类型、错误信息和状态码
- 网络异常：网络请求异常、响应解析异常等

## 开发说明

### 代码结构
- 使用FastMCP装饰器声明MCP工具
- 同步HTTP客户端处理API调用
- 完整的错误处理和日志记录
- 标准化的返回格式

### 扩展新工具
1. 使用`@mcp.tool()`装饰器定义新工具
2. 实现对应的函数逻辑
3. 添加适当的错误处理
4. 工具会自动注册到MCP服务器

### 添加新的HTTP端点
FastMCP自动处理所有MCP相关的端点，无需手动添加。

## 故障排除

### 常见问题
1. **端口被占用**: FastMCP会自动选择可用端口
2. **依赖安装失败**: 确保Python版本兼容性
3. **认证失败**: 确认userToken和clientToken的有效性
4. **网络连接问题**: 检查BASE_URL是否可访问

### 调试技巧
1. **查看控制台输出**: 服务器启动时会显示所有可用工具
2. **检查日志**: 每个工具调用都有详细的日志输出
3. **测试工具**: 可以直接在Python中导入和测试工具函数

## 性能优化

### 同步处理
- 使用requests库进行同步HTTP请求
- 适合大多数企业应用场景
- 简单可靠的错误处理

### 超时设置
- 所有API调用都设置了30秒超时
- 避免长时间等待响应
- 提供更好的用户体验

## 许可证

本项目遵循相应的开源许可证。
