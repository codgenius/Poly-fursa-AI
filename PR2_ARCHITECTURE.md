# PR2 Architecture Document

This document defines the complete architecture for PR2 (persistent multi-turn image conversations). It is the single source of truth for all PR2 work.

**IMPORTANT RULE:** Every future implementation must follow this document exactly. If implementation needs to differ from this architecture, update this document first and explain why. Do not silently diverge.

**Do not code until this document is finalized.**

---

## 1. Overall Architecture

### Component Responsibilities

#### Frontend (chat.tsx, api.ts)
**Owns:**
- User interface
- Message history (displayed to user)
- Current chat_id (received from Agent)
- User input collection

**Responsibilities:**
- Collect user text and image uploads
- Display messages and images
- Send to Agent
- Render responses

**Must Never:**
- Process images
- Know about S3, YOLO, or MCP
- Perform image manipulation
- Understand object detection
- Make decisions about tools

#### Agent (services/agent/app.py)
**Owns:**
- Conversation orchestration
- Image state (S3 keys, detections)
- Request-scoped image data
- Tool routing decisions

**Responsibilities:**
- Receive user requests
- Understand natural language
- Decide which tool to call
- Maintain chat_id state across requests
- Download/upload images from S3
- Call YOLO and MCP services
- Cache detection results
- Return responses to frontend

**Must Never:**
- Perform image processing itself
- Know image format details beyond base64
- Cache full images in memory (only S3 keys)
- Make decisions for the user

#### YOLO (services/yolo/app.py)
**Owns:**
- Detection algorithm
- Detection results
- Annotated image generation

**Responsibilities:**
- Receive image bytes
- Run object detection
- Return detections + confidence
- Generate annotated image

**Must Never:**
- Modify user's original image beyond annotation
- Know about chat_id or conversations
- Know about S3 or image history
- Persist state

#### MCP (services/img-proc-mcp/app.py)
**Owns:**
- Pure image transformation functions
- Image processing logic
- Tool implementations (blur, rotate, crop, resize, etc.)

**Responsibilities:**
- Receive base64 image + parameters
- Perform transformation
- Return modified base64 image

**Must Never:**
- Know about chat_id
- Know about S3
- Know about conversation context
- Know about object detection
- Know about tool history
- Persist state

**Critical Constraint:** MCP is stateless and context-blind. It receives opaque base64 images and returns modified base64. It does NOT know whether the image is:
- Full image or crop
- Original or current version
- From S3 or memory
- What chat_id it belongs to
- Whether it came from YOLO annotation

Agent is entirely responsible for framing, cropping, pasting, and context management.

#### S3 Storage
**Owns:**
- Persistent image storage
- Source of truth between requests

**Responsibilities:**
- Store original image
- Store current working image
- Provide reliable retrieval

**Must Never:**
- Know about conversation context (unnecessary)
- Make decisions about which image to use

---

## 2. Image Lifecycle

### First Request: Image Upload + Detection

```
1. User uploads image + asks question
2. Frontend sends to Agent
3. Agent receives ChatRequest
   - chat_id: None (first request)
   - messages: [user_message_with_image]

4. Agent creates NEW chat_id = uuid()
5. Agent initializes _chat_image_state[chat_id] = {}
6. Agent extracts image bytes from message
7. Agent uploads to S3 with chat_id + prediction_id
   → get original_s3_key

8. Agent stores in _chat_image_state[chat_id]:
   {
       "original_s3_key": "s3://bucket/original...",
       "current_s3_key": "s3://bucket/original...",
       "detections": [],
   }

9. Agent sets _current_image_b64 from the same uploaded bytes (NO re-download)

10. Agent calls detect_objects tool
    - Uses _current_image_b64 (already in memory)
    - Sends to YOLO service
    - YOLO returns: detections + annotated_image_b64

11. Agent stores detections in _current_detections (request-scoped)
12. Agent also updates _chat_image_state[chat_id]["detections"] (persistent)
13. Agent stores annotated_image_b64 for display

14. After run_agent finishes, agent uploads final image to S3 (if modified)
15. Updates current_s3_key in state

16. Agent returns ChatResponse:
    {
        "chat_id": "abc-123-def",
        "response": "I found 3 people...",
        "prediction_id": "pred-xyz",
        "annotated_image": "base64...",
        ...
    }

17. Frontend receives chat_id and stores it for next request
18. Frontend displays annotated image and response
```

