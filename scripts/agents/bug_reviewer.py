"""Agente Revisor de Bugs de CivicMesh.

Analiza estáticamente (vía `ast`, sin ejecutar nada) el código bajo
`civicmesh/` en busca de problemas verificables: `except` sin tipo, uso de
`random.*` global en vez de un `random.Random` inyectado, código sin test
asociado bajo `tests/`, recursos (`open`/sockets) abiertos fuera de un
bloque `with`, y parámetros de función que nunca se referencian en su
cuerpo. Por cada hallazgo nuevo (deduplicado) crea un issue con las
etiquetas `agent-bug-reviewer` y `bug`, respetando el mismo límite y
comportamiento fail-closed que el Documentador.

Este agente NUNCA modifica código ni intenta corregir nada, y NUNCA decide
por sí mismo sobre cambios de protocolo/semántica distribuida: esos
hallazgos se marcan explícitamente como "Requiere intervención humana".

Uso:
    python -m scripts.agents.bug_reviewer            # crea issues reales
    python -m scripts.agents.bug_reviewer --dry-run   # solo imprime
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.agents.common import (
    AIProviderConfig,
    GitHubClient,
    build_marker,
    can_create_issue,
    find_issue_with_marker,
    generate_summary,
    requires_human_intervention,
)

AGENT_NAME = "bug_reviewer"
LABELS = ["agent-bug-reviewer", "bug"]

_RANDOM_MODULE_FUNCS = {"random", "randint", "sample", "choice", "shuffle", "uniform", "randrange", "seed"}
_RESOURCE_FUNCS_BARE = {"open"}
_RESOURCE_FUNCS_ATTR = {"socket", "create_connection"}


@dataclass(frozen=True)
class Finding:
    key: str
    title: str
    detail: str
    paths: tuple[str, ...]

    @property
    def human_intervention(self) -> bool:
        return requires_human_intervention(self.paths)


def _iter_python_files(civicmesh_dir: Path):
    return sorted(civicmesh_dir.rglob("*.py"))


def _parse(py_file: Path) -> ast.Module | None:
    try:
        return ast.parse(py_file.read_text(encoding="utf-8"))
    except SyntaxError:
        return None


def find_bare_except_findings(repo_root: Path) -> list[Finding]:
    civicmesh_dir = repo_root / "civicmesh"
    if not civicmesh_dir.is_dir():
        return []
    findings: list[Finding] = []
    for py_file in _iter_python_files(civicmesh_dir):
        tree = _parse(py_file)
        if tree is None:
            continue
        rel = py_file.relative_to(repo_root)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                findings.append(
                    Finding(
                        key=f"bare-except:{rel}:{node.lineno}",
                        title=f"except sin tipo en {rel}:{node.lineno}",
                        detail=f"{rel}:{node.lineno} usa 'except:' sin especificar el tipo de excepción; puede ocultar errores inesperados.",
                        paths=(str(rel),),
                    )
                )
    return findings


def find_global_random_findings(repo_root: Path) -> list[Finding]:
    civicmesh_dir = repo_root / "civicmesh"
    if not civicmesh_dir.is_dir():
        return []
    findings: list[Finding] = []
    for py_file in _iter_python_files(civicmesh_dir):
        tree = _parse(py_file)
        if tree is None:
            continue
        rel = py_file.relative_to(repo_root)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _RANDOM_MODULE_FUNCS
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "random"
            ):
                findings.append(
                    Finding(
                        key=f"global-random:{rel}:{node.lineno}",
                        title=f"Uso de random.{node.func.attr}() sin RNG inyectado en {rel}:{node.lineno}",
                        detail=(
                            f"{rel}:{node.lineno} llama a random.{node.func.attr}() directamente. "
                            "La convención del proyecto es inyectar random.Random(seed) para mantener "
                            "el comportamiento determinista y testeable."
                        ),
                        paths=(str(rel),),
                    )
                )
    return findings


def find_missing_test_findings(repo_root: Path) -> list[Finding]:
    civicmesh_dir = repo_root / "civicmesh"
    if not civicmesh_dir.is_dir():
        return []
    tests_dir = repo_root / "tests"
    existing_test_stems = set()
    if tests_dir.is_dir():
        existing_test_stems = {p.stem.lower() for p in tests_dir.rglob("test_*.py")}

    findings: list[Finding] = []
    for py_file in _iter_python_files(civicmesh_dir):
        if py_file.name == "__init__.py":
            continue
        stem = py_file.stem.lower()
        expected_fragment = f"test_{stem}"
        if not any(expected_fragment in existing for existing in existing_test_stems):
            rel = py_file.relative_to(repo_root)
            findings.append(
                Finding(
                    key=f"missing-test:{rel}",
                    title=f"Código sin test asociado: {rel}",
                    detail=f"No se encontró un archivo bajo tests/ que corresponda a '{stem}'.",
                    paths=(str(rel),),
                )
            )
    return findings


def _is_resource_call(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name) and func.id in _RESOURCE_FUNCS_BARE:
        return True
    if isinstance(func, ast.Attribute) and func.attr in _RESOURCE_FUNCS_ATTR:
        return True
    return False


def find_unclosed_resource_findings(repo_root: Path) -> list[Finding]:
    civicmesh_dir = repo_root / "civicmesh"
    if not civicmesh_dir.is_dir():
        return []
    findings: list[Finding] = []
    for py_file in _iter_python_files(civicmesh_dir):
        tree = _parse(py_file)
        if tree is None:
            continue
        protected_ids: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.With):
                for item in node.items:
                    for sub in ast.walk(item.context_expr):
                        if isinstance(sub, ast.Call):
                            protected_ids.add(id(sub))
        rel = py_file.relative_to(repo_root)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_resource_call(node) and id(node) not in protected_ids:
                findings.append(
                    Finding(
                        key=f"unclosed-resource:{rel}:{node.lineno}",
                        title=f"Posible recurso sin cierre garantizado en {rel}:{node.lineno}",
                        detail=f"{rel}:{node.lineno} abre un recurso (archivo/socket) fuera de un bloque 'with'.",
                        paths=(str(rel),),
                    )
                )
    return findings


def _is_stub_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """``True`` si el cuerpo es solo docstring/``pass``/``...`` (stub de
    interfaz/Protocol), donde parámetros "sin usar" son esperables."""
    for stmt in node.body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            if stmt.value.value is ... or isinstance(stmt.value.value, str):
                continue
        return False
    return True


def find_unused_parameter_findings(repo_root: Path) -> list[Finding]:
    civicmesh_dir = repo_root / "civicmesh"
    if not civicmesh_dir.is_dir():
        return []
    findings: list[Finding] = []
    for py_file in _iter_python_files(civicmesh_dir):
        tree = _parse(py_file)
        if tree is None:
            continue
        rel = py_file.relative_to(repo_root)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _is_stub_function(node):
                continue
            used_names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            params = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
            for param in params:
                if param.startswith("_"):
                    continue
                if param not in used_names:
                    findings.append(
                        Finding(
                            key=f"unused-param:{rel}:{node.name}:{param}",
                            title=f"Parámetro posiblemente ignorado: {node.name}({param}) en {rel}",
                            detail=f"{rel}: la función '{node.name}' recibe '{param}' pero no se referencia en su cuerpo.",
                            paths=(str(rel),),
                        )
                    )
    return findings


def collect_findings(repo_root: Path) -> list[Finding]:
    return [
        *find_bare_except_findings(repo_root),
        *find_global_random_findings(repo_root),
        *find_missing_test_findings(repo_root),
        *find_unclosed_resource_findings(repo_root),
        *find_unused_parameter_findings(repo_root),
    ]


def render_issue_body(finding: Finding, config: AIProviderConfig | None = None) -> str:
    marker = build_marker(AGENT_NAME, finding.key)
    summary = generate_summary(
        prompt=f"Hallazgo de revisión de bugs en CivicMesh: {finding.title}\n{finding.detail}",
        static_fallback=finding.detail,
        config=config,
    )
    lines = [marker, "", summary]
    if finding.human_intervention:
        lines += ["", "Requiere intervención humana"]
    lines += ["", "---", "Generado automáticamente por el agente Revisor de Bugs (scripts/agents/bug_reviewer.py)."]
    return "\n".join(lines)


def run(repo_root: Path, dry_run: bool, client: GitHubClient | None = None) -> int:
    client = client or GitHubClient()
    config = AIProviderConfig.from_env()
    findings = collect_findings(repo_root)

    if not findings:
        print("[bug_reviewer] sin hallazgos.")
        return 0

    created = 0
    for finding in findings:
        marker = build_marker(AGENT_NAME, finding.key)
        existing = find_issue_with_marker(client, LABELS, marker)
        if existing:
            print(f"[bug_reviewer] ya existe issue para '{finding.key}' (dedup), se omite.")
            continue

        if dry_run:
            print(f"[bug_reviewer][dry-run] crearía issue: {finding.title}")
            continue

        if not can_create_issue(client, LABELS):
            print("[bug_reviewer] límite de issues alcanzado o no verificable (fail-closed): no se crean más issues en esta corrida.")
            break

        body = render_issue_body(finding, config)
        client.create_issue(title=finding.title, body=body, labels=LABELS)
        created += 1
        print(f"[bug_reviewer] issue creado: {finding.title}")

    print(f"[bug_reviewer] hallazgos: {len(findings)}, issues creados: {created}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agente Revisor de Bugs de CivicMesh")
    parser.add_argument("--dry-run", action="store_true", help="No crea issues, solo imprime lo que haría")
    parser.add_argument("--repo-root", default=".", help="Raíz del repositorio a inspeccionar")
    args = parser.parse_args(argv)
    return run(Path(args.repo_root).resolve(), dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
