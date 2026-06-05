import os
import unittest
import tempfile
from fastapi.testclient import TestClient
import app as app_module
from app import app, init_db


class TestPrecictByLabel(unittest.TestCase):
    def setup(self):
        _, app_module.DB_PATH = tempfile.mkstemp(suffix=".db")
        init_db()
        self.client = TestClient(app)
    
    @patch("app.Image")   # prevent PIL from processing a fake frame
    @patch("app.model")
    def test_predict_by_label(self, mock_model, mock_image):
        fake_result = MagicMock()
        fake_result.boxes = []   # no detections - keeps the test simple
        mock_model.return_value = [fake_result]
        mock_model.names = {}
        

        with open("tests/data/beatles.jpeg", "rb") as f:
            response = self.client.post("/predictions/{"car"}", files={"file": f})

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["detection_count"], 0)
        self.assertEqual(body["labels"], [])
        self.assertIn("prediction_uid", body)
