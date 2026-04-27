"""
Telnyx WebSocket Handler

This module handles bidirectional audio streaming between Telnyx phone calls
and the Gemini ADK agent using WebSockets.

Flow:
    1. Telnyx receives phone call
    2. TeXML directs call to create WebSocket connection
    3. This handler accepts connection and bridges audio between:
       - Phone caller (via Telnyx) ↔ Gemini ADK Agent
    4. Audio transcoding happens automatically (μ-law ↔ PCM16)

Telnyx WebSocket Message Format:
    - Incoming: {"event": "media", "payload": "base64_mulaw", "media_format": {"encoding": "audio/x-mulaw"}}
    - Outgoing: {"event": "media", "payload": "base64_mulaw"}
"""

import asyncio
import base64
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .audio_transcode import (
    transcode_mulaw_to_pcm16,
    transcode_pcm16_to_mulaw,
    chunk_audio_for_streaming
)

logger = logging.getLogger(__name__)


# Pricing constants (per 1M tokens) - Gemini 2.5 Flash Native Audio Preview
# https://ai.google.dev/pricing (as of Jan 2026)
PRICING = {
    "audio_input": 3.00,    # $3.00 per 1M tokens
    "audio_output": 12.00,  # $12.00 per 1M tokens
    "text_input": 0.50,     # $0.50 per 1M tokens
    "text_output": 2.00,    # $2.00 per 1M tokens
}

# Token estimation constants
AUDIO_TOKENS_PER_SECOND = 25  # ~25 tokens per second of audio
SYSTEM_PROMPT_TOKENS = 1200   # Estimated tokens for system prompt + tools


