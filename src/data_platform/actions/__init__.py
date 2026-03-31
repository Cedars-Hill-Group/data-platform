"""Action tools for the data platform.

This package provides higher-level action tools that operate on the
Knowledge Base, including metadata sanitization and classification.

Modules
-------
sanitize_company
    Walk company markdown files and normalize metadata using LLM calls.
llm_client
    Thin wrapper around the OpenAI API used by the action tools.
"""

from __future__ import annotations
