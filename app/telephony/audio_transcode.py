"""
Audio Transcoding Utilities for Telephony Integration

This module provides audio format conversion between telephony formats
(μ-law encoded) and the PCM16 format used by Gemini ADK.

Twilio uses:
    - μ-law encoding (G.711)
    - 8kHz sample rate
    - Mono channel

Gemini ADK uses:
    - PCM16 (linear PCM, 16-bit)
    - 16kHz input, 24kHz output
    - Mono channel

This module handles the conversion between these formats.
"""

import logging
from typing import Optional

# Import audioop - built-in for Python 3.10-3.12, external package for 3.13+
try:
    import audioop  # Built-in module for Python <= 3.12
except ImportError:
    try:
        import audioop_lts as audioop  # Backport for Python >= 3.13
    except ImportError:
        raise ImportError(
            "audioop module not available. "
            "For Python 3.13+, install: pip install audioop-lts"
        )

logger = logging.getLogger(__name__)


def transcode_mulaw_to_pcm16(
    mulaw_data: bytes,
    from_rate: int = 8000,
    to_rate: int = 16000
) -> bytes:
    """
    Convert μ-law encoded audio to PCM16 format with sample rate conversion.
    
    This is used for incoming audio from phone calls (Twilio → Gemini).
    
    Args:
        mulaw_data: μ-law encoded audio data (from Twilio)
        from_rate: Source sample rate in Hz (default: 8000 for phone quality)
        to_rate: Target sample rate in Hz (default: 16000 for Gemini)
    
    Returns:
        PCM16 encoded audio data at target sample rate
    
    Example:
        >>> mulaw_chunk = base64.b64decode(twilio_payload)
        >>> pcm16_chunk = transcode_mulaw_to_pcm16(mulaw_chunk)
        >>> # Send pcm16_chunk to Gemini
    """
    try:
        # Step 1: Decode μ-law to linear PCM (16-bit)
        # audioop.ulaw2lin converts μ-law to linear PCM
        # Second parameter is sample width: 2 bytes (16-bit)
        pcm_linear = audioop.ulaw2lin(mulaw_data, 2)
        
        # Step 2: Resample from source rate to target rate
        # audioop.ratecv(fragment, width, nchannels, inrate, outrate, state)
        # Returns (newfragment, newstate)
        if from_rate != to_rate:
            pcm_resampled, _ = audioop.ratecv(
                pcm_linear,
                2,  # Sample width: 2 bytes (16-bit)
                1,  # Mono channel
                from_rate,
                to_rate,
                None  # No state (for continuous resampling, you'd pass previous state)
            )
            return pcm_resampled
        else:
            return pcm_linear
            
    except Exception as e:
        logger.error(f"Error transcoding μ-law to PCM16: {e}", exc_info=True)
        raise


def transcode_pcm16_to_mulaw(
    pcm_data: bytes,
    from_rate: int = 24000,
    to_rate: int = 8000
) -> bytes:
    """
    Convert PCM16 audio to μ-law format with sample rate conversion.
    
    This is used for outgoing audio to phone calls (Gemini → Twilio).
    
    Args:
        pcm_data: PCM16 encoded audio data (from Gemini)
        from_rate: Source sample rate in Hz (default: 24000 for Gemini output)
        to_rate: Target sample rate in Hz (default: 8000 for phone quality)
    
    Returns:
        μ-law encoded audio data at target sample rate
    
    Example:
        >>> gemini_audio = event.content.parts[0].inline_data.data
        >>> mulaw_chunk = transcode_pcm16_to_mulaw(gemini_audio, from_rate=24000)
        >>> # Send mulaw_chunk to Twilio
    """
    try:
        # Step 1: Resample from source rate to target rate
        if from_rate != to_rate:
            pcm_resampled, _ = audioop.ratecv(
                pcm_data,
                2,  # Sample width: 2 bytes (16-bit)
                1,  # Mono channel
                from_rate,
                to_rate,
                None
            )
        else:
            pcm_resampled = pcm_data
        
        # Step 2: Encode linear PCM to μ-law
        # audioop.lin2ulaw converts linear PCM to μ-law
        mulaw_data = audioop.lin2ulaw(pcm_resampled, 2)
        
        return mulaw_data
        
    except Exception as e:
        logger.error(f"Error transcoding PCM16 to μ-law: {e}", exc_info=True)
        raise


def chunk_audio_for_streaming(
    audio_data: bytes,
    chunk_size: int = 160
) -> list[bytes]:
    """
    Split audio data into smaller chunks suitable for streaming.
    
    Twilio prefers smaller audio chunks for smoother playback.
    160 bytes = 20ms of μ-law audio at 8kHz (standard for telephony).
    
    Args:
        audio_data: Audio data to chunk
        chunk_size: Size of each chunk in bytes (default: 160 = 20ms)
    
    Returns:
        List of audio chunks
    
    Example:
        >>> mulaw_audio = transcode_pcm16_to_mulaw(gemini_output)
        >>> chunks = chunk_audio_for_streaming(mulaw_audio)
        >>> for chunk in chunks:
        >>>     # Send each chunk to Twilio
    """
    chunks = []
    for i in range(0, len(audio_data), chunk_size):
        chunk = audio_data[i:i + chunk_size]
        chunks.append(chunk)
    return chunks


# Audio format constants for reference
TWILIO_AUDIO_FORMAT = {
    'encoding': 'μ-law (G.711)',
    'sample_rate': 8000,
    'channels': 1,
    'bits_per_sample': 8,
}

GEMINI_INPUT_FORMAT = {
    'encoding': 'PCM16',
    'sample_rate': 16000,
    'channels': 1,
    'bits_per_sample': 16,
}

GEMINI_OUTPUT_FORMAT = {
    'encoding': 'PCM16',
    'sample_rate': 24000,
    'channels': 1,
    'bits_per_sample': 16,
}