@dataclass
class CallMetrics:
    """Tracks metrics for a single IVR call session."""
    call_id: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # Byte counts (for token estimation fallback)
    audio_bytes_received: int = 0
    audio_bytes_sent: int = 0
    text_output_chars: int = 0
    
    # Interaction counts
    audio_chunks_received: int = 0
    audio_chunks_sent: int = 0
    tool_calls: int = 0
    
    # Actual Gemini-reported token counts (from usageMetadata events)
    gemini_prompt_tokens: int = 0          # Total input tokens reported by Gemini
    gemini_candidates_tokens: int = 0      # Total output tokens reported by Gemini
    gemini_audio_input_tokens: int = 0     # Audio input tokens (from details)
    gemini_audio_output_tokens: int = 0    # Audio output tokens (from details)
    gemini_text_input_tokens: int = 0      # Text input tokens (from details)
    gemini_text_output_tokens: int = 0     # Text output tokens (from details)
    gemini_thoughts_tokens: int = 0        # Thinking/reasoning tokens
    gemini_cached_tokens: int = 0          # Cached content tokens
    gemini_total_tokens: int = 0           # Total tokens from API
    usage_events_count: int = 0            # Number of usageMetadata events received
    
    def start(self, call_id: str) -> None:
        """Mark call start."""
        self.call_id = call_id
        self.start_time = datetime.now()
    
    def end(self) -> None:
        """Mark call end."""
        self.end_time = datetime.now()
    
    @property
    def duration_seconds(self) -> float:
        """Calculate call duration in seconds."""
        if not self.start_time or not self.end_time:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()
    
    @property
    def audio_input_tokens(self) -> int:
        """Estimate audio input tokens from bytes received.
        160 bytes = 20ms of μ-law 8kHz audio
        """
        duration_ms = (self.audio_bytes_received / 160) * 20
        duration_sec = duration_ms / 1000
        return int(duration_sec * AUDIO_TOKENS_PER_SECOND)
    
    @property
    def audio_output_tokens(self) -> int:
        """Estimate audio output tokens from bytes sent.
        PCM16 24kHz: 48000 bytes/sec, then downsampled to 8kHz μ-law
        """
        # Sent bytes are μ-law 8kHz (8000 bytes/sec)
        duration_sec = self.audio_bytes_sent / 8000
        return int(duration_sec * AUDIO_TOKENS_PER_SECOND)
    
    @property
    def text_input_tokens(self) -> int:
        """Fixed text input tokens (system prompt + tools)."""
        return SYSTEM_PROMPT_TOKENS
    
    @property
    def text_output_tokens(self) -> int:
        """Estimate text output tokens from agent thoughts."""
        return self.text_output_chars // 4
    
    def add_usage_metadata(self, usage_metadata) -> None:
        """Add token counts from a Gemini usageMetadata event.
        
        Gemini Live API returns usage metadata with this structure:
        {
            'prompt_token_count': 4121,
            'prompt_tokens_details': [
                {'modality': 'TEXT', 'token_count': 4057},
                {'modality': 'AUDIO', 'token_count': 64}
            ],
            'thoughts_token_count': 200,
            'candidates_token_count': None,  # Not reported in Live API
            'candidates_tokens_details': None,
            'total_token_count': 4879
        }
        
        Output tokens are calculated as: total - prompt - thoughts
        """
        self.usage_events_count += 1
        
        # Get values directly from object attributes
        prompt_tokens = getattr(usage_metadata, 'prompt_token_count', None) or 0
        candidates_tokens = getattr(usage_metadata, 'candidates_token_count', None) or 0
        thoughts_tokens = getattr(usage_metadata, 'thoughts_token_count', None) or 0
        cached_tokens = getattr(usage_metadata, 'cached_content_token_count', None) or 0
        total_tokens = getattr(usage_metadata, 'total_token_count', None) or 0
        
        # Accumulate totals
        self.gemini_prompt_tokens += prompt_tokens
        self.gemini_candidates_tokens += candidates_tokens
        self.gemini_thoughts_tokens += thoughts_tokens
        self.gemini_cached_tokens += cached_tokens
        self.gemini_total_tokens += total_tokens
        
        # Parse prompt_tokens_details - it's a LIST with modality and token_count
        prompt_details = getattr(usage_metadata, 'prompt_tokens_details', None)
        if prompt_details and isinstance(prompt_details, list):
            for detail in prompt_details:
                modality = None
                token_count = 0
                
                # Handle both dict and object formats
                if isinstance(detail, dict):
                    modality = detail.get('modality', '')
                    token_count = detail.get('token_count', 0) or 0
                else:
                    modality = getattr(detail, 'modality', None)
                    token_count = getattr(detail, 'token_count', 0) or 0
                
                # Convert modality enum to string if needed
                modality_str = str(modality).upper() if modality else ''
                
                if 'TEXT' in modality_str:
                    self.gemini_text_input_tokens += token_count
                elif 'AUDIO' in modality_str:
                    self.gemini_audio_input_tokens += token_count
        
        # Parse candidates_tokens_details (if present)
        candidates_details = getattr(usage_metadata, 'candidates_tokens_details', None)
        if candidates_details and isinstance(candidates_details, list):
            for detail in candidates_details:
                modality = None
                token_count = 0
                
                if isinstance(detail, dict):
                    modality = detail.get('modality', '')
                    token_count = detail.get('token_count', 0) or 0
                else:
                    modality = getattr(detail, 'modality', None)
                    token_count = getattr(detail, 'token_count', 0) or 0
                
                modality_str = str(modality).upper() if modality else ''
                
                if 'TEXT' in modality_str:
                    self.gemini_text_output_tokens += token_count
                elif 'AUDIO' in modality_str:
                    self.gemini_audio_output_tokens += token_count
        
        # Calculate implied output tokens if candidates_token_count is None/0
        # In Live API: total = prompt + thoughts + output
        # So: output = total - prompt - thoughts
        implied_output = max(0, total_tokens - prompt_tokens - thoughts_tokens)
        
        logger.info(f"📊 Usage #{self.usage_events_count}: prompt={prompt_tokens}, thoughts={thoughts_tokens}, "
                   f"candidates={candidates_tokens}, total={total_tokens}, implied_output={implied_output}")
        logger.info(f"📊 Details: text_in={self.gemini_text_input_tokens}, audio_in={self.gemini_audio_input_tokens}")
    
    @property
    def calculated_output_tokens(self) -> int:
        """Calculate output tokens from total - prompt - thoughts.
        
        Gemini Live API doesn't report candidates_token_count, so we derive it.
        """
        if self.gemini_candidates_tokens > 0:
            return self.gemini_candidates_tokens
        # Derive from totals: output = total - prompt - thoughts
        return max(0, self.gemini_total_tokens - self.gemini_prompt_tokens - self.gemini_thoughts_tokens)
    
    def calculate_cost(self) -> dict:
        """Calculate cost breakdown using actual Gemini tokens.
        
        For Gemini Live API:
        - Input cost = audio_input_tokens * audio_rate + text_input_tokens * text_rate
        - Output cost = calculated_output_tokens * audio_rate (assume audio output)
        - Thoughts cost = thoughts_tokens * text_rate (internal reasoning)
        """
        # Check if we have Gemini-reported tokens
        if self.gemini_total_tokens > 0:
            # Use detailed input breakdown
            audio_in_cost = (self.gemini_audio_input_tokens / 1_000_000) * PRICING["audio_input"]
            text_in_cost = (self.gemini_text_input_tokens / 1_000_000) * PRICING["text_input"]
            
            # Calculate output - assume all output is audio for voice calls
            output_tokens = self.calculated_output_tokens
            audio_out_cost = (output_tokens / 1_000_000) * PRICING["audio_output"]
            
            # Thoughts are text-based internal reasoning
            thoughts_cost = (self.gemini_thoughts_tokens / 1_000_000) * PRICING["text_output"]
            
            return {
                "audio_input": audio_in_cost,
                "audio_output": audio_out_cost,
                "text_input": text_in_cost,
                "text_output": thoughts_cost,  # thoughts count as text output
                "total": audio_in_cost + audio_out_cost + text_in_cost + thoughts_cost
            }
        else:
            # Fall back to byte-based estimates
            audio_in_cost = (self.audio_input_tokens / 1_000_000) * PRICING["audio_input"]
            audio_out_cost = (self.audio_output_tokens / 1_000_000) * PRICING["audio_output"]
            text_in_cost = (self.text_input_tokens / 1_000_000) * PRICING["text_input"]
            text_out_cost = (self.text_output_tokens / 1_000_000) * PRICING["text_output"]
            
            return {
                "audio_input": audio_in_cost,
                "audio_output": audio_out_cost,
                "text_input": text_in_cost,
                "text_output": text_out_cost,
                "total": audio_in_cost + audio_out_cost + text_in_cost + text_out_cost
            }
    
    def print_summary(self) -> None:
        """Print call summary to logger."""
        costs = self.calculate_cost()
        
        # Determine if we're using actual or estimated tokens
        using_actual = self.gemini_total_tokens > 0
        token_source = "ACTUAL (from Gemini)" if using_actual else "ESTIMATED (from bytes)"
        
        # Calculate derived output tokens
        output_tokens = self.calculated_output_tokens
        
        # Build token usage section
        if using_actual:
            token_section = f"""TOKEN USAGE - {token_source}:
  Usage events received:  {self.usage_events_count}
  ┌─ INPUT TOKENS ────────────────────
  │  Audio Input:     {self.gemini_audio_input_tokens:,} tokens
  │  Text Input:      {self.gemini_text_input_tokens:,} tokens  (system prompt + tools)
  │  PROMPT TOTAL:    {self.gemini_prompt_tokens:,} tokens
  ├─ OUTPUT TOKENS ───────────────────
  │  Audio Output:    {output_tokens:,} tokens  (calculated: total - prompt - thoughts)
  │  Thoughts:        {self.gemini_thoughts_tokens:,} tokens  (internal reasoning)
  ├─ TOTALS ──────────────────────────
  │  Cached:          {self.gemini_cached_tokens:,} tokens
  │  API Total:       {self.gemini_total_tokens:,} tokens
  └───────────────────────────────────"""
        else:
            # Fall back to byte-based estimates
            token_section = f"""TOKEN USAGE - {token_source}:
  Audio Input:    {self.audio_input_tokens:,} tokens
  Audio Output:   {self.audio_output_tokens:,} tokens
  Text Input:     {self.text_input_tokens:,} tokens (system prompt)
  Text Output:    {self.text_output_tokens:,} tokens"""
        
        summary = f"""
{'='*80}
📞 CALL SUMMARY
{'='*80}
Call ID:        {self.call_id[:50]}{'...' if len(self.call_id) > 50 else ''}
Duration:       {self.duration_seconds:.1f} seconds ({self.duration_seconds/60:.2f} minutes)
Start:          {self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else 'N/A'}
End:            {self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else 'N/A'}

INTERACTIONS:
  Audio chunks received:  {self.audio_chunks_received:,}
  Audio chunks sent:      {self.audio_chunks_sent:,}
  Tool calls:             {self.tool_calls}

{token_section}

COST BREAKDOWN (Gemini 2.5 Flash Native Audio):
  Audio Input:    ${costs['audio_input']:.6f}  (@$3.00/1M tokens)
  Audio Output:   ${costs['audio_output']:.6f}  (@$12.00/1M tokens)
  Text Input:     ${costs['text_input']:.6f}  (@$0.50/1M tokens)
  Text Output:    ${costs['text_output']:.6f}  (@$2.00/1M tokens)
  {'─'*45}
  GEMINI TOTAL:   ${costs['total']:.6f} (~{costs['total']*100:.4f} cents)
  
  + Telnyx (est): ${self.duration_seconds/60 * 0.017:.6f} (~{self.duration_seconds/60 * 0.017 * 100:.4f} cents)
  {'─'*45}
  CALL TOTAL:     ${costs['total'] + self.duration_seconds/60 * 0.017:.6f} (~{(costs['total'] + self.duration_seconds/60 * 0.017)*100:.4f} cents)
{'='*80}"""
        
        logger.info(summary)


