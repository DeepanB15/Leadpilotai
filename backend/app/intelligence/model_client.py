import asyncio
import logging
from typing import Protocol

import httpx

log = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    model_id: str

    async def chat_json(self, system: str, user: str) -> str: ...


class OllamaClient:
    """Minimal Ollama chat client requesting JSON output (temperature 0)."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float = 300.0,
        num_ctx: int = 8192,
        retries: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.model_id = model
        self.num_ctx = num_ctx
        self.retries = retries
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport)

    async def chat_json(self, system: str, user: str) -> str:
        payload = {
            "model": self.model_id,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_ctx": self.num_ctx},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                resp = await self._client.post("/api/chat", json=payload)
                if resp.status_code >= 500:
                    raise LLMError(f"Ollama server error {resp.status_code}")
                if resp.status_code >= 400:
                    raise LLMError(f"Ollama rejected the request ({resp.status_code}): {resp.text[:200]}")
                content = resp.json().get("message", {}).get("content", "")
                if not content:
                    raise LLMError("Ollama returned an empty response")
                return content
            except (httpx.TransportError, LLMError) as exc:
                last = exc
                # 4xx errors are not transient
                if isinstance(exc, LLMError) and "rejected" in str(exc):
                    break
                if attempt < self.retries - 1:
                    delay = 2**attempt
                    log.warning("ollama call failed (%s); retrying in %ss", exc, delay)
                    await asyncio.sleep(delay)
        raise LLMError(f"LLM unavailable: {last.__class__.__name__}: {last}") from last

    async def aclose(self) -> None:
        await self._client.aclose()
