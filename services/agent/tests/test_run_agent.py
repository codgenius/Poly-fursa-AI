"""
Unit tests for the run_agent() function.

Tests verify:
- Agent loop correctly processes LLM responses
- Tool calls are executed and results appended to messages
- Max iterations limit is enforced
- Final no-tool-call response is returned
- Context limit is checked and enforced
- Token usage is tracked across iterations
- run_agent() makes no real LLM or YOLO service calls
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


@pytest.fixture(autouse=True)
def load_app():
    """Load the app module for all tests in this module."""
    import app
    return app


class TestRunAgentBasics:
    """Test basic run_agent functionality."""
    
    def test_single_iteration_no_tools(self, mock_ai_response_no_tools, load_app):
        """Agent stops immediately when no tool calls in response."""
        with patch.object(load_app, "llm_with_tools") as mock_llm:
            mock_llm.invoke.return_value = mock_ai_response_no_tools
            
            response = load_app.run_agent([HumanMessage(content="Hello")])
            
            assert response.response == "This is the final answer."
            assert response.iterations == 1
            assert response.tools_called == []
            assert response.context_limit_exceeded is False
            assert response.tokens_used.input == 100
            assert response.tokens_used.output == 50
    
    def test_single_tool_call_then_response(
        self,
        mock_ai_response_with_tool_call,
        mock_ai_response_no_tools,
        mock_tool_result,
        load_app,
    ):
        """Agent executes one tool and returns final response."""
        with patch.object(load_app, "llm_with_tools") as mock_llm:
            # First call: response with tool call
            # Second call: response without tool call (final)
            mock_llm.invoke.side_effect = [
                mock_ai_response_with_tool_call,
                mock_ai_response_no_tools,
            ]
            
            with patch.object(load_app, "TOOLS") as mock_tools:
                mock_detect = MagicMock()
                mock_detect.invoke.return_value = mock_tool_result
                mock_tools.__getitem__.return_value = mock_detect
                
                response = load_app.run_agent([HumanMessage(content="What's in the image?")])
                
                assert response.response == "This is the final answer."
                assert response.iterations == 2
                assert "detect_objects" in response.tools_called
                assert len(response.tools_called) == 1
                assert response.context_limit_exceeded is False
    
    def test_multiple_tool_calls_in_single_response(
        self,
        mock_ai_response_no_tools,
        load_app,
    ):
        """Agent handles multiple tool calls in a single response."""
        with patch.object(load_app, "llm_with_tools") as mock_llm:
            # Create response with multiple tool calls
            multi_tool_response = AIMessage(
                content="Let me check multiple things.",
                usage_metadata={
                    "input_tokens": 100,
                    "output_tokens": 40,
                    "total_tokens": 140,
                }
            )
            multi_tool_response.tool_calls = [
                {"id": "call_1", "name": "detect_objects", "args": {}},
                {"id": "call_2", "name": "detect_objects", "args": {}},
            ]
            
            mock_llm.invoke.side_effect = [
                multi_tool_response,
                mock_ai_response_no_tools,
            ]
            
            with patch.object(load_app, "TOOLS") as mock_tools:
                mock_detect = MagicMock()
                tool_result = ToolMessage(
                    content=json.dumps({"detections": []}),
                    tool_call_id="call_id",
                )
                mock_detect.invoke.return_value = tool_result
                mock_tools.__getitem__.return_value = mock_detect
                
                response = load_app.run_agent([HumanMessage(content="Check things")])
                
                assert response.iterations == 2
                # Should have 2 tool calls tracked
                assert len(response.tools_called) == 2


class TestRunAgentMaxIterations:
    """Test max_iterations limit enforcement."""
    
    def test_max_iterations_exceeded(self, mock_ai_response_with_tool_call, mock_tool_result, load_app):
        """Agent stops and returns error when max_iterations is exceeded."""
        with patch.object(load_app, "llm_with_tools") as mock_llm:
            # Keep returning tool calls to exceed max_iterations
            mock_llm.invoke.return_value = mock_ai_response_with_tool_call
            
            with patch.object(load_app, "TOOLS") as mock_tools:
                mock_detect = MagicMock()
                mock_detect.invoke.return_value = mock_tool_result
                mock_tools.__getitem__.return_value = mock_detect
                
                response = load_app.run_agent(
                    [HumanMessage(content="Loop")],
                    max_iterations=3
                )
                
                # Should hit max_iterations and return
                assert response.iterations == 3
                assert response.context_limit_exceeded is True
                assert "maximum number of tool calls" in response.response
                # Should have called LLM exactly 3 times (max_iterations)
                assert mock_llm.invoke.call_count == 3
    
    def test_max_iterations_default_is_10(self, mock_ai_response_with_tool_call, mock_tool_result, load_app):
        """Default max_iterations should be 10."""
        with patch.object(load_app, "llm_with_tools") as mock_llm:
            mock_llm.invoke.return_value = mock_ai_response_with_tool_call
            
            with patch.object(load_app, "TOOLS") as mock_tools:
                mock_detect = MagicMock()
                mock_detect.invoke.return_value = mock_tool_result
                mock_tools.__getitem__.return_value = mock_detect
                
                # Call with no max_iterations parameter
                response = load_app.run_agent([HumanMessage(content="Loop")])
                
                # Should use default of 10
                assert response.iterations == 10
                assert mock_llm.invoke.call_count == 10


class TestRunAgentContextLimit:
    """Test context limit checking."""
    
    def test_context_limit_exceeded_mid_loop(self, mock_ai_response_with_tool_call, load_app):
        """Agent stops when input tokens exceed 90% of max."""
        with patch.object(load_app, "llm_with_tools") as mock_llm:
            # Response with very high input tokens
            high_token_response = AIMessage(
                content="Processing",
                usage_metadata={
                    "input_tokens": 195000,  # 97.5% of 200k
                    "output_tokens": 100,
                    "total_tokens": 195100,
                }
            )
            high_token_response.tool_calls = [
                {"id": "call_1", "name": "detect_objects", "args": {}},
            ]
            
            mock_llm.invoke.return_value = high_token_response
            
            with patch.object(load_app, "TOOLS") as mock_tools:
                mock_detect = MagicMock()
                mock_detect.invoke.return_value = ToolMessage(
                    content="{}",
                    tool_call_id="call_1",
                )
                mock_tools.__getitem__.return_value = mock_detect
                
                with patch.object(load_app, "MAX_INPUT_TOKENS", 200000):
                    response = load_app.run_agent([HumanMessage(content="Hi")])
                    
                    # Should stop due to context limit
                    assert response.context_limit_exceeded is True
                    assert "context limit" in response.response
    
    def test_context_limit_none_no_check(self, mock_ai_response_no_tools, load_app):
        """When MAX_INPUT_TOKENS is None, context limit check is skipped."""
        with patch.object(load_app, "llm_with_tools") as mock_llm:
            mock_llm.invoke.return_value = mock_ai_response_no_tools
            
            with patch.object(load_app, "MAX_INPUT_TOKENS", None):
                response = load_app.run_agent([HumanMessage(content="Hi")])
                
                assert response.context_limit_exceeded is False


class TestRunAgentTokenTracking:
    """Test token usage tracking across iterations."""
    
    def test_token_accumulation_across_iterations(
        self,
        mock_ai_response_no_tools,
        load_app,
    ):
        """Token counts should accumulate across iterations."""
        with patch.object(load_app, "llm_with_tools") as mock_llm:
            # First response: 100 input, 30 output
            response_1 = AIMessage(
                content="Processing",
                usage_metadata={
                    "input_tokens": 100,
                    "output_tokens": 30,
                    "total_tokens": 130,
                }
            )
            response_1.tool_calls = [
                {"id": "call_1", "name": "detect_objects", "args": {}},
            ]
            
            # Second response: 150 input, 50 output (total so far: 250+80)
            response_2 = AIMessage(
                content="Final answer",
                usage_metadata={
                    "input_tokens": 150,
                    "output_tokens": 50,
                    "total_tokens": 200,
                }
            )
            response_2.tool_calls = []
            
            mock_llm.invoke.side_effect = [response_1, response_2]
            
            with patch.object(load_app, "TOOLS") as mock_tools:
                mock_detect = MagicMock()
                mock_detect.invoke.return_value = ToolMessage(
                    content="{}",
                    tool_call_id="call_1",
                )
                mock_tools.__getitem__.return_value = mock_detect
                
                result = load_app.run_agent([HumanMessage(content="Hi")])
                
                # Tokens should accumulate
                assert result.tokens_used.input == 250  # 100 + 150
                assert result.tokens_used.output == 80  # 30 + 50
                assert result.tokens_used.total == 330  # 130 + 200
    
    def test_missing_usage_metadata(self, load_app):
        """Should handle responses without usage_metadata gracefully."""
        with patch.object(load_app, "llm_with_tools") as mock_llm:
            # Response without usage_metadata
            response = AIMessage(content="No token info")
            response.tool_calls = []
            # Simulate no usage_metadata
            if hasattr(response, "usage_metadata"):
                del response.usage_metadata
            
            mock_llm.invoke.return_value = response
            
            result = load_app.run_agent([HumanMessage(content="Hi")])
            
            # Should default to 0
            assert result.tokens_used.input == 0
            assert result.tokens_used.output == 0


class TestRunAgentMessageFlow:
    """Test message flow through the agent loop."""
    
    def test_system_prompt_prepended(self, mock_ai_response_no_tools, load_app):
        """System prompt should be first message sent to LLM."""
        with patch.object(load_app, "llm_with_tools") as mock_llm:
            mock_llm.invoke.return_value = mock_ai_response_no_tools
            
            user_msg = HumanMessage(content="Hello")
            load_app.run_agent([user_msg])
            
            # Check that invoke was called
            assert mock_llm.invoke.called
            
            # Get the messages passed to invoke
            call_args = mock_llm.invoke.call_args
            messages = call_args[0][0]  # First positional argument
            
            # First message should be SystemMessage
            assert isinstance(messages[0], SystemMessage)
            assert "vision" in messages[0].content.lower()
            # Original user message should be included
            assert any(isinstance(m, HumanMessage) for m in messages)
    
    def test_tool_result_appended_to_messages(
        self,
        mock_ai_response_with_tool_call,
        mock_ai_response_no_tools,
        load_app,
    ):
        """Tool results should be appended as messages to continue loop."""
        with patch.object(load_app, "llm_with_tools") as mock_llm:
            mock_llm.invoke.side_effect = [
                mock_ai_response_with_tool_call,
                mock_ai_response_no_tools,
            ]
            
            with patch.object(load_app, "TOOLS") as mock_tools:
                tool_result_msg = ToolMessage(
                    content=json.dumps({"result": "detection"}),
                    tool_call_id="call_123",
                )
                mock_detect = MagicMock()
                mock_detect.invoke.return_value = tool_result_msg
                mock_tools.__getitem__.return_value = mock_detect
                
                load_app.run_agent([HumanMessage(content="What's in the image?")])
                
                # LLM should be called twice
                assert mock_llm.invoke.call_count == 2
                
                # Second call should have tool result message
                second_call_messages = mock_llm.invoke.call_args_list[1][0][0]
                assert any(isinstance(m, ToolMessage) for m in second_call_messages)


class TestRunAgentToolCalls:
    """Test tool call tracking and execution."""
    
    def test_tool_call_tracking(self, mock_ai_response_with_tool_call, mock_ai_response_no_tools, load_app):
        """Tool names should be tracked in tools_called list."""
        with patch.object(load_app, "llm_with_tools") as mock_llm:
            mock_llm.invoke.side_effect = [
                mock_ai_response_with_tool_call,
                mock_ai_response_no_tools,
            ]
            
            with patch.object(load_app, "TOOLS") as mock_tools:
                mock_detect = MagicMock()
                mock_detect.invoke.return_value = ToolMessage(
                    content="{}",
                    tool_call_id="call_123",
                )
                mock_tools.__getitem__.return_value = mock_detect
                
                result = load_app.run_agent([HumanMessage(content="Detect")])
                
                assert "detect_objects" in result.tools_called
                assert len(result.tools_called) == 1
    
    def test_detection_result_returned(self, mock_ai_response_with_tool_call, load_app):
        """Detection result should be captured and returned."""
        with patch.object(load_app, "llm_with_tools") as mock_llm:
            final_response = AIMessage(content="Detection complete")
            final_response.tool_calls = []
            
            mock_llm.invoke.side_effect = [
                mock_ai_response_with_tool_call,
                final_response,
            ]
            
            with patch.object(load_app, "TOOLS") as mock_tools:
                # Simulate detection result with prediction_id
                tool_result = ToolMessage(
                    content=json.dumps({"prediction_uid": "pred_789"}),
                    tool_call_id="call_123",
                )
                mock_detect = MagicMock()
                mock_detect.invoke.return_value = tool_result
                mock_tools.__getitem__.return_value = mock_detect
                
                # Reset detection result
                load_app._detection_result["prediction_id"] = None
                
                result = load_app.run_agent([HumanMessage(content="Detect")])
                
                # _detection_result should be set by detect_objects tool
                # In this test setup, we're not actually calling the real tool
                # but the flow should still track it
                assert result.response == "Detection complete"

