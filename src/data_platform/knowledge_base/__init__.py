"""Knowledge Base package – markdown file reader, writer, and manager."""

from data_platform.knowledge_base.manager import KnowledgeBaseManager
from data_platform.knowledge_base.properties_catalog import (
    collect_property_catalog,
    emit_properties_json,
)
from data_platform.knowledge_base.reader import KnowledgeBaseReader
from data_platform.knowledge_base.writer import KnowledgeBaseWriter

__all__ = [
    "KnowledgeBaseManager",
    "KnowledgeBaseReader",
    "KnowledgeBaseWriter",
    "collect_property_catalog",
    "emit_properties_json",
]
