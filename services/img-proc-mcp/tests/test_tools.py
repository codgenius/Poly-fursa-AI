"""
Tests for image processing tools.
Validates tool registration, input/output handling, and edge cases.
"""
import base64
import io
import sys
import os
import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import blur, rotate, flip, resize, crop, add_noise


class TestRotate:
    """Test the rotate tool."""

    def test_rotate_valid_angle(self, test_image_b64):
        """Test rotate with a valid angle (90 degrees)."""
        result_b64 = rotate(image_b64=test_image_b64, angle=90)
        
        # Verify result is valid base64
        assert isinstance(result_b64, str)
        decoded = base64.b64decode(result_b64)
        assert len(decoded) > 0
        
        # Verify result decodes to a valid PNG image
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        # Rotated 10x10 should still be roughly square (PIL may adjust)
        assert output_img.size[0] > 0 and output_img.size[1] > 0

    def test_rotate_zero_degrees(self, test_image_b64):
        """Test rotate with zero degrees (should return similar image)."""
        result_b64 = rotate(image_b64=test_image_b64, angle=0)
        
        # Should still be valid base64 PNG
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)

    def test_rotate_negative_angle(self, test_image_b64):
        """Test rotate with negative angle (-45 degrees)."""
        result_b64 = rotate(image_b64=test_image_b64, angle=-45)
        
        # Should still be valid base64 PNG
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"

    def test_rotate_360_degrees(self, test_image_b64):
        """Test rotate with 360 degrees (full rotation)."""
        result_b64 = rotate(image_b64=test_image_b64, angle=360)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"

    def test_rotate_output_is_png(self, test_image_b64):
        """Verify output is always PNG format."""
        for angle in [45, 90, 180, -90, 270]:
            result_b64 = rotate(image_b64=test_image_b64, angle=angle)
            decoded = base64.b64decode(result_b64)
            output_img = Image.open(io.BytesIO(decoded))
            assert output_img.format == "PNG", f"Failed for angle {angle}"

    def test_rotate_preserves_content(self, test_image_b64_with_pattern):
        """Test that rotate preserves image data (not blank)."""
        result_b64 = rotate(image_b64=test_image_b64_with_pattern, angle=45)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        
        # Image should have pixel data (not all white/empty)
        pixels = list(output_img.getdata())
        assert len(pixels) > 0
        # At least some pixels should be different from all-white
        assert not all(p == (255, 255, 255) for p in pixels), "Output image is blank"


class TestBlur:
    """Test the blur tool (already implemented, verify it still works)."""

    def test_blur_valid_radius(self, test_image_b64):
        """Test blur with a valid radius."""
        result_b64 = blur(image_b64=test_image_b64, radius=2.0)
        
        # Verify result is valid base64
        assert isinstance(result_b64, str)
        decoded = base64.b64decode(result_b64)
        assert len(decoded) > 0
        
        # Verify result decodes to a valid PNG image
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)

    def test_blur_zero_radius(self, test_image_b64):
        """Test blur with zero radius (edge case)."""
        result_b64 = blur(image_b64=test_image_b64, radius=0)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"

    def test_blur_negative_radius_raises_error(self, test_image_b64):
        """Test that negative radius raises ValueError."""
        with pytest.raises(ValueError, match="must be non-negative"):
            blur(image_b64=test_image_b64, radius=-1.0)


class TestFlip:
    """Test the flip tool."""

    def test_flip_horizontal(self, test_image_b64_with_pattern):
        """Test horizontal flip."""
        result_b64 = flip(image_b64=test_image_b64_with_pattern, direction="horizontal")
        
        # Verify result is valid base64
        assert isinstance(result_b64, str)
        decoded = base64.b64decode(result_b64)
        assert len(decoded) > 0
        
        # Verify result decodes to a valid PNG image
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (20, 20)

    def test_flip_vertical(self, test_image_b64_with_pattern):
        """Test vertical flip."""
        result_b64 = flip(image_b64=test_image_b64_with_pattern, direction="vertical")
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (20, 20)

    def test_flip_horizontal_case_insensitive(self, test_image_b64):
        """Test that direction is case-insensitive."""
        result_b64 = flip(image_b64=test_image_b64, direction="HORIZONTAL")
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"

    def test_flip_vertical_case_insensitive(self, test_image_b64):
        """Test that direction is case-insensitive."""
        result_b64 = flip(image_b64=test_image_b64, direction="Vertical")
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"

    def test_flip_invalid_direction(self, test_image_b64):
        """Test that invalid direction raises ValueError."""
        with pytest.raises(ValueError, match="Invalid direction"):
            flip(image_b64=test_image_b64, direction="diagonal")

    def test_flip_preserves_content(self, test_image_b64_with_pattern):
        """Test that flip preserves image data (not blank)."""
        result_b64 = flip(image_b64=test_image_b64_with_pattern, direction="horizontal")
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        
        # Image should have pixel data
        pixels = list(output_img.getdata())
        assert len(pixels) > 0
        # At least some pixels should be different from all-white
        assert not all(p == (255, 255, 255) for p in pixels), "Output image is blank"


