"""Best-effort defense-in-depth redaction for reports and errors."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "authorization", "proxy_authorization", "api_key", "apikey", "x_api_key",
    "secret", "token", "access_token", "password", "cookie", "set_cookie", "credential",
}
_PATTERNS = (
    re.compile(r"(?im)\b(authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*[:=]\s*[^\r\n]*"),
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{6,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)([?&](?:access_token|api_key|token|key|sig|signature|auth|session|cookie)=)[^&#\s]+"),
)


def redact(value: Any, secrets: Iterable[str] = ()) -> Any:
    secret_values = tuple(secret for secret in secrets if secret)
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            output[str(key)] = REDACTED if normalized in _SENSITIVE_KEYS else redact(child, secret_values)
        return output
    if isinstance(value, list):
        return [redact(item, secret_values) for item in value]
    if isinstance(value, tuple):
        return [redact(item, secret_values) for item in value]
    if isinstance(value, str):
        result = value
        for secret in secret_values:
            result = result.replace(secret, REDACTED)
        for pattern in _PATTERNS:
            result = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + REDACTED, result)
        return result
    return value
