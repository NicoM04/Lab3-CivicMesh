import tempfile
import unittest
from pathlib import Path

from scripts.agents import documenter
from scripts.agents.common import AIProviderConfig, HUMAN_INTERVENTION_NOTICE, build_marker
from scripts.agents.tests.fakes import FakeGitHubClient

_NO_PROVIDER = AIProviderConfig(api_url=None, api_key=None, model=None)


class ReadmeFindingsTests(unittest.TestCase):
    def test_missing_readme_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            findings = documenter.find_readme_findings(Path(tmp))
        self.assertEqual([f.key for f in findings], ["missing-readme"])

    def test_minimal_readme_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "README.md").write_text("# Title\n", encoding="utf-8")
            findings = documenter.find_readme_findings(Path(tmp))
        self.assertEqual([f.key for f in findings], ["readme-min-content"])

    def test_adequate_readme_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content = "\n".join(f"line {i}" for i in range(10))
            (Path(tmp) / "README.md").write_text(content, encoding="utf-8")
            findings = documenter.find_readme_findings(Path(tmp))
        self.assertEqual(findings, [])


class ChangelogFindingsTests(unittest.TestCase):
    def test_missing_changelog_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            findings = documenter.find_changelog_findings(Path(tmp))
        self.assertEqual(len(findings), 1)

    def test_existing_changelog_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
            findings = documenter.find_changelog_findings(Path(tmp))
        self.assertEqual(findings, [])


class BrokenLinkFindingsTests(unittest.TestCase):
    def test_flags_broken_relative_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("Ver [docs](docs/nope.md).\n", encoding="utf-8")
            findings = documenter.find_broken_link_findings(root)
        self.assertEqual(len(findings), 1)
        self.assertIn("docs/nope.md", findings[0].detail)

    def test_does_not_flag_existing_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "real.md").write_text("x", encoding="utf-8")
            (root / "README.md").write_text("Ver [docs](docs/real.md).\n", encoding="utf-8")
            findings = documenter.find_broken_link_findings(root)
        self.assertEqual(findings, [])

    def test_ignores_external_urls_and_anchors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("Ver [ext](https://example.com) y [seccion](#intro).\n", encoding="utf-8")
            findings = documenter.find_broken_link_findings(root)
        self.assertEqual(findings, [])


class UndocumentedPackageFindingsTests(unittest.TestCase):
    def test_flags_package_without_docstring(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "civicmesh" / "gossip"
            pkg.mkdir(parents=True)
            (pkg / "__init__.py").write_text("x = 1\n", encoding="utf-8")
            findings = documenter.find_undocumented_package_findings(root)
        self.assertEqual(len(findings), 1)

    def test_does_not_flag_package_with_docstring(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "civicmesh"
            pkg.mkdir(parents=True)
            (pkg / "__init__.py").write_text('"""Doc."""\n', encoding="utf-8")
            findings = documenter.find_undocumented_package_findings(root)
        self.assertEqual(findings, [])

    def test_no_civicmesh_dir_returns_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            findings = documenter.find_undocumented_package_findings(Path(tmp))
        self.assertEqual(findings, [])


class HumanInterventionFlagTests(unittest.TestCase):
    def test_gossip_path_is_flagged_human(self) -> None:
        finding = documenter.Finding(key="k", title="t", detail="d", paths=("civicmesh/gossip/x.py",))
        self.assertTrue(finding.human_intervention)

    def test_docs_path_is_not_flagged_human(self) -> None:
        finding = documenter.Finding(key="k", title="t", detail="d", paths=("README.md",))
        self.assertFalse(finding.human_intervention)


class RenderIssueBodyTests(unittest.TestCase):
    def test_includes_marker_and_detail(self) -> None:
        finding = documenter.Finding(key="missing-changelog", title="t", detail="detalle", paths=("CHANGELOG.md",))
        body = documenter.render_issue_body(finding, config=_NO_PROVIDER)
        self.assertIn(build_marker("documenter", "missing-changelog"), body)
        self.assertIn("detalle", body)

    def test_includes_human_notice_when_applicable(self) -> None:
        finding = documenter.Finding(key="k", title="t", detail="d", paths=("civicmesh/pubsub/x.py",))
        body = documenter.render_issue_body(finding, config=_NO_PROVIDER)
        self.assertIn(HUMAN_INTERVENTION_NOTICE, body)

    def test_no_human_notice_for_mechanical_finding(self) -> None:
        finding = documenter.Finding(key="k", title="t", detail="d", paths=("README.md",))
        body = documenter.render_issue_body(finding, config=_NO_PROVIDER)
        self.assertNotIn(HUMAN_INTERVENTION_NOTICE, body)


class RunTests(unittest.TestCase):
    def test_dry_run_creates_no_issues(self) -> None:
        client = FakeGitHubClient()
        with tempfile.TemporaryDirectory() as tmp:
            documenter.run(Path(tmp), dry_run=True, client=client)
        self.assertEqual(client.issues, [])

    def test_creates_issues_for_new_findings(self) -> None:
        client = FakeGitHubClient()
        with tempfile.TemporaryDirectory() as tmp:
            documenter.run(Path(tmp), dry_run=False, client=client)
        self.assertGreaterEqual(len(client.issues), 1)

    def test_does_not_duplicate_existing_finding(self) -> None:
        client = FakeGitHubClient()
        marker = build_marker("documenter", "missing-changelog")
        client.add_existing_issue("Falta CHANGELOG.md", marker, ["agent-documenter", "documentation"])
        with tempfile.TemporaryDirectory() as tmp:
            documenter.run(Path(tmp), dry_run=False, client=client)
        changelog_issues = [i for i in client.issues if marker in i["body"]]
        self.assertEqual(len(changelog_issues), 1)

    def test_fail_closed_when_limit_cannot_be_verified(self) -> None:
        client = FakeGitHubClient(fail_methods={"list_issues"})
        with tempfile.TemporaryDirectory() as tmp:
            documenter.run(Path(tmp), dry_run=False, client=client)
        self.assertEqual(client.issues, [])


if __name__ == "__main__":
    unittest.main()
