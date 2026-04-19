"""Thin OpenAI API wrapper used by data-platform action tools.

Usage::

    from data_platform.actions.llm_client import LLMClient

    client = LLMClient(api_key="sk-...")
    response = client.chat(
        system="You are a classification analyst.",
        user="Classify this company ...",
    )
"""

from __future__ import annotations

import os
from importlib import import_module
from typing import Any

from data_platform.log import get_logger

logger = get_logger(__name__)

_dotenv = import_module("dotenv")

try:
    import openai as _openai

    _OPENAI_AVAILABLE = True
except ImportError:  # pragma: no cover
    _openai = None  # type: ignore[assignment]
    _OPENAI_AVAILABLE = False

_DEFAULT_MODEL = "gpt-4o-mini"


_MISSING_API_KEY_MSG = (
    "OpenAI API key is missing. Set OPENAI_API_KEY in your .env file, "
    "in your environment, or pass api_key=... when constructing LLMClient.\n\n"
    "PowerShell (current shell): $env:OPENAI_API_KEY = 'sk-...'\n"
    "PowerShell (persist for future shells): setx OPENAI_API_KEY 'sk-...'"
)


class LLMClient:
    """Thin wrapper around the OpenAI Chat Completions API.

    Parameters
    ----------
    api_key:
        OpenAI API key.  When *None* the ``OPENAI_API_KEY`` environment
        variable is used automatically by the underlying ``openai`` library.
    model:
        Model identifier passed to the Chat Completions endpoint.
        Defaults to ``"gpt-4o-mini"``.
    temperature:
        Sampling temperature (0 → deterministic).
    max_tokens:
        Maximum tokens in the completion response.
    **client_kwargs:
        Additional keyword arguments forwarded to
        :class:`openai.OpenAI` (e.g. ``timeout``, ``base_url``).

    Raises
    ------
    ImportError
        If the ``openai`` package is not installed.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        temperature: float = 0.0,
        max_tokens: int = 512,
        **client_kwargs: Any,
    ) -> None:
        if not _OPENAI_AVAILABLE:
            raise ImportError(
                "The 'openai' package is required to use LLMClient. "
                "Install it with: pip install openai"
            )
        _dotenv.load_dotenv(_dotenv.find_dotenv(usecwd=True), override=False)
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError(_MISSING_API_KEY_MSG)
        self._client = _openai.OpenAI(api_key=resolved_key, **client_kwargs)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(self, *, system: str, user: str) -> str:
        """Send a chat completion request and return the assistant message.

        Parameters
        ----------
        system:
            System-level prompt that sets the LLM's role.
        user:
            User-turn prompt containing the actual classification task.

        Returns
        -------
        str
            The raw text content of the first choice returned by the API.

        Raises
        ------
        openai.OpenAIError
            Propagated from the underlying API call on server/auth errors.
        """
        logger.debug("LLM chat request: model=%s, system_len=%d, user_len=%d",
                     self.model, len(system), len(user))

        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        content: str = response.choices[0].message.content or ""
        logger.debug("LLM chat response: %d chars", len(content))
        return content
