# services/img-proc-mcp/app.py
import base64
import io
import numpy as np
from mcp.server.fastmcp import FastMCP
from PIL import Image, ImageFilter

mcp = FastMCP("img-proc")

def _decode(b64: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(b64)))

def _encode(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

@mcp.tool()
def blur(image_b64: str, radius: float = 2.0) -> str:
    """Apply Gaussian blur to an image. Returns base64-encoded PNG."""
    if radius < 0:
        raise ValueError(f"radius must be non-negative, got {radius}")
    img = _decode(image_b64).filter(ImageFilter.GaussianBlur(radius))
    return _encode(img)

@mcp.tool()
def rotate(image_b64: str, angle: float) -> str:
    """Rotate an image by the given angle in degrees. Returns base64-encoded PNG."""
    img = _decode(image_b64).rotate(angle, expand=False)
    return _encode(img)

@mcp.tool()
def flip(image_b64: str, direction: str) -> str:
    """Flip an image horizontally or vertically. Direction must be 'horizontal' or 'vertical'. Returns base64-encoded PNG."""
    img = _decode(image_b64)
    if direction.lower() == "horizontal":
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    elif direction.lower() == "vertical":
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    else:
        raise ValueError(f"Invalid direction: {direction}. Must be 'horizontal' or 'vertical'.")
    return _encode(img)

@mcp.tool()
def resize(image_b64: str, width: int, height: int) -> str:
    """Resize an image to the given width and height in pixels. Returns base64-encoded PNG."""
    if width <= 0 or height <= 0:
        raise ValueError(f"Width and height must be positive integers, got width={width}, height={height}")
    img = _decode(image_b64).resize((width, height), Image.Resampling.LANCZOS)
    return _encode(img)

@mcp.tool()
def crop(image_b64: str, left: int, top: int, right: int, bottom: int) -> str:
    """Crop an image by bounding box coordinates (left, top, right, bottom). Returns base64-encoded PNG."""
    if left < 0 or top < 0 or right <= left or bottom <= top:
        raise ValueError(
            f"Invalid crop coordinates: left={left}, top={top}, right={right}, bottom={bottom}. "
            "Require: 0 <= left < right and 0 <= top < bottom"
        )
    img = _decode(image_b64).crop((left, top, right, bottom))
    return _encode(img)

@mcp.tool()
def add_noise(image_b64: str, amount: float = 0.1) -> str:
    """Add salt-and-pepper noise to an image. amount is the proportion of pixels to noise (0.0-1.0). Returns base64-encoded PNG."""
    if amount < 0 or amount > 1:
        raise ValueError(f"amount must be between 0.0 and 1.0, got {amount}")
    
    img = _decode(image_b64)
    img_array = np.array(img, dtype=np.uint8)
    
    # Get image dimensions
    h, w = img_array.shape[:2]
    
    # Create noise positions: True where noise should be applied
    noise_coords = np.random.random((h, w)) < amount
    # Create salt/pepper choice: True for salt (white), False for pepper (black)
    salt_pepper = np.random.random((h, w)) < 0.5
    
    # Apply noise to each channel (handles both RGB and grayscale)
    if len(img_array.shape) == 3:
        for c in range(img_array.shape[2]):
            img_array[noise_coords & salt_pepper, c] = 255  # salt (white)
            img_array[noise_coords & ~salt_pepper, c] = 0   # pepper (black)
    else:
        img_array[noise_coords & salt_pepper] = 255  # salt
        img_array[noise_coords & ~salt_pepper] = 0   # pepper
    
    img = Image.fromarray(img_array)
    return _encode(img)


if __name__ == "__main__":
    mcp.run()