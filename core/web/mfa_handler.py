"""
MFA Handler for Web Automation

Handles multi-factor authentication resolution using multiple strategies.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum

import pyotp

from core.web.mfa_detector import MFAField, MFAInputType


class MFAResolutionMethod(Enum):
    """Methods for resolving MFA challenges"""
    USER_PROMPT = "user_prompt"  # Ask user to provide code
    TOTP_AUTO = "totp_auto"  # Auto-generate TOTP from seed
    SMS_RETRIEVAL = "sms_retrieval"  # Auto-retrieve SMS code
    EMAIL_RETRIEVAL = "email_retrieval"  # Auto-retrieve email code
    PUSH_APPROVAL = "push_approval"  # Handle push notification


@dataclass
class MFAResolutionResult:
    """Result of MFA resolution attempt"""
    success: bool
    code_used: str | None
    method_used: MFAResolutionMethod
    error_message: str | None = None
    retry_allowed: bool = True


class TOTPProvider:
    """
    Manages TOTP providers (Google Authenticator, Authy, Microsoft Authenticator).

    Uses the otpkey library for compatibility with all major providers.
    """

    # Supported providers
    PROVIDERS = {
        'google': 'Google Authenticator',
        'authy': 'Authy',
        'microsoft': 'Microsoft Authenticator',
        'duo': 'Duo Mobile',
        'lastpass': 'LastPass Authenticator',
        'yubikey': 'Yubico Authenticator',
        '1password': '1Password',
        'bitwarden': 'Bitwarden'
    }

    def __init__(self):
        self.secrets: dict[str, str] = {}  # {service_name: secret_key}

    def add_secret(self, service: str, secret: str) -> None:
        """
        Add a TOTP secret for a service.

        Args:
            service: Service name (e.g., 'aws', 'github')
            secret: Base32-encoded secret key
        """
        self.secrets[service.lower()] = secret

    def remove_secret(self, service: str) -> None:
        """Remove a TOTP secret"""
        self.secrets.pop(service.lower(), None)

    def get_secret(self, service: str) -> str | None:
        """Get the TOTP secret for a service"""
        return self.secrets.get(service.lower())

    def generate_totp(self, service: str, time_step: int = 30) -> str | None:
        """
        Generate current TOTP code for a service.

        Args:
            service: Service name
            time_step: Time step in seconds (default 30)

        Returns:
            Current 6-digit TOTP code or None if secret not found
        """
        secret = self.get_secret(service)
        if not secret:
            return None

        try:
            totp = pyotp.TOTP(secret)
            return totp.now()
        except Exception as e:
            print(f"Error generating TOTP: {e}")
            return None

    def verify_totp(self, service: str, code: str,
                    valid_window: int = 1) -> bool:
        """
        Verify a TOTP code for a service.

        Args:
            service: Service name
            code: Code to verify
            valid_window: Number of time steps to allow (default 1)

        Returns:
            True if code is valid
        """
        secret = self.get_secret(service)
        if not secret:
            return False

        try:
            totp = pyotp.TOTP(secret)
            return totp.verify(code, valid_window=valid_window)
        except Exception as e:
            print(f"Error verifying TOTP: {e}")
            return False

    def get_time_remaining(self, time_step: int = 30) -> int:
        """
        Get seconds remaining in current TOTP time step.

        Args:
            time_step: Time step in seconds (default 30)

        Returns:
            Seconds remaining (0-30)
        """
        current_time = int(time.time())
        return time_step - (current_time % time_step)

    def list_services(self) -> list:
        """List all services with stored secrets"""
        return list(self.secrets.keys())


class MFAHandler:
    """
    Handles MFA resolution using multiple strategies.

    Resolution strategies (tried in order):
    1. TOTP auto-generation (if user has shared seed)
    2. User prompt (ask user to provide code)
    3. SMS/Email auto-retrieval (if accessible via API)
    """

    def __init__(self):
        self.totp_provider = TOTPProvider()
        self.resolution_history: list = []
        self.max_attempts = 3
        self.code_cache: dict[str, tuple] = {}  # {code: (timestamp, service)}
        self.cache_ttl = 300  # 5 minutes

    def add_totp_secret(self, service: str, secret: str) -> None:
        """Add a TOTP secret for auto-generation"""
        self.totp_provider.add_secret(service, secret)

    def resolve_mfa(self, mfa_field: MFAField, page_url: str,
                   user_callback: Callable[[str], Awaitable[str]] | None = None,
                   service_name: str | None = None) -> MFAResolutionResult:
        """
        Resolve an MFA challenge using available methods.

        Args:
            mfa_field: The MFA field to resolve
            page_url: URL of the current page (for service detection)
            user_callback: Optional async callback to prompt user for code
            service_name: Optional service name for TOTP lookup

        Returns:
            MFAResolutionResult with resolution outcome
        """
        resolution_attempts = []

        # Strategy 1: Try TOTP auto-generation first
        if mfa_field.input_type == MFAInputType.TOTP:
            service = service_name or self._extract_service_from_url(page_url)
            totp_result = self._try_totp_auto(service)
            resolution_attempts.append(totp_result)
            if totp_result.success:
                return totp_result

        # Strategy 2: Prompt user for code
        if user_callback:
            user_result = asyncio.run(self._try_user_prompt(
                mfa_field, user_callback
            ))
            resolution_attempts.append(user_result)
            if user_result.success:
                return user_result

        # Strategy 3: Try SMS/Email retrieval (if applicable)
        if mfa_field.input_type in [MFAInputType.SMS, MFAInputType.EMAIL]:
            retrieval_result = self._try_code_retrieval(mfa_field)
            resolution_attempts.append(retrieval_result)
            if retrieval_result.success:
                return retrieval_result

        # All strategies failed - return best result
        return self._select_best_result(resolution_attempts)

    def _try_totp_auto(self, service: str | None) -> MFAResolutionResult:
        """Try to auto-generate TOTP code"""
        if not service:
            return MFAResolutionResult(
                success=False,
                code_used=None,
                method_used=MFAResolutionMethod.TOTP_AUTO,
                error_message="No service name provided for TOTP lookup",
                retry_allowed=True
            )

        # Check cache first
        cached_code = self._check_cache(service)
        if cached_code:
            return MFAResolutionResult(
                success=True,
                code_used=cached_code,
                method_used=MFAResolutionMethod.TOTP_AUTO
            )

        # Generate new TOTP
        code = self.totp_provider.generate_totp(service)
        if code:
            self._cache_code(service, code)
            return MFAResolutionResult(
                success=True,
                code_used=code,
                method_used=MFAResolutionMethod.TOTP_AUTO
            )

        return MFAResolutionResult(
            success=False,
            code_used=None,
            method_used=MFAResolutionMethod.TOTP_AUTO,
            error_message=f"No TOTP secret found for service: {service}",
            retry_allowed=False
        )

    async def _try_user_prompt(self, mfa_field: MFAField,
                              user_callback: Callable[[str], Awaitable[str]]) -> MFAResolutionResult:
        """Prompt user to provide MFA code"""
        try:
            # Generate prompt based on MFA type
            prompt = self._generate_user_prompt(mfa_field)
            code = await user_callback(prompt)

            if code and code.strip():
                return MFAResolutionResult(
                    success=True,
                    code_used=code.strip(),
                    method_used=MFAResolutionMethod.USER_PROMPT
                )

            return MFAResolutionResult(
                success=False,
                code_used=None,
                method_used=MFAResolutionMethod.USER_PROMPT,
                error_message="User did not provide a code",
                retry_allowed=True
            )
        except Exception as e:
            return MFAResolutionResult(
                success=False,
                code_used=None,
                method_used=MFAResolutionMethod.USER_PROMPT,
                error_message=f"Error prompting user: {str(e)}",
                retry_allowed=True
            )

    def _try_code_retrieval(self, mfa_field: MFAField) -> MFAResolutionResult:
        """
        Try to auto-retrieve SMS/Email code.

        Note: This is a placeholder for future implementation.
        Actual implementation would depend on:
        - SMS: Integration with SMS APIs (Twilio, etc.)
        - Email: Integration with email APIs (Gmail API, etc.)
        """
        method = (
            MFAResolutionMethod.SMS_RETRIEVAL
            if mfa_field.input_type == MFAInputType.SMS
            else MFAResolutionMethod.EMAIL_RETRIEVAL
        )

        return MFAResolutionResult(
            success=False,
            code_used=None,
            method_used=method,
            error_message="Automatic code retrieval not implemented yet",
            retry_allowed=False
        )

    def _generate_user_prompt(self, mfa_field: MFAField) -> str:
        """Generate user-friendly prompt for MFA code"""
        if mfa_field.input_type == MFAInputType.TOTP:
            return (
                "Please enter the current 6-digit code from your "
                "authenticator app (Google Authenticator, Authy, etc.):"
            )
        elif mfa_field.input_type == MFAInputType.SMS:
            return "Please enter the verification code sent to your phone:"
        elif mfa_field.input_type == MFAInputType.EMAIL:
            return "Please enter the verification code sent to your email:"
        elif mfa_field.input_type == MFAInputType.RECOVERY:
            return "Please enter your recovery or backup code:"
        else:
            return "Please enter the verification code:"

    def _extract_service_from_url(self, url: str) -> str | None:
        """
        Extract service name from URL for TOTP lookup.

        Examples:
            https://github.com/login -> github
            https://aws.amazon.com/console -> aws
            https://accounts.google.com -> google
        """
        url = url.lower()

        # Common service patterns
        service_patterns = {
            'github.com': 'github',
            'aws.amazon.com': 'aws',
            'amazon.com': 'amazon',
            'accounts.google.com': 'google',
            'mail.google.com': 'google',
            'facebook.com': 'facebook',
            'twitter.com': 'twitter',
            'x.com': 'twitter',
            'linkedin.com': 'linkedin',
            'microsoft.com': 'microsoft',
            'live.com': 'microsoft',
            'outlook.com': 'microsoft',
            'dropbox.com': 'dropbox',
            'stripe.com': 'stripe',
            'paypal.com': 'paypal',
            'ebay.com': 'ebay',
            'reddit.com': 'reddit'
        }

        for pattern, service in service_patterns.items():
            # Ensure we match the domain properly (not just substring)
            # Pattern 'x.com' should not match 'dropbox.com'
            if url.startswith("https://") or url.startswith("http://"):
                # Remove protocol for matching
                url_without_protocol = url.split("://", 1)[1]
                # Check if pattern matches at the start or after a dot
                if (url_without_protocol.startswith(pattern) or
                    f".{pattern}" in url_without_protocol or
                    f"/{pattern}" in url_without_protocol):
                    return service
            else:
                # Fallback to simple match for non-URL strings
                if pattern in url:
                    return service

        return None

    def _check_cache(self, service: str) -> str | None:
        """Check if we have a cached code for this service"""
        if service in self.code_cache:
            timestamp, code = self.code_cache[service]
            if time.time() - timestamp < self.cache_ttl:
                return code
            else:
                # Cache expired
                del self.code_cache[service]
        return None

    def _cache_code(self, service: str, code: str) -> None:
        """Cache a TOTP code"""
        self.code_cache[service] = (time.time(), code)

    def _select_best_result(self, results: list) -> MFAResolutionResult:
        """Select the best result from multiple attempts"""
        # Prefer user prompts (most reliable)
        for result in results:
            if result.success and result.method_used == MFAResolutionMethod.USER_PROMPT:
                return result

        # Then TOTP
        for result in results:
            if result.success and result.method_used == MFAResolutionMethod.TOTP_AUTO:
                return result

        # Then retrieval methods
        for result in results:
            if result.success:
                return result

        # Return first failure if all failed
        return results[0] if results else MFAResolutionResult(
            success=False,
            code_used=None,
            method_used=MFAResolutionMethod.USER_PROMPT,
            error_message="No resolution methods available"
        )


def create_mfa_handler() -> MFAHandler:
    """Create a new MFAHandler instance"""
    return MFAHandler()
