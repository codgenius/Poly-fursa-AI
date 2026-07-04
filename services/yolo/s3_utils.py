import os
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def download_image_from_s3(s3_key: str) -> bytes:
    """
    Download an image from S3.
    
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
        return response["Body"].read()
    except ClientError as e:
        logger.error(f"Failed to download image from S3: {e}")
        raise


def upload_image_to_s3(
    image_bytes: bytes, 
    chat_id: str, 
    prediction_id: str, 
    image_type: str = "predicted"
) -> str:
    """
    Upload an image to S3 and return the object key.
    
    Args:
        image_bytes: Image binary data
        chat_id: Chat session ID
        prediction_id: Prediction ID
        image_type: Type of image ('original' or 'predicted')
    
    Returns:
        S3 object key (path)
    """
    aws_region = os.environ.get("AWS_REGION", "us-east-1")
    aws_bucket = os.environ.get("AWS_S3_BUCKET")
    
    if not aws_bucket:
        raise ValueError(
            "AWS_S3_BUCKET environment variable must be set to use S3 image storage."
        )
    
    # Construct S3 key: chat_id/prediction_id/predicted/filename
    s3_key = f"{chat_id}/{prediction_id}/{image_type}/{prediction_id}.jpg"
    
    try:
        s3_client = boto3.client("s3", region_name=aws_region)
        s3_client.put_object(
            Bucket=aws_bucket,
            Key=s3_key,
            Body=image_bytes,
            ContentType="image/jpeg"
        )
        logger.info(f"Uploaded {image_type} image to S3: s3://{aws_bucket}/{s3_key}")
        return s3_key
    except ClientError as e:
        logger.error(f"Failed to upload image to S3: {e}")
        raise

