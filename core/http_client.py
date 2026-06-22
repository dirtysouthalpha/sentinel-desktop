"""Sentinel Desktop v16.0 — HTTP client actions.

Lightweight wrappers around httpx (already a project dependency) for
agent-callable HTTP actions: http_get, http_post, http_download.

No new dependencies — httpx ~= 0.28 is already required.

Usage::

    from core.http_client import http_get, http_post

    result = http_get("https://api.github.com/repos/octocat/Hello-World")
    result = http_post("https://httpbin.org/post", json={"key": "value"})
"""

from __future__ import annotations

import ipaddress
import logging
import urllib.parse
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Max response body returned to agent (prevent huge payloads flooding context)
MAX_BODY_LENGTH = 50_000
# Cap a single download to bound disk usage and block large-data exfiltration.
MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024

# Cloud instance-metadata endpoints. Reaching these returns cloud credentials,
# so they are blocked regardless of caller. Internal IT appliances (RFC1918
# private space) are intentionally NOT blocked — reaching them is this tool's
# core use case (routers, firewalls, APs).
_METADATA_HOSTS = frozenset(
    {
        "metadata.google.internal",  # GCP metadata (DNS name)
        "metadata.azure.com",  # Azure metadata (DNS name)
    }
)
# IPv4 link-local covers AWS/Azure/GCP IMDS (169.254.169.254) and the ECS task
# metadata alternates (169.254.170.2 / .23, 169.254.169.253).
_LINK_LOCAL_NETWORK = ipaddress.ip_network("169.254.0.0/16")
# AWS IPv6 IMDS.
_METADATA_IPS = frozenset({ipaddress.ip_address("fd00:ec2::254")})


def _host_to_ip(host: str) -> ipaddress._BaseAddress | None:
    """Return the IP for an IP-literal host, decoding int/hex encodings.

    Handles dotted-decimal IPv4, IPv6 literals, and the single-number integer
    (``2852039166``) / hex (``0xa9fea9fe``) encodings of IPv4 that the OS
    resolver still accepts but the string-prefix guard misses. DNS names are
    NOT resolved here — DNS-rebinding is a separate, harder problem.
    """
    if not host:
        return None
    h = host.strip("[]")
    try:
        return ipaddress.ip_address(h)
    except ValueError:
        pass
    try:
        n = int(h, 0)  # base 0: accepts 0x.. hex and decimal; rejects DNS names
    except ValueError:
        return None
    if 0 <= n <= 0xFFFFFFFF:
        return ipaddress.IPv4Address(n)
    return None


def _is_metadata_endpoint(url: str) -> bool:
    """Return True if *url* targets a known cloud instance-metadata endpoint."""
    try:
        host = urllib.parse.urlparse(url).hostname
    except ValueError:
        return False
    if not host:
        return False
    host = host.lower().strip("[]")
    if host in _METADATA_HOSTS:
        return True
    ip = _host_to_ip(host)
    if ip is None:
        return False
    if isinstance(ip, ipaddress.IPv4Address):
        return ip in _LINK_LOCAL_NETWORK
    return ip in _METADATA_IPS

# Default timeout for all requests
DEFAULT_TIMEOUT = 30.0


