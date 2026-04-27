# Stress Test Suite

AI-to-AI stress testing for the SmartShip Voice Assistant.

## Overview

This stress test uses a **simple relay pattern** with all intelligence in the CustomerAgent:

```
┌──────────────────────────────────────────────────────────────────────┐
│                      CUSTOMER AGENT (ADK)                            │
│                                                                      │
│   Model: gemini-2.0-flash (via Google ADK Runner)                   │
│                                                                      │
│   ┌────────────────────────────────────────────────────────────┐    │
│   │  FULL AUDIO PIPELINE:                                      │    │
│   │                                                            │    │
│   │  1. Transcribe μ-law audio → text (Gemini)                 │    │
│   │  2. Generate customer response (ADK Agent)                 │    │
│   │  3. Convert text → μ-law audio (Edge TTS)                  │    │
│   └────────────────────────────────────────────────────────────┘    │
│                          ▲               │                           │
│                  Agent   │               │ Customer                  │
│                  Audio   │               │ Audio                     │
│                          │               ▼                           │
│   ┌────────────────────────────────────────────────────────────┐    │
│   │                 MEDIATOR (Simple Relay)                    │    │
│   │                                                            │    │
│   │  • Receives agent audio → Passes to CustomerAgent          │    │
│   │  • Gets customer audio → Sends to IVR App                  │    │
│   │  • No AI logic - just relay                                │    │
│   └────────────────────────────────────────────────────────────┘    │
│                          ▲               │                           │
│                          │ μ-law 8kHz    │ μ-law 8kHz                │
│                          │ (agent voice) │ (customer voice)          │
└──────────────────────────┼───────────────┼───────────────────────────┘
                           │               │
                           │  WebSocket    │
                           │  /ws/phone    │
                           ▼               │
┌──────────────────────────────────────────────────────────────────────┐
│              YOUR IVR APPLICATION (Unchanged)                        │
│                                                                      │
│   Model: gemini-2.5-flash-native-audio-preview (Live API)           │
│                                                                      │
│   • Receives customer audio via Telnyx protocol                      │
│   • Processes with Gemini Live (real speech recognition)             │
│   • Calls shipping tools (validate_postal, calculate_rates)          │
│   • Responds with audio                                              │
└──────────────────────────────────────────────────────────────────────┘
```

## Models Used

| Component | Model | Purpose |
|-----------|-------|---------|
| **IVR App** | `gemini-2.5-flash-native-audio-preview` | Your production agent (Live API) |
| **Customer Agent** | `gemini-2.0-flash` | Full pipeline: transcription + response + TTS (ADK) |

The Customer Agent uses Google ADK (Agent Development Kit) for consistency with the main IVR application.

Configure models in `.env`:
```env
# Customer simulator model
CUSTOMER_MODEL=gemini-2.0-flash

# TTS provider and voice
TTS_PROVIDER=edge-tts
TTS_VOICE=en-CA-LiamNeural
```

## Files

| File | Description |
|------|-------------|
| `.env` | Configuration (models, server, TTS) |
| `customer_agent.py` | Customer agent with full audio pipeline (ADK + TTS) |
| `mediator_simulator.py` | Simple relay between IVR and CustomerAgent |
| `stress_test.py` | Main stress test runner |
| `run_stress_test.ps1` | PowerShell launcher |
| `telnyx_simulator.py` | Basic Telnyx protocol simulator (deprecated) |

## Installation

```powershell
# From project root
cd stress-test

# Install dependencies
uv sync
```

## Usage

### 1. Start the IVR Server (in a separate terminal)

```powershell
# From project root, go to the app folder
cd app
uv run python main.py
```

### 2. Run Stress Test (in another terminal)

```powershell
cd stress-test
.\run_stress_test.ps1 -Calls 10
```

### Options

```powershell
.\run_stress_test.ps1 -Calls 5           # 5 concurrent calls
.\run_stress_test.ps1 -Sequential        # Run one at a time
.\run_stress_test.ps1 -Verbose           # Debug logging
.\run_stress_test.ps1 -Delay 2.0         # 2 seconds between call starts
```

## What Gets Tested

| Component | Tested? | How |
|-----------|---------|-----|
| WebSocket /ws/phone | ✅ | Real connection with Telnyx protocol |
| Telnyx message format | ✅ | start/media/stop events |
| Audio encoding | ✅ | μ-law 8kHz ↔ PCM16 transcoding |
| Speech recognition | ✅ | Customer speaks real words via TTS |
| Agent understanding | ✅ | Agent must understand and respond |
| Tool calling | ✅ | validate_postal, calculate_rates |
| Multi-turn conversation | ✅ | Full shipping workflow |
| Concurrent connections | ✅ | Multiple simultaneous calls |

## Example Output

```
================================================================================
🔥 STRESS TEST: 5 Concurrent Telnyx Phone Calls (AI-to-AI)
================================================================================
Endpoint: /ws/phone (Telnyx WebSocket protocol)
Customer Model: gemini-2.0-flash
TTS: edge-tts (en-CA-LiamNeural)
Started at: 2026-01-24 14:30:00

Starting calls...

  📞 Call 1/5: [K2P 1L4 → M5V 3L9, 25x15x10cm] (id: a1b2c3d4)
  📞 Call 2/5: [H3Z 2Y7 → T2P 4R5, 30x20x15cm] (id: e5f6g7h8)
  ...
  ✅ Call a1b2c3d4: 45.2s, 120 sent/85 recv, 8 turns
  ✅ Call e5f6g7h8: 52.1s, 135 sent/92 recv, 9 turns

================================================================================
📊 STRESS TEST RESULTS
================================================================================

  Total Calls:        5
  Successful:         5 (100.0%)
  Failed:             0 (0.0%)
  
  Total Duration:     58.3 seconds
  Avg Call Time:      48.7 seconds
  Min Call Time:      42.1 seconds
  Max Call Time:      55.8 seconds

================================================================================

🎉 All calls completed successfully!
```

## Conversation Flow

Each simulated call follows this flow:

1. **Connect** - WebSocket to /ws/phone
2. **Agent Greeting** - "Hello! Welcome to SmartShip..."
3. **Customer Response** - "Hi, I need to ship a package"
4. **Dimensions** - "It's 25 by 15 by 10 centimeters"
5. **From Postal** - "K2P 1L4"
6. **To Postal** - "M5V 3L9"
7. **Rate Selection** - "I'll take the Expedited Parcel"
8. **Confirmation** - "Yes, please confirm"
9. **Goodbye** - "Thank you, goodbye"

The Customer Agent generates natural, contextual responses based on:
- Random package dimensions (10-50 × 10-40 × 5-30 cm)
- Random Canadian postal codes
- Random service preference

## Troubleshooting

### "edge-tts not installed"
```powershell
uv pip install edge-tts
```

### "pydub not installed"
```powershell
uv pip install pydub
# Also need ffmpeg for audio conversion
winget install ffmpeg
```

### "Server not running"
```powershell
cd app
uv run python main.py
```

### Transcription failing
- Check GOOGLE_API_KEY is set in app/.env
- The stress test loads the API key from there