async def handle_telnyx_call(
    websocket: WebSocket,
    call_control_id: Optional[str],
    app_name: str,
    create_agent_func,
    session_service: InMemorySessionService,
) -> None:
    """
    Handle a Telnyx WebSocket connection for a phone call.
    
    This function manages the complete lifecycle of a phone call:
    - Accepts WebSocket connection from Telnyx
    - Creates IVR-mode agent (audio-only, no camera)
    - Bridges audio between phone and Gemini ADK
    - Handles audio transcoding automatically
    - Manages session cleanup
    
    Args:
        websocket: FastAPI WebSocket connection from Telnyx
        call_control_id: Telnyx Call Control ID (can be None - will be extracted from 'start' event)
        app_name: Application name for ADK
        create_agent_func: Function to create agent (e.g., create_agent("ivr"))
        session_service: ADK session service for state management
    
    Raises:
        WebSocketDisconnect: When call ends
    """
    # Initialize call metrics
    metrics = CallMetrics()
    
    logger.info("="*80)
    logger.info(f"📞 NEW CALL - Waiting for Telnyx stream...")
    logger.info("="*80)
    
    await websocket.accept()
    
    # Call Control ID will be extracted from the 'start' event
    # Initialize user_id and session_id as None until we get the Call Control ID
    user_id = None
    session_id = None
    
    # Create IVR-mode agent (audio-only, uses system_prompt_ivr.txt)
    session_agent = create_agent_func("ivr")
    # logger.info(f"📞 Created IVR agent with model: {session_agent.model}")
    
    # Create runner for this phone call
    phone_runner = Runner(
        app_name=app_name,
        agent=session_agent,
        session_service=session_service
    )
    
    # Session will be created after receiving 'start' event with Call Control ID
    
    # Configure for audio streaming (native audio model)
    # NOTE: ProactivityConfig not supported with gemini-2.5-flash-native-audio-preview
    # We'll trigger greeting manually by sending "Hello" message on call start
    run_config = RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=["AUDIO"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )
    
    live_request_queue = LiveRequestQueue()
    
    # Telnyx call metadata
    call_started = False
    stream_id = None  # Will be set from 'start' event
    
    # Event to signal when 'start' event is received and session is ready
    session_ready = asyncio.Event()
    
    async def upstream_task() -> None:
        """
        Receives audio from Telnyx phone call and sends to Gemini.
        
        Handles Telnyx WebSocket events:
        - 'start': Call begins, store call metadata
        - 'media': Audio data from caller
        - 'stop': Call ends
        """
        nonlocal call_started, stream_id
        
        audio_chunk_count = 0
        
        try:
            while True:
                # Receive text message from Telnyx (JSON)
                message = await websocket.receive_text()
                data = json.loads(message)
                event_type = data.get('event')
                
                if event_type == 'start':
                    # Call started - extract Call Control ID and store metadata
                    nonlocal user_id, session_id
                    
                    # Telnyx puts the data inside a "start" object
                    start_data = data.get('start', {})
                    extracted_call_control_id = start_data.get('call_control_id')
                    call_session_id = start_data.get('call_session_id')
                    stream_id = data.get('stream_id')  # Capture stream_id for responses
                    call_started = True
                    
                    # Start tracking metrics
                    metrics.start(extracted_call_control_id or "unknown")
                    logger.info(f"📞 CALL STARTED: {extracted_call_control_id}")
                    
                    # Now that we have Call Control ID, initialize session
                    user_id = f"phone_{extracted_call_control_id}"
                    session_id = extracted_call_control_id
                    
                    # Create session (delete existing one first if it exists from a previous attempt)
                    try:
                        await session_service.delete_session(
                            app_name=app_name,
                            user_id=user_id,
                            session_id=session_id
                        )
                    except Exception:
                        pass  # Session didn't exist, that's fine
                    
                    await session_service.create_session(
                        app_name=app_name,
                        user_id=user_id,
                        session_id=session_id
                    )
                    
                    # Signal that session is ready for downstream_task to start
                    session_ready.set()
                    
                    # Send greeting to start conversation
                    # This triggers the IVR agent to introduce itself
                    greeting = types.Content(
                        role="user",
                        parts=[types.Part.from_text(text="Hello")]
                    )
                    live_request_queue.send_content(content=greeting)
                    
                elif event_type == 'media':
                    # Audio data from caller
                    if not call_started:
                        continue
                    
                    # Extract μ-law audio payload from nested media object
                    media_data = data.get('media', {})
                    mulaw_b64 = media_data.get('payload', '')
                    track = media_data.get('track', 'unknown')
                    
                    # Only process inbound audio (from caller), not outbound (our audio)
                    if track != 'inbound':
                        continue
                        
                    if not mulaw_b64:
                        continue
                        
                    mulaw_bytes = base64.b64decode(mulaw_b64)
                    
                    # Track metrics
                    audio_chunk_count += 1
                    metrics.audio_chunks_received += 1
                    metrics.audio_bytes_received += len(mulaw_bytes)
                    
                    # Transcode μ-law 8kHz → PCM16 16kHz
                    pcm16_data = transcode_mulaw_to_pcm16(mulaw_bytes)
                    
                    # Send to Gemini
                    audio_blob = types.Blob(
                        mime_type="audio/pcm;rate=16000",
                        data=pcm16_data
                    )
                    live_request_queue.send_realtime(audio_blob)
                    
                elif event_type == 'stop':
                    # Call ended
                    break
                    
                elif event_type == 'connected':
                    # WebSocket connection established
                    pass
                    
                elif event_type == 'mark':
                    # Mark event (used for synchronization, can be ignored)
                    pass
                
                elif event_type == 'ping':
                    # Respond to keepalive ping with pong
                    pong_event = {"event": "pong", "stream_id": stream_id}
                    await websocket.send_text(json.dumps(pong_event))
                    logger.debug("📞 Responded to ping with pong")
                    
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass  # Normal call end or task cancelled
        except json.JSONDecodeError as e:
            logger.error(f"📞 Failed to parse Telnyx message: {e}")
        except Exception as e:
            logger.error(f"📞 Error in upstream_task: {e}")
    
    async def downstream_task() -> None:
        """
        Receives audio from Gemini and sends to Telnyx phone call.
        
        - Extracts audio from Gemini events
        - Transcodes PCM16 24kHz → μ-law 8kHz
        - Chunks audio for smooth streaming
        - Sends to Telnyx in proper format
        - Handles Gemini session drops with automatic reconnection
        """
        # Wait for session to be ready (after 'start' event)
        await session_ready.wait()
        
        response_count = 0
        max_reconnect_attempts = 3
        reconnect_attempt = 0
        
        while reconnect_attempt < max_reconnect_attempts:
            try:
                if reconnect_attempt > 0:
                    logger.warning(f"📞 Gemini reconnection attempt {reconnect_attempt}/{max_reconnect_attempts}")
                    # Brief pause before reconnecting
                    await asyncio.sleep(0.5)
                    # Re-trigger conversation with context
                    resume_msg = types.Content(
                        role="user",
                        parts=[types.Part.from_text(text="Please continue where we left off.")]
                    )
                    live_request_queue.send_content(content=resume_msg)
                
                async for event in phone_runner.run_live(
                    user_id=user_id,
                    session_id=session_id,
                    live_request_queue=live_request_queue,
                    run_config=run_config,
                ):
                    # Extract audio from event - check multiple possible structures
                    audio_data = None
                    
                    # Method 1: Check event.content.parts[].inline_data
                    if hasattr(event, 'content') and event.content:
                        if hasattr(event.content, 'parts'):
                            for part in event.content.parts:
                                if hasattr(part, 'inline_data') and part.inline_data:
                                    mime_type = getattr(part.inline_data, 'mime_type', '')
                                    if 'audio' in mime_type:
                                        audio_data = part.inline_data.data
                                        break
                    
                    # Method 2: Check event.server_content.model_turn.parts[].inline_data (Gemini Live format)
                    if not audio_data and hasattr(event, 'server_content'):
                        server_content = event.server_content
                        if hasattr(server_content, 'model_turn') and server_content.model_turn:
                            if hasattr(server_content.model_turn, 'parts'):
                                for part in server_content.model_turn.parts:
                                    if hasattr(part, 'inline_data') and part.inline_data:
                                        mime_type = getattr(part.inline_data, 'mime_type', '')
                                        if 'audio' in mime_type:
                                            audio_data = part.inline_data.data
                                            break
                    
                    # Method 3: Direct data attribute
                    if not audio_data and hasattr(event, 'data'):
                        if isinstance(event.data, bytes):
                            audio_data = event.data
                    
                    if audio_data:
                        # Got audio from Gemini - track metrics
                        response_count += 1
                        metrics.audio_chunks_sent += 1
                        
                        # Transcode PCM16 24kHz → μ-law 8kHz
                        mulaw_data = transcode_pcm16_to_mulaw(
                            audio_data,
                            from_rate=24000,
                            to_rate=8000
                        )
                        
                        # Track bytes sent
                        metrics.audio_bytes_sent += len(mulaw_data)
                        
                        # Send as single payload to Telnyx with proper format
                        # Include stream_id for bidirectional streaming
                        mulaw_b64 = base64.b64encode(mulaw_data).decode('utf-8')
                        
                        telnyx_msg = json.dumps({
                            "event": "media",
                            "stream_id": stream_id,
                            "media": {
                                "payload": mulaw_b64
                            }
                        })
                        
                        try:
                            await websocket.send_text(telnyx_msg)
                        except Exception as e:
                            logger.error(f"📞 Failed to send to Telnyx: {e}")
                            break
                    
                    # Track text output (agent thoughts/transcriptions)
                    if hasattr(event, 'content') and event.content:
                        if hasattr(event.content, 'parts'):
                            for part in event.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    metrics.text_output_chars += len(part.text)
                                    # Check for tool calls
                                    if 'function_call' in str(type(part)).lower():
                                        metrics.tool_calls += 1
                    
                    # Extract actual token counts from Gemini usageMetadata
                    # Check multiple possible attribute names (ADK uses snake_case, Gemini uses camelCase)
                    usage_metadata = None
                    if hasattr(event, 'usage_metadata') and event.usage_metadata:
                        usage_metadata = event.usage_metadata
                    elif hasattr(event, 'usageMetadata') and event.usageMetadata:
                        usage_metadata = event.usageMetadata
                    
                    if usage_metadata:
                        metrics.add_usage_metadata(usage_metadata)
                        logger.debug(f"📊 Token event: prompt={getattr(usage_metadata, 'prompt_token_count', 'N/A')}, "
                                    f"candidates={getattr(usage_metadata, 'candidates_token_count', 'N/A')}")
                    
                    # Reset reconnect counter on successful event processing
                    reconnect_attempt = 0
                
                # Normal completion of async for loop, exit while loop
                break
                                
            except asyncio.CancelledError:
                break  # Task was cancelled, exit the reconnect loop
            except Exception as e:
                error_str = str(e).lower()
                # Check if this is a recoverable Gemini session drop
                if "close frame" in error_str or "connection closed" in error_str or "websocket" in error_str:
                    reconnect_attempt += 1
                    logger.warning(f"📞 Gemini session dropped ({e}), attempting reconnect...")
                    if reconnect_attempt >= max_reconnect_attempts:
                        logger.error(f"📞 Max reconnection attempts reached, ending call")
                        break
                    continue  # Try reconnecting
                else:
                    logger.error(f"📞 Error in downstream_task: {e}")
                    break  # Non-recoverable error
    
    # Run both tasks concurrently
    upstream = asyncio.create_task(upstream_task())
    downstream = asyncio.create_task(downstream_task())
    
    try:
        # Wait for either task to complete (usually upstream ends when call disconnects)
        done, pending = await asyncio.wait(
            [upstream, downstream],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel any pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
                
    except Exception as e:
        logger.error(f"📞 Error handling call: {e}")
        # Cancel both tasks on error
        upstream.cancel()
        downstream.cancel()
        
    finally:
        # End metrics tracking
        metrics.end()
        
        # Cleanup
        live_request_queue.close()
        
        # Reset workflow state for next call
        try:
            from shipping_agent.tools import reset_workflow_state
            reset_workflow_state()
        except Exception:
            pass  # Ignore reset errors
        
        # Print call summary
        metrics.print_summary()
