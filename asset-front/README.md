# 智能资产管理系统前端

一个现代化的Web界面，用于与智能资产管理Agent进行交互。

## 功能特性

- 🤖 **智能对话**: 通过自然语言与资产管理Agent交互
- 💬 **实时聊天**: 类似聊天应用的对话界面
- 📱 **响应式设计**: 支持桌面和移动设备
- 🎨 **现代UI**: 采用毛玻璃效果和渐变设计
- ⚡ **快速响应**: 优化的用户体验

## 使用方法

### 1. 启动后端服务

首先确保资产管理Agent服务正在运行：

```bash
cd asset-agent
python agent/asset_manage_agent.py
```

默认运行在 `http://localhost:8001`

### 2. 打开前端页面

直接在浏览器中打开 `index.html` 文件，或者使用本地服务器：

```bash
# 使用Python内置服务器
cd asset-front
python -m http.server 8080

# 或使用Node.js服务器
npx http-server -p 8080
```

然后访问 `http://localhost:8080`

### 3. 开始使用

系统已内置访问令牌，您可以直接在对话框中输入需求，例如：

- "查询所有未分配的资产"
- "为用户张三分配一个广联达云锁资产"
- "添加一个新的企业成员"
- "查询资产产品详情"

**注意**: 系统会自动在每个请求前添加预配置的用户令牌和客户端令牌。

## 支持的操作

### 令牌管理
- 生成客户端令牌
- 生成用户令牌

### 成员管理
- 添加企业成员
- 查询企业成员

### 资产管理
- 查询资产状态
- 分配资产权限
- 取消资产分配
- 查询资产产品详情

### 其他功能
- 资产续费
- 自然语言理解
- 智能参数提取

## 技术栈

- **前端**: HTML5, CSS3, JavaScript (ES6+)
- **UI框架**: 原生CSS（毛玻璃效果、渐变）
- **图标**: Font Awesome 6.0
- **后端通信**: Fetch API
- **响应式**: CSS Grid & Flexbox

## 浏览器兼容性

- Chrome 60+
- Firefox 55+
- Safari 12+
- Edge 79+

## 配置

可以在 `script.js` 中修改配置：

```javascript
const CONFIG = {
    AGENT_API_BASE: 'http://localhost:8001',                      // Agent API地址
    RECONNECT_INTERVAL: 5000,                                     // 重连间隔
    MAX_RECONNECT_ATTEMPTS: 3,                                    // 最大重连次数
    DEFAULT_USER_TOKEN: 'cn-8cb357d5-93f6-4a4f-80df-482271c87ee8',   // 内置用户令牌
    DEFAULT_CLIENT_TOKEN: 'cn-1e522f6f-ff6e-4384-be68-e35c302c786c'  // 内置客户端令牌
};
```

**重要**: 如需更换令牌，请修改 `DEFAULT_USER_TOKEN` 和 `DEFAULT_CLIENT_TOKEN` 的值。

## 故障排除

### 连接失败
1. 确认Agent服务正在运行
2. 检查API地址配置是否正确
3. 查看浏览器控制台错误信息

### 跨域问题
如果遇到CORS错误，可以：
1. 使用本地服务器运行前端
2. 在Agent服务中添加CORS支持

### 样式问题
确保网络连接正常，Font Awesome图标需要从CDN加载。

## 开发

### 文件结构
```
asset-front/
├── index.html      # 主页面
├── styles.css      # 样式文件
├── script.js       # 交互逻辑
└── README.md       # 说明文档
```

### 自定义样式
主要的CSS变量和颜色定义在 `styles.css` 顶部，可以轻松自定义主题色彩。

### 添加新功能
在 `script.js` 中添加新的函数，并在HTML中绑定相应的事件处理器。 