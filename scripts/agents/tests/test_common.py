import json
import subprocess
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from scripts.agents.common import (
    MAX_ISSUES_PER_WINDOW,
    STATIC_ANALYSIS_MARKER,
    AIProviderConfig,
    GitHubClient,
    GitHubClientError,
    build_marker,
    can_create_issue,
    find_issue_with_marker,
    generate_summary,
    requires_human_intervention,
)
from scripts.agents.tests.fakes import FakeGitHubClient


class RequiresHumanInterventionTests(unittest.TestCase):
    def test_flags_gossip_path(self) -> None:
        self.assertTrue(requires_human_intervention(["civicmesh/gossip/membership.py"]))

    def test_flags_pubsub_path(self) -> None:
        self.assertTrue(requires_human_intervention(["civicmesh/pubsub/topics.py"]))

    def test_does_not_flag_unrelated_path(self) -> None:
        self.assertFalse(requires_human_intervention(["README.md", "docs/git-flow.md"]))

    def test_empty_list_is_false(self) -> None:
        self.assertFalse(requires_human_intervention([]))


class BuildMarkerTests(unittest.TestCase):
    def test_marker_is_stable_for_same_inputs(self) -> None:
        self.assertEqual(build_marker("documenter", "missing-changelog"), build_marker("documenter", "missing-changelog"))

    def test_marker_differs_by_agent(self) -> None:
        self.assertNotEqual(build_marker("documenter", "x"), build_marker("bug_reviewer", "x"))


