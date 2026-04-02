"""Tests for LLMClient credential resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from data_platform.actions import llm_client as llm_module


class _DummyOpenAIClient:
    """Minimal stub that captures kwargs passed to openai.OpenAI."""

    last_kwargs: dict[str, str] = {}

    def __init__(self, **kwargs):
        _DummyOpenAIClient.last_kwargs = kwargs


class _DummyOpenAI:
    OpenAI = _DummyOpenAIClient


def test_reads_api_key_from_dotenv(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test-dotenv\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _DummyOpenAIClient.last_kwargs = {}

    monkeypatch.setattr(llm_module, "_OPENAI_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "_openai", _DummyOpenAI)

    llm_module.LLMClient()

    assert _DummyOpenAIClient.last_kwargs["api_key"] == "sk-test-dotenv"


def test_explicit_api_key_wins_over_dotenv(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-from-dotenv\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _DummyOpenAIClient.last_kwargs = {}

    monkeypatch.setattr(llm_module, "_OPENAI_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "_openai", _DummyOpenAI)

    llm_module.LLMClient(api_key="sk-explicit")

    assert _DummyOpenAIClient.last_kwargs["api_key"] == "sk-explicit"


def test_raises_when_no_key_available(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    monkeypatch.setattr(llm_module, "_OPENAI_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "_openai", _DummyOpenAI)

    with pytest.raises(ValueError, match="OpenAI API key is missing"):
        llm_module.LLMClient()