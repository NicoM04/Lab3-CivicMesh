"""Agente Revisor de Pull Requests de CivicMesh.

Se dispara vía `workflow_run` cuando el workflow de CI (`ci.yml`) termina.
Solo actúa si:

- el `workflow_run` que lo disparó corresponde a un evento `pull_request`
  (no a un `push` directo a `main`), y
- su `conclusion` es exactamente `"success"`.

En cualquier otro caso no comenta nada: nunca antes del resultado de CI, y
nunca sobre una corrida en rojo. Publica un único comentario por PR y por
commit (deduplicado por SHA) resumiendo: resultado de CI, archivos
cambiados, y si el diff toca código de protocolo/semántica distribuida
(en cuyo caso agrega "Requiere intervención humana"). El comentario siempre
recuerda que el merge y la aprobación son responsabilidad humana. Este
agente NUNCA aprueba ni fusiona nada — solo tiene permiso para comentar.

Uso (normalmente invocado por `.github/workflows/agent-pr-reviewer.yml`):
    python -m scripts.agents.pr_reviewer
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.agents.common import (
    GitHubClient,
    build_marker,
    requires_human_intervention,
)

AGENT_NAME = "pr_reviewer"
_MAX_FILES_LISTED = 25


@dataclass(frozen=True)
class WorkflowRunEvent:
    conclusion: str | None
    triggering_event: str | None
    head_sha: str | None
    pull_request_numbers: tuple[int, ...]


def parse_workflow_run_event(raw: dict) -> WorkflowRunEvent:
    """Extrae los campos relevantes del payload de un evento `workflow_run`.

    Nunca lanza excepción por claves faltantes: ante datos incompletos
    devuelve un evento "vacío" que :func:`should_review` tratará como "no
    comentar" (más seguro que asumir éxito).
    """
    workflow_run = raw.get("workflow_run") if isinstance(raw, dict) else None
    if not isinstance(workflow_run, dict):
        return WorkflowRunEvent(conclusion=None, triggering_event=None, head_sha=None, pull_request_numbers=())

    pull_requests = workflow_run.get("pull_requests") or []
    numbers = tuple(pr.get("number") for pr in pull_requests if isinstance(pr, dict) and pr.get("number") is not None)

    return WorkflowRunEvent(
        conclusion=workflow_run.get("conclusion"),
        triggering_event=workflow_run.get("event"),
        head_sha=workflow_run.get("head_sha"),
        pull_request_numbers=numbers,
    )


def should_review(event: WorkflowRunEvent) -> bool:
    """``True`` solo si el CI de una Pull Request terminó exitosamente."""
    return event.triggering_event == "pull_request" and event.conclusion == "success"


def resolve_pr_number(event: WorkflowRunEvent, client: GitHubClient) -> int | None:
    """Número de PR asociado al `workflow_run`.

    El payload de `workflow_run` puede traer `pull_requests` vacío (p. ej.
    para PRs desde forks); en ese caso se hace un fallback de búsqueda por
    SHA. Devuelve ``None`` si no se pudo determinar (no comentar es más
    seguro que adivinar sobre qué PR comentar).
    """
    if event.pull_request_numbers:
        return event.pull_request_numbers[0]
    if not event.head_sha:
        return None
    try:
        return client.find_pr_by_commit(event.head_sha)
    except Exception:  # noqa: BLE001 - fail-closed: cualquier error de red/CLI => no comentar
        return None


def build_review_comment(pr_number: int, head_sha: str, changed_files: list[str]) -> str:
    marker = build_marker(AGENT_NAME, head_sha)
    human_review_needed = requires_human_intervention(changed_files)

    listed_files = changed_files[:_MAX_FILES_LISTED]
    files_block = "\n".join(f"- `{path}`" for path in listed_files) or "_(no se pudo obtener la lista de archivos cambiados)_"
    if len(changed_files) > _MAX_FILES_LISTED:
        files_block += f"\n- _(+{len(changed_files) - _MAX_FILES_LISTED} archivos más)_"

    nature = (
        "Este cambio toca código de protocolo/semántica distribuida (Gossip, membership, "
        "Pub/Sub, forwarding, TTL, prioridad o similar)."
        if human_review_needed
        else "A primera vista, el cambio parece mecánico (documentación, tests, configuración u otro código no ligado a protocolo/semántica distribuida)."
    )

    lines = [
        marker,
        "### Resultado de CI",
        "CI (`tests`) terminó en verde para este commit.",
        "",
        "### Archivos cambiados",
        files_block,
        "",
        "### Riesgos / naturaleza del cambio",
        nature,
    ]
    if human_review_needed:
        lines += ["", "Requiere intervención humana"]
    lines += [
        "",
        "---",
        "El merge y la aprobación son responsabilidad humana: este comentario es solo "
        "informativo y no constituye una aprobación. Generado automáticamente por el "
        "agente Revisor de Pull Requests (scripts/agents/pr_reviewer.py).",
    ]
    return "\n".join(lines)


def already_commented(client: GitHubClient, pr_number: int, head_sha: str) -> bool:
    marker = build_marker(AGENT_NAME, head_sha)
    try:
        comments = client.list_pr_comments(pr_number)
    except Exception:  # noqa: BLE001 - fail-closed: si no se puede verificar, no se duplica el intento de comentar
        return True
    return any(marker in (comment.get("body") or "") for comment in comments)


def run(event_path: Path, dry_run: bool, client: GitHubClient | None = None) -> int:
    client = client or GitHubClient()

    if not event_path.exists():
        print(f"[pr_reviewer] no se encontró el evento en {event_path}; no se comenta nada.")
        return 0

    try:
        raw_event = json.loads(event_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("[pr_reviewer] evento con JSON inválido; no se comenta nada.")
        return 0

    event = parse_workflow_run_event(raw_event)
    if not should_review(event):
        print(f"[pr_reviewer] nada que hacer (event={event.triggering_event!r}, conclusion={event.conclusion!r}).")
        return 0

    pr_number = resolve_pr_number(event, client)
    if pr_number is None:
        print("[pr_reviewer] no se pudo determinar el número de PR asociado; no se comenta nada.")
        return 0

    if not event.head_sha:
        print("[pr_reviewer] evento sin head_sha; no se comenta nada.")
        return 0

    if already_commented(client, pr_number, event.head_sha):
        print(f"[pr_reviewer] ya existe comentario para PR #{pr_number} en {event.head_sha} (dedup), se omite.")
        return 0

    try:
        changed_files = client.changed_files(pr_number)
    except Exception:  # noqa: BLE001 - sin la lista de archivos igual se puede comentar el resultado de CI
        changed_files = []

    comment = build_review_comment(pr_number, event.head_sha, changed_files)

    if dry_run:
        print(f"[pr_reviewer][dry-run] comentaría PR #{pr_number}:\n{comment}")
        return 0

    client.create_pr_comment(pr_number, comment)
    print(f"[pr_reviewer] comentario publicado en PR #{pr_number}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agente Revisor de Pull Requests de CivicMesh")
    parser.add_argument("--dry-run", action="store_true", help="No comenta, solo imprime lo que haría")
    parser.add_argument(
        "--event-path",
        default=os.environ.get("GITHUB_EVENT_PATH", ""),
        help="Ruta al JSON del evento workflow_run (por defecto, GITHUB_EVENT_PATH)",
    )
    args = parser.parse_args(argv)
    if not args.event_path:
        print("[pr_reviewer] no hay GITHUB_EVENT_PATH ni --event-path; nada que hacer.")
        return 0
    return run(Path(args.event_path), dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
