"""
MCP Client wrapper for sync Agent tools.

Wraps langchain-mcp-adapters (async) with sync public methods for use in Agent tools.

Usage:
    mcp_client = MCPClient()
    blurred_b64 = mcp_client.blur(image_b64, radius=5.0)
    cropped_b64 = mcp_client.crop(image_b64, left, top, right, bottom)
"""

import asyncio
import logging
from typing import Optional
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)


class MCPClient:
    """
    Synchronous wrapper around langchain-mcp-adapters for image processing tools.
    
    Exposes sync public methods (blur, crop, rotate, etc.) that call async
    MultiServerMCPClient internally.
    
    Design:
    - All public methods are sync (compatible with sync Agent tools)
    - Internal async implementations use langchain-mcp-adapters
    - Event loop is created/destroyed per call (safe for sync context)
    - Response parsing handles langchain-mcp-adapters format
    """
    
    def __init__(self, url: str = "http://localhost:9000/mcp"):
        """Initialize MCP client.
        
        Args:
            url: MCP server endpoint (default: http://localhost:9000/mcp)
        """
        self.url = url
        self.config = {
            "img-proc": {
                "url": url,
                "transport": "http",
            }
        }
        self._client: Optional[MultiServerMCPClient] = None
    
    async def _get_client_async(self) -> MultiServerMCPClient:
        """Lazy-initialize async MCP client.
        
        Returns:
            MultiServerMCPClient instance
        """
        if not self._client:
            self._client = MultiServerMCPClient(self.config)
        return self._client
    
    def _run_async(self, coro):
        """Execute async coroutine from sync context using new event loop.
        
        Args:
            coro: Coroutine to execute
            
        Returns:
            Result of coroutine
            
        Raises:
            RuntimeError: If called from within an async context
        """
        try:
            # Check if there's already a running loop
            loop = asyncio.get_running_loop()
            # If we get here, there's a running loop and we can't use run_until_complete
            raise RuntimeError(
                "Cannot use sync MCPClient methods from within an async context. "
                "MCPClient is designed for sync Agent tools only."
            )
        except RuntimeError as e:
            if "no running event loop" in str(e) or "There is no current event loop" in str(e):
                # No running loop - create one and execute
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(coro)
                finally:
                    loop.close()
            else:
                # Some other runtime error (like our custom message above)
                raise
    
    @staticmethod
    def _extract_b64(result) -> str:
        """Parse langchain-mcp-adapters response to extract base64 string.
        
        Response format from MCP adapter (verified in spike test):
        [{'type': 'text', 'text': 'iVBORw0KGgo...'}]
        
        Args:
            result: Response from langchain-mcp-adapters tool.ainvoke()
            
        Returns:
            Base64-encoded string
            
        Raises:
            ValueError: If response format is unexpected
        """
        if isinstance(result, list) and len(result) > 0:
            first_item = result[0]
            if isinstance(first_item, dict) and "text" in first_item:
                return first_item["text"]
        elif isinstance(result, dict):
            if "text" in result:
                return result["text"]
        
        raise ValueError(f"Unexpected MCP response format: {result}")
    
    # ========================================================================
    # PUBLIC SYNC METHODS - Used by Agent tools (@tool def)
    # ========================================================================
    
    def blur(self, image_b64: str, radius: float = 2.0) -> str:
        """Apply Gaussian blur to an image.
        
        Args:
            image_b64: Base64-encoded image (PNG, JPEG, etc.)
            radius: Blur radius in pixels (default 2.0)
            
        Returns:
            Base64-encoded blurred image
            
        Raises:
            ValueError: If MCP server returns unexpected response
        """
        return self._run_async(self._blur_async(image_b64, radius))
    
    def crop(self, image_b64: str, left: int, top: int, right: int, bottom: int) -> str:
        """Crop an image to a bounding box.
        
        Args:
            image_b64: Base64-encoded image
            left: Left edge x coordinate
            top: Top edge y coordinate
            right: Right edge x coordinate
            bottom: Bottom edge y coordinate
            
        Returns:
            Base64-encoded cropped image
            
        Raises:
            ValueError: If MCP server returns unexpected response
        """
        return self._run_async(self._crop_async(image_b64, left, top, right, bottom))
    
    def rotate(self, image_b64: str, angle: float) -> str:
        """Rotate an image by angle in degrees.
        
        Args:
            image_b64: Base64-encoded image
            angle: Rotation angle in degrees
            
        Returns:
            Base64-encoded rotated image
            
        Raises:
            ValueError: If MCP server returns unexpected response
        """
        return self._run_async(self._rotate_async(image_b64, angle))
    
    def flip(self, image_b64: str, direction: str) -> str:
        """Flip an image horizontally or vertically.
        
        Args:
            image_b64: Base64-encoded image
            direction: "horizontal" or "vertical"
            
        Returns:
            Base64-encoded flipped image
            
        Raises:
            ValueError: If MCP server returns unexpected response
        """
        return self._run_async(self._flip_async(image_b64, direction))
    
    def resize(self, image_b64: str, width: int, height: int) -> str:
        """Resize an image to specified dimensions.
        
        Args:
            image_b64: Base64-encoded image
            width: Target width in pixels
            height: Target height in pixels
            
        Returns:
            Base64-encoded resized image
            
        Raises:
            ValueError: If MCP server returns unexpected response
        """
        return self._run_async(self._resize_async(image_b64, width, height))
    
    def add_noise(self, image_b64: str, amount: float = 0.1) -> str:
        """Add salt-and-pepper noise to an image.
        
        Args:
            image_b64: Base64-encoded image
            amount: Noise amount proportion (0.0-1.0, default 0.1)
            
        Returns:
            Base64-encoded noisy image
            
        Raises:
            ValueError: If MCP server returns unexpected response
        """
        return self._run_async(self._add_noise_async(image_b64, amount))
    
    # ========================================================================
    # PRIVATE ASYNC METHODS - Internal implementations using langchain-mcp-adapters
    # ========================================================================
    
    async def _blur_async(self, image_b64: str, radius: float = 2.0) -> str:
        """Internal async blur implementation."""
        client = await self._get_client_async()
        tools = await client.get_tools(server_name="img-proc")
        blur_tool = next((t for t in tools if t.name == "blur"), None)
        if not blur_tool:
            raise ValueError("blur tool not found in MCP server")
        result = await blur_tool.ainvoke({"image_b64": image_b64, "radius": radius})
        return self._extract_b64(result)
    
    async def _crop_async(self, image_b64: str, left: int, top: int, right: int, bottom: int) -> str:
        """Internal async crop implementation."""
        client = await self._get_client_async()
        tools = await client.get_tools(server_name="img-proc")
        crop_tool = next((t for t in tools if t.name == "crop"), None)
        if not crop_tool:
            raise ValueError("crop tool not found in MCP server")
        result = await crop_tool.ainvoke({
            "image_b64": image_b64,
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom
        })
        return self._extract_b64(result)
    
    async def _rotate_async(self, image_b64: str, angle: float) -> str:
        """Internal async rotate implementation."""
        client = await self._get_client_async()
        tools = await client.get_tools(server_name="img-proc")
        rotate_tool = next((t for t in tools if t.name == "rotate"), None)
        if not rotate_tool:
            raise ValueError("rotate tool not found in MCP server")
        result = await rotate_tool.ainvoke({"image_b64": image_b64, "angle": angle})
        return self._extract_b64(result)
    
    async def _flip_async(self, image_b64: str, direction: str) -> str:
        """Internal async flip implementation."""
        client = await self._get_client_async()
        tools = await client.get_tools(server_name="img-proc")
        flip_tool = next((t for t in tools if t.name == "flip"), None)
        if not flip_tool:
            raise ValueError("flip tool not found in MCP server")
        result = await flip_tool.ainvoke({"image_b64": image_b64, "direction": direction})
        return self._extract_b64(result)
    
    async def _resize_async(self, image_b64: str, width: int, height: int) -> str:
        """Internal async resize implementation."""
        client = await self._get_client_async()
        tools = await client.get_tools(server_name="img-proc")
        resize_tool = next((t for t in tools if t.name == "resize"), None)
        if not resize_tool:
            raise ValueError("resize tool not found in MCP server")
        result = await resize_tool.ainvoke({
            "image_b64": image_b64,
            "width": width,
            "height": height
        })
        return self._extract_b64(result)
    
    async def _add_noise_async(self, image_b64: str, amount: float = 0.1) -> str:
        """Internal async add_noise implementation."""
        client = await self._get_client_async()
        tools = await client.get_tools(server_name="img-proc")
        noise_tool = next((t for t in tools if t.name == "add_noise"), None)
        if not noise_tool:
            raise ValueError("add_noise tool not found in MCP server")
        result = await noise_tool.ainvoke({"image_b64": image_b64, "amount": amount})
        return self._extract_b64(result)
