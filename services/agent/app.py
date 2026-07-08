import base64
import io
import json
import logging
import os
from contextvars import ContextVar
from typing import Optional
import uuid

import time

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logging.getLogger("langchain").setLevel(logging.DEBUG)
logging.getLogger("langchain_core").setLevel(logging.DEBUG)

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain.chat_models import init_chat_model
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from s3_utils import upload_image_to_s3, download_image_from_s3
from image_utils import bytes_to_b64
from mcp_client import MCPClient

YOLO_SERVICE_URL = os.environ.get("YOLO_SERVICE_URL", "http://localhost:8080")
MODEL = os.environ.get("MODEL")

# Text-only models - format: "provider:model_id" or "bedrock:model_id"
ALLOWED_MODELS = {
    "openai:gpt-5.4-mini",
    "anthropic:claude-haiku-4-5",
    "bedrock:amazon.nova-micro-v1:0",
    "bedrock:anthropic.claude-3-5-sonnet-20241022-v2:0",
}

if MODEL not in ALLOWED_MODELS:
    allowed_list = "\n  ".join(sorted(ALLOWED_MODELS))
    raise SystemExit(
        f"\n[ERROR] MODEL='{MODEL}' is not allowed.\n"
        f"Set MODEL in your .env to one of the supported text-only models:\n  {allowed_list}\n"
    )

SYSTEM_PROMPT = (
    "You are an AI vision assistant. You help users understand and analyze images. "
    "CRITICAL: When the user asks to blur, crop, rotate, flip, resize, add noise to, or modify an image in any way, "
    "you MUST call the corresponding tool EVERY TIME. Never claim an operation succeeded unless you actually invoked and executed the tool. "
    "Each user request is independent - do not copy or repeat previous assistant responses. Always generate fresh tool invocations for each request. "
    "If a tool call fails or cannot be performed, explicitly say you could not complete the operation. "
    "Available tools: detect_objects, blur_object, crop_object, blur_image, rotate_image, flip_image, resize_image, add_noise_image, add_noise_object."
)

# Context variables for tracking image metadata during agent execution
_current_image_s3_key: ContextVar[Optional[str]] = ContextVar("current_image_s3_key", default=None)
_current_chat_id: ContextVar[Optional[str]] = ContextVar("current_chat_id", default=None)
_current_prediction_id: ContextVar[Optional[str]] = ContextVar("current_prediction_id", default=None)
_current_image_b64: ContextVar[Optional[str]] = ContextVar("current_image_b64", default=None)
_current_detections: ContextVar[list] = ContextVar("current_detections", default=[])
_detection_result = {
    "prediction_id": None,
    "annotated_image": None,
}

# Persistent chat state indexed by chat_id
_chat_image_state: dict[str, dict] = {}
# Structure: {
#   "chat_id": {
#       "original_s3_key": str,
#       "current_s3_key": str,
#       "detections": list,  # Cached YOLO detections from latest detect_objects call
#   }
# }