### Second Request: Image Operation (Example: Blur Object)

```
1. User says "blur the person on the right"
2. Frontend sends ChatRequest:
   {
       "chat_id": "abc-123-def",
       "messages": [... full history ...]
   }

3. Agent receives request
4. Agent checks: request.chat_id is "abc-123-def"
5. Agent checks: "abc-123-def" in _chat_image_state
6. Agent RESTORES state:
   {
       "original_s3_key": "s3://bucket/original...",
       "current_s3_key": "s3://bucket/possibly-modified...",  ← from previous ops
       "detections": [...],  ← previous detections
   }

7. Agent downloads current_s3_key from S3 ONCE
8. Agent sets _current_image_b64 in memory
9. Agent restores _current_detections from _chat_image_state[chat_id]["detections"]

10. Agent understands "person on the right"
    → Resolves to object_id using detections

11. Agent calls blur_object(object_id=1, radius=2.0)
    - Uses _current_image_b64 (already in memory)
    - Extracts object bounding box
    - Crops object region
    - Sends crop to MCP service with radius=2.0
    - MCP returns blurred_crop_b64
    - Agent pastes blurred crop back into _current_image_b64
    - (Does NOT upload yet)

12. After run_agent finishes:
    - Agent uploads modified _current_image_b64 to S3
    → get new_s3_key
    - Agent updates _chat_image_state[chat_id]:
      {
          "original_s3_key": "s3://bucket/original...",  ← unchanged
          "current_s3_key": "s3://bucket/modified...",   ← updated
          "detections": [...],  ← unchanged (no new detection run)
      }

13. Agent returns ChatResponse:
    {
        "chat_id": "abc-123-def",
        "response": "I've blurred the person on the right",
        "annotated_image": "base64...",  ← modified image
        ...
    }

14. Frontend updates display with new image
```

### Third Request: Show Original

```
1. User says "show me the original"
2. Frontend sends ChatRequest with chat_id
3. Agent restores state from _chat_image_state
4. Agent calls show_image(source="original")
   - Retrieves original_s3_key from state
   - Downloads from S3
   - Returns to frontend

5. Frontend displays original image
```

### Fourth Request: Upload New Image in Existing Chat

```
1. User uploads NEW image in existing chat (chat_id already set)
2. Frontend sends ChatRequest:
   {
       "chat_id": "abc-123-def",
       "messages": [... full history ...]
   }

3. Agent receives request
4. Agent checks: request.chat_id exists AND is in _chat_image_state
5. Agent detects: NEW image in message (replaces current image)
6. Agent replaces state:
   {
       "original_s3_key": "s3://bucket/NEW-ORIGINAL...",  ← new image
       "current_s3_key": "s3://bucket/NEW-ORIGINAL...",   ← new image
       "detections": [],  ← cleared (stale for new image)
   }

7. Agent uploads new image to S3
8. Stores S3 keys in state
9. Returns to frontend with new image
10. User can now operate on new image (detections will run if requested)
```

**Rule:** Uploading a new image **replaces** the current image state for that chat, clearing old detections until detect_objects runs again.

### Key Rule

**IMPORTANT:** Every image operation tool ALWAYS works on CURRENT image, not original, unless explicitly requested by user.

This allows operations to compose:
- Blur object → rotate image → resize → crop
- Each operates on result of previous

---

## 3. Conversation Context

### What Must Persist Between Requests

```
_chat_image_state[chat_id] = {
    "original_s3_key": str,           # Immutable, never changes
    "current_s3_key": str,            # Changes as tools modify image
    "detections": list,               # Latest detections from YOLO
}
```

**Why:**
- `original_s3_key`: Allows user to "show original" or reset anytime
- `current_s3_key`: Tells start of request which image to load
- `detections`: Follow-up requests need object information (e.g., "blur the person on the right")

