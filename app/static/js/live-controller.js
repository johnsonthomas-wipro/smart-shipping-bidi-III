/**
 * SmartShip Voice Assistant v9 - Gemini Live API with AudioWorklets
 * Real-time bidirectional audio streaming
 */

// Import AudioWorklet modules
import { startAudioRecorderWorklet } from "./audio-recorder.js";
import { startAudioPlayerWorklet } from "./audio-player.js";

class LiveAudioController {
    constructor(mode = 'voice') {
        console.log(`=== LiveAudioController v9 (AudioWorklets) Initialized - Mode: ${mode} ===`);
        
        // Store mode (voice or ivr)
        this.mode = mode;  // 'voice' = with camera, 'ivr' = audio-only
        
        // WebSocket for Gemini Live API
        this.ws = null;
        this.isConnected = false;
        this.intentionalClose = false;  // Flag to prevent error on intentional close
        this.keepaliveInterval = null;  // Keepalive timer
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 3;
        
        // Audio context and AudioWorklets
        this.audioRecorderContext = null;
        this.audioPlayerContext = null;
        this.mediaStream = null;
        this.audioRecorderNode = null;
        this.audioPlayerNode = null;
        
        // Camera
        this.cameraStream = null;
        this.capturedImages = [];
        this.captureInterval = null;
        this.isAnalyzing = false;  // Prevent duplicate camera triggers during analysis
        
        // State
        this.currentState = 'idle';
        this.isSpeaking = false;
        this.isListening = false;
        this.isPaused = false;
        
        // UI elements
        this.statusText = document.getElementById('statusText');
        this.statusSubtext = document.getElementById('statusSubtext');
        this.transcriptDisplay = document.getElementById('transcriptDisplay');
        this.startView = document.getElementById('startView');
        this.voiceButton = document.getElementById('voiceButton');
        this.cameraView = document.getElementById('cameraView');
        this.resultsView = document.getElementById('resultsView');
        this.video = document.getElementById('video');
        this.captureProgress = document.getElementById('captureProgress');
        this.restartBtn = document.getElementById('restartBtn');
        this.restartBtnResults = document.getElementById('restartBtnResults');
        this.pauseBtn = document.getElementById('pauseBtn');
        this.pauseIcon = document.getElementById('pauseIcon');
        this.pauseText = document.getElementById('pauseText');
        
        this.setupButtonHandlers();
        this.init();
    }
    
    setupButtonHandlers() {
        // Pause/Resume button
        if (this.pauseBtn) {
            this.pauseBtn.addEventListener('click', () => {
                if (this.isPaused) {
                    this.resume();
                } else {
                    this.pause();
                }
            });
        }
        
        // Restart button in main view
        if (this.restartBtn) {
            this.restartBtn.addEventListener('click', () => {
                console.log('🔄 Restart button clicked');
                this.restart();
            });
        }
        
        // Restart button in results view
        if (this.restartBtnResults) {
            this.restartBtnResults.addEventListener('click', () => {
                console.log('🔄 Restart button clicked (results view)');
                this.restart();
            });
        }
    }
    
    pause() {
        console.log('⏸️ Pausing Live API...');
        this.isPaused = true;
        
        // Close WebSocket to stop charges
        if (this.ws) {
            this.intentionalClose = true;  // Mark as intentional
            this.stopKeepalive();
            this.ws.close();
            this.ws = null;
        }
        
        this.isConnected = false;
        this.isListening = false;
        
        // Update UI
        this.updateStatus('Audio paused');
        if (this.pauseIcon) this.pauseIcon.textContent = '▶️';
        if (this.pauseText) this.pauseText.textContent = 'Resume';
        if (this.voiceButton) this.voiceButton.classList.remove('listening');
        
        console.log('✅ Live API paused - WebSocket disconnected');
    }
    
    async resume() {
        console.log('▶️ Resuming Live API...');
        this.isPaused = false;
        
        // Update UI first
        if (this.pauseIcon) this.pauseIcon.textContent = '⏸️';
        if (this.pauseText) this.pauseText.textContent = 'Pause';
        this.updateStatus('Connecting...');
        
        // Reconnect to Live API
        await this.connectToLiveAPI();
        
        console.log('✅ Live API resumed');
    }
    