@tool
def detect_objects() -> str:
    """Detect and identify objects in the image provided by the user using YOLO object detection."""
    image_s3_key = _current_image_s3_key.get()
    chat_id = _current_chat_id.get()
    
    # Generate fresh prediction_id for this detection call (not reusing per-request one)
    # This ensures YOLO doesn't see duplicate UIDs if detect_objects is called multiple times
    detection_prediction_id = str(uuid.uuid4())
    
    if not image_s3_key:
        return json.dumps({"error": "No image was provided by the user."})

    with httpx.Client(timeout=30.0) as client:
        payload = {
            "image_s3_key": image_s3_key,
            "chat_id": chat_id,
            "prediction_id": detection_prediction_id,
        }
        logging.info(f"🔍 DEBUG: Sending request to YOLO")
        logging.info(f"   YOLO_SERVICE_URL: {YOLO_SERVICE_URL}")
        logging.info(f"   Endpoint: {YOLO_SERVICE_URL}/predict")
        logging.info(f"   Payload: {json.dumps(payload, indent=2)}")
        logging.info(f"   Content-Type: application/json")
        
        response = client.post(
            f"{YOLO_SERVICE_URL}/predict",
            json=payload
        )
        
        logging.info(f"🔍 DEBUG: YOLO Response Received")
        logging.info(f"   Status Code: {response.status_code}")
        logging.info(f"   Headers: {dict(response.headers)}")
        logging.info(f"   Body: {response.text}")
        
        response.raise_for_status()

        prediction_data = response.json()
        prediction_id_from_response = prediction_data.get("prediction_uid")

        if prediction_id_from_response:
            _detection_result["prediction_id"] = prediction_id_from_response

            image_response = client.get(
                f"{YOLO_SERVICE_URL}/prediction/{prediction_id_from_response}/image"
            )
            image_response.raise_for_status()

            annotated_image_b64 = base64.b64encode(image_response.content).decode("utf-8")
            _detection_result["annotated_image"] = annotated_image_b64
            
            # Keep working image as clean version (without boxes) - annotated is display-only
            # Tools like blur_object should work on the original, not the version with boxes
        
        # Fetch full detection objects from YOLO using the prediction_id
        detections = []
        if prediction_id_from_response:
            detections_response = client.get(
                f"{YOLO_SERVICE_URL}/prediction/{prediction_id_from_response}"
            )
            detections_response.raise_for_status()
            detection_data = detections_response.json()
            
            # Parse detection_objects from YOLO response
            if "detection_objects" in detection_data:
                for idx, obj in enumerate(detection_data["detection_objects"]):
                    # Parse box format: JSON array string "[x1, y1, x2, y2]"
                    try:
                        box_str = obj.get("box", "[]")
                        # Handle both JSON array string and direct string formats
                        if isinstance(box_str, str):
                            box_coords = json.loads(box_str)
                        else:
                            box_coords = box_str
                        x1, y1, x2, y2 = box_coords[0], box_coords[1], box_coords[2], box_coords[3]
                    except (ValueError, IndexError, json.JSONDecodeError, TypeError):
                        x1, y1, x2, y2 = 0, 0, 0, 0
                    
                    detections.append({
                        "id": idx,
                        "label": obj.get("label", "unknown"),
                        "bbox": (x1, y1, x2, y2),
                        "confidence": obj.get("score", 0.0),
                    })
        
        _current_detections.set(detections)
        # Also save to persistent state so other tools in the same request can access detections
        # (ContextVar isolation prevents same-request tool calls from seeing ContextVar values)
        if chat_id and chat_id in _chat_image_state:
            _chat_image_state[chat_id]["detections"] = detections
        logging.info(f"✅ Parsed {len(detections)} detections and stored in _current_detections context")
        for i, det in enumerate(detections):
            logging.info(f"   [{i}] {det['label']} (confidence: {det['confidence']:.2f})")

    return json.dumps(prediction_data)

def _set_current_image(image_b64: str):
    """Update all image state tracking with a modified image.
    
    Ensures consistency across ContextVars and _detection_result dict,
    which is necessary to persist changes across tool context boundaries (Phase 5).
    """
    _current_image_b64.set(image_b64)
    _detection_result["annotated_image"] = image_b64
    _detection_result["final_image_b64"] = image_b64

def _validate_and_get_detection(object_id: int):
    """Validate context and get detection object.
    
    Returns:
        tuple: (detection_dict, label_str) on success
        str: JSON error response on failure
    """
    image_b64 = _current_image_b64.get()
    detections = _current_detections.get()
    chat_id = _current_chat_id.get()
    
    logging.info(f"🔍 _validate_and_get_detection({object_id}): detections_contextvar={len(detections) if detections else 0}, chat_id={chat_id}")
    
    # Fallback to persistent state if ContextVar is empty (ContextVar isolation across tool calls)
    if not detections and chat_id and chat_id in _chat_image_state:
        detections = _chat_image_state[chat_id].get("detections", [])
        logging.info(f"   ↳ Restored {len(detections)} detections from persistent state")
    
    if not image_b64:
        return json.dumps({"error": "No image available. Please detect objects first."})
    
    if not detections:
        logging.info(f"   ↳ No detections available (none in contextvar, fallback empty/missing)")
        return json.dumps({"error": "No detections available. Please detect objects first."})
    
    if object_id < 0 or object_id >= len(detections):
        return json.dumps({"error": f"Invalid object_id {object_id}. Available objects: 0-{len(detections)-1}"})
    
    detection = detections[object_id]
    return detection, detection["label"]

def _update_image_and_respond(modified_image_b64: str, label: str, object_id: int, action: str, details: str = ""):
    """Update context and detection result, return success response.
    
    Args:
        modified_image_b64: Updated image in base64
        label: Object label for message
        object_id: Object ID for message
        action: Action name (e.g., "blurred", "cropped")
        details: Additional details for message (e.g., "with radius 5.0")
    
    Returns:
        str: JSON success response
    """
    _set_current_image(modified_image_b64)
    
    message = f"Successfully {action} {label} (object #{object_id})"
    if details:
        message += f" {details}"
    
    return json.dumps({
        "success": True,
        "message": message
    })

