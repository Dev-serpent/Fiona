"""Tests for the layered memory system (Phase 7: Memory System)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from Agent.memory import (
    ChatStoreMemoryProvider,
    InMemoryProvider,
    MemoryEntry,
    MemoryManager,
    MemoryNamespace,
    MemoryProvider,
)


# ======================================================================
# 1. MemoryEntry
# ======================================================================


class TestMemoryEntry:
    def test_create(self):
        entry = MemoryEntry(namespace="user", key="name", value="Alice")
        assert entry.namespace == "user"
        assert entry.key == "name"
        assert entry.value == "Alice"
        assert entry.metadata == {}
        assert entry.ttl is None
        assert not entry.expired

    def test_expired(self):
        entry = MemoryEntry(
            namespace="user",
            key="temp",
            value="x",
            timestamp=time.time() - 100,
            ttl=10,
        )
        assert entry.expired

    def test_not_expired(self):
        entry = MemoryEntry(
            namespace="user",
            key="temp",
            value="x",
            timestamp=time.time(),
            ttl=3600,
        )
        assert not entry.expired

    def test_no_ttl_never_expires(self):
        entry = MemoryEntry(
            namespace="user",
            key="perm",
            value="x",
            timestamp=0,
            ttl=None,
        )
        assert not entry.expired


# ======================================================================
# 2. MemoryNamespace constants
# ======================================================================


class TestMemoryNamespace:
    def test_all_returns_six(self):
        namespaces = MemoryNamespace.all()
        assert len(namespaces) == 6
        assert MemoryNamespace.CONVERSATION in namespaces
        assert MemoryNamespace.TASK in namespaces
        assert MemoryNamespace.WORKSPACE in namespaces
        assert MemoryNamespace.USER in namespaces
        assert MemoryNamespace.AGENT in namespaces
        assert MemoryNamespace.PROJECT in namespaces

    def test_constants(self):
        assert MemoryNamespace.CONVERSATION == "conversation"
        assert MemoryNamespace.TASK == "task"
        assert MemoryNamespace.WORKSPACE == "workspace"
        assert MemoryNamespace.USER == "user"
        assert MemoryNamespace.AGENT == "agent"
        assert MemoryNamespace.PROJECT == "project"


# ======================================================================
# 3. InMemoryProvider
# ======================================================================


class TestInMemoryProvider:
    @pytest.fixture
    def provider(self):
        return InMemoryProvider()

    def test_store_and_retrieve(self, provider):
        provider.store("user", "name", "Alice")
        assert provider.retrieve("user", "name") == "Alice"

    def test_retrieve_nonexistent(self, provider):
        with pytest.raises(KeyError):
            provider.retrieve("user", "nonexistent")

    def test_retrieve_nonexistent_namespace(self, provider):
        with pytest.raises(KeyError):
            provider.retrieve("unknown", "key")

    def test_store_with_metadata(self, provider):
        provider.store(
            "user",
            "email",
            "alice@example.com",
            metadata={"source": "form", "verified": True},
        )
        # Verify via search
        results = provider.search("user", "alice")
        assert len(results) == 1
        assert results[0].metadata["source"] == "form"

    def test_store_with_ttl(self, provider):
        provider.store(
            "user",
            "temp",
            "expires_soon",
            ttl=0.01,
        )
        time.sleep(0.02)
        with pytest.raises(KeyError):
            provider.retrieve("user", "temp")

    def test_delete_existing(self, provider):
        provider.store("user", "name", "Alice")
        assert provider.delete("user", "name") is True
        with pytest.raises(KeyError):
            provider.retrieve("user", "name")

    def test_delete_nonexistent(self, provider):
        assert provider.delete("user", "nonexistent") is False

    def test_clear_namespace(self, provider):
        provider.store("user", "a", 1)
        provider.store("user", "b", 2)
        provider.clear("user")
        assert provider.count("user") == 0

    def test_search_substring_key(self, provider):
        provider.store("user", "preferred_language", "Python")
        results = provider.search("user", "preferred")
        assert len(results) == 1
        assert results[0].key == "preferred_language"

    def test_search_substring_value(self, provider):
        provider.store("user", "bio", "Loves Python and Rust")
        results = provider.search("user", "Python")
        assert len(results) == 1

    def test_search_metadata(self, provider):
        provider.store("user", "age", 30, metadata={"unit": "years"})
        results = provider.search("user", "years")
        assert len(results) == 1

    def test_search_no_match(self, provider):
        provider.store("user", "name", "Alice")
        results = provider.search("user", "Bob")
        assert len(results) == 0

    def test_search_limit(self, provider):
        for i in range(20):
            provider.store("user", f"key_{i}", f"value_{i}")
        results = provider.search("user", "value", limit=5)
        assert len(results) == 5

    def test_search_empty_namespace(self, provider):
        results = provider.search("empty", "anything")
        assert results == []

    def test_list_namespaces(self, provider):
        provider.store("user", "a", 1)
        provider.store("task", "b", 2)
        nss = provider.list_namespaces()
        assert "user" in nss
        assert "task" in nss

    def test_count(self, provider):
        assert provider.count("user") == 0
        provider.store("user", "a", 1)
        provider.store("user", "b", 2)
        assert provider.count("user") == 2

    def test_store_empty_key_raises(self, provider):
        with pytest.raises(ValueError):
            provider.store("user", "", "x")

    def test_store_empty_namespace_raises(self, provider):
        with pytest.raises(ValueError):
            provider.store("", "key", "x")

    def test_thread_safety(self, provider):
        """Concurrent stores should not corrupt data."""
        import threading

        errors: list[Exception] = []

        def writer(i: int):
            try:
                provider.store("shared", f"k{i}", i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert provider.count("shared") == 50


# ======================================================================
# 4. ChatStoreMemoryProvider adapter
# ======================================================================


class TestChatStoreMemoryProvider:
    @pytest.fixture
    def mock_chat_store(self):
        store = MagicMock()
        store.list_sessions.return_value = ["session-1", "session-2"]
        store.search.return_value = [
            {"session_id": "session-1", "role": "user", "content": "hello"},
        ]
        return store

    @pytest.fixture
    def provider(self, mock_chat_store):
        return ChatStoreMemoryProvider(mock_chat_store)

    def test_store_conversation(self, provider, mock_chat_store):
        provider.store(
            MemoryNamespace.CONVERSATION,
            "session-1",
            "remember this",
        )
        mock_chat_store.add_message.assert_called_once_with(
            session_id="session-1",
            role="system",
            content="remember this",
        )

    def test_store_other_namespace(self, provider, mock_chat_store):
        """Non-conversation stores go to fallback."""
        provider.store("user", "name", "Alice")
        mock_chat_store.add_message.assert_not_called()
        assert provider.retrieve("user", "name") == "Alice"

    def test_retrieve_conversation(self, provider, mock_chat_store):
        messages = provider.retrieve(MemoryNamespace.CONVERSATION, "session-1")
        mock_chat_store.get_context_window.assert_called_once_with(session_id="session-1")

    def test_retrieve_conversation_not_found(self, provider, mock_chat_store):
        mock_chat_store.get_context_window.side_effect = Exception("not found")
        with pytest.raises(KeyError):
            provider.retrieve(MemoryNamespace.CONVERSATION, "bad-session")

    def test_search_conversation(self, provider, mock_chat_store):
        results = provider.search(MemoryNamespace.CONVERSATION, "hello")
        mock_chat_store.search.assert_called_once_with("hello", limit=10)
        assert len(results) == 1
        assert results[0].key == "session-1"

    def test_search_other_namespace(self, provider, mock_chat_store):
        provider.store("user", "name", "Alice")
        results = provider.search("user", "Alice")
        assert len(results) == 1

    def test_delete_conversation(self, provider, mock_chat_store):
        assert provider.delete(MemoryNamespace.CONVERSATION, "session-1")
        mock_chat_store.delete_session.assert_called_once_with("session-1")

    def test_delete_conversation_failure(self, provider, mock_chat_store):
        mock_chat_store.delete_session.side_effect = Exception("fail")
        assert not provider.delete(MemoryNamespace.CONVERSATION, "session-1")

    def test_clear_conversation(self, provider, mock_chat_store):
        provider.clear(MemoryNamespace.CONVERSATION)
        assert mock_chat_store.delete_session.call_count == 2

    def test_list_namespaces(self, provider):
        provider.store("user", "a", 1)
        nss = provider.list_namespaces()
        assert MemoryNamespace.CONVERSATION in nss
        assert "user" in nss

    def test_count_conversation(self, provider, mock_chat_store):
        assert provider.count(MemoryNamespace.CONVERSATION) == 2


# ======================================================================
# 5. MemoryManager facade
# ======================================================================


class TestMemoryManager:
    @pytest.fixture
    def manager(self):
        return MemoryManager()

    def test_auto_register_all_namespaces(self):
        mgr = MemoryManager()
        nss = mgr.list_namespaces()
        for ns in MemoryNamespace.all():
            assert ns in nss, f"Missing namespace: {ns}"

    def test_store_and_retrieve(self, manager):
        manager.store("user", "name", "Alice")
        assert manager.retrieve("user", "name") == "Alice"

    def test_retrieve_nonexistent(self, manager):
        with pytest.raises(KeyError):
            manager.retrieve("user", "nonexistent")

    def test_search(self, manager):
        manager.store("project", "lang", "Python")
        results = manager.search("project", "Python")
        assert len(results) == 1

    def test_delete(self, manager):
        manager.store("user", "x", 1)
        assert manager.delete("user", "x") is True
        assert manager.delete("user", "x") is False

    def test_clear(self, manager):
        manager.store("user", "a", 1)
        manager.store("user", "b", 2)
        manager.clear("user")
        assert manager.count("user") == 0

    def test_count(self, manager):
        assert manager.count("user") == 0
        manager.store("user", "a", 1)
        assert manager.count("user") == 1

    def test_get_summary(self, manager):
        manager.store("user", "a", 1)
        manager.store("task", "b", 2)
        summary = manager.get_summary()
        assert summary["user"] >= 1
        assert summary["task"] >= 1

    def test_register_provider(self, manager):
        custom = InMemoryProvider()
        manager.register_provider("custom", custom)
        assert manager.get_provider("custom") is custom

    def test_remove_provider(self, manager):
        assert manager.remove_provider("nonexistent") is False
        manager.register_provider("custom", InMemoryProvider())
        assert manager.remove_provider("custom") is True

    def test_list_providers(self, manager):
        providers = manager.list_providers()
        for ns in MemoryNamespace.all():
            assert ns in providers
            assert providers[ns] == "InMemoryProvider"

    def test_get_provider_fallback(self, manager):
        provider = manager.get_provider("nonexistent_namespace")
        assert isinstance(provider, InMemoryProvider)

    def test_custom_providers_at_init(self):
        custom = InMemoryProvider()
        mgr = MemoryManager(providers={"custom": custom})
        assert mgr.get_provider("custom") is custom

    def test_store_with_metadata(self, manager):
        manager.store("user", "email", "a@b.com", metadata={"source": "test"})
        results = manager.search("user", "test")
        assert len(results) == 1

    def test_store_with_ttl(self, manager):
        manager.store("user", "temp", "x", ttl=0.01)
        time.sleep(0.02)
        with pytest.raises(KeyError):
            manager.retrieve("user", "temp")

    def test_set_event_bus(self):
        mgr = MemoryManager()
        bus = MagicMock()
        mgr.set_event_bus(bus)
        assert mgr._event_bus is bus


class TestMemoryManagerMultiNamespace:
    def test_independent_namespaces(self):
        """Operations in one namespace don't affect others."""
        mgr = MemoryManager()
        mgr.store("user", "name", "Alice")
        mgr.store("task", "id", 42)
        mgr.store("project", "name", "Fiona")

        assert mgr.retrieve("user", "name") == "Alice"
        assert mgr.retrieve("task", "id") == 42
        assert mgr.retrieve("project", "name") == "Fiona"

        mgr.clear("user")
        with pytest.raises(KeyError):
            mgr.retrieve("user", "name")
        assert mgr.retrieve("task", "id") == 42  # still there

    def test_search_across_namespaces(self):
        """Each namespace maintain separate search indices."""
        mgr = MemoryManager()
        mgr.store("user", "lang", "Python")
        mgr.store("project", "lang", "Rust")

        user_results = mgr.search("user", "Python")
        project_results = mgr.search("project", "Rust")

        assert len(user_results) == 1
        assert len(project_results) == 1
        assert user_results[0].namespace == "user"
        assert project_results[0].namespace == "project"


# ======================================================================
# 6. MemoryProvider ABC contract
# ======================================================================


class TestMemoryProviderContract:
    def test_abc_cannot_instantiate(self):
        with pytest.raises(TypeError):
            MemoryProvider()  # type: ignore[abstract]

    def test_inmemory_is_concrete(self):
        provider = InMemoryProvider()
        assert isinstance(provider, MemoryProvider)

    def test_chatstore_is_concrete(self):
        provider = ChatStoreMemoryProvider(MagicMock())
        assert isinstance(provider, MemoryProvider)
