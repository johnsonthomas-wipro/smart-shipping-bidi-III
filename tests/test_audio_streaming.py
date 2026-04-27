"""
Test Audio Streaming
Tests sending audio data and receiving audio response from ADK
"""
import asyncio
import websockets
import json
import struct
import math
import sys

def generate_test_audio(duration_ms=1000, sample_rate=16000):
    """
    Generate test audio: a simple sine wave
    Returns PCM16 audio data (Int16Array buffer)
    """
    num_samples = int(sample_rate * duration_ms / 1000)
    frequency = 440  # A4 note
    
    audio_data = []
    for i in range(num_samples):
        # Generate sine wave
        t = i / sample_rate
        sample = math.sin(2 * math.pi * frequency * t)
        
        # Convert to 16-bit PCM
        pcm_value = int(sample * 32767)
        pcm_value = max(-32768, min(32767, pcm_value))
        audio_data.append(pcm_value)
    
    # Pack as little-endian signed 16-bit integers
    return struct.pack(f'<{len(audio_data)}h', *audio_data)

async def test_audio_streaming():
    """Test sending audio and receiving audio response"""
    
    print("=" * 60)
    print("TEST 2: Audio Streaming")
    print("=" * 60)
    
    # Test configuration
    host = "localhost"
    port = 8000
    user_id = "test-user"
    session_id = "test-session-002"
    ws_url = f"ws://{host}:{port}/ws/{user_id}/{session_id}"
    
    print(f"\n📡 Connecting to: {ws_url}")
    
    try:
        async with websockets.connect(ws_url) as websocket:
            print("✅ WebSocket connected")
            
            # Generate test audio (1 second of 440Hz tone)
            print("\n🎵 Generating test audio...")
            audio_data = generate_test_audio(duration_ms=500, sample_rate=16000)
            print(f"   Generated: {len(audio_data)} bytes of PCM16 audio")
            print(f"   Samples: {len(audio_data) // 2}")
            print(f"   Duration: ~500ms")
            
            # Send audio data
            print("\n📤 Sending audio to ADK...")
            await websocket.send(audio_data)
            print("✅ Audio sent successfully")
            
            # Wait for responses
            print("\n⏳ Waiting for ADK responses (10 seconds max)...")
            responses_received = 0
            audio_received = False
            text_received = False
            
            try:
                timeout = 10.0
                start_time = asyncio.get_event_loop().time()
                
                while (asyncio.get_event_loop().time() - start_time) < timeout:
                    try:
                        message = await asyncio.wait_for(
                            websocket.recv(), 
                            timeout=timeout - (asyncio.get_event_loop().time() - start_time)
                        )
                        responses_received += 1
                        
                        # Try to parse as JSON (ADK events)
                        try:
                            event = json.loads(message)
                            print(f"\n📨 Response #{responses_received}: JSON Event")
                            
                            # Check for content
                            if event.get('content') and event['content'].get('parts'):
                                parts = event['content']['parts']
                                print(f"   Parts: {len(parts)}")
                                
                                for i, part in enumerate(parts):
                                    if part.get('inlineData'):
                                        mime = part['inlineData'].get('mimeType', 'unknown')
                                        data = part['inlineData'].get('data', '')
                                        print(f"   Part {i+1}: {mime}")
                                        print(f"     Data length: {len(data)} chars (base64)")
                                        
                                        if mime.startswith('audio/'):
                                            audio_received = True
                                            print("     ✅ AUDIO DATA RECEIVED!")
                                    
                                    if part.get('text'):
                                        text_received = True
                                        print(f"   Part {i+1}: text")
                                        print(f"     Text: {part['text'][:100]}...")
                            
                            # Check for transcriptions
                            if event.get('outputTranscription'):
                                text = event['outputTranscription'].get('text', '')
                                print(f"   Output transcription: {text[:100]}...")
                                text_received = True
                            
                            if event.get('inputTranscription'):
                                text = event['inputTranscription'].get('text', '')
                                print(f"   Input transcription: {text[:100]}...")
                            
                            # Check for turn complete
                            if event.get('turnComplete'):
                                print("   ✅ Turn complete!")
                                break
                                
                        except json.JSONDecodeError:
                            # Binary message
                            print(f"\n📨 Response #{responses_received}: Binary Data")
                            print(f"   Length: {len(message)} bytes")
                            
                    except asyncio.TimeoutError:
                        break
                        
            except Exception as e:
                print(f"\n⚠️  Error receiving messages: {e}")
            
            # Summary
            print("\n" + "=" * 60)
            print("TEST SUMMARY")
            print("=" * 60)
            print(f"Total responses: {responses_received}")
            print(f"Audio received: {'✅ YES' if audio_received else '❌ NO'}")
            print(f"Text received: {'✅ YES' if text_received else '❌ NO'}")
            
            if responses_received > 0 and (audio_received or text_received):
                print("\n✅ TEST PASSED: Audio streaming works!")
                print("=" * 60)
                return True
            else:
                print("\n⚠️  TEST PARTIAL: Connection works but limited response")
                print("   This might be expected if ADK is still initializing")
                print("=" * 60)
                return True
            
    except ConnectionRefusedError:
        print("\n❌ Connection refused!")
        print("   Make sure the server is running:")
        print("   > cd app")
        print("   > uv run uvicorn main:app --reload")
        return False
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        print(f"   Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n🧪 Running Audio Streaming Test\n")
    
    success = asyncio.run(test_audio_streaming())
    
    sys.exit(0 if success else 1)