def http_get(
    url: str,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    """Perform an HTTP GET request.

    Args:
        url:        Target URL.
        headers:    Optional request headers.
        params:     Optional query parameters.
        timeout:    Request timeout in seconds.
        verify_ssl: Verify SSL certificates. Set False for self-signed certs.

    Returns:
        Dict with ``success``, ``status_code``, ``body``, ``headers``.
    """
    return _request(
        "GET", url, headers=headers, params=params, timeout=timeout, verify_ssl=verify_ssl
    )


def http_post(
    url: str,
    body: str | None = None,
    json: dict | list | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    """Perform an HTTP POST request.

    Args:
        url:     Target URL.
        body:    Raw request body string (mutually exclusive with json).
        json:    JSON-serializable payload. Sets Content-Type automatically.
        headers: Optional request headers.
        params:  Optional query parameters.
        timeout: Request timeout in seconds.
    """
    return _request(
        "POST",
        url,
        body=body,
        json=json,
        headers=headers,
        params=params,
        timeout=timeout,
        verify_ssl=verify_ssl,
    )


def http_put(
    url: str,
    body: str | None = None,
    json: dict | list | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    """Perform an HTTP PUT request."""
    return _request(
        "PUT", url, body=body, json=json, headers=headers, timeout=timeout, verify_ssl=verify_ssl
    )


def http_delete(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    """Perform an HTTP DELETE request."""
    return _request("DELETE", url, headers=headers, timeout=timeout, verify_ssl=verify_ssl)


def http_download(
    url: str,
    save_path: str,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    """Download a file from *url* and save to *save_path*.

    Returns:
        Dict with ``success``, ``path``, ``size_bytes``.
    """
    if _is_metadata_endpoint(url):
        return {
            "success": False,
            "output": f"Refusing cloud metadata endpoint (SSRF guard): {url!r}",
            "error": "blocked_metadata",
        }
    try:
        import httpx  # type: ignore

        dest = Path(save_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        with httpx.stream(
            "GET",
            url,
            headers=headers or {},
            timeout=timeout,
            verify=verify_ssl,
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            # Re-check the final (post-redirect) URL BEFORE writing any bytes.
            if _is_metadata_endpoint(str(getattr(response, "url", ""))):
                return {
                    "success": False,
                    "output": "Refusing cloud metadata endpoint reached via "
                    "redirect (SSRF guard).",
                    "error": "blocked_metadata",
                }
            size = 0
            with dest.open("wb") as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        f.close()
                        dest.unlink(missing_ok=True)
                        return {
                            "success": False,
                            "output": (
                                f"Download aborted: exceeded {MAX_DOWNLOAD_BYTES:,} "
                                "byte cap."
                            ),
                            "error": "download_too_large",
                        }
                    f.write(chunk)

        return {
            "success": True,
            "path": str(dest),
            "size_bytes": size,
            "output": f"Downloaded {size:,} bytes to {dest}",
        }
    except ImportError:
        return {"success": False, "output": "httpx not installed", "error": "missing_dep"}
    except Exception as exc:
        return {"success": False, "output": str(exc), "error": type(exc).__name__}


def _request(
    method: str,
    url: str,
    body: str | None = None,
    json: dict | list | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    """Internal HTTP request dispatcher."""
    # Only allow http(s) to prevent SSRF to local files / custom protocols
    if not url.startswith(("http://", "https://")):
        return {
            "success": False,
            "output": f"Refusing non-http(s) URL: {url!r}",
            "error": "invalid_url",
        }
    # Block cloud instance-metadata endpoints (SSRF → cloud-cred exfiltration).
    if _is_metadata_endpoint(url):
        return {
            "success": False,
            "output": f"Refusing cloud metadata endpoint (SSRF guard): {url!r}",
            "error": "blocked_metadata",
        }

    try:
        import httpx  # type: ignore

        kwargs: dict[str, Any] = {
            "headers": headers or {},
            "timeout": timeout,
            "verify": verify_ssl,
            "follow_redirects": True,
        }
        if params:
            kwargs["params"] = params
        if json is not None:
            kwargs["json"] = json
        elif body is not None:
            kwargs["content"] = body.encode("utf-8")

        response = httpx.request(method, url, **kwargs)

        # Re-check the final (post-redirect) URL: an external server can return
        # a 30x to a metadata endpoint, bypassing the request-URL guard above.
        # httpx top-level request() has no event_hooks hook, so we verify after.
        final_url = str(getattr(response, "url", ""))
        if _is_metadata_endpoint(final_url):
            return {
                "success": False,
                "output": "Refusing cloud metadata endpoint reached via redirect "
                "(SSRF guard).",
                "error": "blocked_metadata",
            }

        # Parse JSON body if content-type indicates it
        content_type = response.headers.get("content-type", "")
        raw = response.text
        parsed_json = None
        if "application/json" in content_type:
            try:
                parsed_json = response.json()
            except Exception:
                pass

        body_preview = raw[:MAX_BODY_LENGTH]
        if len(raw) > MAX_BODY_LENGTH:
            body_preview += f"\n[... truncated — full length {len(raw):,} chars]"

        return {
            "success": response.is_success,
            "status_code": response.status_code,
            "body": parsed_json if parsed_json is not None else body_preview,
            "headers": dict(response.headers),
            "output": f"HTTP {response.status_code} {method} {url}",
        }
    except ImportError:
        return {"success": False, "output": "httpx not installed", "error": "missing_dep"}
    except Exception as exc:
        return {"success": False, "output": str(exc), "error": type(exc).__name__}