@tool
def blur_object(object_id: int, radius: float = 2.0) -> str:
    """Blur a detected object in the image. Specify the object ID and blur radius (default 2.0)."""
    # Step 1: Validate and get detection
    result = _validate_and_get_detection(object_id)
    if isinstance(result, str):
        return result  # Error response
    detection, label = result
    bbox = detection["bbox"]
    # Convert bbox coordinates to integers (YOLO returns floats)
    left, top, right, bottom = tuple(int(round(coord)) for coord in bbox)
    
    # Step 2: Get current image
    image_b64 = _current_image_b64.get()
    
    try:
        client = MCPClient()
        
        # Step 3: MCP crop
        logging.info(f"🔍 blur_object: Cropping object {object_id} bbox ({left}, {top}, {right}, {bottom})")
        cropped_b64 = client.crop(image_b64, left, top, right, bottom)
        logging.info(f"   ✓ Cropped: {len(cropped_b64)} chars")
        
        # Step 4: MCP blur
        logging.info(f"🔍 blur_object: Blurring cropped region (radius={radius})")
        blurred_b64 = client.blur(cropped_b64, radius)
        logging.info(f"   ✓ Blurred: {len(blurred_b64)} chars")
        
        # Step 5: MCP paste_region
        logging.info(f"🔍 blur_object: Pasting blurred region back into full image")
        modified_image_b64 = client.paste_region(image_b64, blurred_b64, left, top, right, bottom)
        logging.info(f"   ✓ Composited: {len(modified_image_b64)} chars")
        
        # Step 6: Update and respond
        return _update_image_and_respond(
            modified_image_b64,
            label,
            object_id,
            "blurred",
            f"with radius {radius}"
        )
    
    except Exception as e:
        logging.error(f"❌ blur_object failed: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Failed to blur object: {str(e)}"})

@tool
def crop_object(object_id: int, left_offset: int = 0, top_offset: int = 0, right_offset: int = 0, bottom_offset: int = 0) -> str:
    """Crop a detected object from the image. Specify the object ID and optional pixel offsets to expand/shrink the crop region."""
    # Validate and get detection
    result = _validate_and_get_detection(object_id)
    if isinstance(result, str):
        return result  # Error response
    detection, label = result
    bbox = detection["bbox"]
    # Convert bbox coordinates to integers (YOLO returns floats)
    bbox = tuple(int(round(coord)) for coord in bbox)
    
    image_b64 = _current_image_b64.get()
    
    # Apply offsets to bbox: (x1, y1, x2, y2)
    x1, y1, x2, y2 = bbox
    left = int(x1 - left_offset)
    top = int(y1 - top_offset)
    right = int(x2 + right_offset)
    bottom = int(y2 + bottom_offset)
    
    try:
        # Get current image and crop region
        client = MCPClient()
        cropped_b64 = client.crop(image_b64, left, top, right, bottom)
        
        # Update and respond
        return _update_image_and_respond(
            cropped_b64,
            label,
            object_id,
            "cropped",
            f"to region [{left}, {top}, {right}, {bottom}]"
        )
    
    except Exception as e:
        return json.dumps({"error": f"Failed to crop object: {str(e)}"})

@tool
def blur_image(radius: float = 2.0) -> str:
    """Apply Gaussian blur to the entire image. Specify the blur radius (default 2.0 pixels)."""
    image_b64 = _current_image_b64.get()
    
    if not image_b64:
        return json.dumps({"error": "No image available. Please provide an image first."})
    
    try:
        logging.info(f"🔵 blur_image: Calling MCP blur with radius={radius}")
        logging.info(f"   Input image size: {len(image_b64)} chars")
        
        # Call MCP service to blur the full image
        client = MCPClient()
        blurred_b64 = client.blur(image_b64, radius)
        
        logging.info(f"   Output image size: {len(blurred_b64)} chars")
        logging.info(f"   ✅ MCP blur completed successfully")
        
        # Update all image state with the blurred result
        _set_current_image(blurred_b64)
        
        return json.dumps({
            "success": True,
            "message": f"Successfully blurred the entire image with radius {radius}",
            "image_updated": True
        })
    
    except Exception as e:
        logging.error(f"❌ blur_image failed: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Failed to blur image: {str(e)}"})

