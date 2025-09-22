// 配置信息
const CONFIG = {
    AGENT_API_BASE: 'http://localhost:8001',
    DEFAULT_USER_TOKEN: 'cn-8cb357d5-93f6-4a4f-80df-482271c87ee8',
    DEFAULT_CLIENT_TOKEN: 'cn-1e522f6f-ff6e-4384-be68-e35c302c786c',
    REQUEST_TIMEOUT: 5 * 60 * 1000, // 5分钟
    TYPING_SPEED: 50, // 打字机效果速度（毫秒）
    THINKING_DELAY: 1000, // 思考延时（毫秒）
    STEP_DELAY: 800, // 步骤间延时（毫秒）
    ANIMATION_DURATION: 300 // 动画持续时间（毫秒）
};

// 全局状态
let thinkingModeEnabled = true; // 默认开启思考模式
let progressTimer = null;
let currentTypingAnimation = null;
let currentAbortController = null; // 用于终止当前请求
let isProcessing = false; // 是否正在处理请求

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
    
    // 事件监听器在setupEventListeners中统一设置
    
    // 设置字符计数
    updateCharCount();
    
    // 添加欢迎消息的入场动画
    setTimeout(() => {
        const welcomeMessage = document.querySelector('.welcome-message');
        if (welcomeMessage) {
            welcomeMessage.style.animation = 'fadeInUp 0.8s ease-out';
        }
    }, 300);
}

// 设置事件监听器
function setupEventListeners() {
    const messageInput = document.getElementById('messageInput');
    if (messageInput) {
        // 整合所有输入相关的事件监听器
        messageInput.addEventListener('input', function() {
            autoResizeTextarea();
            updateCharCount();
        });
        
        messageInput.addEventListener('keydown', handleKeyDown);
        
        messageInput.addEventListener('paste', function() {
            // 粘贴后需要延迟一下再调整高度，因为粘贴内容需要时间插入
            setTimeout(() => {
                autoResizeTextarea();
                updateCharCount();
            }, 10);
        });
        
        messageInput.addEventListener('cut', function() {
            // 剪切后也需要调整高度
            setTimeout(() => {
                autoResizeTextarea();
                updateCharCount();
            }, 10);
        });
    }

    // 全局键盘快捷键
    document.addEventListener('keydown', function(e) {
        // Ctrl+Shift+N 或 Cmd+Shift+N 开启新对话
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'N') {
            e.preventDefault();
            startNewChat();
        }
    });
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

// 掩码令牌显示
function maskToken(token) {
    if (!token || token.length < 8) return token;
    return token.substring(0, 8) + '...' + token.substring(token.length - 4);
}

// 切换侧边栏
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        sidebar.classList.toggle('collapsed');
    }
}

// 开启新对话
function startNewChat() {
    const newChatBtn = document.querySelector('.new-chat-btn');
    
    // 更新按钮状态
    if (newChatBtn) {
        newChatBtn.disabled = true;
        newChatBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>正在开启...</span>';
    }
    
    // 如果当前有正在进行的请求，先停止它
    if (isProcessing) {
        stopProcessing();
        // 等待一小段时间确保请求已停止
        setTimeout(() => {
            clearChatAndShowWelcome();
            resetNewChatButton();
        }, 300);
    } else {
        clearChatAndShowWelcome();
        resetNewChatButton();
    }
}

// 重置新对话按钮状态
function resetNewChatButton() {
    const newChatBtn = document.querySelector('.new-chat-btn');
    if (newChatBtn) {
        newChatBtn.disabled = false;
        newChatBtn.innerHTML = '<i class="fas fa-plus"></i><span>开启新对话</span>';
    }
}

// 清除聊天记录并显示欢迎消息
function clearChatAndShowWelcome() {
    // 清除聊天记录
    const chatMessages = document.getElementById('chatMessages');
    chatMessages.innerHTML = '';
    
    // 重新显示欢迎消息
    const welcomeMessage = document.createElement('div');
    welcomeMessage.className = 'welcome-message';
    welcomeMessage.innerHTML = `
        <div class="welcome-icon">
            <i class="fas fa-robot"></i>
        </div>
        <h2>你好！我是智能资产管理助手</h2>
        <p>我可以帮助您进行资产查询、权限分配、成员管理等操作</p>
    `;
    
    chatMessages.appendChild(welcomeMessage);
    
    // 清空输入框
    const messageInput = document.getElementById('messageInput');
    if (messageInput) {
        messageInput.value = '';
        messageInput.style.height = 'auto';
        updateCharCount();
    }
    
    // 滚动到顶部
    chatMessages.scrollTop = 0;
    
    // 显示成功提示
    showToast('新对话已开启', 'success');
}

