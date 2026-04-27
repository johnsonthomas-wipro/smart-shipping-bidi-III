/**
 * text-mode.js: Text chat mode functionality for SmartShip
 */

// Track current mode (voice or text)
let currentMode = null;
let textWebSocket = null;
let isTextConnected = false;
let currentResponseText = '';  // Accumulate streaming response
let lastAgentMessageBubble = null;  // Track last agent bubble for updates
let lastProcessedText = '';  // Track last text to avoid duplicates

// Get DOM elements
const modeSelectionOverlay = document.getElementById('modeSelectionOverlay');
const startVoiceBtn = document.getElementById('startVoiceBtn');
const startIvrBtn = document.getElementById('startIvrBtn');
const startTextBtn = document.getElementById('startTextBtn');
const switchModeBtn = document.getElementById('switchModeBtn');
const switchModeIcon = document.getElementById('switchModeIcon');
const switchModeText = document.getElementById('switchModeText');
const voiceSection = document.getElementById('voiceSection');
const textChatSection = document.getElementById('textChatSection');
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const chatSendBtn = document.getElementById('chatSendBtn');
const mainTitle = document.getElementById('mainTitle');
const card = document.querySelector('.card');
const featuresSection = document.getElementById('featuresSection');
const pauseBtn = document.getElementById('pauseBtn');

// Initialize mode selection
function initModeSelection() {
    if (modeSelectionOverlay) {
        modeSelectionOverlay.classList.remove('hidden');
    }
    
    if (startVoiceBtn) {
        startVoiceBtn.addEventListener('click', () => startVoiceMode());
    }
    
    if (startIvrBtn) {
        startIvrBtn.addEventListener('click', () => startIvrMode());
    }
    
    if (startTextBtn) {
        startTextBtn.addEventListener('click', () => startTextMode());
    }
    
    if (switchModeBtn) {
        switchModeBtn.addEventListener('click', () => toggleMode());
    }
}

// Start voice mode (with camera)
function startVoiceMode() {
    currentMode = 'voice';
    modeSelectionOverlay.classList.add('hidden');
    voiceSection.classList.remove('hidden');
    textChatSection.classList.add('hidden');
    card.classList.remove('text-mode');
    featuresSection.classList.remove('hidden');
    pauseBtn.classList.remove('hidden');
    switchModeIcon.textContent = '💬';
    switchModeText.textContent = 'Switch Mode';
    mainTitle.textContent = 'SmartShip Voice';
    document.dispatchEvent(new Event('startVoiceMode'));
}

// Start IVR mode (voice without camera)
function startIvrMode() {
    currentMode = 'ivr';
    modeSelectionOverlay.classList.add('hidden');
    voiceSection.classList.remove('hidden');
    textChatSection.classList.add('hidden');
    card.classList.remove('text-mode');
    featuresSection.classList.add('hidden');
    pauseBtn.classList.remove('hidden');
    switchModeIcon.textContent = '💬';
    switchModeText.textContent = 'Switch Mode';
    mainTitle.textContent = 'SmartShip IVR';
    document.dispatchEvent(new Event('startIvrMode'));
}

// Start text mode
function startTextMode() {
    currentMode = 'text';
    modeSelectionOverlay.classList.add('hidden');
    voiceSection.classList.add('hidden');
    textChatSection.classList.remove('hidden');
    card.classList.add('text-mode');
    featuresSection.classList.add('hidden');
    pauseBtn.classList.add('hidden');
    switchModeIcon.textContent = '🎤';
    switchModeText.textContent = 'Switch Mode';
    mainTitle.textContent = 'SmartShip Text';
    initTextChat();
}

// Toggle between modes
function toggleMode() {
    if ((currentMode === 'voice' || currentMode === 'ivr') && window.websocket) {
        window.websocket.close();
    } else if (currentMode === 'text' && textWebSocket) {
        textWebSocket.close();
    }
    
    if (currentMode === 'text') {
        clearChatMessages();
    }
    
    modeSelectionOverlay.classList.remove('hidden');
}

// Initialize text chat
function initTextChat() {
    connectTextWebSocket();
    chatSendBtn.addEventListener('click', sendTextMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendTextMessage();
        }
    });
}

// Connect to WebSocket for text mode
function connectTextWebSocket() {
    const userId = "text-user";
    const sessionId = "text-session-" + Math.random().toString(36).substring(7);
    const protocol = window.location.protocol === "https:" ? "wss://" : "ws://";
    const wsUrl = protocol + window.location.host + "/ws/" + userId + "/" + sessionId + "?mode=text";
    
    textWebSocket = new WebSocket(wsUrl);
    
    textWebSocket.onopen = () => {
        isTextConnected = true;
        chatSendBtn.disabled = false;
        setTimeout(() => {
            textWebSocket.send(JSON.stringify({ type: 'text', text: 'Hello' }));
        }, 500);
    };
    
    textWebSocket.onmessage = (event) => handleTextWebSocketMessage(event);
    textWebSocket.onerror = (error) => addAgentMessage('Sorry, there was a connection error. Please refresh the page and try again.');
    textWebSocket.onclose = () => {
        isTextConnected = false;
        chatSendBtn.disabled = true;
    };
}