    restart() {
        console.log('🔄 Restarting conversation...');
        
        // Close existing WebSocket
        if (this.ws) {
            this.intentionalClose = true;  // Mark as intentional
            this.ws.close();
            this.ws = null;
            this.isConnected = false;
        }
        
        // Stop camera if active
        if (this.cameraStream) {
            this.cameraStream.getTracks().forEach(track => track.stop());
            this.cameraStream = null;
        }
        
        // Clear capture interval
        if (this.captureInterval) {
            clearInterval(this.captureInterval);
            this.captureInterval = null;
        }
        
        // Clear captured images
        this.capturedImages = [];
        
        // Reset state
        this.currentState = 'idle';
        this.isSpeaking = false;
        this.isPaused = false;
        
        // Clear transcript
        if (this.transcriptDisplay) {
            this.transcriptDisplay.innerHTML = '';
        }
        
        // Clear dimensions display
        const dimensionDetails = document.getElementById('dimensionDetails');
        if (dimensionDetails) {
            dimensionDetails.innerHTML = '';
        }
        
        // Clear postal code displays
        const fromDisplay = document.getElementById('fromPostalDisplay');
        const toDisplay = document.getElementById('toPostalDisplay');
        if (fromDisplay) fromDisplay.textContent = '';
        if (toDisplay) toDisplay.textContent = '';
        
        // Clear rates display
        const ratesDisplay = document.getElementById('ratesDisplay');
        if (ratesDisplay) ratesDisplay.innerHTML = '';
        
        // Switch back to start view
        this.switchView('start');
        
        // Update status
        this.updateStatus('Restarting...');
        
        console.log('✅ Conversation restarted - Reconnecting to Live API');
        
        // Reinitialize - reconnect to Live API (greeting will come from Gemini)
        this.init();
    }
    
    async init() {
        console.log('🎤 Initializing audio systems...');
        
        // Initialize Live API directly - greeting will come from Gemini
        this.updateStatus('Connecting...');
        this.initializeLiveAPI();
    }
    
