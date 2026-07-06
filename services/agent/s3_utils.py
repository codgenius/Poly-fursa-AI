import os
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def upload_image_to_s3(
    image_bytes: bytes, 
    chat_id: str, 
    prediction_id: str, 
    original_filename: str
) -> str:
    """
    Upload an image to S3 and return the object key.
    
    Args:
        image_bytes: Image binary data
        chat_id: Chat session ID
        prediction_id: Prediction ID
        original_filename: Original filename to preserve extension
    
    Returns:
        S3 object key (path)
    """
    aws_region = os.environ.get("AWS_REGION", "us-east-1")
    aws_bucket = os.environ.get("AWS_S3_BUCKET")
    
    if not aws_bucket:
        raise ValueError(
            "AWS_S3_BUCKET environment variable must be set to use S3 image storage."
        )
    
    # Extract file extension
    _, ext = os.path.splitext(original_filename)
    if not ext:
        ext = ".jpg"
    
    # Construct S3 key: chat_id/prediction_id/original/filename
    s3_key = f"{chat_id}/{prediction_id}/original/{prediction_id}{ext}"
    
    try:
        s3_client = boto3.client("s3", region_name=aws_region)
        s3_client.put_object(
            Bucket=aws_bucket,
            Key=s3_key,
            Body=image_bytes,
            ContentType="image/jpeg" if ext.lower() in [".jpg", ".jpeg"] else "image/png"
        )
        logger.info(f"Uploaded image to S3: s3://{aws_bucket}/{s3_key}")
        return s3_key
    except ClientError as e:
        logger.error(f"Failed to upload image to S3: {e}")
        raise


def download_image_from_s3(s3_key: str) -> bytes:
    """
    Download an image from S3 and return the binary data.
    
    Args:
        s3_key: S3 object key (path)
    
    Returns:
        Image binary data
    """
    aws_region = os.environ.get("AWS_REGION", "us-east-1")
    aws_bucket = os.environ.get("AWS_S3_BUCKET")
    
    if not aws_bucket:
        raise ValueError(
            "AWS_S3_BUCKET environment variable must be set to use S3 image storage."
        )
    
    try:
        s3_client = boto3.client("s3", region_name=aws_region)
        response = s3_client.get_object(Bucket=aws_bucket, Key=s3_key)
        image_bytes = response["Body"].read()
        logger.info(f"Downloaded image from S3: s3://{aws_bucket}/{s3_key}")
        return image_bytes
    except ClientError as e:
        logger.error(f"Failed to download image from S3: {e}")
        raise

