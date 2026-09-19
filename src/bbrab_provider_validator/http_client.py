"""Small, redirect-free JSON HTTP client."""

from __future__ import annotations

import http.client
import json
import socket
import ssl
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .config import LiveTarget


class TransportError(RuntimeError):
    pass


MAX_RESPONSE_BYTES = 1_048_576


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to a verified IP while verifying TLS against the original hostname."""

    def __init__(self, target: LiveTarget, *, timeout: float) -> None:
        super().__init__(target.hostname, target.port, timeout=timeout, context=ssl.create_default_context())
        self._pinned_ip = target.ip

    def connect(self) -> None:
        raw_socket = socket.create_connection((self._pinned_ip, self.port), self.timeout, self.source_address)
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except BaseException:
            raw_socket.close()
            raise


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: Any


def request_json(
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    timeout: float = 15.0,
    target: LiveTarget,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
) -> Response:
    if max_response_bytes < 1:
        raise TransportError("invalid response byte limit")
    parsed = urlparse(url)
    parsed_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if (
        parsed.scheme != target.scheme
        or (parsed.hostname or "").lower() != target.hostname
        or parsed_port != target.port
        or parsed.path != target.request_target
        or parsed.query
        or parsed.fragment
    ):
        raise TransportError("request target mismatch")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {**headers, "Accept": "application/json", "Host": target.host_header}
    connection: http.client.HTTPConnection
    if target.scheme == "https":
        connection = _PinnedHTTPSConnection(target, timeout=timeout)
    else:
        connection = http.client.HTTPConnection(target.ip, target.port, timeout=timeout)
    try:
        connection.request(method, target.request_target, body=data, headers=request_headers)
        response = connection.getresponse()
        try:
            raw = response.read(max_response_bytes + 1)
            status = response.status
            response_headers = dict(response.getheaders())
        finally:
            response.close()
        if len(raw) > max_response_bytes:
            raise TransportError("provider response exceeded the byte limit")
    except TransportError:
        raise
    except (OSError, ValueError, http.client.HTTPException, ssl.SSLError) as exc:
        raise TransportError("provider transport failed") from exc
    finally:
        connection.close()
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TransportError(f"HTTP {status} did not return valid JSON") from exc
    return Response(status=status, headers={key.lower(): value for key, value in response_headers.items()}, body=body)
