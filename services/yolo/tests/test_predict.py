import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app import app


class TestPredict(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("app.Image")   # prevent PIL from processing a fake frame
    @patch("app.model")   # prevent the real YOLO model from running
    def test_predict(self, mock_model, mock_image):
        fake_result = MagicMock()
        fake_result.boxes = []   # no detections - keeps the test simple
        mock_model.return_value = [fake_result]
        mock_model.names = {}

        with open("tests/data/beatles.jpeg", "rb") as f:
            response = self.client.post("/predict", files={"file": f})

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["detection_count"], 0)
        self.assertEqual(body["labels"], [])
        self.assertIn("prediction_uid", body)