"""
S3 client wrapper.
- Local dev: points to LocalStack (S3_ENDPOINT=http://localstack:4566)
- Production: standard boto3 with IAM role (no endpoint override)
"""
import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

S3_BUCKET    = os.getenv("S3_BUCKET", "robotops-firmware-local")
S3_ENDPOINT  = os.getenv("S3_ENDPOINT")          # None in production
AWS_REGION   = os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1")


def _client():
    kwargs: dict = {"region_name": AWS_REGION}
    if S3_ENDPOINT:
        # LocalStack: dummy credentials required
        kwargs["endpoint_url"]          = S3_ENDPOINT
        kwargs["aws_access_key_id"]     = "test"
        kwargs["aws_secret_access_key"] = "test"
    return boto3.client("s3", **kwargs)


def ensure_bucket() -> None:
    """Create the firmware bucket if it does not exist (idempotent)."""
    client = _client()
    try:
        client.head_bucket(Bucket=S3_BUCKET)
        logger.info("S3 bucket '%s' already exists", S3_BUCKET)
    except ClientError:
        client.create_bucket(
            Bucket=S3_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
        )
        logger.info("S3 bucket '%s' created", S3_BUCKET)


def upload(key: str, content: bytes, content_type: str = "application/json") -> None:
    _client().put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=content,
        ContentType=content_type,
    )
    logger.info("S3 uploaded s3://%s/%s (%d bytes)", S3_BUCKET, key, len(content))


def download(key: str) -> bytes:
    resp = _client().get_object(Bucket=S3_BUCKET, Key=key)
    data = resp["Body"].read()
    logger.info("S3 downloaded s3://%s/%s (%d bytes)", S3_BUCKET, key, len(data))
    return data
