"""
Pytest configuration and fixtures for agent service tests.
"""

import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, Mock

# Set required environment variables before any imports
os.environ["MODEL"] = "anthropic:claude-haiku-4-5"
os.environ["YOLO_SERVICE_URL"] = "http://localhost:8080"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["AWS_S3_BUCKET"] = "test-bucket"

# Ensure services/agent is in the path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def mock_llm():
    """Mock LLM with tools."""
    llm = MagicMock()
    llm.profile = {
        "tool_calling": True,
        "max_input_tokens": 200000,
    }
    return llm


@pytest.fixture(autouse=True)
def mock_s3_upload_global():
    """Global mock for S3 upload to avoid actual S3 calls."""
    with patch("s3_utils.upload_image_to_s3") as mock_s3:
        mock_s3.return_value = "chat_id/prediction_id/original/original.jpg"
        yield mock_s3


@pytest.fixture
def client():
    """FastAPI TestClient for the agent app."""
    from fastapi.testclient import TestClient
    
    # Mock init_chat_model at module level before importing app
    with patch("langchain.chat_models.init_chat_model") as mock_init:
        mock_llm = MagicMock()
        mock_llm.profile = {
            "tool_calling": True,
            "max_input_tokens": 200000,
        }
        mock_bound_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_bound_llm
        mock_init.return_value = mock_llm
        
        # Import app module with mocks in place
        import app
        
        # Store the mocks in the app module for test use
        app._mock_llm = mock_llm
        app._mock_bound_llm = mock_bound_llm
        
        return TestClient(app.app)


@pytest.fixture
def load_app():
    """Load and return the app module with mocks in place."""
    # Mock init_chat_model before importing app
    with patch("langchain.chat_models.init_chat_model") as mock_init:
        mock_llm = MagicMock()
        mock_llm.profile = {
            "tool_calling": True,
            "max_input_tokens": 200000,
        }
        mock_bound_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_bound_llm
        mock_init.return_value = mock_llm
        
        import app
        return app


@pytest.fixture
def mock_ai_response_no_tools():
    """Mock AIMessage response with no tool calls (final response)."""
    from langchain_core.messages import AIMessage
    
    msg = AIMessage(
        content="This is the final answer.",
        usage_metadata={
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }
    )
    msg.tool_calls = []
    return msg


@pytest.fixture
def mock_ai_response_with_tool_call():
    """Mock AIMessage response with a tool call."""
    from langchain_core.messages import AIMessage
    
    msg = AIMessage(
        content="Let me detect objects in the image.",
        usage_metadata={
            "input_tokens": 100,
            "output_tokens": 30,
            "total_tokens": 130,
        }
    )
    msg.tool_calls = [
        {
            "id": "call_123",
            "name": "detect_objects",
            "args": {},
        }
    ]
    return msg


@pytest.fixture
def mock_tool_result():
    """Mock tool result message."""
    from langchain_core.messages import ToolMessage
    
    return ToolMessage(
        content=json.dumps({
            "detections": [
                {"class": "person", "confidence": 0.95},
                {"class": "car", "confidence": 0.87},
            ]
        }),
        tool_call_id="call_123",
    )