    async initializeLiveAPI() {
        console.log('🎤 Initializing Live API with AudioWorklets...');
        
        try {
            // Initialize audio recorder worklet (creates its own context and gets microphone)
            //console.log('🎙️ Starting audio recorder worklet...');
            const [audioRecorderNode, audioRecorderContext, micStream] = await startAudioRecorderWorklet(
                (pcmData) => {
                    // pcmData is already an ArrayBuffer from convertFloat32ToPCM
                    // Send PCM data directly via WebSocket (always send user audio)
                    if (this.ws && this.ws.readyState === WebSocket.OPEN && !this.isPaused) {
                        try {
                            this.ws.send(pcmData);  // Send ArrayBuffer directly
                            //console.log(`📤 Sent ${pcmData.byteLength} bytes of audio (WS state: ${this.ws.readyState})`);
                        } catch (err) {
                            console.error('❌ Error sending audio:', err);
                        }
                    } else {
                        console.warn(`⚠️ Cannot send audio - WS state: ${this.ws ? this.ws.readyState : 'null'}, isPaused: ${this.isPaused}`);
                    }
                }
            );
            this.audioRecorderNode = audioRecorderNode;
            this.audioRecorderContext = audioRecorderContext;
            this.mediaStream = micStream;
            console.log('✅ Audio recorder worklet started at', audioRecorderContext.sampleRate, 'Hz');
            
            // Initialize audio player worklet (creates its own context at 24kHz)
            //console.log('🔊 Starting audio player worklet...');
            const [audioPlayerNode, audioPlayerContext] = await startAudioPlayerWorklet();
            this.audioPlayerNode = audioPlayerNode;
            this.audioPlayerContext = audioPlayerContext;
            //console.log('✅ Audio player worklet started at', audioPlayerContext.sampleRate, 'Hz');
            
            // Connect to Live API
            await this.connectToLiveAPI();
            
        } catch (err) {
            console.error('❌ Initialization error:', err);
            console.error('Error name:', err.name);
            console.error('Error message:', err.message);
            
            // Provide specific error messages based on error type
            let errorMessage = 'Microphone access required';
            let errorSubtext = 'Please allow microphone access in your browser';
            
            if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                errorMessage = 'Microphone permission denied';
                errorSubtext = 'Click the 🔒 icon in your address bar and allow microphone access';
            } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
                errorMessage = 'No microphone found';
                errorSubtext = 'Please connect a microphone and refresh the page';
            } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
                errorMessage = 'Microphone is in use';
                errorSubtext = 'Close other apps using your microphone and try again';
            } else if (err.name === 'OverconstrainedError') {
                errorMessage = 'Microphone not compatible';
                errorSubtext = 'Your microphone does not support the required audio settings';
            } else if (err.name === 'SecurityError') {
                errorMessage = 'Security error';
                errorSubtext = 'Microphone access blocked by browser security policy';
            }
            
            this.updateStatus(errorMessage);
            if (this.statusSubtext) {
                this.statusSubtext.textContent = errorSubtext;
            }
            
            // Show overlay again so user can retry
            const overlay = document.getElementById('audioInitOverlay');
            const overlayMessage = document.getElementById('overlayMessage');
            if (overlay) {
                overlay.style.display = 'flex';
                if (overlayMessage) {
                    overlayMessage.textContent = `${errorMessage} - ${errorSubtext}`;
                    overlayMessage.style.color = '#ff4444';
                }
            }
        }
    }
    
    async connectToLiveAPI() {
        console.log('📡 Connecting to Gemini Live API...');
        
        // Generate user and session IDs
        const userId = "smartship-user";
        const sessionId = "session-" + Math.random().toString(36).substring(7);
        
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // Pass mode parameter to backend (voice or ivr)
        const wsUrl = `${protocol}//${window.location.host}/ws/${userId}/${sessionId}?proactivity=false&mode=${this.mode}`;
        
        console.log('📡 WebSocket URL:', wsUrl);
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onopen = () => {
            console.log('✅ Connected to Live API');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.updateStatus('Listening... Ready when you are');
            
            // Start keepalive ping every 30 seconds
            this.startKeepalive();
            
            // AudioWorklets are already streaming - no need to call startAudioStreaming()
            this.isListening = true;
            if (this.voiceButton) {
                this.voiceButton.classList.add('listening');
            }
        };
        
        this.ws.onmessage = (event) => {
            try {
                const adkEvent = JSON.parse(event.data);
                
                // Also check if event contains "workflow_state" text anywhere
                // const eventStr = JSON.stringify(adkEvent);
                // if (eventStr.includes('workflow_state')) {
                //     console.log('📊 ========== EVENT WITH WORKFLOW_STATE ==========');
                //     console.log('Full Event:', JSON.stringify(adkEvent, null, 2));
                //     console.log('==================================================');
                // }
                
                //console.log('📨 Raw ADK Event keys:', Object.keys(adkEvent));
                //console.log('📨 ADK Event:', adkEvent);
                this.handleADKEvent(adkEvent);
            } catch (err) {
                console.error('❌ Error parsing message:', err);
            }
        };
        
        this.ws.onerror = (error) => {
            if (!this.intentionalClose) {
                console.error('❌ WebSocket error:', error);
                this.updateStatus('Connection error');
            }
        };
        
        this.ws.onclose = () => {
            this.isConnected = false;
            this.stopKeepalive();
            
            if (!this.intentionalClose) {
                console.log('🔴 Disconnected from Live API');
                
                // Attempt reconnection
                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnectAttempts++;
                    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000);
                    console.log(`🔄 Reconnecting in ${delay/1000}s (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
                    this.updateStatus(`Reconnecting in ${delay/1000}s...`);
                    
                    setTimeout(() => {
                        if (!this.isConnected && !this.intentionalClose) {
                            console.log('🔄 Attempting reconnection...');
                            this.connectToLiveAPI();
                        }
                    }, delay);
                } else {
                    console.log('❌ Max reconnection attempts reached');
                    this.updateStatus('Disconnected - Click Restart to reconnect');
                }
            }
            
            // Reset flag for next connection
            this.intentionalClose = false;
        };
    }
    
    handleADKEvent(adkEvent) {
        // Track if camera was triggered in this event to prevent duplicates
        let cameraTriggerProcessed = false;
        //console.log('📦 ADK event', adkEvent);
        
        // Handle pong response from server keepalive
        if (adkEvent.type === 'pong') {
            console.log('🏓 Keepalive pong received');
            return;
        }
        
        // Handle workflow state updates
        if (adkEvent.type === 'workflow_state_update') {
            console.log('📊 ========== WORKFLOW STATE UPDATE ==========');
            console.log('Full Event:', JSON.stringify(adkEvent, null, 2));
            console.log('============================================');
            
            if (adkEvent.workflow_state === 'waiting_for_camera_ready') {
                this.triggerCameraCapture();
                return;
            } else if (adkEvent.workflow_state === 'capturing') {
                this.startCapturing();
                return;
            }
        }
        
        // Only log full event if it contains function calls or responses
        const hasFunctionCall = adkEvent.toolCall || adkEvent.toolCalls || 
            (adkEvent.content?.parts?.some(p => p.functionCall || p.functionResponse)) ||
            (adkEvent.serverContent?.modelTurn?.parts?.some(p => p.functionCall || p.functionResponse));
        
        if (hasFunctionCall) {
            console.log('📨 ADK Event with FUNCTION CALL:', JSON.stringify(adkEvent, null, 2));
        }
        
        // Handle turn complete
        if (adkEvent.turnComplete === true) {
            // console.log('✅ Turn complete - Gemini finished');
            this.isSpeaking = false;
            this.updateStatus('Listening...');
            return;
        }
        
        // Handle interrupted
        if (adkEvent.interrupted) {
            console.log('⏸️ Interrupted');
            this.isSpeaking = false;
            return;
        }
        
        // Handle input transcription (what user said)
        if (adkEvent.inputTranscription) {
            const text = adkEvent.inputTranscription.text || '';
            const isFinished = adkEvent.inputTranscription.finished;
            
            // Only log and add to transcript when the transcription is complete
            if (isFinished) {
                //console.log('🎤 USER SAID:', text);
                this.addToTranscript('user', text);
            }
        }
        
        // Handle output transcription (what agent is saying)
        if (adkEvent.outputTranscription) {
            const text = adkEvent.outputTranscription.text || '';
            //console.log('📝 Output:', text);
            this.addToTranscript('assistant', text);
            // Note: Camera trigger is handled in content.parts[] below (primary source)
        }
        
        // // Handle tool calls (check multiple possible locations)
        // if (adkEvent.toolCall) {
        //     console.log('🔧 Tool call found in adkEvent.toolCall:', adkEvent.toolCall);
        //     this.handleFunctionCall(adkEvent.toolCall);
        // }
        
        // if (adkEvent.toolCalls && Array.isArray(adkEvent.toolCalls)) {
        //     console.log('🔧 Tool calls found in adkEvent.toolCalls:', adkEvent.toolCalls);
        //     adkEvent.toolCalls.forEach(call => this.handleFunctionCall(call));
        // }
        
        // // Handle server content
        // if (adkEvent.serverContent) {
        //     console.log('📦 Processing serverContent');
            
        //     // Check for tool calls in serverContent.modelTurn
        //     if (adkEvent.serverContent.modelTurn && adkEvent.serverContent.modelTurn.parts) {
        //         console.log('📦 Processing modelTurn parts:', adkEvent.serverContent.modelTurn.parts.length);
        //         for (const part of adkEvent.serverContent.modelTurn.parts) {
        //             if (part.functionCall) {
        //                 console.log('🔧 Function call in modelTurn part:', part.functionCall);
        //                 this.handleFunctionCall(part.functionCall);
        //             }
        //             if (part.functionResponse) {
        //                 console.log('✅ Function response in modelTurn part:', part.functionResponse);
        //                 this.handleFunctionResponse(part.functionResponse);
        //             }
        //         }
        //     }
        // }
        // // Handle function calls in parts
        // if (part.functionCall) {
        //     console.log('🔧 Function call in part:', part.functionCall);
        //     this.handleFunctionCall(part.functionCall);
        // }
        
        // Handle content (audio, text, tool calls)
        if (adkEvent.content && adkEvent.content.parts) {
            // console.log('📦 Processing content parts:', adkEvent.content.parts.length);
            for (const part of adkEvent.content.parts) {
                // Handle audio data
                if (part.inlineData && part.inlineData.mimeType && part.inlineData.mimeType.startsWith('audio/')) {
                    // console.log('🔊 Playing audio:', part.inlineData.mimeType, 'length:', part.inlineData.data?.length);
                    this.isSpeaking = true;
                    this.updateStatus('Speaking...');
                    this.playAudioChunk(part.inlineData.data, part.inlineData.mimeType);
                }
                else
                {
                    //console.log('📝 not audio logging:', part);
                }
                
                // 🚀 CHECK FOR TEXT CONTENT WITH JSON CAMERA TRIGGER 🚀
                // Note: Only process for camera triggers in voice mode, not IVR
                if (part.text && this.mode === 'voice') {
                    const text = part.text;
                    
                    // Only log if it's NOT internal thinking (marked with ** or workflow keywords)
                    const isInternalThinking = text.includes('**') || text.includes('workflow') || 
                                              text.includes('state') || text.includes('plan');
                    if (!isInternalThinking) {
                        console.log('📝 Text part received:', text);
                    }
                    
                    try {
                        if (text.trim().startsWith('{') && text.includes('enable_camera')) {
                            const jsonMatch = text.match(/\{[^}]+\}/);
                            if (jsonMatch) {
                                const command = JSON.parse(jsonMatch[0]);
                                if (command.action === 'enable_camera') {
                                    console.log('📸 Camera trigger detected in text part:', command);
                                    if (cameraTriggerProcessed) {
                                        console.log('📸 Camera already triggered in this event, skipping duplicate');
                                    } else if (!this.cameraStream) {
                                        console.log('📸 Enabling camera from JSON command in content.parts');
                                        this.enableCamera();
                                        cameraTriggerProcessed = true;
                                    } else {
                                        console.log('📸 Camera already active, skipping duplicate trigger');
                                    }
                                }
                            }
                        }
                    } catch (e) {
                        // Not JSON, ignore
                    }
                }
                
                
                
                // Handle function responses
                if (part.functionResponse) {
                    console.log('✅ Function response:', part.functionResponse);
                    this.handleFunctionResponse(part.functionResponse);
                }
            }
        }
    }
    
    // handleFunctionCall(functionCall) {
    //     const toolName = functionCall.name;
    //     const args = functionCall.args || functionCall.arguments || {};
        
    //     console.log(`\n🔧 ========== FUNCTION CALL ==========`);
    //     console.log('Function:', toolName);
    //     console.log('Args:', args);
    //     console.log('=====================================\n');
        
    //     switch (toolName) {
    //         case 'capture_and_measure_package':
    //             console.log('📸 Camera capture requested via capture_and_measure_package');
    //             this.triggerCameraCapture();
    //             break;
                
    //         case 'capture_and_measure_package_at_browser':
    //             console.log('📸 Camera capture requested via capture_and_measure_package_at_browser');
    //             this.triggerCameraCapture();
    //             break;
                
    //         case 'validate_postal_code':
    //             console.log('📮 Validating postal code:', args.postal_code);
    //             // Validation happens on server, just log
    //             break;
                
    //         case 'calculate_shipping_rates':
    //             console.log('💰 Calculating shipping rates');
    //             console.log('   From:', args.from_postal);
    //             console.log('   To:', args.to_postal);
    //             console.log('   Dimensions:', args.dimensions);
    //             break;
                
    //         case 'update_workflow_state':
    //             console.log('📊 Workflow state update:', args.state);
    //             break;
                
    //         default:
    //             console.log('🔧 Unknown tool:', toolName);
    //     }
    // }
    
    handleFunctionResponse(functionResponse) {
        const toolName = functionResponse.name;
        const result = functionResponse.response || {};
        
        console.log(`\n✅ ========== FUNCTION RESPONSE ==========`);
        console.log(`Tool: ${toolName}`);
        console.log('Result:', JSON.stringify(result, null, 2));
        console.log('==========================================\n');
        
        switch (toolName) {
            case 'capture_and_measure_package_at_browser':
                console.log('� Camera capture response received:', result);
                // Check if this is the initial trigger (action: enable_camera)
                if (result.action === 'enable_camera') {
                    console.log('📸 Enabling camera from function response (backup trigger)');
                    if (!this.cameraStream) {  // Only enable if not already enabled
                        this.enableCamera();
                    }
                }
                // Or if dimensions are included in the response (from analyze-and-confirm)
                if (result.success && result.dimensions) {
                    console.log('📏 Dimensions received from server:', result.dimensions);
                    this.displayDimensions(result.dimensions);
                }
                break;
                
            case 'validate_postal_code':
                console.log('📮 Postal code validation result:', result);
                if (result.valid && result.formatted) {
                    this.displayPostalCode(result.formatted, result.type);
                }
                break;
                
            case 'calculate_shipping_rates':
                console.log('💰 Shipping rates received:', result);
                if (result.success && result.rates) {
                    this.displayShippingRates(result);
                }
                break;
        }
    }
    
    displayDimensions(dimensions) {
        console.log('📏 Displaying dimensions in UI:', dimensions);
        const dimensionDetails = document.getElementById('dimensionDetails');
        if (dimensionDetails && dimensions) {
            dimensionDetails.innerHTML = `
                <div class="dimension-card">
                    <div class="dimension-label">Length</div>
                    <div class="dimension-value">${dimensions.length} <span class="dimension-unit">cm</span></div>
                </div>
                <div class="dimension-card">
                    <div class="dimension-label">Width</div>
                    <div class="dimension-value">${dimensions.width} <span class="dimension-unit">cm</span></div>
                </div>
                <div class="dimension-card">
                    <div class="dimension-label">Height</div>
                    <div class="dimension-value">${dimensions.height} <span class="dimension-unit">cm</span></div>
                </div>
            `;
            console.log('✅ Dimensions displayed in UI');
        }
    }
    
    displayPostalCode(postalCode, type) {
        console.log(`📮 Displaying ${type} postal code:`, postalCode);
        const fromDisplay = document.getElementById('fromPostalDisplay');
        const toDisplay = document.getElementById('toPostalDisplay');
        
        // Determine which field to update based on current state or which is empty
        if (type === 'from' || (fromDisplay && !fromDisplay.textContent)) {
            if (fromDisplay) {
                fromDisplay.textContent = postalCode;
                console.log('✅ Updated FROM postal code display');
            }
        } else if (type === 'to' || (toDisplay && !toDisplay.textContent)) {
            if (toDisplay) {
                toDisplay.textContent = postalCode;
                console.log('✅ Updated TO postal code display');
            }
        } else if (fromDisplay && !fromDisplay.textContent) {
            fromDisplay.textContent = postalCode;
            console.log('✅ Updated FROM postal code display (fallback)');
        } else if (toDisplay) {
            toDisplay.textContent = postalCode;
            console.log('✅ Updated TO postal code display (fallback)');
        }
    }
    
    displayShippingRates(result) {
        console.log('💰 Displaying shipping rates in UI');
        
        // Update postal codes
        const fromDisplay = document.getElementById('fromPostalDisplay');
        const toDisplay = document.getElementById('toPostalDisplay');
        if (fromDisplay && result.from_postal) {
            fromDisplay.textContent = result.from_postal;
        }
        if (toDisplay && result.to_postal) {
            toDisplay.textContent = result.to_postal;
        }
        
        // Update dimensions
        if (result.dimensions) {
            this.displayDimensions(result.dimensions);
        }
        
        // Display rates
        const ratesDisplay = document.getElementById('ratesDisplay');
        if (ratesDisplay && result.rates) {
            ratesDisplay.innerHTML = result.rates.map((rate, index) => `
                <div class="shipping-option ${index === 0 ? 'recommended' : ''}">
                    <div class="shipping-info">
                        <div class="shipping-name">
                            ${rate.service}
                            ${index === 0 ? '<span class="recommended-badge">Best Value</span>' : ''}
                        </div>
                        <div class="shipping-time">${rate.delivery}</div>
                    </div>
                    <div class="shipping-price">
                        <div class="price-amount">${rate.price}</div>
                    </div>
                </div>
            `).join('');
            console.log('✅ Rates displayed in UI with', result.rates.length, 'options');
            
            // Switch to results view
            this.switchView('results');
            console.log('✅ Switched to results view');
        }
    }
    
    
    
    
    
    async playAudioChunk(audioBase64, mimeType = 'audio/pcm') {
        try {
            if (!this.audioPlayerNode) {
                console.error('❌ Audio player not initialized');
                return;
            }
            
            // Handle URL-safe base64 (convert - to + and _ to /)
            let standardBase64 = audioBase64.replace(/-/g, '+').replace(/_/g, '/');
            
            // Add padding if needed
            while (standardBase64.length % 4) {
                standardBase64 += '=';
            }
            
            // Decode base64 to ArrayBuffer
            const binaryString = atob(standardBase64);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            
            // Send ArrayBuffer to AudioWorklet (worklet will convert to Int16Array)
            this.audioPlayerNode.port.postMessage(bytes.buffer);
            //console.log(`🔊 Sent ${bytes.length} bytes to audio player worklet`);
            
        } catch (err) {
            console.error('❌ Error playing audio chunk:', err);
            console.error('   Base64 length:', audioBase64?.length);
            console.error('   First 50 chars:', audioBase64?.substring(0, 50));
        }
    }
    
    sendEndOfTurn() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'end_of_turn'
            }));
            console.log('📤 Sent end-of-turn signal');
        }
    }
    
    updateStatus(text, subtext = '') {
        if (this.statusText) {
            this.statusText.textContent = text;
        }
        if (this.statusSubtext) {
            this.statusSubtext.textContent = subtext;
        }
    }
    
    addToTranscript(role, text) {
        if (!this.transcriptDisplay) return;
        
        const div = document.createElement('div');
        div.className = role === 'user' ? 'user-text' : 'assistant-text';
        div.textContent = text;
        this.transcriptDisplay.appendChild(div);
        this.transcriptDisplay.scrollTop = this.transcriptDisplay.scrollHeight;
    }
    
    arrayBufferToBase64(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }
    
    stopListening() {
        console.log('🛑 Stopping listening - Flow complete');
        
        // Close WebSocket connection
        if (this.ws) {
            this.intentionalClose = true;  // Mark as intentional
            this.ws.close();
            this.ws = null;
        }
        
        this.isConnected = false;
        this.isListening = false;
        
        // Update UI
        this.updateStatus('Flow complete - Press restart to begin again');
        if (this.voiceButton) {
            this.voiceButton.classList.remove('listening');
        }
        
        console.log('✅ Listening stopped - WebSocket closed');
    }
    
    disconnect() {
        if (this.ws) {
            this.ws.close();
        }
        
        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
        }
        
        if (this.cameraStream) {
            this.cameraStream.getTracks().forEach(track => track.stop());
        }
        
        console.log('🔴 Disconnected');
    }
    switchView(viewName) {
        // Hide all views
        if (this.startView) this.startView.classList.add('hidden');
        if (this.cameraView) this.cameraView.classList.add('hidden');
        if (this.resultsView) this.resultsView.classList.add('hidden');
        
        // Show requested view
        if (viewName === 'start' && this.startView) {
            this.startView.classList.remove('hidden');
        } else if (viewName === 'camera' && this.cameraView) {
            this.cameraView.classList.remove('hidden');
        } else if (viewName === 'results' && this.resultsView) {
            this.resultsView.classList.remove('hidden');
        }
        
        console.log(`📺 Switched to ${viewName} view`);
    }
    
    triggerCameraCapture() {
        console.log('📸 Camera capture requested - enabling camera NOW');
        console.log('📸 Current camera stream status:', this.cameraStream ? 'ACTIVE' : 'INACTIVE');
        if (!this.cameraStream) {
            console.log('📸 Triggering camera from workflow state or function call');
            this.enableCamera();
        } else {
            console.log('📸 Camera already active, skipping duplicate trigger');
        }
    }
    
    async enableCamera() {
        // Prevent duplicate camera initialization
        if (this.cameraStream || this.captureInterval) {
            console.log('📸 Camera already active or capturing, skipping duplicate enableCamera call');
            return;
        }
        
        try {
            console.log('🎥 Enabling camera...');
            
            // Switch to camera view FIRST
            this.switchView('camera');
            
            // Ensure video element exists
            if (!this.video) {
                console.error('❌ Video element not found!');
                this.updateStatus('Error: Video element not found');
                return;
            }
            
            console.log('✓ Video element found:', this.video);
            
            // Request camera access
            console.log('📸 Requesting camera permission...');
            this.cameraStream = await navigator.mediaDevices.getUserMedia({ 
                video: { 
                    facingMode: 'environment',
                    width: { ideal: 1920 },
                    height: { ideal: 1080 }
                } 
            });
            
            console.log('✓ Camera stream acquired');
            
            // Attach stream to video element
            this.video.srcObject = this.cameraStream;
            console.log('✓ Stream attached to video element');
            
            // Wait for video to be ready
            await new Promise((resolve) => {
                this.video.onloadedmetadata = () => {
                    console.log('✓ Video metadata loaded');
                    this.video.play().then(() => {
                        console.log('✓ Video playing');
                        resolve();
                    }).catch(err => {
                        console.error('❌ Error playing video:', err);
                        resolve();
                    });
                };
            });
            
            console.log('✅ Camera enabled and ready');
            this.updateStatus('Camera ready - Capturing automatically...');
            
            // Start capturing after 1 second
            //setTimeout(() => this.startCapturing(), 1000);
            
        } catch (err) {
            console.error('❌ Camera error:', err);
            this.updateStatus('Camera access denied');
            this.switchView('start');
        }
    }
    
    startCapturing() {
        // Check if video is ready
        if (!this.video || !this.video.videoWidth || !this.video.videoHeight) {
            console.error('❌ Video not ready, waiting 500ms...');
            console.log(`Video state: width=${this.video?.videoWidth}, height=${this.video?.videoHeight}`);
            setTimeout(() => this.startCapturing(), 500);
            return;
        }
        
        console.log('📸 Starting image capture...');
        console.log(`📸 Video ready: ${this.video.videoWidth}x${this.video.videoHeight}`);
        this.capturedImages = [];
        let count = 0;
        
        // Capture immediately first image
        if (this.captureProgress) {
            this.captureProgress.textContent = 'Capturing image 1 of 6...';
        }
        this.captureImage();
        count++;
        
        // Check if only 1 image needed (shouldn't happen with 6, but for safety)
        if (count >= 6) {
            this.finishCapture();
            return;
        }
        
        // Then capture every 2 seconds until we have 6 total
        this.captureInterval = setInterval(() => {
            // Capture image first
            this.captureImage();
            count++;
            
            // Update progress
            if (count < 6) {
                const remaining = (6 - count) * 2;
                if (this.captureProgress) {
                    this.captureProgress.textContent = `Capturing image ${count + 1} of 6... (${remaining}s remaining)`;
                }
            }
            
            // Check if we're done (after capturing)
            if (count >= 6) {
                clearInterval(this.captureInterval);
                this.captureInterval = null;
                console.log('✅ Captured all 6 images, finishing...');
                if (this.captureProgress) {
                    this.captureProgress.textContent = 'Processing images...';
                }
                this.finishCapture();
            }
        }, 2000);
    }
    
    captureImage() {
        try {
            if (!this.video.videoWidth || !this.video.videoHeight) {
                console.error('❌ Invalid video dimensions');
                return;
            }
            
            const canvas = document.createElement('canvas');
            canvas.width = this.video.videoWidth;
            canvas.height = this.video.videoHeight;
            const ctx = canvas.getContext('2d');
            
            if (!ctx) {
                console.error('❌ Failed to get canvas context');
                return;
            }
            
            ctx.drawImage(this.video, 0, 0);
            const imageData = canvas.toDataURL('image/jpeg', 0.8);
            
            this.capturedImages.push({
                image: imageData,
                angle: `view_${this.capturedImages.length + 1}`
            });
            
            console.log(`📸 Captured image ${this.capturedImages.length} of 6`);
        } catch (error) {
            console.error('❌ Capture failed:', error);
        }
    }
    
    async finishCapture() {
        console.log('📊 Sending images to server for analysis...');
        
        // Set analyzing flag to prevent re-triggering
        this.isAnalyzing = true;
        
        // Stop camera
        if (this.cameraStream) {
            this.cameraStream.getTracks().forEach(track => track.stop());
            this.cameraStream = null;
        }
        
        // Switch back to start view
        console.log('🔍 Analyzing captured images...');
        this.switchView('start');
        this.updateStatus('Analyzing Package...');
        if (this.statusSubtext) {
            this.statusSubtext.textContent = 'Please wait while we process the dimensions';
        }
        
        try {
            // Send images to server for analysis
            const response = await fetch('/api/analyze-and-confirm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ images: this.capturedImages })
            });
            
            const data = await response.json();
            console.log('✅ Server response:', data);
            
            if (data.success && data.dimensions) {
                // Send dimensions through WebSocket to Gemini
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    const dims = data.dimensions;
                    
                    // Display dimensions in UI
                    const dimensionDetails = document.getElementById('dimensionDetails');
                    if (dimensionDetails) {
                        dimensionDetails.innerHTML = `
                            <div class="dimension-card">
                                <div class="dimension-label">Length</div>
                                <div class="dimension-value">${dims.length} <span class="dimension-unit">cm</span></div>
                            </div>
                            <div class="dimension-card">
                                <div class="dimension-label">Width</div>
                                <div class="dimension-value">${dims.width} <span class="dimension-unit">cm</span></div>
                            </div>
                            <div class="dimension-card">
                                <div class="dimension-label">Height</div>
                                <div class="dimension-value">${dims.height} <span class="dimension-unit">cm</span></div>
                            </div>
                        `;
                    }
                    
                    // Notify user the dimensions were captured
                    this.updateStatus('Dimensions captured!');
                    console.log('📏 Dimensions:', dims);
                    
                    // Send dimensions to Gemini so it can confirm and continue workflow
                    const dimensionText = `I have measured the package. The dimensions are: Length ${dims.length} cm, Width ${dims.width} cm, Height ${dims.height} cm. Please confirm these dimensions with the user and then proceed to collect postal codes.`;
                    
                    this.ws.send(JSON.stringify({
                        type: 'text',
                        text: dimensionText
                    }));
                    console.log('📤 Sent dimensions to Gemini for confirmation');
                }
            } else {
                console.error('❌ Analysis failed:', data.error);
                this.updateStatus('Error analyzing images');
                // Clear analyzing flag on error
                this.isAnalyzing = false;
            }
        } catch (err) {
            console.error('❌ Analysis error:', err);
            this.updateStatus('Error connecting to server');
            // Clear analyzing flag on error
            this.isAnalyzing = false;
        }
    }
    
    startKeepalive() {
        // Send ping every 30 seconds to keep WebSocket alive on Cloud Run
        this.stopKeepalive(); // Clear any existing interval
        this.keepaliveInterval = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'ping' }));
                console.log('🏓 Keepalive ping sent');
            }
        }, 30000); // 30 seconds
    }
    
    stopKeepalive() {
        if (this.keepaliveInterval) {
            clearInterval(this.keepaliveInterval);
            this.keepaliveInterval = null;
        }
    }
}

// Initialize when DOM is loaded or when voice mode is selected
document.addEventListener('DOMContentLoaded', () => {
    console.log('=== DOM LOADED ===');
    
    // Don't auto-initialize - wait for mode selection from text-mode.js
});

// Listen for voice mode start event from text-mode.js
document.addEventListener('startVoiceMode', () => {
    console.log('📻 Voice mode selected - initializing with camera');
    if (!window.liveController) {
        window.liveController = new LiveAudioController('voice');
    }
});

// Listen for IVR mode start event from text-mode.js
document.addEventListener('startIvrMode', () => {
    console.log('📞 IVR mode selected - initializing audio-only (no camera)');
    if (!window.liveController) {
        window.liveController = new LiveAudioController('ivr');
    }
});