### What Should NOT Persist

These are request-scoped ContextVars and regenerated each request:

```
_current_image_s3_key (ContextVar)      # Downloaded from S3, reset after request
_current_image_b64 (ContextVar)         # In-memory image during request, reset after
_current_prediction_id (ContextVar)     # New UUID each request, reset after
_current_chat_id (ContextVar)           # Current request's chat_id, reset after
_current_detections (ContextVar)        # Restored from _chat_image_state at start,
                                        # updated during request, reset after
```

**Important clarification:** The ContextVar `_current_detections` itself is request-scoped and reset after each request. However, the detections **data** it holds is persisted in `_chat_image_state[chat_id]["detections"]`. At the start of each request, detections are restored from the persistent state into the ContextVar for use during that request.

### Why ContextVar Alone Cannot Support Multi-Turn

**ContextVar Problem:**
- Request-scoped (lives for duration of one /chat request)
- Automatically reset in `finally` block
- Next request starts with empty ContextVars
- No automatic restoration mechanism

**Example of failure:**

```python
# Request 1: Upload image
_current_image_s3_key.set("s3://original")
_current_detections.set([...])
# ... request completes
_current_image_s3_key.reset()    # ← Lost!
_current_detections.reset()      # ← Lost!

# Request 2: User says "blur the person"
_current_detections.get()         # ← Returns [] (empty!)
# Agent doesn't know about previous detections
# Must re-run detect_objects or ask user again
```

**Solution:**
- Use persistent dict `_chat_image_state` indexed by `chat_id`
- Store only S3 keys (immutable identifiers)
- Detections are cached during request (can be re-fetched if needed)
- Follow-up requests restore S3 keys, then download as needed

### Concurrency Assumption

**Out of scope for PR2.** This architecture assumes **at most one request in-flight per chat_id** at any time. Multiple concurrent requests to the same chat_id will cause data races in `_chat_image_state`. For the single-user chat sessions in this project, this is acceptable. Multi-user deployments would require per-chat_id locks or a proper database transaction layer.

### S3 Cleanup

**Out of scope for PR2.** The global `_chat_image_state` dict grows indefinitely as users chat. S3 objects are never deleted. For testing and development, manual cleanup is acceptable (delete S3 objects by hand, restart the agent). Production deployments would need:
- TTL-based session cleanup (remove inactive chats after N days)
- DELETE `/chat/{chat_id}` endpoint to explicitly end conversations
- S3 lifecycle policies to auto-delete old objects

These are future enhancements (post-PR2).

---

## 4. Image State Invariants

These invariants define how the system maintains consistency across requests:

1. **original_s3_key never changes** until a new image is uploaded to the chat. Once set, it always points to the original image the user provided in that conversation.

2. **current_s3_key always points to the latest working image.** It may differ from original_s3_key if image tools have modified the image. It reflects the exact state at the end of the previous request.

3. **Detections always correspond to the image on which YOLO last executed.** If the current image changes (via image operation tools), detections may become stale and correspond to a previous image state.

4. **ContextVars never survive beyond a request.** All context variables are reset in the `finally` block. State recovery across requests happens via _chat_image_state, not via ContextVar persistence.

---

## 5. State Ownership

### Frontend Owns
- Message history (displayed to user)
- UI state (input field, loading spinner, etc.)
- `chat_id` (received from Agent, used for next request)

### Agent Owns
- `_chat_image_state`: dict[chat_id] → {original_s3_key, current_s3_key}
- Detections (cached in ContextVar during request)
- Prediction ID (generated per request)
- Orchestration logic (which tool to call)
- Tool routing decisions

### S3 Owns
- Original image file
- Current working image file

### YOLO Owns
- Detection results (only while processing)
- Annotated image (only while processing)

### MCP Owns
- Nothing after request completes
- Processing is stateless

---

## 6. Tool Workflow

### Universal Tool Pattern

Every image-modification tool follows this pattern:

```
1. Get _current_image_b64 from context (already downloaded)
2. Perform transformation on _current_image_b64
3. Update _current_image_b64 in context
4. Return status to user (do NOT upload)
```

**Important:** Tools do NOT upload to S3. Upload happens once after run_agent finishes, in the /chat endpoint.

### Specific Tool Workflows

#### detect_objects()
- **Input:** None (uses _current_image_b64 from context)
- **Process:**
  1. Use _current_image_b64 (already in memory)
  2. Send image to YOLO
  3. Receive: detections + annotated_image_b64
  4. Cache detections in _current_detections
  5. Update _detection_result["annotated_image"] for display
  6. Return status to user
- **Important:** Does NOT modify the working image (_current_image_b64 remains unchanged)
- **Output:** Detections (for tool use) + annotated image (for display only)
- **Does NOT upload** (detection produces no change to current image)

#### blur_object(object_id, radius)
- **Input:** object_id (index), radius (float)
- **Process:**
  1. Use _current_image_b64 (already in memory)
  2. Use _current_detections to find bounding box
  3. Crop region around object
  4. Send crop to MCP with radius parameter
  5. Receive blurred_crop_b64
  6. Paste blurred_crop back into _current_image_b64
  7. Update _current_image_b64 in context
  8. Return status (do NOT upload)
- **Upload happens once after run_agent** in /chat endpoint
- **Detection staleness:** After blur_object modifies the image, the detections may become stale (coordinates were relative to previous image state). This is an accepted property of the system.

#### blur_image(radius)
- **Input:** radius (float)
- **Process:**
  1. Use _current_image_b64 (already in memory)
  2. Send full image to MCP with radius parameter
  3. Receive blurred_image_b64
  4. Update _current_image_b64 with result
  5. Return status (do NOT upload)

#### rotate_image(angle)
- **Input:** angle (float)
- **Process:**
  1. Use _current_image_b64 (already in memory)
  2. Send to MCP with angle parameter
  3. Receive rotated_image_b64
  4. Update _current_image_b64 with result
  5. Return status (do NOT upload)

#### crop_object(object_id, offsets)
- **Input:** object_id, left/top/right/bottom offsets
- **Process:**
  1. Use _current_image_b64 (already in memory)
  2. Use _current_detections to find bounding box
  3. Apply offsets
  4. Crop to new bounding box
  5. Update _current_image_b64 with cropped result
  6. Return status (do NOT upload)

#### resize_image(width, height)
- **Input:** width, height
- **Process:**
  1. Use _current_image_b64 (already in memory)
  2. Send to MCP with dimensions
  3. Receive resized_image_b64
  4. Update _current_image_b64 with result
  5. Return status (do NOT upload)

#### add_noise_image(amount)
- **Input:** amount (0.0-1.0)
- **Process:**
  1. Use _current_image_b64 (already in memory)
  2. Send to MCP with amount parameter
  3. Receive noisy_image_b64
  4. Update _current_image_b64 with result
  5. Return status (do NOT upload)

#### add_noise_object(object_id, amount)
- **Input:** object_id, amount
- **Process:**
  1. Use _current_image_b64 (already in memory)
  2. Use _current_detections to find bounding box
  3. Crop region around object
  4. Send crop to MCP with amount parameter
  5. Receive noisy_crop_b64
  6. Paste into full _current_image_b64
  7. Return status (do NOT upload)

#### show_image(source)
- **Input:** source = "original" | "current"
- **Process:**
  1. If source == "original":
     - Use original_s3_key from state
     - Download from S3
  2. If source == "current":
     - Return _current_image_b64 (already in memory, no download needed)
  3. Return image (no modification, no upload)

#### flip_image(direction)
- **Input:** direction ("horizontal" | "vertical")
- **Process:**
  1. Use _current_image_b64 (already in memory)
  2. Send to MCP with direction parameter
  3. Receive flipped_image_b64
  4. Update _current_image_b64 with result
  5. Return status (do NOT upload)

---

## 7. chat_id vs prediction_id Ownership

### Definitions

**chat_id:** Stable identifier for entire conversation with a user
- Generated once per new conversation
- Never changes
- Used to restore image state across requests
- Persists in _chat_image_state
- Returned to frontend for session continuity

