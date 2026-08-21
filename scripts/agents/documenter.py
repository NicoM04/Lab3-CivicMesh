"""Agente Documentador de CivicMesh.

Revisa `README.md`, `CHANGELOG.md` y `docs/` en busca de documentación
faltante, referencias obsoletas (links locales rotos) y paquetes públicos de
`civicmesh/` sin docstring de módulo. Por cada hallazgo nuevo (deduplicado
por un marcador estable) crea un issue con las etiquetas `agent-documenter`
y `documentation`, respetando un límite de issues por ventana de tiempo y un
comportamiento fail-closed si no puede verificar ese límite contra GitHub.

Este agente NUNCA modifica archivos, nunca aprueba ni fusiona nada: solo
reporta. Ver `scripts/agents/README.md` para el detalle completo.

Uso:
    python -m scripts.agents.documenter            # crea issues reales
    python -m scripts.agents.documenter --dry-run   # solo imprime, no crea nada
"""

from __future__ import annotations

import argparse
import re
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

AGENT_NAME = "documenter"
LABELS = ["agent-documenter", "documentation"]

_MIN_README_LINES = 5
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


@dataclass(frozen=True)
class Finding:
    key: str
    title: str
    detail: str
    paths: tuple[str, ...]

    @property
    def human_intervention(self) -> bool:
        return requires_human_intervention(self.paths)


def _non_empty_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def find_readme_findings(repo_root: Path) -> list[Finding]:
    readme = repo_root / "README.md"
    if not readme.exists():
        return [Finding(key="missing-readme", title="Falta README.md", detail="El repositorio no tiene README.md.", paths=("README.md",))]
    content = readme.read_text(encoding="utf-8")
    if len(_non_empty_lines(content)) < _MIN_README_LINES:
        return [
            Finding(
                key="readme-min-content",
                title="README.md no documenta el proyecto todavía",
                detail=(
                    "README.md existe pero tiene contenido mínimo "
                    f"(menos de {_MIN_README_LINES} líneas no vacías). "
                    "Debería explicar al menos: descripción, arquitectura general, "
                    "roles/responsabilidades y cómo correr el proyecto."
                ),
                paths=("README.md",),
            )
        ]
    return []


def find_changelog_findings(repo_root: Path) -> list[Finding]:
    changelog = repo_root / "CHANGELOG.md"
    if not changelog.exists():
        return [
            Finding(
                key="missing-changelog",
                title="Falta CHANGELOG.md",
                detail="El repositorio no tiene CHANGELOG.md (formato Keep a Changelog).",
                paths=("CHANGELOG.md",),
            )
        ]
    return []


def find_broken_link_findings(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    candidates = [repo_root / "README.md"]
    docs_dir = repo_root / "docs"
    if docs_dir.is_dir():
        candidates.extend(sorted(docs_dir.glob("*.md")))

    for md_file in candidates:
        if not md_file.exists():
            continue
        content = md_file.read_text(encoding="utf-8")
        for match in _MARKDOWN_LINK_RE.finditer(content):
            target = match.group(1)
            if "://" in target or target.startswith("#") or target.startswith("mailto:"):
                continue
            target_path = (md_file.parent / target.split("#", 1)[0]).resolve()
            try:
                target_path.relative_to(repo_root.resolve())
            except ValueError:
                continue  # fuera del repo, no es responsabilidad de este chequeo
            if not target_path.exists():
                rel_source = md_file.relative_to(repo_root)
                findings.append(
                    Finding(
                        key=f"broken-link:{rel_source}:{target}",
                        title=f"Referencia obsoleta en {rel_source}",
                        detail=f"{rel_source} enlaza a '{target}', que no existe en el repositorio.",
                        paths=(str(rel_source),),
                    )
                )
    return findings


def find_undocumented_package_findings(repo_root: Path) -> list[Finding]:
    civicmesh_dir = repo_root / "civicmesh"
    if not civicmesh_dir.is_dir():
        return []
    findings: list[Finding] = []
    for init_file in sorted(civicmesh_dir.rglob("__init__.py")):
        content = init_file.read_text(encoding="utf-8")
        stripped = content.lstrip()
        has_docstring = stripped.startswith('"""') or stripped.startswith("'''")
        if not has_docstring:
            rel = init_file.relative_to(repo_root)
            findings.append(
                Finding(
                    key=f"undocumented-package:{rel}",
                    title=f"Paquete sin documentación: {rel.parent}",
                    detail=f"{rel} no tiene un docstring de módulo que explique el propósito del paquete.",
                    paths=(str(rel),),
                )
            )
    return findings


def collect_findings(repo_root: Path) -> list[Finding]:
    return [
        *find_readme_findings(repo_root),
        *find_changelog_findings(repo_root),
        *find_broken_link_findings(repo_root),
        *find_undocumented_package_findings(repo_root),
    ]


def render_issue_body(finding: Finding, config: AIProviderConfig | None = None) -> str:
    marker = build_marker(AGENT_NAME, finding.key)
    summary = generate_summary(
        prompt=f"Hallazgo de documentación en CivicMesh: {finding.title}\n{finding.detail}",
        static_fallback=finding.detail,
        config=config,
    )
    lines = [marker, "", summary]
    if finding.human_intervention:
        lines += ["", "Requiere intervención humana"]
    lines += ["", "---", "Generado automáticamente por el agente Documentador (scripts/agents/documenter.py)."]
    return "\n".join(lines)


def run(repo_root: Path, dry_run: bool, client: GitHubClient | None = None) -> int:
    client = client or GitHubClient()
    config = AIProviderConfig.from_env()
    findings = collect_findings(repo_root)

    if not findings:
        print("[documenter] sin hallazgos.")
        return 0

    created = 0
    for finding in findings:
        marker = build_marker(AGENT_NAME, finding.key)
        existing = find_issue_with_marker(client, LABELS, marker)
        if existing:
            print(f"[documenter] ya existe issue para '{finding.key}' (dedup), se omite.")
            continue

        if dry_run:
            print(f"[documenter][dry-run] crearía issue: {finding.title}")
            continue

        if not can_create_issue(client, LABELS):
            print("[documenter] límite de issues alcanzado o no verificable (fail-closed): no se crean más issues en esta corrida.")
            break

        body = render_issue_body(finding, config)
        client.create_issue(title=finding.title, body=body, labels=LABELS)
        created += 1
        print(f"[documenter] issue creado: {finding.title}")

    print(f"[documenter] hallazgos: {len(findings)}, issues creados: {created}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agente Documentador de CivicMesh")
    parser.add_argument("--dry-run", action="store_true", help="No crea issues, solo imprime lo que haría")
    parser.add_argument("--repo-root", default=".", help="Raíz del repositorio a inspeccionar")
    args = parser.parse_args(argv)
    return run(Path(args.repo_root).resolve(), dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
