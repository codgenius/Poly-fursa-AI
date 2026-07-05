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
    crop_image_region,
    paste_image_region,
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


class TestCropRegion:
    """Test crop_image_region"""
    
    def test_crop_full_image(self):
        """Crop the entire image"""
        img_bytes = generate_test_image(100, 100)
        cropped = crop_image_region(img_bytes, (0, 0, 100, 100))
        
        # Should be same size
        cropped_img = Image.open(io.BytesIO(cropped))
        assert cropped_img.size == (100, 100)
    
    def test_crop_center_region(self):
        """Crop center 50x50 from 100x100 image"""
        img_bytes = generate_test_image(100, 100)
        cropped = crop_image_region(img_bytes, (25, 25, 75, 75))
        
        cropped_img = Image.open(io.BytesIO(cropped))
        assert cropped_img.size == (50, 50)
    
    def test_crop_quarter(self):
        """Crop top-left quarter"""
        img_bytes = generate_test_image(100, 100)
        cropped = crop_image_region(img_bytes, (0, 0, 50, 50))
        
        cropped_img = Image.open(io.BytesIO(cropped))
        assert cropped_img.size == (50, 50)
    
    def test_invalid_bbox_left_gte_right(self):
        """bbox with left >= right raises ValueError"""
        img_bytes = generate_test_image()
        
        with pytest.raises(ValueError, match="Invalid crop bbox"):
            crop_image_region(img_bytes, (50, 0, 50, 100))  # left == right
        
        with pytest.raises(ValueError, match="Invalid crop bbox"):
            crop_image_region(img_bytes, (100, 0, 50, 100))  # left > right
    
    def test_invalid_bbox_top_gte_bottom(self):
        """bbox with top >= bottom raises ValueError"""
        img_bytes = generate_test_image()
        
        with pytest.raises(ValueError, match="Invalid crop bbox"):
            crop_image_region(img_bytes, (0, 50, 100, 50))  # top > bottom
    
    def test_invalid_bbox_negative(self):
        """bbox with negative coordinates raises ValueError"""
        img_bytes = generate_test_image()
        
        with pytest.raises(ValueError, match="Invalid crop bbox"):
            crop_image_region(img_bytes, (-10, 0, 50, 50))  # negative left
    
    def test_crop_out_of_bounds_clamps(self):
        """Out-of-bounds crop clamps to image edges"""
        img_bytes = generate_test_image(100, 100)
        
        # Request crop beyond image bounds - should clamp
        cropped = crop_image_region(img_bytes, (50, 50, 200, 200))
        cropped_img = Image.open(io.BytesIO(cropped))
        
        # Should be 50x50 (from 50,50 to 100,100)
        assert cropped_img.size == (50, 50)


class TestPasteRegion:
    """Test paste_image_region"""
    
    def test_paste_full_region(self):
        """Paste full-size region back (should be identical)"""
        original = generate_test_image(100, 100, "red")
        
        # Paste entire image at (0,0)
        result = paste_image_region(original, original, (0, 0, 100, 100))
        
        result_img = Image.open(io.BytesIO(result))
        assert result_img.size == (100, 100)
    
    def test_paste_center_region(self):
        """Paste a 50x50 region into center of 100x100 image"""
        full = generate_test_image(100, 100, "red")
        center = generate_test_image(50, 50, "blue")
        
        # Paste 50x50 blue region at (25, 25)
        result = paste_image_region(full, center, (25, 25, 75, 75))
        
        result_img = Image.open(io.BytesIO(result))
        assert result_img.size == (100, 100)
        
        # Center should be blue (different from red background)
        # Just verify it doesn't crash for now
    
    def test_paste_mismatched_size(self):
        """Region size doesn't match bbox raises ValueError"""
        full = generate_test_image(100, 100)
        region = generate_test_image(30, 30)  # 30x30
        
        # Try to paste 30x30 region into 50x50 bbox
        with pytest.raises(ValueError, match="does not match"):
            paste_image_region(full, region, (0, 0, 50, 50))
    
    def test_paste_invalid_bbox_negative(self):
        """Invalid bbox raises ValueError"""
        full = generate_test_image(100, 100)
        region = generate_test_image(50, 50)
        
        with pytest.raises(ValueError, match="Invalid paste bbox"):
            paste_image_region(full, region, (-10, 0, 40, 50))
    
    def test_paste_invalid_bbox_inverted(self):
        """Inverted bbox raises ValueError"""
        full = generate_test_image(100, 100)
        region = generate_test_image(50, 50)
        
        with pytest.raises(ValueError, match="Invalid paste bbox"):
            paste_image_region(full, region, (50, 0, 0, 50))  # left > right


class TestCropPasteRoundtrip:
    """Test crop → paste roundtrip"""
    
    def test_roundtrip_exact_bbox(self):
        """Crop region and paste it back, should be identical"""
        original = generate_test_image(100, 100, "red")
        bbox = (25, 25, 75, 75)
        
        # Crop center region
        cropped = crop_image_region(original, bbox)
        
        # Paste it back
        result = paste_image_region(original, cropped, bbox)
        
        # Should be identical to original
        assert result == original
    
    def test_roundtrip_modified_region(self):
        """Crop, modify region, paste back"""
        original = generate_test_image(100, 100, "red")
        bbox = (20, 20, 80, 80)
        
        # Crop center region
        cropped = crop_image_region(original, bbox)
        
        # Convert to blue (simulating MCP modification)
        cropped_img = Image.open(io.BytesIO(cropped))
        blue_img = Image.new("RGB", cropped_img.size, "blue")
        blue_buf = io.BytesIO()
        blue_img.save(blue_buf, format="PNG")
        modified = blue_buf.getvalue()
        
        # Paste modified region back
        result = paste_image_region(original, modified, bbox)
        
        # Result should have blue center and red edges
        result_img = Image.open(io.BytesIO(result))
        assert result_img.size == (100, 100)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