// Handle incoming WebSocket messages
function handleTextWebSocketMessage(event) {
    try {
        if (typeof event.data === 'string') {
            const data = JSON.parse(event.data);
            
            // Log to debug
            console.log('[TEXT MODE] Received:', data);
            
            if (data.type === 'workflow_state_update') {
                handleWorkflowStateUpdate(data.workflow_state, data.data);
                return;
            }
            
            // Handle turn complete events
            if (data.turnComplete === true) {
                console.log('[TEXT MODE] Turn complete - resetting for next message');
                currentResponseText = '';
                lastAgentMessageBubble = null;
                lastProcessedText = '';
                return;
            }
            
            if (data.content && data.content.parts) {
                const textParts = data.content.parts.filter(part => part.text).map(part => part.text).join('');
                
                if (textParts) {
                    // Check if this is a duplicate of the full previous response
                    // Some models send the complete text multiple times instead of streaming incrementally
                    if (textParts === lastProcessedText) {
                        console.log('[TEXT MODE] Skipping duplicate message');
                        return;
                    }
                    
                    // Start a new message if this is a new turn
                    if (!lastAgentMessageBubble || currentResponseText === '') {
                        console.log('[TEXT MODE] Starting new message bubble');
                        removeTypingIndicator();
                        lastAgentMessageBubble = createAgentMessageBubble();
                        chatMessages.appendChild(lastAgentMessageBubble);
                        currentResponseText = '';
                    }
                    
                    // For non-streaming models that send complete text each time,
                    // replace instead of append
                    if (textParts.includes(currentResponseText)) {
                        currentResponseText = textParts;
                    } else {
                        currentResponseText += textParts;
                    }
                    
                    lastProcessedText = textParts;
                    updateMessageBubbleContent(lastAgentMessageBubble, currentResponseText);
                    scrollChatToBottom();
                }
            }
        }
    } catch (error) {
        console.error('Error handling message:', error, event.data);
    }
}

// Send text message
function sendTextMessage() {
    const text = chatInput.value.trim();
    if (!text || !isTextConnected) return;
    
    addUserMessage(text);
    chatInput.value = '';
    addTypingIndicator();
    textWebSocket.send(JSON.stringify({ type: 'text', text: text }));
}

// Add user message bubble
function addUserMessage(text) {
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble user-bubble';
    bubble.textContent = text;
    chatMessages.appendChild(bubble);
    scrollChatToBottom();
}

// Create agent message bubble
function createAgentMessageBubble() {
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble agent-bubble';
    return bubble;
}

// Update message bubble content
function updateMessageBubbleContent(bubble, text) {
    bubble.innerHTML = '';
    text = text.replace(/\n{3,}/g, '\n\n').trim();
    
    if (text.includes('\n-') || text.includes('\n•') || text.includes('\n📦') || text.includes('\n📍')) {
        const parts = text.split('\n');
        let inList = false;
        let listItems = [];
        
        parts.forEach(part => {
            const trimmed = part.trim();
            if (trimmed.startsWith('-') || trimmed.startsWith('•') || trimmed.startsWith('📦') || trimmed.startsWith('📍')) {
                if (!inList) {
                    inList = true;
                    listItems = [];
                }
                let itemText = trimmed.substring(1).trim();
                if (trimmed.startsWith('📦') || trimmed.startsWith('📍')) {
                    itemText = trimmed;
                }
                listItems.push(itemText);
            } else {
                if (inList) {
                    const ul = document.createElement('ul');
                    listItems.forEach(item => {
                        const li = document.createElement('li');
                        li.textContent = item;
                        ul.appendChild(li);
                    });
                    bubble.appendChild(ul);
                    inList = false;
                    listItems = [];
                }
                if (trimmed) {
                    const p = document.createElement('p');
                    p.textContent = trimmed;
                    bubble.appendChild(p);
                }
            }
        });
        
        if (inList) {
            const ul = document.createElement('ul');
            listItems.forEach(item => {
                const li = document.createElement('li');
                li.textContent = item;
                ul.appendChild(li);
            });
            bubble.appendChild(ul);
        }
    } else {
        bubble.textContent = text;
    }
}

// Add agent message
function addAgentMessage(text) {
    const bubble = createAgentMessageBubble();
    updateMessageBubbleContent(bubble, text);
    chatMessages.appendChild(bubble);
    scrollChatToBottom();
}

// Add typing indicator
function addTypingIndicator() {
    removeTypingIndicator();
    const indicator = document.createElement('div');
    indicator.className = 'message-bubble typing-indicator-bubble';
    indicator.id = 'typingIndicator';
    for (let i = 0; i < 3; i++) {
        const dot = document.createElement('span');
        dot.className = 'typing-dot';
        indicator.appendChild(dot);
    }
    chatMessages.appendChild(indicator);
    scrollChatToBottom();
}

// Remove typing indicator
function removeTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) indicator.remove();
}

// Scroll chat to bottom
function scrollChatToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Clear chat messages
function clearChatMessages() {
    while (chatMessages.children.length > 1) {
        chatMessages.removeChild(chatMessages.lastChild);
    }
    currentResponseText = '';
    lastAgentMessageBubble = null;
    lastProcessedText = '';
}

// Handle workflow state updates
function handleWorkflowStateUpdate(state, data) {
    if (state === 'complete') {
        console.log('Workflow complete!');
    }
}

// Initialize when DOM is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initModeSelection());
} else {
    initModeSelection();
}

// Export for use by other scripts
window.textMode = {
    startTextMode,
    startVoiceMode,
    startIvrMode,
    currentMode: () => currentMode
};