class TestResize:
    """Test the resize tool."""

    def test_resize_upscale(self, test_image_b64):
        """Test resizing to larger dimensions."""
        result_b64 = resize(image_b64=test_image_b64, width=20, height=20)
        
        # Verify result is valid base64
        assert isinstance(result_b64, str)
        decoded = base64.b64decode(result_b64)
        assert len(decoded) > 0
        
        # Verify result decodes to a valid PNG image with correct dimensions
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (20, 20)

    def test_resize_downscale(self, test_image_b64_with_pattern):
        """Test resizing to smaller dimensions."""
        result_b64 = resize(image_b64=test_image_b64_with_pattern, width=5, height=5)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (5, 5)

    def test_resize_asymmetric(self, test_image_b64):
        """Test resizing with asymmetric dimensions."""
        result_b64 = resize(image_b64=test_image_b64, width=30, height=15)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (30, 15)

    def test_resize_same_dimensions(self, test_image_b64):
        """Test resizing to same dimensions (should work without issue)."""
        result_b64 = resize(image_b64=test_image_b64, width=10, height=10)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)

    def test_resize_very_small(self, test_image_b64):
        """Test resizing to very small dimensions (1x1)."""
        result_b64 = resize(image_b64=test_image_b64, width=1, height=1)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (1, 1)

    def test_resize_very_large(self, test_image_b64):
        """Test resizing to very large dimensions."""
        result_b64 = resize(image_b64=test_image_b64, width=500, height=500)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (500, 500)

    def test_resize_zero_width_raises_error(self, test_image_b64):
        """Test that zero width raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            resize(image_b64=test_image_b64, width=0, height=10)

    def test_resize_zero_height_raises_error(self, test_image_b64):
        """Test that zero height raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            resize(image_b64=test_image_b64, width=10, height=0)

    def test_resize_negative_width_raises_error(self, test_image_b64):
        """Test that negative width raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            resize(image_b64=test_image_b64, width=-10, height=10)

    def test_resize_negative_height_raises_error(self, test_image_b64):
        """Test that negative height raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            resize(image_b64=test_image_b64, width=10, height=-10)


class TestCrop:
    """Test the crop tool."""

    def test_crop_valid_region(self, test_image_b64_with_pattern):
        """Test cropping a valid region from the center."""
        # Original image is 20x20, crop to center 10x10
        result_b64 = crop(image_b64=test_image_b64_with_pattern, left=5, top=5, right=15, bottom=15)
        
        # Verify result is valid base64
        assert isinstance(result_b64, str)
        decoded = base64.b64decode(result_b64)
        assert len(decoded) > 0
        
        # Verify result decodes to a valid PNG image with correct dimensions
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)

    def test_crop_full_image(self, test_image_b64):
        """Test cropping the entire image (should return same size)."""
        result_b64 = crop(image_b64=test_image_b64, left=0, top=0, right=10, bottom=10)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)

    def test_crop_top_left_corner(self, test_image_b64_with_pattern):
        """Test cropping top-left corner."""
        result_b64 = crop(image_b64=test_image_b64_with_pattern, left=0, top=0, right=10, bottom=10)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)

    def test_crop_bottom_right_corner(self, test_image_b64_with_pattern):
        """Test cropping bottom-right corner."""
        result_b64 = crop(image_b64=test_image_b64_with_pattern, left=10, top=10, right=20, bottom=20)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)

    def test_crop_thin_slice(self, test_image_b64_with_pattern):
        """Test cropping a thin horizontal slice."""
        result_b64 = crop(image_b64=test_image_b64_with_pattern, left=0, top=9, right=20, bottom=11)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (20, 2)

    def test_crop_single_pixel(self, test_image_b64_with_pattern):
        """Test cropping a single pixel region."""
        result_b64 = crop(image_b64=test_image_b64_with_pattern, left=5, top=5, right=6, bottom=6)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (1, 1)

    def test_crop_invalid_left_negative(self, test_image_b64):
        """Test that negative left coordinate raises ValueError."""
        with pytest.raises(ValueError, match="Invalid crop coordinates"):
            crop(image_b64=test_image_b64, left=-1, top=0, right=10, bottom=10)

    def test_crop_invalid_top_negative(self, test_image_b64):
        """Test that negative top coordinate raises ValueError."""
        with pytest.raises(ValueError, match="Invalid crop coordinates"):
            crop(image_b64=test_image_b64, left=0, top=-1, right=10, bottom=10)

    def test_crop_invalid_left_equals_right(self, test_image_b64):
        """Test that left >= right raises ValueError."""
        with pytest.raises(ValueError, match="Invalid crop coordinates"):
            crop(image_b64=test_image_b64, left=5, top=0, right=5, bottom=10)

    def test_crop_invalid_left_greater_than_right(self, test_image_b64):
        """Test that left > right raises ValueError."""
        with pytest.raises(ValueError, match="Invalid crop coordinates"):
            crop(image_b64=test_image_b64, left=10, top=0, right=5, bottom=10)

    def test_crop_invalid_top_equals_bottom(self, test_image_b64):
        """Test that top >= bottom raises ValueError."""
        with pytest.raises(ValueError, match="Invalid crop coordinates"):
            crop(image_b64=test_image_b64, left=0, top=5, right=10, bottom=5)

    def test_crop_invalid_top_greater_than_bottom(self, test_image_b64):
        """Test that top > bottom raises ValueError."""
        with pytest.raises(ValueError, match="Invalid crop coordinates"):
            crop(image_b64=test_image_b64, left=0, top=10, right=10, bottom=5)

    def test_crop_preserves_content(self, test_image_b64_with_pattern):
        """Test that crop preserves image content."""
        result_b64 = crop(image_b64=test_image_b64_with_pattern, left=5, top=5, right=15, bottom=15)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        
        # Image should have pixel data
        pixels = list(output_img.getdata())
        assert len(pixels) > 0
        # Should contain some black pixels from the cross pattern
        assert any(p == (0, 0, 0) for p in pixels), "Cropped image missing expected black pixels"


