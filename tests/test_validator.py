from __future__ import annotations

import json
import os
import io
import http.client
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bbrab_provider_validator.cli import main
from bbrab_provider_validator.config import ConfigurationError, LiveTarget, resolve_live_target, validate_config
from bbrab_provider_validator.http_client import Response, TransportError, _PinnedHTTPSConnection, request_json
from bbrab_provider_validator.redact import REDACTED, redact
from bbrab_provider_validator.report import markdown_report
from bbrab_provider_validator.validator import validate_fixture, validate_live

ROOT = Path(__file__).resolve().parents[1]


def example_config() -> dict:
    return json.loads((ROOT / "examples/provider.example.json").read_text())


def passing_fixture() -> dict:
    return json.loads((ROOT / "examples/fixture.passing.json").read_text())


class FixtureTests(unittest.TestCase):
    def test_passing_fixture_accepts_non_empty_content_exact_usage_and_errors(self) -> None:
        report = validate_fixture(example_config(), passing_fixture())
        self.assertEqual("passed", report["status"])
        self.assertTrue(all(item["status"] == "passed" for item in report["checks"]))

    def test_empty_content_fails(self) -> None:
        fixture = passing_fixture()
        fixture["completion"]["body"]["choices"][0]["message"]["content"] = "  "
        report = validate_fixture(example_config(), fixture)
        failed = {item["name"] for item in report["checks"] if item["status"] == "failed"}
        self.assertIn("non_empty_completion", failed)

    def test_usage_must_equal_prompt_plus_completion(self) -> None:
        fixture = passing_fixture()
        fixture["completion"]["body"]["usage"]["total_tokens"] = 99
        report = validate_fixture(example_config(), fixture)
        self.assertEqual("failed", report["status"])
        self.assertEqual("failed", next(item for item in report["checks"] if item["name"] == "non_empty_usage")["status"])

    def test_usage_rejects_booleans_and_drops_extensions(self) -> None:
        fixture = passing_fixture()
        fixture["completion"]["body"]["usage"] = {
            "prompt_tokens": True,
            "completion_tokens": 1,
            "total_tokens": 2,
            "provider_private_extension": "must-not-be-exported",
        }
        report = validate_fixture(example_config(), fixture)
        usage_check = next(item for item in report["checks"] if item["name"] == "non_empty_usage")
        self.assertEqual("failed", usage_check["status"])
        self.assertEqual(
            {"prompt_tokens": None, "completion_tokens": 1, "total_tokens": 2},
            usage_check["detail"],
        )
        self.assertNotIn("provider_private_extension", json.dumps(report))
        self.assertNotIn("must-not-be-exported", json.dumps(report))

    def test_malformed_models_and_choices_become_failed_checks(self) -> None:
        fixture = passing_fixture()
        fixture["models"]["body"]["data"] = {"id": "not-a-list"}
        fixture["completion"]["body"]["choices"] = {"message": "not-a-list"}
        report = validate_fixture(example_config(), fixture)
        failed = {item["name"] for item in report["checks"] if item["status"] == "failed"}
        self.assertIn("models_shape", failed)
        self.assertIn("completion_shape", failed)
        self.assertIn("non_empty_completion", failed)

    def test_environment_marker_mismatch_fails(self) -> None:
        fixture = passing_fixture()
        fixture["models"]["headers"]["X-Provider-Environment"] = "production"
        self.assertEqual("failed", validate_fixture(example_config(), fixture)["status"])

    def test_embedded_credentials_are_rejected(self) -> None:
        config = example_config()
        config["credential"]["api_key"] = "literal-must-never-be-accepted"
        with self.assertRaises(ConfigurationError):
            validate_config(config)

    def test_secret_shaped_config_value_is_rejected(self) -> None:
        config = example_config()
        config["provider"]["name"] = "Authorization: Bearer forbiddenvalue"
        with self.assertRaisesRegex(ConfigurationError, "credential material"):
            validate_config(config)

    def test_custom_auth_cannot_replace_routing_or_cookie_headers(self) -> None:
        for header in ("Host", "Content-Length", "Proxy-Authorization", "Cookie"):
            with self.subTest(header=header):
                config = example_config()
                config["credential"].update({"auth": "header", "header": header})
                with self.assertRaisesRegex(ConfigurationError, "routing, framing, proxy, or cookie"):
                    validate_config(config)

    def test_probe_budget_cannot_exceed_normal_request_budget(self) -> None:
        config = example_config()
        config["probe"] = {"max_tokens": 8, "normal_request_max_tokens": 4}
        with self.assertRaises(ConfigurationError):
            validate_config(config)

    def test_redaction_is_recursive(self) -> None:
        value = redact({
            "nested": [{"authorization": "Bearer abcdefgh", "Set-Cookie": "session=topsecret"}],
            "message": "saw sk-abcdefghijk at https://example.test/x?access_token=urlsecret and Cookie: session=rawsecret",
        })
        self.assertEqual(REDACTED, value["nested"][0]["authorization"])
        rendered = json.dumps(value)
        for secret in ("abcdefgh", "topsecret", "urlsecret", "rawsecret"):
            self.assertNotIn(secret, rendered)

    def test_redaction_removes_complete_cookie_and_header_lines(self) -> None:
        value = redact(
            "Cookie: first=alpha; second=beta, third=gamma\n"
            "Set-Cookie: session=delta; Path=/; HttpOnly\n"
            "Authorization: Bearer epsilon\n"
            "safe line"
        )
        for secret in ("alpha", "beta", "gamma", "delta", "epsilon", "HttpOnly"):
            self.assertNotIn(secret, value)
        self.assertIn("safe line", value)

    def test_python_markdown_escapes_all_dynamic_fields(self) -> None:
        report = {
            "status": "passed<script>",
            "mode": "fixture`mode",
            "contract": "contract\n# injected",
            "provider": {"name": "<img src=x> `name`\n| cell", "environment": "stage|prod"},
            "checks": [{
                "name": "check|name",
                "status": "passed\n| forged | row |",
                "detail": {"dynamic": "<script>`tick`\n| value"},
            }],
        }
        rendered = markdown_report(report)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertNotIn("`tick`", rendered)
        self.assertNotIn("\n# injected", rendered)
        self.assertNotIn("| forged | row |", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("&grave;tick&grave;", rendered)
        self.assertIn("&vert;", rendered)

    def test_provider_error_original_and_usage_are_safely_exported(self) -> None:
        fixture = passing_fixture()
        fixture["error"]["body"]["error"]["message"] = (
            "customer-specific upstream failure Authorization: Bearer echoedsecret "
            "https://provider.test/debug?token=querysecret&session=sessionsecret"
        )
        report = validate_fixture(example_config(), fixture)
        rendered = json.dumps(report)
        for private_text in ("customer-specific", "echoedsecret", "querysecret", "sessionsecret"):
            self.assertNotIn(private_text, rendered)
        error_check = next(item for item in report["checks"] if item["name"] == "structured_client_error")
        self.assertTrue(error_check["detail"]["message_present"])
        self.assertIn('"prompt_tokens": 5', rendered)

    def test_credential_query_url_is_rejected(self) -> None:
        config = example_config()
        config["provider"]["base_url"] += "?api_key=forbidden"
        with self.assertRaises(ConfigurationError):
            validate_config(config)

    def test_transport_exception_is_redacted_in_report(self) -> None:
        config = {
            "schema_version": 1,
            "provider": {"name": "mock", "base_url": "http://127.0.0.1:9/v1", "environment": "test", "model": "mock-chat"},
            "credential": {"env": "MOCK_TEST_API_KEY", "environment": "test", "auth": "bearer"},
            "isolation": {"allowed_hosts": ["127.0.0.1"]},
        }

        def fail(*args, **kwargs):
            raise TransportError("raw localvalue Authorization: Bearer transportsecret Cookie: session=cookiesecret https://x/?token=urlsecret")

        with patch.dict(os.environ, {"MOCK_TEST_API_KEY": "localvalue"}):
            report = validate_live(config, live=True, acknowledge_provider_cost=True, request=fail)
        rendered = json.dumps(report)
        for secret in ("transportsecret", "cookiesecret", "urlsecret", "localvalue"):
            self.assertNotIn(secret, rendered)

    def test_live_resolves_and_pins_each_request_target(self) -> None:
        config = {
            "schema_version": 1,
            "provider": {"name": "mock", "base_url": "http://127.0.0.1:8080/v1", "environment": "test", "model": "mock-chat"},
            "credential": {"env": "MOCK_TEST_API_KEY", "environment": "test", "auth": "bearer"},
            "isolation": {"allowed_hosts": ["127.0.0.1"]},
        }
        targets = []

        def respond(url, *, method, headers, timeout, target, payload=None):
            targets.append(target)
            if url.endswith("/models"):
                return Response(200, {}, {"data": [{"id": "mock-chat"}]})
            if payload["model"] == "bbrab-validator-intentionally-invalid-model":
                return Response(404, {}, {"error": {"message": "not found"}})
            return Response(200, {}, {
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            })

        answer = [(2, 1, 6, "", ("127.0.0.1", 8080))]
        with patch.dict(os.environ, {"MOCK_TEST_API_KEY": "localvalue"}), patch(
            "bbrab_provider_validator.config.socket.getaddrinfo", return_value=answer
        ) as resolver:
            report = validate_live(config, live=True, acknowledge_provider_cost=True, request=respond)
        self.assertEqual("passed", report["status"])
        self.assertEqual(3, len(targets))
        self.assertTrue(all(target.ip == "127.0.0.1" for target in targets))
        self.assertEqual(["/v1/models", "/v1/chat/completions", "/v1/chat/completions"], [target.request_target for target in targets])
        self.assertGreaterEqual(resolver.call_count, 3)

    def test_live_mode_requires_both_flags(self) -> None:
        with redirect_stderr(io.StringIO()):
            rc = main(["validate", "--config", str(ROOT / "examples/provider.example.json"), "--live"])
        self.assertEqual(2, rc)

    def test_cli_does_not_print_raw_value_error(self) -> None:
        with redirect_stderr(io.StringIO()) as stderr, patch(
            "bbrab_provider_validator.cli.validate_fixture",
            side_effect=ValueError("Authorization: Bearer cli-secret"),
        ):
            rc = main([
                "validate",
                "--config", str(ROOT / "examples/provider.example.json"),
                "--fixture", str(ROOT / "examples/fixture.passing.json"),
            ])
        self.assertEqual(2, rc)
        self.assertEqual("error: invalid input or output\n", stderr.getvalue())

    def test_cli_does_not_print_raw_http_exception(self) -> None:
        with redirect_stderr(io.StringIO()) as stderr, patch(
            "bbrab_provider_validator.cli.validate_fixture",
            side_effect=http.client.HTTPException("Set-Cookie: session=cli-secret"),
        ):
            rc = main([
                "validate",
                "--config", str(ROOT / "examples/provider.example.json"),
                "--fixture", str(ROOT / "examples/fixture.passing.json"),
            ])
        self.assertEqual(2, rc)
        self.assertEqual("error: validation failed safely\n", stderr.getvalue())

    def test_credential_control_characters_are_rejected_before_transport(self) -> None:
        config = {
            "schema_version": 1,
            "provider": {"name": "mock", "base_url": "http://127.0.0.1:9/v1", "environment": "test", "model": "mock-chat"},
            "credential": {"env": "MOCK_TEST_API_KEY", "environment": "test", "auth": "bearer"},
            "isolation": {"allowed_hosts": ["127.0.0.1"]},
        }
        with patch.dict(os.environ, {"MOCK_TEST_API_KEY": "unsafe\r\nInjected: value"}):
            with self.assertRaisesRegex(PermissionError, "control characters"):
                validate_live(config, live=True, acknowledge_provider_cost=True, request=lambda *args, **kwargs: None)

    def test_test_environment_does_not_allow_named_private_targets(self) -> None:
        config = example_config()
        config["provider"].update({"base_url": "https://internal.example/v1", "environment": "test"})
        config["credential"]["environment"] = "test"
        config["isolation"]["allowed_hosts"] = ["internal.example"]
        checked = validate_config(config)
        private_answer = [(2, 1, 6, "", ("10.1.2.3", 443))]
        with patch("bbrab_provider_validator.config.socket.getaddrinfo", return_value=private_answer):
            with self.assertRaisesRegex(ConfigurationError, "explicit loopback"):
                resolve_live_target(checked, "https://internal.example/v1/models")


class HttpTransportTests(unittest.TestCase):
    def test_response_limit_closes_response_and_connection(self) -> None:
        state = {"response_closed": False, "connection_closed": False}

        class FakeResponse:
            status = 200

            def read(self, amount: int) -> bytes:
                self.amount = amount
                return b"123456"

            def getheaders(self):
                return []

            def close(self) -> None:
                state["response_closed"] = True

        class FakeConnection:
            def __init__(self, *args, **kwargs):
                pass

            def request(self, *args, **kwargs):
                pass

            def getresponse(self):
                return FakeResponse()

            def close(self) -> None:
                state["connection_closed"] = True

        target = LiveTarget("http", "127.0.0.1", 80, "127.0.0.1", "127.0.0.1", "/v1/models")
        with patch("bbrab_provider_validator.http_client.http.client.HTTPConnection", FakeConnection):
            with self.assertRaisesRegex(TransportError, "byte limit"):
                request_json("http://127.0.0.1/v1/models", method="GET", headers={}, target=target, max_response_bytes=5)
        self.assertTrue(state["response_closed"])
        self.assertTrue(state["connection_closed"])

    def test_http_exception_is_wrapped_without_original_text(self) -> None:
        class FailingConnection:
            def __init__(self, *args, **kwargs):
                pass

            def request(self, *args, **kwargs):
                raise http.client.HTTPException("Cookie: private-cookie")

            def close(self) -> None:
                pass

        target = LiveTarget("http", "127.0.0.1", 80, "127.0.0.1", "127.0.0.1", "/v1/models")
        with patch("bbrab_provider_validator.http_client.http.client.HTTPConnection", FailingConnection):
            with self.assertRaises(TransportError) as caught:
                request_json("http://127.0.0.1/v1/models", method="GET", headers={}, target=target)
        self.assertEqual("provider transport failed", str(caught.exception))

    def test_redirect_is_returned_and_never_followed(self) -> None:
        calls = []

        class RedirectResponse:
            status = 302

            def read(self, amount: int) -> bytes:
                return b'{"error":{"message":"redirect denied"}}'

            def getheaders(self):
                return [("Location", "https://attacker.invalid/")]

            def close(self) -> None:
                pass

        class DirectConnection:
            def __init__(self, host, port, timeout):
                calls.append((host, port))

            def request(self, *args, **kwargs):
                pass

            def getresponse(self):
                return RedirectResponse()

            def close(self) -> None:
                pass

        target = LiveTarget("http", "localhost", 80, "127.0.0.1", "localhost", "/v1/models")
        with patch.dict(os.environ, {"HTTP_PROXY": "http://attacker.invalid:8080"}), patch(
            "bbrab_provider_validator.http_client.http.client.HTTPConnection", DirectConnection
        ):
            response = request_json("http://localhost/v1/models", method="GET", headers={}, target=target)
        self.assertEqual(302, response.status)
        self.assertEqual([("127.0.0.1", 80)], calls)

    def test_https_pin_keeps_original_tls_hostname(self) -> None:
        observed = {}

        class RawSocket:
            def close(self):
                observed["raw_closed"] = True

        class Context:
            def wrap_socket(self, raw, *, server_hostname):
                observed["server_hostname"] = server_hostname
                observed["raw"] = raw
                return object()

        target = LiveTarget("https", "api.example.test", 443, "203.0.113.8", "api.example.test", "/v1/models")
        with patch("bbrab_provider_validator.http_client.ssl.create_default_context", return_value=Context()), patch(
            "bbrab_provider_validator.http_client.socket.create_connection", return_value=RawSocket()
        ) as create_connection:
            connection = _PinnedHTTPSConnection(target, timeout=2.0)
            connection.connect()
        create_connection.assert_called_once_with(("203.0.113.8", 443), 2.0, None)
        self.assertEqual("api.example.test", observed["server_hostname"])


class _ProviderHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, dict, str]] = []
    secret = "local-mock-secret"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, status: int, body: dict) -> None:
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Provider-Environment", "test")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        self.requests.append((self.path, {}, self.headers.get("Authorization", "")))
        self._send(200, {"data": [{"id": "mock-chat"}]})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        self.requests.append((self.path, body, self.headers.get("Authorization", "")))
        if body["model"] == "bbrab-validator-intentionally-invalid-model":
            self._send(404, {"error": {"message": f"unknown model; debug={self.secret}", "type": "invalid_request_error"}})
        else:
            self._send(200, {
                "choices": [{"message": {"role": "assistant", "content": "OK"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
            })


class LiveMockTests(unittest.TestCase):
    def test_local_mock_exercises_live_http_without_provider_cost(self) -> None:
        _ProviderHandler.requests = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ProviderHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = {
                "schema_version": 1,
                "provider": {"name": "mock", "base_url": f"http://127.0.0.1:{server.server_port}/v1", "environment": "test", "model": "mock-chat"},
                "credential": {"env": "MOCK_TEST_API_KEY", "environment": "test", "auth": "bearer"},
                "isolation": {"allowed_hosts": ["127.0.0.1"], "response_environment_header": "X-Provider-Environment"},
                "probe": {"max_tokens": 4, "normal_request_max_tokens": 64},
            }
            with TemporaryDirectory() as directory, patch.dict(os.environ, {
                "MOCK_TEST_API_KEY": _ProviderHandler.secret,
                "HTTP_PROXY": "http://attacker.invalid:8080",
                "HTTPS_PROXY": "http://attacker.invalid:8080",
                "ALL_PROXY": "http://attacker.invalid:8080",
            }):
                config_path = Path(directory) / "config.json"
                report_path = Path(directory) / "report.json"
                config_path.write_text(json.dumps(config))
                with redirect_stdout(io.StringIO()):
                    rc = main(["validate", "--config", str(config_path), "--live", "--acknowledge-provider-cost", "--report-json", str(report_path)])
                self.assertEqual(0, rc)
                rendered = report_path.read_text()
                self.assertNotIn(_ProviderHandler.secret, rendered)
                self.assertIn("MOCK_TEST_API_KEY", rendered)
            self.assertEqual(3, len(_ProviderHandler.requests))
            self.assertEqual(["/v1/models", "/v1/chat/completions", "/v1/chat/completions"], [item[0] for item in _ProviderHandler.requests])
            self.assertEqual("mock-chat", _ProviderHandler.requests[1][1]["model"])
            self.assertEqual(4, _ProviderHandler.requests[1][1]["max_tokens"])
            self.assertTrue(all(item[2] == f"Bearer {_ProviderHandler.secret}" for item in _ProviderHandler.requests))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
