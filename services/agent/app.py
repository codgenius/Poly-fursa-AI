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

from s3_utils import upload_image_to_s3
from image_utils import b64_to_bytes, crop_image_region, paste_image_region, bytes_to_b64
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
    "You can detect objects using detect_objects, blur specific objects using blur_object, "
    "and crop specific objects using crop_object. "
    "Use the available tools to extract information from images and perform image processing tasks. "
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
#   }
# }

@tool
def detect_objects() -> str:
    """Detect and identify objects in the image provided by the user using YOLO object detection."""
    image_s3_key = _current_image_s3_key.get()
    chat_id = _current_chat_id.get()
    prediction_id = _current_prediction_id.get()
    
    if not image_s3_key:
        return json.dumps({"error": "No image was provided by the user."})

    with httpx.Client(timeout=30.0) as client:
        payload = {
            "image_s3_key": image_s3_key,
            "chat_id": chat_id,
            "prediction_id": prediction_id,
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
            
            # Store annotated image in context for blur_object/crop_object to use
            _current_image_b64.set(annotated_image_b64)
        
        # Parse detections from YOLO response and store in context
        detections = []
        if "detections" in prediction_data:
            for idx, detection in enumerate(prediction_data["detections"]):
                detections.append({
                    "id": idx,
                    "label": detection.get("label", "unknown"),
                    "bbox": (
                        detection.get("x1", 0),
                        detection.get("y1", 0),
                        detection.get("x2", 0),
                        detection.get("y2", 0),
                    ),
                    "confidence": detection.get("confidence", 0.0),
                })
        _current_detections.set(detections)

    return json.dumps(prediction_data)

def _validate_and_get_detection(object_id: int):
    """Validate context and get detection object.
    
    Returns:
        tuple: (detection_dict, label_str) on success
        str: JSON error response on failure
    """
    image_b64 = _current_image_b64.get()
    detections = _current_detections.get()
    
    if not image_b64:
        return json.dumps({"error": "No image available. Please detect objects first."})
    
    if not detections:
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
    _current_image_b64.set(modified_image_b64)
    _detection_result["annotated_image"] = modified_image_b64
    
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
    # Validate and get detection
    result = _validate_and_get_detection(object_id)
    if isinstance(result, str):
        return result  # Error response
    detection, label = result
    bbox = detection["bbox"]
    
    image_b64 = _current_image_b64.get()
    
    try:
        # DEBUG: Step 1 - Convert image from base64 to bytes
        logging.info(f"🔍 blur_object: Step 1 - Converting image b64 to bytes (b64 len: {len(image_b64)})")
        full_image_bytes = b64_to_bytes(image_b64)
        logging.info(f"   ✓ Image bytes: {len(full_image_bytes)} bytes")
        
        # DEBUG: Step 2 - Crop the region
        logging.info(f"🔍 blur_object: Step 2 - Cropping bbox {bbox}")
        cropped_bytes = crop_image_region(full_image_bytes, bbox)
        logging.info(f"   ✓ Cropped bytes: {len(cropped_bytes)} bytes")
        
        # DEBUG: Step 3 - Convert cropped region to base64
        logging.info(f"🔍 blur_object: Step 3 - Converting cropped to b64")
        cropped_b64 = bytes_to_b64(cropped_bytes)
        logging.info(f"   ✓ Cropped b64: {len(cropped_b64)} chars")
        
        # DEBUG: Step 4 - Call MCP blur
        logging.info(f"🔍 blur_object: Step 4 - Calling MCP blur (radius={radius})")
        client = MCPClient()
        blurred_b64 = client.blur(cropped_b64, radius)
        logging.info(f"   ✓ Blurred b64: {len(blurred_b64)} chars")
        
        # DEBUG: Step 5 - Convert blurred result back to bytes
        logging.info(f"🔍 blur_object: Step 5 - Converting blurred b64 to bytes")
        blurred_bytes = b64_to_bytes(blurred_b64)
        logging.info(f"   ✓ Blurred bytes: {len(blurred_bytes)} bytes")
        
        # DEBUG: Step 6 - Paste back into full image
        logging.info(f"🔍 blur_object: Step 6 - Pasting blurred region back into full image")
        modified_image_bytes = paste_image_region(full_image_bytes, blurred_bytes, bbox)
        logging.info(f"   ✓ Modified image bytes: {len(modified_image_bytes)} bytes")
        
        # DEBUG: Step 7 - Convert result back to base64
        logging.info(f"🔍 blur_object: Step 7 - Converting result to b64")
        modified_image_b64 = bytes_to_b64(modified_image_bytes)
        logging.info(f"   ✓ Modified b64: {len(modified_image_b64)} chars")
        
        # Update and respond
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
    
    image_b64 = _current_image_b64.get()
    
    # Apply offsets to bbox: (x1, y1, x2, y2)
    x1, y1, x2, y2 = bbox
    left = x1 - left_offset
    top = y1 - top_offset
    right = x2 + right_offset
    bottom = y2 + bottom_offset
    
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

# Registry: map tool name -> tool function
TOOLS = {
    detect_objects.name: detect_objects,
    blur_object.name: blur_object,
    crop_object.name: crop_object,
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
        response: AIMessage = llm_with_tools.invoke(messages)
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
    prediction_id = str(uuid.uuid4())
    
    # Restore or create chat session
    if request.chat_id and request.chat_id in _chat_image_state:
        # Follow-up request: restore existing session
        chat_id = request.chat_id
        latest_image_s3_key = _chat_image_state[chat_id].get("current_s3_key")
    else:
        # New request: generate new chat_id
        chat_id = str(uuid.uuid4())
        latest_image_s3_key = None
        _chat_image_state[chat_id] = {}  # Initialize state for new chat

    for msg in request.messages:
        if msg.role == "user":
            if msg.image_base64:
                # Upload original image to S3
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

    _detection_result["prediction_id"] = None
    _detection_result["annotated_image"] = None

    # Set context variables for the agent
    image_token = _current_image_s3_key.set(latest_image_s3_key)
    chat_token = _current_chat_id.set(chat_id)
    pred_token = _current_prediction_id.set(prediction_id)
    image_b64_token = _current_image_b64.set(None)  # Will be set by detect_objects
    detections_token = _current_detections.set([])  # Will be populated by detect_objects

    try:
        response = run_agent(lc_messages)
        response.chat_id = chat_id  # Always return current chat_id
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
