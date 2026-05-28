"""S3/MinIO utility functions."""

import logging
from typing import Optional, Dict

import boto3
from botocore.exceptions import ClientError

from api.settings import settings

logger = logging.getLogger(__name__)

# Initialize S3 client
s3_client = boto3.client(
    "s3",
    endpoint_url=settings.s3_endpoint_url,
    aws_access_key_id=settings.s3_access_key,
    aws_secret_access_key=settings.s3_secret_key,
    region_name=settings.s3_region,
)


def s3_put_object(
    key: str,
    body: bytes,
    bucket: str = "anpr",
    metadata: Optional[Dict[str, str]] = None,
    content_type: str = "application/octet-stream",
) -> bool:
    """Upload object to S3/MinIO."""
    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            Metadata=metadata or {},
        )
        logger.debug(f"Uploaded {key} to {bucket}")
        return True
    except ClientError as e:
        logger.error(f"Failed to upload {key}: {e}")
        return False


def s3_delete_object(
    key: str,
    bucket: str = "anpr",
) -> bool:
    """Delete object from S3/MinIO."""
    try:
        s3_client.delete_object(Bucket=bucket, Key=key)
        logger.debug(f"Deleted {key} from {bucket}")
        return True
    except ClientError as e:
        logger.error(f"Failed to delete {key}: {e}")
        return False


def s3_get_object(
    key: str,
    bucket: str = "anpr",
) -> Optional[bytes]:
    """Retrieve object from S3/MinIO."""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            logger.warning(f"Object not found: {key}")
        else:
            logger.error(f"Failed to download {key}: {e}")
        return None
