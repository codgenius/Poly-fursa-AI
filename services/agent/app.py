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
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from s3_utils import upload_image_to_s3, download_image_from_s3
from image_utils import bytes_to_b64

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
    "You are an AI vision assistant helping users understand and modify images.\n\n"
    "[CRITICAL] AFTER get_mcp_tools(), YOU MUST IMMEDIATELY USE THE TOOLS:\n"
    "- When you call get_mcp_tools() and receive the tool list, CONTINUE IN THE SAME MESSAGE\n"
    "- DO NOT respond with thinking text and wait for next iteration\n"
    "- DO NOT respond with 'tools are now available' and then stop\n"
    "- IMMEDIATELY after receiving tools, INVOKE THE ACTUAL TOOL the user requested\n"
    "- Example: User says 'blur' → Call get_mcp_tools() → THEN call blur() in same response\n\n"
    "[AUTO-INJECT] IMAGE AUTO-INJECTION - Tools automatically get the current image:\n"
    "- When you call blur(), crop(), rotate(), etc., DO NOT specify image_b64\n"
    "- The tool wrapper automatically provides the current image from context\n"
    "- Just call: blur(radius=5.0) - no image_b64 needed!\n"
    "- The tool tracks the image across all calls automatically\n\n"
    "[WARNING] ANTI-SPAM RULE - Only call get_mcp_tools() ONCE:\n"
    "- Call get_mcp_tools() ONLY ONCE when you first need image processing tools\n"
    "- After tools are loaded, REUSE them for the rest of the conversation\n"
    "- Never call get_mcp_tools() multiple times - you already have the tools!\n"
    "- Exception: Only call again if a tool invoke actually FAILS with 'tool not found' error\n\n"
    "TOOL AVAILABILITY:\n"
    "- LOCAL tools (always available): detect_objects, resolve_object_reference, get_mcp_tools\n"
    "- MCP tools (image processing): blur, crop, rotate, flip, resize, add_noise, paste_region\n"
    "- MCP tools are loaded on-demand by calling get_mcp_tools() ONCE\n\n"
    "CRITICAL WORKFLOW - DO THIS CORRECTLY:\n\n"
    "When user asks 'Blur the image':\n"
    "  1. Check if you have blur tool\n"
    "  2. If NOT: Call get_mcp_tools() to load all tools\n"
    "  3. SAME RESPONSE - Call blur(radius=5.0) [image auto-injected!]\n"
    "  4. Report: 'Successfully blurred the image'\n\n"
    "When user asks 'Blur the first person':\n"
    "  1. Check if you have blur tool\n"
    "  2. If NOT: Call get_mcp_tools() to load tools\n"
    "  3. SAME RESPONSE - Call detect_objects()\n"
    "  4. SAME RESPONSE - Call resolve_object_reference('first person')\n"
    "  5. SAME RESPONSE - Call blur(left=X, top=Y, right=X2, bottom=Y2, radius=5.0)\n"
    "  6. Report: 'Successfully blurred the first person'\n\n"
    "[WRONG] Do NOT do this:\n"
    "  - Call get_mcp_tools() then respond 'tools loaded' without using them\n"
    "  - Call get_mcp_tools() multiple times in conversation\n"
    "  - Respond with thinking instead of calling actual tool\n"
    "  - Specify image_b64 parameter - tools auto-inject it!\n\n"
    "RULES:\n"
    "- After calling get_mcp_tools(), you have all 7 MCP tools available\n"
    "- For full-image: blur(radius=5.0), rotate(angle=90), flip(direction='horizontal')\n"
    "- For regions: blur(left=X, top=Y, right=X2, bottom=Y2, radius=5.0)\n"
    "- Report clearly: 'Successfully blurred' or 'Failed: reason'"
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
        
        response = client.post(
            f"{YOLO_SERVICE_URL}/predict",
            json=payload
        )
        
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

    return json.dumps(prediction_data)