class TestAddNoise:
    """Test the add_noise tool."""

    def test_add_noise_valid_amount(self, test_image_b64):
        """Test adding noise with a valid amount."""
        result_b64 = add_noise(image_b64=test_image_b64, amount=0.1)
        
        # Verify result is valid base64
        assert isinstance(result_b64, str)
        decoded = base64.b64decode(result_b64)
        assert len(decoded) > 0
        
        # Verify result decodes to a valid PNG image
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)

    def test_add_noise_zero_amount(self, test_image_b64):
        """Test adding noise with zero amount (should return unmodified image)."""
        result_b64 = add_noise(image_b64=test_image_b64, amount=0.0)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)

    def test_add_noise_full_amount(self, test_image_b64):
        """Test adding noise with full amount (1.0, every pixel is noise)."""
        result_b64 = add_noise(image_b64=test_image_b64, amount=1.0)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)
        
        # All pixels should be either black (0,0,0) or white (255,255,255)
        pixels = list(output_img.getdata())
        for p in pixels:
            assert p == (0, 0, 0) or p == (255, 255, 255), f"Unexpected pixel value at full noise: {p}"

    def test_add_noise_medium_amount(self, test_image_b64_with_pattern):
        """Test adding noise with 50% amount."""
        result_b64 = add_noise(image_b64=test_image_b64_with_pattern, amount=0.5)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (20, 20)

    def test_add_noise_invalid_negative_amount(self, test_image_b64):
        """Test that negative amount raises ValueError."""
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            add_noise(image_b64=test_image_b64, amount=-0.1)

    def test_add_noise_invalid_amount_greater_than_one(self, test_image_b64):
        """Test that amount > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            add_noise(image_b64=test_image_b64, amount=1.5)

    def test_add_noise_adds_variation(self, test_image_b64_with_pattern):
        """Test that noise actually modifies the image (not all pixels stay the same)."""
        result_b64 = add_noise(image_b64=test_image_b64_with_pattern, amount=0.2)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        
        # Image should have some black or white pixels from the noise
        pixels = list(output_img.getdata())
        
        # Should contain salt (255,255,255) and/or pepper (0,0,0) from noise
        has_salt = any(p == (255, 255, 255) for p in pixels)
        has_pepper = any(p == (0, 0, 0) for p in pixels)
        
        # At least one type of noise should be present
        assert has_salt or has_pepper, "No noise detected in output image"

    def test_add_noise_preserves_dimensions(self, test_image_b64):
        """Test that noise preserves original image dimensions."""
        for amount in [0.05, 0.2, 0.5]:
            result_b64 = add_noise(image_b64=test_image_b64, amount=amount)
            decoded = base64.b64decode(result_b64)
            output_img = Image.open(io.BytesIO(decoded))
            assert output_img.size == (10, 10), f"Dimensions changed at amount={amount}"

    def test_add_noise_output_format(self, test_image_b64):
        """Test that output is always PNG format."""
        result_b64 = add_noise(image_b64=test_image_b64, amount=0.3)
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"


class TestInvalidInputs:
    """Test error handling with invalid inputs."""

    def test_blur_invalid_base64(self, invalid_base64):
        """Test that blur raises exception with invalid base64."""
        with pytest.raises(Exception):  # base64 decode error or image open error
            blur(image_b64=invalid_base64, radius=2.0)

    def test_rotate_invalid_base64(self, invalid_base64):
        """Test that rotate raises exception with invalid base64."""
        with pytest.raises(Exception):
            rotate(image_b64=invalid_base64, angle=45)

    def test_flip_invalid_base64(self, invalid_base64):
        """Test that flip raises exception with invalid base64."""
        with pytest.raises(Exception):
            flip(image_b64=invalid_base64, direction="horizontal")

    def test_resize_invalid_base64(self, invalid_base64):
        """Test that resize raises exception with invalid base64."""
        with pytest.raises(Exception):
            resize(image_b64=invalid_base64, width=10, height=10)

    def test_crop_invalid_base64(self, invalid_base64):
        """Test that crop raises exception with invalid base64."""
        with pytest.raises(Exception):
            crop(image_b64=invalid_base64, left=0, top=0, right=5, bottom=5)

    def test_add_noise_invalid_base64(self, invalid_base64):
        """Test that add_noise raises exception with invalid base64."""
        with pytest.raises(Exception):
            add_noise(image_b64=invalid_base64, amount=0.1)


class TestGrayscaleImages:
    """Test tools with grayscale images."""

    def test_blur_grayscale(self, test_image_grayscale_b64):
        """Test blur works with grayscale images."""
        result_b64 = blur(image_b64=test_image_grayscale_b64, radius=2.0)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)

    def test_rotate_grayscale(self, test_image_grayscale_b64):
        """Test rotate works with grayscale images."""
        result_b64 = rotate(image_b64=test_image_grayscale_b64, angle=90)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size[0] > 0 and output_img.size[1] > 0

    def test_flip_grayscale(self, test_image_grayscale_b64):
        """Test flip works with grayscale images."""
        result_b64 = flip(image_b64=test_image_grayscale_b64, direction="horizontal")
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)

    def test_resize_grayscale(self, test_image_grayscale_b64):
        """Test resize works with grayscale images."""
        result_b64 = resize(image_b64=test_image_grayscale_b64, width=20, height=20)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (20, 20)

    def test_crop_grayscale(self, test_image_grayscale_b64):
        """Test crop works with grayscale images."""
        result_b64 = crop(image_b64=test_image_grayscale_b64, left=2, top=2, right=8, bottom=8)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (6, 6)

    def test_add_noise_grayscale(self, test_image_grayscale_b64):
        """Test add_noise works with grayscale images."""
        result_b64 = add_noise(image_b64=test_image_grayscale_b64, amount=0.2)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)


class TestRGBAImages:
    """Test tools with RGBA images (with alpha channel)."""

    def test_blur_rgba(self, test_image_rgba_b64):
        """Test blur works with RGBA images."""
        result_b64 = blur(image_b64=test_image_rgba_b64, radius=2.0)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)

    def test_rotate_rgba(self, test_image_rgba_b64):
        """Test rotate works with RGBA images."""
        result_b64 = rotate(image_b64=test_image_rgba_b64, angle=45)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"

    def test_flip_rgba(self, test_image_rgba_b64):
        """Test flip works with RGBA images."""
        result_b64 = flip(image_b64=test_image_rgba_b64, direction="vertical")
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)

    def test_resize_rgba(self, test_image_rgba_b64):
        """Test resize works with RGBA images."""
        result_b64 = resize(image_b64=test_image_rgba_b64, width=15, height=15)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (15, 15)

    def test_crop_rgba(self, test_image_rgba_b64):
        """Test crop works with RGBA images."""
        result_b64 = crop(image_b64=test_image_rgba_b64, left=1, top=1, right=9, bottom=9)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (8, 8)

    def test_add_noise_rgba(self, test_image_rgba_b64):
        """Test add_noise works with RGBA images."""
        result_b64 = add_noise(image_b64=test_image_rgba_b64, amount=0.15)
        
        decoded = base64.b64decode(result_b64)
        output_img = Image.open(io.BytesIO(decoded))
        assert output_img.format == "PNG"
        assert output_img.size == (10, 10)
