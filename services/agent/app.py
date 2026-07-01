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
    "Use the available tools to extract information from images. "
)

# Context variables for tracking image metadata during agent execution
_current_image_s3_key: ContextVar[Optional[str]] = ContextVar("current_image_s3_key", default=None)
_current_chat_id: ContextVar[Optional[str]] = ContextVar("current_chat_id", default=None)
_current_prediction_id: ContextVar[Optional[str]] = ContextVar("current_prediction_id", default=None)
_detection_result = {
    "prediction_id": None,
    "annotated_image": None,
}

@tool
def detect_objects() -> str:
    """Detect and identify objects in the image provided by the user using YOLO object detection."""
    image_s3_key = _current_image_s3_key.get()
    chat_id = _current_chat_id.get()
    prediction_id = _current_prediction_id.get()
    
    if not image_s3_key:
        return json.dumps({"error": "No image was provided by the user."})

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{YOLO_SERVICE_URL}/predict",
            json={
                "image_s3_key": image_s3_key,
                "chat_id": chat_id,
                "prediction_id": prediction_id,
            }
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

    return json.dumps(prediction_data)

# Registry: map tool name -> tool function
TOOLS = {
    detect_objects.name: detect_objects
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
    messages: list[ChatMessage]         # full conversation thread, oldest first


class ChatResponse(BaseModel):
    response: str
    prediction_id: Optional[str] = None
    annotated_image: Optional[str] = None
    agent_loop_time_s: float = 0.0
    iterations: int = 0
    tools_called: list[str] = Field(default_factory=list)
    context_limit_exceeded: bool = False
    tokens_used: TokensUsed = Field(default_factory=TokensUsed)

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
                response=response.content,
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
    chat_id = str(uuid.uuid4())
    prediction_id = str(uuid.uuid4())

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

    try:
        return run_agent(lc_messages)
    finally:
        _current_image_s3_key.reset(image_token)
        _current_chat_id.reset(chat_token)
        _current_prediction_id.reset(pred_token)

@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