// 检查Agent状态
async function checkAgentStatus() {
    try {
        const response = await fetch(`${CONFIG.AGENT_API_BASE}/status`);
        const data = await response.json();
        
        if (data.status === 'healthy') {
            console.log('Agent状态正常');
            showToast('系统已就绪', 'success');
        }
    } catch (error) {
        console.error('无法连接到Agent服务:', error);
        showToast('系统连接异常', 'error');
    }
}

// 切换侧边栏
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    sidebar.classList.toggle('collapsed');
}

// 清除聊天记录
function clearChat() {
    const chatMessages = document.getElementById('chatMessages');
    chatMessages.innerHTML = '';
    
    // 重新显示欢迎消息
    const welcomeMessage = document.createElement('div');
    welcomeMessage.className = 'welcome-message';
    welcomeMessage.innerHTML = `
        <div class="welcome-icon">
            <i class="fas fa-robot"></i>
        </div>
        <h2>你好！我是智能资产管理助手</h2>
        <p>我可以帮助您进行资产查询、权限分配、成员管理等操作</p>
        
        <div class="suggestions">
            <div class="suggestion-item" onclick="sendSuggestion('查询所有未分配的资产')">
                <i class="fas fa-search"></i>
                <span>查询未分配资产</span>
            </div>
            <div class="suggestion-item" onclick="sendSuggestion('分配资产权限给指定成员')">
                <i class="fas fa-key"></i>
                <span>分配资产权限</span>
            </div>
            <div class="suggestion-item" onclick="sendSuggestion('查询企业成员列表')">
                <i class="fas fa-users"></i>
                <span>查询成员列表</span>
            </div>
        </div>
    `;
    
    chatMessages.appendChild(welcomeMessage);
    
    showToast('聊天记录已清除', 'info');
}

// 发送建议消息
function sendSuggestion(suggestion) {
    const messageInput = document.getElementById('messageInput');
    messageInput.value = suggestion;
    sendMessage();
}

// 清除欢迎消息
function clearWelcomeMessage() {
    const welcomeMessage = document.querySelector('.welcome-message');
    if (welcomeMessage) {
        welcomeMessage.style.animation = 'fadeOut 0.3s ease-out';
        setTimeout(() => {
            welcomeMessage.remove();
        }, 300);
    }
}

// 终止处理
function stopProcessing() {
    if (currentAbortController) {
        currentAbortController.abort();
        currentAbortController = null;
    }
    
    // 清除定时器
    if (progressTimer) {
        clearTimeout(progressTimer);
        progressTimer = null;
    }
    
    // 清除打字机动画
    if (currentTypingAnimation) {
        clearInterval(currentTypingAnimation);
        currentTypingAnimation = null;
    }
    
    // 停止思考过程显示
    stopThinkingProcess();
    
    // 移除处理指示器
    const processingIndicator = document.querySelector('.message.processing');
    if (processingIndicator) {
        processingIndicator.remove();
    }
    
    // 重置状态
    isProcessing = false;
    updateButtonStates();
    
    // 显示终止消息
    addMessageWithAnimation('assistant', '处理已被用户终止。');
    
    showToast('处理已终止', 'info');
}

// 停止思考过程
function stopThinkingProcess() {
    // 找到所有思考容器并停止动画
    const thinkingContainers = document.querySelectorAll('.message.thinking-container');
    thinkingContainers.forEach(container => {
        // 更新思考标题和停止动画
        const thinkingDots = container.querySelector('.thinking-dots');
        if (thinkingDots) {
            thinkingDots.innerHTML = '<i class="fas fa-times" style="color: #ff6b6b; margin-right: 8px; font-size: 12px;"></i>已终止';
        }
    });
}

// 更新按钮状态
function updateButtonStates() {
    const sendBtn = document.getElementById('sendBtn');
    const stopBtn = document.getElementById('stopBtn');
    
    if (isProcessing) {
        sendBtn.style.display = 'none';
        stopBtn.style.display = 'flex';
    } else {
        sendBtn.style.display = 'flex';
        stopBtn.style.display = 'none';
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
    }
}

