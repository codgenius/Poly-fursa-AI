"""
Unit tests for image_utils.py

Tests crop/paste/b64 conversion utilities in isolation.
"""

import pytest
import base64
import io
from PIL import Image
from image_utils import (
    b64_to_bytes,
    bytes_to_b64,
)


def generate_test_image(width: int = 100, height: int = 100, color: str = "red") -> bytes:
    """Generate a simple test image as bytes."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestB64Conversion:
    """Test base64 ↔ bytes conversion"""
    
    def test_b64_to_bytes(self):
        """Convert base64 string to bytes"""
        test_bytes = generate_test_image()
        b64_str = base64.b64encode(test_bytes).decode()
        
        result = b64_to_bytes(b64_str)
        assert result == test_bytes
    
    def test_bytes_to_b64(self):
        """Convert bytes to base64 string"""
        test_bytes = generate_test_image()
        b64_str = bytes_to_b64(test_bytes)
        
        # Verify it's valid base64
        decoded = base64.b64decode(b64_str)
        assert decoded == test_bytes
    
    def test_b64_roundtrip(self):
        """Convert bytes → b64 → bytes and verify"""
        original = generate_test_image()
        
        b64 = bytes_to_b64(original)
        recovered = b64_to_bytes(b64)
        
        assert recovered == original
    
    def test_invalid_b64(self):
        """Invalid base64 raises ValueError"""
        with pytest.raises(ValueError, match="Invalid base64"):
            b64_to_bytes("not valid base64!!!!")





if __name__ == "__main__":
    pytest.main([__file__, "-v"])
