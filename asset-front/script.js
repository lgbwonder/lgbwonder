// 全局配置
const CONFIG = {
    AGENT_API_BASE: 'http://localhost:8001',
    RECONNECT_INTERVAL: 5000,
    MAX_RECONNECT_ATTEMPTS: 3,
    // 内置令牌
    DEFAULT_USER_TOKEN: 'cn-8cb357d5-93f6-4a4f-80df-482271c87ee8',
    DEFAULT_CLIENT_TOKEN: 'cn-1e522f6f-ff6e-4384-be68-e35c302c786c'
};

// 全局状态
let reconnectAttempts = 0;
let isConnected = false;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
    updateTokenDisplay();
});

// 初始化应用
async function initializeApp() {
    updateStatus('connecting', '连接中...');
    
    try {
        // 检查Agent状态
        await checkAgentStatus();
        
        // 移除工具加载功能
        
        updateStatus('connected', '已连接');
        isConnected = true;
        reconnectAttempts = 0;
        
    } catch (error) {
        console.error('初始化失败:', error);
        updateStatus('error', '连接失败');
        
        // 尝试重连
        if (reconnectAttempts < CONFIG.MAX_RECONNECT_ATTEMPTS) {
            setTimeout(() => {
                reconnectAttempts++;
                initializeApp();
            }, CONFIG.RECONNECT_INTERVAL);
        }
    }
    
    // 绑定事件监听器
    bindEventListeners();
}

// 绑定事件监听器
function bindEventListeners() {
    // 回车发送消息
    const messageInput = document.getElementById('messageInput');
    messageInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    // 令牌类型切换
    const tokenType = document.getElementById('tokenType');
    if (tokenType) {
        tokenType.addEventListener('change', function() {
            const uidGroup = document.getElementById('uidGroup');
            if (this.value === 'user') {
                uidGroup.style.display = 'block';
            } else {
                uidGroup.style.display = 'none';
            }
        });
    }
    
    // 点击模态框外部关闭
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('modal')) {
            closeModal(e.target.id);
        }
    });
}

// 更新连接状态
function updateStatus(status, text) {
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    
    statusDot.className = `status-dot ${status}`;
    statusText.textContent = text;
}

// 检查Agent状态
async function checkAgentStatus() {
    try {
        const response = await fetch(`${CONFIG.AGENT_API_BASE}/status`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        if (data.success) {
            console.log('Agent状态:', data.data);
            return true;
        } else {
            throw new Error('Agent响应异常');
        }
    } catch (error) {
        // 如果/status端点不可用，回退到/tools端点
        try {
            const fallbackResponse = await fetch(`${CONFIG.AGENT_API_BASE}/tools`);
            if (fallbackResponse.ok) {
                const fallbackData = await fallbackResponse.json();
                return fallbackData.success;
            }
        } catch (fallbackError) {
            console.error('状态检查失败:', error, fallbackError);
        }
        throw error;
    }
}

// 更新令牌显示
function updateTokenDisplay() {
    const tokenInfo = document.querySelector('.token-info span');
    if (tokenInfo) {
        // 显示令牌的前8位和后4位，中间用...代替
        const userToken = CONFIG.DEFAULT_USER_TOKEN;
        const clientToken = CONFIG.DEFAULT_CLIENT_TOKEN;
        const maskedUserToken = userToken.substring(0, 8) + '...' + userToken.substring(userToken.length - 4);
        const maskedClientToken = clientToken.substring(0, 8) + '...' + clientToken.substring(clientToken.length - 4);
        
        tokenInfo.innerHTML = `用户令牌: ${maskedUserToken}<br>客户令牌: ${maskedClientToken}`;
        tokenInfo.title = '令牌已自动配置，将在每次请求中使用';
    }
}

// 发送消息
async function sendMessage() {
    const messageInput = document.getElementById('messageInput');
    const message = messageInput.value.trim();
    
    if (!message) return;
    
    // 添加用户消息到聊天区域
    addMessage('user', message);
    
    // 清空输入框
    messageInput.value = '';
    
    // 禁用发送按钮
    const sendBtn = document.querySelector('.send-btn');
    sendBtn.disabled = true;
    sendBtn.innerHTML = '<div class="spinner"></div> 处理中...';
    
    // 显示打字动画
    showTypingIndicator();
    
    try {
        // 构建包含令牌信息的完整消息
        const fullMessage = `userToken:${CONFIG.DEFAULT_USER_TOKEN},clientToken:${CONFIG.DEFAULT_CLIENT_TOKEN}，${message}`;
        
        // 发送请求到Agent
        const response = await fetch(`${CONFIG.AGENT_API_BASE}/process`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: fullMessage
            })
        });
        
        const data = await response.json();
        
        // 移除打字动画
        hideTypingIndicator();
        
        if (data.success && data.data) {
            // 添加Assistant回复，包含思考步骤
            addMessageWithThinking('assistant', data.data.output || '处理完成', data.data.thinking_steps || []);
            
            // 移除操作记录功能
        } else {
            addMessage('assistant', '抱歉，处理您的请求时出现了问题。请稍后重试。');
        }
        
    } catch (error) {
        console.error('发送消息失败:', error);
        // 移除打字动画
        hideTypingIndicator();
        addMessage('assistant', '网络连接异常，请检查网络后重试。');
        showToast('网络连接异常', 'error');
    } finally {
        // 恢复发送按钮
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i> 发送';
    }
}

