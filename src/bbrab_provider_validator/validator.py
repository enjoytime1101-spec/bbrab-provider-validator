"""Provider acceptance contracts shared by fixture and live modes."""

from __future__ import annotations

import os
import math
from datetime import datetime, timezone
from typing import Any, Callable

from .config import assert_live_target, resolve_live_target, validate_config
from .http_client import Response, TransportError, request_json
from .redact import redact

CONTRACT = "openai-compatible-acceptance-v1"


def _check(checks: list[dict[str, Any]], name: str, passed: bool, detail: Any) -> None:
    checks.append({"name": name, "status": "passed" if passed else "failed", "detail": redact(detail)})


def _environment(response: Response, config: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    isolation = config["isolation"]
    header_name = isolation.get("response_environment_header", "")
    if not header_name:
        _check(checks, "environment_response_marker", True, "not required by configuration")
        return
    actual = response.headers.get(header_name.lower(), "")
    expected = config["provider"]["environment"]
    _check(checks, "environment_response_marker", actual == expected, {
        "expected": expected,
        "present": bool(actual),
        "matched": actual == expected,
    })


def _accept(
    config: dict[str, Any],
    responses: dict[str, Response],
    mode: str,
    secret_values: tuple[str, ...] = (),
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    provider = config["provider"]
    models = responses["models"]
    model_data = models.body.get("data") if isinstance(models.body, dict) else None
    models_shape_ok = isinstance(model_data, list)
    ids = [
        item.get("id")
        for item in model_data if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]
    ] if models_shape_ok else []
    _check(checks, "connection", models.status == 200, {"status": models.status})
    _check(checks, "models_shape", models_shape_ok, {"data_is_list": models_shape_ok})
    _check(checks, "non_empty_capabilities", bool(ids), {"model_count": len(ids)})
    _check(checks, "configured_model_advertised", provider["model"] in ids, {"model": provider["model"]})
    _environment(models, config, checks)

    completion = responses["completion"]
    content = ""
    choices = completion.body.get("choices") if isinstance(completion.body, dict) else None
    choices_shape_ok = isinstance(choices, list) and bool(choices) and isinstance(choices[0], dict)
    if choices_shape_ok:
        if isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                content = message["content"].strip()
    _check(checks, "completion_status", completion.status == 200, {"status": completion.status})
    _check(checks, "completion_shape", choices_shape_ok, {"choices_is_non_empty_list": choices_shape_ok})
    _check(checks, "non_empty_completion", bool(content), {"content_length": len(content)})
    usage = completion.body.get("usage") if isinstance(completion.body, dict) else None
    usage_keys = ("prompt_tokens", "completion_tokens", "total_tokens")
    safe_usage = {key: usage.get(key) if isinstance(usage, dict) and type(usage.get(key)) is int else None for key in usage_keys}
    usage_ok = isinstance(usage, dict) and all(type(usage.get(key)) is int for key in usage_keys)
    if usage_ok:
        usage_ok = usage["prompt_tokens"] >= 0 and usage["completion_tokens"] >= 0 and usage["total_tokens"] > 0
        usage_ok = usage_ok and usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    _check(checks, "non_empty_usage", bool(usage_ok), safe_usage)
    _environment(completion, config, checks)

    error = responses["error"]
    error_object = error.body.get("error") if isinstance(error.body, dict) else None
    error_ok = 400 <= error.status < 500 and isinstance(error_object, dict)
    error_ok = error_ok and isinstance(error_object.get("message"), str) and bool(error_object["message"].strip())
    error_message = error_object.get("message", "") if isinstance(error_object, dict) else ""
    _check(checks, "structured_client_error", bool(error_ok), {
        "status": error.status,
        "error_object_present": isinstance(error_object, dict),
        "message_present": bool(error_message.strip()) if isinstance(error_message, str) else False,
        "message_length": len(error_message) if isinstance(error_message, str) else 0,
    })
    _environment(error, config, checks)

    passed = all(item["status"] == "passed" for item in checks)
    return redact({
        "contract": CONTRACT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "provider": {
            "name": provider["name"],
            "base_url": provider["base_url"],
            "environment": provider["environment"],
            "model": provider["model"],
            "credential_env": config["credential"]["env"],
        },
        "status": "passed" if passed else "failed",
        "checks": checks,
    }, secrets=secret_values)


def _fixture_response(value: Any, name: str) -> Response:
    if not isinstance(value, dict) or type(value.get("status")) is not int or "body" not in value:
        raise ValueError(f"fixture.{name} must contain integer status and body")
    headers = value.get("headers", {})
    if not isinstance(headers, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in headers.items()):
        raise ValueError(f"fixture.{name}.headers must be a string map")
    return Response(value["status"], {key.lower(): val for key, val in headers.items()}, value["body"])


def validate_fixture(config: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    checked = validate_config(config)
    responses = {name: _fixture_response(fixture.get(name), name) for name in ("models", "completion", "error")}
    return _accept(checked, responses, "fixture")


def validate_live(
    config: dict[str, Any],
    *,
    live: bool = False,
    acknowledge_provider_cost: bool = False,
    timeout: float = 15.0,
    request: Callable[..., Response] = request_json,
) -> dict[str, Any]:
    if not live or not acknowledge_provider_cost:
        raise PermissionError("live validation requires both --live and --acknowledge-provider-cost")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 60:
        raise PermissionError("timeout must be a finite number from 0 to 60 seconds")
    checked = validate_config(config)
    assert_live_target(checked)
    credential = checked["credential"]
    secret = os.environ.get(credential["env"], "")
    if not secret:
        raise PermissionError(f"credential environment variable {credential['env']} is not set")
    if any(ord(character) < 32 or ord(character) == 127 for character in secret):
        raise PermissionError("credential contains forbidden control characters")
    headers = {"Content-Type": "application/json"}
    if credential.get("auth", "bearer") == "bearer":
        headers["Authorization"] = f"Bearer {secret}"
    else:
        headers[credential["header"]] = secret
    base_url = checked["provider"]["base_url"]
    model = checked["provider"]["model"]
    try:
        models_url = base_url + "/models"
        completion_url = base_url + "/chat/completions"
        responses = {
            "models": request(models_url, method="GET", headers=headers, timeout=timeout, target=resolve_live_target(checked, models_url)),
            "completion": request(completion_url, method="POST", headers=headers, timeout=timeout, target=resolve_live_target(checked, completion_url), payload={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": checked["probe"]["max_tokens"],
                "temperature": 0,
            }),
            "error": request(completion_url, method="POST", headers=headers, timeout=timeout, target=resolve_live_target(checked, completion_url), payload={
                "model": "bbrab-validator-intentionally-invalid-model",
                "messages": [{"role": "user", "content": "This request must be rejected."}],
                "max_tokens": 1,
            }),
        }
    except TransportError:
        return redact({
            "contract": CONTRACT,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "live",
            "provider": {"name": checked["provider"]["name"], "environment": checked["provider"]["environment"]},
            "status": "failed",
            "checks": [{"name": "transport", "status": "failed", "detail": {"reason": "transport_failed"}}],
        }, secrets=(secret,))
    return _accept(checked, responses, "live", secret_values=(secret,))
