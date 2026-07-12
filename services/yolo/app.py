from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends
from fastapi.responses import FileResponse, Response
from prometheus_fastapi_instrumentator import Instrumentator
from ultralytics import YOLO
from PIL import Image
from sqlalchemy.orm import Session
import logging
import os
import uuid
import shutil
import time
import signal
import threading
import sys
import io
from pydantic import BaseModel
from typing import List, Optional
from typing import List, Optional

from models import PredictionSession, DetectionObject
from db import init_db, get_db
from s3_utils import download_image_from_s3, upload_image_to_s3
from dotenv import load_dotenv
load_dotenv()

is_shutting_down = False

def delayed_exit():
    logging.info("Cleanup started. Waiting before exit...")
    time.sleep(10)
    logging.info("Cleanup done. Exiting.")
    os._exit(0)

def handle_sigterm(signum, frame):
    global is_shutting_down
    is_shutting_down = True
    logging.info("Received SIGTERM. Shutting down gracefully...")
    logging.info("Cleanup started. Waiting before exit...")
    time.sleep(10)
    logging.info("Cleanup done. Exiting.")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Disable GPU usage
import torch
torch.cuda.is_available = lambda: False

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Initialize database tables on application startup."""
    init_db()
    logging.info("Database initialized - tables created")
    yield
    logging.info("Application shutting down")

app = FastAPI(lifespan=lifespan)

# Expose /metrics endpoint with default process metrics + FastAPI HTTP metrics
Instrumentator().instrument(app).expose(app)

# Confidence threshold for object detection (0.0 - 1.0).
# Detections below this score are discarded.
# Override with: export CONFIDENCE_THRESHOLD=0.7
_raw_threshold = os.environ.get("CONFIDENCE_THRESHOLD")
if _raw_threshold is not None:
    CONFIDENCE_THRESHOLD = float(_raw_threshold)
    logging.info(f"CONFIDENCE_THRESHOLD set to {CONFIDENCE_THRESHOLD} (from environment)")
else:
    CONFIDENCE_THRESHOLD = 0.5
    logging.info(f"CONFIDENCE_THRESHOLD not set, using default: {CONFIDENCE_THRESHOLD}")

UPLOAD_DIR = "uploads/original"
PREDICTED_DIR = "uploads/predicted"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PREDICTED_DIR, exist_ok=True)

# Download the AI model (tiny model ~6MB)
model = YOLO("yolov8n.pt")

class PredictResponse(BaseModel):
    prediction_uid: str
    detection_count: int
    labels: List[str]
    time_took: float


class PredictRequest(BaseModel):
    """Request model for S3-based image prediction"""
    image_s3_key: str
    chat_id: str
    prediction_id: str


@app.post("/predict", response_model=PredictResponse)
async def predict(
    request: Request,
    file: Optional[UploadFile] = File(None), 
    db: Session = Depends(get_db)
):
    """
    Predict objects in an image.
    Supports both file upload (legacy) and S3-based image retrieval.
    
    For S3-based: send JSON body with image_s3_key, chat_id, and prediction_id
    For file upload: send file as multipart/form-data
    """
    start_time = time.time()
    
    image_s3_key = None
    chat_id = None
    prediction_id = None
    
    # Handle JSON body for S3-based prediction
    if request.headers.get("content-type") == "application/json":
        try:
            body = await request.json()
            image_s3_key = body.get("image_s3_key")
            chat_id = body.get("chat_id")
            prediction_id = body.get("prediction_id")
        except Exception as e:
            logging.error(f"Failed to parse JSON body: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    # Determine image source and get image bytes
    if image_s3_key:
        # S3-based prediction
        try:
            image_bytes = download_image_from_s3(image_s3_key)
            uid = prediction_id
            ext = ".jpg"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to download image from S3: {str(e)}")
    elif file:
        # Legacy file upload
        if file.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
            raise HTTPException(status_code=400, detail="Only image files are supported")
        ext = os.path.splitext(file.filename)[1]
        uid = str(uuid.uuid4())
        image_bytes = file.file.read()
    else:
        raise HTTPException(status_code=400, detail="Either 'image_s3_key' or 'file' must be provided")

    # Save original image locally for processing
    original_path = os.path.join(UPLOAD_DIR, uid + ext)
    predicted_path = os.path.join(PREDICTED_DIR, uid + ext)

    with open(original_path, "wb") as f:
        f.write(image_bytes)

    # Run prediction
    results = model(original_path, device="cpu", conf=CONFIDENCE_THRESHOLD)

    # Generate annotated image
    annotated_frame = results[0].plot()  # NumPy image with boxes
    annotated_image = Image.fromarray(annotated_frame)
    annotated_image.save(predicted_path)

    # Convert annotated image to bytes for S3 upload if using S3
    if image_s3_key:
        with open(predicted_path, "rb") as f:
            predicted_image_bytes = f.read()
        try:
            upload_image_to_s3(
                image_bytes=predicted_image_bytes,
                chat_id=chat_id,
                prediction_id=prediction_id,
                image_type="predicted"
            )
        except Exception as e:
            logging.error(f"Failed to upload predicted image to S3: {e}")
            # Continue anyway - we still have local storage

    # Save prediction session to database
    prediction_session = PredictionSession(
        uid=uid,
        original_image=original_path,
        predicted_image=predicted_path
    )
    db.add(prediction_session)
    db.commit()
    
    detected_labels = []
    for box in results[0].boxes:
        label_idx = int(box.cls[0].item())
        label = model.names[label_idx]
        score = float(box.conf[0])
        bbox = box.xyxy[0].tolist()
        
        # Save detection object using SQLAlchemy
        detection = DetectionObject(
            prediction_uid=uid,
            label=label,
            score=score,
            box=str(bbox)
        )
        db.add(detection)
        detected_labels.append(label)
    
    db.commit()
    processing_time = round(time.time() - start_time, 2)
    return {
        "prediction_uid": uid, 
        "detection_count": len(results[0].boxes),
        "labels": detected_labels,
        "time_took": processing_time
    }

@app.get("/prediction/{uid}")
def get_prediction_by_uid(uid: str, db: Session = Depends(get_db)):
    """
    Get prediction session by uid with all detected objects
    """
    session = db.query(PredictionSession).filter_by(uid=uid).first()
    if not session:
        raise HTTPException(status_code=404, detail="Prediction not found")
    
    objects = db.query(DetectionObject).filter_by(prediction_uid=uid).all()
    
    return {
        "uid": session.uid,
        "timestamp": session.timestamp,
        "original_image": session.original_image,
        "predicted_image": session.predicted_image,
        "detection_objects": [
            {
                "id": obj.id,
                "label": obj.label,
                "score": obj.score,
                "box": obj.box
            } for obj in objects
        ]
    }


@app.get("/prediction/{uid}/image")
def get_prediction_image(uid: str, db: Session = Depends(get_db)):
    """
    Return the annotated (bounding-box) image for a prediction
    """
    session = db.query(PredictionSession).filter_by(uid=uid).first()
    if not session or not os.path.exists(session.predicted_image):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(session.predicted_image)


@app.get("/predictions/label/{label}")
def get_predictions_by_label(label: str, db: Session = Depends(get_db)):
    """
    Get all prediction sessions that detected a given label
    """
    if not label:
        raise HTTPException(status_code=400, detail="Label cannot be empty")
    
    # Get distinct prediction sessions that contain the label
    sessions = db.query(PredictionSession).join(
        DetectionObject, PredictionSession.uid == DetectionObject.prediction_uid
    ).filter(DetectionObject.label == label).distinct().all()
    
    result = []
    for session in sessions:
        objects = db.query(DetectionObject).filter(
            DetectionObject.prediction_uid == session.uid,
            DetectionObject.label == label
        ).all()
        result.append({
            "uid": session.uid,
            "timestamp": session.timestamp,
            "original_image": session.original_image,
            "predicted_image": session.predicted_image,
            "detection_objects": [
                {
                    "id": obj.id,
                    "label": obj.label,
                    "score": obj.score,
                    "box": obj.box
                } for obj in objects
            ]
        })
    return result


@app.get("/predictions/score/{min_score}")
def get_predictions_by_score(min_score: float, db: Session = Depends(get_db)):
    """
    Get all detection objects with confidence score >= min_score
    """
    if min_score < 0.0 or min_score > 1.0:
        raise HTTPException(status_code=400, detail="min_score must be between 0.0 and 1.0")
    
    objects = db.query(DetectionObject).filter(DetectionObject.score >= min_score).all()
    
    return [
        {
            "id": obj.id,
            "prediction_uid": obj.prediction_uid,
            "label": obj.label,
            "score": obj.score,
            "box": obj.box
        } for obj in objects
    ]

@app.get("/health")
def health():
    """
    Health check endpoint
    """
    return {"status": "ok"}

@app.get("/ready")
def ready():
    if is_shutting_down:
        raise HTTPException(status_code=503, detail="Service is shutting down")
    return {"status": "ready"}

@app.get("/hello")
def hello():
    return{"status": "hello there"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