// 显示打字动画
function showTypingIndicator() {
    const chatMessages = document.getElementById('chatMessages');
    
    // 移除已存在的打字动画
    const existingTyping = chatMessages.querySelector('.typing-indicator');
    if (existingTyping) {
        existingTyping.remove();
    }
    
    const typingDiv = document.createElement('div');
    typingDiv.className = 'typing-indicator';
    typingDiv.id = 'typingIndicator';
    
    typingDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-robot"></i>
        </div>
        <div class="typing-content">
            <span class="typing-text">正在思考</span>
            <div class="typing-dots">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        </div>
    `;
    
    chatMessages.appendChild(typingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 隐藏打字动画
function hideTypingIndicator() {
    const typingIndicator = document.getElementById('typingIndicator');
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

// 添加消息到聊天区域
function addMessage(type, content) {
    const chatMessages = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    
    const now = new Date();
    const timeStr = now.toLocaleTimeString('zh-CN', { 
        hour: '2-digit', 
        minute: '2-digit' 
    });
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-${type === 'user' ? 'user' : 'robot'}"></i>
        </div>
        <div class="message-content">
            <div class="message-text">${formatMessage(content)}</div>
            <div class="message-time">${timeStr}</div>
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 添加带思考步骤的消息
function addMessageWithThinking(type, content, thinkingSteps) {
    const chatMessages = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    
    const now = new Date();
    const timeStr = now.toLocaleTimeString('zh-CN', { 
        hour: '2-digit', 
        minute: '2-digit' 
    });
    
    const thinkingStepsHtml = thinkingSteps && thinkingSteps.length > 0 
        ? generateThinkingStepsHtml(thinkingSteps) 
        : '';
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-${type === 'user' ? 'user' : 'robot'}"></i>
        </div>
        <div class="message-content">
            <div class="message-text">
                ${formatMessage(content)}
                ${thinkingStepsHtml}
            </div>
            <div class="message-time">${timeStr}</div>
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    
    // 绑定思考步骤切换事件
    const toggleBtn = messageDiv.querySelector('.thinking-toggle');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', function() {
            const stepsContainer = messageDiv.querySelector('.thinking-steps');
            const isCollapsed = stepsContainer.classList.contains('collapsed');
            
            if (isCollapsed) {
                stepsContainer.classList.remove('collapsed');
                toggleBtn.classList.remove('collapsed');
                toggleBtn.innerHTML = '<i class="fas fa-chevron-down toggle-icon"></i> 隐藏思考过程';
            } else {
                stepsContainer.classList.add('collapsed');
                toggleBtn.classList.add('collapsed');
                toggleBtn.innerHTML = '<i class="fas fa-chevron-right toggle-icon"></i> 查看思考过程';
            }
        });
    }
    
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 生成思考步骤HTML
function generateThinkingStepsHtml(steps) {
    if (!steps || steps.length === 0) return '';
    
    const stepsHtml = steps.map(step => {
        const icon = getStepIcon(step.type);
        const title = getStepTitle(step.type);
        const timestamp = new Date(step.timestamp).toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
        
        let detailsHtml = '';
        if (step.tool_name) {
            detailsHtml = `
                <div class="step-details">
                    <strong>工具:</strong> ${step.tool_name}<br>
                    <strong>参数:</strong> ${JSON.stringify(step.tool_input, null, 2)}
                </div>
            `;
        }
        
        return `
            <div class="thinking-step ${step.type}">
                <div class="step-icon">
                    <i class="fas ${icon}"></i>
                </div>
                <div class="step-content">
                    <div class="step-title">${title}</div>
                    <div class="step-text">${formatMessage(step.content)}</div>
                    ${detailsHtml}
                    <div class="step-timestamp">${timestamp}</div>
                </div>
            </div>
        `;
    }).join('');
    
    return `
        <div class="thinking-toggle collapsed">
            <i class="fas fa-chevron-right toggle-icon"></i>
            查看思考过程 (${steps.length}步)
        </div>
        <div class="thinking-steps collapsed">
            ${stepsHtml}
        </div>
    `;
}

// 获取步骤图标
function getStepIcon(type) {
    switch (type) {
        case 'thinking': return 'fa-brain';
        case 'action': return 'fa-cog';
        case 'observation': return 'fa-eye';
        default: return 'fa-circle';
    }
}

// 获取步骤标题
function getStepTitle(type) {
    switch (type) {
        case 'thinking': return '思考';
        case 'action': return '执行';
        case 'observation': return '观察';
        default: return '步骤';
    }
}

// 格式化消息内容
function formatMessage(content) {
    // 处理换行
    content = content.replace(/\n/g, '<br>');
    
    // 处理JSON格式的内容
    try {
        const jsonMatch = content.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
            const jsonStr = jsonMatch[0];
            const jsonObj = JSON.parse(jsonStr);
            const formattedJson = JSON.stringify(jsonObj, null, 2);
            content = content.replace(jsonStr, `<pre><code>${formattedJson}</code></pre>`);
        }
    } catch (e) {
        // 不是JSON格式，保持原样
    }
    
    return content;
}

// 清空聊天记录
function clearChat() {
    const chatMessages = document.getElementById('chatMessages');
    chatMessages.innerHTML = `
        <div class="message assistant">
            <div class="message-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="message-content">
                <div class="message-text">
                    您好！我是智能资产管理助手。我可以帮您：<br>
                    • 查询和管理企业资产<br>
                    • 添加和管理企业成员<br>
                    • 分配资产权限<br>
                    • 生成访问令牌<br><br>
                    请告诉我您需要什么帮助？
                </div>
                <div class="message-time">刚刚</div>
            </div>
        </div>
    `;
}

// 移除操作记录功能

// 显示提示消息
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// 模态框相关函数
function showModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.classList.add('show');
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.classList.remove('show');
}

// 快速操作函数
function showTokenDialog() {
    showModal('tokenModal');
}

function showMemberDialog() {
    showModal('memberModal');
}

function showAssetDialog() {
    showModal('assetModal');
}

function showAllocationDialog() {
    showModal('allocationModal');
}

// 生成令牌
async function generateToken() {
    const tokenType = document.getElementById('tokenType').value;
    const userUid = document.getElementById('userUid').value;
    
    let message = '';
    if (tokenType === 'client') {
        message = '请生成客户端令牌';
    } else {
        if (!userUid.trim()) {
            showToast('请输入用户ID', 'error');
            return;
        }
        message = `请为用户ID ${userUid} 生成用户令牌`;
    }
    
    closeModal('tokenModal');
    
    // 添加到聊天并发送
    document.getElementById('messageInput').value = message;
    sendMessage();
}

// 添加成员
async function addMember() {
    const userToken = document.getElementById('memberUserToken').value;
    const userName = document.getElementById('memberUserName').value;
    const password = document.getElementById('memberPassword').value;
    const name = document.getElementById('memberName').value;
    const phone = document.getElementById('memberPhone').value;
    
    if (!userToken.trim() || !userName.trim() || !password.trim() || !name.trim()) {
        showToast('请填写所有必填字段', 'error');
        return;
    }
    
    let message = `请添加企业成员：用户名 ${userName}，姓名 ${name}，密码 ${password}`;
    if (phone.trim()) {
        message += `，密保手机 ${phone}`;
    }
    message += `。用户令牌：${userToken}`;
    
    closeModal('memberModal');
    
    // 添加到聊天并发送
    document.getElementById('messageInput').value = message;
    sendMessage();
}

// 查询资产
async function queryAssets() {
    const userToken = document.getElementById('assetUserToken').value;
    const clientToken = document.getElementById('assetClientToken').value;
    const searchType = document.getElementById('assetSearchType').value;
    const searchCondition = document.getElementById('assetSearchCondition').value;
    
    if (!userToken.trim() || !clientToken.trim()) {
        showToast('请填写用户令牌和客户端令牌', 'error');
        return;
    }
    
    // 获取选中的资产状态
    const statusCheckboxes = document.querySelectorAll('#assetModal input[type="checkbox"]:checked');
    const statuses = Array.from(statusCheckboxes).map(cb => cb.value);
    
    if (statuses.length === 0) {
        showToast('请至少选择一个资产状态', 'error');
        return;
    }
    
    let message = `请查询资产：搜索类型 ${searchType}`;
    if (searchCondition.trim()) {
        message += `，搜索条件 ${searchCondition}`;
    }
    message += `，资产状态 ${statuses.join('、')}。用户令牌：${userToken}，客户端令牌：${clientToken}`;
    
    closeModal('assetModal');
    
    // 添加到聊天并发送
    document.getElementById('messageInput').value = message;
    sendMessage();
}

// 分配资产
async function allocateAsset() {
    const userToken = document.getElementById('allocUserToken').value;
    const clientToken = document.getElementById('allocClientToken').value;
    const assetNum = document.getElementById('allocAssetNum').value;
    const assetId = document.getElementById('allocAssetId').value;
    const memberId = document.getElementById('allocMemberId').value;
    const assignType = document.getElementById('allocAssignType').value;
    
    if (!userToken.trim() || !clientToken.trim() || !assetNum.trim() || !assetId.trim() || !memberId.trim()) {
        showToast('请填写所有必填字段', 'error');
        return;
    }
    
    const action = assignType === 'assign' ? '分配' : '取消分配';
    const message = `请${action}资产权限：资产编号 ${assetNum}，资产ID ${assetId}，成员ID ${memberId}。用户令牌：${userToken}，客户端令牌：${clientToken}`;
    
    closeModal('allocationModal');
    
    // 添加到聊天并发送
    document.getElementById('messageInput').value = message;
    sendMessage();
}

// 工具函数：格式化时间
function formatTime(date) {
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

// 工具函数：复制到剪贴板
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('已复制到剪贴板', 'success');
    } catch (err) {
        console.error('复制失败:', err);
        showToast('复制失败', 'error');
    }
}

// 错误处理
window.addEventListener('error', function(e) {
    console.error('全局错误:', e.error);
    showToast('系统出现异常，请刷新页面重试', 'error');
});

// 网络状态监听
window.addEventListener('online', function() {
    if (!isConnected) {
        showToast('网络已恢复，正在重连...', 'success');
        initializeApp();
    }
});

window.addEventListener('offline', function() {
    updateStatus('error', '网络断开');
    isConnected = false;
    showToast('网络连接已断开', 'error');
}); 