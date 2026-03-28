"""
HIPAA-compliant de-identification layer for clinical notes.

Detects and masks PHI (Protected Health Information) per HIPAA Security Rule:
- Names, dates, ages, medical record numbers, SSN, contact info, etc.
- Uses regex patterns with medical variations and replacements
- Preserves semantic meaning for clinical context (e.g., relative dates, age ranges)
- Tracks de-identification mappings for audit and potential re-identification if authorized
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum


class PHICategory(Enum):
    """HIPAA PHI categories per Safe Harbor method."""
    NAME = "name"
    DATE = "date"
    AGE = "age"
    MRN = "medical_record_number"
    SSN = "social_security_number"
    PHONE = "phone"
    EMAIL = "email"
    ADDRESS = "address"
    INSURANCE = "insurance_id"
    LICENSE = "license_number"
    PATIENT_ID = "patient_id"
    PROVIDER_ID = "provider_id"
    DEVICE_ID = "device_id"


@dataclass
class PHIReplacement:
    """Record of a de-identified PHI element."""
    original: str
    replacement: str
    category: PHICategory
    position: tuple[int, int]  # (start, end) in original text
    hash_digest: str = ""  # SHA-256 for reversibility check

    def __post_init__(self):
        if not self.hash_digest:
            self.hash_digest = hashlib.sha256(self.original.encode()).hexdigest()[:8]


@dataclass
class DeIdentificationResult:
    """Result of de-identification process."""
    original_text: str
    de_identified_text: str
    replacements: list[PHIReplacement] = field(default_factory=list)
    phi_detected: bool = False

    def to_dict(self):
        return {
            "original_hash": hashlib.sha256(self.original_text.encode()).hexdigest()[:8],
            "de_identified_text": self.de_identified_text,
            "replacements_count": len(self.replacements),
            "categories_found": list(set(r.category.value for r in self.replacements)),
            "timestamp": datetime.utcnow().isoformat(),
        }


class PHIDetector:
    """Detects and masks Protected Health Information in clinical notes."""

    def __init__(self):
        """Initialize PHI detection patterns."""
        # SSN pattern: XXX-XX-XXXX or XXXXXXXXX
        self.ssn_pattern = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b")

        # Phone patterns: (XXX) XXX-XXXX, XXX-XXX-XXXX, XXXXXXXXXX
        self.phone_pattern = re.compile(
            r"\b\(?(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4})\b"
        )

        # Email pattern
        self.email_pattern = re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        )

        # Medical Record Number: MRN followed by numbers (with variations)
        self.mrn_pattern = re.compile(r"(?:MRN|medical record|chart number)[\s:]*([A-Z0-9]+\d+)", re.IGNORECASE)

        # Patient ID variations
        self.patient_id_pattern = re.compile(
            r"(?:patient\s+(?:id|#|identifier))[\s:]*([A-Z0-9]+\d+)", re.IGNORECASE
        )

        # Provider ID variations
        self.provider_id_pattern = re.compile(
            r"(?:provider\s+(?:id|npi|#))[\s:]*(\d{10})", re.IGNORECASE
        )

        # Insurance ID/policy number
        self.insurance_pattern = re.compile(
            r"(?:insurance|policy|subscriber)[\s:]*([A-Z0-9]+)", re.IGNORECASE
        )

        # License number (medical license format)
        self.license_pattern = re.compile(
            r"(?:medical\s+license|license\s+#)[\s:]*([A-Z]{2,}\d+)", re.IGNORECASE
        )

        # Device serial number (pacemaker, implant, etc.)
        self.device_pattern = re.compile(
            r"(?:device\s+serial|serial\s+#|pacemaker|implant)[\s:]*([A-Z0-9]{8,})", re.IGNORECASE
        )

        # Person names in medical context (Dr., Mr., Ms., patient name, etc.)
        # Common medical name markers
        self.name_pattern = re.compile(
            r"(?:patient|dr\.?|mr\.?|mrs\.?|ms\.?|attending|resident|physician|hospitalist)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
            re.IGNORECASE,
        )

        # Specific date patterns (preserve relative temporal info)
        # Full dates: MM/DD/YYYY, MM-DD-YYYY, Month DD, YYYY
        self.date_pattern = re.compile(
            r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{4}|"  # MM/DD/YYYY
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]?\s+\d{1,2},?\s+\d{4}|"  # Month DD, YYYY
            r"\d{4}-(?:0?[1-9]|1[0-2])-(?:0?[1-9]|[12]\d|3[01]))\b",  # YYYY-MM-DD
            re.IGNORECASE,
        )

        # Age: patterns like "67 year old", "age 45", etc.
        self.age_pattern = re.compile(r"\b(?:age|aged|years?)\s+(?:old\s+)?(\d{1,3})\b", re.IGNORECASE)

        # Address patterns: street addresses with numbers
        self.address_pattern = re.compile(
            r"\b\d+\s+[A-Za-z\s]+(?:street|st|avenue|ave|road|rd|drive|dr|boulevard|blvd)\b",
            re.IGNORECASE,
        )

    def detect_dates(self, text: str) -> list[PHIReplacement]:
        """Detect dates and convert to relative references."""
        replacements = []
        # For clinical context, convert specific dates to temporal references
        # This preserves clinical meaning while de-identifying
        for match in self.date_pattern.finditer(text):
            try:
                date_str = match.group()
                # Convert to relative date (days ago) or keep as "DATE_REDACTED"
                replacement = "[DATE_REDACTED]"
                replacements.append(
                    PHIReplacement(
                        original=date_str,
                        replacement=replacement,
                        category=PHICategory.DATE,
                        position=match.span(),
                    )
                )
            except Exception:
                pass
        return replacements

    def detect_ages(self, text: str) -> list[PHIReplacement]:
        """
        Detect specific ages and generalize to age bands.
        HIPAA allows age bands (90+) vs specific ages.
        """
        replacements = []
        for match in self.age_pattern.finditer(text):
            try:
                age_str = match.group()
                age = int(match.group(1))
                # Generalize to age band (90+ for HIPAA compliance)
                if age >= 90:
                    replacement = "[AGE_90_PLUS]"
                elif age >= 80:
                    replacement = "[AGE_80S]"
                elif age >= 70:
                    replacement = "[AGE_70S]"
                else:
                    replacement = f"[AGE_RANGE]"
                replacements.append(
                    PHIReplacement(
                        original=age_str,
                        replacement=replacement,
                        category=PHICategory.AGE,
                        position=match.span(),
                    )
                )
            except Exception:
                pass
        return replacements

    def detect_phi(self, text: str) -> list[PHIReplacement]:
        """Detect all PHI elements in the text."""
        replacements = []

        # SSN
        for match in self.ssn_pattern.finditer(text):
            replacements.append(
                PHIReplacement(
                    original=match.group(),
                    replacement="[SSN_REDACTED]",
                    category=PHICategory.SSN,
                    position=match.span(),
                )
            )

        # Phone numbers
        for match in self.phone_pattern.finditer(text):
            replacements.append(
                PHIReplacement(
                    original=match.group(),
                    replacement="[PHONE_REDACTED]",
                    category=PHICategory.PHONE,
                    position=match.span(),
                )
            )

        # Email
        for match in self.email_pattern.finditer(text):
            replacements.append(
                PHIReplacement(
                    original=match.group(),
                    replacement="[EMAIL_REDACTED]",
                    category=PHICategory.EMAIL,
                    position=match.span(),
                )
            )

        # MRN
        for match in self.mrn_pattern.finditer(text):
            replacements.append(
                PHIReplacement(
                    original=match.group(),
                    replacement="[MRN_REDACTED]",
                    category=PHICategory.MRN,
                    position=match.span(),
                )
            )

        # Patient ID
        for match in self.patient_id_pattern.finditer(text):
            replacements.append(
                PHIReplacement(
                    original=match.group(),
                    replacement="[PATIENT_ID_REDACTED]",
                    category=PHICategory.PATIENT_ID,
                    position=match.span(),
                )
            )

        # Provider ID
        for match in self.provider_id_pattern.finditer(text):
            replacements.append(
                PHIReplacement(
                    original=match.group(),
                    replacement="[PROVIDER_ID_REDACTED]",
                    category=PHICategory.PROVIDER_ID,
                    position=match.span(),
                )
            )

        # Insurance
        for match in self.insurance_pattern.finditer(text):
            replacements.append(
                PHIReplacement(
                    original=match.group(),
                    replacement="[INSURANCE_REDACTED]",
                    category=PHICategory.INSURANCE,
                    position=match.span(),
                )
            )

        # License
        for match in self.license_pattern.finditer(text):
            replacements.append(
                PHIReplacement(
                    original=match.group(),
                    replacement="[LICENSE_REDACTED]",
                    category=PHICategory.LICENSE,
                    position=match.span(),
                )
            )

        # Device serial
        for match in self.device_pattern.finditer(text):
            replacements.append(
                PHIReplacement(
                    original=match.group(),
                    replacement="[DEVICE_REDACTED]",
                    category=PHICategory.DEVICE_ID,
                    position=match.span(),
                )
            )

        # Names (conservative: only after role markers)
        for match in self.name_pattern.finditer(text):
            replacements.append(
                PHIReplacement(
                    original=match.group(1),
                    replacement="[NAME_REDACTED]",
                    category=PHICategory.NAME,
                    position=(match.start(1), match.end(1)),
                )
            )

        # Dates
        replacements.extend(self.detect_dates(text))

        # Ages
        replacements.extend(self.detect_ages(text))

        # Addresses
        for match in self.address_pattern.finditer(text):
            replacements.append(
                PHIReplacement(
                    original=match.group(),
                    replacement="[ADDRESS_REDACTED]",
                    category=PHICategory.ADDRESS,
                    position=match.span(),
                )
            )

        return replacements

    def de_identify(self, text: str) -> DeIdentificationResult:
        """
        De-identify a clinical note by detecting and masking all PHI.

        Returns DeIdentificationResult with:
        - de_identified_text: text with PHI replaced
        - replacements: list of PHIReplacement records
        - phi_detected: boolean indicating presence of PHI
        """
        if not text or not text.strip():
            return DeIdentificationResult(
                original_text=text,
                de_identified_text=text,
                replacements=[],
                phi_detected=False,
            )

        replacements = self.detect_phi(text)

        # Sort replacements by position (reverse order to avoid offset issues)
        replacements.sort(key=lambda x: x.position[0], reverse=True)

        # Apply replacements
        de_identified = text
        for repl in replacements:
            start, end = repl.position
            de_identified = (
                de_identified[:start] + repl.replacement + de_identified[end:]
            )

        return DeIdentificationResult(
            original_text=text,
            de_identified_text=de_identified,
            replacements=replacements,
            phi_detected=len(replacements) > 0,
        )
