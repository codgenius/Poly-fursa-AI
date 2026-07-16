"""
Comprehensive tests for MCP image processing tools.

Tests cover:
- Blur (whole image vs region)
- Add noise (whole image vs region)
- Crop (no region vs region)
- Rotate, flip, resize (full image operations)
- Coordinate validation and error handling
- Response format validation (all should be valid PNG base64)
"""

import base64
import io
import pytest
from PIL import Image, ImageDraw
import sys
import os

# Add parent directory to path to import app module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import (
    blur, add_noise, crop, rotate, flip, resize,
    paste_region, _paste_region,
    _decode, _encode
)


@pytest.fixture
def sample_image_b64():
    """Create a simple test image: 100x100 RGB with red background."""
    img = Image.new("RGB", (100, 100), color="red")
    return _encode(img)


@pytest.fixture
def sample_image_with_square_b64():
    """Create a test image with a blue square in the center for region testing."""
    img = Image.new("RGB", (200, 200), color="white")
    draw = ImageDraw.Draw(img)
    # Draw blue square: 50,50 to 150,150
    draw.rectangle([50, 50, 150, 150], fill="blue")
    return _encode(img)


class TestBlur:
    """Test blur() function with and without region coordinates."""
    
    def test_blur_whole_image_default(self, sample_image_b64):
        """Test blurring entire image with default radius."""
        result_b64 = blur(sample_image_b64)
        assert isinstance(result_b64, str)
        
        # Verify result is valid PNG base64
        img = _decode(result_b64)
        assert img.size == (100, 100)
        assert img.mode == "RGB"
    
    def test_blur_whole_image_high_radius(self, sample_image_b64):
        """Test blurring entire image with high radius."""
        result_b64 = blur(sample_image_b64, radius=10.0)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (100, 100)
    
    def test_blur_region_small_bbox(self, sample_image_with_square_b64):
        """Test blurring a small region (10x10 square)."""
        result_b64 = blur(sample_image_with_square_b64, left=45, top=45, right=55, bottom=55, radius=5.0)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (200, 200), "Full image should be returned"
    
    def test_blur_region_large_bbox(self, sample_image_with_square_b64):
        """Test blurring a large region (100x100)."""
        result_b64 = blur(sample_image_with_square_b64, left=50, top=50, right=150, bottom=150, radius=3.0)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (200, 200), "Full image should be returned"
    
    def test_blur_region_edge_bbox(self, sample_image_with_square_b64):
        """Test blurring a region at image edge."""
        result_b64 = blur(sample_image_with_square_b64, left=0, top=0, right=50, bottom=50, radius=2.0)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (200, 200)
    
    def test_blur_negative_radius(self, sample_image_b64):
        """Test that negative radius raises ValueError."""
        with pytest.raises(ValueError, match="radius must be non-negative"):
            blur(sample_image_b64, radius=-1.0)
    
    def test_blur_invalid_region_coords_reversed(self, sample_image_b64):
        """Test that reversed coordinates (right < left) raise ValueError."""
        with pytest.raises(ValueError, match="Invalid region coordinates"):
            blur(sample_image_b64, left=100, top=10, right=10, bottom=50, radius=2.0)
    
    def test_blur_invalid_region_coords_negative(self, sample_image_b64):
        """Test that negative coordinates raise ValueError."""
        with pytest.raises(ValueError, match="Invalid region coordinates"):
            blur(sample_image_b64, left=-10, top=10, right=50, bottom=50, radius=2.0)
    
    def test_blur_zero_radius(self, sample_image_b64):
        """Test blurring with zero radius (should be valid but minimal effect)."""
        result_b64 = blur(sample_image_b64, radius=0.0)
        assert isinstance(result_b64, str)
        img = _decode(result_b64)
        assert img.size == (100, 100)


