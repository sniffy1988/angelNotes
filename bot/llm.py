from __future__ import annotations

import logging
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

ChatRole = Literal["system", "user", "assistant"]
ChatMessage = dict[str, str]

MAX_CHAT_HISTORY = 16
MAX_RESPONSE_CHARS = 3500


class OllamaError(Exception):
    """Base error for Ollama client failures."""


class OllamaUnavailableError(OllamaError):
    """Ollama server is unreachable."""


class OllamaTimeoutError(OllamaError):
    """Ollama request timed out."""


class OllamaModelError(OllamaError):
    """Ollama returned an error (e.g. missing model)."""


def trim_history(messages: list[ChatMessage], limit: int = MAX_CHAT_HISTORY) -> list[ChatMessage]:
    if len(messages) <= limit:
        return list(messages)
    return list(messages[-limit:])


def append_turn(
    history: list[ChatMessage],
    user_text: str,
    assistant_text: str,
    *,
    limit: int = MAX_CHAT_HISTORY,
) -> list[ChatMessage]:
    updated = [*history, {"role": "user", "content": user_text}, {"role": "assistant", "content": assistant_text}]
    return trim_history(updated, limit)


def truncate_response(text: str, limit: int = MAX_RESPONSE_CHARS) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def parse_chat_response(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if not isinstance(message, dict):
        raise OllamaError("Unexpected Ollama response: missing message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise OllamaError("Unexpected Ollama response: empty content")
    return truncate_response(content)


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def open(self) -> None:
        self._client = httpx.AsyncClient(timeout=self.timeout)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("OllamaClient is not opened")
        return self._client

    async def chat(self, messages: list[ChatMessage]) -> str:
        url = f"{self.base_url}/api/chat"
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        try:
            response = await self.client.post(url, json=body)
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(str(exc)) from exc
        except httpx.RequestError as exc:
            raise OllamaUnavailableError(str(exc)) from exc

        if response.status_code >= 400:
            detail = response.text.strip() or f"HTTP {response.status_code}"
            logger.warning("Ollama error %s: %s", response.status_code, detail)
            raise OllamaModelError(detail)

        try:
            payload = response.json()
        except ValueError as exc:
            raise OllamaError("Invalid JSON from Ollama") from exc

        return parse_chat_response(payload)
