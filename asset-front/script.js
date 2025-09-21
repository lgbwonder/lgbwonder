// 配置信息
const CONFIG = {
    AGENT_API_BASE: 'http://localhost:8001',
    DEFAULT_USER_TOKEN: 'cn-8cb357d5-93f6-4a4f-80df-482271c87ee8',
    DEFAULT_CLIENT_TOKEN: 'cn-1e522f6f-ff6e-4384-be68-e35c302c786c',
    REQUEST_TIMEOUT: 5 * 60 * 1000 // 5分钟
};

// 全局状态
let thinkingModeEnabled = false;
let progressTimer = null;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
    setupEventListeners();
    updateTokenDisplay();
    checkAgentStatus();
});

// 初始化应用
function initializeApp() {
    console.log('智能资产管理助手已启动');
    
    // 设置输入框自动调整高度
    const messageInput = document.getElementById('messageInput');
    if (messageInput) {
        messageInput.addEventListener('input', autoResizeTextarea);
        messageInput.addEventListener('keydown', handleKeyDown);
    }
    
    // 设置字符计数
    updateCharCount();
}

// 设置事件监听器
function setupEventListeners() {
    const messageInput = document.getElementById('messageInput');
    if (messageInput) {
        messageInput.addEventListener('input', updateCharCount);
    }
}

// 自动调整文本框高度
function autoResizeTextarea() {
    const textarea = document.getElementById('messageInput');
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

// 处理键盘事件
function handleKeyDown(event) {
    if (event.ctrlKey && event.key === 'Enter') {
        event.preventDefault();
        sendMessage();
    }
}

// 更新字符计数
function updateCharCount() {
    const messageInput = document.getElementById('messageInput');
    const charCount = document.getElementById('charCount');
    if (messageInput && charCount) {
        charCount.textContent = messageInput.value.length;
        
        // 根据字符数量改变颜色
        if (messageInput.value.length > 800) {
            charCount.style.color = '#f56565';
        } else if (messageInput.value.length > 600) {
            charCount.style.color = '#ed8936';
        } else {
            charCount.style.color = 'rgba(255, 255, 255, 0.6)';
        }
    }
}

// 更新令牌显示
function updateTokenDisplay() {
    const userTokenDisplay = document.getElementById('userTokenDisplay');
    const clientTokenDisplay = document.getElementById('clientTokenDisplay');
    
    if (userTokenDisplay) {
        userTokenDisplay.textContent = maskToken(CONFIG.DEFAULT_USER_TOKEN);
    }
    if (clientTokenDisplay) {
        clientTokenDisplay.textContent = maskToken(CONFIG.DEFAULT_CLIENT_TOKEN);
    }
}

// 遮罩令牌显示
function maskToken(token) {
    if (!token || token.length < 10) return token;
    return token.substring(0, 8) + '...' + token.substring(token.length - 4);
}

// 检查Agent状态
async function checkAgentStatus() {
    try {
        const response = await fetch(`${CONFIG.AGENT_API_BASE}/status`);
        if (response.ok) {
            showToast('系统已连接', 'success');
        } else {
            showToast('系统连接异常', 'error');
        }
    } catch (error) {
        console.error('状态检查失败:', error);
        showToast('无法连接到服务器', 'error');
    }
}

// 切换思考模式
function toggleThinkingMode() {
    thinkingModeEnabled = !thinkingModeEnabled;
    const btn = document.getElementById('thinkingModeBtn');
    
    if (btn) {
        if (thinkingModeEnabled) {
            btn.classList.add('active');
            btn.innerHTML = '<i class="fas fa-brain"></i><span>思考模式 (开启)</span>';
            showToast('思考模式已开启，将显示详细处理过程', 'info');
        } else {
            btn.classList.remove('active');
            btn.innerHTML = '<i class="fas fa-brain"></i><span>思考模式</span>';
            showToast('思考模式已关闭', 'info');
        }
    }
}

// 切换侧边栏
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        sidebar.classList.toggle('open');
    }
}

// 快速操作
function quickAction(type) {
    const suggestions = {
        'query': '查询我的资产分配情况',
        'allocate': '为张三分配一个广联达云锁资产',
        'member': '添加一个新的企业成员'
    };
    
    if (suggestions[type]) {
        sendSuggestion(suggestions[type]);
    }
}

