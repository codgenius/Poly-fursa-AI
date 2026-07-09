"""
Tests for natural-language object reference resolution (Phase 3).

Tests the _preprocess_reference and _parse_object_reference helpers
used by the resolve_object_reference LangChain tool.
"""

import pytest
import sys
from unittest.mock import patch

# Import from app.py
sys.path.insert(0, '/home/hadikhier/Poly-fursa-AI/services/agent')
from app import _preprocess_reference, _parse_object_reference


# Mock detections for testing
MOCK_DETECTIONS_3_DOGS = [
    {"id": 0, "label": "dog", "bbox": (10, 20, 50, 60), "confidence": 0.95},
    {"id": 1, "label": "dog", "bbox": (100, 30, 150, 80), "confidence": 0.92},
    {"id": 2, "label": "dog", "bbox": (200, 40, 250, 90), "confidence": 0.88},
]

MOCK_DETECTIONS_MIXED = [
    {"id": 0, "label": "person", "bbox": (10, 20, 50, 100), "confidence": 0.98},
    {"id": 1, "label": "dog", "bbox": (100, 30, 150, 80), "confidence": 0.92},
    {"id": 2, "label": "person", "bbox": (200, 40, 250, 120), "confidence": 0.95},
    {"id": 3, "label": "car", "bbox": (300, 50, 450, 150), "confidence": 0.89},
]

MOCK_DETECTIONS_SINGLE_DOG = [
    {"id": 0, "label": "dog", "bbox": (100, 30, 150, 80), "confidence": 0.92},
]


class TestPreprocessReference:
    """Test _preprocess_reference action verb stripping."""

    def test_strip_blur_action(self):
        """Test stripping 'blur' action."""
        result = _preprocess_reference("blur the second person from the right")
        assert result == "second person from the right"

    def test_strip_crop_action(self):
        """Test stripping 'crop' action (also strips 'the')."""
        result = _preprocess_reference("crop the dog")
        assert result == "dog"

    def test_strip_add_noise_action(self):
        """Test stripping 'add noise to' action (also strips 'the')."""
        result = _preprocess_reference("add noise to the car")
        assert result == "car"

    def test_strip_add_salt_pepper_action(self):
        """Test stripping 'add salt and pepper noise to' action."""
        result = _preprocess_reference("add salt and pepper noise to leftmost person")
        assert result == "leftmost person"

    def test_strip_can_you_prefix(self):
        """Test stripping 'can you' prefix."""
        result = _preprocess_reference("can you blur the dog")
        assert result == "dog"

    def test_strip_could_you_prefix(self):
        """Test stripping 'could you' prefix."""
        result = _preprocess_reference("could you crop the car")
        assert result == "car"

    def test_strip_please_prefix(self):
        """Test stripping 'please' prefix."""
        result = _preprocess_reference("please add noise to the person")
        assert result == "person"

    def test_no_action_verb_unchanged(self):
        """Test that reference without action verb is unchanged."""
        result = _preprocess_reference("second dog from the right")
        assert result == "second dog from the right"

    def test_the_already_removed_after_action(self):
        """Test that 'the' after action is also removed."""
        result = _preprocess_reference("blur the leftmost car")
        assert result == "leftmost car"