class AIProviderConfigTests(unittest.TestCase):
    def test_not_configured_without_url_or_key(self) -> None:
        config = AIProviderConfig(api_url=None, api_key=None, model=None)
        self.assertFalse(config.is_configured())

    def test_configured_with_url_and_key(self) -> None:
        config = AIProviderConfig(api_url="https://example.invalid", api_key="k", model="m")
        self.assertTrue(config.is_configured())

    def test_call_returns_none_when_not_configured(self) -> None:
        config = AIProviderConfig(api_url=None, api_key=None, model=None)
        self.assertIsNone(config.call("prompt"))

    def test_call_returns_text_on_success(self) -> None:
        config = AIProviderConfig(api_url="https://example.invalid", api_key="k", model="m")
        fake_response = MagicMock()
        fake_response.__enter__.return_value = fake_response
        fake_response.read.return_value = json.dumps({"output": "hola"}).encode("utf-8")
        with patch("scripts.agents.common.urllib.request.urlopen", return_value=fake_response):
            self.assertEqual(config.call("prompt"), "hola")

    def test_call_returns_none_on_url_error(self) -> None:
        config = AIProviderConfig(api_url="https://example.invalid", api_key="k", model="m")
        with patch("scripts.agents.common.urllib.request.urlopen", side_effect=urllib.error.URLError("boom")):
            self.assertIsNone(config.call("prompt"))

    def test_call_returns_none_on_timeout(self) -> None:
        config = AIProviderConfig(api_url="https://example.invalid", api_key="k", model="m")
        with patch("scripts.agents.common.urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            self.assertIsNone(config.call("prompt"))

    def test_call_returns_none_on_invalid_json(self) -> None:
        config = AIProviderConfig(api_url="https://example.invalid", api_key="k", model="m")
        fake_response = MagicMock()
        fake_response.__enter__.return_value = fake_response
        fake_response.read.return_value = b"not json"
        with patch("scripts.agents.common.urllib.request.urlopen", return_value=fake_response):
            self.assertIsNone(config.call("prompt"))

    def test_call_returns_none_on_incomplete_response(self) -> None:
        config = AIProviderConfig(api_url="https://example.invalid", api_key="k", model="m")
        fake_response = MagicMock()
        fake_response.__enter__.return_value = fake_response
        fake_response.read.return_value = json.dumps({"other": "x"}).encode("utf-8")
        with patch("scripts.agents.common.urllib.request.urlopen", return_value=fake_response):
            self.assertIsNone(config.call("prompt"))

    def test_call_never_raises_even_on_failure(self) -> None:
        config = AIProviderConfig(api_url="https://example.invalid", api_key="super-secret-key", model="m")
        with patch("scripts.agents.common.urllib.request.urlopen", side_effect=urllib.error.URLError("boom")):
            try:
                result = config.call("prompt")
            except Exception as exc:  # pragma: no cover - no debería ocurrir
                self.fail(f"call() no debe lanzar excepciones: {exc}")
            self.assertIsNone(result)


class GenerateSummaryTests(unittest.TestCase):
    def test_uses_static_fallback_when_not_configured(self) -> None:
        config = AIProviderConfig(api_url=None, api_key=None, model=None)
        result = generate_summary("prompt", "detalle estatico", config=config)
        self.assertIn(STATIC_ANALYSIS_MARKER, result)
        self.assertIn("detalle estatico", result)

    def test_uses_provider_output_when_available(self) -> None:
        config = AIProviderConfig(api_url="https://example.invalid", api_key="k", model="m")
        with patch.object(AIProviderConfig, "call", return_value="resumen generado"):
            result = generate_summary("prompt", "detalle estatico", config=config)
        self.assertEqual(result, "resumen generado")

    def test_falls_back_when_provider_returns_none(self) -> None:
        config = AIProviderConfig(api_url="https://example.invalid", api_key="k", model="m")
        with patch.object(AIProviderConfig, "call", return_value=None):
            result = generate_summary("prompt", "detalle estatico", config=config)
        self.assertIn(STATIC_ANALYSIS_MARKER, result)


class GitHubClientRunTests(unittest.TestCase):
    def test_gh_not_found_raises_client_error(self) -> None:
        client = GitHubClient()
        with patch("scripts.agents.common.subprocess.run", side_effect=FileNotFoundError()):
            with self.assertRaises(GitHubClientError):
                client.list_issues(["x"])

    def test_gh_timeout_raises_client_error(self) -> None:
        client = GitHubClient()
        with patch("scripts.agents.common.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=1)):
            with self.assertRaises(GitHubClientError):
                client.list_issues(["x"])

    def test_nonzero_exit_raises_client_error_without_leaking_secrets(self) -> None:
        client = GitHubClient()
        fake_result = MagicMock(returncode=1, stdout="", stderr="permission denied")
        with patch("scripts.agents.common.subprocess.run", return_value=fake_result):
            with self.assertRaises(GitHubClientError) as ctx:
                client.list_issues(["x"])
        self.assertNotIn("ghp_", str(ctx.exception))

    def test_invalid_json_raises_client_error(self) -> None:
        client = GitHubClient()
        fake_result = MagicMock(returncode=0, stdout="not json", stderr="")
        with patch("scripts.agents.common.subprocess.run", return_value=fake_result):
            with self.assertRaises(GitHubClientError):
                client.list_issues(["x"])


class FindIssueWithMarkerTests(unittest.TestCase):
    def test_finds_existing_marker(self) -> None:
        client = FakeGitHubClient()
        marker = build_marker("documenter", "missing-changelog")
        client.add_existing_issue("t", f"{marker}\nbody", ["agent-documenter"])
        found = find_issue_with_marker(client, ["agent-documenter"], marker)
        self.assertIsNotNone(found)

    def test_returns_none_when_marker_absent(self) -> None:
        client = FakeGitHubClient()
        marker = build_marker("documenter", "missing-changelog")
        found = find_issue_with_marker(client, ["agent-documenter"], marker)
        self.assertIsNone(found)

    def test_returns_none_when_github_query_fails(self) -> None:
        client = FakeGitHubClient(fail_methods={"list_issues"})
        marker = build_marker("documenter", "x")
        found = find_issue_with_marker(client, ["agent-documenter"], marker)
        self.assertIsNone(found)


class CanCreateIssueTests(unittest.TestCase):
    def test_true_when_under_limit(self) -> None:
        client = FakeGitHubClient()
        self.assertTrue(can_create_issue(client, ["agent-documenter"]))

    def test_false_when_at_limit_within_window(self) -> None:
        client = FakeGitHubClient()
        for _ in range(MAX_ISSUES_PER_WINDOW):
            client.add_existing_issue("t", "b", ["agent-documenter"])
        self.assertFalse(can_create_issue(client, ["agent-documenter"]))

    def test_true_when_old_issues_are_outside_window(self) -> None:
        client = FakeGitHubClient()
        old_date = "2000-01-01T00:00:00+00:00"
        for _ in range(MAX_ISSUES_PER_WINDOW):
            client.add_existing_issue("t", "b", ["agent-documenter"], created_at=old_date)
        self.assertTrue(can_create_issue(client, ["agent-documenter"]))

    def test_fail_closed_when_github_query_fails(self) -> None:
        client = FakeGitHubClient(fail_methods={"list_issues"})
        self.assertFalse(can_create_issue(client, ["agent-documenter"]))


if __name__ == "__main__":
    unittest.main()
