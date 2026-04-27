"""
Telephony Integration Package

This package contains all telephony-related functionality for connecting
the SmartShip Voice Assistant to phone networks via providers like Telnyx.

Modules:
    audio_transcode: Audio format conversion utilities (μ-law ↔ PCM16)
    telnyx_handler: Telnyx-specific WebSocket connection handler
"""

from .audio_transcode import transcode_mulaw_to_pcm16, transcode_pcm16_to_mulaw
from .telnyx_handler import handle_telnyx_call

__all__ = [
    'transcode_mulaw_to_pcm16',
    'transcode_pcm16_to_mulaw',
    'handle_telnyx_call',
]