def _create_mcp_tool_wrapper(mcp_tool):
    """Wrap an MCP tool to auto-inject image from context.
    
    The MCP tool from langchain-mcp-adapters already has a StructuredTool with proper
    parameter schema. We create a new wrapper tool that injects the image from context
    before calling the original tool.
    
    Args:
        mcp_tool: A StructuredTool from langchain-mcp-adapters
        
    Returns:
        A new StructuredTool that wraps the original with auto-injected image
    """
    import asyncio
    from langchain_core.tools import StructuredTool
    
    original_tool = mcp_tool
    tool_name = mcp_tool.name
    original_args_schema = getattr(mcp_tool, 'args_schema', None)
    
    def invoke_with_image_injection(tool_input=None, **kwargs):
        """Sync invoke that injects image before calling original.
        
        Accepts either tool_input dict or individual kwargs (or both merged).
        LangChain can pass parameters either way depending on how the tool is invoked.
        """
        # Merge tool_input dict and kwargs
        if tool_input is None:
            tool_input = kwargs
        elif isinstance(tool_input, dict):
            tool_input = {**tool_input, **kwargs}
        else:
            tool_input = kwargs
        
        image_b64 = _current_image_b64.get()
        if not image_b64:
            return json.dumps({"error": f"{tool_name} requires image in context"})
        
        # Inject image into the tool input
        if isinstance(tool_input, dict):
            tool_input['image_b64'] = image_b64
        
        logging.info(f"🔧 Calling {tool_name} with auto-injected image")
        
        # Call the original tool's invoke
        try:
            result = original_tool.invoke(tool_input)
        except (NotImplementedError, RuntimeError) as e:
            # If sync fails, try async
            if hasattr(original_tool, 'ainvoke') and "does not support sync" in str(e):
                async def run_async():
                    return await original_tool.ainvoke(tool_input)
                
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    try:
                        result = loop.run_until_complete(run_async())
                    finally:
                        loop.close()
            else:
                raise
        
        # Extract image from result
        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict):
            result_b64 = result[0].get('text', str(result))
        else:
            result_b64 = str(result)
        
        # Update context with result image
        _set_current_image(result_b64)
        logging.info(f"✅ {tool_name} completed, image updated")
        
        return json.dumps({"success": True, "message": f"Applied {tool_name}"})
    
    # Create a new StructuredTool wrapper with the same schema as the original
    wrapped_tool = StructuredTool(
        name=original_tool.name,
        description=original_tool.description,
        func=invoke_with_image_injection,
        args_schema=original_args_schema  # Preserve original parameter schema
    )
    
    return wrapped_tool

@tool
def resolve_object_reference(reference: str) -> str:
    """Resolve natural-language object references to a specific object_id.
    
    Examples:
    - "object 0" → first object
    - "the dog" / "detected car" → object with that label (error if ambiguous)
    - "first person from left" / "first person from the left" → leftmost person
    - "second dog from right" / "second dog from the right" → second from rightmost
    - "leftmost person" / "left person" / "person on the left" → person with smallest bbox.left
    - "rightmost car" / "right car" / "car on the right" → car with largest bbox.right
    - "middle cat" → cat at median horizontal position
    - "second person" → second person from left (default direction)
    
    Robust to full action phrases (e.g., 'blur the second person from right' will work).
    
    Returns JSON with object_id, label, confidence, bbox on success.
    Returns JSON error if no match or ambiguous.
    """
    # Preprocess: strip action verbs if user accidentally passed full sentence
    cleaned_reference = _preprocess_reference(reference)
    result = _parse_object_reference(cleaned_reference)
    return json.dumps(result)

def _preprocess_reference(reference: str) -> str:
    """Strip action verbs from reference if user passed full sentence.
    
    Examples:
      - "blur the second person from the right" → "second person from the right"
      - "add noise to the dog" → "the dog"
      - "can you crop the leftmost car" → "the leftmost car"
      - "second person from right" → "second person from right" (no change)
    """
    import re
    ref = reference.strip()
    
    # Strip common action phrases at the start (case-insensitive)
    # Pattern: optional "can you" or "please", then action verb(s)
    action_pattern = r"^(?:can you\s+|could you\s+|please\s+)?(blur|crop|add noise to|add salt and pepper noise to|add noise|rotate|flip|resize)\s+(?:the\s+)?"
    ref = re.sub(action_pattern, "", ref, flags=re.IGNORECASE, count=1)
    
    return ref.strip()

