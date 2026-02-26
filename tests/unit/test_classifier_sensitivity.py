"""Unit tests for agent_sovereign.classifier.sensitivity."""
from __future__ import annotations

import pytest

from agent_sovereign.classifier.levels import SovereigntyLevel
from agent_sovereign.classifier.sensitivity import (
    DATA_SENSITIVITY,
    DataSensitivityDetector,
    DetectionResult,
)


class TestDataSensitivityMapping:
    def test_public_info_scores_one(self) -> None:
        assert DATA_SENSITIVITY["public_info"] == 1

    def test_classified_scores_seven(self) -> None:
        assert DATA_SENSITIVITY["classified"] == 7

    def test_phi_scores_five(self) -> None:
        assert DATA_SENSITIVITY["phi"] == 5

    def test_medical_records_scores_four(self) -> None:
        assert DATA_SENSITIVITY["medical_records"] == 4

    def test_financial_data_scores_three(self) -> None:
        assert DATA_SENSITIVITY["financial_data"] == 3

    def test_biometric_data_scores_five(self) -> None:
        assert DATA_SENSITIVITY["biometric_data"] == 5

    def test_itar_technical_data_scores_seven(self) -> None:
        assert DATA_SENSITIVITY["itar_technical_data"] == 7


class TestDetectionResult:
    def test_default_sovereignty_level_is_l1(self) -> None:
        result = DetectionResult()
        assert result.sovereignty_level == SovereigntyLevel.L1_CLOUD

    def test_default_max_level_is_one(self) -> None:
        result = DetectionResult()
        assert result.max_level == 1

    def test_default_detected_types_is_empty(self) -> None:
        result = DetectionResult()
        assert result.detected_types == []


class TestDataSensitivityDetectorScan:
    def setup_method(self) -> None:
        self.detector = DataSensitivityDetector()

    def test_scan_empty_string_returns_l1(self) -> None:
        result = self.detector.scan("")
        assert result.sovereignty_level == SovereigntyLevel.L1_CLOUD
        assert result.detected_types == []

    def test_scan_plain_text_returns_l1(self) -> None:
        result = self.detector.scan("The quick brown fox jumps over the lazy dog.")
        assert result.sovereignty_level == SovereigntyLevel.L1_CLOUD

    def test_scan_detects_email_address(self) -> None:
        result = self.detector.scan("Contact us at alice@example.com for support.")
        assert "customer_email" in result.detected_types

    def test_scan_email_sets_level_two(self) -> None:
        result = self.detector.scan("Email: bob@company.org")
        assert result.max_level >= 2

    def test_scan_detects_pci_card_number(self) -> None:
        result = self.detector.scan("Card number: 4111111111111111")
        assert "pci_card_data" in result.detected_types

    def test_scan_detects_cvv_keyword(self) -> None:
        result = self.detector.scan("Enter your CVV to complete the transaction.")
        assert "pci_card_data" in result.detected_types

    def test_scan_detects_medical_records(self) -> None:
        result = self.detector.scan("Patient diagnosis: ICD-10 code J18.9")
        assert "medical_records" in result.detected_types

    def test_scan_detects_patient_id(self) -> None:
        result = self.detector.scan("The patient record contains a patient ID.")
        assert "medical_records" in result.detected_types

    def test_scan_detects_phi_ssn_format(self) -> None:
        result = self.detector.scan("SSN: 123-45-6789")
        assert "phi" in result.detected_types

    def test_scan_detects_phi_keyword(self) -> None:
        result = self.detector.scan("This document contains protected health information.")
        assert "phi" in result.detected_types

    def test_scan_detects_biometric_data(self) -> None:
        result = self.detector.scan("The system uses fingerprint recognition.")
        assert "biometric_data" in result.detected_types

    def test_scan_detects_genetic_data(self) -> None:
        result = self.detector.scan("The genome sequence was analysed for SNP variants.")
        assert "genetic_data" in result.detected_types

    def test_scan_detects_classified_marker(self) -> None:
        result = self.detector.scan("TOP SECRET document regarding national security.")
        assert "classified" in result.detected_types
        assert result.sovereignty_level == SovereigntyLevel.L7_AIRGAPPED

    def test_scan_detects_itar(self) -> None:
        result = self.detector.scan("This item is ITAR controlled under USML Category XV.")
        assert "itar_technical_data" in result.detected_types

    def test_scan_detects_financial_routing_number(self) -> None:
        result = self.detector.scan("Routing number provided for wire transfer.")
        assert "financial_data" in result.detected_types

    def test_scan_detected_types_are_sorted(self) -> None:
        result = self.detector.scan(
            "Email: test@test.com. Routing number for wire transfer."
        )
        assert result.detected_types == sorted(result.detected_types)

    def test_scan_evidence_keys_match_detected_types(self) -> None:
        result = self.detector.scan("Email: test@example.com for billing.")
        for data_type in result.detected_types:
            assert data_type in result.evidence

    def test_scan_max_level_reflects_highest_type(self) -> None:
        # Classified = 7, should dominate
        result = self.detector.scan(
            "Email: a@b.com. TOP SECRET clearance required."
        )
        assert result.max_level == 7

    def test_scan_phi_dominates_over_medical_records(self) -> None:
        result = self.detector.scan(
            "Patient record with date of birth and diagnosis."
        )
        # PHI scores 5, medical_records scores 4
        assert result.max_level >= 4


class TestDataSensitivityDetectorScoreDataTypes:
    def setup_method(self) -> None:
        self.detector = DataSensitivityDetector()

    def test_empty_list_returns_one(self) -> None:
        assert self.detector.score_data_types([]) == 1

    def test_single_known_type_returns_its_score(self) -> None:
        assert self.detector.score_data_types(["medical_records"]) == 4

    def test_multiple_types_returns_max(self) -> None:
        score = self.detector.score_data_types(["employee_data", "phi"])
        assert score == 5  # phi=5 > employee_data=2

    def test_unknown_type_defaults_to_one(self) -> None:
        assert self.detector.score_data_types(["nonexistent_type"]) == 1

    def test_classified_returns_seven(self) -> None:
        assert self.detector.score_data_types(["classified"]) == 7


class TestDataSensitivityDetectorCustomisation:
    def test_custom_score_overrides_builtin(self) -> None:
        detector = DataSensitivityDetector(custom_scores={"phi": 6})
        assert detector.score_data_types(["phi"]) == 6

    def test_custom_pattern_is_detected(self) -> None:
        import re

        custom_patterns = {"financial_data": [re.compile(r"\bPROPRIETARY\b")]}
        detector = DataSensitivityDetector(custom_patterns=custom_patterns)
        result = detector.scan("This is PROPRIETARY corporate information.")
        assert "financial_data" in result.detected_types

    def test_custom_new_data_type_with_score(self) -> None:
        import re

        custom_patterns = {"trade_secret": [re.compile(r"\bTRADE_SECRET\b")]}
        custom_scores = {"trade_secret": 6}
        detector = DataSensitivityDetector(
            custom_patterns=custom_patterns,
            custom_scores=custom_scores,
        )
        result = detector.scan("Document contains TRADE_SECRET information.")
        assert "trade_secret" in result.detected_types
        assert result.max_level == 6
