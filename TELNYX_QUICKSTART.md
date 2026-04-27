# Telnyx Integration Quick Start

This guide helps you connect your SmartShip Voice Assistant to the phone network using Telnyx.

## Prerequisites

- Python 3.10+ installed
- Telnyx account with a phone number
- Public URL (ngrok, VS Code port forwarding, or deployed server)

## Quick Setup Steps

### 1. Install Dependencies

```bash
pip install -e .
```

### 2. Configure Environment

Create `.env` file in `app/` directory:

```bash
# Required for Gemini AI
GOOGLE_API_KEY=your_gemini_api_key_here

# Optional - show conversation in console
SHOW_CONVERSATION=false
```

### 3. Telnyx Setup

1. Create account: https://portal.telnyx.com/
2. Buy a phone number:
   - Go to Numbers → Search & Buy
   - Select a number and purchase it
3. Configure your number for TeXML:
   - Go to Numbers → My Numbers
   - Click on your number
   - Under "Voice Settings":
     - Connection Type: Select "TeXML Application"
     - Create a new TeXML Application or select existing
   - In TeXML Application settings:
     - Webhook URL: `https://your-domain.com/texml/voice`
     - Make sure it's using HTTPS
4. Note your Telnyx API credentials (optional, for advanced features)

### 4. Start the Server

```bash
cd app
python main.py
```

### 5. Test It!

Call your Telnyx number and say: "I need to ship a package"

## Architecture Overview

```
┌────────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────────┐
│   Phone    │────▶│   Telnyx     │────▶│  Your Server │────▶│   Gemini    │
│   Caller   │     │   Network    │     │  (FastAPI)   │     │  ADK Agent  │
└────────────┘     └──────────────┘     └──────────────┘     └─────────────┘
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │ Audio Codec  │
                                        │ μ-law ↔ PCM │
                                        └──────────────┘
```

### How It Works

1. User dials Telnyx number
   - Telnyx receives call
2. Telnyx executes TeXML → plays greeting
3. Telnyx creates WebSocket connection to your server
   - URL: `wss://your-domain.com/ws/phone`
4. Bidirectional audio streaming begins:
   - Caller speaks → Telnyx → Server → Gemini
   - Gemini responds → Server → Telnyx → Caller
5. Call continues until caller hangs up

## Troubleshooting

### "Connection refused" error
- Make sure server is running: `python main.py`
- Check your public URL is accessible
- Verify Telnyx webhook URL is correct

### No audio or one-way audio
- Check audio transcoding (μ-law ↔ PCM16)
- Verify WebSocket connection is established
- Check server logs for audio chunks

### Verify dependencies
```bash
python -c "from telephony import handle_telnyx_call; print('Telephony package OK')"
```

## Production Deployment

For production, you'll need:
1. **HTTPS domain** (required by Telnyx)
2. **Persistent server** (not ngrok)
3. **Monitor logs** for debugging
4. **Scale with load balancer** if needed

See [deployment/README.md](deployment/README.md) for Azure deployment guide.

## Next Steps

- Test different voice scenarios
- Add custom prompts in `system_prompt_ivr.txt`
- Deploy to Azure Container Apps (see deployment guide)
- Set up monitoring and logging
