"""
Mediator Call Simulator - Simple relay for AI-to-AI conversation testing.

This module acts as a simple relay between:
1. YOUR IVR APP (Gemini 2.5 Flash Native Audio via Live API)
2. CUSTOMER AGENT (handles transcription, response, and TTS)

Flow:
- Connects to /ws/phone (Telnyx protocol)
- Receives audio from IVR app → Passes to Customer Agent
- Customer Agent returns audio → Sends back to IVR app

The mediator is intentionally simple - all intelligence is in the CustomerAgent.
"""

import asyncio
import base64
import io
import json
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import websockets
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent / ".env")

# Customer Agent handles all AI logic (transcription, response, TTS)
from customer_agent import CustomerAgent

logger = logging.getLogger(__name__)


class AudioSaver:
    """Saves audio files for debugging when SAVE_AUDIO=true."""
    
    def __init__(self, call_id: str):
        self.enabled = os.getenv("SAVE_AUDIO", "false").lower() == "true"
        self.call_id = call_id[:8]
        self.base_dir = Path(__file__).parent / os.getenv("AUDIO_LOG_DIR", "log/audio")
        self.call_dir: Optional[Path] = None
        self.turn_count = 0
        
        if self.enabled:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.call_dir = self.base_dir / f"{timestamp}_{self.call_id}"
            self.call_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"[{self.call_id}] Audio logging enabled: {self.call_dir}")
    
    def save_received(self, audio_data: bytes, turn: int) -> None:
        """Save audio received from IVR agent."""
        if not self.enabled or not self.call_dir:
            return
        filepath = self.call_dir / f"turn{turn:02d}_agent_received.ulaw"
        filepath.write_bytes(audio_data)
        logger.debug(f"[{self.call_id}] Saved agent audio: {filepath.name} ({len(audio_data)} bytes)")
    
    def save_sent(self, audio_data: bytes, turn: int) -> None:
        """Save audio sent to IVR agent (customer response)."""
        if not self.enabled or not self.call_dir:
            return
        filepath = self.call_dir / f"turn{turn:02d}_customer_sent.ulaw"
        filepath.write_bytes(audio_data)
        logger.debug(f"[{self.call_id}] Saved customer audio: {filepath.name} ({len(audio_data)} bytes)")


# Valid Canadian postal code first letters
VALID_POSTAL_PREFIXES = list('ABCEGHJKLMNPRSTVXY')

# Shipping service options
SHIPPING_SERVICES = ['Regular Parcel', 'Expedited Parcel', 'Xpresspost']


@dataclass
class CallResult:
    """Results from a simulated call."""
    call_id: str
    success: bool
    duration_seconds: float
    from_postal: str
    to_postal: str
    dimensions: Dict[str, int]
    selected_service: Optional[str] = None
    audio_chunks_sent: int = 0
    audio_chunks_received: int = 0
    turns: int = 0
    error: Optional[str] = None
    conversation_log: List[Dict[str, str]] = field(default_factory=list)


def generate_random_postal_code() -> str:
    """Generate a random valid Canadian postal code."""
    first = random.choice(VALID_POSTAL_PREFIXES)
    d1 = random.randint(0, 9)
    l2 = random.choice('ABCEGHJKLMNPRSTVWXYZ')
    d2 = random.randint(0, 9)
    l3 = random.choice('ABCEGHJKLMNPRSTVWXYZ')
    d3 = random.randint(0, 9)
    return f"{first}{d1}{l2} {d2}{l3}{d3}"


def generate_random_dimensions() -> Dict[str, int]:
    """Generate random package dimensions in cm."""
    return {
        'length': random.randint(10, 50),
        'width': random.randint(10, 40),
        'height': random.randint(5, 30),
    }


