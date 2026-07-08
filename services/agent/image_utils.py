"""
Base64 image encoding/decoding utilities.

Provides helpers for converting between base64 strings and image bytes.
Used by agent for transporting images between services.
"""

import base64


def b64_to_bytes(b64_str: str) -> bytes:
    """Convert base64 string to image bytes.
    
    Args:
        b64_str: Base64-encoded image string
        
    Returns:
        Image bytes (PNG, JPEG, etc.)
        
    Raises:
        ValueError: If base64 string is invalid
    """
    try:
        return base64.b64decode(b64_str)
    except Exception as e:
        raise ValueError(f"Invalid base64 image: {e}")


def bytes_to_b64(data: bytes) -> str:
    """Convert image bytes to base64 string.
    
    Args:
        data: Image bytes
        
    Returns:
        Base64-encoded string
    """
    return base64.b64encode(data).decode("utf-8")