**prediction_id:** Unique identifier for a single YOLO detection run
- Generated fresh for EVERY YOLO /predict call
- Used to store YOLO results (annotations, detections)
- Temporary, for YOLO service use only
- Must never be confused with chat_id
- Must never be used to index conversation state

### Rules

1. **Each YOLO call gets new prediction_id:**
   ```python
   prediction_id = str(uuid.uuid4())  # NEW for every detect_objects call
   ```

2. **prediction_id is never reused as chat_id**
   - Different namespaces
   - Different purposes
   - Predictable collision potential if mixed

3. **chat_id NEVER used for YOLO calls**
   - YOLO doesn't know about conversations
   - Only prediction_id passed to YOLO

4. **ChatResponse.prediction_id field:**
   - Contains the latest YOLO prediction_id from this request
   - Only populated if detect_objects was called
   - Can be None if user only did image operations

---

## 8. Context Bug Analysis

### What Is the Bug?

**Current behavior:**
- Every request generates a NEW `chat_id`
- Request 1: chat_id = "abc-123"
  - Uploads image to S3
  - Runs detect_objects
  - Returns response with chat_id
- Request 2: chat_id = "xyz-789" (NEW!)
  - Frontend sends previous chat_id "abc-123" in request body
  - Agent generates NEW chat_id "xyz-789"
  - Agent ignores request.chat_id
  - Agent downloads NOTHING from S3 (no previous image)
  - Treats request as brand new conversation
  - Detections are lost
  - Image history is lost

### Why Does It Happen?

```python
def chat(request: ChatRequest):
    chat_id = str(uuid.uuid4())  # ← ALWAYS NEW, ignores request.chat_id
```

Root causes:
1. `ChatRequest` doesn't accept `chat_id` parameter
2. Agent never checks for incoming `chat_id`
3. No `_chat_image_state` to lookup session state
4. Architecture assumes all requests are independent

### What Information Is Lost?

- **Detections:** User must re-run detect_objects each turn
- **Image state:** Tools always start with original, can't chain operations
- **Conversation context:** No relationship between requests
- **User intent:** "Blur the person" requires re-detecting objects

### What Should Be Preserved?

- `chat_id`: Identifier for entire conversation
- `original_s3_key`: Path to original image (immutable)
- `current_s3_key`: Path to current working image (mutable)
- `detections`: Object locations and labels

### Correct Architecture

```python
_chat_image_state: dict[str, dict] = {}
# {
#   "chat-abc-123": {
#       "original_s3_key": "s3://bucket/original...",
#       "current_s3_key": "s3://bucket/current..."
#   },
#   "chat-xyz-789": {
#       "original_s3_key": "s3://bucket/other...",
#       "current_s3_key": "s3://bucket/other..."
#   }
# }

def chat(request: ChatRequest):
    if request.chat_id and request.chat_id in _chat_image_state:
        # Restore existing session
        chat_id = request.chat_id
        current_s3_key = _chat_image_state[chat_id]["current_s3_key"]
    else:
        # Create new session
        chat_id = str(uuid.uuid4())
        current_s3_key = None
```

---

## 9. Natural Language Understanding

### How LLM + Architecture Work Together

The LLM (Large Language Model) in the Agent processes natural language. The architecture supports this by providing structured data.

**The LLM does NOT understand anything automatically. The architecture provides:**

1. **Structured detections:** Each detection includes:
   - object_id (index)
   - label ("person", "car", etc.)
   - bounding box (x1, y1, x2, y2)
   - confidence score

2. **Position resolution:** Agent computes left/center/right from bounding box:
   - Objects sorted by x-center
   - Left third → "left"
   - Middle third → "center"
   - Right third → "right"

3. **Simple tool interface:** Tools have clear, deterministic parameters
   - blur_object(object_id, radius)
   - rotate_image(angle)
   - crop_object(object_id, offsets)

4. **Immutable references:**
   - original_s3_key: Always points to original
   - current_s3_key: Always points to current working image

