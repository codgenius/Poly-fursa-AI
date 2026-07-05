"""
Image composition utilities for object-specific image operations.

Provides helpers for:
- Converting between base64 and bytes
- Cropping regions from images
- Pasting regions back into images

Used by blur_object and crop_object tools to compose MCP-processed regions
back into full images.
"""

import base64
import io
from PIL import Image


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


def crop_image_region(image_bytes: bytes, bbox: tuple[int, int, int, int]) -> bytes:
    """Extract a rectangular region from an image.
    
    Args:
        image_bytes: Full image as bytes
        bbox: Bounding box as (left, top, right, bottom) in pixels
        
    Returns:
        Cropped region as bytes
        
    Raises:
        ValueError: If bbox coordinates are invalid
    """
    left, top, right, bottom = bbox
    
    if left < 0 or top < 0 or right <= left or bottom <= top:
        raise ValueError(
            f"Invalid crop bbox: ({left}, {top}, {right}, {bottom}). "
            "Expected: left < right and top < bottom, all >= 0"
        )
    
    img = Image.open(io.BytesIO(image_bytes))
    
    # Clamp to image bounds
    img_width, img_height = img.size
    left = max(0, min(left, img_width))
    top = max(0, min(top, img_height))
    right = max(left, min(right, img_width))
    bottom = max(top, min(bottom, img_height))
    
    cropped = img.crop((left, top, right, bottom))
    
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()


def paste_image_region(
    full_image_bytes: bytes,
    cropped_region_bytes: bytes,
    bbox: tuple[int, int, int, int]
) -> bytes:
    """Paste a cropped region back into a full image at the specified location.
    
    Used after MCP processes a region (e.g., blur_object blurs a region,
    then pastes the blurred region back into the original full image).
    
    Args:
        full_image_bytes: Full image as bytes
        cropped_region_bytes: Processed region (e.g., blurred) as bytes
        bbox: Bounding box (left, top, right, bottom) where region should be pasted
        
    Returns:
        Full image with region pasted, as bytes
        
    Raises:
        ValueError: If region size doesn't match bbox dimensions
    """
    left, top, right, bottom = bbox
    
    if left < 0 or top < 0 or right <= left or bottom <= top:
        raise ValueError(
            f"Invalid paste bbox: ({left}, {top}, {right}, {bottom}). "
            "Expected: left < right and top < bottom, all >= 0"
        )
    
    full_img = Image.open(io.BytesIO(full_image_bytes))
    region_img = Image.open(io.BytesIO(cropped_region_bytes))
    
    # Validate region size matches bbox
    bbox_width = right - left
    bbox_height = bottom - top
    region_width, region_height = region_img.size
    
    if region_width != bbox_width or region_height != bbox_height:
        raise ValueError(
            f"Region size ({region_width}x{region_height}) does not match "
            f"bbox size ({bbox_width}x{bbox_height}) at ({left}, {top}, {right}, {bottom})"
        )
    
    # Ensure region has alpha channel if full image does (for proper compositing)
    if full_img.mode in ("RGBA", "LA"):
        if region_img.mode != "RGBA":
            region_img = region_img.convert("RGBA")
    
    # Paste region into full image
    full_img.paste(region_img, (left, top))
    
    buf = io.BytesIO()
    full_img.save(buf, format="PNG")
    return buf.getvalue()
