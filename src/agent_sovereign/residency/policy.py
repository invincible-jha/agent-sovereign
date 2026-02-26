"""Data residency policy definitions and checker.

Defines the DataResidencyPolicy dataclass and ResidencyChecker which validates
whether a target deployment location satisfies the residency policy requirements.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DataResidencyPolicy:
    """Policy specifying where data may reside.

    Attributes
    ----------
    policy_id:
        Unique identifier for this policy (e.g. "eu-gdpr-strict").
    allowed_regions:
        Explicit list of permitted deployment regions or countries.
        If non-empty, data may ONLY reside in these locations.
        ISO 3166-1 alpha-2 country codes or region identifiers (e.g. "EU", "US").
    blocked_regions:
        Explicit list of regions where data must NOT reside.
    require_same_jurisdiction:
        When True, all replicas must remain within a single jurisdiction.
    require_data_localisation:
        When True, data must remain within the country of origin (no cross-border transfers).
    allowed_jurisdictions:
        Set of legal jurisdictions that are acceptable (e.g. {"EU", "EEA"}).
    description:
        Human-readable description of this policy's intent.
    metadata:
        Additional key/value context for the policy.
    """

    policy_id: str
    allowed_regions: list[str] = field(default_factory=list)
    blocked_regions: list[str] = field(default_factory=list)
    require_same_jurisdiction: bool = False
    require_data_localisation: bool = False
    allowed_jurisdictions: list[str] = field(default_factory=list)
    description: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


# Mapping from region/country code to its governing jurisdiction
_REGION_TO_JURISDICTION: dict[str, str] = {
    # EU / EEA members
    "AT": "EU", "BE": "EU", "BG": "EU", "CY": "EU", "CZ": "EU",
    "DE": "EU", "DK": "EU", "EE": "EU", "ES": "EU", "FI": "EU",
    "FR": "EU", "GR": "EU", "HR": "EU", "HU": "EU", "IE": "EU",
    "IT": "EU", "LT": "EU", "LU": "EU", "LV": "EU", "MT": "EU",
    "NL": "EU", "PL": "EU", "PT": "EU", "RO": "EU", "SE": "EU",
    "SI": "EU", "SK": "EU", "IS": "EEA", "LI": "EEA", "NO": "EEA",
    "EU": "EU", "EEA": "EEA",
    # United Kingdom
    "GB": "UK", "UK": "UK",
    # United States
    "US": "US",
    # China
    "CN": "CN",
    # India
    "IN": "IN",
    # Brazil
    "BR": "BR",
    # Australia
    "AU": "AU",
    # Canada
    "CA": "CA",
    # Japan
    "JP": "JP",
    # Singapore
    "SG": "SG",
    # Switzerland (FADP - adequacy)
    "CH": "CH",
    # South Korea (PIPA)
    "KR": "KR",
}


class ResidencyChecker:
    """Checks whether a deployment location satisfies a data residency policy.

    Parameters
    ----------
    region_jurisdiction_map:
        Optional override or extension of the built-in region-to-jurisdiction
        mapping. Keys are region codes, values are jurisdiction identifiers.
    """

    def __init__(
        self,
        region_jurisdiction_map: dict[str, str] | None = None,
    ) -> None:
        self._jurisdiction_map: dict[str, str] = dict(_REGION_TO_JURISDICTION)
        if region_jurisdiction_map:
            self._jurisdiction_map.update(region_jurisdiction_map)

    def check(self, location: str, policy: DataResidencyPolicy) -> bool:
        """Check whether a deployment location satisfies the policy.

        Evaluates the following rules in order:
        1. If location is in blocked_regions, return False.
        2. If allowed_regions is non-empty and location is not in it, return False.
        3. If allowed_jurisdictions is non-empty and the location's jurisdiction
           is not in allowed_jurisdictions, return False.
        4. If require_data_localisation is True, verify the location's
           jurisdiction matches the jurisdiction implied by allowed_regions.

        Parameters
        ----------
        location:
            The deployment location (region or country code, e.g. "DE", "US").
        policy:
            The DataResidencyPolicy to evaluate against.

        Returns
        -------
        bool
            True if the location satisfies all policy constraints.
        """
        if location in policy.blocked_regions:
            return False

        if policy.allowed_regions and location not in policy.allowed_regions:
            # Also allow if the location is a country in an allowed region group
            location_jurisdiction = self._jurisdiction_map.get(location, location)
            if location_jurisdiction not in policy.allowed_regions:
                return False

        if policy.allowed_jurisdictions:
            location_jurisdiction = self._jurisdiction_map.get(location, location)
            jurisdiction_ok = (
                location_jurisdiction in policy.allowed_jurisdictions
                or location in policy.allowed_jurisdictions
            )
            if not jurisdiction_ok:
                return False

        return True

    def get_compliant_regions(self, policy: DataResidencyPolicy) -> list[str]:
        """Return all known regions that comply with the given policy.

        Parameters
        ----------
        policy:
            The DataResidencyPolicy to evaluate.

        Returns
        -------
        list[str]
            Sorted list of region codes that satisfy the policy.
        """
        all_regions = list(self._jurisdiction_map.keys())
        return sorted(
            region for region in all_regions if self.check(region, policy)
        )

    def get_jurisdiction(self, region: str) -> str | None:
        """Return the legal jurisdiction for a region code.

        Parameters
        ----------
        region:
            Region or country code to look up.

        Returns
        -------
        str | None
            The governing jurisdiction, or None if the region is unknown.
        """
        return self._jurisdiction_map.get(region)

    def known_regions(self) -> list[str]:
        """Return a sorted list of all known region codes.

        Returns
        -------
        list[str]
            All region/country codes in the jurisdiction map.
        """
        return sorted(self._jurisdiction_map)


__all__ = [
    "DataResidencyPolicy",
    "ResidencyChecker",
]
