"""
Test WebSocket Connection
Tests basic WebSocket connectivity to the ADK server
"""
import asyncio
import websockets
import json
import sys

async def test_websocket_connection():
    """Test that WebSocket connection can be established"""
    
    print("=" * 60)
    print("TEST 1: WebSocket Connection")
    print("=" * 60)
    
    # Test configuration
    host = "localhost"
    port = 8000
    user_id = "test-user"
    session_id = "test-session-001"
    ws_url = f"ws://{host}:{port}/ws/{user_id}/{session_id}"
    
    print(f"\n📡 Connecting to: {ws_url}")
    
    try:
        async with websockets.connect(ws_url) as websocket:
            print("✅ WebSocket connection established!")
            print(f"   Protocol: {websocket.protocol}")
            print(f"   State: {websocket.state.name}")
            
            # Wait for initial greeting/message
            print("\n⏳ Waiting for server greeting (5 seconds)...")
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                
                # Try to parse as JSON
                try:
                    data = json.loads(message)
                    print(f"✅ Received JSON message:")
                    print(f"   Type: {data.get('type', 'unknown')}")
                    print(f"   Keys: {list(data.keys())}")
                except json.JSONDecodeError:
                    print(f"✅ Received binary/text message:")
                    print(f"   Length: {len(message)} bytes")
                    
            except asyncio.TimeoutError:
                print("ℹ️  No immediate greeting (this is OK)")
            
            # Send a keepalive ping
            print("\n📤 Sending keepalive ping...")
            ping_message = json.dumps({"type": "ping"})
            await websocket.send(ping_message)
            print("✅ Ping sent successfully")
            
            # Wait for pong or any response
            print("\n⏳ Waiting for response (3 seconds)...")
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=3.0)
                print("✅ Server is responsive!")
            except asyncio.TimeoutError:
                print("ℹ️  No response to ping (server may be processing)")
            
            print("\n" + "=" * 60)
            print("✅ TEST PASSED: WebSocket connection works!")
            print("=" * 60)
            return True
            
    except ConnectionRefusedError:
        print("\n❌ Connection refused!")
        print("   Make sure the server is running:")
        print("   > cd app")
        print("   > uv run uvicorn main:app --reload")
        return False
        
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        print(f"   Error type: {type(e).__name__}")
        return False

if __name__ == "__main__":
    print("\n🧪 Running WebSocket Connection Test\n")
    
    success = asyncio.run(test_websocket_connection())
    
    sys.exit(0 if success else 1)