### Example: "Blur the person on the right"

**Process:**
1. LLM receives user phrase: "Blur the person on the right"
2. LLM receives structured detections (from persistent state)
3. LLM maps: label="person" + position="right" → object_id=3
4. LLM calls: blur_object(object_id=3, radius=2.0)

**If LLM is unreliable**, Agent can add deterministic resolver logic later, but PR2 assumes the LLM works.

### What Architecture Does NOT Provide

- Natural language understanding (that's the LLM's job)
- Prompt engineering strategies
- Error correction or fallbacks

### What Architecture DOES Provide

- Persistent detections so references remain valid across requests
- Immutable original reference always available
- Mutable current reference for chained operations
- Clear, deterministic tool interface
- Structure for resolver logic if needed later

---

## 10. Minimal Implementation Plan

### Overview

The implementation must satisfy these priorities:

1. **Correct architecture:** Restore conversation context
2. **Simplicity:** Minimal code changes, avoid overengineering
3. **No duplicate state:** One source of truth per piece of data
4. **No temporary workarounds:** Each change solves a real problem
5. **Enable future features:** Don't block PR3 (MCP integration) or PR4 (undo/history)

### Changes Required

#### Change 1: Add persistent state dict

**File:** services/agent/app.py  
**Location:** After context variables (line ~67)  
**What to add:**
```python
_chat_image_state: dict[str, dict] = {}
# Structure: {
#   "chat_id": {
#       "original_s3_key": str,
#       "current_s3_key": str,
#   }
# }
```

**Why necessary:**
- ContextVar cannot persist across requests
- Need to store S3 keys per chat_id
- Enables image state restoration

**What bug it fixes:**
- Fixes: Image state lost between requests
- Enables: Multi-turn conversations

**Can this remove existing code?**
- No, but it makes previous workarounds unnecessary
- Previous requests always generated new chat_id; now we can restore

#### Change 2: Add chat_id to ChatRequest

**File:** services/agent/app.py  
**Location:** Line ~336 (ChatRequest class)  
**What to add:**
```python
class ChatRequest(BaseModel):
    chat_id: Optional[str] = None        # ← ADD THIS
    messages: list[ChatMessage]
```

**Why necessary:**
- Frontend needs to send chat_id for follow-up requests
- Agent needs to know which session this request belongs to

**What bug it fixes:**
- Fixes: Agent doesn't know session context
- Enables: Frontend can provide chat_id

**Can this remove existing code?**
- No, purely additive

#### Change 3: Add chat_id to ChatResponse

**File:** services/agent/app.py  
**Location:** Line ~340 (ChatResponse class)  
**What to add:**
```python
class ChatResponse(BaseModel):
    chat_id: str                         # ← ADD THIS
    response: str
    prediction_id: Optional[str] = None
    annotated_image: Optional[str] = None
    agent_loop_time_s: float = 0.0
    iterations: int = 0
    tools_called: list[str] = Field(default_factory=list)
    context_limit_exceeded: bool = False
    tokens_used: TokensUsed = Field(default_factory=TokensUsed)
```

**Why necessary:**
- Frontend needs to know which chat_id was used
- Frontend stores this for next request

**What bug it fixes:**
- Fixes: Frontend doesn't know which chat_id to use
- Enables: Frontend can preserve session across requests

**Can this remove existing code?**
- No, purely additive

#### Change 4: Refactor /chat endpoint to restore-or-create

**File:** services/agent/app.py  
**Location:** Line ~435 (chat function start)  
**What to change:**

**OLD (generates new UUID always):**
```python
def chat(request: ChatRequest):
    lc_messages = []
    latest_image_s3_key = None
    chat_id = str(uuid.uuid4())
    prediction_id = str(uuid.uuid4())
```

**NEW (restore or create):**
```python
def chat(request: ChatRequest):
    lc_messages = []
    latest_image_s3_key = None
    prediction_id = str(uuid.uuid4())
    
    # Restore or create chat session
    if request.chat_id and request.chat_id in _chat_image_state:
        # Follow-up request: restore current image from state
        chat_id = request.chat_id
        latest_image_s3_key = _chat_image_state[chat_id]["current_s3_key"]
    else:
        # New request: generate new chat_id
        chat_id = str(uuid.uuid4())
        latest_image_s3_key = None
        _chat_image_state[chat_id] = {}  # Initialize state
```

