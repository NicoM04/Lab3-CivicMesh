import json
import tempfile
import unittest
from pathlib import Path

from scripts.agents import pr_reviewer
from scripts.agents.common import HUMAN_INTERVENTION_NOTICE, build_marker
from scripts.agents.tests.fakes import FakeGitHubClient


def _workflow_run_event(conclusion="success", event="pull_request", head_sha="abc123", pr_numbers=(7,)) -> dict:
    return {
        "workflow_run": {
            "conclusion": conclusion,
            "event": event,
            "head_sha": head_sha,
            "pull_requests": [{"number": n} for n in pr_numbers],
        }
    }


class ParseWorkflowRunEventTests(unittest.TestCase):
    def test_parses_full_event(self) -> None:
        event = pr_reviewer.parse_workflow_run_event(_workflow_run_event())
        self.assertEqual(event.conclusion, "success")
        self.assertEqual(event.triggering_event, "pull_request")
        self.assertEqual(event.head_sha, "abc123")
        self.assertEqual(event.pull_request_numbers, (7,))

    def test_missing_workflow_run_key_is_safe(self) -> None:
        event = pr_reviewer.parse_workflow_run_event({})
        self.assertIsNone(event.conclusion)
        self.assertEqual(event.pull_request_numbers, ())

    def test_empty_pull_requests_list(self) -> None:
        raw = _workflow_run_event(pr_numbers=())
        event = pr_reviewer.parse_workflow_run_event(raw)
        self.assertEqual(event.pull_request_numbers, ())


class ShouldReviewTests(unittest.TestCase):
    def test_true_for_successful_pr_run(self) -> None:
        event = pr_reviewer.parse_workflow_run_event(_workflow_run_event())
        self.assertTrue(pr_reviewer.should_review(event))

    def test_false_when_ci_failed(self) -> None:
        event = pr_reviewer.parse_workflow_run_event(_workflow_run_event(conclusion="failure"))
        self.assertFalse(pr_reviewer.should_review(event))

    def test_false_when_not_pull_request_event(self) -> None:
        event = pr_reviewer.parse_workflow_run_event(_workflow_run_event(event="push"))
        self.assertFalse(pr_reviewer.should_review(event))

    def test_false_when_conclusion_missing(self) -> None:
        event = pr_reviewer.parse_workflow_run_event({})
        self.assertFalse(pr_reviewer.should_review(event))


class ResolvePrNumberTests(unittest.TestCase):
    def test_uses_pull_requests_list_when_present(self) -> None:
        client = FakeGitHubClient()
        event = pr_reviewer.parse_workflow_run_event(_workflow_run_event(pr_numbers=(42,)))
        self.assertEqual(pr_reviewer.resolve_pr_number(event, client), 42)

    def test_falls_back_to_commit_search_when_empty(self) -> None:
        client = FakeGitHubClient()
        client.pr_by_commit["abc123"] = 99
        event = pr_reviewer.parse_workflow_run_event(_workflow_run_event(pr_numbers=()))
        self.assertEqual(pr_reviewer.resolve_pr_number(event, client), 99)

    def test_returns_none_when_unresolvable(self) -> None:
        client = FakeGitHubClient()
        event = pr_reviewer.parse_workflow_run_event(_workflow_run_event(pr_numbers=()))
        self.assertIsNone(pr_reviewer.resolve_pr_number(event, client))

    def test_returns_none_when_commit_search_fails(self) -> None:
        client = FakeGitHubClient(fail_methods={"find_pr_by_commit"})
        event = pr_reviewer.parse_workflow_run_event(_workflow_run_event(pr_numbers=()))
        self.assertIsNone(pr_reviewer.resolve_pr_number(event, client))


