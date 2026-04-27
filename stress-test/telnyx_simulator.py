"""
Telnyx Call Simulator - Simulates a Telnyx phone call through the shipping workflow.

This module simulates what Telnyx does when connecting a phone call:
1. Connect to /ws/phone WebSocket endpoint
2. Send 'start' event with call metadata
3. Send 'media' events with μ-law audio (we'll use TTS-generated audio)
4. Receive 'media' events with agent audio responses
5. Send 'stop' event when done

For simplicity in testing, we simulate speech by sending text-to-speech audio
or by using a simple approach where we send audio representing spoken words.
"""

import asyncio
import audioop
import base64
import json
import logging
import random
import struct
import time
import uuid
import math
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import websockets

logger = logging.getLogger(__name__)


# Valid Canadian postal code first letters (by province/territory)
VALID_POSTAL_PREFIXES = {
    'A': 'Newfoundland and Labrador',
    'B': 'Nova Scotia',
    'C': 'Prince Edward Island',
    'E': 'New Brunswick',
    'G': 'Eastern Quebec',
    'H': 'Metropolitan Montreal',
    'J': 'Western Quebec',
    'K': 'Eastern Ontario',
    'L': 'Central Ontario',
    'M': 'Metropolitan Toronto',
    'N': 'Southwestern Ontario',
    'P': 'Northern Ontario',
    'R': 'Manitoba',
    'S': 'Saskatchewan',
    'T': 'Alberta',
    'V': 'British Columbia',
    'X': 'Northwest Territories/Nunavut',
    'Y': 'Yukon',
}

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
    error: Optional[str] = None
    transcript: List[str] = field(default_factory=list)


def generate_random_postal_code() -> str:
    """Generate a random valid Canadian postal code."""
    first_letter = random.choice(list(VALID_POSTAL_PREFIXES.keys()))
    digit1 = random.randint(0, 9)
    letter2 = random.choice('ABCEGHJKLMNPRSTVWXYZ')
    digit2 = random.randint(0, 9)
    letter3 = random.choice('ABCEGHJKLMNPRSTVWXYZ')
    digit3 = random.randint(0, 9)
    
    return f"{first_letter}{digit1}{letter2} {digit2}{letter3}{digit3}"


def generate_random_dimensions() -> Dict[str, int]:
    """Generate random package dimensions in cm."""
    return {
        'length': random.randint(5, 50),
        'width': random.randint(5, 40),
        'height': random.randint(5, 30),
    }


def generate_silence_mulaw(duration_ms: int = 100, sample_rate: int = 8000) -> bytes:
    """Generate silent μ-law audio."""
    num_samples = int(sample_rate * duration_ms / 1000)
    # μ-law silence is 0xFF (positive zero) or 0x7F (negative zero)
    return bytes([0xFF] * num_samples)


def generate_tone_mulaw(duration_ms: int = 500, frequency: int = 440, sample_rate: int = 8000) -> bytes:
    """Generate a tone as μ-law audio (simulates someone speaking)."""
    num_samples = int(sample_rate * duration_ms / 1000)
    
    # Generate PCM16 sine wave
    pcm_samples = []
    for i in range(num_samples):
        t = i / sample_rate
        # Mix a few frequencies to sound more like voice
        sample = (
            0.5 * math.sin(2 * math.pi * frequency * t) +
            0.3 * math.sin(2 * math.pi * (frequency * 1.5) * t) +
            0.2 * math.sin(2 * math.pi * (frequency * 2) * t)
        )
        pcm_value = int(sample * 16000)  # Not too loud
        pcm_value = max(-32768, min(32767, pcm_value))
        pcm_samples.append(pcm_value)
    
    # Pack as PCM16
    pcm_bytes = struct.pack(f'<{len(pcm_samples)}h', *pcm_samples)
    
    # Convert to μ-law
    mulaw_bytes = audioop.lin2ulaw(pcm_bytes, 2)
    
    return mulaw_bytes


def simulate_speech_audio(text: str, sample_rate: int = 8000) -> bytes:
    """
    Simulate speech audio for the given text.
    
    In a real scenario, you'd use TTS. Here we generate a tone
    with duration proportional to the text length.
    """
    # Rough estimate: 150 words per minute = 2.5 words per second
    # Average word is 5 characters
    words = len(text) / 5
    duration_ms = int(words / 2.5 * 1000)
    duration_ms = max(500, min(5000, duration_ms))  # Clamp between 0.5s and 5s
    
    # Generate "speech-like" audio (varying frequency)
    base_freq = random.randint(200, 400)  # Human voice range
    return generate_tone_mulaw(duration_ms, base_freq, sample_rate)


