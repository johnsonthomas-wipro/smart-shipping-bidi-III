# Smart Shipping Bidi - Test Suite

This folder contains integration tests for the WebSocket-based voice assistant.

## Quick Start

### 1. Start the Server (Terminal 1)
```powershell
cd C:\code\canadapost\voice3\smart-shipping-bidi\app
uvicorn main:app --reload
```

Or use the provided script:
```powershell
cd C:\code\canadapost\voice3\smart-shipping-bidi
.\start_server.ps1
```

**Wait for:** `INFO: Application startup complete.`

### 2. Run Tests (Terminal 2)
```powershell
cd C:\code\canadapost\voice3\smart-shipping-bidi\tests

# Run individual tests
python test_websocket_connection.py
python test_audio_streaming.py

# Or run all tests
.\run_tests.ps1
```

### Test 1: WebSocket Connection
Tests basic WebSocket connectivity to the ADK server.

```powershell
cd tests
python test_websocket_connection.py
```

**What it tests:**
- ✅ Can establish WebSocket connection to `/ws/{user_id}/{session_id}`
- ✅ Connection stays open
- ✅ Can send/receive messages
- ✅ Server responds to keepalive pings

**Expected output:**
```
✅ TEST PASSED: WebSocket connection works!
```

---

### Test 2: Audio Streaming
Tests sending audio data and receiving audio/text responses from ADK.

```powershell
cd tests
python test_audio_streaming.py
```

**What it tests:**
- ✅ Can send PCM16 audio data via WebSocket
- ✅ ADK processes audio and returns events
- ✅ Response contains audio data (`inlineData` with `audio/pcm`)
- ✅ Response contains text/transcriptions
- ✅ Turn completion is signaled

**Expected output:**
```
✅ TEST PASSED: Audio streaming works!
Total responses: 5+
Audio received: ✅ YES
Text received: ✅ YES
```

---

## Running All Tests

```powershell
# Run both tests
cd tests
python test_websocket_connection.py
python test_audio_streaming.py
```

Or create a simple batch file:
```powershell
# run_tests.ps1
Write-Host "Running WebSocket Connection Test..." -ForegroundColor Cyan
python test_websocket_connection.py

Write-Host "`nRunning Audio Streaming Test..." -ForegroundColor Cyan
python test_audio_streaming.py
```

---

## Troubleshooting

### Connection Refused
```
❌ Connection refused!
```
**Solution:** Make sure the server is running:
```powershell
cd app
uv run uvicorn main:app --reload
```

### No Audio Response
```
⚠️ TEST PARTIAL: Connection works but limited response
```
**Possible causes:**
1. ADK is still initializing (wait 10-20 seconds after server start)
2. Test audio is too short (already 500ms, should be enough)
3. ADK model might need actual speech (test uses sine wave tone)

**Solution:** Try testing with the actual frontend at http://localhost:8000

### Import Error (websockets)
```
ModuleNotFoundError: No module named 'websockets'
```
**Solution:**
```powershell
pip install websockets
```

---

## Test Architecture

```
Client Test → WebSocket → FastAPI Server → ADK Agent
    ↓              ↓            ↓              ↓
Generate      Binary PCM   upstream_task  Gemini API
Sine Wave     → Audio      processes      processes
                           audio          & responds
                                             ↓
                           downstream_task ←── ADK Events
                           sends JSON       (audio + text)
                              ↓
                           WebSocket
                              ↓
                           Test receives
                           & validates
```

---

## Expected Timeline

1. **T+0s**: WebSocket connects
2. **T+0.1s**: Test sends audio (500ms of sine wave)
3. **T+0.5s**: ADK starts processing
4. **T+1-3s**: First responses arrive (may include setup events)
5. **T+3-5s**: Audio response arrives (base64-encoded PCM)
6. **T+5-8s**: Turn complete signal

**Note:** First request after server start may take longer (10-20s) as ADK initializes.

---

## What Success Looks Like

### Test 1 Success:
```
✅ WebSocket connection established!
✅ Ping sent successfully
✅ Server is responsive!
✅ TEST PASSED: WebSocket connection works!
```

### Test 2 Success:
```
✅ WebSocket connected
✅ Audio sent successfully
📨 Response #1: JSON Event
   Part 1: audio/pcm
     ✅ AUDIO DATA RECEIVED!
   Output transcription: Hello! I can help you...
✅ Turn complete!

Total responses: 5
Audio received: ✅ YES
Text received: ✅ YES
✅ TEST PASSED: Audio streaming works!
```
