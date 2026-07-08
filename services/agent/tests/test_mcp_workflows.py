"""
Test agent tool MCP workflows.

Verifies that blur_object and add_noise_object use MCPClient tools
in the correct sequence: crop → process → paste_region.

These are simplified tests that verify the tool implementations work
correctly when provided with mocked MCPClient and context.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock


class TestBlurObjectWorkflow:
    """Test blur_object MCP workflow."""
    
    def test_blur_object_uses_mcp_crop_blur_paste(self):
        """blur_object delegates to MCP: crop → blur → paste_region."""
        # This test verifies the tool uses MCPClient correctly
        # by checking that all three methods are called
        
        with patch('app.MCPClient') as MockMCP, \
             patch('app._current_image_b64') as img_var, \
             patch('app._current_detections') as det_var, \
             patch('app._update_image_and_respond') as respond, \
             patch('app._validate_and_get_detection') as validate:
            
            # Setup mocks
            img_var.get.return_value = "full_image_b64"
            det_var.get.return_value = [{"bbox": [10, 20, 30, 40], "label": "obj"}]
            validate.return_value = ({"bbox": [10, 20, 30, 40], "label": "obj"}, "obj")
            
            client = MagicMock()
            MockMCP.return_value = client
            client.crop.return_value = "region_b64"
            client.blur.return_value = "blurred_b64"
            client.paste_region.return_value = "final_b64"
            
            # Access the underlying function via the tool's func attribute
            from app import blur_object
            func = blur_object.func if hasattr(blur_object, 'func') else blur_object
            
            result = func(0, 2.0)
            
            # Verify all three MCP calls were made
            client.crop.assert_called_once()
            client.blur.assert_called_once()
            client.paste_region.assert_called_once()


class TestAddNoiseObjectWorkflow:
    """Test add_noise_object MCP workflow."""
    
    def test_add_noise_object_uses_mcp_crop_noise_paste(self):
        """add_noise_object delegates to MCP: crop → add_noise → paste_region."""
        
        with patch('app.MCPClient') as MockMCP, \
             patch('app._current_image_b64') as img_var, \
             patch('app._current_detections') as det_var, \
             patch('app._update_image_and_respond') as respond, \
             patch('app._validate_and_get_detection') as validate:
            
            # Setup mocks
            img_var.get.return_value = "full_image_b64"
            det_var.get.return_value = [{"bbox": [50, 60, 70, 80], "label": "obj"}]
            validate.return_value = ({"bbox": [50, 60, 70, 80], "label": "obj"}, "obj")
            
            client = MagicMock()
            MockMCP.return_value = client
            client.crop.return_value = "region_b64"
            client.add_noise.return_value = "noisy_b64"
            client.paste_region.return_value = "final_b64"
            
            # Access the underlying function
            from app import add_noise_object
            func = add_noise_object.func if hasattr(add_noise_object, 'func') else add_noise_object
            
            result = func(0, 0.3)
            
            # Verify all three MCP calls were made in sequence
            client.crop.assert_called_once()
            client.add_noise.assert_called_once()
            client.paste_region.assert_called_once()


class TestMCPCallSequence:
    """Test that MCP calls happen in correct order."""
    
    def test_blur_object_crop_before_blur(self):
        """Verify crop is called before blur."""
        with patch('app.MCPClient') as MockMCP, \
             patch('app._current_image_b64') as img_var, \
             patch('app._validate_and_get_detection') as validate, \
             patch('app._update_image_and_respond'):
            
            img_var.get.return_value = "image_b64"
            validate.return_value = ({"bbox": [0, 0, 10, 10], "label": "obj"}, "obj")
            
            client = MagicMock()
            MockMCP.return_value = client
            client.crop.return_value = "cropped_b64"
            client.blur.return_value = "blurred_b64"
            client.paste_region.return_value = "final_b64"
            
            from app import blur_object
            func = blur_object.func if hasattr(blur_object, 'func') else blur_object
            func(0, 2.0)
            
            # Get call order from mock
            assert client.crop.call_count >= 1
            assert client.blur.call_count >= 1
            # Verify crop was called with image_b64, blur with cropped result
            crop_call = client.crop.call_args
            blur_call = client.blur.call_args
            
            assert crop_call[0][0] == "image_b64"  # First arg to crop
            assert blur_call[0][0] == "cropped_b64"  # First arg to blur


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
