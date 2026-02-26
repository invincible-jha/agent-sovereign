"""Tests for PluginRegistry."""
from __future__ import annotations

from abc import abstractmethod
from unittest.mock import MagicMock, patch

import pytest

from agent_sovereign.plugins.registry import (
    PluginAlreadyRegisteredError,
    PluginNotFoundError,
    PluginRegistry,
)
from abc import ABC


# ---------------------------------------------------------------------------
# Test fixtures — a minimal plugin base class
# ---------------------------------------------------------------------------

class BasePlugin(ABC):
    @abstractmethod
    def run(self) -> str: ...


class ConcretePluginA(BasePlugin):
    def run(self) -> str:
        return "A"


class ConcretePluginB(BasePlugin):
    def run(self) -> str:
        return "B"


@pytest.fixture()
def registry() -> PluginRegistry[BasePlugin]:
    return PluginRegistry(BasePlugin, "test-registry")


# ---------------------------------------------------------------------------
# PluginNotFoundError
# ---------------------------------------------------------------------------

class TestPluginNotFoundError:
    def test_attributes(self) -> None:
        err = PluginNotFoundError("missing", "my-reg")
        assert err.plugin_name == "missing"
        assert err.registry_name == "my-reg"
        assert "missing" in str(err)

    def test_is_key_error(self) -> None:
        err = PluginNotFoundError("x", "y")
        assert isinstance(err, KeyError)


# ---------------------------------------------------------------------------
# PluginAlreadyRegisteredError
# ---------------------------------------------------------------------------

class TestPluginAlreadyRegisteredError:
    def test_attributes(self) -> None:
        err = PluginAlreadyRegisteredError("dup", "my-reg")
        assert err.plugin_name == "dup"
        assert err.registry_name == "my-reg"
        assert "dup" in str(err)

    def test_is_value_error(self) -> None:
        err = PluginAlreadyRegisteredError("x", "y")
        assert isinstance(err, ValueError)


# ---------------------------------------------------------------------------
# PluginRegistry.register (decorator)
# ---------------------------------------------------------------------------

class TestRegisterDecorator:
    def test_register_and_get(self, registry: PluginRegistry[BasePlugin]) -> None:
        @registry.register("plugin-a")
        class LocalPlugin(BasePlugin):
            def run(self) -> str:
                return "local"
        result = registry.get("plugin-a")
        assert result is LocalPlugin

    def test_register_returns_class_unchanged(
        self, registry: PluginRegistry[BasePlugin]
    ) -> None:
        @registry.register("plugin-ret")
        class LocalPlugin(BasePlugin):
            def run(self) -> str:
                return "ret"
        assert LocalPlugin().run() == "ret"

    def test_duplicate_raises(self, registry: PluginRegistry[BasePlugin]) -> None:
        @registry.register("dup-plugin")
        class P1(BasePlugin):
            def run(self) -> str:
                return "1"

        with pytest.raises(PluginAlreadyRegisteredError):
            @registry.register("dup-plugin")
            class P2(BasePlugin):
                def run(self) -> str:
                    return "2"

    def test_non_subclass_raises(self, registry: PluginRegistry[BasePlugin]) -> None:
        with pytest.raises(TypeError):
            @registry.register("bad")  # type: ignore[arg-type]
            class NotAPlugin:
                pass


# ---------------------------------------------------------------------------
# PluginRegistry.register_class
# ---------------------------------------------------------------------------

class TestRegisterClass:
    def test_register_class_directly(self, registry: PluginRegistry[BasePlugin]) -> None:
        registry.register_class("cls-a", ConcretePluginA)
        assert registry.get("cls-a") is ConcretePluginA

    def test_duplicate_raises(self, registry: PluginRegistry[BasePlugin]) -> None:
        registry.register_class("cls-b", ConcretePluginA)
        with pytest.raises(PluginAlreadyRegisteredError):
            registry.register_class("cls-b", ConcretePluginB)

    def test_non_subclass_raises(self, registry: PluginRegistry[BasePlugin]) -> None:
        class NotPlugin:
            pass
        with pytest.raises(TypeError):
            registry.register_class("bad", NotPlugin)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# PluginRegistry.deregister
# ---------------------------------------------------------------------------

