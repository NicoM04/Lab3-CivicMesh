"""Fake de GitHubClient para tests de agentes: nunca toca la red ni GitHub
real. No es un módulo de tests en sí (sin prefijo `test_`), es un helper
compartido por los que sí lo son.
"""

from __future__ import annotations

from datetime import datetime, timezone

from scripts.agents.common import GitHubClientError


class FakeGitHubClient:
    """Implementa la misma interfaz que ``GitHubClient``, en memoria.

    ``fail_methods`` simula fallas de GitHub (CLI ausente, timeout, error de
    API) para poder testear el comportamiento fail-closed de los agentes.
    """

    def __init__(self, fail_methods: set[str] | None = None) -> None:
        self.issues: list[dict] = []
        self.pr_comments: dict[int, list[dict]] = {}
        self.pr_files: dict[int, list[str]] = {}
        self.pr_by_commit: dict[str, int] = {}
        self._next_issue_number = 1
        self._fail_methods = fail_methods or set()

    def _maybe_fail(self, name: str) -> None:
        if name in self._fail_methods:
            raise GitHubClientError(f"fallo simulado en {name}")

    def add_existing_issue(self, title: str, body: str, labels: list[str], created_at: str | None = None) -> dict:
        issue = {
            "number": self._next_issue_number,
            "title": title,
            "body": body,
            "createdAt": created_at or datetime.now(timezone.utc).isoformat(),
            "labels_set": set(labels),
        }
        self._next_issue_number += 1
        self.issues.append(issue)
        return issue

    def list_issues(self, labels: list[str], state: str = "open", limit: int = 100) -> list[dict]:
        self._maybe_fail("list_issues")
        label_set = set(labels)
        return [issue for issue in self.issues if label_set.issubset(issue["labels_set"])]

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict:
        self._maybe_fail("create_issue")
        return self.add_existing_issue(title, body, labels)

    def list_pr_comments(self, pr_number: int) -> list[dict]:
        self._maybe_fail("list_pr_comments")
        return self.pr_comments.get(pr_number, [])

    def create_pr_comment(self, pr_number: int, body: str) -> None:
        self._maybe_fail("create_pr_comment")
        self.pr_comments.setdefault(pr_number, []).append({"body": body})

    def find_pr_by_commit(self, sha: str) -> int | None:
        self._maybe_fail("find_pr_by_commit")
        return self.pr_by_commit.get(sha)

    def changed_files(self, pr_number: int) -> list[str]:
        self._maybe_fail("changed_files")
        return self.pr_files.get(pr_number, [])
