"""Knowledge Base package – markdown file reader and writer."""

from data_platform.knowledge_base.properties_catalog import (
    collect_property_catalog,
    emit_properties_json,
)
from data_platform.knowledge_base.reader import KnowledgeBaseReader
from data_platform.knowledge_base.writer import KnowledgeBaseWriter

__all__ = [
    "KnowledgeBaseReader",
    "KnowledgeBaseWriter",
    "collect_property_catalog",
    "emit_properties_json",
]
