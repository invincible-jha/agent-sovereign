"""Regulatory framework to sovereignty level mapping.

Maps known data-protection and security regulations to their minimum required
sovereignty level. Organisations must meet or exceed these minimums.
"""
from __future__ import annotations

from agent_sovereign.classifier.levels import SovereigntyLevel

# Maps regulation identifier strings to minimum required sovereignty level scores.
# Values correspond to SovereigntyLevel integer values.
REGULATORY_MINIMUMS: dict[str, int] = {
    "GDPR": 6,
    "HIPAA": 3,
    "ITAR": 7,
    "SOX": 3,
    "FERPA": 3,
    "FedRAMP_High": 5,
    "FedRAMP_Moderate": 4,
    "EU_AI_Act_High_Risk": 3,
    "CCPA": 2,
    "PCI_DSS": 3,
    # Additional common frameworks
    "NIST_800_171": 4,
    "CMMC_Level_2": 4,
    "CMMC_Level_3": 5,
    "ISO_27001": 3,
    "SOC2_Type2": 3,
    "FISMA_High": 5,
    "FISMA_Moderate": 4,
}

_REGULATION_DESCRIPTIONS: dict[str, str] = {
    "GDPR": (
        "EU General Data Protection Regulation — requires data residency controls "
        "and subject rights enforcement; maximum-restriction interpretation requires L6."
    ),
    "HIPAA": (
        "US Health Insurance Portability and Accountability Act — requires PHI "
        "protection with access controls and audit logging; minimum L3 hybrid."
    ),
    "ITAR": (
        "International Traffic in Arms Regulations — export-controlled technical data "
        "requires air-gapped deployment; minimum L7."
    ),
    "SOX": (
        "Sarbanes-Oxley Act — financial reporting integrity; requires controlled "
        "access and audit trails; minimum L3."
    ),
    "FERPA": (
        "Family Educational Rights and Privacy Act — student education records "
        "protection; minimum L3."
    ),
    "FedRAMP_High": (
        "FedRAMP High Impact baseline — US federal cloud authorization for high-impact "
        "systems; minimum L5."
    ),
    "FedRAMP_Moderate": (
        "FedRAMP Moderate Impact baseline — US federal cloud authorization for "
        "moderate-impact systems; minimum L4."
    ),
    "EU_AI_Act_High_Risk": (
        "EU AI Act high-risk system requirements — transparency, human oversight, "
        "and accuracy requirements; minimum L3."
    ),
    "CCPA": (
        "California Consumer Privacy Act — consumer data rights; minimum L2."
    ),
    "PCI_DSS": (
        "Payment Card Industry Data Security Standard — cardholder data protection; "
        "minimum L3."
    ),
}


class RegulatoryMapper:
    """Maps regulatory frameworks to minimum sovereignty levels.

    Determines the strictest (highest) sovereignty level required by any
    combination of applicable regulations.

    Parameters
    ----------
    additional_minimums:
        Optional mapping of custom regulation names to integer level scores.
        These augment (and may override) the built-in REGULATORY_MINIMUMS.
    """

    def __init__(self, additional_minimums: dict[str, int] | None = None) -> None:
        self._minimums: dict[str, int] = dict(REGULATORY_MINIMUMS)
        if additional_minimums:
            self._minimums.update(additional_minimums)

    def minimum_level_for(self, regulation: str) -> SovereigntyLevel:
        """Return the minimum sovereignty level required by a single regulation.

        Parameters
        ----------
        regulation:
            Regulation identifier string (e.g. "HIPAA", "GDPR"). Case-sensitive;
            must match a key in REGULATORY_MINIMUMS or custom_minimums.

        Returns
        -------
        SovereigntyLevel
            The minimum sovereignty level for the regulation.

        Raises
        ------
        KeyError
            If the regulation identifier is not recognised.
        """
        if regulation not in self._minimums:
            raise KeyError(
                f"Unknown regulation {regulation!r}. "
                f"Known regulations: {sorted(self._minimums)}"
            )
        return SovereigntyLevel(self._minimums[regulation])

    def combined_minimum(self, regulations: list[str]) -> SovereigntyLevel:
        """Return the highest minimum sovereignty level across all regulations.

        Parameters
        ----------
        regulations:
            List of regulation identifier strings. Unknown identifiers are
            skipped with no error (logged at DEBUG level).

        Returns
        -------
        SovereigntyLevel
            The maximum (strictest) level required by any of the regulations,
            or L1_CLOUD if no regulations are provided or recognised.
        """
        max_score = 1
        for regulation in regulations:
            score = self._minimums.get(regulation)
            if score is not None and score > max_score:
                max_score = score
        return SovereigntyLevel(max_score)

    def drivers_for(self, regulations: list[str]) -> dict[str, SovereigntyLevel]:
        """Return a mapping of each recognised regulation to its minimum level.

        Parameters
        ----------
        regulations:
            List of regulation identifier strings to evaluate.

        Returns
        -------
        dict[str, SovereigntyLevel]
            Only regulations that are recognised are included in the result.
        """
        return {
            reg: SovereigntyLevel(self._minimums[reg])
            for reg in regulations
            if reg in self._minimums
        }

    def describe(self, regulation: str) -> str:
        """Return a human-readable description of a regulation's requirements.

        Parameters
        ----------
        regulation:
            Regulation identifier string.

        Returns
        -------
        str
            Description, or a generic message if no description is available.
        """
        return _REGULATION_DESCRIPTIONS.get(
            regulation,
            f"No description available for {regulation!r}.",
        )

    def known_regulations(self) -> list[str]:
        """Return a sorted list of all known regulation identifiers.

        Returns
        -------
        list[str]
            All regulation keys available in this mapper instance.
        """
        return sorted(self._minimums)


__all__ = [
    "REGULATORY_MINIMUMS",
    "RegulatoryMapper",
]
