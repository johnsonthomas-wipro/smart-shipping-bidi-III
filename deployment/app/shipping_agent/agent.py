"""SmartShip Shipping Agent definition for ADK Bidi-streaming."""

import os
from pathlib import Path
from google.adk.agents import Agent

# Import our tool implementations
from .tools import (
    validate_canadian_postal_code,
    calculate_shipping_rates,
    update_workflow_state
)


# Load system prompt from external file
def load_system_prompt(mode: str = "voice") -> str:
    """Load system prompt from external file based on mode.
    
    Args:
        mode: Either "voice", "text", or "ivr" to determine which prompt to load
        
    Returns:
        System prompt string
    """
    try:
        if mode == "text":
            prompt_file = Path(__file__).parent.parent / 'system_prompt_text.txt'
        elif mode == "ivr":
            prompt_file = Path(__file__).parent.parent / 'system_prompt_ivr.txt'
        else:
            prompt_file = Path(__file__).parent.parent / 'system_prompt.txt'
            
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"⚠️  Failed to load system prompt file: {e}")
        return "You are a helpful assistant for SmartShip package shipping service."


def create_agent(mode: str = "voice") -> Agent:
    """Create a SmartShip agent configured for the specified mode.
    
    Args:
        mode: "voice" (with camera), "text" (chat), or "ivr" (audio-only, no camera)
        
    Returns:
        Configured Agent instance
    """
    # Text mode uses gemini-2.0-flash-exp which supports bidi streaming without audio
    # IVR and Voice modes use native audio model for voice interaction
    if mode == "text":
        model = os.getenv("DEMO_TEXT_MODEL", "gemini-2.0-flash-exp")
    else:
        # Both voice and ivr use native audio model
        model = os.getenv("DEMO_AGENT_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")
    
    return Agent(
        name=f"smartship_{mode}_agent",
        model=model,
        tools=[
            validate_canadian_postal_code,
            calculate_shipping_rates,
            update_workflow_state
        ],
        instruction=load_system_prompt(mode),
    )


# Create the default SmartShip agent (voice mode)
# This is kept for backward compatibility
agent = create_agent("voice")
