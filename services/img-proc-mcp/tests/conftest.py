"""
Shared pytest configuration and fixtures for image processing tests.
"""
import base64
import io
import sys
import os
import pytest
from PIL import Image

# Add parent directory to path to import app
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def test_image_b64():
    """
    Generate a small base64-encoded test image.
    Creates a 10x10 RGB image with a gradient for rotation/flip testing.
    Returns base64-encoded PNG.
    """
    img = Image.new("RGB", (10, 10), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def test_image_b64_with_pattern():
    """
    Generate a base64-encoded test image with a distinct pattern.
    Creates a 20x20 image with a cross pattern for rotation/flip testing.
    Returns base64-encoded PNG.
    """
    img = Image.new("RGB", (20, 20), color="white")
    pixels = img.load()
    
    # Draw a cross pattern (easier to verify rotation/flip worked)
    for i in range(20):
        pixels[10, i] = (0, 0, 0)  # Vertical line
        pixels[i, 10] = (0, 0, 0)  # Horizontal line
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def test_image_grayscale_b64():
    """
    Generate a base64-encoded grayscale test image.
    Creates a 10x10 grayscale image.
    Returns base64-encoded PNG.
    """
    img = Image.new("L", (10, 10), color=128)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def test_image_rgba_b64():
    """
    Generate a base64-encoded RGBA test image.
    Creates a 10x10 RGBA image with semi-transparent red.
    Returns base64-encoded PNG.
    """
    img = Image.new("RGBA", (10, 10), color=(255, 0, 0, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def invalid_base64():
    """Return an invalid base64 string."""
    return "this_is_not_valid_base64!!!"