class TelnyxCallSimulator:
    """Simulates a Telnyx phone call through the shipping workflow."""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        from_postal: Optional[str] = None,
        to_postal: Optional[str] = None,
        dimensions: Optional[Dict[str, int]] = None,
        service: Optional[str] = None,
        timeout: float = 120.0,
    ):
        self.host = host
        self.port = port
        self.from_postal = from_postal or generate_random_postal_code()
        self.to_postal = to_postal or generate_random_postal_code()
        self.dimensions = dimensions or generate_random_dimensions()
        self.service = service or random.choice(SHIPPING_SERVICES)
        self.timeout = timeout
        
        # Telnyx-style IDs
        self.call_control_id = str(uuid.uuid4())
        self.call_session_id = str(uuid.uuid4())
        self.stream_id = str(uuid.uuid4())
        
        self.audio_chunks_sent = 0
        self.audio_chunks_received = 0
        self.transcript: List[str] = []
        self.start_time: Optional[float] = None
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        
        # Control flags
        self._receiving = True
        
    @property
    def ws_url(self) -> str:
        """Get the WebSocket URL (Telnyx endpoint)."""
        return f"ws://{self.host}:{self.port}/ws/phone"
    
    async def send_telnyx_start(self) -> None:
        """Send Telnyx 'start' event."""
        if not self.websocket:
            raise RuntimeError("WebSocket not connected")
        
        start_event = {
            "event": "start",
            "stream_id": self.stream_id,
            "start": {
                "call_control_id": self.call_control_id,
                "call_session_id": self.call_session_id,
                "user_id": f"stress-test-{self.call_control_id[:8]}",
            }
        }
        await self.websocket.send(json.dumps(start_event))
        logger.debug(f"[{self.call_control_id[:8]}] Sent 'start' event")
    
    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio as Telnyx 'media' event."""
        if not self.websocket:
            raise RuntimeError("WebSocket not connected")
        
        # Telnyx sends audio in chunks (typically 20ms = 160 bytes at 8kHz)
        chunk_size = 160  # 20ms of μ-law 8kHz
        
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            
            media_event = {
                "event": "media",
                "stream_id": self.stream_id,
                "media": {
                    "payload": base64.b64encode(chunk).decode('utf-8'),
                    "track": "inbound",
                    "timestamp": str(int(time.time() * 1000)),
                }
            }
            await self.websocket.send(json.dumps(media_event))
            self.audio_chunks_sent += 1
            
            # Small delay to simulate real-time streaming
            await asyncio.sleep(0.02)  # 20ms between chunks
    
    async def send_speech(self, text: str) -> None:
        """Simulate speaking the given text."""
        logger.info(f"[{self.call_control_id[:8]}] 🎤 Speaking: {text}")
        self.transcript.append(f"USER: {text}")
        
        # Generate audio for the speech
        audio = simulate_speech_audio(text)
        await self.send_audio(audio)
        
        # Brief pause after speaking
        await asyncio.sleep(0.3)
    
    async def send_stop(self) -> None:
        """Send Telnyx 'stop' event."""
        if not self.websocket:
            return
        
        stop_event = {
            "event": "stop",
            "stream_id": self.stream_id,
        }
        await self.websocket.send(json.dumps(stop_event))
        logger.debug(f"[{self.call_control_id[:8]}] Sent 'stop' event")
    
    async def receive_responses(self) -> None:
        """Background task to receive audio from server."""
        try:
            while self._receiving and self.websocket:
                try:
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=1.0
                    )
                    
                    data = json.loads(message)
                    event_type = data.get('event')
                    
                    if event_type == 'media':
                        self.audio_chunks_received += 1
                        # In a real test, we'd decode and analyze the audio
                        
                except asyncio.TimeoutError:
                    continue
                except json.JSONDecodeError:
                    # Binary data
                    self.audio_chunks_received += 1
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        except asyncio.CancelledError:
            pass
    
    async def wait_for_agent_response(self, timeout: float = 10.0) -> None:
        """Wait for agent to finish responding (detected by silence)."""
        initial_count = self.audio_chunks_received
        last_count = initial_count
        stable_time = 0
        
        start = time.time()
        while time.time() - start < timeout:
            await asyncio.sleep(0.5)
            
            if self.audio_chunks_received > last_count:
                # Still receiving
                last_count = self.audio_chunks_received
                stable_time = 0
            else:
                # Not receiving
                stable_time += 0.5
                if stable_time >= 2.0:  # 2 seconds of silence
                    break
        
        received = self.audio_chunks_received - initial_count
        if received > 0:
            logger.debug(f"[{self.call_control_id[:8]}] Received {received} audio chunks")
    
    async def run_conversation(self) -> None:
        """Run through the complete shipping conversation."""
        
        # Wait for agent's initial greeting
        logger.info(f"[{self.call_control_id[:8]}] Waiting for greeting...")
        await self.wait_for_agent_response(timeout=15.0)
        
        # Step 1: Respond to greeting
        await self.send_speech("Hello, I'd like to ship a package")
        await self.wait_for_agent_response()
        
        # Step 2: Provide dimensions
        dim_text = f"{self.dimensions['length']} by {self.dimensions['width']} by {self.dimensions['height']} centimeters"
        await self.send_speech(f"The package is {dim_text}")
        await self.wait_for_agent_response()
        
        # Step 3: Provide origin postal code
        # Spell it out for clarity
        postal_spoken = ' '.join(self.from_postal.replace(' ', ''))
        await self.send_speech(f"I'm shipping from {postal_spoken}")
        await self.wait_for_agent_response()
        
        # Step 4: Provide destination postal code
        postal_spoken = ' '.join(self.to_postal.replace(' ', ''))
        await self.send_speech(f"It's going to {postal_spoken}")
        await self.wait_for_agent_response()
        
        # Step 5: Select service
        await self.send_speech(f"I'll take the {self.service}")
        await self.wait_for_agent_response()
        
        # Step 6: Confirm
        await self.send_speech("Yes, please confirm")
        await self.wait_for_agent_response()
        
        logger.info(f"[{self.call_control_id[:8]}] ✅ Conversation complete!")
    
    async def run(self) -> CallResult:
        """Run the complete simulated Telnyx call."""
        self.start_time = time.time()
        error: Optional[str] = None
        success = False
        
        try:
            logger.info(f"[{self.call_control_id[:8]}] Connecting to {self.ws_url}")
            
            async with websockets.connect(
                self.ws_url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
            ) as websocket:
                self.websocket = websocket
                logger.info(f"[{self.call_control_id[:8]}] ✅ Connected!")
                
                # Start receiving responses in background
                receive_task = asyncio.create_task(self.receive_responses())
                
                try:
                    # Send Telnyx start event
                    await self.send_telnyx_start()
                    
                    # Run the conversation
                    await asyncio.wait_for(
                        self.run_conversation(),
                        timeout=self.timeout
                    )
                    
                    success = True
                    
                finally:
                    # Stop receiving and send stop event
                    self._receiving = False
                    receive_task.cancel()
                    try:
                        await receive_task
                    except asyncio.CancelledError:
                        pass
                    
                    await self.send_stop()
                
        except asyncio.TimeoutError:
            error = "Conversation timeout"
            logger.error(f"[{self.call_control_id[:8]}] ⏱️ Timeout!")
        except websockets.exceptions.ConnectionClosed as e:
            error = f"Connection closed: {e}"
            logger.error(f"[{self.call_control_id[:8]}] Connection closed: {e}")
        except Exception as e:
            error = str(e)
            logger.error(f"[{self.call_control_id[:8]}] ❌ Error: {e}")
        finally:
            self.websocket = None
        
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
            error=error,
            transcript=self.transcript,
        )


async def simulate_single_call(
    host: str = "localhost",
    port: int = 8000,
) -> CallResult:
    """Convenience function to simulate a single Telnyx call."""
    simulator = TelnyxCallSimulator(host=host, port=port)
    return await simulator.run()


if __name__ == "__main__":
    # Test single call
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    async def main():
        result = await simulate_single_call()
        print(f"\n{'='*60}")
        print(f"Call Result:")
        print(f"  Success: {result.success}")
        print(f"  Duration: {result.duration_seconds:.2f}s")
        print(f"  From: {result.from_postal} → To: {result.to_postal}")
        print(f"  Dimensions: {result.dimensions}")
        print(f"  Service: {result.selected_service}")
        print(f"  Audio chunks: {result.audio_chunks_sent} sent, {result.audio_chunks_received} received")
        if result.error:
            print(f"  Error: {result.error}")
        print(f"{'='*60}")
    
    asyncio.run(main())
