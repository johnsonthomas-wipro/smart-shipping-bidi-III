"""FastAPI application for SmartShip Voice Assistant with ADK Bidi-streaming."""

import asyncio
import base64
import json
import logging
import os
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Load environment variables from .env file BEFORE importing agent
load_dotenv(Path(__file__).parent / ".env")

# Import agent after loading environment variables
# pylint: disable=wrong-import-position
from shipping_agent.agent import agent, create_agent  # noqa: E402

# Import Telnyx telephony integration
from telephony import handle_telnyx_call  # noqa: E402

# Configure logging to both console and file
log_file = Path(__file__).parent / "app.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file, mode='w', encoding='utf-8'),  # UTF-8 for emojis
        logging.StreamHandler()  # Also print to console
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Logging to file: {log_file}")

# Suppress Pydantic serialization warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Application name constant
APP_NAME = "smartship-bidi"

# Configuration
GEMINI_API_KEY = os.getenv('GOOGLE_API_KEY', '')
SHOW_CONVERSATION = os.getenv('SHOW_CONVERSATION', 'false').lower() == 'true'
TELNYX_API_KEY = os.getenv('TELNYX_API_KEY', '')  # For Call Control API

# Pricing constants for Gemini 2.5 Flash Native Audio (per 1M tokens)
# Source: https://ai.google.dev/gemini-api/docs/pricing
PRICING = {
    "audio_input": 3.00,      # $3.00 per 1M audio input tokens
    "audio_output": 12.00,    # $12.00 per 1M audio output tokens
    "text_input": 0.50,       # $0.50 per 1M text input tokens (prompts)
    "text_output": 2.00,      # $2.00 per 1M text output tokens
}


