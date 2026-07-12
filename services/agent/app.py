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
from prometheus_fastapi_instrumentator import Instrumentator
from langchain.chat_models import init_chat_model
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from s3_utils import upload_image_to_s3, download_image_from_s3
from image_utils import bytes_to_b64

YOLO_SERVICE_URL = os.environ.get("YOLO_SERVICE_URL", "http://localhost:8080")
MCP_SERVICE_URL = os.environ.get("MCP_SERVICE_URL", "http://localhost:9000/mcp")
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
    "[CRITICAL CONSTRAINT] YOU CANNOT SEE THE IMAGE DIRECTLY\n"
    "- You have NO access to image pixels or visual content\n"
    "- You can ONLY see what detect_objects() tells you\n"
    "- If you haven't called detect_objects(), you don't know what's in the image\n"
    "- DO NOT guess or assume what's in the image\n"
    "- DO NOT claim success without calling the actual tool (blur, crop, etc.)\n"
    "- If user says 'blur the leftmost person' and you haven't called detect_objects or blur, that's a HALLUCINATION\n\n"
    "[OBJECT DETECTION FORMAT]\n"
    "When detect_objects() returns results, you receive a list of detections with:\n"
    "- object_id: 0-based index (0 is first object)\n"
    "- label: object class name (e.g., 'person', 'dog', 'car')\n"
    "- bbox: [x1, y1, x2, y2] where x1,y1 = top-left, x2,y2 = bottom-right\n"
    "- confidence: confidence score 0.0-1.0\n\n"
    "CRITICAL: FILTER BY LABEL FIRST!\n"
    "When user says 'blur the leftmost person':\n"
    "  1. FILTER: Select ONLY detections with label='person'\n"
    "  2. THEN: Apply position logic (find min x1 among filtered persons)\n"
    "  3. DO NOT take overall leftmost if it's a car!\n\n"
    "POSITION REASONING from filtered bboxes:\n"
    "- LEFTMOST: object with smallest x1 value (among filtered by label)\n"
    "- RIGHTMOST: object with largest x2 value (among filtered by label)\n"
    "- TOPMOST: object with smallest y1 value (among filtered by label)\n"
    "- BOTTOMMOST: object with largest y2 value (among filtered by label)\n"
    "- CENTER X of object: (x1 + x2) / 2\n\n"
    "[CRITICAL] AFTER get_mcp_tools(), YOU MUST IMMEDIATELY USE THE TOOLS:\n"
    "- When you call get_mcp_tools() and receive the tool list, CONTINUE IN THE SAME MESSAGE\n"
    "- DO NOT respond with thinking text and wait for next iteration\n"
    "- DO NOT respond with 'tools are now available' and then stop\n"
    "- IMMEDIATELY after receiving tools, INVOKE THE ACTUAL TOOL the user requested\n\n"
    "[AUTO-INJECT] IMAGE AUTO-INJECTION - Tools automatically get the current image:\n"
    "- When you call blur(), crop(), rotate(), etc., DO NOT specify image_b64\n"
    "- The tool wrapper automatically provides the current image from context\n"
    "- Just call: blur(radius=5.0) - no image_b64 needed!\n\n"
    "[WARNING] ANTI-SPAM RULE - Only call get_mcp_tools() ONCE:\n"
    "- Call get_mcp_tools() ONLY ONCE when you first need image processing tools\n"
    "- After tools are loaded, REUSE them for the rest of the conversation\n\n"
    "TOOL AVAILABILITY:\n"
    "- LOCAL tools (always available): detect_objects, get_mcp_tools\n"
    "- MCP tools (image processing): blur, crop, rotate, flip, resize, add_noise, paste_region\n\n"
    "CRITICAL WORKFLOW - DO THIS CORRECTLY:\n\n"
    "When user sends image + asks 'Blur the leftmost person':\n"
    "  1. Call detect_objects() to see all detected objects\n"
    "  2. SAME RESPONSE - Filter: Keep only objects where label='person'\n"
    "  3. SAME RESPONSE - Find person with smallest x1 (leftmost among persons, not overall!)\n"
    "  4. SAME RESPONSE - Call get_mcp_tools() if you don't have blur yet\n"
    "  5. SAME RESPONSE - Call blur(left=X1, top=Y1, right=X2, bottom=Y2, radius=5.0) with that bbox\n"
    "  6. Report: 'Successfully blurred the leftmost person'\n\n"
    "When user asks 'Blur the second car from right':\n"
    "  1. Call detect_objects()\n"
    "  2. SAME RESPONSE - Filter: Keep only objects where label='car'\n"
    "  3. SAME RESPONSE - Sort cars by x2 descending (rightmost first), pick second one\n"
    "  4. SAME RESPONSE - Call blur(left=X1, top=Y1, right=X2, bottom=Y2, radius=5.0)\n"
    "  5. Report: 'Successfully blurred the second car from right'\n\n"
    "When user says 'rotate image' (on same image, already detected):\n"
    "  1. You already HAVE prior detections from previous request\n"
    "  2. NO NEED to call detect_objects() again\n"
    "  3. SAME RESPONSE - Call rotate(angle=90) with DEFAULT angle\n"
    "  4. Report: 'Successfully rotated the image 90 degrees'\n\n"
    "[WRONG] Do NOT do this:\n"
    "  - Respond with thinking instead of using tools\n"
    "  - Specify image_b64 parameter - tools auto-inject it!\n"
    "  - Forget to call detect_objects() when you need to find objects by position\n"
    "  - Claim success without calling the actual tool (blur, crop, etc.)\n"
    "  - Guess what's in the image without calling detect_objects\n"
    "  - Ask user for parameters when defaults exist (e.g., ask 'what angle?' for rotate)\n"
    "  - Call detect_objects() again when you already have prior detections in same session\n\n"
    "RULES:\n"
    "- After calling get_mcp_tools(), you have all 7 MCP tools available\n"
    "- For full-image operations USE DEFAULT VALUES:\n"
    "  * blur(radius=5.0) - if user just says 'blur image'\n"
    "  * rotate(angle=90) - if user just says 'rotate image' (90 degrees default)\n"
    "  * flip(direction='horizontal') - if user just says 'flip image'\n"
    "  * resize(width=800, height=600) - if user just says 'resize image'\n"
    "- For regions with detections: use bbox from detections as left/top/right/bottom parameters\n"
    "- When you have prior detections, you can use blur/crop/rotate on regions WITHOUT calling detect_objects again\n"
    "- Report clearly: 'Successfully rotated' or 'Failed: reason'\n"
    "- NEVER claim success without actually calling the tool"
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
    """Detect and identify objects in the image provided by the user using YOLO object detection.
    
    Returns detailed detection info including bboxes for reasoning about object positions.
    """
    image_s3_key = _current_image_s3_key.get()
    chat_id = _current_chat_id.get()
    
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
        
        detections = []
        if prediction_id_from_response:
            detections_response = client.get(
                f"{YOLO_SERVICE_URL}/prediction/{prediction_id_from_response}"
            )
            detections_response.raise_for_status()
            detection_data = detections_response.json()
            
            if "detection_objects" in detection_data:
                for idx, obj in enumerate(detection_data["detection_objects"]):
                    try:
                        box_str = obj.get("box", "[]")
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
        if chat_id and chat_id in _chat_image_state:
            _chat_image_state[chat_id]["detections"] = detections
        
        # Format detection summary for LLM reasoning about positions
        detection_summary = f"Detected {len(detections)} objects:\n"
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            center_x = (x1 + x2) / 2
            detection_summary += f"  - object_id {det['id']}: {det['label']} (confidence: {det['confidence']:.2f})\n"
            detection_summary += f"    bbox: left={x1:.1f}, top={y1:.1f}, right={x2:.1f}, bottom={y2:.1f}, center_x={center_x:.1f}\n"
        
        return detection_summary

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
        
        return json.dumps({"success": True, "message": f"Applied {tool_name}"})
    
    # Create a new StructuredTool wrapper with the same schema as the original
    wrapped_tool = StructuredTool(
        name=original_tool.name,
        description=original_tool.description,
        func=invoke_with_image_injection,
        args_schema=original_args_schema  # Preserve original parameter schema
    )
    
    return wrapped_tool

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
    
    # Fallback to persistent state if ContextVar is empty (ContextVar isolation across tool calls)
    if not detections and chat_id and chat_id in _chat_image_state:
        detections = _chat_image_state[chat_id].get("detections", [])
    
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
                "url": MCP_SERVICE_URL,
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
    local_tools = ["detect_objects"]
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
Instrumentator().instrument(app).expose(app)

allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
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
    else:
        # New request: generate new chat_id
        chat_id = str(uuid.uuid4())
        latest_image_s3_key = None
        _chat_image_state[chat_id] = {}  # Initialize state for new chat

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
            logging.warning(f"Could not restore image from S3: {e}")

    _detection_result["prediction_id"] = None
    _detection_result["annotated_image"] = None
    _detection_result["final_image_b64"] = None

    # Store initial image for change detection
    initial_image_b64 = current_image_b64

    # Set context variables for the agent
    image_token = _current_image_s3_key.set(latest_image_s3_key)
    chat_token = _current_chat_id.set(chat_id)
    pred_token = _current_prediction_id.set(prediction_id)
    image_b64_token = _current_image_b64.set(current_image_b64)  # Set with restored or uploaded image
    detections_token = _current_detections.set(restored_detections)

    # Sanitize message history to break pattern-matching
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
        
        response = run_agent(user_only_messages)
        response.chat_id = chat_id  # Always return current chat_id
        
        # Hallucination guard with two-tier strategy
        latest_user_msg = ""
        for msg in reversed(request.messages):
            if msg.role == "user":
                latest_user_msg = msg.content.lower()
                break
        
        # Check for modification keywords (strong guard - always require tools)
        modification_keywords = {"blur", "crop", "rotate", "flip", "resize", "noise", "modify", "edit", "transform", "change", "adjust"}
        user_asked_for_modification = any(keyword in latest_user_msg for keyword in modification_keywords)
        
        # Check for detect keywords (smart guard - only guard if no prior detections)
        detect_keywords = {"detect", "find", "identify", "see", "what's", "whats", "analyze"}
        user_asked_for_detect = any(keyword in latest_user_msg for keyword in detect_keywords)
        prior_detections = _current_detections.get() or _chat_image_state.get(chat_id, {}).get("detections", [])
        
        # STRONG GUARD: Image operations need tools, BUT only if we don't have prior detections
        # If user already detected objects in a prior request, they can do operations without re-detecting
        if response.tools_called == [] and user_asked_for_modification and not prior_detections:
            logging.warning(f"❌ HALLUCINATION GUARD (modification): User requested action but no tools invoked and no prior detections. User msg: '{latest_user_msg}'. LLM response: '{response.response}'")
            return ChatResponse(
                chat_id=chat_id,
                response=f"I need to analyze the image first. Let me detect what's in it, then I can help you.",
                prediction_id=_detection_result["prediction_id"],
                annotated_image=_detection_result["annotated_image"],
                agent_loop_time_s=response.agent_loop_time_s,
                iterations=response.iterations,
                tools_called=[],
                context_limit_exceeded=False,
                tokens_used=response.tokens_used,
            )
        
        # Also guard if new image uploaded (forces detection on fresh image)
        if response.tools_called == [] and new_image_uploaded:
            logging.warning(f"❌ HALLUCINATION GUARD (new_image): User uploaded new image but LLM didn't analyze it. User msg: '{latest_user_msg}'. LLM response: '{response.response}'")
            return ChatResponse(
                chat_id=chat_id,
                response=f"New image uploaded. Let me analyze it first.",
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
            logging.warning(f"❌ HALLUCINATION GUARD (detect): User requested detection but no tools invoked and no prior detections. User msg: '{latest_user_msg}'. LLM response: '{response.response}'")
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
        if final_detections:  # Only update if detections were set (e.g., by detect_objects)
            _chat_image_state[chat_id]["detections"] = final_detections
        else:
            # Ensure detections key exists even if empty
            if "detections" not in _chat_image_state[chat_id]:
                _chat_image_state[chat_id]["detections"] = []
        
        # Persist final working image if it changed during the request
        final_image_b64 = _detection_result.get("final_image_b64") or _current_image_b64.get()
        if final_image_b64 and final_image_b64 != initial_image_b64:
            try:
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
            except Exception as e:
                logging.error(f"Failed to persist modified image to S3: {e}", exc_info=True)
        
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
