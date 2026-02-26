"""Data sensitivity detection.

Provides regex-based PII/PHI/classified data detection and a mapping of
data types to sovereignty level scores.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent_sovereign.classifier.levels import SovereigntyLevel

# Maps data type keys to minimum sovereignty level scores.
# Higher scores mean more sensitive data requiring a higher sovereignty level.
DATA_SENSITIVITY: dict[str, int] = {
    "public_info": 1,
    "aggregated_anonymous": 1,
    "internal_communications": 2,
    "customer_email": 2,
    "employee_data": 2,
    "financial_data": 3,
    "pci_card_data": 3,
    "medical_records": 4,
    "phi": 5,
    "biometric_data": 5,
    "genetic_data": 5,
    "classified": 7,
    "itar_technical_data": 7,
    "sci_compartmented": 7,
}

# Regex patterns for each detectable data type.
# Each entry is a list of compiled patterns; a match on ANY pattern triggers detection.
_DETECTION_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "customer_email": [
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    ],
    "pci_card_data": [
        # Visa, Mastercard, Amex, Discover card numbers (simplified Luhn-format)
        re.compile(r"\b(?:4\d{12}(?:\d{3})?|5[1-5]\d{14}|3[47]\d{13}|6011\d{12})\b"),
        re.compile(r"\bcard(?:holder|number|num)\b", re.IGNORECASE),
        re.compile(r"\bcvv\b|\bcvc\b|\bcvv2\b", re.IGNORECASE),
    ],
    "medical_records": [
        re.compile(r"\b(?:diagnosis|prescription|icd[-\s]?\d+|cpt\s*\d{5})\b", re.IGNORECASE),
        re.compile(r"\b(?:patient\s+(?:id|name|record|chart))\b", re.IGNORECASE),
        re.compile(r"\bmrn\b|\behr\b|\bemr\b", re.IGNORECASE),
    ],
    "phi": [
        # HIPAA-covered identifiers beyond basic medical records
        re.compile(
            r"\b(?:ssn|social\s+security|date\s+of\s+birth|dob|health\s+plan"
            r"|beneficiary|account\s+number|certificate\s+number)\b",
            re.IGNORECASE,
        ),
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN pattern
        re.compile(r"\b(?:hip[ao]a|protected\s+health\s+information)\b", re.IGNORECASE),
    ],
    "biometric_data": [
        re.compile(
            r"\b(?:fingerprint|retina\s+scan|iris\s+scan|facial\s+recognition"
            r"|voice\s+print|biometric)\b",
            re.IGNORECASE,
        ),
    ],
    "genetic_data": [
        re.compile(
            r"\b(?:genome|dna\s+sequence|rna\s+sequence|snp|genotype|exome)\b",
            re.IGNORECASE,
        ),
    ],
    "financial_data": [
        re.compile(
            r"\b(?:routing\s+number|account\s+balance|wire\s+transfer|swift\s+code"
            r"|iban|tax\s+return|w[-\s]?2|1099)\b",
            re.IGNORECASE,
        ),
    ],
    "classified": [
        re.compile(
            r"\b(?:top\s+secret|secret//|confidential//|sci|noforn|fouo"
            r"|controlled\s+unclassified)\b",
            re.IGNORECASE,
        ),
    ],
    "itar_technical_data": [
        re.compile(
            r"\b(?:itar|usml|ear\s+controlled|munitions\s+list|export\s+controlled"
            r"|eccn)\b",
            re.IGNORECASE,
        ),
    ],
}


@dataclass
class DetectionResult:
    """Result of a data sensitivity scan."""

    detected_types: list[str] = field(default_factory=list)
    """Data types found in the scanned text."""

    max_level: int = 1
    """Highest sensitivity level score among detected types."""

    sovereignty_level: SovereigntyLevel = SovereigntyLevel.L1_CLOUD
    """Recommended minimum sovereignty level based on detected types."""

    evidence: dict[str, list[str]] = field(default_factory=dict)
    """Map of data type to list of matched pattern strings (redacted)."""


class DataSensitivityDetector:
    """Regex-based detector for PII, PHI, and classified data patterns.

    Scans text for known sensitive data patterns and maps detected types to
    the minimum sovereignty level score defined in DATA_SENSITIVITY.

    Parameters
    ----------
    custom_patterns:
        Optional additional patterns to supplement the built-in set.
        Keys must match entries in DATA_SENSITIVITY or be new types
        accompanied by a score entry.
    custom_scores:
        Optional score overrides or additions for custom data types.
    """

    def __init__(
        self,
        custom_patterns: dict[str, list[re.Pattern[str]]] | None = None,
        custom_scores: dict[str, int] | None = None,
    ) -> None:
        self._patterns: dict[str, list[re.Pattern[str]]] = dict(_DETECTION_PATTERNS)
        if custom_patterns:
            for data_type, patterns in custom_patterns.items():
                existing = self._patterns.get(data_type, [])
                self._patterns[data_type] = existing + patterns

        self._scores: dict[str, int] = dict(DATA_SENSITIVITY)
        if custom_scores:
            self._scores.update(custom_scores)

    def scan(self, text: str) -> DetectionResult:
        """Scan text for sensitive data patterns.

        Parameters
        ----------
        text:
            The string content to scan. May be log lines, document text,
            prompt content, or any plain text.

        Returns
        -------
        DetectionResult
            Aggregated detection findings including detected types,
            max sensitivity score, and recommended sovereignty level.
        """
        detected_types: list[str] = []
        evidence: dict[str, list[str]] = {}
        max_score = 1

        for data_type, patterns in self._patterns.items():
            matches: list[str] = []
            for pattern in patterns:
                found = pattern.findall(text)
                if found:
                    # Redact actual matched values to avoid echoing PII in results
                    matches.append(f"[{pattern.pattern[:40]}...] matched {len(found)} time(s)")

            if matches:
                detected_types.append(data_type)
                evidence[data_type] = matches
                score = self._scores.get(data_type, 1)
                if score > max_score:
                    max_score = score

        sovereignty_level = _score_to_level(max_score)

        return DetectionResult(
            detected_types=sorted(detected_types),
            max_level=max_score,
            sovereignty_level=sovereignty_level,
            evidence=evidence,
        )

    def score_data_types(self, data_types: list[str]) -> int:
        """Return the maximum sensitivity score for a list of data type keys.

        Parameters
        ----------
        data_types:
            List of data type keys (must match entries in DATA_SENSITIVITY
            or custom_scores provided at construction).

        Returns
        -------
        int
            The highest score among the provided data types, or 1 if none match.
        """
        return max((self._scores.get(dt, 1) for dt in data_types), default=1)


def _score_to_level(score: int) -> SovereigntyLevel:
    """Map a numeric sensitivity score to the corresponding SovereigntyLevel.

    Parameters
    ----------
    score:
        Numeric sensitivity score (1–7).

    Returns
    -------
    SovereigntyLevel
        The sovereignty level matching the score, clamped to the valid range.
    """
    clamped = max(1, min(7, score))
    return SovereigntyLevel(clamped)


__all__ = [
    "DATA_SENSITIVITY",
    "DataSensitivityDetector",
    "DetectionResult",
]
