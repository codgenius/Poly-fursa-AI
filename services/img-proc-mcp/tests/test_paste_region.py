"""
Test MCP paste_region tool.

Verifies that paste_region correctly composites a processed region
back into a full image with proper dimensions and positioning.
"""

import pytest
import base64
import io
from PIL import Image, ImageDraw

import sys
sys.path.insert(0, '/home/hadikhier/Poly-fursa-AI/services/img-proc-mcp')

from app import paste_region


def image_to_b64(img: Image.Image) -> str:
    """Convert PIL Image to base64 string."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def b64_to_image(b64_str: str) -> Image.Image:
    """Convert base64 string to PIL Image."""
    return Image.open(io.BytesIO(base64.b64decode(b64_str)))


class TestPasteRegion:
    """Test paste_region MCP tool"""
    
    def test_paste_region_preserves_full_dimensions(self):
        """Paste region back into full image preserves original dimensions."""
        # Create 100x100 red full image
        full_img = Image.new("RGB", (100, 100), "red")
        full_b64 = image_to_b64(full_img)
        
        # Create 50x50 blue region
        region_img = Image.new("RGB", (50, 50), "blue")
        region_b64 = image_to_b64(region_img)
        
        # Paste blue region at (25, 25)
        result_b64 = paste_region(full_b64, region_b64, 25, 25, 75, 75)
        
        # Verify result is valid image
        result_img = b64_to_image(result_b64)
        assert result_img.size == (100, 100)
        assert result_img.mode == "RGB"
    
    def test_paste_region_correct_positioning(self):
        """Pasted region appears in correct location."""
        # Create 100x100 red full image
        full_img = Image.new("RGB", (100, 100), "red")
        full_b64 = image_to_b64(full_img)
        
        # Create 20x20 blue region
        region_img = Image.new("RGB", (20, 20), "blue")
        region_b64 = image_to_b64(region_img)
        
        # Paste at top-left (0, 0)
        result_b64 = paste_region(full_b64, region_b64, 0, 0, 20, 20)
        result_img = b64_to_image(result_b64)
        
        # Top-left pixel should be blue
        assert result_img.getpixel((0, 0))[:2] == (0, 0)  # blue channel high
        # Pixel at (25, 25) should still be red (outside pasted region)
        assert result_img.getpixel((25, 25)) == (255, 0, 0)  # red
    
    def test_paste_region_full_image_replacement(self):
        """Pasting full-size region replaces entire image."""
        # Create 50x50 red full image
        full_img = Image.new("RGB", (50, 50), "red")
        full_b64 = image_to_b64(full_img)
        
        # Create 50x50 green replacement region
        region_img = Image.new("RGB", (50, 50), "green")
        region_b64 = image_to_b64(region_img)
        
        # Paste region over entire image
        result_b64 = paste_region(full_b64, region_b64, 0, 0, 50, 50)
        result_img = b64_to_image(result_b64)
        
        # Result should be entirely green
        assert result_img.size == (50, 50)
        center_pixel = result_img.getpixel((25, 25))
        assert center_pixel == (0, 128, 0)  # green
    
    def test_paste_region_invalid_size_raises_error(self):
        """Region size mismatch raises ValueError."""
        full_img = Image.new("RGB", (100, 100), "red")
        full_b64 = image_to_b64(full_img)
        
        # Create 30x30 region (doesn't match 50x50 bbox)
        region_img = Image.new("RGB", (30, 30), "blue")
        region_b64 = image_to_b64(region_img)
        
        # Should raise error
        with pytest.raises(ValueError, match="does not match"):
            paste_region(full_b64, region_b64, 0, 0, 50, 50)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
