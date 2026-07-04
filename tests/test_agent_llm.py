"""Tests for Multi-Provider LLM system (Phase 9: Multi-Provider LLM)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from Agent.llm import (
    LLMManager,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    OllamaProvider,
    OpenAIProvider,
    ProviderRegistry,
)


# ======================================================================
# 1. Data types
# ======================================================================


class TestLLMMessage:
    def test_create(self):
        msg = LLMMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.tool_calls is None

    def test_create_system(self):
        msg = LLMMessage(role="system", content="Be helpful")
        assert msg.role == "system"

    def test_create_tool_call(self):
        msg = LLMMessage(
            role="assistant",
            content=None,
            tool_calls=[{"id": "call_1", "function_name": "search"}],
        )
        assert msg.tool_calls is not None

    def test_create_tool_response(self):
        msg = LLMMessage(role="tool", content="Result", tool_call_id="call_1")
        assert msg.tool_call_id == "call_1"


class TestLLMResponse:
    def test_create(self):
        resp = LLMResponse(content="Hello!", finish_reason="stop")
        assert resp.content == "Hello!"
        assert resp.finish_reason == "stop"
        assert resp.latency_ms == 0.0

    def test_with_tool_calls(self):
        resp = LLMResponse(
            content=None,
            tool_calls=[{"id": "1", "function_name": "search", "arguments": {}}],
            finish_reason="tool_calls",
        )
        assert len(resp.tool_calls) == 1

    def test_error_response(self):
        resp = LLMResponse(finish_reason="error", usage={"error": "timeout"})
        assert resp.usage["error"] == "timeout"


# ======================================================================
# 2. LLMProvider ABC
# ======================================================================


class TestLLMProviderABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            LLMProvider()  # type: ignore[abstract]

    def test_health_default(self):
        """Concrete subclass should inherit health() returning True."""
        provider = OllamaProvider()
        # Replace the frozen client entirely with a mock
        mock_client = MagicMock()
        mock_client.health.return_value = {}
        provider._client = mock_client  # type: ignore[assignment]
        assert provider.health()

    def test_count_tokens_approximate(self):
        provider = OllamaProvider()
        count = provider.count_tokens("hello world")
        assert count >= 1
        assert count == len("hello world") // 4

    def test_name_property(self):
        """Default name for an unconfigured provider."""
        # We can't instantiate ABC directly, but subclasses set name
        assert OllamaProvider.name == "ollama"


# ======================================================================
# 3. OllamaProvider
# ======================================================================


class TestOllamaProvider:
    @pytest.fixture
    def provider(self):
        p = OllamaProvider()
        # Replace frozen OllamaClient with a mock to avoid real network calls
        p._client = MagicMock()  # type: ignore[assignment]
        return p

    def test_name(self, provider):
        assert provider.name == "ollama"

    def test_chat_success(self, provider):
        mock_response = MagicMock()
        mock_response.content = "Hello back"
        mock_response.tool_calls = None
        mock_response.finish_reason = "stop"
        mock_response.usage = {"total_tokens": 10}
        provider._client.chat.return_value = mock_response

        resp = provider.chat(messages=[{"role": "user", "content": "Hi"}])
        assert resp.content == "Hello back"
        assert resp.finish_reason == "stop"
        assert resp.provider == "ollama"
        assert resp.latency_ms >= 0

    def test_chat_with_tool_calls(self, provider):
        mock_response = MagicMock()
        mock_response.content = None
        mock_response.tool_calls = [
            MagicMock(id="call_1", function_name="search", arguments={"q": "test"})
        ]
        mock_response.finish_reason = "tool_calls"
        mock_response.usage = None
        provider._client.chat.return_value = mock_response

        resp = provider.chat(
            messages=[{"role": "user", "content": "Search something"}],
            tools=[{"function": {"name": "search"}}],
        )
        assert resp.content is None
        assert resp.finish_reason == "tool_calls"
        assert resp.tool_calls is not None
        assert resp.tool_calls[0]["function_name"] == "search"

    def test_chat_error(self, provider):
        provider._client.chat.side_effect = Exception("timeout")
        resp = provider.chat(messages=[{"role": "user", "content": "Hi"}])
        assert resp.finish_reason == "error"
        assert resp.content is None

    def test_stream(self, provider):
        mock_stream = iter(["chunk1", "chunk2"])
        provider._client.stream.return_value = mock_stream

        chunks = list(provider.stream(messages=[{"role": "user", "content": "Hi"}]))
        assert chunks == ["chunk1", "chunk2"]

    def test_llm_message_conversion(self, provider):
        """LLMMessage objects should be converted to dicts."""
        mock_response = MagicMock()
        mock_response.content = "ok"
        mock_response.tool_calls = None
        mock_response.finish_reason = "stop"
        mock_response.usage = None
        provider._client.chat.return_value = mock_response

        resp = provider.chat(
            messages=[LLMMessage(role="user", content="Hello")]
        )
        assert resp.content == "ok"

    def test_health_success(self, provider):
        provider._client.health.return_value = {}
        assert provider.health()

    def test_health_failure(self, provider):
        provider._client.health.side_effect = Exception("offline")
        assert not provider.health()


# ======================================================================
# 4. OpenAIProvider (mocked — no real API key needed)
# ======================================================================


class TestOpenAIProvider:
    @pytest.fixture
    def provider(self):
        p = OpenAIProvider(api_key="test-key")
        # Pre-set the client to avoid real network calls
        p._client = MagicMock()
        return p

    def test_name(self, provider):
        assert provider.name == "openai"

    def test_lazy_import_missing(self, provider):
        """If openai package missing, _get_client should raise ImportError."""
        provider._client = None
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ImportError):
                provider._get_client()

    def test_chat_success(self, provider):
        mock_message = MagicMock()
        mock_message.content = "Hello from OpenAI"
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.model_dump.return_value = {"total_tokens": 15}

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        provider._client.chat.completions.create.return_value = mock_response

        resp = provider.chat(messages=[{"role": "user", "content": "Hi"}])
        assert resp.content == "Hello from OpenAI"
        assert resp.provider == "openai"
        assert resp.usage["total_tokens"] == 15

    def test_chat_error(self, provider):
        provider._client.chat.completions.create.side_effect = Exception("API error")

        resp = provider.chat(messages=[{"role": "user", "content": "Hi"}])
        assert resp.finish_reason == "error"
        assert "error" in resp.usage

    def test_stream(self, provider):
        class MockChunk:
            def __init__(self, content):
                self.choices = [MagicMock()]
                self.choices[0].delta.content = content

        provider._client.chat.completions.create.return_value = iter([
            MockChunk("Hello "),
            MockChunk("World"),
        ])

        chunks = list(provider.stream(messages=[{"role": "user", "content": "Hi"}]))
        assert chunks == ["Hello ", "World"]

    def test_health_success(self, provider):
        provider._client.models.list.return_value = ["model1"]
        assert provider.health()

    def test_health_failure(self, provider):
        provider._client.models.list.side_effect = Exception("offline")
        assert not provider.health()


# ======================================================================
# 5. ProviderRegistry
# ======================================================================


class TestProviderRegistry:
    @pytest.fixture
    def registry(self):
        return ProviderRegistry()

    def test_register(self, registry):
        p = OllamaProvider()
        registry.register("ollama", p)
        assert registry.count() == 1
        assert registry.get("ollama") is p

    def test_register_duplicate_raises(self, registry):
        p1 = OllamaProvider()
        p2 = OllamaProvider()
        registry.register("same", p1)
        with pytest.raises(ValueError):
            registry.register("same", p2)

    def test_get_nonexistent(self, registry):
        assert registry.get("nonexistent") is None

    def test_list_sorted(self, registry):
        registry.register("z", OllamaProvider())
        registry.register("a", OllamaProvider())
        names = [n for n, _ in registry.list()]
        assert names == ["a", "z"]

    def test_remove_existing(self, registry):
        p = OllamaProvider()
        registry.register("tmp", p)
        assert registry.remove("tmp") is True
        assert registry.count() == 0

    def test_remove_nonexistent(self, registry):
        assert registry.remove("nonexistent") is False

    def test_get_names(self, registry):
        registry.register("a", OllamaProvider())
        registry.register("b", OllamaProvider())
        assert registry.get_names() == ["a", "b"]


# ======================================================================
# 6. LLMManager facade
# ======================================================================


class TestLLMManager:
    def test_auto_register_ollama(self):
        mgr = LLMManager()
        names = mgr.list_providers()
        assert "ollama" in names

    def test_auto_register_failure_fallback(self):
        """If Ollama init fails, we should still get a manager with no providers."""
        with patch("Agent.llm.OllamaProvider", side_effect=Exception("fail")):
            mgr = LLMManager(auto_register_default=True)
            assert mgr.list_providers() == []

    def test_custom_providers(self):
        p = OllamaProvider()
        mgr = LLMManager(providers={"custom": p})
        assert mgr.list_providers() == ["custom"]
        assert mgr.get_provider("custom") is p

    def test_register_provider(self):
        mgr = LLMManager(auto_register_default=False)
        mgr.register_provider("test", OllamaProvider())
        assert "test" in mgr.list_providers()

    def test_get_provider_default(self):
        mgr = LLMManager()
        p = mgr.get_provider()
        assert p is not None

    def test_get_provider_nonexistent(self):
        mgr = LLMManager(auto_register_default=False)
        assert mgr.get_provider("nonexistent") is None

    def test_set_default_provider(self):
        mgr = LLMManager(auto_register_default=False)
        mgr.register_provider("custom", OllamaProvider())
        mgr.set_default_provider("custom")
        assert mgr._default_provider == "custom"

    def test_set_default_provider_not_found(self):
        mgr = LLMManager(auto_register_default=False)
        with pytest.raises(KeyError):
            mgr.set_default_provider("nonexistent")

    def test_chat_with_provider_name(self):
        mgr = LLMManager(auto_register_default=False)
        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.name = "mock"
        mock_provider.chat.return_value = LLMResponse(content="Mock response")
        mgr.register_provider("mock", mock_provider)

        resp = mgr.chat(
            provider_name="mock",
            messages=[{"role": "user", "content": "Hi"}],
        )
        assert resp.content == "Mock response"
        mock_provider.chat.assert_called_once()

    def test_chat_with_default_provider(self):
        mgr = LLMManager(auto_register_default=False)
        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.name = "default"
        mock_provider.chat.return_value = LLMResponse(content="Default response")
        mgr.register_provider("default", mock_provider)
        mgr.set_default_provider("default")

        resp = mgr.chat(messages=[{"role": "user", "content": "Hi"}])
        assert resp.content == "Default response"

    def test_chat_no_provider(self):
        mgr = LLMManager(auto_register_default=False)
        resp = mgr.chat(messages=[{"role": "user", "content": "Hi"}])
        assert resp.finish_reason == "error"
        assert "error" in resp.usage

    def test_stream_with_provider(self):
        mgr = LLMManager(auto_register_default=False)
        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.name = "mock"
        mock_provider.stream.return_value = iter(["a", "b"])
        mgr.register_provider("mock", mock_provider)

        chunks = list(mgr.stream(provider_name="mock", messages=[{"role": "user", "content": "Hi"}]))
        assert chunks == ["a", "b"]

    def test_stream_no_provider(self):
        mgr = LLMManager(auto_register_default=False)
        chunks = list(mgr.stream(messages=[{"role": "user", "content": "Hi"}]))
        assert chunks == []