class BuildReviewCommentTests(unittest.TestCase):
    def test_mechanical_change_has_no_human_notice(self) -> None:
        comment = pr_reviewer.build_review_comment(1, "sha1", ["README.md", "docs/git-flow.md"])
        self.assertNotIn(HUMAN_INTERVENTION_NOTICE, comment)

    def test_protocol_change_has_human_notice(self) -> None:
        comment = pr_reviewer.build_review_comment(1, "sha1", ["civicmesh/gossip/membership.py"])
        self.assertIn(HUMAN_INTERVENTION_NOTICE, comment)

    def test_always_reminds_merge_is_human_responsibility(self) -> None:
        comment = pr_reviewer.build_review_comment(1, "sha1", ["README.md"])
        self.assertIn("responsabilidad humana", comment)

    def test_includes_marker_for_dedup(self) -> None:
        comment = pr_reviewer.build_review_comment(1, "sha1", [])
        self.assertIn(build_marker("pr_reviewer", "sha1"), comment)

    def test_truncates_long_file_lists(self) -> None:
        many_files = [f"file_{i}.py" for i in range(40)]
        comment = pr_reviewer.build_review_comment(1, "sha1", many_files)
        self.assertIn("archivos más", comment)


class AlreadyCommentedTests(unittest.TestCase):
    def test_false_when_no_prior_comment(self) -> None:
        client = FakeGitHubClient()
        self.assertFalse(pr_reviewer.already_commented(client, 1, "sha1"))

    def test_true_when_marker_present(self) -> None:
        client = FakeGitHubClient()
        marker = build_marker("pr_reviewer", "sha1")
        client.pr_comments[1] = [{"body": f"{marker}\nhola"}]
        self.assertTrue(pr_reviewer.already_commented(client, 1, "sha1"))

    def test_fail_closed_true_when_cannot_verify(self) -> None:
        client = FakeGitHubClient(fail_methods={"list_pr_comments"})
        self.assertTrue(pr_reviewer.already_commented(client, 1, "sha1"))


class RunTests(unittest.TestCase):
    def _write_event(self, tmp_dir: str, raw: dict) -> Path:
        event_path = Path(tmp_dir) / "event.json"
        event_path.write_text(json.dumps(raw), encoding="utf-8")
        return event_path

    def test_comments_on_successful_pr_run(self) -> None:
        client = FakeGitHubClient()
        client.pr_files[7] = ["README.md"]
        with tempfile.TemporaryDirectory() as tmp:
            event_path = self._write_event(tmp, _workflow_run_event())
            pr_reviewer.run(event_path, dry_run=False, client=client)
        self.assertEqual(len(client.pr_comments.get(7, [])), 1)

    def test_does_not_comment_when_ci_failed(self) -> None:
        client = FakeGitHubClient()
        with tempfile.TemporaryDirectory() as tmp:
            event_path = self._write_event(tmp, _workflow_run_event(conclusion="failure"))
            pr_reviewer.run(event_path, dry_run=False, client=client)
        self.assertEqual(client.pr_comments, {})

    def test_does_not_comment_when_not_pull_request_event(self) -> None:
        client = FakeGitHubClient()
        with tempfile.TemporaryDirectory() as tmp:
            event_path = self._write_event(tmp, _workflow_run_event(event="push"))
            pr_reviewer.run(event_path, dry_run=False, client=client)
        self.assertEqual(client.pr_comments, {})

    def test_does_not_duplicate_comment_for_same_sha(self) -> None:
        client = FakeGitHubClient()
        marker = build_marker("pr_reviewer", "abc123")
        client.pr_comments[7] = [{"body": marker}]
        with tempfile.TemporaryDirectory() as tmp:
            event_path = self._write_event(tmp, _workflow_run_event())
            pr_reviewer.run(event_path, dry_run=False, client=client)
        self.assertEqual(len(client.pr_comments[7]), 1)

    def test_missing_event_file_does_nothing(self) -> None:
        client = FakeGitHubClient()
        pr_reviewer.run(Path("/nonexistent/event.json"), dry_run=False, client=client)
        self.assertEqual(client.pr_comments, {})

    def test_invalid_json_does_nothing(self) -> None:
        client = FakeGitHubClient()
        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "event.json"
            event_path.write_text("not json", encoding="utf-8")
            pr_reviewer.run(event_path, dry_run=False, client=client)
        self.assertEqual(client.pr_comments, {})

    def test_dry_run_does_not_comment(self) -> None:
        client = FakeGitHubClient()
        with tempfile.TemporaryDirectory() as tmp:
            event_path = self._write_event(tmp, _workflow_run_event())
            pr_reviewer.run(event_path, dry_run=True, client=client)
        self.assertEqual(client.pr_comments, {})


if __name__ == "__main__":
    unittest.main()