@dataclass
class SessionMetrics:
    """Tracks usage metrics for a web session."""
    session_id: str = ""
    user_id: str = ""
    mode: str = "voice"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # Interaction counts
    audio_chunks_received: int = 0
    audio_chunks_sent: int = 0
    text_messages_received: int = 0
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
    
    def start(self, user_id: str, session_id: str, mode: str) -> None:
        """Mark session start."""
        self.user_id = user_id
        self.session_id = session_id
        self.mode = mode
        self.start_time = datetime.now()
    
    def end(self) -> None:
        """Mark session end."""
        self.end_time = datetime.now()
    
    @property
    def duration_seconds(self) -> float:
        """Calculate session duration in seconds."""
        if not self.start_time or not self.end_time:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()
    
    @property
    def calculated_output_tokens(self) -> int:
        """Calculate output tokens from total - prompt - thoughts."""
        if self.gemini_candidates_tokens > 0:
            return self.gemini_candidates_tokens
        return max(0, self.gemini_total_tokens - self.gemini_prompt_tokens - self.gemini_thoughts_tokens)
    
    def add_usage_metadata(self, usage_metadata) -> None:
        """Add token counts from a Gemini usageMetadata event."""
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
        
        # Parse prompt_tokens_details
        prompt_details = getattr(usage_metadata, 'prompt_tokens_details', None)
        if prompt_details and isinstance(prompt_details, list):
            for detail in prompt_details:
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
        
        # Calculate implied output tokens
        implied_output = max(0, total_tokens - prompt_tokens - thoughts_tokens)
        
        logger.info(f"📊 Usage #{self.usage_events_count}: prompt={prompt_tokens}, thoughts={thoughts_tokens}, "
                   f"candidates={candidates_tokens}, total={total_tokens}, implied_output={implied_output}")
        logger.info(f"📊 Details: text_in={self.gemini_text_input_tokens}, audio_in={self.gemini_audio_input_tokens}")
    
    def calculate_cost(self) -> dict:
        """Calculate cost breakdown using actual Gemini tokens."""
        if self.gemini_total_tokens > 0:
            # Use detailed input breakdown
            audio_in_cost = (self.gemini_audio_input_tokens / 1_000_000) * PRICING["audio_input"]
            text_in_cost = (self.gemini_text_input_tokens / 1_000_000) * PRICING["text_input"]
            
            # Calculate output - assume all output is audio for voice/ivr modes
            output_tokens = self.calculated_output_tokens
            if self.mode in ("voice", "ivr"):
                audio_out_cost = (output_tokens / 1_000_000) * PRICING["audio_output"]
                text_out_cost = 0
            else:
                audio_out_cost = 0
                text_out_cost = (output_tokens / 1_000_000) * PRICING["text_output"]
            
            # Thoughts are text-based internal reasoning
            thoughts_cost = (self.gemini_thoughts_tokens / 1_000_000) * PRICING["text_output"]
            
            return {
                "audio_input": audio_in_cost,
                "audio_output": audio_out_cost,
                "text_input": text_in_cost,
                "text_output": text_out_cost + thoughts_cost,
                "total": audio_in_cost + audio_out_cost + text_in_cost + text_out_cost + thoughts_cost
            }
        else:
            return {
                "audio_input": 0,
                "audio_output": 0,
                "text_input": 0,
                "text_output": 0,
                "total": 0
            }
    
    def print_summary(self) -> None:
        """Print session summary to logger."""
        costs = self.calculate_cost()
        
        using_actual = self.gemini_total_tokens > 0
        token_source = "ACTUAL (from Gemini)" if using_actual else "NO DATA"
        
        output_tokens = self.calculated_output_tokens
        
        # Determine output type based on mode
        output_type = "Audio" if self.mode in ("voice", "ivr") else "Text"
        
        if using_actual:
            token_section = f"""TOKEN USAGE - {token_source}:
  Usage events received:  {self.usage_events_count}
  ┌─ INPUT TOKENS ────────────────────
  │  Audio Input:     {self.gemini_audio_input_tokens:,} tokens
  │  Text Input:      {self.gemini_text_input_tokens:,} tokens  (system prompt + tools)
  │  PROMPT TOTAL:    {self.gemini_prompt_tokens:,} tokens
  ├─ OUTPUT TOKENS ───────────────────
  │  {output_type} Output:    {output_tokens:,} tokens  (calculated: total - prompt - thoughts)
  │  Thoughts:        {self.gemini_thoughts_tokens:,} tokens  (internal reasoning)
  ├─ TOTALS ──────────────────────────
  │  Cached:          {self.gemini_cached_tokens:,} tokens
  │  API Total:       {self.gemini_total_tokens:,} tokens
  └───────────────────────────────────"""
        else:
            token_section = f"""TOKEN USAGE - {token_source}:
  No usage data collected."""
        
        summary = f"""
{'='*80}
🌐 WEB SESSION SUMMARY
{'='*80}
User ID:        {self.user_id}
Session ID:     {self.session_id[:50]}{'...' if len(self.session_id) > 50 else ''}
Mode:           {self.mode}
Duration:       {self.duration_seconds:.1f} seconds ({self.duration_seconds/60:.2f} minutes)
Start:          {self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else 'N/A'}
End:            {self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else 'N/A'}

INTERACTIONS:
  Audio chunks received:  {self.audio_chunks_received:,}
  Audio chunks sent:      {self.audio_chunks_sent:,}
  Text messages:          {self.text_messages_received}
  Tool calls:             {self.tool_calls}

{token_section}

COST BREAKDOWN (Gemini 2.5 Flash Native Audio):
  Audio Input:    ${costs['audio_input']:.6f}  (@$3.00/1M tokens)
  Audio Output:   ${costs['audio_output']:.6f}  (@$12.00/1M tokens)
  Text Input:     ${costs['text_input']:.6f}  (@$0.50/1M tokens)
  Text Output:    ${costs['text_output']:.6f}  (@$2.00/1M tokens)
  {'─'*45}
  GEMINI TOTAL:   ${costs['total']:.6f} (~{costs['total']*100:.4f} cents)
{'='*80}"""
        
        logger.info(summary)

# ========================================
# Phase 1: Application Initialization (once at startup)
# ========================================

app = FastAPI()

# Mount static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Setup templates
templates = Jinja2Templates(directory=static_dir)

# Define your session service
session_service = InMemorySessionService()

# Define your runner
runner = Runner(app_name=APP_NAME, agent=agent, session_service=session_service)

