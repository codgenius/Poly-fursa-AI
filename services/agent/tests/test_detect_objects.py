"""
Tests for detect_objects tool and detection workflow.

Tests verify:
- detect_objects calls YOLO service correctly
- Detection results are formatted with bbox information for LLM reasoning
- Detections are cached in persistent state
- Detection format includes position info (left, top, right, bottom, center_x)
"""

import json
import pytest
from unittest.mock import patch, MagicMock
import base64


class TestDetectObjectsBasic:
    """Test basic detect_objects functionality."""
    
    def test_detect_objects_requires_image(self, load_app):
        """detect_objects returns error if no image in context."""
        with patch.object(load_app, "_current_image_s3_key") as mock_s3_key:
            mock_s3_key.get.return_value = None
            
            result = load_app.detect_objects.invoke({})
            result_data = json.loads(result)
            
            assert "error" in result_data
            assert "No image" in result_data["error"]
    
    def test_detect_objects_successful_detection(self, load_app):
        """detect_objects successfully detects and formats objects."""
        # Mock YOLO response with detection data
        mock_yolo_response = {
            "prediction_uid": "pred_123",
            "detection_objects": [
                {
                    "label": "person",
                    "box": json.dumps([10.0, 20.0, 150.0, 300.0]),
                    "score": 0.95
                },
                {
                    "label": "car",
                    "box": json.dumps([200.0, 50.0, 400.0, 250.0]),
                    "score": 0.88
                }
            ]
        }
        
        with patch.object(load_app, "_current_image_s3_key") as mock_s3_key, \
             patch.object(load_app, "_current_chat_id") as mock_chat_id, \
             patch.object(load_app, "_current_detections") as mock_detections, \
             patch.object(load_app, "_chat_image_state", {}), \
             patch("httpx.Client") as mock_http_client:
            
            mock_s3_key.get.return_value = "test_image.jpg"
            mock_chat_id.get.return_value = "chat_123"
            
            # Setup HTTP mocks
            mock_client = MagicMock()
            mock_http_client.return_value.__enter__.return_value = mock_client
            
            # Mock YOLO detection response
            mock_response = MagicMock()
            mock_response.json.return_value = mock_yolo_response
            mock_response.raise_for_status.return_value = None
            
            # Mock annotated image response
            mock_image_response = MagicMock()
            mock_image_response.content = b"fake_image_data"
            mock_image_response.raise_for_status.return_value = None
            
            mock_client.post.return_value = mock_response
            mock_client.get.side_effect = [mock_image_response, mock_response]
            
            result = load_app.detect_objects.invoke({})
            
            assert "Detected 2 objects:" in result
            assert "person" in result
            assert "car" in result
            assert "confidence: 0.95" in result
            assert "confidence: 0.88" in result
    
    def test_detect_objects_format_includes_bbox_details(self, load_app):
        """Detection format includes bbox coordinates for position reasoning."""
        mock_yolo_response = {
            "prediction_uid": "pred_123",
            "detection_objects": [
                {
                    "label": "dog",
                    "box": json.dumps([100.0, 150.0, 250.0, 400.0]),
                    "score": 0.92
                }
            ]
        }
        
        with patch.object(load_app, "_current_image_s3_key") as mock_s3_key, \
             patch.object(load_app, "_current_chat_id") as mock_chat_id, \
             patch.object(load_app, "_current_detections") as mock_detections, \
             patch.object(load_app, "_chat_image_state", {}), \
             patch("httpx.Client") as mock_http_client:
            
            mock_s3_key.get.return_value = "test_image.jpg"
            mock_chat_id.get.return_value = "chat_123"
            
            mock_client = MagicMock()
            mock_http_client.return_value.__enter__.return_value = mock_client
            
            mock_response = MagicMock()
            mock_response.json.return_value = mock_yolo_response
            mock_response.raise_for_status.return_value = None
            
            mock_image_response = MagicMock()
            mock_image_response.content = b"fake_image_data"
            mock_image_response.raise_for_status.return_value = None
            
            mock_client.post.return_value = mock_response
            mock_client.get.side_effect = [mock_image_response, mock_response]
            
            result = load_app.detect_objects.invoke({})
            
            # Verify bbox format for LLM reasoning
            assert "left=" in result  # x1
            assert "top=" in result   # y1
            assert "right=" in result  # x2
            assert "bottom=" in result  # y2
            assert "center_x=" in result
            
            # Verify values are in result
            assert "100.0" in result or "100" in result  # left
            assert "150.0" in result or "150" in result  # top
            assert "250.0" in result or "250" in result  # right
            assert "400.0" in result or "400" in result  # bottom
    
    def test_detect_objects_caches_detections(self, load_app):
        """Detections are stored in persistent state for multi-turn sessions."""
        mock_yolo_response = {
            "prediction_uid": "pred_123",
            "detection_objects": [
                {
                    "label": "person",
                    "box": json.dumps([10.0, 20.0, 150.0, 300.0]),
                    "score": 0.95
                }
            ]
        }
        
        with patch.object(load_app, "_current_image_s3_key") as mock_s3_key, \
             patch.object(load_app, "_current_chat_id") as mock_chat_id, \
             patch.object(load_app, "_current_detections") as mock_detections, \
             patch.object(load_app, "_chat_image_state", {"chat_123": {"detections": []}}), \
             patch("httpx.Client") as mock_http_client:
            
            mock_s3_key.get.return_value = "test_image.jpg"
            mock_chat_id.get.return_value = "chat_123"
            
            mock_client = MagicMock()
            mock_http_client.return_value.__enter__.return_value = mock_client
            
            mock_response = MagicMock()
            mock_response.json.return_value = mock_yolo_response
            mock_response.raise_for_status.return_value = None
            
            mock_image_response = MagicMock()
            mock_image_response.content = b"fake_image_data"
            mock_image_response.raise_for_status.return_value = None
            
            mock_client.post.return_value = mock_response
            mock_client.get.side_effect = [mock_image_response, mock_response]
            
            load_app.detect_objects.invoke({})
            
            # Verify ContextVar was set
            mock_detections.set.assert_called()
