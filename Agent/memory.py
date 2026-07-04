"""Layered Memory System for Fiona.

Provides a multi-layer memory architecture with pluggable
backends and a unified ``MemoryManager`` facade.

Layers (namespaces):
    - ``conversation``: Per-session chat history.
    - ``task``: Per-task goals, decisions, intermediate results.
    - ``workspace``: Workspace-level key-value context.
    - ``user``: User preferences, known facts, history.
    - ``agent``: Agent-internal state, learnings, patterns.
    - ``project``: Project-wide conventions, glossary, knowledge.

Usage::

    manager = MemoryManager()
    manager.register_provider("user", InMemoryProvider())
    manager.store("user", "preferred_language", "Python")
    value = manager.retrieve("user", "preferred_language")
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ======================================================================
# 1. Data types
# ======================================================================


@dataclass
class MemoryEntry:
    """A single entry in any memory layer.

    Attributes:
        namespace: Which layer this entry belongs to.
        key: Unique identifier within the namespace.
        value: The stored data (any JSON-serialisable type).
        metadata: Optional key-value annotations.
        timestamp: Unix timestamp of when this entry was stored.
        ttl: Optional time-to-live in seconds (``None`` = never expires).
    """

    namespace: str
    key: str
    value: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    ttl: float | None = None

    @property
    def expired(self) -> bool:
        """Whether this entry has exceeded its TTL."""
        if self.ttl is None:
            return False
        return (time.time() - self.timestamp) > self.ttl


class MemoryNamespace:
    """Well-known memory layer names."""

    CONVERSATION = "conversation"
    TASK = "task"
    WORKSPACE = "workspace"
    USER = "user"
    AGENT = "agent"
    PROJECT = "project"

    @classmethod
    def all(cls) -> list[str]:
        """Return all well-known namespace names."""
        return [
            cls.CONVERSATION,
            cls.TASK,
            cls.WORKSPACE,
            cls.USER,
            cls.AGENT,
            cls.PROJECT,
        ]


# ======================================================================
# 2. Abstract provider interface
# ======================================================================


class MemoryProvider(ABC):
    """Abstract base class for memory storage backends.

    Subclasses must implement all abstract methods.  Providers are
    expected to be thread-safe (the ``MemoryManager`` does not add
    additional locking).
    """

    @abstractmethod
    def store(
        self,
        namespace: str,
        key: str,
        value: Any,
        metadata: dict[str, Any] | None = None,
        ttl: float | None = None,
    ) -> None:
        """Store a value under *namespace* / *key*.

        Args:
            namespace: Memory layer name.
            key: Unique identifier within the namespace.
            value: The value to store.
            metadata: Optional annotations.
            ttl: Optional TTL in seconds.
        """
        ...

    @abstractmethod
    def retrieve(self, namespace: str, key: str) -> Any:
        """Retrieve a value by *namespace* / *key*.

        Returns:
            The stored value, or ``None`` if not found.

        Raises:
            KeyError: If the key does not exist in the namespace.
        """
        ...

    @abstractmethod
    def search(
        self,
        namespace: str,
        query: str,
        *,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Search within a namespace for entries matching *query*.

        Args:
            namespace: Memory layer name.
            query: Free-text search string.
            limit: Maximum number of results.

        Returns:
            A list of matching ``MemoryEntry`` objects.
        """
        ...

    @abstractmethod
    def delete(self, namespace: str, key: str) -> bool:
        """Delete an entry from the given namespace.

        Returns:
            ``True`` if the entry existed and was removed.
        """
        ...

    @abstractmethod
    def clear(self, namespace: str) -> None:
        """Remove **all** entries from the given namespace."""
        ...

    @abstractmethod
    def list_namespaces(self) -> list[str]:
        """Return the list of namespaces this provider manages."""
        ...

    @abstractmethod
    def count(self, namespace: str) -> int:
        """Return the number of entries in *namespace*."""
        ...


# ======================================================================
# 3. Built-in in-memory provider
# ======================================================================