@app.get("/")
async def root(request: Request):
    """Serve the index.html page with template rendering."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "show_conversation": SHOW_CONVERSATION}
    )

@app.websocket("/ws/{user_id}/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    session_id: str,
    proactivity: bool = False,
    affective_dialog: bool = False,
    mode: str = "voice",
) -> None:
    """WebSocket endpoint for bidirectional streaming with ADK.

    Args:
        websocket: The WebSocket connection
        user_id: User identifier
        session_id: Session identifier
        proactivity: Enable proactive audio (native audio models only)
        affective_dialog: Enable affective dialog (native audio models only)
        mode: Interaction mode - "voice" (with camera), "text" (chat), or "ivr" (audio-only)
    """
    logger.info(
        f"🔌 NEW CONNECTION: user={user_id}, session={session_id}, mode={mode}"
    )
    await websocket.accept()

    # Initialize session metrics
    metrics = SessionMetrics()
    metrics.start(user_id, session_id, mode)

    # ========================================
    # Phase 2: Session Initialization (once per streaming session)
    # ========================================

    # Create agent based on mode
    session_agent = create_agent(mode)
    
    # Create a mode-specific runner
    mode_runner = Runner(app_name=APP_NAME, agent=session_agent, session_service=session_service)

    # Automatically determine response modality based on mode and model architecture
    # Text mode: Always use TEXT response modality
    # Voice/IVR modes: Native audio models ONLY support AUDIO response modality
    model_name = session_agent.model
    is_native_audio = "native-audio" in model_name.lower()

    if mode == "text":
        # Text mode always uses TEXT response modality
        # No audio transcription, no speech config
        response_modalities = ["TEXT"]
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=response_modalities,
            input_audio_transcription=None,
            output_audio_transcription=None,
            # Explicitly disable speech config for text mode
            speech_config=None,
        )
        logger.debug(
            f"Text mode: {model_name}, using TEXT response modality"
        )
    elif is_native_audio:
        # Native audio models require AUDIO response modality
        # with audio transcription
        response_modalities = ["AUDIO"]

        # Build RunConfig with optional proactivity and affective dialog
        # These features are only supported on native audio models
        # Note: session_resumption is only for Vertex AI, not Google AI (API key)
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=response_modalities,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            proactivity=(
                types.ProactivityConfig(proactive_audio=True) if proactivity else None
            ),
            enable_affective_dialog=affective_dialog if affective_dialog else None,
        )
        logger.debug(
            f"Native audio model detected: {model_name}, "
            f"using AUDIO response modality, "
            f"proactivity={proactivity}, affective_dialog={affective_dialog}"
        )
    else:
        # Half-cascade models support TEXT response modality
        # for faster performance
        response_modalities = ["TEXT"]
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=response_modalities,
            input_audio_transcription=None,
            output_audio_transcription=None,
        )
        logger.debug(
            f"Half-cascade model detected: {model_name}, "
            "using TEXT response modality"
        )
        # Warn if user tried to enable native-audio-only features
        if proactivity or affective_dialog:
            logger.warning(
                f"Proactivity and affective dialog are only supported on native "
                f"audio models. Current model: {model_name}. "
                f"These settings will be ignored."
            )
    logger.debug(f"RunConfig created: {run_config}")

    # Get or create session (handles both new sessions and reconnections)
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if not session:
        await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )

    live_request_queue = LiveRequestQueue()

    # ========================================
    # Phase 3: Active Session (concurrent bidirectional communication)
    # ========================================
    
    # Shared state between tasks
    auto_close_task = None
    auto_close_lock = asyncio.Lock()
    workflow_complete = False  # Track if workflow has reached 'complete' state

    async def restart_auto_close_timer():
        """Restart the auto-close timer (used after user activity post-completion)."""
        nonlocal auto_close_task
        
        async def auto_close_after_timeout():
            try:
                await asyncio.sleep(60)
                logger.info("⏰ 60 seconds elapsed with no activity - closing connection")
                await websocket.close(code=1000, reason="Workflow complete - auto-closing after timeout")
            except asyncio.CancelledError:
                logger.info("⏰ Auto-close timer cancelled (user sent message)")
        
        async with auto_close_lock:
            # Cancel any existing timer
            if auto_close_task and not auto_close_task.done():
                auto_close_task.cancel()
            # Start new timer
            auto_close_task = asyncio.create_task(auto_close_after_timeout())
            logger.info("⏰ Restarting 60 second auto-close timer")

    async def upstream_task() -> None:
        """Receives messages from WebSocket and sends to LiveRequestQueue."""
        nonlocal auto_close_task, workflow_complete
        audio_chunk_count = 0
        try:
            while True:
                # Receive message from WebSocket (text or binary)
                message = await websocket.receive()
                
                # NOTE: Don't cancel timer on every message - audio chunks come 100+/second
                # Timer restart is handled only for TEXT messages below
                
                # Handle binary frames (audio data only)
                if "bytes" in message:
                    audio_data = message["bytes"]
                    audio_chunk_count += 1
                    metrics.audio_chunks_received += 1
                    if audio_chunk_count <= 2:  # Only log first 2 chunks
                        logger.info(f"✅ Received audio chunk #{audio_chunk_count}: {len(audio_data)} bytes")

                    audio_blob = types.Blob(
                        mime_type="audio/pcm;rate=16000", data=audio_data
                    )
                    live_request_queue.send_realtime(audio_blob)
                    # Don't log sending - too verbose
                    # NOTE: Don't restart timer on audio chunks - too frequent (100+ per second)
                    # Timer will restart when we detect actual speech turn (via transcript)
                elif "text" in message:
                    text_msg = message['text']
                    if text_msg and text_msg != 'undefined':
                        # Parse JSON to check if it's a structured message (dimensions, ping, etc.)
                        try:
                            data = json.loads(text_msg)
                            msg_type = data.get('type', 'text')
                            
                            if msg_type == 'ping':
                                logger.debug("Received keepalive ping, sending pong")
                                await websocket.send_text(json.dumps({"type": "pong"}))
                                continue  # Don't forward pings to ADK
                            
                            if msg_type == 'text':
                                text_content = data.get('text', '')
                                metrics.text_messages_received += 1
                                logger.info(f"📨 TEXT from client: {text_content[:100]}")
                                # Send text message to model using send_content()
                                # This works the same as the initial greeting - both native audio
                                # and half-cascade models support text input via Content objects
                                text_part = types.Content(
                                    role="user",
                                    parts=[types.Part.from_text(text=text_content)]
                                )
                                live_request_queue.send_content(content=text_part)
                                logger.info("✅ Text message sent to model")
                                
                                # Restart auto-close timer if workflow is complete
                                if workflow_complete:
                                    asyncio.create_task(restart_auto_close_timer())
                                continue
                        except json.JSONDecodeError:
                            # Not JSON, treat as plain text (shouldn't happen with current client)
                            logger.info(f"Received plain text message: {text_msg[:100]}")
                else:
                    logger.warning(f"Received unknown message type: {message.keys()}")
        except Exception as e:
            logger.error(f"Error in upstream_task: {e}", exc_info=True)
            raise

    async def downstream_task() -> None:
        """Receives Events from run_live() and sends to WebSocket."""
        
        nonlocal auto_close_task, workflow_complete
        
        # Register callback for workflow state changes from tools.py
        from shipping_agent.tools import set_workflow_state_callback
        
        def on_workflow_state_change(state: str, data: Dict[str, Any]) -> None:
            """Callback triggered when workflow state changes in tools.py"""
            nonlocal auto_close_task, workflow_complete
            
            workflow_message = json.dumps({
                'type': 'workflow_state_update',
                'workflow_state': state,
                'data': data
            })
            # Schedule the send_text coroutine to run
            asyncio.create_task(websocket.send_text(workflow_message))
            logger.info(f"📊 Sent workflow state to browser: {state}")
            
            # Start auto-close timer when workflow reaches 'complete'
            if state == 'complete':
                workflow_complete = True  # Set flag so timer restarts after user activity
                logger.info("⏰ Workflow complete - starting 60 second auto-close timer")
                asyncio.create_task(restart_auto_close_timer())
        
        set_workflow_state_callback(on_workflow_state_change)
        
        # Only send manual greeting if proactivity is disabled and mode is voice/ivr
        # When proactivity=true, the model starts talking automatically
        # In text mode, greeting is sent after connection is established
        logger.info("proactivity: %s, mode: %s", proactivity, mode)
        if not proactivity and mode in ("voice", "ivr"):
            async def send_initial_greeting():
                await asyncio.sleep(0.0001)  # Wait for connection to stabilize
                initial_content = types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="Hello")]
                )
                live_request_queue.send_content(content=initial_content)
                logger.info("🎤 Initial greeting trigger sent")
            
            # Start greeting task in background
            asyncio.create_task(send_initial_greeting())
        else:
            if mode in ("voice", "ivr"):
                logger.info("🎤 Proactivity enabled - model will start automatically")
            else:
                logger.info("💬 Text mode - waiting for user input")
        
        # Reconnection logic for Gemini session drops
        max_reconnect_attempts = 3
        reconnect_attempt = 0
        
        while reconnect_attempt < max_reconnect_attempts:
            try:
                if reconnect_attempt > 0:
                    logger.warning(f"🔄 Gemini reconnection attempt {reconnect_attempt}/{max_reconnect_attempts}")
                    await asyncio.sleep(0.5)
                    resume_msg = types.Content(
                        role="user",
                        parts=[types.Part.from_text(text="Please continue where we left off.")]
                    )
                    live_request_queue.send_content(content=resume_msg)
                
                async for event in mode_runner.run_live(
                    user_id=user_id,
                    session_id=session_id,
                    live_request_queue=live_request_queue,
                    run_config=run_config,
                ):
                    # Track usage metadata from Gemini
                    if hasattr(event, 'usage_metadata') and event.usage_metadata:
                        metrics.add_usage_metadata(event.usage_metadata)
                    
                    # Only log events without audio data and from agent
                    has_audio = False
                    
                    # Check if event contains audio in content.parts
                    if hasattr(event, 'content') and event.content:
                        if hasattr(event.content, 'parts'):
                            for part in event.content.parts:
                                if hasattr(part, 'inline_data') and part.inline_data:
                                    mime_type = getattr(part.inline_data, 'mime_type', '')
                                    if mime_type and 'audio' in mime_type:
                                        has_audio = True
                                        metrics.audio_chunks_sent += 1
                                        break
                    
                    # Check event author and content role
                    author = getattr(event, 'author', None)
                    content_role = getattr(event.content, 'role', None) if hasattr(event, 'content') and event.content else None
                    
                    # Only log non-audio events from agent with role='model'
                    agent_name = f"smartship_{mode}_agent"
                    if not has_audio and author == agent_name and content_role == 'model':
                        logger.info("Event from model: %s", event)
                    
                    # Restart timer when user speech is detected (voice mode user activity)
                    if workflow_complete and content_role == 'user':
                        logger.info("🎤 User speech detected - restarting auto-close timer")
                        asyncio.create_task(restart_auto_close_timer())
                    
                    event_json = event.model_dump_json(exclude_none=True, by_alias=True)            
                    await websocket.send_text(event_json)
                    
                    # Reset reconnect counter on successful event
                    reconnect_attempt = 0
                
                # Normal completion, exit the reconnect loop
                break
                
            except asyncio.CancelledError:
                break  # Task was cancelled, exit
            except Exception as e:
                error_str = str(e).lower()
                if "close frame" in error_str or "connection closed" in error_str or "websocket" in error_str:
                    reconnect_attempt += 1
                    logger.warning(f"🔄 Gemini session dropped ({e}), attempting reconnect...")
                    if reconnect_attempt >= max_reconnect_attempts:
                        logger.error(f"🔄 Max reconnection attempts reached")
                        break
                    continue
                else:
                    raise  # Re-raise non-recoverable errors
 
    # Run both tasks concurrently
    # Exceptions from either task will propagate and cancel the other task
    try:
        await asyncio.gather(upstream_task(), downstream_task())
    except WebSocketDisconnect:
        logger.info("❌ Client disconnected")
    except Exception as e:
        logger.error(f"❌ ERROR in streaming: {e}", exc_info=True)
    finally:
        # Mark session end and print summary
        metrics.end()
        metrics.print_summary()
        
        # Cancel auto-close timer if still running
        if auto_close_task and not auto_close_task.done():
            auto_close_task.cancel()
            logger.info("⏰ Cancelled auto-close timer during cleanup")
        
        # Reset workflow state for next connection
        from shipping_agent.tools import reset_workflow_state
        reset_workflow_state()
        
        logger.debug("Closing live_request_queue")
        live_request_queue.close()
        logger.info("✅ Connection cleanup complete")

@app.websocket("/ws/phone")
async def phone_websocket_endpoint(
    websocket: WebSocket,
) -> None:
    """
    Telnyx WebSocket endpoint for phone calls.
    
    This endpoint handles incoming phone calls via Telnyx:
    - Receives μ-law audio at 8kHz from phone network
    - Transcodes to PCM16 at 16kHz for Gemini
    - Uses IVR-mode agent (audio-only, no camera features)
    - Transcodes Gemini responses back to μ-law for phone
    
    The Call Control ID is extracted from the Telnyx 'start' event message,
    so no URL parameters are needed.
    
    TeXML Configuration Example:
        <Response>
            <Stream url="wss://your-domain.com/ws/phone" />
        </Response>
    
    Args:
        websocket: WebSocket connection from Telnyx
    """
    await handle_telnyx_call(
        websocket=websocket,
        call_control_id=None,  # Will be extracted from 'start' event
        app_name=APP_NAME,
        create_agent_func=create_agent,
        session_service=session_service,
    )


@app.post("/telnyx/webhook")
async def telnyx_webhook(request: Request):
    """
    Telnyx Call Control API webhook endpoint.
    
    Handles call events and starts media streaming when a call is answered.
    
    This endpoint should be configured in:
    - Telnyx Portal → Voice API Applications → Webhook URL
    """
    import httpx
    
    try:
        payload = await request.json()
        event_type = payload.get("data", {}).get("event_type")
        
        logger.info(f"📞 Telnyx webhook: {event_type}")
        logger.info(f"📞 Full payload: {json.dumps(payload, indent=2)}")
        
        if event_type == "call.initiated":
            # Call is coming in - answer it
            call_control_id = payload["data"]["payload"]["call_control_id"]
            call_leg_id = payload["data"]["payload"]["call_leg_id"]
            
            logger.info(f"📞 Call initiated: {call_control_id}")
            
            # Answer the call using Telnyx API
            async with httpx.AsyncClient() as client:
                answer_response = await client.post(
                    f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/answer",
                    headers={
                        "Authorization": f"Bearer {TELNYX_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "answering_machine_detection": "disabled",
                        "client_state": ""
                    }
                )
                logger.info(f"📞 Answer response: {answer_response.status_code}")
                
        elif event_type == "call.answered":
            # Call has been answered - start media streaming
            call_control_id = payload["data"]["payload"]["call_control_id"]
            
            logger.info(f"📞 Call answered: {call_control_id}")
            
            # Get WebSocket URL
            # Cloud Run uses x-forwarded-proto to indicate HTTPS
            forwarded_proto = request.headers.get("x-forwarded-proto", "")
            forwarded_host = request.headers.get("x-forwarded-host")
            host = forwarded_host or request.headers.get("host", "localhost:8000")
            
            # Use wss:// for production (HTTPS) or ws:// for local dev
            if forwarded_proto == "https" or forwarded_host or ".run.app" in host:
                scheme = "wss"
            else:
                scheme = "ws"
            
            ws_url = f"{scheme}://{host}/ws/phone"
            
            logger.info(f"📞 Starting stream to: {ws_url}")
            
            # Start media streaming using Telnyx API
            # Use RTP bidirectional mode for real-time audio streaming
            async with httpx.AsyncClient() as client:
                stream_response = await client.post(
                    f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/streaming_start",
                    headers={
                        "Authorization": f"Bearer {TELNYX_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "stream_url": ws_url,
                        "stream_track": "both_tracks",
                        "stream_bidirectional_mode": "rtp",
                        "stream_bidirectional_codec": "PCMU"
                    }
                )
                logger.info(f"📞 Stream start response: {stream_response.status_code}")
                if stream_response.status_code != 200:
                    logger.error(f"📞 Stream start failed: {stream_response.text}")
                    
        elif event_type == "call.hangup":
            logger.info(f"📞 Call ended")
            
        elif event_type == "streaming.started":
            logger.info(f"📞 Streaming started successfully")
            
        elif event_type == "streaming.stopped":
            logger.info(f"📞 Streaming stopped")
            
        elif event_type == "streaming.failed":
            logger.error(f"📞 Streaming failed: {payload}")
            
        return JSONResponse({"status": "ok"})
        
    except Exception as e:
        logger.error(f"📞 Error in Telnyx webhook: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/analyze-and-confirm")
async def analyze_and_confirm(request: Request):
    """Analyze captured images using Gemini Vision to measure package dimensions."""
    try:
        import google.generativeai as genai
        
        logger.info("="*80)
        logger.info("📸 CAMERA: Image analysis request received")
        
        data = await request.json()
        images = data.get('images', [])
        
        logger.info(f"Received {len(images)} images for analysis")
        
        if not images or len(images) < 3:
            logger.error(f"Insufficient images ({len(images)})")
            return JSONResponse({
                'success': False, 
                'error': 'Need at least 3 images for analysis'
            }, status_code=400)
        
        # Configure Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        #model = genai.GenerativeModel('gemini-2.0-flash-exp')
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = """You are analyzing MULTIPLE IMAGES of the same object from different angles to measure it accurately for shipping.

            CRITICAL INSTRUCTIONS:
            1. Look at ALL images provided - they show the SAME object from different angles
            2. Use visual cues (standard objects like credit cards, keyboards, hands, or packaging materials) for scale reference
            3. Provide measurements in CENTIMETERS
            4. Be conservative - if unsure, estimate slightly larger
            5. Round to nearest whole centimeter

            Analyze these images and provide:
            - Length (longest dimension in cm)
            - Width (medium dimension in cm)
            - Height (shortest dimension in cm)

            Respond ONLY with valid JSON in this exact format:
            {
            "length_cm": 25,
            "width_cm": 15,
            "height_cm": 10
            }

            Do not include any other text or explanation - ONLY the JSON object."""

        # Prepare images for Gemini
        image_parts = []
        for idx, image_item in enumerate(images):
            try:
                # Handle both formats: string or {image: string, angle: string}
                if isinstance(image_item, dict):
                    image_data = image_item.get('image', '')
                else:
                    image_data = image_item
                
                # Remove data URL prefix if present (data:image/jpeg;base64,...)
                if ',' in image_data:
                    image_data = image_data.split(',')[1]
                
                # Decode base64 to bytes
                image_bytes = base64.b64decode(image_data)
                
                image_parts.append({
                    'mime_type': 'image/jpeg',
                    'data': image_bytes
                })
                logger.info(f"  Image {idx + 1}: {len(image_bytes)} bytes")
            except Exception as e:
                logger.error(f"Failed to process image {idx + 1}: {str(e)}")
                continue
        
        if not image_parts:
            return JSONResponse({
                'success': False,
                'error': 'Failed to process any images'
            }, status_code=400)
        
        # Call Gemini Vision API
        logger.info("Calling Gemini Vision API for dimension analysis...")
        
        response = model.generate_content([prompt] + image_parts)
        result_text = response.text.strip()
        
        logger.info(f"Gemini response: {result_text}")
        
        # Parse JSON response
        # Remove markdown code blocks if present
        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0].strip()
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0].strip()
        
        dimensions = json.loads(result_text)
        
        logger.info(f"📏 Measured dimensions: {dimensions}")
        
        return JSONResponse({
            'success': True,
            'dimensions': {
                'length': dimensions.get('length_cm'),
                'width': dimensions.get('width_cm'),
                'height': dimensions.get('height_cm')
            }
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response as JSON: {str(e)}")
        logger.error(f"Raw response: {result_text}")
        return JSONResponse({
            'success': False,
            'error': 'Failed to parse dimension measurements'
        }, status_code=500)
    except Exception as e:
        logger.error(f"Image analysis error: {str(e)}", exc_info=True)
        return JSONResponse({
            'success': False,
            'error': str(e)
        }, status_code=500)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000,log_config=None,log_level="info")
