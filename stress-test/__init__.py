"""
Stress Test Package

AI-to-AI stress testing for the SmartShip Voice Assistant.
Uses a mediator pattern with:
- Customer Agent (Gemini 2.0 Flash) for generating responses
- Edge TTS for text-to-speech
- Telnyx protocol simulation for /ws/phone endpoint
"""

from .mediator_simulator import (
    MediatorCallSimulator,
    CallResult,
    generate_random_postal_code,
    generate_random_dimensions,
    simulate_single_call,
    VALID_POSTAL_PREFIXES,
    SHIPPING_SERVICES,
)

from .customer_agent import (
    create_customer_agent,
    create_customer_system_prompt,
)

from .stress_test import (
    run_stress_test,
    StressTestResults,
)

__all__ = [
    # Mediator simulator
    "MediatorCallSimulator",
    "CallResult",
    "generate_random_postal_code",
    "generate_random_dimensions",
    "simulate_single_call",
    "VALID_POSTAL_PREFIXES",
    "SHIPPING_SERVICES",
    # Customer agent
    "create_customer_agent",
    "create_customer_system_prompt",
    # Stress test
    "run_stress_test",
    "StressTestResults",
]
