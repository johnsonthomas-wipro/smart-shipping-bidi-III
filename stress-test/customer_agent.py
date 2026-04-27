"""
Customer Agent - Simulates a customer calling to ship a package.

Uses Google ADK (Agent Development Kit) for consistency with the main IVR app.
Handles the full audio pipeline: transcription → response generation → TTS.
"""

import asyncio
import audioop
import io
import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent / ".env")

from google import genai
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

logger = logging.getLogger(__name__)

# Initialize Gemini client
genai_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# Global semaphore to limit concurrent CustomerAgent API calls
# This prevents overwhelming Gemini with too many simultaneous requests
MAX_CONCURRENT_CUSTOMER_AGENTS = int(os.getenv("MAX_CONCURRENT_CUSTOMER_AGENTS", "20"))
_customer_agent_semaphore: Optional[asyncio.Semaphore] = None

def get_customer_agent_semaphore() -> asyncio.Semaphore:
    """Get or create the global semaphore for CustomerAgent concurrency control."""
    global _customer_agent_semaphore
    if _customer_agent_semaphore is None:
        _customer_agent_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CUSTOMER_AGENTS)
    return _customer_agent_semaphore


def create_customer_system_prompt(
    length: int,
    width: int, 
    height: int,
    from_postal: str,
    to_postal: str,
    preferred_service: str,
) -> str:
    """Create a system prompt for the customer agent with specific package details."""
    
    return f"""You are a customer calling SmartShip to get shipping rates for a package.

YOUR PACKAGE DETAILS (use these when asked):
- Dimensions: {length} centimeters by {width} centimeters by {height} centimeters
- Shipping FROM postal code: {from_postal}
- Shipping TO postal code: {to_postal}  
- Your preferred shipping service: {preferred_service}

CONVERSATION RULES:
1. You are on a PHONE CALL. Speak naturally and conversationally.
2. Keep responses SHORT - 1-2 sentences maximum.
3. Only provide information when the agent asks for it.
4. Don't volunteer all information at once - wait to be asked.
5. When spelling postal codes, say each character clearly (e.g., "K 2 P 1 L 4").

RESPONSE GUIDELINES:

When agent greets you:
- Say something like "Hi, I need to ship a package" or "Hello, I'd like to get shipping rates"

When asked for dimensions:
- Say "{length} by {width} by {height} centimeters" or "It's {length} centimeters long, {width} wide, and {height} tall"

When asked for pickup/origin postal code:
- Say "I'm shipping from {from_postal}" or just "{from_postal}"

When asked for destination postal code:
- Say "It's going to {to_postal}" or just "{to_postal}"

When rates are presented:
- Select your preferred service: "{preferred_service}"
- Say something like "I'll take the {preferred_service}" or "The {preferred_service} please"

When asked to confirm:
- Say "Yes" or "Yes, please confirm" or "That's correct"

When transaction is complete:
- Say "Thank you, goodbye" or "Thanks, bye"

IMPORTANT:
- Stay in character as a customer
- Don't explain what you're doing, just do it
- If you don't understand something, ask the agent to repeat
- Be polite but brief
"""


@dataclass
class CustomerSession:
    """Holds the customer agent session state."""
    agent: Agent
    runner: Runner
    session_service: InMemorySessionService
    user_id: str
    session_id: str
    

