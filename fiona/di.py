"""Simple service container for dependency injection.

Not a full DI framework — just enough to avoid global singletons
while remaining pytest-friendly.

Usage:
    container = FionaContainer()
    container.register_instance("config", config)
    container.register_factory("browser_provider", lambda: SeleniumBrowserProvider())
    browser = container.resolve("browser_provider")
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class FionaContainer:
    """Lightweight dependency injection container.

    Supports registration of concrete instances and lazy-singleton
    factories.  All public methods are thread-safe.

    Attributes:
        _services: Mapping of service names to cached instances.
        _factories: Mapping of service names to factory callables.
        _lock: Reentrant lock guarding all mutations.
    """

    def __init__(self) -> None:
        """Initialise an empty container."""
        self._services: dict[str, Any] = {}
        self._factories: dict[str, Callable[[], Any]] = {}
        self._lock = threading.RLock()

    def register_instance(self, name: str, instance: Any) -> None:
        """Register a concrete instance under *name*.

        The instance is returned as-is on every ``resolve(name)`` call.

        Args:
            name: Unique service identifier.
            instance: The object to register.

        Raises:
            ValueError: If *name* is already registered (as instance or
                factory).
        """
        with self._lock:
            if name in self._services:
                raise ValueError(f"Service already registered as instance: {name}")
            if name in self._factories:
                raise ValueError(f"Service already registered as factory: {name}")
            self._services[name] = instance

    def register_factory(self, name: str, factory: Callable[[], Any]) -> None:
        """Register a *factory* that produces the service on first access.

        The factory is called at most once; the result is cached and
        returned for all subsequent ``resolve(name)`` calls (lazy
        singleton semantics).

        Args:
            name: Unique service identifier.
            factory: Zero-argument callable that returns the service.

        Raises:
            ValueError: If *name* is already registered (as instance or
                factory).
        """
        with self._lock:
            if name in self._services:
                raise ValueError(f"Service already registered as instance: {name}")
            if name in self._factories:
                raise ValueError(f"Service already registered as factory: {name}")
            self._factories[name] = factory

    def resolve(self, name: str) -> Any:
        """Return the service registered under *name*.

        If a factory was registered, it is invoked once and the result
        is cached for subsequent calls.

        Args:
            name: Service identifier to look up.

        Returns:
            The registered instance (or factory result).

        Raises:
            KeyError: If no service is registered under *name*.
        """
        with self._lock:
            # Fast path — already instantiated.
            if name in self._services:
                return self._services[name]

            # Lazy-init path — factory exists, call & cache.
            factory = self._factories.get(name)
            if factory is not None:
                instance = factory()
                self._services[name] = instance
                return instance

        raise KeyError(
            f"Service not registered: {name!r}. "
            f"Call register_instance() or register_factory() first."
        )

    def __contains__(self, name: str) -> bool:
        """Check if a service is registered (instance or factory).

        Args:
            name: Service identifier.

        Returns:
            True if the service can be resolved.
        """
        with self._lock:
            return name in self._services or name in self._factories

    def __repr__(self) -> str:
        with self._lock:
            instances = len(self._services)
            factories = len(self._factories)
        return f"FionaContainer({instances} instances, {factories} factories)"


# ======================================================================
# SciRetrieval integration
# ======================================================================

_default_container: FionaContainer | None = None


def _get_default_container() -> FionaContainer:
    """Return the module-level default DI container, creating it lazily."""
    global _default_container
    if _default_container is None:
        _default_container = FionaContainer()
    return _default_container


def register_sci_retrieval(container: FionaContainer) -> None:
    """Register SciRetrieval components in the DI container."""
    from pathlib import Path

    from SciPhi.interfaces.model import ScientificDomain
    from SciRetrieval.router import Router
    from SciRetrieval.provider_registry import ProviderRegistry
    from SciRetrieval.normalizer import (
        Normalizer,
        _normalize_pubchem,
        _normalize_ncbi,
        _normalize_nist,
    )
    from SciRetrieval.entity_resolver import EntityResolver
    from SciRetrieval.retrieval_manager import RetrievalManager
    from SciRetrieval.cache.cache_backend import MemoryBackend, DiskBackend
    from SciRetrieval.cache.conversation_cache import ConversationCache
    from SciRetrieval.cache.dataset_cache import DatasetCache
    from SciRetrieval.cache.nist_cache import NISTCache
    from SciRetrieval.cache_manager import CacheManager
    from SciRetrieval.scilab.parser import SciLabParser
    from SciRetrieval.scilab.ranker import Ranker
    from SciRetrieval.scilab.deduplicator import Deduplicator
    from SciRetrieval.scilab.summarizer import Summarizer
    from SciRetrieval.scilab.context_generator import ContextGenerator
    from SciRetrieval.scilab.engine import SciLabEngine
    from SciRetrieval.maintext_bridge import MainTextBridge
    from SciRetrieval.providers.ncbi import NCBIProvider
    from SciRetrieval.providers.pubchem import PubChemProvider
    from SciRetrieval.providers.nist import NISTProvider

    base = Path(__file__).resolve().parent.parent  # project root

    # Keyword path
    keyword_path = base / "SciRetrieval" / "data" / "keywordlist.json"
    container.register_instance("sci_retrieval.keyword_path", keyword_path)

    # Router
    container.register_factory("sci_retrieval.router", lambda: Router(keyword_path))

    # Providers
    container.register_factory(
        "sci_retrieval.provider.ncbi", lambda: NCBIProvider()
    )
    container.register_factory(
        "sci_retrieval.provider.pubchem", lambda: PubChemProvider()
    )
    container.register_factory(
        "sci_retrieval.provider.nist", lambda: NISTProvider()
    )

    # Provider registry
    def _init_registry():
        reg = ProviderRegistry()
        reg.register(
            container.resolve("sci_retrieval.provider.pubchem"),
            [ScientificDomain.CHEMISTRY],
            primary=True,
        )
        reg.register(
            container.resolve("sci_retrieval.provider.ncbi"),
            [ScientificDomain.BIOLOGY],
            primary=True,
        )
        reg.register(
            container.resolve("sci_retrieval.provider.nist"),
            [ScientificDomain.CHEMISTRY, ScientificDomain.PHYSICS, ScientificDomain.ENGINEERING],
            primary=False,
        )
        reg.register(
            container.resolve("sci_retrieval.provider.pubchem"),
            [ScientificDomain.BIOLOGY],
            primary=False,
        )
        return reg

    container.register_factory("sci_retrieval.provider_registry", _init_registry)

    # Normalizer
    def _init_normalizer():
        n = Normalizer()
        n.register_adapter("pubchem", _normalize_pubchem)
        n.register_adapter("ncbi", _normalize_ncbi)
        n.register_adapter("nist", _normalize_nist)
        return n

    container.register_factory("sci_retrieval.normalizer", _init_normalizer)

    # Entity Resolver
    synonym_path = base / "SciRetrieval" / "data" / "synonyms.json"
    container.register_factory(
        "sci_retrieval.resolver",
        lambda: EntityResolver(synonym_path if synonym_path.exists() else None),
    )

    # SciLab components
    container.register_factory(
        "sci_retrieval.scilab.parser", lambda: SciLabParser()
    )
    container.register_factory(
        "sci_retrieval.scilab.ranker", lambda: Ranker()
    )
    container.register_factory(
        "sci_retrieval.scilab.deduplicator", lambda: Deduplicator()
    )
    container.register_factory(
        "sci_retrieval.scilab.summarizer", lambda: Summarizer()
    )
    container.register_factory(
        "sci_retrieval.scilab.context_generator", lambda: ContextGenerator()
    )
    container.register_factory(
        "sci_retrieval.scilab.engine",
        lambda: SciLabEngine(
            parser=container.resolve("sci_retrieval.scilab.parser"),
            ranker=container.resolve("sci_retrieval.scilab.ranker"),
            deduplicator=container.resolve("sci_retrieval.scilab.deduplicator"),
            summarizer=container.resolve("sci_retrieval.scilab.summarizer"),
            context_generator=container.resolve("sci_retrieval.scilab.context_generator"),
        ),
    )

    # Cache backends
    container.register_factory(
        "sci_retrieval.cache.memory", lambda: MemoryBackend()
    )
    disk_dir = base / "SciRetrieval" / "data" / "cache"
    nist_disk_dir = base / "SciRetrieval" / "data" / "nist_cache"
    container.register_factory(
        "sci_retrieval.cache.disk", lambda: DiskBackend(disk_dir)
    )
    container.register_factory(
        "sci_retrieval.cache.nist_disk", lambda: DiskBackend(nist_disk_dir)
    )

    # Cache manager (wraps raw backends into conversation / dataset / nist caches)
    container.register_factory(
        "sci_retrieval.cache_manager",
        lambda: CacheManager(
            conversation_backend=container.resolve("sci_retrieval.cache.memory"),
            dataset_backend=container.resolve("sci_retrieval.cache.disk"),
            persistent_backend=container.resolve("sci_retrieval.cache.nist_disk"),
        ),
    )

    # Retrieval manager
    container.register_factory(
        "sci_retrieval.manager",
        lambda: RetrievalManager(
            classifier=container.resolve("sci_retrieval.router"),
            registry=container.resolve("sci_retrieval.provider_registry"),
            normalizer=container.resolve("sci_retrieval.normalizer"),
            resolver=container.resolve("sci_retrieval.resolver"),
            scilab=container.resolve("sci_retrieval.scilab.engine"),
            cache_manager=container.resolve("sci_retrieval.cache_manager"),
        ),
    )

    # Bridge
    container.register_factory(
        "sci_retrieval.bridge",
        lambda: MainTextBridge(
            retrieval_manager=container.resolve("sci_retrieval.manager"),
        ),
    )


def register_tool_runtime(container: FionaContainer) -> None:
    """Register the ToolRuntime in the DI container.

    Args:
        container: A FionaContainer instance.
    """
    from Agent.tool_runtime import ToolRuntime

    def _factory() -> ToolRuntime:
        return ToolRuntime()

    container.register_factory("tool.runtime", _factory)


def register_email_client(container: FionaContainer) -> None:
    """Register EmailClient in the DI container.

    Args:
        container: A FionaContainer instance.
    """
    from pathlib import Path

    from Communications.email_client import EmailClient, EmailConfig

    config_path = Path.home() / ".config" / "fiona" / "email.json"

    def _load_email_config() -> EmailConfig:
        if config_path.exists():
            import json
            from dataclasses import fields

            data = json.loads(config_path.read_text(encoding="utf-8"))
            valid = {f.name for f in fields(EmailConfig)}
            filtered = {k: v for k, v in data.items() if k in valid}
            return EmailConfig(**filtered)
        return EmailConfig()

    container.register_factory("email.config", _load_email_config)
    container.register_factory(
        "email.client",
        lambda: EmailClient(container.resolve("email.config")),
    )


def get_sci_retrieval_bridge(
    container: FionaContainer | None = None,
) -> "MainTextBridge":
    """Resolve the MainTextBridge from the DI container.

    Args:
        container: A FionaContainer instance.  If *None* the default
            module-level container is used.

    Returns:
        A configured MainTextBridge instance.
    """
    if container is None:
        container = _get_default_container()
    if "sci_retrieval.bridge" not in container:
        register_sci_retrieval(container)
    return container.resolve("sci_retrieval.bridge")
