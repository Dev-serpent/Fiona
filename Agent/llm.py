"""Multi-Provider LLM Support — abstract provider interface and registry.

Provides:
- ``LLMProvider``: Abstract base for all LLM backends.
- ``OllamaProvider``: Adapter wrapping the existing ``OllamaClient``.
- ``OpenAIProvider``: Adapter for OpenAI-compatible APIs (OpenAI, Groq, etc.).
- ``ProviderRegistry``: Namespace-based provider registration.
- ``LLMManager``: Facade for selecting and using providers.

Usage::

    manager = LLMManager()
    manager.register_provider("ollama", OllamaProvider(base_url="..."))
    response = manager.chat("ollama", messages=[
        {"role": "user", "content": "Hello"}
    ])
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


# ======================================================================
# 1. Shared data types
# ======================================================================


@dataclass(frozen=True)
class LLMMessage:
    """A single message in a chat conversation.

    Attributes:
        role: One of ``"system"``, ``"user"``, ``"assistant"``, ``"tool"``.
        content: The message text.
        tool_calls: Optional list of tool call requests.
        tool_call_id: If role is ``"tool"``, the ID of the tool call being responded to.
    """

    role: str
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    """A structured response from an LLM provider.

    Attributes:
        content: The response text content (may be ``None`` if only tool calls).
        tool_calls: List of tool call dicts, each with ``id``, ``function_name``,
            and ``arguments`` keys.
        finish_reason: Reason the generation stopped (``"stop"``, ``"tool_calls"``,
            ``"length"``).
        usage: Optional dict with token usage information.
        model: Model name that generated the response.
        provider: Provider name that served the request.
        latency_ms: Request round-trip time in milliseconds.
    """

    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    finish_reason: str = "stop"
    usage: dict[str, Any] | None = None
    model: str = ""
    provider: str = ""
    latency_ms: float = 0.0


# ======================================================================
# 2. Abstract provider interface
# ======================================================================


class LLMProvider(ABC):
    """Abstract base class for LLM backends.

    Subclasses must implement ``chat()`` and ``stream()``.
    All other methods have sensible defaults.
    """

    name: str = "base"
    """Human-readable provider name."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]] | list[LLMMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Send a chat completion request.

        Args:
            messages: Conversation history (list of role/content dicts).
            system: Optional system prompt override.
            tools: Optional list of tool definitions.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            model: Model override (provider-specific).

        Returns:
            An ``LLMResponse`` with the generation result.
        """
        ...

    @abstractmethod
    def stream(
        self,
        messages: list[dict[str, Any]] | list[LLMMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> Any:
        """Stream a chat completion.

        Yields:
            Text chunks as they arrive from the model.
        """
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Estimate or count the number of tokens in *text*.

        May use a local tokenizer or a heuristic.
        """
        ...

    def health(self) -> bool:
        """Check whether this provider is reachable and operational.

        Returns:
            ``True`` if the provider is healthy.
        """
        return True


# ======================================================================
# 3. Ollama provider adapter
# ======================================================================