class TestDirectIndex:
    """Test Pattern 1: Direct object index."""

    def test_object_0_valid(self):
        """Test 'object 0' returns first detection."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_3_DOGS
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("object 0")
        assert result["success"] is True
        assert result["object_id"] == 0
        assert result["label"] == "dog"

    def test_object_2_valid(self):
        """Test 'object 2' returns third detection."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_3_DOGS
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("object 2")
        assert result["success"] is True
        assert result["object_id"] == 2

    def test_object_out_of_range(self):
        """Test 'object 99' out of range returns error."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_3_DOGS
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("object 99")
        assert result["success"] is False
        assert "out of range" in result["error"]


class TestLabelMatching:
    """Test Pattern 2: Exact label matching."""

    def test_the_label_single_match(self):
        """Test 'the dog' with one dog returns that dog."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_SINGLE_DOG
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("the dog")
        assert result["success"] is True
        assert result["object_id"] == 0
        assert result["label"] == "dog"

    def test_detected_label_single_match(self):
        """Test 'detected car' with one car returns that car."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_MIXED
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("detected car")
        assert result["success"] is True
        assert result["label"] == "car"

    def test_label_not_found(self):
        """Test 'the zebra' when no zebra detected returns error."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_3_DOGS
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("the zebra")
        assert result["success"] is False
        assert "No 'zebra' detected" in result["error"]

    def test_label_ambiguous_error(self):
        """Test 'the dog' with 3 dogs returns ambiguous error."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_3_DOGS
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("the dog")
        assert result["success"] is False
        assert "Found 3 'dog' objects" in result["error"]


class TestOrdinalPosition:
    """Test Pattern 3: Ordinal position with direction."""

    def test_first_dog_from_left(self):
        """Test 'first dog from left' returns leftmost dog."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_3_DOGS
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("first dog from left")
        assert result["success"] is True
        assert result["object_id"] == 0

    def test_first_dog_from_the_left(self):
        """Test 'first dog from the left' with article."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_3_DOGS
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("first dog from the left")
        assert result["success"] is True
        assert result["object_id"] == 0

    def test_second_dog_from_right(self):
        """Test 'second dog from right' returns second from rightmost."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_3_DOGS
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("second dog from right")
        assert result["success"] is True
        assert result["object_id"] == 1

    def test_second_dog_from_the_right(self):
        """Test 'second dog from the right' with article."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_3_DOGS
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("second dog from the right")
        assert result["success"] is True
        assert result["object_id"] == 1

    def test_second_person_no_direction_defaults_left(self):
        """Test 'second person' with no direction defaults to left-to-right."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_MIXED
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("second person")
        assert result["success"] is True
        assert result["object_id"] == 2


class TestExtremePositions:
    """Test Pattern 4: Leftmost/rightmost and variations."""

    def test_leftmost_person(self):
        """Test 'leftmost person' returns person with smallest bbox[0]."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_MIXED
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("leftmost person")
        assert result["success"] is True
        assert result["object_id"] == 0

    def test_rightmost_car(self):
        """Test 'rightmost car' returns car with largest bbox[2]."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_MIXED
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("rightmost car")
        assert result["success"] is True
        assert result["object_id"] == 3

    def test_left_person_maps_to_leftmost(self):
        """Test 'left person' maps to leftmost person."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_MIXED
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("left person")
        assert result["success"] is True
        assert result["object_id"] == 0

    def test_right_car_maps_to_rightmost(self):
        """Test 'right car' maps to rightmost car."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_MIXED
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("right car")
        assert result["success"] is True
        assert result["object_id"] == 3

    def test_person_on_the_left(self):
        """Test 'person on the left' maps to leftmost person."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_MIXED
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("person on the left")
        assert result["success"] is True
        assert result["object_id"] == 0

    def test_car_on_the_right(self):
        """Test 'car on the right' maps to rightmost car."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_MIXED
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("car on the right")
        assert result["success"] is True
        assert result["object_id"] == 3


class TestMiddlePosition:
    """Test Pattern 5: Middle position."""

    def test_middle_dog_median_position(self):
        """Test 'middle dog' returns dog at median position."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_3_DOGS
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("middle dog")
        assert result["success"] is True
        assert result["object_id"] == 1


class TestErrorHandling:
    """Test error cases."""

    def test_no_detections_error(self):
        """Test error when no detections available."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = []
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("first dog")
        assert result["success"] is False
        assert "No detections available" in result["error"]

    def test_unparseable_reference(self):
        """Test error for unparseable reference."""
        with patch('app._current_detections') as mock_detections, \
             patch('app._current_chat_id') as mock_chat_id, \
             patch('app._chat_image_state', {}):
            mock_detections.get.return_value = MOCK_DETECTIONS_3_DOGS
            mock_chat_id.get.return_value = "test-chat-1"
            result = _parse_object_reference("xyzzy qwerty")
        assert result["success"] is False
        assert "Could not parse reference" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