class MediatorCallSimulator:
    """Simple relay that connects the IVR app to the CustomerAgent."""
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        from_postal: Optional[str] = None,
        to_postal: Optional[str] = None,
        dimensions: Optional[Dict[str, int]] = None,
        service: Optional[str] = None,
        timeout: float = None,
    ):
        self.host = host or os.getenv("SERVER_HOST", "localhost")
        self.port = port or int(os.getenv("SERVER_PORT", "8000"))
        self.from_postal = from_postal or generate_random_postal_code()
        self.to_postal = to_postal or generate_random_postal_code()
        self.dimensions = dimensions or generate_random_dimensions()
        self.service = service or random.choice(SHIPPING_SERVICES)
        self.timeout = timeout or float(os.getenv("CALL_TIMEOUT", "120"))
        
        # Telnyx-style IDs
        self.call_control_id = str(uuid.uuid4())
        self.stream_id = str(uuid.uuid4())
        
        # Metrics
        self.audio_chunks_sent = 0
        self.audio_chunks_received = 0
        self.turns = 0
        self.start_time: Optional[float] = None
        
        # Customer agent - handles transcription, response generation, and TTS
        self.customer_agent = CustomerAgent(
            dimensions=self.dimensions,
            from_postal=self.from_postal,
            to_postal=self.to_postal,
            preferred_service=self.service,
        )
        
        # WebSocket connection
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        
        # Audio buffer for receiving agent audio
        self.audio_buffer = io.BytesIO()
        self._receiving = True
        
        # Audio saver for debugging
        self.audio_saver = AudioSaver(self.call_control_id)
        
    @property
    def ws_url(self) -> str:
        # Use wss:// for port 443 or .run.app hosts, otherwise ws://
        if self.port == 443 or ".run.app" in self.host:
            return f"wss://{self.host}/ws/phone"
        return f"ws://{self.host}:{self.port}/ws/phone"
    
    async def send_telnyx_start(self) -> None:
        """Send Telnyx 'start' event."""
        start_event = {
            "event": "start",
            "stream_id": self.stream_id,
            "start": {
                "call_control_id": self.call_control_id,
                "call_session_id": str(uuid.uuid4()),
            }
        }
        await self.websocket.send(json.dumps(start_event))
        logger.debug(f"[{self.call_control_id[:8]}] Sent 'start' event")
    
    async def send_audio(self, mulaw_data: bytes) -> None:
        """Send μ-law audio as Telnyx 'media' events."""
        chunk_size = 160  # 20ms at 8kHz
        
        for i in range(0, len(mulaw_data), chunk_size):
            chunk = mulaw_data[i:i + chunk_size]
            
            media_event = {
                "event": "media",
                "stream_id": self.stream_id,
                "media": {
                    "payload": base64.b64encode(chunk).decode('utf-8'),
                    "track": "inbound",
                }
            }
            await self.websocket.send(json.dumps(media_event))
            self.audio_chunks_sent += 1
            
            # Simulate real-time streaming
            await asyncio.sleep(0.02)
    
    async def send_telnyx_stop(self) -> None:
        """Send Telnyx 'stop' event."""
        stop_event = {"event": "stop", "stream_id": self.stream_id}
        await self.websocket.send(json.dumps(stop_event))
    
    async def receive_audio_loop(self) -> None:
        """Background task to receive audio from IVR app."""
        try:
            while self._receiving and self.websocket:
                try:
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=0.5
                    )
                    
                    data = json.loads(message)
                    if data.get('event') == 'media':
                        media = data.get('media', {})
                        payload = media.get('payload', '')
                        if payload:
                            audio_bytes = base64.b64decode(payload)
                            self.audio_buffer.write(audio_bytes)
                            self.audio_chunks_received += 1
                            
                except asyncio.TimeoutError:
                    continue
                except json.JSONDecodeError:
                    continue
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        except asyncio.CancelledError:
            pass
    
    async def wait_for_agent_turn(self, timeout: float = 15.0) -> bytes:
        """Wait for agent to finish speaking and return audio."""
        # Reset buffer
        self.audio_buffer = io.BytesIO()
        
        start = time.time()
        last_size = 0
        silence_time = 0
        
        while time.time() - start < timeout:
            await asyncio.sleep(0.3)
            
            current_size = self.audio_buffer.tell()
            if current_size > last_size:
                last_size = current_size
                silence_time = 0
            else:
                silence_time += 0.3
                # 1.5 seconds of silence = agent done speaking
                if silence_time >= 1.5 and current_size > 0:
                    break
        
        self.audio_buffer.seek(0)
        return self.audio_buffer.read()
    
    async def relay_customer_audio(self, mulaw_audio: bytes) -> None:
        """Relay audio from CustomerAgent to IVR app."""
        await self.send_audio(mulaw_audio)
    
    async def run_conversation(self) -> None:
        """Run the AI-to-AI conversation - mediator just relays audio."""
        max_turns = 15  # Safety limit
        
        for turn in range(max_turns):
            self.turns = turn + 1
            
            # Wait for agent to speak
            logger.info(f"[{self.call_control_id[:8]}] Waiting for agent (turn {turn + 1})...")
            agent_audio = await self.wait_for_agent_turn()
            
            if len(agent_audio) < 500:
                logger.warning(f"[{self.call_control_id[:8]}] No audio received")
                # For first turn, get opening from CustomerAgent
                if turn == 0:
                    customer_audio, text = await self.customer_agent.get_opening_audio()
                    logger.info(f"[{self.call_control_id[:8]}] [Customer] {text}")
                    self.audio_saver.save_sent(customer_audio, turn + 1)
                    await self.relay_customer_audio(customer_audio)
                    continue
                else:
                    await asyncio.sleep(1)
                    continue
            
            # Save received agent audio
            self.audio_saver.save_received(agent_audio, turn + 1)
            
            # Pass audio to CustomerAgent - it handles transcription, response, and TTS
            customer_audio, agent_text, customer_text = await self.customer_agent.process_agent_audio(agent_audio)
            
            logger.info(f"[{self.call_control_id[:8]}] [Agent] {agent_text[:100]}...")
            logger.info(f"[{self.call_control_id[:8]}] [Customer] {customer_text}")
            
            # Check if conversation is complete
            if self.customer_agent.is_conversation_complete(agent_text):
                # Get goodbye audio from CustomerAgent
                goodbye_audio, goodbye_text = await self.customer_agent.get_goodbye_audio()
                logger.info(f"[{self.call_control_id[:8]}] [Customer] {goodbye_text}")
                self.audio_saver.save_sent(goodbye_audio, turn + 1)
                await self.relay_customer_audio(goodbye_audio)
                logger.info(f"[{self.call_control_id[:8]}] Conversation complete!")
                return
            
            # Save and relay customer audio to IVR app
            self.audio_saver.save_sent(customer_audio, turn + 1)
            await self.relay_customer_audio(customer_audio)
            
            # Small pause between turns
            await asyncio.sleep(0.5)
        
        logger.warning(f"[{self.call_control_id[:8]}] Max turns reached")
    
    async def run(self) -> CallResult:
        """Run the complete simulated call."""
        self.start_time = time.time()
        error: Optional[str] = None
        success = False
        
        try:
            logger.info(f"[{self.call_control_id[:8]}] Connecting to {self.ws_url}")
            logger.info(f"[{self.call_control_id[:8]}] Package: {self.dimensions}, "
                       f"{self.from_postal} -> {self.to_postal}")
            
            async with websockets.connect(
                self.ws_url,
                ping_interval=20,
                ping_timeout=20,
            ) as websocket:
                self.websocket = websocket
                logger.info(f"[{self.call_control_id[:8]}] Connected!")
                
                # Start receiving audio in background
                receive_task = asyncio.create_task(self.receive_audio_loop())
                
                try:
                    # Send Telnyx start
                    await self.send_telnyx_start()
                    
                    # Run conversation
                    await asyncio.wait_for(
                        self.run_conversation(),
                        timeout=self.timeout
                    )
                    
                    success = True
                    
                finally:
                    self._receiving = False
                    receive_task.cancel()
                    try:
                        await receive_task
                    except asyncio.CancelledError:
                        pass
                    
                    await self.send_telnyx_stop()
                    
        except asyncio.TimeoutError:
            error = "Timeout"
        except Exception as e:
            error = str(e)
            logger.error(f"[{self.call_control_id[:8]}] Error: {e}")
        
        duration = time.time() - self.start_time
        
        return CallResult(
            call_id=self.call_control_id[:8],
            success=success,
            duration_seconds=duration,
            from_postal=self.from_postal,
            to_postal=self.to_postal,
            dimensions=self.dimensions,
            selected_service=self.service if success else None,
            audio_chunks_sent=self.audio_chunks_sent,
            audio_chunks_received=self.audio_chunks_received,
            turns=self.turns,
            error=error,
            conversation_log=self.customer_agent.conversation_log,
        )


async def simulate_single_call(
    host: str = None,
    port: int = None,
) -> CallResult:
    """Convenience function to simulate a single call."""
    simulator = MediatorCallSimulator(host=host, port=port)
    return await simulator.run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    async def main():
        result = await simulate_single_call()
        print(f"\n{'='*60}")
        print(f"Call Result: {'✅ SUCCESS' if result.success else '❌ FAILED'}")
        print(f"Duration: {result.duration_seconds:.2f}s")
        print(f"Route: {result.from_postal} → {result.to_postal}")
        print(f"Package: {result.dimensions}")
        print(f"Turns: {result.turns}")
        print(f"Audio: {result.audio_chunks_sent} sent, {result.audio_chunks_received} recv")
        if result.error:
            print(f"Error: {result.error}")
        print(f"\nConversation:")
        for entry in result.conversation_log:
            role = "🤖 Agent" if entry['role'] == 'agent' else "🎤 Customer"
            print(f"  {role}: {entry['text'][:80]}...")
        print(f"{'='*60}")
    
    asyncio.run(main())