@tool
def rotate_image(angle: float) -> str:
    """Rotate the entire image. Specify the rotation angle in degrees."""
    image_b64 = _current_image_b64.get()
    
    if not image_b64:
        return json.dumps({"error": "No image available. Please provide an image first."})
    
    try:
        logging.info(f"🔵 rotate_image: Calling MCP rotate with angle={angle}")
        logging.info(f"   Input image size: {len(image_b64)} chars")
        
        # Call MCP service to rotate the full image
        client = MCPClient()
        rotated_b64 = client.rotate(image_b64, angle)
        
        logging.info(f"   Output image size: {len(rotated_b64)} chars")
        logging.info(f"   ✅ MCP rotate completed successfully")
        
        # Update all image state with the rotated result
        _set_current_image(rotated_b64)
        
        return json.dumps({
            "success": True,
            "message": f"Successfully rotated the entire image by {angle} degrees",
            "image_updated": True
        })
    
    except Exception as e:
        logging.error(f"❌ rotate_image failed: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Failed to rotate image: {str(e)}"})

@tool
def flip_image(direction: str) -> str:
    """Flip the entire image horizontally or vertically. Direction must be 'horizontal' or 'vertical'."""
    if direction not in ["horizontal", "vertical"]:
        return json.dumps({"error": f"Invalid direction '{direction}'. Must be 'horizontal' or 'vertical'."})
    
    image_b64 = _current_image_b64.get()
    
    if not image_b64:
        return json.dumps({"error": "No image available. Please provide an image first."})
    
    try:
        logging.info(f"🔵 flip_image: Calling MCP flip with direction={direction}")
        logging.info(f"   Input image size: {len(image_b64)} chars")
        
        # Call MCP service to flip the full image
        client = MCPClient()
        flipped_b64 = client.flip(image_b64, direction)
        
        logging.info(f"   Output image size: {len(flipped_b64)} chars")
        logging.info(f"   ✅ MCP flip completed successfully")
        
        # Update all image state with the flipped result
        _set_current_image(flipped_b64)
        
        return json.dumps({
            "success": True,
            "message": f"Successfully flipped the entire image {direction}",
            "image_updated": True
        })
    
    except Exception as e:
        logging.error(f"❌ flip_image failed: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Failed to flip image: {str(e)}"})

@tool
def resize_image(width: int, height: int) -> str:
    """Resize the entire image to specified dimensions. Width and height must be positive integers."""
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        return json.dumps({"error": "Width and height must be positive integers."})
    
    image_b64 = _current_image_b64.get()
    
    if not image_b64:
        return json.dumps({"error": "No image available. Please provide an image first."})
    
    try:
        logging.info(f"🔵 resize_image: Calling MCP resize with width={width}, height={height}")
        logging.info(f"   Input image size: {len(image_b64)} chars")
        
        # Call MCP service to resize the full image
        client = MCPClient()
        resized_b64 = client.resize(image_b64, width, height)
        
        logging.info(f"   Output image size: {len(resized_b64)} chars")
        logging.info(f"   ✅ MCP resize completed successfully")
        
        # Update all image state with the resized result
        _set_current_image(resized_b64)
        
        return json.dumps({
            "success": True,
            "message": f"Successfully resized the entire image to {width}x{height}",
            "image_updated": True
        })
    
    except Exception as e:
        logging.error(f"❌ resize_image failed: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Failed to resize image: {str(e)}"})

@tool
def add_noise_image(amount: float = 0.1) -> str:
    """Add noise to the entire image. Amount must be between 0.0 and 1.0."""
    if not isinstance(amount, (int, float)) or amount < 0.0 or amount > 1.0:
        return json.dumps({"error": "Amount must be a number between 0.0 and 1.0."})
    
    image_b64 = _current_image_b64.get()
    
    if not image_b64:
        return json.dumps({"error": "No image available. Please provide an image first."})
    
    try:
        logging.info(f"🔵 add_noise_image: Calling MCP add_noise with amount={amount}")
        logging.info(f"   Input image size: {len(image_b64)} chars")
        
        # Call MCP service to add noise to the full image
        client = MCPClient()
        noisy_b64 = client.add_noise(image_b64, amount)
        
        logging.info(f"   Output image size: {len(noisy_b64)} chars")
        logging.info(f"   ✅ MCP add_noise completed successfully")
        
        # Update all image state with the noisy result
        _set_current_image(noisy_b64)
        
        return json.dumps({
            "success": True,
            "message": f"Successfully added noise to the entire image with amount {amount}",
            "image_updated": True
        })
    
    except Exception as e:
        logging.error(f"❌ add_noise_image failed: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Failed to add noise to image: {str(e)}"})