// 发送消息
async function sendMessage() {
    const messageInput = document.getElementById('messageInput');
    const message = messageInput.value.trim();
    
    if (!message || isProcessing) return;
    
    // 清除欢迎消息
    clearWelcomeMessage();
    
    // 添加用户消息到聊天区域（带动画）
    await addMessageWithAnimation('user', message);
    
    // 设置处理状态
    isProcessing = true;
    updateButtonStates();
    
    // 清空输入框
    messageInput.value = '';
    messageInput.style.height = 'auto';
    updateCharCount();
    
    // 创建AbortController用于超时控制
    currentAbortController = new AbortController();
    
    try {
        // 设置超时定时器
        const timeoutId = setTimeout(() => currentAbortController.abort(), CONFIG.REQUEST_TIMEOUT);
        
        // 构建完整消息（包含令牌）
        const fullMessage = `userToken:${CONFIG.DEFAULT_USER_TOKEN},clientToken:${CONFIG.DEFAULT_CLIENT_TOKEN},${message}`;
        
        // 使用分层交互处理请求
        await handleLayeredRequest(fullMessage, currentAbortController);
        
        // 清除超时定时器
        clearTimeout(timeoutId);
        
    } catch (error) {
        console.error('发送消息失败:', error);
        
        if (error.name === 'AbortError') {
            // 如果是用户主动终止，不显示错误消息
            if (isProcessing) {
                await addMessageWithAnimation('assistant', '请求处理时间过长（超过5分钟），已自动取消。请尝试简化您的请求或稍后重试。');
                showToast('请求超时', 'error');
            }
        } else {
            await addMessageWithAnimation('assistant', '抱歉，处理您的请求时出现了问题。请稍后重试。');
            showToast('请求失败', 'error');
        }
    } finally {
        // 重置状态
        isProcessing = false;
        currentAbortController = null;
        updateButtonStates();
        
        // 清除进度定时器
        if (progressTimer) {
            clearTimeout(progressTimer);
            progressTimer = null;
        }
    }
}

// 分层交互处理请求
async function handleLayeredRequest(fullMessage, controller) {
    // 第一层：显示开始处理
    const processingMessage = await showProcessingIndicator('开始处理您的请求...');
    
    try {
        // 发送请求获取完整结果
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
        
        // 移除处理指示器
        if (processingMessage) {
            await fadeOutElement(processingMessage);
            processingMessage.remove();
        }
        
        // 第二层：创建思考过程容器
        const thinkingContainer = await createThinkingContainer();
        
        // 第三层：处理流式响应，逐步展示思考过程
        await processStreamingResponse(response, thinkingContainer);
        
    } catch (error) {
        // 移除处理指示器
        if (processingMessage) {
            await fadeOutElement(processingMessage);
            processingMessage.remove();
        }
        throw error;
    }
}

// 显示处理指示器
async function showProcessingIndicator(text) {
    const chatMessages = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant processing';
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-robot"></i>
        </div>
        <div class="message-content">
            <div class="message-text">
                <div class="processing-indicator">
                    <div class="processing-spinner">
                        <div class="spinner-ring"></div>
                    </div>
                    <span class="processing-text">${text}</span>
                </div>
            </div>
            <div class="message-time">${new Date().toLocaleTimeString()}</div>
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    
    // 添加入场动画
    messageDiv.style.opacity = '0';
    messageDiv.style.transform = 'translateY(20px)';
    
    await new Promise(resolve => {
        setTimeout(() => {
            messageDiv.style.transition = `all ${CONFIG.ANIMATION_DURATION}ms ease-out`;
            messageDiv.style.opacity = '1';
            messageDiv.style.transform = 'translateY(0)';
            resolve();
        }, 100);
    });
    
    scrollToBottom();
    return messageDiv;
}

