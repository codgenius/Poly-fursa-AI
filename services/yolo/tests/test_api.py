"""
Basic API health check and error handling tests
"""


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_predict_invalid_content_type(client):
    """Test /predict endpoint rejects non-image file types"""
    test_file = ("test.txt", b"This is not an image", "text/plain")
    response = client.post("/predict", files={"file": test_file})
    assert response.status_code == 400
    assert "Only image files are supported" in response.json()["detail"]