// 发送建议消息
function sendSuggestion(text) {
    const messageInput = document.getElementById('messageInput');
    if (messageInput) {
        messageInput.value = text;
        autoResizeTextarea();
        sendMessage();
    }
}

// 发送消息
async function sendMessage() {
    const messageInput = document.getElementById('messageInput');
    const message = messageInput.value.trim();
    
    if (!message) return;
    
    // 清除欢迎消息
    clearWelcomeMessage();
    
    // 添加用户消息到聊天区域
    addMessage('user', message);
    
    // 清空输入框
    messageInput.value = '';
    messageInput.style.height = 'auto';
    updateCharCount();
    
    // 禁用发送按钮
    const sendBtn = document.querySelector('.send-btn');
    sendBtn.disabled = true;
    sendBtn.innerHTML = '<div class="spinner"></div>';
    
    // 显示加载指示器
    showLoadingOverlay();
    
    // 创建AbortController用于超时控制
    const controller = new AbortController();
    
    try {
        // 设置超时定时器
        const timeoutId = setTimeout(() => controller.abort(), CONFIG.REQUEST_TIMEOUT);
        
        // 设置进度提示
        progressTimer = setTimeout(() => {
            showToast('处理中，请稍候...', 'info');
        }, 30000);
        
        setTimeout(() => {
            if (progressTimer) {
                showToast('正在深度分析，请耐心等待...', 'info');
            }
        }, 120000);
        
        // 构建完整消息（包含令牌）
        const fullMessage = `userToken:${CONFIG.DEFAULT_USER_TOKEN},clientToken:${CONFIG.DEFAULT_CLIENT_TOKEN},${message}`;
        
        // 根据思考模式选择不同的处理方式
        if (thinkingModeEnabled) {
            await handleStreamingRequest(fullMessage, controller);
        } else {
            await handleNormalRequest(fullMessage, controller);
        }
        
        // 清除超时定时器
        clearTimeout(timeoutId);
        
    } catch (error) {
        console.error('发送消息失败:', error);
        
        if (error.name === 'AbortError') {
            addMessage('assistant', '请求处理时间过长（超过5分钟），已自动取消。请尝试简化您的请求或稍后重试。');
            showToast('请求超时', 'error');
        } else {
            addMessage('assistant', '抱歉，处理您的请求时出现了问题。请稍后重试。');
            showToast('请求失败', 'error');
        }
    } finally {
        // 恢复发送按钮
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
        
        // 隐藏加载指示器
        hideLoadingOverlay();
        
        // 清除进度定时器
        if (progressTimer) {
            clearTimeout(progressTimer);
            progressTimer = null;
        }
    }
}

