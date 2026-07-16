# services/img-proc-mcp/app.py
import base64
import io
import json
import numpy as np
from fastmcp import FastMCP
from PIL import Image, ImageFilter

mcp = FastMCP("img-proc")

def _decode(b64: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(b64)))

def _encode(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

@mcp.tool()
def blur(image_b64: str, left: int = 0, top: int = 0, right: int = 0, bottom: int = 0, radius: float = 2.0) -> str:
    """Apply Gaussian blur to an image or a region.
    
    If all coordinates (left, top, right, bottom) are 0, blurs the entire image.
    Otherwise, blurs only the specified region and returns the full image with the blurred region pasted back.
    
    Args:
        image_b64: Base64-encoded image
        left, top, right, bottom: Region coordinates (optional, default 0,0,0,0 = whole image)
        radius: Blur radius in pixels (default 2.0)
        
    Returns:
        Base64-encoded modified image
        
    Raises:
        ValueError: If radius is negative or coordinates are invalid (when region specified)
    """
    if radius < 0:
        raise ValueError(f"radius must be non-negative, got {radius}")
    
    img = _decode(image_b64)
    
    # Check if region coordinates are all zero (blur whole image)
    if left == 0 and top == 0 and right == 0 and bottom == 0:
        # Blur entire image
        blurred_img = img.filter(ImageFilter.GaussianBlur(radius))
        return _encode(blurred_img)
    
    # Blur specific region
    if left < 0 or top < 0 or right <= left or bottom <= top:
        raise ValueError(
            f"Invalid region coordinates: left={left}, top={top}, right={right}, bottom={bottom}. "
            "Require: 0 <= left < right and 0 <= top < bottom"
        )
    
    # Crop region
    region = img.crop((left, top, right, bottom))
    # Blur region
    blurred_region = region.filter(ImageFilter.GaussianBlur(radius))
    # Paste back into full image
    img.paste(blurred_region, (left, top))
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
def crop(image_b64: str, left: int = 0, top: int = 0, right: int = 0, bottom: int = 0) -> str:
    """Crop an image by bounding box coordinates (left, top, right, bottom).
    
    If all coordinates are 0, returns the full image unchanged.
    Otherwise, returns only the cropped region.
    
    Args:
        image_b64: Base64-encoded image
        left, top, right, bottom: Bounding box coordinates (all 0 = return full image)
        
    Returns:
        Base64-encoded PNG (full image or cropped region)
        
    Raises:
        ValueError: If bbox coordinates are invalid (when region specified)
    """
    img = _decode(image_b64)
    
    # If no crop region specified (all zeros), return full image
    if left == 0 and top == 0 and right == 0 and bottom == 0:
        return _encode(img)
    
    # Validate coordinates
    if left < 0 or top < 0 or right <= left or bottom <= top:
        raise ValueError(
            f"Invalid crop coordinates: left={left}, top={top}, right={right}, bottom={bottom}. "
            "Require: 0 <= left < right and 0 <= top < bottom"
        )
    
    cropped_img = img.crop((left, top, right, bottom))
    return _encode(cropped_img)

@mcp.tool()
def add_noise(image_b64: str, left: int = 0, top: int = 0, right: int = 0, bottom: int = 0, amount: float = 0.1) -> str:
    """Add salt-and-pepper noise to an image or a region.
    
    If all coordinates (left, top, right, bottom) are 0, adds noise to the entire image.
    Otherwise, adds noise only to the specified region and returns the full image with the noised region pasted back.
    
    Args:
        image_b64: Base64-encoded image
        left, top, right, bottom: Region coordinates (optional, default 0,0,0,0 = whole image)
        amount: Noise amount proportion (0.0-1.0, default 0.1)
        
    Returns:
        Base64-encoded modified image
        
    Raises:
        ValueError: If amount is invalid (not 0.0-1.0) or coordinates are invalid (when region specified)
    """
    if amount < 0 or amount > 1:
        raise ValueError(f"amount must be between 0.0 and 1.0, got {amount}")
    
    img = _decode(image_b64)
    
    # Check if region coordinates are all zero (noise whole image)
    if left == 0 and top == 0 and right == 0 and bottom == 0:
        # Add noise to entire image
        img_array = np.array(img, dtype=np.uint8)
        h, w = img_array.shape[:2]
        noise_coords = np.random.random((h, w)) < amount
        salt_pepper = np.random.random((h, w)) < 0.5
        
        if len(img_array.shape) == 3:
            for c in range(img_array.shape[2]):
                img_array[noise_coords & salt_pepper, c] = 255
                img_array[noise_coords & ~salt_pepper, c] = 0
        else:
            img_array[noise_coords & salt_pepper] = 255
            img_array[noise_coords & ~salt_pepper] = 0
        
        result_img = Image.fromarray(img_array)
        return _encode(result_img)
    
    # Add noise to specific region
    if left < 0 or top < 0 or right <= left or bottom <= top:
        raise ValueError(
            f"Invalid region coordinates: left={left}, top={top}, right={right}, bottom={bottom}. "
            "Require: 0 <= left < right and 0 <= top < bottom"
        )
    
    # Crop region
    region = img.crop((left, top, right, bottom))
    # Add noise to region
    region_array = np.array(region, dtype=np.uint8)
    h, w = region_array.shape[:2]
    noise_coords = np.random.random((h, w)) < amount
    salt_pepper = np.random.random((h, w)) < 0.5
    
    if len(region_array.shape) == 3:
        for c in range(region_array.shape[2]):
            region_array[noise_coords & salt_pepper, c] = 255
            region_array[noise_coords & ~salt_pepper, c] = 0
    else:
        region_array[noise_coords & salt_pepper] = 255
        region_array[noise_coords & ~salt_pepper] = 0
    
    noisy_region = Image.fromarray(region_array)
    # Paste back into full image
    img.paste(noisy_region, (left, top))
    return _encode(img)


def _paste_region(full_image_b64: str, region_b64: str, left: int, top: int, right: int, bottom: int) -> str:
    """Internal helper: Paste a processed region back into a full image at specified coordinates.
    
    Used internally by blur() and add_noise() to composite region-specific transformations back into the full image.
    
    Args:
        full_image_b64: Full original image as base64-encoded PNG
        region_b64: Processed region to paste as base64-encoded PNG
        left, top, right, bottom: Bounding box coordinates where region should be pasted
        
    Returns:
        Full image with region pasted, as base64-encoded PNG
        
    Raises:
        ValueError: If bbox coordinates are invalid or region size doesn't match bbox dimensions
    """
    if left < 0 or top < 0 or right <= left or bottom <= top:
        raise ValueError(
            f"Invalid bbox coordinates: left={left}, top={top}, right={right}, bottom={bottom}. "
            "Require: 0 <= left < right and 0 <= top < bottom"
        )
    
    full_img = _decode(full_image_b64)
    region_img = _decode(region_b64)
    
    # Validate region size matches bbox dimensions
    bbox_width = right - left
    bbox_height = bottom - top
    region_width, region_height = region_img.size
    
    if region_width != bbox_width or region_height != bbox_height:
        raise ValueError(
            f"Region size ({region_width}x{region_height}) does not match "
            f"bbox dimensions ({bbox_width}x{bbox_height}) at coordinates ({left}, {top}, {right}, {bottom})"
        )
    
    # Ensure region has alpha channel if full image does (for proper compositing)
    if full_img.mode in ("RGBA", "LA"):
        if region_img.mode != "RGBA":
            region_img = region_img.convert("RGBA")
    
    # Paste region into full image
    full_img.paste(region_img, (left, top))
    
    return _encode(full_img)


@mcp.tool()
def paste_region(full_image_b64: str, region_b64: str, left: int, top: int, right: int, bottom: int) -> str:
    """Paste a processed region back into a full image at specified coordinates.
    
    Used to composite object-specific transformations (e.g., a blurred region) back into the full image.
    
    Args:
        full_image_b64: Full original image as base64-encoded PNG
        region_b64: Processed region to paste as base64-encoded PNG
        left, top, right, bottom: Bounding box coordinates where region should be pasted
        
    Returns:
        Full image with region pasted, as base64-encoded PNG
        
    Raises:
        ValueError: If bbox coordinates are invalid or region size doesn't match bbox dimensions
    """
    return _paste_region(full_image_b64, region_b64, left, top, right, bottom)


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=9000)