class CustomerAgent:
    """Customer Agent that handles full audio pipeline.
    
    Receives μ-law audio → Transcribes → Generates response → TTS → Returns μ-law audio
    """
    
    def __init__(
        self,
        dimensions: Dict[str, int],
        from_postal: str,
        to_postal: str,
        preferred_service: str,
    ):
        """Initialize customer agent with package details."""
        self.dimensions = dimensions
        self.from_postal = from_postal
        self.to_postal = to_postal
        self.preferred_service = preferred_service
        
        # Create the agent
        self.model = os.getenv("CUSTOMER_MODEL", "gemini-2.0-flash")
        self.agent = self._create_agent()
        
        # Create session service and runner
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            agent=self.agent,
            app_name="customer_simulator",
            session_service=self.session_service,
        )
        
        # Session IDs
        self.user_id = "stress_test_user"
        self.session_id = f"stress_test_session_{id(self)}"
        
        # Session will be created on first use by the runner
        self._session_initialized = False
        
        # TTS settings
        self.tts_voice = os.getenv("TTS_VOICE", "en-CA-LiamNeural")
        
        # Conversation log
        self.conversation_log: List[Dict[str, str]] = []
        
    def _create_agent(self) -> Agent:
        """Create the ADK Agent."""
        system_prompt = create_customer_system_prompt(
            length=self.dimensions['length'],
            width=self.dimensions['width'],
            height=self.dimensions['height'],
            from_postal=self.from_postal,
            to_postal=self.to_postal,
            preferred_service=self.preferred_service,
        )
        
        return Agent(
            name="customer_simulator",
            model=self.model,
            instruction=system_prompt,
            tools=[],  # No tools needed - customer just talks
        )
    
    async def transcribe_audio(self, mulaw_audio: bytes) -> str:
        """Transcribe μ-law audio to text using Gemini.
        
        Args:
            mulaw_audio: μ-law 8kHz audio bytes
            
        Returns:
            Transcribed text
        """
        if len(mulaw_audio) < 1000:
            return ""
        
        try:
            # Convert μ-law to PCM16
            pcm_audio = audioop.ulaw2lin(mulaw_audio, 2)
            
            # Convert PCM to WAV format (Gemini needs proper audio format)
            import wave
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(8000)
                wav_file.writeframes(pcm_audio)
            wav_buffer.seek(0)
            wav_data = wav_buffer.read()
            
            # Use Gemini for transcription (with concurrency control)
            from google.genai import types
            
            semaphore = get_customer_agent_semaphore()
            async with semaphore:
                response = genai_client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[
                        "Transcribe this audio. Return ONLY the spoken words, nothing else.",
                        types.Part.from_bytes(
                            data=wav_data,
                            mime_type="audio/wav",
                        ),
                    ],
                )
            
            return response.text.strip()
            
        except Exception as e:
            logger.warning(f"Transcription failed: {e}")
            return "[transcription failed]"
    
    async def text_to_speech(self, text: str) -> bytes:
        """Convert text to μ-law audio using Edge TTS.
        
        Args:
            text: Text to speak
            
        Returns:
            μ-law 8kHz audio bytes
        """
        try:
            import edge_tts
            from pydub import AudioSegment
            
            logger.debug(f"TTS starting for: {text[:50]}...")
            
            # Generate MP3 audio
            communicate = edge_tts.Communicate(text, self.tts_voice)
            
            audio_data = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.write(chunk["data"])
            
            audio_data.seek(0)
            mp3_data = audio_data.read()
            logger.debug(f"TTS generated {len(mp3_data)} bytes MP3")
            
            # Convert MP3 to μ-law 8kHz
            audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))
            audio = audio.set_channels(1)
            audio = audio.set_frame_rate(8000)
            audio = audio.set_sample_width(2)
            
            pcm_data = audio.raw_data
            mulaw_data = audioop.lin2ulaw(pcm_data, 2)
            logger.debug(f"TTS converted to {len(mulaw_data)} bytes ulaw")
            
            return mulaw_data
            
        except Exception as e:
            logger.error(f"TTS failed: {e}")
            raise
    
    async def _ensure_session(self) -> None:
        """Ensure session is created before first use."""
        if not self._session_initialized:
            await self.session_service.create_session(
                app_name="customer_simulator",
                user_id=self.user_id,
                session_id=self.session_id,
            )
            self._session_initialized = True
    
    async def _get_text_response(self, agent_message: str) -> str:
        """Get customer's text response to what the IVR agent said."""
        # Use semaphore to limit concurrent ADK API calls
        semaphore = get_customer_agent_semaphore()
        async with semaphore:
            await self._ensure_session()
            from google.genai import types
            
            content = types.Content(
                role="user",
                parts=[types.Part(text=f"[Agent says]: {agent_message}")]
            )
            
            response_text = ""
            async for event in self.runner.run_async(
                user_id=self.user_id,
                session_id=self.session_id,
                new_message=content,
            ):
                if hasattr(event, 'content') and event.content:
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            response_text += part.text
                            
            return response_text.strip().strip('"\'')
    
    async def process_agent_audio(self, mulaw_audio: bytes) -> tuple[bytes, str, str]:
        """Process agent audio and return customer response audio.
        
        This is the main method for audio-to-audio conversation.
        
        Args:
            mulaw_audio: Agent's μ-law 8kHz audio
            
        Returns:
            Tuple of (customer_mulaw_audio, agent_text, customer_text)
        """
        # 1. Transcribe agent audio
        agent_text = await self.transcribe_audio(mulaw_audio)
        logger.info(f"[Agent] {agent_text[:100]}...")
        self.conversation_log.append({"role": "agent", "text": agent_text})
        
        # 2. Generate customer response
        customer_text = await self._get_text_response(agent_text)
        logger.info(f"[Customer] {customer_text}")
        self.conversation_log.append({"role": "customer", "text": customer_text})
        
        # 3. Convert to audio
        customer_audio = await self.text_to_speech(customer_text)
        
        return customer_audio, agent_text, customer_text
    
    async def get_opening_audio(self) -> tuple[bytes, str]:
        """Get customer's opening line as audio.
        
        Returns:
            Tuple of (mulaw_audio, text)
        """
        from google.genai import types
        
        content = types.Content(
            role="user", 
            parts=[types.Part(text="[The phone call has started. The agent is waiting for you to speak first.]")]
        )
        
        response_text = ""
        async for event in self.runner.run_async(
            user_id=self.user_id,
            session_id=self.session_id,
            new_message=content,
        ):
            if hasattr(event, 'content') and event.content:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        response_text += part.text
        
        text = response_text.strip().strip('"\'')
        logger.info(f"[Customer] Opening: {text}")
        self.conversation_log.append({"role": "customer", "text": text})
        
        audio = await self.text_to_speech(text)
        return audio, text
    
    async def get_goodbye_audio(self) -> tuple[bytes, str]:
        """Get customer's goodbye response as audio.
        
        Returns:
            Tuple of (mulaw_audio, text)
        """
        text = "No, that's all. Thank you, goodbye!"
        logger.info(f"[Customer] Goodbye: {text}")
        self.conversation_log.append({"role": "customer", "text": text})
        
        audio = await self.text_to_speech(text)
        return audio, text
    
    def is_conversation_complete(self, agent_text: str) -> bool:
        """Check if the agent's response indicates conversation is complete."""
        completion_phrases = [
            "anything else", "else i can help", "have a great day",
            "thank you for calling", "goodbye", "bye"
        ]
        return any(phrase in agent_text.lower() for phrase in completion_phrases)


# For backwards compatibility - simple function-based creation
def create_customer_agent(
    dimensions: Dict[str, int],
    from_postal: str,
    to_postal: str,
    preferred_service: str,
) -> Agent:
    """Create a customer agent with specific package details.
    
    Args:
        dimensions: Dict with 'length', 'width', 'height' in cm
        from_postal: Origin postal code
        to_postal: Destination postal code
        preferred_service: Preferred shipping service name
        
    Returns:
        Configured Agent instance for simulating a customer
    """
    model = os.getenv("CUSTOMER_MODEL", "gemini-2.0-flash")
    
    system_prompt = create_customer_system_prompt(
        length=dimensions['length'],
        width=dimensions['width'],
        height=dimensions['height'],
        from_postal=from_postal,
        to_postal=to_postal,
        preferred_service=preferred_service,
    )
    
    return Agent(
        name="customer_simulator",
        model=model,
        instruction=system_prompt,
        tools=[],  # No tools needed - customer just talks
    )