@tool
def add_noise_object(object_id: int, amount: float = 0.1) -> str:
    """Add noise to a detected object in the image. Specify the object ID and noise amount (0.0-1.0)."""
    # Validate amount
    if not isinstance(amount, (int, float)) or amount < 0.0 or amount > 1.0:
        return json.dumps({"error": "Amount must be a number between 0.0 and 1.0."})
    
    # Step 1: Validate and get detection
    result = _validate_and_get_detection(object_id)
    if isinstance(result, str):
        return result  # Error response
    detection, label = result
    bbox = detection["bbox"]
    # Convert bbox coordinates to integers (YOLO returns floats)
    left, top, right, bottom = tuple(int(round(coord)) for coord in bbox)
    
    # Step 2: Get current image
    image_b64 = _current_image_b64.get()
    
    try:
        client = MCPClient()
        
        # Step 3: MCP crop
        logging.info(f"🔍 add_noise_object: Cropping object {object_id} bbox ({left}, {top}, {right}, {bottom})")
        cropped_b64 = client.crop(image_b64, left, top, right, bottom)
        logging.info(f"   ✓ Cropped: {len(cropped_b64)} chars")
        
        # Step 4: MCP add_noise
        logging.info(f"🔍 add_noise_object: Adding noise to cropped region (amount={amount})")
        noisy_b64 = client.add_noise(cropped_b64, amount)
        logging.info(f"   ✓ Noisy: {len(noisy_b64)} chars")
        
        # Step 5: MCP paste_region
        logging.info(f"🔍 add_noise_object: Pasting noisy region back into full image")
        modified_image_b64 = client.paste_region(image_b64, noisy_b64, left, top, right, bottom)
        logging.info(f"   ✓ Composited: {len(modified_image_b64)} chars")
        
        # Step 6: Update and respond
        return _update_image_and_respond(
            modified_image_b64,
            label,
            object_id,
            "added noise to",
            f"with amount {amount}"
        )
    
    except Exception as e:
        logging.error(f"❌ add_noise_object failed: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Failed to add noise to object: {str(e)}"})

# Registry: map tool name -> tool function
TOOLS = {
    detect_objects.name: detect_objects,
    blur_object.name: blur_object,
    crop_object.name: crop_object,
    blur_image.name: blur_image,
    rotate_image.name: rotate_image,
    flip_image.name: flip_image,
    resize_image.name: resize_image,
    add_noise_image.name: add_noise_image,
    add_noise_object.name: add_noise_object,
}

# Parse MODEL string (format: "provider:model_id")
provider, model_id = MODEL.split(":", 1)
rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.2,
    check_every_n_seconds=0.1,
    max_bucket_size=2,
)
if provider == "bedrock":
    
    llm = init_chat_model(
        model_id,
        model_provider="bedrock",
        temperature=0,
        region_name="us-east-1",
        rate_limiter=rate_limiter,
    )
else:
    llm = init_chat_model(MODEL, temperature=0, rate_limiter=rate_limiter)

MODEL_PROFILE = getattr(llm, "profile", None) or {}
REQUIRED_FEATURES = ["tool_calling"]
for feature in REQUIRED_FEATURES:
    if not MODEL_PROFILE.get(feature, False):
        raise SystemExit(
            f"[ERROR] MODEL='{MODEL}' does not support required feature '{feature}'."
        )

MAX_INPUT_TOKENS = MODEL_PROFILE.get("max_input_tokens")

llm_with_tools = llm.bind_tools(list(TOOLS.values()))


class TokensUsed(BaseModel):
    input: int = 0
    output: int = 0
    total: int = 0
    
class ChatMessage(BaseModel):
    role: str                           # "user" or "assistant"
    content: str
    image_base64: Optional[str] = None  # only on user messages that carry an image


class ChatRequest(BaseModel):
    chat_id: Optional[str] = None       # session identifier (None for new conversation)
    messages: list[ChatMessage]         # full conversation thread, oldest first


class ChatResponse(BaseModel):
    chat_id: Optional[str] = None       # session identifier for next request (set by /chat endpoint)
    response: str
    prediction_id: Optional[str] = None
    annotated_image: Optional[str] = None
    agent_loop_time_s: float = 0.0
    iterations: int = 0
    tools_called: list[str] = Field(default_factory=list)
    context_limit_exceeded: bool = False
    tokens_used: TokensUsed = Field(default_factory=TokensUsed)

def message_content_to_text(content) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif "text" in item:
                    text_parts.append(item["text"])
        return "\n".join(part for part in text_parts if part)

    return str(content)

