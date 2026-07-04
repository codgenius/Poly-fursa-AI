# Image Processing MCP Server

This is a Model Context Protocol (MCP) server that exposes image manipulation tools using FastMCP and Pillow. The server accepts base64-encoded images and returns base64-encoded PNG images.

## Available Tools

- **blur**: Apply Gaussian blur with a given radius
- **rotate**: Rotate image by a given angle in degrees
- **flip**: Flip horizontally or vertically
- **resize**: Resize to given width and height
- **crop**: Crop a region by bounding box coordinates (left, top, right, bottom)
- **add_noise**: Add salt-and-pepper noise with configurable amount (0.0-1.0)

## Setup Instructions

1. Make sure the shared project virtualenv is activated (see the root README).

2. Install requirements (from `services/img-proc-mcp/`):

```bash
pip install -r requirements.txt
```

3. Run the MCP server:

```bash
python app.py
```

The server will start and be ready to accept tool calls.

## Testing

Run all tests:

```bash
pytest tests/test_tools.py -v
```

Run specific test class:

```bash
pytest tests/test_tools.py::TestRotate -v
```

Run with coverage:

```bash
pytest tests/ --cov=app --cov-report=html
```

## Testing with MCP Inspector

To interactively test tools with the MCP Inspector:

```bash
mcp dev app.py
```

This opens an interactive CLI where you can call tools with JSON arguments. Example:

```json
{
  "tool_name": "blur",
  "arguments": {
    "image_b64": "iVBORw0KGgoAAAANS...",
    "radius": 2.0
  }
}
```

## Input/Output Format

All tools:
- **Input**: `image_b64` (string) — base64-encoded PNG image
- **Output**: base64-encoded PNG image

Additional parameters vary by tool. Refer to function docstrings for details.

## Supported Image Formats

Tools work with:
- RGB images (3 channels)
- Grayscale images (1 channel)
- RGBA images (4 channels with alpha)

Output is always PNG format.
