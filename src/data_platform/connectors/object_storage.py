"""Object / blob storage connector.

Provides a uniform interface for reading and writing files to:
- Amazon S3  (requires ``boto3``)
- Google Cloud Storage (requires ``google-cloud-storage``)
- Azure Blob Storage  (requires ``azure-storage-blob``)
- Local filesystem    (no extra dependencies)

The ``type`` field in :class:`~data_platform.config.ObjectStorageConfig`
selects the backend.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from data_platform.config import ObjectStorageConfig
from data_platform.connectors.base import BaseConnector


class ObjectStorageConnector(BaseConnector):
    """Reads and writes binary objects to a configured storage backend.

    Parameters
    ----------
    config:
        Object storage configuration (type, bucket, prefix, etc.).
    """

    def __init__(self, config: ObjectStorageConfig) -> None:
        self._config = config
        self._client: Any = None
        self._connected = False

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    def connect(self) -> None:
        stype = self._config.type.lower()
        if stype == "s3":
            try:
                import boto3  # noqa: PLC0415

                self._client = boto3.client("s3", region_name=self._config.region)
            except ImportError as exc:
                raise ImportError("boto3 is required for S3 storage. Install it with: pip install boto3") from exc
        elif stype == "gcs":
            try:
                from google.cloud import storage  # noqa: PLC0415

                self._client = storage.Client()
            except ImportError as exc:
                raise ImportError(
                    "google-cloud-storage is required for GCS. "
                    "Install it with: pip install google-cloud-storage"
                ) from exc
        elif stype == "azure":
            try:
                from azure.storage.blob import BlobServiceClient  # noqa: PLC0415

                conn_str = self._config.metadata.get("connection_string", "")  # type: ignore[attr-defined]
                self._client = BlobServiceClient.from_connection_string(conn_str)
            except ImportError as exc:
                raise ImportError(
                    "azure-storage-blob is required for Azure. "
                    "Install it with: pip install azure-storage-blob"
                ) from exc
        elif stype in ("local", "none"):
            self._client = None
        else:
            raise ValueError(f"Unsupported object storage type: '{stype}'.")
        self._connected = True

    def disconnect(self) -> None:
        self._client = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def execute(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Not applicable for object storage; raises ``NotImplementedError``."""
        raise NotImplementedError("ObjectStorageConnector does not support query execution.")

    # ------------------------------------------------------------------
    # Object storage operations
    # ------------------------------------------------------------------

    def upload(self, local_path: Path, remote_key: str) -> None:
        """Upload a local file to the configured storage backend.

        Parameters
        ----------
        local_path:
            Path to the local file.
        remote_key:
            Destination key/path within the bucket or prefix.
        """
        if not self._connected:
            raise RuntimeError("Not connected.")
        stype = self._config.type.lower()
        full_key = self._full_key(remote_key)

        if stype == "s3":
            self._client.upload_file(str(local_path), self._config.bucket, full_key)
        elif stype == "gcs":
            bucket = self._client.bucket(self._config.bucket)
            blob = bucket.blob(full_key)
            blob.upload_from_filename(str(local_path))
        elif stype == "local":
            dest = self._local_root / full_key
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, dest)

    def download(self, remote_key: str, local_path: Path) -> None:
        """Download an object from storage to a local file.

        Parameters
        ----------
        remote_key:
            Source key/path within the bucket or prefix.
        local_path:
            Destination local path.
        """
        if not self._connected:
            raise RuntimeError("Not connected.")
        stype = self._config.type.lower()
        full_key = self._full_key(remote_key)

        local_path.parent.mkdir(parents=True, exist_ok=True)
        if stype == "s3":
            self._client.download_file(self._config.bucket, full_key, str(local_path))
        elif stype == "gcs":
            bucket = self._client.bucket(self._config.bucket)
            blob = bucket.blob(full_key)
            blob.download_to_filename(str(local_path))
        elif stype == "local":
            src = self._local_root / full_key
            shutil.copy2(src, local_path)

    def list_objects(self, prefix: str = "") -> list[str]:
        """Return object keys under the optional *prefix*.

        The returned keys are relative to the connector's configured prefix.
        """
        if not self._connected:
            raise RuntimeError("Not connected.")
        stype = self._config.type.lower()
        full_prefix = self._full_key(prefix)

        if stype == "s3":
            paginator = self._client.get_paginator("list_objects_v2")
            keys = []
            for page in paginator.paginate(Bucket=self._config.bucket, Prefix=full_prefix):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"][len(self._config.prefix):])
            return keys
        if stype == "gcs":
            bucket = self._client.bucket(self._config.bucket)
            return [
                blob.name[len(self._config.prefix):]
                for blob in bucket.list_blobs(prefix=full_prefix)
            ]
        if stype == "local":
            root = self._local_root / prefix
            if not root.exists():
                return []
            return [str(p.relative_to(self._local_root)) for p in root.rglob("*") if p.is_file()]
        return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _full_key(self, key: str) -> str:
        prefix = self._config.prefix.rstrip("/")
        return f"{prefix}/{key}" if prefix else key

    @property
    def _local_root(self) -> Path:
        if self._config.root_path is None:
            raise ValueError("root_path must be set for local storage backend.")
        return Path(self._config.root_path)
