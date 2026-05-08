"""Proxy diagnostic helpers.

Why this exists: boto3/botocore silently accepts a non-functional proxy
(e.g. Privoxy running standalone without a SOCKS upstream) and will then
make direct requests that Anthropic rejects because the source IP is in
a restricted region. There is no exception raised, no warning, and the
only symptom is a confusing ValidationException about unsupported
countries. This module gives us a way to *look* at the proxy's exit IP
so the user (and us) can spot the problem in one second.

The checks use urllib (stdlib only) so they work whether or not boto3 is
the thing doing the real requests.
"""

from __future__ import annotations

import logging
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional


# AWS-owned IP echo service. Chosen because:
#   1) It returns the plain IP as text (no HTML to parse).
#   2) The LLM provider is also on *.amazonaws.com, so if this works
#      through the proxy, Bedrock should too.
#   3) No auth, no rate limits that matter for one request.
_CHECK_URL = "https://checkip.amazonaws.com"


@dataclass
class ProxyCheckResult:
    """Outcome of a proxy diagnostic probe."""

    proxy_url: Optional[str]
    ok: bool
    exit_ip: Optional[str] = None
    error: Optional[str] = None
    check_url: str = _CHECK_URL

    def format(self) -> str:
        """Human-readable one-block summary (for CLI output)."""
        lines = []
        if self.proxy_url:
            lines.append(f"Proxy:     {self.proxy_url}")
        else:
            lines.append("Proxy:     (none; direct connection)")
        lines.append(f"Probe URL: {self.check_url}")
        if self.ok:
            lines.append(f"Exit IP:   {self.exit_ip}")
            if self.proxy_url:
                lines.append(
                    "Notes:     If this IP is your own machine or a "
                    "region Anthropic blocks (e.g. China), the proxy "
                    "is reachable but not actually forwarding traffic "
                    "abroad. Check your proxy's upstream configuration."
                )
            else:
                lines.append(
                    "Notes:     Connected directly without a proxy. "
                    "If Anthropic blocks your region, set proxy_url "
                    "in your config."
                )
        else:
            lines.append(f"Exit IP:   (could not determine)")
            lines.append(f"Error:     {self.error}")
        return "\n".join(lines)


def check_proxy(
    proxy_url: Optional[str],
    *,
    timeout: float = 10.0,
    logger: Optional[logging.Logger] = None,
) -> ProxyCheckResult:
    """Run a lightweight "what is my exit IP" probe, through the proxy if given.

    Args:
        proxy_url: HTTP proxy URL, e.g. ``http://127.0.0.1:8118``.
            ``None`` or empty string means go direct.
        timeout: Socket timeout in seconds for the probe.
        logger: Optional logger to note failures.

    Returns:
        A :class:`ProxyCheckResult`. This function never raises; failures
        are reported via the ``error`` field.
    """
    proxy_url = (proxy_url or "").strip() or None

    # Build a one-off urllib opener. Critically, we do NOT install this
    # globally so concurrent code paths aren't affected.
    if proxy_url:
        handlers = [
            urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}),
            # Our ProxyHandler fully covers proxying; disable env-var
            # discovery so results are predictable.
            urllib.request.HTTPHandler(),
            urllib.request.HTTPSHandler(),
        ]
        opener = urllib.request.build_opener(*handlers)
    else:
        opener = urllib.request.build_opener()

    try:
        with opener.open(_CHECK_URL, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace").strip()
    except urllib.error.URLError as e:
        # Connection refused, DNS failure, proxy unreachable, etc.
        reason = getattr(e, "reason", e)
        msg = f"{type(e).__name__}: {reason}"
        if logger:
            logger.warning("Proxy probe failed: %s", msg)
        return ProxyCheckResult(proxy_url=proxy_url, ok=False, error=msg)
    except socket.timeout:
        msg = f"timed out after {timeout:.1f}s"
        if logger:
            logger.warning("Proxy probe timed out: %s", msg)
        return ProxyCheckResult(proxy_url=proxy_url, ok=False, error=msg)
    except Exception as e:  # pragma: no cover - truly unexpected
        msg = f"{type(e).__name__}: {e}"
        if logger:
            logger.warning("Proxy probe raised unexpected error: %s", msg)
        return ProxyCheckResult(proxy_url=proxy_url, ok=False, error=msg)

    ip = body.splitlines()[0].strip() if body else ""
    if not ip:
        return ProxyCheckResult(
            proxy_url=proxy_url,
            ok=False,
            error=f"probe returned an empty body from {_CHECK_URL}",
        )

    return ProxyCheckResult(proxy_url=proxy_url, ok=True, exit_ip=ip)
