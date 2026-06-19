"""
MFA Detector for Web Automation

Detects multi-factor authentication inputs on web pages using multiple strategies.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class MFAInputType(Enum):
    """Types of MFA inputs"""

    TOTP = "totp"  # Time-based one-time password (6-8 digits)
    SMS = "sms"  # SMS verification code
    EMAIL = "email"  # Email verification code
    PUSH = "push"  # Push notification approval
    RECOVERY = "recovery"  # Recovery code/backup code
    UNKNOWN = "unknown"


@dataclass
class MFAField:
    """Represents a detected MFA input field"""

    element_id: str
    input_type: MFAInputType
    label: str | None = None
    placeholder: str | None = None
    name: str | None = None
    max_length: int | None = None
    input_mode: str | None = None
    confidence: float = 0.0  # 0.0 to 1.0


@dataclass
class MFADetectionResult:
    """Result of MFA detection on a page"""

    has_mfa: bool
    mfa_fields: list[MFAField]
    detection_methods: list[str]  # Which strategies detected MFA
    confidence: float  # Overall confidence score
    page_type: str | None = None  # "login", "mfa", "registration", etc.


class MFADetector:
    """
    Detects MFA inputs using multiple strategies:
    1. Keyword-based (field names, labels, hints)
    2. DOM attribute analysis (autocomplete, inputmode, maxlength)
    3. Page structure analysis
    4. Heuristic pattern matching
    """

    # MFA-related keywords
    MFA_KEYWORDS = {
        "totp": [
            "authenticator",
            "verification code",
            "verify code",
            "auth code",
            "two-factor",
            "2fa",
            "mfa",
            "multi-factor",
            "totp",
            "otp",
            "authenticator app",
            "authentication code",
            "security code",
        ],
        "sms": [
            "sms",
            "text message",
            "phone verification",
            "mobile code",
            "verify phone",
            "phone code",
            "sms code",
            "text message code",
            "mobile verification",
            "phone verification code",
            "sms code",
            "verification sms",
        ],
        "email": [
            "email code",
            "email verification",
            "verify email",
            "email token",
            "check your email",
            "email otp",
            "email verification code",
            "verification email",
            "email authentication",
        ],
        "recovery": [
            "recovery code",
            "backup code",
            "recovery key",
            "backup key",
            "recovery phrase",
            "restore code",
        ],
    }

    # Patterns that strongly indicate MFA
    MFA_PATTERNS = [
        r"\b(enter|type|input|provide).*?\d+.*?(digit|code|token)\b",
        r"\b\d{6}\b.*?(code|token|authentication)",
        r"\bverification\b.*?\bcode\b",
        r"\bauthenticator\b.*?\bcode\b",
        r"\b2fa\b.*?\bcode\b",
        r"\bmfa\b.*?\bcode\b",
    ]

    # DOM attributes that indicate MFA
    MFA_DOM_ATTRIBUTES = {
        "autocomplete": ["one-time-code", "otp", "verification-code"],
        "inputmode": ["numeric", "tel"],
        "maxlength": [6, 7, 8],  # Common TOTP lengths
        "name_pattern": [
            "otp",
            "code",
            "token",
            "mfa",
            "2fa",
            "totp",
            "verification",
            "authenticator",
            "challenge",
        ],
        "id_pattern": [
            "otp",
            "code",
            "token",
            "mfa",
            "2fa",
            "totp",
            "verification",
            "authenticator",
        ],
    }

    def __init__(self):
        self.detection_history: list[MFADetectionResult] = []

    def detect_mfa(self, page_data: dict[str, Any]) -> MFADetectionResult:
        """
        Detect MFA on a page using multiple strategies.

        Args:
            page_data: Dictionary containing page information:
                - url: Page URL
                - title: Page title
                - inputs: List of input field data
                - forms: List of form data
                - text: Page text content

        Returns:
            MFADetectionResult with detection results
        """
        inputs = page_data.get("inputs", [])
        forms = page_data.get("forms", [])
        text = page_data.get("text", "")
        url = page_data.get("url", "")

        detection_methods = []
        all_mfa_fields = []

        # Strategy 1: Keyword-based detection
        keyword_fields = self._detect_by_keywords(inputs, text)
        if keyword_fields:
            detection_methods.append("keywords")
            all_mfa_fields.extend(keyword_fields)

        # Strategy 2: DOM attribute analysis
        dom_fields = self._detect_by_dom_attributes(inputs)
        if dom_fields:
            detection_methods.append("dom_attributes")
            all_mfa_fields.extend(dom_fields)

        # Strategy 3: Page structure analysis
        structure_fields = self._detect_by_structure(forms, inputs, text, url)
        if structure_fields:
            detection_methods.append("structure")
            all_mfa_fields.extend(structure_fields)

        # Strategy 4: Heuristic pattern matching
        pattern_fields = self._detect_by_patterns(text, inputs)
        if pattern_fields:
            detection_methods.append("patterns")
            all_mfa_fields.extend(pattern_fields)

        # Deduplicate and merge MFA fields
        unique_fields = self._merge_mfa_fields(all_mfa_fields)

        # Calculate overall confidence
        confidence = self._calculate_confidence(unique_fields, detection_methods)

        # Determine page type
        page_type = self._classify_page_type(text, url, forms)

        result = MFADetectionResult(
            has_mfa=len(unique_fields) > 0,
            mfa_fields=unique_fields,
            detection_methods=detection_methods,
            confidence=confidence,
            page_type=page_type,
        )

        self.detection_history.append(result)
        return result

    def _detect_by_keywords(self, inputs: list[dict], text: str) -> list[MFAField]:
        """Detect MFA fields using keyword matching"""
        mfa_fields = []
        text_lower = text.lower()

        for inp in inputs:
            if inp.get("type", "") == "hidden":
                continue

            # Check all text attributes for MFA keywords
            search_text = " ".join(
                [
                    inp.get("name", ""),
                    inp.get("id", ""),
                    inp.get("label", ""),
                    inp.get("placeholder", ""),
                    inp.get("aria-label", ""),
                    inp.get("title", ""),
                ]
            ).lower()

            # Check each MFA type
            for mfa_type, keywords in self.MFA_KEYWORDS.items():
                for keyword in keywords:
                    if keyword in search_text or keyword in text_lower:
                        # Determine confidence based on match quality
                        confidence = 0.6
                        if keyword in search_text:
                            confidence = 0.8
                        if "code" in keyword or "token" in keyword:
                            confidence += 0.1

                        mfa_field = MFAField(
                            element_id=inp.get("id", ""),
                            input_type=MFAInputType[mfa_type.upper()],
                            label=inp.get("label"),
                            placeholder=inp.get("placeholder"),
                            name=inp.get("name"),
                            max_length=inp.get("maxlength"),
                            input_mode=inp.get("inputmode"),
                            confidence=min(confidence, 1.0),
                        )
                        mfa_fields.append(mfa_field)
                        break

        return mfa_fields

    def _detect_by_dom_attributes(self, inputs: list[dict]) -> list[MFAField]:
        """Detect MFA fields using DOM attribute analysis"""
        mfa_fields = []

        for inp in inputs:
            if inp.get("type", "") == "hidden":
                continue

            confidence = 0.0

            # Check autocomplete attribute
            autocomplete = inp.get("autocomplete", "")
            if autocomplete in self.MFA_DOM_ATTRIBUTES["autocomplete"]:
                confidence = max(confidence, 0.9)

            # Check inputmode
            inputmode = inp.get("inputmode", "")
            if inputmode in self.MFA_DOM_ATTRIBUTES["inputmode"]:
                confidence = max(confidence, 0.7)

            # Check maxlength
            maxlength = inp.get("maxlength")
            if maxlength and int(maxlength) in self.MFA_DOM_ATTRIBUTES["maxlength"]:
                confidence = max(confidence, 0.6)

            # Check name/id patterns
            name = inp.get("name", "").lower()
            inp_id = inp.get("id", "").lower()
            for pattern in self.MFA_DOM_ATTRIBUTES["name_pattern"]:
                if pattern in name or pattern in inp_id:
                    confidence = max(confidence, 0.5)
                    break

            # Determine MFA type based on attributes
            if confidence > 0.5:
                mfa_type = self._classify_mfa_type(inp)

                mfa_field = MFAField(
                    element_id=inp.get("id", ""),
                    input_type=mfa_type,
                    label=inp.get("label"),
                    placeholder=inp.get("placeholder"),
                    name=inp.get("name"),
                    max_length=inp.get("maxlength"),
                    input_mode=inp.get("inputmode"),
                    confidence=confidence,
                )
                mfa_fields.append(mfa_field)

        return mfa_fields

    def _detect_by_structure(
        self, forms: list[dict], inputs: list[dict], text: str, url: str
    ) -> list[MFAField]:
        """Detect MFA using page structure analysis"""
        mfa_fields = []
        text_lower = text.lower()

        # Check if this is a login/mfa page
        is_login_page = (
            "login" in url.lower()
            or "signin" in url.lower()
            or "sign-in" in url.lower()
            or "auth" in url.lower()
            or "verify" in url.lower()
            or "mfa" in url.lower()
            or "2fa" in url.lower()
        )

        has_login_keywords = any(
            kw in text_lower for kw in ["sign in", "login", "log in", "authenticate", "verify"]
        )

        has_mfa_keywords = any(
            kw in text_lower for kw in ["verification code", "authenticator", "2fa", "mfa", "otp"]
        )

        # Look for small numeric inputs near login forms
        for inp in inputs:
            if inp.get("type", "") == "hidden":
                continue

            maxlength = inp.get("maxlength")
            inputmode = inp.get("inputmode", "")

            # Small numeric input (likely TOTP)
            if (
                is_login_page
                and has_login_keywords
                and (maxlength and int(maxlength) in [6, 7, 8])
                and inputmode == "numeric"
            ):
                confidence = 0.7
                if has_mfa_keywords:
                    confidence = 0.9

                mfa_field = MFAField(
                    element_id=inp.get("id", ""),
                    input_type=MFAInputType.TOTP,
                    label=inp.get("label"),
                    placeholder=inp.get("placeholder"),
                    name=inp.get("name"),
                    max_length=maxlength,
                    input_mode=inputmode,
                    confidence=confidence,
                )
                mfa_fields.append(mfa_field)

        return mfa_fields

    def _detect_by_patterns(self, text: str, inputs: list[dict]) -> list[MFAField]:
        """Detect MFA using heuristic pattern matching"""
        mfa_fields = []
        text_lower = text.lower()

        # Check for MFA-related patterns
        for pattern in self.MFA_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                # Look for corresponding input field
                for inp in inputs:
                    if inp.get("type", "") in ["text", "tel", "number"]:
                        # Found potential MFA input
                        mfa_type = self._classify_mfa_type(inp)

                        mfa_field = MFAField(
                            element_id=inp.get("id", ""),
                            input_type=mfa_type,
                            label=inp.get("label"),
                            placeholder=inp.get("placeholder"),
                            name=inp.get("name"),
                            max_length=inp.get("maxlength"),
                            input_mode=inp.get("inputmode"),
                            confidence=0.6,
                        )
                        mfa_fields.append(mfa_field)
                        break

        return mfa_fields

    def _classify_mfa_type(self, inp: dict) -> MFAInputType:
        """Classify the type of MFA input"""
        search_text = " ".join(
            [
                inp.get("name", ""),
                inp.get("id", ""),
                inp.get("label", ""),
                inp.get("placeholder", ""),
            ]
        ).lower()

        # Check for SMS
        if any(kw in search_text for kw in ["sms", "text", "phone", "mobile"]):
            return MFAInputType.SMS

        # Check for email
        if any(kw in search_text for kw in ["email", "mail"]):
            return MFAInputType.EMAIL

        # Check for recovery
        if any(kw in search_text for kw in ["recovery", "backup", "restore"]):
            return MFAInputType.RECOVERY

        # Default to TOTP
        return MFAInputType.TOTP

    def _merge_mfa_fields(self, fields: list[MFAField]) -> list[MFAField]:
        """Merge duplicate MFA fields and average confidence"""
        unique_fields = {}

        # Priority order for MFA types (specific to generic)
        type_priority = {
            MFAInputType.SMS: 3,
            MFAInputType.EMAIL: 3,
            MFAInputType.RECOVERY: 2,
            MFAInputType.TOTP: 1,
            MFAInputType.PUSH: 1,
            MFAInputType.UNKNOWN: 0,
        }

        for field in fields:
            key = field.element_id or field.name or field.label
            if key in unique_fields:
                existing = unique_fields[key]
                # Choose the field with higher priority type
                if type_priority.get(field.input_type, 0) > type_priority.get(
                    existing.input_type, 0
                ):
                    unique_fields[key] = field
                    # Average confidence when keeping the higher priority type
                    field.confidence = (field.confidence + existing.confidence) / 2
                else:
                    # Keep existing, average confidence
                    existing.confidence = (existing.confidence + field.confidence) / 2
            else:
                unique_fields[key] = field

        return list(unique_fields.values())

    def _calculate_confidence(self, fields: list[MFAField], methods: list[str]) -> float:
        """Calculate overall detection confidence"""
        if not fields:
            return 0.0

        # Average field confidence
        avg_field_confidence = sum(f.confidence for f in fields) / len(fields)

        # Boost based on number of detection methods
        method_boost = len(methods) * 0.1

        return min(avg_field_confidence + method_boost, 1.0)

    def _classify_page_type(self, text: str, url: str, forms: list[dict]) -> str | None:
        """Classify the type of page"""
        text_lower = text.lower()
        url_lower = url.lower()

        # Check for MFA page
        if any(
            kw in text_lower or kw in url_lower
            for kw in ["verification", "mfa", "2fa", "authenticator", "otp"]
        ):
            return "mfa"

        # Check for login page
        if any(
            kw in text_lower or kw in url_lower for kw in ["login", "signin", "sign-in", "auth"]
        ):
            return "login"

        # Check for registration
        if any(
            kw in text_lower or kw in url_lower
            for kw in ["register", "signup", "sign-up", "create account"]
        ):
            return "registration"

        return None


def detect_mfa(page_data: dict[str, Any]) -> MFADetectionResult:
    """
    Convenience function to detect MFA on a page.

    Args:
        page_data: Dictionary containing page information

    Returns:
        MFADetectionResult with detection results
    """
    detector = MFADetector()
    return detector.detect_mfa(page_data)