**Why necessary:**
- Agent must lookup session state when chat_id provided
- Must initialize state for new chats
- Must restore image state for follow-up requests

**What bug it fixes:**
- Fixes: Agent always creates new session
- Fixes: Image state lost between requests
- Enables: Follow-up requests can restore context

**Can this remove existing code?**
- No, but it replaces the simple uuid.uuid4() assignment with smarter logic

#### Change 5: Store S3 keys in _chat_image_state after upload

**File:** services/agent/app.py  
**Location:** Line ~460 (after upload_image_to_s3 call)  
**What to add:**

**AFTER this existing code:**
```python
latest_image_s3_key = upload_image_to_s3(
    image_bytes=image_bytes,
    chat_id=chat_id,
    prediction_id=prediction_id,
    original_filename="original.jpg"
)
logging.info(f"Image uploaded to S3: {latest_image_s3_key}")
```

**ADD this:**
```python
# Store original and current S3 keys in chat state
_chat_image_state[chat_id]["original_s3_key"] = latest_image_s3_key
_chat_image_state[chat_id]["current_s3_key"] = latest_image_s3_key
```

**Why necessary:**
- After upload, must persist S3 keys for future requests
- Original and current start as same (no modifications yet)

**What bug it fixes:**
- Fixes: S3 keys not available for follow-up requests
- Enables: Tools can access current image key

**Can this remove existing code?**
- No, purely additive

#### Change 6: Return chat_id in response

**File:** services/agent/app.py  
**Location:** Line ~484 (before return run_agent)  
**What to change:**

**OLD:**
```python
try:
    return run_agent(lc_messages)
finally:
    _current_image_s3_key.reset(image_token)
```

**NEW:**
```python
try:
    response = run_agent(lc_messages)
    response.chat_id = chat_id  # ← ADD THIS
    return response
finally:
    _current_image_s3_key.reset(image_token)
```

**Why necessary:**
- Agent must return chat_id to frontend
- Frontend uses it for follow-up requests

**What bug it fixes:**
- Fixes: Frontend doesn't receive chat_id
- Enables: Frontend can preserve session

**Can this remove existing code?**
- No, but it changes return from direct to assignment

### Summary Table

| Change | Type | Size | Why | Fixes |
|--------|------|------|-----|-------|
| 1. Add _chat_image_state | Addition | 4 lines | Persist session state | Multi-turn context |
| 2. Add chat_id to ChatRequest | Addition | 1 line | Accept incoming chat_id | Session restoration |
| 3. Add chat_id to ChatResponse | Addition | 1 line | Return chat_id | Session tracking |
| 4. Refactor /chat logic | Change | ~10 lines | Restore or create | Image state persistence |
| 5. Store S3 keys in state | Addition | 2 lines | Persist S3 keys | Tool access to images |
| 6. Return chat_id in response | Change | 2 lines | Send chat_id to frontend | Session continuity |

**Total:** ~20 lines of code changes (mostly additions, few rewrites)

### What This Does NOT Change

- Tool implementations (tools will be updated in PR3 after this foundation)
- Frontend code (reverted separately, updated after backend verified)
- YOLO integration (unchanged)
- MCP integration (future PR3)
- System prompt (unchanged for now)

### What This Enables

✅ Multi-turn conversations  
✅ Image state restoration  
✅ Persistent detections across requests  
✅ Follow-up operations build on previous results  
✅ Foundation for PR3 (MCP tool integration)  
✅ Foundation for future features (history, undo, advanced features)  

---

## 11. Complete Request Lifecycle

This section describes the exact flow of a single /chat request from start to finish.

