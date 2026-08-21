import tempfile
import unittest
from pathlib import Path

from scripts.agents import bug_reviewer
from scripts.agents.tests.fakes import FakeGitHubClient


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class BareExceptTests(unittest.TestCase):
    def test_flags_bare_except(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "civicmesh/x.py", "try:\n    pass\nexcept:\n    pass\n")
            findings = bug_reviewer.find_bare_except_findings(root)
        self.assertEqual(len(findings), 1)

    def test_does_not_flag_typed_except(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "civicmesh/x.py", "try:\n    pass\nexcept ValueError:\n    pass\n")
            findings = bug_reviewer.find_bare_except_findings(root)
        self.assertEqual(findings, [])


class GlobalRandomTests(unittest.TestCase):
    def test_flags_module_level_random_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "civicmesh/gossip/x.py", "import random\n\ndef pick(items):\n    return random.choice(items)\n")
            findings = bug_reviewer.find_global_random_findings(root)
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0].human_intervention)

    def test_does_not_flag_random_random_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root,
                "civicmesh/gossip/x.py",
                "import random\n\ndef pick(items, rng=None):\n    rng = rng or random.Random()\n    return rng.choice(items)\n",
            )
            findings = bug_reviewer.find_global_random_findings(root)
        self.assertEqual(findings, [])


class MissingTestFindingsTests(unittest.TestCase):
    def test_flags_module_without_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "civicmesh/gossip/peer.py", "x = 1\n")
            findings = bug_reviewer.find_missing_test_findings(root)
        self.assertEqual(len(findings), 1)

    def test_does_not_flag_module_with_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "civicmesh/gossip/peer.py", "x = 1\n")
            _write(root, "tests/gossip/test_peer.py", "x = 1\n")
            findings = bug_reviewer.find_missing_test_findings(root)
        self.assertEqual(findings, [])

    def test_ignores_init_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "civicmesh/__init__.py", "")
            findings = bug_reviewer.find_missing_test_findings(root)
        self.assertEqual(findings, [])


class UnclosedResourceTests(unittest.TestCase):
    def test_flags_open_outside_with(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "civicmesh/x.py", "f = open('a.txt')\n")
            findings = bug_reviewer.find_unclosed_resource_findings(root)
        self.assertEqual(len(findings), 1)

    def test_does_not_flag_open_inside_with(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "civicmesh/x.py", "with open('a.txt') as f:\n    pass\n")
            findings = bug_reviewer.find_unclosed_resource_findings(root)
        self.assertEqual(findings, [])


class UnusedParameterTests(unittest.TestCase):
    def test_flags_unused_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "civicmesh/x.py", "def foo(a, b):\n    return a\n")
            findings = bug_reviewer.find_unused_parameter_findings(root)
        self.assertEqual(len(findings), 1)

    def test_does_not_flag_used_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "civicmesh/x.py", "def foo(a, b):\n    return a + b\n")
            findings = bug_reviewer.find_unused_parameter_findings(root)
        self.assertEqual(findings, [])

    def test_does_not_flag_protocol_stub_methods(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "civicmesh/x.py", "class P:\n    def send(self, target, payload) -> None:\n        ...\n")
            findings = bug_reviewer.find_unused_parameter_findings(root)
        self.assertEqual(findings, [])

    def test_does_not_flag_underscore_prefixed_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "civicmesh/x.py", "def foo(a, _b):\n    return a\n")
            findings = bug_reviewer.find_unused_parameter_findings(root)
        self.assertEqual(findings, [])


class RunTests(unittest.TestCase):
    def test_no_findings_when_no_civicmesh_dir(self) -> None:
        client = FakeGitHubClient()
        with tempfile.TemporaryDirectory() as tmp:
            bug_reviewer.run(Path(tmp), dry_run=False, client=client)
        self.assertEqual(client.issues, [])

    def test_dry_run_creates_no_issues(self) -> None:
        client = FakeGitHubClient()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "civicmesh/x.py", "try:\n    pass\nexcept:\n    pass\n")
            bug_reviewer.run(root, dry_run=True, client=client)
        self.assertEqual(client.issues, [])

    def test_fail_closed_when_limit_cannot_be_verified(self) -> None:
        client = FakeGitHubClient(fail_methods={"list_issues"})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "civicmesh/x.py", "try:\n    pass\nexcept:\n    pass\n")
            bug_reviewer.run(root, dry_run=False, client=client)
        self.assertEqual(client.issues, [])


if __name__ == "__main__":
    unittest.main()
