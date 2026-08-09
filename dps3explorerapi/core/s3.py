"""
Shared S3 client factory — still boto3.client("s3") under the hood.

Primary switch (one variable):
  S3_ENDPOINT_URL empty  → real AWS (env keys or IAM credential chain)
  S3_ENDPOINT_URL set    → MinIO / LocalStack / any S3 API endpoint

When an endpoint is set and AWS keys are not provided, MinIO defaults
(minioadmin / minioadmin) are used so local mode does not require swapping keys.
"""

from __future__ import annotations

from typing import Optional

import boto3
from botocore.client import BaseClient, Config

from core.config import settings

_MINIO_DEFAULT_KEY = "minioadmin"
_MINIO_DEFAULT_SECRET = "minioadmin"


def get_s3_client(region_name: Optional[str] = None) -> BaseClient:
    """Return a boto3 S3 client. Optional region_name matches existing call sites."""
    kwargs: dict = {
        "service_name": "s3",
        "region_name": region_name or settings.AWS_DEFAULT_REGION,
    }
    endpoint = (settings.S3_ENDPOINT_URL or "").strip()
    if endpoint:
        # Path-style required for MinIO / custom endpoints inside Docker DNS.
        kwargs["endpoint_url"] = endpoint
        kwargs["config"] = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        )
        # Prefer explicit keys if set; otherwise MinIO defaults for local S3.
        access_key = (settings.AWS_ACCESS_KEY_ID or "").strip()
        secret_key = (settings.AWS_SECRET_ACCESS_KEY or "").strip()
        kwargs["aws_access_key_id"] = access_key or _MINIO_DEFAULT_KEY
        kwargs["aws_secret_access_key"] = secret_key or _MINIO_DEFAULT_SECRET
    # AWS mode: do not pass keys — boto3 uses env / shared config / IAM.
    return boto3.client(**kwargs)