class TestDeregister:
    def test_deregister_removes(self, registry: PluginRegistry[BasePlugin]) -> None:
        registry.register_class("to-remove", ConcretePluginA)
        registry.deregister("to-remove")
        assert "to-remove" not in registry

    def test_deregister_missing_raises(self, registry: PluginRegistry[BasePlugin]) -> None:
        with pytest.raises(PluginNotFoundError):
            registry.deregister("nonexistent")


# ---------------------------------------------------------------------------
# PluginRegistry.get
# ---------------------------------------------------------------------------

class TestGet:
    def test_get_registered(self, registry: PluginRegistry[BasePlugin]) -> None:
        registry.register_class("get-a", ConcretePluginA)
        assert registry.get("get-a") is ConcretePluginA

    def test_get_missing_raises(self, registry: PluginRegistry[BasePlugin]) -> None:
        with pytest.raises(PluginNotFoundError):
            registry.get("not-there")


# ---------------------------------------------------------------------------
# PluginRegistry.list_plugins
# ---------------------------------------------------------------------------

class TestListPlugins:
    def test_empty_registry(self, registry: PluginRegistry[BasePlugin]) -> None:
        assert registry.list_plugins() == []

    def test_sorted_list(self, registry: PluginRegistry[BasePlugin]) -> None:
        registry.register_class("z-plugin", ConcretePluginA)
        registry.register_class("a-plugin", ConcretePluginB)
        assert registry.list_plugins() == ["a-plugin", "z-plugin"]


# ---------------------------------------------------------------------------
# PluginRegistry membership and sizing
# ---------------------------------------------------------------------------

class TestMembershipAndSizing:
    def test_contains_registered(self, registry: PluginRegistry[BasePlugin]) -> None:
        registry.register_class("member", ConcretePluginA)
        assert "member" in registry

    def test_not_contains_unregistered(self, registry: PluginRegistry[BasePlugin]) -> None:
        assert "ghost" not in registry

    def test_len_empty(self, registry: PluginRegistry[BasePlugin]) -> None:
        assert len(registry) == 0

    def test_len_after_registrations(self, registry: PluginRegistry[BasePlugin]) -> None:
        registry.register_class("p1", ConcretePluginA)
        registry.register_class("p2", ConcretePluginB)
        assert len(registry) == 2

    def test_repr(self, registry: PluginRegistry[BasePlugin]) -> None:
        registry.register_class("r1", ConcretePluginA)
        rep = repr(registry)
        assert "test-registry" in rep
        assert "r1" in rep


# ---------------------------------------------------------------------------
# PluginRegistry.load_entrypoints
# ---------------------------------------------------------------------------

class TestLoadEntrypoints:
    def test_load_entrypoints_empty_group(self, registry: PluginRegistry[BasePlugin]) -> None:
        with patch("importlib.metadata.entry_points", return_value=[]):
            registry.load_entrypoints("nonexistent.group")
        assert len(registry) == 0

    def test_load_entrypoints_skips_existing(
        self, registry: PluginRegistry[BasePlugin]
    ) -> None:
        registry.register_class("pre-existing", ConcretePluginA)
        mock_ep = MagicMock()
        mock_ep.name = "pre-existing"
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            registry.load_entrypoints("some.group")
        # Still only 1, not called load
        mock_ep.load.assert_not_called()
        assert len(registry) == 1

    def test_load_entrypoints_loads_valid_plugin(
        self, registry: PluginRegistry[BasePlugin]
    ) -> None:
        mock_ep = MagicMock()
        mock_ep.name = "ep-plugin"
        mock_ep.load.return_value = ConcretePluginA
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            registry.load_entrypoints("some.group")
        assert "ep-plugin" in registry

    def test_load_entrypoints_handles_load_exception(
        self, registry: PluginRegistry[BasePlugin]
    ) -> None:
        mock_ep = MagicMock()
        mock_ep.name = "bad-ep"
        mock_ep.load.side_effect = ImportError("module not found")
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            registry.load_entrypoints("some.group")  # should not raise
        assert len(registry) == 0

    def test_load_entrypoints_handles_type_error_from_register(
        self, registry: PluginRegistry[BasePlugin]
    ) -> None:
        mock_ep = MagicMock()
        mock_ep.name = "type-err"

        class NotSubclass:
            pass

        mock_ep.load.return_value = NotSubclass
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            registry.load_entrypoints("some.group")  # should not raise
        assert "type-err" not in registry