class TestAddNoise:
    """Test add_noise() function with and without region coordinates."""
    
    def test_add_noise_whole_image_default(self, sample_image_b64):
        """Test adding noise to entire image with default amount."""
        result_b64 = add_noise(sample_image_b64)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (100, 100)
        assert img.mode == "RGB"
    
    def test_add_noise_whole_image_high_amount(self, sample_image_b64):
        """Test adding noise to entire image with high amount (50%)."""
        result_b64 = add_noise(sample_image_b64, amount=0.5)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (100, 100)
    
    def test_add_noise_region_small_bbox(self, sample_image_with_square_b64):
        """Test adding noise to a small region."""
        result_b64 = add_noise(sample_image_with_square_b64, left=45, top=45, right=55, bottom=55, amount=0.3)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (200, 200), "Full image should be returned"
    
    def test_add_noise_region_large_bbox(self, sample_image_with_square_b64):
        """Test adding noise to a large region."""
        result_b64 = add_noise(sample_image_with_square_b64, left=50, top=50, right=150, bottom=150, amount=0.2)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (200, 200)
    
    def test_add_noise_amount_zero(self, sample_image_b64):
        """Test adding noise with zero amount (no noise)."""
        result_b64 = add_noise(sample_image_b64, amount=0.0)
        assert isinstance(result_b64, str)
        img = _decode(result_b64)
        assert img.size == (100, 100)
    
    def test_add_noise_amount_one(self, sample_image_b64):
        """Test adding noise with amount=1.0 (all pixels noisy)."""
        result_b64 = add_noise(sample_image_b64, amount=1.0)
        assert isinstance(result_b64, str)
        img = _decode(result_b64)
        assert img.size == (100, 100)
    
    def test_add_noise_invalid_amount_negative(self, sample_image_b64):
        """Test that negative amount raises ValueError."""
        with pytest.raises(ValueError, match="amount must be between 0.0 and 1.0"):
            add_noise(sample_image_b64, amount=-0.1)
    
    def test_add_noise_invalid_amount_over_one(self, sample_image_b64):
        """Test that amount > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="amount must be between 0.0 and 1.0"):
            add_noise(sample_image_b64, amount=1.5)
    
    def test_add_noise_invalid_region_coords(self, sample_image_b64):
        """Test that invalid region coordinates raise ValueError."""
        with pytest.raises(ValueError, match="Invalid region coordinates"):
            add_noise(sample_image_b64, left=100, top=10, right=50, bottom=50, amount=0.1)


class TestCrop:
    """Test crop() function with and without region coordinates."""
    
    def test_crop_no_region_returns_full_image(self, sample_image_b64):
        """Test that crop with all-zero coordinates returns full image."""
        result_b64 = crop(sample_image_b64)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (100, 100), "Should return full image"
    
    def test_crop_small_region(self, sample_image_with_square_b64):
        """Test cropping a small 20x20 region."""
        result_b64 = crop(sample_image_with_square_b64, left=50, top=50, right=70, bottom=70)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (20, 20), "Should return cropped region only"
    
    def test_crop_large_region(self, sample_image_with_square_b64):
        """Test cropping a large 100x100 region."""
        result_b64 = crop(sample_image_with_square_b64, left=50, top=50, right=150, bottom=150)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (100, 100)
    
    def test_crop_edge_region(self, sample_image_with_square_b64):
        """Test cropping from image edge."""
        result_b64 = crop(sample_image_with_square_b64, left=0, top=0, right=50, bottom=50)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (50, 50)
    
    def test_crop_invalid_coords_reversed(self, sample_image_b64):
        """Test that reversed coordinates raise ValueError."""
        with pytest.raises(ValueError, match="Invalid crop coordinates"):
            crop(sample_image_b64, left=50, top=10, right=20, bottom=50)
    
    def test_crop_invalid_coords_negative(self, sample_image_b64):
        """Test that negative coordinates raise ValueError."""
        with pytest.raises(ValueError, match="Invalid crop coordinates"):
            crop(sample_image_b64, left=-10, top=10, right=50, bottom=50)
    
    def test_crop_invalid_coords_equal_edges(self, sample_image_b64):
        """Test that equal left/right (or top/bottom) raise ValueError."""
        with pytest.raises(ValueError, match="Invalid crop coordinates"):
            crop(sample_image_b64, left=50, top=10, right=50, bottom=50)


class TestRotate:
    """Test rotate() function."""
    
    def test_rotate_90_degrees(self, sample_image_with_square_b64):
        """Test rotating image 90 degrees."""
        result_b64 = rotate(sample_image_with_square_b64, angle=90)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (200, 200), "Rotation without expand should maintain size"
    
    def test_rotate_negative_angle(self, sample_image_b64):
        """Test rotating with negative angle (counter-clockwise)."""
        result_b64 = rotate(sample_image_b64, angle=-45)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (100, 100)
    
    def test_rotate_zero_degrees(self, sample_image_b64):
        """Test rotating 0 degrees (no change)."""
        result_b64 = rotate(sample_image_b64, angle=0)
        assert isinstance(result_b64, str)
        img = _decode(result_b64)
        assert img.size == (100, 100)


class TestFlip:
    """Test flip() function."""
    
    def test_flip_horizontal(self, sample_image_with_square_b64):
        """Test flipping image horizontally."""
        result_b64 = flip(sample_image_with_square_b64, direction="horizontal")
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (200, 200)
    
    def test_flip_vertical(self, sample_image_with_square_b64):
        """Test flipping image vertically."""
        result_b64 = flip(sample_image_with_square_b64, direction="vertical")
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (200, 200)
    
    def test_flip_invalid_direction(self, sample_image_b64):
        """Test that invalid direction raises ValueError."""
        with pytest.raises(ValueError, match="Invalid direction"):
            flip(sample_image_b64, direction="diagonal")
    
    def test_flip_case_insensitive(self, sample_image_b64):
        """Test that direction is case-insensitive."""
        result_b64 = flip(sample_image_b64, direction="HORIZONTAL")
        assert isinstance(result_b64, str)
        img = _decode(result_b64)
        assert img.size == (100, 100)


class TestResize:
    """Test resize() function."""
    
    def test_resize_to_smaller(self, sample_image_b64):
        """Test resizing to smaller dimensions."""
        result_b64 = resize(sample_image_b64, width=50, height=50)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (50, 50)
    
    def test_resize_to_larger(self, sample_image_b64):
        """Test resizing to larger dimensions."""
        result_b64 = resize(sample_image_b64, width=200, height=200)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (200, 200)
    
    def test_resize_non_square(self, sample_image_b64):
        """Test resizing to non-square dimensions."""
        result_b64 = resize(sample_image_b64, width=150, height=75)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (150, 75)
    
    def test_resize_invalid_width(self, sample_image_b64):
        """Test that non-positive width raises ValueError."""
        with pytest.raises(ValueError, match="Width and height must be positive"):
            resize(sample_image_b64, width=0, height=50)
    
    def test_resize_invalid_height(self, sample_image_b64):
        """Test that non-positive height raises ValueError."""
        with pytest.raises(ValueError, match="Width and height must be positive"):
            resize(sample_image_b64, width=50, height=-10)


class TestPasteRegion:
    """Test paste_region() function."""
    
    def test_paste_region_valid(self, sample_image_with_square_b64):
        """Test pasting a region back into full image."""
        # Crop a 50x50 region
        region_b64 = crop(sample_image_with_square_b64, left=50, top=50, right=100, bottom=100)
        
        # Blur it
        blurred_region_b64 = blur(region_b64, radius=5.0)
        
        # Paste back
        result_b64 = paste_region(sample_image_with_square_b64, blurred_region_b64, left=50, top=50, right=100, bottom=100)
        assert isinstance(result_b64, str)
        
        img = _decode(result_b64)
        assert img.size == (200, 200)
    
    def test_paste_region_mismatched_size(self, sample_image_with_square_b64):
        """Test that pasting with wrong size raises ValueError."""
        # Crop a 50x50 region
        region_b64 = crop(sample_image_with_square_b64, left=50, top=50, right=100, bottom=100)
        
        # Try to paste at wrong coordinates (30x30 bbox)
        with pytest.raises(ValueError, match="Region size.*does not match"):
            paste_region(sample_image_with_square_b64, region_b64, left=50, top=50, right=80, bottom=80)
    
    def test_paste_region_invalid_coords(self, sample_image_with_square_b64):
        """Test that invalid coordinates raise ValueError."""
        region_b64 = crop(sample_image_with_square_b64, left=50, top=50, right=100, bottom=100)
        
        with pytest.raises(ValueError, match="Invalid bbox coordinates"):
            paste_region(sample_image_with_square_b64, region_b64, left=100, top=50, right=50, bottom=100)


class TestEncodeDecode:
    """Test _encode() and _decode() helper functions."""
    
    def test_encode_decode_roundtrip(self, sample_image_b64):
        """Test that encode->decode roundtrip preserves image."""
        img1 = _decode(sample_image_b64)
        re_encoded = _encode(img1)
        img2 = _decode(re_encoded)
        
        assert img1.size == img2.size
        assert img1.mode == img2.mode
    
    def test_decode_invalid_base64(self):
        """Test that invalid base64 raises exception."""
        with pytest.raises(Exception):
            _decode("not valid base64!!!")
    
    def test_encode_returns_string(self):
        """Test that _encode returns a string."""
        img = Image.new("RGB", (10, 10), color="red")
        result = _encode(img)
        assert isinstance(result, str)


class TestIntegrationScenarios:
    """Integration tests for real-world usage scenarios."""
    
    def test_blur_object_workflow(self, sample_image_with_square_b64):
        """Test workflow: blur a specific region in an image."""
        # Agent detects object at bbox (50, 50, 150, 150)
        # Agent calls blur() with region coords
        result_b64 = blur(sample_image_with_square_b64, left=50, top=50, right=150, bottom=150, radius=5.0)
        
        img = _decode(result_b64)
        assert img.size == (200, 200)
        assert isinstance(result_b64, str)
    
    def test_add_noise_object_workflow(self, sample_image_with_square_b64):
        """Test workflow: add noise to a specific region."""
        result_b64 = add_noise(sample_image_with_square_b64, left=50, top=50, right=150, bottom=150, amount=0.2)
        
        img = _decode(result_b64)
        assert img.size == (200, 200)
    
    def test_crop_object_workflow(self, sample_image_with_square_b64):
        """Test workflow: crop an object region from image."""
        result_b64 = crop(sample_image_with_square_b64, left=50, top=50, right=150, bottom=150)
        
        img = _decode(result_b64)
        assert img.size == (100, 100), "Cropped object should be 100x100"
    
    def test_multiple_operations_workflow(self, sample_image_with_square_b64):
        """Test workflow: crop -> blur -> return (simulating old agent behavior)."""
        # Step 1: Crop object
        cropped_b64 = crop(sample_image_with_square_b64, left=50, top=50, right=150, bottom=150)
        
        # Step 2: Blur cropped object
        blurred_b64 = blur(cropped_b64, radius=5.0)  # No coords = blur whole cropped image
        
        # Result is the blurred object (not full image)
        img = _decode(blurred_b64)
        assert img.size == (100, 100)