class OllamaProvider(LLMProvider):
    """Adapter that wraps the existing ``OllamaClient`` as an ``LLMProvider``.

    This is the default provider when no other backend is configured.
    """

    name: str = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434/api",
        model: str = "qwen3:8b-en",
        timeout_seconds: float = 120.0,
    ) -> None:
        """
        Args:
            base_url: Ollama server base URL.
            model: Default model name.
            timeout_seconds: Request timeout.
        """
        self.base_url = base_url
        self.model = model
        self.timeout_seconds = timeout_seconds
        from Agent.ollama import OllamaClient

        self._client = OllamaClient(
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
        )

    def _to_ollama_messages(
        self,
        messages: list[dict[str, Any]] | list[LLMMessage],
    ) -> list[dict[str, Any]]:
        """Convert messages to Ollama format."""
        result: list[dict[str, Any]] = []
        for msg in messages:
            if isinstance(msg, LLMMessage):
                entry: dict[str, Any] = {"role": msg.role}
                if msg.content is not None:
                    entry["content"] = msg.content
                if msg.tool_calls:
                    entry["tool_calls"] = msg.tool_calls
                if msg.tool_call_id:
                    entry["tool_call_id"] = msg.tool_call_id
                result.append(entry)
            else:
                result.append(msg)
        return result

    def chat(
        self,
        messages: list[dict[str, Any]] | list[LLMMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        start = time.monotonic()
        ollama_messages = self._to_ollama_messages(messages)
        try:
            raw = self._client.chat(
                messages=ollama_messages,
                system=system,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model,
            )
            elapsed = (time.monotonic() - start) * 1000
            return LLMResponse(
                content=raw.content,
                tool_calls=(
                    [
                        {
                            "id": tc.id,
                            "function_name": tc.function_name,
                            "arguments": tc.arguments,
                        }
                        for tc in raw.tool_calls
                    ]
                    if raw.tool_calls
                    else None
                ),
                finish_reason=raw.finish_reason,
                usage=raw.usage,
                model=model or self.model,
                provider=self.name,
                latency_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            logger.error("OllamaProvider.chat failed: %s", exc)
            return LLMResponse(
                content=None,
                finish_reason="error",
                model=model or self.model,
                provider=self.name,
                latency_ms=elapsed,
                usage={"error": str(exc)},
            )

    def stream(
        self,
        messages: list[dict[str, Any]] | list[LLMMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> Any:
        ollama_messages = self._to_ollama_messages(messages)
        return self._client.stream(
            messages=ollama_messages,
            system=system,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
        )

    def count_tokens(self, text: str) -> int:
        """Rough token estimate (4 chars = 1 token)."""
        return max(1, len(text) // 4)

    def health(self) -> bool:
        try:
            self._client.health()
            return True
        except Exception:
            return False


# ======================================================================
# 4. OpenAI-compatible provider
# ======================================================================


class OpenAIProvider(LLMProvider):
    """Adapter for OpenAI-compatible REST APIs.

    Works with OpenAI, Groq, Together AI, Azure OpenAI, and any other
    API that follows the ``/v1/chat/completions`` schema.

    Requires the ``openai`` package (``pip install openai``).
    """

    name: str = "openai"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 60.0,
    ) -> None:
        """
        Args:
            api_key: API key.  Falls back to ``OPENAI_API_KEY`` env var.
            base_url: API base URL.  Defaults to OpenAI.
            model: Default model name.
            timeout_seconds: Request timeout.
        """
        import os

        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-import and create the OpenAI client."""
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout_seconds,
            )
        except ImportError:
            raise ImportError(
                "The 'openai' package is required for OpenAIProvider. "
                "Install with: pip install openai"
            )
        return self._client

    def chat(
        self,
        messages: list[dict[str, Any]] | list[LLMMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        start = time.monotonic()
        client = self._get_client()

        openai_messages: list[dict[str, Any]] = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        for msg in messages:
            if isinstance(msg, LLMMessage):
                entry: dict[str, Any] = {"role": msg.role}
                if msg.content is not None:
                    entry["content"] = msg.content
                if msg.tool_calls:
                    entry["tool_calls"] = msg.tool_calls
                if msg.tool_call_id:
                    entry["tool_call_id"] = msg.tool_call_id
                openai_messages.append(entry)
            else:
                openai_messages.append(msg)

        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": openai_messages,
        }
        if tools is not None:
            kwargs["tools"] = tools
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        try:
            response = client.chat.completions.create(**kwargs)
            elapsed = (time.monotonic() - start) * 1000
            choice = response.choices[0] if response.choices else None
            if choice is None:
                return LLMResponse(
                    finish_reason="error",
                    model=model or self.model,
                    provider=self.name,
                    latency_ms=elapsed,
                )

            message = choice.message
            raw_tool_calls = message.tool_calls
            tool_calls = None
            if raw_tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "function_name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments)
                        if isinstance(tc.function.arguments, str)
                        else tc.function.arguments,
                    }
                    for tc in raw_tool_calls
                ]

            return LLMResponse(
                content=message.content,
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason or "stop",
                usage=response.usage.model_dump() if response.usage else None,
                model=model or self.model,
                provider=self.name,
                latency_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            logger.error("OpenAIProvider.chat failed: %s", exc)
            return LLMResponse(
                finish_reason="error",
                model=model or self.model,
                provider=self.name,
                latency_ms=elapsed,
                usage={"error": str(exc)},
            )

    def stream(
        self,
        messages: list[dict[str, Any]] | list[LLMMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> Any:
        client = self._get_client()
        openai_messages: list[dict[str, Any]] = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        for msg in messages:
            if isinstance(msg, LLMMessage):
                entry: dict[str, Any] = {"role": msg.role}
                if msg.content is not None:
                    entry["content"] = msg.content
                if msg.tool_calls:
                    entry["tool_calls"] = msg.tool_calls
                openai_messages.append(entry)
            else:
                openai_messages.append(msg)

        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": openai_messages,
            "stream": True,
        }
        if tools is not None:
            kwargs["tools"] = tools
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        response = client.chat.completions.create(**kwargs)
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def count_tokens(self, text: str) -> int:
        """Rough token estimate (4 chars = 1 token)."""
        return max(1, len(text) // 4)

    def health(self) -> bool:
        try:
            client = self._get_client()
            client.models.list()
            return True
        except Exception:
            return False


# ======================================================================
# 5. ProviderRegistry
# ======================================================================


class ProviderRegistry:
    """Registry of named LLM providers.

    Allows registering providers by name and querying them.
    """

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, name: str, provider: LLMProvider) -> None:
        """Register a provider under *name*.

        Args:
            name: Unique provider name.
            provider: An ``LLMProvider`` instance.

        Raises:
            ValueError: If a provider with the same name is registered.
        """
        if name in self._providers:
            raise ValueError(f"Provider {name!r} is already registered")
        self._providers[name] = provider

    def get(self, name: str) -> LLMProvider | None:
        """Look up a provider by name."""
        return self._providers.get(name)

    def list(self) -> list[tuple[str, LLMProvider]]:
        """Return all registered (name, provider) pairs, sorted."""
        return sorted(self._providers.items(), key=lambda x: x[0])

    def remove(self, name: str) -> bool:
        """Remove a provider. Returns ``True`` if it existed."""
        return self._providers.pop(name, None) is not None

    def count(self) -> int:
        return len(self._providers)

    def get_names(self) -> list[str]:
        return sorted(self._providers.keys())


# ======================================================================
# 6. LLMManager — unified facade
# ======================================================================


class LLMManager:
    """High-level facade for selecting and using LLM providers.

    Automatically registers a default ``OllamaProvider`` if no providers
    are explicitly configured.

    Usage::

        mgr = LLMManager()
        mgr.register_provider("ollama", OllamaProvider())
        mgr.register_provider("openai", OpenAIProvider(api_key="..."))

        # Explicit provider
        response = mgr.chat("ollama", messages=[{"role": "user", "content": "Hi"}])

        # Active provider (default or explicitly set)
        response = mgr.chat(messages=[{"role": "user", "content": "Hi"}])
    """

    def __init__(
        self,
        providers: dict[str, LLMProvider] | None = None,
        *,
        default_provider: str = "ollama",
        auto_register_default: bool = True,
    ) -> None:
        """
        Args:
            providers: Optional mapping of name → provider.
            default_provider: Name of the default/active provider.
            auto_register_default: If ``True`` (default), automatically
                register an ``OllamaProvider`` if no providers exist.
        """
        self._registry = ProviderRegistry()
        self._default_provider = default_provider

        if providers:
            for name, prov in providers.items():
                self._registry.register(name, prov)
        elif auto_register_default:
            try:
                ollama = OllamaProvider()
                self._registry.register("ollama", ollama)
            except Exception as exc:
                logger.warning("Failed to register default OllamaProvider: %s", exc)

    # ------------------------------------------------------------------
    # Provider management
    # ------------------------------------------------------------------

    def register_provider(self, name: str, provider: LLMProvider) -> None:
        """Register an LLM provider.

        Args:
            name: Unique provider name.
            provider: An ``LLMProvider`` instance.
        """
        self._registry.register(name, provider)

    def get_provider(self, name: str | None = None) -> LLMProvider | None:
        """Get a provider by name (or the default if *name* is ``None``)."""
        return self._registry.get(name or self._default_provider)

    def list_providers(self) -> list[str]:
        """Return all registered provider names."""
        return self._registry.get_names()

    def set_default_provider(self, name: str) -> None:
        """Set the default provider name.

        Raises:
            KeyError: If no provider with *name* is registered.
        """
        if self._registry.get(name) is None:
            raise KeyError(f"Provider {name!r} is not registered")
        self._default_provider = name

    # ------------------------------------------------------------------
    # Chat operations
    # ------------------------------------------------------------------

    def chat(
        self,
        provider_name: str | None = None,
        messages: list[dict[str, Any]] | list[LLMMessage] | None = None,
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion using the specified (or default) provider.

        Args:
            provider_name: Provider to use (default if ``None``).
            messages: Conversation history.

        Returns:
            An ``LLMResponse``.
        """
        provider = self.get_provider(provider_name)
        if provider is None:
            return LLMResponse(
                finish_reason="error",
                provider=provider_name or self._default_provider,
                usage={"error": f"No provider available: {provider_name or self._default_provider}"},
            )
        return provider.chat(
            messages=messages or [],
            system=system,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
        )

    def stream(
        self,
        provider_name: str | None = None,
        messages: list[dict[str, Any]] | list[LLMMessage] | None = None,
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> Any:
        """Stream a chat completion."""
        provider = self.get_provider(provider_name)
        if provider is None:
            return iter([])
        return provider.stream(
            messages=messages or [],
            system=system,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
        )


__all__ = [
    "LLMManager",
    "LLMMessage",
    "LLMProvider",
    "LLMResponse",
    "OllamaProvider",
    "OpenAIProvider",
    "ProviderRegistry",
]