```
BEGIN /chat request

┌─ Step 1: Receive ChatRequest
│  Input: ChatRequest with optional chat_id and messages
│
├─ Step 2: Resolve or Create Chat Session
│  if request.chat_id exists AND chat_id in _chat_image_state:
│      Restore session: chat_id = request.chat_id
│      state = _chat_image_state[chat_id]
│  else:
│      Create new: chat_id = uuid()
│      Initialize: _chat_image_state[chat_id] = {}
│      state = _chat_image_state[chat_id]
│
├─ Step 3: Handle Image Upload (if new image)
│  if message contains image_base64:
│      Decode image bytes
│      Upload original to S3 → original_s3_key
│      Set state["original_s3_key"] = original_s3_key
│      Set state["current_s3_key"] = original_s3_key (starts same)
│      Set _current_image_b64 from uploaded bytes (NO re-download)
│  else:
│      No new image (follow-up request or text-only)
│
├─ Step 4: Restore or Download Current Image
│  if no new image uploaded:
│      Download state["current_s3_key"] from S3 ONCE
│      Set _current_image_b64 in memory
│  endif
│  (Now _current_image_b64 is always available in memory)
│
├─ Step 5: Restore Latest Detections
│  if state["detections"] exists:
│      Set _current_detections = state["detections"]
│  else:
│      Set _current_detections = []
│
├─ Step 6: Initialize Context Variables
│  Set _current_chat_id = chat_id
│  Set _current_prediction_id for any YOLO calls
│  Set _detection_result = {"prediction_id": None, "annotated_image": None}
│
├─ Step 7: Run Agent Tool Loop
│  Call run_agent(lc_messages) ← Agent decides which tools to call
│  
│  Tools during loop:
│  ├─ detect_objects():
│  │   - Sends _current_image_b64 to YOLO with NEW prediction_id
│  │   - Receives detections + annotated_image_b64
│  │   - Updates _current_detections
│  │   - Updates _detection_result["annotated_image"]
│  │
│  └─ Image operation tools (blur, rotate, crop, etc.):
│      - Receive _current_image_b64 from context
│      - Perform transformation
│      - Update _current_image_b64 in context
│      - Do NOT upload to S3
│
├─ Step 8: After run_agent Completes
│  if _current_image_b64 was modified:
│      Upload final _current_image_b64 to S3 → new_s3_key
│      Update state["current_s3_key"] = new_s3_key
│  endif
│  
│  if _current_detections was updated:
│      Update state["detections"] = _current_detections
│  endif
│
├─ Step 9: Build ChatResponse
│  response = ChatResponse(
│      chat_id = chat_id,  ← Always return current chat_id
│      response = agent_text_response,
│      prediction_id = _detection_result["prediction_id"],  ← If detection ran
│      annotated_image = _detection_result["annotated_image"],  ← Latest image (detection or operation)
│      agent_loop_time_s = elapsed_time,
│      iterations = tool_call_count,
│      tools_called = [list of tool names],
│      ...
│  )
│
├─ Step 10: Reset Context Variables
│  In finally block:
│      _current_image_s3_key.reset()
│      _current_image_b64.reset()
│      _current_chat_id.reset()
│      _current_prediction_id.reset()
│      _current_detections.reset()
│
└─ Return ChatResponse to frontend

END /chat request
```

### Key Invariants

1. **_current_image_b64 is downloaded exactly once per request** (unless new image upload)
2. **Modified image is uploaded exactly once per request** (after run_agent completes)
3. **Tools only modify _current_image_b64, never upload directly**
4. **Detections are persisted after every detect_objects call** (stored in _chat_image_state[chat_id]["detections"])
5. **chat_id is stable across requests** (or new if not provided)
6. **prediction_id is unique per YOLO call** (never reused, never used as chat_id)
7. **S3 keys point to actual file sources** (original never changes, current evolves)
8. **annotated_image in ChatResponse contains the latest image for display** (populated by detect_objects or image operation tools that modified _current_image_b64)

---

## Checklist Before Coding

- [ ] Architecture document is approved
- [ ] All 10 sections reviewed
- [ ] Implementation plan is clear
- [ ] No ambiguity about what changes where
- [ ] Team agrees this is minimal and correct
- [ ] No questions about responsibilities or ownership