def run_agent(history: list, max_iterations: int = 10) -> ChatResponse:
    """
    Simple ReAct loop with max-iterations guard and structured metadata.
    """
    start_time = time.time()
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + history
    tools_called: list[str] = []
    tokens_used = TokensUsed()

    for iteration in range(1, max_iterations + 1):
        # ===== DEBUG: Log messages before invoke =====
        print(f"\n{'='*80}")
        print(f"ITERATION {iteration}: About to invoke LLM")
        print(f"{'='*80}")
        print(f"Total messages: {len(messages)}")
        
        has_successfully_blurred = False
        for i, msg in enumerate(messages):
            msg_type = type(msg).__name__
            content = msg.content if hasattr(msg, "content") else str(msg)
            if isinstance(content, list):
                content_str = str(content)[:300]
            else:
                content_str = str(content)[:300]
            
            print(f"  [{i}] {msg_type}: {content_str}...")
            
            if msg_type == "AIMessage" and "successfully blurred" in str(msg.content).lower():
                has_successfully_blurred = True
        
        print(f"\nPrevious messages contain 'successfully blurred': {has_successfully_blurred}")
        print(f"{'='*80}\n")
        
        response: AIMessage = llm_with_tools.invoke(messages)
        
        # ===== DEBUG: Log response after invoke =====
        print(f"\n{'='*80}")
        print(f"ITERATION {iteration}: LLM Response")
        print(f"{'='*80}")
        response_content = response.content if hasattr(response, "content") else str(response)
        if isinstance(response_content, list):
            response_content_str = str(response_content)[:300]
        else:
            response_content_str = str(response_content)[:300]
        print(f"Response content (first 300 chars): {response_content_str}...")
        print(f"Response tool_calls: {response.tool_calls}")
        print(f"{'='*80}\n")
        
        usage = getattr(response, "usage_metadata", None) or {}

        tokens_used.input += usage.get("input_tokens", 0)
        tokens_used.output += usage.get("output_tokens", 0)
        tokens_used.total += usage.get("total_tokens", 0)

        if MAX_INPUT_TOKENS and tokens_used.input >= int(MAX_INPUT_TOKENS * 0.9):
            return ChatResponse(
                response="Sorry, the conversation is approaching the model context limit.",
                prediction_id=_detection_result["prediction_id"],
                annotated_image=_detection_result["annotated_image"],
                agent_loop_time_s=round(time.time() - start_time, 3),
                iterations=iteration,
                tools_called=tools_called,
                context_limit_exceeded=True,
                tokens_used=tokens_used,
            )
        messages.append(response)

        if not response.tool_calls:
            return ChatResponse(
                response=message_content_to_text(response.content),
                prediction_id=_detection_result["prediction_id"],
                annotated_image=_detection_result["annotated_image"],
                agent_loop_time_s=round(time.time() - start_time, 3),
                iterations=iteration,
                tools_called=tools_called,
                context_limit_exceeded=False,
                tokens_used=tokens_used,
            )

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tools_called.append(tool_name)

            tool_fn = TOOLS[tool_name]
            tool_result = tool_fn.invoke(tool_call)
            messages.append(tool_result)

    return ChatResponse(
        response="Sorry, I could not complete the request because the agent reached the maximum number of tool calls.",
        prediction_id=_detection_result["prediction_id"],
        annotated_image=_detection_result["annotated_image"],
        agent_loop_time_s=round(time.time() - start_time, 3),
        iterations=max_iterations,
        tools_called=tools_called,
        context_limit_exceeded=True,
        tokens_used=tokens_used,
    )
