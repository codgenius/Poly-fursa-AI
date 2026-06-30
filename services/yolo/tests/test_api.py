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


def test_predict_json_body_missing_params(client):
    """Test /predict endpoint with JSON body missing required parameters"""
    response = client.post(
        "/predict",
        json={"image_s3_key": "some-key"}  # Missing chat_id and prediction_id
    )
    # Should fail because image_s3_key isn't a real S3 file
    assert response.status_code == 400


def test_predict_json_body_invalid_json(client):
    """Test /predict endpoint with invalid JSON body"""
    response = client.post(
        "/predict",
        content=b"not valid json",
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400
    assert "Invalid JSON body" in response.json()["detail"]


def test_predict_no_input_provided(client):
    """Test /predict endpoint with neither file nor JSON body"""
    response = client.post("/predict")
    assert response.status_code == 400
    assert "Either 'image_s3_key' or 'file' must be provided" in response.json()["detail"]