class InMemoryProvider(MemoryProvider):
    """Simple thread-safe in-memory dict-based memory provider.

    This is the default provider used when no other backend is configured.
    Data is lost when the process exits.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[str, MemoryEntry]] = {}
        import threading

        self._lock = threading.Lock()

    def store(
        self,
        namespace: str,
        key: str,
        value: Any,
        metadata: dict[str, Any] | None = None,
        ttl: float | None = None,
    ) -> None:
        if not namespace or not key:
            raise ValueError("namespace and key must be non-empty")
        entry = MemoryEntry(
            namespace=namespace,
            key=key,
            value=value,
            metadata=metadata or {},
            timestamp=time.time(),
            ttl=ttl,
        )
        with self._lock:
            self._data.setdefault(namespace, {})[key] = entry

    def retrieve(self, namespace: str, key: str) -> Any:
        with self._lock:
            ns = self._data.get(namespace)
            if ns is None:
                raise KeyError(f"No entries in namespace {namespace!r}")
            entry = ns.get(key)
            if entry is None:
                raise KeyError(f"No entry {key!r} in namespace {namespace!r}")
            if entry.expired:
                del ns[key]
                raise KeyError(f"Entry {key!r} in {namespace!r} has expired")
            return entry.value

    def search(
        self,
        namespace: str,
        query: str,
        *,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        query_lower = query.lower()
        results: list[MemoryEntry] = []
        with self._lock:
            ns = self._data.get(namespace)
            if ns is None:
                return results
            for entry in ns.values():
                if entry.expired:
                    continue
                # Simple substring matching on key, value (stringified), and metadata
                if (
                    query_lower in entry.key.lower()
                    or query_lower in str(entry.value).lower()
                    or any(
                        query_lower in str(v).lower() for v in entry.metadata.values()
                    )
                ):
                    results.append(entry)
                    if len(results) >= limit:
                        break
        return results

    def delete(self, namespace: str, key: str) -> bool:
        with self._lock:
            ns = self._data.get(namespace)
            if ns is None:
                return False
            return ns.pop(key, None) is not None

    def clear(self, namespace: str) -> None:
        with self._lock:
            self._data.pop(namespace, None)

    def list_namespaces(self) -> list[str]:
        with self._lock:
            return list(self._data.keys())

    def count(self, namespace: str) -> int:
        with self._lock:
            ns = self._data.get(namespace)
            return len(ns) if ns else 0


# ======================================================================
# 4. ChatStore adapter
# ======================================================================


class ChatStoreMemoryProvider(MemoryProvider):
    """Adapter that exposes an existing ``ChatStore`` as a ``MemoryProvider``.

    The ``conversation`` namespace maps to chat sessions/messages.
    Other namespaces are stored in-memory as a fallback.

    This allows existing ``ChatStore``-backed conversations to participate
    in the unified memory system without data duplication.
    """

    def __init__(self, chat_store: Any) -> None:
        """
        Args:
            chat_store: A ``ChatStore`` instance (from ``Agent.chat_store``).
        """
        self._chat_store = chat_store
        self._fallback = InMemoryProvider()

    def store(
        self,
        namespace: str,
        key: str,
        value: Any,
        metadata: dict[str, Any] | None = None,
        ttl: float | None = None,
    ) -> None:
        if namespace == MemoryNamespace.CONVERSATION:
            # ChatStore uses session_id — store as a note/context key
            self._chat_store.add_message(
                session_id=key,
                role="system",
                content=str(value),
            )
        else:
            self._fallback.store(namespace, key, value, metadata, ttl)

    def retrieve(self, namespace: str, key: str) -> Any:
        if namespace == MemoryNamespace.CONVERSATION:
            try:
                messages = self._chat_store.get_context_window(session_id=key)
                return messages
            except Exception:
                raise KeyError(f"No conversation session {key!r}")
        return self._fallback.retrieve(namespace, key)

    def search(
        self,
        namespace: str,
        query: str,
        *,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        if namespace == MemoryNamespace.CONVERSATION:
            # ChatStore has its own search
            try:
                results = self._chat_store.search(query, limit=limit)
            except Exception:
                results = []
            return [
                MemoryEntry(
                    namespace=namespace,
                    key=str(r.get("session_id", "")),
                    value=r.get("content", ""),
                    metadata={"role": r.get("role", "")},
                )
                for r in results
            ]
        return self._fallback.search(namespace, query, limit=limit)

    def delete(self, namespace: str, key: str) -> bool:
        if namespace == MemoryNamespace.CONVERSATION:
            try:
                self._chat_store.delete_session(key)
                return True
            except Exception:
                return False
        return self._fallback.delete(namespace, key)

    def clear(self, namespace: str) -> None:
        if namespace == MemoryNamespace.CONVERSATION:
            for session in self._chat_store.list_sessions():
                try:
                    self._chat_store.delete_session(session)
                except Exception:
                    pass
        else:
            self._fallback.clear(namespace)

    def list_namespaces(self) -> list[str]:
        namespaces = set(self._fallback.list_namespaces())
        namespaces.add(MemoryNamespace.CONVERSATION)
        return sorted(namespaces)

    def count(self, namespace: str) -> int:
        if namespace == MemoryNamespace.CONVERSATION:
            return len(self._chat_store.list_sessions())
        return self._fallback.count(namespace)


# ======================================================================
# 5. MemoryManager — unified facade
# ======================================================================


class MemoryManager:
    """Unified facade over multiple memory providers and layers.

    Automatically creates an ``InMemoryProvider`` for every well-known
    namespace that doesn't already have a registered provider.

    Usage::

        mgr = MemoryManager()
        mgr.store("user", "name", "Alice", metadata={"source": "onboarding"})
        name = mgr.retrieve("user", "name")
        results = mgr.search("project", "authentication")
        mgr.delete("task", "goal-1")
    """

    def __init__(
        self,
        providers: dict[str, MemoryProvider] | None = None,
        *,
        auto_register: bool = True,
    ) -> None:
        """Initialise the memory manager.

        Args:
            providers: Optional mapping of namespace → provider.
            auto_register: If ``True`` (default), automatically create
                ``InMemoryProvider`` instances for any well-known namespace
                that is not yet registered.
        """
        self._providers: dict[str, MemoryProvider] = {}
        self._default_provider = InMemoryProvider()
        self._event_bus: Any = None

        if providers:
            self._providers.update(providers)

        if auto_register:
            for ns in MemoryNamespace.all():
                if ns not in self._providers:
                    self._providers[ns] = InMemoryProvider()

    # ------------------------------------------------------------------
    # Provider management
    # ------------------------------------------------------------------

    def register_provider(
        self,
        namespace: str,
        provider: MemoryProvider,
    ) -> None:
        """Register a provider for a specific namespace.

        Args:
            namespace: The namespace to handle (e.g. ``"user"``).
            provider: A ``MemoryProvider`` instance.
        """
        if not namespace:
            raise ValueError("Namespace must be non-empty")
        self._providers[namespace] = provider

    def get_provider(self, namespace: str) -> MemoryProvider:
        """Return the provider for *namespace*.

        Falls back to the default in-memory provider if no specific
        provider is registered.
        """
        return self._providers.get(namespace, self._default_provider)

    def remove_provider(self, namespace: str) -> bool:
        """Remove a registered provider.

        Returns:
            ``True`` if the provider existed.
        """
        return self._providers.pop(namespace, None) is not None

    def list_providers(self) -> dict[str, type[MemoryProvider]]:
        """Return mapping of namespace → provider class name."""
        return {ns: type(p).__name__ for ns, p in self._providers.items()}

    # ------------------------------------------------------------------
    # Event bus wiring
    # ------------------------------------------------------------------

    def set_event_bus(self, event_bus: Any) -> None:
        """Set the event bus for publishing memory events."""
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def store(
        self,
        namespace: str,
        key: str,
        value: Any,
        metadata: dict[str, Any] | None = None,
        ttl: float | None = None,
    ) -> None:
        """Store a value in the given namespace.

        Args:
            namespace: Memory layer name (e.g. ``"user"``, ``"task"``).
            key: Unique identifier within the namespace.
            value: Any JSON-serialisable value.
            metadata: Optional annotations.
            ttl: Optional TTL in seconds.
        """
        provider = self.get_provider(namespace)
        provider.store(namespace, key, value, metadata, ttl)

    def retrieve(self, namespace: str, key: str) -> Any:
        """Retrieve a value from the given namespace.

        Returns:
            The stored value.

        Raises:
            KeyError: If the key does not exist.
        """
        provider = self.get_provider(namespace)
        return provider.retrieve(namespace, key)

    def search(
        self,
        namespace: str,
        query: str,
        *,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Search within a namespace.

        Args:
            namespace: Memory layer to search.
            query: Free-text search (simple substring match by default).
            limit: Maximum results.

        Returns:
            List of matching ``MemoryEntry`` objects.
        """
        provider = self.get_provider(namespace)
        return provider.search(namespace, query, limit=limit)

    def delete(self, namespace: str, key: str) -> bool:
        """Delete an entry.

        Returns:
            ``True`` if the entry existed.
        """
        provider = self.get_provider(namespace)
        return provider.delete(namespace, key)

    def clear(self, namespace: str) -> None:
        """Remove all entries from a namespace."""
        provider = self.get_provider(namespace)
        provider.clear(namespace)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def count(self, namespace: str) -> int:
        """Return the number of entries in *namespace*."""
        provider = self.get_provider(namespace)
        return provider.count(namespace)

    def list_namespaces(self) -> list[str]:
        """Return all known namespaces.

        Includes both explicitly registered namespaces and those
        discovered from default providers.
        """
        result: set[str] = set(self._providers.keys())
        for p in self._providers.values():
            try:
                result.update(p.list_namespaces())
            except Exception:
                pass
        return sorted(result)

    def get_summary(self) -> dict[str, int]:
        """Return a summary of entry counts per namespace.

        Returns:
            Dict mapping namespace → entry count.
        """
        summary: dict[str, int] = {}
        for ns in self.list_namespaces():
            summary[ns] = self.count(ns)
        return summary


__all__ = [
    "ChatStoreMemoryProvider",
    "InMemoryProvider",
    "MemoryEntry",
    "MemoryManager",
    "MemoryNamespace",
    "MemoryProvider",
]
