"""Plugin subsystem for agent-sovereign.

The registry module provides the decorator-based registration surface.
Third-party implementations register via this system using
``importlib.metadata`` entry-points under the "agent_sovereign.plugins"
group.

Example
-------
Declare a plugin in pyproject.toml:

.. code-block:: toml

    [agent_sovereign.plugins]
    my_plugin = "my_package.plugins.my_plugin:MyPlugin"
"""
from __future__ import annotations

from agent_sovereign.plugins.registry import PluginRegistry

__all__ = ["PluginRegistry"]
