import io
import unittest
from unittest.mock import patch
import urllib.error

import echo_beta1 as echo


class CalculatorTests(unittest.TestCase):
    def test_basic_math(self):
        self.assertEqual(echo.safe_calculate("12 * (4 + 3)"), 84)
        self.assertEqual(echo.safe_calculate("-5 + 2"), -3)
        self.assertEqual(echo.safe_calculate("2 ** 3"), 8)

    def test_divide_by_zero(self):
        with self.assertRaises(ZeroDivisionError):
            echo.safe_calculate("1 / 0")

    def test_blocks_python_expressions(self):
        with self.assertRaises(ValueError):
            echo.safe_calculate("__import__('os').system('echo unsafe')")

    def test_limits_exponents(self):
        with self.assertRaises(ValueError):
            echo.safe_calculate("2 ** 99")


class CommandTests(unittest.TestCase):
    def test_local_commands_route_even_with_api_key(self):
        with patch.object(echo, "API_KEY", "test-key"):
            result = echo.call_model([{"role": "user", "content": "/calc 12 * (4 + 3)"}])
        self.assertEqual(result, "Result: 84")

    def test_help(self):
        self.assertIn("/calc", echo.local_reply("/help"))

    def test_study_requires_topic(self):
        self.assertIn("Usage:", echo.local_reply("/study"))

    def test_summarize_requires_text(self):
        self.assertIn("Usage:", echo.local_reply("/summarize"))


class ApiDiagnosticTests(unittest.TestCase):
    def test_cloudflare_1010_is_reported_without_claiming_wrong_key(self):
        details = echo._clean_provider_error("<html>Cloudflare Error 1010</html>")
        message = echo._describe_api_error(403, details)
        self.assertIn("Error 1010", details)
        self.assertIn("does not by itself", message)

    def test_401_has_auth_diagnostic(self):
        self.assertIn("Authentication failed", echo._describe_api_error(401))

    def test_request_uses_descriptive_user_agent_and_reports_cloudflare_1010(self):
        secret = "api-key-test-secret"
        def blocked(request, timeout):
            self.assertEqual(request.get_header("User-agent"), echo.USER_AGENT)
            self.assertEqual(timeout, 45)
            body = io.BytesIO(b"<html>Cloudflare Error 1010</html>")
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, body)

        with patch("echo_beta1.urllib.request.urlopen", side_effect=blocked):
            result = echo.call_model(
                [{"role": "user", "content": "Hi"}],
                api_key=secret,
                api_url="https://api.groq.com/openai/v1/chat/completions",
                model="example-model",
            )
        self.assertIn("Cloudflare Error 1010", result)
        self.assertNotIn(secret, result)

    def test_api_key_is_redacted_from_error_detail(self):
        secret = "sk-test-dont-show"
        cleaned = echo._clean_provider_error('{"error":{"message":"bad key sk-test-dont-show"}}', secret)
        self.assertNotIn(secret, cleaned)
        self.assertIn("[REDACTED API KEY]", cleaned)


if __name__ == "__main__":
    unittest.main(verbosity=2)
