"""Configuration loading and safety policy."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    """Raised when configuration is unsafe or malformed."""


_SECRET_KEYS = {"api_key", "apikey", "secret", "token", "password", "authorization"}
_ENV_RE = re.compile(r"^[A-Z_][A-Z0-9_]{1,127}$")
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{6,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)[?&](?:access_token|api_key|token|key|sig|signature|auth|session|cookie)="),
    re.compile(r"(?i)\b(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*[:=]"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


@dataclass(frozen=True)
class LiveTarget:
    """A request target resolved once and safe to connect to without another DNS lookup."""

    scheme: str
    hostname: str
    port: int
    ip: str
    host_header: str
    request_target: str


def _reject_embedded_secrets(value: Any, path: str = "config") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _SECRET_KEYS:
                raise ConfigurationError("configuration contains a forbidden credential field")
            _reject_embedded_secrets(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_embedded_secrets(child, f"{path}[{index}]")
    elif isinstance(value, str) and any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS):
        raise ConfigurationError("configuration contains forbidden credential material")


def load_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError("cannot read JSON document") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("the JSON document must be an object")
    return value


def validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    _reject_embedded_secrets(raw)
    if type(raw.get("schema_version")) is not int or raw.get("schema_version") != 1:
        raise ConfigurationError("schema_version must be 1")
    provider = raw.get("provider")
    if not isinstance(provider, dict):
        raise ConfigurationError("provider must be an object")
    required = ("name", "base_url", "environment", "model")
    for key in required:
        if not isinstance(provider.get(key), str) or not provider[key].strip():
            raise ConfigurationError(f"provider.{key} must be a non-empty string")
        if any(ord(character) < 32 or ord(character) == 127 for character in provider[key]):
            raise ConfigurationError(f"provider.{key} cannot contain control characters")
    environment = provider["environment"].lower()
    if environment not in {"local", "test", "staging", "production"}:
        raise ConfigurationError("provider.environment must be local, test, staging, or production")
    try:
        parsed = urlparse(provider["base_url"])
        hostname = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise ConfigurationError("provider.base_url is not a valid URL") from exc
    if parsed.scheme not in {"http", "https"} or not hostname or parsed.username or parsed.password:
        raise ConfigurationError("provider.base_url must be an HTTP(S) URL without user information")
    if parsed.query or parsed.fragment:
        raise ConfigurationError("provider.base_url cannot contain a query string or fragment")
    provider["base_url"] = provider["base_url"].rstrip("/")

    credential = raw.get("credential")
    if not isinstance(credential, dict):
        raise ConfigurationError("credential must be an object")
    env_name = credential.get("env")
    if not isinstance(env_name, str) or not _ENV_RE.fullmatch(env_name):
        raise ConfigurationError("credential.env must be an uppercase environment-variable name")
    if credential.get("environment") != environment:
        raise ConfigurationError("credential.environment must exactly match provider.environment")
    auth = credential.get("auth", "bearer")
    if auth not in {"bearer", "header"}:
        raise ConfigurationError("credential.auth must be bearer or header")
    if auth == "header":
        header = credential.get("header")
        if not isinstance(header, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,80}", header):
            raise ConfigurationError("credential.header must be a valid header name")
        if header.lower() in {"host", "content-length", "connection", "transfer-encoding", "proxy-authorization", "cookie", "set-cookie"}:
            raise ConfigurationError("credential.header cannot be a routing, framing, proxy, or cookie header")

    isolation = raw.get("isolation")
    if not isinstance(isolation, dict) or not isinstance(isolation.get("allowed_hosts"), list):
        raise ConfigurationError("isolation.allowed_hosts must be a list")
    hosts = isolation["allowed_hosts"]
    if not hosts or any(not isinstance(host, str) or not host for host in hosts):
        raise ConfigurationError("isolation.allowed_hosts must contain non-empty host names")
    if hostname.lower() not in {host.lower() for host in hosts}:
        raise ConfigurationError("provider host is outside isolation.allowed_hosts")
    expected_header = isolation.get("response_environment_header", "")
    if expected_header and not re.fullmatch(r"[A-Za-z0-9-]{1,80}", expected_header):
        raise ConfigurationError("isolation.response_environment_header is invalid")
    probe = raw.setdefault("probe", {})
    if not isinstance(probe, dict):
        raise ConfigurationError("probe must be an object")
    max_tokens = probe.setdefault("max_tokens", 4)
    normal_max = probe.setdefault("normal_request_max_tokens", 128)
    if type(max_tokens) is not int or not 1 <= max_tokens <= 16:
        raise ConfigurationError("probe.max_tokens must be an integer from 1 to 16")
    if type(normal_max) is not int or normal_max < 1:
        raise ConfigurationError("probe.normal_request_max_tokens must be a positive integer")
    if max_tokens > normal_max:
        raise ConfigurationError("probe.max_tokens cannot exceed the normal request budget")
    return raw


def resolve_live_target(config: dict[str, Any], url: str) -> LiveTarget:
    provider = config["provider"]
    base = urlparse(provider["base_url"])
    parsed = urlparse(url)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError("live request URL is outside the validated target")
    base_port = base.port or (443 if base.scheme == "https" else 80)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if parsed.scheme != base.scheme or parsed.hostname.lower() != (base.hostname or "").lower() or port != base_port:
        raise ConfigurationError("live request URL is outside the validated target")
    base_path = base.path.rstrip("/")
    allowed_paths = {base_path + "/models", base_path + "/chat/completions"}
    if parsed.path not in allowed_paths:
        raise ConfigurationError("live request path is outside the validated adapter endpoints")
    hostname = parsed.hostname.lower()
    local_mode = provider["environment"] in {"local", "test"}
    if hostname in _LOOPBACK_HOSTS and not local_mode:
        raise ConfigurationError("loopback targets require a local or test environment")
    if parsed.scheme == "http" and hostname not in _LOOPBACK_HOSTS:
        raise ConfigurationError("live non-loopback targets require HTTPS")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise ConfigurationError("provider host cannot be resolved") from exc
    if not addresses:
        raise ConfigurationError("provider host cannot be resolved")
    for address in sorted(addresses):
        ip = ipaddress.ip_address(address)
        if hostname in _LOOPBACK_HOSTS:
            if not ip.is_loopback:
                raise ConfigurationError("literal loopback target resolved outside loopback")
        elif not ip.is_global:
            raise ConfigurationError("private or special live targets require an explicit loopback host")
    selected = sorted(addresses, key=lambda value: (ipaddress.ip_address(value).version, value))[0]
    default_port = 443 if parsed.scheme == "https" else 80
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    host_header = display_host if port == default_port else f"{display_host}:{port}"
    return LiveTarget(
        scheme=parsed.scheme,
        hostname=hostname,
        port=port,
        ip=selected,
        host_header=host_header,
        request_target=parsed.path or "/",
    )


def assert_live_target(config: dict[str, Any]) -> None:
    """Compatibility preflight; every actual request is resolved again before transport."""

    resolve_live_target(config, config["provider"]["base_url"] + "/models")