// 创建思考过程容器
async function createThinkingContainer() {
    const chatMessages = document.getElementById('chatMessages');
    const containerDiv = document.createElement('div');
    containerDiv.className = 'message assistant thinking-container';
    
    containerDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-brain"></i>
        </div>
        <div class="message-content">
            <div class="message-text">
                <div class="thinking-header">
                    <span class="thinking-dots">思考中<span class="dots"></span></span>
                </div>
                <div class="thinking-steps"></div>
            </div>
            <div class="message-time">${new Date().toLocaleTimeString()}</div>
        </div>
    `;
    
    chatMessages.appendChild(containerDiv);
    
    // 添加入场动画
    containerDiv.style.opacity = '0';
    containerDiv.style.transform = 'translateY(20px)';
    
    await new Promise(resolve => {
        setTimeout(() => {
            containerDiv.style.transition = `all ${CONFIG.ANIMATION_DURATION}ms ease-out`;
            containerDiv.style.opacity = '1';
            containerDiv.style.transform = 'translateY(0)';
            resolve();
        }, 100);
    });
    
    scrollToBottom();
    return containerDiv;
}

// 处理流式响应
async function processStreamingResponse(response, thinkingContainer) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let finalResult = null;
    let stepCount = 0;
    
    try {
        while (true) {
            // 检查是否已被终止
            if (!isProcessing) {
                console.log('流式处理已被终止');
                break;
            }
            
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');
            
            for (const line of lines) {
                // 再次检查是否已被终止
                if (!isProcessing) {
                    break;
                }
                
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        console.log('收到流式数据:', data);
                        
                        if (data.type === 'start') {
                            console.log('开始处理:', data.message);
                        } else if (data.type === 'thinking_step') {
                            if (!isProcessing) break;
                            stepCount++;
                            const stepData = data.data || data.step || data;
                            await addThinkingStep(thinkingContainer, stepData, stepCount);
                            if (!isProcessing) break;
                            await new Promise(resolve => setTimeout(resolve, CONFIG.STEP_DELAY));
                        } else if (data.type === 'step') {
                            if (!isProcessing) break;
                            stepCount++;
                            await addThinkingStep(thinkingContainer, data.step, stepCount);
                            if (!isProcessing) break;
                            await new Promise(resolve => setTimeout(resolve, CONFIG.STEP_DELAY));
                        } else if (data.type === 'final_result') {
                            finalResult = {
                                type: 'result',
                                content: data.output || data.content || '处理完成',
                                success: true
                            };
                        } else if (data.type === 'result') {
                            finalResult = data;
                        } else if (data.type === 'error') {
                            finalResult = {
                                type: 'result',
                                content: data.message || '处理出现错误',
                                success: false
                            };
                        } else if (data.type === 'end') {
                            console.log('处理结束');
                        }
                    } catch (e) {
                        console.warn('解析流式数据失败:', e, '原始数据:', line);
                    }
                }
            }
        }
        
        // 完成思考过程
        if (isProcessing) {
            await completeThinkingProcess(thinkingContainer);
        }
        
        // 第四层：展示最终结果
        if (finalResult && isProcessing) {
            await new Promise(resolve => setTimeout(resolve, CONFIG.THINKING_DELAY));
            if (isProcessing) {
                await showFinalResult(finalResult);
            }
        }
        
    } catch (error) {
        console.error('处理流式响应失败:', error);
        throw error;
    }
}

// 添加思考步骤
async function addThinkingStep(container, step, stepNumber) {
    // 如果已被终止，不添加新的思考步骤
    if (!isProcessing) {
        return;
    }
    
    const stepsContainer = container.querySelector('.thinking-steps');
    const stepDiv = document.createElement('div');
    stepDiv.className = 'thinking-step';
    
    // 处理不同格式的步骤数据
    let content = step.content || '处理中...';
    let result = step.result || '完成';
    let resultType = step.result_type || step.resultType || 'success';
    let progress = step.progress || '';
    
    console.log('添加思考步骤:', { stepNumber, content, result, resultType, progress });
    
    // 确定步骤状态和图标
    const statusIcon = resultType === 'success' ? 'fas fa-check-circle' : 
                      resultType === 'error' ? 'fas fa-times-circle' : 
                      resultType === 'warning' ? 'fas fa-exclamation-triangle' :
                      'fas fa-info-circle';
    
    const statusClass = resultType === 'success' ? 'success' : 
                       resultType === 'error' ? 'error' : 
                       resultType === 'warning' ? 'warning' :
                       'info';
    
    stepDiv.innerHTML = `
        <div class="step-number">${stepNumber}</div>
        <div class="step-content">
            <div class="step-text">${content}</div>
            <div class="step-info">
                <i class="${statusIcon} step-icon ${statusClass}"></i>
                <span class="result-text">${result}</span>
                ${progress ? `<span class="step-progress">${progress}</span>` : ''}
            </div>
        </div>
    `;
    
    stepsContainer.appendChild(stepDiv);
    
    // 添加步骤动画
    stepDiv.style.opacity = '0';
    stepDiv.style.transform = 'translateX(-20px)';
    
    await new Promise(resolve => {
        setTimeout(() => {
            stepDiv.style.transition = `all ${CONFIG.ANIMATION_DURATION}ms ease-out`;
            stepDiv.style.opacity = '1';
            stepDiv.style.transform = 'translateX(0)';
            resolve();
        }, 100);
    });
    
    scrollToBottom();
}

// 完成思考过程
async function completeThinkingProcess(container) {
    const header = container.querySelector('.thinking-header');
    const thinkingDots = header.querySelector('.thinking-dots');
    
    if (thinkingDots) {
        // 停止点动画，显示完成状态
        thinkingDots.innerHTML = '<i class="fas fa-check" style="color: #00d26a; margin-right: 8px; font-size: 12px;"></i>分析完成';
    }
}

// 展示最终结果
async function showFinalResult(resultData) {
    const chatMessages = document.getElementById('chatMessages');
    const resultDiv = document.createElement('div');
    resultDiv.className = 'message assistant final-result';
    
    resultDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-robot"></i>
        </div>
        <div class="message-content">
            <div class="message-text">
                <div class="result-header">
                    <i class="fas fa-star"></i>
                    <span>处理结果</span>
                </div>
                <div class="result-content">
                    ${resultData.content || '处理完成'}
                </div>
            </div>
            <div class="message-time">${new Date().toLocaleTimeString()}</div>
        </div>
    `;
    
    chatMessages.appendChild(resultDiv);
    
    // 添加入场动画
    resultDiv.style.opacity = '0';
    resultDiv.style.transform = 'translateY(20px)';
    
    await new Promise(resolve => {
        setTimeout(() => {
            resultDiv.style.transition = `all ${CONFIG.ANIMATION_DURATION}ms ease-out`;
            resultDiv.style.opacity = '1';
            resultDiv.style.transform = 'translateY(0)';
            resolve();
        }, 100);
    });
    
    // 打字机效果显示结果内容
    const resultContent = resultDiv.querySelector('.result-content');
    const originalText = resultContent.textContent;
    resultContent.textContent = '';
    
    await typewriterEffect(resultContent, originalText);
    
    scrollToBottom();
}