// 处理流式请求
async function handleStreamingRequest(fullMessage, controller) {
    try {
        const response = await fetch(`${CONFIG.AGENT_API_BASE}/process-stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: fullMessage
            }),
            signal: controller.signal
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        // 创建助手消息容器
        const assistantMessage = createStreamingMessage();
        
        // 处理流式响应
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        await handleStreamingData(data, assistantMessage);
                    } catch (e) {
                        console.warn('解析流式数据失败:', e);
                    }
                }
            }
        }
        
    } catch (error) {
        console.error('流式请求失败:', error);
        throw error;
    }
}

// 处理普通请求
async function handleNormalRequest(fullMessage, controller) {
    try {
        const response = await fetch(`${CONFIG.AGENT_API_BASE}/process`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: fullMessage
            }),
            signal: controller.signal
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.success) {
            addMessage('assistant', data.output || '处理完成');
        } else {
            addMessage('assistant', data.message || '处理失败，请重试');
        }
        
    } catch (error) {
        console.error('普通请求失败:', error);
        throw error;
    }
}

// 创建流式消息容器
function createStreamingMessage() {
    const chatMessages = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant streaming';
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-robot"></i>
        </div>
        <div class="message-content">
            <div class="message-text">
                <div class="streaming-status">
                    <i class="fas fa-cog fa-spin"></i>
                    <span>正在思考中...</span>
                </div>
                <div class="streaming-steps"></div>
                <div class="streaming-result" style="display: none;"></div>
            </div>
            <div class="message-time">${new Date().toLocaleTimeString()}</div>
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    scrollToBottom();
    
    return messageDiv;
}

// 处理流式数据
async function handleStreamingData(data, messageElement) {
    const streamingStatus = messageElement.querySelector('.streaming-status');
    const streamingSteps = messageElement.querySelector('.streaming-steps');
    const streamingResult = messageElement.querySelector('.streaming-result');
    
    if (data.type === 'step') {
        // 更新状态
        if (streamingStatus) {
            streamingStatus.innerHTML = `
                <i class="fas fa-cog fa-spin"></i>
                <span>${data.content || '处理中...'}</span>
            `;
        }
        
        // 添加步骤
        if (streamingSteps && data.step) {
            const stepElement = createStreamingStep(data.step);
            streamingSteps.appendChild(stepElement);
            scrollToBottom();
        }
        
    } else if (data.type === 'result') {
        // 隐藏状态指示器
        if (streamingStatus) {
            streamingStatus.style.display = 'none';
        }
        
        // 显示最终结果
        if (streamingResult) {
            streamingResult.style.display = 'block';
            streamingResult.innerHTML = `
                <div class="final-result">
                    <div class="result-header">
                        <i class="fas fa-check-circle"></i>
                        <span>处理完成</span>
                    </div>
                    <div class="result-content">${data.content || '操作已完成'}</div>
                </div>
            `;
        }
        
        scrollToBottom();
    }
}

// 创建流式步骤元素
function createStreamingStep(stepData) {
    const stepDiv = document.createElement('div');
    stepDiv.className = 'streaming-step';
    
    const resultClass = stepData.result_type === 'success' ? 'success' : 
                       stepData.result_type === 'error' ? 'error' : '';
    
    stepDiv.innerHTML = `
        <div class="step-number">${stepData.step || 1}</div>
        <div class="step-content">
            <div class="step-header">
                <div class="step-type">${stepData.type || 'thinking'}</div>
                <div class="step-progress">${stepData.progress || ''}</div>
            </div>
            <div class="step-text">${stepData.content || '处理中...'}</div>
            <div class="step-result ${resultClass}">${stepData.result || ''}</div>
        </div>
    `;
    
    return stepDiv;
}

// 清除欢迎消息
function clearWelcomeMessage() {
    const welcomeMessage = document.querySelector('.welcome-message');
    if (welcomeMessage) {
        welcomeMessage.style.display = 'none';
    }
}

// 添加消息到聊天区域
function addMessage(sender, content) {
    const chatMessages = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;
    
    const avatarIcon = sender === 'user' ? 'fas fa-user' : 'fas fa-robot';
    const time = new Date().toLocaleTimeString();
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <i class="${avatarIcon}"></i>
        </div>
        <div class="message-content">
            <div class="message-text">${content}</div>
            <div class="message-time">${time}</div>
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    scrollToBottom();
}

// 清空对话
function clearChat() {
    const chatMessages = document.getElementById('chatMessages');
    if (chatMessages) {
        // 清除所有消息，但保留欢迎消息
        const messages = chatMessages.querySelectorAll('.message');
        messages.forEach(message => message.remove());
        
        // 显示欢迎消息
        const welcomeMessage = chatMessages.querySelector('.welcome-message');
        if (welcomeMessage) {
            welcomeMessage.style.display = 'flex';
        }
    }
    
    showToast('对话已清空', 'info');
}

// 滚动到底部
function scrollToBottom() {
    const chatMessages = document.getElementById('chatMessages');
    if (chatMessages) {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

// 显示加载覆盖层
function showLoadingOverlay() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.classList.add('show');
    }
}

// 隐藏加载覆盖层
function hideLoadingOverlay() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.classList.remove('show');
    }
}

// 显示Toast通知
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    // 3秒后自动移除
    setTimeout(() => {
        if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
        }
    }, 3000);
}

// 工具函数：格式化时间
function formatTime(date) {
    return date.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

// 工具函数：防抖
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 响应式处理
function handleResize() {
    const sidebar = document.querySelector('.sidebar');
    const isMobile = window.innerWidth <= 768;
    
    if (sidebar && !isMobile) {
        sidebar.classList.remove('open');
    }
}

// 监听窗口大小变化
window.addEventListener('resize', debounce(handleResize, 250));

// 导出主要函数供HTML调用
window.sendMessage = sendMessage;
window.toggleThinkingMode = toggleThinkingMode;
window.toggleSidebar = toggleSidebar;
window.clearChat = clearChat;
window.quickAction = quickAction;
window.sendSuggestion = sendSuggestion; 