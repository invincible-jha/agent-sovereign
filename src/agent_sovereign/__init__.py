"""agent-sovereign — Sovereign and edge deployment toolkit for self-contained agent bundles.

Public API
----------
The stable public surface is everything exported from this module.
Anything inside submodules not re-exported here is considered private
and may change without notice.

Example
-------
>>> import agent_sovereign
>>> agent_sovereign.__version__
'0.1.0'

Classifier
----------
>>> from agent_sovereign import SovereigntyLevel, SovereigntyAssessor
>>> assessor = SovereigntyAssessor()
>>> result = assessor.assess(data_types=["phi"], regulations=["HIPAA"])
>>> result.level
<SovereigntyLevel.L4_LOCAL_AUGMENTED: 4>

Deployment
----------
>>> from agent_sovereign import get_template, DeploymentPackager, DeploymentValidator
>>> template = get_template(SovereigntyLevel.L3_HYBRID)
>>> packager = DeploymentPackager(SovereigntyLevel.L3_HYBRID)

Provenance
----------
>>> from agent_sovereign import ProvenanceTracker, ModelProvenance, AttestationGenerator
>>> import secrets
>>> tracker = ProvenanceTracker()
>>> tracker.record(ModelProvenance(model_id="m1", source="internal", version="1.0"))

Edge
----
>>> from agent_sovereign import EdgeRuntime, EdgeConfig, OfflineManager, SyncManager

Residency
---------
>>> from agent_sovereign import ResidencyChecker, DataResidencyPolicy, JurisdictionMapper

Compliance
----------
>>> from agent_sovereign import SovereigntyComplianceChecker
"""
from __future__ import annotations

__version__: str = "0.1.0"

# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------
from agent_sovereign.classifier.assessor import SovereigntyAssessment, SovereigntyAssessor
from agent_sovereign.classifier.levels import (
    CAPABILITY_REQUIREMENTS,
    LEVEL_DESCRIPTIONS,
    SovereigntyLevel,
    get_capability_requirements,
    get_level_description,
)
from agent_sovereign.classifier.regulatory import REGULATORY_MINIMUMS, RegulatoryMapper
from agent_sovereign.classifier.rules import (
    ClassificationRule,
    ClassificationRules,
    RuleMatchResult,
)
from agent_sovereign.classifier.sensitivity import (
    DATA_SENSITIVITY,
    DataSensitivityDetector,
    DetectionResult,
)

# ---------------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------------
from agent_sovereign.deployment.packager import DeploymentManifest, DeploymentPackage, DeploymentPackager
from agent_sovereign.deployment.templates import (
    ComputeRequirements,
    DeploymentTemplate,
    NetworkConfig,
    SecurityControls,
    StorageRequirements,
    TemplateLibrary,
    get_template,
)
from agent_sovereign.deployment.validator import (
    DeploymentConfig,
    DeploymentValidator,
    ValidationResult,
    ValidationStatus,
)

# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------
from agent_sovereign.provenance.attestation import Attestation, AttestationGenerator
from agent_sovereign.provenance.tracker import ModelProvenance, ProvenanceTracker

# ---------------------------------------------------------------------------
# Edge
# ---------------------------------------------------------------------------
from agent_sovereign.edge.offline import CachedResponse, OfflineCapability, OfflineManager, OfflineStatus
from agent_sovereign.edge.runtime import (
    EdgeConfig,
    EdgeRuntime,
    PerformanceEstimate,
    QuantizationLevel,
    ResourceValidationResult,
)
from agent_sovereign.edge.sync import (
    SyncManager,
    SyncPolicy,
    SyncPriority,
    SyncTask,
    SyncTaskProcessor,
    SyncTaskStatus,
)

# ---------------------------------------------------------------------------
# Residency
# ---------------------------------------------------------------------------
from agent_sovereign.residency.mapper import JurisdictionMapper, JurisdictionRequirements
from agent_sovereign.residency.policy import DataResidencyPolicy, ResidencyChecker

# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------
from agent_sovereign.compliance.checker import (
    ComplianceIssue,
    ComplianceReport,
    ComplianceStatus,
    SovereigntyComplianceChecker,
)

__all__ = [
    # Version
    "__version__",
    # Classifier — levels
    "SovereigntyLevel",
    "LEVEL_DESCRIPTIONS",
    "CAPABILITY_REQUIREMENTS",
    "get_level_description",
    "get_capability_requirements",
    # Classifier — regulatory
    "REGULATORY_MINIMUMS",
    "RegulatoryMapper",
    # Classifier — rules
    "ClassificationRule",
    "ClassificationRules",
    "RuleMatchResult",
    # Classifier — sensitivity
    "DATA_SENSITIVITY",
    "DataSensitivityDetector",
    "DetectionResult",
    # Classifier — assessor
    "SovereigntyAssessment",
    "SovereigntyAssessor",
    # Deployment — templates
    "ComputeRequirements",
    "DeploymentTemplate",
    "NetworkConfig",
    "SecurityControls",
    "StorageRequirements",
    "TemplateLibrary",
    "get_template",
    # Deployment — packager
    "DeploymentManifest",
    "DeploymentPackage",
    "DeploymentPackager",
    # Deployment — validator
    "DeploymentConfig",
    "DeploymentValidator",
    "ValidationResult",
    "ValidationStatus",
    # Provenance — tracker
    "ModelProvenance",
    "ProvenanceTracker",
    # Provenance — attestation
    "Attestation",
    "AttestationGenerator",
    # Edge — runtime
    "EdgeConfig",
    "EdgeRuntime",
    "PerformanceEstimate",
    "QuantizationLevel",
    "ResourceValidationResult",
    # Edge — sync
    "SyncManager",
    "SyncPolicy",
    "SyncPriority",
    "SyncTask",
    "SyncTaskProcessor",
    "SyncTaskStatus",
    # Edge — offline
    "CachedResponse",
    "OfflineCapability",
    "OfflineManager",
    "OfflineStatus",
    # Residency — policy
    "DataResidencyPolicy",
    "ResidencyChecker",
    # Residency — mapper
    "JurisdictionMapper",
    "JurisdictionRequirements",
    # Compliance
    "ComplianceIssue",
    "ComplianceReport",
    "ComplianceStatus",
    "SovereigntyComplianceChecker",
]
