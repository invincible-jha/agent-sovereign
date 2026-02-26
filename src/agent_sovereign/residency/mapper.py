"""Jurisdiction mapper for data sovereignty requirements.

Maps legal jurisdictions to their applicable data protection laws,
residency requirements, and cross-border transfer rules. Built-in
coverage includes EU/GDPR, US, China/PIPL, India/DPDP, and Brazil/LGPD.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class JurisdictionRequirements:
    """Data protection and residency requirements for a legal jurisdiction.

    Attributes
    ----------
    jurisdiction:
        Identifier for the jurisdiction (e.g. "EU", "CN").
    primary_regulation:
        The primary data protection regulation (e.g. "GDPR").
    requires_data_localisation:
        Whether data must remain within the jurisdiction's borders.
    allows_cross_border_transfers:
        Whether cross-border data transfers are permitted (with conditions).
    transfer_mechanisms:
        Mechanisms that may be used for cross-border transfers (e.g.
        "Standard Contractual Clauses", "Adequacy Decision").
    data_subject_rights:
        List of rights granted to data subjects (e.g. "erasure", "portability").
    breach_notification_hours:
        Mandatory breach notification window in hours (-1 if not specified).
    supervisory_authority:
        Name of the primary regulatory/supervisory authority.
    special_category_data_rules:
        Description of rules for sensitive/special-category data.
    agent_ai_specific_rules:
        Description of any AI-specific or automated decision rules.
    description:
        Human-readable summary of the jurisdiction's requirements.
    """

    jurisdiction: str
    primary_regulation: str
    requires_data_localisation: bool
    allows_cross_border_transfers: bool
    transfer_mechanisms: list[str]
    data_subject_rights: list[str]
    breach_notification_hours: int
    supervisory_authority: str
    special_category_data_rules: str
    agent_ai_specific_rules: str
    description: str


# ---------------------------------------------------------------------------
# Built-in jurisdiction definitions
# ---------------------------------------------------------------------------

_EU_GDPR = JurisdictionRequirements(
    jurisdiction="EU",
    primary_regulation="GDPR",
    requires_data_localisation=False,
    allows_cross_border_transfers=True,
    transfer_mechanisms=[
        "Adequacy Decision",
        "Standard Contractual Clauses (SCCs)",
        "Binding Corporate Rules (BCRs)",
        "Explicit Consent",
        "Vital Interests",
    ],
    data_subject_rights=[
        "access",
        "rectification",
        "erasure",
        "portability",
        "restriction_of_processing",
        "object",
        "automated_decision_making",
    ],
    breach_notification_hours=72,
    supervisory_authority="Lead EU Data Protection Authority (varies by member state)",
    special_category_data_rules=(
        "Article 9 prohibits processing of special categories (health, biometric, "
        "genetic, racial/ethnic, political, religious, trade union, sexual orientation) "
        "unless an explicit exception under Art. 9(2) applies."
    ),
    agent_ai_specific_rules=(
        "Article 22: Data subjects have the right not to be subject to solely "
        "automated decisions with legal or similarly significant effects. "
        "EU AI Act imposes additional conformity requirements for high-risk AI systems."
    ),
    description=(
        "EU General Data Protection Regulation applies to all EU/EEA member states. "
        "Transfers outside the EEA require an approved mechanism. GDPR-max interpretation "
        "maps to sovereignty level L6."
    ),
)

_US = JurisdictionRequirements(
    jurisdiction="US",
    primary_regulation="Patchwork (CCPA, HIPAA, FERPA, SOX, FTC Act, state laws)",
    requires_data_localisation=False,
    allows_cross_border_transfers=True,
    transfer_mechanisms=[
        "EU-US Data Privacy Framework",
        "Standard Contractual Clauses",
        "Binding Corporate Rules",
        "Contractual Consent",
    ],
    data_subject_rights=[
        "access (CCPA)",
        "deletion (CCPA)",
        "opt_out_of_sale (CCPA)",
        "correction (CCPA)",
    ],
    breach_notification_hours=72,  # varies by state; 72h is common
    supervisory_authority="FTC / State AGs / Sector-Specific Agencies",
    special_category_data_rules=(
        "Health data regulated by HIPAA; financial data by GLBA; children's data "
        "by COPPA. No single overarching special-category rule — sector-specific laws apply."
    ),
    agent_ai_specific_rules=(
        "Executive Order on AI (Oct 2023) establishes guidance for AI safety; "
        "sector-specific guidance from NIST AI RMF. Colorado, Texas, Illinois have "
        "AI-specific laws. Federal AI Act pending."
    ),
    description=(
        "The US operates a sectoral privacy framework. Federal law applies to specific "
        "sectors (health, finance, education). CCPA/CPRA applies in California. No single "
        "federal omnibus privacy law as of 2025."
    ),
)

_CN_PIPL = JurisdictionRequirements(
    jurisdiction="CN",
    primary_regulation="PIPL",
    requires_data_localisation=True,
    allows_cross_border_transfers=True,
    transfer_mechanisms=[
        "CAC Security Assessment (mandatory for critical data / large scale transfers)",
        "Standard Contract filed with CAC",
        "Personal Information Protection Certification",
        "Government-approved mechanism",
    ],
    data_subject_rights=[
        "access",
        "correction",
        "deletion",
        "withdrawal_of_consent",
        "transfer_copy",
        "refuse_automated_decision",
    ],
    breach_notification_hours=24,
    supervisory_authority="Cyberspace Administration of China (CAC)",
    special_category_data_rules=(
        "Article 28 PIPL: sensitive personal information (biometric, religion, medical, "
        "financial, location, minors) requires separate consent and heightened protection. "
        "Data localisation is strictly enforced for critical information infrastructure."
    ),
    agent_ai_specific_rules=(
        "Interim Measures for Generative AI Services (2023) requires security assessment "
        "for public-facing AI. Algorithm Recommendation Regulations apply to recommender "
        "systems. Deep Synthesis Regulations govern synthetic media."
    ),
    description=(
        "China's Personal Information Protection Law (PIPL) took effect Nov 2021. "
        "Cross-border transfers require government security assessment or certification. "
        "Data localisation required for critical sectors. Maps to sovereignty level L6."
    ),
)

_IN_DPDP = JurisdictionRequirements(
    jurisdiction="IN",
    primary_regulation="DPDP Act 2023",
    requires_data_localisation=False,
    allows_cross_border_transfers=True,
    transfer_mechanisms=[
        "Transfer to countries approved by Central Government",
        "Standard Contractual Clauses (draft)",
        "Contractual Consent",
    ],
    data_subject_rights=[
        "access",
        "correction_and_completion",
        "erasure",
        "grievance_redressal",
        "nominate_representative",
    ],
    breach_notification_hours=72,
    supervisory_authority="Data Protection Board of India",
    special_category_data_rules=(
        "Sensitive personal data (financial, health, sex life, sexual orientation, "
        "biometric, genetic, religion/belief, political affiliation) must have explicit "
        "consent; additional obligations apply."
    ),
    agent_ai_specific_rules=(
        "No AI-specific legislation as of 2025, but Ministry of Electronics and IT "
        "has published advisory frameworks. Significant financial sector AI guidance "
        "from RBI and SEBI."
    ),
    description=(
        "India's Digital Personal Data Protection Act 2023 establishes rights and "
        "obligations similar to GDPR but with a government-approved whitelist for "
        "cross-border transfers. Implementation regulations pending."
    ),
)

_BR_LGPD = JurisdictionRequirements(
    jurisdiction="BR",
    primary_regulation="LGPD",
    requires_data_localisation=False,
    allows_cross_border_transfers=True,
    transfer_mechanisms=[
        "Adequacy Decision by ANPD",
        "Standard Contractual Clauses",
        "Binding Corporate Rules",
        "Explicit Consent",
        "Regular Contracts (with ANPD approval)",
    ],
    data_subject_rights=[
        "access",
        "correction",
        "anonymisation_or_deletion",
        "portability",
        "information_on_sharing",
        "opt_out_of_consent",
        "review_automated_decision",
    ],
    breach_notification_hours=72,
    supervisory_authority="National Data Protection Authority (ANPD)",
    special_category_data_rules=(
        "Article 11 LGPD: sensitive data (racial/ethnic, religious, political, "
        "trade union, health, sexual orientation, genetic, biometric) requires "
        "specific legal basis and heightened protection."
    ),
    agent_ai_specific_rules=(
        "Article 20 LGPD grants data subjects the right to review automated decisions "
        "that affect their interests. Brazil is developing AI-specific legislation "
        "through a federal AI bill."
    ),
    description=(
        "Brazil's Lei Geral de Proteção de Dados (LGPD) is broadly aligned with GDPR. "
        "Enforced by ANPD since 2021. Penalties up to 2% of revenue in Brazil. "
        "Maps to sovereignty level L3 baseline."
    ),
)


class JurisdictionMapper:
    """Maps jurisdiction codes to their regulatory requirements.

    Built-in jurisdictions: EU (GDPR), US (sectoral), CN (PIPL),
    IN (DPDP Act 2023), BR (LGPD).

    Custom jurisdictions can be registered via ``register``.

    Parameters
    ----------
    custom_jurisdictions:
        Optional additional JurisdictionRequirements to supplement
        the built-in set. Custom entries override built-ins if they
        share the same jurisdiction identifier.
    """

    def __init__(
        self,
        custom_jurisdictions: list[JurisdictionRequirements] | None = None,
    ) -> None:
        self._jurisdictions: dict[str, JurisdictionRequirements] = {
            req.jurisdiction: req
            for req in [_EU_GDPR, _US, _CN_PIPL, _IN_DPDP, _BR_LGPD]
        }
        if custom_jurisdictions:
            for req in custom_jurisdictions:
                self._jurisdictions[req.jurisdiction] = req

    def get_requirements(self, jurisdiction: str) -> JurisdictionRequirements:
        """Return the regulatory requirements for a jurisdiction.

        Parameters
        ----------
        jurisdiction:
            Jurisdiction code (e.g. "EU", "CN", "BR").

        Returns
        -------
        JurisdictionRequirements
            The requirements for the given jurisdiction.

        Raises
        ------
        KeyError
            If the jurisdiction is not known to this mapper.
        """
        if jurisdiction not in self._jurisdictions:
            raise KeyError(
                f"Unknown jurisdiction {jurisdiction!r}. "
                f"Known jurisdictions: {sorted(self._jurisdictions)}"
            )
        return self._jurisdictions[jurisdiction]

    def register(self, requirements: JurisdictionRequirements) -> None:
        """Register or overwrite a jurisdiction's requirements.

        Parameters
        ----------
        requirements:
            The JurisdictionRequirements to register.
        """
        self._jurisdictions[requirements.jurisdiction] = requirements

    def known_jurisdictions(self) -> list[str]:
        """Return a sorted list of all known jurisdiction codes.

        Returns
        -------
        list[str]
            All jurisdiction identifiers available in this mapper.
        """
        return sorted(self._jurisdictions)

    def jurisdictions_requiring_localisation(self) -> list[str]:
        """Return jurisdictions that mandate data localisation.

        Returns
        -------
        list[str]
            Sorted list of jurisdiction codes with requires_data_localisation=True.
        """
        return sorted(
            j for j, r in self._jurisdictions.items() if r.requires_data_localisation
        )

    def jurisdictions_allowing_transfers(self) -> list[str]:
        """Return jurisdictions that permit cross-border data transfers.

        Returns
        -------
        list[str]
            Sorted list of jurisdiction codes allowing transfers (with conditions).
        """
        return sorted(
            j for j, r in self._jurisdictions.items() if r.allows_cross_border_transfers
        )


__all__ = [
    "JurisdictionMapper",
    "JurisdictionRequirements",
]
