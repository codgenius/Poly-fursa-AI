import os
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app import app


def test_predict(client):
    """Test the /predict endpoint with mocked YOLO model"""
    with patch("app.Image") as mock_image, \
         patch("app.model") as mock_model:
        
        # Setup mocks
        fake_result = MagicMock()
        fake_result.boxes = []   # no detections - keeps the test simple
        mock_model.return_value = [fake_result]
        mock_model.names = {}

        with open("tests/data/beatles.jpeg", "rb") as f:
            response = client.post("/predict", files={"file": f})

        body = response.json()
        assert response.status_code == 200
        assert body["detection_count"] == 0
        assert body["labels"] == []
        assert "prediction_uid" in body