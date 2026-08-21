"""Utilidades compartidas por los tres agentes automatizados de CivicMesh.

Estos agentes son auxiliares (ver ``scripts/agents/README.md``): nunca
aprueban ni fusionan Pull Requests, nunca hacen push directo a ``main``, y
nunca deciden por sí mismos cambios de protocolo o semántica distribuida
(Gossip, membership, timeout/fallos, Pub/Sub, ``should_forward``, TTL,
prioridad, modelos estadísticos). Este módulo concentra:

- acceso a la CLI ``gh`` para leer/crear issues y comentar Pull Requests,
  con manejo explícito de errores (timeouts, JSON inválido, `gh` ausente)
  y sin filtrar nunca secrets en los mensajes de error;
- una interfaz opcional a un proveedor de IA configurado por variables de
  entorno (``AGENT_API_URL``, ``AGENT_API_KEY``, ``AGENT_MODEL``), con
  fallback determinista a análisis estático si no hay proveedor
  configurado o si la llamada falla por cualquier motivo;
- deduplicación (marcador estable embebido en el cuerpo) y límite de
  issues automáticos por agente, con comportamiento fail-closed si no se
  puede verificar el estado real en GitHub.

Ningún secret real se versiona en este repositorio: ``AGENT_API_URL`` /
``AGENT_API_KEY`` / ``AGENT_MODEL`` se leen exclusivamente de variables de
entorno (pensadas para completarse como GitHub Actions secrets), y el
repositorio no contiene ningún valor real para ellas.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

STATIC_ANALYSIS_MARKER = "ANÁLISIS ESTÁTICO (sin modelo de IA disponible)"
HUMAN_INTERVENTION_NOTICE = "Requiere intervención humana"

# Fragmentos de ruta que identifican código de protocolo/semántica
# distribuida. La lista es deliberadamente amplia: un falso positivo (marcar
# "requiere intervención humana" de más) es preferible a uno negativo.
PROTOCOL_SENSITIVE_PATH_FRAGMENTS: tuple[str, ...] = (
    "gossip",
    "membership",
    "pubsub",
    "pub_sub",
    "should_forward",
    "forwarding",
    "ttl",
    "priority",
    "replay",
    "seed",
    "rng",
)

MAX_ISSUES_PER_WINDOW = 5
ISSUE_WINDOW_DAYS = 7
MARKER_PREFIX = "civicmesh-agent-marker"

_DEFAULT_TIMEOUT_SECONDS = 20.0


def requires_human_intervention(paths: list[str] | tuple[str, ...]) -> bool:
    """``True`` si alguna ruta toca código de protocolo/semántica distribuida.

    Usado por los tres agentes para decidir si un finding/PR debe llevar la
    leyenda :data:`HUMAN_INTERVENTION_NOTICE` en vez de tratarse como un
    cambio mecánico.
    """
    lowered = [p.lower() for p in paths]
    return any(
        fragment in path
        for path in lowered
        for fragment in PROTOCOL_SENSITIVE_PATH_FRAGMENTS
    )


def build_marker(agent: str, key: str) -> str:
    """Marcador estable embebible en un cuerpo de issue/comentario para
    deduplicación. Dos findings con el mismo ``agent``+``key`` producen
    siempre el mismo marcador, sin depender de IDs de GitHub.
    """
    return f"<!-- {MARKER_PREFIX}:{agent}:{key} -->"


# --------------------------------------------------------------------------
# Proveedor de IA opcional (fallback determinista si no está configurado)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AIProviderConfig:
    """Configuración de un proveedor generativo externo, leída de variables
    de entorno. Ninguna de ellas tiene un valor real versionado en este
    repositorio.
    """

    api_url: str | None
    api_key: str | None
    model: str | None

    @staticmethod
    def from_env() -> "AIProviderConfig":
        return AIProviderConfig(
            api_url=os.environ.get("AGENT_API_URL") or None,
            api_key=os.environ.get("AGENT_API_KEY") or None,
            model=os.environ.get("AGENT_MODEL") or None,
        )

    def is_configured(self) -> bool:
        return bool(self.api_url and self.api_key)

    def call(self, prompt: str, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> str | None:
        """Intenta obtener una respuesta del proveedor configurado.

        Devuelve ``None`` ante cualquier error (URL/red, timeout, HTTP no
        exitoso, JSON inválido o respuesta incompleta) en vez de propagar
        la excepción: una falla de un proveedor externo nunca debe romper
        el flujo principal del agente. El mensaje de error registrado nunca
        incluye ``api_key`` ni el cuerpo de la petición/respuesta.
        """
        if not self.is_configured():
            return None
        payload = json.dumps({"model": self.model, "prompt": prompt}).encode("utf-8")
        request = urllib.request.Request(
            self.api_url,  # type: ignore[arg-type]
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw_body = response.read()
                data = json.loads(raw_body.decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"[agents] proveedor de IA no disponible ({type(exc).__name__})")
            return None
        except json.JSONDecodeError:
            print("[agents] proveedor de IA devolvió una respuesta con JSON inválido")
            return None

        text = data.get("output") if isinstance(data, dict) else None
        if not isinstance(text, str) or not text.strip():
            print("[agents] proveedor de IA devolvió una respuesta incompleta")
            return None
        return text.strip()


def generate_summary(prompt: str, static_fallback: str, config: AIProviderConfig | None = None) -> str:
    """Texto de resumen para un finding/comentario.

    Si hay un proveedor de IA configurado y responde correctamente, se usa
    su salida tal cual. En cualquier otro caso (no configurado, o falla por
    el motivo que sea) se usa ``static_fallback``, siempre precedido del
    marcador :data:`STATIC_ANALYSIS_MARKER` para que la salida sea
    transparente sobre su origen y nunca se atribuya a un modelo que no
    generó el resultado.
    """
    config = config or AIProviderConfig.from_env()
    if config.is_configured():
        result = config.call(prompt)
        if result:
            return result
    return f"{STATIC_ANALYSIS_MARKER}\n\n{static_fallback}"


def load_prompt(name: str) -> str:
    """Lee ``scripts/agents/prompts/{name}.md`` (relativo a este archivo)."""
    prompt_path = Path(__file__).parent / "prompts" / f"{name}.md"
    return prompt_path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Cliente GitHub (vía `gh`), con fail-closed explícito ante cualquier error
# --------------------------------------------------------------------------


class GitHubClientError(Exception):
    """Error al invocar la CLI `gh`. El mensaje nunca incluye secrets."""


class GitHubClient:
    """Wrapper mínimo sobre la CLI `gh`, pensado para ser reemplazado por un
    fake en tests (ninguno de los agentes debería necesitar red/GitHub real
    para correr su suite de tests).
    """

    def __init__(self, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self.timeout = timeout

    def _run(self, args: list[str]) -> str:
        try:
            result = subprocess.run(
                ["gh", *args],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise GitHubClientError("la CLI 'gh' no está disponible en este entorno") from exc
        except subprocess.TimeoutExpired as exc:
            raise GitHubClientError(f"'gh {args[0]}' agotó el tiempo de espera") from exc
        except OSError as exc:
            raise GitHubClientError(f"error de sistema ejecutando 'gh {args[0]}': {type(exc).__name__}") from exc

        if result.returncode != 0:
            # stderr de `gh` puede incluir detalles útiles, pero nunca un
            # token: `gh` se autentica vía GH_TOKEN de entorno, no vía
            # argumentos de línea de comandos.
            raise GitHubClientError(f"'gh {args[0]}' terminó con código {result.returncode}: {result.stderr.strip()[:500]}")
        return result.stdout

    def list_issues(self, labels: list[str], state: str = "open", limit: int = 100) -> list[dict]:
        args = ["issue", "list", "--state", state, "--limit", str(limit), "--json", "number,title,body,createdAt,labels"]
        for label in labels:
            args.extend(["--label", label])
        raw = self._run(args)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GitHubClientError("respuesta no-JSON de 'gh issue list'") from exc
        if not isinstance(data, list):
            raise GitHubClientError("formato inesperado de 'gh issue list'")
        return data

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict:
        args = ["issue", "create", "--title", title, "--body", body]
        for label in labels:
            args.extend(["--label", label])
        raw = self._run(args)
        url = raw.strip().splitlines()[-1] if raw.strip() else ""
        return {"url": url}

    def list_pr_comments(self, pr_number: int) -> list[dict]:
        raw = self._run(["pr", "view", str(pr_number), "--json", "comments"])
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GitHubClientError("respuesta no-JSON de 'gh pr view'") from exc
        return data.get("comments", []) if isinstance(data, dict) else []

    def create_pr_comment(self, pr_number: int, body: str) -> None:
        self._run(["pr", "comment", str(pr_number), "--body", body])

    def find_pr_by_commit(self, sha: str) -> int | None:
        raw = self._run(["pr", "list", "--state", "all", "--search", f"{sha}", "--json", "number,headRefOid", "--limit", "20"])
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GitHubClientError("respuesta no-JSON de 'gh pr list'") from exc
        if not isinstance(data, list):
            return None
        for pr in data:
            if pr.get("headRefOid") == sha:
                return pr.get("number")
        return None

    def changed_files(self, pr_number: int) -> list[str]:
        raw = self._run(["pr", "diff", str(pr_number), "--name-only"])
        return [line.strip() for line in raw.splitlines() if line.strip()]


# --------------------------------------------------------------------------
# Deduplicación y límite de issues automáticos (fail-closed)
# --------------------------------------------------------------------------


def find_issue_with_marker(client: GitHubClient, labels: list[str], marker: str) -> dict | None:
    """Busca, entre los issues abiertos con ``labels``, uno cuyo cuerpo ya
    contenga ``marker``. Devuelve ``None`` si no hay ninguno o si la
    consulta a GitHub falla (fail-closed: ante la duda, no se duplica pero
    tampoco se asume que ya existe; ver :func:`can_create_issue`, que es
    quien realmente bloquea la creación ante fallas de GitHub).
    """
    try:
        issues = client.list_issues(labels)
    except GitHubClientError:
        return None
    for issue in issues:
        if marker in (issue.get("body") or ""):
            return issue
    return None


def can_create_issue(
    client: GitHubClient,
    labels: list[str],
    max_issues: int = MAX_ISSUES_PER_WINDOW,
    window_days: int = ISSUE_WINDOW_DAYS,
) -> bool:
    """``True`` solo si se pudo consultar GitHub y el conteo de issues
    recientes con ``labels`` está por debajo de ``max_issues``.

    Fail-closed: si la consulta a GitHub falla por cualquier motivo (CLI
    ausente, timeout, JSON inválido, error de la API), se devuelve
    ``False`` y no se crean issues nuevos en esa corrida.
    """
    from datetime import datetime, timedelta, timezone

    try:
        issues = client.list_issues(labels, limit=100)
    except GitHubClientError:
        return False

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    recent_count = 0
    for issue in issues:
        created_at_raw = issue.get("createdAt")
        if not created_at_raw:
            continue
        try:
            created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if created_at >= cutoff:
            recent_count += 1
    return recent_count < max_issues
