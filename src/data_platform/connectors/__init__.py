"""Connectors package – adapters to external storage backends."""

from data_platform.connectors.base import BaseConnector
from data_platform.connectors.database import DatabaseConnector
from data_platform.connectors.object_storage import ObjectStorageConnector
from data_platform.connectors.warehouse import WarehouseConnector

__all__ = [
    "BaseConnector",
    "DatabaseConnector",
    "ObjectStorageConnector",
    "WarehouseConnector",
]
