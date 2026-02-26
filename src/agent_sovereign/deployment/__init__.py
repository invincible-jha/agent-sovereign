"""Deployment sub-package for agent-sovereign.

Provides deployment templates, packaging, and validation for
sovereign deployment bundles across all sovereignty levels.
"""
from __future__ import annotations

from agent_sovereign.deployment.packager import DeploymentPackage, DeploymentPackager
from agent_sovereign.deployment.templates import (
    DeploymentTemplate,
    TemplateLibrary,
    get_template,
)
from agent_sovereign.deployment.validator import DeploymentValidator, ValidationResult

__all__ = [
    "DeploymentPackage",
    "DeploymentPackager",
    "DeploymentTemplate",
    "DeploymentValidator",
    "TemplateLibrary",
    "ValidationResult",
    "get_template",
]