// 打字机效果
async function typewriterEffect(element, text) {
    return new Promise(resolve => {
        let index = 0;
        const timer = setInterval(() => {
            if (index < text.length) {
                element.textContent += text.charAt(index);
                index++;
                scrollToBottom();
            } else {
                clearInterval(timer);
                resolve();
            }
        }, CONFIG.TYPING_SPEED);
        
        // 保存当前动画引用，以便可能的取消
        currentTypingAnimation = timer;
    });
}

// 添加消息（带动画）
async function addMessageWithAnimation(role, content) {
    const chatMessages = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    const avatar = role === 'user' ? 
        '<i class="fas fa-user"></i>' : 
        '<i class="fas fa-robot"></i>';
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            ${avatar}
        </div>
        <div class="message-content">
            <div class="message-text">${content}</div>
            <div class="message-time">${new Date().toLocaleTimeString()}</div>
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    
    // 添加入场动画
    messageDiv.style.opacity = '0';
    messageDiv.style.transform = 'translateY(20px)';
    
    await new Promise(resolve => {
        setTimeout(() => {
            messageDiv.style.transition = `all ${CONFIG.ANIMATION_DURATION}ms ease-out`;
            messageDiv.style.opacity = '1';
            messageDiv.style.transform = 'translateY(0)';
            resolve();
        }, 100);
    });
    
    scrollToBottom();
    return messageDiv;
}

// 淡出元素
async function fadeOutElement(element) {
    return new Promise(resolve => {
        element.style.transition = `all ${CONFIG.ANIMATION_DURATION}ms ease-out`;
        element.style.opacity = '0';
        element.style.transform = 'translateY(-10px)';
        setTimeout(resolve, CONFIG.ANIMATION_DURATION);
    });
}

// 滚动到底部
function scrollToBottom() {
    const chatMessages = document.getElementById('chatMessages');
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 显示提示消息
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) return;
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    const icon = type === 'success' ? 'fa-check-circle' :
                 type === 'error' ? 'fa-times-circle' :
                 type === 'warning' ? 'fa-exclamation-triangle' :
                 'fa-info-circle';
    
    toast.innerHTML = `
        <i class="fas ${icon}"></i>
        <span>${message}</span>
    `;
    
    toastContainer.appendChild(toast);
    
    // 显示动画
    setTimeout(() => {
        toast.classList.add('show');
    }, 100);
    
    // 自动隐藏
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
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
window.toggleSidebar = toggleSidebar;
window.clearChat = clearChat;
window.sendSuggestion = sendSuggestion;
window.startNewChat = startNewChat;
window.stopProcessing = stopProcessing; 