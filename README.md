# SmartShip Voice Assistant - ADK Bidi-Streaming

Voice-powered package shipping assistant using Google ADK (Agent Development Kit) with native audio streaming and SmartShip UI.

## ✅ Implementation Complete

Successfully migrated from bidi-demo2 + agentic8 to create smart-shipping-bidi with:
- ✅ ADK framework with WebSocket infrastructure from bidi-demo2
- ✅ SmartShip UI and shipping agent from agentic8
- ✅ 4 ADK FunctionTools for shipping workflow
- ✅ Camera-based package measurement with Gemini Vision
- ✅ System prompt with conversational shipping workflow
- ✅ Google Cloud Run deployment ready

## Features

- 🎤 **Real-time voice conversation** with Gemini Live API
- 📦 **SmartShip shipping workflow** - guided package shipping process
- 📸 **Camera-based package measurement** - AI analyzes images to measure dimensions
- 📝 **Live transcriptions** for user and agent speech
- 🔄 **ADK-powered tools** - postal code validation, shipping rate calculation
- � **Telnyx phone integration** - call from any phone to interact with AI
- �💬 **Affective Dialog & Proactivity** - optional emotional awareness

## Quick Start

### Installation

```bash
# Install dependencies with uv
uv sync

# Create .env file
echo "GOOGLE_API_KEY=your_api_key_here" > app/.env
```

### Run Locally

```bash
cd app
uv run python main.py
```

Open http://localhost:8000

## Project Structure

```
smart-shipping-bidi/
├── app/
│   ├── main.py              # FastAPI application with WebSocket
│   ├── shipping_agent/      # SmartShip agent implementation
│   │   ├── agent.py         # ADK agent definition
│   │   └── tools.py         # ADK FunctionTools
│   ├── static/              # Frontend assets
│   ├── system_prompt.txt    # Agent instructions
│   └── .env                 # API key configuration
├── pyproject.toml           # UV dependency management
└── uv.lock                  # Locked dependencies
```

## License

Apache 2.0
