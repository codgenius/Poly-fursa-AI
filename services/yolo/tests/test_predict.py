import tempfile
from unittest.mock import MagicMock, patch
import pytest


@patch("app.Image")   # prevent PIL from processing a fake frame
@patch("app.model")   # prevent the real YOLO model from running
def test_predict(mock_model, mock_image, client):
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
