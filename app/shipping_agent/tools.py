"""Tool implementations for SmartShip shipping assistant."""

import re
import logging
from typing import Dict, Any, Callable, Optional

logger = logging.getLogger(__name__)

# Global workflow state tracking (per-session in production should use session storage)
_current_workflow_state = {
    "state": "initial",
    "data": {}
}

# Callback function to notify when workflow state changes
_workflow_state_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None


def set_workflow_state_callback(callback: Callable[[str, Dict[str, Any]], None]) -> None:
    """Register a callback to be called when workflow state changes.
    
    Args:
        callback: Function that takes (state: str, data: Dict[str, Any])
    """
    global _workflow_state_callback
    _workflow_state_callback = callback
    logger.info("📞 Workflow state callback registered")


def reset_workflow_state() -> None:
    """Reset workflow state to initial. Called on connection restart."""
    global _current_workflow_state
    _current_workflow_state = {
        "state": "initial",
        "data": {}
    }
    logger.info("🔄 Workflow state reset to initial")


def validate_canadian_postal_code(postal_code: str) -> Dict[str, Any]:
    """Validate Canadian postal code format and check if it's valid.
    
    Args:
        postal_code: 6-character Canadian postal code (e.g., "K1A0B1" or "K1A 0B1")
    
    Returns:
        Dict with 'valid' (bool), 'formatted' (str or None), and 'error' (str or None)
    """
    logger.info("++++++++++++++ TOOL INVOKED: validate_canadian_postal_code ++++++++++++++")
    logger.info(f"Input: postal_code={postal_code}")
    
    if not postal_code:
        return {"valid": False, "formatted": None, "error": "Postal code is empty"}
    
    clean = postal_code.replace(' ', '').upper()
    
    if not re.match(r'^[A-Z]\d[A-Z]\d[A-Z]\d$', clean):
        return {
            "valid": False,
            "formatted": None,
            "error": "Invalid postal code format. Should be L#L #L# (e.g., K1A 0B1)"
        }
    
    invalid_first = ['D', 'F', 'I', 'O', 'Q', 'U', 'W', 'Z']
    if clean[0] in invalid_first:
        return {
            "valid": False,
            "formatted": None,
            "error": f"Invalid postal code. First letter cannot be {clean[0]}"
        }
    
    formatted = f"{clean[:3]} {clean[3:]}"
    result = {"valid": True, "formatted": formatted, "error": None}
    logger.info(f"Result: {result}")
    logger.info("++++++++++++++ END: validate_canadian_postal_code ++++++++++++++")
    return result


def calculate_shipping_rates(
    from_postal: str,
    to_postal: str,
    dimensions: Dict[str, float]
) -> Dict[str, Any]:
    """Calculate shipping rates between two postal codes with package dimensions.
    
    Args:
        from_postal: Sender postal code (e.g., "H4V 2T4")
        to_postal: Destination postal code (e.g., "M5V 3L9")
        dimensions: Dict with 'length', 'width', 'height' in centimeters
    
    Returns:
        Dict with 'success', postal codes, dimensions, and 'rates' array
    """
    logger.info("++++++++++++++ TOOL INVOKED: calculate_shipping_rates ++++++++++++++")
    logger.info(f"Input: from_postal={from_postal}, to_postal={to_postal}, dimensions={dimensions}")
    
    # Mock shipping calculation (in production, call real Canada Post API)
    rates = [
        {
            'service': 'Regular Parcel',
            'price': '$12.50',
            'delivery': '5-7 business days'
        },
        {
            'service': 'Expedited Parcel',
            'price': '$18.75',
            'delivery': '2-3 business days'
        },
        {
            'service': 'Xpresspost',
            'price': '$24.99',
            'delivery': '1-2 business days'
        }
    ]
    
    result = {
        "success": True,
        "from_postal": from_postal,
        "to_postal": to_postal,
        "dimensions": dimensions,
        "rates": rates
    }
    logger.info(f"Result: {result}")
    logger.info("++++++++++++++ END: calculate_shipping_rates ++++++++++++++")
    return result


def update_workflow_state(state: str, data: str = "") -> Dict[str, Any]:
    """Update the workflow state and track conversation progress.
    
    Args:
        state: Current workflow state (e.g., "greeting", "collecting_dimensions", etc.)
        data: Additional state data as JSON string (optional)
    
    Returns:
        Dict with 'success', 'new_state', and 'message'
    """
    global _current_workflow_state
    
    valid_states = [
        "initial", "greeting", "waiting_for_camera_ready","send_instruction_to_enable_camera_at_browser", "capturing", 
        "collecting_dimensions", "confirming_dimensions",
        "collecting_from_postal", "confirming_from_postal",
        "collecting_to_postal", "confirming_to_postal",
        "calculating_rates", "presenting_rates", "awaiting_selection",
        "complete"
    ]
    
    if state not in valid_states:
        logger.warning(f"🔄 Workflow state INVALID: {state}")
        return {
            "success": False,
            "new_state": state,
            "message": f"Invalid state: {state}"
        }
    
    # Check if state actually changed
    old_state = _current_workflow_state["state"]
    state_changed = old_state != state
    
    # Store the current state
    _current_workflow_state = {
        "state": state,
        "data": data or {}
    }
    
    logger.info(f"🔄 Workflow state → {state}")
    
    # Trigger callback if state changed and callback is registered
    if state_changed and _workflow_state_callback:
        logger.info(f"📞 Triggering callback: {old_state} → {state}")
        _workflow_state_callback(state, data or {})
    
    return {
        "success": True,
        "new_state": state,
        "message": f"State updated to {state}",
        "data": data or {}
    }


def get_current_workflow_state() -> Dict[str, Any]:
    """Get the current workflow state.
    
    Returns:
        Dict with 'state' and 'data' of current workflow
    """
    global _current_workflow_state
    logger.info(f"📊 Getting workflow state: {_current_workflow_state['state']}")
    return _current_workflow_state