app = FastAPI(title="Vision Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    lc_messages = []
    latest_image_s3_key = None
    current_image_b64 = None  # Will hold base64 image data
    prediction_id = str(uuid.uuid4())
    new_image_uploaded = False  # Track if a new image was uploaded in this request
    restored_detections = []  # Detections to restore from previous request
    
    # Restore or create chat session
    if request.chat_id and request.chat_id in _chat_image_state:
        # Follow-up request: restore existing session
        chat_id = request.chat_id
        latest_image_s3_key = _chat_image_state[chat_id].get("current_s3_key")
        restored_detections = _chat_image_state[chat_id].get("detections", [])
        logging.info(f"🔄 Restored session {chat_id}: current_s3_key={latest_image_s3_key}, detections={len(restored_detections)}")
    else:
        # New request: generate new chat_id
        chat_id = str(uuid.uuid4())
        latest_image_s3_key = None
        _chat_image_state[chat_id] = {}  # Initialize state for new chat
        logging.info(f"✨ Created new chat session: {chat_id}")

    for msg in request.messages:
        if msg.role == "user":
            if msg.image_base64:
                # New image uploaded - this replaces any previous image
                new_image_uploaded = True
                try:
                    image_bytes = base64.b64decode(msg.image_base64)
                    latest_image_s3_key = upload_image_to_s3(
                        image_bytes=image_bytes,
                        chat_id=chat_id,
                        prediction_id=prediction_id,
                        original_filename="original.jpg"
                    )
                    logging.info(f"Image uploaded to S3: {latest_image_s3_key}")
                    
                    # Store original and current S3 keys in chat state
                    _chat_image_state[chat_id]["original_s3_key"] = latest_image_s3_key
                    _chat_image_state[chat_id]["current_s3_key"] = latest_image_s3_key
                    
                    # Clear detections for new image
                    _chat_image_state[chat_id]["detections"] = []
                    restored_detections = []
                    
                    # Convert uploaded image to base64 for immediate use (no re-download)
                    current_image_b64 = msg.image_base64
                except Exception as e:
                    logging.error(f"Failed to upload image to S3: {e}")
                    return ChatResponse(
                        response=f"Failed to process image: {str(e)}",
                        agent_loop_time_s=0.0,
                        iterations=0,
                        tools_called=[],
                        context_limit_exceeded=False,
                        tokens_used=TokensUsed()
                    )
                
                content = msg.content + "\n[An image was uploaded. Use existing tools to analyze it according to user instructions.]"
            else:
                content = msg.content
            lc_messages.append(HumanMessage(content=content))
        else:
            lc_messages.append(AIMessage(content=msg.content))

    # If no new image was uploaded but we have a current_s3_key, download it for restoration
    if not new_image_uploaded and latest_image_s3_key:
        try:
            logging.info(f"Restoring image from S3: {latest_image_s3_key}")
            image_bytes = download_image_from_s3(latest_image_s3_key)
            current_image_b64 = bytes_to_b64(image_bytes)
            logging.info(f"Image restored from S3 (size: {len(current_image_b64)} chars)")
        except Exception as e:
            logging.error(f"Failed to restore image from S3: {e}")
            # Continue without image rather than failing

    _detection_result["prediction_id"] = None
    _detection_result["annotated_image"] = None
    _detection_result["final_image_b64"] = None  # Phase 5: Store final image after tool modifications

    # Phase 5: Store initial image for change detection
    initial_image_b64 = current_image_b64

    # Set context variables for the agent
    image_token = _current_image_s3_key.set(latest_image_s3_key)
    chat_token = _current_chat_id.set(chat_id)
    pred_token = _current_prediction_id.set(prediction_id)
    image_b64_token = _current_image_b64.set(current_image_b64)  # Set with restored or uploaded image
    detections_token = _current_detections.set(restored_detections)  # Restore previous detections
    logging.info(f"📸 Set context vars: image_s3_key={latest_image_s3_key}, detections={len(restored_detections)}")

    # Phase 6: Sanitize message history to break pattern-matching
    # Replace prior assistant messages that confirm image-operation success with neutral summaries
    sanitized_lc_messages = []
    for msg in lc_messages:
        if isinstance(msg, AIMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            
            # Check if this is a success confirmation message (not the current response)
            is_success_confirmation = any([
                "successfully blurred" in content.lower(),
                "blur operation" in content.lower() and "successful" in content.lower(),
                "successfully cropped" in content.lower(),
                "successfully rotated" in content.lower(),
                "successfully flipped" in content.lower(),
                "successfully resized" in content.lower(),
                "successfully added noise" in content.lower(),
                "operation was successful" in content.lower() and any(op in content.lower() for op in ["blur", "crop", "rotate", "flip", "resize", "noise"]),
            ])
            
            if is_success_confirmation:
                # Replace with neutral summary to avoid pattern-matching
                logging.info(f"🧹 Sanitizing prior success message (first 80 chars): {content[:80]}")
                sanitized_lc_messages.append(AIMessage(
                    content="[Previous assistant response summarized: an image operation result was shown to the user.]"
                ))
            else:
                sanitized_lc_messages.append(msg)
        else:
            sanitized_lc_messages.append(msg)

    try:
        response = run_agent(sanitized_lc_messages)
        response.chat_id = chat_id  # Always return current chat_id
        
        # Hallucination guard with two-tier strategy
        latest_user_msg = ""
        for msg in reversed(request.messages):
            if msg.role == "user":
                latest_user_msg = msg.content.lower()
                break
        
        # Check for modification keywords (strong guard - always require tools)
        modification_keywords = {"blur", "crop", "rotate", "flip", "resize", "noise", "modify", "edit", "transform"}
        user_asked_for_modification = any(keyword in latest_user_msg for keyword in modification_keywords)
        
        # Check for detect keywords (smart guard - only guard if no prior detections)
        user_asked_for_detect = "detect objects" in latest_user_msg or "detect all" in latest_user_msg
        prior_detections = _current_detections.get() or _chat_image_state.get(chat_id, {}).get("detections", [])
        
        # STRONG GUARD: Modification commands must always invoke tools
        if response.tools_called == [] and user_asked_for_modification:
            logging.warning(f"❌ HALLUCINATION GUARD (modification): User requested image modification but no tools invoked. User msg: '{latest_user_msg}'. LLM response: '{response.response}'")
            return ChatResponse(
                chat_id=chat_id,
                response=f"I could not perform the requested image operation. Please try again or rephrase your request.",
                prediction_id=_detection_result["prediction_id"],
                annotated_image=_detection_result["annotated_image"],
                agent_loop_time_s=response.agent_loop_time_s,
                iterations=response.iterations,
                tools_called=[],
                context_limit_exceeded=False,
                tokens_used=response.tokens_used,
            )
        
        # SMART GUARD: Detect only errors if no prior detections and tools not called
        if response.tools_called == [] and user_asked_for_detect and not prior_detections:
            logging.warning(f"❌ HALLUCINATION GUARD (detect): User requested object detection but no tools invoked and no prior detections. User msg: '{latest_user_msg}'. LLM response: '{response.response}'")
            return ChatResponse(
                chat_id=chat_id,
                response=f"I could not detect objects. Please try again or rephrase your request.",
                prediction_id=_detection_result["prediction_id"],
                annotated_image=_detection_result["annotated_image"],
                agent_loop_time_s=response.agent_loop_time_s,
                iterations=response.iterations,
                tools_called=[],
                context_limit_exceeded=False,
                tokens_used=response.tokens_used,
            )
        
        # Persist detections back to chat state after agent completes
        final_detections = _current_detections.get()
        logging.info(f"🔄 Checking detection persistence: current={len(final_detections)} items, was_restored={len(restored_detections)}")
        if final_detections:  # Only update if detections were set (e.g., by detect_objects)
            _chat_image_state[chat_id]["detections"] = final_detections
            logging.info(f"✅ Persisted {len(final_detections)} detections to chat state for {chat_id}")
        else:
            # Ensure detections key exists even if empty
            if "detections" not in _chat_image_state[chat_id]:
                _chat_image_state[chat_id]["detections"] = []
            logging.info(f"✅ Detections state consistent: {len(_chat_image_state[chat_id]['detections'])} items in state")
        
        # Phase 5: Persist final working image if it changed during the request
        # Tools store their final output in _detection_result["final_image_b64"] to bypass ContextVar context isolation
        final_image_b64 = _detection_result.get("final_image_b64") or _current_image_b64.get()
        initial_len = len(initial_image_b64 or '')
        final_len = len(final_image_b64 or '')
        logging.info(f"📊 Phase 5 image comparison: initial={initial_len} chars, final={final_len} chars, equal={initial_image_b64 == final_image_b64}")
        if final_image_b64 and final_image_b64 != initial_image_b64:
            try:
                logging.info(f"🖼️ Image was modified during request: {initial_len} → {final_len} chars")
                image_bytes = base64.b64decode(final_image_b64)
                
                # Generate fresh UUID for modified image upload
                # Not a YOLO prediction_id; upload_image_to_s3 uses this parameter for S3 key construction.
                modified_upload_id = str(uuid.uuid4())
                
                new_s3_key = upload_image_to_s3(
                    image_bytes=image_bytes,
                    chat_id=chat_id,
                    prediction_id=modified_upload_id,
                    original_filename="working.jpg"
                )
                _chat_image_state[chat_id]["current_s3_key"] = new_s3_key
                logging.info(f"✅ Persisted modified image to S3: {new_s3_key}")
            except Exception as e:
                logging.error(f"❌ Failed to persist modified image: {e}", exc_info=True)
                # Continue without S3 persistence - don't fail the whole request
        else:
            logging.info(f"🔵 Image unchanged: no persistence needed (final_image_b64 is None: {final_image_b64 is None})")
        
        return response
    finally:
        _current_image_s3_key.reset(image_token)
        _current_chat_id.reset(chat_token)
        _current_prediction_id.reset(pred_token)
        _current_image_b64.reset(image_b64_token)
        _current_detections.reset(detections_token)

@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