def _set_current_image(image_b64: str):
    """Update all image state tracking with a modified image.
    
    Ensures consistency across ContextVars and _detection_result dict,
    which is necessary to persist changes across tool context boundaries (Phase 5).
    """
    _current_image_b64.set(image_b64)
    _detection_result["annotated_image"] = image_b64
    _detection_result["final_image_b64"] = image_b64

def _parse_object_reference(reference: str) -> dict:
    """Parse natural-language object reference and resolve to object info.
    
    Supports patterns:
      - "object 0" → first object
      - "the dog" / "detected dog" → exact label match (error if ambiguous)
      - "first/second/third dog from left" → position from left
      - "first/second/third dog from right" → position from right
      - "leftmost/rightmost dog" → extreme positions
      - "middle dog" → median position
    
    Returns dict with success info or error.
    """
    import re
    
    detections = _current_detections.get()
    chat_id = _current_chat_id.get()
    
    # Fallback to persistent state if empty (ContextVar isolation across tool calls)
    if not detections and chat_id and chat_id in _chat_image_state:
        detections = _chat_image_state[chat_id].get("detections", [])
    
    if not detections:
        return {"success": False, "reference": reference, "error": "No detections available. Please detect objects first."}
    
    ref = reference.strip().lower()
    
    # Pattern 1: "object N" or "objectN"
    match = re.match(r"^object\s*(\d+)$", ref)
    if match:
        obj_id = int(match.group(1))
        if 0 <= obj_id < len(detections):
            det = detections[obj_id]
            return {
                "success": True,
                "reference": reference,
                "object_id": obj_id,
                "label": det["label"],
                "confidence": det["confidence"],
                "bbox": det["bbox"]
            }
        return {
            "success": False,
            "reference": reference,
            "error": f"object_id {obj_id} out of range [0-{len(detections)-1}]"
        }
    
    # Plural handling: map plural forms to singular
    plural_to_singular = {
        "people": "person",
        "persons": "person",
        "dogs": "dog",
        "cats": "cat",
        "cars": "car",
        "items": "item",
        "objects": "object",
    }
    for plural, singular in plural_to_singular.items():
        ref = ref.replace(plural, singular)
    
    # Pattern 2: "the LABEL" / "detected LABEL"
    match = re.match(r"^(?:the|detected)\s+(\w+)$", ref)
    if match:
        label = match.group(1)
        matching = [i for i, d in enumerate(detections) if d["label"].lower() == label]
        if len(matching) == 1:
            obj_id = matching[0]
            det = detections[obj_id]
            return {
                "success": True,
                "reference": reference,
                "object_id": obj_id,
                "label": det["label"],
                "confidence": det["confidence"],
                "bbox": det["bbox"]
            }
        if len(matching) == 0:
            return {
                "success": False,
                "reference": reference,
                "error": f"No '{label}' detected in image."
            }
        # Ambiguous: multiple matches
        return {
            "success": False,
            "reference": reference,
            "error": f"Found {len(matching)} '{label}' objects; be more specific. Try 'first {label} from left', 'second {label} from right', 'leftmost {label}', or 'middle {label}'."
        }
    
    # Pattern 3: "first/second/third LABEL from left/right" or "first/second/third LABEL" (defaults to left)
    # Try with explicit direction first (with optional "the" after "from")
    match = re.match(r"^(first|second|third|\d+(?:st|nd|rd|th)?)\s+(\w+)\s+from\s+(?:the\s+)?(left|right)$", ref)
    if match:
        pos_word = match.group(1)
        label = match.group(2)
        direction = match.group(3)
    else:
        # Try without direction (defaults to left-to-right)
        match = re.match(r"^(first|second|third|\d+(?:st|nd|rd|th)?)\s+(\w+)$", ref)
        if match:
            pos_word = match.group(1)
            label = match.group(2)
            direction = "left"
        else:
            match = None
    
    if match:
        # Map word to index
        pos_map = {"first": 0, "second": 1, "third": 2}
        if pos_word in pos_map:
            position = pos_map[pos_word]
        else:
            # Try parsing as number with ordinal suffix (e.g., "1st", "2nd")
            try:
                num_str = re.sub(r"(?:st|nd|rd|th)$", "", pos_word)
                position = int(num_str) - 1
            except (ValueError, IndexError):
                return {
                    "success": False,
                    "reference": reference,
                    "error": f"Could not parse position: '{pos_word}'"
                }
        
        # Find all detections matching the label
        matching = [i for i, d in enumerate(detections) if d["label"].lower() == label]
        if not matching:
            return {
                "success": False,
                "reference": reference,
                "error": f"No '{label}' detected in image."
            }
        
        # Sort by bbox center (horizontal position)
        if direction == "left":
            matching.sort(key=lambda i: (detections[i]["bbox"][0] + detections[i]["bbox"][2]) / 2)
        else:  # right
            matching.sort(key=lambda i: (detections[i]["bbox"][0] + detections[i]["bbox"][2]) / 2, reverse=True)
        
        if position >= len(matching):
            return {
                "success": False,
                "reference": reference,
                "error": f"Only {len(matching)} '{label}' object(s) found from {direction}; requested position {position+1}."
            }
        
        obj_id = matching[position]
        det = detections[obj_id]
        return {
            "success": True,
            "reference": reference,
            "object_id": obj_id,
            "label": det["label"],
            "confidence": det["confidence"],
            "bbox": det["bbox"]
        }
    
    # Pattern 4: "leftmost/rightmost LABEL" or "left/right LABEL" or "LABEL on the left/right"
    # Try "leftmost/rightmost LABEL"
    match = re.match(r"^(leftmost|rightmost)\s+(\w+)$", ref)
    if match:
        direction = match.group(1)
        label = match.group(2)
        matching = [i for i, d in enumerate(detections) if d["label"].lower() == label]
        if not matching:
            return {
                "success": False,
                "reference": reference,
                "error": f"No '{label}' detected in image."
            }
        
        if direction == "leftmost":
            obj_id = min(matching, key=lambda i: detections[i]["bbox"][0])
        else:  # rightmost
            obj_id = max(matching, key=lambda i: detections[i]["bbox"][2])
        
        det = detections[obj_id]
        return {
            "success": True,
            "reference": reference,
            "object_id": obj_id,
            "label": det["label"],
            "confidence": det["confidence"],
            "bbox": det["bbox"]
        }
    
    # Try "left/right LABEL" (maps to leftmost/rightmost)
    match = re.match(r"^(left|right)\s+(\w+)$", ref)
    if match:
        direction = match.group(1)
        label = match.group(2)
        matching = [i for i, d in enumerate(detections) if d["label"].lower() == label]
        if not matching:
            return {
                "success": False,
                "reference": reference,
                "error": f"No '{label}' detected in image."
            }
        
        if direction == "left":
            obj_id = min(matching, key=lambda i: detections[i]["bbox"][0])
        else:  # right
            obj_id = max(matching, key=lambda i: detections[i]["bbox"][2])
        
        det = detections[obj_id]
        return {
            "success": True,
            "reference": reference,
            "object_id": obj_id,
            "label": det["label"],
            "confidence": det["confidence"],
            "bbox": det["bbox"]
        }
    
    # Try "LABEL on the left/right"
    match = re.match(r"^(\w+)\s+on\s+the\s+(left|right)$", ref)
    if match:
        label = match.group(1)
        direction = match.group(2)
        matching = [i for i, d in enumerate(detections) if d["label"].lower() == label]
        if not matching:
            return {
                "success": False,
                "reference": reference,
                "error": f"No '{label}' detected in image."
            }
        
        if direction == "left":
            obj_id = min(matching, key=lambda i: detections[i]["bbox"][0])
        else:  # right
            obj_id = max(matching, key=lambda i: detections[i]["bbox"][2])
        
        det = detections[obj_id]
        return {
            "success": True,
            "reference": reference,
            "object_id": obj_id,
            "label": det["label"],
            "confidence": det["confidence"],
            "bbox": det["bbox"]
        }
    
    # Pattern 5: "middle LABEL"
    match = re.match(r"^middle\s+(\w+)$", ref)
    if match:
        label = match.group(1)
        matching = [i for i, d in enumerate(detections) if d["label"].lower() == label]
        if not matching:
            return {
                "success": False,
                "reference": reference,
                "error": f"No '{label}' detected in image."
            }
        
        # Sort by bbox center and take median
        matching.sort(key=lambda i: (detections[i]["bbox"][0] + detections[i]["bbox"][2]) / 2)
        obj_id = matching[len(matching) // 2]
        det = detections[obj_id]
        return {
            "success": True,
            "reference": reference,
            "object_id": obj_id,
            "label": det["label"],
            "confidence": det["confidence"],
            "bbox": det["bbox"]
        }
    
    return {
        "success": False,
        "reference": reference,
        "error": f"Could not parse reference: '{reference}'. Try 'object 0', 'the dog', 'first person from left', 'leftmost car', 'left person', 'person on the left', or 'middle person'."
    }

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
def get_mcp_tools(refresh: bool = True) -> str:
    """Refresh available tools by connecting to the MCP server and updating the toolbox.
    
    Args:
        refresh: Whether to refresh the tool list (always True). Included for tool schema compatibility.
    
    This tool dynamically initializes/refreshes the connection to the MCP server and loads
    all available image processing tools. Call this when:
    - You need to discover what tools are available
    - A tool invoke failed and you want to retry with fresh tools
    - You're unsure if a tool exists in your toolbox
    
    Returns updated list of all tools (MCP + local) with their descriptions.
    """
    import asyncio
    from langchain_mcp_adapters.client import MultiServerMCPClient
    global mcp_tools, llm_with_tools
    
    tools_info = []
    
    try:
        # Initialize/refresh MCP client connection
        mcp_config = {
            "img-proc": {
                "url": "http://localhost:9000/mcp",
                "transport": "http"
            }
        }
        mcp_client_temp = MultiServerMCPClient(mcp_config)
        fresh_mcp_tools = asyncio.run(mcp_client_temp.get_tools())
        
        # Update global TOOLS registry with WRAPPED MCP tools
        global mcp_tools, llm_with_tools
        mcp_tools = fresh_mcp_tools
        
        for raw_mcp_tool in fresh_mcp_tools:
            # Wrap the raw MCP tool to auto-inject image from context
            wrapped_tool = _create_mcp_tool_wrapper(raw_mcp_tool)
            TOOLS[raw_mcp_tool.name] = wrapped_tool
            
            tool_info = {
                "name": raw_mcp_tool.name,
                "description": raw_mcp_tool.description,
                "source": "mcp"
            }
            tools_info.append(tool_info)
        
        # RE-BIND tools to LLM so new MCP tools are available for calling
        # CRITICAL: Only bind tools that have been properly decorated or wrapped
        # Don't try to bind raw MCP StructuredTools - they cause Bedrock schema errors
        llm_with_tools = llm.bind_tools([tool for tool in TOOLS.values() if hasattr(tool, 'invoke')])
        
    except Exception as e:
        logging.error(f"❌ Failed to fetch MCP tools: {e}", exc_info=True)
    
    # Always include local tools in response
    local_tools = ["detect_objects", "resolve_object_reference"]
    for tool_name in local_tools:
        if tool_name in TOOLS:
            tool_obj = TOOLS[tool_name]
            if hasattr(tool_obj, 'description'):
                tool_info = {
                    "name": tool_name,
                    "description": tool_obj.description,
                    "source": "local"
                }
                tools_info.append(tool_info)
    
    return json.dumps({
        "tools": tools_info,
        "count": len(tools_info),
        "message": f"Updated toolbox: {len(tools_info)} tools available (MCP connection refreshed, tools auto-inject image)"
    }, indent=2)


# Global variable to hold loaded MCP tools
mcp_tools = []

# Registry: map tool name -> tool function
# Start with LOCAL tools only - MCP tools loaded on-demand via get_mcp_tools()
TOOLS = {
    detect_objects.name: detect_objects,
    resolve_object_reference.name: resolve_object_reference,
    get_mcp_tools.name: get_mcp_tools,
}

logging.info(f"✅ TOOLS registry initialized with {len(TOOLS)} LOCAL tools: {list(TOOLS.keys())}")

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

llm_with_tools = llm.bind_tools([tool for tool in TOOLS.values() if hasattr(tool, 'invoke')])


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
    Handles both sync (local) and async (MCP) tools.
    """
    import asyncio
    global llm_with_tools
    
    start_time = time.time()
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + history
    tools_called: list[str] = []
    tokens_used = TokensUsed()
    
    # PRELOAD MCP TOOLS at the start so they're available for all iterations
    try:
        get_mcp_tools.invoke({"refresh": True})
    except Exception as e:
        logging.warning(f"⚠️  Failed to preload MCP tools: {e}. Continuing with local tools only.")

    for iteration in range(1, max_iterations + 1):
        # Debug: Show message structure before invoke
        msg_structure: list[tuple[str, int]] = [(type(msg).__name__, len(str(msg.content)) if hasattr(msg, "content") else 0) for msg in messages]
        available_tools: list[str] = list(TOOLS.keys())
        print(f"\n[ITERATION {iteration}] Invoking LLM with {len(messages)} messages: {msg_structure}")
        print(f"[ITERATION {iteration}] Available tools: {available_tools}\n")
        
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
            tool_call_id = tool_call["id"]
            tools_called.append(tool_name)

            tool_fn = TOOLS[tool_name]
            
            # Handle async tools (MCP tools) vs sync tools (local tools)
            # Check if this is an async StructuredTool by trying to invoke
            try:
                # Try sync invoke first (works for local @tool functions)
                # IMPORTANT: Pass only the args, not the full tool_call
                tool_result = tool_fn.invoke(tool_call["args"])
            except (NotImplementedError, RuntimeError) as e:
                # If sync fails, this is an async tool - use asyncio to run it
                if "does not support sync invocation" in str(e) or "no running event loop" in str(e):
                    logging.info(f"🔄 Tool '{tool_name}' is async, converting to sync with asyncio")
                    
                    # For async tools, we need to use their ainvoke method
                    async def invoke_async_tool():
                        return await tool_fn.ainvoke(tool_call["args"])
                    
                    try:
                        loop = asyncio.get_running_loop()
                        # Already in async context - shouldn't happen in sync run_agent
                        raise RuntimeError("Cannot invoke async tools from running event loop")
                    except RuntimeError as loop_err:
                        if "no running event loop" in str(loop_err):
                            # Create new event loop for async tool
                            loop = asyncio.new_event_loop()
                            try:
                                tool_result = loop.run_until_complete(invoke_async_tool())
                            finally:
                                loop.close()
                        else:
                            raise
                else:
                    raise
            
            # Wrap tool result in proper ToolMessage with tool_call_id
            tool_message = ToolMessage(content=str(tool_result), tool_call_id=tool_call_id)
            messages.append(tool_message)

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
            image_bytes = download_image_from_s3(latest_image_s3_key)
            current_image_b64 = bytes_to_b64(image_bytes)
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
        # Only pass the LATEST user message to run_agent
        # This prevents broken tool-calling sequences from multiple consecutive HumanMessages
        # Agent state (detections, image) is preserved through context variables (_current_detections, _current_image_b64)
        user_only_messages = [msg for msg in sanitized_lc_messages if isinstance(msg, HumanMessage)]
        if user_only_messages:
            # Keep only the latest user message (the current input)
            user_only_messages = [user_only_messages[-1]]
            if new_image_uploaded:
                logging.info(f"🖼️  New image uploaded: passing only latest message to agent (conversation cleared)")
        
        response = run_agent(user_only_messages)
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
