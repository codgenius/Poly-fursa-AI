"""
API endpoint tests for the Vision Agent service.

Tests verify:
- /health endpoint responds with status ok
- /chat endpoint accepts requests and returns responses
- run_agent() is mocked so no real LLM/YOLO calls occur
- Request validation and response structure
"""

import json
import pytest
from unittest.mock import patch, MagicMock


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""
    
    def test_health_returns_ok(self, client):
        """Health check should return status: ok."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestChatEndpoint:
    """Tests for POST /chat endpoint."""
    
    def test_chat_simple_text_no_image(self, client):
        """Chat with text-only message (no image)."""
        import app
        with patch.object(app, "run_agent") as mock_run_agent:
            mock_run_agent.return_value = app.ChatResponse(
                response="Hello! How can I help?",
                prediction_id=None,
                annotated_image=None,
                agent_loop_time_s=0.5,
                iterations=1,
                tools_called=[],
                context_limit_exceeded=False,
                tokens_used=app.TokensUsed(input=50, output=20, total=70),
            )
            
            response = client.post(
                "/chat",
                json={
                    "messages": [
                        {
                            "role": "user",
                            "content": "Hello!",
                            "image_base64": None,
                        }
                    ]
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["response"] == "Hello! How can I help?"
            assert data["iterations"] == 1
            assert data["tools_called"] == []
    
    def test_chat_with_image_base64(self, client):
        """Chat with base64-encoded image."""
        # A minimal valid JPEG in base64
        minimal_jpeg_b64 = "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAA=="
        
        import app
        with patch.object(app, "run_agent") as mock_run_agent:
            mock_run_agent.return_value = app.ChatResponse(
                response="I detected 2 objects in the image.",
                prediction_id="pred_123",
                annotated_image="annotated_b64_data",
                agent_loop_time_s=2.5,
                iterations=2,
                tools_called=["detect_objects"],
                context_limit_exceeded=False,
                tokens_used=app.TokensUsed(input=500, output=100, total=600),
            )
            
            response = client.post(
                "/chat",
                json={
                    "messages": [
                        {
                            "role": "user",
                            "content": "What's in this image?",
                            "image_base64": minimal_jpeg_b64,
                        }
                    ]
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["response"] == "I detected 2 objects in the image."
            assert data["prediction_id"] == "pred_123"
            assert data["annotated_image"] == "annotated_b64_data"
            assert "detect_objects" in data["tools_called"]
    
    def test_chat_multi_turn_conversation(self, client):
        """Chat with multi-turn conversation history."""
        import app
        with patch.object(app, "run_agent") as mock_run_agent:
            mock_run_agent.return_value = app.ChatResponse(
                response="The car in the previous image was a red sedan.",
                prediction_id=None,
                annotated_image=None,
                agent_loop_time_s=1.2,
                iterations=1,
                tools_called=[],
                context_limit_exceeded=False,
                tokens_used=app.TokensUsed(input=300, output=50, total=350),
            )
            
            response = client.post(
                "/chat",
                json={
                    "messages": [
                        {
                            "role": "user",
                            "content": "What color was that car?",
                        },
                        {
                            "role": "assistant",
                            "content": "I need to look at the image again.",
                        },
                    ]
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "red sedan" in data["response"]
    
    def test_chat_context_limit_exceeded(self, client):
        """Chat response when context limit is exceeded."""
        import app
        with patch.object(app, "run_agent") as mock_run_agent:
            mock_run_agent.return_value = app.ChatResponse(
                response="Sorry, the conversation is approaching the model context limit.",
                prediction_id=None,
                annotated_image=None,
                agent_loop_time_s=0.8,
                iterations=5,
                tools_called=[],
                context_limit_exceeded=True,
                tokens_used=app.TokensUsed(input=180000, output=1000, total=181000),
            )
            
            response = client.post(
                "/chat",
                json={
                    "messages": [
                        {
                            "role": "user",
                            "content": "Continue our very long conversation...",
                        }
                    ]
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["context_limit_exceeded"] is True
            assert "context limit" in data["response"]
    
    def test_chat_max_iterations_exceeded(self, client):
        """Chat response when max iterations is exceeded."""
        import app
        with patch.object(app, "run_agent") as mock_run_agent:
            mock_run_agent.return_value = app.ChatResponse(
                response="Sorry, I could not complete the request because the agent reached the maximum number of tool calls.",
                prediction_id=None,
                annotated_image=None,
                agent_loop_time_s=5.0,
                iterations=10,
                tools_called=["detect_objects"] * 10,
                context_limit_exceeded=True,
                tokens_used=app.TokensUsed(input=100000, output=5000, total=105000),
            )
            
            response = client.post(
                "/chat",
                json={
                    "messages": [
                        {
                            "role": "user",
                            "content": "Process many images.",
                        }
                    ]
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["iterations"] == 10
            assert "maximum number of tool calls" in data["response"]
    
    def test_chat_response_structure(self, client):
        """Verify complete response structure matches ChatResponse schema."""
        import app
        with patch.object(app, "run_agent") as mock_run_agent:
            mock_run_agent.return_value = app.ChatResponse(
                response="Test response",
                prediction_id="pred_456",
                annotated_image="img_data",
                agent_loop_time_s=1.23,
                iterations=2,
                tools_called=["detect_objects"],
                context_limit_exceeded=False,
                tokens_used=app.TokensUsed(input=100, output=50, total=150),
            )
            
            response = client.post(
                "/chat",
                json={
                    "messages": [
                        {
                            "role": "user",
                            "content": "Test",
                        }
                    ]
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify all required fields are present
            assert "response" in data
            assert "prediction_id" in data
            assert "annotated_image" in data
            assert "agent_loop_time_s" in data
            assert "iterations" in data
            assert "tools_called" in data
            assert "context_limit_exceeded" in data
            assert "tokens_used" in data
            
            # Verify types
            assert isinstance(data["response"], str)
            assert isinstance(data["iterations"], int)
            assert isinstance(data["tools_called"], list)
            assert isinstance(data["context_limit_exceeded"], bool)
            assert isinstance(data["agent_loop_time_s"], (int, float))
            assert isinstance(data["tokens_used"], dict)

